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
                    "anchor": anchor,
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


def compare_retraining(
    *,
    base_dataset: str | Path,
    pseudo_dataset: str | Path,
    output: str | Path,
    validation_dataset: str | Path | None = None,
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
    result = {
        "schema_version": 1,
        "base_dataset": str(base_dataset),
        "pseudo_dataset": str(pseudo_dataset),
        "validation_dataset": str(validation_source),
        "baseline": baseline,
        "augmented": augmented,
        "delta": _training_comparison_delta(baseline, augmented),
    }
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, indent=2, sort_keys=True),
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
