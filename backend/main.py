import base64
import io
import json
import os
from datetime import datetime

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from PIL import Image
from pillow_heif import register_heif_opener
from openai import OpenAI

from auth import (
    create_access_token,
    get_current_user,
    hash_password,
    validate_password_strength,
    verify_password,
)
from categorizer import categorize_items
from database import (
    create_user,
    delete_receipt,
    get_budgets,
    get_monthly_spend_by_category,
    get_receipt,
    get_user_by_username,
    init_db,
    list_receipts,
    save_receipt,
    update_receipt,
    upsert_budgets,
)

register_heif_opener()

app = FastAPI(title="Receipt Scanner API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

SCAN_PROMPT = """You are a receipt parser. Extract structured data from this receipt image.
Return ONLY valid JSON with this exact schema (no markdown, no code fences):
{
  "storeName": "string or null",
  "date": "string or null (e.g. 04/16/2026)",
  "items": [
    {"name": "string", "price": number, "productId": "string or null"}
  ],
  "subtotal": number or null,
  "tax": number or null,
  "tip": number or null,
  "total": number or null
}
Rules:
- All prices are in dollars as floats (e.g. 3.49, not 349)
- Include every line item you can read
- If a field is unreadable, use null
- Do NOT include payment method lines, change due, or card numbers as items"""


class AuthPayload(BaseModel):
    username: str
    password: str


class BudgetPayload(BaseModel):
    budgets: dict[str, float]


@app.on_event("startup")
def startup():
    init_db()


def _validate_month(month: str) -> None:
    try:
        datetime.strptime(month, "%Y-%m")
    except ValueError:
        raise HTTPException(status_code=400, detail="month must be in YYYY-MM format")


def image_to_base64_data_url(image: Image.Image) -> str:
    """Convert a PIL Image to a base64 data URL for the OpenAI API."""
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{b64}"


@app.post("/api/auth/register")
async def register(payload: AuthPayload):
    username = payload.username.strip().lower()
    if len(username) < 3:
        raise HTTPException(status_code=400, detail="Username must be at least 3 characters")

    validate_password_strength(payload.password)
    created = create_user(username, hash_password(payload.password))
    if not created:
        raise HTTPException(status_code=409, detail="Username already exists")

    token = create_access_token(created["id"], created["username"])
    return {
        "accessToken": token,
        "user": {"id": created["id"], "username": created["username"]},
    }


@app.post("/api/auth/login")
async def login(payload: AuthPayload):
    username = payload.username.strip().lower()
    user = get_user_by_username(username)
    if not user or not verify_password(payload.password, user["passwordHash"]):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    token = create_access_token(user["id"], user["username"])
    return {
        "accessToken": token,
        "user": {"id": user["id"], "username": user["username"]},
    }


@app.get("/api/auth/me")
async def me(current_user: dict = Depends(get_current_user)):
    return {"id": current_user["id"], "username": current_user["username"]}


@app.post("/api/scan")
async def scan_receipt(
    file: UploadFile = File(...), current_user: dict = Depends(get_current_user)
):
    """Upload a receipt image and get structured data back via GPT-4o vision."""
    if not client.api_key:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY not configured")

    contents = await file.read()
    try:
        image = Image.open(io.BytesIO(contents))
    except Exception:
        raise HTTPException(status_code=400, detail="Unsupported or corrupt image file")

    if image.mode not in ("RGB", "L"):
        image = image.convert("RGB")

    data_url = image_to_base64_data_url(image)

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": SCAN_PROMPT},
                        {
                            "type": "image_url",
                            "image_url": {"url": data_url, "detail": "high"},
                        },
                    ],
                }
            ],
            max_tokens=2000,
            temperature=0,
        )
        raw_text = response.choices[0].message.content.strip()

        if raw_text.startswith("```"):
            raw_text = raw_text.split("\n", 1)[1] if "\n" in raw_text else raw_text[3:]
            if raw_text.endswith("```"):
                raw_text = raw_text[:-3].strip()

        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail=f"GPT-4o returned invalid JSON: {raw_text[:200]}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OpenAI API error: {str(e)}")

    items = []
    for item in parsed.get("items", []):
        items.append(
            {
                "id": None,
                "name": item.get("name", ""),
                "price": item.get("price", 0),
                "productId": item.get("productId"),
            }
        )

    result = {
        "storeName": parsed.get("storeName"),
        "date": parsed.get("date"),
        "items": categorize_items(items),
        "subtotal": parsed.get("subtotal"),
        "tax": parsed.get("tax"),
        "tip": parsed.get("tip"),
        "total": parsed.get("total"),
        "rawText": raw_text,
    }
    return result


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/receipts")
async def api_list_receipts(current_user: dict = Depends(get_current_user)):
    return list_receipts(user_id=current_user["id"])


@app.post("/api/receipts")
async def api_save_receipt(receipt: dict, current_user: dict = Depends(get_current_user)):
    saved = save_receipt(receipt, user_id=current_user["id"])
    return saved


@app.get("/api/receipts/{receipt_id}")
async def api_get_receipt(receipt_id: int, current_user: dict = Depends(get_current_user)):
    result = get_receipt(receipt_id, user_id=current_user["id"])
    if not result:
        raise HTTPException(status_code=404, detail="Receipt not found")
    return result


@app.put("/api/receipts/{receipt_id}")
async def api_update_receipt(
    receipt_id: int, receipt: dict, current_user: dict = Depends(get_current_user)
):
    result = update_receipt(receipt_id, receipt, user_id=current_user["id"])
    if not result:
        raise HTTPException(status_code=404, detail="Receipt not found")
    return result


@app.delete("/api/receipts/{receipt_id}")
async def api_delete_receipt(receipt_id: int, current_user: dict = Depends(get_current_user)):
    if not delete_receipt(receipt_id, user_id=current_user["id"]):
        raise HTTPException(status_code=404, detail="Receipt not found")
    return {"ok": True}


@app.get("/api/stats/categories")
async def api_category_stats(current_user: dict = Depends(get_current_user)):
    receipts = list_receipts(user_id=current_user["id"])
    category_totals = {}
    category_counts = {}
    for r in receipts:
        for item in r.get("items", []):
            cat = item.get("category") or "Other"
            price = item.get("price") or 0
            category_totals[cat] = round(category_totals.get(cat, 0) + price, 2)
            category_counts[cat] = category_counts.get(cat, 0) + 1
    categories = []
    for cat in sorted(category_totals.keys()):
        categories.append(
            {
                "category": cat,
                "totalSpent": category_totals[cat],
                "itemCount": category_counts[cat],
            }
        )
    return categories


@app.get("/api/budgets/{month}")
async def api_get_budgets(month: str, current_user: dict = Depends(get_current_user)):
    _validate_month(month)
    return {"month": month, "budgets": get_budgets(current_user["id"], month)}


@app.put("/api/budgets/{month}")
async def api_put_budgets(
    month: str, payload: BudgetPayload, current_user: dict = Depends(get_current_user)
):
    _validate_month(month)
    clean = {
        category: float(value)
        for category, value in payload.budgets.items()
        if isinstance(value, (int, float)) and value >= 0
    }
    updated = upsert_budgets(current_user["id"], month, clean)
    return {"month": month, "budgets": updated}


@app.get("/api/stats/monthly-summary")
async def api_monthly_summary(month: str, current_user: dict = Depends(get_current_user)):
    _validate_month(month)
    spend = get_monthly_spend_by_category(current_user["id"], month)
    budgets = get_budgets(current_user["id"], month)

    categories = sorted(set(spend.keys()) | set(budgets.keys()))
    summary = []
    for category in categories:
        spent = round(spend.get(category, 0), 2)
        budget = round(budgets.get(category, 0), 2)
        pct = 100 if budget <= 0 and spent > 0 else 0
        if budget > 0:
            pct = round((spent / budget) * 100, 2)
        remaining = round(max(budget - spent, 0), 2)
        summary.append(
            {
                "category": category,
                "spent": spent,
                "budget": budget,
                "remaining": remaining,
                "percentUsed": pct,
                "satisfied": spent <= budget if budget > 0 else True,
            }
        )

    summary.sort(key=lambda row: row["spent"], reverse=True)
    totals = {
        "spent": round(sum(row["spent"] for row in summary), 2),
        "budget": round(sum(row["budget"] for row in summary), 2),
    }
    totals["remaining"] = round(max(totals["budget"] - totals["spent"], 0), 2)

    return {"month": month, "totals": totals, "categories": summary}
