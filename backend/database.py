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
