
# 📄 COPILOT_SPEC — Minimal Admin Web UI (ANLA)

---

## 🎯 Objective

Add a minimal Admin Web UI to `anla-api`, served under `/admin`, that allows:

* Viewing all devices
* Viewing device details
* Approving devices
* Revoking devices
* Rotating tokens
* Seeing ingestion stats per device

This UI is for personal fleet management (handful of phones).
Keep it simple, server-rendered, no JS frameworks.

---

# 1️⃣ High-Level Design

## Tech

* FastAPI
* Jinja2Templates
* Existing SQLAlchemy models
* Existing control plane logic
* ADMIN_TOKEN for authentication

## URL Structure

```text
/admin/login
/admin/devices
/admin/devices/{deviceId}
/admin/devices/{deviceId}/approve
/admin/devices/{deviceId}/revoke
/admin/devices/{deviceId}/rotate-token
```

---

# 2️⃣ Templates Structure

Create:

```text
app/templates/
  base.html
  login.html
  devices.html
  device_detail.html
  token_modal.html (optional)
```

Use:

```python
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="app/templates")
```

---

# 3️⃣ Authentication Model (Simple Session Cookie)

## Behavior

* `/admin/login` shows login form
* User enters admin token
* If token matches `ADMIN_TOKEN`, set signed session cookie
* All `/admin/*` routes require session

## Implementation

* Use FastAPI `Request` + `Response`
* Store session token in signed cookie
* Compare using constant-time comparison
* If not authenticated → redirect to `/admin/login`

Do NOT reuse `X-Admin-Token` header for browser UI.

---

# 4️⃣ Device List Page

## Route

```python
GET /admin/devices
```

## Behavior

* Require authenticated session
* Query all devices
* LEFT JOIN raw_events
* Compute:

  * totalEventsIngested
  * lastEventAt

## Template Data

Pass:

```python
{
  "devices": [
    {
      "deviceId": ...,
      "deviceUuid": ...,
      "deviceName": ...,
      "status": ...,
      "lastSeenAt": ...,
      "approvedAt": ...,
      "appVersion": ...,
      "androidVersion": ...,
      "totalEventsIngested": ...,
      "lastEventAt": ...
    }
  ]
}
```

## UI Table Columns

| Device Name | Status | Last Seen | App Version | Total Events | Actions |

Actions:

* View
* Approve (if pending)
* Revoke
* Rotate Token

---

# 5️⃣ Device Detail Page

## Route

```python
GET /admin/devices/{deviceId}
```

## Show:

* Device UUID
* Server ID
* Status
* Approved at
* Last seen
* App version
* Android version
* Total events
* Last event timestamp
* Active token count

Buttons:

* Approve (if pending)
* Revoke
* Rotate Token

---

# 6️⃣ Approve Action

## Route

```python
POST /admin/devices/{deviceId}/approve
```

Behavior:

* Call existing approval logic
* Capture returned plaintext token
* Render page showing:

```text
⚠️ Copy this token now. It will not be shown again.
anla_xxxxxxxxxxxxxxxxx
```

* Log audit event
* Redirect to detail page after acknowledgement

---

# 7️⃣ Revoke Action

```python
POST /admin/devices/{deviceId}/revoke
```

* Call existing revoke logic
* Log audit
* Redirect back to device detail

---

# 8️⃣ Rotate Token Action

```python
POST /admin/devices/{deviceId}/rotate-token
```

* Call rotate logic
* Revoke old tokens
* Generate new token
* Show plaintext once
* Log audit
* Redirect to device detail

---

# 9️⃣ UI Design Constraints

* Clean table
* Minimal CSS (in base.html)
* No external CSS frameworks required
* No JavaScript required (optional for token modal)
* Use simple POST forms for actions

---

# 🔟 Base Template Requirements

base.html should include:

* Page title
* Simple nav bar:

  * Devices
  * Logout
* Flash message area (optional)
* Minimal CSS for table styling

---

# 1️⃣1️⃣ Logout

Add:

```python
GET /admin/logout
```

* Clear session cookie
* Redirect to login

---

# 1️⃣2️⃣ Security Requirements

* All `/admin/*` routes require session auth
* No admin API token exposed in HTML
* No plaintext token stored
* Token only shown once after approval/rotation
* Use POST for all state-changing actions

---

# 1️⃣3️⃣ Non-Goals

Do NOT build:

* Pagination UI (unless devices > 50)
* Search UI
* Role-based access
* CSRF tokens (optional for now)
* Separate frontend project
* Device grouping

Keep it minimal.

---

# 1️⃣4️⃣ Definition of Done

* [ ] Can log into `/admin`
* [ ] Can view device list
* [ ] Can view device detail
* [ ] Can approve pending device
* [ ] Can revoke device
* [ ] Can rotate token
* [ ] Plaintext token only shown once
* [ ] Audit log entries created
* [ ] No breaking changes to existing API

---

