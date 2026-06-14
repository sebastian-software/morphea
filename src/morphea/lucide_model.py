"""Lucide corpus adapter for the generic raster-target model."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from morphea.raster_target_model import (
    RASTER_TARGET_FALLBACK_TRAINING_IMPLEMENTATION,
    RASTER_TARGET_MLX_TRAINING_IMPLEMENTATION,
    RASTER_TARGET_MODEL_TYPE,
    RASTER_TARGET_TRAINING_IMPLEMENTATION,
    RasterTargetTrainingConfig,
    is_raster_target_mlx_available,
    raster_target_runtime_status,
    render_raster_target_model_markdown,
    train_raster_target_model,
)


LUCIDE_TARGET_LABEL_KEY = "anchor_kind_targets"
LUCIDE_TARGET_MODEL_TYPE = RASTER_TARGET_MODEL_TYPE
LUCIDE_TARGET_MLX_TRAINING_IMPLEMENTATION = RASTER_TARGET_MLX_TRAINING_IMPLEMENTATION
LUCIDE_TARGET_FALLBACK_TRAINING_IMPLEMENTATION = (
    RASTER_TARGET_FALLBACK_TRAINING_IMPLEMENTATION
)
LUCIDE_TARGET_TRAINING_IMPLEMENTATION = RASTER_TARGET_TRAINING_IMPLEMENTATION
LucideTargetTrainingConfig = RasterTargetTrainingConfig
is_lucide_mlx_available = is_raster_target_mlx_available
lucide_target_runtime_status = raster_target_runtime_status
render_lucide_target_model_markdown = render_raster_target_model_markdown


def train_lucide_target_model(
    corpus_json: str | Path,
    *,
    output: str | Path,
    markdown: str | Path | None = None,
    config: RasterTargetTrainingConfig | None = None,
) -> dict[str, Any]:
    """Train the generic raster-target model from a Lucide corpus manifest."""

    return train_raster_target_model(
        corpus_json,
        output=output,
        markdown=markdown,
        config=config,
        target_label_key=LUCIDE_TARGET_LABEL_KEY,
    )
