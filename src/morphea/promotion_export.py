"""Promotion-state SVG export helpers."""

from __future__ import annotations

import json
from html import escape
from math import cos, sin
from pathlib import Path
from statistics import mean
from typing import Any


def write_promotion_svg_exports(
    *,
    manifest: str | Path,
    promoted_svg: str | Path | None = None,
    fallback_svg: str | Path | None = None,
    output: str | Path | None = None,
) -> dict[str, object]:
    manifest_path = Path(manifest)
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("promotion export manifest must be a JSON object")
    promoted_path = Path(promoted_svg) if promoted_svg is not None else (
        manifest_path.with_name("promoted.svg")
    )
    fallback_path = Path(fallback_svg) if fallback_svg is not None else (
        manifest_path.with_name("fallback.svg")
    )
    promoted_indexes = _promoted_anchor_indexes(data)
    anchors = data.get("anchors", [])
    anchors = anchors if isinstance(anchors, list) else []
    fallback_indexes = [
        index for index in range(len(anchors)) if index not in promoted_indexes
    ]
    promoted_path.parent.mkdir(parents=True, exist_ok=True)
    fallback_path.parent.mkdir(parents=True, exist_ok=True)
    promoted_path.write_text(
        manifest_to_svg(data, promoted_indexes),
        encoding="utf-8",
    )
    fallback_path.write_text(
        manifest_to_svg(data, fallback_indexes),
        encoding="utf-8",
    )
    result = {
        "schema_version": 1,
        "manifest": str(manifest_path),
        "anchor_count": len(anchors),
        "promoted_anchor_indexes": promoted_indexes,
        "fallback_anchor_indexes": fallback_indexes,
        "region_state_counts": _promotion_region_state_counts(data),
        "promoted_svg": str(promoted_path),
        "fallback_svg": str(fallback_path),
    }
    if output is not None:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(result, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    return result


def manifest_to_svg(
    manifest: dict[str, Any],
    anchor_indexes: list[int],
) -> str:
    width = int(manifest.get("width", 1))
    height = int(manifest.get("height", 1))
    anchors = manifest.get("anchors", [])
    anchors = anchors if isinstance(anchors, list) else []
    lines = [
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'viewBox="0 0 {width} {height}" width="{width}" height="{height}">'
        )
    ]
    for index in anchor_indexes:
        if 0 <= index < len(anchors) and isinstance(anchors[index], dict):
            lines.append(f"  {_manifest_anchor_to_svg(anchors[index])}")
    lines.append("</svg>")
    return "\n".join(lines)


def _promoted_anchor_indexes(manifest: dict[str, Any]) -> list[int]:
    anchors = manifest.get("anchors", [])
    anchors = anchors if isinstance(anchors, list) else []
    promoted = [
        index
        for index, anchor in enumerate(anchors)
        if isinstance(anchor, dict) and anchor.get("promotion_state") == "promoted"
    ]
    if promoted:
        return promoted
    promotion = manifest.get("promotion", {})
    if not isinstance(promotion, dict):
        return []
    regions = promotion.get("regions", [])
    if not isinstance(regions, list):
        return []
    indexes: set[int] = set()
    for region in regions:
        if not isinstance(region, dict) or region.get("state") != "promoted":
            continue
        selected = region.get("selected_anchor_indexes", [])
        if not isinstance(selected, list):
            continue
        indexes.update(index for index in selected if isinstance(index, int))
    return sorted(indexes)


def _promotion_region_state_counts(manifest: dict[str, Any]) -> dict[str, int]:
    promotion = manifest.get("promotion", {})
    if not isinstance(promotion, dict):
        return {}
    regions = promotion.get("regions", [])
    if not isinstance(regions, list):
        return {}
    counts: dict[str, int] = {}
    for region in regions:
        if not isinstance(region, dict):
            continue
        state = str(region.get("state", "unknown"))
        counts[state] = counts.get(state, 0) + 1
    return dict(sorted(counts.items()))


def _manifest_anchor_to_svg(anchor: dict[str, Any]) -> str:
    kind = str(anchor.get("kind", ""))
    color = escape(str(anchor.get("color") or "#0b2d5f"))
    if kind == "circle" and isinstance(anchor.get("circle"), dict):
        circle = anchor["circle"]
        return (
            f'<circle cx="{_fmt(circle.get("cx", 0))}" '
            f'cy="{_fmt(circle.get("cy", 0))}" r="{_fmt(circle.get("r", 0))}" '
            f'fill="{color}" />'
        )
    if kind == "stroke_circle" and isinstance(anchor.get("circle"), dict):
        circle = anchor["circle"]
        return (
            f'<circle cx="{_fmt(circle.get("cx", 0))}" '
            f'cy="{_fmt(circle.get("cy", 0))}" r="{_fmt(circle.get("r", 0))}" '
            f'fill="none" stroke="{color}" '
            f'stroke-width="{_fmt(_stroke_width(anchor))}" />'
        )
    if kind in {"ellipse", "stroke_ellipse"} and isinstance(anchor.get("ellipse"), dict):
        return _ellipse_to_svg(anchor, stroke=kind == "stroke_ellipse")
    if kind in {"rect", "rounded_rect", "quad"} and isinstance(anchor.get("quad"), dict):
        points = _point_list(anchor["quad"].get("corners", []))
        return f'<polygon points="{points}" fill="{color}" />'
    if kind in {"stroke", "stroke_polyline", "stroke_path"} and isinstance(
        anchor.get("stroke"),
        dict,
    ):
        return _stroke_to_svg(anchor)
    if kind == "arc" and isinstance(anchor.get("arc"), dict):
        return _arc_to_svg(anchor)
    if kind == "cubic_path" and isinstance(anchor.get("path"), dict):
        return _path_to_svg(anchor)
    return f'<g data-unsupported-kind="{escape(kind)}" />'


def _ellipse_to_svg(anchor: dict[str, Any], *, stroke: bool) -> str:
    ellipse = anchor["ellipse"]
    color = escape(str(anchor.get("color") or "#0b2d5f"))
    transform = ""
    rotation = float(ellipse.get("rotation", 0.0) or 0.0)
    if abs(rotation) > 1e-6:
        transform = (
            f' transform="rotate({_fmt(rotation)} {_fmt(ellipse.get("cx", 0))} '
            f'{_fmt(ellipse.get("cy", 0))})"'
        )
    if stroke:
        return (
            f'<ellipse cx="{_fmt(ellipse.get("cx", 0))}" '
            f'cy="{_fmt(ellipse.get("cy", 0))}" '
            f'rx="{_fmt(ellipse.get("rx", 0))}" ry="{_fmt(ellipse.get("ry", 0))}"'
            f'{transform} fill="none" stroke="{color}" '
            f'stroke-width="{_fmt(_stroke_width(anchor))}" />'
        )
    return (
        f'<ellipse cx="{_fmt(ellipse.get("cx", 0))}" '
        f'cy="{_fmt(ellipse.get("cy", 0))}" '
        f'rx="{_fmt(ellipse.get("rx", 0))}" ry="{_fmt(ellipse.get("ry", 0))}"'
        f'{transform} fill="{color}" />'
    )


def _stroke_to_svg(anchor: dict[str, Any]) -> str:
    stroke = anchor["stroke"]
    color = escape(str(anchor.get("color") or "#0b2d5f"))
    points = stroke.get("centerline", [])
    path = _path_from_points(points, closed=bool(stroke.get("closed", False)))
    cap = escape(str(stroke.get("cap_style", "round")))
    join = escape(str(stroke.get("join_style", "round")))
    return (
        f'<path d="{path}" fill="none" stroke="{color}" '
        f'stroke-width="{_fmt(_stroke_width(anchor))}" '
        f'stroke-linecap="{cap}" stroke-linejoin="{join}" />'
    )


def _arc_to_svg(anchor: dict[str, Any]) -> str:
    arc = anchor["arc"]
    color = escape(str(anchor.get("color") or "#0b2d5f"))
    cx = float(arc.get("cx", 0.0) or 0.0)
    cy = float(arc.get("cy", 0.0) or 0.0)
    radius = float(arc.get("r", 0.0) or 0.0)
    start = float(arc.get("theta_start", 0.0) or 0.0)
    end = float(arc.get("theta_end", 0.0) or 0.0)
    x1 = cx + radius * cos(start)
    y1 = cy + radius * sin(start)
    x2 = cx + radius * cos(end)
    y2 = cy + radius * sin(end)
    large_arc = 1 if bool(arc.get("large_arc", False)) else 0
    sweep = 1 if bool(arc.get("sweep", True)) else 0
    path = (
        f"M {_fmt(x1)} {_fmt(y1)} "
        f"A {_fmt(radius)} {_fmt(radius)} 0 {large_arc} {sweep} {_fmt(x2)} {_fmt(y2)}"
    )
    return (
        f'<path d="{path}" fill="none" stroke="{color}" '
        f'stroke-width="{_fmt(_stroke_width(anchor))}" />'
    )


def _path_to_svg(anchor: dict[str, Any]) -> str:
    path = anchor["path"]
    color = escape(str(anchor.get("color") or "#0b2d5f"))
    path_data = _bezier_path(path.get("points", []), path.get("controls"))
    for hole in path.get("holes", []):
        if isinstance(hole, dict):
            path_data += " " + _bezier_path(hole.get("points", []), hole.get("controls"))
    fill_rule = ' fill-rule="evenodd"' if path.get("holes") else ""
    return f'<path d="{path_data}" fill="{color}"{fill_rule} />'


def _bezier_path(points: object, controls: object) -> str:
    if not isinstance(points, list) or not points:
        return ""
    start = points[0]
    path = f"M {_fmt(start.get('x', 0))} {_fmt(start.get('y', 0))}"
    if isinstance(controls, list) and len(controls) == len(points):
        for index, pair in enumerate(controls):
            if not isinstance(pair, list) or len(pair) != 2:
                continue
            target = points[(index + 1) % len(points)]
            path += (
                f" C {_fmt(pair[0].get('x', 0))} {_fmt(pair[0].get('y', 0))},"
                f" {_fmt(pair[1].get('x', 0))} {_fmt(pair[1].get('y', 0))},"
                f" {_fmt(target.get('x', 0))} {_fmt(target.get('y', 0))}"
            )
    else:
        for point in points[1:]:
            path += f" L {_fmt(point.get('x', 0))} {_fmt(point.get('y', 0))}"
    return path + " Z"


def _path_from_points(points: object, *, closed: bool) -> str:
    if not isinstance(points, list) or not points:
        return ""
    start = points[0]
    path = f"M {_fmt(start.get('x', 0))} {_fmt(start.get('y', 0))}"
    for point in points[1:]:
        path += f" L {_fmt(point.get('x', 0))} {_fmt(point.get('y', 0))}"
    if closed:
        path += " Z"
    return path


def _point_list(points: object) -> str:
    if not isinstance(points, list):
        return ""
    return " ".join(
        f"{_fmt(point.get('x', 0))},{_fmt(point.get('y', 0))}"
        for point in points
        if isinstance(point, dict)
    )


def _stroke_width(anchor: dict[str, Any]) -> float:
    stroke = anchor.get("stroke", {})
    if not isinstance(stroke, dict):
        return 1.0
    samples = stroke.get("width_samples", [])
    if not isinstance(samples, list) or not samples:
        return 1.0
    numeric = [float(value) for value in samples if isinstance(value, (int, float))]
    return mean(numeric) if numeric else 1.0


def _fmt(value: object) -> str:
    numeric = float(value) if isinstance(value, (int, float)) else 0.0
    text = f"{numeric:.6f}".rstrip("0").rstrip(".")
    return text or "0"
