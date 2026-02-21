from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import require_device_token
from app.db import get_db
from app.models import Device, RawEvent
from app.api.schemas import (
    EventListResponse,
    EventOut,
    EventResponse,
    NotificationEventIn,
    StatsResponse,
)

router = APIRouter(prefix="/api/v1", tags=["events"])


@router.post("/events", response_model=EventResponse, status_code=201)
async def ingest_event(
    event: NotificationEventIn,
    device: Device = Depends(require_device_token),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    # Convert epoch millis → UTC datetime
    event_timestamp = datetime.fromtimestamp(
        event.timestamp / 1000.0, tz=timezone.utc
    )

    row = RawEvent(
        message_hash=event.messageHash,
        package_name=event.packageName,
        app_name=event.appName,
        title=event.title,
        text=event.text,
        big_text=event.bigText,
        event_timestamp=event_timestamp,
        notification_id=event.notificationId,
        source_type=event.sourceType,
        device_id=device.id,
    )

    try:
        db.add(row)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        # Duplicate message_hash — idempotent accept
        return JSONResponse(
            status_code=200,
            content={"status": "accepted", "duplicate": True},
        )

    return JSONResponse(
        status_code=201,
        content={"status": "accepted", "duplicate": False},
    )


def _parse_datetime(value: str) -> datetime:
    """Parse ISO datetime string. Naive datetimes are treated as UTC."""
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


@router.get("/events", response_model=EventListResponse)
async def list_events(
    db: AsyncSession = Depends(get_db),
    sourceType: str | None = Query(None),
    packageName: str | None = Query(None),
    appName: str | None = Query(None),
    from_: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
    limit: int = Query(50, ge=1),
    offset: int = Query(0, ge=0),
    sort: Literal["asc", "desc"] = Query("desc"),
) -> EventListResponse:
    # Cap limit at 500
    if limit > 500:
        limit = 500

    # Parse date filters
    from_dt: datetime | None = None
    to_dt: datetime | None = None
    if from_ is not None:
        try:
            from_dt = _parse_datetime(from_)
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid 'from' date format. Use ISO 8601.")
    if to is not None:
        try:
            to_dt = _parse_datetime(to)
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid 'to' date format. Use ISO 8601.")

    # Build base filter
    conditions = []
    if sourceType is not None:
        conditions.append(RawEvent.source_type == sourceType)
    if packageName is not None:
        conditions.append(RawEvent.package_name == packageName)
    if appName is not None:
        conditions.append(RawEvent.app_name == appName)
    if from_dt is not None:
        conditions.append(RawEvent.event_timestamp >= from_dt)
    if to_dt is not None:
        conditions.append(RawEvent.event_timestamp <= to_dt)

    # Count total matching rows
    count_stmt = select(func.count(RawEvent.id))
    for cond in conditions:
        count_stmt = count_stmt.where(cond)
    total = (await db.execute(count_stmt)).scalar_one()

    # Fetch paginated items
    order_col = RawEvent.event_timestamp.asc() if sort == "asc" else RawEvent.event_timestamp.desc()
    items_stmt = select(RawEvent)
    for cond in conditions:
        items_stmt = items_stmt.where(cond)
    items_stmt = items_stmt.order_by(order_col).limit(limit).offset(offset)
    result = await db.execute(items_stmt)
    rows = result.scalars().all()

    return EventListResponse(
        items=[EventOut.model_validate(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/events/{event_id}", response_model=EventOut)
async def get_event(
    event_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> EventOut:
    stmt = select(RawEvent).where(RawEvent.id == event_id)
    result = await db.execute(stmt)
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return EventOut.model_validate(row)


@router.get("/stats", response_model=StatsResponse)
async def get_stats(
    db: AsyncSession = Depends(get_db),
) -> StatsResponse:
    # Total events
    total = (await db.execute(select(func.count(RawEvent.id)))).scalar_one()

    # Count by source type — dynamic, only keys present in DB
    source_stmt = select(
        RawEvent.source_type, func.count(RawEvent.id)
    ).group_by(RawEvent.source_type)
    source_result = await db.execute(source_stmt)
    by_source = {row[0]: row[1] for row in source_result.all()}

    # Count by app name — dynamic, only keys present in DB
    app_stmt = select(
        RawEvent.app_name, func.count(RawEvent.id)
    ).where(RawEvent.app_name.is_not(None)).group_by(RawEvent.app_name)
    app_result = await db.execute(app_stmt)
    by_app_name = {row[0]: row[1] for row in app_result.all()}

    # Count by package name — dynamic, only keys present in DB
    pkg_stmt = select(
        RawEvent.package_name, func.count(RawEvent.id)
    ).group_by(RawEvent.package_name)
    pkg_result = await db.execute(pkg_stmt)
    by_package_name = {row[0]: row[1] for row in pkg_result.all()}

    # Last event timestamp
    last_event = (await db.execute(select(func.max(RawEvent.event_timestamp)))).scalar_one()

    return StatsResponse(
        totalEvents=total,
        bySource=by_source,
        byAppName=by_app_name,
        byPackageName=by_package_name,
        lastEventAt=last_event,
    )
