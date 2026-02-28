"""Authentication utilities for Control Plane v1.

- Admin auth via X-Admin-Token header (constant-time comparison)
- Device Bearer auth via token hash lookup against device_tokens
"""

import hashlib
import hmac
import logging
import os
import secrets
from datetime import datetime, timezone

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_db
from app.models import Device, DeviceToken, DeviceTelemetryLog

logger = logging.getLogger("control_plane.auth")

# ---------------------------------------------------------------------------
# Admin token from environment
# ---------------------------------------------------------------------------

ADMIN_TOKEN: str | None = os.environ.get("ADMIN_TOKEN")


def _constant_time_compare(a: str, b: str) -> bool:
    """Constant-time string comparison to prevent timing attacks."""
    return hmac.compare_digest(a.encode(), b.encode())


# ---------------------------------------------------------------------------
# Token hashing
# ---------------------------------------------------------------------------


def hash_token(plaintext: str) -> str:
    """SHA-256 hash a plaintext token. Used for storage and lookup."""
    return hashlib.sha256(plaintext.encode()).hexdigest()


def generate_token() -> str:
    """Generate a new API token with 'anla_' prefix + 32 random bytes (url-safe base64)."""
    return "anla_" + secrets.token_urlsafe(32)


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------


async def require_admin(
    x_admin_token: str | None = Header(None, alias="X-Admin-Token"),
) -> None:
    """Dependency: require valid admin token via X-Admin-Token header."""
    if ADMIN_TOKEN is None:
        raise HTTPException(status_code=500, detail="Admin auth not configured")
    if x_admin_token is None:
        raise HTTPException(status_code=401, detail="Missing X-Admin-Token header")
    if not _constant_time_compare(x_admin_token, ADMIN_TOKEN):
        logger.warning("Invalid admin token attempt")
        raise HTTPException(status_code=401, detail="Invalid admin token")


async def require_device_token(
    authorization: str | None = Header(None),
    x_battery_level: int | None = Header(None, alias="X-Battery-Level"),
    x_device_temperature: float | None = Header(None, alias="X-Device-Temperature"),
    x_device_latitude: float | None = Header(None, alias="X-Device-Latitude"),
    x_device_longitude: float | None = Header(None, alias="X-Device-Longitude"),
    x_device_altitude: float | None = Header(None, alias="X-Device-Altitude"),
    db: AsyncSession = Depends(get_db),
) -> Device:
    """Dependency: validate Bearer token and return the associated Device.

    Checks:
    - Bearer token present
    - Token hash exists in device_tokens
    - Token not revoked (revoked_at IS NULL)
    - Token not expired
    - Device status == 'approved'

    Side effect:
    - Updates device.last_seen_at
    - Updates device.battery_percentage, temperature, latitude, longitude
    """
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    plaintext = authorization[7:]  # strip "Bearer "
    token_hash = hash_token(plaintext)

    # Look up token + eagerly load device and config
    stmt = (
        select(DeviceToken)
        .options(
            selectinload(DeviceToken.device).selectinload(Device.config)
        )
        .where(DeviceToken.token_hash == token_hash)
    )
    result = await db.execute(stmt)
    device_token = result.scalar_one_or_none()

    if device_token is None:
        logger.warning("Token lookup failed (hash not found)")
        raise HTTPException(status_code=401, detail="Invalid token")

    # Check revocation
    if device_token.revoked_at is not None:
        logger.warning("Revoked token used for device_id=%s", device_token.device_id)
        raise HTTPException(status_code=401, detail="Token revoked")

    # Check expiration
    if device_token.expires_at is not None:
        now = datetime.now(timezone.utc)
        if device_token.expires_at <= now:
            logger.warning("Expired token used for device_id=%s", device_token.device_id)
            raise HTTPException(status_code=401, detail="Token expired")

    # Check device status
    device = device_token.device
    if device.status != "approved":
        logger.warning(
            "Token used for non-approved device_id=%s status=%s",
            device.id,
            device.status,
        )
        raise HTTPException(status_code=401, detail=f"Device not approved (status={device.status})")

    # Heartbeat: update last_seen_at
    device.last_seen_at = datetime.now(timezone.utc)
    
    config = device.config
    if x_battery_level is not None:
        # Respect granular config
        batt = x_battery_level if (config and config.collect_battery) else None
        temp = x_device_temperature if (config and config.collect_temperature) else None
        
        lat = None
        lng = None
        alt = None
        if config and config.collect_location:
            lat = x_device_latitude
            lng = x_device_longitude
            alt = x_device_altitude

        # Only log if some data is actually collected
        if any(v is not None for v in [batt, temp, lat, lng, alt]):
            should_log = False
            if (device.battery_percentage != batt or 
                device.temperature != temp or
                device.latitude != lat or
                device.longitude != lng or
                device.altitude != alt):
                should_log = True
            else:
                # Check last log timestamp
                last_log_stmt = (
                    select(DeviceTelemetryLog)
                    .where(DeviceTelemetryLog.device_id == device.id)
                    .order_by(desc(DeviceTelemetryLog.created_at))
                    .limit(1)
                )
                last_log = (await db.execute(last_log_stmt)).scalar_one_or_none()
                if not last_log:
                    should_log = True
                else:
                    elapsed = datetime.now(timezone.utc) - last_log.created_at
                    if elapsed.total_seconds() > 900:  # 15 minutes
                        should_log = True

            if should_log:
                db.add(DeviceTelemetryLog(
                    device_id=device.id, 
                    battery_percentage=batt if batt is not None else (device.battery_percentage or 0),
                    temperature=temp,
                    latitude=lat,
                    longitude=lng,
                    altitude=alt
                ))

        if batt is not None: device.battery_percentage = batt
        if temp is not None: device.temperature = temp
        if lat is not None: device.latitude = lat
        if lng is not None: device.longitude = lng
        if alt is not None: device.altitude = alt

    await db.commit()
    return device
