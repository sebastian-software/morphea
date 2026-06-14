"""Pseudo-label harvesting for the self-learning loop."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from morphea.classifier import (
    FEATURE_NAMES,
    TrainingExample,
    anchors_from_dataset,
    centroids_from_examples,
    evaluate_classifier,
    evaluate_classifier_ranking,
    examples_from_dataset,
    feature_importance_from_centroids,
    raster_examples_from_dataset,
)
from morphea.curated import check_curated_suite
from morphea.lucide_quality import check_lucide_suite
from morphea.mlx_classifier import (
    MlxClassifierTrainingConfig,
    train_mlx_transformer_classifier,
)
from morphea.promotion_export import apply_reviewed_region_promotions


HARVEST_FILTER_DEFAULTS = {
    "max_run_diagnostics": 0,
    "max_classifier_prior_error": 0.0,
    "min_editability_score": 0.0,
    "max_fragmentation_penalty": 1.0,
    "max_raster_l1_error": 1.0,
    "max_raster_edge_error": 1.0,
    "max_anchor_quality_error": 1.0,
    "require_applied_review": False,
}
SELF_LEARNING_GATE_DECISIONS = {"accept", "manual_review", "reject"}
SELF_LEARNING_FAMILY_VALIDATION_SUITES = ("primitive", "real_image", "lucide")
SELF_LEARNING_BASELINE_SNAPSHOT_STATUSES = {
    "not_configured",
    "skipped_not_accepted",
    "skipped_missing_review_evidence",
    "skipped_existing_output_requires_matching_baseline",
    "skipped_coverage_regression",
    "written",
}


def harvest_pseudo_labels(
    *,
    run_root: str | Path,
    output: str | Path,
    markdown: str | Path | None = None,
    max_run_diagnostics: int = 0,
    max_classifier_prior_error: float = 0.0,
    min_editability_score: float = 0.0,
    max_fragmentation_penalty: float = 1.0,
    max_raster_l1_error: float = 1.0,
    max_raster_edge_error: float = 1.0,
    max_anchor_quality_error: float = 1.0,
    require_applied_review: bool = False,
) -> dict[str, object]:
    root = Path(run_root)
    records: list[dict[str, object]] = []
    rejected_runs: list[dict[str, object]] = []

    for manifest_path in sorted(root.glob("*/manifest.json")):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        applied_review = _applied_review_decision(manifest)
        applied_review_status = _applied_review_harvest_status(applied_review)
        if require_applied_review and not applied_review_status["ok"]:
            rejected_runs.append(
                {
                    "run": manifest_path.parent.name,
                    "reason": applied_review_status["reason"],
                    "review_decision": applied_review_status["decision"],
                }
            )
            continue
        promotion_state_counts = None
        if require_applied_review and applied_review_status["ok"]:
            promotion_state_counts = _promotion_anchor_state_counts(manifest)
            if (
                promotion_state_counts is not None
                and promotion_state_counts.get("promoted", 0) <= 0
            ):
                rejected_runs.append(
                    {
                        "run": manifest_path.parent.name,
                        "reason": "applied_review_without_promoted_anchors",
                        "review_decision": applied_review_status["decision"],
                        "promoted_anchor_count": 0,
                        "anchor_state_counts": promotion_state_counts,
                    }
                )
                continue
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
        raster_l1_error = float(run_metrics.get("raster_l1_error", 0.0))
        if raster_l1_error > max_raster_l1_error:
            rejected_runs.append(
                {
                    "run": manifest_path.parent.name,
                    "reason": "raster_l1_error_too_high",
                    "raster_l1_error": raster_l1_error,
                    "max_raster_l1_error": max_raster_l1_error,
                }
            )
            continue
        raster_edge_error = float(run_metrics.get("raster_edge_error", 0.0))
        if raster_edge_error > max_raster_edge_error:
            rejected_runs.append(
                {
                    "run": manifest_path.parent.name,
                    "reason": "raster_edge_error_too_high",
                    "raster_edge_error": raster_edge_error,
                    "max_raster_edge_error": max_raster_edge_error,
                }
            )
            continue

        for index, anchor in enumerate(manifest.get("anchors", [])):
            if (
                require_applied_review
                and promotion_state_counts is not None
                and anchor.get("promotion_state") != "promoted"
            ):
                continue
            metrics = anchor.get("metrics", {})
            prior_error = float(metrics.get("classifier_prior_error", 0.0))
            if prior_error > max_classifier_prior_error:
                continue
            quality_error = _anchor_quality_error(metrics)
            if quality_error > max_anchor_quality_error:
                continue
            source_image = _source_image_from_manifest_path(manifest_path)
            record = {
                "run": manifest_path.parent.name,
                "anchor_index": index,
                "kind": anchor.get("kind"),
                "color": anchor.get("color"),
                "anchor": anchor,
                "metrics": metrics,
                "anchor_quality_error": quality_error,
                "run_metrics": run_metrics,
                "group_context": _anchor_group_context(manifest, index),
                "source_manifest": str(manifest_path),
            }
            if source_image is not None:
                record["source_image"] = str(source_image)
            if applied_review:
                record["review_decision_applied"] = applied_review
            records.append(record)

    result = {
        "pseudo_label_count": len(records),
        "pseudo_labels": records,
        "rejected_runs": rejected_runs,
        "filters": {
            "max_run_diagnostics": max_run_diagnostics,
            "max_classifier_prior_error": max_classifier_prior_error,
            "min_editability_score": min_editability_score,
            "max_fragmentation_penalty": max_fragmentation_penalty,
            "max_raster_l1_error": max_raster_l1_error,
            "max_raster_edge_error": max_raster_edge_error,
            "max_anchor_quality_error": max_anchor_quality_error,
            "require_applied_review": require_applied_review,
        },
    }
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    if markdown is not None:
        markdown_path = Path(markdown)
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(
            render_harvest_markdown(result),
            encoding="utf-8",
        )
    return result


def harvest_curated_pseudo_labels(
    *,
    suite: str | Path,
    run_root: str | Path,
    output: str | Path,
    curated_report: str | Path | None = None,
    snapshot: str | Path | None = None,
    markdown: str | Path | None = None,
    max_run_diagnostics: int = 0,
    max_classifier_prior_error: float = 0.0,
    min_editability_score: float = 0.0,
    max_fragmentation_penalty: float = 1.0,
    max_raster_l1_error: float = 1.0,
    max_raster_edge_error: float = 1.0,
    max_anchor_quality_error: float = 1.0,
    require_applied_review: bool = False,
) -> dict[str, object]:
    run_root_path = Path(run_root)
    existing_applied_reviews = _existing_applied_reviews(run_root_path)
    curated = check_curated_suite(
        suite,
        output=curated_report,
        output_dir=run_root_path,
        run=True,
        snapshot=snapshot,
    )
    restored_applied_reviews = _restore_curated_applied_reviews(
        run_root_path,
        curated,
        existing_applied_reviews,
    )
    if curated_report is not None and restored_applied_reviews:
        Path(curated_report).write_text(
            json.dumps(curated, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    result = harvest_pseudo_labels(
        run_root=run_root_path,
        output=output,
        max_run_diagnostics=max_run_diagnostics,
        max_classifier_prior_error=max_classifier_prior_error,
        min_editability_score=min_editability_score,
        max_fragmentation_penalty=max_fragmentation_penalty,
        max_raster_l1_error=max_raster_l1_error,
        max_raster_edge_error=max_raster_edge_error,
        max_anchor_quality_error=max_anchor_quality_error,
        require_applied_review=require_applied_review,
    )
    result.update(
        {
            "schema_version": 1,
            "source": "curated_suite",
            "suite": str(suite),
            "run_root": str(run_root_path),
            "curated_ok": bool(curated.get("ok", False)),
            "curated_case_count": int(curated.get("case_count", 0)),
            "curated_checked_count": sum(
                1
                for case in curated.get("cases", [])
                if isinstance(case, dict) and case.get("status") == "checked"
            ),
            "curated_missing_source_count": sum(
                1
                for case in curated.get("cases", [])
                if isinstance(case, dict) and case.get("status") == "missing_source"
            ),
            "applied_review_restored_count": len(restored_applied_reviews),
            "applied_review_restored_cases": restored_applied_reviews,
        }
    )
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    if markdown is not None:
        markdown_path = Path(markdown)
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(render_harvest_markdown(result), encoding="utf-8")
    return result


def _existing_applied_reviews(run_root: Path) -> dict[str, dict[str, object]]:
    reviews: dict[str, dict[str, object]] = {}
    for manifest_path in sorted(run_root.glob("*/manifest.json")):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            continue
        applied = _applied_review_decision(manifest)
        if applied:
            reviews[manifest_path.parent.name] = applied
    return reviews


def _restore_curated_applied_reviews(
    run_root: Path,
    curated: dict[str, object],
    applied_reviews: dict[str, dict[str, object]],
) -> list[str]:
    if not applied_reviews:
        return []
    restored: list[str] = []
    cases = curated.get("cases", [])
    if not isinstance(cases, list):
        cases = []
    for case in cases:
        if not isinstance(case, dict):
            continue
        case_id = case.get("id")
        if not isinstance(case_id, str) or case_id not in applied_reviews:
            continue
        applied = applied_reviews[case_id]
        case["review_decision_applied"] = applied
        manifest_path = run_root / case_id / "manifest.json"
        if manifest_path.exists():
            _write_manifest_applied_review(manifest_path, applied)
        restored.append(case_id)
    return restored


def _write_manifest_applied_review(
    manifest_path: Path,
    applied_review: dict[str, object],
) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        return
    manifest["review_decision_applied"] = applied_review
    apply_reviewed_region_promotions(manifest, applied_review)
    promotion = manifest.get("promotion")
    if isinstance(promotion, dict):
        promotion["review_decision_applied"] = applied_review
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _applied_review_decision(manifest: dict[str, object]) -> dict[str, object]:
    applied = manifest.get("review_decision_applied")
    if isinstance(applied, dict):
        return applied
    promotion = manifest.get("promotion")
    if isinstance(promotion, dict):
        applied = promotion.get("review_decision_applied")
        if isinstance(applied, dict):
            return applied
    return {}


def _applied_review_harvest_status(
    applied_review: dict[str, object],
) -> dict[str, object]:
    if not applied_review:
        return {
            "ok": False,
            "reason": "missing_applied_review",
            "decision": "n/a",
        }
    decision = applied_review.get("decision")
    if decision in {"accepted", "corrected"}:
        return {"ok": True, "reason": "accepted_applied_review", "decision": decision}
    if decision in {"rejected", "deferred"}:
        return {
            "ok": False,
            "reason": "applied_review_not_accepted",
            "decision": decision,
        }
    return {
        "ok": False,
        "reason": "invalid_applied_review_decision",
        "decision": str(decision),
    }


def _promotion_anchor_state_counts(
    manifest: dict[str, object],
) -> dict[str, int] | None:
    anchors = manifest.get("anchors")
    if not isinstance(anchors, list):
        return None
    counts: dict[str, int] = {}
    saw_promotion_state = False
    for anchor in anchors:
        if not isinstance(anchor, dict):
            continue
        state = anchor.get("promotion_state")
        if not isinstance(state, str) or not state:
            continue
        saw_promotion_state = True
        counts[state] = counts.get(state, 0) + 1
    if not saw_promotion_state:
        return None
    return dict(sorted(counts.items()))


def render_harvest_markdown(report: dict[str, object]) -> str:
    filters = report.get("filters", {})
    if not isinstance(filters, dict):
        filters = {}
    pseudo_labels = report.get("pseudo_labels", [])
    if not isinstance(pseudo_labels, list):
        pseudo_labels = []
    rejected_runs = report.get("rejected_runs", [])
    if not isinstance(rejected_runs, list):
        rejected_runs = []

    lines = [
        "# Morphēa Pseudo-Label Harvest",
        "",
        f"- Pseudo-labels: {_fmt_metric(report.get('pseudo_label_count'))}",
        f"- Rejected runs: {_fmt_metric(len(rejected_runs))}",
    ]
    if report.get("source") == "curated_suite":
        lines.extend(
            [
                f"- Suite: `{report.get('suite')}`",
                f"- Curated cases: {_fmt_metric(report.get('curated_case_count'))}",
                f"- Checked cases: {_fmt_metric(report.get('curated_checked_count'))}",
                f"- Missing sources: {_fmt_metric(report.get('curated_missing_source_count'))}",
                f"- Restored applied reviews: {_fmt_metric(report.get('applied_review_restored_count'))}",
            ]
        )
    lines.extend(
        [
            "",
            "## Filters",
            "",
            "| Gate | Value |",
            "| --- | ---: |",
        ]
    )
    for key in sorted(filters):
        lines.append(f"| `{key}` | {_fmt_metric(filters.get(key))} |")

    lines.extend(
        [
            "",
            "## Accepted Labels",
            "",
            "| Run | Anchor | Kind | Quality error | Source |",
            "| --- | ---: | --- | ---: | --- |",
        ]
    )
    if pseudo_labels:
        for label in pseudo_labels:
            if not isinstance(label, dict):
                continue
            group_context = label.get("group_context", [])
            lines.append(
                "| "
                f"`{label.get('run', 'n/a')}` | "
                f"{_fmt_metric(label.get('anchor_index'))} | "
                f"`{label.get('kind', 'n/a')}`"
                f"{_group_context_suffix(group_context)} | "
                f"{_fmt_metric(label.get('anchor_quality_error'))} | "
                f"`{label.get('source_manifest', 'n/a')}` |"
            )
    else:
        lines.append("| n/a | n/a | n/a | n/a | n/a |")

    lines.extend(
        [
            "",
            "## Rejected Runs",
            "",
            "| Run | Reason | Detail |",
            "| --- | --- | ---: |",
        ]
    )
    if rejected_runs:
        for rejected in rejected_runs:
            if not isinstance(rejected, dict):
                continue
            lines.append(
                "| "
                f"`{rejected.get('run', 'n/a')}` | "
                f"`{rejected.get('reason', 'n/a')}` | "
                f"{_rejection_detail_for_markdown(rejected)} |"
            )
    else:
        lines.append("| n/a | n/a | n/a |")
    return "\n".join(lines) + "\n"


def _rejection_detail_for_markdown(rejected: dict[str, object]) -> str:
    for key in (
        "diagnostic_count",
        "editability_score",
        "fragmentation_penalty",
        "raster_l1_error",
        "raster_edge_error",
        "promoted_anchor_count",
    ):
        if key in rejected:
            return _fmt_metric(rejected[key])
    return "n/a"


def _anchor_quality_error(metrics: object) -> float:
    if not isinstance(metrics, dict):
        return 0.0
    total = 0.0
    for key, value in metrics.items():
        if key == "classifier_prior_error":
            continue
        if key.endswith("_error") or key == "stroke_width_variance":
            total += float(value)
    return total


def _anchor_group_context(
    manifest: dict[str, object],
    anchor_index: int,
) -> list[dict[str, object]]:
    groups = manifest.get("groups", [])
    if not isinstance(groups, list):
        return []
    context = []
    for group_index, group in enumerate(groups):
        if not isinstance(group, dict):
            continue
        anchor_indexes = group.get("anchor_indexes", [])
        if not isinstance(anchor_indexes, list) or anchor_index not in anchor_indexes:
            continue
        context.append(
            {
                "id": group.get("id", f"group-{group_index:04d}"),
                "kind": group.get("kind"),
                "anchor_indexes": anchor_indexes,
                "anchor_position": anchor_indexes.index(anchor_index),
                "metrics": group.get("metrics", {}),
                "color": group.get("color"),
            }
        )
    return context


def _source_image_from_manifest_path(manifest_path: Path) -> Path | None:
    input_dir = manifest_path.parent / "input"
    if not input_dir.is_dir():
        return None
    files = sorted(path for path in input_dir.iterdir() if path.is_file())
    if len(files) != 1:
        return None
    return files[0]


def _group_context_suffix(value: object) -> str:
    if not isinstance(value, list) or not value:
        return ""
    kinds = sorted(
        {
            str(group.get("kind"))
            for group in value
            if isinstance(group, dict) and group.get("kind") is not None
        }
    )
    if not kinds:
        return ""
    return f" ({', '.join(kinds)})"


def _format_group_context(value: object) -> str:
    if not isinstance(value, list) or not value:
        return "n/a"
    parts = []
    for group in value:
        if not isinstance(group, dict):
            continue
        kind = group.get("kind")
        if kind is None:
            continue
        position = group.get("anchor_position")
        suffix = f"#{position}" if isinstance(position, int) else ""
        parts.append(f"`{kind}{suffix}`")
    return ", ".join(parts) if parts else "n/a"


def _rejected_group_context(item: dict[str, object]) -> str:
    label = item.get("label", {})
    if not isinstance(label, dict):
        return "n/a"
    return _format_group_context(label.get("group_context", []))


def compare_retraining(
    *,
    base_dataset: str | Path,
    pseudo_dataset: str | Path,
    output: str | Path,
    validation_dataset: str | Path | None = None,
    markdown: str | Path | None = None,
) -> dict[str, object]:
    """Compare baseline training against reviewed pseudo-label augmentation."""

    validation_source = validation_dataset or base_dataset
    baseline_train = examples_from_dataset(base_dataset, splits=("train",))
    pseudo_train = examples_from_dataset(pseudo_dataset, splits=("train",))
    augmented_train = baseline_train + pseudo_train

    baseline = _training_comparison_model(
        train_examples=baseline_train,
        validation_dataset=validation_source,
    )
    augmented = _training_comparison_model(
        train_examples=augmented_train,
        validation_dataset=validation_source,
    )
    delta = _training_comparison_delta(baseline, augmented)
    result = {
        "schema_version": 1,
        "base_dataset": str(base_dataset),
        "pseudo_dataset": str(pseudo_dataset),
        "validation_dataset": str(validation_source),
        "baseline": baseline,
        "augmented": augmented,
        "delta": delta,
        "summary": _training_comparison_summary(delta),
    }
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    if markdown is not None:
        markdown_path = Path(markdown)
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(
            render_training_comparison_markdown(result),
            encoding="utf-8",
        )
    return result


def gate_training_comparison(
    *,
    comparison: str | Path,
    output: str | Path,
    markdown: str | Path | None = None,
    min_train_examples_delta: int = 1,
    min_best_accuracy_delta: float = 0.0,
    max_worst_accuracy_drop: float = 0.0,
    allow_unchanged: bool = False,
) -> dict[str, object]:
    report = json.loads(Path(comparison).read_text(encoding="utf-8"))
    summary = report.get("summary", {})
    if not isinstance(summary, dict):
        summary = {}
    metric_delta_summary = _training_gate_metric_delta_summary(report)
    reasons: list[str] = []
    reject = False
    manual_review = False

    train_delta = summary.get("train_examples_delta")
    if not isinstance(train_delta, int) or train_delta < min_train_examples_delta:
        reject = True
        reasons.append("train_examples_delta_below_min")

    best_delta = summary.get("best_accuracy_delta")
    if not isinstance(best_delta, (int, float)):
        manual_review = True
        reasons.append("missing_best_accuracy_delta")
    elif float(best_delta) < min_best_accuracy_delta:
        reject = True
        reasons.append("best_accuracy_delta_below_min")

    worst_delta = summary.get("worst_accuracy_delta")
    if not isinstance(worst_delta, (int, float)):
        manual_review = True
        reasons.append("missing_worst_accuracy_delta")
    elif float(worst_delta) < -max_worst_accuracy_drop:
        reject = True
        reasons.append("worst_accuracy_delta_below_tolerance")

    status = summary.get("status")
    if status == "regressed":
        reject = True
        reasons.append("comparison_status_regressed")
    elif status == "mixed":
        manual_review = True
        reasons.append("comparison_status_mixed")
    elif status == "unchanged" and not allow_unchanged:
        manual_review = True
        reasons.append("comparison_status_unchanged")
    elif status not in {"improved", "unchanged", "mixed", "regressed"}:
        manual_review = True
        reasons.append("comparison_status_insufficient")

    if reject:
        decision = "reject"
    elif manual_review:
        decision = "manual_review"
    else:
        decision = "accept"

    result = {
        "schema_version": 1,
        "comparison": str(comparison),
        "decision": decision,
        "accepted": decision == "accept",
        "reasons": reasons,
        "gates": {
            "min_train_examples_delta": min_train_examples_delta,
            "min_best_accuracy_delta": min_best_accuracy_delta,
            "max_worst_accuracy_drop": max_worst_accuracy_drop,
            "allow_unchanged": allow_unchanged,
        },
        "summary": summary,
        "metric_delta_summary": metric_delta_summary,
    }
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    if markdown is not None:
        markdown_path = Path(markdown)
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(render_training_gate_markdown(result), encoding="utf-8")
    return result


def render_training_gate_markdown(result: dict[str, object]) -> str:
    gates = result.get("gates", {})
    if not isinstance(gates, dict):
        gates = {}
    summary = result.get("summary", {})
    if not isinstance(summary, dict):
        summary = {}
    reasons = result.get("reasons", [])
    if not isinstance(reasons, list):
        reasons = []
    lines = [
        "# Morphēa Training Gate",
        "",
        f"- Decision: `{result.get('decision', 'n/a')}`",
        f"- Accepted: `{result.get('accepted', False)}`",
        f"- Comparison: `{result.get('comparison', 'n/a')}`",
        f"- Comparison status: `{summary.get('status', 'n/a')}`",
        f"- Train example delta: {_fmt_metric(summary.get('train_examples_delta'))}",
        f"- Best accuracy delta: {_fmt_metric(summary.get('best_accuracy_delta'))}",
        f"- Worst accuracy delta: {_fmt_metric(summary.get('worst_accuracy_delta'))}",
        "",
        "## Gates",
        "",
        "| Gate | Value |",
        "| --- | ---: |",
    ]
    for key in sorted(gates):
        lines.append(f"| `{key}` | {_fmt_gate_value(gates.get(key))} |")
    lines.extend(
        [
            "",
            "## Reasons",
            "",
            ", ".join(f"`{reason}`" for reason in reasons) if reasons else "n/a",
        ]
    )
    metric_delta_rows = _training_gate_metric_delta_markdown_rows(
        result.get("metric_delta_summary")
    )
    if metric_delta_rows:
        lines.extend(
            [
                "",
                "## Metric Contributors",
                "",
                "| Direction | Metric | Split | Label | Delta |",
                "| --- | --- | --- | --- | ---: |",
            ]
        )
        lines.extend(metric_delta_rows)
    return "\n".join(lines) + "\n"


def _fmt_gate_value(value: object) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    return _fmt_metric(value)


def _training_gate_metric_delta_summary(
    report: dict[str, object],
    *,
    limit: int = 5,
) -> dict[str, object]:
    delta = report.get("delta", {})
    if not isinstance(delta, dict):
        return {"worst": [], "best": []}
    rows = _comparison_metric_delta_rows(delta)
    if not rows:
        return {"worst": [], "best": []}
    worst = sorted(
        rows,
        key=lambda item: (
            float(item.get("delta", 0.0)),
            str(item.get("metric", "")),
            str(item.get("split", "")),
            str(item.get("label", "")),
        ),
    )
    best = sorted(
        rows,
        key=lambda item: (
            -float(item.get("delta", 0.0)),
            str(item.get("metric", "")),
            str(item.get("split", "")),
            str(item.get("label", "")),
        ),
    )
    return {
        "worst": worst[:limit],
        "best": best[:limit],
    }


def _training_gate_metric_delta_markdown_rows(value: object) -> list[str]:
    if not isinstance(value, dict):
        return []
    rows = []
    for direction in ("worst", "best"):
        items = value.get(direction, [])
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            rows.append(
                "| "
                f"`{direction}` | "
                f"`{_metric_delta_cell(item.get('metric'))}` | "
                f"`{_metric_delta_cell(item.get('split'))}` | "
                f"`{_metric_delta_cell(item.get('label'))}` | "
                f"{_fmt_metric(item.get('delta'))} |"
            )
    return rows


def _metric_delta_cell(value: object) -> str:
    if isinstance(value, str) and value:
        return value
    return "n/a"


def run_self_learning_cycle(
    *,
    base_dataset: str | Path,
    reviewed_labels: str | Path,
    output_dir: str | Path,
    validation_dataset: str | Path | None = None,
    curated_suite: str | Path | None = None,
    curated_output_dir: str | Path | None = None,
    curated_report: str | Path | None = None,
    curated_snapshot: str | Path | None = None,
    lucide_suite: str | Path | None = None,
    lucide_output_dir: str | Path | None = None,
    lucide_report: str | Path | None = None,
    suite_family_baseline: str | Path | None = None,
    suite_family_baseline_output: str | Path | None = None,
    suite_family_baseline_reviewer: str = "",
    suite_family_baseline_reason: str = "",
    suite_family_baseline_changelog: str | Path | None = None,
    min_train_examples_delta: int = 1,
    min_best_accuracy_delta: float = 0.0,
    max_worst_accuracy_drop: float = 0.0,
    min_mlx_raster_pseudo_examples: int = 0,
    allow_unchanged: bool = False,
    backend: str = "centroid",
    mlx_config: MlxClassifierTrainingConfig | None = None,
    markdown: str | Path | None = None,
) -> dict[str, object]:
    """Run the reviewed-label retraining decision loop as one repeatable cycle."""

    if backend not in {"centroid", "mlx"}:
        raise ValueError("self-learning backend must be one of: centroid, mlx")

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    pseudo_dir = output / "pseudo-dataset"
    comparison_path = output / "comparison.json"
    comparison_markdown = output / "comparison.md"
    gate_path = output / "gate.json"
    gate_markdown = output / "gate.md"
    model_path = output / "model.json"
    curated_report_path = (
        Path(curated_report)
        if curated_report is not None
        else output / "curated-validation.json"
    )
    curated_snapshot_path = (
        Path(curated_snapshot)
        if curated_snapshot is not None
        else output / "curated-validation-snapshot.json"
    )
    curated_output_path = (
        Path(curated_output_dir)
        if curated_output_dir is not None
        else output / "curated-validation-runs"
    )
    lucide_report_path = (
        Path(lucide_report)
        if lucide_report is not None
        else output / "lucide-validation.json"
    )
    lucide_output_path = (
        Path(lucide_output_dir)
        if lucide_output_dir is not None
        else output / "lucide-validation-runs"
    )
    suite_family_baseline_output_path = (
        Path(suite_family_baseline_output)
        if suite_family_baseline_output is not None
        else None
    )
    suite_family_baseline_changelog_path = (
        Path(suite_family_baseline_changelog)
        if suite_family_baseline_changelog is not None
        else None
    )

    pseudo_dataset = merge_reviewed_pseudo_label_dataset(
        reviewed_labels=reviewed_labels,
        output_dir=pseudo_dir,
    )
    comparison = compare_retraining(
        base_dataset=base_dataset,
        pseudo_dataset=pseudo_dir / "dataset.json",
        validation_dataset=validation_dataset,
        output=comparison_path,
        markdown=comparison_markdown,
    )
    gate = gate_training_comparison(
        comparison=comparison_path,
        output=gate_path,
        markdown=gate_markdown,
        min_train_examples_delta=min_train_examples_delta,
        min_best_accuracy_delta=min_best_accuracy_delta,
        max_worst_accuracy_drop=max_worst_accuracy_drop,
        allow_unchanged=allow_unchanged,
    )
    model: dict[str, object] | None = None
    if gate["accepted"]:
        if backend == "mlx":
            model = retrain_mlx_classifier(
                base_dataset=base_dataset,
                pseudo_dataset=pseudo_dir / "dataset.json",
                validation_dataset=validation_dataset,
                output=model_path,
                config=mlx_config,
            )
        else:
            model = retrain_centroid_classifier(
                base_dataset=base_dataset,
                pseudo_dataset=pseudo_dir / "dataset.json",
                validation_dataset=validation_dataset,
                output=model_path,
            )
    curated_validation: dict[str, object] | None = None
    if curated_suite is not None:
        if model is not None:
            curated = check_curated_suite(
                curated_suite,
                output=curated_report_path,
                output_dir=curated_output_path,
                run=True,
                snapshot=curated_snapshot_path,
                config_overrides={"classifier_model": model_path},
            )
            curated_validation = _curated_validation_summary(curated, curated_suite)
        else:
            curated_validation = {
                "status": "skipped_gate_not_accepted",
                "suite": str(curated_suite),
                "ok": None,
                "case_count": 0,
                "checked_count": 0,
                "missing_source_count": 0,
                "family_summary": {},
            }

    lucide_validation: dict[str, object] | None = None
    if lucide_suite is not None:
        if model is not None:
            lucide = check_lucide_suite(
                lucide_suite,
                output=lucide_report_path,
                output_dir=lucide_output_path,
                config_overrides={"classifier_model": model_path},
            )
            lucide_validation = _lucide_validation_summary(lucide, lucide_suite)
        else:
            lucide_validation = {
                "status": "skipped_gate_not_accepted",
                "suite": str(lucide_suite),
                "ok": None,
                "case_count": 0,
                "checked_count": 0,
                "failed_count": 0,
                "family_summary": {},
            }

    suite_family_validation = _suite_family_validation_summary(
        comparison=comparison,
        curated_validation=curated_validation,
        lucide_validation=lucide_validation,
    )
    suite_family_baseline_comparison = _compare_suite_family_validation_to_baseline(
        suite_family_validation,
        suite_family_baseline,
    )
    acceptance_gate = _self_learning_acceptance_gate(
        gate=gate,
        model=model,
        backend=backend,
        min_mlx_raster_pseudo_examples=min_mlx_raster_pseudo_examples,
        curated_validation=curated_validation,
        curated_required=curated_suite is not None,
        lucide_validation=lucide_validation,
        lucide_required=lucide_suite is not None,
        suite_family_baseline_comparison=suite_family_baseline_comparison,
    )
    summary_path = output / "self-learning-cycle.json"
    markdown_path = (
        Path(markdown) if markdown is not None else output / "self-learning-cycle.md"
    )
    suite_family_baseline_snapshot = _write_suite_family_baseline_snapshot(
        output=suite_family_baseline_output_path,
        baseline_source=Path(suite_family_baseline)
        if suite_family_baseline is not None
        else None,
        accepted=bool(acceptance_gate["accepted"]),
        suite_family_validation=suite_family_validation,
        changelog=suite_family_baseline_changelog_path,
        review={
            "reviewer": suite_family_baseline_reviewer,
            "reason": suite_family_baseline_reason,
        },
    )
    result = {
        "schema_version": 1,
        "status": "retrained" if model is not None else "skipped_retrain",
        "accepted": acceptance_gate["accepted"],
        "base_dataset": str(base_dataset),
        "reviewed_labels": str(reviewed_labels),
        "validation_dataset": str(validation_dataset or base_dataset),
        "training_backend": backend,
        "min_mlx_raster_pseudo_examples": min_mlx_raster_pseudo_examples,
        "output_dir": str(output),
        "artifacts": {
            "pseudo_dataset": str(pseudo_dir / "dataset.json"),
            "comparison": str(comparison_path),
            "comparison_markdown": str(comparison_markdown),
            "gate": str(gate_path),
            "gate_markdown": str(gate_markdown),
            "model": str(model_path) if model is not None else None,
            "curated_report": (
                str(curated_report_path)
                if curated_validation is not None and model is not None
                else None
            ),
            "curated_snapshot": (
                str(curated_snapshot_path)
                if curated_validation is not None and model is not None
                else None
            ),
            "curated_output_dir": (
                str(curated_output_path)
                if curated_validation is not None and model is not None
                else None
            ),
            "lucide_report": (
                str(lucide_report_path)
                if lucide_validation is not None and model is not None
                else None
            ),
            "lucide_output_dir": (
                str(lucide_output_path)
                if lucide_validation is not None and model is not None
                else None
            ),
            "suite_family_baseline_snapshot": (
                suite_family_baseline_snapshot.get("output")
                if suite_family_baseline_snapshot.get("status") == "written"
                else None
            ),
            "summary": str(summary_path),
            "summary_markdown": str(markdown_path),
        },
        "pseudo_dataset": {
            "count": pseudo_dataset["count"],
            "splits": pseudo_dataset["splits"],
            "reviewed_label_summary": pseudo_dataset.get(
                "reviewed_label_summary",
                {},
            ),
        },
        "comparison_summary": comparison["summary"],
        "gate": {
            "decision": gate["decision"],
            "accepted": gate["accepted"],
            "reasons": gate["reasons"],
        },
        "acceptance_gate": acceptance_gate,
        "model": (
            _self_learning_model_summary(model, backend)
            if model is not None
            else None
        ),
        "curated_validation": curated_validation,
        "lucide_validation": lucide_validation,
        "suite_family_validation": suite_family_validation,
        "suite_family_baseline_comparison": suite_family_baseline_comparison,
        "suite_family_baseline_snapshot": suite_family_baseline_snapshot,
    }
    result["reviewed_label_loop_audit"] = _reviewed_label_loop_audit(result)
    result["multi_family_regression_audit"] = _multi_family_regression_audit(result)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(
        render_self_learning_cycle_markdown(result),
        encoding="utf-8",
    )
    summary_path.write_text(
        json.dumps(result, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return result


def _self_learning_model_summary(
    model: dict[str, object],
    backend: str,
) -> dict[str, object]:
    summary = {
        "model_type": model["model_type"],
        "train_examples": model["train_examples"],
        "retraining_backend": model.get("retraining_backend", backend),
        "status": model.get("status", "trained"),
        "training_implementation": model.get("training_implementation"),
        "augmentation": model["augmentation"],
    }
    component_summary = _model_training_component_summary(model)
    if component_summary is not None:
        summary["training_component_summary"] = component_summary
    source_summary = model.get("training_source_summary")
    if isinstance(source_summary, dict):
        summary["training_source_summary"] = source_summary
    return summary


def _model_training_component_summary(
    model: dict[str, object],
) -> dict[str, object] | None:
    training = model.get("mlx_training")
    if not isinstance(training, dict):
        return None
    component_summary = training.get("component_summary")
    if isinstance(component_summary, dict):
        return component_summary
    return None


def _curated_validation_summary(
    report: dict[str, object],
    suite: str | Path,
) -> dict[str, object]:
    cases = _report_cases(report)
    return {
        "status": "checked",
        "suite": str(suite),
        "ok": report.get("ok"),
        "case_count": report.get("case_count", len(cases)),
        "checked_count": _case_status_count(cases, "checked"),
        "missing_source_count": _case_status_count(cases, "missing_source"),
        "family_summary": _family_summary_from_report(report, cases),
    }


def _lucide_validation_summary(
    report: dict[str, object],
    suite: str | Path,
) -> dict[str, object]:
    cases = _report_cases(report)
    return {
        "status": "checked",
        "suite": str(suite),
        "ok": report.get("ok"),
        "case_count": report.get("case_count", len(cases)),
        "checked_count": _case_status_count(cases, "checked"),
        "failed_count": report.get("failed_count", _failed_case_count(cases)),
        "family_summary": _family_summary_from_report(report, cases),
    }


def _suite_family_validation_summary(
    *,
    comparison: dict[str, object],
    curated_validation: dict[str, object] | None,
    lucide_validation: dict[str, object] | None,
) -> dict[str, object]:
    return {
        "primitive": _primitive_family_validation(comparison),
        "real_image": _suite_validation_view(curated_validation),
        "lucide": _suite_validation_view(lucide_validation),
    }


def _compare_suite_family_validation_to_baseline(
    current: dict[str, object],
    baseline_path: str | Path | None,
) -> dict[str, object] | None:
    if baseline_path is None:
        return None
    baseline_file = Path(baseline_path)
    baseline_data = json.loads(baseline_file.read_text(encoding="utf-8"))
    baseline = _suite_family_validation_from_baseline(baseline_data)
    baseline_rows = _suite_family_outcomes_by_key(baseline)
    current_rows = _suite_family_outcomes_by_key(current)
    comparisons = []
    new_regressions = []
    resolved_regressions = []
    known_debt = []
    missing_current_families = []
    for key in sorted(set(current_rows) | set(baseline_rows)):
        current_row = current_rows.get(key)
        baseline_row = baseline_rows.get(key)
        current_outcome = current_row.get("outcome") if current_row else None
        baseline_outcome = baseline_row.get("outcome") if baseline_row else None
        row = current_row or _missing_current_family_row(baseline_row)
        status = _suite_family_baseline_comparison_status(
            current_outcome=current_outcome,
            baseline_outcome=baseline_outcome,
            has_current=current_row is not None,
            has_baseline=baseline_row is not None,
        )
        comparison = _baseline_comparison_row(row, baseline_outcome)
        comparison["status"] = status
        comparisons.append(comparison)
        if status == "new_regression":
            new_regressions.append(comparison)
        elif status == "known_debt":
            known_debt.append(comparison)
        elif status == "resolved_regression":
            resolved_regressions.append(comparison)
        elif status == "missing_current_family":
            missing_current_families.append(comparison)
    return {
        "status": "checked",
        "baseline": str(baseline_file),
        "ok": not new_regressions and not missing_current_families,
        "comparison_count": len(comparisons),
        "comparison_outcome_counts": _suite_family_comparison_counts(comparisons),
        "new_regression_count": len(new_regressions),
        "resolved_regression_count": len(resolved_regressions),
        "known_debt_count": len(known_debt),
        "missing_current_family_count": len(missing_current_families),
        "comparisons": comparisons,
        "new_regressions": new_regressions,
        "resolved_regressions": resolved_regressions,
        "known_debt": known_debt,
        "missing_current_families": missing_current_families,
    }


def _suite_family_validation_from_baseline(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    nested = value.get("suite_family_validation")
    if isinstance(nested, dict):
        return nested
    return value


def _write_suite_family_baseline_snapshot(
    *,
    output: Path | None,
    baseline_source: Path | None,
    accepted: bool,
    suite_family_validation: dict[str, object],
    changelog: Path | None,
    review: dict[str, object],
) -> dict[str, object]:
    if output is None:
        return {"status": "not_configured", "output": None}
    if not accepted:
        return {
            "status": "skipped_not_accepted",
            "output": str(output),
            "changelog": str(changelog) if changelog is not None else None,
            "review": _suite_family_baseline_review(review),
        }
    normalized_review = _suite_family_baseline_review(review)
    missing_review_fields = _missing_suite_family_baseline_review_fields(
        normalized_review,
        changelog,
    )
    if missing_review_fields:
        return {
            "status": "skipped_missing_review_evidence",
            "output": str(output),
            "changelog": str(changelog) if changelog is not None else None,
            "missing_review_fields": missing_review_fields,
            "review": normalized_review,
        }
    if output.exists() and not _baseline_output_matches_source(
        output,
        baseline_source,
    ):
        return {
            "status": "skipped_existing_output_requires_matching_baseline",
            "output": str(output),
            "baseline_source": str(baseline_source) if baseline_source else None,
            "changelog": str(changelog) if changelog is not None else None,
            "review": normalized_review,
        }
    coverage_regressions = _suite_family_baseline_coverage_regressions(
        suite_family_validation,
        baseline_source,
    )
    if coverage_regressions:
        return {
            "status": "skipped_coverage_regression",
            "output": str(output),
            "baseline_source": str(baseline_source) if baseline_source else None,
            "changelog": str(changelog) if changelog is not None else None,
            "review": normalized_review,
            "coverage_regressions": coverage_regressions,
        }
    output.parent.mkdir(parents=True, exist_ok=True)
    snapshot = {
        "schema_version": 1,
        "source": "self_learning_cycle",
        "accepted": True,
        "review": normalized_review,
        "suite_family_validation": suite_family_validation,
    }
    output.write_text(
        json.dumps(snapshot, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    changelog_entry = {
        "schema_version": 1,
        "action": "suite_family_baseline_updated",
        "baseline_snapshot": str(output),
        "review": normalized_review,
        "family_count": _suite_family_validation_family_count(
            suite_family_validation,
        ),
    }
    assert changelog is not None
    changelog.parent.mkdir(parents=True, exist_ok=True)
    with changelog.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(changelog_entry, sort_keys=True) + "\n")
    return {
        "status": "written",
        "output": str(output),
        "baseline_source": str(baseline_source) if baseline_source else None,
        "changelog": str(changelog),
        "review": normalized_review,
    }


def _baseline_output_matches_source(
    output: Path,
    baseline_source: Path | None,
) -> bool:
    if baseline_source is None:
        return False
    return output.resolve() == baseline_source.resolve()


def _suite_family_baseline_coverage_regressions(
    current: dict[str, object],
    baseline_source: Path | None,
) -> list[dict[str, object]]:
    if baseline_source is None or not baseline_source.exists():
        return []
    baseline_data = json.loads(baseline_source.read_text(encoding="utf-8"))
    baseline = _suite_family_validation_from_baseline(baseline_data)
    baseline_rows = _suite_family_outcomes_by_key(baseline)
    current_rows = _suite_family_outcomes_by_key(current)
    regressions = []
    for key, baseline_row in sorted(baseline_rows.items()):
        suite_name, split, family = key
        current_row = current_rows.get(key)
        if not isinstance(current_row, dict):
            continue
        for metric in _suite_family_coverage_metrics(suite_name):
            baseline_value = _numeric_metric(baseline_row.get(metric))
            current_value = _numeric_metric(current_row.get(metric))
            if (
                baseline_value is not None
                and current_value is not None
                and current_value < baseline_value
            ):
                regressions.append(
                    {
                        "suite": suite_name,
                        "split": split,
                        "family": family,
                        "metric": metric,
                        "baseline": baseline_value,
                        "current": current_value,
                    }
                )
    return regressions


def _suite_family_coverage_metrics(suite_name: str) -> tuple[str, ...]:
    if suite_name == "primitive":
        return ("baseline_examples", "augmented_examples")
    return ("case_count", "checked_count")


def _numeric_metric(value: object) -> int | float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    return None


def _suite_family_baseline_review(review: dict[str, object]) -> dict[str, object]:
    return {
        "reviewer": str(review.get("reviewer", "")).strip(),
        "reason": str(review.get("reason", "")).strip(),
    }


def _missing_suite_family_baseline_review_fields(
    review: dict[str, object],
    changelog: Path | None,
) -> list[str]:
    missing = []
    for key in ("reviewer", "reason"):
        value = review.get(key)
        if not isinstance(value, str) or not value:
            missing.append(key)
    if changelog is None:
        missing.append("changelog")
    return missing


def _suite_family_validation_family_count(validation: dict[str, object]) -> int:
    count = 0
    for suite in validation.values():
        if not isinstance(suite, dict):
            continue
        families = suite.get("families", [])
        if isinstance(families, list):
            count += sum(1 for item in families if isinstance(item, dict))
    return count


def _suite_family_outcomes_by_key(
    validation: dict[str, object],
) -> dict[tuple[str, str, str], dict[str, object]]:
    rows: dict[tuple[str, str, str], dict[str, object]] = {}
    for suite_name, suite in validation.items():
        if not isinstance(suite_name, str) or not isinstance(suite, dict):
            continue
        families = suite.get("families", [])
        if not isinstance(families, list):
            continue
        for family in families:
            if not isinstance(family, dict):
                continue
            family_name = family.get("family")
            if not isinstance(family_name, str) or not family_name:
                continue
            split = family.get("split") if suite_name == "primitive" else None
            key = (
                suite_name,
                str(split) if isinstance(split, str) and split else "",
                family_name,
            )
            row = dict(family)
            row["suite"] = suite_name
            row["split"] = key[1]
            rows[key] = row
    return rows


def _suite_family_baseline_comparison_status(
    *,
    current_outcome: object,
    baseline_outcome: object,
    has_current: bool,
    has_baseline: bool,
) -> str:
    current_bad = _is_bad_family_outcome(current_outcome)
    baseline_bad = _is_bad_family_outcome(baseline_outcome)
    if has_baseline and not has_current:
        return "resolved_regression" if baseline_bad else "missing_current_family"
    if has_current and not has_baseline:
        return "new_regression" if current_bad else "new_family"
    if current_bad and baseline_bad:
        return "known_debt"
    if current_bad:
        return "new_regression"
    if baseline_bad:
        return "resolved_regression"
    if current_outcome == "improved":
        return "improved"
    if current_outcome in {"held", "passed"} and current_outcome == baseline_outcome:
        return "held"
    if current_outcome == "held":
        return "held"
    if current_outcome == "passed":
        return "held"
    return "changed"


def _missing_current_family_row(
    baseline_row: dict[str, object] | None,
) -> dict[str, object]:
    if not isinstance(baseline_row, dict):
        return {}
    return {
        "suite": baseline_row.get("suite"),
        "split": baseline_row.get("split"),
        "family": baseline_row.get("family"),
        "outcome": None,
    }


def _suite_family_comparison_counts(
    comparisons: list[dict[str, object]],
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for comparison in comparisons:
        status = comparison.get("status")
        if not isinstance(status, str) or not status:
            continue
        counts[status] = counts.get(status, 0) + 1
    return dict(sorted(counts.items()))


def _baseline_comparison_row(
    row: dict[str, object],
    baseline_outcome: object,
) -> dict[str, object]:
    result = {
        "suite": row.get("suite"),
        "split": row.get("split"),
        "family": row.get("family"),
        "baseline_outcome": baseline_outcome,
        "current_outcome": row.get("outcome"),
    }
    for key in (
        "accuracy_delta",
        "case_count",
        "checked_count",
        "passed_count",
        "failed_count",
        "missing_source_count",
        "pipeline_quality_counts",
    ):
        if key in row:
            result[key] = row.get(key)
    return result


def _is_bad_family_outcome(value: object) -> bool:
    return value in {"regressed", "failed", "failed_missing", "missing"}


def _primitive_family_validation(report: dict[str, object]) -> dict[str, object]:
    delta = report.get("delta", {})
    label_accuracy = {}
    if isinstance(delta, dict):
        value = delta.get("label_accuracy", {})
        if isinstance(value, dict):
            label_accuracy = value
    families: list[dict[str, object]] = []
    for split, split_data in sorted(label_accuracy.items()):
        if not isinstance(split_data, dict):
            continue
        for family, item in sorted(split_data.items()):
            if not isinstance(item, dict):
                continue
            accuracy_delta = item.get("accuracy_delta")
            families.append(
                {
                    "split": str(split),
                    "family": str(family),
                    "baseline_accuracy": item.get("baseline_accuracy"),
                    "augmented_accuracy": item.get("augmented_accuracy"),
                    "accuracy_delta": accuracy_delta,
                    "baseline_examples": item.get("baseline_examples"),
                    "augmented_examples": item.get("augmented_examples"),
                    "outcome": _accuracy_delta_outcome(accuracy_delta),
                }
            )
    return {
        "status": _family_validation_status(families),
        "ok": _families_have_no_regressions(families) if families else None,
        "families": families,
    }


def _suite_validation_view(
    validation: dict[str, object] | None,
) -> dict[str, object]:
    if not isinstance(validation, dict):
        return {"status": "not_configured", "ok": None, "families": []}
    families = []
    family_summary = validation.get("family_summary", {})
    if isinstance(family_summary, dict):
        for family, summary in sorted(family_summary.items()):
            if not isinstance(summary, dict):
                continue
            family_row = {
                "family": str(family),
                "case_count": summary.get("case_count"),
                "checked_count": summary.get("checked_count"),
                "passed_count": summary.get("passed_count"),
                "failed_count": summary.get("failed_count"),
                "missing_source_count": summary.get("missing_source_count"),
                "outcome": _suite_family_outcome(summary),
            }
            pipeline_counts = _counts_from_object(
                summary.get("pipeline_quality_counts")
            )
            if pipeline_counts:
                family_row["pipeline_quality_counts"] = pipeline_counts
            families.append(family_row)
    return {
        "status": validation.get("status", "n/a"),
        "ok": validation.get("ok"),
        "suite": validation.get("suite"),
        "families": families,
    }


def _family_summary_from_report(
    report: dict[str, object],
    cases: list[dict[str, object]],
) -> dict[str, dict[str, object]]:
    summary = report.get("family_summary")
    if isinstance(summary, dict) and summary:
        normalized: dict[str, dict[str, object]] = {}
        has_pipeline_counts = False
        for family, item in summary.items():
            if not isinstance(item, dict):
                continue
            case_count = _int_count(item.get("case_count"))
            normalized_item: dict[str, object] = {
                "case_count": case_count,
                "checked_count": (
                    _int_count(item.get("checked_count"))
                    if "checked_count" in item
                    else case_count
                ),
                "passed_count": _int_count(item.get("passed_count")),
                "failed_count": _int_count(item.get("failed_count")),
                "missing_source_count": _int_count(item.get("missing_source_count")),
            }
            pipeline_counts = _counts_from_object(
                item.get("pipeline_quality_counts")
            )
            if pipeline_counts:
                normalized_item["pipeline_quality_counts"] = pipeline_counts
                has_pipeline_counts = True
            normalized[str(family)] = normalized_item
        if not has_pipeline_counts:
            _attach_pipeline_quality_counts(normalized, cases)
        return dict(sorted(normalized.items()))
    return _family_summary_from_cases(cases)


def _family_summary_from_cases(
    cases: list[dict[str, object]],
) -> dict[str, dict[str, object]]:
    summary: dict[str, dict[str, object]] = {}
    for case in cases:
        family = _case_family(case)
        item = summary.setdefault(
            family,
            {
                "case_count": 0,
                "checked_count": 0,
                "passed_count": 0,
                "failed_count": 0,
                "missing_source_count": 0,
            },
        )
        item["case_count"] += 1
        if case.get("status") == "checked":
            item["checked_count"] += 1
        if case.get("ok"):
            item["passed_count"] += 1
        else:
            item["failed_count"] += 1
        if case.get("status") == "missing_source":
            item["missing_source_count"] += 1
    _attach_pipeline_quality_counts(summary, cases)
    return dict(sorted(summary.items()))


def _attach_pipeline_quality_counts(
    summary: dict[str, dict[str, object]],
    cases: list[dict[str, object]],
) -> None:
    for case in cases:
        label = case.get("pipeline_quality_label")
        if not isinstance(label, str) or not label:
            continue
        item = summary.get(_case_family(case))
        if not isinstance(item, dict):
            continue
        counts = item.setdefault("pipeline_quality_counts", {})
        if not isinstance(counts, dict):
            counts = {}
            item["pipeline_quality_counts"] = counts
        counts[label] = _int_count(counts.get(label)) + 1
    for item in summary.values():
        counts = _counts_from_object(item.get("pipeline_quality_counts"))
        if counts:
            item["pipeline_quality_counts"] = counts
        else:
            item.pop("pipeline_quality_counts", None)


def _case_family(case: dict[str, object]) -> str:
    family = case.get("family")
    if isinstance(family, str) and family:
        return family
    promotion = case.get("promotion")
    if isinstance(promotion, dict):
        stress_family = promotion.get("stress_family")
        if isinstance(stress_family, str) and stress_family:
            return stress_family
    return "unknown"


def _report_cases(report: dict[str, object]) -> list[dict[str, object]]:
    cases = report.get("cases", [])
    if not isinstance(cases, list):
        return []
    return [case for case in cases if isinstance(case, dict)]


def _case_status_count(cases: list[dict[str, object]], status: str) -> int:
    return sum(1 for case in cases if case.get("status") == status)


def _failed_case_count(cases: list[dict[str, object]]) -> int:
    return sum(1 for case in cases if case.get("ok") is not True)


def _int_count(value: object) -> int:
    return int(value) if isinstance(value, (int, float)) else 0


def _accuracy_delta_outcome(value: object) -> str:
    if not isinstance(value, (int, float)):
        return "insufficient"
    if float(value) > 0:
        return "improved"
    if float(value) < 0:
        return "regressed"
    return "held"


def _family_validation_status(families: list[dict[str, object]]) -> str:
    outcomes = {str(family.get("outcome")) for family in families}
    if not families or outcomes == {"insufficient"}:
        return "insufficient"
    if "regressed" in outcomes:
        return "regressed"
    if "improved" in outcomes:
        return "improved"
    if outcomes <= {"held", "insufficient"}:
        return "held"
    return "mixed"


def _families_have_no_regressions(families: list[dict[str, object]]) -> bool:
    return all(family.get("outcome") != "regressed" for family in families)


def _suite_family_outcome(summary: dict[str, object]) -> str:
    failed_count = _int_count(summary.get("failed_count"))
    missing_count = _int_count(summary.get("missing_source_count"))
    if failed_count > 0 and missing_count > 0:
        return "failed_missing"
    if failed_count > 0:
        return "failed"
    if missing_count > 0:
        return "missing"
    return "passed"


def _self_learning_acceptance_gate(
    *,
    gate: dict[str, object],
    model: dict[str, object] | None,
    backend: str,
    min_mlx_raster_pseudo_examples: int,
    curated_validation: dict[str, object] | None,
    curated_required: bool,
    lucide_validation: dict[str, object] | None,
    lucide_required: bool,
    suite_family_baseline_comparison: dict[str, object] | None,
) -> dict[str, object]:
    reasons: list[str] = []
    if gate.get("accepted") is not True:
        reasons.append("training_gate_not_accepted")
    if curated_required:
        if not isinstance(curated_validation, dict):
            reasons.append("missing_curated_validation")
        elif curated_validation.get("ok") is not True:
            if _validation_failure_is_known_baseline_debt(
                suite_family_baseline_comparison,
            ):
                reasons.append("curated_validation_known_baseline_debt")
            else:
                reasons.append("curated_validation_failed")
    if lucide_required:
        if not isinstance(lucide_validation, dict):
            reasons.append("missing_lucide_validation")
        elif lucide_validation.get("ok") is not True:
            if _validation_failure_is_known_baseline_debt(
                suite_family_baseline_comparison,
            ):
                reasons.append("lucide_validation_known_baseline_debt")
            else:
                reasons.append("lucide_validation_failed")
    if (
        isinstance(suite_family_baseline_comparison, dict)
        and suite_family_baseline_comparison.get("ok") is not True
    ):
        reasons.append("suite_family_baseline_regressed")
    if backend == "mlx" and min_mlx_raster_pseudo_examples > 0:
        source_summary = _model_training_source_summary(model)
        raster_pseudo = source_summary.get("raster_pseudo_train_examples")
        if (
            not isinstance(raster_pseudo, int)
            or raster_pseudo < min_mlx_raster_pseudo_examples
        ):
            reasons.append("mlx_raster_pseudo_examples_below_min")
    return {
        "accepted": not _blocking_acceptance_reasons(reasons),
        "reasons": reasons,
        "blocking_reasons": _blocking_acceptance_reasons(reasons),
        "curated_required": curated_required,
        "lucide_required": lucide_required,
        "min_mlx_raster_pseudo_examples": min_mlx_raster_pseudo_examples,
        "suite_family_baseline_checked": isinstance(
            suite_family_baseline_comparison,
            dict,
        ),
    }


def _validation_failure_is_known_baseline_debt(
    baseline_comparison: dict[str, object] | None,
) -> bool:
    return (
        isinstance(baseline_comparison, dict)
        and baseline_comparison.get("status") == "checked"
        and baseline_comparison.get("ok") is True
    )


def _model_training_source_summary(
    model: dict[str, object] | None,
) -> dict[str, object]:
    if not isinstance(model, dict):
        return {}
    source_summary = model.get("training_source_summary")
    if isinstance(source_summary, dict):
        return source_summary
    return {}


def _reviewed_label_loop_audit(result: dict[str, object]) -> dict[str, object]:
    reviewed = _json_object_from_path(result.get("reviewed_labels"))
    dataset_path = _cycle_artifact_path(result, "pseudo_dataset")
    dataset = _json_object_from_path(dataset_path)
    comparison = _json_object_from_path(_cycle_artifact_path(result, "comparison"))
    gate_artifact = _json_object_from_path(_cycle_artifact_path(result, "gate"))
    accepted_labels = _object_list(reviewed.get("accepted") if reviewed else None)
    rejected_labels = _object_list(reviewed.get("rejected") if reviewed else None)
    pending_labels = _object_list(reviewed.get("pending") if reviewed else None)
    samples = _object_list(dataset.get("samples") if dataset else None)
    checks = {
        "reviewed_label_source": reviewed is not None
        and isinstance(reviewed.get("accepted"), list),
        "accepted_label_only_dataset": _accepted_label_only_dataset(
            reviewed,
            dataset,
        ),
        "pseudo_manifest_artifacts": _pseudo_manifest_artifacts_ok(
            dataset,
            dataset_path,
        ),
        "provenance_summary_records": _provenance_summary_records_ok(
            result,
            dataset,
        ),
        "training_gate_records": _training_gate_records_ok(
            result,
            comparison,
            gate_artifact,
        ),
        "acceptance_gate_records": _acceptance_gate_records_ok(result),
        "model_acceptance_contract": _model_acceptance_contract_ok(result),
        "suite_family_validation_records": _suite_family_validation_records_ok(result),
        "baseline_review_records": _baseline_review_records_ok(result),
        "mlx_raster_pseudo_gate": _mlx_raster_pseudo_gate_ok(result),
    }
    missing_checks = [name for name, covered in checks.items() if not covered]
    reviewed_summary = {}
    pseudo_dataset = result.get("pseudo_dataset")
    if isinstance(pseudo_dataset, dict):
        summary = pseudo_dataset.get("reviewed_label_summary")
        if isinstance(summary, dict):
            reviewed_summary = summary
    acceptance_gate = result.get("acceptance_gate")
    acceptance_gate = acceptance_gate if isinstance(acceptance_gate, dict) else {}
    return {
        "schema_version": 1,
        "ok": not missing_checks,
        "checks": checks,
        "summary": {
            "required_check_count": len(checks),
            "covered_check_count": sum(1 for value in checks.values() if value),
            "missing_checks": missing_checks,
            "accepted_label_count": len(accepted_labels),
            "rejected_label_count": len(rejected_labels),
            "pending_label_count": len(pending_labels),
            "pseudo_dataset_sample_count": len(samples),
            "training_backend": result.get("training_backend", "centroid"),
            "training_gate_decision": _dict_field(result.get("gate"), "decision"),
            "cycle_accepted": result.get("accepted", False),
            "blocking_acceptance_reasons": acceptance_gate.get(
                "blocking_reasons",
                [],
            ),
            "applied_review_decision_counts": reviewed_summary.get(
                "applied_review_decision_counts",
                {},
            ),
            "provenance_field_counts": reviewed_summary.get(
                "provenance_field_counts",
                {},
            ),
        },
    }


def _multi_family_regression_audit(result: dict[str, object]) -> dict[str, object]:
    validation = result.get("suite_family_validation")
    baseline = result.get("suite_family_baseline_comparison")
    comparison = _json_object_from_path(_cycle_artifact_path(result, "comparison"))
    curated_report = _json_object_from_path(
        _cycle_artifact_path(result, "curated_report")
    )
    lucide_report = _json_object_from_path(
        _cycle_artifact_path(result, "lucide_report")
    )
    checks = {
        "suite_family_view": _suite_family_view_ok(validation),
        "family_outcome_records": _family_outcome_records_ok(validation),
        "real_image_quality_counts": _real_image_quality_counts_ok(validation),
        "baseline_comparison_records": _baseline_comparison_records_ok(baseline),
        "blocking_regression_visibility": _blocking_regression_visibility_ok(result),
        "configured_validation_artifacts": _configured_validation_artifacts_ok(
            result,
            curated_report=curated_report,
            lucide_report=lucide_report,
        ),
        "contact_sheet_index": _contact_sheet_index_ok(curated_report),
        "failure_severity_records": _failure_severity_records_ok(curated_report),
        "yellow_drift_records": _yellow_drift_records_ok(
            validation,
            curated_report,
        ),
        "comparison_delta_records": _comparison_delta_records_ok(comparison),
    }
    missing_checks = [name for name, covered in checks.items() if not covered]
    failure_summary = _curated_failure_summary(curated_report)
    return {
        "schema_version": 1,
        "ok": not missing_checks,
        "checks": checks,
        "summary": {
            "required_check_count": len(checks),
            "covered_check_count": sum(1 for value in checks.values() if value),
            "missing_checks": missing_checks,
            "primitive_family_count": _suite_family_count(validation, "primitive"),
            "real_image_family_count": _suite_family_count(validation, "real_image"),
            "lucide_family_count": _suite_family_count(validation, "lucide"),
            "baseline_comparison_count": _dict_int(
                baseline,
                "comparison_count",
            ),
            "new_regression_count": _dict_int(baseline, "new_regression_count"),
            "known_debt_count": _dict_int(baseline, "known_debt_count"),
            "missing_current_family_count": _dict_int(
                baseline,
                "missing_current_family_count",
            ),
            "red_failure_count": failure_summary["red_failure_count"],
            "yellow_drift_count": failure_summary["yellow_drift_count"],
            "contact_sheet_count": failure_summary["contact_sheet_count"],
        },
    }


def _suite_family_view_ok(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    for suite_name in SELF_LEARNING_FAMILY_VALIDATION_SUITES:
        suite = value.get(suite_name)
        if not isinstance(suite, dict):
            return False
        if not isinstance(suite.get("status"), str):
            return False
        if suite.get("ok") is not None and not isinstance(suite.get("ok"), bool):
            return False
        if not isinstance(suite.get("families"), list):
            return False
    return True


def _family_outcome_records_ok(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    for suite_name in SELF_LEARNING_FAMILY_VALIDATION_SUITES:
        suite = value.get(suite_name)
        if not isinstance(suite, dict):
            return False
        families = suite.get("families")
        if not isinstance(families, list):
            return False
        for family in families:
            if not isinstance(family, dict):
                return False
            if not _non_empty_string(family.get("family")):
                return False
            if not _non_empty_string(family.get("outcome")):
                return False
            if suite_name == "primitive":
                if not isinstance(family.get("split"), str):
                    return False
                if "accuracy_delta" not in family:
                    return False
            else:
                for key in (
                    "case_count",
                    "checked_count",
                    "passed_count",
                    "failed_count",
                    "missing_source_count",
                ):
                    if key not in family:
                        return False
    return True


def _real_image_quality_counts_ok(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    real_image = value.get("real_image")
    if not isinstance(real_image, dict):
        return False
    if real_image.get("status") != "checked":
        return True
    families = real_image.get("families")
    if not isinstance(families, list):
        return False
    for family in families:
        if not isinstance(family, dict):
            return False
        counts = family.get("pipeline_quality_counts")
        if counts is not None and not _count_map_ok(counts):
            return False
    return True


def _baseline_comparison_records_ok(value: object) -> bool:
    if value is None:
        return True
    if not isinstance(value, dict):
        return False
    if value.get("status") != "checked":
        return False
    if not isinstance(value.get("ok"), bool):
        return False
    if not isinstance(value.get("comparisons"), list):
        return False
    if not _count_map_ok(value.get("comparison_outcome_counts")):
        return False
    for key in (
        "new_regressions",
        "known_debt",
        "resolved_regressions",
        "missing_current_families",
    ):
        if not isinstance(value.get(key), list):
            return False
    return True


def _blocking_regression_visibility_ok(result: dict[str, object]) -> bool:
    baseline = result.get("suite_family_baseline_comparison")
    if not isinstance(baseline, dict) or baseline.get("ok") is not False:
        return True
    acceptance_gate = result.get("acceptance_gate")
    if not isinstance(acceptance_gate, dict):
        return False
    blocking = acceptance_gate.get("blocking_reasons")
    return (
        isinstance(blocking, list)
        and "suite_family_baseline_regressed" in blocking
    )


def _configured_validation_artifacts_ok(
    result: dict[str, object],
    *,
    curated_report: dict[str, object] | None,
    lucide_report: dict[str, object] | None,
) -> bool:
    curated = result.get("curated_validation")
    if isinstance(curated, dict) and curated.get("status") == "checked":
        if curated_report is None or not isinstance(
            curated_report.get("cases"),
            list,
        ):
            return False
    lucide = result.get("lucide_validation")
    if isinstance(lucide, dict) and lucide.get("status") == "checked":
        if lucide_report is None or not isinstance(
            lucide_report.get("cases"),
            list,
        ):
            return False
    return True


def _contact_sheet_index_ok(curated_report: dict[str, object] | None) -> bool:
    if curated_report is None:
        return True
    for case in _report_case_objects(curated_report):
        if not isinstance(case.get("promotion"), dict):
            continue
        if case.get("status") != "checked":
            continue
        artifacts = case.get("artifacts")
        if not isinstance(artifacts, dict):
            return False
        contact_sheet = _path_from_value(artifacts.get("contact_sheet"))
        if contact_sheet is None or not contact_sheet.exists():
            return False
    return True


def _failure_severity_records_ok(curated_report: dict[str, object] | None) -> bool:
    if curated_report is None:
        return True
    for gate in _failed_curated_gates(curated_report):
        if gate.get("severity") not in {"red", "yellow"}:
            return False
        if not _non_empty_string(gate.get("reason")):
            return False
        if not _non_empty_string(gate.get("id")):
            return False
    return True


def _yellow_drift_records_ok(
    validation: object,
    curated_report: dict[str, object] | None,
) -> bool:
    if not _real_image_quality_counts_ok(validation):
        return False
    if curated_report is None:
        return True
    for gate in _failed_curated_gates(curated_report):
        if gate.get("severity") == "yellow" and not _non_empty_string(
            gate.get("reason")
        ):
            return False
    return True


def _comparison_delta_records_ok(comparison: dict[str, object] | None) -> bool:
    if not isinstance(comparison, dict):
        return False
    summary = comparison.get("summary")
    delta = comparison.get("delta")
    if not isinstance(summary, dict) or not isinstance(delta, dict):
        return False
    if summary.get("status") not in {
        "improved",
        "insufficient_data",
        "mixed",
        "regressed",
        "unchanged",
    }:
        return False
    return (
        "train_examples_delta" in summary
        and "best_accuracy_delta" in summary
        and "worst_accuracy_delta" in summary
    )


def _curated_failure_summary(
    curated_report: dict[str, object] | None,
) -> dict[str, int]:
    failed_gates = _failed_curated_gates(curated_report)
    contact_sheet_count = 0
    if curated_report is not None:
        for case in _report_case_objects(curated_report):
            artifacts = case.get("artifacts")
            if not isinstance(artifacts, dict):
                continue
            contact_sheet = _path_from_value(artifacts.get("contact_sheet"))
            if contact_sheet is not None and contact_sheet.exists():
                contact_sheet_count += 1
    return {
        "red_failure_count": sum(
            1 for gate in failed_gates if gate.get("severity") == "red"
        ),
        "yellow_drift_count": sum(
            1 for gate in failed_gates if gate.get("severity") == "yellow"
        ),
        "contact_sheet_count": contact_sheet_count,
    }


def _failed_curated_gates(
    curated_report: dict[str, object] | None,
) -> list[dict[str, object]]:
    if curated_report is None:
        return []
    failed: list[dict[str, object]] = []
    for case in _report_case_objects(curated_report):
        gates = case.get("promotion_gates")
        if not isinstance(gates, list):
            continue
        for gate in gates:
            if isinstance(gate, dict) and gate.get("ok") is not True:
                failed.append(gate)
    return failed


def _report_case_objects(report: dict[str, object]) -> list[dict[str, object]]:
    return _object_list(report.get("cases"))


def _suite_family_count(value: object, suite_name: str) -> int:
    if not isinstance(value, dict):
        return 0
    suite = value.get(suite_name)
    if not isinstance(suite, dict):
        return 0
    return len(_object_list(suite.get("families")))


def _dict_int(value: object, key: str) -> int:
    if not isinstance(value, dict):
        return 0
    return _int_value(value.get(key))


def _count_map_ok(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    return all(
        isinstance(key, str) and isinstance(count, int)
        for key, count in value.items()
    )


def _accepted_label_only_dataset(
    reviewed: dict[str, object] | None,
    dataset: dict[str, object] | None,
) -> bool:
    if not isinstance(reviewed, dict) or not isinstance(dataset, dict):
        return False
    accepted = _object_list(reviewed.get("accepted"))
    samples = _object_list(dataset.get("samples"))
    splits = dataset.get("splits")
    if dataset.get("count") != len(samples):
        return False
    if not isinstance(splits, dict) or splits.get("train") != len(samples):
        return False
    if _int_value(splits.get("val")) != 0 or _int_value(splits.get("test")) != 0:
        return False
    if len(samples) != len(accepted):
        return False
    if any(sample.get("split") != "train" for sample in samples):
        return False
    return str(dataset.get("source_reviewed_labels", "")) != ""


def _pseudo_manifest_artifacts_ok(
    dataset: dict[str, object] | None,
    dataset_path: Path | None,
) -> bool:
    if not isinstance(dataset, dict) or dataset_path is None:
        return False
    samples = _object_list(dataset.get("samples"))
    base_dir = dataset_path.parent
    for sample in samples:
        manifest = sample.get("manifest")
        if not isinstance(manifest, str) or not manifest:
            return False
        manifest_path = base_dir / manifest
        if not manifest_path.exists():
            return False
        manifest_data = _json_object_from_path(manifest_path)
        if not isinstance(manifest_data, dict):
            return False
        if manifest_data.get("schema_version") != 1:
            return False
        if manifest_data.get("anchor_count") != 1:
            return False
        if not isinstance(manifest_data.get("anchors"), list):
            return False
    return True


def _provenance_summary_records_ok(
    result: dict[str, object],
    dataset: dict[str, object] | None,
) -> bool:
    pseudo_dataset = result.get("pseudo_dataset")
    if not isinstance(pseudo_dataset, dict) or not isinstance(dataset, dict):
        return False
    summary = pseudo_dataset.get("reviewed_label_summary")
    dataset_summary = dataset.get("reviewed_label_summary")
    if not isinstance(summary, dict) or not isinstance(dataset_summary, dict):
        return False
    if summary.get("sample_count") != pseudo_dataset.get("count"):
        return False
    if dataset_summary.get("sample_count") != dataset.get("count"):
        return False
    return isinstance(summary.get("provenance_field_counts"), dict) and isinstance(
        summary.get("applied_review_decision_counts"),
        dict,
    )


def _training_gate_records_ok(
    result: dict[str, object],
    comparison: dict[str, object] | None,
    gate_artifact: dict[str, object] | None,
) -> bool:
    gate = result.get("gate")
    comparison_summary = result.get("comparison_summary")
    artifacts = result.get("artifacts")
    if not isinstance(gate, dict) or not isinstance(comparison_summary, dict):
        return False
    if gate.get("decision") not in SELF_LEARNING_GATE_DECISIONS:
        return False
    if not isinstance(gate.get("accepted"), bool):
        return False
    if not isinstance(gate.get("reasons"), list):
        return False
    if not isinstance(comparison, dict) or not isinstance(gate_artifact, dict):
        return False
    if not isinstance(artifacts, dict):
        return False
    for key in ("comparison_markdown", "gate_markdown"):
        path = _path_from_value(artifacts.get(key))
        if path is None or not path.exists():
            return False
    return comparison_summary.get("status") in {
        "improved",
        "insufficient_data",
        "mixed",
        "regressed",
        "unchanged",
    }


def _acceptance_gate_records_ok(result: dict[str, object]) -> bool:
    acceptance_gate = result.get("acceptance_gate")
    if not isinstance(acceptance_gate, dict):
        return False
    if not isinstance(result.get("accepted"), bool):
        return False
    if acceptance_gate.get("accepted") is not result.get("accepted"):
        return False
    reasons = acceptance_gate.get("reasons")
    blocking = acceptance_gate.get("blocking_reasons")
    if not isinstance(reasons, list) or not isinstance(blocking, list):
        return False
    return bool(blocking) is (result.get("accepted") is False)


def _model_acceptance_contract_ok(result: dict[str, object]) -> bool:
    gate = result.get("gate")
    gate = gate if isinstance(gate, dict) else {}
    model = result.get("model")
    artifacts = result.get("artifacts")
    artifacts = artifacts if isinstance(artifacts, dict) else {}
    model_path = _path_from_value(artifacts.get("model"))
    gate_accepted = gate.get("accepted") is True
    cycle_accepted = result.get("accepted") is True
    if cycle_accepted:
        return (
            gate_accepted
            and isinstance(model, dict)
            and result.get("status") == "retrained"
            and model_path is not None
            and model_path.exists()
        )
    if not gate_accepted:
        return result.get("status") == "skipped_retrain" and model is None
    return isinstance(model, dict) and result.get("status") == "retrained"


def _suite_family_validation_records_ok(result: dict[str, object]) -> bool:
    validation = result.get("suite_family_validation")
    if not isinstance(validation, dict):
        return False
    for suite_name in SELF_LEARNING_FAMILY_VALIDATION_SUITES:
        suite = validation.get(suite_name)
        if not isinstance(suite, dict):
            return False
        if not isinstance(suite.get("status"), str):
            return False
        if suite.get("ok") is not None and not isinstance(suite.get("ok"), bool):
            return False
        families = suite.get("families")
        if not isinstance(families, list):
            return False
        for family in families:
            if not isinstance(family, dict):
                return False
            if not isinstance(family.get("family"), str):
                return False
            if not isinstance(family.get("outcome"), str):
                return False
    comparison = result.get("suite_family_baseline_comparison")
    if comparison is None:
        return True
    if not isinstance(comparison, dict):
        return False
    if comparison.get("status") != "checked":
        return False
    if not isinstance(comparison.get("ok"), bool):
        return False
    return isinstance(comparison.get("comparisons"), list)


def _baseline_review_records_ok(result: dict[str, object]) -> bool:
    snapshot = result.get("suite_family_baseline_snapshot")
    if not isinstance(snapshot, dict):
        return False
    status = snapshot.get("status")
    if status not in SELF_LEARNING_BASELINE_SNAPSHOT_STATUSES:
        return False
    if status == "written":
        output = _path_from_value(snapshot.get("output"))
        if output is None or not output.exists():
            return False
        review = snapshot.get("review")
        if not isinstance(review, dict):
            return False
        if not _non_empty_string(review.get("reviewer")):
            return False
        if not _non_empty_string(review.get("reason")):
            return False
        return _non_empty_string(snapshot.get("changelog"))
    if status == "skipped_missing_review_evidence":
        return isinstance(snapshot.get("missing_review_fields"), list)
    if status == "skipped_coverage_regression":
        return isinstance(snapshot.get("coverage_regressions"), list)
    return True


def _mlx_raster_pseudo_gate_ok(result: dict[str, object]) -> bool:
    if result.get("training_backend") != "mlx":
        return True
    acceptance_gate = result.get("acceptance_gate")
    acceptance_gate = acceptance_gate if isinstance(acceptance_gate, dict) else {}
    configured_min = result.get("min_mlx_raster_pseudo_examples")
    if acceptance_gate.get("min_mlx_raster_pseudo_examples") != configured_min:
        return False
    if not isinstance(configured_min, int) or configured_min <= 0:
        return True
    model = result.get("model")
    source_summary = _model_training_source_summary(
        model if isinstance(model, dict) else None
    )
    raster_count = source_summary.get("raster_pseudo_train_examples")
    if isinstance(raster_count, int) and raster_count >= configured_min:
        return True
    blocking = acceptance_gate.get("blocking_reasons")
    return (
        isinstance(blocking, list)
        and "mlx_raster_pseudo_examples_below_min" in blocking
    )


def _cycle_artifact_path(result: dict[str, object], key: str) -> Path | None:
    artifacts = result.get("artifacts")
    if not isinstance(artifacts, dict):
        return None
    return _path_from_value(artifacts.get(key))


def _json_object_from_path(value: object) -> dict[str, object] | None:
    path = _path_from_value(value)
    if path is None or not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _path_from_value(value: object) -> Path | None:
    if isinstance(value, Path):
        return value
    if isinstance(value, str) and value:
        return Path(value)
    return None


def _object_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _dict_field(value: object, key: str) -> object:
    return value.get(key) if isinstance(value, dict) else None


def _non_empty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _int_value(value: object) -> int:
    return int(value) if isinstance(value, int) and not isinstance(value, bool) else 0


def _blocking_acceptance_reasons(reasons: list[str]) -> list[str]:
    non_blocking = {
        "curated_validation_known_baseline_debt",
        "lucide_validation_known_baseline_debt",
    }
    return [reason for reason in reasons if reason not in non_blocking]


def render_self_learning_cycle_markdown(result: dict[str, object]) -> str:
    artifacts = result.get("artifacts", {})
    if not isinstance(artifacts, dict):
        artifacts = {}
    gate = result.get("gate", {})
    if not isinstance(gate, dict):
        gate = {}
    acceptance_gate = result.get("acceptance_gate", {})
    if not isinstance(acceptance_gate, dict):
        acceptance_gate = {}
    comparison = result.get("comparison_summary", {})
    if not isinstance(comparison, dict):
        comparison = {}
    pseudo_dataset = result.get("pseudo_dataset", {})
    if not isinstance(pseudo_dataset, dict):
        pseudo_dataset = {}
    reviewed_summary = pseudo_dataset.get("reviewed_label_summary", {})
    if not isinstance(reviewed_summary, dict):
        reviewed_summary = {}
    lines = [
        "# Morphēa Self-Learning Cycle",
        "",
        f"- Status: `{result.get('status', 'n/a')}`",
        f"- Accepted: `{result.get('accepted', False)}`",
        f"- Training backend: `{result.get('training_backend', 'centroid')}`",
        f"- Gate decision: `{gate.get('decision', 'n/a')}`",
        f"- Gate accepted: `{gate.get('accepted', False)}`",
        f"- Acceptance reasons: {_format_reason_list(acceptance_gate.get('reasons'))}",
        f"- Blocking acceptance reasons: {_format_reason_list(acceptance_gate.get('blocking_reasons'))}",
        f"- Pseudo-label examples: {_fmt_metric(pseudo_dataset.get('count'))}",
        f"- Applied review decisions: {_format_issue_counts(_counts_from_object(reviewed_summary.get('applied_review_decision_counts')))}",
        f"- Comparison status: `{comparison.get('status', 'n/a')}`",
        f"- Best accuracy delta: {_fmt_metric(comparison.get('best_accuracy_delta'))}",
        f"- Worst accuracy delta: {_fmt_metric(comparison.get('worst_accuracy_delta'))}",
    ]
    audit = result.get("reviewed_label_loop_audit")
    if isinstance(audit, dict):
        audit_summary = audit.get("summary", {})
        audit_summary = audit_summary if isinstance(audit_summary, dict) else {}
        lines.extend(
            [
                "",
                "## RIP7 Reviewed Label Loop Audit",
                "",
                f"- Status: `{'pass' if audit.get('ok', False) else 'fail'}`",
                f"- Covered checks: {_fmt_metric(audit_summary.get('covered_check_count'))} / {_fmt_metric(audit_summary.get('required_check_count'))}",
                f"- Missing checks: {_format_reason_list(audit_summary.get('missing_checks'))}",
                f"- Accepted labels: {_fmt_metric(audit_summary.get('accepted_label_count'))}",
                f"- Pseudo dataset samples: {_fmt_metric(audit_summary.get('pseudo_dataset_sample_count'))}",
                f"- Blocking acceptance reasons: {_format_reason_list(audit_summary.get('blocking_acceptance_reasons'))}",
                "",
                "| Check | Covered |",
                "| --- | --- |",
            ]
        )
        checks = audit.get("checks", {})
        if isinstance(checks, dict):
            for name, covered in sorted(checks.items()):
                lines.append(f"| `{name}` | `{str(bool(covered)).lower()}` |")
    family_audit = result.get("multi_family_regression_audit")
    if isinstance(family_audit, dict):
        family_summary = family_audit.get("summary", {})
        family_summary = family_summary if isinstance(family_summary, dict) else {}
        lines.extend(
            [
                "",
                "## RIP8 Multi-Family Regression Audit",
                "",
                f"- Status: `{'pass' if family_audit.get('ok', False) else 'fail'}`",
                f"- Covered checks: {_fmt_metric(family_summary.get('covered_check_count'))} / {_fmt_metric(family_summary.get('required_check_count'))}",
                f"- Missing checks: {_format_reason_list(family_summary.get('missing_checks'))}",
                f"- Primitive families: {_fmt_metric(family_summary.get('primitive_family_count'))}",
                f"- Real-image families: {_fmt_metric(family_summary.get('real_image_family_count'))}",
                f"- Lucide families: {_fmt_metric(family_summary.get('lucide_family_count'))}",
                f"- Red failures: {_fmt_metric(family_summary.get('red_failure_count'))}",
                f"- Yellow drift: {_fmt_metric(family_summary.get('yellow_drift_count'))}",
                "",
                "| Check | Covered |",
                "| --- | --- |",
            ]
        )
        checks = family_audit.get("checks", {})
        if isinstance(checks, dict):
            for name, covered in sorted(checks.items()):
                lines.append(f"| `{name}` | `{str(bool(covered)).lower()}` |")
    model = result.get("model")
    if isinstance(model, dict):
        lines.extend(
            [
                "",
                "## Model",
                "",
                f"- Model type: `{model.get('model_type', 'n/a')}`",
                f"- Retraining backend: `{model.get('retraining_backend', 'n/a')}`",
                f"- Status: `{model.get('status', 'n/a')}`",
                f"- Training implementation: `{model.get('training_implementation', 'n/a')}`",
                f"- Train examples: {_fmt_metric(model.get('train_examples'))}",
            ]
        )
        component_summary = model.get("training_component_summary")
        if isinstance(component_summary, dict):
            lines.extend(_model_component_summary_markdown(component_summary))
        source_summary = model.get("training_source_summary")
        if isinstance(source_summary, dict):
            lines.extend(_model_training_source_markdown(source_summary))
    if reviewed_summary or isinstance(pseudo_dataset.get("samples"), list):
        provenance_counts = _counts_from_object(
            reviewed_summary.get("provenance_field_counts")
        )
        if not provenance_counts:
            provenance_counts = _reviewed_sample_provenance_counts(
                pseudo_dataset.get("samples")
            )
        lines.extend(
            [
                "",
                "## Reviewed Labels",
                "",
                f"- Issue counts: {_format_issue_counts(_counts_from_object(reviewed_summary.get('issue_counts')))}",
                f"- Provenance fields: {_format_issue_counts(provenance_counts)}",
            ]
        )
    curated = result.get("curated_validation")
    if isinstance(curated, dict):
        lines.extend(
            [
                f"- Curated validation: `{curated.get('status', 'n/a')}`",
                f"- Curated OK: `{curated.get('ok', 'n/a')}`",
                f"- Curated checked cases: {_fmt_metric(curated.get('checked_count'))}",
            ]
        )
    lucide = result.get("lucide_validation")
    if isinstance(lucide, dict):
        lines.extend(
            [
                f"- Lucide validation: `{lucide.get('status', 'n/a')}`",
                f"- Lucide OK: `{lucide.get('ok', 'n/a')}`",
                f"- Lucide checked cases: {_fmt_metric(lucide.get('checked_count'))}",
            ]
        )
    suite_family_validation = result.get("suite_family_validation")
    if isinstance(suite_family_validation, dict):
        lines.extend(
            [
                "",
                "## Suite Family Validation",
                "",
                "| Suite | Status | OK | Family | Evidence | Outcome |",
                "| --- | --- | ---: | --- | --- | --- |",
            ]
        )
        rows = _suite_family_validation_rows(suite_family_validation)
        if rows:
            lines.extend(rows)
        else:
            lines.append("| n/a | n/a | n/a | n/a | n/a | n/a |")
    baseline_comparison = result.get("suite_family_baseline_comparison")
    if isinstance(baseline_comparison, dict):
        lines.extend(
            [
                "",
                "## Suite Family Baseline",
                "",
                f"- Baseline: `{baseline_comparison.get('baseline', 'n/a')}`",
                f"- OK: `{baseline_comparison.get('ok', 'n/a')}`",
                f"- Compared families: {_fmt_metric(baseline_comparison.get('comparison_count'))}",
                f"- Outcome counts: {_format_count_map(baseline_comparison.get('comparison_outcome_counts'))}",
                f"- New regressions: {_fmt_metric(baseline_comparison.get('new_regression_count'))}",
                f"- Known debt: {_fmt_metric(baseline_comparison.get('known_debt_count'))}",
                f"- Resolved regressions: {_fmt_metric(baseline_comparison.get('resolved_regression_count'))}",
                f"- Missing current families: {_fmt_metric(baseline_comparison.get('missing_current_family_count'))}",
                "",
                "| Status | Suite | Split | Family | Baseline | Current | Evidence |",
                "| --- | --- | --- | --- | --- | --- | --- |",
            ]
        )
        rows = _suite_family_baseline_rows(baseline_comparison)
        if rows:
            lines.extend(rows)
        else:
            lines.append("| n/a | n/a | n/a | n/a | n/a | n/a | n/a |")
    baseline_snapshot = result.get("suite_family_baseline_snapshot")
    if (
        isinstance(baseline_snapshot, dict)
        and baseline_snapshot.get("status") != "not_configured"
    ):
        lines.extend(
            [
                "",
                "## Suite Family Baseline Snapshot",
                "",
                f"- Status: `{baseline_snapshot.get('status', 'n/a')}`",
                f"- Output: `{baseline_snapshot.get('output', 'n/a')}`",
                f"- Changelog: `{baseline_snapshot.get('changelog', 'n/a')}`",
                f"- Source cycle: `{artifacts.get('summary', 'n/a')}`",
                f"- Base dataset: `{result.get('base_dataset', 'n/a')}`",
                f"- Reviewed labels: `{result.get('reviewed_labels', 'n/a')}`",
                f"- Validation dataset: `{result.get('validation_dataset', 'n/a')}`",
                f"- Reviewer: `{_baseline_snapshot_review_value(baseline_snapshot, 'reviewer')}`",
                f"- Reason: `{_baseline_snapshot_review_value(baseline_snapshot, 'reason')}`",
                f"- Missing evidence: {_format_reason_list(baseline_snapshot.get('missing_review_fields'))}",
                f"- Coverage regressions: {_suite_family_coverage_regression_list(baseline_snapshot.get('coverage_regressions'))}",
            ]
        )
    lines.extend(
        [
            "",
            "## Artifacts",
            "",
            "| Artifact | Path |",
            "| --- | --- |",
        ]
    )
    for key in sorted(artifacts):
        value = artifacts.get(key)
        if value is not None:
            lines.append(f"| `{key}` | `{value}` |")
    reasons = gate.get("reasons", [])
    if not isinstance(reasons, list):
        reasons = []
    lines.extend(
        [
            "",
            "## Gate Reasons",
            "",
            ", ".join(f"`{reason}`" for reason in reasons) if reasons else "n/a",
        ]
    )
    return "\n".join(lines) + "\n"


def _baseline_snapshot_review_value(snapshot: dict[str, object], key: str) -> str:
    review = snapshot.get("review", {})
    if not isinstance(review, dict):
        return "n/a"
    value = review.get(key)
    return str(value) if value else "n/a"


def _suite_family_baseline_rows(
    comparison: dict[str, object],
) -> list[str]:
    rows = []
    comparisons = comparison.get("comparisons", [])
    if isinstance(comparisons, list):
        for item in comparisons:
            if not isinstance(item, dict):
                continue
            rows.append(_suite_family_baseline_row(item))
        if rows:
            return rows
    for section, status in (
        ("new_regressions", "new_regression"),
        ("known_debt", "known_debt"),
        ("resolved_regressions", "resolved_regression"),
        ("missing_current_families", "missing_current_family"),
    ):
        items = comparison.get(section, [])
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            row = dict(item)
            row["status"] = status
            rows.append(_suite_family_baseline_row(row))
    return rows


def _suite_family_baseline_row(item: dict[str, object]) -> str:
    return (
        "| "
        f"`{item.get('status', 'n/a')}` | "
        f"`{item.get('suite', 'n/a')}` | "
        f"`{item.get('split') or 'n/a'}` | "
        f"`{item.get('family', 'n/a')}` | "
        f"`{item.get('baseline_outcome', 'n/a')}` | "
        f"`{item.get('current_outcome', 'n/a')}` | "
        f"{_suite_family_baseline_evidence(item)} |"
    )


def _suite_family_baseline_evidence(item: dict[str, object]) -> str:
    if "accuracy_delta" in item:
        return f"delta={_fmt_metric(item.get('accuracy_delta'))}"
    evidence = (
        f"cases={_fmt_metric(item.get('case_count'))}, "
        f"failed={_fmt_metric(item.get('failed_count'))}, "
        f"missing={_fmt_metric(item.get('missing_source_count'))}"
    )
    pipeline_counts = _pipeline_quality_counts_evidence(item)
    if pipeline_counts:
        evidence = f"{evidence}, pipeline={pipeline_counts}"
    return evidence


def _suite_family_validation_rows(
    validation: dict[str, object],
) -> list[str]:
    rows: list[str] = []
    for suite_name in ("primitive", "real_image", "lucide"):
        suite = validation.get(suite_name, {})
        if not isinstance(suite, dict):
            continue
        families = suite.get("families", [])
        if not isinstance(families, list) or not families:
            rows.append(
                "| "
                f"`{suite_name}` | "
                f"`{suite.get('status', 'n/a')}` | "
                f"`{suite.get('ok', 'n/a')}` | "
                "n/a | n/a | n/a |"
            )
            continue
        for family in families:
            if not isinstance(family, dict):
                continue
            rows.append(
                "| "
                f"`{suite_name}` | "
                f"`{suite.get('status', 'n/a')}` | "
                f"`{suite.get('ok', 'n/a')}` | "
                f"`{family.get('family', 'n/a')}` | "
                f"{_suite_family_evidence(family)} | "
                f"`{family.get('outcome', 'n/a')}` |"
            )
    return rows


def _suite_family_evidence(family: dict[str, object]) -> str:
    if "accuracy_delta" in family:
        split = family.get("split", "n/a")
        return (
            f"split=`{split}`, "
            f"baseline={_fmt_metric(family.get('baseline_accuracy'))}, "
            f"augmented={_fmt_metric(family.get('augmented_accuracy'))}, "
            f"delta={_fmt_metric(family.get('accuracy_delta'))}"
        )
    evidence = (
        f"cases={_fmt_metric(family.get('case_count'))}, "
        f"checked={_fmt_metric(family.get('checked_count'))}, "
        f"passed={_fmt_metric(family.get('passed_count'))}, "
        f"failed={_fmt_metric(family.get('failed_count'))}, "
        f"missing={_fmt_metric(family.get('missing_source_count'))}"
    )
    pipeline_counts = _pipeline_quality_counts_evidence(family)
    if pipeline_counts:
        evidence = f"{evidence}, pipeline={pipeline_counts}"
    return evidence


def _pipeline_quality_counts_evidence(item: dict[str, object]) -> str:
    counts = _counts_from_object(item.get("pipeline_quality_counts"))
    if not counts:
        return ""
    return ", ".join(
        f"{label}: {_fmt_metric(count)}"
        for label, count in sorted(counts.items())
    )


def _suite_family_coverage_regression_list(value: object) -> str:
    if not isinstance(value, list) or not value:
        return "`none`"
    items = []
    for item in value:
        if not isinstance(item, dict):
            continue
        split = item.get("split") or "n/a"
        items.append(
            "`"
            f"{item.get('suite', 'n/a')}/"
            f"{split}/"
            f"{item.get('family', 'n/a')}: "
            f"{item.get('metric', 'n/a')} "
            f"{_fmt_metric(item.get('baseline'))}->"
            f"{_fmt_metric(item.get('current'))}"
            "`"
        )
    return ", ".join(items) if items else "`none`"


def _format_reason_list(value: object) -> str:
    if not isinstance(value, list) or not value:
        return "`none`"
    return ", ".join(f"`{reason}`" for reason in value)


def _format_count_map(value: object) -> str:
    if not isinstance(value, dict) or not value:
        return "`none`"
    return ", ".join(
        f"`{key}: {_fmt_metric(count)}`"
        for key, count in sorted(value.items())
    )


def retrain_centroid_classifier(
    *,
    base_dataset: str | Path,
    pseudo_dataset: str | Path,
    output: str | Path,
    validation_dataset: str | Path | None = None,
    comparison_output: str | Path | None = None,
) -> dict[str, object]:
    """Train and persist an augmented centroid model from reviewed labels."""

    validation_source = validation_dataset or base_dataset
    baseline_train = examples_from_dataset(base_dataset, splits=("train",))
    pseudo_train = examples_from_dataset(pseudo_dataset, splits=("train",))
    train_examples = baseline_train + pseudo_train
    centroids = centroids_from_examples(train_examples)

    model = {
        "model_type": "centroid_primitive_classifier",
        "retraining_backend": "centroid",
        "status": "trained",
        "training_implementation": "centroid_feature_model",
        "feature_names": list(FEATURE_NAMES),
        "classes": sorted(centroids),
        "centroids": {
            label: list(values)
            for label, values in sorted(centroids.items())
        },
        "feature_importance": feature_importance_from_centroids(centroids),
        "train_examples": len(train_examples),
        "source_datasets": {
            "base_dataset": str(base_dataset),
            "pseudo_dataset": str(pseudo_dataset),
            "validation_dataset": str(validation_source),
        },
        "augmentation": {
            "base_train_examples": len(baseline_train),
            "pseudo_train_examples": len(pseudo_train),
        },
        "evaluation": {
            "val": evaluate_classifier(
                centroids,
                examples_from_dataset(validation_source, splits=("val",)),
            ),
            "test": evaluate_classifier(
                centroids,
                examples_from_dataset(validation_source, splits=("test",)),
            ),
        },
        "ranking_evaluation": {
            "val": evaluate_classifier_ranking(
                centroids,
                anchors_from_dataset(validation_source, splits=("val",)),
            ),
            "test": evaluate_classifier_ranking(
                centroids,
                anchors_from_dataset(validation_source, splits=("test",)),
            ),
        },
    }
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(model, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    if comparison_output is not None:
        compare_retraining(
            base_dataset=base_dataset,
            pseudo_dataset=pseudo_dataset,
            validation_dataset=validation_dataset,
            output=comparison_output,
        )

    return model


def retrain_mlx_classifier(
    *,
    base_dataset: str | Path,
    pseudo_dataset: str | Path,
    output: str | Path,
    validation_dataset: str | Path | None = None,
    comparison_output: str | Path | None = None,
    config: MlxClassifierTrainingConfig | None = None,
) -> dict[str, object]:
    """Train and persist an augmented MLX model from reviewed labels."""

    validation_source = validation_dataset or base_dataset
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    augmented_dataset = output_path.with_name(
        f"{output_path.stem}-augmented-dataset.json"
    )
    training_config = config or MlxClassifierTrainingConfig()
    baseline_train = examples_from_dataset(base_dataset, splits=("train",))
    pseudo_train = examples_from_dataset(pseudo_dataset, splits=("train",))
    _write_augmented_retraining_dataset(
        base_dataset=base_dataset,
        pseudo_dataset=pseudo_dataset,
        validation_dataset=validation_source,
        output=augmented_dataset,
    )
    model = train_mlx_transformer_classifier(
        augmented_dataset,
        output=output_path,
        config=training_config,
    )
    source_summary = _mlx_training_source_summary(
        base_dataset=base_dataset,
        pseudo_dataset=pseudo_dataset,
        crop_size=training_config.crop_size,
        base_train_count=len(baseline_train),
        pseudo_train_count=len(pseudo_train),
    )
    model["source_datasets"] = {
        "base_dataset": str(base_dataset),
        "pseudo_dataset": str(pseudo_dataset),
        "validation_dataset": str(validation_source),
        "augmented_dataset": str(augmented_dataset),
    }
    model["augmentation"] = {
        "base_train_examples": len(baseline_train),
        "pseudo_train_examples": len(pseudo_train),
    }
    model["training_source_summary"] = source_summary
    model["retraining_backend"] = "mlx"
    output_path.write_text(
        json.dumps(model, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    if comparison_output is not None:
        compare_retraining(
            base_dataset=base_dataset,
            pseudo_dataset=pseudo_dataset,
            validation_dataset=validation_dataset,
            output=comparison_output,
        )

    return model


def _mlx_training_source_summary(
    *,
    base_dataset: str | Path,
    pseudo_dataset: str | Path,
    crop_size: int,
    base_train_count: int,
    pseudo_train_count: int,
) -> dict[str, object]:
    base_raster = raster_examples_from_dataset(
        base_dataset,
        crop_size=crop_size,
        splits=("train",),
    )
    pseudo_raster = raster_examples_from_dataset(
        pseudo_dataset,
        crop_size=crop_size,
        splits=("train",),
    )
    return {
        "crop_size": crop_size,
        "semantic_train_examples": base_train_count + pseudo_train_count,
        "semantic_base_train_examples": base_train_count,
        "semantic_pseudo_train_examples": pseudo_train_count,
        "raster_train_examples": len(base_raster) + len(pseudo_raster),
        "raster_base_train_examples": len(base_raster),
        "raster_pseudo_train_examples": len(pseudo_raster),
        "pseudo_labels_train_raster_components": bool(pseudo_raster),
    }


def _write_augmented_retraining_dataset(
    *,
    base_dataset: str | Path,
    pseudo_dataset: str | Path,
    validation_dataset: str | Path,
    output: str | Path,
) -> dict[str, object]:
    base_path = Path(base_dataset)
    pseudo_path = Path(pseudo_dataset)
    validation_path = Path(validation_dataset)
    samples: list[dict[str, object]] = []
    samples.extend(_absolute_dataset_samples(base_path, splits=("train",)))
    samples.extend(_absolute_dataset_samples(pseudo_path, splits=("train",)))
    samples.extend(_absolute_dataset_samples(validation_path, splits=("val", "test")))
    split_counts: dict[str, int] = {}
    for sample in samples:
        split = str(sample.get("split", "train"))
        split_counts[split] = split_counts.get(split, 0) + 1
    dataset = {
        "count": len(samples),
        "seed": None,
        "width": None,
        "height": None,
        "difficulty": "reviewed_pseudo_augmented",
        "splits": split_counts,
        "samples": samples,
        "source_datasets": {
            "base_dataset": str(base_dataset),
            "pseudo_dataset": str(pseudo_dataset),
            "validation_dataset": str(validation_dataset),
        },
    }
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(dataset, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return dataset


def _absolute_dataset_samples(
    dataset_path: Path,
    *,
    splits: tuple[str, ...],
) -> list[dict[str, object]]:
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    root = dataset_path.parent
    samples: list[dict[str, object]] = []
    for sample in dataset.get("samples", []):
        if sample.get("split") not in splits:
            continue
        copied = dict(sample)
        copied["manifest"] = _absolute_sample_path(root, sample.get("manifest"))
        copied["image"] = _absolute_sample_path(root, sample.get("image"))
        samples.append(copied)
    return samples


def _absolute_sample_path(root: Path, value: object) -> str | None:
    if not isinstance(value, str):
        return None
    path = Path(value)
    if not path.is_absolute():
        path = root / path
    return str(path)


def merge_reviewed_pseudo_label_dataset(
    *,
    reviewed_labels: str | Path,
    output_dir: str | Path,
) -> dict[str, object]:
    reviewed_path = Path(reviewed_labels)
    reviewed = json.loads(reviewed_path.read_text(encoding="utf-8"))
    output = Path(output_dir)
    train_dir = output / "train"
    train_dir.mkdir(parents=True, exist_ok=True)
    samples: list[dict[str, object]] = []

    for index, label in enumerate(reviewed.get("accepted", [])):
        anchor = _anchor_from_label(label)
        review = label.get("review")
        review = review if isinstance(review, dict) else {}
        applied_review = label.get("review_decision_applied")
        applied_review = applied_review if isinstance(applied_review, dict) else {}
        manifest = {
            "schema_version": 1,
            "width": label.get("width"),
            "height": label.get("height"),
            "anchor_count": 1,
            "anchors": [anchor],
            "diagnostics": [],
            "groups": _pseudo_label_groups(label),
            "layers": [],
            "metrics": {},
            "source_manifest": label.get("source_manifest"),
            "source_anchor_index": label.get("anchor_index"),
        }
        if review:
            manifest["review"] = review
        if applied_review:
            manifest["review_decision_applied"] = applied_review
        manifest_name = f"pseudo-{index:05d}.json"
        manifest_path = train_dir / manifest_name
        source_image = _reviewed_label_source_image(label, reviewed_path.parent)
        image_ref = None
        if source_image is not None:
            manifest["source_image"] = str(source_image)
            image_ref = _copy_pseudo_label_source_image(
                source_image,
                output=output,
                train_dir=train_dir,
                index=index,
            )
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        sample = {
            "id": f"pseudo-{index:05d}",
            "seed": None,
            "split": "train",
            "difficulty": "pseudo_label",
            "image": image_ref,
            "manifest": str(manifest_path.relative_to(output)),
            "source_manifest": label.get("source_manifest"),
            "source_anchor_index": label.get("anchor_index"),
            "review_decision": review.get("decision"),
            "review_item_id": review.get("review_item_id"),
            "review_reason": review.get("reason"),
            "review_issues": _issues_from_value(review.get("issues")),
            "applied_review_decision": applied_review.get("decision"),
            "applied_review_case_id": applied_review.get("case_id"),
            "applied_review_source_review_decision": applied_review.get(
                "source_review_decision"
            ),
        }
        if source_image is not None:
            sample["source_image"] = str(source_image)
        samples.append(sample)

    dataset = {
        "count": len(samples),
        "seed": None,
        "width": None,
        "height": None,
        "difficulty": "pseudo_label",
        "splits": {"train": len(samples), "val": 0, "test": 0},
        "samples": samples,
        "reviewed_label_summary": _reviewed_label_dataset_summary(samples),
        "source_reviewed_labels": str(reviewed_labels),
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "dataset.json").write_text(
        json.dumps(dataset, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return dataset


def _reviewed_label_dataset_summary(samples: list[dict[str, object]]) -> dict[str, object]:
    issue_counts: dict[str, int] = {}
    decision_counts: dict[str, int] = {}
    for sample in samples:
        decision = sample.get("applied_review_decision")
        if isinstance(decision, str) and decision:
            decision_counts[decision] = decision_counts.get(decision, 0) + 1
        _add_issue_counts(
            issue_counts,
            _issues_from_value(sample.get("review_issues")),
        )
    return {
        "sample_count": len(samples),
        "applied_review_decision_counts": dict(sorted(decision_counts.items())),
        "issue_counts": dict(sorted(issue_counts.items())),
        "provenance_field_counts": _reviewed_sample_provenance_counts(samples),
    }


def _anchor_from_label(label: dict[str, object]) -> dict[str, object]:
    embedded_anchor = label.get("anchor")
    if isinstance(embedded_anchor, dict):
        return embedded_anchor

    source_manifest = label.get("source_manifest")
    anchor_index = label.get("anchor_index")
    if isinstance(source_manifest, str) and isinstance(anchor_index, int):
        manifest_path = Path(source_manifest)
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            anchors = manifest.get("anchors", [])
            if 0 <= anchor_index < len(anchors):
                return anchors[anchor_index]

    return {
        "kind": label.get("kind"),
        "color": label.get("color"),
        "metrics": dict(label.get("metrics", {})),
    }


def _reviewed_label_source_image(
    label: dict[str, object],
    root: Path,
) -> Path | None:
    explicit = label.get("source_image")
    if isinstance(explicit, str) and explicit:
        path = Path(explicit)
        if not path.is_absolute():
            path = root / path
        if path.exists():
            return path

    source_manifest = label.get("source_manifest")
    if isinstance(source_manifest, str) and source_manifest:
        manifest_path = Path(source_manifest)
        if not manifest_path.is_absolute():
            manifest_path = root / manifest_path
        if manifest_path.exists():
            return _source_image_from_manifest_path(manifest_path)
    return None


def _copy_pseudo_label_source_image(
    source_image: Path,
    *,
    output: Path,
    train_dir: Path,
    index: int,
) -> str:
    suffix = source_image.suffix or ".png"
    image_path = train_dir / f"pseudo-{index:05d}{suffix}"
    if source_image.resolve() != image_path.resolve():
        shutil.copy2(source_image, image_path)
    return str(image_path.relative_to(output))


def _pseudo_label_groups(label: dict[str, object]) -> list[dict[str, object]]:
    context = label.get("group_context", [])
    if not isinstance(context, list):
        return []
    groups = []
    for index, group in enumerate(context):
        if not isinstance(group, dict):
            continue
        groups.append(
            {
                "id": f"pseudo-group-{index:04d}",
                "kind": group.get("kind"),
                "anchor_indexes": [0],
                "metrics": group.get("metrics", {}),
                "source_group_id": group.get("id"),
                "source_anchor_indexes": group.get("anchor_indexes", []),
                "source_anchor_position": group.get("anchor_position"),
                "color": group.get("color"),
            }
        )
    return groups


def create_review_file(
    *,
    pseudo_labels: str | Path,
    output: str | Path,
    markdown: str | Path | None = None,
    accept_applied_reviews: bool = False,
) -> dict[str, object]:
    source = json.loads(Path(pseudo_labels).read_text(encoding="utf-8"))
    review_items = []
    for index, label in enumerate(source.get("pseudo_labels", [])):
        review_items.append(
            _review_item_from_label(
                index,
                label,
                accept_applied_reviews=accept_applied_reviews,
            )
        )
    review = {
        "source": str(pseudo_labels),
        "review_count": len(review_items),
        "auto_accepted_applied_review_count": sum(
            1
            for item in review_items
            if item.get("decision") == "accept"
            and item.get("applied_review_decision")
        ),
        "auto_rejected_applied_review_count": sum(
            1
            for item in review_items
            if item.get("decision") == "reject"
            and item.get("applied_review_decision")
        ),
        "issue_counts": _issue_counts_from_review_items(review_items),
        "items": review_items,
    }
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(review, indent=2, sort_keys=True), encoding="utf-8")
    if markdown is not None:
        markdown_path = Path(markdown)
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(render_review_markdown(review), encoding="utf-8")
    return review


def _review_item_from_label(
    index: int,
    label: object,
    *,
    accept_applied_reviews: bool,
) -> dict[str, object]:
    item = {
        "id": f"review-{index:05d}",
        "decision": "pending",
        "reason": "",
        "corrected_kind": "",
        "issues": [],
        "label": label,
    }
    if not accept_applied_reviews or not isinstance(label, dict):
        return item
    applied = label.get("review_decision_applied")
    if not isinstance(applied, dict) or not applied:
        return item
    decision = applied.get("decision")
    if decision in {"accepted", "corrected"}:
        item["decision"] = "accept"
        item["reason"] = f"applied_review_{decision}"
    elif decision in {"rejected", "deferred"}:
        item["decision"] = "reject"
        item["reason"] = f"applied_review_{decision}"
    else:
        item["reason"] = "invalid_applied_review_decision"
    item["issues"] = _issues_from_value(applied.get("issue_tags"))
    item["applied_review_decision"] = {
        "case_id": applied.get("case_id"),
        "decision": decision,
        "source_review_decision": applied.get("source_review_decision"),
    }
    return item


def render_review_markdown(review: dict[str, object]) -> str:
    items = review.get("items", [])
    if not isinstance(items, list):
        items = []
    lines = [
        "# Morphēa Review Queue",
        "",
        f"- Source: `{review.get('source', 'n/a')}`",
        f"- Items: {_fmt_metric(review.get('review_count'))}",
        f"- Auto-accepted applied reviews: {_fmt_metric(review.get('auto_accepted_applied_review_count'))}",
        f"- Auto-rejected applied reviews: {_fmt_metric(review.get('auto_rejected_applied_review_count'))}",
        f"- Issue counts: {_format_issue_counts(_review_issue_counts(review, items))}",
        "",
        "| ID | Decision | Kind | Groups | Quality error | Issues |",
        "| --- | --- | --- | --- | ---: | --- |",
    ]
    if items:
        for item in items:
            if not isinstance(item, dict):
                continue
            label = item.get("label", {})
            if not isinstance(label, dict):
                label = {}
            issues = item.get("issues", [])
            if not isinstance(issues, list):
                issues = []
            lines.append(
                "| "
                f"`{item.get('id', 'n/a')}` | "
                f"`{item.get('decision', 'n/a')}` | "
                f"`{label.get('kind', 'n/a')}` | "
                f"{_format_group_context(label.get('group_context', []))} | "
                f"{_fmt_metric(label.get('anchor_quality_error'))} | "
                f"{', '.join(str(issue) for issue in issues) or 'n/a'} |"
            )
    else:
        lines.append("| n/a | n/a | n/a | n/a | n/a | n/a |")
    return "\n".join(lines) + "\n"


def apply_review_file(
    *,
    review: str | Path,
    output: str | Path,
    markdown: str | Path | None = None,
) -> dict[str, object]:
    review_data = json.loads(Path(review).read_text(encoding="utf-8"))
    accepted = []
    rejected = []
    pending = []
    for item in review_data.get("items", []):
        decision = item.get("decision")
        if decision == "accept":
            accepted.append(_reviewed_label(item))
        elif decision == "reject":
            rejected.append(
                {
                    "id": item.get("id"),
                    "reason": item.get("reason", ""),
                    "corrected_kind": _corrected_kind(item),
                    "issues": _review_issues(item),
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
        "issue_counts": _issue_counts_from_apply_result(
            accepted=accepted,
            rejected=rejected,
            pending_items=_pending_review_items(review_data.get("items", [])),
        ),
        "source_review": str(review),
    }
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    if markdown is not None:
        markdown_path = Path(markdown)
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(
            render_apply_review_markdown(result),
            encoding="utf-8",
        )
    return result


def render_apply_review_markdown(result: dict[str, object]) -> str:
    accepted = result.get("accepted", [])
    if not isinstance(accepted, list):
        accepted = []
    rejected = result.get("rejected", [])
    if not isinstance(rejected, list):
        rejected = []
    pending = result.get("pending", [])
    if not isinstance(pending, list):
        pending = []

    lines = [
        "# Morphēa Apply Review",
        "",
        f"- Source review: `{result.get('source_review', 'n/a')}`",
        f"- Accepted: {_fmt_metric(result.get('accepted_count'))}",
        f"- Rejected: {_fmt_metric(result.get('rejected_count'))}",
        f"- Pending: {_fmt_metric(result.get('pending_count'))}",
        f"- Issue counts: {_format_issue_counts(_apply_issue_counts(result))}",
        "",
        "## Accepted",
        "",
        "| Kind | Corrected kind | Groups | Issues |",
        "| --- | --- | --- | --- |",
    ]
    if accepted:
        for label in accepted:
            if not isinstance(label, dict):
                continue
            review = label.get("review", {})
            if not isinstance(review, dict):
                review = {}
            issues = review.get("issues", [])
            if not isinstance(issues, list):
                issues = []
            lines.append(
                "| "
                f"`{label.get('kind', 'n/a')}` | "
                f"`{review.get('corrected_kind') or 'n/a'}` | "
                f"{_format_group_context(label.get('group_context', []))} | "
                f"{', '.join(str(issue) for issue in issues) or 'n/a'} |"
            )
    else:
        lines.append("| n/a | n/a | n/a | n/a |")

    lines.extend(
        [
            "",
            "## Rejected",
            "",
            "| ID | Reason | Groups | Issues |",
            "| --- | --- | --- | --- |",
        ]
    )
    if rejected:
        for item in rejected:
            if not isinstance(item, dict):
                continue
            issues = item.get("issues", [])
            if not isinstance(issues, list):
                issues = []
            lines.append(
                "| "
                f"`{item.get('id', 'n/a')}` | "
                f"{item.get('reason', '') or 'n/a'} | "
                f"{_rejected_group_context(item)} | "
                f"{', '.join(str(issue) for issue in issues) or 'n/a'} |"
            )
    else:
        lines.append("| n/a | n/a | n/a | n/a |")

    lines.extend(
        [
            "",
            "## Pending",
            "",
            ", ".join(f"`{item}`" for item in pending) if pending else "n/a",
        ]
    )
    return "\n".join(lines) + "\n"


def _review_issue_counts(
    review: dict[str, object],
    items: list[object],
) -> dict[str, int]:
    issue_counts = review.get("issue_counts")
    if isinstance(issue_counts, dict):
        return {
            str(issue): int(count)
            for issue, count in issue_counts.items()
            if isinstance(count, (int, float))
        }
    return _issue_counts_from_review_items(items)


def _apply_issue_counts(result: dict[str, object]) -> dict[str, int]:
    issue_counts = result.get("issue_counts")
    if isinstance(issue_counts, dict):
        return {
            str(issue): int(count)
            for issue, count in issue_counts.items()
            if isinstance(count, (int, float))
        }
    accepted = result.get("accepted", [])
    rejected = result.get("rejected", [])
    return _issue_counts_from_apply_result(
        accepted=accepted if isinstance(accepted, list) else [],
        rejected=rejected if isinstance(rejected, list) else [],
        pending_items=[],
    )


def _issue_counts_from_review_items(items: list[object]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        _add_issue_counts(counts, _review_issues(item))
    return dict(sorted(counts.items()))


def _issue_counts_from_apply_result(
    *,
    accepted: list[object],
    rejected: list[object],
    pending_items: list[object],
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for label in accepted:
        if not isinstance(label, dict):
            continue
        review = label.get("review", {})
        if isinstance(review, dict):
            _add_issue_counts(counts, _issues_from_value(review.get("issues", [])))
    for item in rejected:
        if isinstance(item, dict):
            _add_issue_counts(counts, _issues_from_value(item.get("issues", [])))
    for item in pending_items:
        if isinstance(item, dict):
            _add_issue_counts(counts, _review_issues(item))
    return dict(sorted(counts.items()))


def _pending_review_items(items: object) -> list[object]:
    if not isinstance(items, list):
        return []
    return [
        item
        for item in items
        if isinstance(item, dict) and item.get("decision") not in {"accept", "reject"}
    ]


def _add_issue_counts(counts: dict[str, int], issues: list[str]) -> None:
    for issue in issues:
        counts[issue] = counts.get(issue, 0) + 1


def _format_issue_counts(issue_counts: dict[str, int]) -> str:
    if not issue_counts:
        return "`none`"
    return "`" + ", ".join(
        f"{issue}: {count}" for issue, count in sorted(issue_counts.items())
    ) + "`"


def _model_component_summary_markdown(summary: dict[str, object]) -> list[str]:
    lines = [
        f"- MLX total parameters: {_fmt_metric(summary.get('total_parameter_count'))}",
        f"- MLX trainable components: {_fmt_metric(summary.get('trainable_component_count'))}",
        f"- MLX autograd components: {_fmt_metric(summary.get('mlx_autograd_component_count'))}",
        "",
        "| Priority | Component | Runtime | Training examples | Parameters | Loss epochs | Raster tokens |",
        "| ---: | --- | --- | ---: | ---: | ---: | --- |",
    ]
    components = summary.get("components", [])
    if isinstance(components, list):
        for component in components:
            if not isinstance(component, dict):
                continue
            lines.append(
                "| "
                f"{_fmt_metric(component.get('inference_priority'))} | "
                f"`{component.get('name', 'unknown')}` | "
                f"`{component.get('training_runtime', 'unknown')}` | "
                f"{_fmt_metric(component.get('training_example_count'))} | "
                f"{_fmt_metric(component.get('parameter_count'))} | "
                f"{_fmt_metric(component.get('loss_epochs'))} | "
                f"`{bool(component.get('uses_raster_tokens'))}` |"
            )
    return lines


def _model_training_source_markdown(summary: dict[str, object]) -> list[str]:
    return [
        "",
        (
            "- MLX semantic source examples: "
            f"base={_fmt_metric(summary.get('semantic_base_train_examples'))}, "
            f"pseudo={_fmt_metric(summary.get('semantic_pseudo_train_examples'))}"
        ),
        (
            "- MLX raster source examples: "
            f"base={_fmt_metric(summary.get('raster_base_train_examples'))}, "
            f"pseudo={_fmt_metric(summary.get('raster_pseudo_train_examples'))}"
        ),
        f"- Pseudo labels train raster components: `{bool(summary.get('pseudo_labels_train_raster_components'))}`",
    ]


def _counts_from_object(value: object) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    return {
        str(key): int(count)
        for key, count in value.items()
        if isinstance(count, (int, float))
    }


def _reviewed_sample_provenance_counts(value: object) -> dict[str, int]:
    samples = value if isinstance(value, list) else []
    fields = (
        "review_item_id",
        "review_reason",
        "source_image",
        "applied_review_case_id",
        "applied_review_source_review_decision",
    )
    counts = {field: 0 for field in fields}
    for sample in samples:
        if not isinstance(sample, dict):
            continue
        for field in fields:
            if sample.get(field):
                counts[field] += 1
    return {field: count for field, count in counts.items() if count}


def _reviewed_label(item: dict[str, object]) -> dict[str, object]:
    label = dict(item.get("label", {}))
    corrected_kind = _corrected_kind(item)
    issues = _review_issues(item)
    if corrected_kind is not None:
        label["kind"] = corrected_kind
        anchor = label.get("anchor")
        if isinstance(anchor, dict):
            changed_anchor = dict(anchor)
            changed_anchor["kind"] = corrected_kind
            label["anchor"] = changed_anchor
    label["review"] = {
        "decision": "accept",
        "review_item_id": item.get("id"),
        "reason": item.get("reason", ""),
        "corrected_kind": corrected_kind,
        "issues": issues,
    }
    return label


def _corrected_kind(item: dict[str, object]) -> str | None:
    value = item.get("corrected_kind")
    if isinstance(value, str) and value:
        return value
    return None


def _review_issues(item: dict[str, object]) -> list[str]:
    return _issues_from_value(item.get("issues", []))


def _issues_from_value(value: object) -> list[str]:
    issues = value
    if not isinstance(issues, list):
        return []
    return [issue for issue in issues if isinstance(issue, str) and issue]


def _training_comparison_model(
    *,
    train_examples: tuple[TrainingExample, ...],
    validation_dataset: str | Path,
) -> dict[str, object]:
    centroids = centroids_from_examples(train_examples)
    return {
        "model_type": "centroid_primitive_classifier",
        "train_examples": len(train_examples),
        "classes": sorted(centroids),
        "feature_importance": feature_importance_from_centroids(centroids),
        "evaluation": {
            "val": evaluate_classifier(
                centroids,
                examples_from_dataset(validation_dataset, splits=("val",)),
            ),
            "test": evaluate_classifier(
                centroids,
                examples_from_dataset(validation_dataset, splits=("test",)),
            ),
        },
        "ranking_evaluation": {
            "val": evaluate_classifier_ranking(
                centroids,
                anchors_from_dataset(validation_dataset, splits=("val",)),
            ),
            "test": evaluate_classifier_ranking(
                centroids,
                anchors_from_dataset(validation_dataset, splits=("test",)),
            ),
        },
    }


def render_training_comparison_markdown(report: dict[str, object]) -> str:
    summary = report.get("summary", {})
    if not isinstance(summary, dict):
        summary = {}
    lines = [
        "# Morphēa Training Comparison",
        "",
        f"- Base dataset: `{report.get('base_dataset')}`",
        f"- Pseudo dataset: `{report.get('pseudo_dataset')}`",
        f"- Validation dataset: `{report.get('validation_dataset')}`",
        f"- Status: `{summary.get('status', 'n/a')}`",
        f"- Train example delta: {_fmt_metric(summary.get('train_examples_delta'))}",
        f"- Best accuracy delta: {_fmt_metric(summary.get('best_accuracy_delta'))}",
        f"- Worst accuracy delta: {_fmt_metric(summary.get('worst_accuracy_delta'))}",
        "",
        "| Split | Baseline accuracy | Augmented accuracy | Delta | "
        "Baseline rank | Augmented rank | Rank delta |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    baseline = report.get("baseline", {})
    augmented = report.get("augmented", {})
    delta = report.get("delta", {})
    for split in ("val", "test"):
        lines.append(
            "| "
            f"`{split}` | "
            f"{_fmt_metric(_split_metric_for_markdown(baseline, 'evaluation', split, 'accuracy'))} | "
            f"{_fmt_metric(_split_metric_for_markdown(augmented, 'evaluation', split, 'accuracy'))} | "
            f"{_fmt_metric(_delta_for_markdown(delta, 'evaluation', split))} | "
            f"{_fmt_metric(_split_metric_for_markdown(baseline, 'ranking_evaluation', split, 'classifier_accuracy'))} | "
            f"{_fmt_metric(_split_metric_for_markdown(augmented, 'ranking_evaluation', split, 'classifier_accuracy'))} | "
            f"{_fmt_metric(_delta_for_markdown(delta, 'ranking_evaluation', split, 'classifier_accuracy'))} |"
        )
    label_delta = delta.get("label_accuracy", {})
    if isinstance(label_delta, dict) and label_delta:
        lines.extend(
            [
                "",
                "## Label Accuracy Delta",
                "",
                "| Split | Label | Baseline | Augmented | Delta |",
                "| --- | --- | ---: | ---: | ---: |",
            ]
        )
        for split in ("val", "test"):
            split_data = label_delta.get(split, {})
            if not isinstance(split_data, dict):
                continue
            for label, item in sorted(split_data.items()):
                if not isinstance(item, dict):
                    continue
                lines.append(
                    "| "
                    f"`{split}` | "
                    f"`{label}` | "
                    f"{_fmt_metric(item.get('baseline_accuracy'))} | "
                    f"{_fmt_metric(item.get('augmented_accuracy'))} | "
                    f"{_fmt_metric(item.get('accuracy_delta'))} |"
                )
    ranking_decisions = delta.get("ranking_decisions", {})
    if isinstance(ranking_decisions, dict):
        rows = _ranking_decision_markdown_rows(ranking_decisions)
        if rows:
            lines.extend(
                [
                    "",
                    "## Ranking Decision Delta",
                    "",
                    "| Split | Outcome | Index | Label | Heuristic | Baseline | Augmented |",
                    "| --- | --- | ---: | --- | --- | --- | --- |",
                ]
            )
            lines.extend(rows)
    importance_delta = delta.get("feature_importance", {})
    if isinstance(importance_delta, list) and importance_delta:
        lines.extend(
            [
                "",
                "## Feature Importance Delta",
                "",
                "| Feature | Baseline spread | Augmented spread | Delta |",
                "| --- | ---: | ---: | ---: |",
            ]
        )
        for item in importance_delta[:8]:
            if not isinstance(item, dict):
                continue
            lines.append(
                "| "
                f"`{item.get('feature')}` | "
                f"{_fmt_metric(item.get('baseline_spread'))} | "
                f"{_fmt_metric(item.get('augmented_spread'))} | "
                f"{_fmt_metric(item.get('spread_delta'))} |"
            )
    return "\n".join(lines) + "\n"


def _split_metric_for_markdown(
    report: object,
    section: str,
    split: str,
    metric: str,
) -> object:
    if not isinstance(report, dict):
        return None
    return _split_metric(report, section, split, metric)


def _delta_for_markdown(
    delta: object,
    section: str,
    split: str,
    metric: str | None = None,
) -> object:
    if not isinstance(delta, dict):
        return None
    section_data = delta.get(section, {})
    if not isinstance(section_data, dict):
        return None
    split_data = section_data.get(split)
    if metric is None:
        return split_data
    if not isinstance(split_data, dict):
        return None
    return split_data.get(metric)


def _fmt_metric(value: object) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    if value is None:
        return "n/a"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def _ranking_decision_markdown_rows(value: dict[str, object]) -> list[str]:
    rows = []
    for split in ("val", "test"):
        split_data = value.get(split, {})
        if not isinstance(split_data, dict):
            continue
        items = split_data.get("items", [])
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            rows.append(
                "| "
                f"`{split}` | "
                f"`{_metric_delta_cell(item.get('outcome'))}` | "
                f"{_fmt_metric(item.get('index'))} | "
                f"`{_metric_delta_cell(item.get('label'))}` | "
                f"`{_metric_delta_cell(item.get('heuristic'))}` | "
                f"`{_metric_delta_cell(item.get('baseline_classifier'))}` | "
                f"`{_metric_delta_cell(item.get('augmented_classifier'))}` |"
            )
    return rows


def _training_comparison_delta(
    baseline: dict[str, object],
    augmented: dict[str, object],
) -> dict[str, object]:
    return {
        "train_examples": (
            int(augmented.get("train_examples", 0))
            - int(baseline.get("train_examples", 0))
        ),
        "evaluation": {
            split: _accuracy_delta(
                _split_metric(baseline, "evaluation", split, "accuracy"),
                _split_metric(augmented, "evaluation", split, "accuracy"),
            )
            for split in ("val", "test")
        },
        "ranking_evaluation": {
            split: {
                "classifier_accuracy": _accuracy_delta(
                    _split_metric(
                        baseline,
                        "ranking_evaluation",
                        split,
                        "classifier_accuracy",
                    ),
                    _split_metric(
                        augmented,
                        "ranking_evaluation",
                        split,
                        "classifier_accuracy",
                    ),
                ),
                "accuracy_improvement": _accuracy_delta(
                    _split_metric(
                        baseline,
                        "ranking_evaluation",
                        split,
                        "accuracy_improvement",
                    ),
                    _split_metric(
                        augmented,
                        "ranking_evaluation",
                        split,
                        "accuracy_improvement",
                    ),
                ),
            }
            for split in ("val", "test")
        },
        "label_accuracy": {
            split: _label_accuracy_delta(
                _split_object_metric(baseline, "evaluation", split, "label_accuracy"),
                _split_object_metric(augmented, "evaluation", split, "label_accuracy"),
            )
            for split in ("val", "test")
        },
        "ranking_decisions": _ranking_decision_delta(baseline, augmented),
        "feature_importance": _feature_importance_delta(baseline, augmented),
    }


def _training_comparison_summary(delta: dict[str, object]) -> dict[str, object]:
    metric_deltas = _comparison_metric_deltas(delta)
    if not metric_deltas:
        status = "insufficient_data"
        best_delta = None
        worst_delta = None
    else:
        best_delta = max(metric_deltas)
        worst_delta = min(metric_deltas)
        if best_delta > 0 and worst_delta >= 0:
            status = "improved"
        elif best_delta <= 0 and worst_delta < 0:
            status = "regressed"
        elif best_delta > 0 and worst_delta < 0:
            status = "mixed"
        else:
            status = "unchanged"
    return {
        "status": status,
        "metric_count": len(metric_deltas),
        "best_accuracy_delta": best_delta,
        "worst_accuracy_delta": worst_delta,
        "train_examples_delta": delta.get("train_examples"),
    }


def _comparison_metric_deltas(delta: dict[str, object]) -> list[float]:
    return [
        float(row["delta"])
        for row in _comparison_metric_delta_rows(delta)
        if isinstance(row.get("delta"), (int, float))
    ]


def _comparison_metric_delta_rows(delta: dict[str, object]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    evaluation = delta.get("evaluation", {})
    if isinstance(evaluation, dict):
        for split, value in sorted(evaluation.items()):
            if isinstance(value, (int, float)):
                rows.append(
                    {
                        "metric": "evaluation.accuracy",
                        "split": str(split),
                        "label": None,
                        "delta": float(value),
                    }
                )
    ranking = delta.get("ranking_evaluation", {})
    if isinstance(ranking, dict):
        for split, split_data in sorted(ranking.items()):
            if not isinstance(split_data, dict):
                continue
            for metric, value in sorted(split_data.items()):
                if isinstance(value, (int, float)):
                    rows.append(
                        {
                            "metric": f"ranking_evaluation.{metric}",
                            "split": str(split),
                            "label": None,
                            "delta": float(value),
                        }
                    )
    labels = delta.get("label_accuracy", {})
    if isinstance(labels, dict):
        for split, split_data in sorted(labels.items()):
            if not isinstance(split_data, dict):
                continue
            for label, label_data in sorted(split_data.items()):
                if not isinstance(label_data, dict):
                    continue
                value = label_data.get("accuracy_delta")
                if isinstance(value, (int, float)):
                    rows.append(
                        {
                            "metric": "label_accuracy",
                            "split": str(split),
                            "label": str(label),
                            "delta": float(value),
                        }
                    )
    return rows


def _ranking_decision_delta(
    baseline: dict[str, object],
    augmented: dict[str, object],
) -> dict[str, object]:
    return {
        split: _ranking_decision_split_delta(
            _ranking_decisions(
                _split_object_metric(
                    baseline,
                    "ranking_evaluation",
                    split,
                    "decisions",
                )
            ),
            _ranking_decisions(
                _split_object_metric(
                    augmented,
                    "ranking_evaluation",
                    split,
                    "decisions",
                )
            ),
        )
        for split in ("val", "test")
    }


def _ranking_decision_split_delta(
    baseline: list[dict[str, object]],
    augmented: list[dict[str, object]],
) -> dict[str, object]:
    items = []
    regression_count = 0
    improvement_count = 0
    changed_count = 0
    compared_count = min(len(baseline), len(augmented))
    for index, (base_item, augmented_item) in enumerate(
        zip(baseline, augmented, strict=False)
    ):
        label = _decision_value(augmented_item, "label") or _decision_value(
            base_item,
            "label",
        )
        baseline_classifier = _decision_value(base_item, "classifier")
        augmented_classifier = _decision_value(augmented_item, "classifier")
        baseline_correct = bool(label and baseline_classifier == label)
        augmented_correct = bool(label and augmented_classifier == label)
        changed = baseline_classifier != augmented_classifier
        if not changed and baseline_correct == augmented_correct:
            continue
        if baseline_correct and not augmented_correct:
            outcome = "regression"
            regression_count += 1
        elif not baseline_correct and augmented_correct:
            outcome = "improvement"
            improvement_count += 1
        else:
            outcome = "changed"
        if changed:
            changed_count += 1
        heuristic = _decision_value(augmented_item, "heuristic") or _decision_value(
            base_item,
            "heuristic",
        )
        items.append(
            {
                "index": index,
                "label": label,
                "heuristic": heuristic,
                "baseline_classifier": baseline_classifier,
                "augmented_classifier": augmented_classifier,
                "baseline_correct": baseline_correct,
                "augmented_correct": augmented_correct,
                "outcome": outcome,
            }
        )
    return {
        "baseline_count": len(baseline),
        "augmented_count": len(augmented),
        "compared_count": compared_count,
        "changed_count": changed_count,
        "regression_count": regression_count,
        "improvement_count": improvement_count,
        "items": items,
    }


def _ranking_decisions(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _decision_value(item: dict[str, object], key: str) -> str | None:
    value = item.get(key)
    if isinstance(value, str) and value:
        return value
    return None


def _feature_importance_delta(
    baseline: dict[str, object],
    augmented: dict[str, object],
) -> list[dict[str, object]]:
    baseline_importance = _feature_importance_by_name(
        baseline.get("feature_importance", [])
    )
    augmented_importance = _feature_importance_by_name(
        augmented.get("feature_importance", [])
    )
    features = sorted(set(baseline_importance) | set(augmented_importance))
    rows: list[dict[str, object]] = []
    for feature in features:
        baseline_spread = baseline_importance.get(feature, 0.0)
        augmented_spread = augmented_importance.get(feature, 0.0)
        rows.append(
            {
                "feature": feature,
                "baseline_spread": baseline_spread,
                "augmented_spread": augmented_spread,
                "spread_delta": augmented_spread - baseline_spread,
            }
        )
    return sorted(
        rows,
        key=lambda item: (
            -abs(float(item["spread_delta"])),
            str(item["feature"]),
        ),
    )


def _feature_importance_by_name(value: object) -> dict[str, float]:
    if not isinstance(value, list):
        return {}
    result: dict[str, float] = {}
    for item in value:
        if not isinstance(item, dict):
            continue
        feature = item.get("feature")
        spread = item.get("spread")
        if isinstance(feature, str) and isinstance(spread, (int, float)):
            result[feature] = float(spread)
    return result


def _split_metric(
    report: dict[str, object],
    section: str,
    split: str,
    metric: str,
) -> float | None:
    section_data = report.get(section, {})
    if not isinstance(section_data, dict):
        return None
    split_data = section_data.get(split, {})
    if not isinstance(split_data, dict):
        return None
    value = split_data.get(metric)
    return float(value) if isinstance(value, (int, float)) else None


def _split_object_metric(
    report: dict[str, object],
    section: str,
    split: str,
    metric: str,
) -> object:
    section_data = report.get(section, {})
    if not isinstance(section_data, dict):
        return None
    split_data = section_data.get(split, {})
    if not isinstance(split_data, dict):
        return None
    return split_data.get(metric)


def _accuracy_delta(
    baseline: float | None,
    augmented: float | None,
) -> float | None:
    if baseline is None or augmented is None:
        return None
    return augmented - baseline


def _label_accuracy_delta(
    baseline: object,
    augmented: object,
) -> dict[str, dict[str, object]]:
    if not isinstance(baseline, dict):
        baseline = {}
    if not isinstance(augmented, dict):
        augmented = {}
    labels = sorted(set(baseline) | set(augmented))
    result: dict[str, dict[str, object]] = {}
    for label in labels:
        baseline_data = baseline.get(label, {})
        augmented_data = augmented.get(label, {})
        if not isinstance(baseline_data, dict):
            baseline_data = {}
        if not isinstance(augmented_data, dict):
            augmented_data = {}
        baseline_accuracy = baseline_data.get("accuracy")
        augmented_accuracy = augmented_data.get("accuracy")
        result[str(label)] = {
            "baseline_accuracy": baseline_accuracy,
            "augmented_accuracy": augmented_accuracy,
            "accuracy_delta": _accuracy_delta(
                float(baseline_accuracy)
                if isinstance(baseline_accuracy, (int, float))
                else None,
                float(augmented_accuracy)
                if isinstance(augmented_accuracy, (int, float))
                else None,
            ),
            "baseline_examples": baseline_data.get("examples"),
            "augmented_examples": augmented_data.get("examples"),
        }
    return result
