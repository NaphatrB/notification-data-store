"""SQLAlchemy models for parser-owned tables."""

import uuid

from sqlalchemy import BigInteger, Float, Integer, Numeric, Text, func
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.models import Base


class ParserOffset(Base):
    __tablename__ = "parser_offsets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    parser_name: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    last_seq: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    updated_at: Mapped[str] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )


class StructuredPrice(Base):
    __tablename__ = "structured_prices"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    raw_event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    seq: Mapped[int] = mapped_column(BigInteger, nullable=False)
    parser_version: Mapped[str] = mapped_column(Text, nullable=False)
    supplier: Mapped[str | None] = mapped_column(Text, nullable=True)
    product: Mapped[str | None] = mapped_column(Text, nullable=True)
    product_grade: Mapped[str | None] = mapped_column(Text, nullable=True)
    size: Mapped[str | None] = mapped_column(Text, nullable=True)
    quantity_kg: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    price_per_kg: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    currency: Mapped[str | None] = mapped_column(Text, nullable=True)
    total_kg: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    event_timestamp: Mapped[str] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    llm_raw_response: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[str] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )


class PricingDeadLetter(Base):
    __tablename__ = "pricing_dead_letter"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    raw_event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    seq: Mapped[int] = mapped_column(BigInteger, nullable=False)
    parser_version: Mapped[str] = mapped_column(Text, nullable=False)
    error_type: Mapped[str] = mapped_column(Text, nullable=False)
    error_message: Mapped[str] = mapped_column(Text, nullable=False)
    llm_raw_response: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    original_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
