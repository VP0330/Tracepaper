"""Ollama document classification/extraction contract tests."""

import json
from types import SimpleNamespace

import pytest

from tracepaper.config import Settings
from tracepaper.ingestion.understanding import DocumentUnderstandingService
from tracepaper.llm.client import ChatResponse


class StubClient:
    def __init__(self, response: str):
        self.response = response
        self.schema = None

    def chat(self, messages, tools=None, json_schema=None):
        self.schema = json_schema
        assert "invoice text" in messages[-1]["content"]
        return ChatResponse(text=self.response)


def test_ollama_classification_returns_typed_fields_without_live_server():
    service = DocumentUnderstandingService(Settings(cache_enabled=False))
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
    assert fake.schema["required"] == ["document_type", "control_type", "confidence", "summary", "fields"]


def test_ollama_rejects_unsupported_classification():
    service = DocumentUnderstandingService(Settings(cache_enabled=False))
    service.client = StubClient(json.dumps({
        "document_type": "tax_return", "control_type": "purchase_to_pay",
        "confidence": 0.8, "summary": "", "fields": {},
    }))

    with pytest.raises(ValueError, match="unsupported document type"):
        service.classify_and_extract("unknown.pdf", [SimpleNamespace(page=1, text="invoice text")])


@pytest.mark.parametrize("raw,expected", [(95, 0.95), ("0.8", 0.8), ("90%", 0.9)])
def test_confidence_is_normalized(raw, expected):
    service = DocumentUnderstandingService(Settings(cache_enabled=False))
    service.client = StubClient(json.dumps({
        "document_type": "invoice", "control_type": "purchase_to_pay",
        "confidence": raw, "summary": "", "fields": {},
    }))
    result = service.classify_and_extract("a.pdf", [SimpleNamespace(page=1, text="invoice text")])
    assert result["confidence"] == pytest.approx(expected)


def test_ollama_rejects_non_json_response():
    service = DocumentUnderstandingService(Settings(cache_enabled=False))
    service.client = StubClient("not json")

    with pytest.raises(ValueError, match="valid JSON"):
        service.classify_and_extract("unknown.pdf", [SimpleNamespace(page=1, text="invoice text")])
