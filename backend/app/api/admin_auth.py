"""Shared session-cookie authentication for the Admin Web UI.

Used by both admin.py (device management) and admin_data.py (data viewer).
"""

import os

from fastapi import Request
from itsdangerous import BadSignature, URLSafeTimedSerializer

from app.api.auth import ADMIN_TOKEN

# Session cookie config
SESSION_COOKIE = "anla_session"
SESSION_MAX_AGE = 86400  # 24 hours
SECRET_KEY = os.environ.get("SESSION_SECRET", ADMIN_TOKEN or "fallback-secret-key")
serializer = URLSafeTimedSerializer(SECRET_KEY)


def get_session_user(request: Request) -> str | None:
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


def require_session(request: Request) -> str | None:
    """Check session; return user or None (caller redirects)."""
    return get_session_user(request)
