"""Primitive classifier training and evaluation over synthetic manifests."""

from __future__ import annotations

import json
from dataclasses import dataclass
from math import dist
from pathlib import Path

from curve.anchors import (
    AnchorCandidate,
    AnchorKind,
    CircleAnchor,
    Point,
    QuadAnchor,
    StrokeAnchor,
    semantic_anchor_score,
)


FEATURE_NAMES = (
    "node_count",
    "parameter_count",
    "has_circle",
    "circle_radius",
    "has_stroke",
    "stroke_width",
    "stroke_length",
    "has_quad",
    "quad_width",
    "quad_height",
)


@dataclass(frozen=True)
class TrainingExample:
    label: str
    features: tuple[float, ...]


def features_from_anchor(anchor: dict[str, object]) -> tuple[float, ...]:
    circle = anchor.get("circle")
    stroke = anchor.get("stroke")
    quad = anchor.get("quad")
    stroke_width = 0.0
    stroke_length = 0.0
    if isinstance(stroke, dict):
        widths = stroke.get("width_samples", [])
        if widths:
            stroke_width = sum(widths) / len(widths)
        centerline = stroke.get("centerline", [])
        if len(centerline) >= 2:
            start = centerline[0]
            end = centerline[-1]
            stroke_length = ((end["x"] - start["x"]) ** 2 + (end["y"] - start["y"]) ** 2) ** 0.5

    quad_width = 0.0
    quad_height = 0.0
    if isinstance(quad, dict):
        corners = quad.get("corners", [])
        if len(corners) == 4:
            xs = [point["x"] for point in corners]
            ys = [point["y"] for point in corners]
            quad_width = max(xs) - min(xs)
            quad_height = max(ys) - min(ys)

    return (
        float(anchor.get("node_count", 0)),
        float(anchor.get("parameter_count", 0)),
        1.0 if isinstance(circle, dict) else 0.0,
        float(circle.get("r", 0.0)) if isinstance(circle, dict) else 0.0,
        1.0 if isinstance(stroke, dict) else 0.0,
        float(stroke_width),
        float(stroke_length),
        1.0 if isinstance(quad, dict) else 0.0,
        float(quad_width),
        float(quad_height),
    )


def features_from_candidate(candidate: AnchorCandidate) -> tuple[float, ...]:
    anchor: dict[str, object] = {
        "kind": candidate.kind.value,
        "node_count": candidate.node_count,
        "parameter_count": candidate.parameter_count,
    }
    if candidate.circle is not None:
        anchor["circle"] = {
            "cx": candidate.circle.center.x,
            "cy": candidate.circle.center.y,
            "r": candidate.circle.radius,
        }
    if candidate.stroke is not None:
        anchor["stroke"] = {
            "centerline": [
                {"x": point.x, "y": point.y}
                for point in candidate.stroke.centerline
            ],
            "width_samples": list(candidate.stroke.width_samples),
        }
    if candidate.quad is not None:
        anchor["quad"] = {
            "corners": [
                {"x": point.x, "y": point.y}
                for point in candidate.quad.corners
            ]
        }
    return features_from_anchor(anchor)


def examples_from_dataset(
    dataset_json: str | Path,
    *,
    splits: tuple[str, ...] = ("train",),
) -> tuple[TrainingExample, ...]:
    dataset_path = Path(dataset_json)
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    root = dataset_path.parent
    examples: list[TrainingExample] = []
    for sample in dataset.get("samples", []):
        if sample.get("split") not in splits:
            continue
        manifest = json.loads(
            (root / sample["manifest"]).read_text(encoding="utf-8")
        )
        for anchor in manifest.get("anchors", []):
            examples.append(
                TrainingExample(
                    label=anchor["kind"],
                    features=features_from_anchor(anchor),
                )
            )
    return tuple(examples)


def anchors_from_dataset(
    dataset_json: str | Path,
    *,
    splits: tuple[str, ...] = ("train",),
) -> tuple[dict[str, object], ...]:
    dataset_path = Path(dataset_json)
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    root = dataset_path.parent
    anchors: list[dict[str, object]] = []
    for sample in dataset.get("samples", []):
        if sample.get("split") not in splits:
            continue
        manifest = json.loads((root / sample["manifest"]).read_text(encoding="utf-8"))
        anchors.extend(anchor for anchor in manifest.get("anchors", []))
    return tuple(anchors)


def train_centroid_classifier(
    dataset_json: str | Path,
    *,
    output: str | Path,
) -> dict[str, object]:
    train_examples = examples_from_dataset(dataset_json, splits=("train",))
    if not train_examples:
        msg = "training dataset contains no train examples"
        raise ValueError(msg)

    centroids = _centroids(train_examples)
    model = {
        "model_type": "centroid_primitive_classifier",
        "feature_names": list(FEATURE_NAMES),
        "classes": sorted(centroids),
        "centroids": {
            label: list(values)
            for label, values in sorted(centroids.items())
        },
        "train_examples": len(train_examples),
        "evaluation": {
            "val": evaluate_classifier(
                centroids,
                examples_from_dataset(dataset_json, splits=("val",)),
            ),
            "test": evaluate_classifier(
                centroids,
                examples_from_dataset(dataset_json, splits=("test",)),
            ),
        },
        "ranking_evaluation": {
            "val": evaluate_classifier_ranking(
                centroids,
                anchors_from_dataset(dataset_json, splits=("val",)),
            ),
            "test": evaluate_classifier_ranking(
                centroids,
                anchors_from_dataset(dataset_json, splits=("test",)),
            ),
        },
    }
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(model, indent=2, sort_keys=True), encoding="utf-8")
    return model


def centroids_from_examples(
    examples: tuple[TrainingExample, ...],
) -> dict[str, tuple[float, ...]]:
    if not examples:
        msg = "training examples must not be empty"
        raise ValueError(msg)
    return _centroids(examples)


def load_centroid_model(model_json: str | Path) -> dict[str, tuple[float, ...]]:
    model = json.loads(Path(model_json).read_text(encoding="utf-8"))
    if model.get("model_type") != "centroid_primitive_classifier":
        msg = "unsupported classifier model type"
        raise ValueError(msg)
    return {
        label: tuple(values)
        for label, values in model.get("centroids", {}).items()
    }


def classifier_prior_error(
    centroids: dict[str, tuple[float, ...]],
    candidate: AnchorCandidate,
) -> float:
    if not centroids:
        return 0.0
    predicted = predict_label(centroids, features_from_candidate(candidate))
    return 0.0 if predicted == candidate.kind.value else 0.35


def predict_label(
    centroids: dict[str, tuple[float, ...]],
    features: tuple[float, ...],
) -> str:
    return min(centroids, key=lambda label: dist(features, centroids[label]))


def evaluate_classifier(
    centroids: dict[str, tuple[float, ...]],
    examples: tuple[TrainingExample, ...],
) -> dict[str, object]:
    confusion: dict[str, dict[str, int]] = {}
    correct = 0
    for example in examples:
        predicted = predict_label(centroids, example.features)
        confusion.setdefault(example.label, {})
        confusion[example.label][predicted] = confusion[example.label].get(predicted, 0) + 1
        if predicted == example.label:
            correct += 1
    total = len(examples)
    return {
        "examples": total,
        "accuracy": correct / total if total else None,
        "confusion": confusion,
    }


def evaluate_classifier_ranking(
    centroids: dict[str, tuple[float, ...]],
    anchors: tuple[dict[str, object], ...],
) -> dict[str, object]:
    total = 0
    heuristic_correct = 0
    classifier_correct = 0
    changed = 0
    examples: list[dict[str, object]] = []
    for anchor in anchors:
        true_label = anchor.get("kind")
        if not isinstance(true_label, str):
            continue
        candidates = _candidate_alternatives(anchor)
        if not candidates:
            continue
        total += 1
        heuristic_label = min(candidates, key=semantic_anchor_score).kind.value
        assisted_candidates = tuple(
            _candidate_with_classifier_prior(candidate, centroids)
            for candidate in candidates
        )
        classifier_label = min(
            assisted_candidates,
            key=semantic_anchor_score,
        ).kind.value
        if heuristic_label == true_label:
            heuristic_correct += 1
        if classifier_label == true_label:
            classifier_correct += 1
        if heuristic_label != classifier_label:
            changed += 1
        examples.append(
            {
                "label": true_label,
                "heuristic": heuristic_label,
                "classifier": classifier_label,
            }
        )

    heuristic_accuracy = heuristic_correct / total if total else None
    classifier_accuracy = classifier_correct / total if total else None
    improvement = (
        classifier_accuracy - heuristic_accuracy
        if classifier_accuracy is not None and heuristic_accuracy is not None
        else None
    )
    return {
        "examples": total,
        "heuristic_correct": heuristic_correct,
        "classifier_correct": classifier_correct,
        "heuristic_accuracy": heuristic_accuracy,
        "classifier_accuracy": classifier_accuracy,
        "accuracy_improvement": improvement,
        "changed_decisions": changed,
        "decisions": examples,
    }


def _centroids(examples: tuple[TrainingExample, ...]) -> dict[str, tuple[float, ...]]:
    grouped: dict[str, list[tuple[float, ...]]] = {}
    for example in examples:
        grouped.setdefault(example.label, []).append(example.features)

    centroids: dict[str, tuple[float, ...]] = {}
    for label, rows in grouped.items():
        centroids[label] = tuple(
            sum(row[index] for row in rows) / len(rows)
            for index in range(len(FEATURE_NAMES))
        )
    return centroids


def _candidate_with_classifier_prior(
    candidate: AnchorCandidate,
    centroids: dict[str, tuple[float, ...]],
) -> AnchorCandidate:
    metrics = dict(candidate.metrics)
    metrics["classifier_prior_error"] = classifier_prior_error(centroids, candidate)
    return AnchorCandidate(
        kind=candidate.kind,
        raster_error=candidate.raster_error,
        node_count=candidate.node_count,
        parameter_count=candidate.parameter_count,
        color=candidate.color,
        circle=candidate.circle,
        stroke=candidate.stroke,
        quad=candidate.quad,
        metrics=metrics,
    )


def _candidate_alternatives(anchor: dict[str, object]) -> tuple[AnchorCandidate, ...]:
    candidate = _candidate_from_anchor(anchor)
    if candidate is None:
        return ()

    kinds = {candidate.kind}
    if candidate.circle is not None:
        kinds.update({AnchorKind.CIRCLE, AnchorKind.STROKE_CIRCLE})
    if candidate.stroke is not None:
        kinds.update(
            {AnchorKind.STROKE_POLYLINE, AnchorKind.STROKE_PATH, AnchorKind.ARC}
        )
    if candidate.quad is not None:
        kinds.update({AnchorKind.RECT, AnchorKind.ROUNDED_RECT, AnchorKind.QUAD})
    kinds.add(AnchorKind.CUBIC_PATH)

    return tuple(
        _candidate_as_kind(candidate, kind)
        for kind in sorted(kinds, key=lambda item: item.value)
    )


def _candidate_from_anchor(anchor: dict[str, object]) -> AnchorCandidate | None:
    try:
        kind = AnchorKind(str(anchor.get("kind")))
    except ValueError:
        return None

    return AnchorCandidate(
        kind=kind,
        raster_error=float(anchor.get("raster_error", 0.0)),
        node_count=int(anchor.get("node_count", _default_node_count(kind))),
        parameter_count=int(
            anchor.get("parameter_count", _default_parameter_count(kind))
        ),
        color=anchor.get("color") if isinstance(anchor.get("color"), str) else None,
        circle=_circle_from_anchor(anchor),
        stroke=_stroke_from_anchor(anchor),
        quad=_quad_from_anchor(anchor),
        metrics=_metrics_from_anchor(anchor),
    )


def _candidate_as_kind(candidate: AnchorCandidate, kind: AnchorKind) -> AnchorCandidate:
    return AnchorCandidate(
        kind=kind,
        raster_error=candidate.raster_error,
        node_count=_default_node_count(kind, candidate),
        parameter_count=_default_parameter_count(kind, candidate),
        color=candidate.color,
        circle=candidate.circle,
        stroke=candidate.stroke,
        quad=candidate.quad,
        metrics={},
    )


def _metrics_from_anchor(anchor: dict[str, object]) -> dict[str, float]:
    metrics = anchor.get("metrics", {})
    if not isinstance(metrics, dict):
        return {}
    return {
        str(key): float(value)
        for key, value in metrics.items()
        if isinstance(value, (int, float))
    }


def _circle_from_anchor(anchor: dict[str, object]) -> CircleAnchor | None:
    circle = anchor.get("circle")
    if not isinstance(circle, dict):
        return None
    return CircleAnchor(
        center=Point(float(circle.get("cx", 0.0)), float(circle.get("cy", 0.0))),
        radius=float(circle.get("r", 0.0)),
    )


def _stroke_from_anchor(anchor: dict[str, object]) -> StrokeAnchor | None:
    stroke = anchor.get("stroke")
    if not isinstance(stroke, dict):
        return None
    return StrokeAnchor(
        centerline=tuple(
            Point(float(point.get("x", 0.0)), float(point.get("y", 0.0)))
            for point in stroke.get("centerline", [])
            if isinstance(point, dict)
        ),
        width_samples=tuple(float(width) for width in stroke.get("width_samples", [])),
        is_cutout=bool(stroke.get("is_cutout", False)),
        parallel_group_id=(
            stroke.get("parallel_group_id")
            if isinstance(stroke.get("parallel_group_id"), str)
            else None
        ),
        cap_style=str(stroke.get("cap_style", "round")),
        join_style=str(stroke.get("join_style", "round")),
    )


def _quad_from_anchor(anchor: dict[str, object]) -> QuadAnchor | None:
    quad = anchor.get("quad")
    if not isinstance(quad, dict):
        return None
    corners = tuple(
        Point(float(point.get("x", 0.0)), float(point.get("y", 0.0)))
        for point in quad.get("corners", [])
        if isinstance(point, dict)
    )
    if len(corners) != 4:
        return None
    return QuadAnchor(corners=corners)


def _default_node_count(
    kind: AnchorKind,
    candidate: AnchorCandidate | None = None,
) -> int:
    if kind in {AnchorKind.CIRCLE, AnchorKind.STROKE_CIRCLE}:
        return 1
    if kind in {AnchorKind.STROKE_POLYLINE}:
        return 2
    if kind in {
        AnchorKind.RECT,
        AnchorKind.ROUNDED_RECT,
        AnchorKind.QUAD,
        AnchorKind.ARC,
    }:
        return 4
    if kind == AnchorKind.STROKE_PATH:
        return max(4, candidate.node_count if candidate is not None else 4)
    if kind == AnchorKind.CUBIC_PATH:
        return max(8, (candidate.node_count if candidate is not None else 4) * 2)
    return candidate.node_count if candidate is not None else 4


def _default_parameter_count(
    kind: AnchorKind,
    candidate: AnchorCandidate | None = None,
) -> int:
    if kind == AnchorKind.CIRCLE:
        return 3
    if kind == AnchorKind.STROKE_CIRCLE:
        return 4
    if kind == AnchorKind.STROKE_POLYLINE:
        return 5
    if kind == AnchorKind.ARC:
        return 6
    if kind == AnchorKind.STROKE_PATH:
        return max(8, candidate.parameter_count if candidate is not None else 8)
    if kind == AnchorKind.RECT:
        return 4
    if kind == AnchorKind.ROUNDED_RECT:
        return 5
    if kind == AnchorKind.QUAD:
        return 8
    if kind == AnchorKind.CUBIC_PATH:
        return max(12, (candidate.parameter_count if candidate is not None else 6) * 2)
    return candidate.parameter_count if candidate is not None else 8
