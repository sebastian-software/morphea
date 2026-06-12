"""Deterministic primitive round-trip quality checks."""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from math import hypot
from pathlib import Path
from statistics import mean
from typing import Any, Callable

from PIL import Image, ImageDraw

from morphea.images import scene_from_flat_color_image
from morphea.rendering import raster_fidelity_metrics, render_manifest_image
from morphea.scene import SvgStyle


Geometry = dict[str, Any]
DrawFunction = Callable[[ImageDraw.ImageDraw], None]


@dataclass(frozen=True)
class PrimitiveSpec:
    id: str
    expected_kinds: tuple[str, ...]
    geometry_type: str
    geometry: Geometry
    draw: DrawFunction
    width: int = 64
    height: int = 64
    background: str = "#ffffff"
    color: str = "#003366"
    min_area: int = 4
    coordinate_tolerance: float = 1.5
    max_raster_l1_error: float = 0.02
    max_raster_edge_error: float = 0.03
    min_bbox_iou: float = 0.9
    max_anchor_count: int = 1


def primitive_specs() -> tuple[PrimitiveSpec, ...]:
    blue = "#003366"
    return (
        PrimitiveSpec(
            id="filled_square",
            expected_kinds=("rect", "quad"),
            geometry_type="quad",
            geometry={"corners": ((16, 16), (47, 16), (47, 47), (16, 47))},
            draw=lambda draw: draw.rectangle((16, 16, 47, 47), fill=blue),
            max_raster_l1_error=0.001,
            max_raster_edge_error=0.001,
        ),
        PrimitiveSpec(
            id="filled_rectangle",
            expected_kinds=("rect", "quad"),
            geometry_type="quad",
            geometry={"corners": ((12, 20), (52, 20), (52, 38), (12, 38))},
            draw=lambda draw: draw.rectangle((12, 20, 52, 38), fill=blue),
            max_raster_l1_error=0.001,
            max_raster_edge_error=0.001,
        ),
        PrimitiveSpec(
            id="filled_circle",
            expected_kinds=("circle",),
            geometry_type="circle",
            geometry={"cx": 32.0, "cy": 32.0, "r": 14.0},
            draw=lambda draw: draw.ellipse((18, 18, 46, 46), fill=blue),
            max_raster_l1_error=0.015,
            max_raster_edge_error=0.02,
            min_bbox_iou=0.92,
        ),
        PrimitiveSpec(
            id="horizontal_stroke",
            expected_kinds=("stroke_polyline",),
            geometry_type="stroke",
            geometry={
                "centerline": ((12.0, 32.5), (52.0, 32.5)),
                "width": 4.0,
            },
            draw=lambda draw: draw.line((12, 32, 52, 32), fill=blue, width=4),
            max_raster_l1_error=0.001,
            max_raster_edge_error=0.001,
        ),
        PrimitiveSpec(
            id="vertical_stroke",
            expected_kinds=("stroke_polyline",),
            geometry_type="stroke",
            geometry={
                "centerline": ((32.5, 12.0), (32.5, 52.0)),
                "width": 4.0,
            },
            draw=lambda draw: draw.line((32, 12, 32, 52), fill=blue, width=4),
            max_raster_l1_error=0.001,
            max_raster_edge_error=0.001,
        ),
        PrimitiveSpec(
            id="diagonal_stroke",
            expected_kinds=("stroke_polyline",),
            geometry_type="stroke",
            geometry={
                "centerline": ((14.0, 50.0), (50.0, 14.0)),
                "width": 4.0,
            },
            draw=lambda draw: draw.line((14, 50, 50, 14), fill=blue, width=3),
            max_raster_l1_error=0.02,
            max_raster_edge_error=0.04,
            min_bbox_iou=0.86,
        ),
        PrimitiveSpec(
            id="outlined_ring",
            expected_kinds=("stroke_circle",),
            geometry_type="stroke_circle",
            geometry={"cx": 32.0, "cy": 32.0, "r": 12.5, "width": 4.5},
            draw=lambda draw: draw.ellipse((18, 18, 46, 46), outline=blue, width=4),
            max_raster_l1_error=0.07,
            max_raster_edge_error=0.05,
            min_bbox_iou=0.82,
        ),
        PrimitiveSpec(
            id="rounded_rectangle",
            expected_kinds=("rounded_rect",),
            geometry_type="quad",
            geometry={"corners": ((14, 20), (50, 20), (50, 44), (14, 44))},
            draw=lambda draw: draw.rounded_rectangle(
                (14, 20, 50, 44),
                radius=6,
                fill=blue,
            ),
            max_raster_l1_error=0.02,
            max_raster_edge_error=0.02,
        ),
        PrimitiveSpec(
            id="simple_quad",
            expected_kinds=("quad",),
            geometry_type="quad",
            geometry={"corners": ((20, 18), (46, 18), (54, 44), (12, 44))},
            draw=lambda draw: draw.polygon(
                ((20, 18), (46, 18), (54, 44), (12, 44)),
                fill=blue,
            ),
            max_raster_l1_error=0.001,
            max_raster_edge_error=0.001,
        ),
    )


def check_primitive_quality(
    *,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    output_root = Path(output_dir) if output_dir is not None else None
    if output_root is not None:
        output_root.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        cases = [
            _run_case(spec, output_root=output_root, temp_root=temp_root)
            for spec in primitive_specs()
        ]

    failed = [case for case in cases if not case["ok"]]
    return {
        "schema_version": 1,
        "case_count": len(cases),
        "passed_count": len(cases) - len(failed),
        "failed_count": len(failed),
        "ok": not failed,
        "cases": cases,
    }


def write_primitive_quality_report(
    *,
    output: str | Path,
    output_dir: str | Path | None = None,
    markdown: str | Path | None = None,
) -> dict[str, Any]:
    report = check_primitive_quality(output_dir=output_dir)
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    if markdown is not None:
        markdown_path = Path(markdown)
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(render_primitive_quality_markdown(report), encoding="utf-8")
    return report


def render_primitive_quality_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Morphea Primitive Quality Check",
        "",
        f"- Cases: {report.get('case_count', 0)}",
        f"- Passed: {report.get('passed_count', 0)}",
        f"- Failed: {report.get('failed_count', 0)}",
        f"- OK: `{str(report.get('ok', False)).lower()}`",
        "",
        "| Case | OK | Actual | L1 | Edge | IoU | Failures |",
        "| --- | ---: | --- | ---: | ---: | ---: | --- |",
    ]
    for case in report.get("cases", []):
        metrics = case.get("metrics", {})
        geometry = case.get("geometry", {})
        failures = case.get("failures", [])
        lines.append(
            "| "
            f"`{case.get('id')}` | "
            f"`{str(case.get('ok', False)).lower()}` | "
            f"`{case.get('actual_kind', 'n/a')}` | "
            f"{metrics.get('raster_l1_error', 'n/a')} | "
            f"{metrics.get('raster_edge_error', 'n/a')} | "
            f"{geometry.get('bbox_iou', 'n/a')} | "
            f"{'; '.join(failures) if failures else 'n/a'} |"
        )
    return "\n".join(lines) + "\n"


def _run_case(
    spec: PrimitiveSpec,
    *,
    output_root: Path | None,
    temp_root: Path,
) -> dict[str, Any]:
    case_root = output_root / spec.id if output_root is not None else temp_root / spec.id
    case_root.mkdir(parents=True, exist_ok=True)
    input_path = case_root / "input.png"
    source = _draw_source(spec)
    source.save(input_path)

    scene = scene_from_flat_color_image(input_path, min_area=spec.min_area)
    manifest = scene.to_manifest()
    preview = render_manifest_image(manifest, background=spec.background)
    metrics = raster_fidelity_metrics(source=source, rendered=preview)
    manifest.setdefault("metrics", {}).update(metrics)

    svg_path = case_root / "output.svg"
    debug_svg_path = case_root / "debug.svg"
    manifest_path = case_root / "manifest.json"
    preview_path = case_root / "preview.png"
    if output_root is not None:
        svg_path.write_text(scene.to_svg(SvgStyle()), encoding="utf-8")
        debug_svg_path.write_text(scene.to_debug_svg(), encoding="utf-8")
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        preview.save(preview_path)

    case = _evaluate_case(spec, manifest, metrics)
    if output_root is not None:
        case["artifacts"] = {
            "input": str(input_path),
            "output_svg": str(svg_path),
            "debug_svg": str(debug_svg_path),
            "manifest": str(manifest_path),
            "preview": str(preview_path),
        }
    return case


def _draw_source(spec: PrimitiveSpec) -> Image.Image:
    image = Image.new("RGB", (spec.width, spec.height), spec.background)
    draw = ImageDraw.Draw(image)
    spec.draw(draw)
    return image


def _evaluate_case(
    spec: PrimitiveSpec,
    manifest: dict[str, Any],
    metrics: dict[str, Any],
) -> dict[str, Any]:
    anchors = list(manifest.get("anchors", []))
    failures: list[str] = []
    if len(anchors) > spec.max_anchor_count:
        failures.append(
            f"anchor_count {len(anchors)} exceeds {spec.max_anchor_count}"
        )
    if not anchors:
        failures.append("no anchors detected")
        return _case_result(spec, None, metrics, failures, bbox_iou=0.0, anchor_count=0)

    for anchor in anchors:
        if anchor.get("kind") == "cubic_path":
            failures.append("unexpected cubic_path fallback")
        bounds = _anchor_visual_bounds(anchor)
        if _bounds_outside_canvas(
            bounds,
            width=spec.width,
            height=spec.height,
            tolerance=spec.coordinate_tolerance,
        ):
            failures.append(
                f"anchor bounds outside canvas: {_rounded_bounds(bounds)}"
            )

    anchor = anchors[0]
    actual_kind = str(anchor.get("kind"))
    if actual_kind not in spec.expected_kinds:
        failures.append(
            "expected kind "
            f"{'/'.join(spec.expected_kinds)}, got {actual_kind}"
        )
    if str(anchor.get("color")) != spec.color:
        failures.append(f"expected color {spec.color}, got {anchor.get('color')}")
    if not bool(metrics.get("raster_size_match", False)):
        failures.append("rendered size does not match source")
    if float(metrics.get("raster_l1_error", 1.0)) > spec.max_raster_l1_error:
        failures.append(
            "raster_l1_error "
            f"{metrics.get('raster_l1_error')} exceeds {spec.max_raster_l1_error}"
        )
    if float(metrics.get("raster_edge_error", 1.0)) > spec.max_raster_edge_error:
        failures.append(
            "raster_edge_error "
            f"{metrics.get('raster_edge_error')} exceeds {spec.max_raster_edge_error}"
        )

    expected_bounds = _expected_visual_bounds(spec)
    actual_bounds = _anchor_visual_bounds(anchor)
    bbox_iou = _bbox_iou(expected_bounds, actual_bounds)
    if bbox_iou < spec.min_bbox_iou:
        failures.append(f"bbox_iou {bbox_iou} below {spec.min_bbox_iou}")
    failures.extend(_geometry_failures(spec, anchor))
    return _case_result(
        spec,
        anchor,
        metrics,
        failures,
        bbox_iou=bbox_iou,
        anchor_count=len(anchors),
    )


def _case_result(
    spec: PrimitiveSpec,
    anchor: dict[str, Any] | None,
    metrics: dict[str, Any],
    failures: list[str],
    *,
    bbox_iou: float,
    anchor_count: int,
) -> dict[str, Any]:
    return {
        "id": spec.id,
        "ok": not failures,
        "expected_kinds": list(spec.expected_kinds),
        "actual_kind": anchor.get("kind") if anchor is not None else None,
        "anchor_count": anchor_count,
        "metrics": metrics,
        "geometry": {
            "expected_bounds": _rounded_bounds(_expected_visual_bounds(spec)),
            "actual_bounds": (
                _rounded_bounds(_anchor_visual_bounds(anchor))
                if anchor is not None
                else None
            ),
            "bbox_iou": round(bbox_iou, 6),
        },
        "failures": failures,
    }


def _geometry_failures(spec: PrimitiveSpec, anchor: dict[str, Any]) -> list[str]:
    if spec.geometry_type == "quad":
        return _quad_failures(spec, anchor)
    if spec.geometry_type == "circle":
        return _circle_failures(spec, anchor)
    if spec.geometry_type == "stroke_circle":
        return _circle_failures(spec, anchor) + _stroke_width_failures(spec, anchor)
    if spec.geometry_type == "stroke":
        return _stroke_failures(spec, anchor)
    return [f"unsupported geometry contract {spec.geometry_type}"]


def _quad_failures(spec: PrimitiveSpec, anchor: dict[str, Any]) -> list[str]:
    quad = anchor.get("quad")
    if not isinstance(quad, dict):
        return ["missing quad geometry"]
    actual = tuple(
        (float(point.get("x", 0.0)), float(point.get("y", 0.0)))
        for point in quad.get("corners", [])
    )
    expected = tuple(
        (float(x), float(y)) for x, y in spec.geometry["corners"]
    )
    if len(actual) != len(expected):
        return [f"expected {len(expected)} corners, got {len(actual)}"]
    failures = []
    for index, (left, right) in enumerate(zip(actual, expected, strict=True)):
        if _point_distance(left, right) > spec.coordinate_tolerance:
            failures.append(
                f"corner {index} distance "
                f"{round(_point_distance(left, right), 6)} exceeds "
                f"{spec.coordinate_tolerance}"
            )
    return failures


def _circle_failures(spec: PrimitiveSpec, anchor: dict[str, Any]) -> list[str]:
    circle = anchor.get("circle")
    if not isinstance(circle, dict):
        return ["missing circle geometry"]
    failures = []
    for key in ("cx", "cy", "r"):
        actual = float(circle.get(key, 0.0))
        expected = float(spec.geometry[key])
        if abs(actual - expected) > spec.coordinate_tolerance:
            failures.append(
                f"{key} delta {round(abs(actual - expected), 6)} exceeds "
                f"{spec.coordinate_tolerance}"
            )
    return failures


def _stroke_width_failures(
    spec: PrimitiveSpec,
    anchor: dict[str, Any],
) -> list[str]:
    stroke = anchor.get("stroke")
    if not isinstance(stroke, dict):
        return ["missing stroke geometry"]
    actual = _stroke_width(anchor)
    expected = float(spec.geometry["width"])
    if abs(actual - expected) > spec.coordinate_tolerance:
        return [
            f"stroke width delta {round(abs(actual - expected), 6)} exceeds "
            f"{spec.coordinate_tolerance}"
        ]
    return []


def _stroke_failures(spec: PrimitiveSpec, anchor: dict[str, Any]) -> list[str]:
    stroke = anchor.get("stroke")
    if not isinstance(stroke, dict):
        return ["missing stroke geometry"]
    actual = tuple(
        (float(point.get("x", 0.0)), float(point.get("y", 0.0)))
        for point in stroke.get("centerline", [])
    )
    expected = tuple(
        (float(x), float(y)) for x, y in spec.geometry["centerline"]
    )
    failures = []
    if len(actual) != len(expected):
        failures.append(f"expected {len(expected)} centerline points, got {len(actual)}")
    elif _oriented_line_error(actual, expected) > spec.coordinate_tolerance:
        failures.append(
            "centerline endpoint distance "
            f"{round(_oriented_line_error(actual, expected), 6)} exceeds "
            f"{spec.coordinate_tolerance}"
        )
    failures.extend(_stroke_width_failures(spec, anchor))
    return failures


def _expected_visual_bounds(spec: PrimitiveSpec) -> tuple[float, float, float, float]:
    if spec.geometry_type == "quad":
        points = spec.geometry["corners"]
        xs = [float(x) for x, _ in points]
        ys = [float(y) for _, y in points]
        return min(xs), min(ys), max(xs), max(ys)
    if spec.geometry_type in {"circle", "stroke_circle"}:
        cx = float(spec.geometry["cx"])
        cy = float(spec.geometry["cy"])
        radius = float(spec.geometry["r"])
        if spec.geometry_type == "stroke_circle":
            radius += float(spec.geometry["width"]) / 2
        return cx - radius, cy - radius, cx + radius, cy + radius
    if spec.geometry_type == "stroke":
        points = spec.geometry["centerline"]
        width = float(spec.geometry["width"])
        xs = [float(x) for x, _ in points]
        ys = [float(y) for _, y in points]
        pad = width / 2
        return min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad
    return 0.0, 0.0, 0.0, 0.0


def _anchor_visual_bounds(anchor: dict[str, Any]) -> tuple[float, float, float, float]:
    circle = anchor.get("circle")
    if isinstance(circle, dict):
        radius = float(circle.get("r", 0.0))
        if anchor.get("kind") == "stroke_circle":
            radius += _stroke_width(anchor) / 2
        cx = float(circle.get("cx", 0.0))
        cy = float(circle.get("cy", 0.0))
        return cx - radius, cy - radius, cx + radius, cy + radius
    quad = anchor.get("quad")
    if isinstance(quad, dict):
        points = quad.get("corners", [])
        xs = [float(point.get("x", 0.0)) for point in points]
        ys = [float(point.get("y", 0.0)) for point in points]
        if xs and ys:
            return min(xs), min(ys), max(xs), max(ys)
    stroke = anchor.get("stroke")
    if isinstance(stroke, dict):
        points = stroke.get("centerline", [])
        xs = [float(point.get("x", 0.0)) for point in points]
        ys = [float(point.get("y", 0.0)) for point in points]
        if xs and ys:
            pad = _stroke_width(anchor) / 2
            return min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad
    return 0.0, 0.0, 0.0, 0.0


def _stroke_width(anchor: dict[str, Any]) -> float:
    stroke = anchor.get("stroke")
    if not isinstance(stroke, dict):
        return 1.0
    samples = [float(sample) for sample in stroke.get("width_samples", [])]
    return mean(samples) if samples else 1.0


def _bounds_outside_canvas(
    bounds: tuple[float, float, float, float],
    *,
    width: int,
    height: int,
    tolerance: float,
) -> bool:
    min_x, min_y, max_x, max_y = bounds
    return (
        min_x < -tolerance
        or min_y < -tolerance
        or max_x > width - 1 + tolerance
        or max_y > height - 1 + tolerance
    )


def _bbox_iou(
    left: tuple[float, float, float, float],
    right: tuple[float, float, float, float],
) -> float:
    left_x0, left_y0, left_x1, left_y1 = left
    right_x0, right_y0, right_x1, right_y1 = right
    inter_x0 = max(left_x0, right_x0)
    inter_y0 = max(left_y0, right_y0)
    inter_x1 = min(left_x1, right_x1)
    inter_y1 = min(left_y1, right_y1)
    intersection = max(0.0, inter_x1 - inter_x0) * max(0.0, inter_y1 - inter_y0)
    left_area = max(0.0, left_x1 - left_x0) * max(0.0, left_y1 - left_y0)
    right_area = max(0.0, right_x1 - right_x0) * max(0.0, right_y1 - right_y0)
    union = left_area + right_area - intersection
    return round(intersection / union, 6) if union > 0 else 0.0


def _point_distance(
    left: tuple[float, float],
    right: tuple[float, float],
) -> float:
    return hypot(left[0] - right[0], left[1] - right[1])


def _oriented_line_error(
    actual: tuple[tuple[float, float], ...],
    expected: tuple[tuple[float, float], ...],
) -> float:
    forward = sum(
        _point_distance(left, right)
        for left, right in zip(actual, expected, strict=True)
    )
    reverse = sum(
        _point_distance(left, right)
        for left, right in zip(reversed(actual), expected, strict=True)
    )
    return min(forward, reverse) / len(expected)


def _rounded_bounds(bounds: tuple[float, float, float, float]) -> list[float]:
    return [round(value, 6) for value in bounds]
