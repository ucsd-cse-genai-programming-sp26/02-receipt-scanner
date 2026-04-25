import os
import pytest
from database import init_db, save_receipt, get_receipt, list_receipts, delete_receipt, update_receipt, DB_PATH

import database


@pytest.fixture(autouse=True)
def fresh_db(tmp_path):
    """Use a fresh temporary database for each test."""
    test_db = str(tmp_path / "test.db")
    database.DB_PATH = test_db
    init_db()
    yield
    database.DB_PATH = DB_PATH


def make_receipt(**overrides):
    base = {
        "storeName": "Test Store",
        "date": "04/16/2026",
        "subtotal": 10.00,
        "tax": 0.80,
        "tip": 2.00,
        "total": 12.80,
        "rawText": "raw ocr text",
        "scannedAt": "2026-04-16T12:00:00Z",
        "items": [
            {"name": "Apple", "price": 3.50, "productId": "SKU001"},
            {"name": "Bread", "price": 6.50, "productId": None},
        ],
    }
    base.update(overrides)
    return base


# ──────────────────────────────────────────────
# CREATE
# ──────────────────────────────────────────────

class TestCreateReceipt:
    def test_save_returns_receipt_with_id(self):
        result = save_receipt(make_receipt())
        assert result["id"] is not None
        assert isinstance(result["id"], int)

    def test_save_persists_receipt_fields(self):
        result = save_receipt(make_receipt())
        assert result["storeName"] == "Test Store"
        assert result["date"] == "04/16/2026"
        assert result["subtotal"] == 10.00
        assert result["tax"] == 0.80
        assert result["tip"] == 2.00
        assert result["total"] == 12.80
        assert result["rawText"] == "raw ocr text"
        assert result["scannedAt"] == "2026-04-16T12:00:00Z"

    def test_save_persists_items(self):
        result = save_receipt(make_receipt())
        assert len(result["items"]) == 2
        assert result["items"][0]["name"] == "Apple"
        assert result["items"][0]["price"] == 3.50
        assert result["items"][0]["productId"] == "SKU001"
        assert result["items"][1]["name"] == "Bread"
        assert result["items"][1]["price"] == 6.50

    def test_save_items_get_unique_ids(self):
        result = save_receipt(make_receipt())
        ids = [item["id"] for item in result["items"]]
        assert len(set(ids)) == len(ids)

    def test_save_with_no_items(self):
        result = save_receipt(make_receipt(items=[]))
        assert result["items"] == []

    def test_save_with_null_fields(self):
        result = save_receipt(make_receipt(
            subtotal=None, tax=None, tip=None, total=None, date=None
        ))
        assert result["subtotal"] is None
        assert result["tax"] is None
        assert result["tip"] is None
        assert result["total"] is None
        assert result["date"] is None

    def test_save_stores_cents_correctly(self):
        """Verify dollar-to-cent conversion is precise for common values."""
        result = save_receipt(make_receipt(total=19.99, tax=1.07))
        assert result["total"] == 19.99
        assert result["tax"] == 1.07


# ──────────────────────────────────────────────
# READ
# ──────────────────────────────────────────────

class TestReadReceipt:
    def test_get_by_id(self):
        saved = save_receipt(make_receipt())
        result = get_receipt(saved["id"])
        assert result is not None
        assert result["id"] == saved["id"]
        assert result["storeName"] == "Test Store"

    def test_get_nonexistent_returns_none(self):
        assert get_receipt(999) is None

    def test_list_returns_all_receipts(self):
        save_receipt(make_receipt(storeName="Store A"))
        save_receipt(make_receipt(storeName="Store B"))
        results = list_receipts()
        assert len(results) == 2

    def test_list_returns_newest_first(self):
        save_receipt(make_receipt(storeName="First"))
        save_receipt(make_receipt(storeName="Second"))
        results = list_receipts()
        assert results[0]["storeName"] == "Second"
        assert results[1]["storeName"] == "First"

    def test_list_empty_database(self):
        assert list_receipts() == []

    def test_get_includes_all_items(self):
        saved = save_receipt(make_receipt())
        result = get_receipt(saved["id"])
        assert len(result["items"]) == 2


# ──────────────────────────────────────────────
# DELETE
# ──────────────────────────────────────────────

class TestDeleteReceipt:
    def test_delete_existing(self):
        saved = save_receipt(make_receipt())
        assert delete_receipt(saved["id"]) is True
        assert get_receipt(saved["id"]) is None

    def test_delete_nonexistent_returns_false(self):
        assert delete_receipt(999) is False

    def test_delete_cascades_to_items(self):
        saved = save_receipt(make_receipt())
        receipt_id = saved["id"]
        delete_receipt(receipt_id)
        result = get_receipt(receipt_id)
        assert result is None

    def test_delete_one_does_not_affect_others(self):
        r1 = save_receipt(make_receipt(storeName="Keep"))
        r2 = save_receipt(make_receipt(storeName="Delete"))
        delete_receipt(r2["id"])
        assert get_receipt(r1["id"]) is not None
        assert get_receipt(r2["id"]) is None


# ──────────────────────────────────────────────
# UPDATE — receipt fields
# ──────────────────────────────────────────────

class TestUpdateReceiptFields:
    def test_update_store_name(self):
        saved = save_receipt(make_receipt())
        result = update_receipt(saved["id"], make_receipt(storeName="New Name"))
        assert result["storeName"] == "New Name"

    def test_update_financial_fields(self):
        saved = save_receipt(make_receipt())
        result = update_receipt(saved["id"], make_receipt(
            subtotal=20.00, tax=1.60, tip=4.00, total=25.60
        ))
        assert result["subtotal"] == 20.00
        assert result["tax"] == 1.60
        assert result["tip"] == 4.00
        assert result["total"] == 25.60

    def test_update_nonexistent_returns_none(self):
        assert update_receipt(999, make_receipt()) is None

    def test_update_preserves_receipt_id(self):
        saved = save_receipt(make_receipt())
        result = update_receipt(saved["id"], make_receipt(storeName="Changed"))
        assert result["id"] == saved["id"]


# ──────────────────────────────────────────────
# UPDATE — item PATCH (existing items)
# ──────────────────────────────────────────────

class TestUpdateItemPatch:
    def test_patch_item_name(self):
        saved = save_receipt(make_receipt())
        item_id = saved["items"][0]["id"]
        updated_items = [
            {"id": item_id, "name": "Green Apple", "price": 3.50, "productId": "SKU001"},
            saved["items"][1],
        ]
        result = update_receipt(saved["id"], make_receipt(items=updated_items))
        patched = next(i for i in result["items"] if i["id"] == item_id)
        assert patched["name"] == "Green Apple"

    def test_patch_item_price(self):
        saved = save_receipt(make_receipt())
        item_id = saved["items"][0]["id"]
        updated_items = [
            {"id": item_id, "name": "Apple", "price": 4.99, "productId": "SKU001"},
            saved["items"][1],
        ]
        result = update_receipt(saved["id"], make_receipt(items=updated_items))
        patched = next(i for i in result["items"] if i["id"] == item_id)
        assert patched["price"] == 4.99

    def test_patch_preserves_item_id(self):
        saved = save_receipt(make_receipt())
        original_ids = [i["id"] for i in saved["items"]]
        result = update_receipt(saved["id"], make_receipt(items=saved["items"]))
        updated_ids = [i["id"] for i in result["items"]]
        assert original_ids == updated_ids

    def test_patch_item_product_id(self):
        saved = save_receipt(make_receipt())
        item = saved["items"][1]
        item["productId"] = "NEW_SKU"
        result = update_receipt(saved["id"], make_receipt(items=saved["items"]))
        patched = next(i for i in result["items"] if i["id"] == item["id"])
        assert patched["productId"] == "NEW_SKU"


# ──────────────────────────────────────────────
# UPDATE — item ADD (new items)
# ──────────────────────────────────────────────

class TestUpdateItemAdd:
    def test_add_new_item(self):
        saved = save_receipt(make_receipt())
        new_items = saved["items"] + [
            {"name": "Milk", "price": 2.00, "productId": None},
        ]
        result = update_receipt(saved["id"], make_receipt(items=new_items))
        assert len(result["items"]) == 3
        names = [i["name"] for i in result["items"]]
        assert "Milk" in names

    def test_add_item_gets_new_id(self):
        saved = save_receipt(make_receipt())
        existing_ids = {i["id"] for i in saved["items"]}
        new_items = saved["items"] + [
            {"name": "Milk", "price": 2.00, "productId": None},
        ]
        result = update_receipt(saved["id"], make_receipt(items=new_items))
        new_item = next(i for i in result["items"] if i["name"] == "Milk")
        assert new_item["id"] not in existing_ids

    def test_add_item_with_null_id_treated_as_new(self):
        saved = save_receipt(make_receipt())
        new_items = saved["items"] + [
            {"id": None, "name": "Eggs", "price": 5.00, "productId": None},
        ]
        result = update_receipt(saved["id"], make_receipt(items=new_items))
        assert len(result["items"]) == 3

    def test_add_does_not_affect_existing_items(self):
        saved = save_receipt(make_receipt())
        original_items = saved["items"][:]
        new_items = saved["items"] + [
            {"name": "Juice", "price": 3.00, "productId": None},
        ]
        result = update_receipt(saved["id"], make_receipt(items=new_items))
        for orig in original_items:
            found = next(i for i in result["items"] if i["id"] == orig["id"])
            assert found["name"] == orig["name"]
            assert found["price"] == orig["price"]


# ──────────────────────────────────────────────
# UPDATE — item DELETE (removed items)
# ──────────────────────────────────────────────

class TestUpdateItemDelete:
    def test_remove_item_by_omission(self):
        saved = save_receipt(make_receipt())
        kept_item = saved["items"][0]
        result = update_receipt(saved["id"], make_receipt(items=[kept_item]))
        assert len(result["items"]) == 1
        assert result["items"][0]["id"] == kept_item["id"]

    def test_remove_all_items(self):
        saved = save_receipt(make_receipt())
        result = update_receipt(saved["id"], make_receipt(items=[]))
        assert result["items"] == []

    def test_remove_does_not_affect_kept_items(self):
        saved = save_receipt(make_receipt())
        kept = saved["items"][1]
        result = update_receipt(saved["id"], make_receipt(items=[kept]))
        assert result["items"][0]["id"] == kept["id"]
        assert result["items"][0]["name"] == kept["name"]
        assert result["items"][0]["price"] == kept["price"]


# ──────────────────────────────────────────────
# UPDATE — combined operations
# ──────────────────────────────────────────────

class TestUpdateCombined:
    def test_patch_add_delete_in_one_call(self):
        """Patch Apple, delete Bread, add Milk — all in one PUT."""
        saved = save_receipt(make_receipt())
        apple_id = saved["items"][0]["id"]
        items = [
            {"id": apple_id, "name": "Red Apple", "price": 4.00, "productId": "SKU001"},
            {"name": "Milk", "price": 2.50, "productId": None},
        ]
        result = update_receipt(saved["id"], make_receipt(items=items))

        assert len(result["items"]) == 2
        patched = next(i for i in result["items"] if i["id"] == apple_id)
        assert patched["name"] == "Red Apple"
        assert patched["price"] == 4.00
        added = next(i for i in result["items"] if i["name"] == "Milk")
        assert added["price"] == 2.50
        names = [i["name"] for i in result["items"]]
        assert "Bread" not in names

    def test_multiple_updates_are_idempotent(self):
        """Running the same update twice should produce the same result."""
        saved = save_receipt(make_receipt())
        updated_data = make_receipt(storeName="Updated", items=saved["items"])
        result1 = update_receipt(saved["id"], updated_data)
        result2 = update_receipt(saved["id"], updated_data)
        assert result1["storeName"] == result2["storeName"]
        assert len(result1["items"]) == len(result2["items"])
        for i1, i2 in zip(result1["items"], result2["items"]):
            assert i1["id"] == i2["id"]
            assert i1["name"] == i2["name"]
            assert i1["price"] == i2["price"]
