"""Offset management for the parser high-water mark."""

import logging
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.parser.models import ParserOffset

logger = logging.getLogger(__name__)


def get_current_offset(session: Session, parser_name: str) -> int:
    """Get the current offset (last_seq) for the given parser.

    Returns 0 if no offset record exists (first run).
    """
    stmt = select(ParserOffset.last_seq).where(
        ParserOffset.parser_name == parser_name
    )
    result = session.execute(stmt).scalar_one_or_none()
    if result is None:
        # First run — create the offset row
        offset = ParserOffset(parser_name=parser_name, last_seq=0)
        session.add(offset)
        session.commit()
        logger.info("Created offset record for parser '%s' at seq=0", parser_name)
        return 0
    return result


def update_offset(session: Session, parser_name: str, new_seq: int) -> None:
    """Update the offset to the new high-water mark."""
    stmt = (
        update(ParserOffset)
        .where(ParserOffset.parser_name == parser_name)
        .values(last_seq=new_seq, updated_at=datetime.now(timezone.utc))
    )
    session.execute(stmt)
    session.commit()
    logger.info("Updated offset for '%s' to seq=%d", parser_name, new_seq)


def reset_offset(session: Session, parser_name: str) -> None:
    """Reset the offset to 0 for replay."""
    stmt = (
        update(ParserOffset)
        .where(ParserOffset.parser_name == parser_name)
        .values(last_seq=0, updated_at=datetime.now(timezone.utc))
    )
    result = session.execute(stmt)
    if result.rowcount == 0:
        # No row exists yet — create it at 0
        offset = ParserOffset(parser_name=parser_name, last_seq=0)
        session.add(offset)
    session.commit()
    logger.info("Reset offset for parser '%s' to seq=0", parser_name)
