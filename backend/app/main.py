from fastapi import FastAPI
from sqlalchemy import text

from app.database import async_session
from app.routes.events import router as events_router

app = FastAPI(
    title="ANLA Notification Data Store",
    description="Ingestion-only backend for ANLA notification events.",
    version="0.1.0",
)

app.include_router(events_router)


@app.get("/health")
async def health() -> dict:
    try:
        async with async_session() as session:
            await session.execute(text("SELECT 1"))
        return {"status": "ok"}
    except Exception:
        return {"status": "error", "detail": "database unreachable"}
