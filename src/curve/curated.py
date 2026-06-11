"""Curated real-image regression suite helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from curve.images import scene_from_flat_color_image
from curve.runs import write_vectorize_run


VECTORIZE_CONFIG_KEYS = {
    "min_area",
    "color_tolerance",
    "max_size",
    "max_colors",
    "max_component_area",
    "timeout_seconds",
    "classifier_model",
    "raster_error_weight",
    "quality_error_weight",
    "node_complexity_weight",
    "parameter_complexity_weight",
    "simple_shape_bonus_weight",
}


def load_curated_suite(path: str | Path) -> dict[str, Any]:
    """Load and lightly validate a curated real-image suite file."""

    suite_path = Path(path)
    suite = json.loads(suite_path.read_text(encoding="utf-8"))
    if not isinstance(suite, dict):
        raise ValueError("curated suite must be a JSON object")
    if suite.get("version") != 1:
        raise ValueError("curated suite version must be 1")
    cases = suite.get("cases")
    if not isinstance(cases, list):
        raise ValueError("curated suite must contain a cases array")
    seen_ids: set[str] = set()
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            raise ValueError(f"case {index} must be a JSON object")
        case_id = case.get("id")
        if not isinstance(case_id, str) or not case_id:
            raise ValueError(f"case {index} must have a non-empty id")
        if case_id in seen_ids:
            raise ValueError(f"duplicate curated case id: {case_id}")
        seen_ids.add(case_id)
        source = case.get("source")
        if not isinstance(source, str) or not source:
            raise ValueError(f"case {case_id} must have a non-empty source")
        config = case.get("recommended_config", {})
        if not isinstance(config, dict):
            raise ValueError(f"case {case_id} recommended_config must be an object")
        expectations = case.get("expectations", [])
        if not isinstance(expectations, list):
            raise ValueError(f"case {case_id} expectations must be an array")
        for expectation_index, expectation in enumerate(expectations):
            _validate_expectation(case_id, expectation_index, expectation)
    return suite


def check_curated_suite(
    suite_path: str | Path,
    *,
    output: str | Path | None = None,
    output_dir: str | Path | None = None,
    run: bool = False,
    snapshot: str | Path | None = None,
) -> dict[str, Any]:
    """Validate a curated suite and optionally run bounded vectorization."""

    suite_file = Path(suite_path)
    suite = load_curated_suite(suite_file)
    suite_output_dir = Path(output_dir) if output_dir is not None else None
    cases = [
        _check_curated_case(case, output_dir=suite_output_dir, run=run)
        for case in suite["cases"]
    ]
    report = {
        "suite": str(suite_file),
        "version": suite["version"],
        "run": run,
        "case_count": len(cases),
        "ok": all(case["ok"] for case in cases),
        "cases": cases,
    }
    if output is not None:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(report, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    if snapshot is not None:
        snapshot_path = Path(snapshot)
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot_path.write_text(
            json.dumps(render_curated_snapshot(report), indent=2, sort_keys=True),
            encoding="utf-8",
        )
    return report


def render_curated_snapshot(report: dict[str, Any]) -> dict[str, Any]:
    """Render a deterministic summary suitable for regression diffs."""

    return {
        "schema_version": 1,
        "suite": report.get("suite"),
        "case_count": report.get("case_count", 0),
        "ok": report.get("ok", False),
        "cases": [
            _case_snapshot(case)
            for case in sorted(
                report.get("cases", []),
                key=lambda item: str(item.get("id", "")),
            )
        ],
    }


def _check_curated_case(
    case: dict[str, Any],
    *,
    output_dir: Path | None,
    run: bool,
) -> dict[str, Any]:
    source = Path(case["source"]).expanduser()
    source_exists = source.exists()
    result: dict[str, Any] = {
        "id": case["id"],
        "source": str(source),
        "source_exists": source_exists,
        "status": "not_run",
        "ok": source_exists or not run,
        "expectations": [],
    }
    if not source_exists:
        result["status"] = "missing_source"
        result["ok"] = not run
        return result
    if not run:
        return result

    config = _vectorize_config(case.get("recommended_config", {}))
    scene = scene_from_flat_color_image(source, **config)
    manifest = scene.to_manifest()
    expectation_results = [
        _check_expectation(expectation, manifest)
        for expectation in case.get("expectations", [])
    ]
    result.update(
        {
            "status": "checked",
            "ok": all(item["ok"] for item in expectation_results),
            "config": config,
            "anchor_count": manifest["anchor_count"],
            "anchor_kind_counts": _counts(
                anchor.get("kind") for anchor in manifest.get("anchors", [])
            ),
            "group_kind_counts": _counts(
                group.get("kind") for group in manifest.get("groups", [])
            ),
            "diagnostic_count": len(manifest["diagnostics"]),
            "metrics": dict(sorted(manifest.get("metrics", {}).items())),
            "expectations": expectation_results,
        }
    )
    if output_dir is not None:
        case_dir = output_dir / case["id"]
        vectorize_run = write_vectorize_run(
            run_dir=case_dir,
            input_path=source,
            scene=scene,
            config={
                "command": "curated-check",
                "case_id": case["id"],
                **config,
            },
        )
        result["artifacts"] = {
            "run_dir": str(vectorize_run.run_dir),
            "manifest": str(vectorize_run.manifest_path),
            "preview": str(vectorize_run.preview_path),
            "report": str(vectorize_run.report_path),
            "debug_svg": str(vectorize_run.debug_svg_path),
            "input": str(vectorize_run.input_path),
        }
    return result


def _check_expectation(
    expectation: dict[str, Any],
    manifest: dict[str, Any],
) -> dict[str, Any]:
    minimum = int(expectation.get("min_count", 1))
    if "kind" in expectation:
        kind = expectation["kind"]
        actual = sum(
            1
            for anchor in manifest.get("anchors", [])
            if anchor.get("kind") == kind
        )
        label = {"kind": kind}
    else:
        kind = expectation["group_kind"]
        actual = sum(
            1
            for group in manifest.get("groups", [])
            if group.get("kind") == kind
        )
        label = {"group_kind": kind}
    return {
        "id": expectation["id"],
        **label,
        "min_count": minimum,
        "actual_count": actual,
        "ok": actual >= minimum,
    }


def _vectorize_config(config: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in config.items() if key in VECTORIZE_CONFIG_KEYS}


def _case_snapshot(case: dict[str, Any]) -> dict[str, Any]:
    snapshot: dict[str, Any] = {
        "id": case.get("id"),
        "status": case.get("status"),
        "ok": case.get("ok", False),
        "source_exists": case.get("source_exists", False),
        "expectations": [
            {
                "id": expectation.get("id"),
                "ok": expectation.get("ok", False),
                "actual_count": expectation.get("actual_count", 0),
                "min_count": expectation.get("min_count", 1),
            }
            for expectation in sorted(
                case.get("expectations", []),
                key=lambda item: str(item.get("id", "")),
            )
        ],
    }
    for key in (
        "config",
        "anchor_count",
        "anchor_kind_counts",
        "group_kind_counts",
        "diagnostic_count",
        "metrics",
    ):
        if key in case:
            snapshot[key] = case[key]
    return snapshot


def _counts(values: object) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        key = str(value)
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def _validate_expectation(
    case_id: str,
    index: int,
    expectation: Any,
) -> None:
    if not isinstance(expectation, dict):
        raise ValueError(f"case {case_id} expectation {index} must be an object")
    expectation_id = expectation.get("id")
    if not isinstance(expectation_id, str) or not expectation_id:
        raise ValueError(f"case {case_id} expectation {index} must have an id")
    has_kind = isinstance(expectation.get("kind"), str)
    has_group_kind = isinstance(expectation.get("group_kind"), str)
    if has_kind == has_group_kind:
        raise ValueError(
            f"case {case_id} expectation {expectation_id} must set kind or group_kind"
        )
    min_count = expectation.get("min_count", 1)
    if not isinstance(min_count, int) or min_count < 1:
        raise ValueError(
            f"case {case_id} expectation {expectation_id} min_count must be positive"
        )
