import sqlite3
import os
import json
from contextlib import contextmanager

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


def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS receipts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                store_name TEXT,
                date TEXT,
                subtotal_cents INTEGER,
                tax_cents INTEGER,
                tip_cents INTEGER,
                total_cents INTEGER,
                raw_text TEXT,
                scanned_at TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                receipt_id INTEGER NOT NULL,
                name TEXT,
                price_cents INTEGER,
                product_id TEXT,
                category TEXT,
                FOREIGN KEY (receipt_id) REFERENCES receipts(id) ON DELETE CASCADE
            )
        """)


def _dollars_to_cents(val):
    if val is None:
        return None
    return round(float(val) * 100)


def _cents_to_dollars(val):
    if val is None:
        return None
    return val / 100


def save_receipt(receipt: dict) -> dict:
    with get_db() as conn:
        cursor = conn.execute(
            "INSERT INTO receipts (store_name, date, subtotal_cents, tax_cents, tip_cents, total_cents, raw_text, scanned_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (receipt.get("storeName"), receipt.get("date"),
             _dollars_to_cents(receipt.get("subtotal")),
             _dollars_to_cents(receipt.get("tax")),
             _dollars_to_cents(receipt.get("tip")),
             _dollars_to_cents(receipt.get("total")),
             receipt.get("rawText"), receipt.get("scannedAt")),
        )
        receipt_id = cursor.lastrowid
        for item in receipt.get("items", []):
            conn.execute(
                "INSERT INTO items (receipt_id, name, price_cents, product_id, category) VALUES (?, ?, ?, ?, ?)",
                (receipt_id, item.get("name"),
                 _dollars_to_cents(item.get("price")),
                 item.get("productId"), item.get("category")),
            )
    return get_receipt(receipt_id)


def get_receipt(receipt_id: int) -> dict | None:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM receipts WHERE id = ?", (receipt_id,)).fetchone()
        if not row:
            return None
        items = conn.execute(
            "SELECT * FROM items WHERE receipt_id = ? ORDER BY id", (receipt_id,)
        ).fetchall()
        return _row_to_receipt(row, items)


def update_receipt(receipt_id: int, receipt: dict) -> dict | None:
    with get_db() as conn:
        row = conn.execute("SELECT id FROM receipts WHERE id = ?", (receipt_id,)).fetchone()
        if not row:
            return None
        conn.execute(
            "UPDATE receipts SET store_name=?, date=?, subtotal_cents=?, tax_cents=?, tip_cents=?, total_cents=?, raw_text=?, scanned_at=? WHERE id=?",
            (receipt.get("storeName"), receipt.get("date"),
             _dollars_to_cents(receipt.get("subtotal")),
             _dollars_to_cents(receipt.get("tax")),
             _dollars_to_cents(receipt.get("tip")),
             _dollars_to_cents(receipt.get("total")),
             receipt.get("rawText"), receipt.get("scannedAt"), receipt_id),
        )

        incoming_items = receipt.get("items", [])
        incoming_ids = {item["id"] for item in incoming_items if item.get("id") is not None}

        # Delete items that are no longer in the list
        existing_ids = {
            r["id"] for r in
            conn.execute("SELECT id FROM items WHERE receipt_id = ?", (receipt_id,)).fetchall()
        }
        removed_ids = existing_ids - incoming_ids
        if removed_ids:
            placeholders = ",".join("?" for _ in removed_ids)
            conn.execute(
                f"DELETE FROM items WHERE id IN ({placeholders}) AND receipt_id = ?",
                (*removed_ids, receipt_id),
            )

        # Patch existing items or add new ones
        for item in incoming_items:
            item_id = item.get("id")
            if item_id is not None and item_id in existing_ids:
                conn.execute(
                    "UPDATE items SET name=?, price_cents=?, product_id=?, category=? WHERE id=? AND receipt_id=?",
                    (item.get("name"),
                     _dollars_to_cents(item.get("price")),
                     item.get("productId"), item.get("category"),
                     item_id, receipt_id),
                )
            else:
                conn.execute(
                    "INSERT INTO items (receipt_id, name, price_cents, product_id, category) VALUES (?, ?, ?, ?, ?)",
                    (receipt_id, item.get("name"),
                     _dollars_to_cents(item.get("price")),
                     item.get("productId"), item.get("category")),
                )
    return get_receipt(receipt_id)


def list_receipts() -> list[dict]:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM receipts ORDER BY id DESC").fetchall()
        results = []
        for row in rows:
            items = conn.execute(
                "SELECT * FROM items WHERE receipt_id = ? ORDER BY id", (row["id"],)
            ).fetchall()
            results.append(_row_to_receipt(row, items))
        return results


def delete_receipt(receipt_id: int) -> bool:
    with get_db() as conn:
        cursor = conn.execute("DELETE FROM receipts WHERE id = ?", (receipt_id,))
        return cursor.rowcount > 0


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
