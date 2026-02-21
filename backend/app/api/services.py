"""Shared business logic for device fleet management.

Used by both the JSON API (control.py) and the Admin Web UI (admin.py).
Keeps DB operations and domain rules in one place.
"""

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.audit import log_audit
from app.api.auth import generate_token, hash_token
from app.models import Device, DeviceConfig, DeviceToken, RawEvent

logger = logging.getLogger("control_plane.services")

INGESTION_PUBLIC_BASE_URL: str = os.environ.get("INGESTION_PUBLIC_BASE_URL", "")


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class DeviceNotFoundError(Exception):
    pass


class DeviceStateError(Exception):
    def __init__(self, detail: str):
        self.detail = detail
        super().__init__(detail)


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------


@dataclass
class DeviceWithStats:
    """Device ORM object + computed ingestion stats."""

    device: Device
    total_events: int
    last_event_at: datetime | None


@dataclass
class ApproveResult:
    device: Device
    plaintext_token: str


@dataclass
class RotateResult:
    device: Device
    plaintext_token: str


# ---------------------------------------------------------------------------
# Service functions
# ---------------------------------------------------------------------------


async def list_devices_svc(
    db: AsyncSession,
    *,
    status: str | None = None,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[DeviceWithStats], int]:
    """Return paginated device list with ingestion stats and total count."""
    event_count = func.count(RawEvent.id).label("total_events")
    last_event = func.max(RawEvent.event_timestamp).label("last_event_at")

    stmt = (
        select(Device, event_count, last_event)
        .outerjoin(RawEvent, RawEvent.device_id == Device.id)
        .group_by(Device.id)
    )
    count_stmt = select(func.count(Device.id))

    if status is not None:
        stmt = stmt.where(Device.status == status)
        count_stmt = count_stmt.where(Device.status == status)
    if search is not None:
        pattern = f"%{search}%"
        stmt = stmt.where(Device.device_name.ilike(pattern))
        count_stmt = count_stmt.where(Device.device_name.ilike(pattern))

    total = (await db.execute(count_stmt)).scalar_one()
    stmt = stmt.order_by(Device.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(stmt)

    items = [
        DeviceWithStats(
            device=device,
            total_events=total_events or 0,
            last_event_at=last_event_at,
        )
        for device, total_events, last_event_at in result.all()
    ]
    return items, total


async def get_device_svc(db: AsyncSession, device_id: UUID) -> DeviceWithStats:
    """Return a single device with stats. Raises DeviceNotFoundError."""
    event_count = func.count(RawEvent.id).label("total_events")
    last_event = func.max(RawEvent.event_timestamp).label("last_event_at")

    stmt = (
        select(Device, event_count, last_event)
        .outerjoin(RawEvent, RawEvent.device_id == Device.id)
        .where(Device.id == device_id)
        .group_by(Device.id)
    )
    result = await db.execute(stmt)
    row = result.one_or_none()

    if row is None:
        raise DeviceNotFoundError()

    device, total_events, last_event_at = row
    return DeviceWithStats(
        device=device,
        total_events=total_events or 0,
        last_event_at=last_event_at,
    )


async def approve_device_svc(db: AsyncSession, device_id: UUID) -> ApproveResult:
    """Approve a pending device. Returns plaintext token.

    Raises DeviceNotFoundError or DeviceStateError.
    """
    stmt = select(Device).where(Device.id == device_id)
    result = await db.execute(stmt)
    device = result.scalar_one_or_none()

    if device is None:
        raise DeviceNotFoundError()
    if device.status == "approved":
        raise DeviceStateError("Device already approved")
    if device.status in ("revoked", "disabled"):
        raise DeviceStateError(f"Cannot approve device in '{device.status}' state")

    now = datetime.now(timezone.utc)
    device.status = "approved"
    device.approved_at = now

    plaintext = generate_token()
    token = DeviceToken(
        device_id=device.id,
        token_hash=hash_token(plaintext),
        token_name="auto-approval",
    )
    db.add(token)

    config = DeviceConfig(
        device_id=device.id,
        api_base_url=INGESTION_PUBLIC_BASE_URL or None,
        capture_mode="WHATSAPP_ONLY",
        poll_interval_seconds=300,
        parser_enabled=True,
    )
    db.add(config)

    await db.commit()
    logger.info("Device approved: id=%s", device_id)

    await log_audit(
        db,
        actor="admin",
        action="device_approved",
        target_type="device",
        target_id=device.id,
        metadata={"deviceName": device.device_name},
    )
    await log_audit(
        db,
        actor="admin",
        action="token_issued",
        target_type="device_token",
        target_id=device.id,
        metadata={"tokenName": "auto-approval"},
    )
    await db.commit()

    return ApproveResult(device=device, plaintext_token=plaintext)


async def revoke_device_svc(db: AsyncSession, device_id: UUID) -> Device:
    """Revoke a device and all active tokens.

    Raises DeviceNotFoundError or DeviceStateError.
    """
    stmt = select(Device).where(Device.id == device_id)
    result = await db.execute(stmt)
    device = result.scalar_one_or_none()

    if device is None:
        raise DeviceNotFoundError()
    if device.status == "revoked":
        raise DeviceStateError("Device already revoked")

    now = datetime.now(timezone.utc)
    device.status = "revoked"

    tokens_stmt = select(DeviceToken).where(
        DeviceToken.device_id == device_id,
        DeviceToken.revoked_at.is_(None),
    )
    tokens_result = await db.execute(tokens_stmt)
    for t in tokens_result.scalars().all():
        t.revoked_at = now

    await db.commit()
    logger.info("Device revoked: id=%s", device_id)

    await log_audit(
        db,
        actor="admin",
        action="device_revoked",
        target_type="device",
        target_id=device.id,
        metadata={"deviceName": device.device_name},
    )
    await db.commit()

    return device


async def rotate_token_svc(db: AsyncSession, device_id: UUID) -> RotateResult:
    """Rotate token: revoke all active tokens, generate new one.

    Raises DeviceNotFoundError or DeviceStateError.
    """
    stmt = select(Device).where(Device.id == device_id)
    result = await db.execute(stmt)
    device = result.scalar_one_or_none()

    if device is None:
        raise DeviceNotFoundError()
    if device.status != "approved":
        raise DeviceStateError(
            f"Cannot rotate token for device in '{device.status}' state"
        )

    now = datetime.now(timezone.utc)

    tokens_stmt = select(DeviceToken).where(
        DeviceToken.device_id == device_id,
        DeviceToken.revoked_at.is_(None),
    )
    tokens_result = await db.execute(tokens_stmt)
    for t in tokens_result.scalars().all():
        t.revoked_at = now

    plaintext = generate_token()
    new_token = DeviceToken(
        device_id=device.id,
        token_hash=hash_token(plaintext),
        token_name="rotation",
    )
    db.add(new_token)

    await db.commit()
    logger.info("Token rotated: device_id=%s", device_id)

    await log_audit(
        db,
        actor="admin",
        action="token_rotated",
        target_type="device_token",
        target_id=device.id,
        metadata={"deviceName": device.device_name},
    )
    await db.commit()

    return RotateResult(device=device, plaintext_token=plaintext)
