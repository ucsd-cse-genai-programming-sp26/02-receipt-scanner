# Final Submission

## Overview
Implemented all requested features in the receipt scanner codebase:
1. Secure password-based authentication system.
2. LLM-based item categorization (replacing keyword string matching).
3. Monthly budget summary by category, including budget satisfaction/progress.

---

## 1) Secure Authentication System

### What was added
- User registration and login with password hashing.
- JWT-based access tokens for authenticated API access.
- Password strength validation.
- Per-user data isolation so each user only accesses their own receipts and budgets.

### Backend files changed
- `backend/auth.py` (new)
- `backend/main.py`
- `backend/database.py`
- `backend/requirements.txt`

### Security implementation details
- Passwords are hashed using `passlib[bcrypt]`.
- Password policy enforced at registration:
  - minimum 12 characters
  - at least one uppercase and one lowercase letter
  - at least one number
  - at least one special character
- JWT tokens created with:
  - algorithm: `HS256`
  - expiry: 12 hours
- Protected routes require `Authorization: Bearer <token>`.
- Token validation includes expiry and user existence checks.
- Data is scoped by `user_id` for receipt and budget queries.

### New auth endpoints
- `POST /api/auth/register`
- `POST /api/auth/login`
- `GET /api/auth/me`

### Database changes for auth
- Added `users` table:
  - `id`, `username` (unique), `password_hash`, `created_at`
- Added `user_id` column on `receipts` table (migration-safe check via `PRAGMA table_info`).

### Frontend auth UX
- Added a dedicated auth form with login/register toggle.
- Stores token and user in `localStorage`:
  - `receipt_scanner_token`
  - `receipt_scanner_user`
- Adds bearer token to API requests through centralized `apiFetch`.
- Auto-logout on `401 Unauthorized`.

---

## 2) LLM-Based Categorization

### What was changed
- Replaced keyword-based categorization logic with an LLM call.
- Categorization now uses a single batched model call per receipt item list.

### Backend files changed
- `backend/categorizer.py`
- `backend/main.py`

### Categorization behavior
- Uses OpenAI chat completion with model `gpt-4.1-mini`.
- Uses JSON response format with strict output expectation:
  - `{ "categories": [ ... ] }`
- Enforces allowed category set:
  - `Groceries`, `Beverages`, `Dairy`, `Snacks`, `Personal Care`, `Household`, `Electronics`, `Clothing`, `Dining`, `Entertainment`, `Other`
- Invalid or missing predictions are coerced to `Other`.
- If API key is missing or LLM call fails, falls back safely to `Other`.

---

## 3) Monthly Summary + Budgets

### What was added
- User-defined monthly budgets per category.
- Monthly summary endpoint combining actual spend and budget data.
- Per-category progress and satisfaction status.

### Backend files changed
- `backend/database.py`
- `backend/main.py`

### New database table
- `monthly_budgets`:
  - `id`, `user_id`, `month`, `category`, `budget_cents`
  - unique constraint on `(user_id, month, category)`

### New budget/summary endpoints
- `GET /api/budgets/{month}`
- `PUT /api/budgets/{month}`
- `GET /api/stats/monthly-summary?month=YYYY-MM`

### Summary calculation details
For each category in a month:
- `spent`
- `budget`
- `remaining`
- `percentUsed`
- `satisfied` (true when within budget)

Also returns overall totals:
- `totals.spent`
- `totals.budget`
- `totals.remaining`

### Frontend monthly summary UI
- Added new component:
  - `frontend/src/components/MonthlySummary.jsx`
- Features:
  - month picker (`<input type="month">`)
  - per-category editable budget fields
  - save budgets action
  - per-category progress bar (green within budget, red over budget)
  - monthly totals display

---

## Additional Frontend Integration Work

### Updated files
- `frontend/src/App.jsx`
- `frontend/src/components/SpendingChart.jsx`
- `frontend/src/components/AuthForm.jsx` (new)
- `frontend/src/components/MonthlySummary.jsx` (new)

### Behavior updates
- App is now auth-gated.
- Existing scan/save/history/category-chart functionality now uses authenticated calls.
- Monthly summary refreshes after save/delete operations via `refreshKey` updates.

---

## Dependency Updates

### `backend/requirements.txt`
Added:
- `PyJWT`
- `passlib[bcrypt]`

Existing dependencies retained:
- `fastapi`
- `uvicorn[standard]`
- `Pillow`
- `pillow-heif`
- `python-multipart`
- `openai`

---

## Validation / Verification Performed

### Backend tests
- Command run:
  - `backend/venv/bin/python -m pytest -q backend/test_database.py`
- Result:
  - `34 passed`

### Frontend build
- Command run:
  - `npm run build` (from `frontend/`)
- Result:
  - successful production build completed.

### Import/runtime sanity check
- Verified backend app imports after dependency install when `JWT_SECRET` is set.

---

## Required Runtime Configuration

Set these environment variables before running backend:
- `OPENAI_API_KEY` (required for receipt scan + LLM categorization)
- `JWT_SECRET` (required for signing/verifying auth tokens)

Example:
```bash
export OPENAI_API_KEY="sk-..."
export JWT_SECRET="replace-with-a-long-random-secret"
```

---

## Notes
- Existing CRUD and chart endpoints were preserved but now require authentication and are user-scoped.
- DB values continue using dollars at API boundary and integer cents in storage.
- Existing test suite (`backend/test_database.py`) still passes after refactor.
