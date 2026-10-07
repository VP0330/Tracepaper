"""Phase 3 hybrid retrieval: FTS5, dense similarity, and RRF."""

import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

from tracepaper.storage import ChunkStore
from tracepaper.storage.models import ChunkRecord


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
    lexical_rank: int | None = None
    dense_rank: int | None = None


class _TokenDenseIndex:
    """Dependency-free dense-like fallback for local/offline development."""

    def __init__(self, texts: list[str]):
        self.documents = [Counter(self._tokens(text)) for text in texts]

    @staticmethod
    def _tokens(text: str) -> list[str]:
        return re.findall(r"[a-z0-9]+", text.casefold())

    def search(self, query: str) -> list[tuple[int, float]]:
        query_tokens = Counter(self._tokens(query))
        if not query_tokens:
            return []
        query_norm = math.sqrt(sum(value * value for value in query_tokens.values()))
        results = []
        for index, document in enumerate(self.documents):
            numerator = sum(query_tokens[token] * document[token] for token in query_tokens)
            document_norm = math.sqrt(sum(value * value for value in document.values()))
            score = numerator / (query_norm * document_norm) if document_norm else 0.0
            if score > 0:
                results.append((index, score))
        return sorted(results, key=lambda item: item[1], reverse=True)


class EvidenceRetriever:
    """Retrieve evidence with lexical, dense, and reciprocal-rank fusion."""

    def __init__(self, db_path: str = ":memory:", embedding_model: str | None = None):
        self.store = ChunkStore(db_path)
        self.embedding_model_name = embedding_model
        self._dense_model: Any = None
        self._dense_index: Any = None
        self._chunks: list[ChunkRecord] = []
        self._chunk_fingerprint: tuple[str, ...] | None = None

    def _load_dense_index(self) -> None:
        chunks = self.store.get_all_chunks()
        fingerprint = tuple(chunk.chunk_id for chunk in chunks)
        if self._dense_index is not None and fingerprint == self._chunk_fingerprint:
            return
        self._chunks = chunks
        self._chunk_fingerprint = fingerprint
        self._dense_model = None
        texts = [chunk.extracted_text for chunk in self._chunks]
        if self.embedding_model_name:
            try:
                from sentence_transformers import SentenceTransformer

                self._dense_model = SentenceTransformer(self.embedding_model_name)
                self._dense_index = self._dense_model.encode(texts, normalize_embeddings=True)
                return
            except Exception:
                self._dense_model = None
        self._dense_index = _TokenDenseIndex(texts)

    def _dense_search(self, query: str) -> list[tuple[int, float]]:
        self._load_dense_index()
        if isinstance(self._dense_index, _TokenDenseIndex):
            return self._dense_index.search(query)

        query_vector = self._dense_model.encode([query], normalize_embeddings=True)[0]
        scores = self._dense_index @ query_vector
        return sorted(enumerate(scores.tolist()), key=lambda item: item[1], reverse=True)

    def search(
        self,
        query: str,
        limit: int = 10,
        rrf_k: int = 60,
        doc_ids: list[str] | None = None,
    ) -> list[RetrievalResult]:
        """Return hybrid-ranked evidence results with provenance metadata."""
        if not query.strip() or limit <= 0:
            return []
        lexical_records = self.store.search_chunks(
            query,
            limit=max(limit * 5, 20),
            doc_ids=doc_ids,
        )
        self._load_dense_index()
        by_id = {chunk.chunk_id: chunk for chunk in self._chunks}
        lexical_rank = {chunk.chunk_id: rank for rank, chunk in enumerate(lexical_records, 1)}
        allowed_ids = set(doc_ids) if doc_ids is not None else None
        dense_candidates = [
            (index, score)
            for index, score in self._dense_search(query)
            if allowed_ids is None or self._chunks[index].doc_id in allowed_ids
        ]
        dense_rank = {
            self._chunks[index].chunk_id: rank
            for rank, (index, score) in enumerate(dense_candidates[: max(limit * 5, 20)], 1)
            if score > 0
        }
        candidate_ids = set(lexical_rank) | set(dense_rank)
        results = []
        for chunk_id in candidate_ids:
            chunk = by_id[chunk_id]
            score = sum(
                1.0 / (rrf_k + rank)
                for rank in (lexical_rank.get(chunk_id), dense_rank.get(chunk_id))
                if rank is not None
            )
            results.append(
                RetrievalResult(
                    chunk_id=chunk.chunk_id,
                    doc_id=chunk.doc_id,
                    page=chunk.page,
                    bbox=tuple(json.loads(chunk.bbox)),
                    text=chunk.extracted_text,
                    extraction_method=chunk.extraction_method,
                    score=score,
                    lexical_rank=lexical_rank.get(chunk_id),
                    dense_rank=dense_rank.get(chunk_id),
                )
            )
        return sorted(results, key=lambda result: result.score, reverse=True)[:limit]
