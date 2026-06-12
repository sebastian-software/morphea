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


AVAILABLE_STATUSES = {"available", "json_adapter_available", "trained"}


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
        "| Area | Backend | Status | Available | Reason |",
        "| --- | --- | --- | ---: | --- |",
    ]
    for row in rows:
        lines.append(
            "| "
            f"{row['area']} | "
            f"`{row['backend']}` | "
            f"`{row['status']}` | "
            f"{str(row['available']).lower()} | "
            f"{row['reason'] or 'n/a'} |"
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
                f"{row.get('reason') or 'n/a'}"
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
                f"{row.get('reason') or 'n/a'}"
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
    }
