"""Phase 2d retrieval over persisted evidence chunks."""

from dataclasses import dataclass
import json

from tracepaper.storage import ChunkStore


@dataclass(frozen=True)
class RetrievalResult:
	"""Search result retaining the source citation coordinates."""

	chunk_id: str
	doc_id: str
	page: int
	bbox: tuple[float, float, float, float]
	text: str
	extraction_method: str
	score: float


class EvidenceRetriever:
	"""Retrieve evidence chunks using SQLite FTS5 ranking."""

	def __init__(self, db_path: str = ":memory:"):
		self.store = ChunkStore(db_path)

	def search(self, query: str, limit: int = 10) -> list[RetrievalResult]:
		"""Return ranked evidence results with provenance metadata."""
		records = self.store.search_chunks(query, limit=limit)
		return [
			RetrievalResult(
				chunk_id=record.chunk_id,
				doc_id=record.doc_id,
				page=record.page,
				bbox=tuple(json.loads(record.bbox)),
				text=record.extracted_text,
				extraction_method=record.extraction_method,
				score=1.0 / (index + 1),
			)
			for index, record in enumerate(records)
		]
