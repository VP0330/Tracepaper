"""Run a Phase 3 hybrid retrieval smoke test against the Phase 2 database."""

import sys

sys.path.insert(0, "src")

from tracepaper.retrieval import EvidenceRetriever
from tracepaper.config import get_settings


def main() -> None:
	retriever = EvidenceRetriever(get_settings().database_url)
	results = retriever.search("invoice approved", limit=5)
	print(f"Hybrid results: {len(results)}")
	for result in results:
		print(f"{result.score:.6f} {result.doc_id} p{result.page}: {result.text[:100]}")
	if not results:
		raise SystemExit("No retrieval results found; run Phase 2b first")


if __name__ == "__main__":
	main()
