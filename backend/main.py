import os
import io
import json
import base64
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image
from pillow_heif import register_heif_opener
from openai import OpenAI
from database import init_db, save_receipt, get_receipt, list_receipts, delete_receipt, update_receipt
from categorizer import categorize_items

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


@app.on_event("startup")
def startup():
    init_db()


def image_to_base64_data_url(image: Image.Image) -> str:
    """Convert a PIL Image to a base64 data URL for the OpenAI API."""
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{b64}"


@app.post("/api/scan")
async def scan_receipt(file: UploadFile = File(...)):
    """Upload a receipt image and get structured data back via GPT-4o vision."""
    if not client.api_key:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY not configured")

    contents = await file.read()
    try:
        image = Image.open(io.BytesIO(contents))
    except Exception:
        raise HTTPException(status_code=400, detail="Unsupported or corrupt image file")

    # Convert to RGB if needed (e.g. RGBA, palette modes)
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
                        {"type": "image_url", "image_url": {"url": data_url, "detail": "high"}},
                    ],
                }
            ],
            max_tokens=2000,
            temperature=0,
        )
        raw_text = response.choices[0].message.content.strip()

        # Strip markdown code fences if GPT adds them
        if raw_text.startswith("```"):
            raw_text = raw_text.split("\n", 1)[1] if "\n" in raw_text else raw_text[3:]
            if raw_text.endswith("```"):
                raw_text = raw_text[:-3].strip()

        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail=f"GPT-4o returned invalid JSON: {raw_text[:200]}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OpenAI API error: {str(e)}")

    # Ensure items have the expected shape
    items = []
    for item in parsed.get("items", []):
        items.append({
            "id": None,
            "name": item.get("name", ""),
            "price": item.get("price", 0),
            "productId": item.get("productId"),
        })

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
async def api_list_receipts():
    return list_receipts()


@app.post("/api/receipts")
async def api_save_receipt(receipt: dict):
    saved = save_receipt(receipt)
    return saved


@app.get("/api/receipts/{receipt_id}")
async def api_get_receipt(receipt_id: int):
    result = get_receipt(receipt_id)
    if not result:
        raise HTTPException(status_code=404, detail="Receipt not found")
    return result


@app.put("/api/receipts/{receipt_id}")
async def api_update_receipt(receipt_id: int, receipt: dict):
    result = update_receipt(receipt_id, receipt)
    if not result:
        raise HTTPException(status_code=404, detail="Receipt not found")
    return result


@app.delete("/api/receipts/{receipt_id}")
async def api_delete_receipt(receipt_id: int):
    if not delete_receipt(receipt_id):
        raise HTTPException(status_code=404, detail="Receipt not found")
    return {"ok": True}


@app.get("/api/stats/categories")
async def api_category_stats():
    """Get spending totals grouped by category, optionally filtered by date range."""
    receipts = list_receipts()
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
        categories.append({
            "category": cat,
            "totalSpent": category_totals[cat],
            "itemCount": category_counts[cat],
        })
    return categories
