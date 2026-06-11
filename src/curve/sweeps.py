"""Config-driven experiment sweeps for vectorize runs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from curve.images import scene_from_flat_color_image
from curve.runs import write_vectorize_run


SWEEP_SCHEMA_VERSION = 1
VECTORIZE_CONFIG_KEYS = {
    "min_area",
    "color_tolerance",
    "max_size",
    "max_colors",
    "max_component_area",
    "timeout_seconds",
    "classifier_model",
}


def load_sweep_config(path: str | Path) -> dict[str, Any]:
    config_path = Path(path)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError("sweep config must be a JSON object")
    if config.get("version") != SWEEP_SCHEMA_VERSION:
        raise ValueError("sweep config version must be 1")
    input_path = config.get("input")
    if not isinstance(input_path, str) or not input_path:
        raise ValueError("sweep config must have a non-empty input")
    runs = config.get("runs")
    if not isinstance(runs, list) or not runs:
        raise ValueError("sweep config must contain at least one run")
    seen_ids: set[str] = set()
    for index, run in enumerate(runs):
        if not isinstance(run, dict):
            raise ValueError(f"sweep run {index} must be an object")
        run_id = run.get("id")
        if not isinstance(run_id, str) or not run_id:
            raise ValueError(f"sweep run {index} must have a non-empty id")
        if run_id in seen_ids:
            raise ValueError(f"duplicate sweep run id: {run_id}")
        seen_ids.add(run_id)
        run_config = run.get("config", {})
        if not isinstance(run_config, dict):
            raise ValueError(f"sweep run {run_id} config must be an object")
    return config


def run_sweep(
    sweep_config: str | Path,
    *,
    output_dir: str | Path,
    markdown: str | Path | None = None,
) -> dict[str, Any]:
    config_path = Path(sweep_config)
    config = load_sweep_config(config_path)
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    input_path = Path(config["input"]).expanduser()
    if not input_path.exists():
        raise FileNotFoundError(f"sweep input does not exist: {input_path}")

    run_results = []
    for run in config["runs"]:
        run_id = run["id"]
        vectorize_config = _vectorize_config(run.get("config", {}))
        effective_config = {
            "command": "sweep",
            "sweep": str(config_path),
            "run_id": run_id,
            "input": str(input_path),
            **vectorize_config,
        }
        scene = scene_from_flat_color_image(input_path, **vectorize_config)
        run_dir = root / run_id
        vectorize_run = write_vectorize_run(
            run_dir=run_dir,
            input_path=input_path,
            scene=scene,
            config=effective_config,
        )
        manifest = json.loads(vectorize_run.manifest_path.read_text(encoding="utf-8"))
        metrics = dict(manifest.get("metrics", {}))
        run_results.append(
            {
                "id": run_id,
                "run_dir": str(vectorize_run.run_dir),
                "anchor_count": manifest["anchor_count"],
                "layer_count": len(manifest["layers"]),
                "group_count": len(manifest["groups"]),
                "diagnostic_count": len(manifest["diagnostics"]),
                "editability_score": metrics.get("editability_score"),
                "fragmentation_penalty": metrics.get("fragmentation_penalty"),
                "raster_l1_error": metrics.get("raster_l1_error"),
                "raster_edge_error": metrics.get("raster_edge_error"),
            }
        )

    summary = {
        "schema_version": SWEEP_SCHEMA_VERSION,
        "sweep": str(config_path),
        "input": str(input_path),
        "run_count": len(run_results),
        "runs": run_results,
    }
    (root / "sweep-summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    if markdown is not None:
        markdown_path = Path(markdown)
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(render_sweep_markdown(summary), encoding="utf-8")
    return summary


def render_sweep_markdown(summary: dict[str, Any]) -> str:
    runs = list(summary.get("runs", []))
    ranked = sorted(
        runs,
        key=lambda run: (
            -(float(run.get("editability_score") or 0.0)),
            float(run.get("raster_l1_error") or 1.0),
            str(run.get("id", "")),
        ),
    )
    lines = [
        "# Curve Sweep Summary",
        "",
        f"- Runs: {summary.get('run_count', len(runs))}",
        f"- Input: `{summary.get('input', '')}`",
        "",
        "## Ranked Runs",
        "",
        "| Rank | Run | Editability | Raster L1 | Edge Error | Anchors | Diagnostics |",
        "| ---: | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for rank, run in enumerate(ranked, start=1):
        lines.append(
            "| "
            f"{rank} | `{run.get('id')}` | "
            f"{_fmt(run.get('editability_score'))} | "
            f"{_fmt(run.get('raster_l1_error'))} | "
            f"{_fmt(run.get('raster_edge_error'))} | "
            f"{run.get('anchor_count', 'n/a')} | "
            f"{run.get('diagnostic_count', 'n/a')} |"
        )

    lines.extend(["", "## Run Directories", ""])
    for run in runs:
        lines.append(f"- `{run.get('id')}`: `{run.get('run_dir')}`")
    return "\n".join(lines) + "\n"


def _fmt(value: object) -> str:
    if isinstance(value, (int, float)):
        return f"{value:.6g}"
    return "n/a"


def _vectorize_config(config: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in config.items() if key in VECTORIZE_CONFIG_KEYS}
