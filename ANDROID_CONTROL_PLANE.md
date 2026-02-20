# ANDROID_CONTROL_PLANE.md — Client Integration Spec

Instruction document for implementing Control Plane client-side in the ANLA Android app.

---

## Objective

Integrate the Android app with the server's Control Plane v1. After this:

- App registers itself on first launch
- App cannot send events until approved by admin
- App stores its Bearer token securely
- App fetches remote config and respects it
- App sends Bearer token on every ingestion request
- App handles revocation gracefully

---

## Server Base URL

```
https://envy.buffalo-cliff.ts.net
```

All endpoints below are relative to this base.

---

# 1️⃣ Device Registration

## When

- On first app launch (no `deviceId` in local storage)
- On every app launch (re-registration updates metadata, is idempotent)

## Endpoint

```
POST /control/v1/devices/register
Content-Type: application/json
```

No auth required.

## Request Body

```json
{
  "deviceUuid": "a3f1c2d4-...",
  "deviceName": "Ali's Phone",
  "deviceModel": "Pixel 7",
  "androidVersion": "14",
  "appVersion": "1.2.0"
}
```

| Field | Type | Required | Source |
|-------|------|----------|--------|
| `deviceUuid` | String | Yes | `UUID.randomUUID().toString()` — generate once, persist in SharedPreferences/DataStore |
| `deviceName` | String | No | User-chosen or `Build.MODEL` |
| `deviceModel` | String | No | `Build.MODEL` |
| `androidVersion` | String | No | `Build.VERSION.RELEASE` |
| `appVersion` | String | No | `BuildConfig.VERSION_NAME` |

## Response (200)

```json
{
  "deviceId": "server-uuid-here",
  "status": "pending"
}
```

## Client Behavior

1. Generate `deviceUuid` once (first launch). Store permanently in encrypted SharedPreferences or DataStore.
2. Store returned `deviceId` (server UUID) locally — needed for display/debug.
3. Store returned `status` locally.
4. If `status == "pending"` → do NOT attempt ingestion. Show user "Awaiting approval" state.
5. If `status == "approved"` (re-registration) → proceed normally.
6. If `status == "revoked"` or `"disabled"` → show user "Device revoked" state. Do NOT attempt ingestion.

---

# 2️⃣ Token Storage

After admin approves the device (server-side), the token will be provided to the app **out of band** (e.g. admin copies token and enters it in the app, or a future provisioning flow).

For v1, the simplest approach:

### Option A: Manual Token Entry (Recommended for v1)

- Admin approves device via API (e.g. curl)
- Admin receives plaintext token in response
- Admin enters token into the app via a settings screen
- App stores token in Android EncryptedSharedPreferences

### Option B: Polling for Status (Enhancement)

- App polls `/control/v1/devices/{deviceUuid}/config` periodically
- But this requires a token... which creates a chicken-and-egg problem
- Therefore: v1 uses manual token entry

## Storage Rules

- Store token in `EncryptedSharedPreferences` (AndroidX Security)
- Never log the token
- Never include the token in crash reports
- Never write the token to unencrypted storage
- Clear token on app uninstall (default SharedPreferences behavior)

### Example Storage

```kotlin
// EncryptedSharedPreferences setup
val masterKey = MasterKey.Builder(context)
    .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
    .build()

val securePrefs = EncryptedSharedPreferences.create(
    context,
    "anla_secure_prefs",
    masterKey,
    EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
    EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
)

// Store
securePrefs.edit().putString("bearer_token", token).apply()

// Retrieve
val token = securePrefs.getString("bearer_token", null)
```

---

# 3️⃣ Authenticated Ingestion

## Change from Current Behavior

Currently the app sends events with no auth. After this change:

**Every `POST /api/v1/events` must include the Bearer token.**

## Request

```
POST /api/v1/events
Content-Type: application/json
Authorization: Bearer anla_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
```

Body unchanged — same JSON schema as today.

## Response Codes

| Code | Meaning | Client Action |
|------|---------|---------------|
| 201 | Accepted (new) | Mark event as delivered |
| 200 | Accepted (duplicate) | Mark event as delivered |
| 401 | Unauthorized | Stop sending. Token invalid, revoked, or device not approved. Prompt user to re-enter token or contact admin. |
| 422 | Validation error | Log error, do not retry with same payload |

## Client Behavior on 401

1. Stop the delivery queue immediately
2. Set local device status to `"unauthorized"`
3. Show persistent notification: "ANLA cannot send — device authorization lost"
4. Do NOT delete the token yet (could be a transient issue)
5. On next app launch, re-register (POST `/control/v1/devices/register`) to get current status
6. If status is `"revoked"` → clear token, show revoked state
7. If status is `"approved"` → token may be invalid, prompt re-entry

---

# 4️⃣ Config Fetch

## When

- After token is stored (first time)
- Periodically (every `pollIntervalSeconds` from the config itself, default 300s)
- On app launch

## Endpoint

```
GET /control/v1/devices/{deviceUuid}/config
Authorization: Bearer anla_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
```

Note: path parameter is `deviceUuid` (the client-generated UUID), **not** `deviceId`.

## Response (200)

```json
{
  "status": "approved",
  "apiBaseUrl": "https://envy.buffalo-cliff.ts.net",
  "captureMode": "WHATSAPP_ONLY",
  "pollIntervalSeconds": 300,
  "parserEnabled": true
}
```

## Config Fields

| Field | Type | Usage |
|-------|------|-------|
| `status` | String | Device lifecycle status. If not `"approved"`, stop ingestion. |
| `apiBaseUrl` | String? | Base URL for ingestion endpoint. Use this to construct `POST {apiBaseUrl}/api/v1/events`. |
| `captureMode` | String | Which notifications to capture. Currently `"WHATSAPP_ONLY"`. Respect this filter in the NotificationListenerService. |
| `pollIntervalSeconds` | Int | How often to poll for config changes (seconds). Use for WorkManager periodic interval. |
| `parserEnabled` | Bool | Server-side flag. No client action required — informational only. |

## Client Behavior

1. Store config values locally (regular SharedPreferences is fine, not sensitive).
2. Use `apiBaseUrl` as the base URL for ingestion. If null or empty, fall back to hardcoded default.
3. Respect `captureMode`:
   - `WHATSAPP_ONLY` → only capture `com.whatsapp` / `com.whatsapp.w4b`
   - Future values may include `ALL`, `NONE`, etc.
4. Schedule next config fetch using `pollIntervalSeconds`.
5. If `status != "approved"` in config response → stop ingestion, update local state.
6. If config fetch returns 401 → handle same as ingestion 401 (see above).

---

# 5️⃣ App Startup Flow

```
App Launch
  │
  ├─ Has deviceUuid in storage?
  │   ├─ No  → Generate UUID, store it
  │   └─ Yes → Continue
  │
  ├─ POST /control/v1/devices/register
  │   └─ Store deviceId + status
  │
  ├─ status == "pending"?
  │   └─ Yes → Show "Awaiting approval". Stop. Do not capture or send.
  │
  ├─ Has Bearer token in EncryptedSharedPreferences?
  │   ├─ No  → Show "Enter token" screen. Stop.
  │   └─ Yes → Continue
  │
  ├─ GET /control/v1/devices/{deviceUuid}/config
  │   ├─ 401 → Handle unauthorized (see §3)
  │   └─ 200 → Store config locally
  │
  ├─ config.status == "approved"?
  │   ├─ No  → Show status to user. Stop.
  │   └─ Yes → Continue
  │
  └─ Start NotificationListenerService + delivery queue
      └─ Use config.apiBaseUrl + Bearer token for ingestion
```

---

# 6️⃣ Data Model (Local)

Store in Room or DataStore:

```kotlin
data class DeviceRegistration(
    val deviceUuid: String,      // client-generated, permanent
    val deviceId: String?,       // server-assigned UUID, from register response
    val status: String,          // "pending", "approved", "revoked", "disabled"
)

data class ServerConfig(
    val apiBaseUrl: String?,
    val captureMode: String,
    val pollIntervalSeconds: Int,
    val parserEnabled: Boolean,
    val lastFetchedAt: Long,     // epoch millis
)
```

Bearer token stored separately in `EncryptedSharedPreferences` — never in Room.

---

# 7️⃣ Retrofit Interface

```kotlin
interface AnlaControlApi {

    @POST("control/v1/devices/register")
    suspend fun registerDevice(
        @Body request: DeviceRegisterRequest
    ): DeviceRegisterResponse

    @GET("control/v1/devices/{deviceUuid}/config")
    suspend fun getDeviceConfig(
        @Path("deviceUuid") deviceUuid: String,
        @Header("Authorization") bearerToken: String
    ): DeviceConfigResponse
}

interface AnlaIngestionApi {

    @POST("api/v1/events")
    suspend fun sendEvent(
        @Body event: NotificationEvent,
        @Header("Authorization") bearerToken: String
    ): EventResponse
}
```

Helper to build the auth header:

```kotlin
fun bearerHeader(token: String): String = "Bearer $token"
```

---

# 8️⃣ Error Handling Summary

| Scenario | HTTP | Client Action |
|----------|------|---------------|
| Registration succeeds | 200 | Store deviceId + status |
| Registration — network error | — | Retry with exponential backoff. Queue events locally. |
| Ingestion accepted | 201/200 | Mark event delivered |
| Ingestion — unauthorized | 401 | Stop queue, surface to user |
| Ingestion — validation error | 422 | Drop event, log error |
| Ingestion — network error | — | Keep in queue, retry later |
| Config fetch — success | 200 | Apply config |
| Config fetch — unauthorized | 401 | Same as ingestion 401 |
| Config fetch — network error | — | Use cached config, retry later |

---

# 9️⃣ Migration from Unauthenticated Ingestion

If the app currently sends events without auth:

1. Add token storage + settings screen first
2. Add `Authorization` header to the existing Retrofit ingestion call
3. Guard the delivery queue: if no token → queue locally but do not send
4. Add registration call to app startup
5. Add config fetch after token is available
6. Events queued before approval will be delivered once token is entered

No event format changes required. The JSON body for `POST /api/v1/events` is unchanged.

---

# 🔟 Dependencies

Add to `build.gradle.kts` (app module):

```kotlin
// EncryptedSharedPreferences
implementation("androidx.security:security-crypto:1.1.0-alpha06")
```

Already expected to have: Retrofit, OkHttp, Room/DataStore, WorkManager.

---

# Out of Scope (v1)

- Automatic token provisioning (admin must share token manually)
- Token rotation
- Push-based config updates (polling only)
- Device certificate / mTLS
- Multi-device management UI

---

# Final Implementation Checklist

- [ ] Generate and persist `deviceUuid` on first launch
- [ ] Call `POST /control/v1/devices/register` on every launch
- [ ] Build token entry screen (Settings → Enter API Token)
- [ ] Store token in `EncryptedSharedPreferences`
- [ ] Add `Authorization: Bearer {token}` header to `POST /api/v1/events`
- [ ] Handle 401 on ingestion (stop queue, notify user)
- [ ] Call `GET /control/v1/devices/{deviceUuid}/config` after token available
- [ ] Apply `captureMode` filter in NotificationListenerService
- [ ] Apply `apiBaseUrl` from config (override hardcoded URL)
- [ ] Schedule periodic config refresh via WorkManager
- [ ] Guard delivery queue: no token → queue only, do not send
- [ ] Show UI states: pending, approved, revoked, unauthorized
