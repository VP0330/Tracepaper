"""Generator for Journal Entry Review control test data."""

import random
from datetime import datetime, timedelta
from typing import Any

from tracepaper.corpus import (
    ControlType,
    Disposition,
    Citation,
    LabeledItem,
    PopulationItem,
)


class JournalEntryReviewGenerator:
    """
    Generate test data for Journal Entry Review control.

    Control Rule: Manual journal entries over $100k must have preparer/reviewer
    segregation and an attached explanation document.
    """

    def __init__(self, seed: int | None = None):
        """Initialize generator with optional seed."""
        if seed is not None:
            random.seed(seed)
        self.control_id = "jer_001"
        self.preparers = [
            "alice.accounting@company.com",
            "bob.accounting@company.com",
            "carol.acct@company.com",
        ]
        self.reviewers = [
            "diana.controller@company.com",
            "eric.finance@company.com",
            "fiona.cfo@company.com",
        ]
        self.accounts = ["1000-Cash", "2000-AP", "3000-Revenue", "5000-Expense", "6000-COGS"]

    def generate_journal_entry(
        self,
        je_number: str,
        date: str,
        preparer: str,
        amount: float,
        description: str,
    ) -> dict[str, Any]:
        """Generate mock journal entry."""
        return {
            "type": "journal_entry",
            "je_number": je_number,
            "date": date,
            "preparer": preparer,
            "amount": amount,
            "description": description,
            "line_items": [
                {
                    "account": random.choice(self.accounts),
                    "debit": amount / 2 if random.random() > 0.5 else 0,
                    "credit": amount / 2 if random.random() <= 0.5 else 0,
                }
            ],
        }

    def generate_je_explanation(
        self, je_number: str, description: str, reviewer: str | None = None
    ) -> dict[str, Any]:
        """Generate mock JE explanation/support document."""
        return {
            "type": "je_explanation",
            "je_number": je_number,
            "description": description,
            "business_purpose": f"Business justification: {description}",
            "reviewed_by": reviewer,
            "review_date": datetime.utcnow().strftime("%Y-%m-%d"),
        }

    def generate_sample_items(
        self, count: int = 3
    ) -> tuple[list[PopulationItem], list[LabeledItem]]:
        """
        Generate sample items for Journal Entry Review control.

        Hard cases:
        - Over-threshold JEs with proper segregation and explanation (PASS)
        - Over-threshold JEs without segregation (EXCEPTION)
        - Over-threshold JEs missing explanation (EXCEPTION)
        - Over-threshold JEs prepared and reviewed by same person (EXCEPTION)
        - Under-threshold JEs regardless of documentation (PASS)
        - Missing review entirely (INSUFFICIENT_EVIDENCE)
        """
        population_items = []
        labeled_items = []

        for i in range(count):
            item_id = f"jer_sample_{i+1}"
            je_number = f"JE-{random.randint(10000, 99999)}"
            je_date = (datetime.utcnow() - timedelta(days=random.randint(5, 60))).strftime(
                "%Y-%m-%d"
            )
            preparer = random.choice(self.preparers)

            # Vary cases
            case_type = i % 4
            amount = random.choice([150000, 80000, 50000, 25000])  # Mix above/below $100k

            if case_type == 0:
                # Happy path: over-threshold, segregated, with explanation
                reviewer = random.choice([r for r in self.reviewers])
                has_explanation = True
                same_preparer_reviewer = False
                doc_ids = [f"{item_id}_je", f"{item_id}_explanation"]
                disposition = Disposition.PASS if amount >= 100000 else Disposition.PASS
                hard_case = "Over-threshold with proper segregation and explanation"

            elif case_type == 1:
                # Exception: over-threshold, NO segregation (same preparer = reviewer)
                reviewer = preparer
                has_explanation = True
                same_preparer_reviewer = True
                doc_ids = [f"{item_id}_je", f"{item_id}_explanation"]
                disposition = (
                    Disposition.EXCEPTION if amount >= 100000 else Disposition.PASS
                )
                hard_case = "Preparer and reviewer are the same person"

            elif case_type == 2:
                # Exception: over-threshold, no explanation
                reviewer = random.choice([r for r in self.reviewers])
                has_explanation = False
                same_preparer_reviewer = False
                doc_ids = [f"{item_id}_je"]
                disposition = (
                    Disposition.EXCEPTION if amount >= 100000 else Disposition.PASS
                )
                hard_case = "Over-threshold but missing explanation document"

            else:  # case_type == 3
                # Missing evidence: no review at all
                reviewer = None
                has_explanation = False
                same_preparer_reviewer = False
                doc_ids = [f"{item_id}_je"]
                disposition = (
                    Disposition.INSUFFICIENT_EVIDENCE
                    if amount >= 100000
                    else Disposition.PASS
                )
                hard_case = "Missing review evidence"

            # Population item
            pop_item = PopulationItem(
                population_item_id=item_id,
                control_id=self.control_id,
                control_type=ControlType.JOURNAL_ENTRY_REVIEW,
                data={
                    "je_number": je_number,
                    "date": je_date,
                    "preparer": preparer,
                    "reviewer": reviewer,
                    "amount": amount,
                    "threshold": 100000,
                },
                document_ids=doc_ids,
            )
            population_items.append(pop_item)

            # Label
            has_segregation = (
                preparer != reviewer if reviewer else False
            )
            
            label = LabeledItem(
                population_item_id=item_id,
                control_id=self.control_id,
                control_type=ControlType.JOURNAL_ENTRY_REVIEW,
                attributes={
                    "amount_exceeds_threshold": "yes" if amount >= 100000 else "no",
                    "explanation_exists": "yes" if has_explanation else "no",
                    "reviewed": "yes" if reviewer else "no",
                    "segregation_ok": "yes" if has_segregation else "no",
                },
                overall_disposition=disposition,
                supporting_doc_ids=[did for did in doc_ids if "explanation" in did or "review" in did],
                has_ocr_pages=False,
                has_distractor_docs=False,
                has_missing_evidence=not has_explanation or not reviewer,
                plant_date=je_date,
                description=hard_case,
            )
            labeled_items.append(label)

        return population_items, labeled_items
