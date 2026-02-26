from pathlib import Path

from fastapi import FastAPI, Depends, Request
from fastapi.staticfiles import StaticFiles
from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html
from fastapi.responses import RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy import text

from app.db import async_session
from app.api.routes.admin import router as admin_router
from app.api.routes.admin_data import router as admin_data_router
from app.api.routes.control import router as control_router
from app.api.routes.events import router as events_router
from app.api.routes.pricing import router as pricing_router
from app.api.admin_auth import get_session_user, SECRET_KEY

import logging
import os

logger = logging.getLogger("anla")

app = FastAPI(
    title="ANLA Notification Data Store",
    description="Ingestion & Control Plane backend for ANLA.",
    version="0.6.0",
    docs_url=None,
    redoc_url=None,
    openapi_url="/openapi.json", # Keep openapi.json but it will be protected if we want
)

# Starlette session middleware for OIDC
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)

# Static files
_static_dir = Path(__file__).resolve().parent.parent / "static"
app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")

# Protected Docs Routes
@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html(request: Request):
    user = get_session_user(request)
    if not user:
        return RedirectResponse(url="/admin/login")
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=app.title + " - Swagger UI",
        oauth2_redirect_url=app.swagger_ui_oauth2_redirect_url,
        swagger_js_url="/static/swagger-ui-bundle.js" if os.path.exists(str(_static_dir / "swagger-ui-bundle.js")) else "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js",
        swagger_css_url="/static/swagger-ui.css" if os.path.exists(str(_static_dir / "swagger-ui.css")) else "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css",
    )

@app.get("/redoc", include_in_schema=False)
async def custom_redoc_html(request: Request):
    user = get_session_user(request)
    if not user:
        return RedirectResponse(url="/admin/login")
    return get_redoc_html(
        openapi_url=app.openapi_url,
        title=app.title + " - ReDoc",
        redoc_js_url="https://cdn.jsdelivr.net/npm/redoc@next/bundles/redoc.standalone.js",
    )

# Optionally protect openapi.json too
@app.get("/openapi.json", include_in_schema=False)
async def get_open_api_endpoint(request: Request):
    user = get_session_user(request)
    if not user:
        # Check if it's a browser request
        accept = request.headers.get("accept", "")
        if "text/html" in accept:
            return RedirectResponse(url="/admin/login")
        # For non-browser, we might want to allow or return 401. 
        # But wait, the app might need this? Usually app doesn't need openapi.json.
        return RedirectResponse(url="/admin/login")
    return app.openapi()

app.include_router(events_router)
app.include_router(control_router)
app.include_router(admin_router)
app.include_router(admin_data_router)
app.include_router(pricing_router)


@app.on_event("startup")
async def _startup_checks() -> None:
    admin_token = os.environ.get("ADMIN_TOKEN", "")
    if admin_token == "changeme":
        logger.warning(
            "WARNING: ADMIN_TOKEN is using default value 'changeme'. "
            "Change this in production."
        )


@app.get("/health")
async def health() -> dict:
    try:
        async with async_session() as session:
            await session.execute(text("SELECT 1"))
        return {"status": "ok"}
    except Exception:
        return {"status": "error", "detail": "database unreachable"}
