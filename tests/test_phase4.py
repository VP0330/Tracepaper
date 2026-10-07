"""Phase 4 tool and enforcement tests."""

from tracepaper.agent.enforcement import EnforcementPipeline
from tracepaper.agent.loop import AgentLoop
from tracepaper.agent.tools import EvidenceTools
from tracepaper.ingestion.chunker import chunk_pages
from tracepaper.ingestion.extraction import ExtractedPage
from tracepaper.llm.client import ChatResponse, ToolCall
from tracepaper.retrieval import EvidenceRetriever


def _tools() -> EvidenceTools:
    retriever = EvidenceRetriever()
    chunks = chunk_pages("doc-1", [ExtractedPage(1, "Approval status APPROVED", "text_layer")])
    retriever.store.insert_chunks(chunks)
    return EvidenceTools(retriever)


def test_enforcement_rejects_hallucinated_citation():
    pipeline = EnforcementPipeline(_tools())
    payload = {
        "control_id": "p2p_001", "population_item_id": "item-1", "disposition": "pass",
        "rationale": "Approved", "citations": [{
            "doc_id": "doc-1", "page": 1, "bbox": [0, 0, 1, 1], "quoted_span": "Approval status REJECTED",
        }],
    }
    try:
        pipeline.validate_finding(payload)
        raise AssertionError("hallucinated citation should be rejected")
    except ValueError as error:
        assert "does not resolve" in str(error)


def test_agent_loop_accepts_valid_record_finding():
    tools = _tools()
    finding = {
        "control_id": "p2p_001", "population_item_id": "item-1", "disposition": "pass",
        "rationale": "Approval is documented.", "citations": [{
            "doc_id": "doc-1", "page": 1, "bbox": [0, 0, 1, 1], "quoted_span": "Approval status APPROVED",
        }],
    }

    class FakeClient:
        def chat(self, messages, tools=None, json_schema=None):
            return ChatResponse(tool_calls=[ToolCall("record_finding", finding)])

    result = AgentLoop(FakeClient(), tools).run("Test item-1")
    assert result.disposition == "pass"
