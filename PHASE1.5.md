# ANLA Backend – Phase 1.5 Raw Query Layer

## Copilot Implementation Instructions

---

# 1. Objective

Extend the existing ANLA raw ingestion backend with **read-only query capabilities**.

This phase must:

* Expose raw stored events via HTTP
* Support filtering and pagination
* Provide basic ingestion statistics
* Remain strictly read-only
* Avoid parsing or business logic
* Preserve immutability of raw data

No schema changes required.

---

# 2. Scope

Add the following endpoints:

* `GET /api/v1/events`
* `GET /api/v1/events/{id}`
* `GET /api/v1/stats`

Do NOT implement:

* Search by keyword (future phase)
* Parsing
* Data mutation
* Delivery state changes
* Admin auth
* Structured pricing endpoints

---

# 3. GET /api/v1/events

## Purpose

Return paginated raw events with optional filters.

---

## Query Parameters

| Parameter  | Type         | Required | Description                                       |
| ---------- | ------------ | -------- | ------------------------------------------------- |
| sourceType | string       | No       | Filter by source type                             |
| from       | ISO datetime | No       | Start of event_timestamp range (inclusive)        |
| to         | ISO datetime | No       | End of event_timestamp range (inclusive)          |
| limit      | int          | No       | Default 50, max 500                               |
| offset     | int          | No       | Default 0                                         |
| sort       | string       | No       | `asc` or `desc` by event_timestamp (default desc) |

---

## Filtering Rules

* `sourceType` must match existing enum values.
* `from` and `to` filter on `event_timestamp`.
* Invalid date formats return 422.
* Limit > 500 should be capped at 500.
* Offset cannot be negative.

---

## Response Format

```json
{
  "items": [
    {
      "id": "uuid",
      "messageHash": "abc123",
      "packageName": "com.whatsapp",
      "appName": "WhatsApp",
      "title": "Fish Group",
      "text": "3/5 Ah - 14000 kg @ 1.80 USD",
      "bigText": null,
      "eventTimestamp": "2026-02-19T21:14:00Z",
      "notificationId": 123,
      "sourceType": "whatsapp",
      "receivedAt": "2026-02-19T21:14:05Z"
    }
  ],
  "total": 1243,
  "limit": 50,
  "offset": 0
}
```

Notes:

* `total` = total rows matching filter (before pagination)
* `items` sorted by `event_timestamp`
* No deliveryStatus returned
* No raw client-only fields returned

---

# 4. GET /api/v1/events/{id}

## Purpose

Retrieve a single raw event by UUID.

---

## Behavior

* If event exists → return full raw record
* If not found → return 404

---

## Response Format

```json
{
  "id": "uuid",
  "messageHash": "abc123",
  "packageName": "com.whatsapp",
  "appName": "WhatsApp",
  "title": "Fish Group",
  "text": "...",
  "bigText": null,
  "eventTimestamp": "2026-02-19T21:14:00Z",
  "notificationId": 123,
  "sourceType": "whatsapp",
  "receivedAt": "2026-02-19T21:14:05Z"
}
```

---

# 5. GET /api/v1/stats

## Purpose

Provide ingestion-level visibility.

---

## Response Format

```json
{
  "totalEvents": 1243,
  "bySource": {
    "whatsapp": 900,
    "telegram": 200,
    "facebook": 100,
    "sms": 30,
    "notification": 13
  },
  "lastEventAt": "2026-02-19T21:14:00Z"
}
```

---

## Rules

* `totalEvents` = total rows in raw_events
* `bySource` = grouped count by source_type
* `lastEventAt` = max(event_timestamp) or null if empty

---

# 6. Database Considerations

Ensure indexes exist on:

* `event_timestamp`
* `source_type`

Queries must:

* Use SQLAlchemy async session
* Avoid loading entire table into memory
* Use COUNT query for total
* Use LIMIT/OFFSET for pagination

---

# 7. Validation

* Invalid UUID → 422
* Invalid date format → 422
* Invalid enum for sourceType → 422
* Offset < 0 → 422
* limit < 1 → 422

---

# 8. Performance Requirements

* Default limit: 50
* Hard cap: 500
* Queries must not scan entire table unnecessarily
* Sorting must use indexed column

---

# 9. Security

No authentication required (dev-only Tailscale environment).

Do not expose:

* Internal DB errors
* Stack traces
* Connection details

Return clean error responses.

---

# 10. Acceptance Criteria

System is complete when:

* `GET /api/v1/events` returns paginated results
* Filtering by sourceType works
* Filtering by date range works
* Sorting asc/desc works
* `GET /api/v1/events/{id}` returns correct record
* `GET /api/v1/stats` returns accurate counts
* Empty DB returns clean empty responses
* Performance acceptable for 100k+ rows

---

# 11. Architectural Constraints

* Do not modify raw_events schema
* Do not introduce parsing logic
* Do not introduce write operations
* Keep layer strictly read-only
* Maintain immutability of raw data

---

# 12. Definition of Done

Backend now supports:

* Deterministic raw ingestion
* Deterministic raw retrieval
* Observability of ingestion volume
* Stable foundation for parser service

---
