"""Structure-preserving refinement interface and local baseline backend."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from time import monotonic

from PIL import Image

from curve.rendering import raster_fidelity_metrics, render_manifest_image


LOCAL_REFINEMENT_BACKEND = "local_metric"
OPTIONAL_DIFFERENTIABLE_BACKENDS = ("differentiable", "diffvg")


@dataclass(frozen=True)
class RefinementConfig:
    backend: str = LOCAL_REFINEMENT_BACKEND
    max_iterations: int = 0
    timeout_seconds: float | None = None
    source_image: str | Path | None = None
    raster_l1_weight: float = 1.0
    raster_edge_weight: float = 0.25


def refine_manifest(
    *,
    manifest: str | Path,
    output: str | Path,
    config: RefinementConfig | None = None,
) -> dict[str, object]:
    config = config or RefinementConfig()
    if config.backend in OPTIONAL_DIFFERENTIABLE_BACKENDS:
        _raise_differentiable_backend_unavailable(config.backend)
    if config.backend != LOCAL_REFINEMENT_BACKEND:
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
        optimized_data, optimizer_metrics = _optimize_local_geometry(
            data,
            source_image=Path(config.source_image),
            max_iterations=config.max_iterations,
            started_at=started_at,
            timeout_seconds=config.timeout_seconds,
            raster_l1_weight=config.raster_l1_weight,
            raster_edge_weight=config.raster_edge_weight,
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
        "raster_l1_weight": config.raster_l1_weight,
        "raster_edge_weight": config.raster_edge_weight,
        "structure_preserving": True,
        "optimizer": optimizer_metrics,
    }
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    return result


def available_refinement_backends() -> dict[str, object]:
    return {
        "local": [LOCAL_REFINEMENT_BACKEND],
        "optional": list(OPTIONAL_DIFFERENTIABLE_BACKENDS),
    }


def _raise_differentiable_backend_unavailable(backend: str) -> None:
    msg = (
        f"refinement backend {backend!r} is not installed/configured yet; "
        "install and wire a differentiable renderer before using this backend"
    )
    raise RuntimeError(msg)


def _optimize_local_geometry(
    data: dict[str, object],
    *,
    source_image: Path,
    max_iterations: int,
    started_at: float,
    timeout_seconds: float | None,
    raster_l1_weight: float,
    raster_edge_weight: float,
) -> tuple[dict[str, object], dict[str, object]]:
    result = deepcopy(data)
    if not source_image.exists():
        msg = f"refinement source image does not exist: {source_image}"
        raise FileNotFoundError(msg)

    with Image.open(source_image) as source:
        current_metrics = _manifest_raster_metrics(
            result,
            source,
            raster_l1_weight=raster_l1_weight,
            raster_edge_weight=raster_edge_weight,
        )
        current_error = current_metrics["objective"]
        initial_metrics = current_metrics
        iterations = 0
        timeout_reached = False
        optimized_kinds: set[str] = set()
        for _ in range(max_iterations):
            if _deadline_exceeded(started_at, timeout_seconds):
                timeout_reached = True
                break
            improved = False
            for anchor in result.get("anchors", []):
                if not isinstance(anchor, dict):
                    continue
                kind = str(anchor.get("kind"))
                best_error = current_error
                if kind == "circle":
                    circle = anchor.get("circle")
                    if not isinstance(circle, dict):
                        continue
                    base_radius = float(circle.get("r", 0.0))
                    best_radius = base_radius
                    for delta in (-1.0, 1.0):
                        candidate_radius = max(0.5, base_radius + delta)
                        candidate = _with_circle_radius(
                            result,
                            anchor,
                            candidate_radius,
                        )
                        candidate_error = _manifest_objective(
                            candidate,
                            source,
                            raster_l1_weight=raster_l1_weight,
                            raster_edge_weight=raster_edge_weight,
                        )
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
                        current_metrics = _manifest_raster_metrics(
                            result,
                            source,
                            raster_l1_weight=raster_l1_weight,
                            raster_edge_weight=raster_edge_weight,
                        )
                        optimized_kinds.add(kind)
                        improved = True
                    continue

                if kind not in {"rect", "rounded_rect", "quad"}:
                    continue
                base_corners = _quad_corners(anchor)
                if base_corners is None:
                    continue
                best_corners = base_corners
                for candidate_corners in _quad_corner_variants(base_corners):
                    candidate = _with_quad_corners(
                        result,
                        anchor,
                        candidate_corners,
                    )
                    candidate_error = _manifest_objective(
                        candidate,
                        source,
                        raster_l1_weight=raster_l1_weight,
                        raster_edge_weight=raster_edge_weight,
                    )
                    if candidate_error < best_error:
                        best_error = candidate_error
                        best_corners = candidate_corners
                if best_error < current_error:
                    quad = anchor.get("quad")
                    if not isinstance(quad, dict):
                        continue
                    quad["corners"] = _manifest_corners(best_corners)
                    metrics = dict(anchor.get("metrics", {}))
                    metrics["refinement_quad_corner_delta"] = (
                        metrics.get("refinement_quad_corner_delta", 0.0)
                        + _corner_delta(base_corners, best_corners)
                    )
                    anchor["metrics"] = metrics
                    current_error = best_error
                    current_metrics = _manifest_raster_metrics(
                        result,
                        source,
                        raster_l1_weight=raster_l1_weight,
                        raster_edge_weight=raster_edge_weight,
                    )
                    optimized_kinds.add(kind)
                    improved = True
            iterations += 1
            if not improved:
                break

    metrics = dict(result.get("metrics", {}))
    metrics["raster_l1_error"] = current_metrics["raster_l1_error"]
    metrics["raster_edge_error"] = current_metrics["raster_edge_error"]
    metrics["refinement_objective"] = current_metrics["objective"]
    result["metrics"] = metrics
    return result, {
        "attempted": True,
        "iterations": iterations,
        "objective": "weighted_raster_l1_plus_edge",
        "initial_raster_l1_error": initial_metrics["raster_l1_error"],
        "final_raster_l1_error": current_metrics["raster_l1_error"],
        "initial_raster_edge_error": initial_metrics["raster_edge_error"],
        "final_raster_edge_error": current_metrics["raster_edge_error"],
        "initial_objective": initial_metrics["objective"],
        "final_objective": current_metrics["objective"],
        "optimized_parameter_kinds": sorted(optimized_kinds),
        "timeout_reached": timeout_reached,
    }


def _manifest_raster_metrics(
    manifest: dict[str, object],
    source: Image.Image,
    *,
    raster_l1_weight: float,
    raster_edge_weight: float,
) -> dict[str, float]:
    rendered = render_manifest_image(manifest)
    metrics = raster_fidelity_metrics(source=source, rendered=rendered)
    l1_error = float(metrics["raster_l1_error"])
    edge_error = float(metrics["raster_edge_error"])
    return {
        "raster_l1_error": l1_error,
        "raster_edge_error": edge_error,
        "objective": (l1_error * raster_l1_weight) + (edge_error * raster_edge_weight),
    }


def _manifest_objective(
    manifest: dict[str, object],
    source: Image.Image,
    *,
    raster_l1_weight: float,
    raster_edge_weight: float,
) -> float:
    return _manifest_raster_metrics(
        manifest,
        source,
        raster_l1_weight=raster_l1_weight,
        raster_edge_weight=raster_edge_weight,
    )["objective"]


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


def _with_quad_corners(
    manifest: dict[str, object],
    anchor: dict[str, object],
    corners: tuple[tuple[float, float], ...],
) -> dict[str, object]:
    candidate = dict(manifest)
    candidate_anchors = []
    for candidate_anchor in manifest.get("anchors", []):
        if candidate_anchor is anchor:
            changed = dict(anchor)
            quad = dict(changed.get("quad", {}))
            quad["corners"] = _manifest_corners(corners)
            changed["quad"] = quad
            candidate_anchors.append(changed)
        else:
            candidate_anchors.append(candidate_anchor)
    candidate["anchors"] = candidate_anchors
    return candidate


def _quad_corners(anchor: dict[str, object]) -> tuple[tuple[float, float], ...] | None:
    quad = anchor.get("quad")
    if not isinstance(quad, dict):
        return None
    corners = quad.get("corners")
    if not isinstance(corners, list) or len(corners) != 4:
        return None
    parsed = []
    for point in corners:
        if not isinstance(point, dict):
            return None
        parsed.append((float(point.get("x", 0.0)), float(point.get("y", 0.0))))
    return tuple(parsed)


def _quad_corner_variants(
    corners: tuple[tuple[float, float], ...],
) -> tuple[tuple[tuple[float, float], ...], ...]:
    cx = sum(point[0] for point in corners) / len(corners)
    cy = sum(point[1] for point in corners) / len(corners)
    half_extent = max(
        max(abs(point[0] - cx) for point in corners),
        max(abs(point[1] - cy) for point in corners),
        1.0,
    )
    variants = []
    for dx, dy in ((-1.0, 0.0), (1.0, 0.0), (0.0, -1.0), (0.0, 1.0)):
        variants.append(tuple((x + dx, y + dy) for x, y in corners))
    for delta in (-1.0, 1.0):
        scale = max(0.1, 1.0 + (delta / half_extent))
        variants.append(
            tuple((cx + ((x - cx) * scale), cy + ((y - cy) * scale)) for x, y in corners)
        )
    return tuple(variants)


def _manifest_corners(
    corners: tuple[tuple[float, float], ...],
) -> list[dict[str, float]]:
    return [{"x": x, "y": y} for x, y in corners]


def _corner_delta(
    before: tuple[tuple[float, float], ...],
    after: tuple[tuple[float, float], ...],
) -> float:
    return sum(
        ((after_x - before_x) ** 2 + (after_y - before_y) ** 2) ** 0.5
        for (before_x, before_y), (after_x, after_y) in zip(before, after, strict=True)
    )


def _deadline_exceeded(started_at: float, timeout_seconds: float | None) -> bool:
    return timeout_seconds is not None and monotonic() - started_at >= timeout_seconds
