"""Curated real-image regression suite helpers."""

from __future__ import annotations

from copy import deepcopy
import json
from math import ceil, floor
from pathlib import Path
import re
import shlex
from typing import Any

from PIL import Image, ImageDraw

from morphea.curated_gallery import render_review_gallery_html
from morphea.images import scene_from_flat_color_image
from morphea.rendering import raster_fidelity_metrics
from morphea.review_policy import promotion_quality_label_policy
from morphea.runs import VectorizeRun, write_vectorize_run
from morphea.scene import SvgStyle, anchors_to_svg
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
PROMOTION_QUALITY_LABEL_REVIEW_POLICIES = {"manual_review_pending"}
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
PROMOTION_REVIEW_DECISIONS = ("accepted", "corrected", "rejected", "deferred")
PROMOTION_PIPELINE_DECISIONS = {"promoted", "deferred", "rejected"}
PROMOTION_PIPELINE_REGION_STATES = {"promoted", "deferred", "rejected"}
PROMOTION_PIPELINE_EXPORT_ARTIFACTS = (
    "promoted_svg",
    "fallback_svg",
    "promotion_export",
    "promotion_regions",
)
PROMOTION_PIPELINE_REVIEW_ARTIFACTS = (
    "contact_sheet",
    "manifest",
    "promotion_export",
    "promotion_regions",
    "promotion_review",
    "editability_review",
    "review_decision",
)
PROMOTION_REGION_TOPOLOGY_LIMITS = {
    "min_closed_anchors",
    "max_closed_anchors",
    "min_open_anchors",
    "max_open_anchors",
    "max_hole_count",
    "max_cutout_count",
    "min_nested_contours",
    "max_nested_contours",
    "max_disconnected_components",
}
PROMOTION_REGION_TOPOLOGY_DESCRIPTORS = {
    "empty",
    "closed",
    "open",
    "mixed_open_closed",
    "single_component",
    "multi_component",
    "holes",
    "cutouts",
    "nested_contours",
}
PROMOTION_VISUAL_THRESHOLD_KEYS = {
    "max_raster_l1_error",
    "max_raster_edge_error",
}
PROMOTION_REGION_VISUAL_THRESHOLD_KEYS = PROMOTION_VISUAL_THRESHOLD_KEYS
PROMOTION_STRUCTURE_THRESHOLD_KEYS = {
    "max_fragmentation_penalty",
    "max_layer_count",
    "max_structural_layer_count",
}
RIP1_BOUNDED_CONFIG_KEYS = (
    "max_size",
    "max_colors",
    "max_component_area",
    "timeout_seconds",
)
SIMPLE_ANCHOR_KINDS = {
    "circle",
    "ellipse",
    "rect",
    "rounded_rect",
    "quad",
    "stroke_circle",
    "stroke_ellipse",
    "stroke_polyline",
    "stroke_path",
    "arc",
}
STROKE_ANCHOR_KINDS = {
    "stroke_circle",
    "stroke_ellipse",
    "stroke_polyline",
    "stroke_path",
    "arc",
}
EDITABILITY_REVIEW_THRESHOLDS = {
    "shape_identity_confidence": 0.65,
    "parameter_economy": 0.25,
    "node_economy": 0.5,
    "topology_consistency": 0.75,
    "grouping_quality": 0.5,
    "fragmentation": 0.25,
    "raster_fidelity": 0.75,
    "provenance_confidence": 0.65,
}
EDITABILITY_REVIEW_OBSERVED_THRESHOLDS = {
    "stroke_width_stability": 0.5,
    "line_curve_smoothness": 0.5,
    "classifier_prior_agreement": 0.75,
}
EDITABILITY_REVIEW_MAX_COMPONENT_REGRESSION = 0.05
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
    baseline_snapshot: str | Path | None = None,
    markdown: str | Path | None = None,
    config_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate a curated suite and optionally run bounded vectorization."""

    suite_file = Path(suite_path)
    suite = load_curated_suite(suite_file)
    suite_output_dir = Path(output_dir) if output_dir is not None else None
    overrides = _vectorize_config(config_overrides or {})
    baseline_cases = _baseline_snapshot_cases(baseline_snapshot)
    cases = [
        _check_curated_case(
            case,
            output_dir=suite_output_dir,
            run=run,
            config_overrides=overrides,
            baseline_case=baseline_cases.get(str(case.get("id"))),
            baseline_configured=baseline_snapshot is not None,
        )
        for case in suite["cases"]
    ]
    corpus_audit = _curated_corpus_audit(
        suite["cases"],
        cases,
        contact_sheet_artifacts_required=run and suite_output_dir is not None,
    )
    quality_gate_audit = _curated_quality_gate_audit(suite["cases"], cases)
    promotion_pipeline_audit = _curated_promotion_pipeline_audit(
        suite["cases"],
        cases,
        export_artifacts_required=run and suite_output_dir is not None,
    )
    report = {
        "suite": str(suite_file),
        "version": suite["version"],
        "run": run,
        "case_count": len(cases),
        "ok": all(case["ok"] for case in cases),
        "family_summary": _curated_family_summary(cases),
        "corpus_audit": corpus_audit,
        "quality_gate_audit": quality_gate_audit,
        "promotion_pipeline_audit": promotion_pipeline_audit,
        "cases": cases,
    }
    if suite_output_dir is not None:
        report["artifacts"] = _write_review_packet_artifacts(
            suite_output_dir,
            report,
        )
    if overrides:
        report["config_overrides"] = _json_config(overrides)
    if baseline_snapshot is not None:
        report["baseline_snapshot"] = str(Path(baseline_snapshot))
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
    ]
    raw_next_commands = report.get("next_commands", [])
    if not isinstance(raw_next_commands, list):
        raw_next_commands = []
    next_commands = [
        command
        for command in raw_next_commands
        if isinstance(command, str) and command
    ]
    if next_commands:
        lines.extend(["", "## Next Commands", ""])
        for index, command in enumerate(next_commands):
            if index:
                lines.append("")
            lines.extend(["```sh", command, "```"])
    lines.extend(
        [
            "",
            "## Families",
            "",
            "| Family | Cases | Checked | Passed | Failed | Missing |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    family_summary = report.get("family_summary")
    if not isinstance(family_summary, dict):
        family_summary = _curated_family_summary(
            [case for case in cases if isinstance(case, dict)]
        )
    for family, summary in sorted(family_summary.items()):
        if isinstance(summary, dict):
            lines.append(
                "| "
                f"`{family}` | "
                f"{_fmt_markdown_value(summary.get('case_count'))} | "
                f"{_fmt_markdown_value(summary.get('checked_count'))} | "
                f"{_fmt_markdown_value(summary.get('passed_count'))} | "
                f"{_fmt_markdown_value(summary.get('failed_count'))} | "
                f"{_fmt_markdown_value(summary.get('missing_source_count'))} |"
            )
    lines.extend(
        [
            "",
            "## RIP1 Corpus Audit",
            "",
        ]
    )
    audit = report.get("corpus_audit")
    if isinstance(audit, dict):
        summary = audit.get("summary", {})
        summary = summary if isinstance(summary, dict) else {}
        audit_status = "pass" if audit.get("ok", False) else "fail"
        lines.extend(
            [
                f"- Status: `{audit_status}`",
                f"- Cases: {_fmt_markdown_value(audit.get('case_count'))}",
                f"- Ready cases: {_fmt_markdown_value(summary.get('ready_case_count'))}",
                f"- Incomplete cases: {_fmt_markdown_value(summary.get('incomplete_case_count'))}",
                "",
                "| Case | Ready | Missing |",
                "| --- | --- | --- |",
            ]
        )
        audit_cases = audit.get("cases", [])
        if isinstance(audit_cases, list):
            for item in audit_cases:
                if not isinstance(item, dict):
                    continue
                lines.append(
                    "| "
                    f"`{item.get('id', 'n/a')}` | "
                    f"`{str(item.get('ok', False)).lower()}` | "
                    f"{_fmt_markdown_list(item.get('missing'))} |"
                )
    else:
        lines.extend(
            [
                "- Status: `not_available`",
                "",
            ]
        )
    lines.extend(
        [
            "",
            "## RIP2 Quality Gate Audit",
            "",
        ]
    )
    gate_audit = report.get("quality_gate_audit")
    if isinstance(gate_audit, dict):
        summary = gate_audit.get("summary", {})
        summary = summary if isinstance(summary, dict) else {}
        gate_status = "pass" if gate_audit.get("ok", False) else "fail"
        lines.extend(
            [
                f"- Status: `{gate_status}`",
                f"- Covered checks: {_fmt_markdown_value(summary.get('covered_check_count'))} / {_fmt_markdown_value(summary.get('required_check_count'))}",
                f"- Missing checks: {_fmt_markdown_list(summary.get('missing_checks'))}",
                "",
                "| Check | Covered |",
                "| --- | --- |",
            ]
        )
        checks = gate_audit.get("checks", {})
        if isinstance(checks, dict):
            for name, covered in sorted(checks.items()):
                lines.append(f"| `{name}` | `{str(bool(covered)).lower()}` |")
        lines.extend(
            [
                "",
                "| Case | Ready | Missing |",
                "| --- | --- | --- |",
            ]
        )
        audit_cases = gate_audit.get("cases", [])
        if isinstance(audit_cases, list):
            for item in audit_cases:
                if not isinstance(item, dict):
                    continue
                lines.append(
                    "| "
                    f"`{item.get('id', 'n/a')}` | "
                    f"`{str(item.get('ok', False)).lower()}` | "
                    f"{_fmt_markdown_list(item.get('missing'))} |"
                )
    else:
        lines.extend(["- Status: `not_available`", ""])
    lines.extend(
        [
            "",
            "## RIP3 Promotion Pipeline Audit",
            "",
        ]
    )
    pipeline_audit = report.get("promotion_pipeline_audit")
    if isinstance(pipeline_audit, dict):
        summary = pipeline_audit.get("summary", {})
        summary = summary if isinstance(summary, dict) else {}
        pipeline_status = "pass" if pipeline_audit.get("ok", False) else "fail"
        lines.extend(
            [
                f"- Status: `{pipeline_status}`",
                f"- Covered checks: {_fmt_markdown_value(summary.get('covered_check_count'))} / {_fmt_markdown_value(summary.get('required_check_count'))}",
                f"- Missing checks: {_fmt_markdown_list(summary.get('missing_checks'))}",
                f"- Promotion cases: {_fmt_markdown_value(summary.get('promotion_case_count'))}",
                "",
                "| Check | Covered |",
                "| --- | --- |",
            ]
        )
        checks = pipeline_audit.get("checks", {})
        if isinstance(checks, dict):
            for name, covered in sorted(checks.items()):
                lines.append(f"| `{name}` | `{str(bool(covered)).lower()}` |")
        lines.extend(
            [
                "",
                "| Case | Ready | Decision | Regions | Missing |",
                "| --- | --- | --- | ---: | --- |",
            ]
        )
        audit_cases = pipeline_audit.get("cases", [])
        if isinstance(audit_cases, list):
            for item in audit_cases:
                if not isinstance(item, dict):
                    continue
                lines.append(
                    "| "
                    f"`{item.get('id', 'n/a')}` | "
                    f"`{str(item.get('ok', False)).lower()}` | "
                    f"`{item.get('decision', 'n/a')}` | "
                    f"{_fmt_markdown_value(item.get('region_count'))} | "
                    f"{_fmt_markdown_list(item.get('missing'))} |"
                )
    else:
        lines.extend(["- Status: `not_available`", ""])
    lines.extend(
        [
            "",
            "## Corpus Ledger",
            "",
            "| Case | Quality | Pipeline | Current status | Stress family | Expected families | Issues | Licensing |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for case in _promotion_sorted_cases(cases):
        if not isinstance(case, dict):
            continue
        promotion = case.get("promotion", {})
        promotion = promotion if isinstance(promotion, dict) else {}
        lines.append(
            "| "
            f"`{case.get('id', 'n/a')}` | "
            f"{_fmt_promotion_quality(promotion)} | "
            f"{_fmt_pipeline_quality(case)} | "
            f"`{promotion.get('current_status', 'n/a')}` | "
            f"`{promotion.get('stress_family', 'n/a')}` | "
            f"{_fmt_markdown_list(promotion.get('expected_promotion_families'))} | "
            f"{_fmt_markdown_list(promotion.get('current_issues'))} | "
            f"`{promotion.get('licensing_status', 'n/a')}` |"
        )
    lines.extend(
        [
            "",
            "## Promotion Gates",
            "",
            "| Case | Decision | Quality | Failed gates |",
            "| --- | --- | --- | --- |",
        ]
    )
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
    gate_detail_rows = _promotion_gate_detail_rows(cases)
    if gate_detail_rows:
        lines.extend(
            [
                "",
                "## Promotion Gate Details",
                "",
                "| Case | Gate | Type | Severity | Reason |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        lines.extend(gate_detail_rows)
    region_rows = _region_truth_rows(cases)
    if region_rows:
        lines.extend(
            [
                "",
                "## Region Truth",
                "",
                "| Case | Region | State | Gate | Bounds | Expected | Actual | Layers | Topology | Visual |",
                "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
            ]
        )
        lines.extend(region_rows)
    lines.extend(
        [
            "",
            "## Editability Review",
            "",
            "| Case | Decision | Accepted | Regression | Failed components | Gate-blocked components |",
            "| --- | --- | ---: | --- | --- | --- |",
        ]
    )
    for case in _promotion_sorted_cases(cases):
        if not isinstance(case, dict):
            continue
        review = case.get("editability_review", {})
        review = review if isinstance(review, dict) else {}
        lines.append(
            "| "
            f"`{case.get('id', 'n/a')}` | "
            f"`{review.get('decision', 'n/a')}` | "
            f"`{str(review.get('accepted', False)).lower()}` | "
            f"`{review.get('regression_delta_status', 'n/a')}` | "
            f"{_fmt_failed_components(review.get('failed_components'))} | "
            f"{_fmt_gate_blocked_components(review.get('gate_blocked_components'))} |"
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
            lines.append(
                "- Source provenance: "
                f"`{promotion.get('source_provenance', 'n/a')}`"
            )
            lines.append(
                "- Expected promotion families: "
                f"{_fmt_markdown_list(promotion.get('expected_promotion_families'))}"
            )
            lines.append(
                "- Licensing: "
                f"`{promotion.get('licensing_status', 'n/a')}`"
            )
        if isinstance(case.get("promotion_summary"), dict):
            lines.append(
                "- Promotion gates: "
                f"decision=`{case['promotion_summary'].get('decision', 'n/a')}`, "
                f"failed={_fmt_failed_gates(case.get('promotion_gates'))}"
            )
        if isinstance(case.get("promotion_regions"), list):
            lines.append(
                "- Promotion regions: "
                f"{_fmt_promotion_regions(case.get('promotion_regions'))}"
            )
        if isinstance(case.get("editability_review"), dict):
            review = case["editability_review"]
            lines.append(
                "- Editability review: "
                f"decision=`{review.get('decision', 'n/a')}`, "
                f"accepted=`{str(review.get('accepted', False)).lower()}`, "
                f"reasons={_fmt_markdown_list(review.get('reasons'))}"
            )
        if isinstance(case.get("review_decision"), dict):
            decision = case["review_decision"]
            lines.append(
                "- Review decision: "
                f"state=`{decision.get('decision', 'n/a')}`, "
                f"suggested=`{decision.get('suggested_decision', 'n/a')}`, "
                f"issues={_fmt_markdown_list(decision.get('issue_tags'))}"
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
                components = _fmt_editability_components(
                    metrics.get("editability_components")
                )
                if components != "n/a":
                    lines.append(f"- Editability components: {components}")
                v10_components = _fmt_editability_v10_components(
                    metrics.get("editability_v10_components")
                )
                if v10_components != "n/a":
                    lines.append(f"- Editability v10 components: {v10_components}")
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
        "corpus_audit": report.get("corpus_audit"),
        "quality_gate_audit": report.get("quality_gate_audit"),
        "promotion_pipeline_audit": report.get("promotion_pipeline_audit"),
        "cases": [
            _case_snapshot(case)
            for case in sorted(
                report.get("cases", []),
                key=lambda item: str(item.get("id", "")),
            )
        ],
    }


def _curated_family_summary(cases: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    summary: dict[str, dict[str, int]] = {}
    for case in cases:
        family = _curated_case_family(case)
        family_summary = summary.setdefault(
            family,
            {
                "case_count": 0,
                "checked_count": 0,
                "passed_count": 0,
                "failed_count": 0,
                "missing_source_count": 0,
            },
        )
        family_summary["case_count"] += 1
        if case.get("status") == "checked":
            family_summary["checked_count"] += 1
        if case.get("ok"):
            family_summary["passed_count"] += 1
        else:
            family_summary["failed_count"] += 1
        if case.get("status") == "missing_source":
            family_summary["missing_source_count"] += 1
    return dict(sorted(summary.items()))


def _curated_corpus_audit(
    suite_cases: list[dict[str, Any]],
    report_cases: list[dict[str, Any]],
    *,
    contact_sheet_artifacts_required: bool,
) -> dict[str, Any]:
    report_by_id = {
        str(case.get("id")): case
        for case in report_cases
        if isinstance(case, dict) and isinstance(case.get("id"), str)
    }
    audited_cases = [
        _curated_corpus_case_audit(
            case,
            report_by_id.get(str(case.get("id")), {}),
            contact_sheet_artifacts_required=contact_sheet_artifacts_required,
        )
        for case in suite_cases
        if isinstance(case, dict)
    ]
    ready_case_count = sum(1 for case in audited_cases if case["ok"])
    check_counts: dict[str, int] = {}
    for item in audited_cases:
        checks = item.get("checks", {})
        if not isinstance(checks, dict):
            continue
        for name, passed in checks.items():
            if passed:
                check_counts[name] = check_counts.get(name, 0) + 1
    return {
        "schema_version": 1,
        "ok": ready_case_count == len(audited_cases),
        "case_count": len(audited_cases),
        "summary": {
            "ready_case_count": ready_case_count,
            "incomplete_case_count": len(audited_cases) - ready_case_count,
            "check_pass_counts": dict(sorted(check_counts.items())),
        },
        "cases": audited_cases,
    }


def _curated_corpus_case_audit(
    suite_case: dict[str, Any],
    report_case: dict[str, Any],
    *,
    contact_sheet_artifacts_required: bool,
) -> dict[str, Any]:
    case_id = str(suite_case.get("id", "n/a"))
    promotion = suite_case.get("promotion", {})
    promotion = promotion if isinstance(promotion, dict) else {}
    label = promotion.get("current_quality_label")
    checks = {
        "source_reference": _non_empty_string(suite_case.get("source")),
        "source_status_visible": report_case.get("status")
        in {"not_run", "checked", "missing_source"},
        "source_provenance": _non_empty_string(promotion.get("source_provenance")),
        "licensing_status": _non_empty_string(promotion.get("licensing_status")),
        "stress_family": _non_empty_string(promotion.get("stress_family")),
        "expected_promotion_families": _non_empty_string_list(
            promotion.get("expected_promotion_families")
        ),
        "recommended_bounded_config": _is_recommended_bounded_config(
            suite_case.get("recommended_config")
        ),
        "human_readable_intent": _non_empty_string_list(suite_case.get("notes")),
        "current_quality_label": label in PROMOTION_QUALITY_LABELS,
        "red_yellow_issue_tags": (
            label == "green" or _non_empty_string_list(promotion.get("current_issues"))
        ),
        "visual_audit_status": _non_empty_string(
            promotion.get("visual_audit_status")
        ),
        "contact_sheet_artifact": _corpus_contact_sheet_artifact_ok(
            report_case,
            required=contact_sheet_artifacts_required,
        ),
    }
    missing = [name for name, passed in checks.items() if not passed]
    return {
        "id": case_id,
        "ok": not missing,
        "missing": missing,
        "checks": checks,
        "source_exists": report_case.get("source_exists"),
        "status": report_case.get("status", "unknown"),
    }


def _is_recommended_bounded_config(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    return all(_positive_number(value.get(key)) for key in RIP1_BOUNDED_CONFIG_KEYS)


def _corpus_contact_sheet_artifact_ok(
    report_case: dict[str, Any],
    *,
    required: bool,
) -> bool:
    if not required or report_case.get("status") != "checked":
        return True
    artifacts = report_case.get("artifacts", {})
    return (
        isinstance(artifacts, dict)
        and isinstance(artifacts.get("contact_sheet"), str)
        and bool(artifacts["contact_sheet"])
    )


def _non_empty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value)


def _non_empty_string_list(value: object) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(item, str) and bool(item) for item in value)
    )


def _positive_number(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and value > 0
    )


def _curated_quality_gate_audit(
    suite_cases: list[dict[str, Any]],
    report_cases: list[dict[str, Any]],
) -> dict[str, Any]:
    report_by_id = {
        str(case.get("id")): case
        for case in report_cases
        if isinstance(case, dict) and isinstance(case.get("id"), str)
    }
    audited_cases = [
        _curated_quality_gate_case_audit(
            case,
            report_by_id.get(str(case.get("id")), {}),
        )
        for case in suite_cases
        if isinstance(case, dict)
    ]
    checks = {
        "case_gate_coverage": all(case["ok"] for case in audited_cases),
        "bounded_region_gates": any(
            _bool_case_check(case, "bounded_region_gates")
            for case in audited_cases
        ),
        "region_visual_fidelity_gates": any(
            _bool_case_check(case, "region_visual_fidelity_gates")
            for case in audited_cases
        ),
        "shape_class_gates": all(
            _bool_case_check(case, "shape_class_gates")
            for case in audited_cases
        ),
        "topology_gates": all(
            _bool_case_check(case, "topology_gates")
            for case in audited_cases
        ),
        "fragmentation_layer_gates": all(
            _bool_case_check(case, "fragmentation_layer_gates")
            for case in audited_cases
        ),
        "grouping_gates": all(
            _bool_case_check(case, "grouping_gates")
            for case in audited_cases
        ),
        "visual_fidelity_thresholds": all(
            _bool_case_check(case, "visual_fidelity_thresholds")
            for case in audited_cases
        ),
        "per_family_visual_thresholds": all(
            _bool_case_check(case, "per_family_visual_thresholds")
            for case in audited_cases
        ),
        "contact_sheet_gate_records": all(
            _bool_case_check(case, "contact_sheet_gate_record")
            for case in audited_cases
        ),
    }
    missing_checks = [name for name, covered in checks.items() if not covered]
    gate_type_counts: dict[str, int] = {}
    failed_gate_count = 0
    red_failed_gate_count = 0
    yellow_failed_gate_count = 0
    for case in report_cases:
        gates = case.get("promotion_gates") if isinstance(case, dict) else None
        if not isinstance(gates, list):
            continue
        for gate in gates:
            if not isinstance(gate, dict):
                continue
            gate_type = str(gate.get("gate_type", "unknown"))
            gate_type_counts[gate_type] = gate_type_counts.get(gate_type, 0) + 1
            if not gate.get("ok", False):
                failed_gate_count += 1
                if gate.get("severity") == "red":
                    red_failed_gate_count += 1
                elif gate.get("severity") == "yellow":
                    yellow_failed_gate_count += 1
    return {
        "schema_version": 1,
        "ok": not missing_checks,
        "checks": checks,
        "summary": {
            "required_check_count": len(checks),
            "covered_check_count": sum(1 for value in checks.values() if value),
            "missing_checks": missing_checks,
            "ready_case_count": sum(1 for case in audited_cases if case["ok"]),
            "incomplete_case_count": sum(
                1 for case in audited_cases if not case["ok"]
            ),
            "gate_type_counts": dict(sorted(gate_type_counts.items())),
            "failed_gate_count": failed_gate_count,
            "red_failed_gate_count": red_failed_gate_count,
            "yellow_failed_gate_count": yellow_failed_gate_count,
        },
        "cases": audited_cases,
    }


def _curated_quality_gate_case_audit(
    suite_case: dict[str, Any],
    report_case: dict[str, Any],
) -> dict[str, Any]:
    case_id = str(suite_case.get("id", "n/a"))
    promotion = suite_case.get("promotion", {})
    promotion = promotion if isinstance(promotion, dict) else {}
    checks = {
        "shape_class_gates": _promotion_has_gate_type(promotion, "shape_class"),
        "topology_gates": _promotion_has_gate_type(promotion, "topology"),
        "bounded_region_gates": _promotion_has_bounded_region_gate(promotion),
        "fragmentation_layer_gates": _promotion_has_structure_gate(promotion),
        "grouping_gates": _promotion_has_group_gate(promotion),
        "visual_fidelity_thresholds": _promotion_has_visual_threshold_gate(
            promotion
        ),
        "region_visual_fidelity_gates": _promotion_has_region_visual_gate(
            promotion
        ),
        "per_family_visual_thresholds": _promotion_has_per_family_visual_thresholds(
            promotion
        ),
        "promotion_gate_records": _case_has_promotion_gate_records(report_case),
        "contact_sheet_gate_record": _case_has_promotion_gate_id(
            report_case,
            "visual_contact_sheet",
        ),
    }
    optional_case_checks = {"region_visual_fidelity_gates"}
    missing = [
        name
        for name, passed in checks.items()
        if not passed and name not in optional_case_checks
    ]
    return {
        "id": case_id,
        "ok": not missing,
        "missing": missing,
        "checks": checks,
        "gate_type_counts": _case_gate_type_counts(report_case),
        "failed_gate_ids": _failed_gate_ids(report_case.get("promotion_gates")),
    }


def _bool_case_check(case: dict[str, Any], name: str) -> bool:
    checks = case.get("checks", {})
    return isinstance(checks, dict) and bool(checks.get(name, False))


def _promotion_has_gate_type(promotion: dict[str, Any], gate_type: str) -> bool:
    return any(
        isinstance(gate, dict) and gate.get("gate_type") == gate_type
        for gate in _promotion_metadata_gate_items(promotion)
    )


def _promotion_has_bounded_region_gate(promotion: dict[str, Any]) -> bool:
    for gate in _promotion_metadata_gate_list(promotion, "region_gates"):
        if (
            isinstance(gate, dict)
            and _parse_float_bounds(gate.get("bounds")) is not None
            and _non_empty_string_list(gate.get("expected_kinds"))
        ):
            return True
    return False


def _promotion_has_structure_gate(promotion: dict[str, Any]) -> bool:
    thresholds = promotion.get("structure_thresholds")
    if not isinstance(thresholds, dict):
        return False
    has_fragmentation = isinstance(
        thresholds.get("max_fragmentation_penalty"),
        (int, float),
    )
    has_layer_depth = any(
        isinstance(thresholds.get(key), int)
        for key in ("max_layer_count", "max_structural_layer_count")
    )
    return has_fragmentation and has_layer_depth


def _promotion_has_group_gate(promotion: dict[str, Any]) -> bool:
    return any(
        isinstance(gate, dict)
        and gate.get("gate_type") == "grouping"
        and _non_empty_string_list(gate.get("expected_group_kinds"))
        for gate in _promotion_metadata_gate_list(promotion, "group_gates")
    )


def _promotion_has_visual_threshold_gate(promotion: dict[str, Any]) -> bool:
    return _promotion_has_visual_thresholds(promotion.get("visual_thresholds")) or any(
        isinstance(gate, dict) and _promotion_has_visual_thresholds(gate)
        for gate in _promotion_metadata_gate_list(promotion, "region_gates")
    )


def _promotion_has_region_visual_gate(promotion: dict[str, Any]) -> bool:
    return any(
        isinstance(gate, dict)
        and gate.get("gate_type") == "visual_fidelity"
        and _parse_float_bounds(gate.get("bounds")) is not None
        and _promotion_has_visual_thresholds(gate)
        for gate in _promotion_metadata_gate_list(promotion, "region_gates")
    )


def _promotion_has_per_family_visual_thresholds(
    promotion: dict[str, Any],
) -> bool:
    thresholds = promotion.get("visual_thresholds")
    return (
        isinstance(thresholds, dict)
        and _non_empty_string(thresholds.get("family"))
        and _promotion_has_visual_thresholds(thresholds)
    )


def _promotion_has_visual_thresholds(value: object) -> bool:
    return isinstance(value, dict) and any(
        isinstance(value.get(key), (int, float))
        for key in PROMOTION_VISUAL_THRESHOLD_KEYS
    )


def _promotion_metadata_gate_items(
    promotion: dict[str, Any],
) -> list[dict[str, Any]]:
    gates: list[dict[str, Any]] = []
    for key in ("hard_gates", "region_gates", "group_gates"):
        gates.extend(_promotion_metadata_gate_list(promotion, key))
    return gates


def _promotion_metadata_gate_list(
    promotion: dict[str, Any],
    key: str,
) -> list[dict[str, Any]]:
    value = promotion.get(key)
    if not isinstance(value, list):
        return []
    return [gate for gate in value if isinstance(gate, dict)]


def _case_has_promotion_gate_records(report_case: dict[str, Any]) -> bool:
    gates = report_case.get("promotion_gates")
    return isinstance(gates, list) and bool(gates)


def _case_has_promotion_gate_id(
    report_case: dict[str, Any],
    gate_id: str,
) -> bool:
    gates = report_case.get("promotion_gates")
    return isinstance(gates, list) and any(
        isinstance(gate, dict) and gate.get("id") == gate_id
        for gate in gates
    )


def _case_gate_type_counts(report_case: dict[str, Any]) -> dict[str, int]:
    gates = report_case.get("promotion_gates")
    if not isinstance(gates, list):
        return {}
    return _counts(
        gate.get("gate_type", "unknown")
        for gate in gates
        if isinstance(gate, dict)
    )


def _curated_promotion_pipeline_audit(
    suite_cases: list[dict[str, Any]],
    report_cases: list[dict[str, Any]],
    *,
    export_artifacts_required: bool,
) -> dict[str, Any]:
    report_by_id = {
        str(case.get("id")): case
        for case in report_cases
        if isinstance(case, dict) and isinstance(case.get("id"), str)
    }
    audited_cases = [
        _curated_promotion_pipeline_case_audit(
            case,
            report_by_id.get(str(case.get("id")), {}),
            export_artifacts_required=export_artifacts_required,
        )
        for case in suite_cases
        if isinstance(case, dict) and isinstance(case.get("promotion"), dict)
    ]
    checks = {
        "case_pipeline_coverage": all(case["ok"] for case in audited_cases),
        "promotion_decision_records": all(
            _bool_case_check(case, "promotion_decision_record")
            for case in audited_cases
        ),
        "region_state_records": all(
            _bool_case_check(case, "region_state_records")
            for case in audited_cases
        ),
        "failed_gate_visibility": all(
            _bool_case_check(case, "failed_gate_visibility")
            for case in audited_cases
        ),
        "review_decision_records": all(
            _bool_case_check(case, "review_decision_record")
            for case in audited_cases
        ),
        "review_artifact_links": all(
            _bool_case_check(case, "review_artifact_links")
            for case in audited_cases
        ),
        "filtered_svg_artifacts": all(
            _bool_case_check(case, "filtered_svg_artifacts")
            for case in audited_cases
        ),
        "promotion_export_partitions": all(
            _bool_case_check(case, "promotion_export_partition")
            for case in audited_cases
        ),
        "manifest_region_annotations": all(
            _bool_case_check(case, "manifest_region_annotations")
            for case in audited_cases
        ),
    }
    missing_checks = [name for name, covered in checks.items() if not covered]
    return {
        "schema_version": 1,
        "ok": not missing_checks,
        "checks": checks,
        "summary": {
            "required_check_count": len(checks),
            "covered_check_count": sum(1 for value in checks.values() if value),
            "missing_checks": missing_checks,
            "promotion_case_count": len(audited_cases),
            "ready_case_count": sum(1 for case in audited_cases if case["ok"]),
            "incomplete_case_count": sum(
                1 for case in audited_cases if not case["ok"]
            ),
            "export_artifacts_required": export_artifacts_required,
            "decision_counts": _counts(
                case["decision"]
                for case in audited_cases
                if isinstance(case.get("decision"), str)
            ),
            "region_state_counts": _counts(
                state
                for case in audited_cases
                for state in case.get("region_states", [])
                if isinstance(state, str)
            ),
            "failed_gate_count": sum(
                len(case.get("failed_gate_ids", [])) for case in audited_cases
            ),
            "non_promoted_region_count": sum(
                1
                for case in audited_cases
                for state in case.get("region_states", [])
                if state != "promoted"
            ),
        },
        "cases": audited_cases,
    }


def _curated_promotion_pipeline_case_audit(
    suite_case: dict[str, Any],
    report_case: dict[str, Any],
    *,
    export_artifacts_required: bool,
) -> dict[str, Any]:
    case_id = str(suite_case.get("id", "n/a"))
    promotion = suite_case.get("promotion", {})
    promotion = promotion if isinstance(promotion, dict) else {}
    region_gate_ids = _promotion_region_gate_ids(promotion)
    artifact_required = (
        export_artifacts_required and report_case.get("status") == "checked"
    )
    summary = report_case.get("promotion_summary", {})
    summary = summary if isinstance(summary, dict) else {}
    decision = summary.get("decision")
    regions = _case_promotion_regions(report_case)
    checks = {
        "promotion_decision_record": decision in PROMOTION_PIPELINE_DECISIONS,
        "region_state_records": _case_has_pipeline_region_records(
            report_case,
            region_gate_ids,
        ),
        "failed_gate_visibility": _case_has_failed_gate_visibility(report_case),
        "review_decision_record": _case_has_review_decision_record(report_case),
        "review_artifact_links": _case_has_review_artifact_links(
            report_case,
            required=artifact_required,
        ),
        "filtered_svg_artifacts": _case_has_filtered_svg_artifacts(
            report_case,
            required=artifact_required,
        ),
        "promotion_export_partition": _case_has_promotion_export_partition(
            report_case,
            required=artifact_required,
        ),
        "manifest_region_annotations": _case_has_manifest_promotion_annotations(
            report_case,
            required=artifact_required,
        ),
    }
    missing = [name for name, passed in checks.items() if not passed]
    return {
        "id": case_id,
        "ok": not missing,
        "missing": missing,
        "checks": checks,
        "decision": decision if isinstance(decision, str) else "n/a",
        "status": report_case.get("status", "unknown"),
        "region_count": len(regions),
        "region_states": [
            str(region.get("state"))
            for region in regions
            if isinstance(region.get("state"), str)
        ],
        "region_gate_ids": region_gate_ids,
        "failed_gate_ids": _failed_gate_ids(report_case.get("promotion_gates")),
        "export_artifacts_required": artifact_required,
    }


def _promotion_region_gate_ids(promotion: dict[str, Any]) -> list[str]:
    return [
        str(gate["id"])
        for gate in _promotion_metadata_gate_list(promotion, "region_gates")
        if isinstance(gate.get("id"), str) and gate["id"]
    ]


def _case_promotion_regions(report_case: dict[str, Any]) -> list[dict[str, Any]]:
    regions = report_case.get("promotion_regions")
    if not isinstance(regions, list):
        return []
    return [region for region in regions if isinstance(region, dict)]


def _case_has_pipeline_region_records(
    report_case: dict[str, Any],
    region_gate_ids: list[str],
) -> bool:
    if not region_gate_ids:
        return True
    regions = _case_promotion_regions(report_case)
    if not regions:
        return False
    region_by_gate_id = {
        str(region.get("gate_id", region.get("id"))): region
        for region in regions
        if isinstance(region.get("gate_id", region.get("id")), str)
    }
    if any(gate_id not in region_by_gate_id for gate_id in region_gate_ids):
        return False
    for region in region_by_gate_id.values():
        if region.get("state") not in PROMOTION_PIPELINE_REGION_STATES:
            return False
        if not _non_empty_string(region.get("id")):
            return False
        if not _non_empty_string(region.get("gate_id")):
            return False
        if not _non_empty_string(region.get("gate_type")):
            return False
        if not isinstance(region.get("selected_anchor_indexes"), list):
            return False
        if not isinstance(region.get("selected_anchor_ids"), list):
            return False
    return True


def _case_has_failed_gate_visibility(report_case: dict[str, Any]) -> bool:
    gates = report_case.get("promotion_gates")
    summary = report_case.get("promotion_summary")
    review = report_case.get("review_decision")
    if not isinstance(gates, list) or not isinstance(summary, dict):
        return False
    if not isinstance(review, dict):
        return False
    failed_ids = _failed_gate_ids(gates)
    if summary.get("failed_gate_count") != len(failed_ids):
        return False
    review_failed_gates = review.get("failed_gates")
    if not isinstance(review_failed_gates, list):
        return False
    review_failed_ids = {
        str(gate.get("id"))
        for gate in review_failed_gates
        if isinstance(gate, dict) and isinstance(gate.get("id"), str)
    }
    return all(gate_id in review_failed_ids for gate_id in failed_ids)


def _case_has_review_decision_record(report_case: dict[str, Any]) -> bool:
    review = report_case.get("review_decision")
    if not isinstance(review, dict):
        return False
    decision = review.get("decision")
    suggested = review.get("suggested_decision")
    allowed = review.get("allowed_decisions")
    return (
        review.get("schema_version") == 1
        and decision in {"pending", *PROMOTION_REVIEW_DECISIONS}
        and suggested in PROMOTION_REVIEW_DECISIONS
        and isinstance(allowed, list)
        and set(PROMOTION_REVIEW_DECISIONS).issubset(set(allowed))
        and isinstance(review.get("failed_gates"), list)
    )


def _case_has_review_artifact_links(
    report_case: dict[str, Any],
    *,
    required: bool,
) -> bool:
    if not required:
        return True
    review = report_case.get("review_decision")
    if not isinstance(review, dict):
        return False
    artifacts = review.get("review_artifacts")
    if not isinstance(artifacts, dict):
        return False
    return all(
        _artifact_path_exists(artifacts, key)
        for key in PROMOTION_PIPELINE_REVIEW_ARTIFACTS
    )


def _case_has_filtered_svg_artifacts(
    report_case: dict[str, Any],
    *,
    required: bool,
) -> bool:
    if not required:
        return True
    artifacts = report_case.get("artifacts")
    if not isinstance(artifacts, dict):
        return False
    return all(
        _artifact_path_exists(artifacts, key)
        for key in PROMOTION_PIPELINE_EXPORT_ARTIFACTS
    )


def _case_has_promotion_export_partition(
    report_case: dict[str, Any],
    *,
    required: bool,
) -> bool:
    if not required:
        return True
    export = _case_artifact_json(report_case, "promotion_export")
    if not isinstance(export, dict):
        return False
    list_keys = (
        "promoted_anchor_indexes",
        "fallback_anchor_indexes",
        "fallback_only_anchor_indexes",
        "rejected_anchor_indexes",
        "deferred_anchor_indexes",
        "missing_from_promoted",
        "regions",
    )
    if any(not isinstance(export.get(key), list) for key in list_keys):
        return False
    if not isinstance(export.get("anchor_state_counts"), dict):
        return False
    if not isinstance(export.get("region_state_counts"), dict):
        return False
    if not isinstance(export.get("export_summary"), dict):
        return False
    if not _non_empty_string(export.get("promoted_svg")):
        return False
    if not _non_empty_string(export.get("fallback_svg")):
        return False
    non_promoted_indexes = (
        len(export["fallback_only_anchor_indexes"])
        + len(export["rejected_anchor_indexes"])
        + len(export["deferred_anchor_indexes"])
    )
    return non_promoted_indexes == 0 or bool(export["missing_from_promoted"])


def _case_has_manifest_promotion_annotations(
    report_case: dict[str, Any],
    *,
    required: bool,
) -> bool:
    if not required:
        return True
    manifest = _case_artifact_json(report_case, "manifest")
    if not isinstance(manifest, dict):
        return False
    promotion = manifest.get("promotion")
    if not isinstance(promotion, dict):
        return False
    manifest_regions = promotion.get("regions")
    if not isinstance(manifest_regions, list):
        return False
    manifest_region_ids = {
        str(region.get("id"))
        for region in manifest_regions
        if isinstance(region, dict) and isinstance(region.get("id"), str)
    }
    for region in _case_promotion_regions(report_case):
        region_id = region.get("id")
        if isinstance(region_id, str) and region_id not in manifest_region_ids:
            return False
    artifacts = promotion.get("artifacts")
    if not isinstance(artifacts, dict):
        return False
    if any(key not in artifacts for key in PROMOTION_PIPELINE_EXPORT_ARTIFACTS):
        return False
    anchors = manifest.get("anchors")
    if not isinstance(anchors, list):
        return False
    for anchor in anchors:
        if not isinstance(anchor, dict):
            return False
        if not _non_empty_string(anchor.get("promotion_state")):
            return False
        if not isinstance(anchor.get("promotion_regions"), list):
            return False
    return True


def _case_artifact_json(report_case: dict[str, Any], key: str) -> dict[str, Any] | None:
    artifacts = report_case.get("artifacts")
    if not isinstance(artifacts, dict):
        return None
    path = _artifact_path(artifacts, key)
    if path is None:
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _artifact_path_exists(artifacts: dict[str, Any], key: str) -> bool:
    path = _artifact_path(artifacts, key)
    return path is not None and path.exists()


def _artifact_path(artifacts: dict[str, Any], key: str) -> Path | None:
    value = artifacts.get(key)
    if not isinstance(value, str) or not value:
        return None
    return Path(value).expanduser()


def _curated_case_family(case: dict[str, Any]) -> str:
    promotion = case.get("promotion")
    if isinstance(promotion, dict):
        stress_family = promotion.get("stress_family")
        if isinstance(stress_family, str) and stress_family:
            return stress_family
    gates = case.get("promotion_gates")
    if isinstance(gates, list):
        for gate in gates:
            if not isinstance(gate, dict):
                continue
            evidence = gate.get("evidence")
            if not isinstance(evidence, dict):
                continue
            family = evidence.get("family")
            if isinstance(family, str) and family:
                return family
    return "unknown"


def _baseline_snapshot_cases(path: str | Path | None) -> dict[str, dict[str, Any]]:
    if path is None:
        return {}
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("baseline snapshot must be a JSON object")
    cases = data.get("cases", [])
    if not isinstance(cases, list):
        raise ValueError("baseline snapshot cases must be an array")
    return {
        str(case.get("id")): case
        for case in cases
        if isinstance(case, dict) and isinstance(case.get("id"), str)
    }


def _check_curated_case(
    case: dict[str, Any],
    *,
    output_dir: Path | None,
    run: bool,
    config_overrides: dict[str, Any] | None = None,
    baseline_case: dict[str, Any] | None = None,
    baseline_configured: bool = False,
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
                result["promotion_gates"],
                case_status=result.get("status"),
            )
            _attach_pipeline_quality_label(result)
            result["promotion_regions"] = _promotion_region_results(result)
            result["editability_review"] = _editability_review(
                result,
                baseline_case=baseline_case,
                baseline_configured=baseline_configured,
            )
            result["review_decision"] = _promotion_review_decision_record(result)
        return result
    if not run:
        if isinstance(result.get("promotion"), dict):
            result["promotion_gates"] = _promotion_gate_results(result)
            result["promotion_summary"] = _promotion_summary(
                result["promotion_gates"],
                case_status=result.get("status"),
            )
            _attach_pipeline_quality_label(result)
            result["promotion_regions"] = _promotion_region_results(result)
            result["editability_review"] = _editability_review(
                result,
                baseline_case=baseline_case,
                baseline_configured=baseline_configured,
            )
            result["review_decision"] = _promotion_review_decision_record(result)
        return result

    config = {
        **_vectorize_config(case.get("recommended_config", {})),
        **_vectorize_config(config_overrides or {}),
    }
    scene = scene_from_flat_color_image(source, **config)
    manifest = scene.to_manifest()
    expectation_results = _check_expectations(case.get("expectations", []), manifest)
    region_visuals: dict[str, object] | None = None
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
            "layer_count": len(manifest.get("layers", [])),
            "layer_anchor_counts": _layer_anchor_counts(manifest),
            "diagnostic_count": len(manifest["diagnostics"]),
            "metrics": dict(sorted(manifest.get("metrics", {}).items())),
            "expectations": expectation_results,
        }
    )
    if isinstance(result.get("promotion"), dict):
        region_visuals = _region_visual_context(
            source,
            scene.to_svg(
                SvgStyle(
                    cutout_strategy=str(config.get("cutout_export", "overlay_stroke"))
                )
            ),
            background=str(config.get("background", "#ffffff")),
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
        result["promotion_gates"] = _promotion_gate_results(
            result,
            manifest=manifest,
            region_visuals=region_visuals,
        )
        _apply_promotion_gate_editability_components(
            result.get("metrics"),
            result["promotion_gates"],
        )
        if isinstance(manifest, dict) and isinstance(result.get("metrics"), dict):
            manifest["metrics"] = result["metrics"]
        result["promotion_summary"] = _promotion_summary(
            result["promotion_gates"],
            case_status=result.get("status"),
        )
        _attach_pipeline_quality_label(result)
        result["promotion_regions"] = _promotion_region_results(
            result,
            manifest=manifest,
        )
        result["editability_review"] = _editability_review(
            result,
            baseline_case=baseline_case,
            baseline_configured=baseline_configured,
        )
        result["review_decision"] = _promotion_review_decision_record(result)
        if output_dir is not None and isinstance(result.get("artifacts"), dict):
            result["artifacts"].update(
                _write_promotion_export_artifacts(
                    vectorize_run.run_dir,
                    scene=scene,
                    manifest=manifest,
                    promotion_regions=result.get("promotion_regions"),
                    case_result=result,
                    cutout_strategy=str(config.get("cutout_export", "overlay_stroke")),
                )
            )
            _write_manifest_promotion_state(vectorize_run.manifest_path, result)
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
    elif "kinds" in expectation:
        kinds = tuple(str(kind) for kind in expectation["kinds"])
        kind_set = set(kinds)
        actual = sum(
            1
            for anchor in manifest.get("anchors", [])
            if anchor.get("kind") in kind_set
        )
        label = {"kinds": list(kinds)}
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
    kinds = expectation.get("kinds")
    if isinstance(kinds, list):
        return ("kinds", ",".join(str(kind) for kind in kinds))
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
        "layer_count",
        "layer_anchor_counts",
        "diagnostic_count",
        "metrics",
        "promotion",
        "pipeline_quality_label",
        "promotion_gates",
        "promotion_summary",
        "promotion_regions",
        "editability_review",
        "review_decision",
    ):
        if key in case:
            if key == "promotion_gates":
                snapshot[key] = _snapshot_promotion_gates(case[key])
            else:
                snapshot[key] = case[key]
    return snapshot


def _snapshot_promotion_gates(gates: object) -> object:
    if not isinstance(gates, list):
        return gates
    snapshot_gates: list[object] = []
    for gate in gates:
        if not isinstance(gate, dict):
            snapshot_gates.append(gate)
            continue
        snapshot_gate = dict(gate)
        gate_id = snapshot_gate.get("id")
        if gate_id == "source_available":
            snapshot_gate["evidence"] = {"source_exists": bool(gate.get("ok"))}
        elif gate_id == "visual_contact_sheet":
            snapshot_gate["evidence"] = {
                "contact_sheet_path_recorded": bool(gate.get("evidence"))
            }
        snapshot_gates.append(snapshot_gate)
    return snapshot_gates


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
    if "kind" in expectation:
        snapshot["kind"] = expectation.get("kind")
    if "kinds" in expectation:
        snapshot["kinds"] = expectation.get("kinds")
    if "group_kind" in expectation:
        snapshot["group_kind"] = expectation.get("group_kind")
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


def _layer_anchor_counts(manifest: dict[str, Any]) -> dict[str, int]:
    layers = manifest.get("layers", [])
    if not isinstance(layers, list):
        return {}
    counts: dict[str, int] = {}
    for layer in layers:
        if not isinstance(layer, dict):
            continue
        name = layer.get("name")
        count = layer.get("anchor_count")
        if isinstance(name, str) and isinstance(count, int):
            counts[name] = count
    return dict(sorted(counts.items()))


def _promotion_gate_results(
    case: dict[str, Any],
    *,
    manifest: dict[str, Any] | None = None,
    region_visuals: dict[str, object] | None = None,
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
    quality_policy = (
        promotion.get("quality_label_review_policy")
        if isinstance(promotion, dict)
        else None
    )
    quality_gate_severity = "red" if label == "red" else "yellow"
    quality_gate_reason = f"current quality label is {label or 'missing'}"
    quality_gate_evidence: object = label
    if label == "red" and quality_policy == "manual_review_pending":
        quality_gate_severity = "yellow"
        quality_gate_reason = "current quality label is red; manual review pending"
        quality_gate_evidence = {
            "current_quality_label": label,
            "review_policy": quality_policy,
        }
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
            severity=quality_gate_severity,
            reason=quality_gate_reason,
            evidence=quality_gate_evidence,
        ),
    ]
    if isinstance(promotion, dict):
        gates.extend(_configured_promotion_gates(case, promotion))
        gates.extend(
            _region_promotion_gates(
                case,
                promotion,
                manifest=manifest,
                region_visuals=region_visuals,
            )
        )
        gates.extend(_group_promotion_gates(case, promotion, manifest=manifest))
        structure_gate = _structure_threshold_promotion_gate(case, promotion)
        if structure_gate is not None:
            gates.append(structure_gate)
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
    region_visuals: dict[str, object] | None = None,
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
        required_topology_descriptors = [
            str(item)
            for item in gate.get("required_topology_descriptors", [])
            if isinstance(item, str)
        ]
        forbidden_topology_descriptors = [
            str(item)
            for item in gate.get("forbidden_topology_descriptors", [])
            if isinstance(item, str)
        ]
        min_anchor_coverage_value = gate.get("min_anchor_coverage")
        min_anchor_coverage = (
            float(min_anchor_coverage_value)
            if isinstance(min_anchor_coverage_value, (int, float))
            else None
        )
        default_min_iou = 0.0 if min_anchor_coverage is not None else 0.1
        min_iou = float(gate.get("min_iou", default_min_iou))
        min_count = int(gate.get("min_count", 1))
        max_count = gate.get("max_count")
        if bounds is None:
            selected: list[dict[str, object]] = []
        else:
            selected = _anchors_overlapping_region(
                anchors,
                bounds,
                min_iou,
                min_anchor_coverage=min_anchor_coverage,
            )
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
        visual_delta = _region_visual_delta(region_visuals, bounds)
        visual_thresholds = _region_visual_thresholds(gate)
        visual_failures = _region_visual_threshold_failures(
            visual_delta,
            visual_thresholds,
        )
        candidate_rejections = _region_gate_candidate_rejections(
            selected,
            expected_kinds=expected_kinds,
            forbidden_kinds=forbidden_kinds,
            topology_failures=topology_failures,
            region_bounds=bounds,
        )
        count_ok = len(matching) >= min_count
        if isinstance(max_count, int):
            count_ok = count_ok and len(matching) <= max_count
        ok = (
            checked
            and bounds is not None
            and count_ok
            and not forbidden
            and not topology_failures
            and not visual_failures
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
            visual_failures=visual_failures,
        )
        evidence: dict[str, object] = {
            "bounds": list(bounds) if bounds is not None else None,
            "min_iou": min_iou,
            "min_anchor_coverage": min_anchor_coverage,
            "expected_kinds": expected_kinds,
            "forbidden_kinds": forbidden_kinds,
            "required_topology_descriptors": required_topology_descriptors,
            "forbidden_topology_descriptors": forbidden_topology_descriptors,
            "matching_count": len(matching),
            "selected_count": len(selected),
            "forbidden_count": len(forbidden),
            "topology_summary": topology_summary,
            "topology_failures": topology_failures,
            "candidate_rejections": candidate_rejections,
            "selected_anchors": _region_gate_anchor_evidence(
                selected,
                region_bounds=bounds,
            ),
            "description": gate.get("description"),
        }
        if visual_delta is not None:
            evidence["visual_delta"] = visual_delta
        if visual_thresholds:
            evidence["visual_thresholds"] = visual_thresholds
            evidence["visual_failures"] = visual_failures
        gates.append(
            _promotion_gate(
                str(gate.get("id", "region_gate")),
                gate_type=str(gate.get("gate_type", "shape_class")),
                ok=ok,
                severity=str(gate.get("severity", "red")),
                reason=reason,
                evidence=evidence,
            )
        )
    return gates


def _region_visual_context(
    source_path: Path,
    svg_text: str,
    *,
    background: str,
) -> dict[str, object]:
    with Image.open(source_path) as source_image:
        source = _flatten_visual_audit_source(
            source_image.convert("RGBA"),
            background,
        )
    rendered = rasterized_svg_image(svg_text, background=background).convert("RGBA")
    return {
        "source": source,
        "rendered": rendered,
        "background": background,
    }


def _region_visual_delta(
    region_visuals: dict[str, object] | None,
    bounds: tuple[float, float, float, float] | None,
) -> dict[str, object] | None:
    if bounds is None or not isinstance(region_visuals, dict):
        return None
    source = region_visuals.get("source")
    rendered = region_visuals.get("rendered")
    if not isinstance(source, Image.Image) or not isinstance(rendered, Image.Image):
        return None
    if rendered.size != source.size:
        rendered = rendered.resize(source.size, Image.Resampling.NEAREST)
    crop_box = _region_visual_crop_box(bounds, source.size)
    if crop_box is None:
        return None
    source_crop = source.crop(crop_box)
    rendered_crop = rendered.crop(crop_box)
    metrics = raster_fidelity_metrics(source=source_crop, rendered=rendered_crop)
    return {
        "bounds": list(crop_box),
        "width": crop_box[2] - crop_box[0],
        "height": crop_box[3] - crop_box[1],
        "raster_l1_error": metrics["raster_l1_error"],
        "raster_edge_error": metrics["raster_edge_error"],
        "raster_alpha_error": metrics["raster_alpha_error"],
        "raster_size_match": metrics["raster_size_match"],
    }


def _region_visual_crop_box(
    bounds: tuple[float, float, float, float],
    size: tuple[int, int],
) -> tuple[int, int, int, int] | None:
    width, height = size
    left = max(0, min(width, floor(bounds[0])))
    top = max(0, min(height, floor(bounds[1])))
    right = max(0, min(width, ceil(bounds[2])))
    bottom = max(0, min(height, ceil(bounds[3])))
    if right <= left or bottom <= top:
        return None
    return (left, top, right, bottom)


def _region_visual_thresholds(gate: dict[str, Any]) -> dict[str, float]:
    thresholds: dict[str, float] = {}
    for key in sorted(PROMOTION_REGION_VISUAL_THRESHOLD_KEYS):
        value = gate.get(key)
        if isinstance(value, (int, float)):
            thresholds[key] = float(value)
    return thresholds


def _region_visual_threshold_failures(
    visual_delta: object,
    thresholds: dict[str, float],
) -> list[str]:
    if not thresholds:
        return []
    if not isinstance(visual_delta, dict):
        return ["visual_delta missing"]
    failures: list[str] = []
    for key, limit in sorted(thresholds.items()):
        metric_name = key.removeprefix("max_")
        actual = visual_delta.get(metric_name)
        if not isinstance(actual, (int, float)):
            failures.append(f"{metric_name} missing")
        elif float(actual) > limit:
            failures.append(f"{metric_name} {float(actual):.6g} > {limit:.6g}")
    return failures


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


def _structure_threshold_promotion_gate(
    case: dict[str, Any],
    promotion: dict[str, Any],
) -> dict[str, object] | None:
    thresholds = promotion.get("structure_thresholds")
    if not isinstance(thresholds, dict):
        return None
    checked = case.get("status") == "checked"
    metrics = case.get("metrics", {})
    metrics = metrics if isinstance(metrics, dict) else {}
    failures: list[str] = []
    actuals: dict[str, float | int | None] = {}
    limits: dict[str, float | int] = {}

    max_fragmentation = thresholds.get("max_fragmentation_penalty")
    if isinstance(max_fragmentation, (int, float)):
        actual = metrics.get("fragmentation_penalty")
        actuals["fragmentation_penalty"] = (
            float(actual) if isinstance(actual, (int, float)) else None
        )
        limits["max_fragmentation_penalty"] = float(max_fragmentation)
        if not isinstance(actual, (int, float)):
            failures.append("fragmentation_penalty missing")
        elif float(actual) > float(max_fragmentation):
            failures.append(
                "fragmentation_penalty "
                f"{float(actual):.6g} > {float(max_fragmentation):.6g}"
            )

    max_layer_count = thresholds.get("max_layer_count")
    if isinstance(max_layer_count, int):
        actual_layer_count = case.get("layer_count")
        actuals["layer_count"] = (
            int(actual_layer_count) if isinstance(actual_layer_count, int) else None
        )
        limits["max_layer_count"] = max_layer_count
        if not isinstance(actual_layer_count, int):
            failures.append("layer_count missing")
        elif actual_layer_count > max_layer_count:
            failures.append(f"layer_count {actual_layer_count} > {max_layer_count}")

    max_structural_layer_count = thresholds.get("max_structural_layer_count")
    non_structural_layer_roles = _non_structural_layer_roles(thresholds)
    if isinstance(max_structural_layer_count, int):
        actual_layer_count = case.get("layer_count")
        structural_layer_count = (
            _structural_layer_count(
                actual_layer_count,
                case.get("layer_anchor_counts"),
                non_structural_layer_roles,
            )
            if isinstance(actual_layer_count, int)
            else None
        )
        actuals["structural_layer_count"] = structural_layer_count
        limits["max_structural_layer_count"] = max_structural_layer_count
        if not isinstance(actual_layer_count, int):
            failures.append("structural_layer_count missing")
        elif (
            isinstance(structural_layer_count, int)
            and structural_layer_count > max_structural_layer_count
        ):
            failures.append(
                "structural_layer_count "
                f"{structural_layer_count} > {max_structural_layer_count}"
            )

    ok = checked and not failures and bool(limits)
    if not checked:
        reason = f"case status is {case.get('status', 'unknown')}"
    elif not limits:
        reason = "no structure thresholds configured"
    elif failures:
        reason = "structure thresholds failed: " + ", ".join(failures)
    else:
        reason = "structure thresholds passed"
    return _promotion_gate(
        "fragmentation_layer_thresholds",
        gate_type="fragmentation",
        ok=ok,
        severity=str(thresholds.get("severity", "red")),
        reason=reason,
        evidence={
            "actual": actuals,
            "thresholds": limits,
            "layer_anchor_counts": case.get("layer_anchor_counts", {}),
            "non_structural_layer_roles": list(non_structural_layer_roles),
            "failures": failures,
            "description": thresholds.get("description"),
        },
    )


def _non_structural_layer_roles(thresholds: dict[str, Any]) -> tuple[str, ...]:
    roles = thresholds.get("non_structural_layer_roles")
    if not isinstance(roles, list):
        return ()
    return tuple(str(role) for role in roles)


def _structural_layer_count(
    layer_count: int,
    layer_anchor_counts: object,
    non_structural_layer_roles: tuple[str, ...],
) -> int:
    if not isinstance(layer_anchor_counts, dict):
        return layer_count
    present_roles = {
        str(role)
        for role, count in layer_anchor_counts.items()
        if isinstance(count, int) and count > 0
    }
    if not present_roles:
        return layer_count
    structural_roles = present_roles - set(non_structural_layer_roles)
    return len(structural_roles)


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
    *,
    min_anchor_coverage: float | None = None,
) -> list[dict[str, object]]:
    selected: list[dict[str, object]] = []
    for anchor in anchors:
        anchor_bounds = _manifest_anchor_bounds(anchor)
        if anchor_bounds is None:
            continue
        if min_anchor_coverage is None:
            if _bounds_iou(anchor_bounds, region_bounds) < min_iou:
                continue
        elif (
            _bounds_iou(anchor_bounds, region_bounds) < min_iou
            or _bounds_coverage(anchor_bounds, region_bounds) < min_anchor_coverage
        ):
            continue
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
    visual_failures: list[str],
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
    if visual_failures:
        return "region visual thresholds failed: " + ", ".join(visual_failures)
    return f"matching anchors in region: {matching_count}"


def _region_gate_candidate_rejections(
    anchors: list[dict[str, object]],
    *,
    expected_kinds: list[str],
    forbidden_kinds: list[str],
    topology_failures: list[str],
    region_bounds: tuple[float, float, float, float] | None = None,
) -> list[dict[str, object]]:
    rejections: list[dict[str, object]] = []
    for anchor in anchors[:12]:
        kind = str(anchor.get("kind", "unknown"))
        reasons = []
        if expected_kinds and kind not in expected_kinds:
            reasons.append("kind_mismatch")
        if kind in forbidden_kinds:
            reasons.append("forbidden_kind")
        if topology_failures:
            reasons.append("topology_failure")
        if not reasons:
            continue
        item = _region_gate_anchor_evidence(
            [anchor],
            region_bounds=region_bounds,
        )[0]
        item["reasons"] = reasons
        item["topology_failures"] = list(topology_failures)
        rejections.append(item)
    return rejections


def _region_gate_anchor_evidence(
    anchors: list[dict[str, object]],
    *,
    region_bounds: tuple[float, float, float, float] | None = None,
) -> list[dict[str, object]]:
    evidence: list[dict[str, object]] = []
    for anchor in anchors[:12]:
        bounds = _manifest_anchor_bounds(anchor)
        item = {
            "id": anchor.get("id"),
            "kind": anchor.get("kind"),
            "bounds": list(bounds) if bounds is not None else None,
            "closed": _anchor_closed(anchor),
            "hole_count": _anchor_hole_count(anchor),
            "cutout": _anchor_has_cutout(anchor),
            "nested_contour_count": _anchor_nested_contour_count(anchor),
        }
        if bounds is not None and region_bounds is not None:
            item["region_iou"] = round(_bounds_iou(bounds, region_bounds), 6)
            item["anchor_coverage"] = round(
                _bounds_coverage(bounds, region_bounds),
                6,
            )
        evidence.append(item)
    return evidence


def _region_topology_summary(
    anchors: list[dict[str, object]],
) -> dict[str, object]:
    kind_counts = _counts(anchor.get("kind") for anchor in anchors)
    closed_count = sum(1 for anchor in anchors if _anchor_closed(anchor))
    open_count = len(anchors) - closed_count
    hole_count = sum(_anchor_hole_count(anchor) for anchor in anchors)
    cutout_count = sum(1 for anchor in anchors if _anchor_has_cutout(anchor))
    nested_contour_count = sum(
        _anchor_nested_contour_count(anchor) for anchor in anchors
    )
    summary = {
        "selected_anchor_count": len(anchors),
        "disconnected_component_count": len(anchors),
        "kind_counts": kind_counts,
        "closed_anchor_count": closed_count,
        "open_anchor_count": open_count,
        "hole_count": hole_count,
        "cutout_count": cutout_count,
        "nested_contour_count": nested_contour_count,
    }
    summary["topology_descriptors"] = _region_topology_descriptors(summary)
    return summary


def _region_topology_descriptors(summary: dict[str, object]) -> list[str]:
    selected = summary.get("selected_anchor_count")
    closed = summary.get("closed_anchor_count")
    open_anchors = summary.get("open_anchor_count")
    components = summary.get("disconnected_component_count")
    holes = summary.get("hole_count")
    cutouts = summary.get("cutout_count")
    nested = summary.get("nested_contour_count")
    descriptors: list[str] = []
    if selected == 0:
        descriptors.append("empty")
    elif closed == selected:
        descriptors.append("closed")
    elif open_anchors == selected:
        descriptors.append("open")
    else:
        descriptors.append("mixed_open_closed")
    if isinstance(components, int) and components > 1:
        descriptors.append("multi_component")
    elif isinstance(components, int) and components == 1:
        descriptors.append("single_component")
    if isinstance(holes, int) and holes > 0:
        descriptors.append("holes")
    if isinstance(cutouts, int) and cutouts > 0:
        descriptors.append("cutouts")
    if isinstance(nested, int) and nested > 0:
        descriptors.append("nested_contours")
    return descriptors


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
        ("min_nested_contours", "nested_contour_count", ">="),
        ("max_nested_contours", "nested_contour_count", "<="),
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
    descriptors = summary.get("topology_descriptors")
    descriptor_set = set(descriptors) if isinstance(descriptors, list) else set()
    required = gate.get("required_topology_descriptors")
    if isinstance(required, list):
        for descriptor in required:
            if isinstance(descriptor, str) and descriptor not in descriptor_set:
                failures.append(f"missing topology descriptor: {descriptor}")
    forbidden = gate.get("forbidden_topology_descriptors")
    if isinstance(forbidden, list):
        for descriptor in forbidden:
            if isinstance(descriptor, str) and descriptor in descriptor_set:
                failures.append(f"forbidden topology descriptor: {descriptor}")
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


def _anchor_nested_contour_count(anchor: dict[str, object]) -> int:
    return _anchor_hole_count(anchor) + (1 if _anchor_has_cutout(anchor) else 0)


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


def _bounds_coverage(
    subject: tuple[float, float, float, float],
    region: tuple[float, float, float, float],
) -> float:
    subject_area = _bounds_area(subject)
    if subject_area <= 0:
        return 0.0
    return _bounds_intersection_area(subject, region) / subject_area


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


def _promotion_summary(
    gates: list[dict[str, object]],
    *,
    case_status: object = None,
) -> dict[str, object]:
    failed = [gate for gate in gates if not gate.get("ok", False)]
    has_red = any(gate.get("severity") == "red" for gate in failed)
    has_yellow = any(gate.get("severity") == "yellow" for gate in failed)
    deferred_reason = None
    if case_status == "missing_source":
        decision = "deferred"
        deferred_reason = "missing_source"
    elif has_red:
        decision = "rejected"
    elif has_yellow:
        decision = "deferred"
    else:
        decision = "promoted"
    result = {
        "decision": decision,
        "failed_gate_count": len(failed),
        "red_gate_count": sum(1 for gate in failed if gate.get("severity") == "red"),
        "yellow_gate_count": sum(
            1 for gate in failed if gate.get("severity") == "yellow"
        ),
    }
    if deferred_reason is not None:
        result["deferred_reason"] = deferred_reason
    return result


def _apply_promotion_gate_editability_components(
    metrics: object,
    promotion_gates: object,
) -> None:
    if not isinstance(metrics, dict) or not isinstance(promotion_gates, list):
        return
    components = metrics.get("editability_v10_components")
    if not isinstance(components, dict):
        return
    gate_mapping = {
        "shape_class": "shape_identity_confidence",
        "topology": "topology_consistency",
        "grouping": "grouping_quality",
        "fragmentation": "fragmentation",
        "visual_fidelity": "raster_fidelity",
        "provenance": "provenance_confidence",
    }
    failed_by_component: dict[str, list[str]] = {}
    for gate in promotion_gates:
        if not isinstance(gate, dict) or gate.get("ok", False):
            continue
        if gate.get("severity") != "red":
            continue
        component = gate_mapping.get(str(gate.get("gate_type", "")))
        if component is None:
            continue
        failed_by_component.setdefault(component, []).append(str(gate.get("id")))
    for component_id, failed_gates in failed_by_component.items():
        component = components.get(component_id)
        if not isinstance(component, dict):
            component = {}
            components[component_id] = component
        score = component.get("score")
        if isinstance(score, (int, float)):
            component["uncapped_score"] = round(float(score), 6)
        component["score"] = 0.0
        component["gate_blocked"] = True
        component["failed_gates"] = sorted(failed_gates)


def _editability_review(
    case: dict[str, Any],
    *,
    baseline_case: dict[str, Any] | None = None,
    baseline_configured: bool = False,
) -> dict[str, object]:
    summary = case.get("promotion_summary", {})
    summary = summary if isinstance(summary, dict) else {}
    promotion_decision = str(summary.get("decision", "n/a"))
    metrics = case.get("metrics", {})
    metrics = metrics if isinstance(metrics, dict) else {}
    components = metrics.get("editability_v10_components")
    components = components if isinstance(components, dict) else {}

    failed_components: list[dict[str, object]] = []
    gate_blocked: list[dict[str, object]] = []
    component_scores: dict[str, object] = {}
    reasons: list[str] = []
    if promotion_decision != "promoted":
        reasons.append(f"promotion_decision_{promotion_decision}")
    if not components:
        reasons.append("missing_editability_v10_components")

    for component_id, threshold in EDITABILITY_REVIEW_THRESHOLDS.items():
        component = components.get(component_id)
        score = _component_score(component)
        component_scores[component_id] = score
        if isinstance(component, dict) and component.get("gate_blocked", False):
            gate_blocked.append(
                {
                    "id": component_id,
                    "failed_gates": list(component.get("failed_gates", [])),
                    "uncapped_score": component.get("uncapped_score"),
                }
            )
        if not isinstance(score, (int, float)):
            failed_components.append(
                {
                    "id": component_id,
                    "score": None,
                    "threshold": threshold,
                    "reason": "missing_score",
                }
            )
        elif float(score) < threshold:
            failed_components.append(
                {
                    "id": component_id,
                    "score": round(float(score), 6),
                    "threshold": threshold,
                    "reason": "below_threshold",
                }
            )

    for component_id, threshold in EDITABILITY_REVIEW_OBSERVED_THRESHOLDS.items():
        component = components.get(component_id)
        if not isinstance(component, dict) or component.get("observed") is not True:
            continue
        score = _component_score(component)
        component_scores[component_id] = score
        if isinstance(score, (int, float)) and float(score) < threshold:
            failed_components.append(
                {
                    "id": component_id,
                    "score": round(float(score), 6),
                    "threshold": threshold,
                    "reason": "observed_below_threshold",
                }
            )

    if gate_blocked:
        reasons.append("gate_blocked_components")
    if failed_components:
        reasons.append("component_threshold_failures")

    regression = _editability_regression_deltas(
        component_scores,
        baseline_case=baseline_case,
        baseline_configured=baseline_configured,
    )
    if regression["status"] not in {"not_configured", "passed"}:
        reasons.append(f"regression_delta_{regression['status']}")

    if (
        promotion_decision == "promoted"
        and not failed_components
        and not gate_blocked
        and regression["status"] in {"not_configured", "passed"}
    ):
        decision = "accepted"
    elif promotion_decision == "deferred":
        decision = "manual_review"
    else:
        decision = "rejected"
    if (
        promotion_decision == "promoted"
        and (
            failed_components
            or gate_blocked
            or regression["status"] not in {"not_configured", "passed"}
        )
    ):
        decision = "manual_review"

    return {
        "decision": decision,
        "accepted": decision == "accepted",
        "promotion_decision": promotion_decision,
        "thresholds": {
            "required": dict(sorted(EDITABILITY_REVIEW_THRESHOLDS.items())),
            "observed": dict(sorted(EDITABILITY_REVIEW_OBSERVED_THRESHOLDS.items())),
        },
        "component_scores": dict(sorted(component_scores.items())),
        "failed_components": failed_components,
        "gate_blocked_components": gate_blocked,
        "regression_delta_status": regression["status"],
        "regression_deltas": regression["deltas"],
        "regressed_components": regression["regressed_components"],
        "reasons": sorted(set(reasons)),
    }


def _editability_regression_deltas(
    component_scores: dict[str, object],
    *,
    baseline_case: dict[str, Any] | None,
    baseline_configured: bool,
) -> dict[str, object]:
    if not baseline_configured:
        return {"status": "not_configured", "deltas": [], "regressed_components": []}
    if baseline_case is None:
        return {
            "status": "missing_baseline_case",
            "deltas": [],
            "regressed_components": [],
        }
    baseline_scores = _baseline_component_scores(baseline_case)
    if not baseline_scores:
        return {
            "status": "missing_baseline_scores",
            "deltas": [],
            "regressed_components": [],
        }
    deltas: list[dict[str, object]] = []
    regressed: list[dict[str, object]] = []
    for component_id, current_score in sorted(component_scores.items()):
        baseline_score = baseline_scores.get(component_id)
        if not isinstance(current_score, (int, float)) or not isinstance(
            baseline_score,
            (int, float),
        ):
            continue
        delta = round(float(current_score) - float(baseline_score), 6)
        item = {
            "id": component_id,
            "current": round(float(current_score), 6),
            "baseline": round(float(baseline_score), 6),
            "delta": delta,
            "max_regression": EDITABILITY_REVIEW_MAX_COMPONENT_REGRESSION,
        }
        deltas.append(item)
        if delta < -EDITABILITY_REVIEW_MAX_COMPONENT_REGRESSION:
            regressed.append(item)
    if not deltas:
        return {
            "status": "missing_comparable_scores",
            "deltas": [],
            "regressed_components": [],
        }
    return {
        "status": "failed" if regressed else "passed",
        "deltas": deltas,
        "regressed_components": regressed,
    }


def _baseline_component_scores(case: dict[str, Any]) -> dict[str, object]:
    review = case.get("editability_review", {})
    if isinstance(review, dict) and isinstance(review.get("component_scores"), dict):
        return dict(review["component_scores"])
    metrics = case.get("metrics", {})
    if not isinstance(metrics, dict):
        return {}
    components = metrics.get("editability_v10_components", {})
    if not isinstance(components, dict):
        return {}
    scores: dict[str, object] = {}
    for component_id, component in components.items():
        scores[str(component_id)] = _component_score(component)
    return scores


def _component_score(component: object) -> object:
    if not isinstance(component, dict):
        return None
    score = component.get("score")
    if isinstance(score, (int, float)):
        return round(float(score), 6)
    return None


def _promotion_region_results(
    case: dict[str, Any],
    *,
    manifest: dict[str, Any] | None = None,
) -> list[dict[str, object]]:
    promotion = case.get("promotion")
    if not isinstance(promotion, dict):
        return []
    configured = promotion.get("region_gates", [])
    if not isinstance(configured, list) or not configured:
        return []
    gates_by_id = {
        str(gate.get("id")): gate
        for gate in case.get("promotion_gates", [])
        if isinstance(gate, dict) and isinstance(gate.get("id"), str)
    }
    thresholds = promotion.get("structure_thresholds")
    non_structural_roles = (
        _non_structural_layer_roles(thresholds)
        if isinstance(thresholds, dict)
        else ()
    )
    regions: list[dict[str, object]] = []
    for region in configured:
        if not isinstance(region, dict):
            continue
        region_id = str(region.get("id", "region"))
        gate = gates_by_id.get(region_id)
        state = _promotion_region_state(
            status=str(case.get("status", "unknown")),
            quality=str(promotion.get("current_quality_label", "")),
            gate=gate,
        )
        selected_ids = _gate_selected_anchor_ids(gate)
        selected_indexes = [
            index
            for index in (_anchor_index_from_id(anchor_id) for anchor_id in selected_ids)
            if index is not None
        ]
        region_result = {
            "id": region_id,
            "state": state,
            "gate_id": region_id,
            "gate_type": region.get("gate_type", "shape_class"),
            "gate_ok": bool(gate.get("ok", False)) if isinstance(gate, dict) else False,
            "severity": (
                str(gate.get("severity", "red"))
                if isinstance(gate, dict)
                else "red"
            ),
            "bounds": region.get("bounds"),
            "expected_kinds": region.get("expected_kinds", []),
            "forbidden_kinds": region.get("forbidden_kinds", []),
            "selected_anchor_ids": selected_ids,
            "selected_anchor_indexes": selected_indexes,
            "selected_anchor_count": len(selected_ids),
            "reason": (
                str(gate.get("reason", "missing gate result"))
                if isinstance(gate, dict)
                else "missing gate result"
            ),
        }
        if isinstance(gate, dict):
            evidence = gate.get("evidence")
            if isinstance(evidence, dict):
                for visual_key in (
                    "visual_delta",
                    "visual_thresholds",
                    "visual_failures",
                ):
                    value = evidence.get(visual_key)
                    if value:
                        region_result[visual_key] = value
        region_result.update(
            _promotion_region_layer_summary(
                selected_indexes,
                manifest=manifest,
                non_structural_layer_roles=non_structural_roles,
            )
        )
        region_result.update(
            _promotion_region_anchor_profile(
                selected_indexes,
                manifest=manifest,
            )
        )
        regions.append(region_result)
    return regions


def _promotion_region_layer_summary(
    selected_anchor_indexes: list[int],
    *,
    manifest: dict[str, Any] | None,
    non_structural_layer_roles: tuple[str, ...],
) -> dict[str, object]:
    layer_by_index = _manifest_anchor_layers(manifest)
    roles = [
        layer_by_index[index]
        for index in selected_anchor_indexes
        if index in layer_by_index
    ]
    role_counts = _counts(roles)
    layer_roles = sorted(role_counts)
    structural_roles = [
        role for role in layer_roles if role not in set(non_structural_layer_roles)
    ]
    return {
        "layer_roles": layer_roles,
        "layer_role_counts": role_counts,
        "region_layer_count": len(layer_roles),
        "structural_layer_roles": structural_roles,
        "structural_layer_count": len(structural_roles),
        "non_structural_layer_roles": list(non_structural_layer_roles),
    }


def _manifest_anchor_layers(manifest: dict[str, Any] | None) -> dict[int, str]:
    if not isinstance(manifest, dict):
        return {}
    layer_by_index: dict[int, str] = {}
    anchors = manifest.get("anchors", [])
    if isinstance(anchors, list):
        for index, anchor in enumerate(anchors):
            if not isinstance(anchor, dict):
                continue
            layer = anchor.get("layer")
            if isinstance(layer, str) and layer:
                layer_by_index[index] = layer
    layers = manifest.get("layers", [])
    if isinstance(layers, list):
        for layer in layers:
            if not isinstance(layer, dict):
                continue
            name = layer.get("name")
            indexes = layer.get("anchor_indexes")
            if not isinstance(name, str) or not isinstance(indexes, list):
                continue
            for index in indexes:
                if isinstance(index, int):
                    layer_by_index.setdefault(index, name)
    return layer_by_index


def _promotion_region_anchor_profile(
    selected_anchor_indexes: list[int],
    *,
    manifest: dict[str, Any] | None,
) -> dict[str, object]:
    anchors = manifest.get("anchors", []) if isinstance(manifest, dict) else []
    if not isinstance(anchors, list):
        anchors = []
    kinds = []
    for index in selected_anchor_indexes:
        if index < 0 or index >= len(anchors):
            continue
        anchor = anchors[index]
        if not isinstance(anchor, dict):
            continue
        kind = anchor.get("kind")
        if isinstance(kind, str) and kind:
            kinds.append(kind)
    kind_counts = _counts(kinds)
    simple_count = sum(
        count for kind, count in kind_counts.items() if kind in SIMPLE_ANCHOR_KINDS
    )
    stroke_count = sum(
        count for kind, count in kind_counts.items() if kind in STROKE_ANCHOR_KINDS
    )
    generic_path_count = int(kind_counts.get("cubic_path", 0))
    return {
        "selected_anchor_kind_counts": kind_counts,
        "selected_simple_anchor_count": simple_count,
        "selected_stroke_anchor_count": stroke_count,
        "selected_generic_path_anchor_count": generic_path_count,
    }


def _promotion_region_state(
    *,
    status: str,
    quality: str,
    gate: dict[str, object] | None,
) -> str:
    if status != "checked":
        return "deferred"
    if not isinstance(gate, dict):
        return "deferred"
    if not gate.get("ok", False):
        return "rejected" if gate.get("severity") == "red" else "deferred"
    if quality == "green":
        return "promoted"
    return "deferred"


def _gate_selected_anchor_ids(gate: dict[str, object] | None) -> list[str]:
    if not isinstance(gate, dict):
        return []
    evidence = gate.get("evidence", {})
    if not isinstance(evidence, dict):
        return []
    selected = evidence.get("selected_anchors", [])
    if not isinstance(selected, list):
        return []
    anchor_ids: list[str] = []
    for anchor in selected:
        if isinstance(anchor, dict) and isinstance(anchor.get("id"), str):
            anchor_ids.append(str(anchor["id"]))
    return anchor_ids


def _write_promotion_export_artifacts(
    run_dir: Path,
    *,
    scene: Any,
    manifest: dict[str, Any],
    promotion_regions: object,
    case_result: dict[str, Any],
    cutout_strategy: str,
) -> dict[str, object]:
    promoted_svg_path = run_dir / "promoted.svg"
    fallback_svg_path = run_dir / "fallback.svg"
    promotion_export_path = run_dir / "promotion-export.json"
    promotion_regions_path = run_dir / "promotion-regions.json"
    promotion_review_path = run_dir / "promotion-review.md"
    editability_review_path = run_dir / "editability-review.md"
    review_decision_path = run_dir / "review-decision.json"
    review_templates_dir = run_dir / "review-templates"
    promotion_artifacts = {
        "promoted_svg": str(promoted_svg_path),
        "fallback_svg": str(fallback_svg_path),
        "promotion_export": str(promotion_export_path),
        "promotion_regions": str(promotion_regions_path),
        "promotion_review": str(promotion_review_path),
        "editability_review": str(editability_review_path),
        "review_decision": str(review_decision_path),
    }
    anchor_count = len(scene.anchors)
    state_indexes = _promotion_anchor_state_indexes(
        promotion_regions,
        anchor_count=anchor_count,
    )
    promoted_indexes = set(state_indexes["promoted"])
    promoted_order = sorted(promoted_indexes)
    fallback_indexes = [
        index for index in range(anchor_count) if index not in promoted_indexes
    ]
    style = SvgStyle(cutout_strategy=cutout_strategy)
    export_source_manifest = _manifest_with_promotion_state(
        manifest,
        case_result,
        promotion_artifacts=promotion_artifacts,
    )
    promoted_svg_path.write_text(
        anchors_to_svg(
            (scene.anchors[index] for index in promoted_order),
            scene.width,
            scene.height,
            style=style,
            metadata=_promotion_svg_metadata(export_source_manifest, promoted_order),
        ),
        encoding="utf-8",
    )
    fallback_svg_path.write_text(
        anchors_to_svg(
            (scene.anchors[index] for index in fallback_indexes),
            scene.width,
            scene.height,
            style=style,
            metadata=_promotion_svg_metadata(export_source_manifest, fallback_indexes),
        ),
        encoding="utf-8",
    )
    export_manifest = {
        "schema_version": 1,
        "anchor_count": anchor_count,
        "promoted_anchor_indexes": state_indexes["promoted"],
        "fallback_anchor_indexes": fallback_indexes,
        "fallback_only_anchor_indexes": state_indexes["fallback"],
        "rejected_anchor_indexes": state_indexes["rejected"],
        "deferred_anchor_indexes": state_indexes["deferred"],
        "export_summary": _promotion_export_summary(
            state_indexes,
            promotion_regions,
        ),
        "anchor_state_counts": {
            state: len(indexes)
            for state, indexes in state_indexes.items()
            if indexes
        },
        "region_state_counts": _promotion_region_state_counts(promotion_regions),
        "regions": promotion_regions if isinstance(promotion_regions, list) else [],
        "gates": case_result.get("promotion_gates", []),
        "promoted_svg": str(promoted_svg_path),
        "fallback_svg": str(fallback_svg_path),
        "source_manifest_anchor_count": len(manifest.get("anchors", [])),
        "svg_metadata": {
            "anchor_id_attribute": "data-morphea-anchor-id",
            "anchor_index_attribute": "data-anchor-index",
            "promotion_state_attribute": "data-promotion-state",
            "promotion_regions_attribute": "data-promotion-regions",
        },
    }
    export_manifest["missing_from_promoted"] = _promotion_export_missing_records(
        export_manifest,
    )
    promotion_export_path.write_text(
        json.dumps(export_manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    regions = promotion_regions if isinstance(promotion_regions, list) else []
    promotion_regions_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "region_state_counts": _promotion_region_state_counts(regions),
                "regions": regions,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    promotion_review_path.write_text(
        _render_promotion_review_markdown(export_manifest),
        encoding="utf-8",
    )
    editability_review_path.write_text(
        _render_editability_review_markdown(case_result),
        encoding="utf-8",
    )
    review_artifacts = _promotion_review_artifacts(
        case_result,
        promotion_artifacts,
    )
    review_decision = case_result.get("review_decision")
    if not isinstance(review_decision, dict):
        review_decision = _promotion_review_decision_record(
            case_result,
            review_artifacts=review_artifacts,
        )
    else:
        review_decision = {
            **review_decision,
            "review_artifacts": review_artifacts,
        }
    case_result["review_decision"] = review_decision
    review_decision_path.write_text(
        json.dumps(review_decision, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    review_templates_dir.mkdir(parents=True, exist_ok=True)
    review_templates: dict[str, str] = {}
    for decision, template in _promotion_review_decision_templates(
        case_result,
        review_artifacts=review_artifacts,
    ).items():
        template_path = review_templates_dir / f"{decision}.json"
        template_path.write_text(
            json.dumps(template, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        review_templates[decision] = str(template_path)
    return {
        "promoted_svg": str(promoted_svg_path),
        "fallback_svg": str(fallback_svg_path),
        "promotion_export": str(promotion_export_path),
        "promotion_regions": str(promotion_regions_path),
        "promotion_review": str(promotion_review_path),
        "editability_review": str(editability_review_path),
        "review_decision": str(review_decision_path),
        "review_templates": review_templates,
    }


def _write_review_packet_artifacts(
    output_dir: Path,
    report: dict[str, Any],
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    packet = _review_packet(report)
    packet_path = output_dir / "review-packet.json"
    markdown_path = output_dir / "review-packet.md"
    gallery_path = output_dir / "review-gallery.html"
    packet_path.write_text(
        json.dumps(packet, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    markdown_path.write_text(
        _render_review_packet_markdown(packet),
        encoding="utf-8",
    )
    gallery_path.write_text(
        render_review_gallery_html(report, packet, html_path=gallery_path),
        encoding="utf-8",
    )
    return {
        "review_packet": str(packet_path),
        "review_packet_markdown": str(markdown_path),
        "review_gallery": str(gallery_path),
    }


def write_review_packet_followup_artifacts(
    output_dir: str | Path,
    report: dict[str, Any],
    *,
    review_harvest_config: str | Path,
) -> dict[str, str]:
    """Rewrite review packet artifacts with review-to-harvest follow-up commands."""

    root = Path(output_dir)
    packet_path = root / "review-packet.json"
    markdown_path = root / "review-packet.md"
    gallery_path = root / "review-gallery.html"
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    if not isinstance(packet, dict):
        raise ValueError("review packet must be a JSON object")
    _add_review_packet_followup_commands(
        packet,
        review_harvest_config=review_harvest_config,
    )
    packet_path.write_text(
        json.dumps(packet, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    markdown_path.write_text(
        _render_review_packet_markdown(packet),
        encoding="utf-8",
    )
    gallery_path.write_text(
        render_review_gallery_html(report, packet, html_path=gallery_path),
        encoding="utf-8",
    )
    return {
        "review_packet": str(packet_path),
        "review_packet_markdown": str(markdown_path),
        "review_gallery": str(gallery_path),
    }


def _add_review_packet_followup_commands(
    packet: dict[str, object],
    *,
    review_harvest_config: str | Path,
) -> None:
    config = str(review_harvest_config)
    packet["review_harvest_config"] = config
    packet["review_harvest_command"] = _review_packet_harvest_command(config)
    cases = packet.get("cases", [])
    if not isinstance(cases, list):
        return
    for case in cases:
        if not isinstance(case, dict):
            continue
        case_id = case.get("case_id")
        artifacts = case.get("artifacts", {})
        artifacts = artifacts if isinstance(artifacts, dict) else {}
        templates = artifacts.get("review_templates")
        if not isinstance(case_id, str) or not isinstance(templates, dict):
            continue
        commands: dict[str, str] = {}
        evidence_flags: dict[str, list[str]] = {}
        for decision in PROMOTION_REVIEW_DECISIONS:
            if not isinstance(templates.get(decision), str):
                continue
            commands[decision] = (
                f"{_review_packet_harvest_command(config)} "
                f"--decision-choice {shlex.quote(f'{case_id}={decision}')}"
            )
            evidence_flags[decision] = _review_packet_decision_choice_flags(
                case_id,
                decision,
                reviewable_region_ids=case.get("reviewable_region_ids"),
            )
        if commands:
            case["decision_choice_commands"] = commands
            case["decision_choice_evidence_flags"] = evidence_flags


def _review_packet_harvest_command(config: str) -> str:
    return (
        "PYTHONPATH=src python3 -m morphea.cli promotion-review-harvest "
        f"--config {shlex.quote(config)}"
    )


def _review_packet_decision_choice_flags(
    case_id: str,
    decision: str,
    *,
    reviewable_region_ids: object = (),
) -> list[str]:
    flags = [
        f"--reviewer {shlex.quote(f'{case_id}=REVIEWER')}",
        f"--reason {shlex.quote(f'{case_id}=REASON')}",
    ]
    if decision in {"accepted", "corrected"}:
        for region_id in _reviewable_region_ids(reviewable_region_ids):
            flags.append(f"--reviewed-region {shlex.quote(f'{case_id}={region_id}')}")
    if decision == "corrected":
        flags.extend(
            [
                f"--correction-notes {shlex.quote(f'{case_id}=NOTES')}",
                f"--corrected-artifact {shlex.quote(f'{case_id}=PATH')}",
            ]
        )
    return flags


def _review_packet(report: dict[str, Any]) -> dict[str, object]:
    cases = [
        _review_packet_case(case)
        for case in report.get("cases", [])
        if isinstance(case, dict) and _case_needs_review_packet(case)
    ]
    return {
        "schema_version": 1,
        "suite": report.get("suite"),
        "run": bool(report.get("run", False)),
        "case_count": len(cases),
        "deferred_count": sum(
            1 for case in cases if case.get("promotion_decision") == "deferred"
        ),
        "rejected_count": sum(
            1 for case in cases if case.get("promotion_decision") == "rejected"
        ),
        "manual_review_count": sum(
            1 for case in cases if case.get("editability_decision") == "manual_review"
        ),
        "reviewable_region_summary": _review_packet_region_summary(cases),
        "issue_groups": _review_packet_groups(cases, "issue_tags"),
        "failed_gate_groups": _review_packet_groups(cases, "failed_gate_ids"),
        "cases": cases,
    }


def _case_needs_review_packet(case: dict[str, Any]) -> bool:
    summary = case.get("promotion_summary", {})
    review = case.get("editability_review", {})
    decision = summary.get("decision") if isinstance(summary, dict) else None
    editability_decision = review.get("decision") if isinstance(review, dict) else None
    return decision in {"deferred", "rejected"} or editability_decision in {
        "manual_review",
        "rejected",
    }


def _review_packet_case(case: dict[str, Any]) -> dict[str, object]:
    promotion = case.get("promotion", {})
    promotion = promotion if isinstance(promotion, dict) else {}
    summary = case.get("promotion_summary", {})
    summary = summary if isinstance(summary, dict) else {}
    review = case.get("editability_review", {})
    review = review if isinstance(review, dict) else {}
    decision = case.get("review_decision", {})
    decision = decision if isinstance(decision, dict) else {}
    artifacts = case.get("artifacts", {})
    artifacts = artifacts if isinstance(artifacts, dict) else {}
    artifact_paths: dict[str, object] = {
        key: artifacts[key]
        for key in (
            "contact_sheet",
            "promotion_review",
            "editability_review",
            "review_decision",
            "promotion_export",
            "manifest",
        )
        if isinstance(artifacts.get(key), str)
    }
    templates = artifacts.get("review_templates")
    if isinstance(templates, dict):
        template_paths = {
            decision: path
            for decision, path in templates.items()
            if isinstance(decision, str) and isinstance(path, str)
        }
        if template_paths:
            artifact_paths["review_templates"] = dict(sorted(template_paths.items()))
    review_commands = _review_packet_review_commands(artifact_paths)
    reviewable_regions = _reviewable_region_summaries(
        case.get("promotion_regions")
    )
    return {
        "case_id": case.get("id"),
        "status": case.get("status"),
        "source": case.get("source"),
        "source_exists": bool(case.get("source_exists", False)),
        "quality_label": promotion.get("current_quality_label"),
        "issue_tags": _promotion_issue_tags(promotion),
        "promotion_decision": summary.get("decision", "n/a"),
        "red_gate_count": summary.get("red_gate_count", 0),
        "yellow_gate_count": summary.get("yellow_gate_count", 0),
        "failed_gate_ids": _failed_gate_ids(case.get("promotion_gates")),
        "failed_gate_details": _review_decision_failed_gates(
            case.get("promotion_gates")
        ),
        "editability_decision": review.get("decision", "n/a"),
        "editability_accepted": bool(review.get("accepted", False)),
        "failed_component_ids": _failed_component_ids(
            review.get("failed_components")
        ),
        "suggested_review_decision": decision.get("suggested_decision", "n/a"),
        "review_decision_state": decision.get("decision", "n/a"),
        "review_requirements": _review_packet_requirements(),
        "quality_label_policy": decision.get("quality_label_policy", {}),
        "reviewable_regions": reviewable_regions,
        "reviewable_region_ids": [
            region["id"]
            for region in reviewable_regions
            if isinstance(region.get("id"), str)
        ],
        "artifacts": artifact_paths,
        "review_commands": review_commands,
    }


def _review_packet_requirements() -> dict[str, list[str]]:
    return {
        "required_for_terminal_decisions": ["reviewer", "reason"],
        "optional_for_region_scoped_acceptance": ["reviewed_region_ids"],
        "required_for_corrected_decisions": [
            "correction_notes",
            "corrected_artifacts",
        ],
    }


def _review_packet_region_summary(cases: list[dict[str, object]]) -> dict[str, object]:
    region_count = 0
    selected_anchor_count = 0
    case_count = 0
    state_counts: dict[str, int] = {}
    gate_type_counts: dict[str, int] = {}
    for case in cases:
        regions = case.get("reviewable_regions")
        if not isinstance(regions, list) or not regions:
            continue
        case_has_regions = False
        for region in regions:
            if not isinstance(region, dict):
                continue
            region_count += 1
            case_has_regions = True
            selected_anchor_count += _int_value(region.get("selected_anchor_count"))
            state = str(region.get("state") or "n/a")
            gate_type = str(region.get("gate_type") or "n/a")
            state_counts[state] = state_counts.get(state, 0) + 1
            gate_type_counts[gate_type] = gate_type_counts.get(gate_type, 0) + 1
        if case_has_regions:
            case_count += 1
    return {
        "case_count": case_count,
        "region_count": region_count,
        "selected_anchor_count": selected_anchor_count,
        "state_counts": dict(sorted(state_counts.items())),
        "gate_type_counts": dict(sorted(gate_type_counts.items())),
    }


def _int_value(value: object) -> int:
    return int(value) if isinstance(value, int) and not isinstance(value, bool) else 0


def _reviewable_region_summaries(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    regions: list[dict[str, object]] = []
    for region in value:
        if not isinstance(region, dict):
            continue
        region_id = region.get("id")
        selected_indexes = _reviewable_region_anchor_indexes(region)
        if not isinstance(region_id, str) or not region_id:
            continue
        if region.get("gate_ok") is not True or not selected_indexes:
            continue
        summary: dict[str, object] = {
            "id": region_id,
            "state": region.get("state", "n/a"),
            "gate_id": region.get("gate_id", region_id),
            "gate_type": region.get("gate_type", "n/a"),
            "selected_anchor_count": len(selected_indexes),
            "selected_anchor_indexes": selected_indexes,
        }
        reason = region.get("reason")
        if isinstance(reason, str) and reason:
            summary["reason"] = reason
        regions.append(summary)
    return sorted(regions, key=lambda item: str(item.get("id", "")))


def _reviewable_region_anchor_indexes(region: dict[str, object]) -> list[int]:
    indexes = region.get("selected_anchor_indexes")
    if not isinstance(indexes, list):
        return []
    return sorted(
        {
            index
            for index in indexes
            if isinstance(index, int) and not isinstance(index, bool) and index >= 0
        }
    )


def _reviewable_region_ids(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    ids: list[str] = []
    for item in value:
        if isinstance(item, str) and item and item not in ids:
            ids.append(item)
    return ids


def _review_packet_review_commands(
    artifacts: dict[str, object],
) -> dict[str, str]:
    manifest = artifacts.get("manifest")
    templates = artifacts.get("review_templates")
    if not isinstance(manifest, str) or not isinstance(templates, dict):
        return {}
    output = str(Path(manifest).with_name("applied-review.json"))
    markdown = str(Path(manifest).with_name("applied-review.md"))
    commands: dict[str, str] = {}
    for decision in PROMOTION_REVIEW_DECISIONS:
        template = templates.get(decision)
        if not isinstance(template, str) or not template:
            continue
        commands[decision] = (
            "PYTHONPATH=src python3 -m morphea.cli promotion-apply-review "
            f"{shlex.quote(template)} "
            f"--manifest {shlex.quote(manifest)} "
            f"-o {shlex.quote(output)} "
            f"--markdown {shlex.quote(markdown)}"
        )
    return commands


def _failed_gate_ids(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [
        str(gate.get("id", "n/a"))
        for gate in value
        if isinstance(gate, dict) and not gate.get("ok", False)
    ]


def _failed_component_ids(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [
        str(component.get("id", "n/a"))
        for component in value
        if isinstance(component, dict)
    ]


def _review_packet_groups(
    cases: list[dict[str, object]],
    field: str,
) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    for case in cases:
        case_id = case.get("case_id")
        if not isinstance(case_id, str):
            continue
        values = case.get(field)
        if not isinstance(values, list):
            continue
        for value in values:
            if isinstance(value, str) and value:
                groups.setdefault(value, []).append(case_id)
    return {key: groups[key] for key in sorted(groups)}


def _fmt_review_packet_region_summary(value: object) -> str:
    if not isinstance(value, dict):
        return "n/a"
    return (
        f"{_fmt_markdown_value(value.get('region_count'))} regions, "
        f"{_fmt_markdown_value(value.get('case_count'))} cases, "
        f"{_fmt_markdown_value(value.get('selected_anchor_count'))} anchors; "
        f"states={_fmt_markdown_counts(value.get('state_counts'))}; "
        f"gates={_fmt_markdown_counts(value.get('gate_type_counts'))}"
    )


def _render_review_packet_markdown(packet: dict[str, object]) -> str:
    cases = packet.get("cases", [])
    cases = cases if isinstance(cases, list) else []
    lines = [
        "# Morphēa Review Packet",
        "",
        f"- Suite: `{packet.get('suite', 'n/a')}`",
        f"- Cases needing review: {_fmt_markdown_value(packet.get('case_count'))}",
        f"- Deferred: {_fmt_markdown_value(packet.get('deferred_count'))}",
        f"- Rejected: {_fmt_markdown_value(packet.get('rejected_count'))}",
        f"- Manual review: {_fmt_markdown_value(packet.get('manual_review_count'))}",
        f"- Reviewable regions: {_fmt_review_packet_region_summary(packet.get('reviewable_region_summary'))}",
    ]
    if isinstance(packet.get("review_harvest_config"), str):
        lines.append(f"- Review harvest config: `{packet['review_harvest_config']}`")
    if isinstance(packet.get("review_harvest_command"), str):
        lines.append(f"- Review harvest command: `{packet['review_harvest_command']}`")
    lines.extend(
        [
            "",
            "## Issue Groups",
            "",
            "| Issue | Cases |",
            "| --- | --- |",
        ]
    )
    lines.extend(_review_packet_group_rows(packet.get("issue_groups")))
    lines.extend(
        [
            "",
            "## Failed Gate Groups",
            "",
            "| Gate | Cases |",
            "| --- | --- |",
        ]
    )
    lines.extend(_review_packet_group_rows(packet.get("failed_gate_groups")))
    lines.extend(
        [
            "",
            "## Cases",
            "",
            "| Case | Promotion | Editability | Suggested | Issues | Failed gates | Failed components |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    if not cases:
        lines.append("| n/a | n/a | n/a | n/a | n/a | n/a | n/a |")
    for case in cases:
        if not isinstance(case, dict):
            continue
        lines.append(
            "| "
            f"`{case.get('case_id', 'n/a')}` | "
            f"`{case.get('promotion_decision', 'n/a')}` | "
            f"`{case.get('editability_decision', 'n/a')}` | "
            f"`{case.get('suggested_review_decision', 'n/a')}` | "
            f"{_fmt_markdown_list(case.get('issue_tags'))} | "
            f"{_fmt_markdown_list(case.get('failed_gate_ids'))} | "
            f"{_fmt_markdown_list(case.get('failed_component_ids'))} |"
        )
    for case in cases:
        if not isinstance(case, dict):
            continue
        lines.extend(["", f"## {case.get('case_id', 'n/a')}", ""])
        lines.append(f"- Source: `{case.get('source', 'n/a')}`")
        lines.append(
            "- Decision: "
            f"promotion=`{case.get('promotion_decision', 'n/a')}`, "
            f"editability=`{case.get('editability_decision', 'n/a')}`, "
            f"suggested=`{case.get('suggested_review_decision', 'n/a')}`"
        )
        lines.append(
            "- Review requirements: "
            f"terminal={_fmt_review_requirement_list(case.get('review_requirements'), 'required_for_terminal_decisions')}, "
            f"corrected={_fmt_review_requirement_list(case.get('review_requirements'), 'required_for_corrected_decisions')}, "
            f"region-scoped={_fmt_review_requirement_list(case.get('review_requirements'), 'optional_for_region_scoped_acceptance')}"
        )
        artifacts = case.get("artifacts", {})
        artifacts = artifacts if isinstance(artifacts, dict) else {}
        lines.extend(
            [
                f"- Contact sheet: `{artifacts.get('contact_sheet', 'n/a')}`",
                f"- Promotion review: `{artifacts.get('promotion_review', 'n/a')}`",
                f"- Editability review: `{artifacts.get('editability_review', 'n/a')}`",
                f"- Review decision: `{artifacts.get('review_decision', 'n/a')}`",
            ]
        )
        templates = artifacts.get("review_templates")
        if isinstance(templates, dict) and templates:
            template_parts = [
                f"{decision}=`{path}`"
                for decision, path in sorted(templates.items())
                if isinstance(decision, str) and isinstance(path, str)
            ]
            if template_parts:
                lines.append(f"- Decision templates: {', '.join(template_parts)}")
        failed_gate_details = case.get("failed_gate_details")
        if isinstance(failed_gate_details, list) and failed_gate_details:
            lines.extend(
                [
                    "",
                    "### Failed Gate Details",
                    "",
                    "| Gate | Type | Severity | Reason |",
                    "| --- | --- | --- | --- |",
                ]
            )
            for gate in failed_gate_details:
                if not isinstance(gate, dict):
                    continue
                lines.append(
                    "| "
                    f"{_fmt_markdown_code_value(gate.get('id'))} | "
                    f"{_fmt_markdown_code_value(gate.get('gate_type'))} | "
                    f"{_fmt_markdown_code_value(gate.get('severity'))} | "
                    f"{_fmt_markdown_table_text(gate.get('reason'))} |"
                )
        reviewable_regions = case.get("reviewable_regions")
        if isinstance(reviewable_regions, list) and reviewable_regions:
            lines.extend(
                [
                    "",
                    "### Reviewable Regions",
                    "",
                    "| Region | State | Gate | Type | Anchors | Reason |",
                    "| --- | --- | --- | --- | --- | --- |",
                ]
            )
            for region in reviewable_regions:
                if not isinstance(region, dict):
                    continue
                lines.append(
                    "| "
                    f"{_fmt_markdown_code_value(region.get('id'))} | "
                    f"{_fmt_markdown_code_value(region.get('state'))} | "
                    f"{_fmt_markdown_code_value(region.get('gate_id'))} | "
                    f"{_fmt_markdown_code_value(region.get('gate_type'))} | "
                    f"{_fmt_markdown_value(region.get('selected_anchor_count'))} | "
                    f"{_fmt_markdown_table_text(region.get('reason'))} |"
                )
        commands = case.get("review_commands")
        if isinstance(commands, dict) and commands:
            lines.extend(
                [
                    "",
                    "### Apply Commands",
                    "",
                    "Edit the chosen terminal template first, then run:",
                    "",
                ]
            )
            for decision in PROMOTION_REVIEW_DECISIONS:
                command = commands.get(decision)
                if not isinstance(command, str) or not command:
                    continue
                lines.extend(
                    [
                        f"#### {decision}",
                        "",
                        "```sh",
                        command,
                        "```",
                        "",
                    ]
                )
        choice_commands = case.get("decision_choice_commands")
        if isinstance(choice_commands, dict) and choice_commands:
            flags_by_decision = case.get("decision_choice_evidence_flags")
            flags_by_decision = (
                flags_by_decision if isinstance(flags_by_decision, dict) else {}
            )
            lines.extend(
                [
                    "",
                    "### Harvest Choice Commands",
                    "",
                    "Append reviewer evidence flags before running the selected command:",
                    "",
                ]
            )
            for decision in PROMOTION_REVIEW_DECISIONS:
                command = choice_commands.get(decision)
                if not isinstance(command, str) or not command:
                    continue
                flags = flags_by_decision.get(decision)
                lines.extend(
                    [
                        f"#### {decision}",
                        "",
                        "```sh",
                        command,
                        "```",
                        "",
                        f"- Evidence flags: {_fmt_markdown_list(flags)}",
                        "",
                    ]
                )
    return "\n".join(lines).rstrip() + "\n"


def _fmt_review_requirement_list(value: object, key: str) -> str:
    if not isinstance(value, dict):
        return "n/a"
    return _fmt_markdown_list(value.get(key))


def _review_packet_group_rows(value: object) -> list[str]:
    if not isinstance(value, dict) or not value:
        return ["| n/a | n/a |"]
    rows: list[str] = []
    for key in sorted(value):
        cases = value.get(key)
        case_text = (
            ", ".join(f"`{case}`" for case in cases)
            if isinstance(cases, list) and cases
            else "n/a"
        )
        rows.append(f"| `{key}` | {case_text} |")
    return rows


def _promotion_gate_detail_rows(cases: list[object]) -> list[str]:
    rows: list[str] = []
    for case in _promotion_sorted_cases(cases):
        if not isinstance(case, dict):
            continue
        case_id = case.get("id", "n/a")
        for gate in _review_decision_failed_gates(case.get("promotion_gates")):
            rows.append(
                "| "
                f"`{case_id}` | "
                f"{_fmt_markdown_code_value(gate.get('id'))} | "
                f"{_fmt_markdown_code_value(gate.get('gate_type'))} | "
                f"{_fmt_markdown_code_value(gate.get('severity'))} | "
                f"{_fmt_markdown_table_text(gate.get('reason'))} |"
            )
    return rows


def _fmt_markdown_table_text(value: object) -> str:
    if value is None or value == "":
        return "n/a"
    return str(value).replace("\n", " ").replace("|", "\\|")


def _promotion_anchor_state_indexes(
    promotion_regions: object,
    *,
    anchor_count: int,
) -> dict[str, list[int]]:
    states_by_index: dict[int, set[str]] = {
        index: set() for index in range(anchor_count)
    }
    if isinstance(promotion_regions, list):
        for region in promotion_regions:
            if not isinstance(region, dict):
                continue
            state = region.get("state")
            if state not in {"promoted", "rejected", "deferred"}:
                continue
            indexes = region.get("selected_anchor_indexes", [])
            if not isinstance(indexes, list):
                continue
            for index in indexes:
                if isinstance(index, int) and 0 <= index < anchor_count:
                    states_by_index[index].add(str(state))

    state_indexes = {
        "promoted": [],
        "fallback": [],
        "rejected": [],
        "deferred": [],
    }
    for index in range(anchor_count):
        state_indexes[_promotion_state_from_region_states(states_by_index[index])].append(
            index
        )
    return state_indexes


def _promotion_state_from_region_states(states: set[str]) -> str:
    if "promoted" in states:
        return "promoted"
    if "rejected" in states:
        return "rejected"
    if "deferred" in states:
        return "deferred"
    return "fallback"


def _anchor_index_from_id(value: object) -> int | None:
    if not isinstance(value, str) or not value.startswith("anchor-"):
        return None
    suffix = value.rsplit("-", 1)[-1]
    if not suffix.isdigit():
        return None
    return int(suffix)


def _promotion_region_state_counts(value: object) -> dict[str, int]:
    if not isinstance(value, list):
        return {}
    return _counts(
        region.get("state")
        for region in value
        if isinstance(region, dict)
    )


def _promotion_export_summary(
    state_indexes: dict[str, list[int]],
    promotion_regions: object,
) -> dict[str, int]:
    region_counts = _promotion_region_state_counts(promotion_regions)
    summary: dict[str, int] = {}
    for state in ("promoted", "fallback", "rejected", "deferred"):
        summary[f"{state}_anchor_count"] = len(state_indexes.get(state, []))
        summary[f"{state}_region_count"] = int(region_counts.get(state, 0))
    return summary


def _promotion_export_missing_records(
    export_manifest: dict[str, object],
) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    regions = export_manifest.get("regions")
    for state, key in (
        ("fallback", "fallback_only_anchor_indexes"),
        ("rejected", "rejected_anchor_indexes"),
        ("deferred", "deferred_anchor_indexes"),
    ):
        anchors = _int_list(export_manifest.get(key))
        state_regions = _promotion_regions_for_state(regions, state)
        if not anchors and not state_regions:
            continue
        records.append(
            {
                "state": state,
                "anchor_indexes": anchors,
                "anchor_count": len(anchors),
                "region_ids": _promotion_region_ids(state_regions),
                "region_count": len(state_regions),
                "reasons": _promotion_region_reasons(state_regions),
            }
        )
    return records


def _promotion_regions_for_state(
    value: object,
    state: str,
) -> list[dict[str, object]]:
    regions = value if isinstance(value, list) else []
    return [
        region
        for region in regions
        if isinstance(region, dict) and region.get("state") == state
    ]


def _promotion_region_ids(regions: list[dict[str, object]]) -> list[str]:
    return [
        str(region.get("id"))
        for region in regions
        if isinstance(region.get("id"), str) and region.get("id")
    ]


def _promotion_region_reasons(regions: list[dict[str, object]]) -> list[str]:
    reasons = []
    for region in regions:
        reason = (
            region.get("reason")
            or region.get("rejection_reason")
            or region.get("deferred_reason")
            or "n/a"
        )
        reasons.append(str(reason))
    return reasons


def _int_list(value: object) -> list[int]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, int)]


def _render_promotion_review_markdown(export_manifest: dict[str, object]) -> str:
    regions = export_manifest.get("regions", [])
    regions = regions if isinstance(regions, list) else []
    promoted = export_manifest.get("promoted_anchor_indexes", [])
    promoted_count = len(promoted) if isinstance(promoted, list) else None
    fallback = export_manifest.get("fallback_anchor_indexes", [])
    fallback_count = len(fallback) if isinstance(fallback, list) else None
    lines = [
        "# Morphēa Promotion Review",
        "",
        f"- Anchors: {_fmt_markdown_value(export_manifest.get('anchor_count'))}",
        f"- Promoted anchors: {_fmt_markdown_value(promoted_count)}",
        f"- Fallback anchors: {_fmt_markdown_value(fallback_count)}",
        f"- Anchor states: {_fmt_markdown_counts(export_manifest.get('anchor_state_counts'))}",
        f"- Region states: {_fmt_markdown_counts(export_manifest.get('region_state_counts'))}",
        "",
        "| Region | State | Gate | Selected anchors | Visual delta | Reason |",
        "| --- | --- | --- | ---: | --- | --- |",
    ]
    if not regions:
        lines.append("| n/a | `deferred` | n/a | 0 | n/a | no promotion regions |")
    for region in regions:
        if not isinstance(region, dict):
            continue
        lines.append(
            "| "
            f"`{region.get('id', 'n/a')}` | "
            f"`{region.get('state', 'n/a')}` | "
            f"`{region.get('gate_id', 'n/a')}` | "
            f"{_fmt_markdown_value(region.get('selected_anchor_count'))} | "
            f"{_fmt_region_visual(region)} | "
            f"{region.get('reason', 'n/a')} |"
        )
    rejection_rows = _promotion_review_candidate_rejection_rows(
        export_manifest.get("gates"),
    )
    lines.extend(
        [
            "",
            "## Candidate Rejections",
            "",
            "| Region | Anchor | Kind | Reasons | Topology failures |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    if rejection_rows:
        lines.extend(rejection_rows)
    else:
        lines.append("| n/a | n/a | n/a | n/a | n/a |")
    return "\n".join(lines).rstrip() + "\n"


def _promotion_review_candidate_rejection_rows(gates: object) -> list[str]:
    if not isinstance(gates, list):
        return []
    rows: list[str] = []
    for gate in gates:
        if not isinstance(gate, dict):
            continue
        evidence = gate.get("evidence")
        if not isinstance(evidence, dict):
            continue
        rejections = evidence.get("candidate_rejections")
        if not isinstance(rejections, list):
            continue
        for rejection in rejections:
            if not isinstance(rejection, dict):
                continue
            rows.append(
                "| "
                f"`{gate.get('id', 'n/a')}` | "
                f"{_fmt_markdown_code_value(rejection.get('id'))} | "
                f"{_fmt_markdown_code_value(rejection.get('kind'))} | "
                f"{_fmt_markdown_list(rejection.get('reasons'))} | "
                f"{_fmt_markdown_list(rejection.get('topology_failures'))} |"
            )
    return rows


def _fmt_markdown_code_value(value: object) -> str:
    if value is None or value == "":
        return "n/a"
    return f"`{value}`"


def _render_editability_review_markdown(case_result: dict[str, Any]) -> str:
    review = case_result.get("editability_review", {})
    review = review if isinstance(review, dict) else {}
    promotion = case_result.get("promotion", {})
    promotion = promotion if isinstance(promotion, dict) else {}
    summary = case_result.get("promotion_summary", {})
    summary = summary if isinstance(summary, dict) else {}
    component_scores = review.get("component_scores", {})
    component_scores = component_scores if isinstance(component_scores, dict) else {}
    thresholds = review.get("thresholds", {})
    thresholds = thresholds if isinstance(thresholds, dict) else {}
    required = thresholds.get("required", {})
    required = required if isinstance(required, dict) else {}
    observed = thresholds.get("observed", {})
    observed = observed if isinstance(observed, dict) else {}
    failed_components = review.get("failed_components", [])
    failed_components = (
        failed_components if isinstance(failed_components, list) else []
    )
    gate_blocked = review.get("gate_blocked_components", [])
    gate_blocked = gate_blocked if isinstance(gate_blocked, list) else []
    regression_deltas = review.get("regression_deltas", [])
    regression_deltas = (
        regression_deltas if isinstance(regression_deltas, list) else []
    )
    regressed = review.get("regressed_components", [])
    regressed = regressed if isinstance(regressed, list) else []
    promotion_decision = review.get(
        "promotion_decision",
        summary.get("decision", "n/a"),
    )
    lines = [
        "# Morphēa Editability Review",
        "",
        f"- Case: `{case_result.get('id', 'n/a')}`",
        f"- Decision: `{review.get('decision', 'n/a')}`",
        f"- Accepted: `{str(review.get('accepted', False)).lower()}`",
        f"- Promotion decision: `{promotion_decision}`",
        f"- Regression delta status: `{review.get('regression_delta_status', 'n/a')}`",
        f"- Reasons: {_fmt_markdown_list(review.get('reasons'))}",
        f"- Issue tags: {_fmt_markdown_list(promotion.get('current_issues'))}",
        "",
        "## Required Thresholds",
        "",
        "| Component | Score | Threshold | Status |",
        "| --- | ---: | ---: | --- |",
    ]
    for component_id, threshold in sorted(required.items()):
        score = component_scores.get(component_id)
        status = _editability_threshold_status(
            component_id,
            score,
            threshold,
            failed_components,
        )
        lines.append(
            "| "
            f"`{component_id}` | "
            f"{_fmt_markdown_value(score)} | "
            f"{_fmt_markdown_value(threshold)} | "
            f"`{status}` |"
        )
    if not required:
        lines.append("| n/a | n/a | n/a | `missing_thresholds` |")
    lines.extend(
        [
            "",
            "## Observed Thresholds",
            "",
            "| Component | Score | Threshold | Status |",
            "| --- | ---: | ---: | --- |",
        ]
    )
    for component_id, threshold in sorted(observed.items()):
        score = component_scores.get(component_id)
        status = (
            _editability_threshold_status(
                component_id,
                score,
                threshold,
                failed_components,
            )
            if component_id in component_scores
            else "not_observed"
        )
        lines.append(
            "| "
            f"`{component_id}` | "
            f"{_fmt_markdown_value(score)} | "
            f"{_fmt_markdown_value(threshold)} | "
            f"`{status}` |"
        )
    if not observed:
        lines.append("| n/a | n/a | n/a | `missing_thresholds` |")
    lines.extend(
        [
            "",
            "## Failed Components",
            "",
            "| Component | Score | Threshold | Reason |",
            "| --- | ---: | ---: | --- |",
        ]
    )
    if failed_components:
        for item in failed_components:
            if not isinstance(item, dict):
                continue
            lines.append(
                "| "
                f"`{item.get('id', 'n/a')}` | "
                f"{_fmt_markdown_value(item.get('score'))} | "
                f"{_fmt_markdown_value(item.get('threshold'))} | "
                f"`{item.get('reason', 'n/a')}` |"
            )
    else:
        lines.append("| n/a | n/a | n/a | `none` |")
    lines.extend(
        [
            "",
            "## Gate-Blocked Components",
            "",
            "| Component | Failed gates | Uncapped score |",
            "| --- | --- | ---: |",
        ]
    )
    if gate_blocked:
        for item in gate_blocked:
            if not isinstance(item, dict):
                continue
            lines.append(
                "| "
                f"`{item.get('id', 'n/a')}` | "
                f"{_fmt_markdown_list(item.get('failed_gates'))} | "
                f"{_fmt_markdown_value(item.get('uncapped_score'))} |"
            )
    else:
        lines.append("| n/a | `none` | n/a |")
    lines.extend(
        [
            "",
            "## Regression Deltas",
            "",
            "| Component | Current | Baseline | Delta | Max regression | Status |",
            "| --- | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    regressed_ids = {
        item.get("id")
        for item in regressed
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    if regression_deltas:
        for item in regression_deltas:
            if not isinstance(item, dict):
                continue
            component_id = item.get("id", "n/a")
            status = "failed" if component_id in regressed_ids else "passed"
            lines.append(
                "| "
                f"`{component_id}` | "
                f"{_fmt_markdown_value(item.get('current'))} | "
                f"{_fmt_markdown_value(item.get('baseline'))} | "
                f"{_fmt_markdown_value(item.get('delta'))} | "
                f"{_fmt_markdown_value(item.get('max_regression'))} | "
                f"`{status}` |"
            )
    else:
        lines.append(
            "| n/a | n/a | n/a | n/a | n/a | "
            f"`{review.get('regression_delta_status', 'n/a')}` |"
        )
    return "\n".join(lines).rstrip() + "\n"


def _editability_threshold_status(
    component_id: object,
    score: object,
    threshold: object,
    failed_components: list[object],
) -> str:
    for item in failed_components:
        if isinstance(item, dict) and item.get("id") == component_id:
            return str(item.get("reason", "failed"))
    if not isinstance(score, (int, float)):
        return "missing_score"
    if isinstance(threshold, (int, float)) and float(score) < float(threshold):
        return "below_threshold"
    return "passed"


def _promotion_review_decision_record(
    case_result: dict[str, Any],
    *,
    review_artifacts: dict[str, str] | None = None,
) -> dict[str, object]:
    review = case_result.get("editability_review", {})
    review = review if isinstance(review, dict) else {}
    promotion = case_result.get("promotion", {})
    promotion = promotion if isinstance(promotion, dict) else {}
    summary = case_result.get("promotion_summary", {})
    summary = summary if isinstance(summary, dict) else {}
    return {
        "schema_version": 1,
        "case_id": case_result.get("id"),
        "decision": "pending",
        "allowed_decisions": list(PROMOTION_REVIEW_DECISIONS),
        "suggested_decision": _suggested_promotion_review_decision(
            review,
            summary,
        ),
        "reviewer": "",
        "reason": "",
        "correction_notes": "",
        "corrected_artifacts": [],
        "reviewed_region_ids": [],
        "issue_tags": _promotion_issue_tags(promotion),
        "source_decisions": {
            "promotion_decision": summary.get("decision", "n/a"),
            "editability_decision": review.get("decision", "n/a"),
            "editability_accepted": bool(review.get("accepted", False)),
            "regression_delta_status": review.get(
                "regression_delta_status",
                "n/a",
            ),
        },
        "failed_gates": _review_decision_failed_gates(
            case_result.get("promotion_gates"),
        ),
        "failed_components": _review_decision_list(
            review.get("failed_components"),
        ),
        "gate_blocked_components": _review_decision_list(
            review.get("gate_blocked_components"),
        ),
        "regressed_components": _review_decision_list(
            review.get("regressed_components"),
        ),
        "review_artifacts": review_artifacts
        if review_artifacts is not None
        else _promotion_review_artifacts(case_result),
        "quality_label_policy": promotion_quality_label_policy(),
    }


def _promotion_review_decision_templates(
    case_result: dict[str, Any],
    *,
    review_artifacts: dict[str, str] | None = None,
) -> dict[str, dict[str, object]]:
    base = _promotion_review_decision_record(
        case_result,
        review_artifacts=review_artifacts,
    )
    templates: dict[str, dict[str, object]] = {}
    for decision in PROMOTION_REVIEW_DECISIONS:
        template = deepcopy(base)
        template["decision"] = decision
        template["template_guidance"] = _promotion_review_template_guidance(
            decision,
            suggested=base.get("suggested_decision"),
        )
        templates[decision] = template
    return templates


def _promotion_review_artifacts(
    case_result: dict[str, Any],
    extra_artifacts: dict[str, object] | None = None,
) -> dict[str, str]:
    artifacts: dict[str, object] = {}
    base_artifacts = case_result.get("artifacts")
    if isinstance(base_artifacts, dict):
        artifacts.update(base_artifacts)
    if extra_artifacts:
        artifacts.update(extra_artifacts)
    keys = (
        "manifest",
        "contact_sheet",
        "promotion_export",
        "promotion_regions",
        "promotion_review",
        "editability_review",
        "review_decision",
    )
    return {
        key: value
        for key in keys
        if isinstance((value := artifacts.get(key)), str) and value
    }


def _promotion_review_template_guidance(
    decision: str,
    *,
    suggested: object,
) -> dict[str, object]:
    return {
        "accepted_for_promotion": decision in {"accepted", "corrected"},
        "matches_suggested_decision": decision == suggested,
        "requires_reviewer": True,
        "requires_reason": True,
        "requires_correction_notes": decision == "corrected",
        "requires_corrected_artifacts": decision == "corrected",
    }


def _suggested_promotion_review_decision(
    review: dict[str, object],
    summary: dict[str, object],
) -> str:
    decision = review.get("decision")
    if decision == "accepted":
        return "accepted"
    if decision == "manual_review":
        return "deferred"
    if decision == "rejected":
        return "rejected"
    if summary.get("decision") == "deferred":
        return "deferred"
    return "rejected"


def _promotion_issue_tags(promotion: dict[str, object]) -> list[str]:
    issues = promotion.get("current_issues", [])
    if not isinstance(issues, list):
        return []
    return sorted({str(issue) for issue in issues if isinstance(issue, str) and issue})


def _review_decision_failed_gates(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    failed: list[dict[str, object]] = []
    for gate in value:
        if not isinstance(gate, dict) or gate.get("ok", False):
            continue
        failed.append(
            {
                "id": gate.get("id", "n/a"),
                "gate_type": gate.get("gate_type", "n/a"),
                "severity": gate.get("severity", "red"),
                "reason": gate.get("reason", "n/a"),
            }
        )
    return failed


def _review_decision_list(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def _write_manifest_promotion_state(
    manifest_path: Path,
    case_result: dict[str, Any],
) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        return
    artifacts = case_result.get("artifacts", {})
    artifacts = artifacts if isinstance(artifacts, dict) else {}
    promotion_artifacts: dict[str, object] = {
        key: artifacts[key]
        for key in (
            "promoted_svg",
            "fallback_svg",
            "promotion_export",
            "promotion_regions",
            "promotion_review",
            "editability_review",
            "review_decision",
        )
        if key in artifacts
    }
    review_templates = artifacts.get("review_templates")
    if isinstance(review_templates, dict):
        promotion_artifacts["review_templates"] = {
            str(decision): str(path)
            for decision, path in sorted(review_templates.items())
            if isinstance(decision, str) and isinstance(path, str)
        }
    manifest = _manifest_with_promotion_state(
        manifest,
        case_result,
        promotion_artifacts=promotion_artifacts,
    )
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _manifest_with_promotion_state(
    manifest: dict[str, Any],
    case_result: dict[str, Any],
    *,
    promotion_artifacts: dict[str, object] | None = None,
) -> dict[str, Any]:
    manifest = deepcopy(manifest)
    metrics = case_result.get("metrics")
    if isinstance(metrics, dict):
        manifest["metrics"] = metrics
    review = case_result.get("editability_review")
    if isinstance(review, dict):
        manifest["editability_review"] = review
    decision = case_result.get("review_decision")
    if isinstance(decision, dict):
        manifest["review_decision"] = decision
    regions = case_result.get("promotion_regions", [])
    regions = regions if isinstance(regions, list) else []
    gates = case_result.get("promotion_gates", [])
    gates = gates if isinstance(gates, list) else []
    manifest["promotion"] = {
        "case_id": case_result.get("id"),
        "summary": case_result.get("promotion_summary", {}),
        "regions": regions,
        "gates": gates,
        "artifacts": promotion_artifacts or {},
    }
    anchors = manifest.get("anchors", [])
    if isinstance(anchors, list):
        _annotate_manifest_anchor_promotion(anchors, regions)
    return manifest


def _annotate_manifest_anchor_promotion(
    anchors: list[object],
    regions: list[object],
) -> None:
    region_refs_by_index: dict[int, list[dict[str, object]]] = {}
    for region in regions:
        if not isinstance(region, dict):
            continue
        indexes = region.get("selected_anchor_indexes", [])
        if not isinstance(indexes, list):
            continue
        for index in indexes:
            if not isinstance(index, int):
                continue
            region_refs_by_index.setdefault(index, []).append(
                {
                    "region_id": region.get("id"),
                    "state": region.get("state"),
                    "gate_id": region.get("gate_id"),
                    "reason": region.get("reason"),
                }
            )
    for index, anchor in enumerate(anchors):
        if not isinstance(anchor, dict):
            continue
        refs = region_refs_by_index.get(index, [])
        anchor["promotion_regions"] = refs
        anchor["promotion_state"] = _anchor_promotion_state(refs)


def _anchor_promotion_state(refs: list[dict[str, object]]) -> str:
    states = {str(ref.get("state")) for ref in refs}
    if "promoted" in states:
        return "promoted"
    if "rejected" in states:
        return "rejected"
    if "deferred" in states:
        return "deferred"
    return "fallback"


def _promotion_svg_metadata(
    manifest: dict[str, Any],
    anchor_indexes: list[int],
) -> list[dict[str, object]]:
    anchors = manifest.get("anchors", [])
    anchors = anchors if isinstance(anchors, list) else []
    review_decision = manifest.get("review_decision")
    review_decision = review_decision if isinstance(review_decision, dict) else {}
    promotion = manifest.get("promotion")
    promotion = promotion if isinstance(promotion, dict) else {}
    artifacts = promotion.get("artifacts")
    artifacts = artifacts if isinstance(artifacts, dict) else {}
    metadata: list[dict[str, object]] = []
    for index in anchor_indexes:
        anchor = anchors[index] if 0 <= index < len(anchors) else {}
        anchor = anchor if isinstance(anchor, dict) else {}
        anchor_id = str(anchor.get("id") or f"anchor-{index:04d}")
        item: dict[str, object] = {
            "id": _promotion_svg_node_id(anchor_id, index=index),
            "data-morphea-anchor-id": anchor_id,
            "data-anchor-index": index,
            "data-promotion-state": str(anchor.get("promotion_state") or "fallback"),
        }
        region_ids = _promotion_anchor_region_ids(anchor)
        if region_ids:
            item["data-promotion-regions"] = " ".join(region_ids)
        decision = review_decision.get("decision")
        if isinstance(decision, str) and decision:
            item["data-review-decision"] = decision
        case_id = review_decision.get("case_id") or promotion.get("case_id")
        if isinstance(case_id, str) and case_id:
            item["data-review-case-id"] = case_id
        review_artifact = artifacts.get("review_decision")
        if isinstance(review_artifact, str) and review_artifact:
            item["data-review-decision-artifact"] = review_artifact
        metadata.append(item)
    return metadata


def _promotion_anchor_region_ids(anchor: dict[str, object]) -> list[str]:
    refs = anchor.get("promotion_regions")
    if not isinstance(refs, list):
        return []
    region_ids: list[str] = []
    for ref in refs:
        if not isinstance(ref, dict):
            continue
        region_id = ref.get("region_id")
        if isinstance(region_id, str) and region_id and region_id not in region_ids:
            region_ids.append(region_id)
    return region_ids


def _promotion_svg_node_id(anchor_id: str, *, index: int) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.:-]+", "-", anchor_id).strip("-")
    if not slug:
        slug = f"anchor-{index:04d}"
    return f"morphea-anchor-{index:04d}-{slug}"


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
    region_overlay_path = run_dir / "region-overlay.png"
    contact_sheet_path = run_dir / "contact-sheet.png"

    render_background = "#ffffff"
    svg_text = run.svg_path.read_text(encoding="utf-8")
    svg_render = rasterized_svg_image(svg_text, background=render_background).convert(
        "RGBA"
    )
    svg_render.save(svg_render_path)
    with Image.open(run.input_path) as source_image:
        source = source_image.convert("RGBA")
    with Image.open(run.preview_path) as preview_image:
        preview = preview_image.convert("RGBA")
    diff = _visual_diff_image(
        _flatten_visual_audit_source(source, render_background),
        svg_render,
    )
    diff.save(diff_path)
    anchor_overlay = _anchor_overlay_image(source, manifest)
    anchor_overlay.save(anchor_overlay_path)
    region_overlay = _region_overlay_image(source, promotion_gates)
    region_overlay.save(region_overlay_path)
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
                    "regions",
                    region_overlay,
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
        "region_overlay": str(run_dir / "region-overlay.png"),
        "contact_sheet": str(run_dir / "contact-sheet.png"),
    }


def _flatten_visual_audit_source(source: Image.Image, background: str) -> Image.Image:
    backdrop = Image.new("RGBA", source.size, _visual_audit_rgba(background))
    return Image.alpha_composite(backdrop, source.convert("RGBA"))


def _visual_audit_rgba(background: str) -> tuple[int, int, int, int]:
    value = background.strip()
    if not value.startswith("#") or len(value) not in {7, 9}:
        return (255, 255, 255, 255)
    red = int(value[1:3], 16)
    green = int(value[3:5], 16)
    blue = int(value[5:7], 16)
    alpha = int(value[7:9], 16) if len(value) == 9 else 255
    return (red, green, blue, alpha)


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


def _region_overlay_image(source: Image.Image, promotion_gates: object) -> Image.Image:
    base = source.convert("RGB")
    softened = Image.blend(base, Image.new("RGB", base.size, "white"), 0.25)
    overlay = softened.convert("RGBA")
    draw = ImageDraw.Draw(overlay, "RGBA")
    if not isinstance(promotion_gates, list):
        draw.text((8, 8), "no region gates", fill=(50, 50, 50, 220))
        return overlay.convert("RGB")
    region_gates = [
        gate
        for gate in promotion_gates
        if isinstance(gate, dict)
        and isinstance(gate.get("evidence"), dict)
        and _parse_overlay_bounds(gate["evidence"].get("bounds")) is not None
    ]
    if not region_gates:
        draw.text((8, 8), "no region gates", fill=(50, 50, 50, 220))
        return overlay.convert("RGB")
    line_width = max(2, round(max(overlay.size) / 240))
    for index, gate in enumerate(region_gates[:24]):
        evidence = gate["evidence"]
        if not isinstance(evidence, dict):
            continue
        bounds = _parse_overlay_bounds(evidence.get("bounds"))
        if bounds is None:
            continue
        color = _region_overlay_color(gate)
        fill = (color[0], color[1], color[2], 36)
        draw.rectangle(bounds, fill=fill, outline=color, width=line_width)
        label = _region_overlay_label(gate)
        text_x = max(0, min(bounds[0], overlay.width - 80))
        text_y = max(0, bounds[1] - 13)
        if index < 12:
            draw.text((text_x, text_y), label, fill=color)
    if len(region_gates) > 24:
        draw.text(
            (8, 8),
            f"showing 24/{len(region_gates)} regions",
            fill=(45, 45, 45, 220),
        )
    return overlay.convert("RGB")


def _region_overlay_color(gate: dict[str, object]) -> tuple[int, int, int, int]:
    if gate.get("ok", False):
        return (35, 130, 75, 255)
    if gate.get("severity") == "yellow":
        return (180, 120, 20, 255)
    return (180, 45, 45, 255)


def _region_overlay_label(gate: dict[str, object]) -> str:
    severity = "ok" if gate.get("ok", False) else str(gate.get("severity", "red"))
    gate_id = str(gate.get("id", "region"))
    parts = gate_id.split("-")
    short_id = "-".join(parts[-2:]) if len(parts) >= 2 else gate_id
    return f"{severity}:{short_id}"


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
    if "kind" in expectation:
        expectation_type = expectation.get("kind")
        label = "kind"
    elif "kinds" in expectation:
        expectation_type = ",".join(str(kind) for kind in expectation.get("kinds", []))
        label = "kinds"
    else:
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


def _fmt_pipeline_quality(case: dict[str, Any]) -> str:
    label = case.get("pipeline_quality_label")
    if not isinstance(label, str):
        label = _pipeline_quality_label(case)
    return f"`{label}`" if label is not None else "n/a"


def _attach_pipeline_quality_label(case: dict[str, Any]) -> None:
    label = _pipeline_quality_label(case)
    if label is not None:
        case["pipeline_quality_label"] = label


def _pipeline_quality_label(case: dict[str, Any]) -> str | None:
    summary = case.get("promotion_summary")
    if isinstance(summary, dict):
        decision = summary.get("decision")
        red_count = _safe_int(summary.get("red_gate_count"))
        yellow_count = _safe_int(summary.get("yellow_gate_count"))
        if decision == "rejected" or red_count > 0:
            return "red"
        if decision == "deferred" or yellow_count > 0:
            return "yellow"
        if decision == "promoted":
            return "green"
    status = case.get("status")
    if status == "missing_source":
        return "red"
    if status == "checked" and case.get("ok") is True:
        return "green"
    if status == "checked" and case.get("ok") is False:
        return "red"
    return None


def _safe_int(value: object) -> int:
    if isinstance(value, int):
        return value
    return 0


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


def _fmt_promotion_regions(value: object) -> str:
    if not isinstance(value, list) or not value:
        return "n/a"
    counts = _counts(
        region.get("state")
        for region in value
        if isinstance(region, dict)
    )
    if not counts:
        return "n/a"
    return ", ".join(
        f"`{state}`={_fmt_markdown_value(counts[state])}"
        for state in sorted(counts)
    )


def _region_truth_rows(cases: object) -> list[str]:
    if not isinstance(cases, list):
        return []
    rows = []
    for case in _promotion_sorted_cases(cases):
        if not isinstance(case, dict):
            continue
        regions = {
            str(region.get("id")): region
            for region in case.get("promotion_regions", [])
            if isinstance(region, dict)
        }
        for gate in case.get("promotion_gates", []):
            if not isinstance(gate, dict):
                continue
            evidence = gate.get("evidence")
            if not isinstance(evidence, dict) or "bounds" not in evidence:
                continue
            gate_id = str(gate.get("id", "n/a"))
            region = regions.get(gate_id, {})
            rows.append(
                "| "
                f"`{case.get('id', 'n/a')}` | "
                f"`{gate_id}` | "
                f"`{region.get('state', 'n/a')}` | "
                f"`{gate.get('gate_type', 'n/a')}` | "
                f"{_fmt_region_bounds(evidence.get('bounds'))} | "
                f"{_fmt_region_expected(evidence)} | "
                f"{_fmt_region_actual(evidence)} | "
                f"{_fmt_region_layers(region)} | "
                f"{_fmt_region_topology(evidence)} | "
                f"{_fmt_region_visual(evidence)} |"
            )
    return rows


def _fmt_region_bounds(value: object) -> str:
    bounds = _parse_float_bounds(value)
    if bounds is None:
        return "n/a"
    return "`" + ",".join(_fmt_markdown_value(item) for item in bounds) + "`"


def _fmt_region_expected(evidence: dict[str, object]) -> str:
    parts = []
    expected = _fmt_markdown_list(evidence.get("expected_kinds"))
    if expected != "n/a":
        parts.append(f"kinds={expected}")
    forbidden = _fmt_markdown_list(evidence.get("forbidden_kinds"))
    if forbidden != "n/a":
        parts.append(f"forbidden={forbidden}")
    required_descriptors = _fmt_markdown_list(
        evidence.get("required_topology_descriptors")
    )
    if required_descriptors != "n/a":
        parts.append(f"requires={required_descriptors}")
    forbidden_descriptors = _fmt_markdown_list(
        evidence.get("forbidden_topology_descriptors")
    )
    if forbidden_descriptors != "n/a":
        parts.append(f"forbids={forbidden_descriptors}")
    min_iou = evidence.get("min_iou")
    if isinstance(min_iou, (int, float)):
        parts.append(f"min_iou={_fmt_markdown_value(min_iou)}")
    coverage = evidence.get("min_anchor_coverage")
    if isinstance(coverage, (int, float)):
        parts.append(f"min_coverage={_fmt_markdown_value(coverage)}")
    return ", ".join(parts) if parts else "n/a"


def _fmt_region_actual(evidence: dict[str, object]) -> str:
    candidate_rejections = evidence.get("candidate_rejections")
    rejected_count = (
        len(candidate_rejections) if isinstance(candidate_rejections, list) else 0
    )
    return (
        f"matching={_fmt_markdown_value(evidence.get('matching_count'))}, "
        f"selected={_fmt_markdown_value(evidence.get('selected_count'))}, "
        f"forbidden={_fmt_markdown_value(evidence.get('forbidden_count'))}, "
        f"rejected={_fmt_markdown_value(rejected_count)}"
    )


def _fmt_region_layers(region: object) -> str:
    if not isinstance(region, dict):
        return "n/a"
    roles = _fmt_markdown_list(region.get("layer_roles"))
    if roles == "n/a":
        roles = "`none`"
    kinds = _fmt_markdown_counts(region.get("selected_anchor_kind_counts"))
    if kinds == "n/a":
        kinds = "`none`"
    return (
        f"layers={_fmt_markdown_value(region.get('region_layer_count'))}, "
        f"structural={_fmt_markdown_value(region.get('structural_layer_count'))}, "
        f"roles={roles}, "
        f"kinds={kinds}"
    )


def _fmt_region_topology(evidence: dict[str, object]) -> str:
    summary = evidence.get("topology_summary")
    if not isinstance(summary, dict):
        return "n/a"
    failures = evidence.get("topology_failures")
    failure_text = _fmt_markdown_list(failures)
    return (
        f"closed={_fmt_markdown_value(summary.get('closed_anchor_count'))}, "
        f"open={_fmt_markdown_value(summary.get('open_anchor_count'))}, "
        f"holes={_fmt_markdown_value(summary.get('hole_count'))}, "
        f"cutouts={_fmt_markdown_value(summary.get('cutout_count'))}, "
        f"nested={_fmt_markdown_value(summary.get('nested_contour_count'))}, "
        f"descriptors={_fmt_markdown_list(summary.get('topology_descriptors'))}, "
        f"failures={failure_text}"
    )


def _fmt_region_visual(evidence: dict[str, object]) -> str:
    visual = evidence.get("visual_delta")
    if not isinstance(visual, dict):
        return "n/a"
    parts = []
    if "raster_l1_error" in visual:
        parts.append(f"l1={_fmt_markdown_value(visual.get('raster_l1_error'))}")
    if "raster_edge_error" in visual:
        parts.append(f"edge={_fmt_markdown_value(visual.get('raster_edge_error'))}")
    if "raster_alpha_error" in visual:
        parts.append(f"alpha={_fmt_markdown_value(visual.get('raster_alpha_error'))}")
    bounds = _fmt_region_bounds(visual.get("bounds"))
    if bounds != "n/a":
        parts.append(f"crop={bounds}")
    thresholds = evidence.get("visual_thresholds")
    if isinstance(thresholds, dict):
        l1_limit = thresholds.get("max_raster_l1_error")
        if isinstance(l1_limit, (int, float)):
            parts.append(f"max_l1={_fmt_markdown_value(l1_limit)}")
        edge_limit = thresholds.get("max_raster_edge_error")
        if isinstance(edge_limit, (int, float)):
            parts.append(f"max_edge={_fmt_markdown_value(edge_limit)}")
    failures = _fmt_markdown_list(evidence.get("visual_failures"))
    if failures != "n/a":
        parts.append(f"failures={failures}")
    return ", ".join(parts) if parts else "n/a"


def _fmt_editability_components(value: object) -> str:
    if not isinstance(value, dict):
        return "n/a"
    keys = (
        "simple_shape_ratio",
        "fragmentation_penalty",
        "diagnostic_penalty",
        "generic_path_penalty",
        "unclipped_score",
        "clipped_score",
    )
    parts = [
        f"`{key}`={_fmt_markdown_value(value[key])}"
        for key in keys
        if key in value
    ]
    return ", ".join(parts) if parts else "n/a"


def _fmt_editability_v10_components(value: object) -> str:
    if not isinstance(value, dict):
        return "n/a"
    keys = (
        "shape_identity_confidence",
        "parameter_economy",
        "node_economy",
        "stroke_width_stability",
        "line_curve_smoothness",
        "topology_consistency",
        "grouping_quality",
        "fragmentation",
        "raster_fidelity",
        "provenance_confidence",
        "classifier_prior_agreement",
    )
    parts = []
    for key in keys:
        component = value.get(key)
        if not isinstance(component, dict):
            continue
        score = component.get("score")
        parts.append(f"`{key}`={_fmt_markdown_value(score)}")
    return ", ".join(parts) if parts else "n/a"


def _fmt_failed_components(value: object) -> str:
    if not isinstance(value, list) or not value:
        return "n/a"
    parts = []
    for item in value:
        if not isinstance(item, dict):
            continue
        component = item.get("id", "n/a")
        score = _fmt_markdown_value(item.get("score"))
        threshold = _fmt_markdown_value(item.get("threshold"))
        parts.append(f"`{component}` {score} < {threshold}")
    return ", ".join(parts) if parts else "n/a"


def _fmt_gate_blocked_components(value: object) -> str:
    if not isinstance(value, list) or not value:
        return "n/a"
    parts = []
    for item in value:
        if not isinstance(item, dict):
            continue
        gates = item.get("failed_gates", [])
        gate_text = (
            ", ".join(f"`{gate}`" for gate in gates)
            if isinstance(gates, list) and gates
            else "n/a"
        )
        parts.append(f"`{item.get('id', 'n/a')}` via {gate_text}")
    return ", ".join(parts) if parts else "n/a"


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
    has_kinds = _valid_expectation_kinds(expectation.get("kinds"))
    has_group_kind = isinstance(expectation.get("group_kind"), str)
    has_metric = isinstance(expectation.get("metric"), str)
    if sum((has_kind, has_kinds, has_group_kind, has_metric)) != 1:
        raise ValueError(
            f"case {case_id} expectation {expectation_id} must set kind, "
            "kinds, group_kind, or metric"
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


def _valid_expectation_kinds(value: object) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(item, str) and item for item in value)
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
    quality_policy = value.get("quality_label_review_policy")
    if quality_policy is not None:
        if quality_policy not in PROMOTION_QUALITY_LABEL_REVIEW_POLICIES:
            allowed = ", ".join(sorted(PROMOTION_QUALITY_LABEL_REVIEW_POLICIES))
            raise ValueError(
                f"case {case_id} promotion quality_label_review_policy must be "
                f"one of: {allowed}"
            )
        if label != "red":
            raise ValueError(
                f"case {case_id} promotion quality_label_review_policy requires "
                "current_quality_label red"
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
    structure_thresholds = value.get("structure_thresholds")
    if structure_thresholds is not None:
        _validate_promotion_structure_thresholds(case_id, structure_thresholds)


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
        min_iou_default = (
            0.0 if gate.get("min_anchor_coverage") is not None else 0.1
        )
        min_iou = gate.get("min_iou", min_iou_default)
        if not isinstance(min_iou, (int, float)) or min_iou < 0 or min_iou > 1:
            raise ValueError(
                f"case {case_id} promotion region gate {gate_id} min_iou "
                "must be between 0 and 1"
            )
        min_anchor_coverage = gate.get("min_anchor_coverage")
        if min_anchor_coverage is not None and (
            not isinstance(min_anchor_coverage, (int, float))
            or min_anchor_coverage < 0
            or min_anchor_coverage > 1
        ):
            raise ValueError(
                f"case {case_id} promotion region gate {gate_id} "
                "min_anchor_coverage must be between 0 and 1"
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
        _validate_region_topology_descriptor_list(
            case_id,
            gate_id,
            gate,
            "required_topology_descriptors",
        )
        _validate_region_topology_descriptor_list(
            case_id,
            gate_id,
            gate,
            "forbidden_topology_descriptors",
        )
        _validate_region_visual_thresholds(case_id, gate_id, gate)
        description = gate.get("description")
        if description is not None and (
            not isinstance(description, str) or not description
        ):
            raise ValueError(
                f"case {case_id} promotion region gate {gate_id} "
                "description must be a string"
            )


def _validate_region_visual_thresholds(
    case_id: str,
    gate_id: str,
    gate: dict[str, Any],
) -> None:
    for key in sorted(PROMOTION_REGION_VISUAL_THRESHOLD_KEYS):
        threshold = gate.get(key)
        if threshold is None:
            continue
        if not isinstance(threshold, (int, float)) or threshold < 0:
            raise ValueError(
                f"case {case_id} promotion region gate {gate_id} {key} "
                "must be a non-negative number"
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


def _validate_region_topology_descriptor_list(
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
    invalid = [
        item for item in values if item not in PROMOTION_REGION_TOPOLOGY_DESCRIPTORS
    ]
    if invalid:
        allowed = ", ".join(sorted(PROMOTION_REGION_TOPOLOGY_DESCRIPTORS))
        raise ValueError(
            f"case {case_id} promotion region gate {gate_id} {key} "
            f"contains unsupported descriptor {invalid[0]}; "
            f"must be one of: {allowed}"
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
        ("min_nested_contours", "max_nested_contours"),
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


def _validate_promotion_structure_thresholds(case_id: str, value: Any) -> None:
    if not isinstance(value, dict):
        raise ValueError(
            f"case {case_id} promotion structure_thresholds must be an object"
        )
    configured = False
    fragmentation = value.get("max_fragmentation_penalty")
    if fragmentation is not None:
        configured = True
        if not isinstance(fragmentation, (int, float)) or fragmentation < 0:
            raise ValueError(
                f"case {case_id} promotion structure_thresholds "
                "max_fragmentation_penalty must be a non-negative number"
            )
    layer_count = value.get("max_layer_count")
    if layer_count is not None:
        configured = True
        if not isinstance(layer_count, int) or layer_count < 0:
            raise ValueError(
                f"case {case_id} promotion structure_thresholds "
                "max_layer_count must be a non-negative integer"
            )
    structural_layer_count = value.get("max_structural_layer_count")
    if structural_layer_count is not None:
        configured = True
        if not isinstance(structural_layer_count, int) or structural_layer_count < 0:
            raise ValueError(
                f"case {case_id} promotion structure_thresholds "
                "max_structural_layer_count must be a non-negative integer"
            )
    non_structural_roles = value.get("non_structural_layer_roles")
    if non_structural_roles is not None and (
        not isinstance(non_structural_roles, list)
        or not all(isinstance(item, str) and item for item in non_structural_roles)
    ):
        raise ValueError(
            f"case {case_id} promotion structure_thresholds "
            "non_structural_layer_roles must be a string array"
        )
    if not configured:
        allowed = ", ".join(sorted(PROMOTION_STRUCTURE_THRESHOLD_KEYS))
        raise ValueError(
            f"case {case_id} promotion structure_thresholds must set "
            f"at least one of: {allowed}"
        )
    severity = value.get("severity", "red")
    if severity not in PROMOTION_GATE_SEVERITIES:
        allowed = ", ".join(sorted(PROMOTION_GATE_SEVERITIES))
        raise ValueError(
            f"case {case_id} promotion structure_thresholds severity "
            f"must be one of: {allowed}"
        )
    description = value.get("description")
    if description is not None and (
        not isinstance(description, str) or not description
    ):
        raise ValueError(
            f"case {case_id} promotion structure_thresholds description "
            "must be a string"
        )
