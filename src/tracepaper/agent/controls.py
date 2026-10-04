"""Control definitions used by the Phase 4 agent loop."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ControlDefinition:
    control_id: str
    control_type: str
    name: str
    rule: str
    attributes: tuple[str, ...]


CONTROL_DEFINITIONS = {
    "p2p_001": ControlDefinition(
        "p2p_001", "purchase_to_pay", "Purchase-to-Pay Approval",
        "Invoices at or above $10,000 require documented approval before payment.",
        ("amount_exceeds_threshold", "approval_exists", "approval_on_time", "segregation_ok"),
    ),
    "uar_001": ControlDefinition(
        "uar_001", "user_access_review", "Quarterly User Access Review",
        "Access reviews must be completed, timely, signed, and remove terminated users.",
        ("review_completed", "review_timely", "review_signed", "terminated_users_removed"),
    ),
    "jer_001": ControlDefinition(
        "jer_001", "journal_entry_review", "Journal Entry Review",
        "Manual journal entries at or above $100,000 require explanation and independent review.",
        ("amount_exceeds_threshold", "explanation_exists", "reviewed", "segregation_ok"),
    ),
}


def get_control_definition(control_id: str) -> ControlDefinition:
    """Return a known control definition or fail explicitly."""
    try:
        return CONTROL_DEFINITIONS[control_id]
    except KeyError as exc:
        raise ValueError(f"Unknown control: {control_id}") from exc
