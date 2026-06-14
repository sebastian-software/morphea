"""Primitive classifier training and evaluation over synthetic manifests."""

from __future__ import annotations

import json
from dataclasses import dataclass
from math import dist
from pathlib import Path

from PIL import Image

from morphea.anchors import (
    AnchorCandidate,
    AnchorKind,
    CircleAnchor,
    Point,
    QuadAnchor,
    StrokeAnchor,
    semantic_anchor_score,
)
from morphea.masks import MaskComponent
from morphea.token_transformer import token_transformer_embedding


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
    "group_count",
    "in_perspective_grid",
    "in_parallel_stroke_group",
    "in_same_color_fragment_group",
    "in_text_like_fragment_group",
    "in_primitive_anchor_reservation",
)

GROUP_FEATURE_KINDS = (
    "perspective_grid",
    "parallel_stroke_group",
    "same_color_fragment_group",
    "text_like_fragment_group",
    "primitive_anchor_reservation",
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


@dataclass(frozen=True)
class RasterRankingExample:
    label: str
    anchor: dict[str, object]
    crop_tokens: tuple[tuple[float, float, float, float], ...]
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

    group_context = anchor.get("group_context", [])
    groups = group_context if isinstance(group_context, list) else []
    group_kinds = {
        str(group.get("kind"))
        for group in groups
        if isinstance(group, dict) and group.get("kind") is not None
    }

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
        float(len(groups)),
        *(
            1.0 if kind in group_kinds else 0.0
            for kind in GROUP_FEATURE_KINDS
        ),
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
        for anchor_index, anchor in enumerate(manifest.get("anchors", [])):
            examples.append(
                TrainingExample(
                    label=anchor["kind"],
                    features=features_from_anchor(
                        _anchor_with_group_context(manifest, anchor_index, anchor)
                    ),
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
        image_ref = sample.get("image")
        if not isinstance(image_ref, str):
            continue
        image = Image.open(root / image_ref).convert("RGBA")
        manifest = json.loads((root / sample["manifest"]).read_text(encoding="utf-8"))
        for anchor_index, anchor in enumerate(manifest.get("anchors", [])):
            bounds = _anchor_crop_bounds(anchor, image.size)
            examples.append(
                RasterTrainingExample(
                    label=anchor["kind"],
                    features=features_from_anchor(
                        _anchor_with_group_context(manifest, anchor_index, anchor)
                    ),
                    crop_tokens=_rgba_crop_tokens(image, bounds, crop_size),
                    bounds=bounds,
                    sample_id=str(sample.get("id", "")),
                    anchor_index=anchor_index,
                )
            )
    return tuple(examples)


def raster_ranking_examples_from_dataset(
    dataset_json: str | Path,
    *,
    crop_size: int = 16,
    splits: tuple[str, ...] = ("train",),
) -> tuple[RasterRankingExample, ...]:
    if crop_size <= 0:
        msg = "crop_size must be positive"
        raise ValueError(msg)
    dataset_path = Path(dataset_json)
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    root = dataset_path.parent
    examples: list[RasterRankingExample] = []
    for sample in dataset.get("samples", []):
        if sample.get("split") not in splits:
            continue
        image_ref = sample.get("image")
        if not isinstance(image_ref, str):
            continue
        image = Image.open(root / image_ref).convert("RGBA")
        manifest = json.loads((root / sample["manifest"]).read_text(encoding="utf-8"))
        for anchor_index, anchor in enumerate(manifest.get("anchors", [])):
            if not isinstance(anchor, dict):
                continue
            label = anchor.get("kind")
            if not isinstance(label, str):
                continue
            bounds = _anchor_crop_bounds(anchor, image.size)
            examples.append(
                RasterRankingExample(
                    label=label,
                    anchor=_anchor_with_group_context(
                        manifest,
                        anchor_index,
                        anchor,
                    ),
                    crop_tokens=_rgba_crop_tokens(image, bounds, crop_size),
                    sample_id=str(sample.get("id", "")),
                    anchor_index=anchor_index,
                )
            )
    return tuple(examples)


def component_raster_tokens(
    component: MaskComponent,
    *,
    color: str,
    crop_size: int,
) -> tuple[tuple[float, float, float, float], ...]:
    if crop_size <= 0:
        msg = "crop_size must be positive"
        raise ValueError(msg)
    foreground = _hex_to_rgb(color)
    left, top, right, bottom = _component_crop_bounds(component)
    source_width = max(1, right - left)
    source_height = max(1, bottom - top)
    pixels = component.pixels
    tokens: list[tuple[float, float, float, float]] = []
    for out_y in range(crop_size):
        source_y = top + min(
            source_height - 1,
            int(out_y * source_height / crop_size),
        )
        for out_x in range(crop_size):
            source_x = left + min(
                source_width - 1,
                int(out_x * source_width / crop_size),
            )
            if (source_x, source_y) in pixels:
                red, green, blue = foreground
            else:
                red = green = blue = 255
            tokens.append((red / 255, green / 255, blue / 255, 1.0))
    return tuple(tokens)


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


def _anchor_with_group_context(
    manifest: dict[str, object],
    anchor_index: int,
    anchor: dict[str, object],
) -> dict[str, object]:
    if "group_context" in anchor:
        return anchor
    group_context = _anchor_group_context(manifest, anchor_index)
    if not group_context:
        return anchor
    return {**anchor, "group_context": group_context}


def _anchor_group_context(
    manifest: dict[str, object],
    anchor_index: int,
) -> list[dict[str, object]]:
    groups = manifest.get("groups", [])
    if not isinstance(groups, list):
        return []
    context: list[dict[str, object]] = []
    for group in groups:
        if not isinstance(group, dict):
            continue
        indexes = group.get("anchor_indexes", [])
        if not isinstance(indexes, list) or anchor_index not in indexes:
            continue
        entry: dict[str, object] = {}
        for key in (
            "id",
            "kind",
            "anchor_indexes",
            "metrics",
            "source_group_id",
            "source_anchor_indexes",
            "source_anchor_position",
            "color",
        ):
            if key in group:
                entry[key] = group[key]
        entry["anchor_position"] = indexes.index(anchor_index)
        context.append(entry)
    return context


def _component_crop_bounds(component: MaskComponent) -> tuple[int, int, int, int]:
    min_x, min_y, max_x, max_y = component.bounds
    return (
        max(0, int(min_x) - 2),
        max(0, int(min_y) - 2),
        int(max_x) + 3,
        int(max_y) + 3,
    )


def _hex_to_rgb(color: str) -> tuple[int, int, int]:
    value = color.removeprefix("#")
    if len(value) != 6:
        return (0, 0, 0)
    try:
        return (
            int(value[0:2], 16),
            int(value[2:4], 16),
            int(value[4:6], 16),
        )
    except ValueError:
        return (0, 0, 0)


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
        "feature_importance": feature_importance_from_centroids(centroids),
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
        "ranking_uses_raster_tokens": use_raster_eval,
        "feature_names": model.get("feature_names", list(FEATURE_NAMES)),
        "feature_importance": model.get("feature_importance", []),
        "training_component_summary": _model_training_component_summary(model),
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
            split: (
                evaluate_raster_classifier_ranking(
                    classifier,
                    raster_ranking_examples_from_dataset(
                        dataset_path,
                        crop_size=crop_size,
                        splits=(split,),
                    ),
                )
                if use_raster_eval
                else evaluate_classifier_ranking(
                    classifier,
                    anchors_from_dataset(dataset_path, splits=(split,)),
                )
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
        "# Morphēa Classifier Evaluation",
        "",
        f"- Model: `{report.get('model')}`",
        f"- Dataset: `{report.get('dataset')}`",
        f"- Model type: `{report.get('model_type')}`",
        f"- Direct raster tokens: `{bool(report.get('uses_raster_tokens'))}`",
        f"- Ranking raster tokens: `{bool(report.get('ranking_uses_raster_tokens'))}`",
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
    importance = report.get("feature_importance", [])
    if isinstance(importance, list) and importance:
        lines.extend(["## Feature Importance", ""])
        lines.append("| Feature | Spread | Min | Max |")
        lines.append("| --- | ---: | ---: | ---: |")
        for item in importance[:8]:
            if not isinstance(item, dict):
                continue
            lines.append(
                "| "
                f"`{item.get('feature')}` | "
                f"{_fmt_number(item.get('spread'))} | "
                f"{_fmt_number(item.get('min'))} | "
                f"{_fmt_number(item.get('max'))} |"
            )
        lines.append("")
    component_summary = report.get("training_component_summary")
    if isinstance(component_summary, dict):
        lines.extend(_training_component_summary_markdown(component_summary))
    return "\n".join(lines).rstrip() + "\n"


def _fmt_number(value: object) -> str:
    if isinstance(value, bool):
        return "n/a"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return f"{value:.6g}"
    return "n/a"


def _training_component_summary_markdown(summary: dict[str, object]) -> list[str]:
    lines = [
        "## MLX Training Components",
        "",
        f"- Total parameters: `{_fmt_number(summary.get('total_parameter_count'))}`",
        f"- Trainable components: `{_fmt_number(summary.get('trainable_component_count'))}`",
        f"- MLX autograd components: `{_fmt_number(summary.get('mlx_autograd_component_count'))}`",
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
                f"{_fmt_number(component.get('inference_priority'))} | "
                f"`{component.get('name', 'unknown')}` | "
                f"`{component.get('training_runtime', 'unknown')}` | "
                f"{_fmt_number(component.get('training_example_count'))} | "
                f"{_fmt_number(component.get('parameter_count'))} | "
                f"{_fmt_number(component.get('loss_epochs'))} | "
                f"`{bool(component.get('uses_raster_tokens'))}` |"
            )
    lines.append("")
    return lines


def _model_training_component_summary(model: dict[str, object]) -> dict[str, object] | None:
    training = model.get("mlx_training")
    if not isinstance(training, dict):
        return None
    summary = training.get("component_summary")
    if isinstance(summary, dict):
        return summary
    return None


def centroids_from_examples(
    examples: tuple[TrainingExample, ...],
) -> dict[str, tuple[float, ...]]:
    if not examples:
        msg = "training examples must not be empty"
        raise ValueError(msg)
    return _centroids(examples)


def feature_importance_from_centroids(
    centroids: dict[str, tuple[float, ...]],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index, feature in enumerate(FEATURE_NAMES):
        values = [
            centroid[index] if index < len(centroid) else 0.0
            for centroid in centroids.values()
        ]
        if not values:
            continue
        minimum = min(values)
        maximum = max(values)
        rows.append(
            {
                "feature": feature,
                "spread": maximum - minimum,
                "min": minimum,
                "max": maximum,
            }
        )
    return sorted(
        rows,
        key=lambda item: (-float(item["spread"]), str(item["feature"])),
    )


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
        "feature_raster_fusion": _loaded_feature_raster_fusion(training),
        "token_transformer": _loaded_token_transformer(training),
        "crop_token_spec": training.get("crop_token_spec", {}),
        "fallback_centroids": fallback,
    }


def classifier_prior_error(
    classifier_model: dict[str, object] | dict[str, tuple[float, ...]],
    candidate: AnchorCandidate,
    *,
    crop_tokens: tuple[tuple[float, float, float, float], ...] | None = None,
) -> float:
    if not classifier_model:
        return 0.0
    try:
        predicted = predict_classifier_label(
            classifier_model,
            features_from_candidate(candidate),
            crop_tokens=crop_tokens,
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
    return min(
        centroids,
        key=lambda label: dist(
            _align_features(features, len(centroids[label])),
            centroids[label],
        ),
    )


def _align_features(features: tuple[float, ...], expected_count: int) -> tuple[float, ...]:
    if len(features) == expected_count:
        return features
    if len(features) > expected_count:
        return features[:expected_count]
    return (*features, *((0.0,) * (expected_count - len(features))))


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
    token_transformer_logits = (
        _token_transformer_logits(classifier_model, features, crop_tokens)
        if crop_tokens is not None
        else None
    )
    if (
        token_transformer_logits is not None
        and len(token_transformer_logits) == len(logits)
    ):
        logits = token_transformer_logits
        return labels[max(range(len(logits)), key=logits.__getitem__)]
    fusion_logits = (
        _feature_raster_fusion_logits(classifier_model, features, crop_tokens)
        if crop_tokens is not None
        else None
    )
    if fusion_logits is not None and len(fusion_logits) == len(logits):
        logits = fusion_logits
        return labels[max(range(len(logits)), key=logits.__getitem__)]
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
    if not labels or len(weights) < len(labels) or len(bias) < len(labels):
        msg = "classifier feature head is malformed"
        raise ValueError(msg)
    feature_count = min(
        len(mean),
        len(scale),
        *(len(weights[class_index]) for class_index in range(len(labels))),
    )
    if feature_count <= 0:
        msg = "classifier feature head is malformed"
        raise ValueError(msg)
    aligned_features = _align_features(features, feature_count)
    normalized = tuple(
        (aligned_features[index] - mean[index]) / scale[index]
        for index in range(feature_count)
    )
    logits = [
        bias[class_index]
        + sum(
            weights[class_index][feature_index] * normalized[feature_index]
            for feature_index in range(feature_count)
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


def _loaded_token_transformer(
    training: dict[str, object],
) -> dict[str, object] | None:
    transformer = training.get("token_transformer")
    if not isinstance(transformer, dict):
        return None
    if transformer.get("weight_format") != "mlx_token_transformer_v1":
        return None
    labels = [
        str(label)
        for label in transformer.get("labels", [])
        if isinstance(label, str)
    ]
    weights = _matrix(transformer.get("weights", []))
    bias = _vector(transformer.get("bias", []))
    normalization = transformer.get("normalization", {})
    tokenization = transformer.get("tokenization", {})
    encoder = transformer.get("encoder", {})
    if (
        not isinstance(normalization, dict)
        or not isinstance(tokenization, dict)
        or not isinstance(encoder, dict)
    ):
        return None
    mean = _vector(normalization.get("mean", []))
    scale = _vector(normalization.get("scale", []))
    crop_size = tokenization.get("crop_size")
    raster_grid_size = tokenization.get("raster_grid_size")
    hidden_dim = encoder.get("hidden_dim")
    heads = encoder.get("num_heads")
    layers = encoder.get("num_layers")
    projection = _loaded_token_projection(transformer, hidden_dim)
    token_projection = _loaded_token_projection_weights(transformer, hidden_dim)
    attention_parameters = _loaded_attention_parameters(transformer, hidden_dim, layers)
    if (
        not isinstance(crop_size, int)
        or crop_size <= 0
        or not isinstance(raster_grid_size, int)
        or raster_grid_size <= 0
        or not isinstance(hidden_dim, int)
        or hidden_dim <= 0
        or not isinstance(heads, int)
        or heads <= 0
        or not isinstance(layers, int)
        or layers <= 0
        or not labels
        or len(weights) != len(labels)
        or len(bias) != len(labels)
        or len(mean) != hidden_dim
        or len(scale) != hidden_dim
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
        "tokenization": {
            "crop_size": crop_size,
            "raster_grid_size": raster_grid_size,
        },
        "encoder": {
            "hidden_dim": hidden_dim,
            "num_heads": heads,
            "num_layers": layers,
        },
        "projection_calibration": projection,
        "token_projection": token_projection,
        "attention_parameters": attention_parameters,
    }


def _token_transformer_logits(
    classifier_model: dict[str, object],
    features: tuple[float, ...],
    crop_tokens: tuple[tuple[float, float, float, float], ...],
) -> list[float] | None:
    transformer = classifier_model.get("token_transformer")
    if not isinstance(transformer, dict):
        return None
    tokenization = transformer.get("tokenization", {})
    encoder = transformer.get("encoder", {})
    normalization = transformer.get("normalization", {})
    if (
        not isinstance(tokenization, dict)
        or not isinstance(encoder, dict)
        or not isinstance(normalization, dict)
    ):
        return None
    crop_size = tokenization.get("crop_size")
    raster_grid_size = tokenization.get("raster_grid_size")
    hidden_dim = encoder.get("hidden_dim")
    heads = encoder.get("num_heads")
    layers = encoder.get("num_layers")
    projection = transformer.get("projection_calibration", {})
    if not isinstance(projection, dict):
        projection = {}
    projection_scale = projection.get("scale")
    projection_bias = projection.get("bias")
    token_projection = transformer.get("token_projection", {})
    if not isinstance(token_projection, dict):
        token_projection = {}
    projection_weights = token_projection.get("weights")
    projection_intercept = token_projection.get("bias")
    attention_parameters = transformer.get("attention_parameters")
    if not isinstance(attention_parameters, dict):
        attention_parameters = None
    if (
        not isinstance(crop_size, int)
        or not isinstance(raster_grid_size, int)
        or not isinstance(hidden_dim, int)
        or not isinstance(heads, int)
        or not isinstance(layers, int)
    ):
        return None
    row = token_transformer_embedding(
        features,
        crop_tokens,
        crop_size=crop_size,
        hidden_dim=hidden_dim,
        heads=heads,
        layers=layers,
        raster_grid_size=raster_grid_size,
        projection_scale=(
            projection_scale
            if isinstance(projection_scale, tuple)
            else None
        ),
        projection_bias=(
            projection_bias
            if isinstance(projection_bias, tuple)
            else None
        ),
        projection_weights=(
            projection_weights
            if isinstance(projection_weights, tuple)
            else None
        ),
        projection_intercept=(
            projection_intercept
            if isinstance(projection_intercept, tuple)
            else None
        ),
        attention_parameters=attention_parameters,
    )
    mean = normalization.get("mean", ())
    scale = normalization.get("scale", ())
    weights = transformer.get("weights", ())
    bias = transformer.get("bias", ())
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


def _loaded_token_projection(
    transformer: dict[str, object],
    hidden_dim: object,
) -> dict[str, object]:
    if not isinstance(hidden_dim, int) or hidden_dim <= 0:
        return {
            "scale": (),
            "bias": (),
            "strategy": "identity_fallback",
        }
    projection = transformer.get("projection_calibration")
    if not isinstance(projection, dict):
        return {
            "scale": tuple(1.0 for _ in range(hidden_dim)),
            "bias": tuple(0.0 for _ in range(hidden_dim)),
            "strategy": "identity_fallback",
        }
    scale = _vector(projection.get("scale", []))
    bias = _vector(projection.get("bias", []))
    if len(scale) != hidden_dim or len(bias) != hidden_dim:
        return {
            "scale": tuple(1.0 for _ in range(hidden_dim)),
            "bias": tuple(0.0 for _ in range(hidden_dim)),
            "strategy": "identity_fallback",
        }
    return {
        "scale": tuple(scale),
        "bias": tuple(bias),
        "strategy": str(projection.get("strategy", "")),
        "trained_examples": projection.get("trained_examples"),
    }


def _loaded_token_projection_weights(
    transformer: dict[str, object],
    hidden_dim: object,
) -> dict[str, object] | None:
    if not isinstance(hidden_dim, int) or hidden_dim <= 0:
        return None
    projection = transformer.get("token_projection")
    if not isinstance(projection, dict):
        return None
    if projection.get("weight_format") != "mlx_token_projection_v1":
        return None
    weights = _matrix(projection.get("weights", []))
    bias = _vector(projection.get("bias", []))
    if len(weights) != hidden_dim or len(bias) != hidden_dim:
        return None
    input_count = len(weights[0]) if weights else 0
    if input_count <= 0 or any(len(row) != input_count for row in weights):
        return None
    return {
        "weights": tuple(tuple(row) for row in weights),
        "bias": tuple(bias),
        "input_names": tuple(
            str(name)
            for name in projection.get("input_names", [])
            if isinstance(name, str)
        ),
        "trained_examples": projection.get("trained_examples"),
    }


def _loaded_attention_parameters(
    transformer: dict[str, object],
    hidden_dim: object,
    layer_count: object,
) -> dict[str, object] | None:
    if (
        not isinstance(hidden_dim, int)
        or hidden_dim <= 0
        or not isinstance(layer_count, int)
        or layer_count <= 0
    ):
        return None
    attention = transformer.get("attention_parameters")
    if not isinstance(attention, dict):
        return None
    if attention.get("weight_format") != "mlx_attention_diagonal_v1":
        return None
    layers = attention.get("layers")
    if not isinstance(layers, list) or len(layers) != layer_count:
        return None
    loaded_layers: list[dict[str, tuple[float, ...]]] = []
    for layer in layers:
        if not isinstance(layer, dict):
            return None
        loaded_layer: dict[str, tuple[float, ...]] = {}
        for key in (
            "query_scale",
            "key_scale",
            "value_scale",
            "output_scale",
            "output_bias",
        ):
            values = _vector(layer.get(key, []))
            if len(values) != hidden_dim:
                return None
            loaded_layer[key] = tuple(values)
        loaded_layers.append(loaded_layer)
    return {
        "weight_format": "mlx_attention_diagonal_v1",
        "layers": tuple(loaded_layers),
        "trained_examples": attention.get("trained_examples"),
    }


def _loaded_feature_raster_fusion(
    training: dict[str, object],
) -> dict[str, object] | None:
    fusion = training.get("feature_raster_fusion")
    if not isinstance(fusion, dict):
        return None
    if fusion.get("weight_format") != "mlx_feature_raster_fusion_v1":
        return None
    labels = [
        str(label)
        for label in fusion.get("labels", [])
        if isinstance(label, str)
    ]
    weights = _matrix(fusion.get("weights", []))
    bias = _vector(fusion.get("bias", []))
    normalization = fusion.get("normalization", {})
    if not isinstance(normalization, dict):
        return None
    mean = _vector(normalization.get("mean", []))
    scale = _vector(normalization.get("scale", []))
    raster_embedding_names = [
        str(name)
        for name in fusion.get("raster_embedding_names", [])
        if isinstance(name, str)
    ]
    fusion_config = fusion.get("fusion", {})
    if not isinstance(fusion_config, dict):
        return None
    heads = fusion_config.get("heads")
    input_count = len(FEATURE_NAMES) + len(raster_embedding_names)
    if (
        not isinstance(heads, int)
        or heads <= 0
        or not labels
        or len(weights) != len(labels)
        or len(bias) != len(labels)
        or len(mean) != input_count
        or len(scale) != input_count
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
        "raster_embedding_names": tuple(raster_embedding_names),
        "fusion": {
            "heads": heads,
            "strategy": str(fusion_config.get("strategy", "")),
        },
    }


def _feature_raster_fusion_logits(
    classifier_model: dict[str, object],
    features: tuple[float, ...],
    crop_tokens: tuple[tuple[float, float, float, float], ...],
) -> list[float] | None:
    fusion = classifier_model.get("feature_raster_fusion")
    crop_spec = classifier_model.get("crop_token_spec", {})
    if not isinstance(fusion, dict) or not isinstance(crop_spec, dict):
        return None
    fusion_config = fusion.get("fusion", {})
    normalization = fusion.get("normalization", {})
    if not isinstance(fusion_config, dict) or not isinstance(normalization, dict):
        return None
    heads = fusion_config.get("heads")
    crop_size = crop_spec.get("crop_size")
    if not isinstance(heads, int) or not isinstance(crop_size, int):
        return None
    raster_row = _raster_attention_embedding(
        crop_tokens,
        crop_size=crop_size,
        heads=heads,
    )
    row = (*features, *raster_row)
    mean = normalization.get("mean", ())
    scale = normalization.get("scale", ())
    weights = fusion.get("weights", ())
    bias = fusion.get("bias", ())
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
        and (
            isinstance(classifier_model.get("raster_token_mixer"), dict)
            or isinstance(classifier_model.get("feature_raster_fusion"), dict)
            or isinstance(classifier_model.get("token_transformer"), dict)
        )
        and isinstance(classifier_model.get("crop_token_spec"), dict)
    )


def classifier_uses_raster_tokens(classifier_model: dict[str, object]) -> bool:
    return _classifier_uses_raster_tokens(classifier_model)


def _classifier_crop_size(classifier_model: dict[str, object]) -> int:
    crop_spec = classifier_model.get("crop_token_spec", {})
    if isinstance(crop_spec, dict) and isinstance(crop_spec.get("crop_size"), int):
        return int(crop_spec["crop_size"])
    return 16


def classifier_crop_size(classifier_model: dict[str, object]) -> int:
    return _classifier_crop_size(classifier_model)


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
        "label_accuracy": _label_accuracy_from_confusion(confusion),
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
        "label_accuracy": _label_accuracy_from_confusion(confusion),
    }


def _label_accuracy_from_confusion(
    confusion: dict[str, dict[str, int]],
) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for label, predicted_counts in sorted(confusion.items()):
        total = sum(predicted_counts.values())
        correct = int(predicted_counts.get(label, 0))
        result[label] = {
            "examples": total,
            "correct": correct,
            "accuracy": correct / total if total else None,
        }
    return result


def evaluate_raster_classifier_ranking(
    classifier_model: dict[str, object],
    examples: tuple[RasterRankingExample, ...],
) -> dict[str, object]:
    total = 0
    heuristic_correct = 0
    classifier_correct = 0
    changed = 0
    decisions: list[dict[str, object]] = []
    for example in examples:
        candidates = _candidate_alternatives(example.anchor)
        if not candidates:
            continue
        total += 1
        heuristic_label = min(candidates, key=semantic_anchor_score).kind.value
        assisted_candidates = tuple(
            _candidate_with_classifier_prior(
                candidate,
                classifier_model,
                crop_tokens=example.crop_tokens,
            )
            for candidate in candidates
        )
        classifier_label = min(
            assisted_candidates,
            key=semantic_anchor_score,
        ).kind.value
        if heuristic_label == example.label:
            heuristic_correct += 1
        if classifier_label == example.label:
            classifier_correct += 1
        if heuristic_label != classifier_label:
            changed += 1
        decisions.append(
            {
                "label": example.label,
                "heuristic": heuristic_label,
                "classifier": classifier_label,
                "sample_id": example.sample_id,
                "anchor_index": example.anchor_index,
                "uses_raster_tokens": True,
            }
        )

    result = _ranking_result(
        total=total,
        heuristic_correct=heuristic_correct,
        classifier_correct=classifier_correct,
        changed=changed,
        decisions=decisions,
    )
    result["uses_raster_tokens"] = True
    return result


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

    return _ranking_result(
        total=total,
        heuristic_correct=heuristic_correct,
        classifier_correct=classifier_correct,
        changed=changed,
        decisions=examples,
    )


def _ranking_result(
    *,
    total: int,
    heuristic_correct: int,
    classifier_correct: int,
    changed: int,
    decisions: list[dict[str, object]],
) -> dict[str, object]:
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
        "decisions": decisions,
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
    *,
    crop_tokens: tuple[tuple[float, float, float, float], ...] | None = None,
) -> AnchorCandidate:
    metrics = dict(candidate.metrics)
    metrics["classifier_prior_error"] = classifier_prior_error(
        classifier_model,
        candidate,
        crop_tokens=crop_tokens,
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
        arc=candidate.arc,
        ellipse=candidate.ellipse,
        path=candidate.path,
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
        arc=candidate.arc,
        ellipse=candidate.ellipse,
        path=candidate.path,
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
        closed=bool(stroke.get("closed", False)),
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
