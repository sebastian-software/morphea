"""Shared review-policy records for promotion review artifacts."""

from __future__ import annotations


def promotion_quality_label_policy() -> dict[str, object]:
    """Return the current suite quality-label update policy."""

    return {
        "mode": "sidecar_only",
        "updates_current_quality_label": False,
        "suite_label_update": "manual",
        "review_evidence_field": "review_decision_applied",
        "reason": (
            "Applied promotion reviews are persisted as sidecar/run evidence; "
            "suite current_quality_label remains manual metadata until the "
            "suite file is explicitly edited."
        ),
    }
