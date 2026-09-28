"""Corpus generation for synthetic test data with ground-truth labels."""

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any
from datetime import datetime, timedelta
import json
from pathlib import Path


class ControlType(str, Enum):
    """Supported control types."""

    PURCHASE_TO_PAY = "purchase_to_pay"
    USER_ACCESS_REVIEW = "user_access_review"
    JOURNAL_ENTRY_REVIEW = "journal_entry_review"


class Disposition(str, Enum):
    """Possible finding dispositions."""

    PASS = "pass"
    EXCEPTION = "exception"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


@dataclass
class Citation:
    """A citation pointing to evidence in a document."""

    doc_id: str
    page: int
    bbox: tuple[float, float, float, float]  # normalized (x0, y0, x1, y1)
    quoted_span: str
    supports_claim: bool = True


@dataclass
class AttributeResult:
    """Result of testing a control attribute."""

    attribute: str
    disposition: Disposition
    rationale: str
    citations: list[Citation] = field(default_factory=list)


@dataclass
class LabeledItem:
    """Ground truth for one population item being tested."""

    population_item_id: str
    control_id: str
    control_type: ControlType
    
    # Ground truth findings
    attributes: dict[str, str]  # e.g., {"approval_exists": "yes", "approval_on_time": "yes"}
    overall_disposition: Disposition
    
    # Expected evidence documents (which docs should contain the evidence)
    supporting_doc_ids: list[str]
    
    # Hard case flags
    has_ocr_pages: bool = False
    has_distractor_docs: bool = False
    has_missing_evidence: bool = False
    distractor_doc_ids: list[str] = field(default_factory=list)
    
    # Metadata
    plant_date: str = ""
    description: str = ""  # What makes this case interesting/hard

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for JSON serialization."""
        data = asdict(self)
        # Convert enums to strings
        data["control_type"] = self.control_type.value
        data["overall_disposition"] = self.overall_disposition.value
        data["attributes"] = {k: v for k, v in self.attributes.items()}
        return data


@dataclass
class PopulationItem:
    """One item in the control testing population."""

    population_item_id: str
    control_id: str
    control_type: ControlType
    
    # Item-specific data
    data: dict[str, Any]  # e.g., {"vendor": "Acme Inc", "amount": 15000}
    
    # Documents supporting this item
    document_ids: list[str]


class CorpusMetadata:
    """Metadata about generated corpus."""

    def __init__(self):
        self.generated_at = datetime.utcnow().isoformat()
        self.controls = {
            ControlType.PURCHASE_TO_PAY: {"count": 0, "exceptions": 0},
            ControlType.USER_ACCESS_REVIEW: {"count": 0, "exceptions": 0},
            ControlType.JOURNAL_ENTRY_REVIEW: {"count": 0, "exceptions": 0},
        }
        self.total_documents = 0
        self.total_population_items = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for JSON serialization."""
        return {
            "generated_at": self.generated_at,
            "controls": {k.value: v for k, v in self.controls.items()},
            "total_documents": self.total_documents,
            "total_population_items": self.total_population_items,
        }
