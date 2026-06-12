"""Pseudo-label harvesting for the self-learning loop."""

from __future__ import annotations

import json
from pathlib import Path

from curve.classifier import (
    FEATURE_NAMES,
    TrainingExample,
    anchors_from_dataset,
    centroids_from_examples,
    evaluate_classifier,
    evaluate_classifier_ranking,
    examples_from_dataset,
    feature_importance_from_centroids,
)
from curve.curated import check_curated_suite
from curve.mlx_classifier import (
    MlxClassifierTrainingConfig,
    train_mlx_transformer_classifier,
)


HARVEST_FILTER_DEFAULTS = {
    "max_run_diagnostics": 0,
    "max_classifier_prior_error": 0.0,
    "min_editability_score": 0.0,
    "max_fragmentation_penalty": 1.0,
    "max_raster_l1_error": 1.0,
    "max_raster_edge_error": 1.0,
    "max_anchor_quality_error": 1.0,
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
            metrics = anchor.get("metrics", {})
            prior_error = float(metrics.get("classifier_prior_error", 0.0))
            if prior_error > max_classifier_prior_error:
                continue
            quality_error = _anchor_quality_error(metrics)
            if quality_error > max_anchor_quality_error:
                continue
            records.append(
                {
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
            "max_raster_l1_error": max_raster_l1_error,
            "max_raster_edge_error": max_raster_edge_error,
            "max_anchor_quality_error": max_anchor_quality_error,
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
) -> dict[str, object]:
    curated = check_curated_suite(
        suite,
        output=curated_report,
        output_dir=run_root,
        run=True,
        snapshot=snapshot,
    )
    result = harvest_pseudo_labels(
        run_root=run_root,
        output=output,
        max_run_diagnostics=max_run_diagnostics,
        max_classifier_prior_error=max_classifier_prior_error,
        min_editability_score=min_editability_score,
        max_fragmentation_penalty=max_fragmentation_penalty,
        max_raster_l1_error=max_raster_l1_error,
        max_raster_edge_error=max_raster_edge_error,
        max_anchor_quality_error=max_anchor_quality_error,
    )
    result.update(
        {
            "schema_version": 1,
            "source": "curated_suite",
            "suite": str(suite),
            "run_root": str(run_root),
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
        "# Curve Pseudo-Label Harvest",
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
        "# Curve Training Gate",
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
    return "\n".join(lines) + "\n"


def _fmt_gate_value(value: object) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    return _fmt_metric(value)


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
    min_train_examples_delta: int = 1,
    min_best_accuracy_delta: float = 0.0,
    max_worst_accuracy_drop: float = 0.0,
    allow_unchanged: bool = False,
    markdown: str | Path | None = None,
) -> dict[str, object]:
    """Run the reviewed-label retraining decision loop as one repeatable cycle."""

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
            curated_validation = {
                "status": "checked",
                "suite": str(curated_suite),
                "ok": curated["ok"],
                "case_count": curated["case_count"],
                "checked_count": sum(
                    1
                    for case in curated.get("cases", [])
                    if isinstance(case, dict) and case.get("status") == "checked"
                ),
                "missing_source_count": sum(
                    1
                    for case in curated.get("cases", [])
                    if isinstance(case, dict)
                    and case.get("status") == "missing_source"
                ),
            }
        else:
            curated_validation = {
                "status": "skipped_gate_not_accepted",
                "suite": str(curated_suite),
                "ok": None,
                "case_count": 0,
                "checked_count": 0,
                "missing_source_count": 0,
            }

    result = {
        "schema_version": 1,
        "status": "retrained" if model is not None else "skipped_retrain",
        "base_dataset": str(base_dataset),
        "reviewed_labels": str(reviewed_labels),
        "validation_dataset": str(validation_dataset or base_dataset),
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
        },
        "pseudo_dataset": {
            "count": pseudo_dataset["count"],
            "splits": pseudo_dataset["splits"],
        },
        "comparison_summary": comparison["summary"],
        "gate": {
            "decision": gate["decision"],
            "accepted": gate["accepted"],
            "reasons": gate["reasons"],
        },
        "model": (
            {
                "model_type": model["model_type"],
                "train_examples": model["train_examples"],
                "augmentation": model["augmentation"],
            }
            if model is not None
            else None
        ),
        "curated_validation": curated_validation,
    }
    summary_path = output / "self-learning-cycle.json"
    summary_path.write_text(
        json.dumps(result, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    if markdown is not None:
        markdown_path = Path(markdown)
    else:
        markdown_path = output / "self-learning-cycle.md"
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(render_self_learning_cycle_markdown(result), encoding="utf-8")
    result["artifacts"]["summary"] = str(summary_path)
    result["artifacts"]["summary_markdown"] = str(markdown_path)
    summary_path.write_text(
        json.dumps(result, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return result


def render_self_learning_cycle_markdown(result: dict[str, object]) -> str:
    artifacts = result.get("artifacts", {})
    if not isinstance(artifacts, dict):
        artifacts = {}
    gate = result.get("gate", {})
    if not isinstance(gate, dict):
        gate = {}
    comparison = result.get("comparison_summary", {})
    if not isinstance(comparison, dict):
        comparison = {}
    pseudo_dataset = result.get("pseudo_dataset", {})
    if not isinstance(pseudo_dataset, dict):
        pseudo_dataset = {}
    lines = [
        "# Curve Self-Learning Cycle",
        "",
        f"- Status: `{result.get('status', 'n/a')}`",
        f"- Gate decision: `{gate.get('decision', 'n/a')}`",
        f"- Gate accepted: `{gate.get('accepted', False)}`",
        f"- Pseudo-label examples: {_fmt_metric(pseudo_dataset.get('count'))}",
        f"- Comparison status: `{comparison.get('status', 'n/a')}`",
        f"- Best accuracy delta: {_fmt_metric(comparison.get('best_accuracy_delta'))}",
        f"- Worst accuracy delta: {_fmt_metric(comparison.get('worst_accuracy_delta'))}",
    ]
    curated = result.get("curated_validation")
    if isinstance(curated, dict):
        lines.extend(
            [
                f"- Curated validation: `{curated.get('status', 'n/a')}`",
                f"- Curated OK: `{curated.get('ok', 'n/a')}`",
                f"- Curated checked cases: {_fmt_metric(curated.get('checked_count'))}",
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
        config=config,
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
    reviewed = json.loads(Path(reviewed_labels).read_text(encoding="utf-8"))
    output = Path(output_dir)
    train_dir = output / "train"
    train_dir.mkdir(parents=True, exist_ok=True)
    samples: list[dict[str, object]] = []

    for index, label in enumerate(reviewed.get("accepted", [])):
        anchor = _anchor_from_label(label)
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
        manifest_name = f"pseudo-{index:05d}.json"
        manifest_path = train_dir / manifest_name
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        samples.append(
            {
                "id": f"pseudo-{index:05d}",
                "seed": None,
                "split": "train",
                "difficulty": "pseudo_label",
                "image": None,
                "manifest": str(manifest_path.relative_to(output)),
                "source_manifest": label.get("source_manifest"),
                "source_anchor_index": label.get("anchor_index"),
            }
        )

    dataset = {
        "count": len(samples),
        "seed": None,
        "width": None,
        "height": None,
        "difficulty": "pseudo_label",
        "splits": {"train": len(samples), "val": 0, "test": 0},
        "samples": samples,
        "source_reviewed_labels": str(reviewed_labels),
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "dataset.json").write_text(
        json.dumps(dataset, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return dataset


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
) -> dict[str, object]:
    source = json.loads(Path(pseudo_labels).read_text(encoding="utf-8"))
    review_items = []
    for index, label in enumerate(source.get("pseudo_labels", [])):
        review_items.append(
            {
                "id": f"review-{index:05d}",
                "decision": "pending",
                "reason": "",
                "corrected_kind": "",
                "issues": [],
                "label": label,
            }
        )
    review = {
        "source": str(pseudo_labels),
        "review_count": len(review_items),
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


def render_review_markdown(review: dict[str, object]) -> str:
    items = review.get("items", [])
    if not isinstance(items, list):
        items = []
    lines = [
        "# Curve Review Queue",
        "",
        f"- Source: `{review.get('source', 'n/a')}`",
        f"- Items: {_fmt_metric(review.get('review_count'))}",
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
        "# Curve Apply Review",
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
        "# Curve Training Comparison",
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
    if isinstance(value, bool) or value is None:
        return "n/a"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


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
    values: list[float] = []
    evaluation = delta.get("evaluation", {})
    if isinstance(evaluation, dict):
        for value in evaluation.values():
            if isinstance(value, (int, float)):
                values.append(float(value))
    ranking = delta.get("ranking_evaluation", {})
    if isinstance(ranking, dict):
        for split_data in ranking.values():
            if not isinstance(split_data, dict):
                continue
            for value in split_data.values():
                if isinstance(value, (int, float)):
                    values.append(float(value))
    return values


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


def _accuracy_delta(
    baseline: float | None,
    augmented: float | None,
) -> float | None:
    if baseline is None or augmented is None:
        return None
    return augmented - baseline
