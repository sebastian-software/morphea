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
    perspective_grid_consistency_error,
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

    def to_manifest(self) -> dict[str, object]:
        groups = scene_groups_to_manifest(self.anchors)
        return {
            "schema_version": SCENE_MANIFEST_SCHEMA_VERSION,
            "width": self.width,
            "height": self.height,
            "anchor_count": len(self.anchors),
            "anchors": [anchor_to_manifest(anchor) for anchor in self.anchors],
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

    if anchor.kind in {AnchorKind.STROKE_PATH, AnchorKind.STROKE_POLYLINE}:
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

    if anchor.kind == AnchorKind.QUAD and anchor.quad is not None:
        points = " ".join(_point_pair(point) for point in anchor.quad.corners)
        return f'<polygon points="{points}" fill="{escape(fill)}" />'

    return _unsupported_anchor(anchor)


def anchor_to_manifest(anchor: AnchorCandidate) -> dict[str, object]:
    data: dict[str, object] = {
        "kind": anchor.kind.value,
        "color": anchor.color,
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
    quad_indexes = [
        index
        for index, anchor in enumerate(anchors)
        if anchor.kind == AnchorKind.QUAD and anchor.quad is not None
    ]
    if len(quad_indexes) < 2:
        return []

    quads = [anchors[index].quad for index in quad_indexes]
    return [
        {
            "kind": AnchorKind.PERSPECTIVE_GRID.value,
            "anchor_indexes": quad_indexes,
            "metrics": {
                "perspective_grid_consistency_error": perspective_grid_consistency_error(
                    tuple(quad for quad in quads if quad is not None)
                )
            },
        }
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


def _fragmentation_penalty(anchors: tuple[AnchorCandidate, ...]) -> float:
    if not anchors:
        return 0.0
    excess_fragments = sum(
        max(0, count - 1)
        for count in _color_fragment_counts(anchors).values()
    )
    return min(excess_fragments / max(len(anchors), 1) * 0.5, 0.5)


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
