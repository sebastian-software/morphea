"""Evaluation helpers for Curve run directories."""

from __future__ import annotations

import json
from pathlib import Path


def evaluate_runs(run_root: str | Path) -> dict[str, object]:
    root = Path(run_root)
    run_summaries: list[dict[str, object]] = []
    for manifest_path in sorted(root.glob("*/manifest.json")):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        anchors = list(manifest.get("anchors", []))
        diagnostics = list(manifest.get("diagnostics", []))
        groups = list(manifest.get("groups", []))
        layers = list(manifest.get("layers", []))
        metrics = dict(manifest.get("metrics", {}))
        run_summaries.append(
            {
                "run": manifest_path.parent.name,
                "anchor_count": manifest.get("anchor_count", len(anchors)),
                "layer_count": len(layers),
                "group_count": len(groups),
                "diagnostic_count": len(diagnostics),
                "editability_score": metrics.get("editability_score"),
                "fragmentation_penalty": metrics.get("fragmentation_penalty"),
                "raster_l1_error": metrics.get("raster_l1_error"),
                "raster_alpha_error": metrics.get("raster_alpha_error"),
                "raster_edge_error": metrics.get("raster_edge_error"),
                "anchor_types": _counts(anchor.get("kind") for anchor in anchors),
                "diagnostic_codes": _counts(
                    diagnostic.get("code") for diagnostic in diagnostics
                ),
                "metrics": metrics,
            }
        )

    return {
        "run_count": len(run_summaries),
        "runs": run_summaries,
    }


def write_eval_summary(
    *,
    run_root: str | Path,
    output: str | Path,
    markdown: str | Path | None = None,
) -> dict[str, object]:
    summary = evaluate_runs(run_root)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    if markdown is not None:
        markdown = Path(markdown)
        markdown.parent.mkdir(parents=True, exist_ok=True)
        markdown.write_text(render_eval_markdown(summary), encoding="utf-8")
    return summary


def render_eval_markdown(summary: dict[str, object]) -> str:
    lines = [
        "# Curve Eval Summary",
        "",
        f"- Runs: {summary.get('run_count', 0)}",
        "",
        "## Runs",
        "",
    ]
    for run in summary.get("runs", []):
        lines.append(f"### {run['run']}")
        lines.append("")
        lines.append(f"- Anchors: {run['anchor_count']}")
        lines.append(f"- Layers: {run.get('layer_count', 0)}")
        lines.append(f"- Groups: {run['group_count']}")
        lines.append(f"- Diagnostics: {run['diagnostic_count']}")
        lines.append(f"- Editability score: {run.get('editability_score', 'n/a')}")
        lines.append(
            f"- Fragmentation penalty: {run.get('fragmentation_penalty', 'n/a')}"
        )
        lines.append(f"- Raster L1 error: {run.get('raster_l1_error', 'n/a')}")
        lines.append(f"- Raster edge error: {run.get('raster_edge_error', 'n/a')}")
        lines.append("")
    return "\n".join(lines)


def _counts(values: object) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        key = str(value)
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))
