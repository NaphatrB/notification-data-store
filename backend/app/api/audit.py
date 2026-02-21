"""Audit logging helper for Control Plane actions."""

import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog

logger = logging.getLogger("control_plane.audit")


async def log_audit(
    db: AsyncSession,
    *,
    actor: str,
    action: str,
    target_type: str,
    target_id: UUID | None = None,
    metadata: dict | None = None,
) -> None:
    """Insert an audit log row. Best-effort — logs but does not raise on failure."""
    try:
        entry = AuditLog(
            actor=actor,
            action=action,
            target_type=target_type,
            target_id=target_id,
            metadata_=metadata,
        )
        db.add(entry)
        await db.flush()
        logger.info("audit: %s %s %s target=%s", actor, action, target_type, target_id)
    except Exception:
        logger.exception("Failed to write audit log: action=%s target=%s", action, target_id)
