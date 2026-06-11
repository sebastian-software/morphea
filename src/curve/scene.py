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

    def to_svg(self, style: SvgStyle | None = None) -> str:
        return anchors_to_svg(self.anchors, self.width, self.height, style=style)

    def to_manifest(self) -> dict[str, object]:
        return {
            "width": self.width,
            "height": self.height,
            "anchor_count": len(self.anchors),
            "anchors": [anchor_to_manifest(anchor) for anchor in self.anchors],
            "groups": scene_groups_to_manifest(self.anchors),
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
        return (
            f'<path d="{path}" fill="none" stroke="{escape(stroke)}" '
            f'stroke-width="{_fmt(width)}" stroke-linecap="round" '
            f'stroke-linejoin="round" />'
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
