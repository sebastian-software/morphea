"""Structure-preserving refinement interface and local baseline backend."""

from __future__ import annotations

import importlib.util
import json
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from time import monotonic

from PIL import Image

from morphea.rendering import raster_fidelity_metrics, render_manifest_image


LOCAL_REFINEMENT_BACKEND = "local_metric"
DIFFERENTIABLE_REFINEMENT_BACKEND = "differentiable"
OPTIONAL_DIFFERENTIABLE_BACKENDS = ("diffvg",)
OPTIONAL_REFINEMENT_BACKEND_PACKAGES = {
    "diffvg": ("pydiffvg", "diffvg"),
}


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
    _validate_refinement_config(config)
    if config.backend in OPTIONAL_DIFFERENTIABLE_BACKENDS:
        _raise_differentiable_backend_unavailable(config.backend)
    if config.backend not in {
        LOCAL_REFINEMENT_BACKEND,
        DIFFERENTIABLE_REFINEMENT_BACKEND,
    }:
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
        "stopped_reason": "not_attempted",
    }
    if config.source_image is not None and config.max_iterations > 0:
        optimizer = (
            _optimize_differentiable_geometry
            if config.backend == DIFFERENTIABLE_REFINEMENT_BACKEND
            else _optimize_local_geometry
        )
        optimized_data, optimizer_metrics = optimizer(
            data,
            source_image=Path(config.source_image),
            max_iterations=config.max_iterations,
            started_at=started_at,
            timeout_seconds=config.timeout_seconds,
            raster_l1_weight=config.raster_l1_weight,
            raster_edge_weight=config.raster_edge_weight,
        )

    source_anchors = list(data.get("anchors", []))
    optimized_anchors = list(optimized_data.get("anchors", []))
    structure_audit = _refinement_structure_audit(source_anchors, optimized_anchors)
    optimizer_metrics = dict(optimizer_metrics)
    optimizer_metrics["elapsed_seconds"] = round(monotonic() - started_at, 6)
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
        "structure_audit": structure_audit,
        "optimizer": optimizer_metrics,
    }
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    return result


def gate_refinement_result(
    *,
    refined_manifest: str | Path,
    output: str | Path,
    markdown: str | Path | None = None,
    max_objective_regression: float = 0.0,
    require_improvement: bool = True,
) -> dict[str, object]:
    data = json.loads(Path(refined_manifest).read_text(encoding="utf-8"))
    refinement = data.get("refinement", {})
    if not isinstance(refinement, dict):
        refinement = {}
    structure_audit = refinement.get("structure_audit", {})
    if not isinstance(structure_audit, dict):
        structure_audit = {}
    optimizer = refinement.get("optimizer", {})
    if not isinstance(optimizer, dict):
        optimizer = {}

    reasons: list[str] = []
    reject = False
    manual_review = False

    if not structure_audit.get("structure_preserved", False):
        reject = True
        reasons.append("structure_not_preserved")
    if not structure_audit.get("editability_preserved", False):
        reject = True
        reasons.append("editability_not_preserved")

    initial_objective = optimizer.get("initial_objective")
    final_objective = optimizer.get("final_objective")
    objective_delta = None
    if isinstance(initial_objective, (int, float)) and isinstance(
        final_objective,
        (int, float),
    ):
        objective_delta = float(final_objective) - float(initial_objective)
        if objective_delta > max_objective_regression:
            reject = True
            reasons.append("objective_regressed")
        elif require_improvement and objective_delta >= 0:
            manual_review = True
            reasons.append("objective_not_improved")
    else:
        manual_review = True
        reasons.append("missing_objective_metrics")

    if not optimizer.get("attempted", False):
        manual_review = True
        reasons.append("optimizer_not_attempted")
    if optimizer.get("timeout_reached", False):
        manual_review = True
        reasons.append("optimizer_timeout")

    if reject:
        decision = "reject"
    elif manual_review:
        decision = "manual_review"
    else:
        decision = "accept"

    result = {
        "schema_version": 1,
        "refined_manifest": str(refined_manifest),
        "decision": decision,
        "accepted": decision == "accept",
        "reasons": reasons,
        "gates": {
            "max_objective_regression": max_objective_regression,
            "require_improvement": require_improvement,
        },
        "structure_audit": structure_audit,
        "optimizer": {
            "attempted": optimizer.get("attempted", False),
            "timeout_reached": optimizer.get("timeout_reached", False),
            "stopped_reason": optimizer.get("stopped_reason"),
            "initial_objective": initial_objective,
            "final_objective": final_objective,
            "objective_delta": objective_delta,
            "initial_raster_l1_error": optimizer.get("initial_raster_l1_error"),
            "final_raster_l1_error": optimizer.get("final_raster_l1_error"),
            "initial_raster_edge_error": optimizer.get("initial_raster_edge_error"),
            "final_raster_edge_error": optimizer.get("final_raster_edge_error"),
        },
    }
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    if markdown is not None:
        markdown_path = Path(markdown)
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(render_refinement_gate_markdown(result), encoding="utf-8")
    return result


def render_refinement_gate_markdown(result: dict[str, object]) -> str:
    gates = result.get("gates", {})
    if not isinstance(gates, dict):
        gates = {}
    optimizer = result.get("optimizer", {})
    if not isinstance(optimizer, dict):
        optimizer = {}
    structure = result.get("structure_audit", {})
    if not isinstance(structure, dict):
        structure = {}
    reasons = result.get("reasons", [])
    if not isinstance(reasons, list):
        reasons = []
    lines = [
        "# Morphēa Refinement Gate",
        "",
        f"- Decision: `{result.get('decision', 'n/a')}`",
        f"- Accepted: `{result.get('accepted', False)}`",
        f"- Refined manifest: `{result.get('refined_manifest', 'n/a')}`",
        f"- Structure preserved: `{structure.get('structure_preserved', False)}`",
        f"- Editability preserved: `{structure.get('editability_preserved', False)}`",
        f"- Initial objective: {_fmt_refinement_value(optimizer.get('initial_objective'))}",
        f"- Final objective: {_fmt_refinement_value(optimizer.get('final_objective'))}",
        f"- Objective delta: {_fmt_refinement_value(optimizer.get('objective_delta'))}",
        "",
        "## Gates",
        "",
        "| Gate | Value |",
        "| --- | ---: |",
    ]
    for key in sorted(gates):
        lines.append(f"| `{key}` | {_fmt_refinement_value(gates.get(key))} |")
    lines.extend(
        [
            "",
            "## Reasons",
            "",
            ", ".join(f"`{reason}`" for reason in reasons) if reasons else "n/a",
        ]
    )
    return "\n".join(lines) + "\n"


def _fmt_refinement_value(value: object) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return f"{value:.6g}"
    if value is None:
        return "n/a"
    return str(value)


def available_refinement_backends() -> dict[str, object]:
    return {
        "local": [LOCAL_REFINEMENT_BACKEND, DIFFERENTIABLE_REFINEMENT_BACKEND],
        "optional": list(OPTIONAL_DIFFERENTIABLE_BACKENDS),
        "details": {
            backend: refinement_backend_status(backend)
            for backend in (
                LOCAL_REFINEMENT_BACKEND,
                DIFFERENTIABLE_REFINEMENT_BACKEND,
                *OPTIONAL_DIFFERENTIABLE_BACKENDS,
            )
        },
    }


def is_optional_refinement_package_available(backend: str) -> bool:
    return any(
        importlib.util.find_spec(package) is not None
        for package in OPTIONAL_REFINEMENT_BACKEND_PACKAGES.get(backend, ())
    )


def refinement_backend_status(backend: str) -> dict[str, object]:
    if backend == LOCAL_REFINEMENT_BACKEND:
        return {
            "backend": backend,
            "backend_available": True,
            "status": "available",
            "reason": None,
            "package_available": True,
            "implementation": "local_metric",
        }
    if backend == DIFFERENTIABLE_REFINEMENT_BACKEND:
        return {
            "backend": backend,
            "backend_available": True,
            "status": "available",
            "reason": None,
            "package_available": True,
            "implementation": "soft_raster_gradient",
        }
    if backend in OPTIONAL_DIFFERENTIABLE_BACKENDS:
        package_available = is_optional_refinement_package_available(backend)
        return {
            "backend": backend,
            "backend_available": False,
            "status": "adapter_pending" if package_available else "not_installed",
            "reason": (
                "differentiable renderer adapter is not wired yet"
                if package_available
                else "differentiable renderer package is not installed"
            ),
            "package_available": package_available,
            "package_candidates": list(
                OPTIONAL_REFINEMENT_BACKEND_PACKAGES.get(backend, ())
            ),
            "implementation": None,
        }
    return {
        "backend": backend,
        "backend_available": False,
        "status": "unsupported",
        "reason": "unrecognized refinement backend",
        "package_available": False,
        "implementation": None,
    }


def _validate_refinement_config(config: RefinementConfig) -> None:
    if config.max_iterations < 0:
        raise ValueError("refinement max_iterations must be non-negative")
    if config.timeout_seconds is not None and config.timeout_seconds <= 0:
        raise ValueError("refinement timeout_seconds must be positive")
    if config.raster_l1_weight < 0 or config.raster_edge_weight < 0:
        raise ValueError("refinement raster weights must be non-negative")
    if config.raster_l1_weight == 0 and config.raster_edge_weight == 0:
        raise ValueError("at least one refinement raster weight must be positive")


def _refinement_structure_audit(
    source_anchors: list[object],
    refined_anchors: list[object],
) -> dict[str, object]:
    comparable_pairs = [
        (source, refined)
        for source, refined in zip(source_anchors, refined_anchors, strict=False)
        if isinstance(source, dict) and isinstance(refined, dict)
    ]
    preserved_kind_count = sum(
        1
        for source, refined in comparable_pairs
        if source.get("kind") == refined.get("kind")
    )
    changed_geometry_count = sum(
        1
        for source, refined in comparable_pairs
        if _anchor_geometry_payload(source) != _anchor_geometry_payload(refined)
    )
    anchor_count = len(refined_anchors)
    return {
        "source_anchor_count": len(source_anchors),
        "refined_anchor_count": anchor_count,
        "preserved_kind_count": preserved_kind_count,
        "changed_geometry_count": changed_geometry_count,
        "structure_preserved": (
            len(source_anchors) == anchor_count
            and preserved_kind_count == anchor_count
        ),
        "editability_preserved": (
            len(source_anchors) == anchor_count
            and preserved_kind_count == anchor_count
        ),
    }


def _anchor_geometry_payload(anchor: dict[str, object]) -> dict[str, object]:
    return {
        key: anchor.get(key)
        for key in ("circle", "stroke", "quad", "arc", "ellipse", "path")
        if key in anchor
    }


def _raise_differentiable_backend_unavailable(backend: str) -> None:
    status = refinement_backend_status(backend)
    msg = (
        f"refinement backend {backend!r} is not installed/configured yet; "
        f"status={status['status']}; "
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
        stopped_reason = "max_iterations"
        optimized_kinds: set[str] = set()
        for _ in range(max_iterations):
            if _deadline_exceeded(started_at, timeout_seconds):
                timeout_reached = True
                stopped_reason = "timeout"
                break
            improved = False
            for anchor in result.get("anchors", []):
                if _deadline_exceeded(started_at, timeout_seconds):
                    timeout_reached = True
                    stopped_reason = "timeout"
                    break
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
                        if _deadline_exceeded(started_at, timeout_seconds):
                            timeout_reached = True
                            stopped_reason = "timeout"
                            break
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
                    if timeout_reached:
                        break
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

                if kind in {"stroke_polyline", "stroke_path"}:
                    base_centerline = _stroke_centerline(anchor)
                    if base_centerline is None:
                        continue
                    base_widths = _stroke_width_samples(anchor)
                    best_centerline = base_centerline
                    best_widths = base_widths
                    for candidate_centerline, candidate_widths in _stroke_variants(
                        base_centerline,
                        base_widths,
                    ):
                        if _deadline_exceeded(started_at, timeout_seconds):
                            timeout_reached = True
                            stopped_reason = "timeout"
                            break
                        candidate = _with_stroke_geometry(
                            result,
                            anchor,
                            candidate_centerline,
                            candidate_widths,
                        )
                        candidate_error = _manifest_objective(
                            candidate,
                            source,
                            raster_l1_weight=raster_l1_weight,
                            raster_edge_weight=raster_edge_weight,
                        )
                        if candidate_error < best_error:
                            best_error = candidate_error
                            best_centerline = candidate_centerline
                            best_widths = candidate_widths
                    if timeout_reached:
                        break
                    if best_error < current_error:
                        stroke = anchor.get("stroke")
                        if not isinstance(stroke, dict):
                            continue
                        stroke["centerline"] = _manifest_points(best_centerline)
                        stroke["width_samples"] = list(best_widths)
                        metrics = dict(anchor.get("metrics", {}))
                        metrics["refinement_stroke_centerline_delta"] = (
                            metrics.get("refinement_stroke_centerline_delta", 0.0)
                            + _centerline_delta(base_centerline, best_centerline)
                        )
                        metrics["refinement_stroke_width_delta"] = (
                            metrics.get("refinement_stroke_width_delta", 0.0)
                            + _width_delta(base_widths, best_widths)
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
                    if _deadline_exceeded(started_at, timeout_seconds):
                        timeout_reached = True
                        stopped_reason = "timeout"
                        break
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
                if timeout_reached:
                    break
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
            if timeout_reached:
                break
            if not improved:
                stopped_reason = "converged"
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
        "stopped_reason": stopped_reason,
    }


def _optimize_differentiable_geometry(
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
        source_rgba = source.convert("RGBA")
        initial_hard_metrics = _manifest_raster_metrics(
            result,
            source_rgba,
            raster_l1_weight=raster_l1_weight,
            raster_edge_weight=raster_edge_weight,
        )
        current_metrics = _manifest_soft_raster_metrics(
            result,
            source_rgba,
            raster_l1_weight=raster_l1_weight,
            raster_edge_weight=raster_edge_weight,
        )
        initial_metrics = current_metrics
        iterations = 0
        timeout_reached = False
        stopped_reason = "max_iterations"
        optimized_kinds: set[str] = set()
        renderer_kinds = {
            str(anchor.get("kind"))
            for anchor in result.get("anchors", [])
            if isinstance(anchor, dict)
            and anchor.get("kind")
            in {
                "circle",
                "rect",
                "rounded_rect",
                "quad",
                "stroke_polyline",
                "stroke_path",
                "arc",
            }
        }
        for _ in range(max_iterations):
            if _deadline_exceeded(started_at, timeout_seconds):
                timeout_reached = True
                stopped_reason = "timeout"
                break
            improved = False
            for anchor in result.get("anchors", []):
                if _deadline_exceeded(started_at, timeout_seconds):
                    timeout_reached = True
                    stopped_reason = "timeout"
                    break
                if not isinstance(anchor, dict):
                    continue
                kind = str(anchor.get("kind"))
                if kind == "circle":
                    circle = anchor.get("circle")
                    if not isinstance(circle, dict):
                        continue
                    gradient = _soft_circle_radius_gradient(
                        result,
                        anchor,
                        source_rgba,
                        raster_l1_weight=raster_l1_weight,
                        raster_edge_weight=raster_edge_weight,
                    )
                    if abs(gradient) < 1e-6:
                        continue
                    old_radius = float(circle.get("r", 0.0))
                    candidate_radius = max(0.5, old_radius - gradient * 18.0)
                    if abs(candidate_radius - old_radius) < 1e-6:
                        continue
                    candidate = _with_circle_radius(result, anchor, candidate_radius)
                    candidate_metrics = _manifest_soft_raster_metrics(
                        candidate,
                        source_rgba,
                        raster_l1_weight=raster_l1_weight,
                        raster_edge_weight=raster_edge_weight,
                    )
                    if candidate_metrics["objective"] >= current_metrics["objective"]:
                        continue
                    circle["r"] = candidate_radius
                    metrics = dict(anchor.get("metrics", {}))
                    metrics["refinement_radius_delta"] = (
                        metrics.get("refinement_radius_delta", 0.0)
                        + candidate_radius
                        - old_radius
                    )
                    metrics["differentiable_radius_gradient"] = gradient
                    anchor["metrics"] = metrics
                    current_metrics = candidate_metrics
                    optimized_kinds.add(kind)
                    improved = True
                    continue
                if kind in {"stroke_polyline", "stroke_path"}:
                    base_centerline = _stroke_centerline(anchor)
                    if base_centerline is None:
                        continue
                    base_widths = _stroke_width_samples(anchor)
                    gradient = _soft_stroke_transform_gradient(
                        result,
                        anchor,
                        source_rgba,
                        raster_l1_weight=raster_l1_weight,
                        raster_edge_weight=raster_edge_weight,
                    )
                    if max(abs(value) for value in gradient) < 1e-6:
                        continue
                    candidate_centerline, candidate_widths = _stroke_gradient_step(
                        base_centerline,
                        base_widths,
                        gradient,
                    )
                    if (
                        candidate_centerline == base_centerline
                        and candidate_widths == base_widths
                    ):
                        continue
                    candidate = _with_stroke_geometry(
                        result,
                        anchor,
                        candidate_centerline,
                        candidate_widths,
                    )
                    candidate_metrics = _manifest_soft_raster_metrics(
                        candidate,
                        source_rgba,
                        raster_l1_weight=raster_l1_weight,
                        raster_edge_weight=raster_edge_weight,
                    )
                    if candidate_metrics["objective"] >= current_metrics["objective"]:
                        continue
                    stroke = anchor.get("stroke")
                    if not isinstance(stroke, dict):
                        continue
                    stroke["centerline"] = _manifest_points(candidate_centerline)
                    stroke["width_samples"] = list(candidate_widths)
                    metrics = dict(anchor.get("metrics", {}))
                    metrics["refinement_stroke_centerline_delta"] = (
                        metrics.get("refinement_stroke_centerline_delta", 0.0)
                        + _centerline_delta(base_centerline, candidate_centerline)
                    )
                    metrics["refinement_stroke_width_delta"] = (
                        metrics.get("refinement_stroke_width_delta", 0.0)
                        + _width_delta(base_widths, candidate_widths)
                    )
                    metrics["differentiable_stroke_dx_gradient"] = gradient[0]
                    metrics["differentiable_stroke_dy_gradient"] = gradient[1]
                    metrics["differentiable_stroke_width_gradient"] = gradient[2]
                    anchor["metrics"] = metrics
                    current_metrics = candidate_metrics
                    optimized_kinds.add(kind)
                    improved = True
                    continue
                if kind in {"rect", "rounded_rect", "quad"}:
                    base_corners = _quad_corners(anchor)
                    if base_corners is None:
                        continue
                    gradient = _soft_quad_transform_gradient(
                        result,
                        anchor,
                        source_rgba,
                        raster_l1_weight=raster_l1_weight,
                        raster_edge_weight=raster_edge_weight,
                    )
                    if max(abs(value) for value in gradient) < 1e-6:
                        continue
                    candidate_corners = _quad_gradient_step(base_corners, gradient)
                    if candidate_corners == base_corners:
                        continue
                    candidate = _with_quad_corners(
                        result,
                        anchor,
                        candidate_corners,
                    )
                    candidate_metrics = _manifest_soft_raster_metrics(
                        candidate,
                        source_rgba,
                        raster_l1_weight=raster_l1_weight,
                        raster_edge_weight=raster_edge_weight,
                    )
                    if candidate_metrics["objective"] >= current_metrics["objective"]:
                        continue
                    quad = anchor.get("quad")
                    if not isinstance(quad, dict):
                        continue
                    quad["corners"] = _manifest_corners(candidate_corners)
                    metrics = dict(anchor.get("metrics", {}))
                    metrics["refinement_quad_corner_delta"] = (
                        metrics.get("refinement_quad_corner_delta", 0.0)
                        + _corner_delta(base_corners, candidate_corners)
                    )
                    metrics["differentiable_quad_dx_gradient"] = gradient[0]
                    metrics["differentiable_quad_dy_gradient"] = gradient[1]
                    metrics["differentiable_quad_scale_gradient"] = gradient[2]
                    anchor["metrics"] = metrics
                    current_metrics = candidate_metrics
                    optimized_kinds.add(kind)
                    improved = True
            iterations += 1
            if timeout_reached:
                break
            if not improved:
                stopped_reason = "converged"
                break

    hard_metrics = _manifest_raster_metrics(
        result,
        source_rgba,
        raster_l1_weight=raster_l1_weight,
        raster_edge_weight=raster_edge_weight,
    )
    metrics = dict(result.get("metrics", {}))
    metrics["raster_l1_error"] = hard_metrics["raster_l1_error"]
    metrics["raster_edge_error"] = hard_metrics["raster_edge_error"]
    metrics["refinement_objective"] = current_metrics["objective"]
    result["metrics"] = metrics
    return result, {
        "attempted": True,
        "iterations": iterations,
        "objective": "soft_raster_l1_gradient_plus_edge",
        "initial_raster_l1_error": initial_hard_metrics["raster_l1_error"],
        "final_raster_l1_error": hard_metrics["raster_l1_error"],
        "initial_raster_edge_error": initial_hard_metrics["raster_edge_error"],
        "final_raster_edge_error": hard_metrics["raster_edge_error"],
        "initial_objective": initial_metrics["objective"],
        "final_objective": current_metrics["objective"],
        "optimized_parameter_kinds": sorted(optimized_kinds),
        "timeout_reached": timeout_reached,
        "stopped_reason": stopped_reason,
        "renderer": "soft_raster_primitives",
        "renderer_primitive_kinds": sorted(renderer_kinds),
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


def _manifest_soft_raster_metrics(
    manifest: dict[str, object],
    source: Image.Image,
    *,
    raster_l1_weight: float,
    raster_edge_weight: float,
) -> dict[str, float]:
    source_rgba = source.convert("RGBA")
    source_pixels = source_rgba.load()
    width, height = source_rgba.size
    rgb_error = 0.0
    for y in range(height):
        for x in range(width):
            rendered = _soft_raster_rgb(manifest, x + 0.5, y + 0.5)
            source_red, source_green, source_blue, _ = source_pixels[x, y]
            rgb_error += (
                abs(rendered[0] - source_red)
                + abs(rendered[1] - source_green)
                + abs(rendered[2] - source_blue)
            )
    pixel_count = max(width * height, 1)
    l1_error = rgb_error / (pixel_count * 3 * 255)
    edge_error = float(
        raster_fidelity_metrics(
            source=source_rgba,
            rendered=render_manifest_image(manifest),
        )["raster_edge_error"]
    )
    return {
        "raster_l1_error": l1_error,
        "raster_edge_error": edge_error,
        "objective": (l1_error * raster_l1_weight) + (edge_error * raster_edge_weight),
    }


def _soft_circle_radius_gradient(
    manifest: dict[str, object],
    target_anchor: dict[str, object],
    source: Image.Image,
    *,
    raster_l1_weight: float,
    raster_edge_weight: float,
) -> float:
    del raster_edge_weight
    circle = target_anchor.get("circle")
    if not isinstance(circle, dict):
        return 0.0
    cx = float(circle.get("cx", 0.0))
    cy = float(circle.get("cy", 0.0))
    radius = float(circle.get("r", 0.0))
    color = _hex_rgb(str(target_anchor.get("color") or "#0b2d5f"))
    source_rgba = source.convert("RGBA")
    source_pixels = source_rgba.load()
    width, height = source_rgba.size
    softness = 2.0
    gradient = 0.0
    for y in range(height):
        py = y + 0.5
        for x in range(width):
            px = x + 0.5
            distance = ((px - cx) ** 2 + (py - cy) ** 2) ** 0.5
            edge_value = 0.5 + (radius - distance) / softness
            if edge_value <= 0.0 or edge_value >= 1.0:
                continue
            d_alpha = 1.0 / softness
            rendered = _soft_raster_rgb(manifest, px, py)
            source_red, source_green, source_blue, _ = source_pixels[x, y]
            for channel_index, source_value in enumerate(
                (source_red, source_green, source_blue)
            ):
                channel_delta = rendered[channel_index] - source_value
                if channel_delta == 0:
                    continue
                sign = 1.0 if channel_delta > 0 else -1.0
                d_channel = (color[channel_index] - 255) * d_alpha
                gradient += sign * d_channel
    pixel_count = max(width * height, 1)
    return gradient * raster_l1_weight / (pixel_count * 3 * 255)


def _soft_quad_transform_gradient(
    manifest: dict[str, object],
    target_anchor: dict[str, object],
    source: Image.Image,
    *,
    raster_l1_weight: float,
    raster_edge_weight: float,
) -> tuple[float, float, float]:
    del raster_edge_weight
    base_corners = _quad_corners(target_anchor)
    if base_corners is None:
        return (0.0, 0.0, 0.0)
    epsilon = 0.25

    def objective(corners: tuple[tuple[float, float], ...]) -> float:
        candidate = _with_quad_corners(manifest, target_anchor, corners)
        return _manifest_soft_raster_metrics(
            candidate,
            source,
            raster_l1_weight=raster_l1_weight,
            raster_edge_weight=0.0,
        )["objective"]

    dx_gradient = (
        objective(_translate_quad_corners(base_corners, epsilon, 0.0))
        - objective(_translate_quad_corners(base_corners, -epsilon, 0.0))
    ) / (epsilon * 2.0)
    dy_gradient = (
        objective(_translate_quad_corners(base_corners, 0.0, epsilon))
        - objective(_translate_quad_corners(base_corners, 0.0, -epsilon))
    ) / (epsilon * 2.0)
    scale_gradient = (
        objective(_scale_quad_corners(base_corners, epsilon))
        - objective(_scale_quad_corners(base_corners, -epsilon))
    ) / (epsilon * 2.0)
    return (dx_gradient, dy_gradient, scale_gradient)


def _soft_stroke_transform_gradient(
    manifest: dict[str, object],
    target_anchor: dict[str, object],
    source: Image.Image,
    *,
    raster_l1_weight: float,
    raster_edge_weight: float,
) -> tuple[float, float, float]:
    del raster_edge_weight
    base_centerline = _stroke_centerline(target_anchor)
    if base_centerline is None:
        return (0.0, 0.0, 0.0)
    base_widths = _stroke_width_samples(target_anchor)
    epsilon = 0.25

    def objective(
        centerline: tuple[tuple[float, float], ...],
        width_samples: tuple[float, ...],
    ) -> float:
        candidate = _with_stroke_geometry(
            manifest,
            target_anchor,
            centerline,
            width_samples,
        )
        return _manifest_soft_raster_metrics(
            candidate,
            source,
            raster_l1_weight=raster_l1_weight,
            raster_edge_weight=0.0,
        )["objective"]

    dx_gradient = (
        objective(_translate_points(base_centerline, epsilon, 0.0), base_widths)
        - objective(_translate_points(base_centerline, -epsilon, 0.0), base_widths)
    ) / (epsilon * 2.0)
    dy_gradient = (
        objective(_translate_points(base_centerline, 0.0, epsilon), base_widths)
        - objective(_translate_points(base_centerline, 0.0, -epsilon), base_widths)
    ) / (epsilon * 2.0)
    width_gradient = (
        objective(base_centerline, _adjust_width_samples(base_widths, epsilon))
        - objective(base_centerline, _adjust_width_samples(base_widths, -epsilon))
    ) / (epsilon * 2.0)
    return (dx_gradient, dy_gradient, width_gradient)


def _quad_gradient_step(
    corners: tuple[tuple[float, float], ...],
    gradient: tuple[float, float, float],
) -> tuple[tuple[float, float], ...]:
    dx_gradient, dy_gradient, scale_gradient = gradient
    dx = _bounded_gradient_step(dx_gradient, learning_rate=180.0, max_step=1.0)
    dy = _bounded_gradient_step(dy_gradient, learning_rate=180.0, max_step=1.0)
    scale_delta = _bounded_gradient_step(
        scale_gradient,
        learning_rate=180.0,
        max_step=1.0,
    )
    translated = _translate_quad_corners(corners, dx, dy)
    return _scale_quad_corners(translated, scale_delta)


def _stroke_gradient_step(
    centerline: tuple[tuple[float, float], ...],
    width_samples: tuple[float, ...],
    gradient: tuple[float, float, float],
) -> tuple[tuple[tuple[float, float], ...], tuple[float, ...]]:
    dx_gradient, dy_gradient, width_gradient = gradient
    dx = _bounded_gradient_step(dx_gradient, learning_rate=180.0, max_step=1.0)
    dy = _bounded_gradient_step(dy_gradient, learning_rate=180.0, max_step=1.0)
    width_delta = _bounded_gradient_step(
        width_gradient,
        learning_rate=180.0,
        max_step=1.0,
    )
    return (
        _translate_points(centerline, dx, dy),
        _adjust_width_samples(width_samples, width_delta),
    )


def _bounded_gradient_step(
    gradient: float,
    *,
    learning_rate: float,
    max_step: float,
) -> float:
    if abs(gradient) < 1e-6:
        return 0.0
    magnitude = min(max_step, max(0.25, abs(gradient) * learning_rate))
    return -magnitude if gradient > 0 else magnitude


def _soft_raster_rgb(
    manifest: dict[str, object],
    px: float,
    py: float,
) -> tuple[float, float, float]:
    red = green = blue = 255.0
    for anchor in manifest.get("anchors", []):
        if not isinstance(anchor, dict):
            continue
        kind = anchor.get("kind")
        if kind == "circle":
            circle = anchor.get("circle")
            if not isinstance(circle, dict):
                continue
            cx = float(circle.get("cx", 0.0))
            cy = float(circle.get("cy", 0.0))
            radius = float(circle.get("r", 0.0))
            distance = ((px - cx) ** 2 + (py - cy) ** 2) ** 0.5
            alpha = min(1.0, max(0.0, 0.5 + (radius - distance) / 2.0))
        elif kind in {"rect", "rounded_rect", "quad"}:
            corners = _quad_corners(anchor)
            if corners is None:
                continue
            alpha = _soft_quad_alpha(corners, px, py)
        elif kind in {"stroke_polyline", "stroke_path"}:
            centerline = _stroke_centerline(anchor)
            if centerline is None:
                continue
            alpha = _soft_stroke_alpha(
                centerline,
                _stroke_width_samples(anchor),
                px,
                py,
            )
        else:
            continue
        color = _hex_rgb(str(anchor.get("color") or "#0b2d5f"))
        red = red * (1.0 - alpha) + color[0] * alpha
        green = green * (1.0 - alpha) + color[1] * alpha
        blue = blue * (1.0 - alpha) + color[2] * alpha
    return red, green, blue


def _soft_quad_alpha(
    corners: tuple[tuple[float, float], ...],
    px: float,
    py: float,
) -> float:
    if len(corners) < 3:
        return 0.0
    orientation = _polygon_orientation(corners)
    if orientation == 0.0:
        return 0.0
    orientation_sign = 1.0 if orientation > 0 else -1.0
    signed_distance = float("inf")
    for index, (ax, ay) in enumerate(corners):
        bx, by = corners[(index + 1) % len(corners)]
        edge_x = bx - ax
        edge_y = by - ay
        edge_length = max((edge_x**2 + edge_y**2) ** 0.5, 1e-6)
        cross = edge_x * (py - ay) - edge_y * (px - ax)
        signed_distance = min(signed_distance, orientation_sign * cross / edge_length)
    return min(1.0, max(0.0, 0.5 + signed_distance / 2.0))


def _polygon_orientation(corners: tuple[tuple[float, float], ...]) -> float:
    area = 0.0
    for index, (x1, y1) in enumerate(corners):
        x2, y2 = corners[(index + 1) % len(corners)]
        area += (x1 * y2) - (x2 * y1)
    return area


def _soft_stroke_alpha(
    centerline: tuple[tuple[float, float], ...],
    width_samples: tuple[float, ...],
    px: float,
    py: float,
) -> float:
    if len(centerline) < 2:
        return 0.0
    width = sum(width_samples) / max(len(width_samples), 1)
    radius = max(0.25, width / 2.0)
    distance = min(
        _point_segment_distance(px, py, ax, ay, bx, by)
        for (ax, ay), (bx, by) in zip(centerline, centerline[1:], strict=False)
    )
    return min(1.0, max(0.0, 0.5 + (radius - distance) / 2.0))


def _point_segment_distance(
    px: float,
    py: float,
    ax: float,
    ay: float,
    bx: float,
    by: float,
) -> float:
    edge_x = bx - ax
    edge_y = by - ay
    length_sq = (edge_x**2) + (edge_y**2)
    if length_sq <= 1e-12:
        return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
    t = max(0.0, min(1.0, (((px - ax) * edge_x) + ((py - ay) * edge_y)) / length_sq))
    nearest_x = ax + (t * edge_x)
    nearest_y = ay + (t * edge_y)
    return ((px - nearest_x) ** 2 + (py - nearest_y) ** 2) ** 0.5


def _hex_rgb(color: str) -> tuple[int, int, int]:
    value = color.strip().removeprefix("#")
    if len(value) < 6:
        return (11, 45, 95)
    try:
        return (
            int(value[0:2], 16),
            int(value[2:4], 16),
            int(value[4:6], 16),
        )
    except ValueError:
        return (11, 45, 95)


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


def _with_stroke_geometry(
    manifest: dict[str, object],
    anchor: dict[str, object],
    centerline: tuple[tuple[float, float], ...],
    width_samples: tuple[float, ...],
) -> dict[str, object]:
    candidate = dict(manifest)
    candidate_anchors = []
    for candidate_anchor in manifest.get("anchors", []):
        if candidate_anchor is anchor:
            changed = dict(anchor)
            stroke = dict(changed.get("stroke", {}))
            stroke["centerline"] = _manifest_points(centerline)
            stroke["width_samples"] = list(width_samples)
            changed["stroke"] = stroke
            candidate_anchors.append(changed)
        else:
            candidate_anchors.append(candidate_anchor)
    candidate["anchors"] = candidate_anchors
    return candidate


def _stroke_centerline(
    anchor: dict[str, object],
) -> tuple[tuple[float, float], ...] | None:
    stroke = anchor.get("stroke")
    if not isinstance(stroke, dict):
        return None
    points = stroke.get("centerline")
    if not isinstance(points, list) or len(points) < 2:
        return None
    parsed = []
    for point in points:
        if not isinstance(point, dict):
            return None
        parsed.append((float(point.get("x", 0.0)), float(point.get("y", 0.0))))
    return tuple(parsed)


def _stroke_width_samples(anchor: dict[str, object]) -> tuple[float, ...]:
    stroke = anchor.get("stroke")
    if not isinstance(stroke, dict):
        return (1.0,)
    samples = stroke.get("width_samples")
    if not isinstance(samples, list) or not samples:
        return (1.0,)
    return tuple(max(0.5, float(sample)) for sample in samples)


def _stroke_variants(
    centerline: tuple[tuple[float, float], ...],
    width_samples: tuple[float, ...],
) -> tuple[
    tuple[tuple[tuple[float, float], ...], tuple[float, ...]],
    ...,
]:
    variants = []
    for dx, dy in ((-1.0, 0.0), (1.0, 0.0), (0.0, -1.0), (0.0, 1.0)):
        variants.append((tuple((x + dx, y + dy) for x, y in centerline), width_samples))
    for delta in (-1.0, 1.0):
        variants.append(
            (
                centerline,
                tuple(max(0.5, sample + delta) for sample in width_samples),
            )
        )
    return tuple(variants)


def _translate_points(
    points: tuple[tuple[float, float], ...],
    dx: float,
    dy: float,
) -> tuple[tuple[float, float], ...]:
    return tuple((x + dx, y + dy) for x, y in points)


def _adjust_width_samples(
    width_samples: tuple[float, ...],
    delta: float,
) -> tuple[float, ...]:
    return tuple(max(0.5, sample + delta) for sample in width_samples)


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


def _translate_quad_corners(
    corners: tuple[tuple[float, float], ...],
    dx: float,
    dy: float,
) -> tuple[tuple[float, float], ...]:
    return tuple((x + dx, y + dy) for x, y in corners)


def _scale_quad_corners(
    corners: tuple[tuple[float, float], ...],
    delta: float,
) -> tuple[tuple[float, float], ...]:
    cx = sum(point[0] for point in corners) / len(corners)
    cy = sum(point[1] for point in corners) / len(corners)
    half_extent = max(
        max(abs(point[0] - cx) for point in corners),
        max(abs(point[1] - cy) for point in corners),
        1.0,
    )
    scale = max(0.1, 1.0 + (delta / half_extent))
    return tuple((cx + ((x - cx) * scale), cy + ((y - cy) * scale)) for x, y in corners)


def _manifest_corners(
    corners: tuple[tuple[float, float], ...],
) -> list[dict[str, float]]:
    return [{"x": x, "y": y} for x, y in corners]


def _manifest_points(
    points: tuple[tuple[float, float], ...],
) -> list[dict[str, float]]:
    return [{"x": x, "y": y} for x, y in points]


def _corner_delta(
    before: tuple[tuple[float, float], ...],
    after: tuple[tuple[float, float], ...],
) -> float:
    return sum(
        ((after_x - before_x) ** 2 + (after_y - before_y) ** 2) ** 0.5
        for (before_x, before_y), (after_x, after_y) in zip(before, after, strict=True)
    )


def _centerline_delta(
    before: tuple[tuple[float, float], ...],
    after: tuple[tuple[float, float], ...],
) -> float:
    return sum(
        ((after_x - before_x) ** 2 + (after_y - before_y) ** 2) ** 0.5
        for (before_x, before_y), (after_x, after_y) in zip(before, after, strict=True)
    )


def _width_delta(before: tuple[float, ...], after: tuple[float, ...]) -> float:
    return sum(
        abs(after_width - before_width)
        for before_width, after_width in zip(before, after, strict=True)
    )


def _deadline_exceeded(started_at: float, timeout_seconds: float | None) -> bool:
    return timeout_seconds is not None and monotonic() - started_at >= timeout_seconds
