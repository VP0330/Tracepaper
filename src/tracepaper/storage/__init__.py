"""Persistence API for Phase 2 extracted evidence."""

import json
from sqlalchemy import text

from tracepaper.ingestion.chunker import DocumentChunk
from .db import get_engine, get_session_factory, init_db
from .models import ChunkRecord, DocumentRecord


class ChunkStore:
	"""SQLite-backed chunk store with FTS5 search."""

	def __init__(self, db_path: str = ":memory:"):
		path = ":memory:" if db_path == ":memory:" else db_path
		self.engine = get_engine(path)
		init_db(self.engine)
		self.session_factory = get_session_factory(self.engine)

	def insert_document(self, doc_id: str, document_type: str, file_path: str, pages: int, text_layer_coverage: float) -> None:
		with self.session_factory() as session:
			session.merge(DocumentRecord(
				doc_id=doc_id, document_type=document_type, file_path=file_path,
				pages=pages, text_layer_coverage=text_layer_coverage,
			))
			session.commit()

	def insert_chunks(self, chunks: list[DocumentChunk]) -> None:
		with self.session_factory() as session:
			for chunk in chunks:
				session.merge(ChunkRecord(
					chunk_id=chunk.chunk_id, doc_id=chunk.doc_id, page=chunk.page,
					bbox=json.dumps(chunk.bbox), extracted_text=chunk.text,
					extraction_method=chunk.extraction_method,
					ocr_confidence=chunk.ocr_confidence,
				))
				session.execute(text("DELETE FROM chunks_fts WHERE chunk_id = :id"), {"id": chunk.chunk_id})
				session.execute(text(
					"INSERT INTO chunks_fts(chunk_id, doc_id, extracted_text) VALUES (:id, :doc, :text)"
				), {"id": chunk.chunk_id, "doc": chunk.doc_id, "text": chunk.text})
			session.commit()

	def search_chunks(self, query: str, limit: int = 20) -> list[ChunkRecord]:
		with self.session_factory() as session:
			ids = session.execute(text(
				"SELECT chunk_id FROM chunks_fts WHERE chunks_fts MATCH :query LIMIT :limit"
			), {"query": query, "limit": limit}).scalars().all()
			if not ids:
				return []
			records = session.query(ChunkRecord).filter(ChunkRecord.chunk_id.in_(ids)).all()
			by_id = {record.chunk_id: record for record in records}
			return [by_id[chunk_id] for chunk_id in ids if chunk_id in by_id]

	def get_chunk_by_citation(self, doc_id: str, page: int) -> list[ChunkRecord]:
		with self.session_factory() as session:
			return session.query(ChunkRecord).filter_by(doc_id=doc_id, page=page).all()
