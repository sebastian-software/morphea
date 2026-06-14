"""Canonical scene helpers and SVG export for primitive anchors."""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from math import cos, degrees, sin, sqrt
from statistics import mean
from typing import Iterable

from morphea.anchors import (
    AnchorCandidate,
    AnchorKind,
    ArcAnchor,
    EllipseAnchor,
    PathAnchor,
    Point,
    QuadAnchor,
    parallel_spacing_error,
    perspective_grid_consistency_error,
    quality_metric_error,
    semantic_anchor_score,
    simple_shape_priority_bonus,
)
from morphea.detection import detect_primitive_anchors
from morphea.masks import BinaryMask


SCENE_MANIFEST_SCHEMA_VERSION = 1
TEXT_LIKE_FALLBACK_MAX_BOUNDS_AREA = 384.0
TEXT_LIKE_FALLBACK_MAX_SPAN = 32.0


@dataclass(frozen=True)
class SvgStyle:
    fill: str = "#0b2d5f"
    stroke: str = "#0b2d5f"
    background: str | None = None
    cutout_strategy: str = "overlay_stroke"


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
                width=self.width,
                height=self.height,
            ),
        }


def scene_from_mask(mask: BinaryMask, *, min_area: int = 8) -> Scene:
    return Scene(
        width=mask.width,
        height=mask.height,
        anchors=merge_auto_mergeable_same_color_fragments(
            promote_occluded_rect_fragment_groups(
                promote_occluded_rect_primitives(
                    detect_primitive_anchors(mask, min_area=min_area)
                )
            )
        ),
    )


def promote_occluded_rect_primitives(
    anchors: tuple[AnchorCandidate, ...],
) -> tuple[AnchorCandidate, ...]:
    """Promote simple occluded rect-like quads back to full rects.

    This only applies when a different-color filled primitive overlaps the
    quad's bounds. The visible pixels can look like an L-shaped quad, but the
    editable representation is better as the full base rect drawn before the
    occluding primitive.
    """

    promoted: list[AnchorCandidate] = []
    for index, anchor in enumerate(anchors):
        promoted.append(_promoted_occluded_rect(anchor, anchors, index=index) or anchor)
    return tuple(promoted)


def merge_auto_mergeable_same_color_fragments(
    anchors: tuple[AnchorCandidate, ...],
) -> tuple[AnchorCandidate, ...]:
    """Conservatively merge compact same-color rect fragments."""

    color_groups: dict[str, list[int]] = {}
    for index, anchor in enumerate(anchors):
        if anchor.color is None:
            continue
        color_groups.setdefault(anchor.color, []).append(index)

    replacements: dict[int, AnchorCandidate] = {}
    removed: set[int] = set()
    for indexes in color_groups.values():
        if len(indexes) < 2:
            continue
        fragments = tuple(anchors[index] for index in indexes)
        merged = _merged_rect_fragment_candidate(fragments)
        if merged is None:
            continue
        first, *rest = indexes
        replacements[first] = merged
        removed.update(rest)

    if not replacements:
        return anchors
    return tuple(
        replacements.get(index, anchor)
        for index, anchor in enumerate(anchors)
        if index not in removed
    )


def promote_occluded_rect_fragment_groups(
    anchors: tuple[AnchorCandidate, ...],
) -> tuple[AnchorCandidate, ...]:
    """Promote compact same-color rect fragments hidden by an occluder.

    When a different-color primitive cuts through a filled rect, connected
    component analysis only sees the visible fragments. SVG export should still
    prefer the editable base rect drawn before the occluder instead of exposing
    artificial transparent gaps between fragments.
    """

    color_groups: dict[str, list[int]] = {}
    for index, anchor in enumerate(anchors):
        if anchor.color is None:
            continue
        color_groups.setdefault(anchor.color, []).append(index)

    replacements: dict[int, AnchorCandidate] = {}
    removed: set[int] = set()
    for indexes in color_groups.values():
        if len(indexes) < 2:
            continue
        fragments = tuple(anchors[index] for index in indexes)
        promoted = _promoted_occluded_rect_fragments(fragments, anchors)
        if promoted is None:
            continue
        first, *rest = indexes
        replacements[first] = promoted
        removed.update(rest)

    if not replacements:
        return anchors
    return tuple(
        replacements.get(index, anchor)
        for index, anchor in enumerate(anchors)
        if index not in removed
    )


def _promoted_occluded_rect(
    anchor: AnchorCandidate,
    anchors: tuple[AnchorCandidate, ...],
    *,
    index: int,
) -> AnchorCandidate | None:
    if anchor.kind != AnchorKind.QUAD or anchor.quad is None:
        return None
    if anchor.color is None:
        return None
    if float(anchor.metrics.get("quad_corner_consistency_error", 0.0)) < 0.08:
        return None
    bounds = _anchor_bounds(anchor)
    occluders = [
        other
        for other_index, other in enumerate(anchors)
        if other_index != index
        and other.color is not None
        and other.color != anchor.color
        and _is_filled_primitive(other)
        and _bounds_intersection_area(bounds, _anchor_bounds(other)) > 0.0
    ]
    if not occluders:
        return None
    min_x, min_y, max_x, max_y = bounds
    metrics = dict(anchor.metrics)
    metrics["occluded_rect_promotion"] = 1.0
    metrics["occluding_primitive_count"] = float(len(occluders))
    return AnchorCandidate(
        kind=AnchorKind.RECT,
        raster_error=anchor.raster_error,
        node_count=4,
        parameter_count=4,
        color=anchor.color,
        quad=QuadAnchor(
            corners=(
                Point(min_x, min_y),
                Point(max_x, min_y),
                Point(max_x, max_y),
                Point(min_x, max_y),
            )
        ),
        metrics=metrics,
    )


def _promoted_occluded_rect_fragments(
    fragments: tuple[AnchorCandidate, ...],
    anchors: tuple[AnchorCandidate, ...],
) -> AnchorCandidate | None:
    if len(fragments) < 2:
        return None
    color = fragments[0].color
    if color is None or any(fragment.color != color for fragment in fragments):
        return None
    # Straight occluders slice a rect into axis-aligned rect fragments, but a
    # curved occluder leaves curve-edged quads; both promote back to the rect.
    if any(
        not _axis_aligned_rect_fragment(fragment)
        and not (fragment.kind == AnchorKind.QUAD and fragment.quad is not None)
        for fragment in fragments
    ):
        return None

    merge_plan = _same_color_merge_plan(fragments, list(range(len(fragments))))
    if not merge_plan["auto_merge_allowed"]:
        return None
    combined_bounds = tuple(float(value) for value in merge_plan["bounds"])
    combined_area = _bounds_area(combined_bounds)
    fragment_area = sum(_bounds_area(_anchor_bounds(fragment)) for fragment in fragments)
    occluded_area = max(combined_area - fragment_area, 0.0)

    occluders = [
        anchor
        for anchor in anchors
        if anchor.color is not None
        and anchor.color != color
        and _bounds_intersection_area(_anchor_bounds(anchor), combined_bounds) > 0.0
    ]
    if not occluders:
        return None
    occluder_area = sum(
        _bounds_intersection_area(_anchor_bounds(anchor), combined_bounds)
        for anchor in occluders
    )
    if occluded_area > 0.0:
        occlusion_coverage = min(occluder_area / occluded_area, 1.0)
        if occlusion_coverage < 0.6:
            return None
    else:
        # Curve-cut fragments have overlapping bounding boxes, so the box
        # arithmetic reports no occluded area; require a meaningful occluder
        # footprint inside the combined bounds instead.
        occlusion_coverage = 1.0
        if combined_area <= 0.0 or occluder_area < combined_area * 0.04:
            return None

    min_x, min_y, max_x, max_y = combined_bounds
    return AnchorCandidate(
        kind=AnchorKind.RECT,
        raster_error=max(fragment.raster_error for fragment in fragments),
        node_count=4,
        parameter_count=4,
        color=color,
        quad=QuadAnchor(
            corners=(
                Point(min_x, min_y),
                Point(max_x, min_y),
                Point(max_x, max_y),
                Point(min_x, max_y),
            )
        ),
        metrics={
            "occluded_rect_fragment_promotion": 1.0,
            "source_fragment_count": float(len(fragments)),
            "occluding_primitive_count": float(len(occluders)),
            "occlusion_coverage": round(occlusion_coverage, 6),
            "source_fragment_node_count": float(
                sum(fragment.node_count for fragment in fragments)
            ),
            "source_fragment_parameter_count": float(
                sum(fragment.parameter_count for fragment in fragments)
            ),
        },
    )


def anchors_to_svg(
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
    if style.cutout_strategy == "negative_mask" and any(
        _cutout_mask_eligible(anchor) for anchor in anchor_tuple
    ):
        lines.extend(_negative_cutout_mask_elements(anchor_tuple, width, height, style))
    else:
        for anchor in anchor_tuple:
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


def anchor_to_svg_element(
    anchor: AnchorCandidate,
    style: SvgStyle | None = None,
    *,
    color_override: str | None = None,
) -> str:
    style = style or SvgStyle()
    fill = color_override or anchor.color or style.fill
    stroke = color_override or anchor.color or style.stroke
    if anchor.kind == AnchorKind.CIRCLE and anchor.circle is not None:
        return (
            f'<circle cx="{_fmt(anchor.circle.center.x)}" '
            f'cy="{_fmt(anchor.circle.center.y)}" '
            f'r="{_fmt(anchor.circle.radius)}" '
            f'fill="{escape(fill)}" />'
        )

    if anchor.kind == AnchorKind.ELLIPSE and anchor.ellipse is not None:
        return (
            f'<ellipse cx="{_fmt(anchor.ellipse.center.x)}" '
            f'cy="{_fmt(anchor.ellipse.center.y)}" '
            f'rx="{_fmt(anchor.ellipse.rx)}" ry="{_fmt(anchor.ellipse.ry)}" '
            f"{_ellipse_rotation_attr(anchor.ellipse)}"
            f'fill="{escape(fill)}" />'
        )

    if anchor.kind == AnchorKind.STROKE_ELLIPSE and anchor.ellipse is not None:
        width = _stroke_width(anchor)
        return (
            f'<ellipse cx="{_fmt(anchor.ellipse.center.x)}" '
            f'cy="{_fmt(anchor.ellipse.center.y)}" '
            f'rx="{_fmt(anchor.ellipse.rx)}" ry="{_fmt(anchor.ellipse.ry)}" '
            f"{_ellipse_rotation_attr(anchor.ellipse)}"
            f'fill="none" stroke="{escape(stroke)}" '
            f'stroke-width="{_fmt(width)}" />'
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
        if anchor.kind == AnchorKind.ARC and anchor.arc is not None:
            path = _arc_path(anchor.arc)
        elif anchor.stroke.closed:
            path = _closed_polyline_path(anchor.stroke.centerline)
        elif (
            anchor.kind == AnchorKind.STROKE_PATH
            and len(anchor.stroke.centerline) >= 3
        ):
            path = _smooth_curve_path(anchor.stroke.centerline)
        else:
            path = _polyline_path(anchor.stroke.centerline)
        width = _stroke_width(anchor)
        cap = escape(anchor.stroke.cap_style)
        join = escape(anchor.stroke.join_style)
        return (
            f'<path d="{path}" fill="none" stroke="{escape(stroke)}" '
            f'stroke-width="{_fmt(width)}" stroke-linecap="{cap}" '
            f'stroke-linejoin="{join}" />'
        )

    if anchor.kind in {AnchorKind.RECT, AnchorKind.ROUNDED_RECT} and anchor.quad is not None:
        min_x, min_y, width, height = _rect_svg_box(anchor)
        radius = anchor.metrics.get("corner_radius", 0.0)
        rendering = (
            ' shape-rendering="crispEdges"'
            if radius == 0.0 and _integer_axis_aligned_quad(anchor)
            else ""
        )
        return (
            f'<rect x="{_fmt(min_x)}" y="{_fmt(min_y)}" '
            f'width="{_fmt(width)}" height="{_fmt(height)}" '
            f'rx="{_fmt(radius)}" ry="{_fmt(radius)}" fill="{escape(fill)}"'
            f"{rendering} />"
        )

    if anchor.kind == AnchorKind.QUAD and anchor.quad is not None:
        points = " ".join(_point_pair(point) for point in anchor.quad.corners)
        return f'<polygon points="{points}" fill="{escape(fill)}" />'

    if anchor.kind == AnchorKind.CUBIC_PATH and anchor.path is not None:
        if anchor.path.controls is not None:
            path_data = _closed_bezier_path(
                anchor.path.points,
                anchor.path.controls,
            )
        else:
            path_data = _closed_smooth_path(anchor.path.points)
        for hole_points, hole_controls in anchor.path.holes:
            path_data += " " + _closed_bezier_path(hole_points, hole_controls)
        fill_rule = ' fill-rule="evenodd"' if anchor.path.holes else ""
        return f'<path d="{path_data}" fill="{escape(fill)}"{fill_rule} />'

    return _unsupported_anchor(anchor)


def _negative_cutout_mask_elements(
    anchors: tuple[AnchorCandidate, ...],
    width: int,
    height: int,
    style: SvgStyle,
) -> list[str]:
    mask_id = "morphea-cutout-mask"
    lines = [
        "  <defs>",
        f'    <mask id="{mask_id}" maskUnits="userSpaceOnUse">',
        f'      <rect x="0" y="0" width="{width}" height="{height}" fill="white" />',
    ]
    for anchor in anchors:
        if _cutout_mask_eligible(anchor):
            lines.append(
                f"      {anchor_to_svg_element(anchor, style, color_override='black')}"
            )
    lines.extend(["    </mask>", "  </defs>", f'  <g mask="url(#{mask_id})">'])
    for anchor in anchors:
        if not _cutout_mask_eligible(anchor):
            lines.append(f"    {anchor_to_svg_element(anchor, style)}")
    lines.append("  </g>")
    return lines


def anchor_to_manifest(anchor: AnchorCandidate) -> dict[str, object]:
    return anchor_to_manifest_with_index(anchor, index=None)


def anchor_to_manifest_with_index(
    anchor: AnchorCandidate,
    *,
    index: int | None,
) -> dict[str, object]:
    anchor_id = f"anchor-{index:04d}" if index is not None else None
    source_mask_id = f"mask-{index:04d}" if index is not None else None
    bounds = list(_anchor_bounds(anchor))
    data: dict[str, object] = {
        "id": anchor_id,
        "kind": anchor.kind.value,
        "color": anchor.color,
        "layer": _anchor_layer(anchor),
        "confidence": _anchor_confidence(anchor),
        "reserved": {
            "bounds": bounds,
            "reason": _reservation_reason(anchor),
        },
        "source_mask": {
            "id": source_mask_id,
            "source": "reserved_bounds",
            "bounds": bounds,
            "bounds_area": round(_bounds_area(bounds), 6),
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
        "metrics": _anchor_manifest_metrics(anchor),
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
            "closed": anchor.stroke.closed,
        }
    if anchor.quad is not None:
        data["quad"] = {
            "corners": [
                {"x": point.x, "y": point.y}
                for point in anchor.quad.corners
            ]
        }
    if anchor.path is not None:
        data["path"] = {
            "points": [
                {"x": point.x, "y": point.y}
                for point in anchor.path.points
            ],
            "closed": anchor.path.closed,
            "node_count": len(anchor.path.points),
            "fallback_reason": anchor.path.fallback_reason,
        }
        if anchor.path.controls is not None:
            data["path"]["controls"] = [
                [
                    {"x": control1.x, "y": control1.y},
                    {"x": control2.x, "y": control2.y},
                ]
                for control1, control2 in anchor.path.controls
            ]
        if anchor.path.holes:
            data["path"]["holes"] = [
                {
                    "points": [
                        {"x": point.x, "y": point.y} for point in hole_points
                    ],
                    "controls": [
                        [
                            {"x": control1.x, "y": control1.y},
                            {"x": control2.x, "y": control2.y},
                        ]
                        for control1, control2 in hole_controls
                    ],
                }
                for hole_points, hole_controls in anchor.path.holes
            ]
    if anchor.ellipse is not None:
        data["ellipse"] = {
            "cx": anchor.ellipse.center.x,
            "cy": anchor.ellipse.center.y,
            "rx": anchor.ellipse.rx,
            "ry": anchor.ellipse.ry,
            "rotation": anchor.ellipse.rotation,
        }
    if anchor.arc is not None:
        data["arc"] = {
            "cx": anchor.arc.center.x,
            "cy": anchor.arc.center.y,
            "r": anchor.arc.radius,
            "theta_start": anchor.arc.theta_start,
            "theta_end": anchor.arc.theta_end,
            "sweep": anchor.arc.sweep,
            "large_arc": anchor.arc.large_arc,
        }
    return data


def _anchor_manifest_metrics(anchor: AnchorCandidate) -> dict[str, float]:
    metrics = dict(anchor.metrics)
    metrics["simple_shape_priority_bonus"] = simple_shape_priority_bonus(anchor)
    metrics["semantic_anchor_score"] = semantic_anchor_score(anchor)
    return dict(sorted(metrics.items()))


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
    groups.extend(_auto_parallel_stroke_groups(anchors))

    color_groups: dict[str, list[int]] = {}
    for index, anchor in enumerate(anchors):
        if anchor.color is None:
            continue
        color_groups.setdefault(anchor.color, []).append(index)

    for color, indexes in sorted(color_groups.items()):
        if len(indexes) < 2:
            continue
        merge_plan = _same_color_merge_plan(anchors, indexes)
        groups.append(
            {
                "kind": "same_color_fragment_group",
                "id": f"color-{color.removeprefix('#')}",
                "color": color,
                "anchor_indexes": indexes,
                "merge_plan": merge_plan,
                "metrics": {
                    "fragment_count": len(indexes),
                    "merge_candidate": True,
                    "combined_bounds_area": merge_plan["combined_bounds_area"],
                    "fragment_bounds_area": merge_plan["fragment_bounds_area"],
                    "bounds_fill_ratio": merge_plan["bounds_fill_ratio"],
                    "generic_path_count": sum(
                        1
                        for index in indexes
                        if anchors[index].kind == AnchorKind.CUBIC_PATH
                    ),
                },
            }
        )

    groups.extend(_text_like_fragment_groups(anchors, groups))
    groups.extend(_primitive_contact_groups(anchors))
    groups.extend(_occluded_fragment_groups(anchors, groups))

    reservation_indexes = [
        index
        for index, anchor in enumerate(anchors)
        if _reservation_reason(anchor) == "simple_shape_anchor"
    ]
    if reservation_indexes:
        groups.append(
            {
                "kind": "primitive_anchor_reservation",
                "anchor_indexes": reservation_indexes,
                "metrics": {
                    "reserved_anchor_count": len(reservation_indexes),
                    "reserved_bounds_area": round(
                        _reserved_bounds_area(
                            tuple(anchors[index] for index in reservation_indexes)
                        ),
                        6,
                    ),
                },
            }
        )

    return groups


def _auto_parallel_stroke_groups(
    anchors: tuple[AnchorCandidate, ...],
) -> list[dict[str, object]]:
    buckets: dict[tuple[str, str], list[int]] = {}
    for index, anchor in enumerate(anchors):
        if anchor.stroke is None or anchor.stroke.parallel_group_id is not None:
            continue
        if anchor.kind not in {AnchorKind.STROKE_POLYLINE, AnchorKind.ARC}:
            continue
        if anchor.stroke.is_cutout or len(anchor.stroke.centerline) < 2:
            continue
        orientation = _stroke_orientation_bucket(anchor.stroke.centerline)
        if orientation is None:
            continue
        buckets.setdefault((anchor.color or "#000000", orientation), []).append(index)

    groups: list[dict[str, object]] = []
    for (color, orientation), indexes in sorted(buckets.items()):
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
                "id": f"auto-{color.removeprefix('#')}-{orientation}",
                "color": color,
                "orientation": orientation,
                "anchor_indexes": indexes,
                "metrics": {
                    "parallel_spacing_error": parallel_spacing_error(centerlines)
                },
            }
        )
    return groups


def _stroke_orientation_bucket(points: tuple[Point, ...]) -> str | None:
    start = points[0]
    end = points[-1]
    dx = end.x - start.x
    dy = end.y - start.y
    if abs(dx) < 1e-6 and abs(dy) < 1e-6:
        return None
    if abs(dx) >= abs(dy) * 2:
        return "horizontal"
    if abs(dy) >= abs(dx) * 2:
        return "vertical"
    return "diagonal_pos" if dx * dy >= 0 else "diagonal_neg"


def _primitive_contact_groups(
    anchors: tuple[AnchorCandidate, ...],
) -> list[dict[str, object]]:
    groups: list[dict[str, object]] = []
    for first_index, first in enumerate(anchors):
        for second_index in range(first_index + 1, len(anchors)):
            second = anchors[second_index]
            if first.color is None or second.color is None:
                continue
            if first.color == second.color:
                continue
            first_bounds = _anchor_bounds(first)
            second_bounds = _anchor_bounds(second)
            gap = _bounds_gap(first_bounds, second_bounds)
            intersection = _bounds_intersection_area(first_bounds, second_bounds)
            if gap > 1.0 and intersection <= 0.0:
                continue
            relation = "overlapping" if intersection > 0.0 else "touching"
            groups.append(
                {
                    "kind": "primitive_contact_pair",
                    "anchor_indexes": [first_index, second_index],
                    "relation": relation,
                    "separation_policy": _contact_separation_policy(
                        first,
                        second,
                        relation=relation,
                    ),
                    "colors": [first.color, second.color],
                    "metrics": {
                        "bounds_gap": round(gap, 6),
                        "bounds_iou": round(
                            _bounds_iou(first_bounds, second_bounds),
                            6,
                        ),
                    },
                }
            )
    return groups


def _occluded_fragment_groups(
    anchors: tuple[AnchorCandidate, ...],
    groups: list[dict[str, object]],
) -> list[dict[str, object]]:
    occlusion_groups: list[dict[str, object]] = []
    for group in groups:
        if group.get("kind") != "same_color_fragment_group":
            continue
        indexes = [
            int(index)
            for index in group.get("anchor_indexes", [])
            if isinstance(index, int)
        ]
        if len(indexes) < 2:
            continue
        merge_plan = group.get("merge_plan")
        if not isinstance(merge_plan, dict):
            continue
        if not bool(merge_plan.get("auto_merge_allowed")):
            continue
        combined_area = float(merge_plan.get("combined_bounds_area", 0.0))
        fragment_area = float(merge_plan.get("fragment_bounds_area", 0.0))
        if combined_area <= 0.0 or fragment_area >= combined_area:
            continue
        bounds_value = merge_plan.get("bounds")
        if not isinstance(bounds_value, list) or len(bounds_value) != 4:
            continue
        combined_bounds = tuple(float(value) for value in bounds_value)
        fragment_set = set(indexes)
        base_color = group.get("color")
        occluders = [
            index
            for index, anchor in enumerate(anchors)
            if index not in fragment_set
            and anchor.color != base_color
            and _bounds_intersection_area(_anchor_bounds(anchor), combined_bounds) > 0.0
        ]
        if not occluders:
            continue
        fragments = tuple(anchors[index] for index in indexes)
        occlusion_groups.append(
            {
                "kind": "occluded_primitive_group",
                "anchor_indexes": indexes + occluders,
                "fragment_anchor_indexes": indexes,
                "occluder_anchor_indexes": occluders,
                "base_color": base_color,
                "occluder_colors": [
                    anchors[index].color for index in occluders
                ],
                "target_kind": (
                    "rect"
                    if all(_axis_aligned_rect_fragment(fragment) for fragment in fragments)
                    else "compound_shape"
                ),
                "draw_order": "base_then_occluder",
                "occlusion_policy": "visible_fragments_with_ordered_occluder",
                "metrics": {
                    "fragment_count": len(indexes),
                    "occluder_count": len(occluders),
                    "bounds_fill_ratio": merge_plan.get("bounds_fill_ratio", 0.0),
                    "occluded_bounds_area": round(combined_area - fragment_area, 6),
                },
            }
        )
    return occlusion_groups


def _contact_separation_policy(
    first: AnchorCandidate,
    second: AnchorCandidate,
    *,
    relation: str,
) -> str:
    if relation == "overlapping" and _is_filled_primitive(first) and _is_filled_primitive(second):
        return "ordered_overlap"
    return "separate_by_color"


def _is_filled_primitive(anchor: AnchorCandidate) -> bool:
    return anchor.kind in {
        AnchorKind.CIRCLE,
        AnchorKind.ELLIPSE,
        AnchorKind.RECT,
        AnchorKind.ROUNDED_RECT,
        AnchorKind.QUAD,
    }


def _same_color_merge_plan(
    anchors: tuple[AnchorCandidate, ...],
    indexes: list[int],
) -> dict[str, object]:
    fragment_bounds = [_anchor_bounds(anchors[index]) for index in indexes]
    min_x = min(bounds[0] for bounds in fragment_bounds)
    min_y = min(bounds[1] for bounds in fragment_bounds)
    max_x = max(bounds[2] for bounds in fragment_bounds)
    max_y = max(bounds[3] for bounds in fragment_bounds)
    combined_bounds = (min_x, min_y, max_x, max_y)
    combined_bounds_area = _bounds_area(combined_bounds)
    fragment_bounds_area = sum(_bounds_area(bounds) for bounds in fragment_bounds)
    bounds_fill_ratio = (
        min(fragment_bounds_area / combined_bounds_area, 1.0)
        if combined_bounds_area > 0
        else 0.0
    )
    auto_merge_allowed = bounds_fill_ratio >= 0.55
    merge_action = (
        "merge_adjacent_fragments"
        if auto_merge_allowed
        else "review_as_separate_fragments"
    )
    decision_reason = (
        "compact_same_color_bounds"
        if auto_merge_allowed
        else "sparse_same_color_bounds"
    )
    return {
        "action": merge_action,
        "auto_merge_allowed": auto_merge_allowed,
        "decision_reason": decision_reason,
        "target_kind": "compound_shape",
        "bounds": list(combined_bounds),
        "fragment_bounds": [list(bounds) for bounds in fragment_bounds],
        "combined_bounds_area": round(combined_bounds_area, 6),
        "fragment_bounds_area": round(fragment_bounds_area, 6),
        "bounds_fill_ratio": round(bounds_fill_ratio, 6),
    }


def _text_like_fragment_groups(
    anchors: tuple[AnchorCandidate, ...],
    groups: list[dict[str, object]],
) -> list[dict[str, object]]:
    text_groups: list[dict[str, object]] = []
    for group in groups:
        if not _is_text_like_fragment_group(group):
            continue
        anchor_indexes = [
            int(index)
            for index in group.get("anchor_indexes", [])
            if isinstance(index, int) and 0 <= index < len(anchors)
        ]
        candidate_fallback_indexes = [
            index
            for index in anchor_indexes
            if anchors[index].kind == AnchorKind.CUBIC_PATH
        ]
        fallback_indexes = [
            index
            for index in candidate_fallback_indexes
            if _is_text_like_fallback_anchor(anchors[index])
        ]
        if not fallback_indexes:
            continue
        metrics = group.get("metrics")
        metrics = metrics if isinstance(metrics, dict) else {}
        text_groups.append(
            {
                "kind": "text_like_fragment_group",
                "id": f"text-{str(group.get('id', 'fragments'))}",
                "color": group.get("color"),
                "anchor_indexes": anchor_indexes,
                "fallback_anchor_indexes": fallback_indexes,
                "metrics": {
                    "fragment_count": len(anchor_indexes),
                    "fallback_path_count": len(fallback_indexes),
                    "candidate_fallback_path_count": len(
                        candidate_fallback_indexes
                    ),
                    "excluded_fallback_path_count": (
                        len(candidate_fallback_indexes) - len(fallback_indexes)
                    ),
                    "bounds_fill_ratio": metrics.get("bounds_fill_ratio"),
                    "combined_bounds_area": metrics.get("combined_bounds_area"),
                },
                "source_group_id": group.get("id"),
            }
        )
    return text_groups


def _is_text_like_fallback_anchor(anchor: AnchorCandidate) -> bool:
    if anchor.kind != AnchorKind.CUBIC_PATH:
        return False
    min_x, min_y, max_x, max_y = _anchor_bounds(anchor)
    width = max_x - min_x
    height = max_y - min_y
    if width <= 0.0 or height <= 0.0:
        return False
    return (
        max(width, height) <= TEXT_LIKE_FALLBACK_MAX_SPAN
        and width * height <= TEXT_LIKE_FALLBACK_MAX_BOUNDS_AREA
    )


def _is_text_like_fragment_group(group: dict[str, object]) -> bool:
    if group.get("kind") != "same_color_fragment_group":
        return False
    metrics = group.get("metrics")
    merge_plan = group.get("merge_plan")
    if not isinstance(metrics, dict) or not isinstance(merge_plan, dict):
        return False
    bounds = merge_plan.get("bounds")
    if (
        not isinstance(bounds, list)
        or len(bounds) != 4
        or not all(isinstance(value, (int, float)) for value in bounds)
    ):
        return False
    fragment_count = metrics.get("fragment_count")
    generic_path_count = metrics.get("generic_path_count")
    bounds_fill_ratio = metrics.get("bounds_fill_ratio")
    if (
        not isinstance(fragment_count, int)
        or not isinstance(generic_path_count, int)
        or not isinstance(bounds_fill_ratio, (int, float))
    ):
        return False
    min_x, min_y, max_x, max_y = (float(value) for value in bounds)
    width = max_x - min_x
    height = max_y - min_y
    if height <= 0.0:
        return False
    return (
        fragment_count >= 20
        and generic_path_count >= 8
        and float(bounds_fill_ratio) <= 0.25
        and width / height >= 4.0
    )


def _merged_rect_fragment_candidate(
    fragments: tuple[AnchorCandidate, ...],
) -> AnchorCandidate | None:
    if not fragments:
        return None
    color = fragments[0].color
    if color is None or any(fragment.color != color for fragment in fragments):
        return None
    if any(not _axis_aligned_rect_fragment(fragment) for fragment in fragments):
        return None
    merge_plan = _same_color_merge_plan(
        fragments,
        list(range(len(fragments))),
    )
    if not merge_plan["auto_merge_allowed"]:
        return None
    combined_bounds = tuple(float(value) for value in merge_plan["bounds"])
    combined_area = _bounds_area(combined_bounds)
    fragment_area = sum(_bounds_area(_anchor_bounds(fragment)) for fragment in fragments)
    if combined_area <= 0 or abs(fragment_area - combined_area) > 1e-6:
        return None
    min_x, min_y, max_x, max_y = combined_bounds
    return AnchorCandidate(
        kind=AnchorKind.RECT,
        raster_error=max(fragment.raster_error for fragment in fragments),
        node_count=4,
        parameter_count=4,
        color=color,
        quad=QuadAnchor(
            corners=(
                Point(min_x, min_y),
                Point(max_x, min_y),
                Point(max_x, max_y),
                Point(min_x, max_y),
            )
        ),
        metrics={
            "merged_fragment_count": float(len(fragments)),
            "merge_bounds_fill_ratio": float(merge_plan["bounds_fill_ratio"]),
            "source_fragment_node_count": float(
                sum(fragment.node_count for fragment in fragments)
            ),
            "source_fragment_parameter_count": float(
                sum(fragment.parameter_count for fragment in fragments)
            ),
        },
    )


def _axis_aligned_rect_fragment(anchor: AnchorCandidate) -> bool:
    if anchor.kind != AnchorKind.RECT or anchor.quad is None:
        return False
    min_x, min_y, max_x, max_y = _anchor_bounds(anchor)
    expected = (
        Point(min_x, min_y),
        Point(max_x, min_y),
        Point(max_x, max_y),
        Point(min_x, max_y),
    )
    return all(
        point.distance_to(want) <= 1e-6
        for point, want in zip(anchor.quad.corners, expected)
    )


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
    width: int | None = None,
    height: int | None = None,
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
    reserved_simple_shape_count = sum(
        1
        for anchor in anchors
        if _reservation_reason(anchor) == "simple_shape_anchor"
    )
    reserved_simple_shape_area = _reserved_bounds_area(
        tuple(
            anchor
            for anchor in anchors
            if _reservation_reason(anchor) == "simple_shape_anchor"
        )
    )
    canvas_area = (width or 0) * (height or 0)
    reserved_simple_shape_area_ratio = (
        min(reserved_simple_shape_area / canvas_area, 1.0)
        if canvas_area > 0
        else 0.0
    )
    simple_shape_ratio = (
        simple_shape_count / anchor_count
        if anchor_count
        else 1.0
    )
    structured_text_fallback_indexes = _structured_text_fallback_anchor_indexes(
        anchors,
        groups or [],
    )
    structured_text_fallback_count = len(structured_text_fallback_indexes)
    unstructured_generic_path_count = max(
        generic_path_count - structured_text_fallback_count,
        0,
    )
    fragmentation_penalty = _fragmentation_penalty(anchors)
    unstructured_fragmentation_penalty = _unstructured_fragmentation_penalty(
        anchors,
        structured_fragment_indexes=structured_text_fallback_indexes,
    )
    unstructured_fragment_counts = _color_fragment_counts(
        tuple(
            anchor
            for index, anchor in enumerate(anchors)
            if _is_unstructured_fragment_anchor(anchor)
            and index not in structured_text_fallback_indexes
        )
    )
    anchor_quality_errors = [
        quality_metric_error(anchor.metrics)
        for anchor in anchors
    ]
    simple_shape_priority_bonuses = [
        simple_shape_priority_bonus(anchor)
        for anchor in anchors
    ]
    semantic_anchor_scores = [
        semantic_anchor_score(anchor)
        for anchor in anchors
    ]
    diagnostic_penalty = min(
        sum(1 for diagnostic in diagnostics if diagnostic.get("level") == "warning")
        * 0.05,
        0.5,
    )
    generic_path_penalty = min(generic_path_count * 0.04, 0.4)
    editability_unclipped_score = (
        simple_shape_ratio
        - fragmentation_penalty
        - diagnostic_penalty
        - generic_path_penalty
    )
    editability_score = max(
        0.0,
        min(
            1.0,
            editability_unclipped_score,
        ),
    )
    return {
        "shape_count": anchor_count,
        "node_count": node_count,
        "parameter_count": parameter_count,
        "simple_shape_count": simple_shape_count,
        "reserved_simple_shape_count": reserved_simple_shape_count,
        "reserved_simple_shape_area": round(reserved_simple_shape_area, 6),
        "reserved_simple_shape_area_ratio": round(
            reserved_simple_shape_area_ratio,
            6,
        ),
        "generic_path_count": generic_path_count,
        "structured_text_fallback_count": structured_text_fallback_count,
        "unstructured_generic_path_count": unstructured_generic_path_count,
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
        "unstructured_fragmentation_penalty": round(
            unstructured_fragmentation_penalty,
            6,
        ),
        "anchor_quality_error_mean": round(
            mean(anchor_quality_errors) if anchor_quality_errors else 0.0,
            6,
        ),
        "anchor_quality_error_max": round(
            max(anchor_quality_errors) if anchor_quality_errors else 0.0,
            6,
        ),
        "anchor_quality_metric_summary": _anchor_quality_metric_summary(anchors),
        "anchor_scoring_summary": {
            "simple_shape_priority_bonus_total": round(
                sum(simple_shape_priority_bonuses),
                6,
            ),
            "simple_shape_priority_bonus_mean": round(
                mean(simple_shape_priority_bonuses)
                if simple_shape_priority_bonuses
                else 0.0,
                6,
            ),
            "semantic_anchor_score_mean": round(
                mean(semantic_anchor_scores) if semantic_anchor_scores else 0.0,
                6,
            ),
            "semantic_anchor_score_min": round(
                min(semantic_anchor_scores) if semantic_anchor_scores else 0.0,
                6,
            ),
            "semantic_anchor_score_max": round(
                max(semantic_anchor_scores) if semantic_anchor_scores else 0.0,
                6,
            ),
        },
        "diagnostic_penalty": round(diagnostic_penalty, 6),
        "editability_components": {
            "simple_shape_ratio": round(simple_shape_ratio, 6),
            "fragmentation_penalty": round(fragmentation_penalty, 6),
            "diagnostic_penalty": round(diagnostic_penalty, 6),
            "generic_path_penalty": round(generic_path_penalty, 6),
            "unclipped_score": round(editability_unclipped_score, 6),
            "clipped_score": round(editability_score, 6),
        },
        "editability_v10_components": _editability_v10_components(
            anchors=anchors,
            anchor_count=anchor_count,
            node_count=node_count,
            parameter_count=parameter_count,
            simple_shape_count=simple_shape_count,
            generic_path_count=generic_path_count,
            structured_text_fallback_count=structured_text_fallback_count,
            unstructured_generic_path_count=unstructured_generic_path_count,
            fragmentation_penalty=fragmentation_penalty,
            unstructured_fragmentation_penalty=unstructured_fragmentation_penalty,
            diagnostic_penalty=diagnostic_penalty,
            quality_summary=_anchor_quality_metric_summary(anchors),
            group_count=len(groups or []),
        ),
        "editability_score": round(editability_score, 6),
        "color_fragment_counts": _color_fragment_counts(anchors),
        "unstructured_fragment_counts": unstructured_fragment_counts,
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


def _anchor_quality_metric_summary(
    anchors: tuple[AnchorCandidate, ...],
) -> dict[str, dict[str, float | int]]:
    values_by_metric: dict[str, list[float]] = {}
    for anchor in anchors:
        for key, value in anchor.metrics.items():
            if not _is_anchor_quality_metric(key) or not isinstance(value, (int, float)):
                continue
            values_by_metric.setdefault(key, []).append(float(value))
    return {
        key: {
            "count": len(values),
            "mean": round(mean(values), 6),
            "max": round(max(values), 6),
        }
        for key, values in sorted(values_by_metric.items())
        if values
    }


def _is_anchor_quality_metric(key: str) -> bool:
    return (
        key.endswith("_error")
        or key in {"stroke_width_variance", "classifier_prior_error"}
    )


def refresh_raster_editability_component(metrics: dict[str, object]) -> None:
    """Update v10 editability components after run-level raster metrics exist."""

    components = metrics.get("editability_v10_components")
    if not isinstance(components, dict):
        components = {}
    components["raster_fidelity"] = _raster_fidelity_component(metrics)
    metrics["editability_v10_components"] = components


def _editability_v10_components(
    *,
    anchors: tuple[AnchorCandidate, ...],
    anchor_count: int,
    node_count: int,
    parameter_count: int,
    simple_shape_count: int,
    generic_path_count: int,
    structured_text_fallback_count: int,
    unstructured_generic_path_count: int,
    fragmentation_penalty: float,
    unstructured_fragmentation_penalty: float,
    diagnostic_penalty: float,
    quality_summary: dict[str, dict[str, float | int]],
    group_count: int,
) -> dict[str, dict[str, object]]:
    average_nodes = node_count / anchor_count if anchor_count else 0.0
    average_parameters = parameter_count / anchor_count if anchor_count else 0.0
    simple_shape_ratio = simple_shape_count / anchor_count if anchor_count else 1.0
    recognized_shape_count = simple_shape_count + structured_text_fallback_count
    shape_identity_score = (
        recognized_shape_count / anchor_count
        if anchor_count
        else 1.0
    )
    generic_path_ratio = generic_path_count / anchor_count if anchor_count else 0.0
    unstructured_generic_path_ratio = (
        unstructured_generic_path_count / anchor_count
        if anchor_count
        else 0.0
    )
    return {
        "shape_identity_confidence": {
            "score": round(shape_identity_score, 6),
            "simple_shape_count": simple_shape_count,
            "generic_path_count": generic_path_count,
            "generic_path_ratio": round(generic_path_ratio, 6),
            "structured_text_fallback_count": structured_text_fallback_count,
            "recognized_shape_count": recognized_shape_count,
            "unstructured_generic_path_count": unstructured_generic_path_count,
            "unstructured_generic_path_ratio": round(
                unstructured_generic_path_ratio,
                6,
            ),
        },
        "parameter_economy": _parameter_economy_component(
            anchors=anchors,
            parameter_count=parameter_count,
            average_parameters=average_parameters,
        ),
        "node_economy": {
            "score": _economy_score(average_nodes, budget=24.0),
            "average_node_count": round(average_nodes, 6),
            "node_count": node_count,
        },
        "stroke_width_stability": _metric_component(
            quality_summary,
            "stroke_width_variance",
        ),
        "line_curve_smoothness": _metric_component(
            quality_summary,
            "line_smoothness_error",
        ),
        "topology_consistency": {
            "score": _error_score(diagnostic_penalty, scale=0.5),
            "diagnostic_penalty": round(diagnostic_penalty, 6),
        },
        "grouping_quality": {
            "score": _grouping_score(anchor_count, group_count),
            "group_count": group_count,
        },
        "fragmentation": {
            "score": _error_score(unstructured_fragmentation_penalty, scale=0.5),
            "fragmentation_penalty": round(fragmentation_penalty, 6),
            "unstructured_fragmentation_penalty": round(
                unstructured_fragmentation_penalty,
                6,
            ),
        },
        "raster_fidelity": {
            "score": None,
            "observed": False,
            "reason": "run-level raster metrics unavailable",
        },
        "provenance_confidence": {
            "score": round(1.0 - unstructured_generic_path_ratio, 6),
            "fallback_path_ratio": round(unstructured_generic_path_ratio, 6),
            "raw_fallback_path_ratio": round(generic_path_ratio, 6),
            "structured_text_fallback_count": structured_text_fallback_count,
            "unstructured_generic_path_count": unstructured_generic_path_count,
        },
        "classifier_prior_agreement": _metric_component(
            quality_summary,
            "classifier_prior_error",
        ),
    }


def _metric_component(
    summary: dict[str, dict[str, float | int]],
    metric: str,
) -> dict[str, object]:
    values = summary.get(metric)
    if not isinstance(values, dict):
        return {
            "score": 1.0,
            "observed": False,
            "metric": metric,
            "reason": "metric unavailable",
        }
    max_error = float(values.get("max", 0.0))
    return {
        "score": _error_score(max_error),
        "observed": True,
        "metric": metric,
        "max": round(max_error, 6),
        "mean": round(float(values.get("mean", 0.0)), 6),
        "count": int(values.get("count", 0)),
    }


def _parameter_economy_component(
    *,
    anchors: tuple[AnchorCandidate, ...],
    parameter_count: int,
    average_parameters: float,
) -> dict[str, object]:
    budget = 16.0
    parameter_counts = [anchor.parameter_count for anchor in anchors]
    return {
        "score": _economy_score(average_parameters, budget=budget),
        "average_parameter_count": round(average_parameters, 6),
        "parameter_count": parameter_count,
        "budget": budget,
        "max_parameter_count": max(parameter_counts) if parameter_counts else 0,
        "over_budget_anchor_count": sum(
            1 for count in parameter_counts if count > budget
        ),
        "top_contributors": _top_parameter_contributors(anchors),
    }


def _top_parameter_contributors(
    anchors: tuple[AnchorCandidate, ...],
    *,
    limit: int = 5,
) -> list[dict[str, object]]:
    ranked = sorted(
        enumerate(anchors),
        key=lambda item: item[1].parameter_count,
        reverse=True,
    )
    contributors: list[dict[str, object]] = []
    for index, anchor in ranked[:limit]:
        contributors.append(
            {
                "anchor_index": index,
                "kind": str(anchor.kind),
                "color": anchor.color,
                "parameter_count": anchor.parameter_count,
                "node_count": anchor.node_count,
                "bounds": [
                    round(value, 6)
                    for value in _anchor_bounds(anchor)
                ],
            }
        )
    return contributors


def _raster_fidelity_component(metrics: dict[str, object]) -> dict[str, object]:
    l1 = metrics.get("raster_l1_error")
    edge = metrics.get("raster_edge_error")
    if not isinstance(l1, (int, float)) or not isinstance(edge, (int, float)):
        return {
            "score": None,
            "observed": False,
            "reason": "raster_l1_error or raster_edge_error missing",
        }
    error = min(float(l1) + float(edge), 1.0)
    return {
        "score": _error_score(error),
        "observed": True,
        "raster_l1_error": round(float(l1), 6),
        "raster_edge_error": round(float(edge), 6),
    }


def _economy_score(value: float, *, budget: float) -> float:
    if budget <= 0.0:
        return 0.0
    return _error_score(value / budget)


def _grouping_score(anchor_count: int, group_count: int) -> float:
    if anchor_count <= 1:
        return 1.0
    if group_count > 0:
        return 1.0
    return 0.5


def _error_score(value: float, *, scale: float = 1.0) -> float:
    if scale <= 0.0:
        return 0.0
    return round(max(0.0, min(1.0, 1.0 - float(value) / scale)), 6)


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


def _unstructured_fragmentation_penalty(
    anchors: tuple[AnchorCandidate, ...],
    *,
    structured_fragment_indexes: set[int] | None = None,
) -> float:
    if not anchors:
        return 0.0
    structured = structured_fragment_indexes or set()
    fragment_counts = _color_fragment_counts(
        tuple(
            anchor
            for index, anchor in enumerate(anchors)
            if _is_unstructured_fragment_anchor(anchor)
            and index not in structured
        )
    )
    excess_fragments = sum(max(0, count - 1) for count in fragment_counts.values())
    return min(excess_fragments / max(len(anchors), 1), 0.5)


def _is_unstructured_fragment_anchor(anchor: AnchorCandidate) -> bool:
    return anchor.kind == AnchorKind.CUBIC_PATH


def _structured_text_fallback_anchor_indexes(
    anchors: tuple[AnchorCandidate, ...],
    groups: list[dict[str, object]],
) -> set[int]:
    indexes: set[int] = set()
    for group in groups:
        if (
            not isinstance(group, dict)
            or group.get("kind") != "text_like_fragment_group"
        ):
            continue
        for index in group.get("fallback_anchor_indexes", []):
            if (
                isinstance(index, int)
                and 0 <= index < len(anchors)
                and anchors[index].kind == AnchorKind.CUBIC_PATH
            ):
                indexes.add(index)
    return indexes


def _reserved_bounds_area(anchors: tuple[AnchorCandidate, ...]) -> float:
    area = 0.0
    for anchor in anchors:
        area += _bounds_area(_anchor_bounds(anchor))
    return area


def _bounds_area(bounds: tuple[float, float, float, float] | list[float]) -> float:
    min_x, min_y, max_x, max_y = bounds
    return max(0.0, max_x - min_x) * max(0.0, max_y - min_y)


def _bounds_intersection_area(
    first: tuple[float, float, float, float] | list[float],
    second: tuple[float, float, float, float] | list[float],
) -> float:
    min_x = max(first[0], second[0])
    min_y = max(first[1], second[1])
    max_x = min(first[2], second[2])
    max_y = min(first[3], second[3])
    return _bounds_area((min_x, min_y, max_x, max_y))


def _bounds_iou(
    first: tuple[float, float, float, float] | list[float],
    second: tuple[float, float, float, float] | list[float],
) -> float:
    intersection = _bounds_intersection_area(first, second)
    union = _bounds_area(first) + _bounds_area(second) - intersection
    if union <= 0.0:
        return 0.0
    return intersection / union


def _bounds_gap(
    first: tuple[float, float, float, float] | list[float],
    second: tuple[float, float, float, float] | list[float],
) -> float:
    horizontal_gap = max(first[0] - second[2], second[0] - first[2], 0.0)
    vertical_gap = max(first[1] - second[3], second[1] - first[3], 0.0)
    return (horizontal_gap * horizontal_gap + vertical_gap * vertical_gap) ** 0.5


def _anchor_layer(anchor: AnchorCandidate) -> str:
    if anchor.stroke is not None and anchor.stroke.is_cutout:
        return "cutout_overlays"
    if anchor.kind in {
        AnchorKind.STROKE_CIRCLE,
        AnchorKind.STROKE_ELLIPSE,
        AnchorKind.STROKE_POLYLINE,
        AnchorKind.STROKE_PATH,
        AnchorKind.ARC,
    }:
        return "strokes"
    if anchor.kind in {
        AnchorKind.CIRCLE,
        AnchorKind.ELLIPSE,
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
    if anchor.path is not None and anchor.path.points:
        # Fitted curves bulge past their sparse on-curve points, so bounds
        # come from sampling the actual segments.
        samples = _sampled_path_points(anchor.path)
        xs = [point.x for point in samples]
        ys = [point.y for point in samples]
        return (min(xs), min(ys), max(xs), max(ys))
    if anchor.ellipse is not None:
        center = anchor.ellipse.center
        rx = anchor.ellipse.rx
        ry = anchor.ellipse.ry
        if anchor.kind == AnchorKind.STROKE_ELLIPSE:
            half = _stroke_width(anchor) / 2
            rx += half
            ry += half
        rotation = anchor.ellipse.rotation
        if abs(rotation) > 1e-6:
            # Exact AABB of a rotated ellipse.
            half_w = sqrt(
                (rx * cos(rotation)) ** 2 + (ry * sin(rotation)) ** 2
            )
            half_h = sqrt(
                (rx * sin(rotation)) ** 2 + (ry * cos(rotation)) ** 2
            )
            return (
                center.x - half_w,
                center.y - half_h,
                center.x + half_w,
                center.y + half_h,
            )
        return (center.x - rx, center.y - ry, center.x + rx, center.y + ry)
    if anchor.circle is not None:
        center = anchor.circle.center
        radius = anchor.circle.radius
        if anchor.kind == AnchorKind.STROKE_CIRCLE:
            radius += _stroke_width(anchor) / 2
        return (
            center.x - radius,
            center.y - radius,
            center.x + radius,
            center.y + radius,
        )
    if anchor.stroke is not None and anchor.stroke.centerline:
        return _stroke_bounds(anchor.stroke, _stroke_width(anchor))
    if anchor.quad is not None:
        xs = [point.x for point in anchor.quad.corners]
        ys = [point.y for point in anchor.quad.corners]
        return (min(xs), min(ys), max(xs), max(ys))
    return (0.0, 0.0, 0.0, 0.0)


def _sampled_path_points(path: PathAnchor) -> tuple[Point, ...]:
    if path.controls is None:
        return path.points
    count = len(path.points)
    samples: list[Point] = []
    for index in range(count):
        p0 = path.points[index]
        p3 = path.points[(index + 1) % count]
        c1, c2 = path.controls[index]
        for step in range(12):
            t = step / 12
            u = 1 - t
            samples.append(
                Point(
                    u**3 * p0.x + 3 * u * u * t * c1.x + 3 * u * t * t * c2.x + t**3 * p3.x,
                    u**3 * p0.y + 3 * u * u * t * c1.y + 3 * u * t * t * c2.y + t**3 * p3.y,
                )
            )
    return tuple(samples)


def _rect_svg_box(anchor: AnchorCandidate) -> tuple[float, float, float, float]:
    min_x, min_y, max_x, max_y = _anchor_bounds(anchor)
    width = max_x - min_x
    height = max_y - min_y
    if _integer_axis_aligned_quad(anchor):
        width += 1
        height += 1
    return min_x, min_y, width, height


def _integer_axis_aligned_quad(anchor: AnchorCandidate) -> bool:
    if anchor.quad is None:
        return False
    corners = anchor.quad.corners
    if len(corners) != 4:
        return False
    min_x, min_y, max_x, max_y = _anchor_bounds(anchor)
    expected = {
        (min_x, min_y),
        (max_x, min_y),
        (max_x, max_y),
        (min_x, max_y),
    }
    actual = {(point.x, point.y) for point in corners}
    if actual != expected:
        return False
    return all(
        _is_integer_coordinate(value)
        for point in corners
        for value in (point.x, point.y)
    )


def _is_integer_coordinate(value: float) -> bool:
    return abs(value - round(value)) < 1e-9


def _stroke_bounds(stroke: StrokeAnchor, width: float) -> tuple[float, float, float, float]:
    points = stroke.centerline
    if len(points) < 2:
        xs = [point.x for point in points]
        ys = [point.y for point in points]
        pad = width / 2
        return (min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad)
    if stroke.cap_style != "butt" or len(points) != 2:
        xs = [point.x for point in points]
        ys = [point.y for point in points]
        pad = width / 2
        return (min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad)

    start, end = points
    dx = end.x - start.x
    dy = end.y - start.y
    length = (dx * dx + dy * dy) ** 0.5
    if length <= 0.0:
        pad = width / 2
        return (start.x - pad, start.y - pad, start.x + pad, start.y + pad)
    normal_x = -dy / length
    normal_y = dx / length
    pad = width / 2
    corners = (
        (start.x + normal_x * pad, start.y + normal_y * pad),
        (start.x - normal_x * pad, start.y - normal_y * pad),
        (end.x + normal_x * pad, end.y + normal_y * pad),
        (end.x - normal_x * pad, end.y - normal_y * pad),
    )
    xs = [x for x, _ in corners]
    ys = [y for _, y in corners]
    return (min(xs), min(ys), max(xs), max(ys))


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


def _closed_polyline_path(points: tuple[Point, ...]) -> str:
    if not points:
        return ""
    return _polyline_path(points) + " Z"


def _arc_path(arc: ArcAnchor) -> str:
    start = arc.start
    end = arc.end
    radius = _fmt(arc.radius)
    return (
        f"M {_fmt(start.x)} {_fmt(start.y)} "
        f"A {radius} {radius} 0 "
        f"{1 if arc.large_arc else 0} {1 if arc.sweep else 0} "
        f"{_fmt(end.x)} {_fmt(end.y)}"
    )


def _closed_bezier_path(
    points: tuple[Point, ...],
    controls: tuple[tuple[Point, Point], ...],
) -> str:
    """Closed path from fitted on-curve points and their control pairs."""

    commands = [f"M {_fmt(points[0].x)} {_fmt(points[0].y)}"]
    count = len(points)
    for index in range(count):
        control1, control2 = controls[index]
        end = points[(index + 1) % count]
        commands.append(
            "C "
            f"{_fmt(control1.x)} {_fmt(control1.y)} "
            f"{_fmt(control2.x)} {_fmt(control2.y)} "
            f"{_fmt(end.x)} {_fmt(end.y)}"
        )
    commands.append("Z")
    return " ".join(commands)


def _closed_smooth_path(points: tuple[Point, ...]) -> str:
    """Closed Catmull-Rom outline as cubic Bezier segments ending in Z."""

    if len(points) < 3:
        return _polyline_path(points) + " Z"
    commands = [f"M {_fmt(points[0].x)} {_fmt(points[0].y)}"]
    for control1, control2, end in catmull_rom_segments_closed(points):
        commands.append(
            "C "
            f"{_fmt(control1.x)} {_fmt(control1.y)} "
            f"{_fmt(control2.x)} {_fmt(control2.y)} "
            f"{_fmt(end.x)} {_fmt(end.y)}"
        )
    commands.append("Z")
    return " ".join(commands)


def catmull_rom_segments_closed(
    points: tuple[Point, ...],
) -> list[tuple[Point, Point, Point]]:
    """Closed-loop centripetal Catmull-Rom control pairs around the outline.

    Curvature-adaptive simplification leaves nodes at very uneven spacing
    (tight around tips, sparse along flat arcs). The uniform parameterization
    overshoots there; the centripetal one stays inside the hull and keeps
    tips sharp.
    """

    count = len(points)
    segments: list[tuple[Point, Point, Point]] = []
    for index in range(count):
        p0 = points[(index - 1) % count]
        p1 = points[index]
        p2 = points[(index + 1) % count]
        p3 = points[(index + 2) % count]
        segments.append((*_centripetal_controls(p0, p1, p2, p3), p2))
    return segments


def _centripetal_controls(
    p0: Point,
    p1: Point,
    p2: Point,
    p3: Point,
) -> tuple[Point, Point]:
    d1 = max(p1.distance_to(p0), 1e-4) ** 0.5
    d2 = max(p2.distance_to(p1), 1e-4) ** 0.5
    d3 = max(p3.distance_to(p2), 1e-4) ** 0.5
    scale_one = 3 * d1 * (d1 + d2)
    scale_two = 3 * d3 * (d3 + d2)
    control1 = Point(
        (d1 * d1 * p2.x - d2 * d2 * p0.x + (2 * d1 * d1 + 3 * d1 * d2 + d2 * d2) * p1.x)
        / scale_one,
        (d1 * d1 * p2.y - d2 * d2 * p0.y + (2 * d1 * d1 + 3 * d1 * d2 + d2 * d2) * p1.y)
        / scale_one,
    )
    control2 = Point(
        (d3 * d3 * p1.x - d2 * d2 * p3.x + (2 * d3 * d3 + 3 * d3 * d2 + d2 * d2) * p2.x)
        / scale_two,
        (d3 * d3 * p1.y - d2 * d2 * p3.y + (2 * d3 * d3 + 3 * d3 * d2 + d2 * d2) * p2.y)
        / scale_two,
    )
    return control1, control2


def _smooth_curve_path(points: tuple[Point, ...]) -> str:
    """Render control points as Catmull-Rom-derived cubic Bezier segments."""

    commands = [f"M {_fmt(points[0].x)} {_fmt(points[0].y)}"]
    for control1, control2, end in catmull_rom_segments(points):
        commands.append(
            "C "
            f"{_fmt(control1.x)} {_fmt(control1.y)} "
            f"{_fmt(control2.x)} {_fmt(control2.y)} "
            f"{_fmt(end.x)} {_fmt(end.y)}"
        )
    return " ".join(commands)


def catmull_rom_segments(
    points: tuple[Point, ...],
) -> list[tuple[Point, Point, Point]]:
    """Cubic Bezier control pairs for a Catmull-Rom spline through points."""

    segments: list[tuple[Point, Point, Point]] = []
    extended = (points[0], *points, points[-1])
    for index in range(1, len(extended) - 2):
        p0 = extended[index - 1]
        p1 = extended[index]
        p2 = extended[index + 1]
        p3 = extended[index + 2]
        control1 = Point(
            p1.x + (p2.x - p0.x) / 6,
            p1.y + (p2.y - p0.y) / 6,
        )
        control2 = Point(
            p2.x - (p3.x - p1.x) / 6,
            p2.y - (p3.y - p1.y) / 6,
        )
        segments.append((control1, control2, p2))
    return segments


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


def _ellipse_rotation_attr(ellipse) -> str:
    if abs(ellipse.rotation) < 1e-6:
        return ""
    return (
        f'transform="rotate({_fmt(degrees(ellipse.rotation))} '
        f'{_fmt(ellipse.center.x)} {_fmt(ellipse.center.y)})" '
    )
