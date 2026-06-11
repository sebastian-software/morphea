"""Experiment run directory writing and lightweight reports."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from html import escape
from pathlib import Path

from PIL import Image

from curve.rendering import raster_fidelity_metrics, render_manifest_image
from curve.scene import Scene


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
    preview = render_manifest_image(manifest)
    if input_path.exists():
        with Image.open(input_path) as source:
            manifest.setdefault("metrics", {}).update(
                raster_fidelity_metrics(source=source, rendered=preview)
            )

    svg_path.write_text(scene.to_svg(), encoding="utf-8")
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
    lines = [
        "# Curve Vectorize Report",
        "",
        "## Summary",
        "",
        f"- Size: {manifest.get('width')} x {manifest.get('height')}",
        f"- Anchors: {manifest.get('anchor_count', len(anchors))}",
        f"- Layers: {len(layers)}",
        f"- Groups: {len(groups)}",
        f"- Diagnostics: {len(diagnostics)}",
        f"- Editability score: {metrics.get('editability_score', 'n/a')}",
        f"- Fragmentation penalty: {metrics.get('fragmentation_penalty', 'n/a')}",
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
            indexes = group.get("anchor_indexes", [])
            details = f"{len(indexes)} anchors"
            if group.get("color") is not None:
                details = f"{details}, color `{group.get('color')}`"
            lines.append(f"- `{group.get('kind')}`: {details}")
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
    anchor_counts = _counts(anchor.get("kind") for anchor in anchors)
    lines = [
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        '  <meta charset="utf-8">',
        "  <title>Curve Vectorize Report</title>",
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
        "  <h1>Curve Vectorize Report</h1>",
        "  <h2>Summary</h2>",
        "  <ul>",
        f"    <li>Size: {escape(str(manifest.get('width')))} x {escape(str(manifest.get('height')))}</li>",
        f"    <li>Anchors: {escape(str(manifest.get('anchor_count', len(anchors))))}</li>",
        f"    <li>Layers: {len(layers)}</li>",
        f"    <li>Groups: {len(groups)}</li>",
        f"    <li>Diagnostics: {len(diagnostics)}</li>",
        f"    <li>Editability score: {escape(str(metrics.get('editability_score', 'n/a')))}</li>",
        f"    <li>Fragmentation penalty: {escape(str(metrics.get('fragmentation_penalty', 'n/a')))}</li>",
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
    return details


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
        reserved = anchor.get("reserved", {})
        bounds = reserved.get("bounds", []) if isinstance(reserved, dict) else []
        masks.append(
            {
                "anchor_id": anchor.get("id"),
                "kind": anchor.get("kind"),
                "color": anchor.get("color"),
                "layer": anchor.get("layer"),
                "bounds": bounds,
                "source": "reserved_bounds",
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
