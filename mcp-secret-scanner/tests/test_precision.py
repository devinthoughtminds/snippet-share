"""Precision and recall of scan() on a labelled corpus of real-shaped secrets and look-alikes. No LLM, no network."""

import json
from pathlib import Path

from scanner import scan

CORPUS = json.loads((Path(__file__).parent / "corpus.json").read_text(encoding="utf-8"))


def test_corpus_precision_and_recall():
    tp = fp = fn = 0
    failures = []
    for case in CORPUS:
        found = sorted(f["type"] for f in scan(case["text"]))
        expected = sorted(case["expect"])
        tp += len([t for t in found if t in expected])
        fp += len([t for t in found if t not in expected])
        fn += len([t for t in expected if t not in found])
        if found != expected:
            failures.append((case["text"][:60], expected, found))
    precision, recall = tp / (tp + fp), tp / (tp + fn)
    print(f"precision={precision:.3f} recall={recall:.3f}")
    assert (precision, recall) == (1.0, 1.0), failures
