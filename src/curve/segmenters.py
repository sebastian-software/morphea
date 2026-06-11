"""Segment proposal interfaces for classical and future MLX segmenters."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

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


class Segmenter(Protocol):
    source: str

    def propose(self, image_path: str | Path) -> tuple[SegmentProposal, ...]:
        """Return segment proposals for an image."""


@dataclass(frozen=True)
class FlatColorSegmenter:
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
    source: str = "mlx_sam"

    def propose(self, image_path: str | Path) -> tuple[SegmentProposal, ...]:
        msg = "MLX SAM segmenter is not installed/configured yet"
        raise RuntimeError(msg)


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
        }
        for proposal in proposals
    ]


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
    return SegmentProposal(
        id=f"{source}-{index:04d}",
        source=source,
        confidence=1.0,
        color=color_mask.color,
        bounds=(min(xs), min(ys), max(xs), max(ys)),
        area=len(pixels),
        status=status,
    )


def _proposal_from_component(
    index: int,
    source: str,
    color: str,
    component: MaskComponent,
    *,
    max_component_area: int | None,
) -> SegmentProposal:
    return SegmentProposal(
        id=f"{source}-{index:04d}",
        source=source,
        confidence=1.0,
        color=color,
        bounds=component.bounds,
        area=component.area,
        status=_proposal_status(component.area, max_component_area),
    )


def _proposal_status(area: int, max_component_area: int | None) -> str:
    if max_component_area is not None and area > max_component_area:
        return "deferred"
    return "proposed"
