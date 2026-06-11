"""Flat-color raster image loading for early primitive vectorization."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import monotonic

from PIL import Image

from curve.anchors import AnchorCandidate, CircleAnchor, Point, QuadAnchor, StrokeAnchor
from curve.classifier import load_centroid_model
from curve.detection import detect_cutout_strokes, detect_primitive_anchors
from curve.masks import BinaryMask, MaskComponent, connected_components
from curve.scene import Scene


Rgb = tuple[int, int, int]


@dataclass(frozen=True)
class ColorMask:
    color: str
    mask: BinaryMask


@dataclass(frozen=True)
class ImageMaskResult:
    masks: tuple[ColorMask, ...]
    width: int
    height: int
    scale: float
    diagnostics: tuple[dict[str, object], ...]


def flat_color_masks_from_image(
    path: str | Path,
    *,
    background: Rgb | None = None,
    min_area: int = 8,
    color_tolerance: float = 0.0,
    max_size: int | None = None,
    max_colors: int | None = None,
) -> tuple[ColorMask, ...]:
    """Group an image into flat-color binary masks.

    With the default tolerance this groups exact colors. A positive tolerance
    merges nearby RGB values into the first compatible palette bucket, which is
    enough for simple anti-aliased flat-color fixtures.
    """

    return _flat_color_masks_result(
        path,
        background=background,
        min_area=min_area,
        color_tolerance=color_tolerance,
        max_size=max_size,
        max_colors=max_colors,
    ).masks


def _flat_color_masks_result(
    path: str | Path,
    *,
    background: Rgb | None,
    min_area: int,
    color_tolerance: float,
    max_size: int | None,
    max_colors: int | None,
) -> ImageMaskResult:
    original = Image.open(path).convert("RGBA")
    original_width, original_height = original.size
    image = original
    diagnostics: list[dict[str, object]] = []

    scale = 1.0
    if max_size is not None and max(original_width, original_height) > max_size:
        scale = max_size / max(original_width, original_height)
        resized = (
            max(1, round(original_width * scale)),
            max(1, round(original_height * scale)),
        )
        image = image.resize(resized, Image.Resampling.NEAREST)
        diagnostics.append(
            {
                "level": "info",
                "code": "image_resized_for_analysis",
                "original_size": [original_width, original_height],
                "analysis_size": list(resized),
                "scale": scale,
            }
        )

    quantized_rgb = None
    if max_colors is not None:
        quantized_rgb = image.convert("RGB").quantize(colors=max_colors).convert("RGB")
        diagnostics.append(
            {
                "level": "info",
                "code": "palette_quantized",
                "max_colors": max_colors,
            }
        )

    width, height = image.size
    pixels_by_color: dict[Rgb, set[tuple[int, int]]] = {}
    palette: list[Rgb] = []
    inferred_background = background or image.getpixel((0, 0))[:3]

    for y in range(height):
        for x in range(width):
            red, green, blue, alpha = image.getpixel((x, y))
            if alpha == 0:
                continue
            color = quantized_rgb.getpixel((x, y)) if quantized_rgb is not None else (red, green, blue)
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
    return ImageMaskResult(
        masks=tuple(sorted(masks, key=lambda color_mask: color_mask.color)),
        width=original_width,
        height=original_height,
        scale=scale,
        diagnostics=tuple(diagnostics),
    )


def scene_from_flat_color_image(
    path: str | Path,
    *,
    background: Rgb | None = None,
    min_area: int = 8,
    color_tolerance: float = 0.0,
    max_size: int | None = None,
    max_colors: int | None = None,
    max_component_area: int | None = None,
    timeout_seconds: float | None = None,
    classifier_model: str | Path | None = None,
) -> Scene:
    mask_result = _flat_color_masks_result(
        path,
        background=background,
        min_area=min_area,
        color_tolerance=color_tolerance,
        max_size=max_size,
        max_colors=max_colors,
    )
    color_masks = mask_result.masks
    anchors: list[AnchorCandidate] = []
    diagnostics = list(mask_result.diagnostics)
    started_at = monotonic()
    loaded_classifier = (
        load_centroid_model(classifier_model)
        if classifier_model is not None
        else None
    )
    for color_mask in color_masks:
        if max_component_area is not None and len(color_mask.mask.pixels) > max_component_area:
            diagnostics.append(
                {
                    "level": "warning",
                    "code": "color_mask_deferred",
                    "color": color_mask.color,
                    "area": len(color_mask.mask.pixels),
                    "max_component_area": max_component_area,
                    "message": "color mask was too large to split within current runtime limits",
                }
            )
            continue
        for component in connected_components(color_mask.mask, min_area=min_area):
            if _deadline_exceeded(started_at, timeout_seconds):
                diagnostics.append(
                    {
                        "level": "warning",
                        "code": "timeout_reached",
                        "timeout_seconds": timeout_seconds,
                        "message": "stopped before all color components were processed",
                    }
                )
                return Scene(
                    width=mask_result.width,
                    height=mask_result.height,
                    anchors=tuple(anchors),
                    diagnostics=tuple(diagnostics),
                )
            if max_component_area is not None and component.area > max_component_area:
                diagnostics.append(
                    {
                        "level": "warning",
                        "code": "component_deferred",
                        "color": color_mask.color,
                        "area": component.area,
                        "max_component_area": max_component_area,
                        "bounds": list(component.bounds),
                    }
                )
                continue

            component_mask = _mask_from_component(color_mask.mask, component)
            for anchor in detect_primitive_anchors(
                component_mask,
                min_area=min_area,
                classifier_model=loaded_classifier,
            ):
                anchors.append(_scale_anchor(_with_color(anchor, color_mask.color), mask_result.scale))
            for anchor in detect_cutout_strokes(component_mask):
                anchors.append(_scale_anchor(anchor, mask_result.scale))
    return Scene(
        width=mask_result.width,
        height=mask_result.height,
        anchors=tuple(anchors),
        diagnostics=tuple(diagnostics),
    )


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


def _mask_from_component(mask: BinaryMask, component: MaskComponent) -> BinaryMask:
    return BinaryMask(width=mask.width, height=mask.height, pixels=component.pixels)


def _deadline_exceeded(started_at: float, timeout_seconds: float | None) -> bool:
    return timeout_seconds is not None and monotonic() - started_at >= timeout_seconds


def _scale_anchor(anchor: AnchorCandidate, analysis_scale: float) -> AnchorCandidate:
    if analysis_scale == 1.0:
        return anchor
    factor = 1 / analysis_scale
    return AnchorCandidate(
        kind=anchor.kind,
        raster_error=anchor.raster_error,
        node_count=anchor.node_count,
        parameter_count=anchor.parameter_count,
        color=anchor.color,
        circle=_scale_circle(anchor.circle, factor),
        stroke=_scale_stroke(anchor.stroke, factor),
        quad=_scale_quad(anchor.quad, factor),
        metrics=anchor.metrics,
    )


def _scale_circle(circle: CircleAnchor | None, factor: float) -> CircleAnchor | None:
    if circle is None:
        return None
    return CircleAnchor(
        center=_scale_point(circle.center, factor),
        radius=circle.radius * factor,
        samples=tuple(_scale_point(point, factor) for point in circle.samples),
    )


def _scale_stroke(stroke: StrokeAnchor | None, factor: float) -> StrokeAnchor | None:
    if stroke is None:
        return None
    return StrokeAnchor(
        centerline=tuple(_scale_point(point, factor) for point in stroke.centerline),
        width_samples=tuple(width * factor for width in stroke.width_samples),
        is_cutout=stroke.is_cutout,
        parallel_group_id=stroke.parallel_group_id,
    )


def _scale_quad(quad: QuadAnchor | None, factor: float) -> QuadAnchor | None:
    if quad is None:
        return None
    return QuadAnchor(corners=tuple(_scale_point(point, factor) for point in quad.corners))


def _scale_point(point: Point, factor: float) -> Point:
    return Point(point.x * factor, point.y * factor)


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
