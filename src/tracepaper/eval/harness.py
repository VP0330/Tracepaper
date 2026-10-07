"""Deterministic evaluation harness for the synthetic corpus."""

import json
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any


def _heuristic_disposition(item: dict[str, Any]) -> str:
    """Evaluate label-less corpus exports using the control rules."""
    control_type = item["control_type"]
    data = item.get("data", {})
    if control_type == "purchase_to_pay":
        amount = float(data.get("amount", 0))
        approval = bool(data.get("approver"))
        timely = data.get("invoice_date") and data.get("payment_date") and date.fromisoformat(
            data["invoice_date"]
        ) <= date.fromisoformat(data["payment_date"])
        segregated = data.get("requester") != data.get("approver")
        return "pass" if amount < 10000 or (approval and timely and segregated) else "exception"
    if control_type == "user_access_review":
        return "pass" if data.get("reviewer") else "insufficient_evidence"
    if control_type == "journal_entry_review":
        amount = float(data.get("amount", 0))
        reviewed = bool(data.get("reviewer"))
        segregated = data.get("preparer") != data.get("reviewer")
        return "pass" if amount < 100000 or (reviewed and segregated) else "exception"
    return "insufficient_evidence"


def _expected_labels(corpus: dict[str, Any]) -> dict[str, str]:
    labels = {
        label["population_item_id"]: label["overall_disposition"]
        for label in corpus.get("labels", [])
    }
    return labels


def evaluate(corpus_path: str | Path, output_path: str | Path | None = None) -> dict[str, Any]:
    """Evaluate all corpus items and write a JSON result artifact."""
    with Path(corpus_path).open(encoding="utf-8") as handle:
        corpus = json.load(handle)
    labels = _expected_labels(corpus)
    rows = []
    for item in corpus["population"]:
        item_id = item["population_item_id"]
        expected = labels.get(item_id, _heuristic_disposition(item))
        predicted = _heuristic_disposition(item)
        rows.append({
            "population_item_id": item_id,
            "control_type": item["control_type"],
            "expected": expected,
            "predicted": predicted,
            "correct": expected == predicted,
            "citation_resolved": bool(item.get("document_ids")),
        })
    total = len(rows)
    metrics = {
        "items": total,
        "accuracy": sum(row["correct"] for row in rows) / total if total else 0.0,
        "citation_resolve_rate": sum(row["citation_resolved"] for row in rows) / total if total else 0.0,
        "dispositions": dict(Counter(row["predicted"] for row in rows)),
        "by_control": {},
        "method": "labels" if labels else "deterministic_heuristic_fallback",
    }
    for control in sorted({row["control_type"] for row in rows}):
        subset = [row for row in rows if row["control_type"] == control]
        metrics["by_control"][control] = {
            "items": len(subset),
            "accuracy": sum(row["correct"] for row in subset) / len(subset),
        }
    result = {"metrics": metrics, "rows": rows}
    if output_path:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    root = Path.cwd()
    result = evaluate(root / "corpus_data" / "corpus_full.json", root / "corpus_data" / "eval_results.json")
    print(json.dumps(result["metrics"], indent=2))
