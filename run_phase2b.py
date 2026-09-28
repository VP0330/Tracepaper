"""Run Phase 2b/2c extraction, chunking, persistence, and citation checks."""

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, "src")

from tracepaper.ingestion.citation import resolve_citation
from tracepaper.ingestion.chunker import chunk_pages
from tracepaper.ingestion.extraction import DocumentExtractor
from tracepaper.storage import ChunkStore


def main() -> None:
    root = Path(__file__).parent
    manifest_path = root / "corpus_data" / "documents" / "manifest.json"
    with manifest_path.open(encoding="utf-8") as handle:
        manifest = json.load(handle)

    extractor = DocumentExtractor()
    store = ChunkStore(str(root / "corpus_data" / "phase2.sqlite"))
    method_counts: Counter[str] = Counter()
    total_chunks = 0
    failures: list[tuple[str, str]] = []
    first_chunk = None

    for doc_id, raw_path in manifest["documents"].items():
        path = Path(raw_path)
        if not path.is_absolute():
            path = root / path
        try:
            pages = extractor.extract(path)
            chunks = chunk_pages(doc_id, pages)
            coverage = sum(page.extraction_method == "text_layer" for page in pages) / len(pages)
            store.insert_document(doc_id, path.suffix.lstrip("."), str(path), len(pages), coverage)
            store.insert_chunks(chunks)
            total_chunks += len(chunks)
            method_counts.update(page.extraction_method for page in pages)
            first_chunk = first_chunk or (chunks[0] if chunks else None)
        except Exception as exc:
            failures.append((doc_id, str(exc)))

    valid_citation = False
    hallucinated_citation = False
    if first_chunk:
        valid_citation = resolve_citation(
            first_chunk.doc_id, first_chunk.page, first_chunk.bbox, first_chunk.text, [first_chunk]
        )
        hallucinated_citation = resolve_citation(
            first_chunk.doc_id, first_chunk.page, first_chunk.bbox,
            "This sentence does not exist in the source document.", [first_chunk]
        )

    report = {
        "documents": len(manifest["documents"]),
        "chunks": total_chunks,
        "extraction_methods": dict(method_counts),
        "failures": failures,
        "valid_citation_resolved": valid_citation,
        "hallucinated_citation_rejected": not hallucinated_citation,
    }
    print(json.dumps(report, indent=2))
    if failures or not valid_citation or hallucinated_citation:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
