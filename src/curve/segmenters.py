"""Segment proposal interfaces for classical and future MLX segmenters."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from curve.images import ColorMask, flat_color_masks_from_image


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
    source: str = "flat_color"

    def propose(self, image_path: str | Path) -> tuple[SegmentProposal, ...]:
        masks = flat_color_masks_from_image(
            image_path,
            min_area=self.min_area,
            color_tolerance=self.color_tolerance,
            max_size=self.max_size,
            max_colors=self.max_colors,
        )
        return tuple(
            _proposal_from_color_mask(index, self.source, color_mask)
            for index, color_mask in enumerate(masks)
        )


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
) -> SegmentProposal:
    pixels = color_mask.mask.pixels
    xs = [x for x, _ in pixels]
    ys = [y for _, y in pixels]
    return SegmentProposal(
        id=f"{source}-{index:04d}",
        source=source,
        confidence=1.0,
        color=color_mask.color,
        bounds=(min(xs), min(ys), max(xs), max(ys)),
        area=len(pixels),
    )

