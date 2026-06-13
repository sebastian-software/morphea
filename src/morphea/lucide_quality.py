"""Lucide icon benchmark helpers."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from PIL import Image

from morphea.images import scene_from_flat_color_image
from morphea.rendering import raster_fidelity_metrics
from morphea.runs import write_vectorize_run
from morphea.svg_raster import rasterized_svg_image


LUCIDE_VECTORIZE_CONFIG_KEYS = {
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


def load_lucide_suite(path: str | Path) -> dict[str, Any]:
    """Load and validate a Lucide benchmark suite file."""

    suite_path = Path(path)
    suite = json.loads(suite_path.read_text(encoding="utf-8"))
    if not isinstance(suite, dict):
        raise ValueError("lucide suite must be a JSON object")
    if suite.get("version") != 1:
        raise ValueError("lucide suite version must be 1")
    render = suite.get("render", {})
    if not isinstance(render, dict):
        raise ValueError("lucide suite render must be an object")
    size = render.get("size", 64)
    if not isinstance(size, int) or size <= 0:
        raise ValueError("lucide suite render size must be a positive integer")
    cases = suite.get("cases")
    if not isinstance(cases, list):
        raise ValueError("lucide suite must contain a cases array")
    seen_ids: set[str] = set()
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            raise ValueError(f"case {index} must be a JSON object")
        case_id = case.get("id")
        if not isinstance(case_id, str) or not case_id:
            raise ValueError(f"case {index} must have a non-empty id")
        if case_id in seen_ids:
            raise ValueError(f"duplicate lucide case id: {case_id}")
        seen_ids.add(case_id)
        family = case.get("family")
        if not isinstance(family, str) or not family:
            raise ValueError(f"case {case_id} must have a non-empty family")
        source = case.get("source")
        if not isinstance(source, str) or not source:
            raise ValueError(f"case {case_id} must have a non-empty source")
        expectations = case.get("expectations", [])
        if not isinstance(expectations, list):
            raise ValueError(f"case {case_id} expectations must be an array")
        for expectation_index, expectation in enumerate(expectations):
            _validate_expectation(case_id, expectation_index, expectation)
    config = suite.get("recommended_config", {})
    if config is not None and not isinstance(config, dict):
        raise ValueError("lucide suite recommended_config must be an object")
    return suite


def check_lucide_suite(
    suite_path: str | Path,
    *,
    output: str | Path | None = None,
    output_dir: str | Path | None = None,
    markdown: str | Path | None = None,
    config_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Render, vectorize, and evaluate a Lucide icon benchmark suite."""

    suite_file = Path(suite_path)
    suite = load_lucide_suite(suite_file)
    render_config = _render_config(suite)
    vectorize_config = {
        **_vectorize_config(suite.get("recommended_config", {})),
        **_vectorize_config(config_overrides or {}),
    }
    renderer = lucide_source_renderer_status()
    suite_output_dir = Path(output_dir) if output_dir is not None else None
    cases = [
        _check_lucide_case(
            case,
            suite_file=suite_file,
            output_dir=suite_output_dir,
            renderer=renderer,
            render_config=render_config,
            vectorize_config=vectorize_config,
        )
        for case in suite["cases"]
    ]
    report = {
        "suite": str(suite_file),
        "version": suite["version"],
        "source_package": suite.get("source_package"),
        "source_version": suite.get("source_version"),
        "renderer": renderer,
        "render": render_config,
        "config": _json_config(vectorize_config),
        "case_count": len(cases),
        "passed_count": sum(1 for case in cases if case.get("ok")),
        "failed_count": sum(1 for case in cases if not case.get("ok")),
        "ok": all(case["ok"] for case in cases),
        "family_summary": _family_summary(cases),
        "anchor_kind_counts": _aggregate_counts(
            case.get("anchor_kind_counts", {}) for case in cases
        ),
        "cases": cases,
    }
    if output is not None:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(report, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    if markdown is not None:
        markdown_path = Path(markdown)
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(render_lucide_markdown(report), encoding="utf-8")
    return report


def render_lucide_markdown(report: dict[str, Any]) -> str:
    """Render a scan-friendly Lucide benchmark report."""

    cases = [case for case in report.get("cases", []) if isinstance(case, dict)]
    lines = [
        "# Morphea Lucide Check",
        "",
        f"- Suite: `{report.get('suite', 'n/a')}`",
        f"- Source: `{report.get('source_package', 'n/a')}@{report.get('source_version', 'n/a')}`",
        f"- Renderer: `{_renderer_label(report.get('renderer'))}`",
        f"- Cases: {_fmt_value(report.get('case_count'))}",
        f"- Passed: {_fmt_value(report.get('passed_count'))}",
        f"- Failed: {_fmt_value(report.get('failed_count'))}",
        f"- OK: `{str(report.get('ok', False)).lower()}`",
        "",
        "## Families",
        "",
        "| Family | Cases | Passed | Failed |",
        "| --- | ---: | ---: | ---: |",
    ]
    family_summary = report.get("family_summary", {})
    if isinstance(family_summary, dict):
        for family, summary in sorted(family_summary.items()):
            if not isinstance(summary, dict):
                continue
            lines.append(
                "| "
                f"`{family}` | "
                f"{_fmt_value(summary.get('case_count'))} | "
                f"{_fmt_value(summary.get('passed_count'))} | "
                f"{_fmt_value(summary.get('failed_count'))} |"
            )

    lines.extend(
        [
            "",
            "## Cases",
            "",
            "| Case | Family | OK | Actual | Generic | Nodes | SVG L1 | SVG Edge | Failed expectations |",
            "| --- | --- | ---: | --- | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for case in cases:
        failed = [
            str(expectation.get("id", "n/a"))
            for expectation in case.get("expectations", [])
            if isinstance(expectation, dict) and not expectation.get("ok", False)
        ]
        metrics = case.get("metrics", {})
        if not isinstance(metrics, dict):
            metrics = {}
        lines.append(
            "| "
            f"`{case.get('id', 'n/a')}` | "
            f"`{case.get('family', 'n/a')}` | "
            f"`{str(case.get('ok', False)).lower()}` | "
            f"{_fmt_counts(case.get('anchor_kind_counts'))} | "
            f"{_fmt_value(metrics.get('generic_path_count'))} | "
            f"{_fmt_value(metrics.get('node_count'))} | "
            f"{_fmt_value(metrics.get('svg_raster_l1_error'))} | "
            f"{_fmt_value(metrics.get('svg_raster_edge_error'))} | "
            f"{', '.join(f'`{item}`' for item in failed) if failed else 'n/a'} |"
        )

    for case in cases:
        lines.extend(["", f"## {case.get('id', 'n/a')}", ""])
        lines.append(f"- Family: `{case.get('family', 'n/a')}`")
        lines.append(f"- Status: `{case.get('status', 'n/a')}`")
        lines.append(f"- Anchor kinds: {_fmt_counts(case.get('anchor_kind_counts'))}")
        if isinstance(case.get("artifacts"), dict):
            lines.append(f"- Artifacts: `{case['artifacts'].get('run_dir', 'n/a')}`")
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


def lucide_source_renderer_status() -> dict[str, Any]:
    """Return the source SVG renderer available for Lucide PNG inputs."""

    rsvg = shutil.which("rsvg-convert")
    if rsvg:
        return {
            "backend": "rsvg-convert",
            "available": True,
            "path": rsvg,
        }
    try:
        import cairosvg  # noqa: F401
    except Exception as exc:
        return {
            "backend": None,
            "available": False,
            "reason": (
                "requires rsvg-convert or CairoSVG to render Lucide source SVGs"
            ),
            "error": f"{type(exc).__name__}: {exc}",
        }
    return {
        "backend": "cairosvg",
        "available": True,
        "path": None,
    }


def _check_lucide_case(
    case: dict[str, Any],
    *,
    suite_file: Path,
    output_dir: Path | None,
    renderer: dict[str, Any],
    render_config: dict[str, Any],
    vectorize_config: dict[str, Any],
) -> dict[str, Any]:
    source = (suite_file.parent / str(case["source"])).resolve()
    result: dict[str, Any] = {
        "id": case["id"],
        "family": case["family"],
        "source": str(source),
        "source_exists": source.exists(),
        "status": "not_run",
        "ok": False,
        "expectations": [],
    }
    if not source.exists():
        result["status"] = "missing_source"
        return result
    if not renderer.get("available"):
        result["status"] = "renderer_unavailable"
        result["renderer"] = renderer
        return result

    case_dir = output_dir / case["id"] if output_dir is not None else None
    input_path = (
        case_dir / f"{case['id']}.png"
        if case_dir is not None
        else source.with_suffix(".lucide-input.png")
    )
    input_path.parent.mkdir(parents=True, exist_ok=True)
    _render_source_svg(
        source,
        input_path,
        renderer=renderer,
        render_config=render_config,
    )
    scene = scene_from_flat_color_image(input_path, **vectorize_config)
    manifest = scene.to_manifest()
    source_image = Image.open(input_path).convert("RGBA")
    output_svg_text = scene.to_svg()
    rendered_output = rasterized_svg_image(
        output_svg_text,
        background=str(render_config["background"]),
    )
    svg_metrics = raster_fidelity_metrics(
        source=source_image,
        rendered=rendered_output,
    )
    metrics = manifest.setdefault("metrics", {})
    metrics.update(
        {
            "svg_raster_l1_error": svg_metrics["raster_l1_error"],
            "svg_raster_edge_error": svg_metrics["raster_edge_error"],
            "svg_alpha_error": svg_metrics["raster_alpha_error"],
            "svg_render_size_match": svg_metrics["raster_size_match"],
        }
    )
    expectation_results = _check_expectations(case.get("expectations", []), manifest)
    result.update(
        {
            "status": "checked",
            "ok": all(item["ok"] for item in expectation_results),
            "config": _json_config(vectorize_config),
            "render": dict(render_config),
            "anchor_count": manifest["anchor_count"],
            "anchor_kind_counts": _counts(
                anchor.get("kind") for anchor in manifest.get("anchors", [])
            ),
            "group_kind_counts": _counts(
                group.get("kind") for group in manifest.get("groups", [])
            ),
            "diagnostic_count": len(manifest["diagnostics"]),
            "metrics": dict(sorted(metrics.items())),
            "expectations": expectation_results,
        }
    )
    if case_dir is not None:
        run = write_vectorize_run(
            run_dir=case_dir,
            input_path=input_path,
            scene=scene,
            config={
                "command": "lucide-check",
                "case_id": case["id"],
                "source_svg": str(source),
                **_json_config(vectorize_config),
            },
        )
        run.manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        rendered_output.save(case_dir / "svg-render.png")
        shutil.copy2(source, case_dir / "source.svg")
        result["artifacts"] = {
            "run_dir": str(run.run_dir),
            "source_svg": str(case_dir / "source.svg"),
            "input": str(run.input_path),
            "output_svg": str(run.svg_path),
            "debug_svg": str(run.debug_svg_path),
            "manifest": str(run.manifest_path),
            "preview": str(run.preview_path),
            "svg_render": str(case_dir / "svg-render.png"),
            "report": str(run.report_path),
        }
    elif input_path.name.endswith(".lucide-input.png"):
        input_path.unlink(missing_ok=True)
    return result


def _render_source_svg(
    source: Path,
    output: Path,
    *,
    renderer: dict[str, Any],
    render_config: dict[str, Any],
) -> None:
    backend = renderer.get("backend")
    size = int(render_config["size"])
    background = str(render_config["background"])
    color = str(render_config["color"])
    text = _lucide_svg_for_render(source, color=color)
    temporary_svg = output.with_suffix(".source.svg")
    temporary_svg.write_text(text, encoding="utf-8")
    try:
        if backend == "rsvg-convert":
            command = [
                str(renderer["path"]),
                "-w",
                str(size),
                "-h",
                str(size),
                "-b",
                background,
                "-o",
                str(output),
                str(temporary_svg),
            ]
            subprocess.run(command, check=True, capture_output=True)
        elif backend == "cairosvg":
            import cairosvg

            cairosvg.svg2png(
                url=str(temporary_svg),
                write_to=str(output),
                output_width=size,
                output_height=size,
                background_color=background,
            )
        else:
            raise RuntimeError("no Lucide source SVG renderer available")
    finally:
        temporary_svg.unlink(missing_ok=True)


def _lucide_svg_for_render(source: Path, *, color: str) -> str:
    text = source.read_text(encoding="utf-8")
    return text.replace("currentColor", color)


def _render_config(suite: dict[str, Any]) -> dict[str, Any]:
    render = suite.get("render", {})
    if not isinstance(render, dict):
        render = {}
    return {
        "size": int(render.get("size", 64)),
        "background": str(render.get("background", "#ffffff")),
        "color": str(render.get("color", "#000000")),
    }


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
        ok = isinstance(actual, (int, float, bool))
        result: dict[str, Any] = {
            "id": expectation["id"],
            "metric": metric,
            "actual_value": actual if ok else None,
        }
        if "min_value" in expectation:
            minimum = float(expectation["min_value"])
            result["min_value"] = minimum
            ok = ok and float(actual) >= minimum if ok else False
        if "max_value" in expectation:
            maximum = float(expectation["max_value"])
            result["max_value"] = maximum
            ok = ok and float(actual) <= maximum if ok else False
        result["ok"] = ok
        return result

    kind = expectation.get("kind")
    group_kind = expectation.get("group_kind")
    if kind is not None:
        actual = sum(
            1 for anchor in manifest.get("anchors", []) if anchor.get("kind") == kind
        )
        label = {"kind": kind}
    else:
        actual = sum(
            1
            for group in manifest.get("groups", [])
            if group.get("kind") == group_kind
        )
        label = {"group_kind": group_kind}
    minimum = int(expectation.get("min_count", 1))
    maximum = expectation.get("max_count")
    ok = actual >= minimum
    result = {
        "id": expectation["id"],
        **label,
        "actual_count": actual,
        "min_count": minimum,
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


def _validate_expectation(case_id: str, index: int, expectation: Any) -> None:
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
            if key in expectation and not isinstance(
                expectation.get(key), (int, float)
            ):
                raise ValueError(
                    f"case {case_id} expectation {expectation_id} {key} "
                    "must be numeric"
                )
        return
    min_count = expectation.get("min_count", 1)
    if not isinstance(min_count, int) or min_count < 0:
        raise ValueError(
            f"case {case_id} expectation {expectation_id} min_count must be non-negative"
        )
    max_count = expectation.get("max_count")
    if max_count is not None and (
        not isinstance(max_count, int) or max_count < min_count
    ):
        raise ValueError(
            f"case {case_id} expectation {expectation_id} max_count must be >= min_count"
        )


def _vectorize_config(config: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in config.items()
        if key in LUCIDE_VECTORIZE_CONFIG_KEYS
    }


def _json_config(config: dict[str, Any]) -> dict[str, Any]:
    return {
        key: str(value) if isinstance(value, Path) else value
        for key, value in config.items()
    }


def _family_summary(cases: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    summary: dict[str, dict[str, int]] = {}
    for case in cases:
        family = str(case.get("family", "unknown"))
        family_summary = summary.setdefault(
            family,
            {"case_count": 0, "passed_count": 0, "failed_count": 0},
        )
        family_summary["case_count"] += 1
        if case.get("ok"):
            family_summary["passed_count"] += 1
        else:
            family_summary["failed_count"] += 1
    return dict(sorted(summary.items()))


def _aggregate_counts(items: object) -> dict[str, int]:
    aggregate: dict[str, int] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        for key, value in item.items():
            aggregate[str(key)] = aggregate.get(str(key), 0) + int(value)
    return dict(sorted(aggregate.items()))


def _counts(values: object) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        key = str(value)
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def _renderer_label(value: object) -> str:
    if not isinstance(value, dict):
        return "n/a"
    backend = value.get("backend") or "unavailable"
    if value.get("available"):
        return str(backend)
    return f"{backend}: {value.get('reason', 'unavailable')}"


def _fmt_counts(value: object) -> str:
    if not isinstance(value, dict) or not value:
        return "n/a"
    return ", ".join(f"`{key}`={_fmt_value(value[key])}" for key in sorted(value))


def _fmt_value(value: object) -> str:
    if isinstance(value, bool) or value is None:
        return "n/a"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def _expectation_markdown_row(expectation: dict[str, Any]) -> str:
    if "metric" in expectation:
        required_parts = []
        if "min_value" in expectation:
            required_parts.append(f">= {_fmt_value(expectation['min_value'])}")
        if "max_value" in expectation:
            required_parts.append(f"<= {_fmt_value(expectation['max_value'])}")
        return (
            "| "
            f"`{expectation.get('id', 'n/a')}` | "
            f"`metric:{expectation.get('metric', 'n/a')}` | "
            f"{_fmt_value(expectation.get('actual_value'))} | "
            f"{', '.join(required_parts) if required_parts else 'n/a'} | "
            f"`{str(expectation.get('ok', False)).lower()}` |"
        )
    expectation_type = expectation.get("kind")
    label = "kind"
    if expectation_type is None:
        expectation_type = expectation.get("group_kind")
        label = "group"
    required_minimum = expectation.get(
        "cumulative_min_count",
        expectation.get("min_count"),
    )
    required = f">= {_fmt_value(required_minimum)}"
    if "max_count" in expectation:
        required += f", <= {_fmt_value(expectation.get('max_count'))}"
    return (
        "| "
        f"`{expectation.get('id', 'n/a')}` | "
        f"`{label}:{expectation_type}` | "
        f"{_fmt_value(expectation.get('actual_count'))} | "
        f"{required} | "
        f"`{str(expectation.get('ok', False)).lower()}` |"
    )
