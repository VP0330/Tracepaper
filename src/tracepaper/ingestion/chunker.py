"""Provenance-preserving text chunking."""

from dataclasses import dataclass, asdict
import hashlib
import re

from .extraction import ExtractedPage


@dataclass(frozen=True)
class DocumentChunk:
    chunk_id: str
    doc_id: str
    page: int
    bbox: tuple[float, float, float, float]
    text: str
    extraction_method: str
    ocr_confidence: float | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def chunk_pages(
    doc_id: str, pages: list[ExtractedPage], max_chars: int = 1800, overlap: int = 200
) -> list[DocumentChunk]:
    """Split pages into deterministic overlapping chunks."""
    if max_chars <= overlap:
        raise ValueError("max_chars must be greater than overlap")
    chunks: list[DocumentChunk] = []
    for page in pages:
        text = re.sub(r"\s+", " ", page.text).strip()
        if not text:
            continue
        start = 0
        while start < len(text):
            end = min(len(text), start + max_chars)
            if end < len(text):
                boundary = text.rfind(" ", start, end)
                if boundary > start:
                    end = boundary
            span = text[start:end].strip()
            digest = hashlib.sha1(f"{doc_id}:{page.page}:{start}:{span}".encode()).hexdigest()[:16]
            chunks.append(DocumentChunk(
                chunk_id=f"{doc_id}:{page.page}:{digest}",
                doc_id=doc_id,
                page=page.page,
                bbox=page.bbox,
                text=span,
                extraction_method=page.extraction_method,
                ocr_confidence=page.ocr_confidence,
            ))
            if end == len(text):
                break
            start = max(start + 1, end - overlap)
    return chunks
