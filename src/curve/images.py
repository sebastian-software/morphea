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
    color_tolerance: float = 0.0,
) -> tuple[ColorMask, ...]:
    """Group an image into flat-color binary masks.

    With the default tolerance this groups exact colors. A positive tolerance
    merges nearby RGB values into the first compatible palette bucket, which is
    enough for simple anti-aliased flat-color fixtures.
    """

    image = Image.open(path).convert("RGBA")
    width, height = image.size
    pixels_by_color: dict[Rgb, set[tuple[int, int]]] = {}
    palette: list[Rgb] = []
    inferred_background = background or image.getpixel((0, 0))[:3]

    for y in range(height):
        for x in range(width):
            red, green, blue, alpha = image.getpixel((x, y))
            if alpha == 0:
                continue
            color = (red, green, blue)
            if _color_distance(color, inferred_background) <= color_tolerance:
                continue
            bucket = _nearest_palette_color(color, palette, color_tolerance)
            if bucket is None:
                bucket = color
                palette.append(bucket)
            pixels_by_color.setdefault(bucket, set()).add((x, y))

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
    color_tolerance: float = 0.0,
) -> Scene:
    color_masks = flat_color_masks_from_image(
        path,
        background=background,
        min_area=min_area,
        color_tolerance=color_tolerance,
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


def _nearest_palette_color(
    color: Rgb,
    palette: list[Rgb],
    tolerance: float,
) -> Rgb | None:
    if tolerance <= 0:
        return color if color in palette else None

    matches = [
        (candidate, _color_distance(color, candidate))
        for candidate in palette
    ]
    matches = [
        (candidate, distance)
        for candidate, distance in matches
        if distance <= tolerance
    ]
    if not matches:
        return None
    return min(matches, key=lambda match: match[1])[0]


def _color_distance(left: Rgb, right: Rgb) -> float:
    return (
        (left[0] - right[0]) ** 2
        + (left[1] - right[1]) ** 2
        + (left[2] - right[2]) ** 2
    ) ** 0.5
