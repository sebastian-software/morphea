"""Backend/runtime status aggregation for productized research runs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from curve.mlx_classifier import mlx_classifier_runtime_status
from curve.refinement import available_refinement_backends
from curve.segmenters import (
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
        "# Curve Runtime Status",
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
