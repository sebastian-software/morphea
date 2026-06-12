"""Primitive classifier training and evaluation over synthetic manifests."""

from __future__ import annotations

import json
from dataclasses import dataclass
from math import dist
from pathlib import Path

from PIL import Image

from curve.anchors import (
    AnchorCandidate,
    AnchorKind,
    CircleAnchor,
    Point,
    QuadAnchor,
    StrokeAnchor,
    semantic_anchor_score,
)


ClassifierModel = dict[str, object]


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
    "quad_subtype_code",
)


@dataclass(frozen=True)
class TrainingExample:
    label: str
    features: tuple[float, ...]


@dataclass(frozen=True)
class RasterTrainingExample:
    label: str
    features: tuple[float, ...]
    crop_tokens: tuple[tuple[float, float, float, float], ...]
    bounds: tuple[int, int, int, int]
    sample_id: str
    anchor_index: int


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

    quad_subtype_code = 0.0
    metrics = anchor.get("metrics", {})
    if isinstance(metrics, dict):
        value = metrics.get("quad_subtype_code", 0.0)
        if isinstance(value, (int, float)):
            quad_subtype_code = float(value)

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
        quad_subtype_code,
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


def raster_examples_from_dataset(
    dataset_json: str | Path,
    *,
    crop_size: int = 16,
    splits: tuple[str, ...] = ("train",),
) -> tuple[RasterTrainingExample, ...]:
    if crop_size <= 0:
        msg = "crop_size must be positive"
        raise ValueError(msg)
    dataset_path = Path(dataset_json)
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    root = dataset_path.parent
    examples: list[RasterTrainingExample] = []
    for sample in dataset.get("samples", []):
        if sample.get("split") not in splits:
            continue
        image = Image.open(root / sample["image"]).convert("RGBA")
        manifest = json.loads((root / sample["manifest"]).read_text(encoding="utf-8"))
        for anchor_index, anchor in enumerate(manifest.get("anchors", [])):
            bounds = _anchor_crop_bounds(anchor, image.size)
            examples.append(
                RasterTrainingExample(
                    label=anchor["kind"],
                    features=features_from_anchor(anchor),
                    crop_tokens=_rgba_crop_tokens(image, bounds, crop_size),
                    bounds=bounds,
                    sample_id=str(sample.get("id", "")),
                    anchor_index=anchor_index,
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


def _anchor_crop_bounds(
    anchor: dict[str, object],
    image_size: tuple[int, int],
) -> tuple[int, int, int, int]:
    width, height = image_size
    xs: list[float] = []
    ys: list[float] = []
    margin = 2.0
    circle = anchor.get("circle")
    if isinstance(circle, dict):
        cx = float(circle.get("cx", 0.0))
        cy = float(circle.get("cy", 0.0))
        radius = float(circle.get("r", 0.0))
        xs.extend([cx - radius, cx + radius])
        ys.extend([cy - radius, cy + radius])
    stroke = anchor.get("stroke")
    if isinstance(stroke, dict):
        widths = [
            float(value)
            for value in stroke.get("width_samples", [])
            if isinstance(value, (int, float))
        ]
        if widths:
            margin = max(margin, max(widths) / 2 + 2)
        for point in stroke.get("centerline", []):
            if not isinstance(point, dict):
                continue
            xs.append(float(point.get("x", 0.0)))
            ys.append(float(point.get("y", 0.0)))
    quad = anchor.get("quad")
    if isinstance(quad, dict):
        for point in quad.get("corners", []):
            if not isinstance(point, dict):
                continue
            xs.append(float(point.get("x", 0.0)))
            ys.append(float(point.get("y", 0.0)))

    if not xs or not ys:
        return (0, 0, width, height)
    left = max(0, int(min(xs) - margin))
    top = max(0, int(min(ys) - margin))
    right = min(width, int(max(xs) + margin + 1))
    bottom = min(height, int(max(ys) + margin + 1))
    if right <= left or bottom <= top:
        return (0, 0, width, height)
    return left, top, right, bottom


def _rgba_crop_tokens(
    image: Image.Image,
    bounds: tuple[int, int, int, int],
    crop_size: int,
) -> tuple[tuple[float, float, float, float], ...]:
    crop = image.crop(bounds).resize(
        (crop_size, crop_size),
        Image.Resampling.NEAREST,
    )
    get_flattened_data = getattr(crop, "get_flattened_data", None)
    pixels = get_flattened_data() if get_flattened_data is not None else crop.getdata()
    return tuple(
        (
            red / 255,
            green / 255,
            blue / 255,
            alpha / 255,
        )
        for red, green, blue, alpha in pixels
    )


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


def evaluate_classifier_model(
    model_json: str | Path,
    dataset_json: str | Path,
    *,
    output: str | Path | None = None,
    markdown: str | Path | None = None,
    splits: tuple[str, ...] = ("val", "test"),
) -> dict[str, object]:
    model_path = Path(model_json)
    dataset_path = Path(dataset_json)
    model = json.loads(model_path.read_text(encoding="utf-8"))
    classifier = load_classifier_model(model_path)
    use_raster_eval = _classifier_uses_raster_tokens(classifier)
    crop_size = _classifier_crop_size(classifier)
    report = {
        "schema_version": 1,
        "model": str(model_path),
        "dataset": str(dataset_path),
        "model_type": model.get("model_type"),
        "classifier_backend": classifier.get("classifier_backend"),
        "uses_raster_tokens": use_raster_eval,
        "feature_names": model.get("feature_names", list(FEATURE_NAMES)),
        "classes": model.get("classes", _classifier_labels(classifier)),
        "splits": list(splits),
        "evaluation": {
            split: (
                evaluate_raster_classifier(
                    classifier,
                    raster_examples_from_dataset(
                        dataset_path,
                        crop_size=crop_size,
                        splits=(split,),
                    ),
                )
                if use_raster_eval
                else evaluate_classifier(
                    classifier,
                    examples_from_dataset(dataset_path, splits=(split,)),
                )
            )
            for split in splits
        },
        "ranking_evaluation": {
            split: evaluate_classifier_ranking(
                classifier,
                anchors_from_dataset(dataset_path, splits=(split,)),
            )
            for split in splits
        },
    }
    if output is not None:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(report, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    if markdown is not None:
        markdown_path = Path(markdown)
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(
            render_classifier_evaluation_markdown(report),
            encoding="utf-8",
        )
    return report


def render_classifier_evaluation_markdown(report: dict[str, object]) -> str:
    lines = [
        "# Curve Classifier Evaluation",
        "",
        f"- Model: `{report.get('model')}`",
        f"- Dataset: `{report.get('dataset')}`",
        f"- Model type: `{report.get('model_type')}`",
        "",
        "| Split | Examples | Accuracy | Heuristic | Classifier | Improvement | Changed |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    evaluation = report.get("evaluation", {})
    ranking = report.get("ranking_evaluation", {})
    for split in report.get("splits", []):
        direct = evaluation.get(split, {}) if isinstance(evaluation, dict) else {}
        rank = ranking.get(split, {}) if isinstance(ranking, dict) else {}
        lines.append(
            "| "
            f"`{split}` | "
            f"{_fmt_number(direct.get('examples'))} | "
            f"{_fmt_number(direct.get('accuracy'))} | "
            f"{_fmt_number(rank.get('heuristic_accuracy'))} | "
            f"{_fmt_number(rank.get('classifier_accuracy'))} | "
            f"{_fmt_number(rank.get('accuracy_improvement'))} | "
            f"{_fmt_number(rank.get('changed_decisions'))} |"
        )

    lines.extend(["", "## Confusion", ""])
    for split in report.get("splits", []):
        direct = evaluation.get(split, {}) if isinstance(evaluation, dict) else {}
        confusion = direct.get("confusion", {}) if isinstance(direct, dict) else {}
        lines.append(f"### {split}")
        if not confusion:
            lines.append("")
            lines.append("No confusion entries.")
            lines.append("")
            continue
        for label, predicted in sorted(confusion.items()):
            if not isinstance(predicted, dict):
                continue
            cells = ", ".join(
                f"{target}: {count}"
                for target, count in sorted(predicted.items())
            )
            lines.append(f"- `{label}` -> {cells}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _fmt_number(value: object) -> str:
    if isinstance(value, bool):
        return "n/a"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return f"{value:.6g}"
    return "n/a"


def centroids_from_examples(
    examples: tuple[TrainingExample, ...],
) -> dict[str, tuple[float, ...]]:
    if not examples:
        msg = "training examples must not be empty"
        raise ValueError(msg)
    return _centroids(examples)


def load_centroid_model(model_json: str | Path) -> dict[str, tuple[float, ...]]:
    model = json.loads(Path(model_json).read_text(encoding="utf-8"))
    if model.get("model_type") == "mlx_transformer_primitive_classifier":
        fallback = model.get("fallback_centroids", {})
        return {
            label: tuple(values)
            for label, values in fallback.items()
        }
    if model.get("model_type") != "centroid_primitive_classifier":
        msg = "unsupported classifier model type"
        raise ValueError(msg)
    return {
        label: tuple(values)
        for label, values in model.get("centroids", {}).items()
    }


def load_classifier_model(model_json: str | Path) -> ClassifierModel:
    model = json.loads(Path(model_json).read_text(encoding="utf-8"))
    if model.get("model_type") == "centroid_primitive_classifier":
        return {
            "classifier_backend": "centroid",
            "centroids": _tuple_mapping(model.get("centroids", {})),
        }
    if model.get("model_type") != "mlx_transformer_primitive_classifier":
        msg = "unsupported classifier model type"
        raise ValueError(msg)

    fallback = _tuple_mapping(model.get("fallback_centroids", {}))
    training = model.get("mlx_training", {})
    if not isinstance(training, dict):
        return {
            "classifier_backend": "centroid_fallback",
            "centroids": fallback,
        }
    if training.get("weight_format") != "mlx_feature_head_v1":
        return {
            "classifier_backend": "centroid_fallback",
            "centroids": fallback,
        }
    labels = [
        str(label)
        for label in training.get("labels", [])
        if isinstance(label, str)
    ]
    weights = _matrix(training.get("weights", []))
    bias = _vector(training.get("bias", []))
    normalization = training.get("normalization", {})
    if not isinstance(normalization, dict):
        normalization = {}
    mean = _vector(normalization.get("mean", []))
    scale = _vector(normalization.get("scale", []))
    if (
        not labels
        or len(weights) != len(labels)
        or len(bias) != len(labels)
        or len(mean) != len(FEATURE_NAMES)
        or len(scale) != len(FEATURE_NAMES)
    ):
        return {
            "classifier_backend": "centroid_fallback",
            "centroids": fallback,
        }
    return {
        "classifier_backend": "mlx_feature_head",
        "labels": tuple(labels),
        "weights": tuple(tuple(row) for row in weights),
        "bias": tuple(bias),
        "normalization": {
            "mean": tuple(mean),
            "scale": tuple(scale),
        },
        "raster_token_mixer": _loaded_raster_token_mixer(training),
        "crop_token_spec": training.get("crop_token_spec", {}),
        "fallback_centroids": fallback,
    }


def classifier_prior_error(
    classifier_model: dict[str, object] | dict[str, tuple[float, ...]],
    candidate: AnchorCandidate,
) -> float:
    if not classifier_model:
        return 0.0
    try:
        predicted = predict_classifier_label(
            classifier_model,
            features_from_candidate(candidate),
        )
    except ValueError:
        return 0.0
    return 0.0 if predicted == candidate.kind.value else 0.35


def predict_classifier_label(
    classifier_model: dict[str, object] | dict[str, tuple[float, ...]],
    features: tuple[float, ...],
    *,
    crop_tokens: tuple[tuple[float, float, float, float], ...] | None = None,
) -> str:
    if _is_centroid_mapping(classifier_model):
        return predict_label(classifier_model, features)
    backend = classifier_model.get("classifier_backend")
    if backend == "mlx_feature_head":
        return _predict_mlx_classifier(classifier_model, features, crop_tokens)
    centroids = classifier_model.get("centroids")
    if isinstance(centroids, dict) and centroids:
        return predict_label(_tuple_mapping(centroids), features)
    fallback = classifier_model.get("fallback_centroids")
    if isinstance(fallback, dict) and fallback:
        return predict_label(_tuple_mapping(fallback), features)
    msg = "classifier model has no usable predictor"
    raise ValueError(msg)


def predict_label(
    centroids: dict[str, tuple[float, ...]],
    features: tuple[float, ...],
) -> str:
    return min(centroids, key=lambda label: dist(features, centroids[label]))


def _predict_feature_head(
    classifier_model: dict[str, object],
    features: tuple[float, ...],
) -> str:
    labels, logits = _feature_head_logits(classifier_model, features)
    return labels[max(range(len(logits)), key=logits.__getitem__)]


def _predict_mlx_classifier(
    classifier_model: dict[str, object],
    features: tuple[float, ...],
    crop_tokens: tuple[tuple[float, float, float, float], ...] | None,
) -> str:
    labels, logits = _feature_head_logits(classifier_model, features)
    raster_logits = (
        _raster_mixer_logits(classifier_model, crop_tokens)
        if crop_tokens is not None
        else None
    )
    if raster_logits is not None and len(raster_logits) == len(logits):
        logits = [
            feature_logit + raster_logit
            for feature_logit, raster_logit in zip(logits, raster_logits)
        ]
    return labels[max(range(len(logits)), key=logits.__getitem__)]


def _feature_head_logits(
    classifier_model: dict[str, object],
    features: tuple[float, ...],
) -> tuple[tuple[str, ...], list[float]]:
    labels = tuple(str(label) for label in classifier_model.get("labels", ()))
    weights = tuple(
        tuple(float(value) for value in row)
        for row in classifier_model.get("weights", ())
        if isinstance(row, tuple)
    )
    bias = tuple(float(value) for value in classifier_model.get("bias", ()))
    normalization = classifier_model.get("normalization", {})
    if not isinstance(normalization, dict):
        normalization = {}
    mean = tuple(float(value) for value in normalization.get("mean", ()))
    scale = tuple(float(value) for value in normalization.get("scale", ()))
    normalized = tuple(
        (features[index] - mean[index]) / scale[index]
        for index in range(len(FEATURE_NAMES))
    )
    logits = [
        bias[class_index]
        + sum(
            weights[class_index][feature_index] * normalized[feature_index]
            for feature_index in range(len(FEATURE_NAMES))
        )
        for class_index in range(len(labels))
    ]
    return labels, logits


def _is_centroid_mapping(value: object) -> bool:
    return (
        isinstance(value, dict)
        and bool(value)
        and all(isinstance(item, tuple) for item in value.values())
    )


def _loaded_raster_token_mixer(training: dict[str, object]) -> dict[str, object] | None:
    mixer = training.get("raster_token_mixer")
    if not isinstance(mixer, dict):
        return None
    if mixer.get("weight_format") != "raster_token_mixer_v1":
        return None
    labels = [
        str(label)
        for label in mixer.get("labels", [])
        if isinstance(label, str)
    ]
    weights = _matrix(mixer.get("weights", []))
    bias = _vector(mixer.get("bias", []))
    normalization = mixer.get("normalization", {})
    if not isinstance(normalization, dict):
        return None
    mean = _vector(normalization.get("mean", []))
    scale = _vector(normalization.get("scale", []))
    attention = mixer.get("attention", {})
    if not isinstance(attention, dict):
        return None
    heads = attention.get("heads")
    embedding_names = [
        str(name)
        for name in attention.get("embedding_names", [])
        if isinstance(name, str)
    ]
    if (
        not isinstance(heads, int)
        or heads <= 0
        or not labels
        or len(weights) != len(labels)
        or len(bias) != len(labels)
        or len(mean) != len(embedding_names)
        or len(scale) != len(embedding_names)
    ):
        return None
    return {
        "labels": tuple(labels),
        "weights": tuple(tuple(row) for row in weights),
        "bias": tuple(bias),
        "normalization": {
            "mean": tuple(mean),
            "scale": tuple(scale),
        },
        "attention": {
            "heads": heads,
            "embedding_names": tuple(embedding_names),
        },
    }


def _raster_mixer_logits(
    classifier_model: dict[str, object],
    crop_tokens: tuple[tuple[float, float, float, float], ...],
) -> list[float] | None:
    mixer = classifier_model.get("raster_token_mixer")
    crop_spec = classifier_model.get("crop_token_spec", {})
    if not isinstance(mixer, dict) or not isinstance(crop_spec, dict):
        return None
    attention = mixer.get("attention", {})
    normalization = mixer.get("normalization", {})
    if not isinstance(attention, dict) or not isinstance(normalization, dict):
        return None
    heads = attention.get("heads")
    crop_size = crop_spec.get("crop_size")
    if not isinstance(heads, int) or not isinstance(crop_size, int):
        return None
    row = _raster_attention_embedding(crop_tokens, crop_size=crop_size, heads=heads)
    mean = normalization.get("mean", ())
    scale = normalization.get("scale", ())
    weights = mixer.get("weights", ())
    bias = mixer.get("bias", ())
    if (
        not isinstance(mean, tuple)
        or not isinstance(scale, tuple)
        or len(row) != len(mean)
        or len(row) != len(scale)
        or not isinstance(weights, tuple)
        or not isinstance(bias, tuple)
    ):
        return None
    normalized = tuple(
        (row[index] - mean[index]) / scale[index]
        for index in range(len(row))
    )
    return [
        float(bias[class_index])
        + sum(
            weights[class_index][feature_index] * normalized[feature_index]
            for feature_index in range(len(normalized))
        )
        for class_index in range(len(bias))
    ]


def _raster_attention_embedding(
    crop_tokens: tuple[tuple[float, float, float, float], ...],
    *,
    crop_size: int,
    heads: int,
) -> tuple[float, ...]:
    embedding: list[float] = []
    for head in range(heads):
        weighted = [0.0 for _ in range(7)]
        total_weight = 0.0
        for index, token in enumerate(crop_tokens):
            red, green, blue, alpha = token
            x = (index % crop_size) / max(1, crop_size - 1)
            y = (index // crop_size) / max(1, crop_size - 1)
            foreground = alpha * (
                abs(red - 1.0) + abs(green - 1.0) + abs(blue - 1.0)
            ) / 3
            weight = 1e-6 + foreground * _head_spatial_bias(head, x, y)
            total_weight += weight
            values = (red, green, blue, alpha, x, y, foreground)
            for value_index, value in enumerate(values):
                weighted[value_index] += value * weight
        if total_weight <= 0:
            embedding.extend([0.0 for _ in range(7)])
            continue
        embedding.extend(value / total_weight for value in weighted)
    return tuple(embedding)


def _head_spatial_bias(head: int, x: float, y: float) -> float:
    mode = head % 5
    if mode == 1:
        return 1.0 + x
    if mode == 2:
        return 2.0 - x
    if mode == 3:
        return 1.0 + y
    if mode == 4:
        return 2.0 - y
    return 1.0


def _tuple_mapping(value: object) -> dict[str, tuple[float, ...]]:
    if not isinstance(value, dict):
        return {}
    return {
        str(label): tuple(float(item) for item in values)
        for label, values in value.items()
        if isinstance(values, (list, tuple))
    }


def _vector(value: object) -> list[float]:
    if not isinstance(value, (list, tuple)):
        return []
    return [float(item) for item in value if isinstance(item, (int, float))]


def _matrix(value: object) -> list[list[float]]:
    if not isinstance(value, (list, tuple)):
        return []
    return [
        _vector(row)
        for row in value
        if isinstance(row, (list, tuple))
    ]


def _classifier_labels(classifier_model: dict[str, object]) -> list[str]:
    if classifier_model.get("classifier_backend") == "mlx_feature_head":
        return [str(label) for label in classifier_model.get("labels", [])]
    centroids = classifier_model.get("centroids")
    if isinstance(centroids, dict):
        return sorted(str(label) for label in centroids)
    fallback = classifier_model.get("fallback_centroids")
    if isinstance(fallback, dict):
        return sorted(str(label) for label in fallback)
    return []


def _classifier_uses_raster_tokens(classifier_model: dict[str, object]) -> bool:
    return (
        classifier_model.get("classifier_backend") == "mlx_feature_head"
        and isinstance(classifier_model.get("raster_token_mixer"), dict)
        and isinstance(classifier_model.get("crop_token_spec"), dict)
    )


def _classifier_crop_size(classifier_model: dict[str, object]) -> int:
    crop_spec = classifier_model.get("crop_token_spec", {})
    if isinstance(crop_spec, dict) and isinstance(crop_spec.get("crop_size"), int):
        return int(crop_spec["crop_size"])
    return 16


def evaluate_classifier(
    classifier_model: dict[str, object] | dict[str, tuple[float, ...]],
    examples: tuple[TrainingExample, ...],
) -> dict[str, object]:
    confusion: dict[str, dict[str, int]] = {}
    correct = 0
    for example in examples:
        predicted = predict_classifier_label(classifier_model, example.features)
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


def evaluate_raster_classifier(
    classifier_model: dict[str, object],
    examples: tuple[RasterTrainingExample, ...],
) -> dict[str, object]:
    confusion: dict[str, dict[str, int]] = {}
    correct = 0
    for example in examples:
        predicted = predict_classifier_label(
            classifier_model,
            example.features,
            crop_tokens=example.crop_tokens,
        )
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
    classifier_model: dict[str, object] | dict[str, tuple[float, ...]],
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
            _candidate_with_classifier_prior(candidate, classifier_model)
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
    classifier_model: dict[str, object] | dict[str, tuple[float, ...]],
) -> AnchorCandidate:
    metrics = dict(candidate.metrics)
    metrics["classifier_prior_error"] = classifier_prior_error(
        classifier_model,
        candidate,
    )
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
