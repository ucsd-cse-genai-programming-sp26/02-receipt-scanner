# Receipt Scanner — Design Decisions

## Overview

A mobile-first web app where users photograph a receipt, OCR extracts the data, users correct mistakes inline, and the corrected data is persisted to a SQLite database. Items are automatically categorized for spending analysis.

---

## Three Key Design Decisions

### 1. Store corrected human data in SQLite, not raw images

**Decision**: Persist the structured, user-corrected receipt data (store name, date, line items with prices and categories, tax, tip, total) in a normalized SQLite database. Raw images are not stored.

**Why this matters**: OCR output is inherently noisy — misread characters, merged lines, phantom digits. The valuable artifact is the _corrected_ data after a human reviews and fixes it. Storing raw images would require blob storage, re-parsing on every read, and would never be as accurate as the human-corrected version.

**How it works**:
- The scan endpoint (`POST /api/scan`) returns ephemeral JSON — it is not saved anywhere.
- The user edits fields in the UI, then explicitly clicks Save.
- Only at that point does the data enter SQLite, already cleaned by the user.
- The raw OCR text is stored alongside for debugging, but the source of truth is always the edited fields.

**Schema design**: Two normalized tables instead of a single denormalized blob:

| Table | Key Columns |
|-------|------------|
| `receipts` | id, store_name, date, subtotal_cents, tax_cents, tip_cents, total_cents, raw_text, scanned_at |
| `items` | id, receipt_id (FK CASCADE), name, price_cents, product_id, category |

All monetary values are stored as **integer cents** (e.g., `$3.49` → `349`) to avoid floating-point precision issues. The API sends/receives dollar floats; conversion happens transparently at the database boundary via `_dollars_to_cents()` and `_cents_to_dollars()` helper functions.

**Trade-offs**:
- ✅ Queryable (e.g., "find all Groceries items over $10")
- ✅ Small storage footprint
- ✅ No image processing on reads
- ❌ Cannot re-OCR or re-process later (the image is gone)
- ❌ No migration system yet — schema changes require deleting `receipts.db`

---

### 2. Granular item reconciliation on update (patch/add/delete, not replace-all)

**Decision**: When a user edits a previously saved receipt and hits Update, the backend reconciles items individually rather than deleting all items and reinserting.

**Why this matters**: A naive "delete all items, reinsert" approach destroys item IDs on every update. If items have stable IDs, they can be referenced externally (e.g., linked to categories, flagged for review, tracked over time). It also means a small edit (changing one item's price) doesn't generate unnecessary DELETE+INSERT churn.

**How it works**: The `PUT /api/receipts/:id` endpoint receives the full receipt with its items array. Each item follows an identity contract:

| Item state | Condition | Backend action |
|-----------|-----------|---------------|
| **Patch** | Item has an integer `id` that exists in the DB | `UPDATE` that row's name, price, product_id, category |
| **Add** | Item has `id: null` | `INSERT` a new row; SQLite assigns a new auto-increment ID |
| **Delete** | A DB item's `id` is missing from the incoming list | `DELETE` that row |

**Frontend contract**: When the user clicks "+ Add item" in the UI, the new item gets `id: null` (not a fake numeric ID). This is how the backend distinguishes "new" from "existing":

```
OCR scan         →  items have  id: null     (not yet in DB)
POST /receipts   →  items get   id: 1, 2     (assigned by SQLite)
GET  /receipts   →  items have  id: 1, 2     (from DB)
User adds item   →  new item    id: null     (not yet in DB)
PUT  /receipts/1 →  id:1 patched, id:2 patched, id:null inserted as id:3
```

**Trade-offs**:
- ✅ Stable item IDs across updates
- ✅ Minimal database writes for small edits
- ✅ Categories and other per-item metadata survive updates
- ❌ More complex reconciliation logic than replace-all
- ❌ Frontend must carefully manage `id: null` vs integer IDs

---

### 3. Keyword-based auto-categorization with user override

**Decision**: Use a local, free keyword-matching system to auto-categorize receipt items (no external API or LLM required), with every category editable by the user via a dropdown.

**Why this matters**: Categorization enables the spending visualization feature — without categories, there's nothing to chart. The user wanted LLM-based categorization but also wanted zero API keys and zero cost. A keyword matcher is a pragmatic middle ground: instant, deterministic, and free.

**How it works**:

1. **On scan**: After Tesseract extracts items, `categorize_items()` from `categorizer.py` runs on each item name. It checks against keyword dictionaries for 10 categories:

   | Category | Example keywords |
   |----------|-----------------|
   | Groceries | bread, eggs, flour, rice, chicken, beef |
   | Beverages | coffee, tea, juice, soda, water, beer, wine |
   | Dairy | milk, cheese, yogurt, butter, cream |
   | Snacks | chips, candy, cookies, chocolate, popcorn |
   | Personal Care | shampoo, soap, toothpaste, deodorant |
   | Household | paper towel, detergent, trash bag, bleach |
   | Electronics | battery, cable, charger, adapter, usb |
   | Clothing | shirt, pants, socks, jacket, shoes |
   | Dining | meal, combo, burger, pizza, sandwich |
   | Entertainment | ticket, movie, game, book, magazine |
   | Other | _(default fallback)_ |

2. **On display**: Each item row in `ReceiptCard` shows a `<select>` dropdown pre-populated with the auto-assigned category. The user can change it to any of the 11 options.

3. **On save/update**: The category is stored in the `items.category` column. On update (PUT), existing items keep their user-set category — the auto-categorizer only runs on fresh scans, never on updates.

4. **Visualization**: `GET /api/stats/categories` aggregates `SUM(price_cents)` grouped by category across all receipts. The `SpendingChart` component renders this as a toggleable pie chart or bar chart via Recharts.

**Trade-offs**:
- ✅ Zero cost, zero latency, works offline
- ✅ Deterministic — same item always gets the same category
- ✅ User can always override
- ❌ Limited vocabulary — novel items fall through to "Other"
- ❌ No learning from user corrections (a real LLM could improve over time)
- 🔄 Future upgrade path: swap `categorize_item()` for an LLM call without changing the schema or UI

---

## Supporting Design Choices

These weren't the three _key_ decisions but are worth noting:

- **Tesseract OCR (self-hosted, free)**: No API keys, no costs, works offline. Lower accuracy than cloud services but acceptable for a class project with human correction as a safety net.
- **Vite dev proxy**: `/api/*` → `localhost:9999` avoids CORS issues and mirrors how a production reverse proxy would work.
- **Auto-calculated totals**: Subtotal = sum of item prices (read-only). Total = subtotal + tax + tip (read-only). Only tax and tip are manually editable. This prevents the common bug where the total doesn't match the items.
- **HEIC support**: iPhones default to HEIC format; `pillow-heif` handles this transparently.
- **Mobile-first UI**: `<input capture="environment">` opens the rear camera directly. Tailwind CSS utility classes keep the layout responsive with no custom CSS.
- **Pessimistic updates**: The UI waits for the server response before updating the history list. Simpler than optimistic updates and avoids sync issues.
