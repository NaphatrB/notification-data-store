"""Admin Data Viewer — browse raw events and pricing data.

All routes live under /admin/raw* and /admin/pricing*.
Authentication via signed session cookie (shared with admin.py).
"""

import csv
import io
import logging
from datetime import datetime
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import delete, distinct, exists, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin_auth import require_session
from app.db import get_db
from app.models import Device, RawEvent
from app.parser.models import ParserOffset, PricingDeadLetter, StructuredPrice

logger = logging.getLogger("admin_data")

router = APIRouter(prefix="/admin", tags=["admin-data"])

TEMPLATE_DIR = Path(__file__).resolve().parent.parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _check_session(request: Request):
    """Return RedirectResponse to login if session is invalid, else None."""
    user = require_session(request)
    if user is None:
        return RedirectResponse(url="/admin/login", status_code=303)
    return None


def _clamp_limit(limit: int, max_val: int = 500, default: int = 50) -> int:
    if limit < 1:
        return default
    return min(limit, max_val)


# ---------------------------------------------------------------------------
# Raw Events — Full Page
# ---------------------------------------------------------------------------


@router.get("/raw", response_class=HTMLResponse)
async def raw_list_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Render raw events list page with filter controls."""
    redirect = _check_session(request)
    if redirect:
        return redirect

    # Fetch device list for dropdown
    device_result = await db.execute(
        select(Device.id, Device.device_name, Device.device_uuid).order_by(Device.device_name)
    )
    devices = device_result.all()

    # Fetch distinct source types for dropdown
    st_result = await db.execute(
        select(distinct(RawEvent.source_type)).order_by(RawEvent.source_type)
    )
    source_types = [r[0] for r in st_result.all()]

    return templates.TemplateResponse(
        "admin/raw_list.html",
        {
            "request": request,
            "devices": devices,
            "source_types": source_types,
        },
    )


# ---------------------------------------------------------------------------
# Raw Events — Table Partial (HTMX)
# ---------------------------------------------------------------------------


@router.get("/raw/table", response_class=HTMLResponse)
async def raw_table(
    request: Request,
    db: AsyncSession = Depends(get_db),
    deviceId: str | None = Query(None),
    sourceType: str | None = Query(None),
    status: str | None = Query(None),
    q: str | None = Query(None),
    from_: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
    limit: int = Query(50),
    offset: int = Query(0),
):
    """Return raw events table rows as HTMX partial."""
    redirect = _check_session(request)
    if redirect:
        return redirect

    limit = _clamp_limit(limit)
    if offset < 0:
        offset = 0

    # EXISTS subqueries for parse status
    has_price = exists(
        select(StructuredPrice.id).where(
            StructuredPrice.raw_event_id == RawEvent.id
        )
    ).correlate(RawEvent)

    has_dead_letter = exists(
        select(PricingDeadLetter.id).where(
            PricingDeadLetter.raw_event_id == RawEvent.id
        )
    ).correlate(RawEvent)

    # Main query
    stmt = select(
        RawEvent.id,
        RawEvent.seq,
        RawEvent.device_id,
        RawEvent.source_type,
        RawEvent.app_name,
        RawEvent.title,
        RawEvent.event_timestamp,
        RawEvent.received_at,
        has_price.label("is_parsed"),
        has_dead_letter.label("is_dead_letter"),
    )
    count_stmt = select(func.count(RawEvent.id))

    # Filters
    if deviceId:
        try:
            device_uuid = UUID(deviceId)
            stmt = stmt.where(RawEvent.device_id == device_uuid)
            count_stmt = count_stmt.where(RawEvent.device_id == device_uuid)
        except ValueError:
            pass

    if sourceType:
        stmt = stmt.where(RawEvent.source_type == sourceType)
        count_stmt = count_stmt.where(RawEvent.source_type == sourceType)

    if q:
        pattern = f"%{q}%"
        search_cond = or_(
            RawEvent.title.ilike(pattern),
            RawEvent.text.ilike(pattern),
            RawEvent.big_text.ilike(pattern),
        )
        stmt = stmt.where(search_cond)
        count_stmt = count_stmt.where(search_cond)

    if status == "parsed":
        parsed_cond = exists(
            select(StructuredPrice.id).where(StructuredPrice.raw_event_id == RawEvent.id)
        ).correlate(RawEvent)
        stmt = stmt.where(parsed_cond)
        count_stmt = count_stmt.where(parsed_cond)
    elif status == "dead_letter":
        dl_cond = exists(
            select(PricingDeadLetter.id).where(PricingDeadLetter.raw_event_id == RawEvent.id)
        ).correlate(RawEvent)
        stmt = stmt.where(dl_cond)
        count_stmt = count_stmt.where(dl_cond)
    elif status == "unparsed":
        no_price = ~exists(
            select(StructuredPrice.id).where(StructuredPrice.raw_event_id == RawEvent.id)
        ).correlate(RawEvent)
        no_dl = ~exists(
            select(PricingDeadLetter.id).where(PricingDeadLetter.raw_event_id == RawEvent.id)
        ).correlate(RawEvent)
        stmt = stmt.where(no_price).where(no_dl)
        count_stmt = count_stmt.where(no_price).where(no_dl)

    if from_:
        try:
            from_dt = datetime.fromisoformat(from_)
            stmt = stmt.where(RawEvent.event_timestamp >= from_dt)
            count_stmt = count_stmt.where(RawEvent.event_timestamp >= from_dt)
        except ValueError:
            pass

    if to:
        try:
            to_dt = datetime.fromisoformat(to)
            stmt = stmt.where(RawEvent.event_timestamp <= to_dt)
            count_stmt = count_stmt.where(RawEvent.event_timestamp <= to_dt)
        except ValueError:
            pass

    # Count
    total = (await db.execute(count_stmt)).scalar_one()

    # Order + paginate
    stmt = stmt.order_by(RawEvent.seq.desc()).limit(limit).offset(offset)
    result = await db.execute(stmt)
    rows = result.all()

    # Compute parse status
    events = []
    for r in rows:
        if r.is_parsed:
            parse_status = "parsed"
        elif r.is_dead_letter:
            parse_status = "dead_letter"
        else:
            parse_status = "unparsed"
        events.append({
            "id": r.id,
            "seq": r.seq,
            "device_id": r.device_id,
            "source_type": r.source_type,
            "app_name": r.app_name,
            "title": r.title,
            "event_timestamp": r.event_timestamp,
            "received_at": r.received_at,
            "parse_status": parse_status,
        })

    # Build current filter params for pagination links
    params = {}
    if deviceId:
        params["deviceId"] = deviceId
    if sourceType:
        params["sourceType"] = sourceType
    if q:
        params["q"] = q
    if status:
        params["status"] = status
    if from_:
        params["from"] = from_
    if to:
        params["to"] = to
    params["limit"] = str(limit)

    return templates.TemplateResponse(
        "admin/raw_table.html",
        {
            "request": request,
            "events": events,
            "total": total,
            "limit": limit,
            "offset": offset,
            "params": params,
        },
    )


# ---------------------------------------------------------------------------
# Raw Events — CSV Export
# ---------------------------------------------------------------------------


@router.get("/raw/export")
async def raw_export(
    request: Request,
    db: AsyncSession = Depends(get_db),
    deviceId: str | None = Query(None),
    sourceType: str | None = Query(None),
    q: str | None = Query(None),
    from_: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
):
    """Export filtered raw events as CSV. Hard cap 10,000 rows."""
    redirect = _check_session(request)
    if redirect:
        return redirect

    CSV_MAX = 10_000

    stmt = select(
        RawEvent.seq,
        RawEvent.source_type,
        RawEvent.package_name,
        RawEvent.app_name,
        RawEvent.title,
        RawEvent.text,
        RawEvent.big_text,
        RawEvent.notification_id,
        RawEvent.message_hash,
        RawEvent.event_timestamp,
        RawEvent.received_at,
        RawEvent.device_id,
    )

    # Apply filters
    if deviceId:
        try:
            device_uuid = UUID(deviceId)
            stmt = stmt.where(RawEvent.device_id == device_uuid)
        except ValueError:
            pass
    if sourceType:
        stmt = stmt.where(RawEvent.source_type == sourceType)
    if q:
        pattern = f"%{q}%"
        stmt = stmt.where(or_(
            RawEvent.title.ilike(pattern),
            RawEvent.text.ilike(pattern),
            RawEvent.big_text.ilike(pattern),
        ))
    if from_:
        try:
            stmt = stmt.where(RawEvent.event_timestamp >= datetime.fromisoformat(from_))
        except ValueError:
            pass
    if to:
        try:
            stmt = stmt.where(RawEvent.event_timestamp <= datetime.fromisoformat(to))
        except ValueError:
            pass

    stmt = stmt.order_by(RawEvent.seq.desc()).limit(CSV_MAX)
    result = await db.execute(stmt)
    rows = result.all()

    # Build CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "seq", "sourceType", "packageName", "appName", "title",
        "text", "bigText", "notificationId", "messageHash",
        "eventTimestamp", "receivedAt", "deviceId",
    ])

    for r in rows:
        writer.writerow([
            r.seq,
            r.source_type or "",
            r.package_name or "",
            r.app_name or "",
            r.title or "",
            r.text or "",
            r.big_text or "",
            r.notification_id,
            r.message_hash or "",
            r.event_timestamp.isoformat() if r.event_timestamp else "",
            r.received_at.isoformat() if r.received_at else "",
            str(r.device_id) if r.device_id else "",
        ])

    output.seek(0)
    today = datetime.utcnow().strftime("%Y%m%d")
    filename = f"raw_events_export_{today}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Raw Event Detail
# ---------------------------------------------------------------------------


@router.get("/raw/{event_id}", response_class=HTMLResponse)
async def raw_detail(
    request: Request,
    event_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Render full detail page for a single raw event."""
    redirect = _check_session(request)
    if redirect:
        return redirect

    stmt = select(RawEvent).where(RawEvent.id == event_id)
    result = await db.execute(stmt)
    event = result.scalar_one_or_none()

    if event is None:
        return RedirectResponse(url="/admin/raw?error=Event+not+found", status_code=303)

    # Check parse status
    has_price = await db.execute(
        select(exists(
            select(StructuredPrice.id).where(StructuredPrice.raw_event_id == event_id)
        ))
    )
    has_dead = await db.execute(
        select(exists(
            select(PricingDeadLetter.id).where(PricingDeadLetter.raw_event_id == event_id)
        ))
    )

    if has_price.scalar_one():
        parse_status = "parsed"
    elif has_dead.scalar_one():
        parse_status = "dead_letter"
    else:
        parse_status = "unparsed"

    return templates.TemplateResponse(
        "admin/raw_detail.html",
        {
            "request": request,
            "event": event,
            "parse_status": parse_status,
        },
    )


# ---------------------------------------------------------------------------
# Parser Dashboard
# ---------------------------------------------------------------------------


@router.get("/parser", response_class=HTMLResponse)
async def parser_dashboard(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Parser observability dashboard."""
    redirect = _check_session(request)
    if redirect:
        return redirect

    # Parser offset
    offset_row = (await db.execute(
        select(ParserOffset.last_seq, ParserOffset.updated_at)
        .where(ParserOffset.parser_name == "pricing_v1")
    )).first()
    offset_seq = offset_row.last_seq if offset_row else 0
    offset_updated = (
        offset_row.updated_at.strftime("%Y-%m-%d %H:%M:%S") if offset_row and offset_row.updated_at else "never"
    )

    # Total raw events
    total_raw = (await db.execute(select(func.count(RawEvent.id)))).scalar_one()

    # Total parsed price rows + distinct events
    total_price_rows = (await db.execute(select(func.count(StructuredPrice.id)))).scalar_one()
    total_parsed_events = (await db.execute(
        select(func.count(distinct(StructuredPrice.raw_event_id)))
    )).scalar_one()

    # Total dead-letter rows + distinct events
    total_dead_rows = (await db.execute(select(func.count(PricingDeadLetter.id)))).scalar_one()
    total_dead_events = (await db.execute(
        select(func.count(distinct(PricingDeadLetter.raw_event_id)))
    )).scalar_one()

    # By parser version
    version_rows = (await db.execute(
        select(
            StructuredPrice.parser_version,
            func.count(StructuredPrice.id).label("rows"),
            func.count(distinct(StructuredPrice.raw_event_id)).label("events"),
        )
        .group_by(StructuredPrice.parser_version)
        .order_by(StructuredPrice.parser_version)
    )).all()
    versions = [{"version": v.parser_version, "rows": v.rows, "events": v.events} for v in version_rows]

    # Recent parsed — one row per event (latest price row per raw_event_id)
    recent_prices = (await db.execute(
        select(
            StructuredPrice.seq,
            StructuredPrice.supplier,
            StructuredPrice.confidence,
            StructuredPrice.llm_raw_response,
            StructuredPrice.created_at,
            StructuredPrice.raw_event_id,
        )
        .order_by(StructuredPrice.created_at.desc())
        .limit(60)  # fetch extra to dedupe
    )).all()

    # Dedupe by raw_event_id, keep latest
    seen_events: set = set()
    recent_parsed = []
    for r in recent_prices:
        if r.raw_event_id in seen_events:
            continue
        seen_events.add(r.raw_event_id)

        meta = (r.llm_raw_response or {}).get("_llm_meta", {})
        items_list = (r.llm_raw_response or {}).get("items", [])

        recent_parsed.append({
            "seq": r.seq,
            "supplier": r.supplier,
            "item_count": len(items_list) if isinstance(items_list, list) else "?",
            "confidence": r.confidence,
            "llm_duration": f"{meta['duration_s']}s" if meta.get("duration_s") else None,
            "llm_tokens": f"{meta.get('prompt_tokens', '?')}/{meta.get('completion_tokens', '?')}" if meta else None,
            "llm_model": meta.get("model"),
            "created_at": r.created_at,
        })
        if len(recent_parsed) >= 20:
            break

    # Recent dead letters
    recent_dl = (await db.execute(
        select(
            PricingDeadLetter.seq,
            PricingDeadLetter.error_type,
            PricingDeadLetter.error_message,
            PricingDeadLetter.llm_raw_response,
            PricingDeadLetter.created_at,
        )
        .order_by(PricingDeadLetter.created_at.desc())
        .limit(20)
    )).all()

    recent_dead = []
    for d in recent_dl:
        meta = (d.llm_raw_response or {}).get("_llm_meta", {})
        recent_dead.append({
            "seq": d.seq,
            "error_type": d.error_type,
            "error_message": d.error_message,
            "llm_duration": f"{meta['duration_s']}s" if meta.get("duration_s") else None,
            "created_at": d.created_at,
        })

    return templates.TemplateResponse(
        "admin/parser_dashboard.html",
        {
            "request": request,
            "offset_seq": offset_seq,
            "offset_updated": offset_updated,
            "total_raw": total_raw,
            "total_parsed": total_price_rows,
            "total_dead": total_dead_rows,
            "total_parsed_events": total_parsed_events,
            "total_dead_events": total_dead_events,
            "total_price_rows": total_price_rows,
            "versions": versions,
            "recent_parsed": recent_parsed,
            "recent_dead": recent_dead,
        },
    )


# ---------------------------------------------------------------------------
# Parser — Rerun All
# ---------------------------------------------------------------------------


@router.post("/parser/rerun")
async def parser_rerun(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Delete all parsed data + dead letters and reset parser offset to 0.

    The parser's polling loop will automatically re-process everything.
    """
    redirect = _check_session(request)
    if redirect:
        return redirect

    # Delete parsed prices
    del_prices = await db.execute(delete(StructuredPrice))
    prices_deleted = del_prices.rowcount

    # Delete dead letters
    del_dl = await db.execute(delete(PricingDeadLetter))
    dl_deleted = del_dl.rowcount

    # Reset parser offset to 0
    await db.execute(
        update(ParserOffset).values(last_seq=0)
    )

    await db.commit()

    logger.info(
        "Parser rerun triggered: deleted %d prices, %d dead letters, offset reset to 0",
        prices_deleted,
        dl_deleted,
    )

    return RedirectResponse(
        url=f"/admin/pricing?rerun=1&deleted={prices_deleted}&dl={dl_deleted}",
        status_code=303,
    )


# ---------------------------------------------------------------------------
# Pricing — Full Page
# ---------------------------------------------------------------------------


@router.get("/pricing", response_class=HTMLResponse)
async def pricing_list_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Render pricing data list page with filter controls."""
    redirect = _check_session(request)
    if redirect:
        return redirect

    # Fetch distinct suppliers for dropdown (optional enhancement)
    sup_result = await db.execute(
        select(distinct(StructuredPrice.supplier))
        .where(StructuredPrice.supplier.is_not(None))
        .order_by(StructuredPrice.supplier)
    )
    suppliers = [r[0] for r in sup_result.all()]

    # Fetch distinct currencies
    cur_result = await db.execute(
        select(distinct(StructuredPrice.currency))
        .where(StructuredPrice.currency.is_not(None))
        .order_by(StructuredPrice.currency)
    )
    currencies = [r[0] for r in cur_result.all()]

    # Fetch distinct parser versions
    pv_result = await db.execute(
        select(distinct(StructuredPrice.parser_version))
        .order_by(StructuredPrice.parser_version)
    )
    parser_versions = [r[0] for r in pv_result.all()]

    # Fetch distinct senders (raw_events.title)
    sender_result = await db.execute(
        select(distinct(RawEvent.title))
        .join(StructuredPrice, StructuredPrice.raw_event_id == RawEvent.id)
        .where(RawEvent.title.is_not(None))
        .order_by(RawEvent.title)
    )
    senders = [r[0] for r in sender_result.all()]

    return templates.TemplateResponse(
        "admin/pricing_list.html",
        {
            "request": request,
            "suppliers": suppliers,
            "currencies": currencies,
            "parser_versions": parser_versions,
            "senders": senders,
        },
    )


# ---------------------------------------------------------------------------
# Pricing — Table Partial (HTMX)
# ---------------------------------------------------------------------------


def _build_pricing_filters(
    stmt,
    supplier: str | None,
    currency: str | None,
    minPrice: str | None,
    maxPrice: str | None,
    from_: str | None,
    to: str | None,
    parserVersion: str | None,
    q: str | None = None,
    sender: str | None = None,
):
    """Apply pricing filters to a statement. Returns modified statement."""
    if q:
        pattern = f"%{q}%"
        stmt = stmt.where(or_(
            StructuredPrice.supplier.ilike(pattern),
            StructuredPrice.size.ilike(pattern),
            StructuredPrice.product_grade.ilike(pattern),
            RawEvent.title.ilike(pattern),
        ))
    if sender:
        stmt = stmt.where(RawEvent.title == sender)
    if supplier:
        stmt = stmt.where(StructuredPrice.supplier == supplier)
    if currency:
        stmt = stmt.where(StructuredPrice.currency == currency)
    if parserVersion:
        stmt = stmt.where(StructuredPrice.parser_version == parserVersion)
    if minPrice:
        try:
            stmt = stmt.where(StructuredPrice.price_per_kg >= float(minPrice))
        except ValueError:
            pass
    if maxPrice:
        try:
            stmt = stmt.where(StructuredPrice.price_per_kg <= float(maxPrice))
        except ValueError:
            pass
    if from_:
        try:
            stmt = stmt.where(StructuredPrice.event_timestamp >= datetime.fromisoformat(from_))
        except ValueError:
            pass
    if to:
        try:
            stmt = stmt.where(StructuredPrice.event_timestamp <= datetime.fromisoformat(to))
        except ValueError:
            pass
    return stmt


@router.get("/pricing/table", response_class=HTMLResponse)
async def pricing_table(
    request: Request,
    db: AsyncSession = Depends(get_db),
    q: str | None = Query(None),
    supplier: str | None = Query(None),
    currency: str | None = Query(None),
    minPrice: str | None = Query(None),
    maxPrice: str | None = Query(None),
    from_: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
    parserVersion: str | None = Query(None),
    sender: str | None = Query(None),
    limit: int = Query(50),
    offset: int = Query(0),
):
    """Return pricing table rows as HTMX partial."""
    redirect = _check_session(request)
    if redirect:
        return redirect

    limit = _clamp_limit(limit)
    if offset < 0:
        offset = 0

    # Main query — exclude llm_raw_response
    stmt = (
        select(
            StructuredPrice.id,
            StructuredPrice.seq,
            RawEvent.title.label("sender"),
            StructuredPrice.supplier,
            StructuredPrice.product_grade,
            StructuredPrice.size,
            StructuredPrice.quantity_kg,
            StructuredPrice.price_per_kg,
            StructuredPrice.currency,
            StructuredPrice.total_kg,
            StructuredPrice.confidence,
            StructuredPrice.parser_version,
            StructuredPrice.event_timestamp,
        )
        .outerjoin(RawEvent, StructuredPrice.raw_event_id == RawEvent.id)
    )
    count_stmt = (
        select(func.count(StructuredPrice.id))
        .outerjoin(RawEvent, StructuredPrice.raw_event_id == RawEvent.id)
    )

    # Apply filters
    stmt = _build_pricing_filters(stmt, supplier, currency, minPrice, maxPrice, from_, to, parserVersion, q, sender)
    count_stmt = _build_pricing_filters(count_stmt, supplier, currency, minPrice, maxPrice, from_, to, parserVersion, q, sender)

    # Count
    total = (await db.execute(count_stmt)).scalar_one()

    # Order + paginate
    stmt = stmt.order_by(StructuredPrice.seq.desc()).limit(limit).offset(offset)
    result = await db.execute(stmt)
    rows = result.all()

    items = []
    for r in rows:
        items.append({
            "id": r.id,
            "seq": r.seq,
            "sender": r.sender,
            "supplier": r.supplier,
            "product_grade": r.product_grade,
            "size": r.size,
            "quantity_kg": float(r.quantity_kg) if r.quantity_kg is not None else None,
            "price_per_kg": float(r.price_per_kg) if r.price_per_kg is not None else None,
            "currency": r.currency,
            "total_kg": float(r.total_kg) if r.total_kg is not None else None,
            "confidence": r.confidence,
            "parser_version": r.parser_version,
            "event_timestamp": r.event_timestamp,
        })

    # Build filter params for pagination
    params = {}
    if q:
        params["q"] = q
    if supplier:
        params["supplier"] = supplier
    if currency:
        params["currency"] = currency
    if minPrice:
        params["minPrice"] = minPrice
    if maxPrice:
        params["maxPrice"] = maxPrice
    if from_:
        params["from"] = from_
    if to:
        params["to"] = to
    if parserVersion:
        params["parserVersion"] = parserVersion
    if sender:
        params["sender"] = sender
    params["limit"] = str(limit)

    return templates.TemplateResponse(
        "admin/pricing_table.html",
        {
            "request": request,
            "items": items,
            "total": total,
            "limit": limit,
            "offset": offset,
            "params": params,
        },
    )


# ---------------------------------------------------------------------------
# Pricing — CSV Export
# ---------------------------------------------------------------------------


@router.get("/pricing/export")
async def pricing_export(
    request: Request,
    db: AsyncSession = Depends(get_db),
    q: str | None = Query(None),
    supplier: str | None = Query(None),
    currency: str | None = Query(None),
    minPrice: str | None = Query(None),
    maxPrice: str | None = Query(None),
    from_: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
    parserVersion: str | None = Query(None),
    sender: str | None = Query(None),
):
    """Export filtered pricing data as CSV. Hard cap 10,000 rows."""
    redirect = _check_session(request)
    if redirect:
        return redirect

    CSV_MAX = 10_000

    stmt = (
        select(
            RawEvent.title.label("sender"),
            StructuredPrice.supplier,
            StructuredPrice.size,
            StructuredPrice.product_grade,
            StructuredPrice.quantity_kg,
            StructuredPrice.price_per_kg,
            StructuredPrice.currency,
            StructuredPrice.event_timestamp,
        )
        .outerjoin(RawEvent, StructuredPrice.raw_event_id == RawEvent.id)
    )

    stmt = _build_pricing_filters(stmt, supplier, currency, minPrice, maxPrice, from_, to, parserVersion, q, sender)
    stmt = stmt.order_by(StructuredPrice.seq.desc()).limit(CSV_MAX)

    result = await db.execute(stmt)
    rows = result.all()

    # Build CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["sender", "supplier", "size", "grade", "quantityKg", "pricePerKg", "currency", "eventTimestamp"])

    for r in rows:
        writer.writerow([
            r.sender or "",
            r.supplier or "",
            r.size or "",
            r.product_grade or "",
            float(r.quantity_kg) if r.quantity_kg is not None else "",
            float(r.price_per_kg) if r.price_per_kg is not None else "",
            r.currency or "",
            r.event_timestamp.isoformat() if r.event_timestamp else "",
        ])

    output.seek(0)
    today = datetime.utcnow().strftime("%Y%m%d")
    filename = f"pricing_export_{today}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
