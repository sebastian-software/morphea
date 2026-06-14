"""Backend/runtime status aggregation for productized research runs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from morphea.mlx_classifier import mlx_classifier_runtime_status
from morphea.refinement import available_refinement_backends
from morphea.segmenters import (
    FlatColorSegmenter,
    MlxSamSegmenter,
    segmenter_backend_status,
)


AVAILABLE_STATUSES = {
    "available",
    "json_adapter_available",
    "mlx_sam_package_available",
    "trained",
}
BACKEND_DIAGNOSTIC_FIELDS = (
    "adapter",
    "model_path",
    "model_exists",
    "model_sidecar_path",
    "model_sidecar_exists",
    "model_configured",
    "package_available",
    "sam_package_available",
    "score_threshold",
    "max_masks",
    "timeout_seconds",
    "max_component_area",
    "prompt_strategy",
    "prompt_min_area",
    "prompt_color_tolerance",
    "prompt_max_size",
    "prompt_max_colors",
    "core_available",
    "backend_version",
    "autograd_available",
    "autograd_reason",
    "missing_autograd_symbols",
    "training_implementation",
)


def collect_runtime_status(
    *,
    output: str | Path | None = None,
    markdown: str | Path | None = None,
    mlx_sam_model_path: str | Path | None = None,
) -> dict[str, Any]:
    """Collect machine-readable status for optional and baseline backends."""

    mlx_sam = MlxSamSegmenter(
        model_path=str(mlx_sam_model_path) if mlx_sam_model_path is not None else None
    )
    result: dict[str, Any] = {
        "schema_version": 1,
        "segmenters": {
            "flat_color": segmenter_backend_status(FlatColorSegmenter()),
            "mlx_sam": segmenter_backend_status(mlx_sam),
        },
        "classifiers": {
            "centroid": {
                "backend": "centroid",
                "backend_available": True,
                "status": "available",
                "reason": None,
                "training_implementation": "centroid_baseline",
            },
            "mlx": mlx_classifier_runtime_status(),
        },
        "refinement": available_refinement_backends(),
    }
    result["blocked_backends"] = _blocked_backend_rows(result)
    result["blocked_capabilities"] = _blocked_capability_rows(result)

    if output is not None:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(result, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    if markdown is not None:
        markdown_path = Path(markdown)
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(render_runtime_status_markdown(result), encoding="utf-8")
    return result


def render_runtime_status_markdown(status: dict[str, Any]) -> str:
    rows = _status_rows(status)
    lines = [
        "# Morphēa Runtime Status",
        "",
        "| Area | Backend | Status | Available | Reason | Next action |",
        "| --- | --- | --- | ---: | --- | --- |",
    ]
    for row in rows:
        lines.append(
            "| "
            f"{row['area']} | "
            f"`{row['backend']}` | "
            f"`{row['status']}` | "
            f"{str(row['available']).lower()} | "
            f"{row['reason'] or 'n/a'} | "
            f"{row['next_action'] or 'n/a'} |"
        )
    diagnostics = _backend_diagnostic_rows(status)
    if diagnostics:
        lines.extend(
            [
                "",
                "## Backend Diagnostics",
                "",
                "| Area | Backend | Field | Value |",
                "| --- | --- | --- | --- |",
            ]
        )
        for row in diagnostics:
            lines.append(
                "| "
                f"{row['area']} | "
                f"`{row['backend']}` | "
                f"`{row['field']}` | "
                f"{_markdown_code(row['value'])} |"
            )
    blocked = status.get("blocked_backends", [])
    if not isinstance(blocked, list):
        blocked = []
    lines.extend(["", "## Blocked Backends", ""])
    if blocked:
        for row in blocked:
            if not isinstance(row, dict):
                continue
            lines.append(
                "- "
                f"{row.get('area', 'unknown')}/"
                f"{row.get('backend', 'unknown')}: "
                f"{row.get('status', 'unknown')} - "
                f"{_reason_with_action(row)}"
            )
    else:
        lines.append("n/a")
    blocked_capabilities = status.get("blocked_capabilities", [])
    if not isinstance(blocked_capabilities, list):
        blocked_capabilities = []
    lines.extend(["", "## Blocked Capabilities", ""])
    if blocked_capabilities:
        for row in blocked_capabilities:
            if not isinstance(row, dict):
                continue
            lines.append(
                "- "
                f"{row.get('area', 'unknown')}/"
                f"{row.get('backend', 'unknown')}/"
                f"{row.get('capability', 'unknown')}: "
                f"{row.get('status', 'unknown')} - "
                f"{_reason_with_action(row)}"
            )
    else:
        lines.append("n/a")
    return "\n".join(lines) + "\n"


def _status_rows(status: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    segmenters = status.get("segmenters", {})
    if isinstance(segmenters, dict):
        for backend, detail in sorted(segmenters.items()):
            rows.append(_row("segmenter", backend, detail))
    classifiers = status.get("classifiers", {})
    if isinstance(classifiers, dict):
        for backend, detail in sorted(classifiers.items()):
            rows.append(_row("classifier", backend, detail))
    refinement = status.get("refinement", {})
    details = refinement.get("details", {}) if isinstance(refinement, dict) else {}
    if isinstance(details, dict):
        for backend, detail in sorted(details.items()):
            rows.append(_row("refinement", backend, detail))
    return rows


def _backend_diagnostic_rows(status: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    segmenters = status.get("segmenters", {})
    if isinstance(segmenters, dict):
        for backend, detail in sorted(segmenters.items()):
            rows.extend(_diagnostic_rows("segmenter", backend, detail))
    classifiers = status.get("classifiers", {})
    if isinstance(classifiers, dict):
        for backend, detail in sorted(classifiers.items()):
            rows.extend(_diagnostic_rows("classifier", backend, detail))
    refinement = status.get("refinement", {})
    details = refinement.get("details", {}) if isinstance(refinement, dict) else {}
    if isinstance(details, dict):
        for backend, detail in sorted(details.items()):
            rows.extend(_diagnostic_rows("refinement", backend, detail))
    return rows


def _diagnostic_rows(
    area: str,
    backend: str,
    detail: object,
) -> list[dict[str, Any]]:
    if not isinstance(detail, dict):
        return []
    rows = []
    for field in BACKEND_DIAGNOSTIC_FIELDS:
        if field not in detail or detail[field] is None:
            continue
        rows.append(
            {
                "area": area,
                "backend": backend,
                "field": field,
                "value": detail[field],
            }
        )
    return rows


def _blocked_backend_rows(status: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        row
        for row in _status_rows(status)
        if not row["available"] or row["status"] not in AVAILABLE_STATUSES
    ]


def _blocked_capability_rows(status: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        row
        for row in _capability_rows(status)
        if not row["available"] or row["status"] not in AVAILABLE_STATUSES
    ]


def _capability_rows(status: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    segmenters = status.get("segmenters", {})
    if isinstance(segmenters, dict):
        for backend, detail in sorted(segmenters.items()):
            rows.extend(_backend_capability_rows("segmenter", backend, detail))
    classifiers = status.get("classifiers", {})
    if isinstance(classifiers, dict):
        for backend, detail in sorted(classifiers.items()):
            rows.extend(_backend_capability_rows("classifier", backend, detail))
    refinement = status.get("refinement", {})
    details = refinement.get("details", {}) if isinstance(refinement, dict) else {}
    if isinstance(details, dict):
        for backend, detail in sorted(details.items()):
            rows.extend(_backend_capability_rows("refinement", backend, detail))
    return rows


def _backend_capability_rows(
    area: str,
    backend: str,
    detail: object,
) -> list[dict[str, Any]]:
    if not isinstance(detail, dict):
        return []
    capabilities = detail.get("capabilities", {})
    if not isinstance(capabilities, dict):
        return []
    rows: list[dict[str, Any]] = []
    for capability, capability_detail in sorted(capabilities.items()):
        if not isinstance(capability_detail, dict):
            capability_detail = {}
        rows.append(
            {
                "area": area,
                "backend": backend,
                "capability": capability,
                "status": capability_detail.get("status", "unknown"),
                "available": bool(capability_detail.get("available", False)),
                "reason": capability_detail.get("reason"),
                "next_action": capability_detail.get("next_action"),
            }
        )
    return rows


def _row(area: str, backend: str, detail: object) -> dict[str, Any]:
    if not isinstance(detail, dict):
        detail = {}
    return {
        "area": area,
        "backend": backend,
        "status": detail.get("status", "unknown"),
        "available": bool(detail.get("backend_available", False)),
        "reason": detail.get("reason"),
        "next_action": detail.get("next_action"),
    }


def _reason_with_action(row: dict[str, Any]) -> str:
    reason = row.get("reason") or "n/a"
    next_action = row.get("next_action")
    if not next_action:
        return str(reason)
    return f"{reason}; next action: {next_action}"


def _markdown_code(value: object) -> str:
    if isinstance(value, bool):
        text = str(value).lower()
    else:
        text = str(value)
    escaped = text.replace("|", "\\|").replace("`", "'")
    return f"`{escaped}`"
