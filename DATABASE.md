# Receipt Scanner — Database Schema & Operations

## Overview

All persistent data lives in a single SQLite file (`backend/receipts.db`), created automatically on first server startup. The database uses two normalized tables with a one-to-many relationship.

**PRAGMAs enabled on every connection:**
- `journal_mode=WAL` — Write-Ahead Logging for better concurrent read performance
- `foreign_keys=ON` — Required for SQLite to enforce `ON DELETE CASCADE`

---

## Tables

### `receipts`

Stores one row per scanned/saved receipt.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT | Unique receipt identifier |
| `store_name` | TEXT | nullable | Name of the store (user-editable) |
| `date` | TEXT | nullable | Receipt date as string (e.g., `"04/16/2026"`) |
| `subtotal_cents` | INTEGER | nullable | Pre-tax subtotal in cents (e.g., `1099` = $10.99) |
| `tax_cents` | INTEGER | nullable | Tax amount in cents |
| `tip_cents` | INTEGER | nullable | Tip/gratuity amount in cents |
| `total_cents` | INTEGER | nullable | Final total in cents |
| `raw_text` | TEXT | nullable | Raw GPT-4o response JSON for debugging |
| `scanned_at` | TEXT | nullable | ISO 8601 timestamp of when the receipt was scanned |

### `items`

Stores individual line items belonging to a receipt.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT | Unique item identifier |
| `receipt_id` | INTEGER | NOT NULL, FK → `receipts(id)` ON DELETE CASCADE | Parent receipt |
| `name` | TEXT | nullable | Item name (user-editable) |
| `price_cents` | INTEGER | nullable | Item price in cents (e.g., `349` = $3.49) |
| `product_id` | TEXT | nullable | Product/SKU code if detected |
| `category` | TEXT | nullable | Spending category (e.g., "Groceries", "Beverages") |

### Relationship

```
receipts (1) ──── (many) items
```

Deleting a receipt automatically deletes all its items via `ON DELETE CASCADE`.

---

## Dollar ↔ Cents Conversion

All monetary values are stored as **integer cents** to avoid floating-point precision issues. Two helper functions handle conversion at the database boundary:

| Function | Direction | Example |
|----------|-----------|---------|
| `_dollars_to_cents(val)` | API → DB | `3.49` → `349` (uses `round(float(val) * 100)`) |
| `_cents_to_dollars(val)` | DB → API | `349` → `3.49` (uses `val / 100`) |

The REST API always sends and receives **dollar floats** (e.g., `3.49`). The frontend never sees cents.

---

## Operations

### 1. `init_db()`

**Purpose:** Create both tables if they don't already exist.

**When called:** Automatically on server startup via FastAPI's `@app.on_event("startup")`.

**SQL:**
```sql
CREATE TABLE IF NOT EXISTS receipts (...);
CREATE TABLE IF NOT EXISTS items (...);
```

**Note:** There is no migration system. If the schema changes, you must delete `receipts.db` and restart the server.

---

### 2. `save_receipt(receipt: dict) → dict`

**Purpose:** Insert a new receipt and all its items.

**API route:** `POST /api/receipts`

**Steps:**
1. INSERT one row into `receipts` with all fields converted from dollars to cents
2. For each item in `receipt["items"]`:
   - INSERT into `items` with `receipt_id` set to the new receipt's ID
   - Price converted from dollars to cents
3. Return the fully hydrated receipt (via `get_receipt()`)

**SQL:**
```sql
INSERT INTO receipts (store_name, date, subtotal_cents, tax_cents, tip_cents, total_cents, raw_text, scanned_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?);

-- For each item:
INSERT INTO items (receipt_id, name, price_cents, product_id, category)
VALUES (?, ?, ?, ?, ?);
```

---

### 3. `get_receipt(receipt_id: int) → dict | None`

**Purpose:** Fetch a single receipt with all its items.

**API route:** `GET /api/receipts/:id`

**Steps:**
1. SELECT the receipt row by ID
2. SELECT all items for that receipt, ordered by `id`
3. Convert to API format via `_row_to_receipt()` (cents → dollars)
4. Return `None` if receipt not found

**SQL:**
```sql
SELECT * FROM receipts WHERE id = ?;
SELECT * FROM items WHERE receipt_id = ? ORDER BY id;
```

---

### 4. `list_receipts() → list[dict]`

**Purpose:** Fetch all receipts with their items, newest first.

**API route:** `GET /api/receipts`

**Steps:**
1. SELECT all receipts ordered by `id DESC`
2. For each receipt, SELECT its items ordered by `id`
3. Convert each to API format via `_row_to_receipt()`

**SQL:**
```sql
SELECT * FROM receipts ORDER BY id DESC;
-- For each receipt:
SELECT * FROM items WHERE receipt_id = ? ORDER BY id;
```

**Note:** This uses N+1 queries (one for receipts, one per receipt for items). Acceptable for a single-user app but would need optimization (e.g., a JOIN) at scale.

---

### 5. `update_receipt(receipt_id: int, receipt: dict) → dict | None`

**Purpose:** Update an existing receipt's fields and reconcile its items (patch, add, delete — not replace-all).

**API route:** `PUT /api/receipts/:id`

**Steps:**

1. **Verify existence** — SELECT the receipt by ID. Return `None` if not found.

2. **Update receipt fields** — UPDATE the `receipts` row with new values (all converted to cents).

3. **Reconcile items** using a three-way operation:

   | Operation | Condition | SQL |
   |-----------|-----------|-----|
   | **Delete** | DB item ID is NOT in the incoming items list | `DELETE FROM items WHERE id IN (?) AND receipt_id = ?` |
   | **Patch** | Incoming item has an integer `id` that exists in DB | `UPDATE items SET name=?, price_cents=?, product_id=?, category=? WHERE id=? AND receipt_id=?` |
   | **Add** | Incoming item has `id: null` (or no `id`) | `INSERT INTO items (receipt_id, name, price_cents, product_id, category) VALUES (?, ?, ?, ?, ?)` |

4. **Return** the updated receipt (via `get_receipt()`).

**Item identity contract:**
- `id: null` → new item, will be INSERTed (SQLite assigns a new auto-increment ID)
- `id: <integer>` → existing item, will be UPDATEd in place
- Item missing from incoming list → will be DELETEd

**Example:**

```
Before update:  items in DB = [{id:1, name:"Milk"}, {id:2, name:"Bread"}, {id:3, name:"Eggs"}]
Incoming items: [{id:1, name:"Whole Milk"}, {id:3, name:"Eggs"}, {id:null, name:"Butter"}]

Result:
  - id:1 → PATCHED (name changed to "Whole Milk")
  - id:2 → DELETED (not in incoming list)
  - id:3 → PATCHED (unchanged but still updated)
  - id:null → INSERTED as id:4 ("Butter")
```

---

### 6. `delete_receipt(receipt_id: int) → bool`

**Purpose:** Delete a receipt and all its items.

**API route:** `DELETE /api/receipts/:id`

**Steps:**
1. DELETE the receipt row by ID
2. Items are automatically deleted via `ON DELETE CASCADE`
3. Return `True` if a row was deleted, `False` if not found

**SQL:**
```sql
DELETE FROM receipts WHERE id = ?;
-- Items cascade-deleted automatically
```

---

### 7. `_row_to_receipt(row, item_rows) → dict`

**Purpose:** Convert raw SQLite rows into the API response format.

**Conversions performed:**
- `store_name` → `storeName` (camelCase for JS)
- `*_cents` → dollar floats (via `_cents_to_dollars()`)
- `raw_text` → `rawText`
- `scanned_at` → `scannedAt`
- `product_id` → `productId`
- Each item's `price_cents` → `price` as dollar float

**Output shape:**
```json
{
  "id": 1,
  "storeName": "Target",
  "date": "04/24/2026",
  "subtotal": 12.48,
  "tax": 1.03,
  "tip": null,
  "total": 13.51,
  "rawText": "...",
  "scannedAt": "2026-04-24T23:14:00Z",
  "items": [
    {
      "id": 1,
      "name": "Organic Milk",
      "price": 4.99,
      "productId": null,
      "category": "Dairy"
    }
  ]
}
```

---

## API Summary

| Method | Route | DB Operation | Description |
|--------|-------|-------------|-------------|
| `POST` | `/api/scan` | None | OCR only — returns parsed JSON, nothing saved |
| `POST` | `/api/receipts` | `save_receipt()` | Insert new receipt + items |
| `GET` | `/api/receipts` | `list_receipts()` | List all receipts (newest first) |
| `GET` | `/api/receipts/:id` | `get_receipt()` | Fetch one receipt by ID |
| `PUT` | `/api/receipts/:id` | `update_receipt()` | Update receipt + reconcile items |
| `DELETE` | `/api/receipts/:id` | `delete_receipt()` | Delete receipt (items cascade) |
| `GET` | `/api/stats/categories` | `list_receipts()` | Aggregate spending by category (computed in Python, not SQL) |
| `GET` | `/api/health` | None | Health check |
