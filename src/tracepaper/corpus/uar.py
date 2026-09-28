"""Generator for User Access Review control test data."""

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


class UserAccessReviewGenerator:
    """
    Generate test data for Quarterly User Access Review control.

    Control Rule: Access review must be completed within 15 days of quarter end,
    signed by system owner, with terminated users removed.
    """

    def __init__(self, seed: int | None = None):
        """Initialize generator with optional seed."""
        if seed is not None:
            random.seed(seed)
        self.control_id = "uar_001"
        self.systems = ["SAP", "Salesforce", "ServiceNow", "Oracle EBS"]
        self.system_owners = [
            "john.admin@company.com",
            "sarah.sysadmin@company.com",
            "mike.ops@company.com",
        ]
        self.quarters = ["Q1", "Q2", "Q3", "Q4"]

    def generate_access_review_csv(
        self,
        system: str,
        quarter: str,
        user_count: int,
        removed_count: int,
        reviewed_on: str,
    ) -> dict[str, Any]:
        """Generate mock access review export (CSV format)."""
        users = []
        for i in range(user_count):
            status = "TERMINATED" if i < removed_count else "ACTIVE"
            users.append(
                {
                    "username": f"user{i:03d}",
                    "department": random.choice(["Finance", "Operations", "IT", "Sales"]),
                    "status": status,
                    "access_level": random.choice(["Read", "Write", "Admin"]),
                    "last_login": (datetime.utcnow() - timedelta(days=random.randint(1, 90)))
                    .strftime("%Y-%m-%d"),
                }
            )

        return {
            "type": "access_review_export",
            "system": system,
            "quarter": quarter,
            "reviewed_on": reviewed_on,
            "user_count": user_count,
            "terminated_removed": removed_count,
            "users": users,
        }

    def generate_review_memo(
        self,
        system: str,
        quarter: str,
        review_date: str,
        owner: str,
        is_signed: bool = True,
        missing_users: bool = False,
    ) -> dict[str, Any]:
        """Generate mock access review memo/certification."""
        status = "CERTIFIED" if is_signed else "DRAFT"
        user_msg = "All terminated users have been removed" if not missing_users else "Review pending user removals"
        
        return {
            "type": "access_review_memo",
            "system": system,
            "quarter": quarter,
            "review_date": review_date,
            "owner": owner,
            "status": status,
            "signature": owner if is_signed else None,
            "body": f"I certify that the {quarter} access review for {system} has been completed. {user_msg}.",
        }

    def generate_sample_items(
        self, count: int = 3
    ) -> tuple[list[PopulationItem], list[LabeledItem]]:
        """
        Generate sample items for User Access Review control.

        Hard cases:
        - On-time, complete, signed reviews (PASS)
        - Late reviews (beyond 15 days) (EXCEPTION)
        - Unsigned/unsigned reviews (EXCEPTION)
        - Reviews with terminated users not removed (EXCEPTION)
        - Missing review evidence (INSUFFICIENT_EVIDENCE)
        """
        population_items = []
        labeled_items = []

        for i in range(count):
            item_id = f"uar_sample_{i+1}"
            system = random.choice(self.systems)
            quarter = random.choice(self.quarters)
            owner = random.choice(self.system_owners)

            # Determine quarter end date (simplified: Q1=Mar31, Q2=Jun30, Q3=Sep30, Q4=Dec31)
            year = 2024
            quarter_ends = {"Q1": "03-31", "Q2": "06-30", "Q3": "09-30", "Q4": "12-31"}
            quarter_end_str = quarter_ends[quarter]
            quarter_end = datetime.strptime(f"{year}-{quarter_end_str}", "%Y-%m-%d")

            # Vary cases
            case_type = i % 4
            user_count = random.randint(50, 200)
            removed_count = random.randint(2, 10)

            if case_type == 0:
                # Happy path: on-time, signed, all users removed
                days_after = random.randint(0, 15)
                review_date = (quarter_end + timedelta(days=days_after)).strftime("%Y-%m-%d")
                is_signed = True
                missing_users = False
                has_memo = True
                disposition = Disposition.PASS
                hard_case = "Complete on-time review with sign-off"

            elif case_type == 1:
                # Exception: late review (>15 days after quarter end)
                days_after = random.randint(16, 30)
                review_date = (quarter_end + timedelta(days=days_after)).strftime("%Y-%m-%d")
                is_signed = True
                missing_users = False
                has_memo = True
                disposition = Disposition.EXCEPTION
                hard_case = f"Late completion ({days_after} days after quarter end)"

            elif case_type == 2:
                # Exception: review not signed
                days_after = random.randint(0, 15)
                review_date = (quarter_end + timedelta(days=days_after)).strftime("%Y-%m-%d")
                is_signed = False
                missing_users = False
                has_memo = True
                disposition = Disposition.EXCEPTION
                hard_case = "Review not signed by owner"

            else:  # case_type == 3
                # Missing evidence: no memo
                days_after = random.randint(0, 15)
                review_date = (quarter_end + timedelta(days=days_after)).strftime("%Y-%m-%d")
                is_signed = False
                missing_users = False
                has_memo = False
                disposition = Disposition.INSUFFICIENT_EVIDENCE
                hard_case = "Missing review certification memo"

            # Document IDs
            doc_ids = [f"{item_id}_access_export"]
            if has_memo:
                doc_ids.append(f"{item_id}_review_memo")

            # Population item
            pop_item = PopulationItem(
                population_item_id=item_id,
                control_id=self.control_id,
                control_type=ControlType.USER_ACCESS_REVIEW,
                data={
                    "system": system,
                    "quarter": quarter,
                    "quarter_end": quarter_end.strftime("%Y-%m-%d"),
                    "owner": owner,
                    "user_count": user_count,
                    "terminated_removed": removed_count,
                },
                document_ids=doc_ids,
            )
            population_items.append(pop_item)

            # Label
            days_after_quarter = (
                datetime.strptime(review_date, "%Y-%m-%d") - quarter_end
            ).days
            review_timely = days_after_quarter <= 15

            label = LabeledItem(
                population_item_id=item_id,
                control_id=self.control_id,
                control_type=ControlType.USER_ACCESS_REVIEW,
                attributes={
                    "review_completed": "yes" if has_memo else "no",
                    "review_timely": "yes" if review_timely else "no",
                    "review_signed": "yes" if is_signed else "no",
                    "terminated_users_removed": "yes" if not missing_users else "no",
                },
                overall_disposition=disposition,
                supporting_doc_ids=[did for did in doc_ids if "memo" in did],
                has_ocr_pages=False,
                has_distractor_docs=False,
                has_missing_evidence=not has_memo,
                plant_date=review_date,
                description=hard_case,
            )
            labeled_items.append(label)

        return population_items, labeled_items
