"""Canonical scene helpers and SVG export for primitive anchors."""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from statistics import mean
from typing import Iterable

from curve.anchors import (
    AnchorCandidate,
    AnchorKind,
    Point,
    parallel_spacing_error,
    perspective_grid_consistency_error,
    quality_metric_error,
)
from curve.detection import detect_primitive_anchors
from curve.masks import BinaryMask


SCENE_MANIFEST_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class SvgStyle:
    fill: str = "#0b2d5f"
    stroke: str = "#0b2d5f"
    background: str | None = None


@dataclass(frozen=True)
class Scene:
    width: int
    height: int
    anchors: tuple[AnchorCandidate, ...]
    diagnostics: tuple[dict[str, object], ...] = ()

    def to_svg(self, style: SvgStyle | None = None) -> str:
        return anchors_to_svg(self.anchors, self.width, self.height, style=style)

    def to_debug_svg(self, style: SvgStyle | None = None) -> str:
        return anchors_to_debug_svg(
            self.anchors,
            self.width,
            self.height,
            style=style,
        )

    def to_manifest(self) -> dict[str, object]:
        groups = scene_groups_to_manifest(self.anchors)
        layers = scene_layers_to_manifest(self.anchors)
        return {
            "schema_version": SCENE_MANIFEST_SCHEMA_VERSION,
            "width": self.width,
            "height": self.height,
            "anchor_count": len(self.anchors),
            "anchors": [
                anchor_to_manifest_with_index(anchor, index=index)
                for index, anchor in enumerate(self.anchors)
            ],
            "layers": layers,
            "groups": groups,
            "diagnostics": list(self.diagnostics),
            "metrics": scene_metrics_to_manifest(
                self.anchors,
                groups=groups,
                diagnostics=self.diagnostics,
            ),
        }


def scene_from_mask(mask: BinaryMask, *, min_area: int = 8) -> Scene:
    return Scene(
        width=mask.width,
        height=mask.height,
        anchors=detect_primitive_anchors(mask, min_area=min_area),
    )


def anchors_to_svg(
    anchors: Iterable[AnchorCandidate],
    width: int,
    height: int,
    *,
    style: SvgStyle | None = None,
) -> str:
    style = style or SvgStyle()
    lines = [
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'viewBox="0 0 {width} {height}" width="{width}" height="{height}">'
        )
    ]
    if style.background is not None:
        lines.append(
            f'<rect x="0" y="0" width="{width}" height="{height}" '
            f'fill="{escape(style.background)}" />'
        )
    for anchor in anchors:
        lines.append(f"  {anchor_to_svg_element(anchor, style)}")
    lines.append("</svg>")
    return "\n".join(lines)


def anchors_to_debug_svg(
    anchors: Iterable[AnchorCandidate],
    width: int,
    height: int,
    *,
    style: SvgStyle | None = None,
) -> str:
    style = style or SvgStyle()
    anchor_tuple = tuple(anchors)
    lines = [
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'viewBox="0 0 {width} {height}" width="{width}" height="{height}">'
        )
    ]
    if style.background is not None:
        lines.append(
            f'<rect x="0" y="0" width="{width}" height="{height}" '
            f'fill="{escape(style.background)}" />'
        )
    for index, anchor in enumerate(anchor_tuple):
        anchor_id = f"anchor-{index:04d}"
        lines.append(f'  <g id="{anchor_id}" data-kind="{escape(anchor.kind.value)}">')
        lines.append(f"    {anchor_to_svg_element(anchor, style)}")
        lines.append(f"    {_debug_bounds_element(anchor)}")
        lines.append(f"    {_debug_label_element(anchor, anchor_id)}")
        lines.append("  </g>")
    lines.append("</svg>")
    return "\n".join(lines)


def anchor_to_svg_element(anchor: AnchorCandidate, style: SvgStyle | None = None) -> str:
    style = style or SvgStyle()
    fill = anchor.color or style.fill
    stroke = anchor.color or style.stroke
    if anchor.kind == AnchorKind.CIRCLE and anchor.circle is not None:
        return (
            f'<circle cx="{_fmt(anchor.circle.center.x)}" '
            f'cy="{_fmt(anchor.circle.center.y)}" '
            f'r="{_fmt(anchor.circle.radius)}" '
            f'fill="{escape(fill)}" />'
        )

    if anchor.kind == AnchorKind.STROKE_CIRCLE and anchor.circle is not None:
        width = _stroke_width(anchor)
        return (
            f'<circle cx="{_fmt(anchor.circle.center.x)}" '
            f'cy="{_fmt(anchor.circle.center.y)}" '
            f'r="{_fmt(anchor.circle.radius)}" fill="none" '
            f'stroke="{escape(stroke)}" stroke-width="{_fmt(width)}" />'
        )

    if anchor.kind in {AnchorKind.STROKE_PATH, AnchorKind.STROKE_POLYLINE, AnchorKind.ARC}:
        if anchor.stroke is None:
            return _unsupported_anchor(anchor)
        points = anchor.stroke.centerline
        path = _polyline_path(points)
        width = _stroke_width(anchor)
        cap = escape(anchor.stroke.cap_style)
        join = escape(anchor.stroke.join_style)
        return (
            f'<path d="{path}" fill="none" stroke="{escape(stroke)}" '
            f'stroke-width="{_fmt(width)}" stroke-linecap="{cap}" '
            f'stroke-linejoin="{join}" />'
        )

    if anchor.kind in {AnchorKind.RECT, AnchorKind.ROUNDED_RECT} and anchor.quad is not None:
        min_x, min_y, max_x, max_y = _anchor_bounds(anchor)
        radius = anchor.metrics.get("corner_radius", 0.0)
        return (
            f'<rect x="{_fmt(min_x)}" y="{_fmt(min_y)}" '
            f'width="{_fmt(max_x - min_x)}" height="{_fmt(max_y - min_y)}" '
            f'rx="{_fmt(radius)}" ry="{_fmt(radius)}" fill="{escape(fill)}" />'
        )

    if anchor.kind == AnchorKind.QUAD and anchor.quad is not None:
        points = " ".join(_point_pair(point) for point in anchor.quad.corners)
        return f'<polygon points="{points}" fill="{escape(fill)}" />'

    return _unsupported_anchor(anchor)


def anchor_to_manifest(anchor: AnchorCandidate) -> dict[str, object]:
    return anchor_to_manifest_with_index(anchor, index=None)


def anchor_to_manifest_with_index(
    anchor: AnchorCandidate,
    *,
    index: int | None,
) -> dict[str, object]:
    anchor_id = f"anchor-{index:04d}" if index is not None else None
    data: dict[str, object] = {
        "id": anchor_id,
        "kind": anchor.kind.value,
        "color": anchor.color,
        "layer": _anchor_layer(anchor),
        "confidence": _anchor_confidence(anchor),
        "reserved": {
            "bounds": list(_anchor_bounds(anchor)),
            "reason": _reservation_reason(anchor),
        },
        "provenance": {
            "source": "primitive_anchor_detection",
            "fitting": _anchor_fitting_stage(anchor),
        },
        "export_policy": {
            "editable": anchor.is_simple_shape,
            "debug_label": _debug_label(anchor, anchor_id),
            "cutout_strategy": _cutout_strategy(anchor),
            "mask_eligible": _cutout_mask_eligible(anchor),
        },
        "raster_error": anchor.raster_error,
        "node_count": anchor.node_count,
        "parameter_count": anchor.parameter_count,
        "metrics": dict(sorted(anchor.metrics.items())),
    }
    if anchor.circle is not None:
        data["circle"] = {
            "cx": anchor.circle.center.x,
            "cy": anchor.circle.center.y,
            "r": anchor.circle.radius,
        }
    if anchor.stroke is not None:
        data["stroke"] = {
            "centerline": [
                {"x": point.x, "y": point.y}
                for point in anchor.stroke.centerline
            ],
            "width_samples": list(anchor.stroke.width_samples),
            "is_cutout": anchor.stroke.is_cutout,
            "cap_style": anchor.stroke.cap_style,
            "join_style": anchor.stroke.join_style,
        }
    if anchor.quad is not None:
        data["quad"] = {
            "corners": [
                {"x": point.x, "y": point.y}
                for point in anchor.quad.corners
            ]
        }
    return data


def scene_groups_to_manifest(
    anchors: tuple[AnchorCandidate, ...],
) -> list[dict[str, object]]:
    groups: list[dict[str, object]] = []
    quad_indexes = [
        index
        for index, anchor in enumerate(anchors)
        if anchor.kind == AnchorKind.QUAD and anchor.quad is not None
    ]
    if len(quad_indexes) >= 2:
        quads = tuple(
            quad
            for index in quad_indexes
            if (quad := anchors[index].quad) is not None
        )
        grid_summary = _quad_grid_summary(quads)
        groups.append(
            {
                "kind": AnchorKind.PERSPECTIVE_GRID.value,
                "anchor_indexes": quad_indexes,
                "row_count": grid_summary["row_count"],
                "column_count": grid_summary["column_count"],
                "metrics": {
                    "perspective_grid_consistency_error": perspective_grid_consistency_error(
                        quads
                    ),
                    "vanishing_line_diagnostics": grid_summary[
                        "vanishing_line_diagnostics"
                    ],
                },
            }
        )

    parallel_groups: dict[str, list[int]] = {}
    for index, anchor in enumerate(anchors):
        if anchor.stroke is None or anchor.stroke.parallel_group_id is None:
            continue
        parallel_groups.setdefault(anchor.stroke.parallel_group_id, []).append(index)

    for group_id, indexes in sorted(parallel_groups.items()):
        if len(indexes) < 2:
            continue
        centerlines = [
            anchors[index].stroke.centerline
            for index in indexes
            if anchors[index].stroke is not None
        ]
        groups.append(
            {
                "kind": "parallel_stroke_group",
                "id": group_id,
                "anchor_indexes": indexes,
                "metrics": {
                    "parallel_spacing_error": parallel_spacing_error(centerlines)
                },
            }
        )

    color_groups: dict[str, list[int]] = {}
    for index, anchor in enumerate(anchors):
        if anchor.color is None:
            continue
        color_groups.setdefault(anchor.color, []).append(index)

    for color, indexes in sorted(color_groups.items()):
        if len(indexes) < 2:
            continue
        groups.append(
            {
                "kind": "same_color_fragment_group",
                "id": f"color-{color.removeprefix('#')}",
                "color": color,
                "anchor_indexes": indexes,
                "metrics": {
                    "fragment_count": len(indexes),
                    "merge_candidate": True,
                    "generic_path_count": sum(
                        1
                        for index in indexes
                        if anchors[index].kind == AnchorKind.CUBIC_PATH
                    ),
                },
            }
        )

    return groups


def scene_layers_to_manifest(
    anchors: tuple[AnchorCandidate, ...],
) -> list[dict[str, object]]:
    layer_indexes: dict[str, list[int]] = {}
    for index, anchor in enumerate(anchors):
        layer_indexes.setdefault(_anchor_layer(anchor), []).append(index)
    return [
        {
            "name": name,
            "anchor_indexes": indexes,
            "anchor_count": len(indexes),
        }
        for name, indexes in sorted(layer_indexes.items())
    ]


def scene_metrics_to_manifest(
    anchors: tuple[AnchorCandidate, ...],
    *,
    groups: list[dict[str, object]] | None = None,
    diagnostics: tuple[dict[str, object], ...] = (),
) -> dict[str, object]:
    anchor_count = len(anchors)
    node_count = sum(anchor.node_count for anchor in anchors)
    parameter_count = sum(anchor.parameter_count for anchor in anchors)
    simple_shape_count = sum(1 for anchor in anchors if anchor.is_simple_shape)
    generic_path_count = sum(1 for anchor in anchors if anchor.kind == AnchorKind.CUBIC_PATH)
    cutout_count = sum(
        1
        for anchor in anchors
        if anchor.stroke is not None and anchor.stroke.is_cutout
    )
    simple_shape_ratio = (
        simple_shape_count / anchor_count
        if anchor_count
        else 1.0
    )
    fragmentation_penalty = _fragmentation_penalty(anchors)
    diagnostic_penalty = min(
        sum(1 for diagnostic in diagnostics if diagnostic.get("level") == "warning")
        * 0.05,
        0.5,
    )
    editability_score = max(
        0.0,
        min(
            1.0,
            simple_shape_ratio
            - fragmentation_penalty
            - diagnostic_penalty
            - min(generic_path_count * 0.04, 0.4),
        ),
    )
    return {
        "shape_count": anchor_count,
        "node_count": node_count,
        "parameter_count": parameter_count,
        "simple_shape_count": simple_shape_count,
        "generic_path_count": generic_path_count,
        "cutout_anchor_count": cutout_count,
        "cutout_overlay_count": sum(
            1 for anchor in anchors if _cutout_strategy(anchor) == "overlay_stroke"
        ),
        "negative_mask_candidate_count": sum(
            1 for anchor in anchors if _cutout_mask_eligible(anchor)
        ),
        "group_count": len(groups or []),
        "simple_shape_ratio": round(simple_shape_ratio, 6),
        "fragmentation_penalty": round(fragmentation_penalty, 6),
        "diagnostic_penalty": round(diagnostic_penalty, 6),
        "editability_score": round(editability_score, 6),
        "color_fragment_counts": _color_fragment_counts(anchors),
    }


def _color_fragment_counts(
    anchors: tuple[AnchorCandidate, ...],
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for anchor in anchors:
        if anchor.color is None:
            continue
        counts[anchor.color] = counts.get(anchor.color, 0) + 1
    return dict(sorted(counts.items()))


def _quad_grid_summary(
    quads: tuple[object, ...],
) -> dict[str, object]:
    centers = [_quad_center(quad) for quad in quads if hasattr(quad, "corners")]
    if not centers:
        return {
            "row_count": 0,
            "column_count": 0,
            "vanishing_line_diagnostics": _vanishing_line_diagnostics(quads),
        }
    widths = [
        _quad_axis_span(quad, axis="x")
        for quad in quads
        if hasattr(quad, "corners")
    ]
    heights = [
        _quad_axis_span(quad, axis="y")
        for quad in quads
        if hasattr(quad, "corners")
    ]
    row_tolerance = max(1.0, mean(heights) * 0.6) if heights else 1.0
    column_tolerance = max(1.0, mean(widths) * 0.6) if widths else 1.0
    return {
        "row_count": _cluster_count([center.y for center in centers], row_tolerance),
        "column_count": _cluster_count(
            [center.x for center in centers],
            column_tolerance,
        ),
        "vanishing_line_diagnostics": _vanishing_line_diagnostics(quads),
    }


def _quad_center(quad: object) -> Point:
    corners = getattr(quad, "corners")
    return Point(
        mean(point.x for point in corners),
        mean(point.y for point in corners),
    )


def _quad_axis_span(quad: object, *, axis: str) -> float:
    corners = getattr(quad, "corners")
    values = [getattr(point, axis) for point in corners]
    return max(values) - min(values)


def _cluster_count(values: list[float], tolerance: float) -> int:
    if not values:
        return 0
    clusters = 1
    current = sorted(values)[0]
    for value in sorted(values)[1:]:
        if abs(value - current) > tolerance:
            clusters += 1
            current = value
        else:
            current = (current + value) / 2
    return clusters


def _vanishing_line_diagnostics(quads: tuple[object, ...]) -> dict[str, object]:
    horizontal_pairs = 0
    vertical_pairs = 0
    finite_intersections = 0
    for quad in quads:
        if not hasattr(quad, "corners"):
            continue
        corners = getattr(quad, "corners")
        if len(corners) != 4:
            continue
        top = (corners[0], corners[1])
        right = (corners[1], corners[2])
        bottom = (corners[3], corners[2])
        left = (corners[0], corners[3])
        horizontal_pairs += 1
        vertical_pairs += 1
        if _line_intersection(top, bottom) is not None:
            finite_intersections += 1
        if _line_intersection(left, right) is not None:
            finite_intersections += 1
    return {
        "horizontal_edge_pairs": horizontal_pairs,
        "vertical_edge_pairs": vertical_pairs,
        "finite_intersection_count": finite_intersections,
    }


def _line_intersection(
    first: tuple[Point, Point],
    second: tuple[Point, Point],
) -> Point | None:
    p1, p2 = first
    p3, p4 = second
    denominator = (
        (p1.x - p2.x) * (p3.y - p4.y)
        - (p1.y - p2.y) * (p3.x - p4.x)
    )
    if abs(denominator) < 1e-9:
        return None
    px = (
        (p1.x * p2.y - p1.y * p2.x) * (p3.x - p4.x)
        - (p1.x - p2.x) * (p3.x * p4.y - p3.y * p4.x)
    ) / denominator
    py = (
        (p1.x * p2.y - p1.y * p2.x) * (p3.y - p4.y)
        - (p1.y - p2.y) * (p3.x * p4.y - p3.y * p4.x)
    ) / denominator
    return Point(px, py)


def _fragmentation_penalty(anchors: tuple[AnchorCandidate, ...]) -> float:
    if not anchors:
        return 0.0
    excess_fragments = sum(
        max(0, count - 1)
        for count in _color_fragment_counts(anchors).values()
    )
    return min(excess_fragments / max(len(anchors), 1) * 0.5, 0.5)


def _anchor_layer(anchor: AnchorCandidate) -> str:
    if anchor.stroke is not None and anchor.stroke.is_cutout:
        return "cutout_overlays"
    if anchor.kind in {
        AnchorKind.STROKE_CIRCLE,
        AnchorKind.STROKE_POLYLINE,
        AnchorKind.STROKE_PATH,
        AnchorKind.ARC,
    }:
        return "strokes"
    if anchor.kind in {
        AnchorKind.CIRCLE,
        AnchorKind.RECT,
        AnchorKind.ROUNDED_RECT,
        AnchorKind.QUAD,
    }:
        return "filled_primitives"
    return "generic_paths"


def _anchor_confidence(anchor: AnchorCandidate) -> float:
    metric_error = quality_metric_error(anchor.metrics)
    score = 1.0 - min(anchor.raster_error + metric_error * 0.1, 1.0)
    if not anchor.is_simple_shape:
        score -= 0.2
    return round(max(0.0, min(score, 1.0)), 6)


def _reservation_reason(anchor: AnchorCandidate) -> str:
    if anchor.is_simple_shape:
        return "simple_shape_anchor"
    return "generic_fallback"


def _anchor_fitting_stage(anchor: AnchorCandidate) -> str:
    if anchor.kind == AnchorKind.CUBIC_PATH:
        return "fallback_path"
    return "primitive_fit"


def _cutout_strategy(anchor: AnchorCandidate) -> str | None:
    if anchor.stroke is not None and anchor.stroke.is_cutout:
        return "overlay_stroke"
    return None


def _cutout_mask_eligible(anchor: AnchorCandidate) -> bool:
    return bool(anchor.stroke is not None and anchor.stroke.is_cutout)


def _anchor_bounds(anchor: AnchorCandidate) -> tuple[float, float, float, float]:
    if anchor.circle is not None:
        center = anchor.circle.center
        radius = anchor.circle.radius
        return (
            center.x - radius,
            center.y - radius,
            center.x + radius,
            center.y + radius,
        )
    if anchor.stroke is not None and anchor.stroke.centerline:
        xs = [point.x for point in anchor.stroke.centerline]
        ys = [point.y for point in anchor.stroke.centerline]
        pad = _stroke_width(anchor) / 2
        return (min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad)
    if anchor.quad is not None:
        xs = [point.x for point in anchor.quad.corners]
        ys = [point.y for point in anchor.quad.corners]
        return (min(xs), min(ys), max(xs), max(ys))
    return (0.0, 0.0, 0.0, 0.0)


def _debug_label(anchor: AnchorCandidate, anchor_id: str | None) -> str:
    prefix = anchor_id or "anchor"
    return f"{prefix}:{anchor.kind.value}:{_anchor_confidence(anchor)}"


def _debug_bounds_element(anchor: AnchorCandidate) -> str:
    min_x, min_y, max_x, max_y = _anchor_bounds(anchor)
    return (
        f'<rect x="{_fmt(min_x)}" y="{_fmt(min_y)}" '
        f'width="{_fmt(max_x - min_x)}" height="{_fmt(max_y - min_y)}" '
        f'fill="none" stroke="#ff00ff" stroke-width="1" '
        f'stroke-dasharray="2 2" />'
    )


def _debug_label_element(anchor: AnchorCandidate, anchor_id: str) -> str:
    min_x, min_y, _, _ = _anchor_bounds(anchor)
    return (
        f'<text x="{_fmt(min_x)}" y="{_fmt(max(min_y - 2, 0))}" '
        f'font-size="4" fill="#ff00ff">'
        f'{escape(_debug_label(anchor, anchor_id))}</text>'
    )


def _polyline_path(points: tuple[Point, ...]) -> str:
    if not points:
        return ""
    first, *rest = points
    commands = [f"M {_fmt(first.x)} {_fmt(first.y)}"]
    commands.extend(f"L {_fmt(point.x)} {_fmt(point.y)}" for point in rest)
    return " ".join(commands)


def _point_pair(point: Point) -> str:
    return f"{_fmt(point.x)},{_fmt(point.y)}"


def _stroke_width(anchor: AnchorCandidate) -> float:
    if anchor.stroke is not None and anchor.stroke.width_samples:
        return mean(anchor.stroke.width_samples)
    return 1.0


def _unsupported_anchor(anchor: AnchorCandidate) -> str:
    return (
        f'<!-- unsupported anchor kind="{escape(anchor.kind.value)}" '
        f'nodes="{anchor.node_count}" -->'
    )


def _fmt(value: float) -> str:
    rounded = round(value, 3)
    if rounded == int(rounded):
        return str(int(rounded))
    return f"{rounded:.3f}".rstrip("0").rstrip(".")
