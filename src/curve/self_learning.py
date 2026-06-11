"""Pseudo-label harvesting for the self-learning loop."""

from __future__ import annotations

import json
from pathlib import Path


def harvest_pseudo_labels(
    *,
    run_root: str | Path,
    output: str | Path,
    max_run_diagnostics: int = 0,
    max_classifier_prior_error: float = 0.0,
    min_editability_score: float = 0.0,
    max_fragmentation_penalty: float = 1.0,
) -> dict[str, object]:
    root = Path(run_root)
    records: list[dict[str, object]] = []
    rejected_runs: list[dict[str, object]] = []

    for manifest_path in sorted(root.glob("*/manifest.json")):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        diagnostics = [
            diagnostic
            for diagnostic in manifest.get("diagnostics", [])
            if diagnostic.get("level") == "warning"
        ]
        if len(diagnostics) > max_run_diagnostics:
            rejected_runs.append(
                {
                    "run": manifest_path.parent.name,
                    "reason": "too_many_run_diagnostics",
                    "diagnostic_count": len(diagnostics),
                }
            )
            continue
        run_metrics = dict(manifest.get("metrics", {}))
        editability_score = float(run_metrics.get("editability_score", 1.0))
        if editability_score < min_editability_score:
            rejected_runs.append(
                {
                    "run": manifest_path.parent.name,
                    "reason": "editability_score_too_low",
                    "editability_score": editability_score,
                    "min_editability_score": min_editability_score,
                }
            )
            continue
        fragmentation_penalty = float(run_metrics.get("fragmentation_penalty", 0.0))
        if fragmentation_penalty > max_fragmentation_penalty:
            rejected_runs.append(
                {
                    "run": manifest_path.parent.name,
                    "reason": "fragmentation_penalty_too_high",
                    "fragmentation_penalty": fragmentation_penalty,
                    "max_fragmentation_penalty": max_fragmentation_penalty,
                }
            )
            continue

        for index, anchor in enumerate(manifest.get("anchors", [])):
            metrics = anchor.get("metrics", {})
            prior_error = float(metrics.get("classifier_prior_error", 0.0))
            if prior_error > max_classifier_prior_error:
                continue
            records.append(
                {
                    "run": manifest_path.parent.name,
                    "anchor_index": index,
                    "kind": anchor.get("kind"),
                    "color": anchor.get("color"),
                    "metrics": metrics,
                    "run_metrics": run_metrics,
                    "source_manifest": str(manifest_path),
                }
            )

    result = {
        "pseudo_label_count": len(records),
        "pseudo_labels": records,
        "rejected_runs": rejected_runs,
        "filters": {
            "max_run_diagnostics": max_run_diagnostics,
            "max_classifier_prior_error": max_classifier_prior_error,
            "min_editability_score": min_editability_score,
            "max_fragmentation_penalty": max_fragmentation_penalty,
        },
    }
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    return result


def create_review_file(
    *,
    pseudo_labels: str | Path,
    output: str | Path,
) -> dict[str, object]:
    source = json.loads(Path(pseudo_labels).read_text(encoding="utf-8"))
    review_items = []
    for index, label in enumerate(source.get("pseudo_labels", [])):
        review_items.append(
            {
                "id": f"review-{index:05d}",
                "decision": "pending",
                "reason": "",
                "label": label,
            }
        )
    review = {
        "source": str(pseudo_labels),
        "review_count": len(review_items),
        "items": review_items,
    }
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(review, indent=2, sort_keys=True), encoding="utf-8")
    return review


def apply_review_file(
    *,
    review: str | Path,
    output: str | Path,
) -> dict[str, object]:
    review_data = json.loads(Path(review).read_text(encoding="utf-8"))
    accepted = []
    rejected = []
    pending = []
    for item in review_data.get("items", []):
        decision = item.get("decision")
        if decision == "accept":
            accepted.append(item["label"])
        elif decision == "reject":
            rejected.append(
                {
                    "id": item.get("id"),
                    "reason": item.get("reason", ""),
                    "label": item.get("label"),
                }
            )
        else:
            pending.append(item.get("id"))

    result = {
        "accepted_count": len(accepted),
        "rejected_count": len(rejected),
        "pending_count": len(pending),
        "accepted": accepted,
        "rejected": rejected,
        "pending": pending,
        "source_review": str(review),
    }
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    return result
