import argparse
import base64
import io
import json
import os
from pathlib import Path

from openai import OpenAI
from PIL import Image
from pillow_heif import register_heif_opener

from categorizer import CATEGORY_OPTIONS, categorize_items

register_heif_opener()

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".heic", ".heif", ".webp"}

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


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def default_images_dir() -> Path:
    return repo_root() / "document_scanner_photos"


def default_annotations_path() -> Path:
    return repo_root() / "backend" / "category_annotations.json"


def default_predictions_path() -> Path:
    return repo_root() / "backend" / "category_predictions.json"


def default_report_path() -> Path:
    return repo_root() / "backend" / "category_eval_report.json"


def list_images(images_dir: Path) -> list[Path]:
    if not images_dir.exists():
        raise FileNotFoundError(f"Image directory not found: {images_dir}")
    images = [
        p for p in sorted(images_dir.rglob("*")) if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
    ]
    if not images:
        raise ValueError(f"No images found in {images_dir}")
    return images


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def to_data_url(image_path: Path) -> str:
    image = Image.open(image_path)
    if image.mode not in ("RGB", "L"):
        image = image.convert("RGB")
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{b64}"


def extract_receipt_items(client: OpenAI, image_path: Path, model: str) -> list[dict]:
    data_url = to_data_url(image_path)
    response = client.chat.completions.create(
        model=model,
        temperature=0,
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
    )

    raw_text = (response.choices[0].message.content or "").strip()
    if raw_text.startswith("```"):
        raw_text = raw_text.split("\n", 1)[1] if "\n" in raw_text else raw_text[3:]
        if raw_text.endswith("```"):
            raw_text = raw_text[:-3].strip()

    parsed = json.loads(raw_text)
    items = []
    for item in parsed.get("items", []):
        name = (item.get("name") or "").strip()
        if not name:
            continue
        items.append(
            {
                "name": name,
                "price": item.get("price", 0),
                "productId": item.get("productId"),
                "category": None,
            }
        )
    return items


def predict_categories(item_names: list[str]) -> list[str]:
    items = [{"name": n, "category": None} for n in item_names]
    categorized = categorize_items(items)
    out = []
    for item in categorized:
        cat = item.get("category") or "Other"
        if cat not in CATEGORY_OPTIONS:
            cat = "Other"
        out.append(cat)
    return out


def normalize_category(cat: str) -> str:
    if cat in CATEGORY_OPTIONS:
        return cat
    return "Other"


def compute_metrics(y_true: list[str], y_pred: list[str], labels: list[str]) -> dict:
    if len(y_true) != len(y_pred):
        raise ValueError("y_true and y_pred must have same length")

    total = len(y_true)
    correct = sum(1 for t, p in zip(y_true, y_pred) if t == p)
    accuracy = (correct / total) if total else 0.0

    per_class = {}
    total_tp = total_fp = total_fn = 0

    for label in labels:
        tp = sum(1 for t, p in zip(y_true, y_pred) if t == label and p == label)
        fp = sum(1 for t, p in zip(y_true, y_pred) if t != label and p == label)
        fn = sum(1 for t, p in zip(y_true, y_pred) if t == label and p != label)
        support = sum(1 for t in y_true if t == label)

        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0

        per_class[label] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "support": support,
        }

        total_tp += tp
        total_fp += fp
        total_fn += fn

    macro_precision = sum(x["precision"] for x in per_class.values()) / len(labels)
    macro_recall = sum(x["recall"] for x in per_class.values()) / len(labels)
    macro_f1 = sum(x["f1"] for x in per_class.values()) / len(labels)

    micro_precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) else 0.0
    micro_recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) else 0.0
    micro_f1 = (
        2 * micro_precision * micro_recall / (micro_precision + micro_recall)
        if (micro_precision + micro_recall)
        else 0.0
    )

    return {
        "count": total,
        "accuracy": accuracy,
        "micro": {
            "precision": micro_precision,
            "recall": micro_recall,
            "f1": micro_f1,
        },
        "macro": {
            "precision": macro_precision,
            "recall": macro_recall,
            "f1": macro_f1,
        },
        "per_class": per_class,
    }


def annotate(args: argparse.Namespace) -> None:
    images = list_images(args.images_dir)
    annotations = load_json(args.annotations_file)
    records = annotations.get("records", {})
    predictions_payload = load_json(args.predictions_file)
    predictions = predictions_payload.get("records", {})

    client = None
    if args.seed_from_model:
        if not os.environ.get("OPENAI_API_KEY"):
            print("[WARN] OPENAI_API_KEY not set; cannot seed from model extraction.")
        else:
            client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    print(f"Annotating category labels for {len(images)} images from {args.images_dir}")
    print("For each image: [a]=accept all predictions, [e]=edit, [s]=skip\n")

    for image_path in images:
        rel = str(image_path.relative_to(repo_root()))
        if rel in records and not args.overwrite:
            continue

        predicted_items = []
        if rel in predictions and not args.refresh_predictions:
            predicted_items = predictions[rel].get("items", [])
        elif client is not None:
            extracted_items = extract_receipt_items(client, image_path, args.extract_model)
            names = [x["name"] for x in extracted_items]
            cats = predict_categories(names)
            predicted_items = [
                {
                    "name": n,
                    "predicted_category": c,
                }
                for n, c in zip(names, cats)
            ]
            predictions[rel] = {"items": predicted_items}
            predictions_payload["records"] = predictions
            save_json(args.predictions_file, predictions_payload)

        print("=" * 80)
        print(f"Image: {rel}")
        if not predicted_items:
            print("No predicted items available. Skip this image or rerun with OPENAI_API_KEY.")
            action = input("Action [s]kip: ").strip().lower() or "s"
            if action == "s":
                print("Skipped.\n")
                continue

        for idx, item in enumerate(predicted_items, start=1):
            print(f"{idx:2d}. {item['name']}  ->  {item['predicted_category']}")

        action = input("Action [a/e/s] (default a): ").strip().lower() or "a"
        if action == "s":
            print("Skipped.\n")
            continue

        annotated_items = []
        if action == "a":
            for item in predicted_items:
                annotated_items.append(
                    {
                        "name": item["name"],
                        "predicted_category": normalize_category(item["predicted_category"]),
                        "ground_truth_category": normalize_category(item["predicted_category"]),
                    }
                )
        else:
            print("Allowed categories:")
            print(", ".join(CATEGORY_OPTIONS))
            for item in predicted_items:
                default_cat = normalize_category(item.get("predicted_category", "Other"))
                while True:
                    value = input(f"{item['name']} [{default_cat}]: ").strip()
                    chosen = default_cat if not value else value
                    if chosen in CATEGORY_OPTIONS:
                        annotated_items.append(
                            {
                                "name": item["name"],
                                "predicted_category": default_cat,
                                "ground_truth_category": chosen,
                            }
                        )
                        break
                    print("Invalid category. Use one of the allowed categories.")

        records[rel] = {"items": annotated_items}
        annotations["records"] = records
        save_json(args.annotations_file, annotations)
        print(f"Saved {len(annotated_items)} labeled items.\n")

    print(f"Done. Saved annotations to {args.annotations_file}")


def evaluate(args: argparse.Namespace) -> None:
    annotations = load_json(args.annotations_file)
    records = annotations.get("records", {})
    if not records:
        raise ValueError("No category annotations found. Run annotate mode first.")

    predictions_payload = load_json(args.predictions_file)
    predictions = predictions_payload.get("records", {})

    y_true = []
    y_pred = []
    per_image = []

    for rel, record in sorted(records.items()):
        items = record.get("items", [])
        names = [x.get("name", "") for x in items if x.get("name")]
        truths = [normalize_category(x.get("ground_truth_category", "Other")) for x in items if x.get("name")]
        if not names:
            continue

        if rel in predictions and not args.refresh_predictions:
            pred_items = predictions[rel].get("items", [])
            pred_map = {x.get("name"): normalize_category(x.get("predicted_category", "Other")) for x in pred_items}
            preds = [pred_map.get(name, "Other") for name in names]
        else:
            preds = predict_categories(names)
            predictions[rel] = {
                "items": [
                    {"name": n, "predicted_category": normalize_category(p)} for n, p in zip(names, preds)
                ]
            }
            predictions_payload["records"] = predictions
            save_json(args.predictions_file, predictions_payload)

        image_correct = sum(1 for t, p in zip(truths, preds) if t == p)
        image_acc = image_correct / len(truths)
        per_image.append({"image": rel, "count": len(truths), "accuracy": image_acc})

        y_true.extend(truths)
        y_pred.extend([normalize_category(x) for x in preds])

        print(f"{rel}: accuracy={image_acc:.3f} ({image_correct}/{len(truths)})")

    if not y_true:
        raise ValueError("No labeled items found in annotations.")

    metrics = compute_metrics(y_true, y_pred, CATEGORY_OPTIONS)

    report = {
        "items_evaluated": metrics["count"],
        "accuracy": metrics["accuracy"],
        "micro": metrics["micro"],
        "macro": metrics["macro"],
        "per_class": metrics["per_class"],
        "per_image": per_image,
    }

    save_json(args.output_file, report)

    print("\n=== Aggregate Category Metrics ===")
    print(f"Items: {report['items_evaluated']}")
    print(f"Accuracy: {report['accuracy']:.3f}")
    print(
        f"Micro -> P={report['micro']['precision']:.3f} R={report['micro']['recall']:.3f} F1={report['micro']['f1']:.3f}"
    )
    print(
        f"Macro -> P={report['macro']['precision']:.3f} R={report['macro']['recall']:.3f} F1={report['macro']['f1']:.3f}"
    )
    print(f"Saved report to {args.output_file}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Category evaluation utility")
    sub = parser.add_subparsers(dest="command", required=True)

    p_annotate = sub.add_parser("annotate", help="Annotate item categories per image")
    p_annotate.add_argument(
        "--images-dir",
        type=Path,
        default=default_images_dir(),
        help="Directory containing receipt images",
    )
    p_annotate.add_argument(
        "--annotations-file",
        type=Path,
        default=default_annotations_path(),
        help="Path to category annotations JSON",
    )
    p_annotate.add_argument(
        "--predictions-file",
        type=Path,
        default=default_predictions_path(),
        help="Path to cached category predictions JSON",
    )
    p_annotate.add_argument(
        "--overwrite",
        action="store_true",
        help="Re-annotate images that already have labels",
    )
    p_annotate.add_argument(
        "--refresh-predictions",
        action="store_true",
        help="Ignore cached predictions and regenerate",
    )
    p_annotate.set_defaults(seed_from_model=True)
    p_annotate.add_argument(
        "--no-seed-from-model",
        dest="seed_from_model",
        action="store_false",
        help="Disable model seeding in annotate mode",
    )
    p_annotate.add_argument(
        "--extract-model",
        default="gpt-4o",
        help="Vision model for extracting receipt items",
    )

    p_eval = sub.add_parser("evaluate", help="Evaluate category predictions against annotations")
    p_eval.add_argument(
        "--annotations-file",
        type=Path,
        default=default_annotations_path(),
        help="Path to category annotations JSON",
    )
    p_eval.add_argument(
        "--predictions-file",
        type=Path,
        default=default_predictions_path(),
        help="Path to cached category predictions JSON",
    )
    p_eval.add_argument(
        "--refresh-predictions",
        action="store_true",
        help="Ignore cached predictions and rerun category model",
    )
    p_eval.add_argument(
        "--output-file",
        type=Path,
        default=default_report_path(),
        help="Path to save category evaluation report JSON",
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "annotate":
        annotate(args)
    elif args.command == "evaluate":
        evaluate(args)


if __name__ == "__main__":
    main()
