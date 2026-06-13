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
        if "promotion" in case:
            _validate_promotion_metadata(case_id, case["promotion"])
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
    expectation_results = [
        _check_expectation(expectation, manifest)
        for expectation in case.get("expectations", [])
    ]
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
            **_write_visual_audit_artifacts(vectorize_run.run_dir, vectorize_run),
        }
    if isinstance(result.get("promotion"), dict):
        result["promotion_gates"] = _promotion_gate_results(result)
        result["promotion_summary"] = _promotion_summary(result["promotion_gates"])
    return result


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
    return {
        "id": expectation["id"],
        **label,
        "min_count": minimum,
        "actual_count": actual,
        "ok": actual >= minimum,
    }


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

    return {
        "id": expectation.get("id"),
        "ok": expectation.get("ok", False),
        "actual_count": expectation.get("actual_count", 0),
        "min_count": expectation.get("min_count", 1),
    }


def _counts(values: object) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        key = str(value)
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def _promotion_gate_results(case: dict[str, Any]) -> list[dict[str, object]]:
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
    return [
        _promotion_gate(
            "source_available",
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
            ok=not failed_expectations and checked,
            severity="red",
            reason=semantic_reason,
            evidence=failed_expectations,
        ),
        _promotion_gate(
            "visual_contact_sheet",
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
            ok=label == "green",
            severity="red" if label == "red" else "yellow",
            reason=f"current quality label is {label or 'missing'}",
            evidence=label,
        ),
    ]


def _promotion_gate(
    gate_id: str,
    *,
    ok: bool,
    severity: str,
    reason: str,
    evidence: object,
) -> dict[str, object]:
    return {
        "id": gate_id,
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
) -> dict[str, str]:
    svg_render_path = run_dir / "svg-render.png"
    diff_path = run_dir / "diff.png"
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
    contact_sheet = _contact_sheet_image(
        [
            ("source", source),
            ("preview", preview),
            ("svg render", svg_render),
            ("diff", diff),
        ]
    )
    contact_sheet.save(contact_sheet_path)
    return {
        "svg_render": str(svg_render_path),
        "diff": str(diff_path),
        "contact_sheet": str(contact_sheet_path),
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
    return (
        "| "
        f"`{expectation.get('id', 'n/a')}` | "
        f"`{label}:{expectation_type}` | "
        f"{_fmt_markdown_value(expectation.get('actual_count'))} | "
        f">= {_fmt_markdown_value(expectation.get('min_count'))} | "
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


def _validate_promotion_metadata(case_id: str, value: Any) -> None:
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
