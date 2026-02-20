# CAPABILITY.md — ANLA Notification Data Store

What this system can do today.

---

## Ingestion

- Accepts individual ANLA notification events via `POST /api/v1/events`
- **Authenticated** — requires Bearer token issued by Control Plane
- Token validated against `device_tokens` (SHA-256 hash lookup)
- Device must be in `approved` status; token must not be revoked or expired
- Updates `device.last_seen_at` on every authenticated request
- Returns 401 for missing, invalid, revoked, or expired tokens
- Validates incoming JSON against the ANLA contract (Pydantic v2)
- Rejects unknown fields silently (tolerant ingestion via `extra="ignore"`)
- Rejects invalid `sourceType` or `deliveryStatus` enum values (422)
- Converts client `timestamp` (epoch millis) to UTC `TIMESTAMPTZ`
- Generates server-side UUID for each stored event
- Assigns monotonic `seq` (BIGSERIAL) for cursor-based processing
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
- Columns: `id` (UUID), `seq` (BIGINT, unique), `message_hash`, `package_name`, `app_name`, `title`, `text`, `big_text`, `event_timestamp`, `notification_id`, `source_type`, `received_at`
- Indexed on `event_timestamp`, `source_type`, and `seq`
- Data queryable directly via `psql`

## Health Check

- `GET /health` returns `{"status": "ok"}` with live database connectivity check
- Returns `{"status": "error", "detail": "database unreachable"}` if DB is down

## Query Layer

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

## Pricing Parser (v1)

Autonomous background service that polls `raw_events`, sends candidates to a local LLM, and writes structured pricing data.

### Candidate Selection

Two-layer filter — both applied before any LLM call:

1. **Metadata filters** (SQL-level, configurable via env vars)
   - `PARSER_SOURCE_FILTER` — comma-separated allowlist of `source_type` values (e.g. `whatsapp`)
   - `PARSER_PACKAGE_FILTER` — comma-separated allowlist of `package_name` values
   - `PARSER_APP_FILTER` — comma-separated allowlist of `app_name` values
   - All case-insensitive; empty = accept all
   - Each non-empty list is an independent gate — event must match every configured list
   - Applied at the SQL query level so non-matching events are never fetched
2. **Text heuristic filter** (optional, off by default)
   - Enabled via `PARSER_TEXT_FILTER_ENABLED=true`
   - Requires notification text to contain `kg` + a numeric pattern
   - When disabled, all events matching metadata filters are sent to the LLM

### LLM Integration

- Calls Ollama (`/api/generate`) with structured JSON output
- Model: Qwen3 8B (Q4_K_M quantization) — configurable via `LLM_MODEL`
- Temperature 0.1, max 1024 tokens
- System prompt instructs extraction of: supplier, currency, total_kg, line items (size, grade, quantity_kg, price_per_kg), confidence
- Input text truncated at 8000 chars with logged warning
- Automatic retry (1 retry on LLM failure, 1 retry on validation failure)

### Validation

- LLM output validated via Pydantic (`PricingExtraction` / `PricingItem`)
- All price/quantity fields must be positive
- Items array must not be empty
- `total_kg` consistency check (within 10% of sum of item quantities) — logged as warning, does not block persistence

### Persistence

- Parsed line items stored in `structured_prices` table
  - One row per line item: `raw_event_id`, `seq`, `supplier`, `product_grade`, `size`, `quantity_kg`, `price_per_kg`, `currency`, `total_kg`, `confidence`, `parser_version`, `llm_raw_response` (JSONB)
  - Indexed on `raw_event_id` and `seq`
- **Replay idempotency**: re-processing an event deletes existing rows for that `raw_event_id` before inserting, so `--reset-offset` produces clean results

### Dead Letter Queue

- Events that fail LLM or validation are written to `pricing_dead_letter`
  - Columns: `raw_event_id`, `seq`, `parser_version`, `error_type`, `error_message`, `llm_raw_response`, `original_text`
  - Error types: `llm_error`, `validation_error`
- Dead-lettered events do not block the pipeline — offset advances past them

### Offset Management

- Cursor-based: tracks `last_seq` in `parser_offsets` table per `parser_name`
- Offset advances only after a full batch is processed and committed
- When metadata filters skip events, offset jumps to global max `seq` to avoid re-scanning gaps
- CLI flags: `--reset-offset` / `--start-from-beginning` to reprocess all events
- Can also reset via direct SQL: `UPDATE parser_offsets SET last_seq = 0`

### Observability

- Prometheus metrics on port 9090 (`/metrics`)
  - `parser_processed_total` — events processed (counter)
  - `parser_failed_total` — events that failed LLM/validation (counter)
  - `parser_dead_letter_total` — events sent to dead letter (counter)
  - `parser_batch_latency_seconds` — batch processing time (histogram)
  - `parser_oldest_unprocessed_seconds` — age of oldest unprocessed event (gauge)
- Structured logging with timestamps, log level, and module name

### Configuration

All via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_ENDPOINT` | `http://llm.buffalo-cliff.ts.net:11434` | Ollama API base URL |
| `LLM_MODEL` | `qwen3:8b` | Ollama model name |
| `PARSER_BATCH_SIZE` | `10` | Events per polling batch |
| `POLL_INTERVAL_SECONDS` | `30` | Sleep between polls when idle |
| `PARSER_NAME` | `pricing_v1` | Offset namespace |
| `PARSER_SOURCE_FILTER` | _(empty)_ | Source type allowlist |
| `PARSER_PACKAGE_FILTER` | _(empty)_ | Package name allowlist |
| `PARSER_APP_FILTER` | _(empty)_ | App name allowlist |
| `PARSER_TEXT_FILTER_ENABLED` | `false` | Enable text heuristic gate |

## Control Plane

Device registration, approval, token issuance, revocation, and remote configuration delivery.

### Device Lifecycle

- State machine: `pending` → `approved` → `revoked`; `approved` → `disabled`
- Devices in `pending` cannot ingest
- Devices in `approved` can ingest (Bearer token required)
- Devices in `revoked` or `disabled` — all tokens invalidated, ingestion blocked
- No automatic approval — admin action required

### Authentication

- **Admin endpoints**: protected by `X-Admin-Token` header
  - Token sourced from `ADMIN_TOKEN` environment variable
  - Constant-time comparison to prevent timing attacks
  - Returns 401 if missing or invalid
- **Device endpoints**: protected by Bearer token
  - Token issued once during approval (plaintext never stored or logged)
  - Stored as SHA-256 hash in `device_tokens`
  - Token format: `anla_` prefix + 32 random bytes (url-safe base64, ~43 chars)
  - Multiple tokens per device supported
  - Validation checks: hash match, not revoked, not expired, device status == approved

### Endpoints

- `POST /control/v1/devices/register` — register or re-register a device
  - Accepts: `deviceUuid`, `deviceName`, `deviceModel`, `androidVersion`, `appVersion`
  - New device created with `status=pending`
  - Existing device: metadata updated, existing status preserved, no auto-approve
  - Idempotent on `deviceUuid` (unique constraint)
  - Returns: `deviceId`, `status`
- `POST /control/v1/devices/{deviceId}/approve` — approve a pending device (admin only)
  - Transitions device to `approved`, sets `approved_at`
  - Generates secure random token, stores SHA-256 hash
  - Creates `device_config` with defaults
  - Returns plaintext token **once** — never retrievable again
  - Rejects if device already approved, revoked, or disabled (409)
- `POST /control/v1/devices/{deviceId}/revoke` — revoke a device (admin only)
  - Sets `device.status = revoked`
  - Sets `revoked_at` on all active tokens for the device
  - Device immediately loses ingestion access
  - Rejects if already revoked (409)
- `GET /control/v1/devices/{deviceUuid}/config` — fetch device config (Bearer auth)
  - Validates token ownership matches requested `deviceUuid` (403 if mismatch)
  - Updates `last_seen_at` (heartbeat)
  - Returns: `status`, `apiBaseUrl`, `captureMode`, `pollIntervalSeconds`, `parserEnabled`
  - If device is revoked/disabled, returns status only

### Default Configuration on Approval

| Field | Default |
|-------|---------|
| `apiBaseUrl` | From `INGESTION_PUBLIC_BASE_URL` env var |
| `captureMode` | `WHATSAPP_ONLY` |
| `pollIntervalSeconds` | `300` |
| `parserEnabled` | `true` |

- Admin can modify config via DB directly in v1 (no admin config endpoint yet)

### Security

- Plaintext tokens returned only during approval — never stored, never logged
- All token storage uses SHA-256 hashing
- Constant-time comparison for admin token
- All timestamps stored in UTC
- Revoked tokens immediately rejected on next request

### Control Plane Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ADMIN_TOKEN` | `changeme` | Admin authentication token |
| `INGESTION_PUBLIC_BASE_URL` | `https://envy.buffalo-cliff.ts.net` | Base URL written into device config |

## API Documentation

- Swagger UI at `/docs`
- ReDoc at `/redoc`
- OpenAPI JSON at `/openapi.json`
- Auto-generated from Pydantic models and route definitions

## Infrastructure

- Runs via `docker compose up -d --pull always`
- Three containers: PostgreSQL 15 + FastAPI API + Parser service
- Single Docker image (`anla-api`) with two entrypoints
- Image hosted on private registry (`registry.buffalo-cliff.ts.net/anla-api:latest`)
- Automatic database migrations on startup (Alembic, run by both API and parser entrypoints)
- Automatic DB readiness wait with retry loop
- PostgreSQL healthcheck in compose (`pg_isready`)
- All env vars inlined in `docker-compose.yml` — no `.env` file required
- PostgreSQL data bind-mounted to `./pgdata` (with SELinux `:Z` label for Fedora)
- 4 Alembic migrations: raw_events → seq column → parser tables → control plane tables

## Database Tables

| Table | Purpose |
|-------|---------|
| `raw_events` | Immutable notification store |
| `structured_prices` | Parsed pricing line items |
| `pricing_dead_letter` | Failed parse attempts with error context |
| `parser_offsets` | Cursor position per parser name |
| `devices` | Registered device metadata and status |
| `device_tokens` | Hashed bearer tokens per device |
| `device_config` | Per-device capture and polling config |

---

## Not Yet Implemented

- Batch ingestion (multiple events per request)
- Admin UI / dashboard
- Structured pricing query endpoints
- Parser prompt tuning (deferred until 20–50 real pricing messages collected)
- Media / attachment handling
- Token rotation / re-issuance
- Admin config update endpoint (config editable via DB only)
- Device listing / search endpoint for admin
- mTLS / device certificates
- Multi-tenant control
- Automatic device approval
- Config versioning
- RBAC (production-grade role-based access control)
