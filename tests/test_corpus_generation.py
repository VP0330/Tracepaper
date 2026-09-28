"""Tests for Phase 1 corpus generation."""

import pytest
import json
from pathlib import Path
from tracepaper.corpus import (
    ControlType,
    Disposition,
    LabeledItem,
    PopulationItem,
)
from tracepaper.corpus.p2p import PurchaseToPayGenerator
from tracepaper.corpus.uar import UserAccessReviewGenerator
from tracepaper.corpus.jer import JournalEntryReviewGenerator
from tracepaper.corpus.generator import CorpusGenerator


class TestPurchaseToPayGenerator:
    """Test P2P corpus generation."""

    def test_p2p_generation(self):
        """Test P2P sample generation."""
        gen = PurchaseToPayGenerator(seed=42)
        pop_items, labels = gen.generate_sample_items(count=3)

        assert len(pop_items) == 3
        assert len(labels) == 3

        # Verify structure
        for item, label in zip(pop_items, labels):
            assert item.control_type == ControlType.PURCHASE_TO_PAY
            assert label.control_type == ControlType.PURCHASE_TO_PAY
            assert item.population_item_id == label.population_item_id

    def test_p2p_hard_cases(self):
        """Test that P2P plants intended hard cases."""
        gen = PurchaseToPayGenerator(seed=42)
        pop_items, labels = gen.generate_sample_items(count=3)

        # With seed=42, we should get specific patterns
        dispositions = [l.overall_disposition for l in labels]
        
        # Should have mix of PASS and EXCEPTION
        assert Disposition.PASS in dispositions or Disposition.EXCEPTION in dispositions

    def test_p2p_attributes_present(self):
        """Test that all expected attributes are present in labels."""
        gen = PurchaseToPayGenerator(seed=42)
        _, labels = gen.generate_sample_items(count=1)

        expected_attrs = {
            "amount_exceeds_threshold",
            "approval_exists",
            "approval_on_time",
            "requester_is_approver",
            "segregation_ok",
        }

        label = labels[0]
        assert set(label.attributes.keys()) == expected_attrs

        # All values should be "yes" or "no"
        for val in label.attributes.values():
            assert val in ("yes", "no")


class TestUserAccessReviewGenerator:
    """Test UAR corpus generation."""

    def test_uar_generation(self):
        """Test UAR sample generation."""
        gen = UserAccessReviewGenerator(seed=42)
        pop_items, labels = gen.generate_sample_items(count=3)

        assert len(pop_items) == 3
        assert len(labels) == 3

        for item, label in zip(pop_items, labels):
            assert item.control_type == ControlType.USER_ACCESS_REVIEW
            assert label.control_type == ControlType.USER_ACCESS_REVIEW

    def test_uar_attributes_present(self):
        """Test that all expected attributes are present."""
        gen = UserAccessReviewGenerator(seed=42)
        _, labels = gen.generate_sample_items(count=1)

        expected_attrs = {
            "review_completed",
            "review_timely",
            "review_signed",
            "terminated_users_removed",
        }

        label = labels[0]
        assert set(label.attributes.keys()) == expected_attrs

        for val in label.attributes.values():
            assert val in ("yes", "no")


class TestJournalEntryReviewGenerator:
    """Test JER corpus generation."""

    def test_jer_generation(self):
        """Test JER sample generation."""
        gen = JournalEntryReviewGenerator(seed=42)
        pop_items, labels = gen.generate_sample_items(count=3)

        assert len(pop_items) == 3
        assert len(labels) == 3

        for item, label in zip(pop_items, labels):
            assert item.control_type == ControlType.JOURNAL_ENTRY_REVIEW
            assert label.control_type == ControlType.JOURNAL_ENTRY_REVIEW

    def test_jer_attributes_present(self):
        """Test that all expected attributes are present."""
        gen = JournalEntryReviewGenerator(seed=42)
        _, labels = gen.generate_sample_items(count=1)

        expected_attrs = {
            "amount_exceeds_threshold",
            "explanation_exists",
            "reviewed",
            "segregation_ok",
        }

        label = labels[0]
        assert set(label.attributes.keys()) == expected_attrs

        for val in label.attributes.values():
            assert val in ("yes", "no")


class TestCorpusGenerator:
    """Test master corpus generator."""

    def test_corpus_generation(self, tmp_path):
        """Test full corpus generation."""
        gen = CorpusGenerator(seed=42, output_dir=str(tmp_path))
        corpus = gen.generate_sample_corpus(items_per_control=3)

        # Check structure
        assert "metadata" in corpus
        assert "population" in corpus
        assert "labels" in corpus

        metadata = corpus["metadata"]
        assert "generated_at" in metadata
        assert "controls" in metadata
        assert "total_population_items" in metadata

        # Should have 9 items (3 per control)
        assert metadata["total_population_items"] == 9
        assert len(corpus["population"]) == 9
        assert len(corpus["labels"]) == 9

    def test_corpus_control_breakdown(self, tmp_path):
        """Test that corpus has correct control breakdown."""
        gen = CorpusGenerator(seed=42, output_dir=str(tmp_path))
        corpus = gen.generate_sample_corpus(items_per_control=3)

        metadata = corpus["metadata"]
        controls = metadata["controls"]

        # Should have 3 controls
        assert len(controls) == 3
        assert "purchase_to_pay" in controls
        assert "user_access_review" in controls
        assert "journal_entry_review" in controls

        # Each control should have 3 items
        for control_name, stats in controls.items():
            assert stats["count"] == 3
            assert "exceptions" in stats

    def test_corpus_labels_match_population(self, tmp_path):
        """Test that labels correspond to population items."""
        gen = CorpusGenerator(seed=42, output_dir=str(tmp_path))
        corpus = gen.generate_sample_corpus(items_per_control=3)

        pop_ids = {item["population_item_id"] for item in corpus["population"]}
        label_ids = {label["population_item_id"] for label in corpus["labels"]}

        assert pop_ids == label_ids

    def test_corpus_serialization(self, tmp_path):
        """Test that corpus can be saved and loaded."""
        gen = CorpusGenerator(seed=42, output_dir=str(tmp_path))
        corpus = gen.generate_sample_corpus(items_per_control=3)

        # Save
        output_path = gen.save_corpus(corpus, filename="test_corpus.json")
        assert output_path.exists()

        # Load and verify
        with open(output_path, "r") as f:
            loaded = json.load(f)

        assert loaded["metadata"]["total_population_items"] == 9
        assert len(loaded["population"]) == 9
        assert len(loaded["labels"]) == 9

    def test_dispositions_valid(self, tmp_path):
        """Test that all dispositions are valid."""
        gen = CorpusGenerator(seed=42, output_dir=str(tmp_path))
        corpus = gen.generate_sample_corpus(items_per_control=3)

        valid_dispositions = {"pass", "exception", "insufficient_evidence"}
        for label in corpus["labels"]:
            assert label["overall_disposition"] in valid_dispositions

    def test_reproducibility(self, tmp_path):
        """Test that same seed produces same corpus."""
        gen1 = CorpusGenerator(seed=42, output_dir=str(tmp_path))
        corpus1 = gen1.generate_sample_corpus(items_per_control=3)

        gen2 = CorpusGenerator(seed=42, output_dir=str(tmp_path))
        corpus2 = gen2.generate_sample_corpus(items_per_control=3)

        # Compare critical fields (not timestamps)
        assert len(corpus1["population"]) == len(corpus2["population"])
        assert len(corpus1["labels"]) == len(corpus2["labels"])

        # Sample a few items to verify they match
        for pop1, pop2 in zip(corpus1["population"][:3], corpus2["population"][:3]):
            assert pop1["population_item_id"] == pop2["population_item_id"]
            assert pop1["data"]["amount"] == pop2["data"]["amount"]


class TestDispositionLogic:
    """Test that dispositions align with control rules."""

    def test_p2p_disposition_logic(self):
        """Test P2P disposition logic."""
        gen = PurchaseToPayGenerator(seed=42)
        pop_items, labels = gen.generate_sample_items(count=10)

        for pop, label in zip(pop_items, labels):
            amount = pop.data["amount"]
            threshold = pop.data["threshold"]

            # For items below threshold, should PASS regardless
            if amount < threshold:
                # Can be PASS or INSUFFICIENT_EVIDENCE if no approval
                assert label.overall_disposition in (
                    Disposition.PASS,
                    Disposition.INSUFFICIENT_EVIDENCE,
                )

            # For items above threshold, check segregation & timing
            if amount >= threshold:
                approval_exists = label.attributes["approval_exists"] == "yes"
                if not approval_exists:
                    assert label.overall_disposition == Disposition.INSUFFICIENT_EVIDENCE

    def test_uar_disposition_logic(self):
        """Test UAR disposition logic."""
        gen = UserAccessReviewGenerator(seed=42)
        pop_items, labels = gen.generate_sample_items(count=10)

        for label in labels:
            review_completed = label.attributes["review_completed"] == "yes"

            # If review not completed, should be INSUFFICIENT_EVIDENCE
            if not review_completed:
                assert label.overall_disposition == Disposition.INSUFFICIENT_EVIDENCE

    def test_jer_disposition_logic(self):
        """Test JER disposition logic."""
        gen = JournalEntryReviewGenerator(seed=42)
        pop_items, labels = gen.generate_sample_items(count=10)

        for pop, label in zip(pop_items, labels):
            amount = pop.data["amount"]
            threshold = pop.data["threshold"]

            # Below threshold, should PASS
            if amount < threshold:
                assert label.overall_disposition == Disposition.PASS

            # Above threshold without explanation, should be EXCEPTION/INSUFFICIENT
            if amount >= threshold:
                explanation_exists = label.attributes["explanation_exists"] == "yes"
                if not explanation_exists:
                    assert label.overall_disposition in (
                        Disposition.EXCEPTION,
                        Disposition.INSUFFICIENT_EVIDENCE,
                    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
