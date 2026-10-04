"""Seed and validate the local Tracepaper demo without an LLM."""

import json
from pathlib import Path
import sys

sys.path.insert(0, "src")

from tracepaper.eval.harness import evaluate


def main() -> None:
    root = Path(__file__).parents[1]
    corpus = root / "corpus_data" / "corpus_full.json"
    if not corpus.exists():
        raise SystemExit("Missing corpus_full.json; run Phase 1 first")
    result = evaluate(corpus, root / "corpus_data" / "eval_results.json")
    print("Tracepaper seeded demo")
    print(json.dumps(result["metrics"], indent=2))
    print("Results: corpus_data/eval_results.json")


if __name__ == "__main__":
    main()