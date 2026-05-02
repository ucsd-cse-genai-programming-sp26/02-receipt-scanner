# 🧾 Receipt Scanner

📺 [Watch the demo video](https://youtu.be/8YKEF-zYSv4)

A mobile-first web app that photographs a receipt, extracts data via OCR, lets users correct mistakes inline, and saves the structured result to a SQLite database. Includes automatic item categorization and a spending visualization dashboard.

## Architecture

```
┌──────────────────┐       ┌──────────────────────┐       ┌────────────┐
│  React Frontend  │──────▶│  FastAPI Backend      │──────▶│  SQLite DB │
│  (Vite + Tailwind)│ /api │  (GPT-4o Vision)     │       │ receipts.db│
│  Port 5173       │◀──────│  Port 9999           │◀──────│            │
└──────────────────┘       └──────────────────────┘       └────────────┘
```

The Vite dev server proxies `/api/*` → `localhost:9999`, so both services appear as a single origin with no CORS issues.

## Features

- **GPT-4o Vision OCR** — Upload or photograph a receipt; OpenAI's GPT-4o vision model extracts store name, date, line items, tax, tip, and total directly from the image
- **Inline editing** — Every field is editable so users can fix OCR mistakes before saving
- **Auto-categorization** — Items are automatically assigned a spending category (Groceries, Beverages, Electronics, etc.) via keyword matching; users can override with a dropdown
- **Spending visualization** — Pie chart and bar chart views showing spending by category across all saved receipts (powered by Recharts)
- **Auto-calculated totals** — Subtotal = sum of item prices; total = subtotal + tax + tip. Updated live as you edit.
- **HEIC support** — iPhone photos (HEIC format) are handled automatically via `pillow-heif`
- **Persistent storage** — Corrected receipts are saved to a normalized SQLite database (receipts + items tables)
- **Full CRUD** — Create, read, update, and delete receipts through the REST API
- **Granular updates** — Editing a receipt patches existing items, adds new ones, and removes deleted ones — without destroying other items
- **Mobile-first UI** — `<input capture="environment">` opens the rear camera directly; Tailwind CSS provides a clean responsive layout

## Prerequisites

- **Python 3.10+**
- **OpenAI API key** — get one at [platform.openai.com/api-keys](https://platform.openai.com/api-keys) (GPT-4o vision is used for receipt parsing)
- **Node.js 18+** and npm

## Getting Started

### 1. Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Set your OpenAI API key
export OPENAI_API_KEY="sk-..."

uvicorn main:app --reload --port 9999
```

The database (`receipts.db`) is created automatically on first startup.

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173** in your browser.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/scan` | Upload an image → OCR → return parsed JSON with auto-categories |
| `GET` | `/api/receipts` | List all saved receipts (newest first) |
| `POST` | `/api/receipts` | Save a new corrected receipt |
| `GET` | `/api/receipts/:id` | Get a single receipt by ID |
| `PUT` | `/api/receipts/:id` | Update an existing receipt (reconciles items) |
| `DELETE` | `/api/receipts/:id` | Delete a receipt and its items (cascade) |
| `GET` | `/api/stats/categories` | Get spending totals grouped by category |
| `GET` | `/api/health` | Health check |

## How It Works

1. **Scan** — User uploads/photographs a receipt. The backend sends the image to OpenAI's GPT-4o vision model, which returns structured JSON with store name, date, line items, subtotal, tax, tip, and total. Each item is then automatically categorized using keyword matching.

2. **Edit** — The parsed data appears in an editable card. Users can fix item names/prices, change categories via dropdown, add or remove items, and adjust tax/tip. Subtotal and total are auto-calculated from the items.

3. **Save** — On save, the frontend sends the corrected data as JSON. The backend converts dollar amounts to integer cents and stores everything in SQLite. Fresh scans use `POST` (insert); previously saved receipts use `PUT` (update with item reconciliation: patch existing, insert new, delete removed).

4. **History** — Saved receipts appear in a history list. Users can click to re-open and edit, or delete.

5. **Spending Dashboard** — Below the history, a chart (toggleable between pie and bar) shows spending breakdown by category across all saved receipts. It refreshes automatically after every save or delete.

## Database Schema

**`receipts`** — store_name, date, subtotal/tax/tip/total (stored as integer cents), raw GPT-4o response, scan timestamp.

**`items`** — receipt_id (FK with cascade delete), name, price_cents, product_id, category.

All monetary values cross the API boundary as dollar floats (e.g., `3.50`) and are stored as integer cents (e.g., `350`) to avoid floating-point precision issues.

## Project Structure

```
receipt-scanner-lecture/
├── backend/
│   ├── main.py              # FastAPI app — OCR + CRUD + stats endpoints
│   ├── database.py          # SQLite schema, queries, dollar↔cents conversion
│   ├── categorizer.py       # Keyword-based item categorizer (10 categories)
│   ├── test_database.py     # Pytest tests for all CRUD operations
│   └── requirements.txt     # Python dependencies
├── frontend/
│   ├── src/
│   │   ├── App.jsx                  # Top-level state, API orchestration
│   │   └── components/
│   │       ├── UploadArea.jsx       # Drag-drop + camera upload
│   │       ├── ReceiptCard.jsx      # Editable receipt with category dropdowns
│   │       ├── ReceiptHistory.jsx   # Saved receipts list
│   │       └── SpendingChart.jsx    # Pie/bar chart spending visualization
│   ├── vite.config.js               # Vite + Tailwind + API proxy config
│   └── package.json
├── DESIGN.md                # Detailed design decisions
├── STORAGE.md               # Data flow and storage documentation
└── README.md                # This file
```

## Running Tests

```bash
cd backend
source venv/bin/activate
pytest test_database.py -v
```

## OCR Evaluation Workflow

The repo includes an OCR evaluation utility that supports:
- interactive annotation from `document_scanner_photos`
- OCR-seeded drafts you can keep/edit into ground truth
- precision, recall, F1, accuracy, and exact-match reporting

### 1. Annotate Ground Truth

```bash
cd /home/isadorawhite/cse291p/receipt-scanner-lecture
export OPENAI_API_KEY="sk-..."
backend/venv/bin/python backend/ocr_eval.py annotate
```

Annotation behavior:
- Each image starts with an OCR draft.
- Choose `k` (keep), `e` (edit), or `s` (skip).
- Saved labels go to `backend/ocr_annotations.json`.

### 2. Run Evaluation

```bash
cd /home/isadorawhite/cse291p/receipt-scanner-lecture
export OPENAI_API_KEY="sk-..."
backend/venv/bin/python backend/ocr_eval.py evaluate
```

Outputs:
- per-example metrics in terminal
- aggregate report in `backend/ocr_eval_report.json`
- cached predictions in `backend/ocr_predictions.json`

### Latest Evaluate Run Results

Run date: **May 1, 2026**

- Examples evaluated: `10`
- Micro: `Precision=1.000`, `Recall=1.000`, `F1=1.000`, `Accuracy=1.000`
- Macro: `Precision=1.000`, `Recall=1.000`, `F1=1.000`, `Accuracy=1.000`
- Exact match rate: `1.000`

Command used:

```bash
OPENAI_API_KEY=dummy backend/venv/bin/python backend/ocr_eval.py evaluate
```

Note: this run used cached OCR predictions in `backend/ocr_predictions.json`.

## Category Evaluation Workflow

The repo also includes category-label evaluation for the LLM categorizer.

### 1. Annotate Category Ground Truth

```bash
cd /home/isadorawhite/cse291p/receipt-scanner-lecture
export OPENAI_API_KEY="sk-..."
backend/venv/bin/python backend/category_eval.py annotate
```

Annotation behavior:
- Receipt items are extracted and category-predicted first.
- For each image choose `a` (accept all), `e` (edit each item category), or `s` (skip).
- Saved labels go to `backend/category_annotations.json`.

### 2. Run Category Evaluation

```bash
cd /home/isadorawhite/cse291p/receipt-scanner-lecture
export OPENAI_API_KEY="sk-..."
backend/venv/bin/python backend/category_eval.py evaluate
```

Outputs:
- per-image accuracy in terminal
- aggregate category metrics in `backend/category_eval_report.json`
- cached predictions in `backend/category_predictions.json`

Useful options:

```bash
# Rebuild predictions from model before annotation
backend/venv/bin/python backend/category_eval.py annotate --refresh-predictions

# Re-run category predictions during evaluation
backend/venv/bin/python backend/category_eval.py evaluate --refresh-predictions
```

### Latest Category Evaluate Run Results

Run date: **May 1, 2026**

Baseline run:
- Items evaluated: `24`
- Accuracy: `0.708`
- Micro: `Precision=0.708`, `Recall=0.708`, `F1=0.708`
- Macro: `Precision=0.381`, `Recall=0.409`, `F1=0.376`

Feedback-enabled run (`11:51 PM`):
- Items evaluated: `24`
- Accuracy: `0.833`
- Micro: `Precision=0.833`, `Recall=0.833`, `F1=0.833`
- Macro: `Precision=0.400`, `Recall=0.432`, `F1=0.408`

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 19, Vite 8, Tailwind CSS 4, Recharts |
| Backend | FastAPI, OpenAI GPT-4o Vision, Pillow |
| Database | SQLite (WAL mode) |
| Formats | JPEG, PNG, HEIC (via pillow-heif) |

## Demo Video

📺 [Watch the demo video](https://youtu.be/8YKEF-zYSv4)
