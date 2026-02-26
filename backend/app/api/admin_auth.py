"""Shared session-cookie authentication for the Admin Web UI.

Used by both admin.py (device management) and admin_data.py (data viewer).
"""

import os

from fastapi import HTTPException, Request
from itsdangerous import BadSignature, URLSafeTimedSerializer

from app.api.auth import ADMIN_TOKEN

# Session cookie config
SESSION_COOKIE = "anla_session"
SESSION_MAX_AGE = 86400  # 24 hours
SECRET_KEY = os.environ.get("SESSION_SECRET", ADMIN_TOKEN or "fallback-secret-key")
serializer = URLSafeTimedSerializer(SECRET_KEY)


def get_session_user(request: Request) -> str | None:
    """Extract and validate session cookie or starlette session. Returns 'admin' or None."""
    # 1. Check manual signed cookie (itsdangerous)
    cookie = request.cookies.get(SESSION_COOKIE)
    if cookie:
        try:
            data = serializer.loads(cookie, max_age=SESSION_MAX_AGE)
            if data.get("role") == "admin":
                return "admin"
        except (BadSignature, Exception):
            pass

    # 2. Check Starlette session (used by OIDC)
    try:
        if request.session.get("user"):
            return "admin"
    except (AttributeError, RuntimeError):
        # session might not be initialized yet in some contexts
        pass

    return None


def require_user_session(request: Request) -> str:
    """Dependency: require session; raise 401 if invalid. Used for JSON endpoints."""
    user = get_session_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized session")
    return user


def require_session(request: Request) -> str | None:
    """Check session; return user or None (caller redirects)."""
    return get_session_user(request)
