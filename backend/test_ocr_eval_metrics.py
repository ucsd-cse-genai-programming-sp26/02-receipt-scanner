from ocr_eval import counts_to_scores, metric_counts


def test_perfect_match_scores_are_one():
    counts = metric_counts("milk bread 3.99", "milk bread 3.99")
    scores = counts_to_scores(counts)

    assert counts.tp == 3
    assert counts.fp == 0
    assert counts.fn == 0
    assert scores["precision"] == 1.0
    assert scores["recall"] == 1.0
    assert scores["f1"] == 1.0
    assert scores["accuracy"] == 1.0


def test_partial_match_scores():
    counts = metric_counts("milk bread eggs", "milk eggs soda")
    scores = counts_to_scores(counts)

    assert counts.tp == 2
    assert counts.fp == 1
    assert counts.fn == 1
    assert round(scores["precision"], 4) == round(2 / 3, 4)
    assert round(scores["recall"], 4) == round(2 / 3, 4)
    assert round(scores["f1"], 4) == round(2 / 3, 4)
    assert round(scores["accuracy"], 4) == round(2 / 4, 4)


def test_repeated_tokens_counted_correctly():
    counts = metric_counts("apple apple banana", "apple banana banana")

    assert counts.tp == 2
    assert counts.fp == 1
    assert counts.fn == 1
