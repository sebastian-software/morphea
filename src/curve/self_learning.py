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
        },
    }
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    return result

