"""Ollama document classification/extraction contract tests."""

import json
from types import SimpleNamespace

import pytest

from tracepaper.config import Settings
from tracepaper.ingestion.understanding import DocumentUnderstandingService
from tracepaper.llm.client import ChatResponse
from tracepaper.storage.db import get_engine, get_session_factory, init_db
from tracepaper.storage.models import ClassificationTypeRecord, PromptTemplateRecord


def make_service(prompt="Classify. {document_types} / {control_types}", extract_prompt="Extract {document_type}."):
    engine = get_engine("sqlite:///:memory:")
    init_db(engine)
    factory = get_session_factory(engine)
    with factory() as session:
        if prompt:
            session.add(PromptTemplateRecord(prompt_key="document_understanding", content=prompt))
        if extract_prompt:
            session.add(PromptTemplateRecord(prompt_key="document_extraction", content=extract_prompt))
        types = [
            ("document", "invoice", 1, True),
            ("document", "gw_statement_of_net_position", 2, True),
            ("document", "disabled_type", 3, False),
            ("control", "purchase_to_pay", 1, True),
            ("control", "financial_reporting", 2, True),
        ]
        session.add_all([
            ClassificationTypeRecord(
                category=c, value=v, label=v, description=f"{v} description", sort_order=o, enabled=e,
            ) for c, v, o, e in types
        ])
        session.commit()
    return DocumentUnderstandingService(Settings(cache_enabled=False), session_factory=factory)


class StubClient:
    def __init__(self, response: str):
        self.response = response
        self.schema = None
        self.schemas = []
        self.systems = []

    def chat(self, messages, tools=None, json_schema=None):
        self.schema = json_schema
        self.schemas.append(json_schema)
        self.systems.append(messages[0]["content"])
        return ChatResponse(text=self.response)


def test_ollama_classification_returns_typed_fields_without_live_server():
    service = make_service()
    fake = StubClient(json.dumps({
        "document_type": "invoice",
        "control_type": "purchase_to_pay",
        "confidence": 0.96,
        "summary": "Invoice from Sample Vendor.",
        "fields": {"vendor": "Sample Vendor", "amount": 12500, "currency": "USD"},
    }))
    service.client = fake

    result = service.classify_and_extract(
        "sample.pdf", [SimpleNamespace(page=1, text="invoice text")],
    )

    assert result["document_type"] == "invoice"
    assert result["fields"]["amount"] == 12500
    assert fake.schemas[0]["required"] == ["document_type", "control_type", "confidence", "summary"]
    assert fake.schemas[1]["required"] == ["fields"]


def test_ollama_rejects_unsupported_classification():
    service = make_service()
    service.client = StubClient(json.dumps({
        "document_type": "tax_return", "control_type": "purchase_to_pay",
        "confidence": 0.8, "summary": "", "fields": {},
    }))

    with pytest.raises(ValueError, match="unsupported document type"):
        service.classify_and_extract("unknown.pdf", [SimpleNamespace(page=1, text="invoice text")])


@pytest.mark.parametrize("raw,expected", [(95, 0.95), ("0.8", 0.8), ("90%", 0.9)])
def test_confidence_is_normalized(raw, expected):
    service = make_service()
    service.client = StubClient(json.dumps({
        "document_type": "invoice", "control_type": "purchase_to_pay",
        "confidence": raw, "summary": "", "fields": {},
    }))
    result = service.classify_and_extract("a.pdf", [SimpleNamespace(page=1, text="invoice text")])
    assert result["confidence"] == pytest.approx(expected)


def test_ollama_rejects_non_json_response():
    service = make_service()
    service.client = StubClient("not json")

    with pytest.raises(ValueError, match="valid JSON"):
        service.classify_and_extract("unknown.pdf", [SimpleNamespace(page=1, text="invoice text")])


def test_system_prompt_and_schema_come_from_db():
    service = make_service()
    fake = StubClient(json.dumps({
        "document_type": "invoice", "control_type": "purchase_to_pay",
        "confidence": 1, "summary": "", "fields": {},
    }))
    service.client = fake
    service.classify_and_extract("a.pdf", [SimpleNamespace(page=1, text="invoice text")])
    assert fake.schemas[0]["properties"]["document_type"]["enum"] == ["invoice", "gw_statement_of_net_position"]
    assert "gw_statement_of_net_position" in fake.systems[0]
    assert "disabled_type" not in fake.systems[0]
    assert fake.systems[1] == "Extract invoice."


def test_pages_are_classified_separately_and_merged_into_segments():
    service = make_service()
    answers = iter(["invoice", "gw_statement_of_net_position", "gw_statement_of_net_position"])

    class PerPage:
        def __init__(self):
            self.extract_sources = []

        def chat(self, messages, tools=None, json_schema=None):
            if "fields" in json_schema["properties"]:
                self.extract_sources.append(messages[-1]["content"])
                return ChatResponse(text=json.dumps({"fields": {"n": len(self.extract_sources)}}))
            return ChatResponse(text=json.dumps({
                "document_type": next(answers), "control_type": "purchase_to_pay",
                "confidence": 0.9, "summary": "s",
            }))

    per_page = PerPage()
    service.client = per_page
    pages = [SimpleNamespace(page=n, text=f"text {n}") for n in (1, 2, 3)]
    result = service.classify_and_extract("a.pdf", pages)
    assert [(s["start_page"], s["end_page"], s["document_type"]) for s in result["segments"]] == [
        (1, 1, "invoice"), (2, 3, "gw_statement_of_net_position"),
    ]
    assert result["document_type"] == "gw_statement_of_net_position"
    assert len(per_page.extract_sources) == 2
    assert "text 2" in per_page.extract_sources[1] and "text 3" in per_page.extract_sources[1]
    assert "text 1" not in per_page.extract_sources[1]
    assert result["fields"] == {"n": 2}


def test_missing_extraction_prompt_is_an_error():
    service = make_service(extract_prompt=None)
    with pytest.raises(RuntimeError, match="document_extraction"):
        service.classify_and_extract("a.pdf", [SimpleNamespace(page=1, text="invoice text")])


def test_missing_prompt_template_is_an_error():
    service = make_service(prompt=None)
    with pytest.raises(RuntimeError, match="missing from the database"):
        service.classify_and_extract("a.pdf", [SimpleNamespace(page=1, text="invoice text")])
