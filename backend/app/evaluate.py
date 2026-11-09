"""Evaluate the text gate on all pairs in a small hand-labeled Turkish corpus."""
import json
from itertools import combinations
from pathlib import Path
from types import SimpleNamespace

from .analysis import THRESHOLD, digest, matrices, score


def main():
    corpus = json.loads((Path(__file__).parents[1] / "evaluation.json").read_text(encoding="utf-8"))
    versions = [SimpleNamespace(title=item["title"], body=item["body"], summary="",
                                scope="full", digest=digest(item["body"])) for item in corpus]
    docs, vectors = matrices(versions)
    pairs = []
    for a, b in combinations(range(len(corpus)), 2):
        value, _ = score(versions[a], versions[b], docs[a], docs[b], vectors[a], vectors[b])
        pairs.append((corpus[a]["id"], corpus[b]["id"], corpus[a]["event"] == corpus[b]["event"], value or 0))
    for threshold in (0.20, 0.30, 0.40, THRESHOLD, 0.55, 0.65):
        fp = [(a, b, round(value, 3)) for a, b, same, value in pairs if not same and value >= threshold]
        fn = [(a, b, round(value, 3)) for a, b, same, value in pairs if same and value < threshold]
        tp = sum(same and value >= threshold for _, _, same, value in pairs)
        tn = len(pairs) - tp - len(fp) - len(fn)
        print(f"{threshold:.2f}  TP={tp} TN={tn} FP={len(fp)} FN={len(fn)}")
        if threshold == THRESHOLD:
            print("  Yanlış eşleşmeler:", fp)
            print("  Kaçırılan eşleşmeler:", fn)


if __name__ == "__main__":
    main()

