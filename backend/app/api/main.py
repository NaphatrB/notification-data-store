from fastapi import FastAPI
from sqlalchemy import text

from app.db import async_session
from app.api.routes.control import router as control_router
from app.api.routes.events import router as events_router

app = FastAPI(
    title="ANLA Notification Data Store",
    description="Ingestion & Control Plane backend for ANLA.",
    version="0.2.0",
)

app.include_router(events_router)
app.include_router(control_router)


@app.get("/health")
async def health() -> dict:
    try:
        async with async_session() as session:
            await session.execute(text("SELECT 1"))
        return {"status": "ok"}
    except Exception:
        return {"status": "error", "detail": "database unreachable"}
