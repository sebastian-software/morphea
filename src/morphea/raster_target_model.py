"""Train supervised raster-target models."""

from __future__ import annotations

import importlib.util
import json
from dataclasses import dataclass
from math import exp, sqrt, tanh
from pathlib import Path
from typing import Any

from PIL import Image


RASTER_TARGET_MODEL_TYPE = "raster_target_classifier"
RASTER_TARGET_MLX_TRAINING_IMPLEMENTATION = "mlx_multilabel_raster_target_head"
RASTER_TARGET_FALLBACK_TRAINING_IMPLEMENTATION = "centroid_raster_target_baseline"
RASTER_TARGET_TRAINING_IMPLEMENTATION = RASTER_TARGET_MLX_TRAINING_IMPLEMENTATION
RASTER_TARGET_DEFAULT_GRID_SIZE = 12
RASTER_TARGET_MLX_REQUIRED_SYMBOLS = (
    "array",
    "eval",
    "exp",
    "log",
    "matmul",
    "mean",
    "sigmoid",
    "tanh",
    "transpose",
    "value_and_grad",
    "zeros",
)
RASTER_TARGET_GLOBAL_FEATURE_NAMES = (
    "ink_fraction",
    "ink_center_x",
    "ink_center_y",
    "ink_width",
    "ink_height",
    "ink_aspect_ratio",
    "ink_bbox_area",
)
RASTER_TARGET_FEATURE_NAMES = (
    *RASTER_TARGET_GLOBAL_FEATURE_NAMES,
    *tuple(
        f"ink_grid_{row}_{column}"
        for row in range(RASTER_TARGET_DEFAULT_GRID_SIZE)
        for column in range(RASTER_TARGET_DEFAULT_GRID_SIZE)
    ),
)


@dataclass(frozen=True)
class RasterTargetTrainingConfig:
    """Configuration for supervised raster-target training."""

    epochs: int = 300
    hidden_dim: int = 32
    learning_rate: float = 0.15
    grid_size: int = RASTER_TARGET_DEFAULT_GRID_SIZE
    allow_unavailable: bool = False


def is_raster_target_mlx_available() -> bool:
    """Return whether the MLX package can be discovered."""

    return importlib.util.find_spec("mlx") is not None


def raster_target_runtime_status() -> dict[str, object]:
    """Return local MLX runtime status for raster-target training."""

    package_available = is_raster_target_mlx_available()
    if not package_available:
        return {
            "backend": "mlx",
            "backend_available": False,
            "status": "not_installed",
            "reason": "MLX raster-target training runtime is not installed",
            "next_action": "Install the MLX extra with uv: uv pip install -e '.[mlx]'",
            "training_implementation": RASTER_TARGET_FALLBACK_TRAINING_IMPLEMENTATION,
            "package_available": False,
            "core_available": False,
            "autograd_available": False,
            "missing_symbols": list(RASTER_TARGET_MLX_REQUIRED_SYMBOLS),
        }
    try:
        import mlx.core as mx  # type: ignore[import-not-found]
    except Exception as exc:  # pragma: no cover - exact import failures vary.
        return {
            "backend": "mlx",
            "backend_available": False,
            "status": "core_unavailable",
            "reason": f"MLX core could not be imported: {exc}",
            "next_action": "Upgrade the MLX extra with uv: uv pip install -U -e '.[mlx]'",
            "training_implementation": RASTER_TARGET_FALLBACK_TRAINING_IMPLEMENTATION,
            "package_available": True,
            "core_available": False,
            "autograd_available": False,
            "missing_symbols": list(RASTER_TARGET_MLX_REQUIRED_SYMBOLS),
        }

    missing = [
        name for name in RASTER_TARGET_MLX_REQUIRED_SYMBOLS if not hasattr(mx, name)
    ]
    available = not missing
    return {
        "backend": "mlx",
        "backend_available": available,
        "status": "available" if available else "autograd_unavailable",
        "reason": (
            None
            if available
            else "MLX core is missing required training symbols: "
            + ", ".join(missing)
        ),
        "next_action": None if available else "Upgrade the MLX extra with uv: uv pip install -U -e '.[mlx]'",
        "training_implementation": (
            RASTER_TARGET_MLX_TRAINING_IMPLEMENTATION
            if available
            else RASTER_TARGET_FALLBACK_TRAINING_IMPLEMENTATION
        ),
        "package_available": True,
        "core_available": True,
        "backend_version": getattr(mx, "__version__", "unknown"),
        "autograd_available": available,
        "missing_symbols": missing,
    }


def train_raster_target_model(
    corpus_json: str | Path,
    *,
    output: str | Path,
    markdown: str | Path | None = None,
    config: RasterTargetTrainingConfig | None = None,
    target_label_key: str = "anchor_kind_targets",
) -> dict[str, Any]:
    """Train and persist a multi-label raster target model."""

    training_config = config or RasterTargetTrainingConfig()
    if training_config.epochs <= 0:
        msg = "raster target epochs must be positive"
        raise ValueError(msg)
    if training_config.hidden_dim <= 0:
        msg = "raster target hidden_dim must be positive"
        raise ValueError(msg)
    if training_config.learning_rate <= 0:
        msg = "raster target learning_rate must be positive"
        raise ValueError(msg)
    if training_config.grid_size <= 0:
        msg = "raster target grid_size must be positive"
        raise ValueError(msg)

    feature_names = _raster_feature_names(training_config.grid_size)
    corpus_path = Path(corpus_json)
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    examples = _corpus_examples(
        corpus,
        grid_size=training_config.grid_size,
        target_label_key=target_label_key,
    )
    train_examples = [example for example in examples if example["split"] == "train"]
    if not train_examples:
        msg = "target corpus contains no rendered train examples"
        raise ValueError(msg)
    target_names = sorted(
        {
            target
            for example in train_examples
            for target in example["target_labels"]
        }
    )
    if not target_names:
        msg = "target corpus contains no train target labels"
        raise ValueError(msg)

    target_models = {
        target: _target_centroid_model(train_examples, target, len(feature_names))
        for target in target_names
    }
    runtime = raster_target_runtime_status()
    backend_available = bool(runtime["backend_available"])
    if not backend_available and not training_config.allow_unavailable:
        msg = (
            "MLX raster-target backend is not installed/configured "
            f"(status={runtime['status']}); "
            "rerun with allow_unavailable to write a fallback artifact"
        )
        raise RuntimeError(msg)

    model = {
        "schema_version": 1,
        "model_type": RASTER_TARGET_MODEL_TYPE,
        "backend": "mlx",
        "backend_available": backend_available,
        "status": "trained" if backend_available else "unavailable",
        "runtime": runtime,
        "reason": runtime["reason"],
        "training_implementation": (
            RASTER_TARGET_MLX_TRAINING_IMPLEMENTATION
            if backend_available
            else RASTER_TARGET_FALLBACK_TRAINING_IMPLEMENTATION
        ),
        "target_label_key": target_label_key,
        "source_corpus": str(corpus_path),
        "source_package": corpus.get("source_package"),
        "source_version": corpus.get("source_version"),
        "feature_names": list(feature_names),
        "feature_extraction": {
            "source": "input_png",
            "global_feature_count": len(RASTER_TARGET_GLOBAL_FEATURE_NAMES),
            "grid_size": training_config.grid_size,
            "grid_feature_count": training_config.grid_size * training_config.grid_size,
        },
        "target_names": target_names,
        "train_examples": len(train_examples),
        "target_summary": _target_summary(train_examples),
        "target_models": target_models,
        "training_config": {
            "epochs": training_config.epochs,
            "hidden_dim": training_config.hidden_dim,
            "learning_rate": training_config.learning_rate,
            "grid_size": training_config.grid_size,
            "allow_unavailable": training_config.allow_unavailable,
        },
    }
    if backend_available:
        model["mlx_training"] = _train_mlx_target_head(
            train_examples,
            target_names,
            feature_names,
            training_config,
        )
    model["evaluation"] = _raster_target_model_evaluation(
        examples,
        target_names,
        model,
    )

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(model, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    if markdown is not None:
        markdown_path = Path(markdown)
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(
            render_raster_target_model_markdown(model),
            encoding="utf-8",
        )
    return model


def evaluate_raster_target_model(
    model_json: str | Path,
    corpus_json: str | Path,
    *,
    output: str | Path,
    markdown: str | Path | None = None,
    splits: tuple[str, ...] | None = None,
    target_label_key: str | None = None,
    min_target_accuracy: float | None = None,
    min_exact_match_accuracy: float | None = None,
    max_unknown_expected_targets: int | None = None,
) -> dict[str, Any]:
    """Evaluate a stored raster-target model against a target corpus."""

    min_target_accuracy = _validated_optional_accuracy_gate(
        min_target_accuracy,
        "min_target_accuracy",
    )
    min_exact_match_accuracy = _validated_optional_accuracy_gate(
        min_exact_match_accuracy,
        "min_exact_match_accuracy",
    )
    max_unknown_expected_targets = _validated_optional_unknown_target_gate(
        max_unknown_expected_targets,
    )
    model_path = Path(model_json)
    model = json.loads(model_path.read_text(encoding="utf-8"))
    if model.get("model_type") != RASTER_TARGET_MODEL_TYPE:
        msg = "raster target evaluation requires a raster_target_classifier model"
        raise ValueError(msg)
    target_names = [
        str(target)
        for target in model.get("target_names", [])
        if isinstance(target, str) and target
    ]
    if not target_names:
        msg = "raster target model contains no target_names"
        raise ValueError(msg)

    corpus_path = Path(corpus_json)
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    label_key = target_label_key or str(
        model.get("target_label_key", "anchor_kind_targets")
    )
    examples = _corpus_examples(
        corpus,
        grid_size=_grid_size_from_model(model),
        target_label_key=label_key,
    )
    selected_splits = tuple(splits) if splits is not None else _available_splits(examples)
    evaluation = _raster_target_model_evaluation(
        examples,
        target_names,
        model,
        splits=selected_splits,
    )
    report = {
        "schema_version": 1,
        "model": str(model_path),
        "corpus": str(corpus_path),
        "model_type": model.get("model_type"),
        "training_implementation": model.get("training_implementation"),
        "target_label_key": label_key,
        "target_names": target_names,
        "splits": list(selected_splits),
        "feature_extraction": model.get("feature_extraction", {}),
        "evaluation": evaluation,
    }
    gate = _raster_target_evaluation_gate(
        evaluation,
        min_target_accuracy=min_target_accuracy,
        min_exact_match_accuracy=min_exact_match_accuracy,
        max_unknown_expected_targets=max_unknown_expected_targets,
    )
    if gate is not None:
        report["gate"] = gate
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
            render_raster_target_evaluation_markdown(report),
            encoding="utf-8",
        )
    return report


def render_raster_target_model_markdown(model: dict[str, Any]) -> str:
    """Render a compact training report for the raster target model."""

    lines = [
        "# Morphea Raster Target Model",
        "",
        f"- Model type: `{model.get('model_type', 'n/a')}`",
        f"- Status: `{model.get('status', 'n/a')}`",
        f"- Backend: `{model.get('backend', 'n/a')}`",
        f"- Backend available: `{str(model.get('backend_available', False)).lower()}`",
        f"- Training implementation: `{model.get('training_implementation', 'n/a')}`",
        f"- Source corpus: `{model.get('source_corpus', 'n/a')}`",
        f"- Train examples: {_fmt_value(model.get('train_examples'))}",
        f"- Targets: {_fmt_value(len(model.get('target_names', [])))}",
        "",
    ]
    mlx_training = model.get("mlx_training")
    if isinstance(mlx_training, dict):
        lines.extend(
            [
                "## MLX Training",
                "",
                f"- Weight format: `{mlx_training.get('weight_format', 'n/a')}`",
                f"- Training runtime: `{mlx_training.get('training_runtime', 'n/a')}`",
                f"- Parameters: {_fmt_value(mlx_training.get('parameter_count'))}",
                f"- Epochs: {_fmt_value(mlx_training.get('epochs'))}",
                f"- Final loss: {_fmt_value(_final_history_value(mlx_training, 'loss'))}",
                f"- Final target accuracy: {_fmt_value(_final_history_value(mlx_training, 'target_accuracy'))}",
                f"- Final exact match: {_fmt_value(_final_history_value(mlx_training, 'exact_match_accuracy'))}",
                "",
            ]
        )
    lines.extend(
        [
            "## Targets",
            "",
            "| Target | Positives | Negatives |",
            "| --- | ---: | ---: |",
        ]
    )
    target_models = model.get("target_models", {})
    if isinstance(target_models, dict):
        for target, item in sorted(target_models.items()):
            if not isinstance(item, dict):
                continue
            lines.append(
                "| "
                f"`{target}` | "
                f"{_fmt_value(item.get('positive_examples'))} | "
                f"{_fmt_value(item.get('negative_examples'))} |"
            )
    lines.extend(
        [
            "",
            "## Evaluation",
            "",
            "| Split | Examples | Target accuracy | Exact match |",
            "| --- | ---: | ---: | ---: |",
        ]
    )
    evaluation = model.get("evaluation", {})
    if isinstance(evaluation, dict):
        for split, item in sorted(evaluation.items()):
            if not isinstance(item, dict):
                continue
            lines.append(
                "| "
                f"`{split}` | "
                f"{_fmt_value(item.get('example_count'))} | "
                f"{_fmt_value(item.get('target_accuracy'))} | "
                f"{_fmt_value(item.get('exact_match_accuracy'))} |"
            )
    return "\n".join(lines).rstrip() + "\n"


def render_raster_target_evaluation_markdown(report: dict[str, Any]) -> str:
    """Render a scan-friendly raster-target evaluation report."""

    lines = [
        "# Morphea Raster Target Evaluation",
        "",
        f"- Model: `{report.get('model', 'n/a')}`",
        f"- Corpus: `{report.get('corpus', 'n/a')}`",
        f"- Model type: `{report.get('model_type', 'n/a')}`",
        f"- Training implementation: `{report.get('training_implementation', 'n/a')}`",
        f"- Target label key: `{report.get('target_label_key', 'n/a')}`",
        f"- Targets: {_fmt_value(len(report.get('target_names', [])))}",
        "",
        "## Splits",
        "",
        "| Split | Examples | Target accuracy | Exact match | Unknown expected |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    evaluation = report.get("evaluation", {})
    if isinstance(evaluation, dict):
        for split, item in sorted(evaluation.items()):
            if not isinstance(item, dict):
                continue
            lines.append(
                "| "
                f"`{split}` | "
                f"{_fmt_value(item.get('example_count'))} | "
                f"{_fmt_value(item.get('target_accuracy'))} | "
                f"{_fmt_value(item.get('exact_match_accuracy'))} | "
                f"{_fmt_value(item.get('unknown_expected_target_count'))} |"
            )
    gate = report.get("gate")
    if isinstance(gate, dict):
        lines.extend(
            [
                "",
                "## Gate",
                "",
                f"- Decision: `{gate.get('decision', 'n/a')}`",
                f"- Accepted: `{gate.get('accepted', False)}`",
                f"- Reasons: {_fmt_reason_list(gate.get('reasons', []))}",
                "",
                "| Gate | Value |",
                "| --- | ---: |",
            ]
        )
        gates = gate.get("gates", {})
        if isinstance(gates, dict):
            for name, value in sorted(gates.items()):
                lines.append(f"| `{name}` | {_fmt_value(value)} |")
        split_results = gate.get("split_results", {})
        if isinstance(split_results, dict) and split_results:
            lines.extend(
                [
                    "",
                    "### Split Gate Results",
                    "",
                    "| Split | Decision | Reasons |",
                    "| --- | --- | --- |",
                ]
            )
            for split, result in sorted(split_results.items()):
                if not isinstance(result, dict):
                    continue
                lines.append(
                    "| "
                    f"`{split}` | "
                    f"`{result.get('decision', 'n/a')}` | "
                    f"{_fmt_reason_list(result.get('reasons', []))} |"
                )
    failures = _evaluation_failures(evaluation)
    if failures:
        lines.extend(
            [
                "",
                "## Failures",
                "",
                "| Split | Example | Expected | Predicted | Unknown expected |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        for failure in failures:
            lines.append(
                "| "
                f"`{failure['split']}` | "
                f"`{failure['id']}` | "
                f"{_fmt_targets(failure.get('expected'))} | "
                f"{_fmt_targets(failure.get('predicted'))} | "
                f"{_fmt_targets(failure.get('unknown_expected_targets'))} |"
            )
    return "\n".join(lines).rstrip() + "\n"


def _validated_optional_accuracy_gate(
    value: float | None,
    name: str,
) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        msg = f"raster target evaluation {name} must be a number between 0 and 1"
        raise ValueError(msg)
    normalized = float(value)
    if normalized < 0.0 or normalized > 1.0:
        msg = f"raster target evaluation {name} must be between 0 and 1"
        raise ValueError(msg)
    return normalized


def _validated_optional_unknown_target_gate(value: int | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        msg = (
            "raster target evaluation max_unknown_expected_targets "
            "must be a non-negative integer"
        )
        raise ValueError(msg)
    if value < 0:
        msg = (
            "raster target evaluation max_unknown_expected_targets "
            "must be non-negative"
        )
        raise ValueError(msg)
    return value


def _raster_target_evaluation_gate(
    evaluation: dict[str, Any],
    *,
    min_target_accuracy: float | None,
    min_exact_match_accuracy: float | None,
    max_unknown_expected_targets: int | None,
) -> dict[str, Any] | None:
    gates = {
        key: value
        for key, value in {
            "min_target_accuracy": min_target_accuracy,
            "min_exact_match_accuracy": min_exact_match_accuracy,
            "max_unknown_expected_targets": max_unknown_expected_targets,
        }.items()
        if value is not None
    }
    if not gates:
        return None

    reject = False
    manual_review = False
    reasons: list[str] = []
    split_results: dict[str, dict[str, Any]] = {}
    for split, split_report in sorted(evaluation.items()):
        if not isinstance(split_report, dict):
            split_report = {}
        split_reject = False
        split_manual_review = False
        split_reasons: list[str] = []
        if min_target_accuracy is not None:
            target_accuracy = split_report.get("target_accuracy")
            if not isinstance(target_accuracy, (int, float)):
                split_manual_review = True
                _append_unique_reason(split_reasons, "target_accuracy_missing")
            elif float(target_accuracy) < min_target_accuracy:
                split_reject = True
                _append_unique_reason(split_reasons, "target_accuracy_below_min")
        if min_exact_match_accuracy is not None:
            exact_match_accuracy = split_report.get("exact_match_accuracy")
            if not isinstance(exact_match_accuracy, (int, float)):
                split_manual_review = True
                _append_unique_reason(split_reasons, "exact_match_accuracy_missing")
            elif float(exact_match_accuracy) < min_exact_match_accuracy:
                split_reject = True
                _append_unique_reason(split_reasons, "exact_match_accuracy_below_min")
        if max_unknown_expected_targets is not None:
            unknown_count = split_report.get("unknown_expected_target_count")
            if not isinstance(unknown_count, int):
                split_manual_review = True
                _append_unique_reason(
                    split_reasons,
                    "unknown_expected_targets_missing",
                )
            elif unknown_count > max_unknown_expected_targets:
                split_reject = True
                _append_unique_reason(
                    split_reasons,
                    "unknown_expected_targets_above_max",
                )
        if split_reject:
            split_decision = "reject"
            reject = True
        elif split_manual_review:
            split_decision = "manual_review"
            manual_review = True
        else:
            split_decision = "accept"
        for reason in split_reasons:
            _append_unique_reason(reasons, reason)
        split_results[str(split)] = {
            "decision": split_decision,
            "accepted": split_decision == "accept",
            "reasons": split_reasons,
            "metrics": {
                "target_accuracy": split_report.get("target_accuracy"),
                "exact_match_accuracy": split_report.get("exact_match_accuracy"),
                "unknown_expected_target_count": split_report.get(
                    "unknown_expected_target_count"
                ),
            },
        }

    if reject:
        decision = "reject"
    elif manual_review:
        decision = "manual_review"
    else:
        decision = "accept"
    return {
        "decision": decision,
        "accepted": decision == "accept",
        "reasons": reasons,
        "gates": gates,
        "split_results": split_results,
    }


def _append_unique_reason(reasons: list[str], reason: str) -> None:
    if reason not in reasons:
        reasons.append(reason)


def _corpus_examples(
    corpus: dict[str, Any],
    *,
    grid_size: int,
    target_label_key: str,
) -> list[dict[str, Any]]:
    root = Path(str(corpus.get("output_dir", ".")))
    examples = []
    for item in corpus.get("examples", []):
        if not isinstance(item, dict) or item.get("status") != "rendered":
            continue
        input_png = Path(str(item.get("input_png", "")))
        if not input_png.is_absolute():
            input_png = root / input_png
        if not input_png.exists():
            continue
        features = _image_features(input_png, grid_size=grid_size)
        target_labels = _example_target_labels(item, target_label_key)
        examples.append(
            {
                "id": str(item.get("id", "")),
                "split": str(item.get("split", "train")),
                "family": str(item.get("family", "unknown")),
                "input_png": str(input_png),
                "features": features,
                "target_labels": target_labels,
            }
        )
    return examples


def _example_target_labels(
    example: dict[str, Any],
    target_label_key: str,
) -> tuple[str, ...]:
    labels = example.get("labels", {})
    if not isinstance(labels, dict):
        return ()
    targets = labels.get(target_label_key, {})
    if not isinstance(targets, dict):
        return ()
    return tuple(
        sorted(
            str(target)
            for target, count in targets.items()
            if isinstance(count, (int, float)) and count > 0
        )
    )


def _raster_feature_names(grid_size: int) -> tuple[str, ...]:
    return (
        *RASTER_TARGET_GLOBAL_FEATURE_NAMES,
        *tuple(
            f"ink_grid_{row}_{column}"
            for row in range(grid_size)
            for column in range(grid_size)
        ),
    )


def _image_features(path: Path, *, grid_size: int) -> tuple[float, ...]:
    image = Image.open(path).convert("RGBA")
    width, height = image.size
    pixels = list(image.getdata())
    ink_values = [_pixel_ink(pixel) for pixel in pixels]
    ink_total = sum(ink_values)
    pixel_count = max(1, width * height)
    if ink_total <= 0:
        center_x = center_y = bbox_width = bbox_height = bbox_area = 0.0
    else:
        weighted_x = 0.0
        weighted_y = 0.0
        min_x = width
        min_y = height
        max_x = 0
        max_y = 0
        for index, ink in enumerate(ink_values):
            if ink <= 0:
                continue
            x = index % width
            y = index // width
            weighted_x += x * ink
            weighted_y += y * ink
            min_x = min(min_x, x)
            min_y = min(min_y, y)
            max_x = max(max_x, x)
            max_y = max(max_y, y)
        center_x = weighted_x / ink_total / max(1, width - 1)
        center_y = weighted_y / ink_total / max(1, height - 1)
        bbox_width = (max_x - min_x + 1) / width
        bbox_height = (max_y - min_y + 1) / height
        bbox_area = bbox_width * bbox_height
    aspect_ratio = bbox_width / bbox_height if bbox_height > 0 else 0.0
    return (
        ink_total / pixel_count,
        center_x,
        center_y,
        bbox_width,
        bbox_height,
        aspect_ratio,
        bbox_area,
        *_grid_ink_features(ink_values, width, height, grid_size=grid_size),
    )


def _pixel_ink(pixel: tuple[int, int, int, int]) -> float:
    red, green, blue, alpha = pixel
    darkness = 1.0 - (red + green + blue) / (3 * 255)
    return max(0.0, darkness) * (alpha / 255)


def _grid_ink_features(
    ink_values: list[float],
    width: int,
    height: int,
    *,
    grid_size: int,
) -> tuple[float, ...]:
    features = []
    for row in range(grid_size):
        y0 = int(row * height / grid_size)
        y1 = int((row + 1) * height / grid_size)
        for column in range(grid_size):
            x0 = int(column * width / grid_size)
            x1 = int((column + 1) * width / grid_size)
            total = 0.0
            count = 0
            for y in range(y0, y1):
                for x in range(x0, x1):
                    total += ink_values[y * width + x]
                    count += 1
            features.append(total / max(1, count))
    return tuple(features)


def _train_mlx_target_head(
    train_examples: list[dict[str, Any]],
    target_names: list[str],
    feature_names: tuple[str, ...],
    config: RasterTargetTrainingConfig,
) -> dict[str, Any]:
    import mlx.core as mx  # type: ignore[import-not-found]

    rows = [tuple(example["features"]) for example in train_examples]
    means, scales = _row_normalization(rows, len(feature_names))
    normalized_rows = [_normalize_row(row, means, scales) for row in rows]
    target_rows = [
        [
            1.0 if target in example["target_labels"] else 0.0
            for target in target_names
        ]
        for example in train_examples
    ]
    features = mx.array(normalized_rows)
    targets = mx.array(target_rows)
    params = {
        "hidden_weights": mx.array(
            _initial_weight_matrix(config.hidden_dim, len(feature_names))
        ),
        "hidden_bias": mx.zeros((config.hidden_dim,)),
        "output_weights": mx.array(
            _initial_weight_matrix(len(target_names), config.hidden_dim)
        ),
        "output_bias": mx.zeros((len(target_names),)),
    }
    loss_history: list[dict[str, float | int]] = []
    for epoch in range(config.epochs):
        loss, grads = mx.value_and_grad(
            lambda current: _mlx_multilabel_loss(current, features, targets, mx)
        )(params)
        params = {
            key: params[key] - config.learning_rate * grads[key]
            for key in params
        }
        mx.eval(params)
        probabilities = mx.sigmoid(_mlx_logits(params, features, mx)).tolist()
        target_values = targets.tolist()
        target_accuracy, exact_match_accuracy = _probability_accuracy(
            probabilities,
            target_values,
        )
        loss_history.append(
            {
                "epoch": epoch + 1,
                "loss": float(loss.item()),
                "target_accuracy": target_accuracy,
                "exact_match_accuracy": exact_match_accuracy,
            }
        )

    hidden_weights = _array_to_nested_floats(params["hidden_weights"])
    hidden_bias = _array_to_floats(params["hidden_bias"])
    output_weights = _array_to_nested_floats(params["output_weights"])
    output_bias = _array_to_floats(params["output_bias"])
    return {
        "weight_format": "mlx_multilabel_raster_target_head_v1",
        "architecture": "normalized_raster_feature_mlp_multilabel",
        "training_runtime": "mlx_autograd",
        "optimizer": "manual_sgd",
        "target_names": list(target_names),
        "feature_names": list(feature_names),
        "parameter_count": (
            config.hidden_dim * (len(feature_names) + 1)
            + len(target_names) * (config.hidden_dim + 1)
        ),
        "trained_examples": len(train_examples),
        "epochs": config.epochs,
        "hidden_dim": config.hidden_dim,
        "hidden_activation": "tanh",
        "learning_rate": config.learning_rate,
        "normalization": {
            "mean": list(means),
            "scale": list(scales),
        },
        "threshold": 0.5,
        "hidden_weights": hidden_weights,
        "hidden_bias": hidden_bias,
        "output_weights": output_weights,
        "output_bias": output_bias,
        "weights": output_weights,
        "bias": output_bias,
        "loss_history": loss_history,
    }


def _mlx_multilabel_loss(
    params: dict[str, Any],
    features: Any,
    targets: Any,
    mx: Any,
) -> Any:
    logits = _mlx_logits(params, features, mx)
    probabilities = mx.sigmoid(logits)
    epsilon = 1e-6
    return -mx.mean(
        targets * mx.log(probabilities + epsilon)
        + (1.0 - targets) * mx.log(1.0 - probabilities + epsilon)
    )


def _mlx_logits(params: dict[str, Any], features: Any, mx: Any) -> Any:
    hidden = mx.tanh(
        mx.matmul(features, mx.transpose(params["hidden_weights"]))
        + params["hidden_bias"]
    )
    return (
        mx.matmul(hidden, mx.transpose(params["output_weights"]))
        + params["output_bias"]
    )


def _initial_weight_matrix(rows: int, columns: int) -> list[list[float]]:
    scale = 1.0 / max(1.0, columns**0.5)
    return [
        [
            ((((row + 1) * 37 + (column + 1) * 17) % 29) - 14)
            / 14
            * 0.15
            * scale
            for column in range(columns)
        ]
        for row in range(rows)
    ]


def _probability_accuracy(
    probabilities: list[list[float]],
    expected: list[list[float]],
) -> tuple[float, float]:
    total = 0
    correct = 0
    exact = 0
    for probability_row, expected_row in zip(probabilities, expected):
        row_exact = True
        for probability, expected_value in zip(probability_row, expected_row):
            predicted = probability >= 0.5
            actual = expected_value >= 0.5
            total += 1
            if predicted == actual:
                correct += 1
            else:
                row_exact = False
        if row_exact:
            exact += 1
    return (
        correct / total if total else 0.0,
        exact / len(expected) if expected else 0.0,
    )


def _target_centroid_model(
    examples: list[dict[str, Any]],
    target: str,
    feature_count: int,
) -> dict[str, Any]:
    positive = [
        example["features"]
        for example in examples
        if target in example["target_labels"]
    ]
    negative = [
        example["features"]
        for example in examples
        if target not in example["target_labels"]
    ]
    return {
        "positive_examples": len(positive),
        "negative_examples": len(negative),
        "positive_centroid": list(_centroid(positive, feature_count)),
        "negative_centroid": (
            list(_centroid(negative, feature_count)) if negative else None
        ),
    }


def _centroid(
    rows: list[tuple[float, ...]],
    feature_count: int,
) -> tuple[float, ...]:
    if not rows:
        return tuple(0.0 for _ in range(feature_count))
    return tuple(
        sum(row[index] for row in rows) / len(rows)
        for index in range(feature_count)
    )


def _row_normalization(
    rows: list[tuple[float, ...]],
    feature_count: int,
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    means = tuple(
        sum(row[index] for row in rows) / len(rows)
        for index in range(feature_count)
    )
    variances = tuple(
        sum((row[index] - means[index]) ** 2 for row in rows) / len(rows)
        for index in range(feature_count)
    )
    scales = tuple(max(variance**0.5, 1e-6) for variance in variances)
    return means, scales


def _normalize_row(
    row: tuple[float, ...],
    means: tuple[float, ...],
    scales: tuple[float, ...],
) -> tuple[float, ...]:
    return tuple(
        (row[index] - means[index]) / scales[index]
        for index in range(len(means))
    )


def _target_summary(examples: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for example in examples:
        for target in example["target_labels"]:
            counts[target] = counts.get(target, 0) + 1
    return dict(sorted(counts.items()))


def _raster_target_model_evaluation(
    examples: list[dict[str, Any]],
    target_names: list[str],
    model: dict[str, Any],
    splits: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    eval_splits = splits if splits is not None else _available_splits(examples)
    return {
        split: _evaluate_split(
            [example for example in examples if example["split"] == split],
            target_names,
            model,
        )
        for split in eval_splits
    }


def _evaluate_split(
    examples: list[dict[str, Any]],
    target_names: list[str],
    model: dict[str, Any],
) -> dict[str, Any]:
    total_targets = len(examples) * len(target_names)
    correct_targets = 0
    exact_matches = 0
    target_set = set(target_names)
    unknown_expected_counts: dict[str, int] = {}
    per_target = {
        target: {"examples": 0, "correct": 0}
        for target in target_names
    }
    predictions = []
    for example in examples:
        predicted = _predict_targets(example["features"], target_names, model)
        expected = set(example["target_labels"])
        unknown_expected = sorted(expected - target_set)
        for target in unknown_expected:
            unknown_expected_counts[target] = unknown_expected_counts.get(target, 0) + 1
        predictions.append(
            {
                "id": example["id"],
                "expected": sorted(expected),
                "predicted": sorted(predicted),
                "unknown_expected_targets": unknown_expected,
                "ok": predicted == expected,
            }
        )
        if predicted == expected:
            exact_matches += 1
        for target in target_names:
            expected_value = target in expected
            predicted_value = target in predicted
            per_target[target]["examples"] += 1
            if expected_value == predicted_value:
                correct_targets += 1
                per_target[target]["correct"] += 1
    return {
        "example_count": len(examples),
        "target_count": len(target_names),
        "target_accuracy": (
            correct_targets / total_targets if total_targets else None
        ),
        "exact_match_accuracy": (
            exact_matches / len(examples) if examples else None
        ),
        "per_target": {
            target: {
                **item,
                "accuracy": (
                    item["correct"] / item["examples"]
                    if item["examples"]
                    else None
                ),
            }
            for target, item in sorted(per_target.items())
        },
        "unknown_expected_target_count": sum(unknown_expected_counts.values()),
        "unknown_expected_targets": dict(sorted(unknown_expected_counts.items())),
        "predictions": predictions,
    }


def _available_splits(examples: list[dict[str, Any]]) -> tuple[str, ...]:
    return tuple(sorted({example["split"] for example in examples}))


def _grid_size_from_model(model: dict[str, Any]) -> int:
    feature_extraction = model.get("feature_extraction", {})
    if isinstance(feature_extraction, dict):
        grid_size = feature_extraction.get("grid_size")
        if isinstance(grid_size, int) and grid_size > 0:
            return grid_size
    return RASTER_TARGET_DEFAULT_GRID_SIZE


def _evaluation_failures(evaluation: object) -> list[dict[str, Any]]:
    if not isinstance(evaluation, dict):
        return []
    failures = []
    for split, split_report in sorted(evaluation.items()):
        if not isinstance(split_report, dict):
            continue
        predictions = split_report.get("predictions", [])
        if not isinstance(predictions, list):
            continue
        for prediction in predictions:
            if not isinstance(prediction, dict) or prediction.get("ok", False):
                continue
            failures.append({"split": str(split), **prediction})
    return failures


def _fmt_targets(value: object) -> str:
    if not isinstance(value, list) or not value:
        return "n/a"
    return ", ".join(f"`{item}`" for item in value)


def _fmt_reason_list(value: object) -> str:
    if not isinstance(value, list) or not value:
        return "n/a"
    return ", ".join(f"`{item}`" for item in value)


def _predict_targets(
    features: tuple[float, ...],
    target_names: list[str],
    model: dict[str, Any],
) -> set[str]:
    mlx_training = model.get("mlx_training")
    if isinstance(mlx_training, dict):
        return _predict_mlx_targets(features, target_names, mlx_training)
    target_models = model.get("target_models", {})
    if not isinstance(target_models, dict):
        return set()
    return _predict_centroid_targets(features, target_names, target_models)


def _predict_mlx_targets(
    features: tuple[float, ...],
    target_names: list[str],
    head: dict[str, Any],
) -> set[str]:
    normalization = head.get("normalization", {})
    if not isinstance(normalization, dict):
        return set()
    mean = normalization.get("mean", [])
    scale = normalization.get("scale", [])
    hidden_weights = head.get("hidden_weights")
    hidden_bias = head.get("hidden_bias")
    weights = head.get("output_weights", head.get("weights", []))
    bias = head.get("output_bias", head.get("bias", []))
    threshold = float(head.get("threshold", 0.5))
    normalized = []
    for feature_index, feature in enumerate(features):
        feature_mean = float(mean[feature_index]) if feature_index < len(mean) else 0.0
        feature_scale = float(scale[feature_index]) if feature_index < len(scale) else 1.0
        normalized.append((feature - feature_mean) / max(feature_scale, 1e-6))
    if isinstance(hidden_weights, list) and isinstance(hidden_bias, list):
        encoded = []
        for hidden_index, hidden_row in enumerate(hidden_weights):
            if not isinstance(hidden_row, list):
                continue
            logit = (
                float(hidden_bias[hidden_index])
                if hidden_index < len(hidden_bias)
                else 0.0
            )
            for feature_index, weight in enumerate(hidden_row):
                if feature_index >= len(normalized):
                    continue
                logit += float(weight) * normalized[feature_index]
            encoded.append(tanh(logit))
    else:
        encoded = normalized
    predicted = set()
    for target_index, target in enumerate(target_names):
        if target_index >= len(weights) or target_index >= len(bias):
            continue
        row = weights[target_index]
        if not isinstance(row, list):
            continue
        logit = float(bias[target_index])
        for feature_index, weight in enumerate(row):
            if feature_index >= len(encoded):
                continue
            logit += float(weight) * encoded[feature_index]
        if _sigmoid(logit) >= threshold:
            predicted.add(target)
    return predicted


def _predict_centroid_targets(
    features: tuple[float, ...],
    target_names: list[str],
    target_models: dict[str, Any],
) -> set[str]:
    predicted = set()
    for target in target_names:
        model = target_models[target]
        positive_distance = _distance(features, model.get("positive_centroid"))
        negative_centroid = model.get("negative_centroid")
        if negative_centroid is None:
            predicted.add(target)
            continue
        negative_distance = _distance(features, negative_centroid)
        if positive_distance <= negative_distance:
            predicted.add(target)
    return predicted


def _distance(
    features: tuple[float, ...],
    centroid: object,
) -> float:
    if not isinstance(centroid, list):
        return float("inf")
    return sqrt(
        sum(
            (features[index] - float(centroid[index])) ** 2
            for index in range(min(len(features), len(centroid)))
        )
    )


def _sigmoid(value: float) -> float:
    if value >= 0:
        return 1.0 / (1.0 + exp(-value))
    magnitude = exp(value)
    return magnitude / (1.0 + magnitude)


def _array_to_floats(values: Any) -> list[float]:
    return [float(value) for value in values.tolist()]


def _array_to_nested_floats(values: Any) -> list[list[float]]:
    return [
        [float(value) for value in row]
        for row in values.tolist()
    ]


def _fmt_value(value: object) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def _final_history_value(training: dict[str, Any], key: str) -> object:
    history = training.get("loss_history")
    if not isinstance(history, list) or not history:
        return None
    last = history[-1]
    if not isinstance(last, dict):
        return None
    return last.get(key)
