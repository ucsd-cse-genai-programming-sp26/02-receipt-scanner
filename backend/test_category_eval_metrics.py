from category_eval import compute_metrics


LABELS = ["A", "B", "C"]


def test_multiclass_metrics_basic():
    y_true = ["A", "A", "B", "C"]
    y_pred = ["A", "B", "B", "C"]

    m = compute_metrics(y_true, y_pred, LABELS)

    assert m["count"] == 4
    assert round(m["accuracy"], 4) == 0.75
    assert round(m["micro"]["precision"], 4) == 0.75
    assert round(m["micro"]["recall"], 4) == 0.75
    assert round(m["micro"]["f1"], 4) == 0.75


def test_per_class_support_and_precision():
    y_true = ["A", "A", "B", "C", "C"]
    y_pred = ["A", "B", "B", "C", "A"]

    m = compute_metrics(y_true, y_pred, LABELS)

    assert m["per_class"]["A"]["support"] == 2
    assert m["per_class"]["B"]["support"] == 1
    assert m["per_class"]["C"]["support"] == 2

    assert round(m["per_class"]["B"]["precision"], 4) == 0.5
    assert round(m["per_class"]["B"]["recall"], 4) == 1.0
