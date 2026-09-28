"""Focused Phase 2 extraction, provenance, and storage tests."""

from pathlib import Path

from tracepaper.ingestion.citation import resolve_citation
from tracepaper.ingestion.chunker import chunk_pages
from tracepaper.ingestion.extraction import DocumentExtractor, ExtractedPage
from tracepaper.storage import ChunkStore
from tracepaper.retrieval import EvidenceRetriever


def test_extracts_csv_and_chunks_with_provenance(tmp_path: Path):
    path = tmp_path / "sample.csv"
    path.write_text("ID,STATUS\nA-1,APPROVED\n", encoding="utf-8")

    pages = DocumentExtractor().extract(path)
    chunks = chunk_pages("sample", pages, max_chars=100, overlap=20)

    assert pages[0].extraction_method == "text_layer"
    assert chunks[0].doc_id == "sample"
    assert chunks[0].page == 1
    assert "APPROVED" in chunks[0].text


def test_text_backed_pdf_fixture_is_supported(tmp_path: Path):
    path = tmp_path / "sample.pdf"
    path.write_text("PDF_TEXTLAYER\nInvoice total: $8000", encoding="utf-8")

    page = DocumentExtractor().extract(path)[0]

    assert page.extraction_method == "text_layer"
    assert "Invoice total" in page.text


def test_citation_accepts_source_and_rejects_hallucination():
    pages = [ExtractedPage(1, "Approval status: APPROVED", "text_layer")]
    chunks = chunk_pages("doc-1", pages)
    chunk = chunks[0]

    assert resolve_citation("doc-1", 1, chunk.bbox, "Approval status: APPROVED", chunks)
    assert not resolve_citation("doc-1", 1, chunk.bbox, "Approval status: REJECTED", chunks)


def test_chunk_store_supports_fts_search():
    pages = [ExtractedPage(1, "Vendor Acme Corp invoice approved", "text_layer")]
    chunks = chunk_pages("doc-1", pages)
    store = ChunkStore()
    store.insert_chunks(chunks)

    results = store.search_chunks("invoice")

    assert [result.chunk_id for result in results] == [chunks[0].chunk_id]


def test_retrieval_preserves_provenance():
    pages = [ExtractedPage(1, "Invoice approved by finance", "text_layer")]
    chunks = chunk_pages("doc-1", pages)
    retriever = EvidenceRetriever()
    retriever.store.insert_chunks(chunks)

    results = retriever.search("finance")

    assert results[0].doc_id == "doc-1"
    assert results[0].page == 1
    assert results[0].bbox == (0.0, 0.0, 1.0, 1.0)
