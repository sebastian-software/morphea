"""Segment proposal interfaces for classical and future MLX segmenters."""

from __future__ import annotations

import importlib.util
import json
from dataclasses import dataclass, replace
from pathlib import Path
from time import perf_counter
from typing import Protocol

from curve.anchors import choose_best_anchor, quality_metric_error
from curve.detection import primitive_candidates_for_component
from curve.images import ColorMask, flat_color_masks_from_image
from curve.masks import MaskComponent, connected_components


@dataclass(frozen=True)
class SegmentProposal:
    id: str
    source: str
    confidence: float
    color: str | None
    bounds: tuple[int, int, int, int]
    area: int
    status: str = "proposed"
    downstream_status: str = "pending"
    rejection_reason: str | None = None
    anchor_kind: str | None = None
    anchor_metrics: dict[str, float] | None = None
    anchor_parameter_count: int | None = None
    anchor_reserved: bool = False
    reservation_reason: str | None = None
    reservation_bounds: tuple[int, int, int, int] | None = None
    anchor_quality_error: float | None = None
    downstream_decision_reason: str | None = None


class Segmenter(Protocol):
    source: str

    def propose(self, image_path: str | Path) -> tuple[SegmentProposal, ...]:
        """Return segment proposals for an image."""


@dataclass(frozen=True)
class FlatColorSegmenter:
    background: str | list[int] | tuple[int, int, int] | None = None
    min_area: int = 8
    color_tolerance: float = 0.0
    max_size: int | None = None
    max_colors: int | None = None
    max_component_area: int | None = None
    split_components: bool = True
    source: str = "flat_color"

    def propose(self, image_path: str | Path) -> tuple[SegmentProposal, ...]:
        masks = flat_color_masks_from_image(
            image_path,
            background=self.background,
            min_area=self.min_area,
            color_tolerance=self.color_tolerance,
            max_size=self.max_size,
            max_colors=self.max_colors,
        )
        proposals: list[SegmentProposal] = []
        for color_mask in masks:
            if self.split_components:
                for component in connected_components(
                    color_mask.mask,
                    min_area=self.min_area,
                ):
                    proposals.append(
                        _proposal_from_component(
                            len(proposals),
                            self.source,
                            color_mask.color,
                            component,
                            max_component_area=self.max_component_area,
                        )
                    )
                continue
            proposals.append(
                _proposal_from_color_mask(
                    len(proposals),
                    self.source,
                    color_mask,
                    max_component_area=self.max_component_area,
                )
            )
        return tuple(proposals)


@dataclass(frozen=True)
class MlxSamSegmenter:
    model_path: str | None = None
    score_threshold: float = 0.0
    max_masks: int | None = None
    timeout_seconds: float | None = None
    source: str = "mlx_sam"

    def propose(self, image_path: str | Path) -> tuple[SegmentProposal, ...]:
        status = mlx_sam_runtime_status(self)
        if status["status"] == "json_adapter_available":
            return _json_adapter_proposals(self, image_path)
        details = []
        details.append(f"status={status['status']}")
        if self.model_path is not None:
            details.append(f"model_path={self.model_path}")
        if self.max_masks is not None:
            details.append(f"max_masks={self.max_masks}")
        if self.timeout_seconds is not None:
            details.append(f"timeout_seconds={self.timeout_seconds}")
        suffix = f" ({', '.join(details)})" if details else ""
        msg = f"MLX SAM segmenter is not installed/configured yet{suffix}"
        raise RuntimeError(msg)


def is_mlx_runtime_available() -> bool:
    return importlib.util.find_spec("mlx") is not None


def mlx_sam_runtime_status(segmenter: MlxSamSegmenter) -> dict[str, object]:
    package_available = is_mlx_runtime_available()
    model_configured = segmenter.model_path is not None
    model_path = (
        Path(segmenter.model_path).expanduser()
        if segmenter.model_path is not None
        else None
    )
    model_exists = (
        model_path.exists()
        if model_path is not None
        else False
    )
    json_adapter_available = (
        model_path is not None
        and model_exists
        and model_path.suffix.lower() == ".json"
    )
    if json_adapter_available:
        status = "json_adapter_available"
        reason = None
    elif not package_available:
        status = "not_installed"
        reason = "MLX runtime package is not installed"
    elif not model_configured:
        status = "not_configured"
        reason = "MLX SAM model path is not configured"
    elif not model_exists:
        status = "model_missing"
        reason = "MLX SAM model path does not exist"
    else:
        status = "adapter_pending"
        reason = "MLX SAM proposal adapter is not wired yet"
    return {
        "source": segmenter.source,
        "backend_available": json_adapter_available,
        "status": status,
        "reason": reason,
        "package_available": package_available,
        "model_configured": model_configured,
        "model_exists": model_exists,
        "model_path": segmenter.model_path,
        "adapter": "json_proposals" if json_adapter_available else None,
        "score_threshold": segmenter.score_threshold,
        "max_masks": segmenter.max_masks,
        "timeout_seconds": segmenter.timeout_seconds,
    }


def segmenter_backend_status(
    segmenter: Segmenter,
) -> dict[str, object]:
    if isinstance(segmenter, FlatColorSegmenter):
        return {
            "source": segmenter.source,
            "backend_available": True,
            "status": "available",
            "reason": None,
        }
    if isinstance(segmenter, MlxSamSegmenter):
        return mlx_sam_runtime_status(segmenter)
    return {
        "source": getattr(segmenter, "source", "unknown"),
        "backend_available": False,
        "status": "unknown",
        "reason": "unrecognized segmenter implementation",
    }


def proposals_to_manifest(
    proposals: tuple[SegmentProposal, ...],
) -> list[dict[str, object]]:
    return [
        {
            "id": proposal.id,
            "source": proposal.source,
            "confidence": proposal.confidence,
            "color": proposal.color,
            "bounds": list(proposal.bounds),
            "area": proposal.area,
            "status": proposal.status,
            "downstream_status": proposal.downstream_status,
            "rejection_reason": proposal.rejection_reason,
            "anchor_kind": proposal.anchor_kind,
            "anchor_metrics": proposal.anchor_metrics,
            "anchor_parameter_count": proposal.anchor_parameter_count,
            "anchor_reserved": proposal.anchor_reserved,
            "reservation_reason": proposal.reservation_reason,
            "reservation_bounds": (
                list(proposal.reservation_bounds)
                if proposal.reservation_bounds is not None
                else None
            ),
            "anchor_quality_error": proposal.anchor_quality_error,
            "downstream_decision_reason": proposal.downstream_decision_reason,
        }
        for proposal in proposals
    ]


def segment_proposal_summary(
    proposals: tuple[SegmentProposal, ...],
    proposal_groups: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    proposal_groups = proposal_groups or []
    return {
        "status_counts": _counts(proposal.status for proposal in proposals),
        "downstream_status_counts": _counts(
            proposal.downstream_status for proposal in proposals
        ),
        "anchor_kind_counts": _counts(
            proposal.anchor_kind
            for proposal in proposals
            if proposal.anchor_kind is not None
        ),
        "reserved_anchor_count": sum(
            1 for proposal in proposals if proposal.anchor_reserved
        ),
        "downstream_decision_reason_counts": _counts(
            proposal.downstream_decision_reason
            for proposal in proposals
            if proposal.downstream_decision_reason is not None
        ),
        "proposal_group_counts": _counts(
            group.get("kind")
            for group in proposal_groups
            if isinstance(group, dict) and group.get("kind") is not None
        ),
    }


def segment_proposal_groups(
    proposals: tuple[SegmentProposal, ...],
) -> list[dict[str, object]]:
    """Group simple proposal anchors into higher-level editable structures."""

    tile_group = _tile_grid_group(proposals)
    return [tile_group] if tile_group is not None else []


def gate_segment_proposals(
    proposals: tuple[SegmentProposal, ...],
    *,
    max_anchor_quality_error: float | None = 1.0,
    require_reserved_anchor: bool = False,
) -> tuple[SegmentProposal, ...]:
    """Accept or reject pending proposals using anchor geometry quality."""

    return tuple(
        _gate_segment_proposal(
            proposal,
            max_anchor_quality_error=max_anchor_quality_error,
            require_reserved_anchor=require_reserved_anchor,
        )
        for proposal in proposals
    )


def render_segment_proposal_markdown(manifest: dict[str, object]) -> str:
    """Render a scan-friendly segment proposal report."""

    summary = manifest.get("summary", {})
    if not isinstance(summary, dict):
        summary = {}
    backend = manifest.get("backend", {})
    if not isinstance(backend, dict):
        backend = {}
    lines = [
        "# Curve Segment Proposals",
        "",
        f"- Input: `{manifest.get('input', 'unknown')}`",
        f"- Source: `{backend.get('source', 'unknown')}`",
        f"- Backend status: `{backend.get('status', 'unknown')}`",
        f"- Proposal count: `{manifest.get('proposal_count', 0)}`",
        f"- Status counts: {_format_counts(summary.get('status_counts', {}))}",
        "- Downstream status counts: "
        f"{_format_counts(summary.get('downstream_status_counts', {}))}",
        "- Anchor kind counts: "
        f"{_format_counts(summary.get('anchor_kind_counts', {}))}",
        f"- Reserved anchors: `{summary.get('reserved_anchor_count', 0)}`",
        "- Decision reason counts: "
        f"{_format_counts(summary.get('downstream_decision_reason_counts', {}))}",
        "- Proposal group counts: "
        f"{_format_counts(summary.get('proposal_group_counts', {}))}",
        "",
        "| ID | Status | Downstream | Anchor | Quality | Reserved | Bounds | Reason |",
        "| --- | --- | --- | --- | ---: | ---: | --- | --- |",
    ]
    proposals = manifest.get("proposals", [])
    if not isinstance(proposals, list):
        proposals = []
    for proposal in proposals:
        if not isinstance(proposal, dict):
            continue
        lines.append(
            "| "
            f"`{proposal.get('id', 'unknown')}` | "
            f"`{proposal.get('status', 'unknown')}` | "
            f"`{proposal.get('downstream_status', 'unknown')}` | "
            f"`{proposal.get('anchor_kind') or 'n/a'}` | "
            f"{_format_float(proposal.get('anchor_quality_error'))} | "
            f"{str(bool(proposal.get('anchor_reserved', False))).lower()} | "
            f"`{_format_bounds(proposal.get('bounds'))}` | "
            f"{_proposal_reason(proposal)} |"
        )
    groups = manifest.get("proposal_groups", [])
    if isinstance(groups, list) and groups:
        lines.extend(
            [
                "",
                "## Proposal Groups",
                "",
                "| ID | Kind | Proposals | Rows | Columns | Occupancy |",
                "| --- | --- | ---: | ---: | ---: | ---: |",
            ]
        )
        for group in groups:
            if not isinstance(group, dict):
                continue
            metrics = group.get("metrics", {})
            if not isinstance(metrics, dict):
                metrics = {}
            lines.append(
                "| "
                f"`{group.get('id', 'unknown')}` | "
                f"`{group.get('kind', 'unknown')}` | "
                f"{len(_list_value(group.get('proposal_ids')))} | "
                f"{_format_float(metrics.get('row_count'))} | "
                f"{_format_float(metrics.get('column_count'))} | "
                f"{_format_float(metrics.get('grid_occupancy_ratio'))} |"
            )
    return "\n".join(lines) + "\n"


def _proposal_from_color_mask(
    index: int,
    source: str,
    color_mask: ColorMask,
    *,
    max_component_area: int | None,
) -> SegmentProposal:
    pixels = color_mask.mask.pixels
    xs = [x for x, _ in pixels]
    ys = [y for _, y in pixels]
    status = _proposal_status(len(pixels), max_component_area)
    downstream_status, rejection_reason = _downstream_status(status)
    return SegmentProposal(
        id=f"{source}-{index:04d}",
        source=source,
        confidence=1.0,
        color=color_mask.color,
        bounds=(min(xs), min(ys), max(xs), max(ys)),
        area=len(pixels),
        status=status,
        downstream_status=downstream_status,
        rejection_reason=rejection_reason,
    )


def _proposal_from_component(
    index: int,
    source: str,
    color: str,
    component: MaskComponent,
    *,
    max_component_area: int | None,
) -> SegmentProposal:
    status = _proposal_status(component.area, max_component_area)
    downstream_status, rejection_reason = _downstream_status(status)
    anchor_summary = (
        _primitive_anchor_summary(component)
        if downstream_status == "pending"
        else {}
    )
    return SegmentProposal(
        id=f"{source}-{index:04d}",
        source=source,
        confidence=1.0,
        color=color,
        bounds=component.bounds,
        area=component.area,
        status=status,
        downstream_status=downstream_status,
        rejection_reason=rejection_reason,
        **anchor_summary,
    )


def _json_adapter_proposals(
    segmenter: MlxSamSegmenter,
    image_path: str | Path,
) -> tuple[SegmentProposal, ...]:
    model_path = Path(str(segmenter.model_path)).expanduser()
    payload = json.loads(model_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("MLX SAM JSON adapter model must be a JSON object")
    proposals = payload.get("proposals", [])
    if not isinstance(proposals, list):
        raise ValueError("MLX SAM JSON adapter requires a proposals list")

    accepted: list[SegmentProposal] = []
    started_at = perf_counter()
    for item in proposals:
        if (
            segmenter.timeout_seconds is not None
            and perf_counter() - started_at >= segmenter.timeout_seconds
        ):
            break
        if not isinstance(item, dict):
            continue
        confidence = float(item.get("confidence", item.get("score", 1.0)))
        if confidence < segmenter.score_threshold:
            continue
        component = _json_adapter_component(item)
        if component is None:
            continue
        color = item.get("color")
        accepted.append(
            _proposal_from_adapter_component(
                len(accepted),
                segmenter.source,
                str(color) if isinstance(color, str) else None,
                component,
                confidence=confidence,
            )
        )
        if segmenter.max_masks is not None and len(accepted) >= segmenter.max_masks:
            break
    return tuple(accepted)


def _json_adapter_component(item: dict[str, object]) -> MaskComponent | None:
    mask_component = _json_adapter_mask_component(item)
    if mask_component is not None:
        return mask_component
    bounds = _json_adapter_bounds(item)
    if bounds is None:
        return None
    left, top, right, bottom = bounds
    pixels = {
        (x, y)
        for y in range(top, bottom + 1)
        for x in range(left, right + 1)
    }
    return MaskComponent(frozenset(pixels), bounds_hint=bounds)


def _json_adapter_mask_component(item: dict[str, object]) -> MaskComponent | None:
    mask = item.get("mask")
    origin_x = int(float(item.get("x", item.get("left", 0))))
    origin_y = int(float(item.get("y", item.get("top", 0))))
    rows: list[object]
    if isinstance(mask, dict):
        origin_x = int(float(mask.get("x", mask.get("left", origin_x))))
        origin_y = int(float(mask.get("y", mask.get("top", origin_y))))
        value = mask.get("rows", mask.get("data"))
        rows = value if isinstance(value, list) else []
    elif isinstance(mask, list):
        rows = mask
    else:
        return None

    pixels: set[tuple[int, int]] = set()
    for row_index, row in enumerate(rows):
        if isinstance(row, str):
            for column_index, value in enumerate(row):
                if value not in {".", "0", " ", "_"}:
                    pixels.add((origin_x + column_index, origin_y + row_index))
            continue
        if isinstance(row, list):
            for column_index, value in enumerate(row):
                if bool(value):
                    pixels.add((origin_x + column_index, origin_y + row_index))
    if not pixels:
        return None
    left = min(x for x, _ in pixels)
    top = min(y for _, y in pixels)
    right = max(x for x, _ in pixels)
    bottom = max(y for _, y in pixels)
    return MaskComponent(frozenset(pixels), bounds_hint=(left, top, right, bottom))


def _json_adapter_bounds(item: dict[str, object]) -> tuple[int, int, int, int] | None:
    bounds = item.get("bounds")
    if isinstance(bounds, list) and len(bounds) == 4:
        left, top, right, bottom = (int(float(value)) for value in bounds)
    else:
        bbox = item.get("bbox")
        if not isinstance(bbox, list) or len(bbox) != 4:
            return None
        left = int(float(bbox[0]))
        top = int(float(bbox[1]))
        right = left + int(float(bbox[2])) - 1
        bottom = top + int(float(bbox[3])) - 1
    if right < left or bottom < top:
        return None
    return left, top, right, bottom


def _proposal_from_adapter_component(
    index: int,
    source: str,
    color: str | None,
    component: MaskComponent,
    *,
    confidence: float,
) -> SegmentProposal:
    anchor_summary = _primitive_anchor_summary(component)
    return SegmentProposal(
        id=f"{source}-{index:04d}",
        source=source,
        confidence=confidence,
        color=color,
        bounds=component.bounds,
        area=component.area,
        status="proposed",
        downstream_status="pending",
        **anchor_summary,
    )


def _proposal_status(area: int, max_component_area: int | None) -> str:
    if max_component_area is not None and area > max_component_area:
        return "deferred"
    return "proposed"


def _downstream_status(status: str) -> tuple[str, str | None]:
    if status == "deferred":
        return "rejected", "max_component_area_exceeded"
    return "pending", None


def _counts(values: object) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        key = str(value)
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def _tile_grid_group(
    proposals: tuple[SegmentProposal, ...],
) -> dict[str, object] | None:
    candidates = [
        proposal
        for proposal in proposals
        if proposal.anchor_reserved
        and proposal.anchor_kind in {"rect", "quad"}
        and proposal.status == "proposed"
    ]
    if len(candidates) < 4:
        return None

    centers = {
        proposal.id: _bounds_center(proposal.bounds)
        for proposal in candidates
    }
    widths = [proposal.bounds[2] - proposal.bounds[0] + 1 for proposal in candidates]
    heights = [proposal.bounds[3] - proposal.bounds[1] + 1 for proposal in candidates]
    row_tolerance = max(2.0, _mean(heights) * 0.75)
    column_tolerance = max(2.0, _mean(widths) * 0.75)
    rows = _cluster_axis(
        ((proposal.id, centers[proposal.id][1]) for proposal in candidates),
        tolerance=row_tolerance,
    )
    columns = _cluster_axis(
        ((proposal.id, centers[proposal.id][0]) for proposal in candidates),
        tolerance=column_tolerance,
    )
    if len(rows) < 2 or len(columns) < 2:
        return None

    cell_count = len(rows) * len(columns)
    occupancy = len(candidates) / cell_count if cell_count else 0.0
    if occupancy < 0.6:
        return None

    proposal_ids = [
        proposal.id
        for proposal in sorted(
            candidates,
            key=lambda proposal: (
                _cluster_index(rows, proposal.id),
                _cluster_index(columns, proposal.id),
                proposal.id,
            ),
        )
    ]
    return {
        "id": "proposal-group-0000",
        "kind": "proposal_tile_grid",
        "proposal_ids": proposal_ids,
        "metrics": {
            "row_count": float(len(rows)),
            "column_count": float(len(columns)),
            "tile_count": float(len(candidates)),
            "grid_occupancy_ratio": round(occupancy, 6),
            "row_spacing_error": _spacing_error([row[0] for row in rows]),
            "column_spacing_error": _spacing_error(
                [column[0] for column in columns]
            ),
            "mean_tile_width": round(_mean(widths), 6),
            "mean_tile_height": round(_mean(heights), 6),
        },
    }


def _bounds_center(bounds: tuple[int, int, int, int]) -> tuple[float, float]:
    return ((bounds[0] + bounds[2]) / 2, (bounds[1] + bounds[3]) / 2)


def _cluster_axis(
    values: object,
    *,
    tolerance: float,
) -> list[tuple[float, list[str]]]:
    clusters: list[tuple[float, list[str]]] = []
    for item_id, value in sorted(values, key=lambda item: item[1]):
        if clusters and abs(value - clusters[-1][0]) <= tolerance:
            previous_center, previous_ids = clusters[-1]
            next_ids = [*previous_ids, item_id]
            next_center = (
                previous_center * len(previous_ids) + value
            ) / len(next_ids)
            clusters[-1] = (next_center, next_ids)
            continue
        clusters.append((float(value), [item_id]))
    return clusters


def _cluster_index(clusters: list[tuple[float, list[str]]], item_id: str) -> int:
    for index, (_, item_ids) in enumerate(clusters):
        if item_id in item_ids:
            return index
    return len(clusters)


def _spacing_error(values: list[float]) -> float:
    if len(values) < 3:
        return 0.0
    spacings = [
        values[index + 1] - values[index]
        for index in range(len(values) - 1)
    ]
    average = _mean(spacings)
    if average <= 0:
        return 1.0
    variance = sum((value - average) ** 2 for value in spacings) / len(spacings)
    return round((variance ** 0.5) / average, 6)


def _mean(values: list[float] | list[int]) -> float:
    if not values:
        return 0.0
    return sum(float(value) for value in values) / len(values)


def _list_value(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def _format_counts(value: object) -> str:
    if not isinstance(value, dict) or not value:
        return "`none`"
    parts = [f"{key}: {count}" for key, count in sorted(value.items())]
    return "`" + ", ".join(parts) + "`"


def _format_bounds(value: object) -> str:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return "n/a"
    return ",".join(str(part) for part in value)


def _proposal_reason(proposal: dict[str, object]) -> object:
    return (
        proposal.get("downstream_decision_reason")
        or proposal.get("rejection_reason")
        or proposal.get("reservation_reason")
        or "n/a"
    )


def _format_float(value: object) -> str:
    if not isinstance(value, (int, float)):
        return "n/a"
    return f"{value:.4f}"


def _gate_segment_proposal(
    proposal: SegmentProposal,
    *,
    max_anchor_quality_error: float | None,
    require_reserved_anchor: bool,
) -> SegmentProposal:
    if proposal.downstream_status != "pending":
        return proposal
    if proposal.anchor_kind is None or proposal.anchor_metrics is None:
        return replace(
            proposal,
            downstream_status="rejected",
            rejection_reason="missing_anchor_summary",
            downstream_decision_reason="missing_anchor_summary",
        )

    anchor_quality_error = quality_metric_error(proposal.anchor_metrics)
    if (
        max_anchor_quality_error is not None
        and anchor_quality_error > max_anchor_quality_error
    ):
        return replace(
            proposal,
            downstream_status="rejected",
            rejection_reason="anchor_quality_error_too_high",
            anchor_quality_error=anchor_quality_error,
            downstream_decision_reason="anchor_quality_error_too_high",
        )
    if require_reserved_anchor and not proposal.anchor_reserved:
        return replace(
            proposal,
            downstream_status="rejected",
            rejection_reason="anchor_not_reserved",
            anchor_quality_error=anchor_quality_error,
            downstream_decision_reason="anchor_not_reserved",
        )
    return replace(
        proposal,
        downstream_status="accepted",
        rejection_reason=None,
        anchor_quality_error=anchor_quality_error,
        downstream_decision_reason="geometry_gate_passed",
    )


def _primitive_anchor_summary(component: MaskComponent) -> dict[str, object]:
    candidates = primitive_candidates_for_component(component)
    if not candidates:
        return {}
    best = choose_best_anchor(candidates)
    reserved = best.is_simple_shape
    return {
        "anchor_kind": str(best.kind),
        "anchor_metrics": dict(sorted(best.metrics.items())),
        "anchor_parameter_count": best.parameter_count,
        "anchor_reserved": reserved,
        "reservation_reason": "simple_shape_anchor" if reserved else None,
        "reservation_bounds": component.bounds if reserved else None,
    }
