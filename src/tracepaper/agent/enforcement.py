"""Structured finding validation for Phase 4."""

from dataclasses import dataclass
from typing import Any

from .controls import get_control_definition
from .tools import EvidenceTools


@dataclass(frozen=True)
class Finding:
    control_id: str
    population_item_id: str
    disposition: str
    rationale: str
    citations: tuple[dict[str, Any], ...]


class EnforcementPipeline:
    """Reject malformed or unsupported findings before they leave the agent."""

    def __init__(self, tools: EvidenceTools):
        self.tools = tools

    def validate_finding(self, payload: dict[str, Any]) -> Finding:
        control_id = payload["control_id"]
        get_control_definition(control_id)
        disposition = payload["disposition"]
        if disposition not in {"pass", "exception", "insufficient_evidence"}:
            raise ValueError(f"Invalid disposition: {disposition}")
        citations = tuple(payload.get("citations", []))
        if disposition != "insufficient_evidence" and not citations:
            raise ValueError("Supported findings require at least one citation")
        for citation in citations:
            required = {"doc_id", "page", "bbox", "quoted_span"}
            if not required.issubset(citation):
                raise ValueError("Citation is missing required provenance fields")
            if not self.tools.resolve_citation(citation):
                raise ValueError(f"Citation does not resolve: {citation['doc_id']}")
        return Finding(
            control_id=control_id,
            population_item_id=payload["population_item_id"],
            disposition=disposition,
            rationale=payload.get("rationale", ""),
            citations=citations,
        )
