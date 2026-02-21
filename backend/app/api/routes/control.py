"""Control Plane v1 — device registration, approval, revocation, config.

All endpoints live under /control/v1/.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import require_admin, require_device_token
from app.api.schemas import (
    DeviceApproveResponse,
    DeviceConfigResponse,
    DeviceListItem,
    DeviceListResponse,
    DeviceRegisterRequest,
    DeviceRegisterResponse,
    DeviceReinstateResponse,
    DeviceRevokeResponse,
    TokenRotateResponse,
)
from app.api.services import (
    DeviceNotFoundError,
    DeviceStateError,
    approve_device_svc,
    get_device_svc,
    list_devices_svc,
    reinstate_device_svc,
    revoke_device_svc,
    rotate_token_svc,
)
from app.db import get_db
from app.models import Device, DeviceConfig

logger = logging.getLogger("control_plane")

router = APIRouter(prefix="/control/v1", tags=["control-plane"])


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
    try:
        result = await approve_device_svc(db, device_id)
    except DeviceNotFoundError:
        raise HTTPException(status_code=404, detail="Device not found")
    except DeviceStateError as e:
        raise HTTPException(status_code=409, detail=e.detail)

    return DeviceApproveResponse(
        deviceId=result.device.id,
        status=result.device.status,
        token=result.plaintext_token,
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
    try:
        device = await revoke_device_svc(db, device_id)
    except DeviceNotFoundError:
        raise HTTPException(status_code=404, detail="Device not found")
    except DeviceStateError as e:
        raise HTTPException(status_code=409, detail=e.detail)

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


# ---------------------------------------------------------------------------
# 4.5  Fleet Visibility — List Devices (Admin Only)
# ---------------------------------------------------------------------------


@router.get(
    "/devices",
    response_model=DeviceListResponse,
    dependencies=[Depends(require_admin)],
)
async def list_devices(
    db: AsyncSession = Depends(get_db),
    status: str | None = Query(None),
    search: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> DeviceListResponse:
    """Return paginated list of all devices with ingestion stats."""
    devices, total = await list_devices_svc(
        db, status=status, search=search, limit=limit, offset=offset
    )

    items = [
        DeviceListItem(
            deviceId=d.device.id,
            deviceUuid=d.device.device_uuid,
            deviceName=d.device.device_name,
            status=d.device.status,
            lastSeenAt=d.device.last_seen_at,
            approvedAt=d.device.approved_at,
            appVersion=d.device.app_version,
            androidVersion=d.device.android_version,
            totalEventsIngested=d.total_events,
            lastEventAt=d.last_event_at,
        )
        for d in devices
    ]

    return DeviceListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


# ---------------------------------------------------------------------------
# 4.6  Fleet Visibility — Get Single Device (Admin Only)
# ---------------------------------------------------------------------------


@router.get(
    "/devices/{device_id}",
    response_model=DeviceListItem,
    dependencies=[Depends(require_admin)],
)
async def get_device(
    device_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> DeviceListItem:
    """Return a single device with ingestion stats."""
    try:
        d = await get_device_svc(db, device_id)
    except DeviceNotFoundError:
        raise HTTPException(status_code=404, detail="Device not found")

    return DeviceListItem(
        deviceId=d.device.id,
        deviceUuid=d.device.device_uuid,
        deviceName=d.device.device_name,
        status=d.device.status,
        lastSeenAt=d.device.last_seen_at,
        approvedAt=d.device.approved_at,
        appVersion=d.device.app_version,
        androidVersion=d.device.android_version,
        totalEventsIngested=d.total_events,
        lastEventAt=d.last_event_at,
    )


# ---------------------------------------------------------------------------
# 4.7  Token Rotation (Admin Only)
# ---------------------------------------------------------------------------


@router.post(
    "/devices/{device_id}/rotate-token",
    response_model=TokenRotateResponse,
    dependencies=[Depends(require_admin)],
)
async def rotate_token(
    device_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> TokenRotateResponse:
    """Generate a new token and revoke all previous active tokens."""
    try:
        result = await rotate_token_svc(db, device_id)
    except DeviceNotFoundError:
        raise HTTPException(status_code=404, detail="Device not found")
    except DeviceStateError as e:
        raise HTTPException(status_code=409, detail=e.detail)

    return TokenRotateResponse(
        deviceId=result.device.id,
        token=result.plaintext_token,
    )


# ---------------------------------------------------------------------------
# 4.8  Reinstate Device (Admin Only)
# ---------------------------------------------------------------------------


@router.post(
    "/devices/{device_id}/reinstate",
    response_model=DeviceReinstateResponse,
    dependencies=[Depends(require_admin)],
)
async def reinstate_device(
    device_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> DeviceReinstateResponse:
    """Reinstate a revoked device. Does NOT issue a new token."""
    try:
        device = await reinstate_device_svc(db, device_id)
    except DeviceNotFoundError:
        raise HTTPException(status_code=404, detail="Device not found")
    except DeviceStateError as e:
        raise HTTPException(status_code=409, detail=e.detail)

    return DeviceReinstateResponse(
        deviceId=device.id,
        status=device.status,
        requiresToken=True,
    )
