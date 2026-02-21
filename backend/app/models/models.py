import uuid

from sqlalchemy import BigInteger, Boolean, ForeignKey, Index, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class RawEvent(Base):
    __tablename__ = "raw_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    seq: Mapped[int] = mapped_column(
        BigInteger,
        unique=True,
        nullable=False,
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
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("devices.id"), nullable=True
    )

    __table_args__ = (
        Index("ix_raw_events_event_timestamp", "event_timestamp"),
        Index("ix_raw_events_source_type", "source_type"),
        Index("ix_raw_events_seq", "seq"),
        Index("ix_raw_events_device_id", "device_id"),
    )


# ---------------------------------------------------------------------------
# Control Plane models
# ---------------------------------------------------------------------------


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    device_uuid: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    device_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    device_model: Mapped[str | None] = mapped_column(Text, nullable=True)
    android_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    app_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")
    created_at: Mapped[str] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    approved_at: Mapped[str | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    last_seen_at: Mapped[str | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )

    tokens: Mapped[list["DeviceToken"]] = relationship(back_populates="device")
    config: Mapped["DeviceConfig | None"] = relationship(back_populates="device", uselist=False)

    __table_args__ = (
        Index("ix_devices_status", "status"),
    )


class DeviceToken(Base):
    __tablename__ = "device_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("devices.id"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(Text, nullable=False)
    token_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    revoked_at: Mapped[str | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    expires_at: Mapped[str | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )

    device: Mapped["Device"] = relationship(back_populates="tokens")

    __table_args__ = (
        Index("ix_device_tokens_device_id", "device_id"),
        Index("ix_device_tokens_token_hash", "token_hash"),
    )


class DeviceConfig(Base):
    __tablename__ = "device_config"

    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("devices.id"), primary_key=True
    )
    api_base_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    capture_mode: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="WHATSAPP_ONLY"
    )
    poll_interval_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="300"
    )
    parser_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
    updated_at: Mapped[str] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )

    device: Mapped["Device"] = relationship(back_populates="config")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    actor: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    target_type: Mapped[str] = mapped_column(Text, nullable=False)
    target_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    metadata_: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[str] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_audit_logs_created_at", "created_at"),
        Index("ix_audit_logs_target_id", "target_id"),
    )
