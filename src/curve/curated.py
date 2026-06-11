"""Curated real-image regression suite helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from curve.images import scene_from_flat_color_image
from curve.rendering import write_manifest_preview
from curve.runs import render_markdown_report


VECTORIZE_CONFIG_KEYS = {
    "min_area",
    "color_tolerance",
    "max_size",
    "max_colors",
    "max_component_area",
    "timeout_seconds",
    "classifier_model",
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
    return report


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
            "anchor_count": manifest["anchor_count"],
            "diagnostic_count": len(manifest["diagnostics"]),
            "expectations": expectation_results,
        }
    )
    if output_dir is not None:
        case_dir = output_dir / case["id"]
        case_dir.mkdir(parents=True, exist_ok=True)
        (case_dir / "output.svg").write_text(scene.to_svg(), encoding="utf-8")
        (case_dir / "debug.svg").write_text(scene.to_debug_svg(), encoding="utf-8")
        (case_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        (case_dir / "config.json").write_text(
            json.dumps(config, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        (case_dir / "report.md").write_text(
            render_markdown_report(manifest=manifest, config=config),
            encoding="utf-8",
        )
        write_manifest_preview(manifest=manifest, output=case_dir / "preview.png")
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
