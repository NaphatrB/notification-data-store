# 1. Objective

Implement a minimal FastAPI backend that:

* Accepts ANLA notification events via HTTP POST
* Validates against the ANLA JSON contract
* Stores events in PostgreSQL
* Enforces idempotency using `messageHash`
* Returns structured responses
* Runs in Docker via docker-compose
* Requires no authentication (dev only, Tailscale network)

No parsing.
No business logic.
No delivery queue.
No media handling.

This service is ingestion-only.

---

# 2. Technology Stack

* Python 3.11+
* FastAPI
* Pydantic (v2)
* SQLAlchemy (async)
* asyncpg
* PostgreSQL 15+
* Alembic (migrations)
* Docker + Docker Compose

---

# 3. API Contract

## Endpoint

```
POST /api/v1/events
```

---

## Request Body

The request must match the ANLA JSON schema exactly.

Required fields:

* packageName
* timestamp (epoch millis)
* notificationId
* sourceType
* deliveryStatus
* messageHash

Optional fields:

* id
* appName
* title
* text
* bigText

`additionalProperties` must be rejected.

---

## Important Rules

* Backend ignores client `id` (accepted, not stored)
* Backend ignores client `deliveryStatus` (validated as enum, not stored)
* Backend uses `messageHash` as idempotency key
* Backend converts `timestamp` (epoch millis) → UTC TIMESTAMPTZ
* Backend sets `received_at = NOW()`

## Field Handling Details

| Field            | Required | Nullable | Stored | Notes                                      |
| ---------------- | -------- | -------- | ------ | ------------------------------------------ |
| `id`             | No       | Yes      | No     | Client-local PK, accepted and discarded    |
| `packageName`    | Yes      | No       | Yes    | Android package name                       |
| `appName`        | No       | Yes      | Yes    | Human-readable app label                   |
| `title`          | No       | Yes      | Yes    | Notification title                         |
| `text`           | No       | Yes      | Yes    | Notification body                          |
| `bigText`        | No       | Yes      | Yes    | Expanded content                           |
| `timestamp`      | Yes      | No       | Yes    | Epoch millis → UTC TIMESTAMPTZ             |
| `notificationId` | Yes      | No       | Yes    | Android notification ID                    |
| `sourceType`     | Yes      | No       | Yes    | Strict enum (5 values)                     |
| `deliveryStatus` | Yes      | No       | No     | Validated as enum, then discarded          |
| `messageHash`    | Yes      | Yes      | Yes    | Idempotency key; null = always insert      |

---

# 4. Database Schema

Create table `raw_events`:

Columns:

* id (UUID primary key, generated server-side)
* message_hash (TEXT, UNIQUE, nullable)
* package_name (TEXT, NOT NULL)
* app_name (TEXT, nullable)
* title (TEXT, nullable)
* text (TEXT, nullable)
* big_text (TEXT, nullable)
* event_timestamp (TIMESTAMPTZ, NOT NULL)
* notification_id (INTEGER, NOT NULL)
* source_type (TEXT, NOT NULL)
* received_at (TIMESTAMPTZ, default NOW())

Indexes:

* UNIQUE(message_hash)
* INDEX(event_timestamp)
* INDEX(source_type)

---

# 5. Insert & Idempotency Logic

When POST is received:

1. Validate JSON strictly.
2. Convert epoch millis → datetime (UTC).
3. Attempt insert.
4. If `message_hash` is NOT NULL and duplicate exists:

   * Do not error.
   * Return `{ duplicate: true }`
5. If insert succeeds:

   * Return `{ duplicate: false }`
6. If `messageHash` is null:

   * Insert without deduplication.

Never return 409 for duplicates.

---

# 6. Response Format

### New Insert (201)

```json
{
  "status": "accepted",
  "duplicate": false
}
```

### Duplicate (200)

```json
{
  "status": "accepted",
  "duplicate": true
}
```

### Validation Error (422)

Default FastAPI validation response is acceptable.

---

# 7. Project Structure

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── database.py
│   ├── models.py
│   ├── schemas.py
│   └── routes/
│       ├── __init__.py
│       └── events.py
├── alembic/
│   ├── env.py
│   └── versions/
├── alembic.ini
├── requirements.txt
├── Dockerfile
├── entrypoint.sh
├── docker-compose.yml
├── .env
├── .env.example
└── .gitignore
```

---

# 8. Dockerfile

* Base image: python:3.11-slim
* Install requirements
* Copy app and entrypoint.sh
* Entrypoint: `entrypoint.sh`

## Entrypoint Script

`entrypoint.sh` performs:

1. Wait for DB readiness (Python retry loop)
2. Run `alembic upgrade head` (auto-migrate)
3. Start `uvicorn app.main:app --host 0.0.0.0 --port 8000`

Migrations run automatically on every container start.

---

# 9. Docker Compose

Two services:

## db

* image: postgres:15
* env_file: .env (POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB)
* persistent volume
* healthcheck: `pg_isready -U anla` (interval 5s, retries 5)

## api

* build from Dockerfile
* env_file: .env (DATABASE_URL)
* depends_on db with `condition: service_healthy`
* expose port 8000

---

# 10. Environment Configuration

All config via `.env` file (not committed to git).

Required variables:

```
DATABASE_URL=postgresql+asyncpg://anla:anla@db:5432/anla_db
POSTGRES_USER=anla
POSTGRES_PASSWORD=anla
POSTGRES_DB=anla_db
```

A `.env.example` is committed as a template.

No auth token required.

---

# 11. Acceptance Criteria

System is complete when:

* `docker compose up --build` starts both services
* POST request inserts new row
* Reposting same payload returns duplicate=true
* Event timestamp stored correctly in UTC
* Data visible via psql
* Service reachable over Tailscale IP

---

# 12. Explicitly Out of Scope

Do NOT implement:

* Authentication
* Parsing
* Delivery queue
* Structured pricing tables
* Media handling
* Admin UI

---

# 13. Definition of Done

Backend reliably:

* Accepts ANLA events
* Enforces idempotency
* Stores raw data immutably
* Runs in Docker
* Is ready for parser service integration

---

# 14. Health Endpoint

```
GET /health
```

Returns:

```json
{ "status": "ok" }
```

Includes DB connectivity check. Used for Docker healthchecks and Tailscale debugging.

---

# 15. Architectural Decisions

| Concern              | Decision                                              |
| -------------------- | ----------------------------------------------------- |
| `messageHash` null   | Required field, nullable; null = always insert         |
| `deliveryStatus`     | Validate as enum, discard (not stored)                 |
| `id`                 | Accept optional, discard (not stored)                  |
| `sourceType`         | Strict enum (5 values)                                 |
| Alembic              | Auto-generate migrations, auto-run on startup          |
| Health endpoint      | `GET /health` with DB ping                             |
| Batch ingestion      | Not supported (single event per request)               |
| Config strategy      | `.env` file, `.env.example` committed                  |
| DB readiness         | Postgres healthcheck + Python retry loop               |
| Alembic async driver | `run_async` pattern with `asyncpg` (single URL)        |
| Startup order        | entrypoint.sh: wait DB → migrate → uvicorn             |

---
