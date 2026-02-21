Excellent.
Below is a **focused Copilot instruction document** for implementing the next fleet-management phase inside `anla-api`.

This assumes:

* FastAPI
* SQLAlchemy 2.0
* Alembic
* Existing control plane tables (`devices`, `device_tokens`, `raw_events`, etc.)
* Admin auth via `X-Admin-Token`

We are extending — not refactoring.

---

# 📄 COPILOT_SPEC — Fleet Visibility & Token Rotation (Phase 2A)

---

## 🎯 Objective

Extend `anla-api` with:

1. Device Fleet Visibility API
2. Device-Level Ingestion Stats
3. Token Rotation Endpoint
4. Audit Log Table + Logging Hooks

This phase improves operational visibility and prepares system for commercialization.

Do not modify ingestion or parser behavior.

---

# 1️⃣ Device Fleet Visibility API

## Endpoints to Add

```http
GET /control/v1/devices
GET /control/v1/devices/{deviceId}
```

Admin-only endpoints.

Protected by existing `X-Admin-Token` header.

---

## GET /control/v1/devices

### Purpose

Return paginated list of all registered devices including ingestion statistics.

### Query Parameters

* `status` (optional)
* `limit` (default 50, max 200)
* `offset` (default 0)
* `search` (optional, match deviceName ILIKE)

---

### Response Shape (camelCase)

```json
{
  "items": [
    {
      "deviceId": "uuid",
      "deviceUuid": "uuid",
      "deviceName": "Ali's Phone",
      "status": "approved",
      "lastSeenAt": "2026-02-20T21:11:00Z",
      "approvedAt": "2026-02-19T10:00:00Z",
      "appVersion": "1.2.0",
      "androidVersion": "14",
      "totalEventsIngested": 1523,
      "lastEventAt": "2026-02-20T21:10:58Z"
    }
  ],
  "total": 3,
  "limit": 50,
  "offset": 0
}
```

---

### Implementation Notes

* Join `devices` with `raw_events`
* Compute:

  * `COUNT(raw_events.id)`
  * `MAX(raw_events.event_timestamp)`
* Use GROUP BY devices.id
* Use LEFT JOIN (devices with zero events must still appear)
* Sort default by `created_at DESC`

No materialized views required.

---

## GET /control/v1/devices/{deviceId}

Return single device with stats.

If not found → 404.

Same fields as above.

---

# 2️⃣ Device-Level Ingestion Stats

Extend device listing to include:

| Field                | Source                          |
| -------------------- | ------------------------------- |
| totalEventsIngested  | COUNT(raw_events.id)            |
| lastEventAt          | MAX(raw_events.event_timestamp) |
| last401At (optional) | future field — placeholder only |

Do NOT add new columns yet.

Use computed query only.

---

# 3️⃣ Token Rotation Endpoint

Add:

```http
POST /control/v1/devices/{deviceId}/rotate-token
```

Admin-only.

---

## Behavior

1. Validate device exists
2. Device must be status = approved
3. Generate new token:

   * Prefix: `anla_`
   * 32 random bytes
   * urlsafe base64
4. Hash token with SHA-256
5. Insert new row into `device_tokens`
6. Revoke all previous active tokens:

   * Set `revoked_at = now()`
7. Return plaintext token once

---

## Response

```json
{
  "deviceId": "uuid",
  "token": "anla_xxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
}
```

Do not store plaintext token anywhere.

---

# 4️⃣ Audit Log Table

## New Alembic Migration

Create table:

```sql
audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id UUID,
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
```

Add index on:

* created_at
* target_id

---

# 5️⃣ Audit Logging Hooks

Add helper function:

```python
def log_audit(actor: str, action: str, target_type: str, target_id: UUID, metadata: dict | None = None)
```

Use inside:

* Device approval
* Device revoke
* Token issuance
* Token rotation

Example:

```python
log_audit(
    actor="admin",
    action="device_approved",
    target_type="device",
    target_id=device.id,
    metadata={"deviceName": device.device_name}
)
```

Do not over-engineer.

---

# 6️⃣ Code Organization

Add new router:

```
app/api/routes/devices.py
```

Or extend existing control route file.

Keep routes under:

```
/control/v1/*
```

Do not mix with ingestion endpoints.

---

# 7️⃣ Security Requirements

* All new endpoints require `X-Admin-Token`
* Use constant-time comparison
* Return 401 if invalid
* Do not leak whether device exists if token invalid

---

# 8️⃣ Non-Goals

Do NOT implement:

* Pagination cursors
* Sorting by multiple columns
* Token listing endpoint
* Audit log query endpoint
* Rate limiting
* Device grouping
* RBAC

Keep this minimal and clean.

---

# 9️⃣ Definition of Done

* [ ] GET devices returns list with stats
* [ ] GET device by ID works
* [ ] Token rotation works
* [ ] Old tokens revoked automatically
* [ ] Audit logs written on:

  * device approve
  * device revoke
  * token issued
  * token rotated
* [ ] New migration applied successfully
* [ ] OpenAPI docs updated automatically

---

# 🔟 Design Principles

* Keep schema simple
* Compute stats via query
* Avoid denormalized counters
* Avoid premature optimization
* Keep future multi-tenant possible
* No breaking changes to Android client

---

