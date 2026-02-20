Excellent — these are exactly the right clarifications before implementation.
Let’s lock clean, decisive answers.

---

# 1️⃣ Admin Auth for v1

> Proposal: `ADMIN_TOKEN` env var checked via `X-Admin-Token` header.

## ✅ Decision: Yes — use `ADMIN_TOKEN` + `X-Admin-Token`.

This is perfect for v1.

Implementation rules:

* Env var: `ADMIN_TOKEN`
* Header: `X-Admin-Token`
* Constant-time comparison
* Return 401 if missing/invalid
* No logging of token value

Why this is correct:

* Fast
* Replaceable later
* No RBAC complexity
* Works behind Tailscale
* No JWT needed yet

Good design choice.

---

# 2️⃣ Should Ingestion Be Authenticated Now?

> Currently `/api/v1/events` is open.

## ✅ Decision: Yes — wire ingestion auth now.

Do NOT leave ingestion open.

Control Plane without ingestion enforcement is meaningless.

Required behavior:

* `POST /api/v1/events` requires Bearer token
* Token validated via `device_tokens`
* Device must be `approved`
* Token must not be revoked
* Token must not be expired

If invalid:
→ 401

This is part of Control Plane v1 completion.

---

# 3️⃣ Token Format

> `secrets.token_urlsafe(32)` — acceptable?

## ✅ Yes — use `secrets.token_urlsafe(32)`.

That gives:

* ~43 characters
* ~256-bit entropy
* URL safe
* Strong enough

Optional improvement:

Prefix token for observability:

```text
anla_live_XXXXXXXX
```

This helps debugging and log inspection.

Recommended:

```python
token = "anla_" + secrets.token_urlsafe(32)
```

Still hash only the full token.

Prefix is not required but useful.

---

# 4️⃣ device_config.api_base_url Default

Never hardcode domain.

## ✅ Decision: Pull from environment variable.

Add:

```env
INGESTION_PUBLIC_BASE_URL
```

On approval:

```python
api_base_url = settings.INGESTION_PUBLIC_BASE_URL
```

This avoids:

* Hardcoded Tailscale domain
* Environment mismatch
* Deployment rigidity

Correct production pattern.

---

# 5️⃣ Port Mapping Clarification

Inside container:

* Uvicorn should run on `8000`.

Docker Compose:

* Expose `8000:8000`.

Tailscale Serve:

* Proxies external 5000 → internal 8000 (if configured)

Control plane endpoints live on same FastAPI app.
So port is same as ingestion.

Answer:
Use internal port 8000 consistently.

---

# 6️⃣ Migration Numbering

Latest migration: `0003`.

## ✅ Yes — create:

```
0004_create_control_plane_tables.py
```

Single migration:

* devices
* device_tokens
* device_config

Clean.

---

# 7️⃣ Route File Organization

> Single file or split?

## ✅ Decision: Single file for v1.

Create:

```
app/api/routes/control.py
```

Include:

* register
* approve
* revoke
* config

Why not split?

* Scope is small
* Reduces fragmentation
* Easier to reason about
* Avoid premature modularization

Split later if it grows.

---

# 🔐 One Important Addition (Not Asked But Critical)

When validating Bearer token for ingestion:

You must:

1. Hash incoming token
2. Lookup `device_tokens.token_hash`
3. Ensure:

   * revoked_at IS NULL
   * device.status = approved

But also:

4. Ensure device.status != disabled

And:

5. Update device.last_seen_at

This ensures heartbeat tracking.

---

# 🧠 Final Locked Decisions Summary

| Question        | Decision                                           |
| --------------- | -------------------------------------------------- |
| Admin auth      | ADMIN_TOKEN + X-Admin-Token                        |
| Ingestion auth  | Enforce Bearer validation now                      |
| Token format    | secrets.token_urlsafe(32), optional `anla_` prefix |
| api_base_url    | From env var                                       |
| Uvicorn port    | 8000                                               |
| Migration       | 0004                                               |
| Route structure | Single control.py                                  |

---

# 🎯 Resulting System Integrity

After this:

* No device can ingest without approval
* Tokens can be revoked instantly
* Devices centrally managed
* Config centrally controlled
* Ingestion secured
* Clean upgrade path to mTLS later
