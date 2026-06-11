"""Primitive classifier training and evaluation over synthetic manifests."""

from __future__ import annotations

import json
from dataclasses import dataclass
from math import dist
from pathlib import Path


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
        manifest = json.loads((root / sample["manifest"]).read_text(encoding="utf-8"))
        for anchor in manifest.get("anchors", []):
            examples.append(
                TrainingExample(
                    label=anchor["kind"],
                    features=features_from_anchor(anchor),
                )
            )
    return tuple(examples)


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
        "centroids": {label: list(values) for label, values in sorted(centroids.items())},
        "train_examples": len(train_examples),
        "evaluation": {
            "val": evaluate_classifier(centroids, examples_from_dataset(dataset_json, splits=("val",))),
            "test": evaluate_classifier(centroids, examples_from_dataset(dataset_json, splits=("test",))),
        },
    }
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(model, indent=2, sort_keys=True), encoding="utf-8")
    return model


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

