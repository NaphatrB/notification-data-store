# ANLA Notification Data Store

Ingestion-only backend for ANLA (Android Notification Listener App) notification events.

Accepts raw notification events via HTTP POST, validates against the ANLA JSON contract, enforces idempotency using `messageHash`, and stores events immutably in PostgreSQL.

No parsing. No business logic. No delivery queue. No auth (dev-only, Tailscale network).

---

## Tech Stack

- **Python 3.11+** / **FastAPI** / **Pydantic v2**
- **SQLAlchemy** (async) + **asyncpg**
- **PostgreSQL 15+**
- **Alembic** (auto-run migrations)
- **Docker + Docker Compose**

---

## Quickstart

```bash
cd backend

# Create .env from template
cp .env.example .env

# Build and start (DB + API)
docker compose up --build
```

The API is available at `http://localhost:8000`.

Migrations run automatically on startup — no manual steps required.

---

## API

### POST `/api/v1/events`

Submit a single ANLA notification event.

**Request body** (must match ANLA JSON schema, no extra fields allowed):

```json
{
  "packageName": "com.whatsapp",
  "timestamp": 1708300800000,
  "notificationId": 42,
  "sourceType": "whatsapp",
  "deliveryStatus": "PENDING",
  "messageHash": "abc123def456...",
  "appName": "WhatsApp",
  "title": "John",
  "text": "Hello!",
  "bigText": "John: Hello!\nJohn: How are you?"
}
```

**Responses:**

| Status | Body | Meaning |
|--------|------|---------|
| 201 | `{"status": "accepted", "duplicate": false}` | New event inserted |
| 200 | `{"status": "accepted", "duplicate": true}` | Duplicate `messageHash`, no insert |
| 422 | Validation error detail | Invalid payload |

**Idempotency rules:**

- `messageHash` (string) → deduplicate on UNIQUE constraint
- `messageHash` (null) → always insert (no dedup)
- Duplicates never return 409

### GET `/health`

Returns `{"status": "ok"}` with DB connectivity check.

---

## Project Structure

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py            # FastAPI app + health endpoint
│   ├── database.py         # Async engine, session, wait_for_db
│   ├── models.py           # SQLAlchemy RawEvent model
│   ├── schemas.py          # Pydantic request/response schemas
│   └── routes/
│       ├── __init__.py
│       └── events.py       # POST /api/v1/events
├── alembic/
│   ├── env.py
│   └── versions/
├── alembic.ini
├── requirements.txt
├── Dockerfile
├── entrypoint.sh
├── docker-compose.yml
├── .env                    # Local config (not committed)
├── .env.example            # Template (committed)
└── .gitignore
```

---

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | Async PostgreSQL connection string | `postgresql+asyncpg://anla:anla@db:5432/anla_db` |
| `POSTGRES_USER` | PostgreSQL user (used by postgres container) | `anla` |
| `POSTGRES_PASSWORD` | PostgreSQL password | `anla` |
| `POSTGRES_DB` | PostgreSQL database name | `anla_db` |

---

## Database

Table: `raw_events`

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | UUID | PK, server-generated |
| `message_hash` | TEXT | UNIQUE, nullable |
| `package_name` | TEXT | NOT NULL |
| `app_name` | TEXT | nullable |
| `title` | TEXT | nullable |
| `text` | TEXT | nullable |
| `big_text` | TEXT | nullable |
| `event_timestamp` | TIMESTAMPTZ | NOT NULL |
| `notification_id` | INTEGER | NOT NULL |
| `source_type` | TEXT | NOT NULL |
| `received_at` | TIMESTAMPTZ | DEFAULT NOW() |

Indexes: `UNIQUE(message_hash)`, `INDEX(event_timestamp)`, `INDEX(source_type)`

---

## Phase 1 Scope

See [PHASE1.md](../PHASE1.md) for the full specification and architectural decisions.

**Explicitly out of scope:** Authentication, parsing, delivery queue, media handling, admin UI, batch ingestion.
# notification-data-store
