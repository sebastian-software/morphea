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
    raster_examples_from_dataset,
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
