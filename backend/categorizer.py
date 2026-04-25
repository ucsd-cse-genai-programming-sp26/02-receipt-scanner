"""
Keyword-based item categorizer.

Maps item names to categories using keyword matching.
Designed to be easily replaceable with an LLM-based categorizer later.
"""

CATEGORY_KEYWORDS = {
    "Groceries": [
        "apple", "banana", "orange", "grape", "berry", "lemon", "lime", "mango",
        "peach", "pear", "melon", "avocado", "tomato", "potato", "onion", "garlic",
        "carrot", "broccoli", "lettuce", "spinach", "celery", "pepper", "corn",
        "cucumber", "mushroom", "fruit", "vegetable", "veggie", "produce", "organic",
        "egg", "milk", "cheese", "yogurt", "butter", "cream", "bread", "flour",
        "sugar", "rice", "pasta", "cereal", "oat", "granola", "meat", "chicken",
        "beef", "pork", "fish", "salmon", "tuna", "shrimp", "turkey", "sausage",
        "bacon", "ham", "steak", "ground", "deli",
    ],
    "Beverages": [
        "water", "juice", "soda", "cola", "pepsi", "coke", "sprite", "tea",
        "coffee", "latte", "espresso", "cappuccino", "beer", "wine", "liquor",
        "vodka", "whiskey", "rum", "gin", "champagne", "drink", "smoothie",
        "lemonade", "kombucha", "energy drink", "gatorade",
    ],
    "Snacks": [
        "chip", "chips", "cracker", "cookie", "candy", "chocolate", "gum",
        "popcorn", "pretzel", "nut", "trail mix", "granola bar", "snack",
        "jerky", "brownie", "cake", "donut", "pastry", "muffin", "ice cream",
    ],
    "Household": [
        "paper towel", "toilet paper", "tissue", "napkin", "trash bag", "garbage",
        "detergent", "soap", "cleaner", "sponge", "bleach", "wipe", "foil",
        "plastic wrap", "bag", "battery", "bulb", "candle", "air freshener",
    ],
    "Personal Care": [
        "shampoo", "conditioner", "body wash", "lotion", "deodorant", "toothpaste",
        "toothbrush", "floss", "razor", "shaving", "sunscreen", "lip balm",
        "makeup", "cosmetic", "perfume", "cologne", "hand sanitizer",
    ],
    "Health": [
        "vitamin", "supplement", "medicine", "tylenol", "advil", "ibuprofen",
        "aspirin", "bandage", "first aid", "antacid", "allergy", "cold",
        "cough", "prescription", "pharmacy",
    ],
    "Restaurant": [
        "burger", "pizza", "sandwich", "wrap", "taco", "burrito", "fries",
        "salad", "soup", "appetizer", "entree", "dessert", "combo", "meal",
        "side", "dine", "takeout", "delivery",
    ],
    "Electronics": [
        "charger", "cable", "adapter", "headphone", "earphone", "speaker",
        "phone", "tablet", "laptop", "computer", "usb", "hdmi", "mouse",
        "keyboard", "monitor", "printer",
    ],
    "Clothing": [
        "shirt", "pants", "jeans", "jacket", "coat", "dress", "skirt",
        "shoes", "boots", "socks", "underwear", "hat", "scarf", "gloves",
        "belt", "tie", "blouse",
    ],
}

DEFAULT_CATEGORY = "Other"


def categorize_item(item_name: str) -> str:
    """Categorize an item name using keyword matching."""
    if not item_name:
        return DEFAULT_CATEGORY
    name_lower = item_name.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        for keyword in keywords:
            if keyword in name_lower:
                return category
    return DEFAULT_CATEGORY


def categorize_items(items: list[dict]) -> list[dict]:
    """Add a category to each item that doesn't already have one."""
    for item in items:
        if not item.get("category"):
            item["category"] = categorize_item(item.get("name", ""))
    return items
