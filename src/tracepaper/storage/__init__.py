"""Persistence API for Phase 2 extracted evidence."""

import json
import re

from sqlalchemy import text

from tracepaper.ingestion.chunker import DocumentChunk

from .db import get_engine, get_session_factory, init_db
from .models import ChunkRecord, DocumentRecord


def _fts_terms(query: str) -> str:
    terms = re.findall(r"[A-Za-z0-9_]+", query)
    return " OR ".join(f'"{term}"' for term in terms)


class ChunkStore:
    """SQLAlchemy-backed chunk store with PostgreSQL or SQLite full-text search."""

    def __init__(self, db_path: str = ":memory:"):
        self.engine = get_engine(db_path)
        init_db(self.engine)
        self.session_factory = get_session_factory(self.engine)

    def insert_document(
        self,
        doc_id: str,
        document_type: str,
        file_path: str,
        pages: int,
        text_layer_coverage: float,
    ) -> None:
        with self.session_factory() as session:
            session.merge(
                DocumentRecord(
                    doc_id=doc_id,
                    document_type=document_type,
                    file_path=file_path,
                    pages=pages,
                    text_layer_coverage=text_layer_coverage,
                )
            )
            session.commit()

    def insert_chunks(self, chunks: list[DocumentChunk]) -> None:
        with self.session_factory() as session:
            for chunk in chunks:
                session.merge(
                    ChunkRecord(
                        chunk_id=chunk.chunk_id,
                        doc_id=chunk.doc_id,
                        page=chunk.page,
                        bbox=json.dumps(chunk.bbox),
                        extracted_text=chunk.text,
                        extraction_method=chunk.extraction_method,
                        ocr_confidence=chunk.ocr_confidence,
                    )
                )
                if self.engine.dialect.name == "sqlite":
                    session.execute(
                        text("DELETE FROM chunks_fts WHERE chunk_id = :id"), {"id": chunk.chunk_id}
                    )
                    session.execute(
                        text(
                            "INSERT INTO chunks_fts(chunk_id, doc_id, extracted_text) VALUES (:id, :doc, :text)"
                        ),
                        {"id": chunk.chunk_id, "doc": chunk.doc_id, "text": chunk.text},
                    )
            session.commit()

    def search_chunks(
        self, query: str, limit: int = 20, doc_ids: list[str] | None = None
    ) -> list[ChunkRecord]:
        terms = _fts_terms(query)
        if not terms or doc_ids == []:
            return []
        with self.session_factory() as session:
            params = {"query": terms, "limit": limit}
            doc_filter = ""
            if doc_ids is not None:
                placeholders = []
                for index, doc_id in enumerate(doc_ids):
                    key = f"doc_{index}"
                    placeholders.append(f":{key}")
                    params[key] = doc_id
                doc_filter = f" AND doc_id IN ({', '.join(placeholders)})"
            if self.engine.dialect.name == "postgresql":
                statement = text(
                    "SELECT chunk_id FROM chunks "
                    "WHERE to_tsvector('english', extracted_text) "
                    "@@ websearch_to_tsquery('english', :query)"
                    f"{doc_filter} "
                    "ORDER BY ts_rank(to_tsvector('english', extracted_text), "
                    "websearch_to_tsquery('english', :query)) DESC LIMIT :limit"
                )
            else:
                statement = text(
                    "SELECT chunk_id FROM chunks_fts WHERE chunks_fts MATCH :query"
                    f"{doc_filter} LIMIT :limit"
                )
            ids = session.execute(statement, params).scalars().all()
            if not ids:
                return []
            records = session.query(ChunkRecord).filter(ChunkRecord.chunk_id.in_(ids)).all()
            by_id = {record.chunk_id: record for record in records}
            return [by_id[chunk_id] for chunk_id in ids if chunk_id in by_id]

    def get_chunk_by_citation(self, doc_id: str, page: int) -> list[ChunkRecord]:
        with self.session_factory() as session:
            return session.query(ChunkRecord).filter_by(doc_id=doc_id, page=page).all()

    def get_all_chunks(self) -> list[ChunkRecord]:
        """Return all persisted chunks in stable insertion order."""
        with self.session_factory() as session:
            return session.query(ChunkRecord).order_by(ChunkRecord.chunk_id).all()
