"""Citation validation against extracted document chunks."""

from difflib import SequenceMatcher

from .chunker import DocumentChunk


def resolve_citation(
    doc_id: str,
    page: int,
    bbox: tuple[float, float, float, float],
    quoted_span: str,
    chunks: list[DocumentChunk],
    threshold: float = 0.9,
) -> bool:
    """Return whether a quoted span is supported by the requested location."""
    del bbox  # Chunk coordinates are normalized and page-scoped for now.
    quote = " ".join(quoted_span.split()).casefold()
    if not quote:
        return False
    for chunk in chunks:
        if chunk.doc_id != doc_id or chunk.page != page:
            continue
        text = " ".join(chunk.text.split()).casefold()
        if quote in text:
            return True
        if SequenceMatcher(None, quote, text).ratio() >= threshold:
            return True
    return False
