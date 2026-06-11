"""Lightweight profiling helpers for bounded vectorize runs."""

from __future__ import annotations

import json
from pathlib import Path
from statistics import mean
from time import perf_counter
from typing import Any

from curve.images import scene_from_flat_color_image


def profile_vectorize(
    input_path: str | Path,
    *,
    output: str | Path,
    repeats: int = 1,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if repeats < 1:
        raise ValueError("profile repeats must be at least 1")
    vectorize_config = dict(config or {})
    runs = []
    for index in range(repeats):
        started = perf_counter()
        scene = scene_from_flat_color_image(input_path, **vectorize_config)
        elapsed = perf_counter() - started
        runs.append(
            {
                "index": index,
                "elapsed_seconds": elapsed,
                "anchor_count": len(scene.anchors),
                "diagnostic_count": len(scene.diagnostics),
                "diagnostic_codes": [
                    diagnostic.get("code")
                    for diagnostic in scene.diagnostics
                    if isinstance(diagnostic, dict)
                ],
            }
        )

    elapsed_values = [float(run["elapsed_seconds"]) for run in runs]
    report = {
        "schema_version": 1,
        "input": str(input_path),
        "repeat_count": repeats,
        "config": vectorize_config,
        "runs": runs,
        "summary": {
            "min_elapsed_seconds": min(elapsed_values),
            "mean_elapsed_seconds": mean(elapsed_values),
            "max_elapsed_seconds": max(elapsed_values),
        },
    }
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return report
