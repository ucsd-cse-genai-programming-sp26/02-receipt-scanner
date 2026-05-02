"""LLM-based item categorizer."""

import json
import os

from openai import OpenAI

CATEGORY_OPTIONS = [
    "Groceries",
    "Beverages",
    "Dairy",
    "Snacks",
    "Personal Care",
    "Household",
    "Electronics",
    "Clothing",
    "Dining",
    "Entertainment",
    "Other",
]

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

CATEGORIZATION_PROMPT = """Classify receipt items into spending categories.

Rules:
- Return JSON only as: {"categories": ["Category", ...]}
- Output one category per input item in the same order
- Allowed categories only: Groceries, Beverages, Dairy, Snacks, Personal Care, Household, Electronics, Clothing, Dining, Entertainment, Other
- If uncertain, choose Other
"""


def categorize_items(items: list[dict]) -> list[dict]:
    """Assign categories to items with a single LLM call."""
    if not items:
        return items

    uncategorized_indices = [
        i for i, item in enumerate(items) if not item.get("category") or item.get("category") == "Other"
    ]
    if not uncategorized_indices:
        return items

    names = [items[i].get("name") or "" for i in uncategorized_indices]

    # Keep app functional without an API key by falling back to "Other".
    if not client.api_key:
        for idx in uncategorized_indices:
            items[idx]["category"] = items[idx].get("category") or "Other"
        return items

    try:
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": CATEGORIZATION_PROMPT},
                {"role": "user", "content": json.dumps({"items": names})},
            ],
            max_tokens=300,
        )
        raw = response.choices[0].message.content.strip()
        parsed = json.loads(raw)
        predicted = parsed.get("categories", [])
    except Exception:
        predicted = []

    for local_i, item_idx in enumerate(uncategorized_indices):
        category = predicted[local_i] if local_i < len(predicted) else "Other"
        if category not in CATEGORY_OPTIONS:
            category = "Other"
        items[item_idx]["category"] = category

    return items
