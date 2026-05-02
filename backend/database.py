import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "receipts.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def get_db():
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _column_exists(conn, table_name: str, column_name: str) -> bool:
    cols = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return any(c["name"] == column_name for c in cols)


def init_db():
    with get_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS receipts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                store_name TEXT,
                date TEXT,
                subtotal_cents INTEGER,
                tax_cents INTEGER,
                tip_cents INTEGER,
                total_cents INTEGER,
                raw_text TEXT,
                scanned_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )
        if not _column_exists(conn, "receipts", "user_id"):
            conn.execute("ALTER TABLE receipts ADD COLUMN user_id INTEGER")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                receipt_id INTEGER NOT NULL,
                name TEXT,
                price_cents INTEGER,
                product_id TEXT,
                category TEXT,
                FOREIGN KEY (receipt_id) REFERENCES receipts(id) ON DELETE CASCADE
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS monthly_budgets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                month TEXT NOT NULL,
                category TEXT NOT NULL,
                budget_cents INTEGER NOT NULL,
                UNIQUE (user_id, month, category),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS feedback_item_corrections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                store_name TEXT NOT NULL DEFAULT '',
                raw_item_name TEXT NOT NULL,
                corrected_item_name TEXT NOT NULL,
                corrected_category TEXT NOT NULL,
                times_seen INTEGER NOT NULL DEFAULT 1,
                last_seen TEXT NOT NULL,
                UNIQUE (user_id, store_name, raw_item_name, corrected_item_name, corrected_category),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS feedback_store_corrections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                raw_store_name TEXT NOT NULL,
                corrected_store_name TEXT NOT NULL,
                times_seen INTEGER NOT NULL DEFAULT 1,
                last_seen TEXT NOT NULL,
                UNIQUE (user_id, raw_store_name, corrected_store_name),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )


def _dollars_to_cents(val):
    if val is None:
        return None
    return round(float(val) * 100)


def _cents_to_dollars(val):
    if val is None:
        return None
    return val / 100


def create_user(username: str, password_hash: str) -> dict | None:
    now = datetime.utcnow().isoformat() + "Z"
    try:
        with get_db() as conn:
            cursor = conn.execute(
                "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
                (username, password_hash, now),
            )
        return {"id": cursor.lastrowid, "username": username, "createdAt": now}
    except sqlite3.IntegrityError:
        return None


def get_user_by_username(username: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if not row:
            return None
        return {
            "id": row["id"],
            "username": row["username"],
            "passwordHash": row["password_hash"],
            "createdAt": row["created_at"],
        }


def get_user_by_id(user_id: int) -> dict | None:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if not row:
            return None
        return {
            "id": row["id"],
            "username": row["username"],
            "passwordHash": row["password_hash"],
            "createdAt": row["created_at"],
        }


def save_receipt(receipt: dict, user_id: int | None = None) -> dict:
    with get_db() as conn:
        cursor = conn.execute(
            "INSERT INTO receipts (user_id, store_name, date, subtotal_cents, tax_cents, tip_cents, total_cents, raw_text, scanned_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                user_id,
                receipt.get("storeName"),
                receipt.get("date"),
                _dollars_to_cents(receipt.get("subtotal")),
                _dollars_to_cents(receipt.get("tax")),
                _dollars_to_cents(receipt.get("tip")),
                _dollars_to_cents(receipt.get("total")),
                receipt.get("rawText"),
                receipt.get("scannedAt"),
            ),
        )
        receipt_id = cursor.lastrowid
        for item in receipt.get("items", []):
            conn.execute(
                "INSERT INTO items (receipt_id, name, price_cents, product_id, category) VALUES (?, ?, ?, ?, ?)",
                (
                    receipt_id,
                    item.get("name"),
                    _dollars_to_cents(item.get("price")),
                    item.get("productId"),
                    item.get("category"),
                ),
            )
    return get_receipt(receipt_id, user_id=user_id)


def get_receipt(receipt_id: int, user_id: int | None = None) -> dict | None:
    with get_db() as conn:
        if user_id is None:
            row = conn.execute("SELECT * FROM receipts WHERE id = ?", (receipt_id,)).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM receipts WHERE id = ? AND user_id = ?", (receipt_id, user_id)
            ).fetchone()
        if not row:
            return None
        items = conn.execute(
            "SELECT * FROM items WHERE receipt_id = ? ORDER BY id", (receipt_id,)
        ).fetchall()
        return _row_to_receipt(row, items)


def update_receipt(receipt_id: int, receipt: dict, user_id: int | None = None) -> dict | None:
    with get_db() as conn:
        if user_id is None:
            row = conn.execute("SELECT id FROM receipts WHERE id = ?", (receipt_id,)).fetchone()
        else:
            row = conn.execute(
                "SELECT id FROM receipts WHERE id = ? AND user_id = ?", (receipt_id, user_id)
            ).fetchone()
        if not row:
            return None

        if user_id is None:
            conn.execute(
                "UPDATE receipts SET store_name=?, date=?, subtotal_cents=?, tax_cents=?, tip_cents=?, total_cents=?, raw_text=?, scanned_at=? WHERE id=?",
                (
                    receipt.get("storeName"),
                    receipt.get("date"),
                    _dollars_to_cents(receipt.get("subtotal")),
                    _dollars_to_cents(receipt.get("tax")),
                    _dollars_to_cents(receipt.get("tip")),
                    _dollars_to_cents(receipt.get("total")),
                    receipt.get("rawText"),
                    receipt.get("scannedAt"),
                    receipt_id,
                ),
            )
        else:
            conn.execute(
                "UPDATE receipts SET store_name=?, date=?, subtotal_cents=?, tax_cents=?, tip_cents=?, total_cents=?, raw_text=?, scanned_at=? WHERE id=? AND user_id=?",
                (
                    receipt.get("storeName"),
                    receipt.get("date"),
                    _dollars_to_cents(receipt.get("subtotal")),
                    _dollars_to_cents(receipt.get("tax")),
                    _dollars_to_cents(receipt.get("tip")),
                    _dollars_to_cents(receipt.get("total")),
                    receipt.get("rawText"),
                    receipt.get("scannedAt"),
                    receipt_id,
                    user_id,
                ),
            )

        incoming_items = receipt.get("items", [])
        incoming_ids = {item["id"] for item in incoming_items if item.get("id") is not None}

        existing_ids = {
            r["id"]
            for r in conn.execute("SELECT id FROM items WHERE receipt_id = ?", (receipt_id,)).fetchall()
        }
        removed_ids = existing_ids - incoming_ids
        if removed_ids:
            placeholders = ",".join("?" for _ in removed_ids)
            conn.execute(
                f"DELETE FROM items WHERE id IN ({placeholders}) AND receipt_id = ?",
                (*removed_ids, receipt_id),
            )

        for item in incoming_items:
            item_id = item.get("id")
            if item_id is not None and item_id in existing_ids:
                conn.execute(
                    "UPDATE items SET name=?, price_cents=?, product_id=?, category=? WHERE id=? AND receipt_id=?",
                    (
                        item.get("name"),
                        _dollars_to_cents(item.get("price")),
                        item.get("productId"),
                        item.get("category"),
                        item_id,
                        receipt_id,
                    ),
                )
            else:
                conn.execute(
                    "INSERT INTO items (receipt_id, name, price_cents, product_id, category) VALUES (?, ?, ?, ?, ?)",
                    (
                        receipt_id,
                        item.get("name"),
                        _dollars_to_cents(item.get("price")),
                        item.get("productId"),
                        item.get("category"),
                    ),
                )
    return get_receipt(receipt_id, user_id=user_id)


def list_receipts(user_id: int | None = None) -> list[dict]:
    with get_db() as conn:
        if user_id is None:
            rows = conn.execute("SELECT * FROM receipts ORDER BY id DESC").fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM receipts WHERE user_id = ? ORDER BY id DESC", (user_id,)
            ).fetchall()
        results = []
        for row in rows:
            items = conn.execute(
                "SELECT * FROM items WHERE receipt_id = ? ORDER BY id", (row["id"],)
            ).fetchall()
            results.append(_row_to_receipt(row, items))
        return results


def delete_receipt(receipt_id: int, user_id: int | None = None) -> bool:
    with get_db() as conn:
        if user_id is None:
            cursor = conn.execute("DELETE FROM receipts WHERE id = ?", (receipt_id,))
        else:
            cursor = conn.execute(
                "DELETE FROM receipts WHERE id = ? AND user_id = ?", (receipt_id, user_id)
            )
        return cursor.rowcount > 0


def _receipt_month(receipt_date: str | None, scanned_at: str | None) -> str | None:
    if receipt_date:
        for fmt in ("%m/%d/%Y", "%m-%d-%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(receipt_date, fmt).strftime("%Y-%m")
            except ValueError:
                continue
    if scanned_at and len(scanned_at) >= 7:
        return scanned_at[:7]
    return None


def get_monthly_spend_by_category(user_id: int, month: str) -> dict[str, float]:
    totals = {}
    for receipt in list_receipts(user_id=user_id):
        receipt_month = _receipt_month(receipt.get("date"), receipt.get("scannedAt"))
        if receipt_month != month:
            continue
        for item in receipt.get("items", []):
            category = item.get("category") or "Other"
            price = item.get("price") or 0
            totals[category] = round(totals.get(category, 0) + price, 2)
    return totals


def get_budgets(user_id: int, month: str) -> dict[str, float]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT category, budget_cents FROM monthly_budgets WHERE user_id = ? AND month = ?",
            (user_id, month),
        ).fetchall()
    return {row["category"]: _cents_to_dollars(row["budget_cents"]) for row in rows}


def upsert_budgets(user_id: int, month: str, budgets: dict[str, float]) -> dict[str, float]:
    with get_db() as conn:
        for category, value in budgets.items():
            cents = _dollars_to_cents(value)
            if cents is None or cents <= 0:
                conn.execute(
                    "DELETE FROM monthly_budgets WHERE user_id = ? AND month = ? AND category = ?",
                    (user_id, month, category),
                )
                continue
            conn.execute(
                """
                INSERT INTO monthly_budgets (user_id, month, category, budget_cents)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id, month, category)
                DO UPDATE SET budget_cents=excluded.budget_cents
                """,
                (user_id, month, category, cents),
            )
    return get_budgets(user_id, month)


def _normalize_text(value: str | None) -> str:
    return (value or "").strip()


def _normalize_store(value: str | None) -> str:
    return _normalize_text(value).lower()


def _upsert_item_feedback(
    conn,
    user_id: int,
    store_name: str,
    raw_item_name: str,
    corrected_item_name: str,
    corrected_category: str,
) -> None:
    now = datetime.utcnow().isoformat() + "Z"
    conn.execute(
        """
        INSERT INTO feedback_item_corrections
        (user_id, store_name, raw_item_name, corrected_item_name, corrected_category, times_seen, last_seen)
        VALUES (?, ?, ?, ?, ?, 1, ?)
        ON CONFLICT(user_id, store_name, raw_item_name, corrected_item_name, corrected_category)
        DO UPDATE SET
            times_seen = feedback_item_corrections.times_seen + 1,
            last_seen = excluded.last_seen
        """,
        (user_id, store_name, raw_item_name, corrected_item_name, corrected_category, now),
    )


def _upsert_store_feedback(conn, user_id: int, raw_store_name: str, corrected_store_name: str) -> None:
    now = datetime.utcnow().isoformat() + "Z"
    conn.execute(
        """
        INSERT INTO feedback_store_corrections
        (user_id, raw_store_name, corrected_store_name, times_seen, last_seen)
        VALUES (?, ?, ?, 1, ?)
        ON CONFLICT(user_id, raw_store_name, corrected_store_name)
        DO UPDATE SET
            times_seen = feedback_store_corrections.times_seen + 1,
            last_seen = excluded.last_seen
        """,
        (user_id, raw_store_name, corrected_store_name, now),
    )


def record_feedback_from_receipt_edit(user_id: int, before: dict, after: dict) -> None:
    """
    Persist user-approved corrections so future OCR/categorization prompts can be personalized.
    """
    before_store = _normalize_store(before.get("storeName"))
    after_store = _normalize_store(after.get("storeName"))
    effective_store = after_store or before_store

    with get_db() as conn:
        if before_store and after_store and before_store != after_store:
            _upsert_store_feedback(conn, user_id, before_store, after_store)

        before_by_id = {}
        for item in before.get("items", []):
            item_id = item.get("id")
            if item_id is not None:
                before_by_id[item_id] = item

        for item in after.get("items", []):
            item_id = item.get("id")
            if item_id is None or item_id not in before_by_id:
                continue

            old = before_by_id[item_id]
            old_name = _normalize_text(old.get("name"))
            new_name = _normalize_text(item.get("name"))
            old_category = _normalize_text(old.get("category")) or "Other"
            new_category = _normalize_text(item.get("category")) or "Other"

            changed = (old_name != new_name) or (old_category != new_category)
            if not changed or not old_name:
                continue

            _upsert_item_feedback(
                conn=conn,
                user_id=user_id,
                store_name=effective_store,
                raw_item_name=old_name.lower(),
                corrected_item_name=(new_name or old_name).lower(),
                corrected_category=new_category,
            )


def record_feedback_from_category_overrides(
    user_id: int, store_name: str | None, overrides: list[dict]
) -> None:
    """
    Persist category corrections inferred from a newly saved receipt.
    Each override item should include:
      - rawItemName
      - correctedItemName
      - correctedCategory
    """
    norm_store = _normalize_store(store_name)
    with get_db() as conn:
        for item in overrides:
            raw_name = _normalize_text(item.get("rawItemName")).lower()
            corrected_name = _normalize_text(item.get("correctedItemName")).lower() or raw_name
            corrected_category = _normalize_text(item.get("correctedCategory")) or "Other"
            if not raw_name:
                continue
            _upsert_item_feedback(
                conn=conn,
                user_id=user_id,
                store_name=norm_store,
                raw_item_name=raw_name,
                corrected_item_name=corrected_name,
                corrected_category=corrected_category,
            )


def get_feedback_examples(
    user_id: int, store_name: str | None = None, item_names: list[str] | None = None, limit: int = 8
) -> dict:
    norm_store = _normalize_store(store_name)
    norm_items = {_normalize_text(name).lower() for name in (item_names or []) if _normalize_text(name)}

    with get_db() as conn:
        if norm_store:
            rows = conn.execute(
                """
                SELECT store_name, raw_item_name, corrected_item_name, corrected_category, times_seen, last_seen
                FROM feedback_item_corrections
                WHERE user_id = ? AND (store_name = ? OR store_name = '')
                ORDER BY times_seen DESC, last_seen DESC
                LIMIT 100
                """,
                (user_id, norm_store),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT store_name, raw_item_name, corrected_item_name, corrected_category, times_seen, last_seen
                FROM feedback_item_corrections
                WHERE user_id = ?
                ORDER BY times_seen DESC, last_seen DESC
                LIMIT 100
                """,
                (user_id,),
            ).fetchall()

        item_examples = []
        for row in rows:
            raw_name = row["raw_item_name"]
            corrected_name = row["corrected_item_name"]
            match_score = int(raw_name in norm_items or corrected_name in norm_items)
            store_match = int(bool(norm_store) and row["store_name"] == norm_store)
            if (norm_items or norm_store) and not (match_score or store_match):
                continue
            score = (match_score * 1000) + (store_match * 100) + row["times_seen"]
            item_examples.append(
                {
                    "storeName": row["store_name"],
                    "rawItemName": raw_name,
                    "correctedItemName": corrected_name,
                    "correctedCategory": row["corrected_category"],
                    "timesSeen": row["times_seen"],
                    "score": score,
                }
            )
        item_examples.sort(key=lambda x: (x["score"], x["timesSeen"]), reverse=True)
        item_examples = item_examples[:limit]

        store_rows = conn.execute(
            """
            SELECT raw_store_name, corrected_store_name, times_seen
            FROM feedback_store_corrections
            WHERE user_id = ?
            ORDER BY times_seen DESC, last_seen DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
        store_examples = [
            {
                "rawStoreName": row["raw_store_name"],
                "correctedStoreName": row["corrected_store_name"],
                "timesSeen": row["times_seen"],
            }
            for row in store_rows
        ]

    return {"itemExamples": item_examples, "storeExamples": store_examples}


def _row_to_receipt(row, item_rows) -> dict:
    return {
        "id": row["id"],
        "storeName": row["store_name"],
        "date": row["date"],
        "subtotal": _cents_to_dollars(row["subtotal_cents"]),
        "tax": _cents_to_dollars(row["tax_cents"]),
        "tip": _cents_to_dollars(row["tip_cents"]),
        "total": _cents_to_dollars(row["total_cents"]),
        "rawText": row["raw_text"],
        "scannedAt": row["scanned_at"],
        "items": [
            {
                "id": item["id"],
                "name": item["name"],
                "price": _cents_to_dollars(item["price_cents"]),
                "productId": item["product_id"],
                "category": item["category"],
            }
            for item in item_rows
        ],
    }
