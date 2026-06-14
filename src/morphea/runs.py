"""Experiment run directory writing and lightweight reports."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from html import escape
from pathlib import Path

from PIL import Image

from morphea.diagnostics import diagnostic_stage_counts
from morphea.rendering import raster_fidelity_metrics, render_manifest_image
from morphea.scene import Scene, SvgStyle, refresh_raster_editability_component


@dataclass(frozen=True)
class VectorizeRun:
    run_dir: Path
    svg_path: Path
    manifest_path: Path
    config_path: Path
    report_path: Path
    html_report_path: Path
    preview_path: Path
    debug_svg_path: Path
    anchors_path: Path
    palette_path: Path
    mask_summary_path: Path
    input_path: Path


def create_run_dir(root: str | Path, *, prefix: str = "vectorize") -> Path:
    root = Path(root)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    candidate = root / f"{timestamp}-{prefix}"
    suffix = 1
    while candidate.exists():
        candidate = root / f"{timestamp}-{prefix}-{suffix:02d}"
        suffix += 1
    candidate.mkdir(parents=True)
    return candidate


def write_vectorize_run(
    *,
    run_dir: str | Path,
    input_path: str | Path,
    scene: Scene,
    config: dict[str, object],
) -> VectorizeRun:
    run_dir = Path(run_dir)
    input_path = Path(input_path)
    input_dir = run_dir / "input"
    input_dir.mkdir(parents=True, exist_ok=True)
    copied_input = input_dir / input_path.name
    if input_path.exists():
        shutil.copy2(input_path, copied_input)

    svg_path = run_dir / "output.svg"
    manifest_path = run_dir / "manifest.json"
    config_path = run_dir / "config.json"
    report_path = run_dir / "report.md"
    html_report_path = run_dir / "report.html"
    preview_path = run_dir / "preview.png"
    debug_svg_path = run_dir / "debug.svg"
    anchors_path = run_dir / "anchors.json"
    palette_path = run_dir / "palette.json"
    mask_summary_path = run_dir / "mask-summary.json"

    manifest = scene.to_manifest()
    preview_background = str(config.get("preview_background", "#ffffff"))
    preview = render_manifest_image(manifest, background=preview_background)
    if input_path.exists():
        with Image.open(input_path) as source:
            metrics = manifest.setdefault("metrics", {})
            metrics.update(
                raster_fidelity_metrics(
                    source=source,
                    rendered=preview,
                    background=preview_background,
                )
            )
            if isinstance(metrics, dict):
                refresh_raster_editability_component(metrics)

    cutout_export = str(config.get("cutout_export", "overlay_stroke"))
    svg_path.write_text(
        scene.to_svg(SvgStyle(cutout_strategy=cutout_export)),
        encoding="utf-8",
    )
    debug_svg_path.write_text(scene.to_debug_svg(), encoding="utf-8")
    anchors_path.write_text(
        json.dumps(_anchors_artifact(manifest), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    palette_path.write_text(
        json.dumps(_palette_artifact(manifest), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    mask_summary_path.write_text(
        json.dumps(_mask_summary_artifact(manifest), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    config_path.write_text(
        json.dumps(config, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    report_path.write_text(
        render_markdown_report(manifest=manifest, config=config),
        encoding="utf-8",
    )
    html_report_path.write_text(
        render_html_report(manifest=manifest, config=config),
        encoding="utf-8",
    )
    preview.save(preview_path)

    return VectorizeRun(
        run_dir=run_dir,
        svg_path=svg_path,
        manifest_path=manifest_path,
        config_path=config_path,
        report_path=report_path,
        html_report_path=html_report_path,
        preview_path=preview_path,
        debug_svg_path=debug_svg_path,
        anchors_path=anchors_path,
        palette_path=palette_path,
        mask_summary_path=mask_summary_path,
        input_path=copied_input,
    )


def write_markdown_report(
    *,
    manifest: str | Path,
    output: str | Path,
    config: str | Path | None = None,
) -> str:
    manifest_data = json.loads(Path(manifest).read_text(encoding="utf-8"))
    config_data: dict[str, object] = {}
    if config is not None:
        config_data = json.loads(Path(config).read_text(encoding="utf-8"))
    report = render_markdown_report(manifest=manifest_data, config=config_data)
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")
    return report


def write_html_report(
    *,
    manifest: str | Path,
    output: str | Path,
    config: str | Path | None = None,
) -> str:
    manifest_data = json.loads(Path(manifest).read_text(encoding="utf-8"))
    config_data: dict[str, object] = {}
    if config is not None:
        config_data = json.loads(Path(config).read_text(encoding="utf-8"))
    report = render_html_report(manifest=manifest_data, config=config_data)
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")
    return report


def render_markdown_report(
    *,
    manifest: dict[str, object],
    config: dict[str, object],
) -> str:
    anchors = list(manifest.get("anchors", []))
    diagnostics = list(manifest.get("diagnostics", []))
    groups = list(manifest.get("groups", []))
    layers = list(manifest.get("layers", []))
    metrics = dict(manifest.get("metrics", {}))
    scoring = metrics.get("anchor_scoring_summary", {})
    if not isinstance(scoring, dict):
        scoring = {}
    editability_components = _editability_component_summary(
        metrics.get("editability_components")
    )
    editability_v10_components = _editability_v10_component_summary(
        metrics.get("editability_v10_components")
    )
    stage_counts = diagnostic_stage_counts(diagnostics)
    lines = [
        "# Morphēa Vectorize Report",
        "",
        "## Summary",
        "",
        f"- Size: {manifest.get('width')} x {manifest.get('height')}",
        f"- Anchors: {manifest.get('anchor_count', len(anchors))}",
        f"- Layers: {len(layers)}",
        f"- Groups: {len(groups)}",
        f"- Diagnostics: {len(diagnostics)}",
        f"- Editability score: {metrics.get('editability_score', 'n/a')}",
        f"- Editability components: {editability_components}",
        f"- Editability v10 components: {editability_v10_components}",
        f"- Fragmentation penalty: {metrics.get('fragmentation_penalty', 'n/a')}",
        f"- Anchor quality error mean: {metrics.get('anchor_quality_error_mean', 'n/a')}",
        f"- Anchor quality error max: {metrics.get('anchor_quality_error_max', 'n/a')}",
        f"- Simple-shape priority bonus total: {scoring.get('simple_shape_priority_bonus_total', 'n/a')}",
        f"- Semantic anchor score mean: {scoring.get('semantic_anchor_score_mean', 'n/a')}",
        "",
        "## Anchor Types",
        "",
    ]
    for kind, count in _counts(anchor.get("kind") for anchor in anchors).items():
        lines.append(f"- `{kind}`: {count}")

    lines.extend(["", "## Layers", ""])
    if layers:
        for layer in layers:
            lines.append(f"- `{layer.get('name')}`: {layer.get('anchor_count', 0)}")
    else:
        lines.append("- none")

    lines.extend(["", "## Groups", ""])
    if groups:
        for group in groups:
            lines.append(f"- `{group.get('kind')}`: {_group_report_details(group)}")
    else:
        lines.append("- none")

    lines.extend(["", "## Pipeline Stages", ""])
    if stage_counts:
        for stage, count in stage_counts.items():
            lines.append(f"- `{stage}`: {count}")
    else:
        lines.append("- none")

    lines.extend(["", "## Diagnostics", ""])
    if diagnostics:
        for diagnostic in diagnostics:
            code = diagnostic.get("code", "unknown")
            level = diagnostic.get("level", "info")
            lines.append(f"- `{level}` `{code}`")
    else:
        lines.append("- none")

    lines.extend(["", "## Metrics", ""])
    if metrics:
        for key, value in sorted(metrics.items()):
            if isinstance(value, dict):
                lines.append(f"- `{key}`: `{json.dumps(value, sort_keys=True)}`")
            else:
                lines.append(f"- `{key}`: {value}")
    else:
        lines.append("- none")

    lines.extend(["", "## Config", "", "```json"])
    lines.append(json.dumps(config, indent=2, sort_keys=True))
    lines.append("```")
    return "\n".join(lines) + "\n"


def render_html_report(
    *,
    manifest: dict[str, object],
    config: dict[str, object],
) -> str:
    anchors = list(manifest.get("anchors", []))
    diagnostics = list(manifest.get("diagnostics", []))
    groups = list(manifest.get("groups", []))
    layers = list(manifest.get("layers", []))
    metrics = dict(manifest.get("metrics", {}))
    scoring = metrics.get("anchor_scoring_summary", {})
    if not isinstance(scoring, dict):
        scoring = {}
    editability_components = _editability_component_summary(
        metrics.get("editability_components")
    )
    editability_v10_components = _editability_v10_component_summary(
        metrics.get("editability_v10_components")
    )
    anchor_counts = _counts(anchor.get("kind") for anchor in anchors)
    stage_counts = diagnostic_stage_counts(diagnostics)
    lines = [
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        '  <meta charset="utf-8">',
        "  <title>Morphēa Vectorize Report</title>",
        "  <style>",
        "    body{font-family:system-ui,sans-serif;margin:32px;max-width:980px}",
        "    table{border-collapse:collapse;width:100%;margin:16px 0}",
        "    th,td{border:1px solid #ddd;padding:6px 8px;text-align:left}",
        "    th{background:#f4f4f4}",
        "    code,pre{background:#f7f7f7;padding:2px 4px}",
        "    pre{padding:12px;overflow:auto}",
        "  </style>",
        "</head>",
        "<body>",
        "  <h1>Morphēa Vectorize Report</h1>",
        "  <h2>Summary</h2>",
        "  <ul>",
        f"    <li>Size: {escape(str(manifest.get('width')))} x {escape(str(manifest.get('height')))}</li>",
        f"    <li>Anchors: {escape(str(manifest.get('anchor_count', len(anchors))))}</li>",
        f"    <li>Layers: {len(layers)}</li>",
        f"    <li>Groups: {len(groups)}</li>",
        f"    <li>Diagnostics: {len(diagnostics)}</li>",
        f"    <li>Editability score: {escape(str(metrics.get('editability_score', 'n/a')))}</li>",
        f"    <li>Editability components: {escape(editability_components)}</li>",
        f"    <li>Editability v10 components: {escape(editability_v10_components)}</li>",
        f"    <li>Fragmentation penalty: {escape(str(metrics.get('fragmentation_penalty', 'n/a')))}</li>",
        f"    <li>Anchor quality error mean: {escape(str(metrics.get('anchor_quality_error_mean', 'n/a')))}</li>",
        f"    <li>Anchor quality error max: {escape(str(metrics.get('anchor_quality_error_max', 'n/a')))}</li>",
        f"    <li>Simple-shape priority bonus total: {escape(str(scoring.get('simple_shape_priority_bonus_total', 'n/a')))}</li>",
        f"    <li>Semantic anchor score mean: {escape(str(scoring.get('semantic_anchor_score_mean', 'n/a')))}</li>",
        "  </ul>",
        "  <h2>Anchor Types</h2>",
        _html_table(("Kind", "Count"), anchor_counts.items()),
        "  <h2>Layers</h2>",
        _html_table(
            ("Layer", "Anchors"),
            ((layer.get("name"), layer.get("anchor_count", 0)) for layer in layers),
        )
        if layers
        else "  <p>none</p>",
        "  <h2>Groups</h2>",
        _html_table(
            ("Group", "Details"),
            (
                (
                    group.get("kind"),
                    _group_report_details(group),
                )
                for group in groups
            ),
        )
        if groups
        else "  <p>none</p>",
        "  <h2>Pipeline Stages</h2>",
        _html_table(("Stage", "Diagnostics"), stage_counts.items())
        if stage_counts
        else "  <p>none</p>",
        "  <h2>Diagnostics</h2>",
        _html_table(
            ("Level", "Code"),
            (
                (diagnostic.get("level", "info"), diagnostic.get("code", "unknown"))
                for diagnostic in diagnostics
            ),
        )
        if diagnostics
        else "  <p>none</p>",
        "  <h2>Metrics</h2>",
        _html_table(
            ("Metric", "Value"),
            (
                (
                    key,
                    json.dumps(value, sort_keys=True)
                    if isinstance(value, dict)
                    else value,
                )
                for key, value in sorted(metrics.items())
            ),
        )
        if metrics
        else "  <p>none</p>",
        "  <h2>Config</h2>",
        f"  <pre>{escape(json.dumps(config, indent=2, sort_keys=True))}</pre>",
        "</body>",
        "</html>",
    ]
    return "\n".join(lines) + "\n"


def _html_table(
    headers: tuple[str, str],
    rows: object,
) -> str:
    body = [
        "  <table>",
        "    <thead>",
        "      <tr>"
        f"<th>{escape(str(headers[0]))}</th>"
        f"<th>{escape(str(headers[1]))}</th>"
        "</tr>",
        "    </thead>",
        "    <tbody>",
    ]
    row_count = 0
    for left, right in rows:
        row_count += 1
        body.append(
            "      <tr>"
            f"<td><code>{escape(str(left))}</code></td>"
            f"<td>{escape(str(right))}</td>"
            "</tr>"
        )
    if row_count == 0:
        body.append("      <tr><td colspan=\"2\">none</td></tr>")
    body.extend(["    </tbody>", "  </table>"])
    return "\n".join(body)


def _group_report_details(group: dict[str, object]) -> str:
    indexes = group.get("anchor_indexes", [])
    count = len(indexes) if isinstance(indexes, list) else 0
    details = f"{count} anchors"
    if group.get("color") is not None:
        details = f"{details}, color {group.get('color')}"
    merge_plan = group.get("merge_plan", {})
    if isinstance(merge_plan, dict) and merge_plan.get("action") is not None:
        details = f"{details}, action {merge_plan.get('action')}"
        if merge_plan.get("decision_reason") is not None:
            details = f"{details}, reason {merge_plan.get('decision_reason')}"
    return details


def _editability_component_summary(value: object) -> str:
    if not isinstance(value, dict):
        return "n/a"
    keys = (
        "simple_shape_ratio",
        "fragmentation_penalty",
        "diagnostic_penalty",
        "generic_path_penalty",
        "unclipped_score",
        "clipped_score",
    )
    parts = [
        f"{key}={value[key]}"
        for key in keys
        if key in value
    ]
    return ", ".join(parts) if parts else "n/a"


def _editability_v10_component_summary(value: object) -> str:
    if not isinstance(value, dict):
        return "n/a"
    parts = []
    for key in (
        "shape_identity_confidence",
        "parameter_economy",
        "node_economy",
        "stroke_width_stability",
        "line_curve_smoothness",
        "topology_consistency",
        "grouping_quality",
        "fragmentation",
        "raster_fidelity",
        "provenance_confidence",
        "classifier_prior_agreement",
    ):
        component = value.get(key)
        if not isinstance(component, dict):
            continue
        score = component.get("score")
        if score is None:
            parts.append(f"{key}=n/a")
        else:
            parts.append(f"{key}={score}")
    return ", ".join(parts) if parts else "n/a"


def _anchors_artifact(manifest: dict[str, object]) -> dict[str, object]:
    anchors = list(manifest.get("anchors", []))
    return {
        "schema_version": 1,
        "anchor_count": len(anchors),
        "anchors": anchors,
    }


def _palette_artifact(manifest: dict[str, object]) -> dict[str, object]:
    entries: dict[str, dict[str, object]] = {}
    for anchor in manifest.get("anchors", []):
        if not isinstance(anchor, dict):
            continue
        color = str(anchor.get("color") or "none")
        entry = entries.setdefault(
            color,
            {
                "color": color,
                "anchor_count": 0,
                "kinds": {},
                "layers": {},
            },
        )
        entry["anchor_count"] = int(entry["anchor_count"]) + 1
        _increment_count(entry["kinds"], str(anchor.get("kind")))
        _increment_count(entry["layers"], str(anchor.get("layer")))
    palette = sorted(entries.values(), key=lambda entry: str(entry["color"]))
    return {
        "schema_version": 1,
        "color_count": len(palette),
        "colors": palette,
    }


def _mask_summary_artifact(manifest: dict[str, object]) -> dict[str, object]:
    masks: list[dict[str, object]] = []
    for anchor in manifest.get("anchors", []):
        if not isinstance(anchor, dict):
            continue
        source_mask = anchor.get("source_mask", {})
        source_mask = source_mask if isinstance(source_mask, dict) else {}
        masks.append(
            {
                "id": source_mask.get("id"),
                "anchor_id": anchor.get("id"),
                "kind": anchor.get("kind"),
                "color": anchor.get("color"),
                "layer": anchor.get("layer"),
                "bounds": source_mask.get("bounds", []),
                "bounds_area": source_mask.get("bounds_area", 0.0),
                "source": source_mask.get("source", "reserved_bounds"),
            }
        )
    return {
        "schema_version": 1,
        "mask_count": len(masks),
        "masks": masks,
    }


def _increment_count(counts: object, key: str) -> None:
    if isinstance(counts, dict):
        counts[key] = int(counts.get(key, 0)) + 1


def _counts(values: object) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        key = str(value)
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))
