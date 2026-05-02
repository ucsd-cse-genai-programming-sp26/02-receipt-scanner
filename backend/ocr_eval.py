import argparse
import base64
import io
import json
import os
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from openai import OpenAI
from PIL import Image
from pillow_heif import register_heif_opener

register_heif_opener()

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".heic", ".heif", ".webp"}

OCR_PROMPT = """You are an OCR engine for receipts.
Extract all visible receipt text in reading order.
Return only plain text with line breaks.
Do not add explanations.
"""


@dataclass
class MetricCounts:
    tp: int
    fp: int
    fn: int
    exact_match: bool


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def default_images_dir() -> Path:
    return repo_root() / "document_scanner_photos"


def default_annotations_path() -> Path:
    return repo_root() / "backend" / "ocr_annotations.json"


def default_predictions_path() -> Path:
    return repo_root() / "backend" / "ocr_predictions.json"


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


def tokenize(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9$%./:-]+", text.lower())


def metric_counts(ground_truth: str, prediction: str) -> MetricCounts:
    gt_tokens = tokenize(ground_truth)
    pred_tokens = tokenize(prediction)
    gt_counter = Counter(gt_tokens)
    pred_counter = Counter(pred_tokens)

    tp = sum(min(pred_counter[t], gt_counter[t]) for t in pred_counter)
    fp = sum(max(pred_counter[t] - gt_counter[t], 0) for t in pred_counter)
    fn = sum(max(gt_counter[t] - pred_counter[t], 0) for t in gt_counter)
    exact_match = " ".join(gt_tokens) == " ".join(pred_tokens)

    return MetricCounts(tp=tp, fp=fp, fn=fn, exact_match=exact_match)


def safe_div(n: float, d: float) -> float:
    return n / d if d else 0.0


def counts_to_scores(counts: MetricCounts) -> dict[str, float]:
    precision = safe_div(counts.tp, counts.tp + counts.fp)
    recall = safe_div(counts.tp, counts.tp + counts.fn)
    f1 = safe_div(2 * precision * recall, precision + recall)
    accuracy = safe_div(counts.tp, counts.tp + counts.fp + counts.fn)
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "accuracy": accuracy,
        "exact_match": 1.0 if counts.exact_match else 0.0,
    }


def to_data_url(image_path: Path) -> str:
    image = Image.open(image_path)
    if image.mode not in ("RGB", "L"):
        image = image.convert("RGB")
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{b64}"


def extract_text(client: OpenAI, image_path: Path, model: str) -> str:
    data_url = to_data_url(image_path)
    response = client.chat.completions.create(
        model=model,
        temperature=0,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": OCR_PROMPT},
                    {"type": "image_url", "image_url": {"url": data_url, "detail": "high"}},
                ],
            }
        ],
        max_tokens=3000,
    )
    return (response.choices[0].message.content or "").strip()


def annotate(args: argparse.Namespace) -> None:
    images = list_images(args.images_dir)
    annotations = load_json(args.annotations_file)
    records = annotations.get("records", {})
    predictions_payload = load_json(args.predictions_file)
    predictions = predictions_payload.get("predictions", {})

    client = None
    if args.seed_from_ocr:
        if not os.environ.get("OPENAI_API_KEY"):
            print("[WARN] OPENAI_API_KEY not set; continuing without OCR seed text.")
        else:
            client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    print(f"Annotating {len(images)} images from {args.images_dir}")
    print("Each example can start with OCR draft text.")
    print("Choose [k]eep draft, [e]dit draft, or [s]kip.")
    print("When editing, end input with a line containing only END.\n")

    for image_path in images:
        rel = str(image_path.relative_to(repo_root()))
        if rel in records and not args.overwrite:
            continue

        seed_text = ""
        if client is not None:
            if rel in predictions and not args.refresh_predictions:
                seed_text = predictions[rel]
            else:
                seed_text = extract_text(client, image_path, args.model)
                predictions[rel] = seed_text
                predictions_payload["predictions"] = predictions
                save_json(args.predictions_file, predictions_payload)

        print("=" * 80)
        print(f"Image: {rel}")
        if seed_text:
            print("\n--- OCR Draft Start ---")
            print(seed_text)
            print("--- OCR Draft End ---\n")
        else:
            print("No OCR draft available.")

        default_action = "k" if seed_text else "e"
        action = (
            input(f"Action [k/e/s] (default {default_action}): ").strip().lower()
            or default_action
        )

        if action == "s":
            print("Skipped.\n")
            continue

        if action == "k":
            text = seed_text.strip()
        else:
            print("Paste corrected ground-truth text. End with END on its own line.")
            lines: list[str] = []
            while True:
                line = input()
                if line.strip() == "END":
                    break
                lines.append(line)
            text = "\n".join(lines).strip()

        records[rel] = {"ground_truth_text": text}
        annotations["records"] = records
        save_json(args.annotations_file, annotations)
        print(f"Saved annotation ({len(text)} chars).\n")

    print(f"Done. Saved annotations to {args.annotations_file}")


def evaluate(args: argparse.Namespace) -> None:
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is required for evaluation.")

    annotations = load_json(args.annotations_file)
    records = annotations.get("records", {})
    if not records:
        raise ValueError("No annotations found. Run annotate mode first.")

    predictions_payload = load_json(args.predictions_file)
    predictions = predictions_payload.get("predictions", {})

    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    total_tp = total_fp = total_fn = exact_matches = 0
    per_example = []

    for rel, record in sorted(records.items()):
        gt_text = (record or {}).get("ground_truth_text", "")
        if not gt_text.strip():
            continue

        image_path = repo_root() / rel
        if not image_path.exists():
            print(f"[WARN] Missing image, skipping: {rel}")
            continue

        if rel in predictions and not args.refresh_predictions:
            pred_text = predictions[rel]
        else:
            pred_text = extract_text(client, image_path, args.model)
            predictions[rel] = pred_text
            predictions_payload["predictions"] = predictions
            save_json(args.predictions_file, predictions_payload)

        counts = metric_counts(gt_text, pred_text)
        scores = counts_to_scores(counts)

        total_tp += counts.tp
        total_fp += counts.fp
        total_fn += counts.fn
        exact_matches += int(counts.exact_match)

        per_example.append(
            {
                "image": rel,
                "precision": scores["precision"],
                "recall": scores["recall"],
                "f1": scores["f1"],
                "accuracy": scores["accuracy"],
                "exact_match": scores["exact_match"],
            }
        )

        print(
            f"{rel}: P={scores['precision']:.3f} R={scores['recall']:.3f} "
            f"F1={scores['f1']:.3f} Acc={scores['accuracy']:.3f} "
            f"Exact={int(scores['exact_match'])}"
        )

    if not per_example:
        raise ValueError("No valid annotated examples were evaluated.")

    micro_counts = MetricCounts(
        tp=total_tp,
        fp=total_fp,
        fn=total_fn,
        exact_match=False,
    )
    micro = counts_to_scores(micro_counts)

    macro_precision = sum(x["precision"] for x in per_example) / len(per_example)
    macro_recall = sum(x["recall"] for x in per_example) / len(per_example)
    macro_f1 = sum(x["f1"] for x in per_example) / len(per_example)
    macro_accuracy = sum(x["accuracy"] for x in per_example) / len(per_example)
    exact_match_rate = exact_matches / len(per_example)

    summary = {
        "examples_evaluated": len(per_example),
        "micro": {
            "precision": micro["precision"],
            "recall": micro["recall"],
            "f1": micro["f1"],
            "accuracy": micro["accuracy"],
        },
        "macro": {
            "precision": macro_precision,
            "recall": macro_recall,
            "f1": macro_f1,
            "accuracy": macro_accuracy,
        },
        "exact_match_rate": exact_match_rate,
        "per_example": per_example,
    }

    if args.output_file:
        save_json(args.output_file, summary)

    print("\n=== Aggregate Metrics ===")
    print(f"Examples: {summary['examples_evaluated']}")
    print(
        f"Micro  -> P={summary['micro']['precision']:.3f} R={summary['micro']['recall']:.3f} "
        f"F1={summary['micro']['f1']:.3f} Acc={summary['micro']['accuracy']:.3f}"
    )
    print(
        f"Macro  -> P={summary['macro']['precision']:.3f} R={summary['macro']['recall']:.3f} "
        f"F1={summary['macro']['f1']:.3f} Acc={summary['macro']['accuracy']:.3f}"
    )
    print(f"Exact Match Rate -> {summary['exact_match_rate']:.3f}")

    if args.output_file:
        print(f"Saved report to {args.output_file}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="OCR evaluation utility")
    sub = parser.add_subparsers(dest="command", required=True)

    p_annotate = sub.add_parser("annotate", help="Create/update ground-truth annotations")
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
        help="Path to annotations JSON",
    )
    p_annotate.add_argument(
        "--overwrite",
        action="store_true",
        help="Re-annotate images that already have labels",
    )
    p_annotate.set_defaults(seed_from_ocr=True)
    p_annotate.add_argument(
        "--no-seed-from-ocr",
        dest="seed_from_ocr",
        action="store_false",
        help="Disable OCR draft seeding in annotate mode",
    )
    p_annotate.add_argument(
        "--model",
        default="gpt-4.1-mini",
        help="OpenAI model for OCR seed extraction in annotate mode",
    )
    p_annotate.add_argument(
        "--predictions-file",
        type=Path,
        default=default_predictions_path(),
        help="Path to cache model predictions",
    )
    p_annotate.add_argument(
        "--refresh-predictions",
        action="store_true",
        help="Ignore cached OCR seeds and regenerate in annotate mode",
    )

    p_eval = sub.add_parser("evaluate", help="Evaluate OCR extraction against annotations")
    p_eval.add_argument(
        "--annotations-file",
        type=Path,
        default=default_annotations_path(),
        help="Path to annotations JSON",
    )
    p_eval.add_argument(
        "--predictions-file",
        type=Path,
        default=default_predictions_path(),
        help="Path to cache model predictions",
    )
    p_eval.add_argument(
        "--refresh-predictions",
        action="store_true",
        help="Ignore prediction cache and re-run model extraction",
    )
    p_eval.add_argument(
        "--model",
        default="gpt-4.1-mini",
        help="OpenAI model for OCR extraction",
    )
    p_eval.add_argument(
        "--output-file",
        type=Path,
        default=repo_root() / "backend" / "ocr_eval_report.json",
        help="Path to save aggregate JSON report",
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
