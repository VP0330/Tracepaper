"""Database-configured document classification and structured field extraction.

Pipeline: classify every page, group consecutive pages of one type into sections,
then extract fields once per section from that section's combined text.
"""

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select

from tracepaper.config import Settings
from tracepaper.llm.factory import create_llm_client
from tracepaper.storage.db import get_engine, get_session_factory
from tracepaper.storage.models import ClassificationTypeRecord, PromptTemplateRecord

CLASSIFY_PROMPT_KEY = "document_understanding"
EXTRACT_PROMPT_KEY = "document_extraction"
DOCUMENT_CATEGORY = "document"
CONTROL_CATEGORY = "control"
MAX_PAGE_CHARS = 12000
MAX_SECTION_CHARS = 30000
SKIPPED_EXTRACTION_TYPES = {"other"}

EXTRACTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"fields": {"type": "object", "additionalProperties": True}},
    "required": ["fields"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class UnderstandingConfig:
    """Prompts and allowed classifications loaded from the database."""

    classify_prompt: str
    extract_prompt: str
    document_types: dict[str, str]
    control_types: dict[str, str]

    def classify_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "document_type": {"type": "string", "enum": list(self.document_types)},
                "control_type": {"type": "string", "enum": list(self.control_types)},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "summary": {"type": "string"},
            },
            "required": ["document_type", "control_type", "confidence", "summary"],
            "additionalProperties": False,
        }

    def classify_system_prompt(self) -> str:
        return (
            self.classify_prompt
            .replace("{document_types}", _describe(self.document_types))
            .replace("{control_types}", _describe(self.control_types))
        )

    def extract_system_prompt(self, document_type: str) -> str:
        return (
            self.extract_prompt
            .replace("{document_type}", document_type)
            .replace("{document_type_description}", self.document_types.get(document_type, ""))
        )


def _describe(types: dict[str, str]) -> str:
    return "\n".join(f"- {value}: {description}" for value, description in types.items())


class DocumentUnderstandingService:
    """Classify pages, split into sections, then extract per section using DB-managed config."""

    def __init__(self, settings: Settings, session_factory=None):
        self.client = create_llm_client(settings)
        self.model = settings.llm_model
        self.session_factory = session_factory or get_session_factory(
            get_engine(settings.database_url)
        )

    def load_config(self) -> UnderstandingConfig:
        """Read prompts and enabled types on every call so DB edits apply immediately."""
        with self.session_factory() as session:
            prompts = {}
            for key in (CLASSIFY_PROMPT_KEY, EXTRACT_PROMPT_KEY):
                template = session.get(PromptTemplateRecord, key)
                if template is None or not template.content.strip():
                    raise RuntimeError(f"Prompt template '{key}' is missing from the database")
                prompts[key] = template.content
            rows = session.scalars(
                select(ClassificationTypeRecord)
                .where(ClassificationTypeRecord.enabled.is_(True))
                .order_by(ClassificationTypeRecord.sort_order, ClassificationTypeRecord.value)
            ).all()
            document_types = {
                row.value: (row.description or row.label)
                for row in rows if row.category == DOCUMENT_CATEGORY
            }
            control_types = {
                row.value: (row.description or row.label)
                for row in rows if row.category == CONTROL_CATEGORY
            }
        if not document_types:
            raise RuntimeError("No enabled document types are configured in classification_types")
        if not control_types:
            raise RuntimeError("No enabled control types are configured in classification_types")
        return UnderstandingConfig(
            prompts[CLASSIFY_PROMPT_KEY], prompts[EXTRACT_PROMPT_KEY], document_types, control_types,
        )

    def classify_and_extract(self, file_name: str, pages: list[Any]) -> dict[str, Any]:
        config = self.load_config()
        total = len(pages)
        results: list[dict[str, Any] | None] = []
        for page in pages:
            text = (page.text or "").strip()
            results.append(
                self._classify_page(config, file_name, page.page, total, text) if text else None
            )
        if not any(results):
            raise ValueError("No text could be extracted from this file")

        segments = _build_segments(pages, results)
        page_text = {page.page: (page.text or "").strip() for page in pages}
        for segment in segments:
            segment["fields"] = self._extract_segment(config, file_name, segment, page_text)

        primary = max(
            segments,
            key=lambda s: (s["document_type"] != "other", s["end_page"] - s["start_page"], s["confidence"]),
        )
        if len(segments) == 1:
            summary = primary["summary"]
        else:
            summary = " | ".join(
                f"Pages {s['start_page']}-{s['end_page']} {s['document_type']}: {s['summary']}"
                for s in segments
            )
        return {
            "document_type": primary["document_type"],
            "control_type": primary["control_type"],
            "confidence": primary["confidence"],
            "summary": summary,
            "fields": primary["fields"],
            "segments": segments,
        }

    def _chat_json(self, system: str, user: str, schema: dict[str, Any], label: str) -> dict[str, Any]:
        response = self.client.chat(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            json_schema=schema,
        )
        if not response.text:
            raise ValueError(f"{label}: the model returned no content")
        try:
            result = json.loads(response.text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{label}: the model response was not valid JSON") from exc
        if not isinstance(result, dict):
            raise ValueError(f"{label}: the model response was not a JSON object")
        return result

    def _classify_page(
        self, config: UnderstandingConfig, file_name: str, page_number: int, total: int, text: str,
    ) -> dict[str, Any]:
        label = f"Page {page_number}"
        result = self._chat_json(
            config.classify_system_prompt(),
            f"Filename: {file_name}\nPage {page_number} of {total}\nSource text:\n{text[:MAX_PAGE_CHARS]}",
            config.classify_schema(),
            label,
        )
        if result.get("document_type") not in config.document_types:
            raise ValueError(f"{label}: the model returned an unsupported document type")
        if result.get("control_type") not in config.control_types:
            raise ValueError(f"{label}: the model returned an unsupported control type")
        result["confidence"] = _normalize_confidence(result.get("confidence"))
        result["summary"] = str(result.get("summary") or "")
        return result

    def _extract_segment(
        self, config: UnderstandingConfig, file_name: str, segment: dict[str, Any],
        page_text: dict[int, str],
    ) -> dict[str, Any]:
        if segment["document_type"] in SKIPPED_EXTRACTION_TYPES:
            return {}
        label = f"Pages {segment['start_page']}-{segment['end_page']}"
        source = "\n\n".join(
            f"[Page {number}]\n{page_text.get(number, '')}"
            for number in range(segment["start_page"], segment["end_page"] + 1)
        )
        result = self._chat_json(
            config.extract_system_prompt(segment["document_type"]),
            f"Filename: {file_name}\nDocument type: {segment['document_type']}\n"
            f"Source text:\n{source[:MAX_SECTION_CHARS]}",
            EXTRACTION_SCHEMA,
            label,
        )
        if not isinstance(result.get("fields"), dict):
            raise ValueError(f"{label}: the model did not return extracted fields")
        return result["fields"]


def _build_segments(pages: list[Any], results: list[dict[str, Any] | None]) -> list[dict[str, Any]]:
    """Group consecutive pages of one document type; blank pages join the previous page."""
    first = next(result for result in results if result)
    resolved: list[dict[str, Any]] = []
    previous = first
    for result in results:
        previous = result or previous
        resolved.append(previous)

    segments: list[dict[str, Any]] = []
    scores: list[list[float]] = []
    for page, result in zip(pages, resolved):
        if segments and segments[-1]["document_type"] == result["document_type"]:
            segments[-1]["end_page"] = page.page
            scores[-1].append(result["confidence"])
        else:
            segments.append({
                "start_page": page.page, "end_page": page.page,
                "document_type": result["document_type"], "control_type": result["control_type"],
                "summary": result["summary"], "fields": {},
            })
            scores.append([result["confidence"]])
    for segment, values in zip(segments, scores):
        segment["confidence"] = sum(values) / len(values)
    return segments


def _normalize_confidence(value: Any) -> float:
    """Coerce model confidence output (0-1, 0-100, or numeric string) to a 0-1 float."""
    if isinstance(value, bool):
        raise ValueError("The model returned an invalid confidence score")
    if isinstance(value, str):
        try:
            value = float(value.strip().rstrip("%").strip())
        except ValueError as exc:
            raise ValueError("The model returned an invalid confidence score") from exc
    if not isinstance(value, (int, float)) or value != value or value < 0:
        raise ValueError("The model returned an invalid confidence score")
    if value > 1:
        value = value / 100
    if value > 1:
        raise ValueError("The model returned an invalid confidence score")
    return float(value)
