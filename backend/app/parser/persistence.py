"""Persistence logic for structured prices.

Handles replay idempotency: delete existing rows for a raw_event_id
before re-inserting.
"""

import logging
import uuid

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.parser.config import PARSER_VERSION
from app.parser.models import StructuredPrice
from app.parser.schemas import PricingExtraction

logger = logging.getLogger(__name__)


def persist_extraction(
    session: Session,
    *,
    raw_event_id: uuid.UUID,
    seq: int,
    event_timestamp,
    extraction: PricingExtraction,
    llm_raw_response: dict,
) -> int:
    """Persist extracted pricing items to structured_prices.

    Deletes any existing rows for this raw_event_id first (replay idempotency).
    Returns the number of rows inserted.
    """
    # Delete existing rows for this event (replay support)
    del_stmt = delete(StructuredPrice).where(
        StructuredPrice.raw_event_id == raw_event_id
    )
    deleted = session.execute(del_stmt).rowcount
    if deleted > 0:
        logger.info(
            "Deleted %d existing rows for raw_event_id=%s (replay)",
            deleted,
            raw_event_id,
        )

    # Insert one row per complete line item, per offer
    rows_inserted = 0
    for offer in extraction.offers:
        for item in offer.complete_items():
            row = StructuredPrice(
                raw_event_id=raw_event_id,
                seq=seq,
                parser_version=PARSER_VERSION,
                supplier=offer.supplier,
                product=offer.product,
                product_grade=item.grade,
                size=item.size,
                quantity_kg=item.quantity_kg,
                price_per_kg=item.price_per_kg,
                currency=offer.currency,
                total_kg=offer.total_kg,
                event_timestamp=event_timestamp,
                confidence=extraction.confidence,
                llm_raw_response=llm_raw_response,
            )
            session.add(row)
            rows_inserted += 1

    logger.info(
        "Inserted %d price rows for raw_event_id=%s (seq=%d)",
        rows_inserted,
        raw_event_id,
        seq,
    )
    return rows_inserted
