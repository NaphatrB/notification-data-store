# CAPABILITY.md — ANLA Notification Data Store

What this system can do today.

---

## Ingestion

- Accepts individual ANLA notification events via `POST /api/v1/events`
- Validates incoming JSON against the ANLA contract (Pydantic v2)
- Rejects unknown fields silently (tolerant ingestion)
- Rejects invalid `sourceType` or `deliveryStatus` enum values (422)
- Converts client `timestamp` (epoch millis) to UTC `TIMESTAMPTZ`
- Generates server-side UUID for each stored event
- Sets `received_at` to server time on insert

## Idempotency

- Uses `messageHash` as a deduplication key
- Events with a duplicate `messageHash` return `200 {"status": "accepted", "duplicate": true}` — no error, no re-insert
- Events with `messageHash: null` (or absent) always insert — no deduplication applied
- PostgreSQL UNIQUE constraint on `message_hash` (allows multiple NULLs)
- Never returns 409 for duplicates

## Validation

- Required fields enforced: `packageName`, `timestamp`, `notificationId`, `sourceType`, `deliveryStatus`
- `messageHash` accepted as string, null, or absent (defaults to null)
- `sourceType` restricted to: `whatsapp`, `telegram`, `facebook`, `sms`, `notification`
- `deliveryStatus` restricted to: `PENDING`, `SENT`, `FAILED` — validated then discarded
- Client `id` accepted but not stored (client-local PK)
- Client-internal fields (`lastAttemptTimestamp`, `retryCount`, etc.) silently ignored

## Storage

- All events stored immutably in PostgreSQL `raw_events` table
- Columns: `id` (UUID), `message_hash`, `package_name`, `app_name`, `title`, `text`, `big_text`, `event_timestamp`, `notification_id`, `source_type`, `received_at`
- Indexed on `event_timestamp` and `source_type` for query performance
- Data queryable directly via `psql`

## Health Check

- `GET /health` returns `{"status": "ok"}` with live database connectivity check
- Returns `{"status": "error", "detail": "database unreachable"}` if DB is down

## Query Layer (Phase 1.5)

- `GET /api/v1/events` — paginated list of raw events
  - Filter by `sourceType` (free-form string, matches against DB values)
  - Filter by `packageName` (exact match)
  - Filter by `appName` (exact match)
  - Filter by date range (`from`, `to`) on `eventTimestamp` — inclusive both ends
  - All filters are combinable
  - Accepts ISO 8601 datetimes; naive datetimes treated as UTC
  - Pagination via `limit` (default 50, max 500) and `offset` (default 0)
  - Sort by `eventTimestamp` ascending or descending (default `desc`)
  - Returns `items`, `total`, `limit`, `offset`
- `GET /api/v1/events/{id}` — single event by UUID
  - Returns bare camelCase object
  - 404 if not found
  - 422 for invalid UUID format
- `GET /api/v1/stats` — ingestion statistics
  - `totalEvents` — total row count
  - `bySource` — count per source type (dynamic, only keys present in DB)
  - `byAppName` — count per app name (dynamic, excludes null)
  - `byPackageName` — count per package name (dynamic)
  - `lastEventAt` — most recent `eventTimestamp` or null if empty
- All read endpoints are strictly read-only — no mutations
- Response fields use camelCase (API) mapped from snake_case (DB)

## API Documentation

- Swagger UI at `/docs`
- ReDoc at `/redoc`
- OpenAPI JSON at `/openapi.json`
- Auto-generated from Pydantic models and route definitions

## Infrastructure

- Runs via `docker compose up --build` (single command)
- Two containers: PostgreSQL 15 + FastAPI (uvicorn)
- Automatic database migrations on startup (Alembic)
- Automatic DB readiness wait with retry loop
- PostgreSQL healthcheck in compose (pg_isready)
- Configuration via `.env` file (not committed)
- Persistent PostgreSQL volume across restarts

---

## Not Yet Implemented

- Authentication / authorization
- Batch ingestion (multiple events per request)
- Event parsing or business logic
- Delivery queue or retry mechanisms
- Media handling
- Admin UI
- Structured query endpoints (GET/search)
