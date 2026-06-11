"""Structure-preserving refinement interface and local baseline backend."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from time import monotonic

from PIL import Image

from curve.rendering import raster_fidelity_metrics, render_manifest_image


@dataclass(frozen=True)
class RefinementConfig:
    backend: str = "local_metric"
    max_iterations: int = 0
    timeout_seconds: float | None = None
    source_image: str | Path | None = None


def refine_manifest(
    *,
    manifest: str | Path,
    output: str | Path,
    config: RefinementConfig | None = None,
) -> dict[str, object]:
    config = config or RefinementConfig()
    if config.backend != "local_metric":
        msg = f"unsupported refinement backend: {config.backend}"
        raise ValueError(msg)

    data = json.loads(Path(manifest).read_text(encoding="utf-8"))
    started_at = monotonic()
    optimized_data = dict(data)
    optimizer_metrics: dict[str, object] = {
        "attempted": False,
        "iterations": 0,
        "initial_raster_l1_error": None,
        "final_raster_l1_error": None,
        "timeout_reached": False,
    }
    if config.source_image is not None and config.max_iterations > 0:
        optimized_data, optimizer_metrics = _optimize_circle_radii(
            data,
            source_image=Path(config.source_image),
            max_iterations=config.max_iterations,
            started_at=started_at,
            timeout_seconds=config.timeout_seconds,
        )

    refined_anchors = []
    for anchor in optimized_data.get("anchors", []):
        refined = dict(anchor)
        metrics = dict(refined.get("metrics", {}))
        metrics["refinement_structure_preserved"] = 1.0
        metrics["refinement_iterations"] = float(
            optimizer_metrics["iterations"]
            if optimizer_metrics["attempted"]
            else config.max_iterations
        )
        refined["metrics"] = metrics
        refined_anchors.append(refined)

    result = dict(optimized_data)
    result["anchors"] = refined_anchors
    result["refinement"] = {
        "backend": config.backend,
        "max_iterations": config.max_iterations,
        "timeout_seconds": config.timeout_seconds,
        "source_image": (
            str(config.source_image) if config.source_image is not None else None
        ),
        "structure_preserving": True,
        "optimizer": optimizer_metrics,
    }
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    return result


def _optimize_circle_radii(
    data: dict[str, object],
    *,
    source_image: Path,
    max_iterations: int,
    started_at: float,
    timeout_seconds: float | None,
) -> tuple[dict[str, object], dict[str, object]]:
    result = deepcopy(data)
    if not source_image.exists():
        msg = f"refinement source image does not exist: {source_image}"
        raise FileNotFoundError(msg)

    with Image.open(source_image) as source:
        current_error = _manifest_l1_error(result, source)
        initial_error = current_error
        iterations = 0
        timeout_reached = False
        for _ in range(max_iterations):
            if _deadline_exceeded(started_at, timeout_seconds):
                timeout_reached = True
                break
            improved = False
            for anchor in result.get("anchors", []):
                if not isinstance(anchor, dict) or anchor.get("kind") != "circle":
                    continue
                circle = anchor.get("circle")
                if not isinstance(circle, dict):
                    continue
                base_radius = float(circle.get("r", 0.0))
                best_radius = base_radius
                best_error = current_error
                for delta in (-1.0, 1.0):
                    candidate_radius = max(0.5, base_radius + delta)
                    candidate = _with_circle_radius(result, anchor, candidate_radius)
                    candidate_error = _manifest_l1_error(candidate, source)
                    if candidate_error < best_error:
                        best_error = candidate_error
                        best_radius = candidate_radius
                if best_error < current_error:
                    old_radius = float(circle.get("r", best_radius))
                    circle["r"] = best_radius
                    metrics = dict(anchor.get("metrics", {}))
                    metrics["refinement_radius_delta"] = (
                        metrics.get("refinement_radius_delta", 0.0)
                        + best_radius
                        - old_radius
                    )
                    anchor["metrics"] = metrics
                    current_error = best_error
                    improved = True
            iterations += 1
            if not improved:
                break

    metrics = dict(result.get("metrics", {}))
    metrics["raster_l1_error"] = current_error
    result["metrics"] = metrics
    return result, {
        "attempted": True,
        "iterations": iterations,
        "initial_raster_l1_error": initial_error,
        "final_raster_l1_error": current_error,
        "timeout_reached": timeout_reached,
    }


def _manifest_l1_error(manifest: dict[str, object], source: Image.Image) -> float:
    rendered = render_manifest_image(manifest)
    metrics = raster_fidelity_metrics(source=source, rendered=rendered)
    return float(metrics["raster_l1_error"])


def _with_circle_radius(
    manifest: dict[str, object],
    anchor: dict[str, object],
    radius: float,
) -> dict[str, object]:
    candidate = dict(manifest)
    candidate_anchors = []
    for candidate_anchor in manifest.get("anchors", []):
        if candidate_anchor is anchor:
            changed = dict(anchor)
            circle = dict(changed.get("circle", {}))
            circle["r"] = radius
            changed["circle"] = circle
            candidate_anchors.append(changed)
        else:
            candidate_anchors.append(candidate_anchor)
    candidate["anchors"] = candidate_anchors
    return candidate


def _deadline_exceeded(started_at: float, timeout_seconds: float | None) -> bool:
    return timeout_seconds is not None and monotonic() - started_at >= timeout_seconds
