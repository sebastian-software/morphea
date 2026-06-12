"""Flat-color raster image loading for early primitive vectorization."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from pathlib import Path
from time import monotonic

from PIL import Image

from curve.anchors import (
    AnchorCandidate,
    CircleAnchor,
    Point,
    QuadAnchor,
    ScoringConfig,
    StrokeAnchor,
)
from curve.classifier import load_centroid_model
from curve.detection import (
    AnchorThresholdConfig,
    detect_cutout_strokes,
    detect_primitive_anchors,
)
from curve.masks import BinaryMask, MaskComponent
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

    width, height = image.size
    pixel_indexes_by_color: dict[Rgb, list[int]] = {}
    palette: list[Rgb] = []
    palette_bucket_cache: dict[Rgb, Rgb] = {}
    inferred_background = background or _infer_background_color(image)
    flattened_rgb = _flatten_rgba_image(image, inferred_background)
    quantized_rgb = None
    if max_colors is not None:
        quantized_rgb = flattened_rgb.quantize(colors=max_colors).convert("RGB")
        diagnostics.append(
            {
                "level": "info",
                "code": "palette_quantized",
                "max_colors": max_colors,
            }
        )

    source_pixels = _image_pixels(image)
    flattened_pixels = _image_pixels(flattened_rgb)
    quantized_pixels = (
        _image_pixels(quantized_rgb)
        if quantized_rgb is not None
        else None
    )
    transparent_pixel_count = 0
    partial_alpha_pixel_count = 0

    for index, source_pixel in enumerate(source_pixels):
        _, _, _, alpha = source_pixel
        if alpha == 0:
            transparent_pixel_count += 1
            continue
        if alpha < 255:
            partial_alpha_pixel_count += 1
        color = (
            quantized_pixels[index]
            if quantized_pixels is not None
            else flattened_pixels[index]
        )
        if _color_distance(color, inferred_background) <= color_tolerance:
            continue
        if color_tolerance <= 0:
            bucket = color
        elif color in palette_bucket_cache:
            bucket = palette_bucket_cache[color]
        else:
            bucket = _nearest_palette_color(color, palette, color_tolerance)
            if bucket is None:
                bucket = color
                palette.append(bucket)
            palette_bucket_cache[color] = bucket
        pixel_indexes_by_color.setdefault(bucket, []).append(index)

    if transparent_pixel_count:
        diagnostics.append(
            {
                "level": "info",
                "code": "transparent_pixels_ignored",
                "pixel_count": transparent_pixel_count,
            }
        )
    if partial_alpha_pixel_count:
        diagnostics.append(
            {
                "level": "info",
                "code": "partial_alpha_flattened",
                "pixel_count": partial_alpha_pixel_count,
                "background": _hex_color(inferred_background),
            }
        )

    masks: list[ColorMask] = []
    for color, indexes in pixel_indexes_by_color.items():
        if len(indexes) < min_area:
            continue
        masks.append(
            ColorMask(
                color=_hex_color(color),
                mask=BinaryMask(
                    width=width,
                    height=height,
                    pixels=frozenset(
                        _pixel_from_index(index, width) for index in indexes
                    ),
                ),
            )
        )
    return ImageMaskResult(
        masks=tuple(sorted(masks, key=lambda color_mask: color_mask.color)),
        width=original_width,
        height=original_height,
        scale=scale,
        diagnostics=tuple(diagnostics),
    )


def _infer_background_color(image: Image.Image) -> Rgb:
    red, green, blue, alpha = image.getpixel((0, 0))
    if alpha == 0:
        return (255, 255, 255)
    return (red, green, blue)


def _flatten_rgba_image(image: Image.Image, background: Rgb) -> Image.Image:
    backdrop = Image.new("RGBA", image.size, (*background, 255))
    return Image.alpha_composite(backdrop, image).convert("RGB")


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
    raster_error_weight: float = 1.0,
    quality_error_weight: float = 1.0,
    node_complexity_weight: float = 0.015,
    parameter_complexity_weight: float = 0.01,
    simple_shape_bonus_weight: float = 1.0,
    stroke_circle_min_diameter: int = 6,
    stroke_circle_max_aspect_error: float = 0.18,
    stroke_circle_min_inner_ratio: float = 0.45,
    stroke_circle_max_area_error: float = 0.45,
    circle_min_diameter: int = 3,
    circle_max_aspect_error: float = 0.22,
    circle_max_area_error: float = 0.35,
    stroke_min_length: float = 4.0,
    stroke_min_length_width_ratio: float = 3.0,
    quad_min_fill_ratio: float = 0.35,
    quad_max_fill_error: float = 0.28,
    rect_max_fill_error: float = 0.08,
    rounded_rect_max_fill_error: float = 0.30,
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
    scoring = ScoringConfig(
        raster_error_weight=raster_error_weight,
        quality_error_weight=quality_error_weight,
        node_complexity_weight=node_complexity_weight,
        parameter_complexity_weight=parameter_complexity_weight,
        simple_shape_bonus_weight=simple_shape_bonus_weight,
    )
    thresholds = AnchorThresholdConfig(
        stroke_circle_min_diameter=stroke_circle_min_diameter,
        stroke_circle_max_aspect_error=stroke_circle_max_aspect_error,
        stroke_circle_min_inner_ratio=stroke_circle_min_inner_ratio,
        stroke_circle_max_area_error=stroke_circle_max_area_error,
        circle_min_diameter=circle_min_diameter,
        circle_max_aspect_error=circle_max_aspect_error,
        circle_max_area_error=circle_max_area_error,
        stroke_min_length=stroke_min_length,
        stroke_min_length_width_ratio=stroke_min_length_width_ratio,
        quad_min_fill_ratio=quad_min_fill_ratio,
        quad_max_fill_error=quad_max_fill_error,
        rect_max_fill_error=rect_max_fill_error,
        rounded_rect_max_fill_error=rounded_rect_max_fill_error,
    )
    for color_mask in color_masks:
        if max_component_area is not None and len(color_mask.mask.pixels) > max_component_area:
            diagnostics.append(
                {
                    "level": "info",
                    "code": "color_mask_split_for_components",
                    "color": color_mask.color,
                    "area": len(color_mask.mask.pixels),
                    "max_component_area": max_component_area,
                    "message": "color mask exceeded component limit and was split into bounded components",
                }
            )
        component_result = _bounded_connected_components(
            color_mask.mask,
            min_area=min_area,
            max_component_area=max_component_area,
            started_at=started_at,
            timeout_seconds=timeout_seconds,
            color=color_mask.color,
        )
        diagnostics.extend(component_result.diagnostics)
        if component_result.timed_out:
            return Scene(
                width=mask_result.width,
                height=mask_result.height,
                anchors=tuple(anchors),
                diagnostics=tuple(diagnostics),
            )
        for component in component_result.components:

            component_mask = _mask_from_component(color_mask.mask, component)
            for anchor in detect_primitive_anchors(
                component_mask,
                min_area=min_area,
                classifier_model=loaded_classifier,
                scoring=scoring,
                thresholds=thresholds,
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


@dataclass(frozen=True)
class ComponentScanResult:
    components: tuple[MaskComponent, ...]
    diagnostics: tuple[dict[str, object], ...]
    timed_out: bool = False


def _bounded_connected_components(
    mask: BinaryMask,
    *,
    min_area: int,
    max_component_area: int | None,
    started_at: float,
    timeout_seconds: float | None,
    color: str,
) -> ComponentScanResult:
    grid, seeds = _indexed_mask(mask)
    components: list[MaskComponent] = []
    diagnostics: list[dict[str, object]] = []

    for start in seeds:
        if not grid[start]:
            continue
        if _deadline_exceeded(started_at, timeout_seconds):
            diagnostics.append(_timeout_diagnostic(timeout_seconds))
            return ComponentScanResult(
                components=_sort_components(components),
                diagnostics=tuple(diagnostics),
                timed_out=True,
            )

        grid[start] = 0
        queue: deque[int] = deque([start])
        pixel_indexes: list[int] = []
        area = 0
        start_x = start % mask.width
        start_y = start // mask.width
        min_x = max_x = start_x
        min_y = max_y = start_y
        store_pixels = True

        while queue:
            if area % 512 == 0 and _deadline_exceeded(started_at, timeout_seconds):
                diagnostics.append(_timeout_diagnostic(timeout_seconds))
                return ComponentScanResult(
                    components=_sort_components(components),
                    diagnostics=tuple(diagnostics),
                    timed_out=True,
                )

            index = queue.popleft()
            x = index % mask.width
            y = index // mask.width
            area += 1
            min_x = min(min_x, x)
            max_x = max(max_x, x)
            min_y = min(min_y, y)
            max_y = max(max_y, y)
            if store_pixels:
                pixel_indexes.append(index)
            if max_component_area is not None and area > max_component_area:
                store_pixels = False
                pixel_indexes.clear()

            _enqueue_neighbors8(
                grid,
                queue,
                x=x,
                y=y,
                width=mask.width,
                height=mask.height,
            )

        if area < min_area:
            continue
        if max_component_area is not None and area > max_component_area:
            diagnostics.append(
                {
                    "level": "warning",
                    "code": "component_deferred",
                    "color": color,
                    "area": area,
                    "max_component_area": max_component_area,
                    "bounds": [min_x, min_y, max_x, max_y],
                }
            )
            continue
        components.append(
            MaskComponent(
                frozenset(
                    _pixel_from_index(index, mask.width)
                    for index in pixel_indexes
                ),
                bounds_hint=(min_x, min_y, max_x, max_y),
            )
        )

    return ComponentScanResult(
        components=_sort_components(components),
        diagnostics=tuple(diagnostics),
    )


def _sort_components(components: list[MaskComponent]) -> tuple[MaskComponent, ...]:
    return tuple(
        sorted(components, key=lambda component: component.area, reverse=True)
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


def _timeout_diagnostic(timeout_seconds: float | None) -> dict[str, object]:
    return {
        "level": "warning",
        "code": "timeout_reached",
        "timeout_seconds": timeout_seconds,
        "message": "stopped before all color components were processed",
    }


def _indexed_mask(mask: BinaryMask) -> tuple[bytearray, tuple[int, ...]]:
    grid = bytearray(mask.width * mask.height)
    indexes: list[int] = []
    for x, y in mask.pixels:
        index = y * mask.width + x
        grid[index] = 1
        indexes.append(index)
    return grid, tuple(indexes)


def _enqueue_neighbors8(
    grid: bytearray,
    queue: deque[int],
    *,
    x: int,
    y: int,
    width: int,
    height: int,
) -> None:
    can_left = x > 0
    can_right = x < width - 1
    can_up = y > 0
    can_down = y < height - 1
    index = y * width + x

    if can_up:
        top = index - width
        if grid[top]:
            grid[top] = 0
            queue.append(top)
        if can_left and grid[top - 1]:
            grid[top - 1] = 0
            queue.append(top - 1)
        if can_right and grid[top + 1]:
            grid[top + 1] = 0
            queue.append(top + 1)
    if can_left and grid[index - 1]:
        grid[index - 1] = 0
        queue.append(index - 1)
    if can_right and grid[index + 1]:
        grid[index + 1] = 0
        queue.append(index + 1)
    if can_down:
        bottom = index + width
        if grid[bottom]:
            grid[bottom] = 0
            queue.append(bottom)
        if can_left and grid[bottom - 1]:
            grid[bottom - 1] = 0
            queue.append(bottom - 1)
        if can_right and grid[bottom + 1]:
            grid[bottom + 1] = 0
            queue.append(bottom + 1)


def _pixel_from_index(index: int, width: int) -> tuple[int, int]:
    return index % width, index // width


def _image_pixels(image: Image.Image) -> list[tuple[int, ...]]:
    get_flattened_data = getattr(image, "get_flattened_data", None)
    if get_flattened_data is not None:
        return list(get_flattened_data())
    return list(image.getdata())


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
        cap_style=stroke.cap_style,
        join_style=stroke.join_style,
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
