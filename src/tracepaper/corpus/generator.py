"""Master corpus generator combining all control types."""

import json
from pathlib import Path
from typing import Any

from tracepaper.corpus import ControlType, CorpusMetadata
from tracepaper.corpus.jer import JournalEntryReviewGenerator
from tracepaper.corpus.p2p import PurchaseToPayGenerator
from tracepaper.corpus.uar import UserAccessReviewGenerator


class CorpusGenerator:
    """Generate complete synthetic test corpus with labels."""

    def __init__(self, seed: int | None = None, output_dir: str = "corpus_data"):
        """
        Initialize generator.

        Args:
            seed: Optional seed for reproducibility.
            output_dir: Directory to save generated corpus.
        """
        self.seed = seed
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Initialize control generators
        self.p2p_gen = PurchaseToPayGenerator(seed=seed)
        self.uar_gen = UserAccessReviewGenerator(seed=seed)
        self.jer_gen = JournalEntryReviewGenerator(seed=seed)

    def generate_sample_corpus(self, items_per_control: int = 3) -> dict[str, Any]:
        """
        Generate sample corpus (small, for review before full generation).

        Args:
            items_per_control: Number of items per control type.

        Returns:
            Dict with population, labels, and metadata.
        """
        population = []
        labels = []
        metadata = CorpusMetadata()

        # Generate P2P samples
        print(f"Generating {items_per_control} Purchase-to-Pay samples...")
        p2p_pop, p2p_labels = self.p2p_gen.generate_sample_items(count=items_per_control)
        population.extend(p2p_pop)
        labels.extend(p2p_labels)
        metadata.controls[ControlType.PURCHASE_TO_PAY]["count"] = len(p2p_labels)
        metadata.controls[ControlType.PURCHASE_TO_PAY]["exceptions"] = sum(
            1 for label in p2p_labels if "exception" in str(label.overall_disposition).lower()
        )

        # Generate UAR samples
        print(f"Generating {items_per_control} User Access Review samples...")
        uar_pop, uar_labels = self.uar_gen.generate_sample_items(count=items_per_control)
        population.extend(uar_pop)
        labels.extend(uar_labels)
        metadata.controls[ControlType.USER_ACCESS_REVIEW]["count"] = len(uar_labels)
        metadata.controls[ControlType.USER_ACCESS_REVIEW]["exceptions"] = sum(
            1 for label in uar_labels if "exception" in str(label.overall_disposition).lower()
        )

        # Generate JER samples
        print(f"Generating {items_per_control} Journal Entry Review samples...")
        jer_pop, jer_labels = self.jer_gen.generate_sample_items(count=items_per_control)
        population.extend(jer_pop)
        labels.extend(jer_labels)
        metadata.controls[ControlType.JOURNAL_ENTRY_REVIEW]["count"] = len(jer_labels)
        metadata.controls[ControlType.JOURNAL_ENTRY_REVIEW]["exceptions"] = sum(
            1 for label in jer_labels if "exception" in str(label.overall_disposition).lower()
        )

        metadata.total_population_items = len(population)
        metadata.total_documents = len(population) * 3  # Estimate

        # Serialize
        corpus_data = {
            "metadata": metadata.to_dict(),
            "population": [
                {
                    "population_item_id": p.population_item_id,
                    "control_id": p.control_id,
                    "control_type": p.control_type.value,
                    "data": p.data,
                    "document_ids": p.document_ids,
                }
                for p in population
            ],
            "labels": [label.to_dict() for label in labels],
        }

        return corpus_data

    def save_corpus(self, corpus_data: dict[str, Any], filename: str = "corpus.json") -> Path:
        """Save corpus to JSON file."""
        output_path = self.output_dir / filename
        with open(output_path, "w") as f:
            json.dump(corpus_data, f, indent=2)
        print(f"✓ Corpus saved to {output_path}")
        return output_path

    def print_summary(self, corpus_data: dict[str, Any]) -> None:
        """Print corpus summary."""
        metadata = corpus_data["metadata"]
        print("\n" + "=" * 60)
        print("CORPUS GENERATION SUMMARY")
        print("=" * 60)
        print(f"Generated at: {metadata['generated_at']}")
        print(f"Total population items: {metadata['total_population_items']}")
        print(f"Total documents (estimated): {metadata['total_documents']}")
        print()
        print("Control Breakdown:")
        for control_name, stats in metadata["controls"].items():
            print(
                f"  {control_name.upper()}: {stats['count']} items, "
                f"{stats['exceptions']} exceptions"
            )
        print("=" * 60 + "\n")

    def print_label_schema(self) -> None:
        """Print the label schema for documentation."""
        print("\nLABEL SCHEMA")
        print("=" * 60)
        print("""
LabeledItem {
  population_item_id: str         # Unique ID for this test item
  control_id: str                 # Which control is being tested
  control_type: str               # "purchase_to_pay" | "user_access_review" | "journal_entry_review"

  # Ground truth attribute values
  attributes: dict[str, str]      # Per-control attributes (see control-specific schema below)

  # Overall finding disposition
  overall_disposition: str        # "pass" | "exception" | "insufficient_evidence"

  # Evidence tracking
  supporting_doc_ids: list[str]   # Which documents should contain the evidence

  # Hard case indicators
  has_ocr_pages: bool             # Contains scanned/OCR'd pages
  has_distractor_docs: bool       # Contains intentional decoy documents
  has_missing_evidence: bool      # Evidence is intentionally absent
  distractor_doc_ids: list[str]   # Document IDs that are distractors

  # Metadata
  plant_date: str                 # Date when this test case was "planted"
  description: str                # What makes this case interesting
}

CONTROL-SPECIFIC ATTRIBUTES:

purchase_to_pay:
  - amount_exceeds_threshold: "yes" | "no"     # Is amount >= $10k?
  - approval_exists: "yes" | "no"              # Is approval document present?
  - approval_on_time: "yes" | "no"             # Approval <= payment date?
  - requester_is_approver: "yes" | "no"        # Is requester same as approver?
  - segregation_ok: "yes" | "no"               # Is segregation correct?

user_access_review:
  - review_completed: "yes" | "no"             # Is review memo present?
  - review_timely: "yes" | "no"                # Within 15 days of quarter end?
  - review_signed: "yes" | "no"                # Is it signed by owner?
  - terminated_users_removed: "yes" | "no"     # Are terminated users gone?

journal_entry_review:
  - amount_exceeds_threshold: "yes" | "no"     # Is amount >= $100k?
  - explanation_exists: "yes" | "no"           # Is explanation doc present?
  - reviewed: "yes" | "no"                     # Is reviewer assigned?
  - segregation_ok: "yes" | "no"               # Preparer != Reviewer?
""")
        print("=" * 60 + "\n")


if __name__ == "__main__":
    # Generate sample corpus
    gen = CorpusGenerator(seed=42, output_dir="corpus_data")

    # Print schema first
    gen.print_label_schema()

    # Generate samples
    corpus = gen.generate_sample_corpus(items_per_control=3)

    # Print summary
    gen.print_summary(corpus)

    # Save to file
    gen.save_corpus(corpus, filename="corpus_sample.json")

    print("\n✓ Phase 1 Sample corpus ready for review!")
    print("  View: corpus_data/corpus_sample.json")
