from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Ingestion schemas (existing)
# ---------------------------------------------------------------------------


class NotificationEventIn(BaseModel):
    """Incoming ANLA notification event. Matches json-schema.json contract."""

    model_config = ConfigDict(extra="ignore")

    # Optional — accepted but not stored
    id: int | None = None

    # Required — stored
    packageName: str
    timestamp: int  # epoch millis
    notificationId: int
    sourceType: Literal["whatsapp", "telegram", "facebook", "sms", "notification"]
    messageHash: str | None = None

    # Required — validated but NOT stored
    deliveryStatus: Literal["PENDING", "SENT", "FAILED"]

    # Optional — stored
    appName: str | None = None
    title: str | None = None
    text: str | None = None
    bigText: str | None = None


class EventResponse(BaseModel):
    status: str
    duplicate: bool


class EventOut(BaseModel):
    """Single raw event returned by read endpoints. camelCase output."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    messageHash: str | None = Field(validation_alias="message_hash", default=None)
    packageName: str = Field(validation_alias="package_name")
    appName: str | None = Field(validation_alias="app_name", default=None)
    title: str | None = None
    text: str | None = None
    bigText: str | None = Field(validation_alias="big_text", default=None)
    eventTimestamp: datetime = Field(validation_alias="event_timestamp")
    notificationId: int = Field(validation_alias="notification_id")
    sourceType: str = Field(validation_alias="source_type")
    receivedAt: datetime = Field(validation_alias="received_at")


class EventListResponse(BaseModel):
    items: list[EventOut]
    total: int
    limit: int
    offset: int


class StatsResponse(BaseModel):
    totalEvents: int
    bySource: dict[str, int]
    byAppName: dict[str, int]
    byPackageName: dict[str, int]
    lastEventAt: datetime | None


# ---------------------------------------------------------------------------
# Control Plane schemas
# ---------------------------------------------------------------------------


class DeviceRegisterRequest(BaseModel):
    """Body for POST /control/v1/devices/register."""

    deviceUuid: str
    deviceName: str | None = None
    deviceModel: str | None = None
    androidVersion: str | None = None
    appVersion: str | None = None


class DeviceRegisterResponse(BaseModel):
    deviceId: UUID
    status: str


class DeviceApproveResponse(BaseModel):
    deviceId: UUID
    status: str
    token: str  # plaintext — returned ONCE


class DeviceRevokeResponse(BaseModel):
    deviceId: UUID
    status: str


class DeviceConfigResponse(BaseModel):
    status: str
    apiBaseUrl: str | None = None
    captureMode: str
    pollIntervalSeconds: int
    parserEnabled: bool


# ---------------------------------------------------------------------------
# Fleet Visibility schemas (Phase 2A)
# ---------------------------------------------------------------------------


class DeviceListItem(BaseModel):
    """Single device in fleet listing — includes computed ingestion stats."""

    deviceId: UUID
    deviceUuid: str
    deviceName: str | None = None
    status: str
    lastSeenAt: datetime | None = None
    approvedAt: datetime | None = None
    appVersion: str | None = None
    androidVersion: str | None = None
    totalEventsIngested: int = 0
    lastEventAt: datetime | None = None


class DeviceListResponse(BaseModel):
    items: list[DeviceListItem]
    total: int
    limit: int
    offset: int


class TokenRotateResponse(BaseModel):
    deviceId: UUID
    token: str  # plaintext — returned ONCE
