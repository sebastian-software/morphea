"""Shared diagnostic classification helpers."""

from __future__ import annotations


def diagnostic_stage_counts(diagnostics: object) -> dict[str, int]:
    counts: dict[str, int] = {}
    for diagnostic in diagnostics:
        if not isinstance(diagnostic, dict):
            continue
        stage = diagnostic_stage(str(diagnostic.get("code", "unknown")))
        counts[stage] = counts.get(stage, 0) + 1
    return dict(sorted(counts.items()))


def diagnostic_stage(code: str) -> str:
    if code in {
        "transparent_pixels_ignored",
        "partial_alpha_flattened",
        "image_resized_for_analysis",
    }:
        return "preprocessing"
    if code == "palette_quantized":
        return "palette"
    if code in {"color_mask_split_for_components", "component_deferred"}:
        return "segmentation"
    if code == "timeout_reached":
        return "runtime"
    return "unknown"
