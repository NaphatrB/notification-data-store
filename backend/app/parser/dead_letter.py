"""Dead-letter persistence for failed parsing attempts."""

import logging
import uuid

from sqlalchemy.orm import Session

from app.parser.config import PARSER_VERSION
from app.parser.models import PricingDeadLetter

logger = logging.getLogger(__name__)


def insert_dead_letter(
    session: Session,
    *,
    raw_event_id: uuid.UUID,
    seq: int,
    error_type: str,
    error_message: str,
    llm_raw_response: dict | None,
    original_text: str | None,
) -> None:
    """Insert a dead-letter record for a failed parsing attempt."""
    row = PricingDeadLetter(
        raw_event_id=raw_event_id,
        seq=seq,
        parser_version=PARSER_VERSION,
        error_type=error_type,
        error_message=error_message,
        llm_raw_response=llm_raw_response,
        original_text=original_text,
    )
    session.add(row)
    logger.warning(
        "Dead-lettered event seq=%d raw_event_id=%s: [%s] %s",
        seq,
        raw_event_id,
        error_type,
        error_message,
    )
