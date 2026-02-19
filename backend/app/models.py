import uuid

from sqlalchemy import Index, Text, Integer, func
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class RawEvent(Base):
    __tablename__ = "raw_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    message_hash: Mapped[str | None] = mapped_column(
        Text, unique=True, nullable=True
    )
    package_name: Mapped[str] = mapped_column(Text, nullable=False)
    app_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    big_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    event_timestamp: Mapped[str] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
    notification_id: Mapped[int] = mapped_column(Integer, nullable=False)
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    received_at: Mapped[str] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index("ix_raw_events_event_timestamp", "event_timestamp"),
        Index("ix_raw_events_source_type", "source_type"),
    )
