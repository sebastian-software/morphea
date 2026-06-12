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
)


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
        "",
        "## Filters",
        "",
        "| Gate | Value |",
        "| --- | ---: |",
    ]
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
            lines.append(
                "| "
                f"`{label.get('run', 'n/a')}` | "
                f"{_fmt_metric(label.get('anchor_index'))} | "
                f"`{label.get('kind', 'n/a')}` | "
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
            "groups": [],
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
        "",
        "| ID | Decision | Kind | Quality error | Issues |",
        "| --- | --- | --- | ---: | --- |",
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
                f"{_fmt_metric(label.get('anchor_quality_error'))} | "
                f"{', '.join(str(issue) for issue in issues) or 'n/a'} |"
            )
    else:
        lines.append("| n/a | n/a | n/a | n/a | n/a |")
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
        "",
        "## Accepted",
        "",
        "| Kind | Corrected kind | Issues |",
        "| --- | --- | --- |",
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
                f"{', '.join(str(issue) for issue in issues) or 'n/a'} |"
            )
    else:
        lines.append("| n/a | n/a | n/a |")

    lines.extend(
        [
            "",
            "## Rejected",
            "",
            "| ID | Reason | Issues |",
            "| --- | --- | --- |",
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
                f"{', '.join(str(issue) for issue in issues) or 'n/a'} |"
            )
    else:
        lines.append("| n/a | n/a | n/a |")

    lines.extend(
        [
            "",
            "## Pending",
            "",
            ", ".join(f"`{item}`" for item in pending) if pending else "n/a",
        ]
    )
    return "\n".join(lines) + "\n"


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
    issues = item.get("issues", [])
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
