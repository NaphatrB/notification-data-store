Below is a **clean Copilot instruction document** you can drop into your `anla-api` repo for implementing the **Pricing Query API**.

It assumes Copilot already has full project context (models, DB, control plane, auth, etc.) and focuses only on *what to build*, not how.

---

# 📄 COPILOT_SPEC — Pricing Query API (Read-Only Analytics Layer)

---

## 🎯 Objective

Implement a read-only Pricing Query API on top of the existing `structured_prices` table.

This layer:

* Exposes structured pricing data for analytics and export
* Supports filtering, pagination, sorting
* Supports aggregation (summary statistics)
* Is admin-authenticated
* Does not mutate any data
* Does not expose internal fields (e.g., `llm_raw_response`)

This is Phase 2.5 — analytics surface only.

---

# 1️⃣ Route Structure

Create new router:

```python
/api/v1/pricing
```

Place routes in:

```
app/api/routes/pricing.py
```

Register router in main app.

All endpoints in this file must require **admin authentication**.

Do NOT allow device tokens to access pricing endpoints.

---

# 2️⃣ Endpoint: List Pricing Records

### Route

```
GET /api/v1/pricing
```

---

## Supported Query Parameters

All optional. All combinable.

* `supplier` (exact match)
* `currency` (exact match)
* `productGrade` (exact match)
* `parserVersion` (exact match)
* `minPrice`
* `maxPrice`
* `minQuantity`
* `maxQuantity`
* `from` (ISO datetime inclusive)
* `to` (ISO datetime inclusive)
* `limit` (default 50, max 500)
* `offset` (default 0)
* `sort` (allowed values: `eventTimestamp`, `pricePerKg`, `quantityKg`)
* `order` (`asc` or `desc`, default desc)

Validate:

* limit ≤ 500
* sort field strictly validated (no dynamic SQL injection)

---

## Filtering Behavior

* Exact matches for strings
* Numeric comparisons for price and quantity
* Date range applies to original event timestamp (join to `raw_events` if needed)
* If no filters → return latest records ordered by seq desc

All filters must be applied at SQL level.

---

## Response Shape

```json
{
  "items": [
    {
      "rawEventId": "uuid",
      "seq": 123,
      "supplier": "...",
      "productGrade": "...",
      "size": "...",
      "quantityKg": 14000,
      "pricePerKg": 1.8,
      "currency": "USD",
      "totalKg": 52000,
      "confidence": 0.92,
      "parserVersion": "pricing_v1",
      "eventTimestamp": "2026-02-20T21:14:00Z"
    }
  ],
  "total": 120,
  "limit": 50,
  "offset": 0
}
```

Use camelCase in response.

Map snake_case DB fields to camelCase via Pydantic aliases.

Never include:

* llm_raw_response
* internal DB metadata

---

# 3️⃣ Endpoint: Single Raw Event Pricing

### Route

```
GET /api/v1/pricing/raw/{rawEventId}
```

---

## Behavior

* Return all structured line items for given raw_event_id
* Grouped under single response object

Response:

```json
{
  "rawEventId": "...",
  "eventTimestamp": "...",
  "supplier": "...",
  "totalKg": 52000,
  "items": [
    {
      "productGrade": "...",
      "size": "...",
      "quantityKg": 14000,
      "pricePerKg": 1.8,
      "currency": "USD",
      "confidence": 0.92,
      "parserVersion": "pricing_v1"
    }
  ]
}
```

Return 404 if none found.

---

# 4️⃣ Endpoint: Summary / Aggregation

### Route

```
GET /api/v1/pricing/summary
```

---

## Optional Filters

* supplier
* currency
* from
* to

---

## Response

```json
{
  "averagePricePerKg": 1.72,
  "totalVolumeKg": 245000,
  "uniqueSuppliers": 4,
  "uniqueEvents": 18,
  "minPricePerKg": 1.55,
  "maxPricePerKg": 1.92
}
```

Use SQL aggregation functions.

Return zeros/nulls safely if no records.

---

# 5️⃣ Query Implementation Rules

* Build SQLAlchemy query dynamically
* Only apply filters if parameter provided
* Enforce limit cap at 500
* Default ordering by seq desc
* Use separate COUNT query for total
* Avoid loading all rows into memory
* Ensure efficient SQL (no N+1 joins)

---

# 6️⃣ Indexing

If not already present, add indexes:

* supplier
* currency
* price_per_kg
* parser_version
* seq

Add migration if necessary.

---

# 7️⃣ Authentication

All pricing endpoints:

* Require `X-Admin-Token`
* Reuse existing admin auth dependency
* Return 401 if missing/invalid

Do NOT allow device bearer tokens.

---

# 8️⃣ Validation & Error Handling

* Invalid datetime → 422
* Invalid sort field → 422
* limit > 500 → clamp to 500
* rawEventId invalid UUID → 422
* rawEventId not found → 404

---

# 9️⃣ Definition of Done

* [ ] Router created
* [ ] All endpoints implemented
* [ ] Admin-only enforced
* [ ] CamelCase response models created
* [ ] Filtering works combinably
* [ ] Sorting validated
* [ ] Aggregation endpoint implemented
* [ ] No internal fields leaked
* [ ] OpenAPI docs auto-generated correctly
* [ ] Tested with real parsed pricing data

---

