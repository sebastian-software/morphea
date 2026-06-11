"""Experiment run directory writing and lightweight reports."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
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
    preview_path: Path
    debug_svg_path: Path
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
    preview_path = run_dir / "preview.png"
    debug_svg_path = run_dir / "debug.svg"

    manifest = scene.to_manifest()
    preview = render_manifest_image(manifest)
    if input_path.exists():
        with Image.open(input_path) as source:
            manifest.setdefault("metrics", {}).update(
                raster_fidelity_metrics(source=source, rendered=preview)
            )

    svg_path.write_text(scene.to_svg(), encoding="utf-8")
    debug_svg_path.write_text(scene.to_debug_svg(), encoding="utf-8")
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
    preview.save(preview_path)

    return VectorizeRun(
        run_dir=run_dir,
        svg_path=svg_path,
        manifest_path=manifest_path,
        config_path=config_path,
        report_path=report_path,
        preview_path=preview_path,
        debug_svg_path=debug_svg_path,
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


def _counts(values: object) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        key = str(value)
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))
