"""Lucide icon benchmark helpers."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
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
LUCIDE_QUALITY_LABELS = {"green", "yellow", "red"}
_PATH_COMMAND = re.compile(r"[AaCcHhLlMmQqSsTtVvZz]")


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
        quality_label = case.get("quality_label")
        if quality_label is not None and quality_label not in LUCIDE_QUALITY_LABELS:
            raise ValueError(
                f"case {case_id} quality_label must be one of: "
                f"{', '.join(sorted(LUCIDE_QUALITY_LABELS))}"
            )
        review_notes = case.get("review_notes", [])
        if not isinstance(review_notes, list) or not all(
            isinstance(item, str) and item for item in review_notes
        ):
            raise ValueError(f"case {case_id} review_notes must be a string array")
        if quality_label in {"yellow", "red"} and not review_notes:
            raise ValueError(
                f"case {case_id} quality_label {quality_label} requires review_notes"
            )
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
        "quality_summary": _quality_summary(cases),
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


def build_lucide_training_corpus(
    suite_path: str | Path,
    *,
    output: str | Path,
    output_dir: str | Path,
    markdown: str | Path | None = None,
) -> dict[str, Any]:
    """Render Lucide source SVGs into a supervised image/SVG corpus manifest."""

    suite_file = Path(suite_path)
    suite = load_lucide_suite(suite_file)
    render_config = _render_config(suite)
    renderer = lucide_source_renderer_status()
    corpus_dir = Path(output_dir)
    corpus_dir.mkdir(parents=True, exist_ok=True)
    examples = [
        _lucide_training_example(
            case,
            suite_file=suite_file,
            output_dir=corpus_dir,
            renderer=renderer,
            render_config=render_config,
        )
        for case in suite["cases"]
    ]
    rendered_examples = [item for item in examples if item.get("status") == "rendered"]
    report = {
        "schema_version": 1,
        "source": "lucide_suite",
        "suite": str(suite_file),
        "source_package": suite.get("source_package"),
        "source_version": suite.get("source_version"),
        "renderer": renderer,
        "render": render_config,
        "output_dir": str(corpus_dir),
        "case_count": len(examples),
        "example_count": len(rendered_examples),
        "ok": len(rendered_examples) == len(examples),
        "family_summary": _training_family_summary(examples),
        "target_summary": _training_target_summary(rendered_examples),
        "examples": examples,
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
            render_lucide_corpus_markdown(report),
            encoding="utf-8",
        )
    return report


def render_lucide_corpus_markdown(report: dict[str, Any]) -> str:
    """Render a scan-friendly supervised Lucide corpus summary."""

    examples = [
        item for item in report.get("examples", []) if isinstance(item, dict)
    ]
    target_summary = report.get("target_summary", {})
    if not isinstance(target_summary, dict):
        target_summary = {}
    lines = [
        "# Morphea Lucide Training Corpus",
        "",
        f"- Suite: `{report.get('suite', 'n/a')}`",
        f"- Source: `{report.get('source_package', 'n/a')}@{report.get('source_version', 'n/a')}`",
        f"- Renderer: `{_renderer_label(report.get('renderer'))}`",
        f"- Output dir: `{report.get('output_dir', 'n/a')}`",
        f"- Cases: {_fmt_value(report.get('case_count'))}",
        f"- Examples: {_fmt_value(report.get('example_count'))}",
        f"- OK: `{str(report.get('ok', False)).lower()}`",
        "",
        "## Families",
        "",
        "| Family | Cases | Rendered | Missing |",
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
                f"{_fmt_value(summary.get('rendered_count'))} | "
                f"{_fmt_value(summary.get('missing_count'))} |"
            )
    lines.extend(
        [
            "",
            "## Target Summary",
            "",
            f"- Anchor targets: {_fmt_counts(target_summary.get('anchor_kind_targets'))}",
            f"- Forbidden anchors: {_fmt_counts(target_summary.get('forbidden_anchor_kinds'))}",
            f"- Source SVG elements: {_fmt_counts(target_summary.get('source_element_counts'))}",
            "",
            "## Examples",
            "",
            "| Case | Split | Family | Quality | Status | PNG | Source SVG | Anchor targets | Forbidden |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for example in examples:
        labels = example.get("labels", {})
        if not isinstance(labels, dict):
            labels = {}
        lines.append(
            "| "
            f"`{example.get('id', 'n/a')}` | "
            f"`{example.get('split', 'n/a')}` | "
            f"`{example.get('family', 'n/a')}` | "
            f"`{example.get('quality_label', 'n/a')}` | "
            f"`{example.get('status', 'n/a')}` | "
            f"`{example.get('input_png', 'n/a')}` | "
            f"`{example.get('source_svg', 'n/a')}` | "
            f"{_fmt_counts(labels.get('anchor_kind_targets'))} | "
            f"{_fmt_counts(labels.get('forbidden_anchor_kinds'))} |"
        )
    return "\n".join(lines).rstrip() + "\n"


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
            "## Quality Ledger",
            "",
            f"- Yellow cases: {_fmt_case_ids(_case_ids_for_label(cases, 'yellow'))}",
            f"- Red cases: {_fmt_case_ids(_case_ids_for_label(cases, 'red'))}",
            "",
            "| Case | Family | Quality | OK | Review notes |",
            "| --- | --- | --- | ---: | --- |",
        ]
    )
    for case in cases:
        lines.append(
            "| "
            f"`{case.get('id', 'n/a')}` | "
            f"`{case.get('family', 'n/a')}` | "
            f"`{case.get('quality_label', 'n/a')}` | "
            f"`{str(case.get('ok', False)).lower()}` | "
            f"{_fmt_markdown_list(case.get('review_notes'))} |"
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
                "| Expectation | Type | Actual | Required | OK | Failure |",
                "| --- | --- | ---: | ---: | ---: | --- |",
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
        "quality_label": _lucide_quality_label(case, ok=False),
        "review_notes": _lucide_review_notes(case),
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
    failed_expectation_ids = [
        str(item.get("id", "n/a"))
        for item in expectation_results
        if not item.get("ok", False)
    ]
    result.update(
        {
            "status": "checked",
            "ok": all(item["ok"] for item in expectation_results),
            "quality_label": _lucide_quality_label(
                case,
                ok=all(item["ok"] for item in expectation_results),
            ),
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
            "failed_expectation_count": len(failed_expectation_ids),
            "failed_expectation_ids": failed_expectation_ids,
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


def _lucide_training_example(
    case: dict[str, Any],
    *,
    suite_file: Path,
    output_dir: Path,
    renderer: dict[str, Any],
    render_config: dict[str, Any],
) -> dict[str, Any]:
    source = (suite_file.parent / str(case["source"])).resolve()
    case_dir = output_dir / str(case["id"])
    input_png = case_dir / "input.png"
    source_copy = case_dir / "source.svg"
    labels = _lucide_training_labels(case, source)
    result: dict[str, Any] = {
        "id": case["id"],
        "split": str(case.get("split", "train")),
        "family": case["family"],
        "quality_label": _lucide_quality_label(case, ok=True),
        "review_notes": _lucide_review_notes(case),
        "status": "not_rendered",
        "source": str(source),
        "source_exists": source.exists(),
        "input_png": str(input_png),
        "source_svg": str(source_copy),
        "render": dict(render_config),
        "labels": labels,
    }
    if not source.exists():
        result["status"] = "missing_source"
        return result
    if not renderer.get("available"):
        result["status"] = "renderer_unavailable"
        result["renderer"] = renderer
        return result
    case_dir.mkdir(parents=True, exist_ok=True)
    _render_source_svg(
        source,
        input_png,
        renderer=renderer,
        render_config=render_config,
    )
    shutil.copy2(source, source_copy)
    result["status"] = "rendered"
    return result


def _lucide_training_labels(case: dict[str, Any], source: Path) -> dict[str, Any]:
    expectations = [
        expectation
        for expectation in case.get("expectations", [])
        if isinstance(expectation, dict)
    ]
    return {
        "schema_version": 1,
        "source_svg": _source_svg_training_summary(source),
        "anchor_kind_targets": _expected_kind_counts(expectations, "kind"),
        "group_kind_targets": _expected_kind_counts(expectations, "group_kind"),
        "forbidden_anchor_kinds": _forbidden_kind_counts(expectations, "kind"),
        "forbidden_group_kinds": _forbidden_kind_counts(expectations, "group_kind"),
        "bounded_anchor_targets": _bounded_anchor_targets(expectations),
        "metric_targets": _metric_targets(expectations),
        "expectations": [dict(expectation) for expectation in expectations],
    }


def _source_svg_training_summary(source: Path) -> dict[str, Any]:
    if not source.exists():
        return {"status": "missing_source"}
    try:
        root = ET.fromstring(source.read_text(encoding="utf-8"))
    except ET.ParseError as exc:
        return {
            "status": "parse_error",
            "error": str(exc),
        }
    path_command_counts: dict[str, int] = {}
    path_count = 0
    for element in root.iter():
        if _local_name(element.tag) != "path":
            continue
        path_count += 1
        for command in _PATH_COMMAND.findall(element.attrib.get("d", "")):
            key = command.upper()
            path_command_counts[key] = path_command_counts.get(key, 0) + 1
    return {
        "status": "parsed",
        "view_box": root.attrib.get("viewBox"),
        "width": root.attrib.get("width"),
        "height": root.attrib.get("height"),
        "fill": root.attrib.get("fill"),
        "stroke": root.attrib.get("stroke"),
        "stroke_width": root.attrib.get("stroke-width"),
        "stroke_linecap": root.attrib.get("stroke-linecap"),
        "stroke_linejoin": root.attrib.get("stroke-linejoin"),
        "element_counts": _svg_element_counts(root),
        "path_count": path_count,
        "path_command_counts": dict(sorted(path_command_counts.items())),
    }


def _svg_element_counts(root: ET.Element) -> dict[str, int]:
    counts: dict[str, int] = {}
    for element in root.iter():
        name = _local_name(element.tag)
        counts[name] = counts.get(name, 0) + 1
    return dict(sorted(counts.items()))


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _expected_kind_counts(
    expectations: list[dict[str, Any]],
    key: str,
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for expectation in expectations:
        value = expectation.get(key)
        if not isinstance(value, str) or not value:
            continue
        minimum = int(expectation.get("min_count", 1))
        maximum = expectation.get("max_count")
        if minimum <= 0 and maximum == 0:
            continue
        if minimum <= 0:
            continue
        counts[value] = counts.get(value, 0) + minimum
    return dict(sorted(counts.items()))


def _forbidden_kind_counts(
    expectations: list[dict[str, Any]],
    key: str,
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for expectation in expectations:
        value = expectation.get(key)
        if not isinstance(value, str) or not value:
            continue
        if (
            int(expectation.get("min_count", 1)) == 0
            and expectation.get("max_count") == 0
        ):
            counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _bounded_anchor_targets(
    expectations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    targets = []
    for expectation in expectations:
        kind = expectation.get("kind")
        bounds = expectation.get("bounds")
        if not isinstance(kind, str) or bounds is None:
            continue
        targets.append(
            {
                "id": expectation.get("id"),
                "kind": kind,
                "bounds": bounds,
                "min_iou": expectation.get("min_iou", 0.0),
                "min_count": expectation.get("min_count", 1),
                "max_count": expectation.get("max_count"),
            }
        )
    return targets


def _metric_targets(expectations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    targets = []
    for expectation in expectations:
        metric = expectation.get("metric")
        if not isinstance(metric, str) or not metric:
            continue
        target = {
            "id": expectation.get("id"),
            "metric": metric,
        }
        if "min_value" in expectation:
            target["min_value"] = expectation["min_value"]
        if "max_value" in expectation:
            target["max_value"] = expectation["max_value"]
        targets.append(target)
    return targets


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
        _annotate_expectation_failure(result)
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
        bounds = _parse_float_bounds(expectation.get("bounds"))
        min_iou = float(expectation.get("min_iou", 0.0))
        actual = sum(
            1
            for anchor in manifest.get("anchors", [])
            if anchor.get("kind") == kind
            and _anchor_matches_bounds(anchor, bounds, min_iou)
        )
        label = {"kind": kind}
        if bounds is not None:
            label["bounds"] = list(bounds)
            label["min_iou"] = min_iou
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


def _annotate_expectation_failure(result: dict[str, Any]) -> None:
    if result.get("ok", False):
        return
    if "metric" in result:
        _annotate_metric_expectation_failure(result)
        return
    _annotate_shape_expectation_failure(result)


def _annotate_metric_expectation_failure(result: dict[str, Any]) -> None:
    actual = result.get("actual_value")
    if not isinstance(actual, (int, float, bool)):
        result["failure_reason"] = "missing_metric"
        return
    actual_value = float(actual)
    if "min_value" in result and actual_value < float(result["min_value"]):
        result["failure_reason"] = "metric_below_min"
        result["shortfall_value"] = float(result["min_value"]) - actual_value
        return
    if "max_value" in result and actual_value > float(result["max_value"]):
        result["failure_reason"] = "metric_above_max"
        result["excess_value"] = actual_value - float(result["max_value"])


def _annotate_shape_expectation_failure(result: dict[str, Any]) -> None:
    actual = int(result.get("actual_count", 0))
    required = int(
        result.get(
            "cumulative_min_count",
            result.get("min_count", 0),
        )
    )
    if actual < required:
        result["required_count"] = required
        result["missing_count"] = required - actual
        if "group_kind" in result:
            result["failure_reason"] = "insufficient_groups"
        elif required > int(result.get("min_count", required)):
            result["failure_reason"] = "insufficient_distinct_anchors"
        else:
            result["failure_reason"] = "insufficient_anchors"
        return
    if "max_count" in result and actual > int(result["max_count"]):
        result["failure_reason"] = (
            "forbidden_matches"
            if int(result["max_count"]) == 0
            and int(result.get("min_count", 0)) == 0
            else "too_many_matches"
        )
        result["excess_count"] = actual - int(result["max_count"])


def _shape_expectation_selector(
    expectation: dict[str, Any],
) -> tuple[str, str, str, str]:
    kind = expectation.get("kind")
    bounds = _selector_bounds_key(expectation.get("bounds"))
    min_iou = expectation.get("min_iou", 0.0)
    if kind is not None:
        return ("kind", str(kind), bounds, str(min_iou))
    return ("group_kind", str(expectation.get("group_kind")), bounds, str(min_iou))


def _selector_bounds_key(value: object) -> str:
    bounds = _parse_float_bounds(value)
    if bounds is None:
        return ""
    return ",".join(_fmt_value(item) for item in bounds)


def _anchor_matches_bounds(
    anchor: object,
    bounds: tuple[float, float, float, float] | None,
    min_iou: float,
) -> bool:
    if bounds is None:
        return True
    if not isinstance(anchor, dict):
        return False
    anchor_bounds = _manifest_anchor_bounds(anchor)
    if anchor_bounds is None:
        return False
    return _bounds_iou(anchor_bounds, bounds) >= min_iou


def _manifest_anchor_bounds(
    anchor: dict[str, Any],
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
    if not isinstance(value, list | tuple) or len(value) != 4:
        return None
    try:
        left, top, right, bottom = (float(item) for item in value)
    except (TypeError, ValueError):
        return None
    if right <= left or bottom <= top:
        return None
    return left, top, right, bottom


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
    return _bounds_area((left, top, right, bottom))


def _bounds_area(bounds: tuple[float, float, float, float]) -> float:
    return max(bounds[2] - bounds[0], 0.0) * max(bounds[3] - bounds[1], 0.0)


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
    if "bounds" in expectation and not has_kind:
        raise ValueError(
            f"case {case_id} expectation {expectation_id} bounds are only "
            "supported for kind expectations"
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
    if "bounds" in expectation:
        if _parse_float_bounds(expectation.get("bounds")) is None:
            raise ValueError(
                f"case {case_id} expectation {expectation_id} bounds must be "
                "[left, top, right, bottom] with positive area"
            )
    if "min_iou" in expectation and not isinstance(
        expectation.get("min_iou"),
        (int, float),
    ):
        raise ValueError(
            f"case {case_id} expectation {expectation_id} min_iou must be numeric"
        )
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


def _quality_summary(cases: list[dict[str, Any]]) -> dict[str, int]:
    return _counts(case.get("quality_label", "unknown") for case in cases)


def _training_family_summary(
    examples: list[dict[str, Any]],
) -> dict[str, dict[str, int]]:
    summary: dict[str, dict[str, int]] = {}
    for example in examples:
        family = str(example.get("family", "unknown"))
        item = summary.setdefault(
            family,
            {"case_count": 0, "rendered_count": 0, "missing_count": 0},
        )
        item["case_count"] += 1
        if example.get("status") == "rendered":
            item["rendered_count"] += 1
        else:
            item["missing_count"] += 1
    return dict(sorted(summary.items()))


def _training_target_summary(
    examples: list[dict[str, Any]],
) -> dict[str, dict[str, int]]:
    anchor_targets: dict[str, int] = {}
    group_targets: dict[str, int] = {}
    forbidden_anchors: dict[str, int] = {}
    source_element_counts: dict[str, int] = {}
    path_command_counts: dict[str, int] = {}
    for example in examples:
        labels = example.get("labels", {})
        if not isinstance(labels, dict):
            continue
        _add_counts(anchor_targets, labels.get("anchor_kind_targets"))
        _add_counts(group_targets, labels.get("group_kind_targets"))
        _add_counts(forbidden_anchors, labels.get("forbidden_anchor_kinds"))
        source_svg = labels.get("source_svg", {})
        if isinstance(source_svg, dict):
            _add_counts(source_element_counts, source_svg.get("element_counts"))
            _add_counts(path_command_counts, source_svg.get("path_command_counts"))
    return {
        "anchor_kind_targets": dict(sorted(anchor_targets.items())),
        "group_kind_targets": dict(sorted(group_targets.items())),
        "forbidden_anchor_kinds": dict(sorted(forbidden_anchors.items())),
        "source_element_counts": dict(sorted(source_element_counts.items())),
        "path_command_counts": dict(sorted(path_command_counts.items())),
    }


def _add_counts(target: dict[str, int], value: object) -> None:
    if not isinstance(value, dict):
        return
    for key, count in value.items():
        if not isinstance(count, (int, float)):
            continue
        target[str(key)] = target.get(str(key), 0) + int(count)


def _lucide_quality_label(case: dict[str, Any], *, ok: bool) -> str:
    label = case.get("quality_label")
    if isinstance(label, str) and label:
        return label
    return "green" if ok else "red"


def _lucide_review_notes(case: dict[str, Any]) -> list[str]:
    notes = case.get("review_notes", [])
    if not isinstance(notes, list):
        return []
    return [item for item in notes if isinstance(item, str) and item]


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


def _fmt_markdown_list(value: object) -> str:
    if not isinstance(value, list) or not value:
        return "n/a"
    return ", ".join(f"`{item}`" for item in value)


def _case_ids_for_label(cases: list[dict[str, Any]], label: str) -> list[str]:
    return [
        str(case.get("id", "n/a"))
        for case in cases
        if case.get("quality_label") == label
    ]


def _fmt_case_ids(values: list[str]) -> str:
    if not values:
        return "n/a"
    return ", ".join(f"`{item}`" for item in sorted(values))


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
            f"`{str(expectation.get('ok', False)).lower()}` | "
            f"{_expectation_failure_detail(expectation)} |"
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
    if required_minimum == 0 and expectation.get("max_count") == 0:
        required = "= 0"
    else:
        required = f">= {_fmt_value(required_minimum)}"
    if "max_count" in expectation and required != "= 0":
        required += f", <= {_fmt_value(expectation.get('max_count'))}"
    return (
        "| "
        f"`{expectation.get('id', 'n/a')}` | "
        f"`{label}:{expectation_type}` | "
        f"{_fmt_value(expectation.get('actual_count'))} | "
        f"{required} | "
        f"`{str(expectation.get('ok', False)).lower()}` | "
        f"{_expectation_failure_detail(expectation)} |"
    )


def _expectation_failure_detail(expectation: dict[str, Any]) -> str:
    reason = expectation.get("failure_reason")
    if not isinstance(reason, str) or not reason:
        return "n/a"
    details = [f"`{reason}`"]
    for key in (
        "missing_count",
        "excess_count",
        "shortfall_value",
        "excess_value",
    ):
        if key in expectation:
            details.append(f"{key}={_fmt_value(expectation.get(key))}")
    return ", ".join(details)
