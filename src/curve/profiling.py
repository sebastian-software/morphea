"""Lightweight profiling helpers for bounded vectorize runs."""

from __future__ import annotations

import json
from pathlib import Path
from statistics import mean
from time import perf_counter
from typing import Any

from curve.diagnostics import diagnostic_stage_counts
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
    runs = _profile_runs(input_path, repeats=repeats, config=vectorize_config)
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


def profile_curated_suite(
    suite: str | Path,
    *,
    output: str | Path,
    repeats: int = 1,
    markdown: str | Path | None = None,
) -> dict[str, Any]:
    if repeats < 1:
        raise ValueError("profile-curated repeats must be at least 1")
    suite_path = Path(suite)
    suite_data = json.loads(suite_path.read_text(encoding="utf-8"))
    cases = suite_data.get("cases", [])
    if not isinstance(cases, list):
        cases = []

    case_reports = []
    elapsed_by_case: list[tuple[str, float]] = []
    for case in cases:
        if not isinstance(case, dict):
            continue
        case_id = str(case.get("id", f"case-{len(case_reports):04d}"))
        source = case.get("source")
        source_path = Path(str(source)) if source is not None else None
        config = case.get("recommended_config", {})
        vectorize_config = dict(config) if isinstance(config, dict) else {}
        if source_path is None or not source_path.exists():
            case_reports.append(
                {
                    "id": case_id,
                    "source": str(source) if source is not None else None,
                    "status": "missing_source",
                    "config": vectorize_config,
                    "runs": [],
                    "summary": {},
                }
            )
            continue
        runs = _profile_runs(source_path, repeats=repeats, config=vectorize_config)
        elapsed_values = [float(run["elapsed_seconds"]) for run in runs]
        summary = {
            "min_elapsed_seconds": min(elapsed_values),
            "mean_elapsed_seconds": mean(elapsed_values),
            "max_elapsed_seconds": max(elapsed_values),
        }
        elapsed_by_case.append((case_id, float(summary["max_elapsed_seconds"])))
        case_reports.append(
            {
                "id": case_id,
                "source": str(source_path),
                "status": "checked",
                "config": vectorize_config,
                "runs": runs,
                "summary": summary,
            }
        )

    checked = [
        case
        for case in case_reports
        if case.get("status") == "checked"
    ]
    missing = [
        case
        for case in case_reports
        if case.get("status") == "missing_source"
    ]
    slowest = max(elapsed_by_case, key=lambda item: item[1]) if elapsed_by_case else None
    report = {
        "schema_version": 1,
        "suite": str(suite_path),
        "repeat_count": repeats,
        "case_count": len(case_reports),
        "checked_count": len(checked),
        "missing_source_count": len(missing),
        "cases": case_reports,
        "summary": {
            "slowest_case_id": slowest[0] if slowest else None,
            "max_elapsed_seconds": slowest[1] if slowest else None,
            "mean_case_elapsed_seconds": (
                mean(value for _, value in elapsed_by_case)
                if elapsed_by_case
                else None
            ),
        },
    }
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    if markdown is not None:
        markdown_path = Path(markdown)
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(
            render_curated_profile_markdown(report),
            encoding="utf-8",
        )
    return report


def render_curated_profile_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Curated Profile",
        "",
        f"- Suite: `{report.get('suite')}`",
        f"- Cases: `{report.get('case_count', 0)}`",
        f"- Checked: `{report.get('checked_count', 0)}`",
        f"- Missing sources: `{report.get('missing_source_count', 0)}`",
        f"- Slowest case: `{report.get('summary', {}).get('slowest_case_id') or 'n/a'}`",
        "",
        "| Case | Status | Max elapsed | Anchors | Diagnostics |",
        "| --- | --- | ---: | ---: | ---: |",
    ]
    cases = report.get("cases", [])
    if not isinstance(cases, list):
        cases = []
    for case in cases:
        if not isinstance(case, dict):
            continue
        runs = case.get("runs", [])
        if not isinstance(runs, list):
            runs = []
        summary = case.get("summary", {})
        if not isinstance(summary, dict):
            summary = {}
        anchors = max(
            (int(run.get("anchor_count", 0)) for run in runs if isinstance(run, dict)),
            default=0,
        )
        diagnostics = max(
            (
                int(run.get("diagnostic_count", 0))
                for run in runs
                if isinstance(run, dict)
            ),
            default=0,
        )
        elapsed = summary.get("max_elapsed_seconds")
        elapsed_text = (
            f"{float(elapsed):.4f}"
            if isinstance(elapsed, (int, float))
            else "n/a"
        )
        lines.append(
            "| "
            f"`{case.get('id')}` | "
            f"`{case.get('status')}` | "
            f"{elapsed_text} | "
            f"{anchors} | "
            f"{diagnostics} |"
        )
    return "\n".join(lines) + "\n"


def _profile_runs(
    input_path: str | Path,
    *,
    repeats: int,
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    runs = []
    for index in range(repeats):
        started = perf_counter()
        scene = scene_from_flat_color_image(input_path, **config)
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
                "diagnostic_stage_counts": diagnostic_stage_counts(scene.diagnostics),
            }
        )
    return runs
