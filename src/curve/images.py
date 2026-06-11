"""Flat-color raster image loading for early primitive vectorization."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from curve.anchors import AnchorCandidate
from curve.detection import detect_primitive_anchors
from curve.masks import BinaryMask
from curve.scene import Scene


Rgb = tuple[int, int, int]


@dataclass(frozen=True)
class ColorMask:
    color: str
    mask: BinaryMask


def flat_color_masks_from_image(
    path: str | Path,
    *,
    background: Rgb | None = None,
    min_area: int = 8,
) -> tuple[ColorMask, ...]:
    """Group an image into exact-color binary masks.

    This intentionally targets flat-color fixtures first. Anti-aliased and
    quantized image handling belongs in a later preprocessing layer.
    """

    image = Image.open(path).convert("RGBA")
    width, height = image.size
    pixels_by_color: dict[Rgb, set[tuple[int, int]]] = {}
    inferred_background = background or image.getpixel((0, 0))[:3]

    for y in range(height):
        for x in range(width):
            red, green, blue, alpha = image.getpixel((x, y))
            if alpha == 0:
                continue
            color = (red, green, blue)
            if color == inferred_background:
                continue
            pixels_by_color.setdefault(color, set()).add((x, y))

    masks: list[ColorMask] = []
    for color, pixels in pixels_by_color.items():
        if len(pixels) < min_area:
            continue
        masks.append(
            ColorMask(
                color=_hex_color(color),
                mask=BinaryMask(width=width, height=height, pixels=frozenset(pixels)),
            )
        )
    return tuple(sorted(masks, key=lambda color_mask: color_mask.color))


def scene_from_flat_color_image(
    path: str | Path,
    *,
    background: Rgb | None = None,
    min_area: int = 8,
) -> Scene:
    color_masks = flat_color_masks_from_image(
        path,
        background=background,
        min_area=min_area,
    )
    anchors: list[AnchorCandidate] = []
    width = 0
    height = 0
    for color_mask in color_masks:
        width = color_mask.mask.width
        height = color_mask.mask.height
        for anchor in detect_primitive_anchors(color_mask.mask, min_area=min_area):
            anchors.append(_with_color(anchor, color_mask.color))
    return Scene(width=width, height=height, anchors=tuple(anchors))


def _with_color(anchor: AnchorCandidate, color: str) -> AnchorCandidate:
    return AnchorCandidate(
        kind=anchor.kind,
        raster_error=anchor.raster_error,
        node_count=anchor.node_count,
        parameter_count=anchor.parameter_count,
        color=color,
        circle=anchor.circle,
        stroke=anchor.stroke,
        quad=anchor.quad,
        metrics=anchor.metrics,
    )


def _hex_color(color: Rgb) -> str:
    return f"#{color[0]:02x}{color[1]:02x}{color[2]:02x}"

