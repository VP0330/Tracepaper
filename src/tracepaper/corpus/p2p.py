"""Generator for Purchase-to-Pay control test data."""

import random
from datetime import datetime, timedelta
from typing import Any

from tracepaper.corpus import (
    Citation,
    ControlType,
    Disposition,
    LabeledItem,
    PopulationItem,
)


class PurchaseToPayGenerator:
    """
    Generate test data for Purchase-to-Pay control.

    Control Rule: Invoice over $10,000 requires documented approval by someone
    other than the requester, dated on or before the payment date.
    """

    def __init__(self, seed: int | None = None):
        """Initialize generator with optional seed for reproducibility."""
        if seed is not None:
            random.seed(seed)
        self.control_id = "p2p_001"
        self.vendors = [
            ("Acme Corp", "acme@acme.com"),
            ("Global Supplies Ltd", "sales@globalsupplies.com"),
            ("Tech Solutions Inc", "vendor@techsol.com"),
            ("Premium Services", "contact@premiumsvc.com"),
        ]
        self.approvers = [
            "alice.smith@company.com",
            "bob.jones@company.com",
            "carol.brown@company.com",
            "diana.white@company.com",
        ]

    def generate_invoice_pdf(
        self,
        vendor: str,
        amount: float,
        invoice_date: str,
        po_number: str | None = None,
    ) -> dict[str, Any]:
        """Generate mock invoice PDF content."""
        return {
            "type": "invoice",
            "vendor": vendor,
            "amount": amount,
            "invoice_date": invoice_date,
            "po_number": po_number or f"PO-{random.randint(10000, 99999)}",
            "description": "Goods and services rendered",
        }

    def generate_approval_email(
        self,
        approver: str,
        approval_date: str,
        invoice_amount: float,
        vendor: str,
        requester: str,
        approved: bool = True,
    ) -> dict[str, Any]:
        """Generate mock approval email content."""
        status = "APPROVED" if approved else "REJECTED"
        return {
            "type": "email",
            "from": approver,
            "to": requester,
            "subject": f"{status}: Invoice from {vendor} - ${invoice_amount:,.2f}",
            "date": approval_date,
            "body": f"This is to confirm {status.lower()} the invoice from {vendor} for ${invoice_amount:,.2f}.",
            "in_reply_to": None,
        }

    def generate_po(
        self, vendor: str, amount: float, po_date: str, po_number: str
    ) -> dict[str, Any]:
        """Generate mock Purchase Order."""
        return {
            "type": "purchase_order",
            "vendor": vendor,
            "amount": amount,
            "po_date": po_date,
            "po_number": po_number,
            "line_items": [
                {
                    "description": "Service delivery",
                    "quantity": 1,
                    "unit_price": amount,
                }
            ],
        }

    def generate_sample_items(
        self, count: int = 3
    ) -> tuple[list[PopulationItem], list[LabeledItem]]:
        """
        Generate sample population items with labels.

        Intentionally plants hard cases:
        - Some items with on-time approval
        - Some with late approval (exception)
        - Some with no approval (exception)
        - Some with approval by requester (exception)
        - Some with missing docs entirely
        """
        population_items = []
        labeled_items = []

        for i in range(count):
            item_id = f"p2p_sample_{i+1}"
            vendor, vendor_email = random.choice(self.vendors)
            requester = random.choice(self.approvers)
            approver = random.choice([a for a in self.approvers if a != requester])

            base_date = datetime.utcnow() - timedelta(days=random.randint(5, 60))
            invoice_date = base_date.strftime("%Y-%m-%d")
            payment_date = (base_date + timedelta(days=random.randint(1, 10))).strftime(
                "%Y-%m-%d"
            )
            po_number = f"PO-{random.randint(100000, 999999)}"

            # Vary cases
            case_type = i % 4
            invoice_amount = random.choice([15000, 12000, 8000])  # Mix above/below $10k

            if case_type == 0:
                # Happy path: on-time approval, segregated
                approval_date = payment_date  # On or before payment
                approver_is_requester = False
                has_approval = True
                disposition = Disposition.PASS if invoice_amount >= 10000 else Disposition.PASS
                hard_case = "Standard compliant case"

            elif case_type == 1:
                # Exception: approval AFTER payment
                approval_date = (
                    datetime.strptime(payment_date, "%Y-%m-%d") + timedelta(days=2)
                ).strftime("%Y-%m-%d")
                approver_is_requester = False
                has_approval = True
                disposition = (
                    Disposition.EXCEPTION if invoice_amount >= 10000 else Disposition.PASS
                )
                hard_case = "Late approval (after payment date)"

            elif case_type == 2:
                # Exception: approver == requester (no segregation)
                approval_date = payment_date
                approver_is_requester = True
                has_approval = True
                disposition = (
                    Disposition.EXCEPTION if invoice_amount >= 10000 else Disposition.PASS
                )
                hard_case = "No segregation: requester approved own invoice"

            else:  # case_type == 3
                # Missing evidence: no approval document
                approval_date = payment_date
                approver_is_requester = False
                has_approval = False
                disposition = (
                    Disposition.INSUFFICIENT_EVIDENCE
                    if invoice_amount >= 10000
                    else Disposition.PASS
                )
                hard_case = "Missing approval evidence"

            # Generate document IDs
            doc_ids = [f"{item_id}_po", f"{item_id}_invoice"]
            if has_approval:
                doc_ids.append(f"{item_id}_approval_email")

            # Create population item
            pop_item = PopulationItem(
                population_item_id=item_id,
                control_id=self.control_id,
                control_type=ControlType.PURCHASE_TO_PAY,
                data={
                    "vendor": vendor,
                    "vendor_email": vendor_email,
                    "requester": requester,
                    "approver": approver if not approver_is_requester else requester,
                    "amount": invoice_amount,
                    "invoice_date": invoice_date,
                    "payment_date": payment_date,
                    "po_number": po_number,
                    "threshold": 10000,
                },
                document_ids=doc_ids,
            )
            population_items.append(pop_item)

            # Create labeled ground truth
            approval_on_time = approval_date <= payment_date if has_approval else False
            segregation_ok = (
                (approver != requester) if has_approval else False
            )  # Can't be ok without approval

            citations = []
            if has_approval and invoice_amount >= 10000:
                citations.append(
                    Citation(
                        doc_id=f"{item_id}_approval_email",
                        page=1,
                        bbox=(0.1, 0.2, 0.9, 0.4),
                        quoted_span=f"APPROVED: Invoice from {vendor} for ${invoice_amount:,.2f}",
                        supports_claim=True,
                    )
                )

            label = LabeledItem(
                population_item_id=item_id,
                control_id=self.control_id,
                control_type=ControlType.PURCHASE_TO_PAY,
                attributes={
                    "amount_exceeds_threshold": "yes" if invoice_amount >= 10000 else "no",
                    "approval_exists": "yes" if has_approval else "no",
                    "approval_on_time": "yes" if approval_on_time else "no",
                    "requester_is_approver": "yes" if approver_is_requester else "no",
                    "segregation_ok": "yes" if segregation_ok else "no",
                },
                overall_disposition=disposition,
                supporting_doc_ids=[did for did in doc_ids if "approval" in did or "po" in did],
                has_ocr_pages=False,
                has_distractor_docs=False,
                has_missing_evidence=not has_approval,
                plant_date=invoice_date,
                description=hard_case,
            )
            labeled_items.append(label)

        return population_items, labeled_items
