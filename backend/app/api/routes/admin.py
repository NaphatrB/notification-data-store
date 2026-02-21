"""Admin Web UI — server-rendered device management pages.

All routes live under /admin/.
Authentication via signed session cookie (itsdangerous).
"""

import logging
import os
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from itsdangerous import BadSignature, URLSafeTimedSerializer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import ADMIN_TOKEN, _constant_time_compare
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
from app.models import DeviceToken

logger = logging.getLogger("admin_ui")

router = APIRouter(prefix="/admin", tags=["admin-ui"])

TEMPLATE_DIR = Path(__file__).resolve().parent.parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

# Session cookie config
SESSION_COOKIE = "anla_session"
SESSION_MAX_AGE = 86400  # 24 hours
SECRET_KEY = os.environ.get("SESSION_SECRET", ADMIN_TOKEN or "fallback-secret-key")
serializer = URLSafeTimedSerializer(SECRET_KEY)


# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------


def _get_session_user(request: Request) -> str | None:
    """Extract and validate session cookie. Returns 'admin' or None."""
    cookie = request.cookies.get(SESSION_COOKIE)
    if cookie is None:
        return None
    try:
        data = serializer.loads(cookie, max_age=SESSION_MAX_AGE)
        if data.get("role") == "admin":
            return "admin"
    except (BadSignature, Exception):
        pass
    return None


def _require_session(request: Request) -> str | None:
    """Check session; return user or None (caller redirects)."""
    return _get_session_user(request)


# ---------------------------------------------------------------------------
# Login / Logout
# ---------------------------------------------------------------------------


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Render login form."""
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@router.post("/login", response_class=HTMLResponse)
async def login_submit(request: Request, token: str = Form(...)):
    """Validate admin token, set session cookie."""
    if ADMIN_TOKEN is None:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Admin auth not configured on server."},
        )

    if not _constant_time_compare(token, ADMIN_TOKEN):
        logger.warning("Failed admin login attempt from UI")
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Invalid admin token."},
        )

    # Create signed session cookie
    session_value = serializer.dumps({"role": "admin"})
    response = RedirectResponse(url="/admin/devices", status_code=303)
    response.set_cookie(
        key=SESSION_COOKIE,
        value=session_value,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=SESSION_MAX_AGE,
    )
    logger.info("Admin logged in via UI")
    return response


@router.get("/logout")
async def logout():
    """Clear session cookie and redirect to login."""
    response = RedirectResponse(url="/admin/login", status_code=303)
    response.delete_cookie(key=SESSION_COOKIE)
    return response


# ---------------------------------------------------------------------------
# Device List
# ---------------------------------------------------------------------------


@router.get("/devices", response_class=HTMLResponse)
async def devices_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Render device list page."""
    user = _require_session(request)
    if user is None:
        return RedirectResponse(url="/admin/login", status_code=303)

    devices, _total = await list_devices_svc(db, limit=200)

    return templates.TemplateResponse(
        "devices.html",
        {
            "request": request,
            "devices": devices,
            "error": None,
            "success": None,
        },
    )


# ---------------------------------------------------------------------------
# Device Detail
# ---------------------------------------------------------------------------


@router.get("/devices/{device_id}", response_class=HTMLResponse)
async def device_detail_page(
    request: Request,
    device_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Render device detail page."""
    user = _require_session(request)
    if user is None:
        return RedirectResponse(url="/admin/login", status_code=303)

    try:
        d = await get_device_svc(db, device_id)
    except DeviceNotFoundError:
        return templates.TemplateResponse(
            "devices.html",
            {
                "request": request,
                "devices": [],
                "error": "Device not found.",
                "success": None,
            },
        )

    # Count active tokens
    token_stmt = select(DeviceToken).where(
        DeviceToken.device_id == device_id,
        DeviceToken.revoked_at.is_(None),
    )
    token_result = await db.execute(token_stmt)
    active_token_count = len(token_result.scalars().all())

    return templates.TemplateResponse(
        "device_detail.html",
        {
            "request": request,
            "d": d,
            "active_token_count": active_token_count,
            "error": request.query_params.get("error"),
            "success": request.query_params.get("success"),
        },
    )


# ---------------------------------------------------------------------------
# Approve Action
# ---------------------------------------------------------------------------


@router.post("/devices/{device_id}/approve", response_class=HTMLResponse)
async def approve_action(
    request: Request,
    device_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Approve device, show token reveal page."""
    user = _require_session(request)
    if user is None:
        return RedirectResponse(url="/admin/login", status_code=303)

    try:
        result = await approve_device_svc(db, device_id)
    except DeviceNotFoundError:
        return RedirectResponse(
            url=f"/admin/devices/{device_id}?error=Device+not+found",
            status_code=303,
        )
    except DeviceStateError as e:
        return RedirectResponse(
            url=f"/admin/devices/{device_id}?error={e.detail}",
            status_code=303,
        )

    return templates.TemplateResponse(
        "token_reveal.html",
        {
            "request": request,
            "device_id": device_id,
            "device_name": result.device.device_name,
            "device_uuid": result.device.device_uuid,
            "token": result.plaintext_token,
            "action": "Device Approved — Initial Token Issued",
            "error": None,
            "success": None,
        },
    )


# ---------------------------------------------------------------------------
# Revoke Action
# ---------------------------------------------------------------------------


@router.post("/devices/{device_id}/revoke")
async def revoke_action(
    request: Request,
    device_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Revoke device, redirect back to detail."""
    user = _require_session(request)
    if user is None:
        return RedirectResponse(url="/admin/login", status_code=303)

    try:
        await revoke_device_svc(db, device_id)
    except DeviceNotFoundError:
        return RedirectResponse(
            url=f"/admin/devices/{device_id}?error=Device+not+found",
            status_code=303,
        )
    except DeviceStateError as e:
        return RedirectResponse(
            url=f"/admin/devices/{device_id}?error={e.detail}",
            status_code=303,
        )

    return RedirectResponse(
        url=f"/admin/devices/{device_id}?success=Device+revoked",
        status_code=303,
    )


# ---------------------------------------------------------------------------
# Rotate Token Action
# ---------------------------------------------------------------------------


@router.post("/devices/{device_id}/rotate-token", response_class=HTMLResponse)
async def rotate_token_action(
    request: Request,
    device_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Rotate token, show token reveal page."""
    user = _require_session(request)
    if user is None:
        return RedirectResponse(url="/admin/login", status_code=303)

    try:
        result = await rotate_token_svc(db, device_id)
    except DeviceNotFoundError:
        return RedirectResponse(
            url=f"/admin/devices/{device_id}?error=Device+not+found",
            status_code=303,
        )
    except DeviceStateError as e:
        return RedirectResponse(
            url=f"/admin/devices/{device_id}?error={e.detail}",
            status_code=303,
        )

    return templates.TemplateResponse(
        "token_reveal.html",
        {
            "request": request,
            "device_id": device_id,
            "device_name": result.device.device_name,
            "device_uuid": result.device.device_uuid,
            "token": result.plaintext_token,
            "action": "Token Rotated — Previous Tokens Revoked",
            "error": None,
            "success": None,
        },
    )


# ---------------------------------------------------------------------------
# Reinstate Action
# ---------------------------------------------------------------------------


@router.post("/devices/{device_id}/reinstate")
async def reinstate_action(
    request: Request,
    device_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Reinstate a revoked device, redirect back to detail."""
    user = _require_session(request)
    if user is None:
        return RedirectResponse(url="/admin/login", status_code=303)

    try:
        await reinstate_device_svc(db, device_id)
    except DeviceNotFoundError:
        return RedirectResponse(
            url=f"/admin/devices/{device_id}?error=Device+not+found",
            status_code=303,
        )
    except DeviceStateError as e:
        return RedirectResponse(
            url=f"/admin/devices/{device_id}?error={e.detail}",
            status_code=303,
        )

    return RedirectResponse(
        url=f"/admin/devices/{device_id}?success=Device+reinstated.+Issue+a+new+token+to+restore+ingestion.",
        status_code=303,
    )


# ---------------------------------------------------------------------------
# Root redirect
# ---------------------------------------------------------------------------


@router.get("/")
async def admin_root():
    """Redirect /admin/ to /admin/devices."""
    return RedirectResponse(url="/admin/devices", status_code=303)
