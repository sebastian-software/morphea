"""Segment proposal interfaces for classical and future MLX segmenters."""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from curve.anchors import choose_best_anchor
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
    model_exists = (
        Path(segmenter.model_path).expanduser().exists()
        if segmenter.model_path is not None
        else False
    )
    if not package_available:
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
        "backend_available": False,
        "status": status,
        "reason": reason,
        "package_available": package_available,
        "model_configured": model_configured,
        "model_exists": model_exists,
        "model_path": segmenter.model_path,
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
        }
        for proposal in proposals
    ]


def segment_proposal_summary(
    proposals: tuple[SegmentProposal, ...],
) -> dict[str, object]:
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
    }


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
        f"- Anchor kind counts: {_format_counts(summary.get('anchor_kind_counts', {}))}",
        f"- Reserved anchors: `{summary.get('reserved_anchor_count', 0)}`",
        "",
        "| ID | Status | Downstream | Anchor | Reserved | Bounds | Reason |",
        "| --- | --- | --- | --- | ---: | --- | --- |",
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
            f"{str(bool(proposal.get('anchor_reserved', False))).lower()} | "
            f"`{_format_bounds(proposal.get('bounds'))}` | "
            f"{proposal.get('reservation_reason') or proposal.get('rejection_reason') or 'n/a'} |"
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


def _format_counts(value: object) -> str:
    if not isinstance(value, dict) or not value:
        return "`none`"
    parts = [f"{key}: {count}" for key, count in sorted(value.items())]
    return "`" + ", ".join(parts) + "`"


def _format_bounds(value: object) -> str:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return "n/a"
    return ",".join(str(part) for part in value)


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
