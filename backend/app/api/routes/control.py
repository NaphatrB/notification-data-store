"""Control Plane v1 — device registration, approval, revocation, config.

All endpoints live under /control/v1/.
"""

import logging
import os
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import generate_token, hash_token, require_admin, require_device_token
from app.api.schemas import (
    DeviceApproveResponse,
    DeviceConfigResponse,
    DeviceRegisterRequest,
    DeviceRegisterResponse,
    DeviceRevokeResponse,
)
from app.db import get_db
from app.models import Device, DeviceConfig, DeviceToken

logger = logging.getLogger("control_plane")

router = APIRouter(prefix="/control/v1", tags=["control-plane"])

INGESTION_PUBLIC_BASE_URL: str = os.environ.get("INGESTION_PUBLIC_BASE_URL", "")


# ---------------------------------------------------------------------------
# 4.1  Register Device
# ---------------------------------------------------------------------------


@router.post("/devices/register", response_model=DeviceRegisterResponse, status_code=200)
async def register_device(
    body: DeviceRegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> DeviceRegisterResponse:
    """Register or re-register a device.

    If deviceUuid is new  → create with status=pending.
    If deviceUuid exists → update metadata, return existing status.
    """
    stmt = select(Device).where(Device.device_uuid == body.deviceUuid)
    result = await db.execute(stmt)
    device = result.scalar_one_or_none()

    if device is not None:
        # Update metadata fields
        device.device_name = body.deviceName
        device.device_model = body.deviceModel
        device.android_version = body.androidVersion
        device.app_version = body.appVersion
        await db.commit()
        logger.info("Device re-registered: device_uuid=%s status=%s", body.deviceUuid, device.status)
        return DeviceRegisterResponse(deviceId=device.id, status=device.status)

    # New device
    device = Device(
        device_uuid=body.deviceUuid,
        device_name=body.deviceName,
        device_model=body.deviceModel,
        android_version=body.androidVersion,
        app_version=body.appVersion,
    )
    db.add(device)
    await db.commit()
    await db.refresh(device)
    logger.info("Device registered: device_uuid=%s id=%s", body.deviceUuid, device.id)
    return DeviceRegisterResponse(deviceId=device.id, status=device.status)


# ---------------------------------------------------------------------------
# 4.2  Approve Device (Admin Only)
# ---------------------------------------------------------------------------


@router.post(
    "/devices/{device_id}/approve",
    response_model=DeviceApproveResponse,
    dependencies=[Depends(require_admin)],
)
async def approve_device(
    device_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> DeviceApproveResponse:
    """Approve a pending device. Generates and returns token ONCE."""
    stmt = select(Device).where(Device.id == device_id)
    result = await db.execute(stmt)
    device = result.scalar_one_or_none()

    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")

    if device.status == "approved":
        raise HTTPException(status_code=409, detail="Device already approved")

    if device.status in ("revoked", "disabled"):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot approve device in '{device.status}' state",
        )

    # Transition to approved
    now = datetime.now(timezone.utc)
    device.status = "approved"
    device.approved_at = now

    # Generate token
    plaintext = generate_token()
    token = DeviceToken(
        device_id=device.id,
        token_hash=hash_token(plaintext),
        token_name="auto-approval",
    )
    db.add(token)

    # Create default config
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

    return DeviceApproveResponse(
        deviceId=device.id,
        status=device.status,
        token=plaintext,
    )


# ---------------------------------------------------------------------------
# 4.3  Revoke Device (Admin Only)
# ---------------------------------------------------------------------------


@router.post(
    "/devices/{device_id}/revoke",
    response_model=DeviceRevokeResponse,
    dependencies=[Depends(require_admin)],
)
async def revoke_device(
    device_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> DeviceRevokeResponse:
    """Revoke a device — invalidates all tokens."""
    stmt = select(Device).where(Device.id == device_id)
    result = await db.execute(stmt)
    device = result.scalar_one_or_none()

    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")

    if device.status == "revoked":
        raise HTTPException(status_code=409, detail="Device already revoked")

    now = datetime.now(timezone.utc)
    device.status = "revoked"

    # Revoke all active tokens
    tokens_stmt = select(DeviceToken).where(
        DeviceToken.device_id == device_id,
        DeviceToken.revoked_at.is_(None),
    )
    tokens_result = await db.execute(tokens_stmt)
    for t in tokens_result.scalars().all():
        t.revoked_at = now

    await db.commit()
    logger.info("Device revoked: id=%s", device_id)

    return DeviceRevokeResponse(deviceId=device.id, status=device.status)


# ---------------------------------------------------------------------------
# 4.4  Get Device Config (Authenticated via Bearer)
# ---------------------------------------------------------------------------


@router.get("/devices/{device_uuid}/config", response_model=DeviceConfigResponse)
async def get_device_config(
    device_uuid: str,
    device: Device = Depends(require_device_token),
    db: AsyncSession = Depends(get_db),
) -> DeviceConfigResponse:
    """Return config for authenticated device.

    Bearer token validation + last_seen_at update happens in require_device_token.
    """
    # Ensure the device_uuid in path matches the authenticated device
    if device.device_uuid != device_uuid:
        raise HTTPException(status_code=403, detail="Token does not match requested device")

    if device.status != "approved":
        return DeviceConfigResponse(
            status=device.status,
            captureMode="",
            pollIntervalSeconds=0,
            parserEnabled=False,
        )

    # Load config
    config_stmt = select(DeviceConfig).where(DeviceConfig.device_id == device.id)
    config_result = await db.execute(config_stmt)
    config = config_result.scalar_one_or_none()

    if config is None:
        raise HTTPException(status_code=500, detail="Device config missing")

    logger.info("Config fetched: device_uuid=%s", device_uuid)

    return DeviceConfigResponse(
        status=device.status,
        apiBaseUrl=config.api_base_url,
        captureMode=config.capture_mode,
        pollIntervalSeconds=config.poll_interval_seconds,
        parserEnabled=config.parser_enabled,
    )
