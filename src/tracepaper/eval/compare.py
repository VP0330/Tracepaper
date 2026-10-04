"""Compare evaluation result JSON files."""

import json
from pathlib import Path
import sys


def compare(paths: list[str]) -> str:
    lines = ["| Run | Items | Accuracy | Citation resolve rate |", "|---|---:|---:|---:|"]
    for raw_path in paths:
        path = Path(raw_path)
        data = json.loads(path.read_text(encoding="utf-8"))["metrics"]
        lines.append(
            f"| {path.stem} | {data['items']} | {data['accuracy']:.3f} | "
            f"{data['citation_resolve_rate']:.3f} |"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    paths = sys.argv[1:] or ["corpus_data/eval_results.json"]
    print(compare(paths))
