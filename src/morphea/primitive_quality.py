"""Deterministic primitive round-trip quality checks."""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from fnmatch import fnmatch
from math import hypot
from pathlib import Path
from statistics import mean
from typing import Any, Callable, Iterable

from PIL import Image, ImageDraw

from morphea.images import scene_from_flat_color_image
from morphea.rendering import raster_fidelity_metrics, render_manifest_image
from morphea.scene import SvgStyle


Geometry = dict[str, Any]
DrawFunction = Callable[[ImageDraw.ImageDraw], None]
BLUE = "#003366"


@dataclass(frozen=True)
class PrimitiveSpec:
    id: str
    expected_kinds: tuple[str, ...]
    geometry_type: str
    geometry: Geometry
    draw: DrawFunction
    family: str | None = None
    variant: str = "fixed"
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
    specs: list[PrimitiveSpec] = []
    specs.extend(
        _square_spec(case_id, variant, box)
        for case_id, variant, box in (
            ("filled_square", "base", (16, 16, 47, 47)),
            ("filled_square_small_top_left", "small_top_left", (8, 8, 25, 25)),
            ("filled_square_small_bottom_right", "small_bottom_right", (38, 34, 55, 51)),
            ("filled_square_medium_left", "medium_left", (6, 24, 29, 47)),
            ("filled_square_medium_right", "medium_right", (35, 10, 58, 33)),
            ("filled_square_large_center", "large_center", (10, 10, 53, 53)),
            ("filled_square_near_top", "near_top", (24, 2, 45, 23)),
            ("filled_square_near_bottom", "near_bottom", (20, 40, 41, 61)),
            ("filled_square_tiny_center", "tiny_center", (27, 27, 38, 38)),
            ("filled_square_offset_center", "offset_center", (18, 11, 44, 37)),
        )
    )
    specs.extend(
        _rectangle_spec(case_id, variant, box)
        for case_id, variant, box in (
            ("filled_rectangle", "base", (12, 20, 52, 38)),
            ("filled_rectangle_tall", "tall", (18, 8, 38, 56)),
            ("filled_rectangle_wide", "wide", (6, 24, 58, 38)),
            ("filled_rectangle_wide_thick", "wide_thick", (4, 22, 60, 36)),
            ("filled_rectangle_narrow_tall", "narrow_tall", (26, 4, 40, 60)),
            ("filled_rectangle_small", "small", (8, 8, 28, 22)),
            ("filled_rectangle_bottom", "bottom", (18, 42, 54, 58)),
            ("filled_rectangle_top_strip", "top_strip", (10, 4, 54, 16)),
            ("filled_rectangle_right", "right", (38, 12, 58, 50)),
            ("filled_rectangle_near_square", "near_square", (20, 16, 48, 42)),
        )
    )
    specs.extend(
        _circle_spec(case_id, variant, box)
        for case_id, variant, box in (
            ("filled_circle", "base", (18, 18, 46, 46)),
            ("filled_circle_small_top_left", "small_top_left", (8, 8, 28, 28)),
            ("filled_circle_small_top_right", "small_top_right", (34, 8, 56, 30)),
            ("filled_circle_small_bottom_left", "small_bottom_left", (8, 34, 30, 56)),
            ("filled_circle_large_top_right", "large_top_right", (24, 4, 60, 40)),
            ("filled_circle_large_bottom_left", "large_bottom_left", (4, 24, 36, 56)),
            ("filled_circle_medium_center", "medium_center", (20, 20, 44, 44)),
            ("filled_circle_large_center", "large_center", (10, 14, 50, 54)),
            ("filled_circle_near_origin", "near_origin", (2, 2, 30, 30)),
            ("filled_circle_near_corner", "near_corner", (32, 32, 60, 60)),
        )
    )
    specs.extend(
        _horizontal_stroke_spec(case_id, variant, line, width)
        for case_id, variant, line, width in (
            ("horizontal_stroke", "base", (12, 32, 52, 32), 4),
            ("horizontal_stroke_width_1", "width_1", (8, 14, 56, 14), 1),
            ("horizontal_stroke_width_2", "width_2", (8, 20, 56, 20), 2),
            ("horizontal_stroke_width_3", "width_3", (10, 26, 54, 26), 3),
            ("horizontal_stroke_width_5", "width_5", (8, 38, 56, 38), 5),
            ("horizontal_stroke_width_6", "width_6", (12, 46, 52, 46), 6),
            ("horizontal_stroke_width_8", "width_8", (10, 54, 54, 54), 8),
            ("horizontal_stroke_short", "short", (18, 10, 42, 10), 4),
            ("horizontal_stroke_left", "left", (4, 32, 34, 32), 4),
            ("horizontal_stroke_right", "right", (30, 32, 60, 32), 4),
        )
    )
    specs.extend(
        _vertical_stroke_spec(case_id, variant, line, width)
        for case_id, variant, line, width in (
            ("vertical_stroke", "base", (32, 12, 32, 52), 4),
            ("vertical_stroke_width_1", "width_1", (14, 8, 14, 56), 1),
            ("vertical_stroke_width_2", "width_2", (20, 8, 20, 56), 2),
            ("vertical_stroke_width_3", "width_3", (26, 10, 26, 54), 3),
            ("vertical_stroke_width_5", "width_5", (38, 8, 38, 56), 5),
            ("vertical_stroke_width_6", "width_6", (46, 12, 46, 52), 6),
            ("vertical_stroke_width_8", "width_8", (54, 10, 54, 54), 8),
            ("vertical_stroke_short", "short", (10, 18, 10, 42), 4),
            ("vertical_stroke_top", "top", (32, 4, 32, 34), 4),
            ("vertical_stroke_bottom", "bottom", (32, 30, 32, 60), 4),
        )
    )
    specs.extend(
        _diagonal_stroke_spec(case_id, variant, line, width)
        for case_id, variant, line, width in (
            ("diagonal_stroke", "base", (14, 50, 50, 14), 3),
            ("diagonal_stroke_width_2", "width_2", (12, 52, 52, 12), 2),
            ("diagonal_stroke_width_3", "width_3", (10, 50, 54, 14), 3),
            ("diagonal_stroke_width_4", "width_4", (8, 48, 56, 20), 4),
            ("diagonal_stroke_width_5", "width_5", (12, 12, 52, 52), 5),
            ("diagonal_stroke_width_6", "width_6", (8, 56, 56, 8), 6),
            ("diagonal_stroke_width_7", "width_7", (16, 54, 50, 10), 7),
            ("diagonal_stroke_width_8", "width_8", (10, 16, 54, 48), 8),
            ("diagonal_stroke_shallow", "shallow", (8, 44, 56, 24), 4),
            ("diagonal_stroke_steep", "steep", (24, 56, 42, 8), 4),
        )
    )
    specs.extend(
        _ring_spec(case_id, variant, box, width)
        for case_id, variant, box, width in (
            ("outlined_ring", "base", (18, 18, 46, 46), 4),
            ("outlined_ring_thin", "thin", (18, 18, 46, 46), 2),
            ("outlined_ring_medium", "medium", (16, 16, 48, 48), 4),
            ("outlined_ring_thick", "thick", (16, 16, 48, 48), 6),
            ("outlined_ring_large_thick", "large_thick", (10, 10, 54, 54), 8),
            ("outlined_ring_small_left", "small_left", (6, 18, 34, 46), 4),
            ("outlined_ring_small_right", "small_right", (30, 18, 58, 46), 4),
            ("outlined_ring_top", "top", (18, 4, 46, 32), 4),
            ("outlined_ring_bottom", "bottom", (18, 30, 46, 58), 4),
            ("outlined_ring_large", "large", (8, 8, 56, 56), 5),
        )
    )
    specs.extend(
        _rounded_rectangle_spec(case_id, variant, box, radius)
        for case_id, variant, box, radius in (
            ("rounded_rectangle", "base", (14, 20, 50, 44), 6),
            ("rounded_rectangle_small_radius", "small_radius", (8, 8, 38, 30), 4),
            ("rounded_rectangle_medium_radius", "medium_radius", (10, 18, 54, 46), 10),
            ("rounded_rectangle_tall", "tall", (20, 8, 50, 56), 8),
            ("rounded_rectangle_wide", "wide", (6, 24, 58, 42), 6),
            ("rounded_rectangle_small", "small", (12, 10, 36, 28), 5),
            ("rounded_rectangle_bottom", "bottom", (14, 36, 52, 58), 7),
            ("rounded_rectangle_top", "top", (14, 4, 52, 26), 7),
            ("rounded_rectangle_right", "right", (30, 12, 58, 48), 8),
            ("rounded_rectangle_left", "left", (6, 12, 34, 48), 8),
        )
    )
    specs.extend(
        _quad_spec(case_id, variant, corners)
        for case_id, variant, corners in (
            ("simple_quad", "base", ((20, 18), (46, 18), (54, 44), (12, 44))),
            ("simple_quad_trapezoid_1", "trapezoid_1", ((18, 18), (46, 18), (52, 44), (12, 44))),
            ("simple_quad_trapezoid_2", "trapezoid_2", ((14, 14), (50, 14), (54, 48), (10, 48))),
            ("simple_quad_trapezoid_3", "trapezoid_3", ((18, 12), (42, 12), (50, 52), (10, 52))),
            ("simple_quad_trapezoid_4", "trapezoid_4", ((10, 20), (54, 20), (48, 48), (16, 48))),
            ("simple_quad_trapezoid_5", "trapezoid_5", ((20, 10), (44, 10), (56, 42), (8, 42))),
            ("simple_quad_trapezoid_6", "trapezoid_6", ((8, 12), (56, 12), (50, 32), (16, 32))),
            ("simple_quad_trapezoid_7", "trapezoid_7", ((16, 30), (48, 30), (58, 56), (6, 56))),
            ("simple_quad_trapezoid_8", "trapezoid_8", ((24, 8), (54, 8), (48, 40), (12, 40))),
            ("simple_quad_trapezoid_9", "trapezoid_9", ((12, 24), (52, 24), (44, 54), (20, 54))),
        )
    )
    return tuple(specs)


def _square_spec(
    case_id: str,
    variant: str,
    box: tuple[int, int, int, int],
) -> PrimitiveSpec:
    return _rectangle_spec(case_id, variant, box, family="filled_square")


def _rectangle_spec(
    case_id: str,
    variant: str,
    box: tuple[int, int, int, int],
    *,
    family: str = "filled_rectangle",
) -> PrimitiveSpec:
    x0, y0, x1, y1 = box
    return PrimitiveSpec(
        id=case_id,
        family=family,
        variant=variant,
        expected_kinds=("rect", "quad"),
        geometry_type="quad",
        geometry={"corners": ((x0, y0), (x1, y0), (x1, y1), (x0, y1))},
        draw=lambda draw, box=box: draw.rectangle(box, fill=BLUE),
        max_raster_l1_error=0.001,
        max_raster_edge_error=0.001,
    )


def _circle_spec(
    case_id: str,
    variant: str,
    box: tuple[int, int, int, int],
) -> PrimitiveSpec:
    x0, y0, x1, y1 = box
    radius = (x1 - x0) / 2
    return PrimitiveSpec(
        id=case_id,
        family="filled_circle",
        variant=variant,
        expected_kinds=("circle",),
        geometry_type="circle",
        geometry={"cx": (x0 + x1) / 2, "cy": (y0 + y1) / 2, "r": radius},
        draw=lambda draw, box=box: draw.ellipse(box, fill=BLUE),
        max_raster_l1_error=0.018,
        max_raster_edge_error=0.024,
        min_bbox_iou=0.9,
    )


def _horizontal_stroke_spec(
    case_id: str,
    variant: str,
    line: tuple[int, int, int, int],
    width: int,
) -> PrimitiveSpec:
    x0, y0, x1, y1 = line
    center_y = y0 + (0.5 if width % 2 == 0 else 0.0)
    return PrimitiveSpec(
        id=case_id,
        family="horizontal_stroke",
        variant=variant,
        expected_kinds=("stroke_polyline",),
        geometry_type="stroke",
        geometry={"centerline": ((float(x0), center_y), (float(x1), center_y)), "width": float(width)},
        draw=lambda draw, line=line, width=width: draw.line(line, fill=BLUE, width=width),
        coordinate_tolerance=1.75,
        max_raster_l1_error=0.002,
        max_raster_edge_error=0.002,
    )


def _vertical_stroke_spec(
    case_id: str,
    variant: str,
    line: tuple[int, int, int, int],
    width: int,
) -> PrimitiveSpec:
    x0, y0, x1, y1 = line
    center_x = x0 + (0.5 if width % 2 == 0 else 0.0)
    return PrimitiveSpec(
        id=case_id,
        family="vertical_stroke",
        variant=variant,
        expected_kinds=("stroke_polyline",),
        geometry_type="stroke",
        geometry={"centerline": ((center_x, float(y0)), (center_x, float(y1))), "width": float(width)},
        draw=lambda draw, line=line, width=width: draw.line(line, fill=BLUE, width=width),
        coordinate_tolerance=1.75,
        max_raster_l1_error=0.002,
        max_raster_edge_error=0.002,
    )


def _diagonal_stroke_spec(
    case_id: str,
    variant: str,
    line: tuple[int, int, int, int],
    width: int,
) -> PrimitiveSpec:
    x0, y0, x1, y1 = line
    return PrimitiveSpec(
        id=case_id,
        family="diagonal_stroke",
        variant=variant,
        expected_kinds=("stroke_polyline",),
        geometry_type="stroke",
        geometry={
            "centerline": ((float(x0), float(y0)), (float(x1), float(y1))),
            "width": float(width),
        },
        draw=lambda draw, line=line, width=width: draw.line(line, fill=BLUE, width=width),
        coordinate_tolerance=2.75,
        max_raster_l1_error=0.035,
        max_raster_edge_error=0.055,
        min_bbox_iou=0.78,
    )


def _ring_spec(
    case_id: str,
    variant: str,
    box: tuple[int, int, int, int],
    width: int,
) -> PrimitiveSpec:
    x0, y0, x1, y1 = box
    outer_radius = (x1 - x0) / 2
    return PrimitiveSpec(
        id=case_id,
        family="outlined_ring",
        variant=variant,
        expected_kinds=("stroke_circle",),
        geometry_type="stroke_circle",
        geometry={
            "cx": (x0 + x1) / 2,
            "cy": (y0 + y1) / 2,
            "r": outer_radius - width / 2 + 0.5,
            "width": width + 0.5,
        },
        draw=lambda draw, box=box, width=width: draw.ellipse(
            box,
            outline=BLUE,
            width=width,
        ),
        coordinate_tolerance=2.0,
        max_raster_l1_error=0.18,
        max_raster_edge_error=0.08,
        min_bbox_iou=0.8,
    )


def _rounded_rectangle_spec(
    case_id: str,
    variant: str,
    box: tuple[int, int, int, int],
    radius: int,
) -> PrimitiveSpec:
    x0, y0, x1, y1 = box
    return PrimitiveSpec(
        id=case_id,
        family="rounded_rectangle",
        variant=variant,
        expected_kinds=("rounded_rect",),
        geometry_type="quad",
        geometry={"corners": ((x0, y0), (x1, y0), (x1, y1), (x0, y1))},
        draw=lambda draw, box=box, radius=radius: draw.rounded_rectangle(
            box,
            radius=radius,
            fill=BLUE,
        ),
        max_raster_l1_error=0.03,
        max_raster_edge_error=0.03,
        min_bbox_iou=0.9,
    )


def _quad_spec(
    case_id: str,
    variant: str,
    corners: tuple[tuple[int, int], tuple[int, int], tuple[int, int], tuple[int, int]],
) -> PrimitiveSpec:
    return PrimitiveSpec(
        id=case_id,
        family="simple_quad",
        variant=variant,
        expected_kinds=("quad",),
        geometry_type="quad",
        geometry={"corners": corners},
        draw=lambda draw, corners=corners: draw.polygon(corners, fill=BLUE),
        max_raster_l1_error=0.002,
        max_raster_edge_error=0.002,
        min_bbox_iou=0.9,
    )


def check_primitive_quality(
    *,
    output_dir: str | Path | None = None,
    cases: Iterable[str] = (),
    filter_pattern: str | None = None,
) -> dict[str, Any]:
    requested_cases = tuple(cases)
    output_root = Path(output_dir) if output_dir is not None else None
    if output_root is not None:
        output_root.mkdir(parents=True, exist_ok=True)
    specs = _selected_specs(
        primitive_specs(),
        requested_cases=requested_cases,
        filter_pattern=filter_pattern,
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        case_results = [
            _run_case(spec, output_root=output_root, temp_root=temp_root)
            for spec in specs
        ]

    failed = [case for case in case_results if not case["ok"]]
    family_summaries = _family_summaries(case_results)
    return {
        "schema_version": 1,
        "case_count": len(case_results),
        "passed_count": len(case_results) - len(failed),
        "failed_count": len(failed),
        "ok": bool(case_results) and not failed,
        "selected_case_ids": [case["id"] for case in case_results],
        "family_summaries": family_summaries,
        "selection": {
            "cases": list(requested_cases),
            "filter": filter_pattern,
        },
        "cases": case_results,
    }


def write_primitive_quality_report(
    *,
    output: str | Path,
    output_dir: str | Path | None = None,
    markdown: str | Path | None = None,
    cases: Iterable[str] = (),
    filter_pattern: str | None = None,
) -> dict[str, Any]:
    report = check_primitive_quality(
        output_dir=output_dir,
        cases=cases,
        filter_pattern=filter_pattern,
    )
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
        "| Family | Cases | Passed | Failed |",
        "| --- | ---: | ---: | ---: |",
    ]
    for family in report.get("family_summaries", []):
        lines.append(
            "| "
            f"`{family.get('family')}` | "
            f"{family.get('case_count', 0)} | "
            f"{family.get('passed_count', 0)} | "
            f"{family.get('failed_count', 0)} |"
        )
    lines.extend(
        [
            "",
        "| Case | OK | Actual | L1 | Edge | IoU | Failures |",
        "| --- | ---: | --- | ---: | ---: | ---: | --- |",
        ]
    )
    for case in report.get("cases", []):
        metrics = case.get("metrics", {})
        geometry = case.get("geometry", {})
        failures = case.get("failures", [])
        failure_categories = case.get("failure_categories", [])
        failure_text = "; ".join(failures) if failures else "n/a"
        if failure_categories:
            failure_text = f"{', '.join(failure_categories)}: {failure_text}"
        lines.append(
            "| "
            f"`{case.get('id')}` | "
            f"`{str(case.get('ok', False)).lower()}` | "
            f"`{case.get('actual_kind', 'n/a')}` | "
            f"{metrics.get('raster_l1_error', 'n/a')} | "
            f"{metrics.get('raster_edge_error', 'n/a')} | "
            f"{geometry.get('bbox_iou', 'n/a')} | "
            f"{failure_text} |"
        )
    return "\n".join(lines) + "\n"


def _selected_specs(
    specs: tuple[PrimitiveSpec, ...],
    *,
    requested_cases: tuple[str, ...],
    filter_pattern: str | None,
) -> tuple[PrimitiveSpec, ...]:
    selected = specs
    if requested_cases:
        requested = set(requested_cases)
        selected = tuple(
            spec
            for spec in selected
            if spec.id in requested
        )
    if filter_pattern:
        selected = tuple(
            spec
            for spec in selected
            if fnmatch(spec.id, filter_pattern)
            or fnmatch(_spec_family(spec), filter_pattern)
        )
    return selected


def _family_summaries(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_family: dict[str, list[dict[str, Any]]] = {}
    for case in cases:
        by_family.setdefault(str(case.get("family", case.get("id"))), []).append(case)
    summaries = []
    for family in sorted(by_family):
        family_cases = by_family[family]
        failed = [case for case in family_cases if not case["ok"]]
        summaries.append(
            {
                "family": family,
                "case_count": len(family_cases),
                "passed_count": len(family_cases) - len(failed),
                "failed_count": len(failed),
                "ok": not failed,
            }
        )
    return summaries


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
    failure_details: list[dict[str, str]] = []
    if len(anchors) > spec.max_anchor_count:
        failure_details.append(
            _failure(
                "wrong_count",
                f"anchor_count {len(anchors)} exceeds {spec.max_anchor_count}",
            )
        )
    if not anchors:
        failure_details.append(_failure("wrong_count", "no anchors detected"))
        return _case_result(
            spec,
            None,
            metrics,
            failure_details,
            bbox_iou=0.0,
            anchor_count=0,
        )

    for anchor in anchors:
        if anchor.get("kind") == "cubic_path":
            failure_details.append(
                _failure("fallback_path", "unexpected cubic_path fallback")
            )
        bounds = _anchor_visual_bounds(anchor)
        if _bounds_outside_canvas(
            bounds,
            width=spec.width,
            height=spec.height,
            tolerance=spec.coordinate_tolerance,
        ):
            failure_details.append(
                _failure(
                    "bounds_escape",
                    f"anchor bounds outside canvas: {_rounded_bounds(bounds)}",
                )
            )

    anchor = anchors[0]
    actual_kind = str(anchor.get("kind"))
    if actual_kind not in spec.expected_kinds:
        failure_details.append(
            _failure(
                "wrong_kind",
                "expected kind "
                f"{'/'.join(spec.expected_kinds)}, got {actual_kind}",
            )
        )
    if str(anchor.get("color")) != spec.color:
        failure_details.append(
            _failure("color_drift", f"expected color {spec.color}, got {anchor.get('color')}")
        )
    if not bool(metrics.get("raster_size_match", False)):
        failure_details.append(
            _failure("visual_drift", "rendered size does not match source")
        )
    if float(metrics.get("raster_l1_error", 1.0)) > spec.max_raster_l1_error:
        failure_details.append(
            _failure(
                "visual_drift",
                "raster_l1_error "
                f"{metrics.get('raster_l1_error')} exceeds {spec.max_raster_l1_error}",
            )
        )
    if float(metrics.get("raster_edge_error", 1.0)) > spec.max_raster_edge_error:
        failure_details.append(
            _failure(
                "visual_drift",
                "raster_edge_error "
                f"{metrics.get('raster_edge_error')} exceeds {spec.max_raster_edge_error}",
            )
        )

    expected_bounds = _expected_visual_bounds(spec)
    actual_bounds = _anchor_visual_bounds(anchor)
    bbox_iou = _bbox_iou(expected_bounds, actual_bounds)
    if bbox_iou < spec.min_bbox_iou:
        failure_details.append(
            _failure("geometry_drift", f"bbox_iou {bbox_iou} below {spec.min_bbox_iou}")
        )
    failure_details.extend(_geometry_failures(spec, anchor))
    return _case_result(
        spec,
        anchor,
        metrics,
        failure_details,
        bbox_iou=bbox_iou,
        anchor_count=len(anchors),
    )


def _case_result(
    spec: PrimitiveSpec,
    anchor: dict[str, Any] | None,
    metrics: dict[str, Any],
    failure_details: list[dict[str, str]],
    *,
    bbox_iou: float,
    anchor_count: int,
) -> dict[str, Any]:
    failures = [failure["message"] for failure in failure_details]
    categories = sorted({failure["category"] for failure in failure_details})
    return {
        "id": spec.id,
        "family": _spec_family(spec),
        "variant": spec.variant,
        "ok": not failure_details,
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
        "geometry_diff": _geometry_diff(spec, anchor),
        "failures": failures,
        "failure_categories": categories,
        "failure_details": failure_details,
    }


def _geometry_failures(spec: PrimitiveSpec, anchor: dict[str, Any]) -> list[dict[str, str]]:
    if spec.geometry_type == "quad":
        return _quad_failures(spec, anchor)
    if spec.geometry_type == "circle":
        return _circle_failures(spec, anchor)
    if spec.geometry_type == "stroke_circle":
        return _circle_failures(spec, anchor) + _stroke_width_failures(spec, anchor)
    if spec.geometry_type == "stroke":
        return _stroke_failures(spec, anchor)
    return [_failure("geometry_drift", f"unsupported geometry contract {spec.geometry_type}")]


def _quad_failures(spec: PrimitiveSpec, anchor: dict[str, Any]) -> list[dict[str, str]]:
    quad = anchor.get("quad")
    if not isinstance(quad, dict):
        return [_failure("geometry_drift", "missing quad geometry")]
    actual = tuple(
        (float(point.get("x", 0.0)), float(point.get("y", 0.0)))
        for point in quad.get("corners", [])
    )
    expected = tuple(
        (float(x), float(y)) for x, y in spec.geometry["corners"]
    )
    if len(actual) != len(expected):
        return [
            _failure("geometry_drift", f"expected {len(expected)} corners, got {len(actual)}")
        ]
    failures = []
    for index, (left, right) in enumerate(zip(actual, expected, strict=True)):
        if _point_distance(left, right) > spec.coordinate_tolerance:
            failures.append(
                _failure(
                    "geometry_drift",
                    f"corner {index} distance "
                    f"{round(_point_distance(left, right), 6)} exceeds "
                    f"{spec.coordinate_tolerance}",
                )
            )
    return failures


def _circle_failures(spec: PrimitiveSpec, anchor: dict[str, Any]) -> list[dict[str, str]]:
    circle = anchor.get("circle")
    if not isinstance(circle, dict):
        return [_failure("geometry_drift", "missing circle geometry")]
    failures = []
    for key in ("cx", "cy", "r"):
        actual = float(circle.get(key, 0.0))
        expected = float(spec.geometry[key])
        if abs(actual - expected) > spec.coordinate_tolerance:
            failures.append(
                _failure(
                    "geometry_drift",
                    f"{key} delta {round(abs(actual - expected), 6)} exceeds "
                    f"{spec.coordinate_tolerance}",
                )
            )
    return failures


def _stroke_width_failures(
    spec: PrimitiveSpec,
    anchor: dict[str, Any],
) -> list[dict[str, str]]:
    stroke = anchor.get("stroke")
    if not isinstance(stroke, dict):
        return [_failure("geometry_drift", "missing stroke geometry")]
    actual = _stroke_width(anchor)
    expected = float(spec.geometry["width"])
    if abs(actual - expected) > spec.coordinate_tolerance:
        return [
            _failure(
                "geometry_drift",
                f"stroke width delta {round(abs(actual - expected), 6)} exceeds "
                f"{spec.coordinate_tolerance}",
            )
        ]
    return []


def _stroke_failures(spec: PrimitiveSpec, anchor: dict[str, Any]) -> list[dict[str, str]]:
    stroke = anchor.get("stroke")
    if not isinstance(stroke, dict):
        return [_failure("geometry_drift", "missing stroke geometry")]
    actual = tuple(
        (float(point.get("x", 0.0)), float(point.get("y", 0.0)))
        for point in stroke.get("centerline", [])
    )
    expected = tuple(
        (float(x), float(y)) for x, y in spec.geometry["centerline"]
    )
    failures = []
    if len(actual) != len(expected):
        failures.append(
            _failure(
                "geometry_drift",
                f"expected {len(expected)} centerline points, got {len(actual)}",
            )
        )
    elif _oriented_line_error(actual, expected) > spec.coordinate_tolerance:
        failures.append(
            _failure(
                "geometry_drift",
                "centerline endpoint distance "
                f"{round(_oriented_line_error(actual, expected), 6)} exceeds "
                f"{spec.coordinate_tolerance}",
            )
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


def _geometry_diff(
    spec: PrimitiveSpec,
    anchor: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "expected": {
            "kinds": list(spec.expected_kinds),
            "type": spec.geometry_type,
            "geometry": _rounded_geometry(spec.geometry),
        },
        "actual": _actual_geometry(anchor),
    }


def _actual_geometry(anchor: dict[str, Any] | None) -> dict[str, Any] | None:
    if anchor is None:
        return None
    circle = anchor.get("circle")
    if isinstance(circle, dict):
        return {
            "kind": anchor.get("kind"),
            "type": "circle",
            "geometry": {
                "cx": round(float(circle.get("cx", 0.0)), 6),
                "cy": round(float(circle.get("cy", 0.0)), 6),
                "r": round(float(circle.get("r", 0.0)), 6),
                "width": round(_stroke_width(anchor), 6)
                if anchor.get("kind") == "stroke_circle"
                else None,
            },
        }
    quad = anchor.get("quad")
    if isinstance(quad, dict):
        return {
            "kind": anchor.get("kind"),
            "type": "quad",
            "geometry": {
                "corners": _rounded_points(
                    (
                        (float(point.get("x", 0.0)), float(point.get("y", 0.0)))
                        for point in quad.get("corners", [])
                    )
                )
            },
        }
    stroke = anchor.get("stroke")
    if isinstance(stroke, dict):
        return {
            "kind": anchor.get("kind"),
            "type": "stroke",
            "geometry": {
                "centerline": _rounded_points(
                    (
                        (float(point.get("x", 0.0)), float(point.get("y", 0.0)))
                        for point in stroke.get("centerline", [])
                    )
                ),
                "width": round(_stroke_width(anchor), 6),
            },
        }
    return {"kind": anchor.get("kind"), "type": "unknown", "geometry": {}}


def _rounded_geometry(geometry: Geometry) -> Geometry:
    rounded: Geometry = {}
    for key, value in geometry.items():
        if isinstance(value, tuple):
            rounded[key] = _rounded_points(value)
        elif isinstance(value, float | int):
            rounded[key] = round(float(value), 6)
        else:
            rounded[key] = value
    return rounded


def _rounded_points(points: Iterable[tuple[float, float]]) -> list[list[float]]:
    return [[round(float(x), 6), round(float(y), 6)] for x, y in points]


def _spec_family(spec: PrimitiveSpec) -> str:
    return spec.family or spec.id


def _failure(category: str, message: str) -> dict[str, str]:
    return {"category": category, "message": message}
