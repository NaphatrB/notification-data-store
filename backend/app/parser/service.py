"""Main parser service — synchronous polling loop."""

import logging
import time
from datetime import datetime, timezone

from pydantic import ValidationError
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.models import RawEvent
from app.parser.candidate_filter import is_pricing_candidate
from app.parser.config import (
    LLM_ENDPOINT,
    LLM_MODEL,
    PARSER_APP_FILTER,
    PARSER_BATCH_SIZE,
    PARSER_NAME,
    PARSER_PACKAGE_FILTER,
    PARSER_SOURCE_FILTER,
    PARSER_TEXT_FILTER_ENABLED,
    PARSER_VERSION,
    POLL_INTERVAL_SECONDS,
    RAW_DATABASE_URL,
)
from app.parser.dead_letter import insert_dead_letter
from app.parser.llm_client import call_llm
from app.parser.metrics import (
    batch_latency,
    dead_letter_total,
    failed_total,
    oldest_unprocessed,
    processed_total,
    start_metrics_server,
)
from app.parser.offset import get_current_offset, reset_offset, update_offset
from app.parser.persistence import persist_extraction
from app.parser.schemas import PricingExtraction

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def _build_sync_url(url: str) -> str:
    """Convert async DB URL to sync for the parser's synchronous loop."""
    return url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")


def _get_combined_text(event: RawEvent) -> str:
    """Combine text fields into a single string for dead-letter snapshot."""
    parts = []
    if event.title:
        parts.append(f"Title: {event.title}")
    if event.text:
        parts.append(f"Text: {event.text}")
    if event.big_text:
        parts.append(f"BigText: {event.big_text}")
    return "\n".join(parts) if parts else ""


def _process_event(session: Session, event: RawEvent) -> bool:
    """Process a single raw event. Returns True on success, False on failure."""
    # Check if candidate for pricing extraction
    if not is_pricing_candidate(
        event.source_type, event.package_name, event.app_name,
        event.title, event.text, event.big_text,
    ):
        logger.debug("Skipped non-candidate seq=%d", event.seq)
        processed_total.inc()
        return True

    logger.info("Processing pricing candidate seq=%d", event.seq)

    # Call LLM (first attempt)
    llm_response = call_llm(event.title, event.text, event.big_text)

    if llm_response is None:
        # Retry once
        logger.warning("LLM failed for seq=%d, retrying...", event.seq)
        llm_response = call_llm(event.title, event.text, event.big_text)

    if llm_response is None:
        # Both attempts failed — dead-letter
        insert_dead_letter(
            session,
            raw_event_id=event.id,
            seq=event.seq,
            error_type="llm_error",
            error_message="LLM failed after 2 attempts",
            llm_raw_response=None,
            original_text=_get_combined_text(event),
        )
        dead_letter_total.inc()
        failed_total.inc()
        return True  # Don't block pipeline

    # Validate LLM output
    try:
        extraction = PricingExtraction.model_validate(llm_response)
    except ValidationError as e:
        # Retry LLM once on validation failure
        logger.warning("Validation failed for seq=%d: %s. Retrying LLM...", event.seq, e)
        llm_response_retry = call_llm(event.title, event.text, event.big_text)

        if llm_response_retry is not None:
            try:
                extraction = PricingExtraction.model_validate(llm_response_retry)
                llm_response = llm_response_retry
            except ValidationError as e2:
                insert_dead_letter(
                    session,
                    raw_event_id=event.id,
                    seq=event.seq,
                    error_type="validation_error",
                    error_message=str(e2),
                    llm_raw_response=llm_response_retry,
                    original_text=_get_combined_text(event),
                )
                dead_letter_total.inc()
                failed_total.inc()
                return True
        else:
            insert_dead_letter(
                session,
                raw_event_id=event.id,
                seq=event.seq,
                error_type="validation_error",
                error_message=str(e),
                llm_raw_response=llm_response,
                original_text=_get_combined_text(event),
            )
            dead_letter_total.inc()
            failed_total.inc()
            return True

    # Optional: check total_kg consistency
    if not extraction.check_total_kg_consistency():
        logger.warning(
            "total_kg inconsistency for seq=%d (total_kg=%.2f, items_sum=%.2f)",
            event.seq,
            extraction.total_kg,
            sum(item.quantity_kg for item in extraction.items),
        )

    # Persist extraction
    persist_extraction(
        session,
        raw_event_id=event.id,
        seq=event.seq,
        event_timestamp=event.event_timestamp,
        extraction=extraction,
        llm_raw_response=llm_response,
    )

    processed_total.inc()
    return True


def _update_oldest_unprocessed_metric(session: Session, last_seq: int) -> None:
    """Update the gauge for oldest unprocessed event age."""
    stmt = select(func.min(RawEvent.received_at)).where(RawEvent.seq > last_seq)
    oldest = session.execute(stmt).scalar_one_or_none()
    if oldest is not None:
        age = (datetime.now(timezone.utc) - oldest).total_seconds()
        oldest_unprocessed.set(max(0, age))
    else:
        oldest_unprocessed.set(0)


def run(reset_offset_flag: bool = False) -> None:
    """Main entry point — synchronous polling loop."""
    # Convert async URL to sync
    sync_url = _build_sync_url(RAW_DATABASE_URL)
    engine = create_engine(sync_url, echo=False)
    SessionFactory = sessionmaker(bind=engine)

    logger.info("Parser '%s' (version=%s) starting", PARSER_NAME, PARSER_VERSION)
    logger.info("DB: %s", sync_url.split("@")[-1])  # Log host only, not credentials
    logger.info("LLM: %s (model=%s)", LLM_ENDPOINT, LLM_MODEL)
    logger.info("Batch size: %d, poll interval: %ds", PARSER_BATCH_SIZE, POLL_INTERVAL_SECONDS)
    logger.info(
        "Filters — source: %s, package: %s, app: %s, text_heuristic: %s",
        PARSER_SOURCE_FILTER or "(all)",
        PARSER_PACKAGE_FILTER or "(all)",
        PARSER_APP_FILTER or "(all)",
        PARSER_TEXT_FILTER_ENABLED,
    )

    # Start Prometheus metrics server
    start_metrics_server()

    with SessionFactory() as session:
        # Handle offset reset
        if reset_offset_flag:
            reset_offset(session, PARSER_NAME)
            logger.info("Offset reset to 0 — will reprocess all events")

        # Main polling loop
        while True:
            try:
                current_seq = get_current_offset(session, PARSER_NAME)
                logger.info("Polling from seq > %d", current_seq)

                # Fetch batch — apply SQL-level metadata filters
                stmt = (
                    select(RawEvent)
                    .where(RawEvent.seq > current_seq)
                )
                if PARSER_SOURCE_FILTER:
                    stmt = stmt.where(
                        func.lower(RawEvent.source_type).in_(PARSER_SOURCE_FILTER)
                    )
                if PARSER_PACKAGE_FILTER:
                    stmt = stmt.where(
                        func.lower(RawEvent.package_name).in_(PARSER_PACKAGE_FILTER)
                    )
                if PARSER_APP_FILTER:
                    stmt = stmt.where(
                        func.lower(RawEvent.app_name).in_(PARSER_APP_FILTER)
                    )
                stmt = stmt.order_by(RawEvent.seq.asc()).limit(PARSER_BATCH_SIZE)
                events = session.execute(stmt).scalars().all()

                if not events:
                    # Advance offset past any unmatched events so we don't
                    # re-scan the same gap on every poll cycle.
                    global_max = session.execute(
                        select(func.max(RawEvent.seq))
                    ).scalar_one_or_none()
                    if global_max is not None and global_max > current_seq:
                        update_offset(session, PARSER_NAME, global_max)
                        logger.info(
                            "No matching events in seq %d–%d. Offset → %d",
                            current_seq + 1, global_max, global_max,
                        )
                        continue  # immediately re-poll in case new events arrived
                    _update_oldest_unprocessed_metric(session, current_seq)
                    logger.info("No new events. Sleeping %ds...", POLL_INTERVAL_SECONDS)
                    time.sleep(POLL_INTERVAL_SECONDS)
                    continue

                logger.info("Fetched %d events (seq %d–%d)", len(events), events[0].seq, events[-1].seq)

                # Process batch
                batch_start = time.monotonic()
                max_seq = current_seq

                for event in events:
                    success = _process_event(session, event)
                    if not success:
                        # DB failure — don't advance offset, break and retry
                        logger.error("Processing failed for seq=%d, will retry batch", event.seq)
                        session.rollback()
                        break
                    max_seq = event.seq
                else:
                    # All events processed successfully — commit and advance offset
                    update_offset(session, PARSER_NAME, max_seq)
                    batch_elapsed = time.monotonic() - batch_start
                    batch_latency.observe(batch_elapsed)
                    logger.info(
                        "Batch complete: %d events in %.2fs. Offset → %d",
                        len(events),
                        batch_elapsed,
                        max_seq,
                    )

                _update_oldest_unprocessed_metric(session, max_seq)

            except Exception:
                logger.exception("Unexpected error in polling loop. Sleeping and retrying...")
                session.rollback()
                time.sleep(POLL_INTERVAL_SECONDS)
