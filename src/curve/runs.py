"""Experiment run directory writing and lightweight reports."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from curve.scene import Scene


@dataclass(frozen=True)
class VectorizeRun:
    run_dir: Path
    svg_path: Path
    manifest_path: Path
    config_path: Path
    report_path: Path
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

    manifest = scene.to_manifest()
    svg_path.write_text(scene.to_svg(), encoding="utf-8")
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

    return VectorizeRun(
        run_dir=run_dir,
        svg_path=svg_path,
        manifest_path=manifest_path,
        config_path=config_path,
        report_path=report_path,
        input_path=copied_input,
    )


def render_markdown_report(
    *,
    manifest: dict[str, object],
    config: dict[str, object],
) -> str:
    anchors = list(manifest.get("anchors", []))
    diagnostics = list(manifest.get("diagnostics", []))
    groups = list(manifest.get("groups", []))
    lines = [
        "# Curve Vectorize Report",
        "",
        "## Summary",
        "",
        f"- Size: {manifest.get('width')} x {manifest.get('height')}",
        f"- Anchors: {manifest.get('anchor_count', len(anchors))}",
        f"- Groups: {len(groups)}",
        f"- Diagnostics: {len(diagnostics)}",
        "",
        "## Anchor Types",
        "",
    ]
    for kind, count in _counts(anchor.get("kind") for anchor in anchors).items():
        lines.append(f"- `{kind}`: {count}")

    lines.extend(["", "## Diagnostics", ""])
    if diagnostics:
        for diagnostic in diagnostics:
            code = diagnostic.get("code", "unknown")
            level = diagnostic.get("level", "info")
            lines.append(f"- `{level}` `{code}`")
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

