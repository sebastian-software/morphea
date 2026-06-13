"""Promotion-state SVG export helpers."""

from __future__ import annotations

import json
from html import escape
from math import cos, sin
from pathlib import Path
from statistics import mean
from typing import Any


PROMOTION_REVIEW_DECISIONS = {"accepted", "corrected", "rejected", "deferred"}


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
    anchors = data.get("anchors", [])
    anchors = anchors if isinstance(anchors, list) else []
    state_indexes = _promotion_anchor_state_indexes(data)
    promoted_indexes = state_indexes["promoted"]
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
        "fallback_only_anchor_indexes": state_indexes["fallback"],
        "rejected_anchor_indexes": state_indexes["rejected"],
        "deferred_anchor_indexes": state_indexes["deferred"],
        "anchor_state_counts": {
            state: len(indexes)
            for state, indexes in state_indexes.items()
            if indexes
        },
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


def apply_promotion_review_decision(
    *,
    review_decision: str | Path,
    output: str | Path | None = None,
    markdown: str | Path | None = None,
    manifest: str | Path | None = None,
) -> dict[str, object]:
    review_path = Path(review_decision)
    data = json.loads(review_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("promotion review decision must be a JSON object")
    decision = data.get("decision")
    if decision == "pending":
        raise ValueError("promotion review decision is still pending")
    if decision not in PROMOTION_REVIEW_DECISIONS:
        allowed = ", ".join(sorted(PROMOTION_REVIEW_DECISIONS))
        raise ValueError(f"promotion review decision must be one of: {allowed}")
    suggested = data.get("suggested_decision")
    result = {
        "schema_version": 1,
        "source_review_decision": str(review_path),
        "case_id": data.get("case_id"),
        "decision": decision,
        "accepted_for_promotion": decision in {"accepted", "corrected"},
        "suggested_decision": suggested,
        "matches_suggestion": decision == suggested,
        "reviewer": data.get("reviewer", ""),
        "reason": data.get("reason", ""),
        "correction_notes": data.get("correction_notes", ""),
        "corrected_artifacts": _string_list(data.get("corrected_artifacts")),
        "issue_tags": _string_list(data.get("issue_tags")),
        "source_decisions": _object_dict(data.get("source_decisions")),
        "failed_gates": _object_list(data.get("failed_gates")),
        "failed_components": _object_list(data.get("failed_components")),
        "gate_blocked_components": _object_list(
            data.get("gate_blocked_components"),
        ),
        "regressed_components": _object_list(data.get("regressed_components")),
    }
    if manifest is not None:
        manifest_path = Path(manifest)
        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest_data, dict):
            raise ValueError("promotion review manifest must be a JSON object")
        result["manifest"] = str(manifest_path)
        manifest_data["review_decision_applied"] = result
        promotion = manifest_data.get("promotion")
        if isinstance(promotion, dict):
            promotion["review_decision_applied"] = result
        manifest_path.write_text(
            json.dumps(manifest_data, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    if output is not None:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(result, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    if markdown is not None:
        markdown_path = Path(markdown)
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(
            render_promotion_review_decision_markdown(result),
            encoding="utf-8",
        )
    return result


def render_promotion_review_decision_markdown(result: dict[str, object]) -> str:
    lines = [
        "# Morphēa Promotion Review Decision",
        "",
        f"- Source: `{result.get('source_review_decision', 'n/a')}`",
        f"- Case: `{result.get('case_id', 'n/a')}`",
        f"- Decision: `{result.get('decision', 'n/a')}`",
        f"- Suggested: `{result.get('suggested_decision', 'n/a')}`",
        f"- Matches suggestion: `{str(result.get('matches_suggestion', False)).lower()}`",
        f"- Accepted for promotion: `{str(result.get('accepted_for_promotion', False)).lower()}`",
        f"- Issue tags: {_format_review_values(result.get('issue_tags'))}",
        "",
        "## Evidence",
        "",
        f"- Failed gates: {_format_review_records(result.get('failed_gates'))}",
        f"- Failed components: {_format_review_records(result.get('failed_components'))}",
        f"- Gate-blocked components: {_format_review_records(result.get('gate_blocked_components'))}",
        f"- Regressed components: {_format_review_records(result.get('regressed_components'))}",
    ]
    return "\n".join(lines).rstrip() + "\n"


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


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str) and item]


def _object_list(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def _object_dict(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _format_review_values(value: object) -> str:
    items = _string_list(value)
    if not items:
        return "`none`"
    return ", ".join(f"`{item}`" for item in items)


def _format_review_records(value: object) -> str:
    items = _object_list(value)
    if not items:
        return "`none`"
    ids = []
    for item in items:
        if isinstance(item, dict):
            ids.append(str(item.get("id", "n/a")))
    if not ids:
        return f"`{len(items)}`"
    return ", ".join(f"`{item}`" for item in ids)


def _promotion_anchor_state_indexes(manifest: dict[str, Any]) -> dict[str, list[int]]:
    anchors = manifest.get("anchors", [])
    anchors = anchors if isinstance(anchors, list) else []
    states_by_index: dict[int, set[str]] = {index: set() for index in range(len(anchors))}
    for index, anchor in enumerate(anchors):
        if not isinstance(anchor, dict):
            continue
        state = anchor.get("promotion_state")
        if state in {"promoted", "rejected", "deferred", "fallback"}:
            states_by_index[index].add(str(state))
    promotion = manifest.get("promotion", {})
    if isinstance(promotion, dict):
        regions = promotion.get("regions", [])
        if isinstance(regions, list):
            for region in regions:
                if not isinstance(region, dict):
                    continue
                state = region.get("state")
                if state not in {"promoted", "rejected", "deferred"}:
                    continue
                selected = region.get("selected_anchor_indexes", [])
                if not isinstance(selected, list):
                    continue
                for index in selected:
                    if isinstance(index, int) and 0 <= index < len(anchors):
                        states_by_index[index].add(str(state))

    state_indexes = {
        "promoted": [],
        "fallback": [],
        "rejected": [],
        "deferred": [],
    }
    for index in range(len(anchors)):
        state_indexes[_anchor_promotion_state(states_by_index[index])].append(index)
    return state_indexes


def _anchor_promotion_state(states: set[str]) -> str:
    if "promoted" in states:
        return "promoted"
    if "rejected" in states:
        return "rejected"
    if "deferred" in states:
        return "deferred"
    return "fallback"


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
