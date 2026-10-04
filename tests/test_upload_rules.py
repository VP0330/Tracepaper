"""Integration coverage for authenticated uploads and configurable audit rules."""

from fastapi.testclient import TestClient

from tracepaper import api
from tracepaper.auth import AuthService
from tracepaper.config import Settings
from tracepaper.retrieval import EvidenceRetriever
from tracepaper.storage.models import UserRecord


class StubUnderstanding:
    def classify_and_extract(self, file_name, pages):
        return {
            "document_type": "invoice",
            "control_type": "purchase_to_pay",
            "confidence": 0.97,
            "summary": "Invoice for services.",
            "fields": {"vendor": "Northwind", "amount": 15000, "currency": "USD"},
        }


def test_upload_classifies_extracts_and_flags_rule(monkeypatch):
    auth = AuthService(Settings(database_url="sqlite:///:memory:", cache_enabled=False))
    admin_data = auth.bootstrap_admin("owner@example.test", "Owner", "a-long-owner-password")
    with auth.session_factory() as session:
        owner = session.get(UserRecord, admin_data["user_id"])
        session.expunge(owner)

    retriever = EvidenceRetriever()
    monkeypatch.setattr(api, "get_auth_service", lambda: auth)
    monkeypatch.setattr(api, "get_retriever", lambda: retriever)
    monkeypatch.setattr(api, "get_document_understanding", lambda: StubUnderstanding())
    api.app.dependency_overrides[api.current_user] = lambda: owner
    try:
        client = TestClient(api.app)
        uploaded = client.post(
            "/api/v1/documents/upload",
            files={"upload": ("invoice.csv", b"VENDOR,AMOUNT\nNorthwind,15000\n", "text/csv")},
        )
        assert uploaded.status_code == 200, uploaded.text
        document = uploaded.json()["document"]
        assert document["document_type"] == "invoice"
        assert document["fields"]["amount"] == 15000

        created_rule = client.post("/api/v1/audit-rules", json={
            "name": "Invoice threshold", "control_type": "purchase_to_pay",
            "document_type": "invoice", "field_name": "amount", "operator": "lte",
            "expected_value": 10000, "severity": "high", "enabled": True,
        })
        assert created_rule.status_code == 200, created_rule.text
        assert created_rule.json()["flags_created"] == 1

        findings = client.get("/api/v1/audit-findings")
        assert findings.status_code == 200
        assert findings.json()["findings"][0]["status"] == "needs_review"
        assert findings.json()["findings"][0]["observed_value"] == 15000
    finally:
        api.app.dependency_overrides.pop(api.current_user, None)
