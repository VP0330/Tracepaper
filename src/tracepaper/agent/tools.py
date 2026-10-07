"""Safe deterministic tools exposed to the Phase 4 agent."""

from datetime import date
from typing import Any

from tracepaper.ingestion.chunker import DocumentChunk
from tracepaper.ingestion.citation import resolve_citation
from tracepaper.retrieval import EvidenceRetriever, RetrievalResult


def _result_to_chunk(result: RetrievalResult) -> DocumentChunk:
    return DocumentChunk(
        result.chunk_id, result.doc_id, result.page, result.bbox, result.text,
        result.extraction_method,
    )


class EvidenceTools:
    """Tool facade that keeps retrieval and finding validation deterministic."""

    def __init__(self, retriever: EvidenceRetriever, allowed_doc_ids: list[str] | None = None):
        self.retriever = retriever
        self.allowed_doc_ids = allowed_doc_ids

    def search_evidence(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        return [
            result.__dict__
            for result in self.retriever.search(query, limit, doc_ids=self.allowed_doc_ids)
        ]

    def fetch_page(self, doc_id: str, page: int) -> list[dict[str, Any]]:
        if self.allowed_doc_ids is not None and doc_id not in self.allowed_doc_ids:
            return []
        records = self.retriever.store.get_chunk_by_citation(doc_id, page)
        return [
            {
                "chunk_id": record.chunk_id,
                "doc_id": record.doc_id,
                "page": record.page,
                "bbox": tuple(__import__("json").loads(record.bbox)),
                "text": record.extracted_text,
                "extraction_method": record.extraction_method,
            }
            for record in records
        ]

    @staticmethod
    def compare_dates(left: str, right: str) -> dict[str, Any]:
        first, second = date.fromisoformat(left), date.fromisoformat(right)
        return {"left": left, "right": right, "before_or_equal": first <= second, "days": (second - first).days}

    @staticmethod
    def compare_amounts(left: float, right: float) -> dict[str, Any]:
        return {"left": left, "right": right, "left_gte_right": left >= right, "difference": left - right}

    def resolve_citation(self, citation: dict[str, Any]) -> bool:
        if self.allowed_doc_ids is not None and citation["doc_id"] not in self.allowed_doc_ids:
            return False
        records = self.retriever.store.get_chunk_by_citation(citation["doc_id"], citation["page"])
        chunks = [
            DocumentChunk(record.chunk_id, record.doc_id, record.page,
                          tuple(__import__("json").loads(record.bbox)), record.extracted_text,
                          record.extraction_method, record.ocr_confidence)
            for record in records
        ]
        return resolve_citation(
            citation["doc_id"], citation["page"], tuple(citation["bbox"]),
            citation["quoted_span"], chunks,
        )
