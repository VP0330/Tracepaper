"""Opt-in PostgreSQL integration test for upload/classify/rule persistence."""

import os
import uuid

import pytest
from fastapi.testclient import TestClient

from tracepaper import api
from tracepaper.auth import AuthService
from tracepaper.retrieval import EvidenceRetriever
from tracepaper.storage.models import (
    AuditFindingRecord,
    AuditRuleRecord,
    ChunkRecord,
    DocumentRecord,
    UploadedDocumentRecord,
    UserRecord,
)

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_POSTGRES_INTEGRATION") != "1",
    reason="Set RUN_POSTGRES_INTEGRATION=1 to run against PostgreSQL",
)


class StubUnderstanding:
    def classify_and_extract(self, file_name, pages):
        return {
            "document_type": "invoice", "control_type": "purchase_to_pay",
            "confidence": 0.99, "summary": "Live database integration invoice.",
            "fields": {"vendor": "Test Vendor", "amount": 15000, "currency": "USD"},
        }


def test_postgresql_upload_and_rule_flag_persistence(monkeypatch):
    service = AuthService(api.settings)
    user_id = str(uuid.uuid4())
    document_id = None
    with service.session_factory() as session:
        user = UserRecord(
            user_id=user_id, email=f"{user_id}@example.test", display_name="PG Test",
            password_hash="test-only", role="reviewer",
        )
        session.add(user)
        session.commit()
        session.expunge(user)

    monkeypatch.setattr(api, "get_auth_service", lambda: service)
    monkeypatch.setattr(api, "get_retriever", lambda: EvidenceRetriever(api.settings.database_url))
    monkeypatch.setattr(api, "get_document_understanding", lambda: StubUnderstanding())
    api.app.dependency_overrides[api.current_user] = lambda: user
    try:
        with TestClient(api.app) as client:
            upload = client.post(
                "/api/v1/documents/upload",
                files={"upload": ("pg-invoice.csv", b"VENDOR,AMOUNT\nTest Vendor,15000\n", "text/csv")},
            )
            assert upload.status_code == 200, upload.text
            document_id = upload.json()["document"]["document_id"]
            search = client.get("/api/v1/evidence/search", params={"q": "Test Vendor"})
            assert search.status_code == 200, search.text
            assert any(result["doc_id"] == document_id for result in search.json()["results"])
            created_rule = client.post("/api/v1/audit-rules", json={
                "name": "PG threshold", "control_type": "purchase_to_pay",
                "document_type": "invoice", "field_name": "amount", "operator": "lte",
                "expected_value": 10000, "severity": "high", "enabled": True,
            })
            assert created_rule.status_code == 200, created_rule.text
            assert created_rule.json()["flags_created"] == 1
            listing = client.get("/api/v1/audit-findings")
            assert listing.status_code == 200
            assert any(flag["document_id"] == document_id for flag in listing.json()["findings"])
    finally:
        api.app.dependency_overrides.pop(api.current_user, None)
        with service.session_factory() as session:
            session.query(AuditFindingRecord).filter_by(owner_id=user_id).delete(synchronize_session=False)
            session.query(AuditRuleRecord).filter_by(owner_id=user_id).delete(synchronize_session=False)
            if document_id:
                session.query(ChunkRecord).filter_by(doc_id=document_id).delete(synchronize_session=False)
                session.query(DocumentRecord).filter_by(doc_id=document_id).delete(synchronize_session=False)
                session.query(UploadedDocumentRecord).filter_by(document_id=document_id).delete(synchronize_session=False)
            session.query(UserRecord).filter_by(user_id=user_id).delete(synchronize_session=False)
            session.commit()
