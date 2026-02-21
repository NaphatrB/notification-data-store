"""Pricing Query API — read-only analytics layer over structured_prices.

All routes live under /api/v1/pricing.
All endpoints require admin authentication.
"""

import logging
from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import require_admin
from app.api.schemas import (
    PricingItemOut,
    PricingListResponse,
    PricingRawEventResponse,
    PricingRawLineItem,
    PricingSummaryResponse,
)
from app.db import get_db
from app.parser.models import StructuredPrice

logger = logging.getLogger("pricing_api")

router = APIRouter(
    prefix="/api/v1/pricing",
    tags=["pricing"],
    dependencies=[Depends(require_admin)],
)

# Allowed sort columns — strict whitelist to prevent injection
_SORT_COLUMNS = {
    "eventTimestamp": StructuredPrice.event_timestamp,
    "pricePerKg": StructuredPrice.price_per_kg,
    "quantityKg": StructuredPrice.quantity_kg,
}


# ---------------------------------------------------------------------------
# List Pricing Records
# ---------------------------------------------------------------------------


@router.get("", response_model=PricingListResponse)
async def list_pricing(
    db: AsyncSession = Depends(get_db),
    supplier: str | None = Query(None),
    currency: str | None = Query(None),
    productGrade: str | None = Query(None),
    parserVersion: str | None = Query(None),
    minPrice: float | None = Query(None),
    maxPrice: float | None = Query(None),
    minQuantity: float | None = Query(None),
    maxQuantity: float | None = Query(None),
    from_: datetime | None = Query(None, alias="from"),
    to: datetime | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    sort: Literal["eventTimestamp", "pricePerKg", "quantityKg"] | None = Query(None),
    order: Literal["asc", "desc"] = Query("desc"),
) -> PricingListResponse:
    """Return paginated, filterable list of structured pricing records."""

    # Base query — exclude llm_raw_response
    stmt = select(
        StructuredPrice.id,
        StructuredPrice.raw_event_id,
        StructuredPrice.seq,
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
    count_stmt = select(func.count(StructuredPrice.id))

    # Apply filters
    if supplier is not None:
        stmt = stmt.where(StructuredPrice.supplier == supplier)
        count_stmt = count_stmt.where(StructuredPrice.supplier == supplier)
    if currency is not None:
        stmt = stmt.where(StructuredPrice.currency == currency)
        count_stmt = count_stmt.where(StructuredPrice.currency == currency)
    if productGrade is not None:
        stmt = stmt.where(StructuredPrice.product_grade == productGrade)
        count_stmt = count_stmt.where(StructuredPrice.product_grade == productGrade)
    if parserVersion is not None:
        stmt = stmt.where(StructuredPrice.parser_version == parserVersion)
        count_stmt = count_stmt.where(StructuredPrice.parser_version == parserVersion)
    if minPrice is not None:
        stmt = stmt.where(StructuredPrice.price_per_kg >= minPrice)
        count_stmt = count_stmt.where(StructuredPrice.price_per_kg >= minPrice)
    if maxPrice is not None:
        stmt = stmt.where(StructuredPrice.price_per_kg <= maxPrice)
        count_stmt = count_stmt.where(StructuredPrice.price_per_kg <= maxPrice)
    if minQuantity is not None:
        stmt = stmt.where(StructuredPrice.quantity_kg >= minQuantity)
        count_stmt = count_stmt.where(StructuredPrice.quantity_kg >= minQuantity)
    if maxQuantity is not None:
        stmt = stmt.where(StructuredPrice.quantity_kg <= maxQuantity)
        count_stmt = count_stmt.where(StructuredPrice.quantity_kg <= maxQuantity)
    if from_ is not None:
        stmt = stmt.where(StructuredPrice.event_timestamp >= from_)
        count_stmt = count_stmt.where(StructuredPrice.event_timestamp >= from_)
    if to is not None:
        stmt = stmt.where(StructuredPrice.event_timestamp <= to)
        count_stmt = count_stmt.where(StructuredPrice.event_timestamp <= to)

    # Count
    total = (await db.execute(count_stmt)).scalar_one()

    # Sorting
    if sort is not None:
        sort_col = _SORT_COLUMNS[sort]
        stmt = stmt.order_by(sort_col.asc() if order == "asc" else sort_col.desc())
    else:
        stmt = stmt.order_by(StructuredPrice.seq.desc())

    # Pagination
    stmt = stmt.limit(limit).offset(offset)

    result = await db.execute(stmt)
    rows = result.all()

    items = [
        PricingItemOut(
            rawEventId=r.raw_event_id,
            seq=r.seq,
            supplier=r.supplier,
            productGrade=r.product_grade,
            size=r.size,
            quantityKg=float(r.quantity_kg) if r.quantity_kg is not None else None,
            pricePerKg=float(r.price_per_kg) if r.price_per_kg is not None else None,
            currency=r.currency,
            totalKg=float(r.total_kg) if r.total_kg is not None else None,
            confidence=r.confidence,
            parserVersion=r.parser_version,
            eventTimestamp=r.event_timestamp,
        )
        for r in rows
    ]

    return PricingListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


# ---------------------------------------------------------------------------
# Single Raw Event Pricing
# ---------------------------------------------------------------------------


@router.get("/raw/{raw_event_id}", response_model=PricingRawEventResponse)
async def get_raw_event_pricing(
    raw_event_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> PricingRawEventResponse:
    """Return all structured line items for a given raw event."""

    stmt = select(
        StructuredPrice.raw_event_id,
        StructuredPrice.event_timestamp,
        StructuredPrice.supplier,
        StructuredPrice.total_kg,
        StructuredPrice.product_grade,
        StructuredPrice.size,
        StructuredPrice.quantity_kg,
        StructuredPrice.price_per_kg,
        StructuredPrice.currency,
        StructuredPrice.confidence,
        StructuredPrice.parser_version,
    ).where(
        StructuredPrice.raw_event_id == raw_event_id
    ).order_by(StructuredPrice.seq)

    result = await db.execute(stmt)
    rows = result.all()

    if not rows:
        raise HTTPException(status_code=404, detail="No pricing data for this raw event")

    # Top-level fields: take from first row; null supplier if inconsistent
    first = rows[0]
    suppliers = {r.supplier for r in rows if r.supplier is not None}
    top_supplier = first.supplier if len(suppliers) <= 1 else None
    top_total_kg = float(first.total_kg) if first.total_kg is not None else None

    line_items = [
        PricingRawLineItem(
            productGrade=r.product_grade,
            size=r.size,
            quantityKg=float(r.quantity_kg) if r.quantity_kg is not None else None,
            pricePerKg=float(r.price_per_kg) if r.price_per_kg is not None else None,
            currency=r.currency,
            confidence=r.confidence,
            parserVersion=r.parser_version,
        )
        for r in rows
    ]

    return PricingRawEventResponse(
        rawEventId=first.raw_event_id,
        eventTimestamp=first.event_timestamp,
        supplier=top_supplier,
        totalKg=top_total_kg,
        items=line_items,
    )


# ---------------------------------------------------------------------------
# Summary / Aggregation
# ---------------------------------------------------------------------------


@router.get("/summary", response_model=PricingSummaryResponse)
async def pricing_summary(
    db: AsyncSession = Depends(get_db),
    supplier: str | None = Query(None),
    currency: str | None = Query(None),
    from_: datetime | None = Query(None, alias="from"),
    to: datetime | None = Query(None),
) -> PricingSummaryResponse:
    """Return aggregate statistics over structured pricing data."""

    stmt = select(
        func.avg(StructuredPrice.price_per_kg).label("avg_price"),
        func.sum(StructuredPrice.quantity_kg).label("total_volume"),
        func.count(func.distinct(StructuredPrice.supplier)).label("unique_suppliers"),
        func.count(func.distinct(StructuredPrice.raw_event_id)).label("unique_events"),
        func.min(StructuredPrice.price_per_kg).label("min_price"),
        func.max(StructuredPrice.price_per_kg).label("max_price"),
    )

    if supplier is not None:
        stmt = stmt.where(StructuredPrice.supplier == supplier)
    if currency is not None:
        stmt = stmt.where(StructuredPrice.currency == currency)
    if from_ is not None:
        stmt = stmt.where(StructuredPrice.event_timestamp >= from_)
    if to is not None:
        stmt = stmt.where(StructuredPrice.event_timestamp <= to)

    result = await db.execute(stmt)
    row = result.one()

    return PricingSummaryResponse(
        averagePricePerKg=round(float(row.avg_price), 4) if row.avg_price is not None else None,
        totalVolumeKg=float(row.total_volume) if row.total_volume is not None else 0,
        uniqueSuppliers=row.unique_suppliers or 0,
        uniqueEvents=row.unique_events or 0,
        minPricePerKg=float(row.min_price) if row.min_price is not None else None,
        maxPricePerKg=float(row.max_price) if row.max_price is not None else None,
    )
