
# 📄 COPILOT_SPEC — Admin Data Viewer (FastAPI + Jinja2 + HTMX)

---

## 🎯 Objective

Build a lightweight browser UI under `/admin` to:

1. View raw notifications (`raw_events`)
2. View parsed pricing data (`structured_prices`)
3. Filter, paginate, and sort
4. Inspect individual rows
5. Export filtered pricing data to CSV (basic)

No SPA.
No React.
No build pipeline.

Use:

* FastAPI
* Jinja2 templates
* HTMX for dynamic filtering
* Minimal CSS (Tailwind optional)
* Optional Chart.js later (not in this phase)

---

# 🏗 High-Level Structure

Create:

```
app/
  templates/
    admin/
      base.html
      raw_list.html
      raw_table.html
      pricing_list.html
      pricing_table.html
```

Create router:

```
app/api/routes/admin_data.py
```

Register under:

```
/admin/raw
/admin/pricing
```

All admin routes require:

```
Depends(require_admin)
```

---

# 1️⃣ Base Layout

Create:

`templates/admin/base.html`

Must include:

* Top navigation bar:

  * Devices
  * Raw Events
  * Pricing
* HTMX script:

```html
<script src="https://unpkg.com/htmx.org@1.9.10"></script>
```

* Basic responsive layout
* Simple CSS (inline minimal styling OK)

Keep clean and simple.

---

# 2️⃣ Raw Events Page

## Route

```python
GET /admin/raw
```

Returns:

`raw_list.html`

---

## Layout: raw_list.html

Contains:

* Filter form (GET-based)
* Results container:

```html
<div id="raw-table" hx-get="/admin/raw/table" hx-trigger="load"></div>
```

Filters:

* deviceId (dropdown)
* sourceType
* from
* to
* limit (default 50)
* offset (hidden, default 0)

Filters should use:

```html
hx-get="/admin/raw/table"
hx-target="#raw-table"
hx-trigger="change"
```

So table updates dynamically.

---

## Table Endpoint

```python
GET /admin/raw/table
```

Returns:

`raw_table.html`

This template renders:

* Paginated table
* Columns:

  * seq
  * deviceId
  * sourceType
  * appName
  * title
  * eventTimestamp
  * receivedAt
  * parseStatus (computed)
* “View” button per row

---

## Row Expand (Optional Enhancement)

Each row can include:

```html
<tr hx-get="/admin/raw/{id}" hx-target="closest tr" hx-swap="afterend">
```

But minimal version can use separate page:

```python
GET /admin/raw/{id}
```

Displays:

* Full notification content
* bigText
* messageHash
* JSON formatted block

---

# 3️⃣ Pricing Page

## Route

```python
GET /admin/pricing
```

Returns:

`pricing_list.html`

---

## Layout: pricing_list.html

Similar structure to raw page.

Filters:

* supplier
* currency
* minPrice
* maxPrice
* from
* to
* parserVersion
* limit
* offset

HTMX target:

```html
<div id="pricing-table" hx-get="/admin/pricing/table" hx-trigger="load"></div>
```

---

## Table Endpoint

```python
GET /admin/pricing/table
```

Returns:

`pricing_table.html`

Columns:

* seq
* supplier
* productGrade
* size
* quantityKg
* pricePerKg
* currency
* totalKg
* confidence
* parserVersion
* eventTimestamp

Add pagination controls:

* Previous / Next
* Maintain filters in query params

---

# 4️⃣ CSV Export (Basic)

Add:

```python
GET /admin/pricing/export
```

Uses same filters as pricing/table.

Returns:

* text/csv
* Filename:

  ```
  pricing_export_YYYYMMDD.csv
  ```

Include headers:

* supplier
* size
* grade
* quantityKg
* pricePerKg
* currency
* eventTimestamp

No need for streaming; small scale OK.

---

# 5️⃣ Query Rules

Reuse existing pricing query logic where possible.

Apply:

* Filters only if provided
* Limit cap at 500
* Default ordering:

  * raw: seq desc
  * pricing: seq desc

No joins unless necessary.

Use SQLAlchemy only.

---

# 6️⃣ Parse Status Column (Raw Page)

Add computed column:

* "parsed"
* "dead_letter"
* "unparsed"

Logic:

* If exists in structured_prices → parsed
* If exists in pricing_dead_letter → dead_letter
* Else → unparsed

Implement via EXISTS subqueries, not N+1 queries.

---

# 7️⃣ Security

All routes:

```python
APIRouter(
    prefix="/admin",
    dependencies=[Depends(require_admin)]
)
```

Do not allow device bearer tokens.

---

# 8️⃣ UX Simplicity Rules

* No JavaScript except HTMX
* No frontend framework
* No dynamic state in JS
* All filtering server-side
* All pagination server-side
* Simple HTML tables
* Keep CSS minimal

This is internal admin tool.

---

# 9️⃣ Performance Guardrails

* Max limit 500
* Default 50
* Offset-based pagination only
* No full-table scans without limit
* Index-backed filtering

---

# 🔟 Definition of Done

* [ ] /admin/raw renders
* [ ] Filtering works
* [ ] Pagination works
* [ ] Row detail view works
* [ ] Parse status visible
* [ ] /admin/pricing renders
* [ ] Filtering works
* [ ] Summary available (optional later)
* [ ] CSV export works
* [ ] All admin auth enforced
* [ ] No SPA / build tools introduced

---
