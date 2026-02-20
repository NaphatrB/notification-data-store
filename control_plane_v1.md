Here is a clean, implementation-oriented **Copilot spec** for Control Plane v1.

It assumes:

* FastAPI backend already exists
* SQLAlchemy + Alembic already configured
* Token-based auth middleware exists (or will be extended)
* Single Postgres instance

No low-level code instructions — just behavior and structure.

---

# 📄 CONTROL_PLANE_V1.md

# Control Plane v1 — Device Registration & Management

## Objective

Implement Control Plane v1 inside the existing backend service.

The Control Plane manages:

* Device registration
* Device approval
* API token issuance
* Token revocation
* Remote configuration delivery
* Device lifecycle state

This system governs Android clients but does NOT handle raw event ingestion.

---

# 1️⃣ Architectural Principles

* Control Plane is logically separate from ingestion.
* Devices must not send events unless approved.
* Tokens are issued only after approval.
* Tokens are stored hashed.
* Plaintext tokens are returned once only.
* All decisions are server authoritative.
* Device configuration is delivered via pull (not push).
* Keep implementation simple and deterministic.

---

# 2️⃣ Database Schema

Add new tables via Alembic migration (extend existing chain).

---

## 2.1 devices

Fields:

* id (UUID, primary key, server generated)
* device_uuid (TEXT, unique, client generated)
* device_name (TEXT)
* device_model (TEXT)
* android_version (TEXT)
* app_version (TEXT)
* status (TEXT) — enum:

  * pending
  * approved
  * revoked
  * disabled
* created_at (TIMESTAMPTZ)
* approved_at (TIMESTAMPTZ, nullable)
* last_seen_at (TIMESTAMPTZ, nullable)

Rules:

* device_uuid must be unique.
* status defaults to `pending`.

---

## 2.2 device_tokens

Fields:

* id (UUID)
* device_id (UUID)
* token_hash (TEXT)
* token_name (TEXT)
* created_at (TIMESTAMPTZ)
* revoked_at (TIMESTAMPTZ, nullable)
* expires_at (TIMESTAMPTZ, nullable)

Rules:

* Store SHA256(token).
* Never store plaintext.
* Multiple tokens per device allowed.
* Revoked token must not authenticate.

---

## 2.3 device_config

Fields:

* device_id (UUID)
* api_base_url (TEXT)
* capture_mode (TEXT)
* poll_interval_seconds (INTEGER)
* parser_enabled (BOOLEAN)
* updated_at (TIMESTAMPTZ)

Rules:

* One row per device.
* Default values applied on approval.

---

# 3️⃣ Device Lifecycle

State machine:

pending → approved → revoked
approved → disabled
revoked → (no transition back without manual reset)

Devices in:

* pending: cannot ingest
* approved: can ingest
* revoked: token invalid
* disabled: token invalid

---

# 4️⃣ API Endpoints

All control endpoints live under:

```
/control/v1/
```

---

## 4.1 Register Device

POST `/control/v1/devices/register`

Purpose:
Register or re-register a device.

Request body:

* deviceUuid
* deviceName
* deviceModel
* androidVersion
* appVersion

Behavior:

If deviceUuid does not exist:

* Create new device
* status = pending
* Return deviceId + status

If deviceUuid exists:

* Update metadata fields
* Return existing status
* Do NOT auto-approve

Response:

* deviceId
* status

---

## 4.2 Approve Device (Admin Only)

POST `/control/v1/devices/{deviceId}/approve`

Behavior:

* Change status to approved
* Set approved_at
* Generate secure random token
* Store SHA256(token)
* Create device_config with defaults
* Return plaintext token ONCE

Token length:
Minimum 32 random bytes, base64 encoded.

---

## 4.3 Revoke Device

POST `/control/v1/devices/{deviceId}/revoke`

Behavior:

* Set device.status = revoked
* Set revoked_at on all active tokens

Device must no longer authenticate ingestion.

---

## 4.4 Get Device Config (Authenticated)

GET `/control/v1/devices/{deviceUuid}/config`

Auth:
Bearer token required.

Validation:

* Token hash must match active token
* Device status must be approved
* Token must not be revoked
* Token must not be expired

Behavior:

* Update last_seen_at
* Return configuration

Response includes:

* status
* apiBaseUrl
* captureMode
* pollIntervalSeconds
* parserEnabled

If device is revoked or disabled:
Return status accordingly.

---

# 5️⃣ Token Validation Rules

Token validation middleware must:

* Extract Bearer token
* Hash token
* Look up in device_tokens
* Ensure:

  * revoked_at is null
  * device.status == approved

If invalid:
Return 401.

Control plane and ingestion must share token validation logic.

---

# 6️⃣ Security Constraints

* Never return token_hash
* Never log plaintext token
* Plaintext token returned only during approval
* Use constant-time hash comparison
* All timestamps UTC

No encryption at rest required for v1.

---

# 7️⃣ Default Configuration on Approval

When device is approved, auto-create device_config with:

* api_base_url = ingestion base URL
* capture_mode = WHATSAPP_ONLY
* poll_interval_seconds = 300
* parser_enabled = true

Admin can modify config via DB manually in v1.

No UI required yet.

---

# 8️⃣ Admin Access

For v1, admin endpoints may:

* Be protected by environment-based admin token
  OR
* Be temporarily open in dev environment

Production-grade RBAC not required yet.

---

# 9️⃣ Observability

Add structured logs for:

* Device registration
* Approval
* Revocation
* Config fetch
* Token validation failures

No Prometheus metrics required for control plane v1.

---

# 🔟 Definition of Done

Control Plane v1 is complete when:

* Android can register
* Device remains pending until approved
* Admin can approve and receive token
* Device can fetch config after approval
* Ingestion rejects non-approved devices
* Revoked device cannot authenticate
* Token hash stored securely
* Replay of register does not duplicate device
* Alembic migration clean

---

# 1️⃣1️⃣ Out of Scope (For Now)

* mTLS
* Device certificates
* Admin UI
* Device grouping
* Multi-tenant control
* Device push notifications
* Automatic device approval
* Config versioning

Keep minimal.

---

# Final Instruction to Copilot

Implement Control Plane v1 inside existing backend.

Reuse:

* Existing DB session patterns
* Existing Pydantic conventions
* Existing Alembic migration structure
* Existing token validation middleware if present

Do not introduce unnecessary abstraction.

Keep logic explicit and readable.

Focus on correctness, security basics, and deterministic behavior.

---

If you want next, we can:

* Design Android onboarding flow
* Design token rotation strategy
* Add audit logging strategy
* Or define mTLS roadmap for v2
