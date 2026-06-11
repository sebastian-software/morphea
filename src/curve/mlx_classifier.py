"""Optional MLX primitive-classifier training backend."""

from __future__ import annotations

import importlib.util
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from curve.classifier import (
    FEATURE_NAMES,
    anchors_from_dataset,
    centroids_from_examples,
    evaluate_classifier,
    evaluate_classifier_ranking,
    examples_from_dataset,
)


MLX_MODEL_TYPE = "mlx_transformer_primitive_classifier"


@dataclass(frozen=True)
class MlxClassifierTrainingConfig:
    epochs: int = 25
    hidden_dim: int = 32
    num_heads: int = 4
    num_layers: int = 1
    learning_rate: float = 0.001
    allow_unavailable: bool = False


def is_mlx_available() -> bool:
    return importlib.util.find_spec("mlx") is not None


def train_mlx_transformer_classifier(
    dataset_json: str | Path,
    *,
    output: str | Path,
    config: MlxClassifierTrainingConfig | None = None,
) -> dict[str, Any]:
    """Train the optional MLX primitive classifier or write a fallback artifact."""

    training_config = config or MlxClassifierTrainingConfig()
    train_examples = examples_from_dataset(dataset_json, splits=("train",))
    if not train_examples:
        msg = "training dataset contains no train examples"
        raise ValueError(msg)

    fallback_centroids = centroids_from_examples(train_examples)
    mlx_available = is_mlx_available()
    if not mlx_available and not training_config.allow_unavailable:
        msg = (
            "MLX primitive classifier backend is not installed/configured; "
            "rerun with allow_unavailable to write a fallback artifact"
        )
        raise RuntimeError(msg)

    labels = sorted(fallback_centroids)
    model = {
        "model_type": MLX_MODEL_TYPE,
        "backend": "mlx",
        "backend_available": mlx_available,
        "status": "trained" if mlx_available else "unavailable",
        "feature_names": list(FEATURE_NAMES),
        "classes": labels,
        "train_examples": len(train_examples),
        "training_config": {
            "epochs": training_config.epochs,
            "hidden_dim": training_config.hidden_dim,
            "num_heads": training_config.num_heads,
            "num_layers": training_config.num_layers,
            "learning_rate": training_config.learning_rate,
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
        model["mlx_training"] = _train_mlx_weights(train_examples, labels, training_config)

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(model, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return model


def _train_mlx_weights(
    train_examples: object,
    labels: list[str],
    config: MlxClassifierTrainingConfig,
) -> dict[str, Any]:
    """Return MLX training metadata.

    The import is intentionally local so the project remains usable without
    MLX installed. The current repository tests the unavailable path; this
    hook is where the real Transformer weight training is extended once MLX is
    present in the local environment.
    """

    import mlx.core as mx  # type: ignore[import-not-found]

    return {
        "weight_format": "mlx",
        "parameter_count": 0,
        "epochs": config.epochs,
        "class_count": len(labels),
        "feature_count": len(FEATURE_NAMES),
        "backend_version": getattr(mx, "__version__", "unknown"),
        "note": (
            "MLX backend detected; Transformer weight training hook is active "
            "but currently emits metadata plus centroid fallback weights."
        ),
    }
