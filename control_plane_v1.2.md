
## 🎯 Objective

Implement a safe and auditable way to reinstate a previously revoked device.

Behavioral goals:

* `revoked → approved` transition allowed
* Old tokens remain permanently invalid
* Reinstatement does NOT reuse old tokens
* Admin must issue a new token after reinstatement
* Full audit logging required
* No automatic token provisioning

This preserves strong lifecycle semantics.

---

# 1️⃣ Lifecycle Update

Current state machine:

```
pending → approved
approved → revoked
```

Add:

```
revoked → approved
```

Constraints:

* Cannot reinstate if device is `pending`
* Cannot reinstate if already `approved`
* Cannot reinstate if `disabled` (if you later add it)

---

# 2️⃣ New Endpoint

Add:

```
POST /control/v1/devices/{deviceId}/reinstate
```

### Auth

* Admin-only
* Requires `X-Admin-Token`
* Constant-time comparison

---

## Expected Behavior

### 1. Fetch device by `deviceId`

* 404 if not found

### 2. Validate current status

* If `status != revoked` → return 409 Conflict

### 3. Update device

```python
device.status = "approved"
device.approved_at = now()
```

Do NOT touch:

* device_uuid
* metadata fields
* last_seen_at

### 4. Do NOT issue token automatically

Device will remain approved but unusable until a new token is issued.

Return:

```json
{
  "deviceId": "...",
  "status": "approved",
  "requiresToken": true
}
```

---

# 3️⃣ Token Behavior Rules

When a device is revoked:

* All active tokens must already have `revoked_at` set
* Those tokens must never be reactivated
* Reinstatement does NOT modify tokens

After reinstatement:

Admin must explicitly call:

```
POST /control/v1/devices/{deviceId}/rotate-token
```

to issue new token.

---

# 4️⃣ Database Safety

Ensure:

* `device_tokens` table never allows un-revoking tokens
* `rotate-token` inserts new token row
* Old rows remain with `revoked_at` populated

Optional (recommended):

Add partial unique index if not already present:

```sql
CREATE UNIQUE INDEX one_active_token_per_device
ON device_tokens (device_id)
WHERE revoked_at IS NULL;
```

Ensures only one active token at a time.

---

# 5️⃣ Audit Logging

Add audit log entry:

| Field       | Value                              |
| ----------- | ---------------------------------- |
| actor       | `"admin"`                          |
| action      | `"device_reinstated"`              |
| target_type | `"device"`                         |
| target_id   | device.id                          |
| metadata    | `{ "previous_status": "revoked" }` |

If audit table already exists, reuse logging helper.

---

# 6️⃣ Admin UI Update

Update device detail page:

If `status == revoked`:

Show:

* "Reinstate Device" button (POST form)
* Confirmation prompt:

  > This will re-enable the device but it will require a new token.

After successful reinstatement:

* Redirect to device detail
* Show banner:

  > Device reinstated. Issue a new token to restore ingestion.

---

# 7️⃣ Android App Behavior (No Code Changes Required)

Current logic already handles this correctly:

When device is revoked:

* Config returns `status = revoked`
* App clears token
* App stops ingestion

After reinstatement:

* Config returns `status = approved`
* No token present
* App shows “Enter token” state

This is correct and requires no modification.

---

# 8️⃣ Error Conditions

| Scenario            | Response |
| ------------------- | -------- |
| Device not found    | 404      |
| Device not revoked  | 409      |
| Admin token invalid | 401      |

---

# 9️⃣ Definition of Done

* [ ] Endpoint implemented
* [ ] Admin auth enforced
* [ ] Status transition enforced (revoked only)
* [ ] No token auto-generated
* [ ] Audit log written
* [ ] Admin UI button added
* [ ] Old tokens remain invalid
* [ ] Unit test: revoke → reinstate → rotate-token → ingestion works

