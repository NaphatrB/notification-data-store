# Parser v1 — Pricing Extraction Service

## Objective

Implement the first production-ready pricing parser service.

The parser must:

* Read raw notification events from the existing `raw_events` table
* Extract structured pricing data using a local LLM
* Validate the extracted data
* Store structured results in a new `structured_prices` table
* Track its own processing offset independently
* Be replayable and idempotent

This is a standalone service (separate container), inside the same repository and Docker image.

---

# 1️⃣ Architectural Principles

* The raw ingestion database is immutable and must not be modified (structure-only addition of `seq` column permitted).
* The parser owns its own state and schema.
* The parser must not introduce coupling into the raw layer (no FK constraints).
* The parser must be restart-safe.
* The parser must tolerate malformed messages without blocking the pipeline.
* The parser must be deterministic and validation-driven.
* Synchronous polling loop — no async, no Celery, no worker pool.

---

# 2️⃣ Scope (Parser v1)

This version:

* Handles pricing extraction only
* Uses a single parser name: `pricing_v1`
* Uses polling (pull-based high-water mark strategy via `seq` column)
* Processes events in small batches
* Calls a local LLM (Ollama — Qwen3 8B) for structured extraction
* Validates the output strictly before persistence

Not in scope:

* Multi-parser framework
* Event streaming
* Human review UI
* Control plane integration
* Distributed coordination
* Advanced orchestration

Keep it minimal and correct.

---

# 3️⃣ Database Requirements

## 3.0 Cursor Column

Add `seq BIGSERIAL UNIQUE` column to `raw_events` table (migration 0002).

* Monotonic, auto-incrementing
* Backfill existing rows ordered by `received_at`
* Index: `ix_raw_events_seq`
* This is the parser's high-water mark cursor (not UUID, not timestamp)

## 3.1 Parser Offset Table

Create a `parser_offsets` table (migration 0003).

Columns:

* `id` — serial PK
* `parser_name` — text, unique
* `last_seq` — bigint (references `raw_events.seq` conceptually, no FK)
* `updated_at` — timestamptz

Behavior:

* One row per parser_name.
* Updated only after successful processing of a batch.
* Must support reset.

## 3.2 Structured Prices Table

Create `structured_prices` table (migration 0003).

Each pricing line item becomes one row.

Columns:

* `id` — UUID PK, gen_random_uuid()
* `raw_event_id` — UUID, indexed, **no FK constraint** (soft reference)
* `seq` — bigint
* `parser_version` — text
* `supplier` — text
* `product_grade` — text
* `size` — text
* `quantity_kg` — numeric
* `price_per_kg` — numeric
* `currency` — text
* `total_kg` — numeric
* `event_timestamp` — timestamptz
* `confidence` — float
* `llm_raw_response` — JSONB
* `created_at` — timestamptz, default now()

Design for:

* Debuggability
* Traceability
* Replay support (delete + re-insert on replay)

## 3.3 Dead Letter Table

Create `pricing_dead_letter` table (migration 0003).

Columns:

* `id` — UUID PK, gen_random_uuid()
* `raw_event_id` — UUID
* `seq` — bigint
* `parser_version` — text
* `error_type` — text (validation_error | llm_error | json_error | etc.)
* `error_message` — text
* `llm_raw_response` — JSONB, nullable
* `original_text` — text (snapshot from raw_events for self-contained audit)
* `created_at` — timestamptz, default now()

---

# 4️⃣ Processing Flow

## 4.1 Batch Fetch

* Fetch events ordered by `seq` greater than last offset.
* Limit batch size (configurable, default 10).
* Use small batches.

## 4.2 Candidate Filtering

Before calling the LLM, apply lightweight heuristics:

Only send to LLM if message likely contains pricing:

* Contains "kg"
* Contains "@"
* Contains numeric patterns

Non-candidates should still advance offset without LLM call.

## 4.3 LLM Extraction

Call Ollama at `LLM_ENDPOINT/api/generate` with:

* Model: Qwen3 8B
* Strict JSON-only response requirement
* Low temperature (deterministic)
* Max tokens limited
* Explicit schema instructions
* Input truncated to ~2k tokens (log if truncated)

Expected output structure:

```json
{
  "supplier": "string",
  "currency": "string",
  "total_kg": 0,
  "items": [
    {
      "size": "string",
      "grade": "string",
      "quantity_kg": 0,
      "price_per_kg": 0
    }
  ],
  "confidence": 0.0
}
```

---

# 5️⃣ Validation Layer

After LLM response, validate with Pydantic:

* JSON parses correctly
* Required fields present
* Numeric fields are numeric
* Items array not empty
* Optional: total_kg ≈ sum of item quantities

If validation fails:

* Retry LLM once
* If still invalid, insert event into `pricing_dead_letter` table
* Advance offset regardless

Do not allow a single bad message to block the pipeline.

---

# 6️⃣ Persistence Logic

For each item in validated extraction:

* Insert one row into `structured_prices`
* Store entire LLM JSON response for audit
* Store parser_version (e.g., "pricing_v1_prompt1")
* Store confidence

Use transactions per batch.

Only update offset after successful persistence.

### Replay Idempotency

On replay (offset reset):

* Delete existing `structured_prices` rows for the `raw_event_id`
* Re-run parsing
* Insert fresh rows

Never skip. Never duplicate. Replay reconstructs truth.

---

# 7️⃣ Offset Management

Offset must:

* Persist across restarts
* Update only after batch completion
* Support manual reset

CLI options:

* `--reset-offset` — reset to 0
* `--start-from-beginning` — alias, same behavior

Replay must be possible without modifying raw_events.

---

# 8️⃣ Error Handling

### LLM Failure

* Retry once
* Log structured error
* If persistent, dead-letter

### DB Failure

* Do not update offset
* Let service restart and retry batch

### Partial Batch Failure

* Use transactional integrity
* Do not partially advance offset

---

# 9️⃣ Metrics & Observability

Expose Prometheus metrics on port 9090:

```
GET /metrics
```

Metrics:

* `parser_processed_total` — counter
* `parser_failed_total` — counter
* `parser_dead_letter_total` — counter
* `parser_batch_latency_seconds` — histogram
* `parser_oldest_unprocessed_seconds` — gauge

Uses `prometheus_client` library.

---

# 🔟 Configuration

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `RAW_DATABASE_URL` | required | PostgreSQL connection string |
| `LLM_ENDPOINT` | `https://bigpc.buffalo-cliff.ts.net` | Ollama HTTP endpoint |
| `PARSER_BATCH_SIZE` | `10` | Events per batch |
| `PARSER_NAME` | `pricing_v1` | Parser identifier |
| `POLL_INTERVAL_SECONDS` | `30` | Sleep between poll cycles |

No hardcoded values.

---

# 1️⃣1️⃣ Determinism Requirements

LLM configuration must:

* Use low temperature
* Limit max tokens
* Enforce strict JSON-only output
* Avoid conversational verbosity

Parser must behave predictably across runs.

Prompt is business logic — it must be versioned:

```python
PARSER_VERSION = "pricing_v1_prompt1"
```

If prompt changes, bump version.

---

# 1️⃣2️⃣ Project Structure

Parser lives inside the backend as a separate entrypoint:

```
app/
  api/              ← FastAPI (existing, restructured)
    main.py
    schemas.py
    routes/
      events.py
  db/               ← Database connection
    database.py
  models/           ← Shared SQLAlchemy models
    models.py
  parser/           ← Parser service (new)
    __init__.py
    __main__.py     ← CLI entry: python -m app.parser
    config.py
    service.py      ← Main polling loop
    candidate_filter.py
    llm_client.py
    schemas.py      ← Pydantic validation for LLM output
    persistence.py
    offset.py
    dead_letter.py
    metrics.py
```

Single Dockerfile. Single Alembic chain. Two entrypoints:

* API: `uvicorn app.api.main:app`
* Parser: `python -m app.parser`

Docker Compose: three services (db, api, parser) — same image, different CMD.

---

# 1️⃣3️⃣ Locked Architectural Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Cursor column | `seq BIGSERIAL` on `raw_events` | Monotonic, deterministic replay, common event-store pattern |
| Database | Same Postgres instance | One platform, not microservices |
| Alembic | Extend existing migration chain | Single source of truth |
| FK constraint | Soft reference only (no FK) | Loose coupling, no cross-schema locking |
| LLM | Ollama `/api/generate`, Qwen3 8B | Local, deterministic, hosted at `https://bigpc.buffalo-cliff.ts.net` |
| Context window | ~2k tokens sufficient | WhatsApp pricing messages are short |
| Deployment | Same docker-compose, separate container | Orchestration simplicity |
| Replay strategy | Delete + re-insert | Parser logic may improve, deterministic rebuild |
| Dead-letter | Full audit (including original_text snapshot) | Self-contained debugging |
| Metrics | Prometheus `/metrics` on port 9090 | Standard, professional |
| Code structure | `app/parser/` inside backend, shared models | Single repo, runtime separation |
| Loop style | Synchronous `while True` | Complexity is enemy at v1 |
| Prompt tuning | Deferred until real pricing data collected | No premature abstraction |

---

# 1️⃣4️⃣ Definition of Done

Parser v1 is complete when:

* It processes real raw_events end-to-end
* structured_prices contains correct rows
* Offset advances safely
* Dead-letter table captures malformed events
* Restarting service does not duplicate inserts
* Replay works (reset offset → delete + rebuild)
* Prometheus metrics exposed
* Non-pricing events skipped without LLM call

Performance does not need to be optimized yet.

Correctness > speed.

