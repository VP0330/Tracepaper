"""Phase 5 reviewer API contract tests."""

from types import SimpleNamespace

from fastapi.testclient import TestClient

from tracepaper import api
from tracepaper.ingestion.chunker import chunk_pages
from tracepaper.ingestion.extraction import ExtractedPage
from tracepaper.retrieval import EvidenceRetriever


def _client() -> TestClient:
    retriever = EvidenceRetriever()
    retriever.store.insert_chunks(
        chunk_pages("doc-1", [ExtractedPage(1, "Approval status APPROVED", "text_layer")])
    )
    api.get_retriever = lambda: retriever
    api._owner_document_ids = lambda user_id: ["doc-1"]
    api.app.dependency_overrides[api.current_user] = lambda: SimpleNamespace(
        user_id="test-user", email="reviewer@example.test", display_name="Test Reviewer", role="admin",
    )
    return TestClient(api.app)


def test_engagement_endpoint():
    response = _client().get("/api/v1/engagements")
    assert response.status_code == 200
    assert response.json()["engagements"][0]["status"] == "ready"


def test_search_endpoint_contract():
    response = _client().get("/api/v1/evidence/search", params={"q": "approval"})
    assert response.status_code == 200
    assert response.json()["results"]


def test_finding_validation_endpoint_rejects_bad_citation():
    response = _client().post("/api/v1/findings/validate", json={
        "control_id": "p2p_001",
        "population_item_id": "item-1",
        "disposition": "pass",
        "rationale": "Approval exists",
        "citations": [{
            "doc_id": "doc-1",
            "page": 1,
            "bbox": [0, 0, 1, 1],
            "quoted_span": "Approval status REJECTED",
        }],
    })
    assert response.status_code == 422


def test_finding_review_lifecycle():
    client = _client()
    response = client.post("/api/v1/findings/validate", json={
        "control_id": "p2p_001", "population_item_id": "item-1", "disposition": "pass",
        "rationale": "Approval exists", "citations": [{
            "doc_id": "doc-1", "page": 1, "bbox": [0, 0, 1, 1], "quoted_span": "Approval status APPROVED",
        }],
    })
    finding_id = response.json()["finding_id"]
    accepted = client.post(f"/api/v1/findings/{finding_id}/accept", json={"reviewer": "auditor"})
    trace = client.get(f"/api/v1/findings/{finding_id}/trace")
    assert accepted.json()["status"] == "accepted"
    assert trace.json()["trace"][-1]["status"] == "accepted"


def test_agent_endpoint_uses_configured_agent(monkeypatch):
    class FakeAgent:
        def run(self, task):
            from tracepaper.agent.enforcement import Finding

            return Finding("p2p_001", "item-1", "pass", task, ())

    monkeypatch.setattr(api, "create_llm_client", lambda settings: object())
    monkeypatch.setattr(api, "AgentLoop", lambda client, tools: FakeAgent())
    response = _client().post("/api/v1/agent/analyze", json={"task": "Test item-1"})

    assert response.status_code == 200
    assert response.json()["provider"] == api.settings.llm_provider
    assert response.json()["finding"]["disposition"] == "pass"
