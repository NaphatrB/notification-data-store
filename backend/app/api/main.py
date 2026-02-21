from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.db import async_session
from app.api.routes.admin import router as admin_router
from app.api.routes.admin_data import router as admin_data_router
from app.api.routes.control import router as control_router
from app.api.routes.events import router as events_router
from app.api.routes.pricing import router as pricing_router

import logging
import os

logger = logging.getLogger("anla")

app = FastAPI(
    title="ANLA Notification Data Store",
    description="Ingestion & Control Plane backend for ANLA.",
    version="0.6.0",
)

# Static files
_static_dir = Path(__file__).resolve().parent.parent / "static"
app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")

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
