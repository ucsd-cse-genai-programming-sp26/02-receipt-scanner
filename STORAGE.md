# Receipt Scanner — Data Storage & Frontend-to-Backend Flow

## Overview

Data lives in two places during the lifecycle of a receipt: **React state** (ephemeral, in-browser) and **SQLite** (persistent, server-side). The frontend never writes to disk directly — all persistence goes through the REST API.

---

## Frontend State (React)

### App.jsx — top-level state

`App.jsx` holds five pieces of state that drive the entire UI:

| State | Type | Purpose |
|---|---|---|
| `receipt` | `object \| null` | The currently active receipt being viewed or edited. `null` when showing the upload screen. |
| `loading` | `boolean` | `true` while waiting for the OCR scan response. |
| `error` | `string \| null` | Error message shown in the red banner. Cleared on next action. |
| `history` | `array` | List of saved receipts fetched from `GET /api/receipts`. Refreshed after every save/delete. |
| `previewUrl` | `string \| null` | Blob URL of the uploaded image for the thumbnail. Only exists for fresh scans, not history items. |

### ReceiptCard — editing state

When `ReceiptCard` mounts, it **copies** the receipt prop into local state so edits don't mutate the original object:

| Local State | Source | Editable? |
|---|---|---|
| `items` | `receipt.items` | ✅ Users can edit name, price; add/remove items |
| `storeName` | `receipt.storeName` | ✅ |
| `date` | `receipt.date` | ✅ |
| `tax` | `receipt.tax` | ✅ |
| `tip` | `receipt.tip` | ✅ |
| `subtotal` | Computed: `sum(items.price)` | ❌ Auto-calculated, read-only display |
| `total` | Computed: `subtotal + tax + tip` | ❌ Auto-calculated, read-only display |

The original `receipt` prop is never modified. On save, `handleSave()` merges the edited fields back with the original receipt object (preserving `id`, `rawText`, `scannedAt`) and passes it up to `App.jsx`.

### Item identity in React state

Each item in the `items` array has this shape:

```json
{
  "id": 3,           // integer from DB, or null for new items
  "name": "Apple",
  "price": 3.50,
  "productId": "SKU001"   // or null
}
```

- Items loaded from the DB have an integer `id` — this is preserved through edits.
- Items added via the "+ Add item" button have `id: null`.
- React uses `item.id ?? "new-${index}"` as the list key for stable rendering.

---

## What gets sent to the backend

### On scan (image upload)

```
Frontend                                        Backend
────────                                        ───────
FormData { file: <image blob> }  ──POST /api/scan──▶  Tesseract OCR
                                                        │
receipt = {                      ◀── JSON response ───  parse_receipt_text()
  storeName: "WALMART",                   (no id — not saved yet)
  date: "04/21/2026",
  items: [
    { id: 1, name: "APPLE", price: 3.50, productId: null },
    { id: 2, name: "BREAD", price: 6.50, productId: null }
  ],
  subtotal: null,
  tax: null,
  tip: null,
  total: 10.00,
  rawText: "WALMART\nAPPLE 3.50\n..."
}
```

Note: The `id` values on items from a scan are **temporary sequence numbers** (1, 2, 3...) assigned by the parser. They are **not** database IDs. Since the receipt itself has no `id`, the frontend knows this is a new receipt.

The frontend then adds `scannedAt: new Date().toISOString()` before displaying the card.

### On save (new receipt)

When the user clicks "Save to History" on a freshly scanned receipt:

```
Frontend                                          Backend
────────                                          ───────
{                                                   
  storeName: "Walmart",       (user-corrected)    POST /api/receipts
  date: "04/21/2026",                               │
  items: [                                           ▼
    { id: null, name: "Apple", price: 3.50, ... }, save_receipt()
    { id: null, name: "Bread", price: 6.50, ... }   │ INSERT INTO receipts
  ],                                                 │ INSERT INTO items (×2)
  subtotal: 10.00,            (computed)             │
  tax: 0.80,                  (user-entered)         ▼
  tip: null,                                       dollars_to_cents()
  total: 10.80,              (computed)              │ subtotal → 1000
  rawText: "...",                                    │ tax      → 80
  scannedAt: "2026-04-21T..."                        │ total    → 1080
}                                                    │ items    → 350, 650
                                                     ▼
Response: { id: 1, ... }     ◀── JSON response ──  get_receipt(1)
                                                     │ cents_to_dollars()
                                                     │ back to 10.00, 0.80, etc.
```

Key points:
- Items have `id: null` because they haven't been saved yet.
- `subtotal` and `total` are computed by the frontend and sent as-is.
- The backend converts all dollar amounts to **integer cents** before storing.
- The response includes the new `receipt.id` and DB-assigned `item.id` values.

### On update (editing a saved receipt)

When the user opens a receipt from history, edits it, and clicks "Update":

```
Frontend                                          Backend
────────                                          ───────
{                                                   
  id: 1,                     (from DB)            PUT /api/receipts/1
  storeName: "Walmart",                              │
  items: [                                           ▼
    { id: 5, name: "Green Apple", price: 4.00 },  update_receipt()
    { id: 6, name: "Bread", price: 6.50 },          │
    { id: null, name: "Milk", price: 3.00 }          │ ┌─ id:5 exists in DB → UPDATE
  ],                                                 │ ├─ id:6 exists in DB → UPDATE
  subtotal: 13.50,                                   │ ├─ id:null           → INSERT
  tax: 1.08,                                         │ └─ (no id:7 sent)   → DELETE id:7
  tip: 2.00,                                         │
  total: 16.58,                                      ▼
  ...                                              Response with updated data
}
```

The backend reconciles items by comparing incoming IDs against existing DB IDs:
- **Integer `id` present in DB** → `UPDATE` that row (patch)
- **`id` is `null`** → `INSERT` new row (add)
- **DB row `id` not in incoming list** → `DELETE` that row (remove)

### On delete

```
Frontend                       Backend
────────                       ───────
DELETE /api/receipts/3  ──────▶  DELETE FROM receipts WHERE id = 3
                                   (CASCADE deletes items too)
{ ok: true }            ◀──────  
```

After every save, update, or delete, the frontend calls `GET /api/receipts` to refresh the history list.

---

## Data transformation at the boundary

All monetary values cross the frontend-backend boundary as **dollar floats** (e.g., `3.50`). The conversion happens inside `database.py`:

```
                    Frontend          API Wire         Database
                    ────────          ────────         ────────
On save/update:     3.50       →      3.50      →     350 (cents)
On read:            3.50       ←      3.50      ←     350 (cents)
```

| Function | Direction | Formula |
|---|---|---|
| `_dollars_to_cents(val)` | Write path | `round(float(val) * 100)` |
| `_cents_to_dollars(val)` | Read path | `val / 100` |

The `round()` on the write path prevents floating-point drift (e.g., `19.99 * 100 = 1998.9999...` → `1999`).

---

## State lifecycle summary

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  User takes  │     │  OCR returns │     │  User edits  │     │  Saved to    │
│  photo       │────▶│  parsed data │────▶│  in card     │────▶│  SQLite      │
│              │     │  (no id)     │     │  (React state)│    │  (has id)    │
└──────────────┘     └──────────────┘     └──────────────┘     └──────────────┘
                                                │                      │
                                                │    ┌─────────────────┘
                                                │    │ User clicks history row
                                                │    ▼
                                                │  ┌──────────────┐
                                                └──│  Edit again  │──▶ PUT update
                                                   │  (has id)    │
                                                   └──────────────┘
```

| Stage | Where data lives | Has DB `id`? | Persisted? |
|---|---|---|---|
| After scan | `App.receipt` (React state) | ❌ | ❌ |
| During editing | `ReceiptCard` local state | Depends | ❌ |
| After save | SQLite `receipts` + `items` tables | ✅ | ✅ |
| Viewing history | `App.history` (React state, fetched from API) | ✅ | ✅ |
| Re-editing | `ReceiptCard` local state (copied from history) | ✅ | ✅ (until user saves again) |

Data is only at risk of loss between scan and save — if the user closes the browser before clicking "Save to History", the scanned data is gone. Once saved, it's in SQLite and survives browser refreshes, cache clears, and server restarts.
