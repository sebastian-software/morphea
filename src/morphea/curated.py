"""Curated real-image regression suite helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from morphea.images import scene_from_flat_color_image
from morphea.runs import VectorizeRun, write_vectorize_run
from morphea.svg_raster import rasterized_svg_image


VECTORIZE_CONFIG_KEYS = {
    "background",
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
    "stroke_circle_min_diameter",
    "stroke_circle_max_aspect_error",
    "stroke_circle_min_inner_ratio",
    "stroke_circle_max_area_error",
    "circle_min_diameter",
    "circle_max_aspect_error",
    "circle_max_area_error",
    "stroke_min_length",
    "stroke_min_length_width_ratio",
    "quad_min_fill_ratio",
    "quad_max_fill_error",
    "rect_max_fill_error",
    "rounded_rect_max_fill_error",
}

PROMOTION_QUALITY_LABELS = {"green", "yellow", "red"}
PROMOTION_REQUIRED_STRINGS = {
    "stress_family",
    "source_provenance",
    "licensing_status",
    "current_status",
    "visual_audit_status",
}
PROMOTION_STRING_LISTS = {
    "expected_promotion_families",
    "current_issues",
}
PROMOTION_GATE_TYPES = {
    "shape_class",
    "topology",
    "grouping",
    "fragmentation",
    "visual_fidelity",
    "provenance",
    "review_safety",
}
PROMOTION_GATE_SEVERITIES = {"red", "yellow"}
PROMOTION_REGION_TOPOLOGY_LIMITS = {
    "min_closed_anchors",
    "max_closed_anchors",
    "min_open_anchors",
    "max_open_anchors",
    "max_hole_count",
    "max_cutout_count",
    "max_disconnected_components",
}
PROMOTION_VISUAL_THRESHOLD_KEYS = {
    "max_raster_l1_error",
    "max_raster_edge_error",
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
        expectation_ids = {
            expectation["id"]
            for expectation in expectations
            if isinstance(expectation, dict) and isinstance(expectation.get("id"), str)
        }
        if "promotion" in case:
            _validate_promotion_metadata(case_id, case["promotion"], expectation_ids)
    return suite


def check_curated_suite(
    suite_path: str | Path,
    *,
    output: str | Path | None = None,
    output_dir: str | Path | None = None,
    run: bool = False,
    snapshot: str | Path | None = None,
    markdown: str | Path | None = None,
    config_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate a curated suite and optionally run bounded vectorization."""

    suite_file = Path(suite_path)
    suite = load_curated_suite(suite_file)
    suite_output_dir = Path(output_dir) if output_dir is not None else None
    overrides = _vectorize_config(config_overrides or {})
    cases = [
        _check_curated_case(
            case,
            output_dir=suite_output_dir,
            run=run,
            config_overrides=overrides,
        )
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
    if overrides:
        report["config_overrides"] = _json_config(overrides)
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
    if markdown is not None:
        markdown_path = Path(markdown)
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(
            render_curated_markdown(report),
            encoding="utf-8",
        )
    return report


def render_curated_markdown(report: dict[str, Any]) -> str:
    """Render a scan-friendly curated real-image suite report."""

    cases = report.get("cases", [])
    if not isinstance(cases, list):
        cases = []
    lines = [
        "# Morphēa Curated Check",
        "",
        f"- Suite: `{report.get('suite', 'n/a')}`",
        f"- Run: `{str(report.get('run', False)).lower()}`",
        f"- Cases: {_fmt_markdown_value(report.get('case_count'))}",
        f"- OK: `{str(report.get('ok', False)).lower()}`",
        "",
        "## Promotion Gates",
        "",
        "| Case | Decision | Quality | Failed gates |",
        "| --- | --- | --- | --- |",
    ]
    for case in _promotion_sorted_cases(cases):
        if not isinstance(case, dict):
            continue
        summary = case.get("promotion_summary", {})
        if not isinstance(summary, dict):
            summary = {}
        lines.append(
            "| "
            f"`{case.get('id', 'n/a')}` | "
            f"`{summary.get('decision', 'n/a')}` | "
            f"{_fmt_promotion_quality(case.get('promotion'))} | "
            f"{_fmt_failed_gates(case.get('promotion_gates'))} |"
        )
    lines.extend(
        [
            "",
            "| Case | Status | Quality | OK | Anchors | Diagnostics | Failed expectations |",
            "| --- | --- | --- | ---: | ---: | ---: | --- |",
        ]
    )
    for case in cases:
        if not isinstance(case, dict):
            continue
        failed = [
            str(expectation.get("id", "n/a"))
            for expectation in case.get("expectations", [])
            if isinstance(expectation, dict) and not expectation.get("ok", False)
        ]
        lines.append(
            "| "
            f"`{case.get('id', 'n/a')}` | "
            f"`{case.get('status', 'n/a')}` | "
            f"{_fmt_promotion_quality(case.get('promotion'))} | "
            f"`{str(case.get('ok', False)).lower()}` | "
            f"{_fmt_markdown_value(case.get('anchor_count'))} | "
            f"{_fmt_markdown_value(case.get('diagnostic_count'))} | "
            f"{', '.join(f'`{item}`' for item in failed) if failed else 'n/a'} |"
        )

    for case in cases:
        if not isinstance(case, dict):
            continue
        lines.extend(["", f"## {case.get('id', 'n/a')}", ""])
        if isinstance(case.get("promotion"), dict):
            promotion = case["promotion"]
            lines.append(
                "- Promotion: "
                f"quality={_fmt_promotion_quality(promotion)}, "
                f"stress=`{promotion.get('stress_family', 'n/a')}`, "
                f"issues={_fmt_markdown_list(promotion.get('current_issues'))}"
            )
        if isinstance(case.get("promotion_summary"), dict):
            lines.append(
                "- Promotion gates: "
                f"decision=`{case['promotion_summary'].get('decision', 'n/a')}`, "
                f"failed={_fmt_failed_gates(case.get('promotion_gates'))}"
            )
        if "anchor_kind_counts" in case:
            lines.append(
                f"- Anchor kinds: {_fmt_markdown_counts(case.get('anchor_kind_counts'))}"
            )
        if "group_kind_counts" in case:
            lines.append(
                f"- Group kinds: {_fmt_markdown_counts(case.get('group_kind_counts'))}"
            )
        if "metrics" in case:
            metrics = case.get("metrics")
            if isinstance(metrics, dict):
                metric_parts = [
                    f"`{key}`={_fmt_markdown_value(metrics[key])}"
                    for key in (
                        "editability_score",
                        "simple_shape_ratio",
                        "fragmentation_penalty",
                        "raster_l1_error",
                        "raster_edge_error",
                    )
                    if key in metrics
                ]
                if metric_parts:
                    lines.append(f"- Key metrics: {', '.join(metric_parts)}")
        artifacts = case.get("artifacts", {})
        if isinstance(artifacts, dict) and artifacts:
            lines.append(
                f"- Artifacts: `{artifacts.get('run_dir', 'n/a')}`"
            )
        expectations = [
            item
            for item in case.get("expectations", [])
            if isinstance(item, dict)
        ]
        if not expectations:
            lines.append("- Expectations: n/a")
            continue
        lines.extend(
            [
                "",
                "| Expectation | Type | Actual | Required | OK |",
                "| --- | --- | ---: | ---: | ---: |",
            ]
        )
        for expectation in expectations:
            lines.append(_expectation_markdown_row(expectation))
    return "\n".join(lines).rstrip() + "\n"


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
    config_overrides: dict[str, Any] | None = None,
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
    if isinstance(case.get("promotion"), dict):
        result["promotion"] = dict(sorted(case["promotion"].items()))
    if not source_exists:
        result["status"] = "missing_source"
        result["ok"] = not run
        if isinstance(result.get("promotion"), dict):
            result["promotion_gates"] = _promotion_gate_results(result)
            result["promotion_summary"] = _promotion_summary(
                result["promotion_gates"]
            )
        return result
    if not run:
        if isinstance(result.get("promotion"), dict):
            result["promotion_gates"] = _promotion_gate_results(result)
            result["promotion_summary"] = _promotion_summary(
                result["promotion_gates"]
            )
        return result

    config = {
        **_vectorize_config(case.get("recommended_config", {})),
        **_vectorize_config(config_overrides or {}),
    }
    scene = scene_from_flat_color_image(source, **config)
    manifest = scene.to_manifest()
    expectation_results = _check_expectations(case.get("expectations", []), manifest)
    result.update(
        {
            "status": "checked",
            "ok": all(item["ok"] for item in expectation_results),
            "config": _json_config(config),
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
                **_json_config(config),
            },
        )
        result["artifacts"] = {
            "run_dir": str(vectorize_run.run_dir),
            "manifest": str(vectorize_run.manifest_path),
            "preview": str(vectorize_run.preview_path),
            "report": str(vectorize_run.report_path),
            "debug_svg": str(vectorize_run.debug_svg_path),
            "input": str(vectorize_run.input_path),
            **_visual_audit_artifact_paths(vectorize_run.run_dir),
        }
        run_manifest = json.loads(
            vectorize_run.manifest_path.read_text(encoding="utf-8")
        )
        if isinstance(run_manifest, dict):
            manifest = run_manifest
            metrics = manifest.get("metrics", {})
            if isinstance(metrics, dict):
                result["metrics"] = dict(sorted(metrics.items()))
    if isinstance(result.get("promotion"), dict):
        result["promotion_gates"] = _promotion_gate_results(result, manifest=manifest)
        result["promotion_summary"] = _promotion_summary(result["promotion_gates"])
    if output_dir is not None:
        _write_visual_audit_artifacts(
            vectorize_run.run_dir,
            vectorize_run,
            manifest=manifest,
            promotion=result.get("promotion"),
            promotion_gates=result.get("promotion_gates"),
            promotion_summary=result.get("promotion_summary"),
        )
    return result


def _check_expectations(
    expectations: list[dict[str, Any]],
    manifest: dict[str, Any],
) -> list[dict[str, Any]]:
    cumulative_min_counts: dict[tuple[str, str], int] = {}
    results: list[dict[str, Any]] = []
    for expectation in expectations:
        result = _check_expectation(expectation, manifest)
        if "metric" not in expectation:
            selector = _shape_expectation_selector(expectation)
            minimum = int(expectation.get("min_count", 1))
            cumulative_minimum = cumulative_min_counts.get(selector, 0) + minimum
            cumulative_min_counts[selector] = cumulative_minimum
            result["cumulative_min_count"] = cumulative_minimum
            result["ok"] = bool(result["ok"]) and int(
                result.get("actual_count", 0)
            ) >= cumulative_minimum
        results.append(result)
    return results


def _check_expectation(
    expectation: dict[str, Any],
    manifest: dict[str, Any],
) -> dict[str, Any]:
    if "metric" in expectation:
        metric = expectation["metric"]
        metrics = manifest.get("metrics", {})
        actual = metrics.get(metric) if isinstance(metrics, dict) else None
        ok = isinstance(actual, (int, float))
        result: dict[str, Any] = {
            "id": expectation["id"],
            "metric": metric,
            "actual_value": actual if ok else None,
        }
        if "min_value" in expectation:
            minimum = float(expectation["min_value"])
            result["min_value"] = minimum
            ok = ok and actual >= minimum
        if "max_value" in expectation:
            maximum = float(expectation["max_value"])
            result["max_value"] = maximum
            ok = ok and actual <= maximum
        result["ok"] = ok
        return result

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
    maximum = expectation.get("max_count")
    ok = actual >= minimum
    result = {
        "id": expectation["id"],
        **label,
        "min_count": minimum,
        "actual_count": actual,
        "ok": ok,
    }
    if maximum is not None:
        result["max_count"] = int(maximum)
        result["ok"] = ok and actual <= int(maximum)
    return result


def _shape_expectation_selector(expectation: dict[str, Any]) -> tuple[str, str]:
    kind = expectation.get("kind")
    if kind is not None:
        return ("kind", str(kind))
    return ("group_kind", str(expectation.get("group_kind")))


def _vectorize_config(config: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in config.items() if key in VECTORIZE_CONFIG_KEYS}


def _json_config(config: dict[str, Any]) -> dict[str, Any]:
    return {
        key: str(value) if isinstance(value, Path) else value
        for key, value in config.items()
    }


def _case_snapshot(case: dict[str, Any]) -> dict[str, Any]:
    snapshot: dict[str, Any] = {
        "id": case.get("id"),
        "status": case.get("status"),
        "ok": case.get("ok", False),
        "source_exists": case.get("source_exists", False),
        "expectations": [
            _expectation_snapshot(expectation)
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
        "promotion",
        "promotion_gates",
        "promotion_summary",
    ):
        if key in case:
            snapshot[key] = case[key]
    return snapshot


def _expectation_snapshot(expectation: dict[str, Any]) -> dict[str, Any]:
    if "metric" in expectation:
        snapshot: dict[str, Any] = {
            "id": expectation.get("id"),
            "ok": expectation.get("ok", False),
            "metric": expectation.get("metric"),
            "actual_value": expectation.get("actual_value"),
        }
        for key in ("min_value", "max_value"):
            if key in expectation:
                snapshot[key] = expectation[key]
        return snapshot

    snapshot = {
        "id": expectation.get("id"),
        "ok": expectation.get("ok", False),
        "actual_count": expectation.get("actual_count", 0),
        "min_count": expectation.get("min_count", 1),
    }
    for key in ("cumulative_min_count", "max_count"):
        if key in expectation:
            snapshot[key] = expectation[key]
    return snapshot


def _counts(values: object) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        key = str(value)
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def _promotion_gate_results(
    case: dict[str, Any],
    *,
    manifest: dict[str, Any] | None = None,
) -> list[dict[str, object]]:
    failed_expectations = [
        str(expectation.get("id", "n/a"))
        for expectation in case.get("expectations", [])
        if isinstance(expectation, dict) and not expectation.get("ok", False)
    ]
    artifacts = case.get("artifacts", {})
    has_contact_sheet = (
        isinstance(artifacts, dict)
        and isinstance(artifacts.get("contact_sheet"), str)
        and bool(artifacts["contact_sheet"])
    )
    promotion = case.get("promotion", {})
    label = (
        promotion.get("current_quality_label")
        if isinstance(promotion, dict)
        else None
    )
    source_exists = bool(case.get("source_exists", False))
    checked = case.get("status") == "checked"
    if failed_expectations:
        semantic_reason = "failed expectations: " + ", ".join(failed_expectations)
    elif checked:
        semantic_reason = "semantic expectations passed"
    else:
        semantic_reason = f"case status is {case.get('status', 'unknown')}"
    gates = [
        _promotion_gate(
            "source_available",
            gate_type="provenance",
            ok=source_exists,
            severity="red",
            reason=(
                "source image is available"
                if source_exists
                else "source image is missing"
            ),
            evidence=str(case.get("source", "")),
        ),
        _promotion_gate(
            "semantic_expectations",
            gate_type="shape_class",
            ok=not failed_expectations and checked,
            severity="red",
            reason=semantic_reason,
            evidence=failed_expectations,
        ),
        _promotion_gate(
            "visual_contact_sheet",
            gate_type="visual_fidelity",
            ok=case.get("status") != "checked" or has_contact_sheet,
            severity="yellow",
            reason=(
                "contact sheet available"
                if has_contact_sheet
                else "checked case has no contact sheet artifact"
            ),
            evidence=(
                artifacts.get("contact_sheet") if isinstance(artifacts, dict) else None
            ),
        ),
        _promotion_gate(
            "current_quality_label",
            gate_type="review_safety",
            ok=label == "green",
            severity="red" if label == "red" else "yellow",
            reason=f"current quality label is {label or 'missing'}",
            evidence=label,
        ),
    ]
    if isinstance(promotion, dict):
        gates.extend(_configured_promotion_gates(case, promotion))
        gates.extend(_region_promotion_gates(case, promotion, manifest=manifest))
        gates.extend(_group_promotion_gates(case, promotion, manifest=manifest))
        visual_gate = _visual_threshold_promotion_gate(case, promotion)
        if visual_gate is not None:
            gates.append(visual_gate)
    return gates


def _configured_promotion_gates(
    case: dict[str, Any],
    promotion: dict[str, Any],
) -> list[dict[str, object]]:
    configured = promotion.get("hard_gates", [])
    if not isinstance(configured, list) or not configured:
        return []
    expectations = {
        str(expectation.get("id")): expectation
        for expectation in case.get("expectations", [])
        if isinstance(expectation, dict) and isinstance(expectation.get("id"), str)
    }
    gates: list[dict[str, object]] = []
    checked = case.get("status") == "checked"
    for gate in configured:
        if not isinstance(gate, dict):
            continue
        expectation_ids = [
            str(item)
            for item in gate.get("expectation_ids", [])
            if isinstance(item, str)
        ]
        missing = [
            expectation_id
            for expectation_id in expectation_ids
            if expectation_id not in expectations
        ]
        failed = [
            expectation_id
            for expectation_id in expectation_ids
            if expectation_id in expectations
            and not bool(expectations[expectation_id].get("ok", False))
        ]
        ok = checked and not missing and not failed
        if not checked:
            reason = f"case status is {case.get('status', 'unknown')}"
        elif missing:
            reason = "missing expectation results: " + ", ".join(missing)
        elif failed:
            reason = "failed expectations: " + ", ".join(failed)
        else:
            reason = "referenced expectations passed"
        gates.append(
            _promotion_gate(
                str(gate.get("id", "configured_gate")),
                gate_type=str(gate.get("gate_type", "configured")),
                ok=ok,
                severity=str(gate.get("severity", "red")),
                reason=reason,
                evidence={
                    "expectation_ids": expectation_ids,
                    "description": gate.get("description"),
                },
            )
        )
    return gates


def _region_promotion_gates(
    case: dict[str, Any],
    promotion: dict[str, Any],
    *,
    manifest: dict[str, Any] | None = None,
) -> list[dict[str, object]]:
    configured = promotion.get("region_gates", [])
    if not isinstance(configured, list) or not configured:
        return []
    manifest_anchors = manifest.get("anchors", []) if isinstance(manifest, dict) else []
    anchors = [anchor for anchor in manifest_anchors if isinstance(anchor, dict)]
    checked = case.get("status") == "checked"
    gates: list[dict[str, object]] = []
    for gate in configured:
        if not isinstance(gate, dict):
            continue
        bounds = _parse_float_bounds(gate.get("bounds"))
        expected_kinds = [
            str(item)
            for item in gate.get("expected_kinds", [])
            if isinstance(item, str)
        ]
        forbidden_kinds = [
            str(item)
            for item in gate.get("forbidden_kinds", [])
            if isinstance(item, str)
        ]
        min_iou = float(gate.get("min_iou", 0.1))
        min_count = int(gate.get("min_count", 1))
        max_count = gate.get("max_count")
        if bounds is None:
            selected: list[dict[str, object]] = []
        else:
            selected = _anchors_overlapping_region(anchors, bounds, min_iou)
        matching = [
            anchor
            for anchor in selected
            if not expected_kinds or str(anchor.get("kind")) in expected_kinds
        ]
        forbidden = [
            anchor
            for anchor in selected
            if str(anchor.get("kind")) in forbidden_kinds
        ]
        topology_summary = _region_topology_summary(selected)
        topology_failures = _region_topology_failures(gate, topology_summary)
        count_ok = len(matching) >= min_count
        if isinstance(max_count, int):
            count_ok = count_ok and len(matching) <= max_count
        ok = (
            checked
            and bounds is not None
            and count_ok
            and not forbidden
            and not topology_failures
        )
        reason = _region_gate_reason(
            checked=checked,
            status=str(case.get("status", "unknown")),
            bounds=bounds,
            matching_count=len(matching),
            min_count=min_count,
            max_count=max_count if isinstance(max_count, int) else None,
            forbidden_count=len(forbidden),
            topology_failures=topology_failures,
        )
        gates.append(
            _promotion_gate(
                str(gate.get("id", "region_gate")),
                gate_type=str(gate.get("gate_type", "shape_class")),
                ok=ok,
                severity=str(gate.get("severity", "red")),
                reason=reason,
                evidence={
                    "bounds": list(bounds) if bounds is not None else None,
                    "min_iou": min_iou,
                    "expected_kinds": expected_kinds,
                    "forbidden_kinds": forbidden_kinds,
                    "matching_count": len(matching),
                    "selected_count": len(selected),
                    "forbidden_count": len(forbidden),
                    "topology_summary": topology_summary,
                    "topology_failures": topology_failures,
                    "selected_anchors": _region_gate_anchor_evidence(selected),
                    "description": gate.get("description"),
                },
            )
        )
    return gates


def _visual_threshold_promotion_gate(
    case: dict[str, Any],
    promotion: dict[str, Any],
) -> dict[str, object] | None:
    thresholds = promotion.get("visual_thresholds")
    if not isinstance(thresholds, dict):
        return None
    checked = case.get("status") == "checked"
    metrics = case.get("metrics", {})
    metrics = metrics if isinstance(metrics, dict) else {}
    failures: list[str] = []
    actuals: dict[str, float | None] = {}
    limits: dict[str, float] = {}
    for key in sorted(PROMOTION_VISUAL_THRESHOLD_KEYS):
        limit = thresholds.get(key)
        if not isinstance(limit, (int, float)):
            continue
        metric_name = key.removeprefix("max_")
        actual = metrics.get(metric_name)
        actuals[metric_name] = float(actual) if isinstance(actual, (int, float)) else None
        limits[key] = float(limit)
        if not isinstance(actual, (int, float)):
            failures.append(f"{metric_name} missing")
        elif float(actual) > float(limit):
            failures.append(f"{metric_name} {float(actual):.6g} > {float(limit):.6g}")
    ok = checked and not failures and bool(limits)
    if not checked:
        reason = f"case status is {case.get('status', 'unknown')}"
    elif not limits:
        reason = "no visual thresholds configured"
    elif failures:
        reason = "visual thresholds failed: " + ", ".join(failures)
    else:
        reason = "visual thresholds passed"
    return _promotion_gate(
        "visual_fidelity_thresholds",
        gate_type="visual_fidelity",
        ok=ok,
        severity=str(thresholds.get("severity", "red")),
        reason=reason,
        evidence={
            "family": thresholds.get("family", promotion.get("stress_family")),
            "actual": actuals,
            "thresholds": limits,
            "failures": failures,
            "description": thresholds.get("description"),
        },
    )


def _group_promotion_gates(
    case: dict[str, Any],
    promotion: dict[str, Any],
    *,
    manifest: dict[str, Any] | None = None,
) -> list[dict[str, object]]:
    configured = promotion.get("group_gates", [])
    if not isinstance(configured, list) or not configured:
        return []
    manifest_groups = manifest.get("groups", []) if isinstance(manifest, dict) else []
    groups = [group for group in manifest_groups if isinstance(group, dict)]
    checked = case.get("status") == "checked"
    gates: list[dict[str, object]] = []
    for gate in configured:
        if not isinstance(gate, dict):
            continue
        expected_kinds = [
            str(item)
            for item in gate.get("expected_group_kinds", [])
            if isinstance(item, str)
        ]
        selected = [
            group
            for group in groups
            if not expected_kinds or str(group.get("kind")) in expected_kinds
        ]
        min_count = int(gate.get("min_count", 1))
        max_count = gate.get("max_count")
        min_member_count = int(gate.get("min_member_count", 0))
        max_member_count = gate.get("max_member_count")
        member_counts = [_group_member_count(group) for group in selected]
        best_member_count = max(member_counts, default=0)
        worst_member_count = max(member_counts, default=0)
        failures = _group_gate_failures(
            selected_count=len(selected),
            min_count=min_count,
            max_count=max_count if isinstance(max_count, int) else None,
            best_member_count=best_member_count,
            worst_member_count=worst_member_count,
            min_member_count=min_member_count,
            max_member_count=(
                max_member_count if isinstance(max_member_count, int) else None
            ),
        )
        ok = checked and not failures
        if not checked:
            reason = f"case status is {case.get('status', 'unknown')}"
        elif failures:
            reason = "group constraints failed: " + ", ".join(failures)
        else:
            reason = "group constraints passed"
        gates.append(
            _promotion_gate(
                str(gate.get("id", "group_gate")),
                gate_type=str(gate.get("gate_type", "grouping")),
                ok=ok,
                severity=str(gate.get("severity", "red")),
                reason=reason,
                evidence={
                    "expected_group_kinds": expected_kinds,
                    "selected_count": len(selected),
                    "best_member_count": best_member_count,
                    "worst_member_count": worst_member_count,
                    "selected_groups": _group_gate_evidence(selected),
                    "description": gate.get("description"),
                },
            )
        )
    return gates


def _group_gate_failures(
    *,
    selected_count: int,
    min_count: int,
    max_count: int | None,
    best_member_count: int,
    worst_member_count: int,
    min_member_count: int,
    max_member_count: int | None,
) -> list[str]:
    failures: list[str] = []
    if selected_count < min_count:
        failures.append(f"group_count {selected_count} < {min_count}")
    if max_count is not None and selected_count > max_count:
        failures.append(f"group_count {selected_count} > {max_count}")
    if best_member_count < min_member_count:
        failures.append(f"best_member_count {best_member_count} < {min_member_count}")
    if max_member_count is not None and worst_member_count > max_member_count:
        failures.append(
            f"worst_member_count {worst_member_count} > {max_member_count}"
        )
    return failures


def _group_gate_evidence(groups: list[dict[str, object]]) -> list[dict[str, object]]:
    evidence: list[dict[str, object]] = []
    for group in groups[:12]:
        metrics = group.get("metrics", {})
        evidence.append(
            {
                "id": group.get("id"),
                "kind": group.get("kind"),
                "member_count": _group_member_count(group),
                "metrics": metrics if isinstance(metrics, dict) else {},
            }
        )
    return evidence


def _group_member_count(group: dict[str, object]) -> int:
    indexes = group.get("anchor_indexes", [])
    return len(indexes) if isinstance(indexes, list) else 0


def _anchors_overlapping_region(
    anchors: list[dict[str, object]],
    region_bounds: tuple[float, float, float, float],
    min_iou: float,
) -> list[dict[str, object]]:
    selected: list[dict[str, object]] = []
    for anchor in anchors:
        anchor_bounds = _manifest_anchor_bounds(anchor)
        if anchor_bounds is None:
            continue
        if _bounds_iou(anchor_bounds, region_bounds) >= min_iou:
            selected.append(anchor)
    return selected


def _region_gate_reason(
    *,
    checked: bool,
    status: str,
    bounds: tuple[float, float, float, float] | None,
    matching_count: int,
    min_count: int,
    max_count: int | None,
    forbidden_count: int,
    topology_failures: list[str],
) -> str:
    if not checked:
        return f"case status is {status}"
    if bounds is None:
        return "region bounds are invalid"
    if forbidden_count:
        return f"forbidden anchors in region: {forbidden_count}"
    if matching_count < min_count:
        return f"matching anchors in region: {matching_count} < {min_count}"
    if max_count is not None and matching_count > max_count:
        return f"matching anchors in region: {matching_count} > {max_count}"
    if topology_failures:
        return "topology constraints failed: " + ", ".join(topology_failures)
    return f"matching anchors in region: {matching_count}"


def _region_gate_anchor_evidence(
    anchors: list[dict[str, object]],
) -> list[dict[str, object]]:
    evidence: list[dict[str, object]] = []
    for anchor in anchors[:12]:
        bounds = _manifest_anchor_bounds(anchor)
        evidence.append(
            {
                "id": anchor.get("id"),
                "kind": anchor.get("kind"),
                "bounds": list(bounds) if bounds is not None else None,
                "closed": _anchor_closed(anchor),
                "hole_count": _anchor_hole_count(anchor),
                "cutout": _anchor_has_cutout(anchor),
            }
        )
    return evidence


def _region_topology_summary(
    anchors: list[dict[str, object]],
) -> dict[str, object]:
    kind_counts = _counts(anchor.get("kind") for anchor in anchors)
    closed_count = sum(1 for anchor in anchors if _anchor_closed(anchor))
    open_count = len(anchors) - closed_count
    hole_count = sum(_anchor_hole_count(anchor) for anchor in anchors)
    cutout_count = sum(1 for anchor in anchors if _anchor_has_cutout(anchor))
    return {
        "selected_anchor_count": len(anchors),
        "disconnected_component_count": len(anchors),
        "kind_counts": kind_counts,
        "closed_anchor_count": closed_count,
        "open_anchor_count": open_count,
        "hole_count": hole_count,
        "cutout_count": cutout_count,
    }


def _region_topology_failures(
    gate: dict[str, Any],
    summary: dict[str, object],
) -> list[str]:
    failures: list[str] = []
    checks = [
        ("min_closed_anchors", "closed_anchor_count", ">="),
        ("max_closed_anchors", "closed_anchor_count", "<="),
        ("min_open_anchors", "open_anchor_count", ">="),
        ("max_open_anchors", "open_anchor_count", "<="),
        ("max_hole_count", "hole_count", "<="),
        ("max_cutout_count", "cutout_count", "<="),
        (
            "max_disconnected_components",
            "disconnected_component_count",
            "<=",
        ),
    ]
    for gate_key, summary_key, operator in checks:
        if gate_key not in gate:
            continue
        expected = gate.get(gate_key)
        actual = summary.get(summary_key)
        if not isinstance(expected, int) or not isinstance(actual, int):
            continue
        if operator == ">=" and actual < expected:
            failures.append(f"{summary_key} {actual} < {expected}")
        if operator == "<=" and actual > expected:
            failures.append(f"{summary_key} {actual} > {expected}")
    return failures


def _anchor_closed(anchor: dict[str, object]) -> bool:
    if str(anchor.get("kind")) in {
        "circle",
        "ellipse",
        "rect",
        "rounded_rect",
        "quad",
        "stroke_circle",
    }:
        return True
    path = anchor.get("path")
    if isinstance(path, dict) and isinstance(path.get("closed"), bool):
        return bool(path["closed"])
    stroke = anchor.get("stroke")
    if isinstance(stroke, dict) and isinstance(stroke.get("closed"), bool):
        return bool(stroke["closed"])
    return False


def _anchor_hole_count(anchor: dict[str, object]) -> int:
    metrics = anchor.get("metrics")
    if not isinstance(metrics, dict):
        return 0
    value = metrics.get("path_hole_count", 0)
    if isinstance(value, (int, float)):
        return max(0, int(value))
    return 0


def _anchor_has_cutout(anchor: dict[str, object]) -> bool:
    stroke = anchor.get("stroke")
    if isinstance(stroke, dict) and bool(stroke.get("is_cutout", False)):
        return True
    export_policy = anchor.get("export_policy")
    if isinstance(export_policy, dict):
        strategy = export_policy.get("cutout_strategy")
        return isinstance(strategy, str) and bool(strategy)
    return False


def _manifest_anchor_bounds(
    anchor: dict[str, object],
) -> tuple[float, float, float, float] | None:
    source_mask = anchor.get("source_mask")
    if isinstance(source_mask, dict):
        bounds = _parse_float_bounds(source_mask.get("bounds"))
        if bounds is not None:
            return bounds
    reserved = anchor.get("reserved")
    if isinstance(reserved, dict):
        return _parse_float_bounds(reserved.get("bounds"))
    return None


def _parse_float_bounds(value: object) -> tuple[float, float, float, float] | None:
    if not isinstance(value, list) or len(value) != 4:
        return None
    if not all(isinstance(item, (int, float)) for item in value):
        return None
    left, top, right, bottom = (float(item) for item in value)
    if right <= left or bottom <= top:
        return None
    return (left, top, right, bottom)


def _bounds_iou(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> float:
    intersection = _bounds_intersection_area(first, second)
    union = _bounds_area(first) + _bounds_area(second) - intersection
    if union <= 0:
        return 0.0
    return intersection / union


def _bounds_intersection_area(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> float:
    left = max(first[0], second[0])
    top = max(first[1], second[1])
    right = min(first[2], second[2])
    bottom = min(first[3], second[3])
    if right <= left or bottom <= top:
        return 0.0
    return _bounds_area((left, top, right, bottom))


def _bounds_area(bounds: tuple[float, float, float, float]) -> float:
    return max(bounds[2] - bounds[0], 0.0) * max(bounds[3] - bounds[1], 0.0)


def _promotion_gate(
    gate_id: str,
    *,
    gate_type: str,
    ok: bool,
    severity: str,
    reason: str,
    evidence: object,
) -> dict[str, object]:
    return {
        "id": gate_id,
        "gate_type": gate_type,
        "ok": bool(ok),
        "severity": severity,
        "reason": reason,
        "evidence": evidence,
    }


def _promotion_summary(gates: list[dict[str, object]]) -> dict[str, object]:
    failed = [gate for gate in gates if not gate.get("ok", False)]
    has_red = any(gate.get("severity") == "red" for gate in failed)
    has_yellow = any(gate.get("severity") == "yellow" for gate in failed)
    if has_red:
        decision = "rejected"
    elif has_yellow:
        decision = "deferred"
    else:
        decision = "promoted"
    return {
        "decision": decision,
        "failed_gate_count": len(failed),
        "red_gate_count": sum(1 for gate in failed if gate.get("severity") == "red"),
        "yellow_gate_count": sum(
            1 for gate in failed if gate.get("severity") == "yellow"
        ),
    }


def _write_visual_audit_artifacts(
    run_dir: Path,
    run: VectorizeRun,
    *,
    manifest: object = None,
    promotion: object = None,
    promotion_gates: object = None,
    promotion_summary: object = None,
) -> dict[str, str]:
    svg_render_path = run_dir / "svg-render.png"
    diff_path = run_dir / "diff.png"
    anchor_overlay_path = run_dir / "anchor-overlay.png"
    contact_sheet_path = run_dir / "contact-sheet.png"

    svg_text = run.svg_path.read_text(encoding="utf-8")
    svg_render = rasterized_svg_image(svg_text, background="#ffffff").convert("RGBA")
    svg_render.save(svg_render_path)
    with Image.open(run.input_path) as source_image:
        source = source_image.convert("RGBA")
    with Image.open(run.preview_path) as preview_image:
        preview = preview_image.convert("RGBA")
    diff = _visual_diff_image(source, svg_render)
    diff.save(diff_path)
    anchor_overlay = _anchor_overlay_image(source, manifest)
    anchor_overlay.save(anchor_overlay_path)
    panels = [
        ("source", source),
        ("preview", preview),
        ("anchors", anchor_overlay),
        ("svg render", svg_render),
        ("diff", diff),
    ]
    if isinstance(promotion_summary, dict) or isinstance(promotion_gates, list):
        panels.extend(
            [
                (
                    "promotion",
                    _promotion_summary_panel(promotion, promotion_summary),
                ),
                (
                    "failed gates",
                    _failed_gates_panel(promotion_gates),
                ),
            ]
        )
    contact_sheet = _contact_sheet_image(
        panels
    )
    contact_sheet.save(contact_sheet_path)
    return _visual_audit_artifact_paths(run_dir)


def _visual_audit_artifact_paths(run_dir: Path) -> dict[str, str]:
    return {
        "svg_render": str(run_dir / "svg-render.png"),
        "diff": str(run_dir / "diff.png"),
        "anchor_overlay": str(run_dir / "anchor-overlay.png"),
        "contact_sheet": str(run_dir / "contact-sheet.png"),
    }


def _visual_diff_image(source: Image.Image, rendered: Image.Image) -> Image.Image:
    source_rgba = source.convert("RGBA")
    rendered_rgba = rendered.convert("RGBA")
    if rendered_rgba.size != source_rgba.size:
        rendered_rgba = rendered_rgba.resize(
            source_rgba.size,
            Image.Resampling.NEAREST,
        )
    source_luma = source_rgba.convert("L")
    rendered_luma = rendered_rgba.convert("L")
    diff = Image.new("RGB", source_rgba.size, "white")
    source_pixels = source_luma.load()
    rendered_pixels = rendered_luma.load()
    diff_pixels = diff.load()
    for y in range(source_rgba.height):
        for x in range(source_rgba.width):
            source_black = 255 - source_pixels[x, y]
            rendered_black = 255 - rendered_pixels[x, y]
            delta = source_black - rendered_black
            if abs(delta) < 8:
                value = 240
                diff_pixels[x, y] = (value, value, value)
            elif delta > 0:
                strength = min(255, int(abs(delta) * 1.6))
                diff_pixels[x, y] = (255, 255 - strength, 255 - strength)
            else:
                strength = min(255, int(abs(delta) * 1.6))
                diff_pixels[x, y] = (255 - strength, 255 - strength, 255)
    return diff


def _anchor_overlay_image(source: Image.Image, manifest: object) -> Image.Image:
    base = source.convert("RGB")
    softened = Image.blend(base, Image.new("RGB", base.size, "white"), 0.35)
    overlay = softened.convert("RGBA")
    draw = ImageDraw.Draw(overlay, "RGBA")
    if not isinstance(manifest, dict):
        return overlay.convert("RGB")
    anchors = manifest.get("anchors", [])
    if not isinstance(anchors, list):
        return overlay.convert("RGB")
    line_width = max(1, round(max(overlay.size) / 360))
    for index, anchor in enumerate(anchors[:240]):
        if not isinstance(anchor, dict):
            continue
        bounds = _anchor_overlay_bounds(anchor)
        if bounds is None:
            continue
        color = _anchor_overlay_color(str(anchor.get("kind", "")))
        draw.rectangle(bounds, outline=color, width=line_width)
        if index < 30:
            label = _anchor_overlay_label(anchor, index)
            text_x = max(0, min(bounds[0], overlay.width - 40))
            text_y = max(0, bounds[1] - 10)
            draw.text((text_x, text_y), label, fill=color)
    if len(anchors) > 240:
        draw.text((8, 8), f"showing 240/{len(anchors)} anchors", fill=(45, 45, 45, 220))
    return overlay.convert("RGB")


def _anchor_overlay_bounds(anchor: dict[str, object]) -> tuple[int, int, int, int] | None:
    source_mask = anchor.get("source_mask")
    if isinstance(source_mask, dict):
        bounds = source_mask.get("bounds")
        parsed = _parse_overlay_bounds(bounds)
        if parsed is not None:
            return parsed
    reserved = anchor.get("reserved")
    if isinstance(reserved, dict):
        return _parse_overlay_bounds(reserved.get("bounds"))
    return None


def _parse_overlay_bounds(value: object) -> tuple[int, int, int, int] | None:
    if not isinstance(value, list) or len(value) != 4:
        return None
    if not all(isinstance(item, (int, float)) for item in value):
        return None
    left, top, right, bottom = value
    return (
        int(round(left)),
        int(round(top)),
        int(round(right)),
        int(round(bottom)),
    )


def _anchor_overlay_color(kind: str) -> tuple[int, int, int, int]:
    if kind in {"circle", "stroke_circle"}:
        return (35, 130, 75, 255)
    if kind in {"rect", "rounded_rect", "quad"}:
        return (225, 120, 20, 255)
    if kind in {"stroke", "stroke_polyline", "stroke_path", "stroke_arc"}:
        return (30, 100, 200, 255)
    return (175, 45, 45, 255)


def _anchor_overlay_label(anchor: dict[str, object], index: int) -> str:
    anchor_id = str(anchor.get("id", f"anchor-{index:04d}"))
    suffix = anchor_id.rsplit("-", 1)[-1]
    kind = str(anchor.get("kind", "anchor"))
    return f"{suffix}:{kind}"


def _contact_sheet_image(panels: list[tuple[str, Image.Image]]) -> Image.Image:
    panel_size = 220
    label_height = 24
    gutter = 12
    width = gutter + len(panels) * (panel_size + gutter)
    height = label_height + panel_size + gutter * 2
    sheet = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(sheet)
    for index, (label, image) in enumerate(panels):
        x = gutter + index * (panel_size + gutter)
        draw.text((x, gutter), label, fill=(40, 40, 40))
        panel = image.convert("RGB")
        panel.thumbnail((panel_size, panel_size), Image.Resampling.LANCZOS)
        panel_canvas = Image.new("RGB", (panel_size, panel_size), "white")
        offset = (
            (panel_size - panel.width) // 2,
            (panel_size - panel.height) // 2,
        )
        panel_canvas.paste(panel, offset)
        y = gutter + label_height
        sheet.paste(panel_canvas, (x, y))
        draw.rectangle(
            (x, y, x + panel_size - 1, y + panel_size - 1),
            outline=(180, 180, 180),
        )
    return sheet


def _promotion_summary_panel(
    promotion: object,
    summary: object,
) -> Image.Image:
    panel = Image.new("RGB", (220, 220), "white")
    draw = ImageDraw.Draw(panel)
    summary = summary if isinstance(summary, dict) else {}
    promotion = promotion if isinstance(promotion, dict) else {}
    decision = str(summary.get("decision", "n/a"))
    quality = str(promotion.get("current_quality_label", "n/a"))
    red = _fmt_panel_value(summary.get("red_gate_count"))
    yellow = _fmt_panel_value(summary.get("yellow_gate_count"))
    failed = _fmt_panel_value(summary.get("failed_gate_count"))
    color = _promotion_panel_color(decision, quality)
    draw.rectangle((0, 0, 219, 219), fill=(250, 250, 250), outline=color, width=4)
    draw.text((12, 12), "decision", fill=(50, 50, 50))
    draw.text((12, 34), decision, fill=color)
    draw.text((12, 68), f"quality: {quality}", fill=(45, 45, 45))
    draw.text((12, 92), f"failed: {failed}", fill=(45, 45, 45))
    draw.text((12, 116), f"red: {red}", fill=(45, 45, 45))
    draw.text((12, 140), f"yellow: {yellow}", fill=(45, 45, 45))
    return panel


def _failed_gates_panel(gates: object) -> Image.Image:
    panel = Image.new("RGB", (220, 220), "white")
    draw = ImageDraw.Draw(panel)
    draw.rectangle((0, 0, 219, 219), fill=(250, 250, 250), outline=(180, 180, 180))
    if not isinstance(gates, list):
        draw.text((12, 12), "no gate data", fill=(50, 50, 50))
        return panel
    failed = [gate for gate in gates if isinstance(gate, dict) and not gate.get("ok")]
    if not failed:
        draw.text((12, 12), "all gates passed", fill=(35, 115, 70))
        return panel
    y = 12
    for gate in failed[:6]:
        severity = str(gate.get("severity", "red"))
        gate_id = str(gate.get("id", "n/a"))
        gate_type = str(gate.get("gate_type", "n/a"))
        color = (170, 45, 45) if severity == "red" else (155, 110, 20)
        for line in _wrap_panel_text(f"{severity}: {gate_id}", 26):
            draw.text((12, y), line, fill=color)
            y += 16
        draw.text((12, y), gate_type, fill=(80, 80, 80))
        y += 20
        if y > 188:
            break
    remaining = len(failed) - 6
    if remaining > 0:
        draw.text((12, 196), f"+{remaining} more", fill=(70, 70, 70))
    return panel


def _promotion_panel_color(decision: str, quality: str) -> tuple[int, int, int]:
    if decision == "promoted" and quality == "green":
        return (35, 130, 75)
    if decision == "rejected" or quality == "red":
        return (175, 45, 45)
    return (170, 120, 30)


def _fmt_panel_value(value: object) -> str:
    if isinstance(value, int):
        return str(value)
    return "n/a"


def _wrap_panel_text(text: str, width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = word if not current else f"{current} {word}"
        if len(candidate) <= width:
            current = candidate
            continue
        if current:
            lines.append(current)
        while len(word) > width:
            lines.append(word[:width])
            word = word[width:]
        current = word
    if current:
        lines.append(current)
    return lines or [""]


def _expectation_markdown_row(expectation: dict[str, Any]) -> str:
    if "metric" in expectation:
        required_parts = []
        if "min_value" in expectation:
            required_parts.append(f">= {_fmt_markdown_value(expectation['min_value'])}")
        if "max_value" in expectation:
            required_parts.append(f"<= {_fmt_markdown_value(expectation['max_value'])}")
        return (
            "| "
            f"`{expectation.get('id', 'n/a')}` | "
            f"`metric:{expectation.get('metric', 'n/a')}` | "
            f"{_fmt_markdown_value(expectation.get('actual_value'))} | "
            f"{', '.join(required_parts) if required_parts else 'n/a'} | "
            f"`{str(expectation.get('ok', False)).lower()}` |"
        )
    expectation_type = expectation.get("kind")
    label = "kind"
    if expectation_type is None:
        expectation_type = expectation.get("group_kind")
        label = "group"
    required_parts = [
        f">= {_fmt_markdown_value(expectation.get('cumulative_min_count', expectation.get('min_count')))}"
    ]
    if "max_count" in expectation:
        required_parts.append(f"<= {_fmt_markdown_value(expectation.get('max_count'))}")
    return (
        "| "
        f"`{expectation.get('id', 'n/a')}` | "
        f"`{label}:{expectation_type}` | "
        f"{_fmt_markdown_value(expectation.get('actual_count'))} | "
        f"{', '.join(required_parts)} | "
        f"`{str(expectation.get('ok', False)).lower()}` |"
    )


def _fmt_markdown_counts(value: object) -> str:
    if not isinstance(value, dict) or not value:
        return "n/a"
    return ", ".join(
        f"`{key}`={_fmt_markdown_value(value[key])}"
        for key in sorted(value)
    )


def _promotion_sorted_cases(cases: object) -> list[dict[str, Any]]:
    if not isinstance(cases, list):
        return []
    sortable = [case for case in cases if isinstance(case, dict)]
    return sorted(sortable, key=_promotion_case_sort_key)


def _promotion_case_sort_key(case: dict[str, Any]) -> tuple[int, str]:
    summary = case.get("promotion_summary", {})
    if not isinstance(summary, dict):
        return (3, str(case.get("id", "")))
    if int(summary.get("red_gate_count", 0)) > 0:
        return (0, str(case.get("id", "")))
    if int(summary.get("yellow_gate_count", 0)) > 0:
        return (1, str(case.get("id", "")))
    return (2, str(case.get("id", "")))


def _fmt_promotion_quality(value: object) -> str:
    if not isinstance(value, dict):
        return "n/a"
    label = value.get("current_quality_label")
    if not isinstance(label, str):
        return "n/a"
    return f"`{label}`"


def _fmt_markdown_list(value: object) -> str:
    if not isinstance(value, list) or not value:
        return "n/a"
    return ", ".join(f"`{item}`" for item in value)


def _fmt_failed_gates(value: object) -> str:
    if not isinstance(value, list):
        return "n/a"
    failed = [
        str(gate.get("id", "n/a"))
        for gate in value
        if isinstance(gate, dict) and not gate.get("ok", False)
    ]
    if not failed:
        return "n/a"
    return ", ".join(f"`{item}`" for item in failed)


def _fmt_markdown_value(value: object) -> str:
    if isinstance(value, bool) or value is None:
        return "n/a"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


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
    has_metric = isinstance(expectation.get("metric"), str)
    if sum((has_kind, has_group_kind, has_metric)) != 1:
        raise ValueError(
            f"case {case_id} expectation {expectation_id} must set kind, "
            "group_kind, or metric"
        )
    if has_metric:
        has_min = "min_value" in expectation
        has_max = "max_value" in expectation
        if not has_min and not has_max:
            raise ValueError(
                f"case {case_id} expectation {expectation_id} metric expectation "
                "must set min_value or max_value"
            )
        for key in ("min_value", "max_value"):
            value = expectation.get(key)
            if key in expectation and not isinstance(value, (int, float)):
                raise ValueError(
                    f"case {case_id} expectation {expectation_id} {key} "
                    "must be numeric"
                )
        return

    min_count = expectation.get("min_count", 1)
    if not isinstance(min_count, int) or min_count < 1:
        raise ValueError(
            f"case {case_id} expectation {expectation_id} min_count must be positive"
        )
    max_count = expectation.get("max_count")
    if max_count is not None and (
        not isinstance(max_count, int) or max_count < min_count
    ):
        raise ValueError(
            f"case {case_id} expectation {expectation_id} max_count "
            "must be >= min_count"
        )


def _validate_promotion_metadata(
    case_id: str,
    value: Any,
    expectation_ids: set[str],
) -> None:
    if not isinstance(value, dict):
        raise ValueError(f"case {case_id} promotion must be an object")
    label = value.get("current_quality_label")
    if label not in PROMOTION_QUALITY_LABELS:
        allowed = ", ".join(sorted(PROMOTION_QUALITY_LABELS))
        raise ValueError(
            f"case {case_id} promotion current_quality_label must be one of: "
            f"{allowed}"
        )
    for key in sorted(PROMOTION_REQUIRED_STRINGS):
        if not isinstance(value.get(key), str) or not value[key]:
            raise ValueError(f"case {case_id} promotion {key} must be a string")
    for key in sorted(PROMOTION_STRING_LISTS):
        items = value.get(key)
        if not isinstance(items, list) or not all(
            isinstance(item, str) and item for item in items
        ):
            raise ValueError(
                f"case {case_id} promotion {key} must be a string array"
            )
    if not value["expected_promotion_families"]:
        raise ValueError(
            f"case {case_id} promotion expected_promotion_families must not be empty"
        )
    notes = value.get("review_notes", [])
    if notes is not None and (
        not isinstance(notes, list)
        or not all(isinstance(item, str) and item for item in notes)
    ):
        raise ValueError(
            f"case {case_id} promotion review_notes must be a string array"
        )
    hard_gates = value.get("hard_gates", [])
    if hard_gates is not None:
        _validate_promotion_hard_gates(case_id, hard_gates, expectation_ids)
    region_gates = value.get("region_gates", [])
    if region_gates is not None:
        _validate_promotion_region_gates(case_id, region_gates)
    group_gates = value.get("group_gates", [])
    if group_gates is not None:
        _validate_promotion_group_gates(case_id, group_gates)
    visual_thresholds = value.get("visual_thresholds")
    if visual_thresholds is not None:
        _validate_promotion_visual_thresholds(case_id, visual_thresholds)


def _validate_promotion_hard_gates(
    case_id: str,
    gates: Any,
    expectation_ids: set[str],
) -> None:
    if not isinstance(gates, list):
        raise ValueError(f"case {case_id} promotion hard_gates must be an array")
    seen_ids: set[str] = set()
    for index, gate in enumerate(gates):
        if not isinstance(gate, dict):
            raise ValueError(
                f"case {case_id} promotion hard_gates[{index}] must be an object"
            )
        gate_id = gate.get("id")
        if not isinstance(gate_id, str) or not gate_id:
            raise ValueError(
                f"case {case_id} promotion hard_gates[{index}] id must be a string"
            )
        if gate_id in seen_ids:
            raise ValueError(
                f"case {case_id} promotion duplicate hard gate id: {gate_id}"
            )
        seen_ids.add(gate_id)
        gate_type = gate.get("gate_type")
        if gate_type not in PROMOTION_GATE_TYPES:
            allowed = ", ".join(sorted(PROMOTION_GATE_TYPES))
            raise ValueError(
                f"case {case_id} promotion hard gate {gate_id} gate_type "
                f"must be one of: {allowed}"
            )
        severity = gate.get("severity", "red")
        if severity not in PROMOTION_GATE_SEVERITIES:
            allowed = ", ".join(sorted(PROMOTION_GATE_SEVERITIES))
            raise ValueError(
                f"case {case_id} promotion hard gate {gate_id} severity "
                f"must be one of: {allowed}"
            )
        references = gate.get("expectation_ids")
        if not isinstance(references, list) or not references:
            raise ValueError(
                f"case {case_id} promotion hard gate {gate_id} "
                "expectation_ids must be a non-empty string array"
            )
        for reference in references:
            if not isinstance(reference, str) or not reference:
                raise ValueError(
                    f"case {case_id} promotion hard gate {gate_id} "
                    "expectation_ids must be a non-empty string array"
                )
            if reference not in expectation_ids:
                raise ValueError(
                    f"case {case_id} promotion hard gate {gate_id} references "
                    f"unknown expectation id: {reference}"
                )
        description = gate.get("description")
        if description is not None and (
            not isinstance(description, str) or not description
        ):
            raise ValueError(
                f"case {case_id} promotion hard gate {gate_id} "
                "description must be a string"
            )


def _validate_promotion_region_gates(case_id: str, gates: Any) -> None:
    if not isinstance(gates, list):
        raise ValueError(f"case {case_id} promotion region_gates must be an array")
    seen_ids: set[str] = set()
    for index, gate in enumerate(gates):
        if not isinstance(gate, dict):
            raise ValueError(
                f"case {case_id} promotion region_gates[{index}] must be an object"
            )
        gate_id = gate.get("id")
        if not isinstance(gate_id, str) or not gate_id:
            raise ValueError(
                f"case {case_id} promotion region_gates[{index}] id must be a string"
            )
        if gate_id in seen_ids:
            raise ValueError(
                f"case {case_id} promotion duplicate region gate id: {gate_id}"
            )
        seen_ids.add(gate_id)
        gate_type = gate.get("gate_type")
        if gate_type not in PROMOTION_GATE_TYPES:
            allowed = ", ".join(sorted(PROMOTION_GATE_TYPES))
            raise ValueError(
                f"case {case_id} promotion region gate {gate_id} gate_type "
                f"must be one of: {allowed}"
            )
        severity = gate.get("severity", "red")
        if severity not in PROMOTION_GATE_SEVERITIES:
            allowed = ", ".join(sorted(PROMOTION_GATE_SEVERITIES))
            raise ValueError(
                f"case {case_id} promotion region gate {gate_id} severity "
                f"must be one of: {allowed}"
            )
        if _parse_float_bounds(gate.get("bounds")) is None:
            raise ValueError(
                f"case {case_id} promotion region gate {gate_id} bounds "
                "must be [left, top, right, bottom]"
            )
        min_iou = gate.get("min_iou", 0.1)
        if not isinstance(min_iou, (int, float)) or min_iou < 0 or min_iou > 1:
            raise ValueError(
                f"case {case_id} promotion region gate {gate_id} min_iou "
                "must be between 0 and 1"
            )
        _validate_region_kind_list(case_id, gate_id, gate, "expected_kinds")
        _validate_region_kind_list(case_id, gate_id, gate, "forbidden_kinds")
        if not gate.get("expected_kinds") and not gate.get("forbidden_kinds"):
            raise ValueError(
                f"case {case_id} promotion region gate {gate_id} must set "
                "expected_kinds or forbidden_kinds"
            )
        min_count = gate.get("min_count", 1)
        if not isinstance(min_count, int) or min_count < 0:
            raise ValueError(
                f"case {case_id} promotion region gate {gate_id} min_count "
                "must be non-negative"
            )
        max_count = gate.get("max_count")
        if max_count is not None and (
            not isinstance(max_count, int) or max_count < min_count
        ):
            raise ValueError(
                f"case {case_id} promotion region gate {gate_id} max_count "
                "must be >= min_count"
            )
        _validate_region_topology_limits(case_id, gate_id, gate)
        description = gate.get("description")
        if description is not None and (
            not isinstance(description, str) or not description
        ):
            raise ValueError(
                f"case {case_id} promotion region gate {gate_id} "
                "description must be a string"
            )


def _validate_region_kind_list(
    case_id: str,
    gate_id: str,
    gate: dict[str, Any],
    key: str,
) -> None:
    values = gate.get(key, [])
    if values is None:
        return
    if not isinstance(values, list) or not all(
        isinstance(item, str) and item for item in values
    ):
        raise ValueError(
            f"case {case_id} promotion region gate {gate_id} {key} "
            "must be a string array"
        )


def _validate_region_topology_limits(
    case_id: str,
    gate_id: str,
    gate: dict[str, Any],
) -> None:
    for key in sorted(PROMOTION_REGION_TOPOLOGY_LIMITS):
        value = gate.get(key)
        if value is None:
            continue
        if not isinstance(value, int) or value < 0:
            raise ValueError(
                f"case {case_id} promotion region gate {gate_id} {key} "
                "must be a non-negative integer"
            )
    for minimum_key, maximum_key in (
        ("min_closed_anchors", "max_closed_anchors"),
        ("min_open_anchors", "max_open_anchors"),
    ):
        minimum = gate.get(minimum_key)
        maximum = gate.get(maximum_key)
        if (
            isinstance(minimum, int)
            and isinstance(maximum, int)
            and maximum < minimum
        ):
            raise ValueError(
                f"case {case_id} promotion region gate {gate_id} "
                f"{maximum_key} must be >= {minimum_key}"
            )


def _validate_promotion_visual_thresholds(case_id: str, value: Any) -> None:
    if not isinstance(value, dict):
        raise ValueError(f"case {case_id} promotion visual_thresholds must be an object")
    family = value.get("family")
    if family is not None and (not isinstance(family, str) or not family):
        raise ValueError(
            f"case {case_id} promotion visual_thresholds family must be a string"
        )
    configured = False
    for key in sorted(PROMOTION_VISUAL_THRESHOLD_KEYS):
        threshold = value.get(key)
        if threshold is None:
            continue
        configured = True
        if not isinstance(threshold, (int, float)) or threshold < 0:
            raise ValueError(
                f"case {case_id} promotion visual_thresholds {key} "
                "must be a non-negative number"
            )
    if not configured:
        allowed = ", ".join(sorted(PROMOTION_VISUAL_THRESHOLD_KEYS))
        raise ValueError(
            f"case {case_id} promotion visual_thresholds must set at least one of: "
            f"{allowed}"
        )
    severity = value.get("severity", "red")
    if severity not in PROMOTION_GATE_SEVERITIES:
        allowed = ", ".join(sorted(PROMOTION_GATE_SEVERITIES))
        raise ValueError(
            f"case {case_id} promotion visual_thresholds severity "
            f"must be one of: {allowed}"
        )
    description = value.get("description")
    if description is not None and (
        not isinstance(description, str) or not description
    ):
        raise ValueError(
            f"case {case_id} promotion visual_thresholds description must be a string"
        )


def _validate_promotion_group_gates(case_id: str, gates: Any) -> None:
    if not isinstance(gates, list):
        raise ValueError(f"case {case_id} promotion group_gates must be an array")
    seen_ids: set[str] = set()
    for index, gate in enumerate(gates):
        if not isinstance(gate, dict):
            raise ValueError(
                f"case {case_id} promotion group_gates[{index}] must be an object"
            )
        gate_id = gate.get("id")
        if not isinstance(gate_id, str) or not gate_id:
            raise ValueError(
                f"case {case_id} promotion group_gates[{index}] id must be a string"
            )
        if gate_id in seen_ids:
            raise ValueError(
                f"case {case_id} promotion duplicate group gate id: {gate_id}"
            )
        seen_ids.add(gate_id)
        gate_type = gate.get("gate_type")
        if gate_type not in {"grouping", "fragmentation"}:
            raise ValueError(
                f"case {case_id} promotion group gate {gate_id} gate_type "
                "must be grouping or fragmentation"
            )
        expected = gate.get("expected_group_kinds")
        if not isinstance(expected, list) or not expected or not all(
            isinstance(item, str) and item for item in expected
        ):
            raise ValueError(
                f"case {case_id} promotion group gate {gate_id} "
                "expected_group_kinds must be a non-empty string array"
            )
        _validate_group_gate_count(case_id, gate_id, gate, "min_count", 1)
        _validate_group_gate_count(case_id, gate_id, gate, "max_count", None)
        _validate_group_gate_count(case_id, gate_id, gate, "min_member_count", 0)
        _validate_group_gate_count(case_id, gate_id, gate, "max_member_count", None)
        _validate_group_gate_order(case_id, gate_id, gate, "min_count", "max_count")
        _validate_group_gate_order(
            case_id,
            gate_id,
            gate,
            "min_member_count",
            "max_member_count",
        )
        severity = gate.get("severity", "red")
        if severity not in PROMOTION_GATE_SEVERITIES:
            allowed = ", ".join(sorted(PROMOTION_GATE_SEVERITIES))
            raise ValueError(
                f"case {case_id} promotion group gate {gate_id} severity "
                f"must be one of: {allowed}"
            )
        description = gate.get("description")
        if description is not None and (
            not isinstance(description, str) or not description
        ):
            raise ValueError(
                f"case {case_id} promotion group gate {gate_id} "
                "description must be a string"
            )


def _validate_group_gate_count(
    case_id: str,
    gate_id: str,
    gate: dict[str, Any],
    key: str,
    default: int | None,
) -> None:
    value = gate.get(key, default)
    if value is None:
        return
    if not isinstance(value, int) or value < 0:
        raise ValueError(
            f"case {case_id} promotion group gate {gate_id} {key} "
            "must be a non-negative integer"
        )


def _validate_group_gate_order(
    case_id: str,
    gate_id: str,
    gate: dict[str, Any],
    minimum_key: str,
    maximum_key: str,
) -> None:
    minimum = gate.get(minimum_key)
    maximum = gate.get(maximum_key)
    if isinstance(minimum, int) and isinstance(maximum, int) and maximum < minimum:
        raise ValueError(
            f"case {case_id} promotion group gate {gate_id} "
            f"{maximum_key} must be >= {minimum_key}"
        )
