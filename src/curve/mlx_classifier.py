"""Optional MLX primitive-classifier training backend."""

from __future__ import annotations

import importlib.util
import json
from dataclasses import dataclass
from math import exp, log
from pathlib import Path
from typing import Any

from curve.classifier import (
    FEATURE_NAMES,
    RasterTrainingExample,
    TrainingExample,
    anchors_from_dataset,
    centroids_from_examples,
    evaluate_classifier,
    evaluate_classifier_ranking,
    examples_from_dataset,
    feature_importance_from_centroids,
    raster_examples_from_dataset,
)
from curve.token_transformer import (
    raster_grid_token_count,
    token_transformer_embedding,
)


MLX_MODEL_TYPE = "mlx_transformer_primitive_classifier"


@dataclass(frozen=True)
class MlxClassifierTrainingConfig:
    epochs: int = 25
    hidden_dim: int = 32
    num_heads: int = 4
    num_layers: int = 1
    learning_rate: float = 0.001
    crop_size: int = 16
    allow_unavailable: bool = False


def is_mlx_available() -> bool:
    return importlib.util.find_spec("mlx") is not None


def mlx_classifier_runtime_status() -> dict[str, object]:
    available = is_mlx_available()
    return {
        "backend": "mlx",
        "backend_available": available,
        "status": "available" if available else "not_installed",
        "reason": (
            None
            if available
            else "MLX primitive classifier runtime is not installed"
        ),
        "training_implementation": (
            "mlx_feature_head" if available else "centroid_fallback"
        ),
    }


def train_mlx_transformer_classifier(
    dataset_json: str | Path,
    *,
    output: str | Path,
    config: MlxClassifierTrainingConfig | None = None,
) -> dict[str, Any]:
    """Train the optional MLX primitive classifier or write a fallback artifact."""

    training_config = config or MlxClassifierTrainingConfig()
    if training_config.crop_size <= 0:
        msg = "MLX crop_size must be positive"
        raise ValueError(msg)
    if training_config.num_heads <= 0:
        msg = "MLX num_heads must be positive"
        raise ValueError(msg)
    if training_config.hidden_dim <= 0:
        msg = "MLX hidden_dim must be positive"
        raise ValueError(msg)
    if training_config.num_layers <= 0:
        msg = "MLX num_layers must be positive"
        raise ValueError(msg)
    train_examples = examples_from_dataset(dataset_json, splits=("train",))
    if not train_examples:
        msg = "training dataset contains no train examples"
        raise ValueError(msg)

    fallback_centroids = centroids_from_examples(train_examples)
    runtime = mlx_classifier_runtime_status()
    mlx_available = bool(runtime["backend_available"])
    if not mlx_available and not training_config.allow_unavailable:
        msg = (
            "MLX primitive classifier backend is not installed/configured "
            f"(status={runtime['status']}); "
            "rerun with allow_unavailable to write a fallback artifact"
        )
        raise RuntimeError(msg)

    labels = sorted(fallback_centroids)
    model = {
        "model_type": MLX_MODEL_TYPE,
        "backend": "mlx",
        "backend_available": mlx_available,
        "status": "trained" if mlx_available else "unavailable",
        "runtime": runtime,
        "reason": runtime["reason"],
        "training_implementation": runtime["training_implementation"],
        "feature_names": list(FEATURE_NAMES),
        "classes": labels,
        "train_examples": len(train_examples),
        "training_config": {
            "epochs": training_config.epochs,
            "hidden_dim": training_config.hidden_dim,
            "num_heads": training_config.num_heads,
            "num_layers": training_config.num_layers,
            "learning_rate": training_config.learning_rate,
            "crop_size": training_config.crop_size,
        },
        "fallback_model_type": "centroid_primitive_classifier",
        "fallback_centroids": {
            label: list(values)
            for label, values in sorted(fallback_centroids.items())
        },
        "feature_importance": feature_importance_from_centroids(fallback_centroids),
        "evaluation": {
            "val": evaluate_classifier(
                fallback_centroids,
                examples_from_dataset(dataset_json, splits=("val",)),
            ),
            "test": evaluate_classifier(
                fallback_centroids,
                examples_from_dataset(dataset_json, splits=("test",)),
            ),
        },
        "ranking_evaluation": {
            "val": evaluate_classifier_ranking(
                fallback_centroids,
                anchors_from_dataset(dataset_json, splits=("val",)),
            ),
            "test": evaluate_classifier_ranking(
                fallback_centroids,
                anchors_from_dataset(dataset_json, splits=("test",)),
            ),
        },
    }

    if mlx_available:
        raster_examples = raster_examples_from_dataset(
            dataset_json,
            crop_size=training_config.crop_size,
            splits=("train",),
        )
        model["mlx_training"] = _train_mlx_weights(
            train_examples,
            raster_examples,
            labels,
            training_config,
        )

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(model, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return model


def _train_mlx_weights(
    train_examples: tuple[TrainingExample, ...],
    raster_examples: tuple[RasterTrainingExample, ...],
    labels: list[str],
    config: MlxClassifierTrainingConfig,
) -> dict[str, Any]:
    """Return an optimized MLX feature-head artifact.

    The import is intentionally local so the project remains usable without
    MLX installed. The first implemented MLX-backed head trains over the
    semantic feature sequence and keeps the centroid fallback as the runtime
    ranking prior until the full raster-crop Transformer is wired.
    """

    import mlx.core as mx  # type: ignore[import-not-found]

    head = _train_feature_head(train_examples, labels, config)
    head["crop_token_spec"] = {
        "source": "anchor_rgba_crop",
        "crop_size": config.crop_size,
        "token_shape": [config.crop_size * config.crop_size, 4],
        "channel_order": ["r", "g", "b", "a"],
        "value_range": [0.0, 1.0],
    }
    head["crop_token_summary"] = _crop_token_summary(raster_examples)
    head["raster_token_mixer"] = _train_raster_token_mixer(
        raster_examples,
        labels,
        config,
    )
    head["feature_raster_fusion"] = _train_feature_raster_fusion(
        train_examples,
        raster_examples,
        labels,
        config,
    )
    head["token_transformer"] = _train_token_transformer(
        train_examples,
        raster_examples,
        labels,
        config,
    )
    head["feature_head_parameter_count"] = head["parameter_count"]
    head["parameter_count"] += head["raster_token_mixer"]["parameter_count"]
    head["parameter_count"] += head["feature_raster_fusion"]["parameter_count"]
    head["parameter_count"] += head["token_transformer"]["parameter_count"]
    head["architecture"] = (
        "feature_head_plus_raster_token_mixer_fusion_and_token_transformer"
    )
    head["transformer_status"] = "token_transformer_encoder_serialized"
    head["backend_version"] = getattr(mx, "__version__", "unknown")
    head["backend_array_api"] = "mlx.core"
    return head


def _train_feature_head(
    train_examples: tuple[TrainingExample, ...],
    labels: list[str],
    config: MlxClassifierTrainingConfig,
) -> dict[str, Any]:
    feature_count = len(FEATURE_NAMES)
    label_to_index = {label: index for index, label in enumerate(labels)}
    means, scales = _feature_normalization(train_examples)
    rows = [
        (
            _normalize_features(example.features, means, scales),
            label_to_index[example.label],
        )
        for example in train_examples
        if example.label in label_to_index
    ]
    if not rows:
        msg = "training examples do not match classifier labels"
        raise ValueError(msg)

    weights = [[0.0 for _ in range(feature_count)] for _ in labels]
    bias = [0.0 for _ in labels]
    loss_history: list[dict[str, float | int]] = []
    epochs = max(1, config.epochs)
    learning_rate = config.learning_rate
    for epoch in range(epochs):
        grad_weights = [[0.0 for _ in range(feature_count)] for _ in labels]
        grad_bias = [0.0 for _ in labels]
        loss = 0.0
        correct = 0
        for features, target_index in rows:
            logits = [
                bias[class_index]
                + sum(
                    weights[class_index][feature_index] * features[feature_index]
                    for feature_index in range(feature_count)
                )
                for class_index in range(len(labels))
            ]
            probabilities = _softmax(logits)
            loss -= log(max(probabilities[target_index], 1e-12))
            if _argmax(probabilities) == target_index:
                correct += 1
            for class_index, probability in enumerate(probabilities):
                coefficient = probability - (
                    1.0 if class_index == target_index else 0.0
                )
                grad_bias[class_index] += coefficient
                for feature_index, feature_value in enumerate(features):
                    grad_weights[class_index][feature_index] += (
                        coefficient * feature_value
                    )

        scale = 1 / len(rows)
        for class_index in range(len(labels)):
            bias[class_index] -= learning_rate * grad_bias[class_index] * scale
            for feature_index in range(feature_count):
                weights[class_index][feature_index] -= (
                    learning_rate * grad_weights[class_index][feature_index] * scale
                )
        loss_history.append(
            {
                "epoch": epoch + 1,
                "loss": loss * scale,
                "accuracy": correct / len(rows),
            }
        )

    return {
        "weight_format": "mlx_feature_head_v1",
        "architecture": "normalized_feature_softmax_head",
        "transformer_status": "pending_raster_crop_encoder",
        "parameter_count": len(labels) * (feature_count + 1),
        "epochs": config.epochs,
        "class_count": len(labels),
        "feature_count": len(FEATURE_NAMES),
        "labels": list(labels),
        "feature_names": list(FEATURE_NAMES),
        "normalization": {
            "mean": list(means),
            "scale": list(scales),
        },
        "weights": weights,
        "bias": bias,
        "loss_history": loss_history,
        "note": (
            "MLX backend detected; this artifact contains optimized feature-head "
            "weights while the raster-crop Transformer encoder remains pending."
        ),
    }


def _train_raster_token_mixer(
    raster_examples: tuple[RasterTrainingExample, ...],
    labels: list[str],
    config: MlxClassifierTrainingConfig,
) -> dict[str, Any]:
    embedding_names = _raster_embedding_names(config.num_heads)
    label_to_index = {label: index for index, label in enumerate(labels)}
    rows = [
        (
            _raster_attention_embedding(example, config),
            label_to_index[example.label],
        )
        for example in raster_examples
        if example.label in label_to_index
    ]
    if not rows:
        return {
            "weight_format": "raster_token_mixer_v1",
            "attention": {
                "heads": config.num_heads,
                "embedding_names": embedding_names,
            },
            "parameter_count": 0,
            "weights": [],
            "bias": [],
            "normalization": {"mean": [], "scale": []},
            "loss_history": [],
        }
    means, scales = _row_normalization(tuple(row for row, _ in rows))
    normalized_rows = [
        (_normalize_row(row, means, scales), target_index)
        for row, target_index in rows
    ]
    weights, bias, loss_history = _train_softmax(
        normalized_rows,
        class_count=len(labels),
        input_count=len(embedding_names),
        config=config,
    )
    return {
        "weight_format": "raster_token_mixer_v1",
        "attention": {
            "heads": config.num_heads,
            "embedding_names": embedding_names,
            "score": "foreground_weighted_spatial_rgba",
        },
        "parameter_count": len(labels) * (len(embedding_names) + 1),
        "labels": list(labels),
        "normalization": {
            "mean": list(means),
            "scale": list(scales),
        },
        "weights": weights,
        "bias": bias,
        "loss_history": loss_history,
    }


def _train_feature_raster_fusion(
    train_examples: tuple[TrainingExample, ...],
    raster_examples: tuple[RasterTrainingExample, ...],
    labels: list[str],
    config: MlxClassifierTrainingConfig,
) -> dict[str, Any]:
    raster_embedding_names = _raster_embedding_names(config.num_heads)
    input_names = [
        *(f"feature_{name}" for name in FEATURE_NAMES),
        *raster_embedding_names,
    ]
    label_to_index = {label: index for index, label in enumerate(labels)}
    rows = []
    for example, raster_example in zip(train_examples, raster_examples):
        if (
            example.label not in label_to_index
            or raster_example.label != example.label
        ):
            continue
        row = (
            *example.features,
            *_raster_attention_embedding(raster_example, config),
        )
        rows.append((row, label_to_index[example.label]))
    if not rows:
        return {
            "weight_format": "mlx_feature_raster_fusion_v1",
            "feature_names": list(FEATURE_NAMES),
            "raster_embedding_names": raster_embedding_names,
            "input_names": input_names,
            "fusion": {
                "strategy": "concat_feature_and_raster_attention",
                "heads": config.num_heads,
            },
            "parameter_count": 0,
            "weights": [],
            "bias": [],
            "normalization": {"mean": [], "scale": []},
            "loss_history": [],
        }

    means, scales = _row_normalization(tuple(row for row, _ in rows))
    normalized_rows = [
        (_normalize_row(row, means, scales), target_index)
        for row, target_index in rows
    ]
    weights, bias, loss_history = _train_softmax(
        normalized_rows,
        class_count=len(labels),
        input_count=len(input_names),
        config=config,
    )
    return {
        "weight_format": "mlx_feature_raster_fusion_v1",
        "feature_names": list(FEATURE_NAMES),
        "raster_embedding_names": raster_embedding_names,
        "input_names": input_names,
        "labels": list(labels),
        "fusion": {
            "strategy": "concat_feature_and_raster_attention",
            "heads": config.num_heads,
        },
        "parameter_count": len(labels) * (len(input_names) + 1),
        "normalization": {
            "mean": list(means),
            "scale": list(scales),
        },
        "weights": weights,
        "bias": bias,
        "loss_history": loss_history,
    }


def _train_token_transformer(
    train_examples: tuple[TrainingExample, ...],
    raster_examples: tuple[RasterTrainingExample, ...],
    labels: list[str],
    config: MlxClassifierTrainingConfig,
) -> dict[str, Any]:
    label_to_index = {label: index for index, label in enumerate(labels)}
    projection = _learn_token_projection_calibration(
        train_examples,
        raster_examples,
        labels,
        config,
    )
    rows = []
    for example, raster_example in zip(train_examples, raster_examples):
        if (
            example.label not in label_to_index
            or raster_example.label != example.label
        ):
            continue
        rows.append(
            (
                token_transformer_embedding(
                    example.features,
                    raster_example.crop_tokens,
                    crop_size=config.crop_size,
                    hidden_dim=config.hidden_dim,
                    heads=config.num_heads,
                    layers=config.num_layers,
                    projection_scale=tuple(projection["scale"]),
                    projection_bias=tuple(projection["bias"]),
                ),
                label_to_index[example.label],
            )
        )
    if not rows:
        return {
            "weight_format": "mlx_token_transformer_v1",
            "labels": list(labels),
            "tokenization": _token_transformer_tokenization(config),
            "encoder": _token_transformer_encoder_config(config),
            "projection_calibration": projection,
            "parameter_count": 0,
            "weights": [],
            "bias": [],
            "normalization": {"mean": [], "scale": []},
            "loss_history": [],
        }

    means, scales = _row_normalization(tuple(row for row, _ in rows))
    normalized_rows = [
        (_normalize_row(row, means, scales), target_index)
        for row, target_index in rows
    ]
    weights, bias, loss_history = _train_softmax(
        normalized_rows,
        class_count=len(labels),
        input_count=config.hidden_dim,
        config=config,
    )
    return {
        "weight_format": "mlx_token_transformer_v1",
        "labels": list(labels),
        "tokenization": _token_transformer_tokenization(config),
        "encoder": _token_transformer_encoder_config(config),
        "projection_calibration": projection,
        "parameter_count": len(labels) * (config.hidden_dim + 1)
        + config.hidden_dim * 2,
        "normalization": {
            "mean": list(means),
            "scale": list(scales),
        },
        "weights": weights,
        "bias": bias,
        "loss_history": loss_history,
    }


def _token_transformer_tokenization(
    config: MlxClassifierTrainingConfig,
) -> dict[str, Any]:
    return {
        "feature_names": list(FEATURE_NAMES),
        "crop_size": config.crop_size,
        "raster_grid_size": min(4, config.crop_size),
        "raster_token_count": raster_grid_token_count(config.crop_size),
        "feature_token_count": len(FEATURE_NAMES),
        "channel_order": ["r", "g", "b", "a"],
    }


def _token_transformer_encoder_config(
    config: MlxClassifierTrainingConfig,
) -> dict[str, Any]:
    return {
        "hidden_dim": config.hidden_dim,
        "num_heads": config.num_heads,
        "num_layers": config.num_layers,
        "attention": "scaled_dot_product_self_attention",
        "projection": "learned_calibrated_feature_rgba_v1",
        "pooling": "mean_token_pool",
    }


def _learn_token_projection_calibration(
    train_examples: tuple[TrainingExample, ...],
    raster_examples: tuple[RasterTrainingExample, ...],
    labels: list[str],
    config: MlxClassifierTrainingConfig,
) -> dict[str, Any]:
    grouped: dict[str, list[tuple[float, ...]]] = {label: [] for label in labels}
    for example, raster_example in zip(train_examples, raster_examples):
        if example.label not in grouped or raster_example.label != example.label:
            continue
        grouped[example.label].append(
            token_transformer_embedding(
                example.features,
                raster_example.crop_tokens,
                crop_size=config.crop_size,
                hidden_dim=config.hidden_dim,
                heads=config.num_heads,
                layers=config.num_layers,
            )
        )
    rows = [row for group in grouped.values() for row in group]
    if not rows:
        return {
            "strategy": "between_class_encoder_output_calibration",
            "scale": [1.0 for _ in range(config.hidden_dim)],
            "bias": [0.0 for _ in range(config.hidden_dim)],
            "trained_examples": 0,
        }

    global_mean = [
        sum(row[index] for row in rows) / len(rows)
        for index in range(config.hidden_dim)
    ]
    scale: list[float] = []
    bias: list[float] = []
    for index in range(config.hidden_dim):
        class_means = [
            sum(row[index] for row in group) / len(group)
            for group in grouped.values()
            if group
        ]
        if not class_means:
            scale.append(1.0)
            bias.append(0.0)
            continue
        between = (
            sum(abs(value - global_mean[index]) for value in class_means)
            / len(class_means)
        )
        multiplier = min(1.5, between * 2.0)
        scale.append(1.0 + multiplier)
        bias.append(-global_mean[index] * min(0.5, multiplier))
    return {
        "strategy": "between_class_encoder_output_calibration",
        "scale": scale,
        "bias": bias,
        "trained_examples": len(rows),
    }


def _feature_normalization(
    train_examples: tuple[TrainingExample, ...],
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    feature_count = len(FEATURE_NAMES)
    means = tuple(
        sum(example.features[index] for example in train_examples) / len(train_examples)
        for index in range(feature_count)
    )
    variances = tuple(
        sum((example.features[index] - means[index]) ** 2 for example in train_examples)
        / len(train_examples)
        for index in range(feature_count)
    )
    scales = tuple(max(variance ** 0.5, 1.0) for variance in variances)
    return means, scales


def _normalize_features(
    features: tuple[float, ...],
    means: tuple[float, ...],
    scales: tuple[float, ...],
) -> tuple[float, ...]:
    return tuple(
        (features[index] - means[index]) / scales[index]
        for index in range(len(FEATURE_NAMES))
    )


def _raster_embedding_names(head_count: int) -> list[str]:
    names: list[str] = []
    for head in range(head_count):
        names.extend(
            [
                f"head_{head}_red",
                f"head_{head}_green",
                f"head_{head}_blue",
                f"head_{head}_alpha",
                f"head_{head}_x",
                f"head_{head}_y",
                f"head_{head}_foreground",
            ]
        )
    return names


def _raster_attention_embedding(
    example: RasterTrainingExample,
    config: MlxClassifierTrainingConfig,
) -> tuple[float, ...]:
    crop_size = config.crop_size
    embedding: list[float] = []
    for head in range(config.num_heads):
        weighted = [0.0 for _ in range(7)]
        total_weight = 0.0
        for index, token in enumerate(example.crop_tokens):
            red, green, blue, alpha = token
            x = (index % crop_size) / max(1, crop_size - 1)
            y = (index // crop_size) / max(1, crop_size - 1)
            foreground = alpha * (
                abs(red - 1.0) + abs(green - 1.0) + abs(blue - 1.0)
            ) / 3
            spatial_bias = _head_spatial_bias(head, x, y)
            weight = 1e-6 + foreground * spatial_bias
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


def _row_normalization(
    rows: tuple[tuple[float, ...], ...],
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    if not rows:
        return (), ()
    input_count = len(rows[0])
    means = tuple(
        sum(row[index] for row in rows) / len(rows)
        for index in range(input_count)
    )
    variances = tuple(
        sum((row[index] - means[index]) ** 2 for row in rows) / len(rows)
        for index in range(input_count)
    )
    scales = tuple(max(variance ** 0.5, 1.0) for variance in variances)
    return means, scales


def _normalize_row(
    row: tuple[float, ...],
    means: tuple[float, ...],
    scales: tuple[float, ...],
) -> tuple[float, ...]:
    return tuple(
        (row[index] - means[index]) / scales[index]
        for index in range(len(row))
    )


def _train_softmax(
    rows: list[tuple[tuple[float, ...], int]],
    *,
    class_count: int,
    input_count: int,
    config: MlxClassifierTrainingConfig,
) -> tuple[list[list[float]], list[float], list[dict[str, float | int]]]:
    weights = [[0.0 for _ in range(input_count)] for _ in range(class_count)]
    bias = [0.0 for _ in range(class_count)]
    loss_history: list[dict[str, float | int]] = []
    epochs = max(1, config.epochs)
    learning_rate = config.learning_rate
    for epoch in range(epochs):
        grad_weights = [[0.0 for _ in range(input_count)] for _ in range(class_count)]
        grad_bias = [0.0 for _ in range(class_count)]
        loss = 0.0
        correct = 0
        for values, target_index in rows:
            logits = [
                bias[class_index]
                + sum(
                    weights[class_index][input_index] * values[input_index]
                    for input_index in range(input_count)
                )
                for class_index in range(class_count)
            ]
            probabilities = _softmax(logits)
            loss -= log(max(probabilities[target_index], 1e-12))
            if _argmax(probabilities) == target_index:
                correct += 1
            for class_index, probability in enumerate(probabilities):
                coefficient = probability - (
                    1.0 if class_index == target_index else 0.0
                )
                grad_bias[class_index] += coefficient
                for input_index, value in enumerate(values):
                    grad_weights[class_index][input_index] += coefficient * value
        scale = 1 / len(rows)
        for class_index in range(class_count):
            bias[class_index] -= learning_rate * grad_bias[class_index] * scale
            for input_index in range(input_count):
                weights[class_index][input_index] -= (
                    learning_rate * grad_weights[class_index][input_index] * scale
                )
        loss_history.append(
            {
                "epoch": epoch + 1,
                "loss": loss * scale,
                "accuracy": correct / len(rows),
            }
        )
    return weights, bias, loss_history


def _softmax(logits: list[float]) -> list[float]:
    offset = max(logits)
    exps = [exp(logit - offset) for logit in logits]
    total = sum(exps)
    return [value / total for value in exps]


def _argmax(values: list[float]) -> int:
    return max(range(len(values)), key=values.__getitem__)


def _crop_token_summary(
    raster_examples: tuple[RasterTrainingExample, ...],
) -> dict[str, Any]:
    if not raster_examples:
        return {
            "raster_example_count": 0,
            "mean_rgba": [0.0, 0.0, 0.0, 0.0],
            "bounds_area_mean": 0.0,
        }
    channel_sums = [0.0, 0.0, 0.0, 0.0]
    token_count = 0
    bounds_area = 0.0
    for example in raster_examples:
        left, top, right, bottom = example.bounds
        bounds_area += max(0, right - left) * max(0, bottom - top)
        for token in example.crop_tokens:
            token_count += 1
            for index, value in enumerate(token):
                channel_sums[index] += value
    return {
        "raster_example_count": len(raster_examples),
        "mean_rgba": [
            value / token_count if token_count else 0.0
            for value in channel_sums
        ],
        "bounds_area_mean": bounds_area / len(raster_examples),
    }
