"""Shared diagnostic classification helpers."""

from __future__ import annotations


CANONICAL_DIAGNOSTIC_STAGES = (
    "preprocessing",
    "palette",
    "segmentation",
    "fitting",
    "cleanup",
    "scoring",
    "export",
    "runtime",
    "unknown",
)


def diagnostic_stage_counts(diagnostics: object) -> dict[str, int]:
    counts: dict[str, int] = {}
    for diagnostic in diagnostics:
        if not isinstance(diagnostic, dict):
            continue
        explicit_stage = diagnostic.get("stage")
        if isinstance(explicit_stage, str):
            stage = normalise_diagnostic_stage(explicit_stage)
        else:
            stage = diagnostic_stage(str(diagnostic.get("code", "unknown")))
        counts[stage] = counts.get(stage, 0) + 1
    return dict(sorted(counts.items()))


def normalise_diagnostic_stage(stage: str) -> str:
    normalized = stage.strip().lower().replace("-", "_")
    if normalized in CANONICAL_DIAGNOSTIC_STAGES:
        return normalized
    return "unknown"


def diagnostic_stage(code: str) -> str:
    code = code.strip().lower()
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
    if code.startswith("fit_") or code.endswith("_fit_failed"):
        return "fitting"
    if code.startswith("cleanup_") or code.startswith("merge_"):
        return "cleanup"
    if code.startswith("score_") or code.startswith("gate_"):
        return "scoring"
    if code.startswith("export_") or code.endswith("_export_failed"):
        return "export"
    if code == "timeout_reached":
        return "runtime"
    return "unknown"
