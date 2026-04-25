# 🧾 Receipt Scanner

A mobile-first web app that photographs a receipt, extracts data via OCR, lets users correct mistakes inline, and saves the structured result to a SQLite database. Includes automatic item categorization and a spending visualization dashboard.

## Architecture

```
┌──────────────────┐       ┌──────────────────────┐       ┌────────────┐
│  React Frontend  │──────▶│  FastAPI Backend      │──────▶│  SQLite DB │
│  (Vite + Tailwind)│ /api │  (Tesseract OCR)     │       │ receipts.db│
│  Port 5173       │◀──────│  Port 9999           │◀──────│            │
└──────────────────┘       └──────────────────────┘       └────────────┘
```

The Vite dev server proxies `/api/*` → `localhost:9999`, so both services appear as a single origin with no CORS issues.

## Features

- **OCR scanning** — Upload or photograph a receipt; Tesseract extracts store name, date, line items, tax, tip, and total
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
- **Tesseract OCR** — install the system package:
  ```bash
  # macOS
  brew install tesseract

  # Ubuntu/Debian
  sudo apt install tesseract-ocr

  # conda (no sudo needed)
  conda install -c conda-forge tesseract
  ```
- **Node.js 18+** and npm

## Getting Started

### 1. Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
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

1. **Scan** — User uploads/photographs a receipt. The backend preprocesses the image (grayscale → auto-contrast → binary threshold → median filter) and runs Tesseract OCR. Regex patterns extract the store name, date, line items, subtotal, tax, tip, and total. Each item is automatically categorized using keyword matching.

2. **Edit** — The parsed data appears in an editable card. Users can fix item names/prices, change categories via dropdown, add or remove items, and adjust tax/tip. Subtotal and total are auto-calculated from the items.

3. **Save** — On save, the frontend sends the corrected data as JSON. The backend converts dollar amounts to integer cents and stores everything in SQLite. Fresh scans use `POST` (insert); previously saved receipts use `PUT` (update with item reconciliation: patch existing, insert new, delete removed).

4. **History** — Saved receipts appear in a history list. Users can click to re-open and edit, or delete.

5. **Spending Dashboard** — Below the history, a chart (toggleable between pie and bar) shows spending breakdown by category across all saved receipts. It refreshes automatically after every save or delete.

## Database Schema

**`receipts`** — store_name, date, subtotal/tax/tip/total (stored as integer cents), raw OCR text, scan timestamp.

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

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 19, Vite 8, Tailwind CSS 4, Recharts |
| Backend | FastAPI, Tesseract OCR, Pillow |
| Database | SQLite (WAL mode) |
| Formats | JPEG, PNG, HEIC (via pillow-heif) |
