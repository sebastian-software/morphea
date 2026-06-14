"""Flat-color raster image loading for early primitive vectorization."""

from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass
from pathlib import Path
from time import monotonic

from PIL import Image

from morphea.anchors import (
    AnchorCandidate,
    AnchorKind,
    ArcAnchor,
    CircleAnchor,
    EllipseAnchor,
    PathAnchor,
    Point,
    QuadAnchor,
    ScoringConfig,
    StrokeAnchor,
    choose_best_anchor,
)
from morphea.classifier import (
    classifier_crop_size,
    classifier_uses_raster_tokens,
    component_raster_tokens,
    load_classifier_model,
)
from morphea.detection import (
    AnchorThresholdConfig,
    detect_cutout_strokes_for_component,
    detect_primitive_anchors,
    primitive_candidates_for_component,
)
from morphea.masks import BinaryMask, MaskComponent, connected_components
from morphea.scene import (
    Scene,
    merge_auto_mergeable_same_color_fragments,
    promote_occluded_rect_fragment_groups,
    promote_occluded_rect_primitives,
)


Rgb = tuple[int, int, int]
BackgroundColor = Rgb | str | list[int] | None


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
    background: BackgroundColor = None,
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
    background: BackgroundColor,
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
    inferred_background = (
        _normalize_background_color(background) or _infer_background_color(image)
    )
    flattened_rgb = _flatten_rgba_image(image, inferred_background)

    source_pixels = _image_pixels(image)
    flattened_pixels = _image_pixels(flattened_rgb)
    quantized_pixels = None
    if max_colors is not None:
        # Median-cut quantization spends its clusters on the dominant
        # background and anti-aliasing ramps of flat artwork, dropping
        # small-but-distinct brand colors such as a thin dark ring. Instead,
        # anchor the palette at the most frequent well-separated colors and
        # snap every pixel to its nearest anchor (or the background).
        anchors = _dominant_palette_anchors(
            flattened_pixels,
            background=inferred_background,
            max_colors=max_colors,
            min_separation=max(48.0, color_tolerance * 2),
            background_tolerance=color_tolerance,
        )
        quantized_pixels = [
            _nearest_anchor(pixel, anchors, inferred_background)
            for pixel in flattened_pixels
        ]
        diagnostics.append(
            {
                "level": "info",
                "code": "palette_quantized",
                "max_colors": max_colors,
                "palette": [_hex_color(anchor) for anchor in anchors],
            }
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
        representative_color = _representative_mask_color(
            indexes,
            flattened_pixels,
            fallback=color,
        )
        masks.append(
            ColorMask(
                color=_hex_color(representative_color),
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


def _dominant_palette_anchors(
    pixels: list[tuple[int, ...]],
    *,
    background: Rgb,
    max_colors: int,
    min_separation: float,
    background_tolerance: float,
) -> list[Rgb]:
    # Generated artwork rarely repeats exact colors, so dominance is
    # aggregated over coarse 16-step color cells; each anchor is the most
    # common exact color of its cell, keeping the brand tone crisp.
    cell_counts: Counter[tuple[int, int, int]] = Counter()
    cell_colors: dict[tuple[int, int, int], Counter[Rgb]] = {}
    for pixel in pixels:
        color = (int(pixel[0]), int(pixel[1]), int(pixel[2]))
        cell = (color[0] >> 4, color[1] >> 4, color[2] >> 4)
        cell_counts[cell] += 1
        cell_colors.setdefault(cell, Counter())[color] += 1
    minimum_share = max(16, len(pixels) // 500)
    large_blend_share = max(minimum_share * 4, len(pixels) // 200)
    anchors: list[Rgb] = []
    for cell, count in cell_counts.most_common():
        if count < minimum_share:
            break
        color = cell_colors[cell].most_common(1)[0][0]
        if _color_distance(color, background) <= background_tolerance:
            continue
        if any(
            _color_distance(color, anchor) < min_separation
            for anchor in anchors
        ):
            continue
        # Anti-aliasing ramps sit on the straight RGB line between two real
        # colors; a candidate close to any anchor/background pair's segment
        # is a blend seam, not a brand color. Large near-background fills are
        # the exception: generated table cells can be intentional beige fills
        # even when they lie on the same RGB segment as a gold/background ramp.
        if _is_blend_of_existing(color, anchors, background) and (
            count < large_blend_share
            or _is_neutral_rgb(color)
            or _color_distance(color, background) > 96.0
        ):
            continue
        anchors.append(color)
        if len(anchors) >= max_colors:
            break
    return anchors


def _is_blend_of_existing(
    color: Rgb,
    anchors: list[Rgb],
    background: Rgb,
) -> bool:
    palette = [background, *anchors]
    for index, first in enumerate(palette):
        for second in palette[index + 1 :]:
            if _point_to_rgb_segment_distance(color, first, second) < 24.0:
                return True
    return False


def _point_to_rgb_segment_distance(point: Rgb, start: Rgb, end: Rgb) -> float:
    direction = tuple(e - s for s, e in zip(start, end))
    length_squared = sum(d * d for d in direction)
    if length_squared <= 0:
        return _color_distance(point, start)
    t = sum(
        (p - s) * d for p, s, d in zip(point, start, direction)
    ) / length_squared
    t = max(0.0, min(1.0, t))
    closest = tuple(s + d * t for s, d in zip(start, direction))
    return (
        sum((p - c) ** 2 for p, c in zip(point, closest))
    ) ** 0.5


def _nearest_anchor(
    pixel: tuple[int, ...],
    anchors: list[Rgb],
    background: Rgb,
) -> Rgb:
    color = (int(pixel[0]), int(pixel[1]), int(pixel[2]))
    best = background
    best_distance = _color_distance(color, background)
    for anchor in anchors:
        distance = _color_distance(color, anchor)
        if distance < best_distance:
            best = anchor
            best_distance = distance
    return best


def _representative_mask_color(
    indexes: list[int],
    pixels: list[tuple[int, ...]],
    *,
    fallback: Rgb,
) -> Rgb:
    counts: Counter[Rgb] = Counter()
    for index in indexes:
        pixel = pixels[index]
        if len(pixel) >= 3:
            counts[(int(pixel[0]), int(pixel[1]), int(pixel[2]))] += 1
    if not counts:
        return fallback
    return counts.most_common(1)[0][0]


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
    background: BackgroundColor = None,
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
    stroke_circle_min_inner_ratio: float = 0.25,
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
        load_classifier_model(classifier_model)
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
            crop_tokens = (
                component_raster_tokens(
                    component,
                    color=color_mask.color,
                    crop_size=classifier_crop_size(loaded_classifier),
                )
                if loaded_classifier is not None
                and classifier_uses_raster_tokens(loaded_classifier)
                else None
            )
            for anchor in detect_primitive_anchors(
                component_mask,
                min_area=min_area,
                classifier_model=loaded_classifier,
                classifier_crop_tokens=crop_tokens,
                scoring=scoring,
                thresholds=thresholds,
            ):
                anchors.append(_scale_anchor(_with_color(anchor, color_mask.color), mask_result.scale))
            for anchor in detect_cutout_strokes_for_component(component):
                anchors.append(_scale_anchor(anchor, mask_result.scale))
    anchors.extend(
        _neutral_composite_circle_anchors(
            color_masks,
            min_area=min_area,
            thresholds=thresholds,
            scoring=scoring,
            analysis_scale=mask_result.scale,
        )
    )
    deduplicated_anchors = _deduplicate_equivalent_anchors(tuple(anchors))
    return Scene(
        width=mask_result.width,
        height=mask_result.height,
        anchors=merge_auto_mergeable_same_color_fragments(
            promote_occluded_rect_fragment_groups(
                promote_occluded_rect_primitives(deduplicated_anchors)
            )
        ),
        diagnostics=tuple(diagnostics),
    )


@dataclass(frozen=True)
class ComponentScanResult:
    components: tuple[MaskComponent, ...]
    diagnostics: tuple[dict[str, object], ...]
    timed_out: bool = False


def _neutral_composite_circle_anchors(
    color_masks: tuple[ColorMask, ...],
    *,
    min_area: int,
    thresholds: AnchorThresholdConfig,
    scoring: ScoringConfig,
    analysis_scale: float,
) -> tuple[AnchorCandidate, ...]:
    neutral_pixels = frozenset(
        pixel
        for color_mask in color_masks
        if _is_neutral_color(color_mask.color)
        for pixel in color_mask.mask.pixels
    )
    if len(neutral_pixels) < min_area:
        return ()

    first_mask = color_masks[0].mask
    composite_mask = BinaryMask(
        width=first_mask.width,
        height=first_mask.height,
        pixels=neutral_pixels,
    )
    anchors: list[AnchorCandidate] = []
    for component in connected_components(composite_mask, min_area=min_area):
        component_mask = BinaryMask(
            width=composite_mask.width,
            height=composite_mask.height,
            pixels=component.pixels,
        )
        component_anchors = detect_primitive_anchors(
            component_mask,
            min_area=min_area,
            thresholds=thresholds,
        )
        if any(
            anchor.kind == AnchorKind.STROKE_PATH
            and anchor.metrics.get("irregular_circular_outline") == 1.0
            for anchor in component_anchors
        ):
            continue
        candidates = primitive_candidates_for_component(
            component,
            thresholds=thresholds,
        )
        circle_candidates = tuple(
            candidate
            for candidate in candidates
            if candidate.kind in {AnchorKind.CIRCLE, AnchorKind.STROKE_CIRCLE}
        )
        if not circle_candidates:
            continue
        anchor = choose_best_anchor(circle_candidates, scoring=scoring)
        anchors.append(_scale_anchor(_with_color(anchor, "#000000"), analysis_scale))
    return tuple(anchors)


def _deduplicate_equivalent_anchors(
    anchors: tuple[AnchorCandidate, ...],
) -> tuple[AnchorCandidate, ...]:
    seen: set[tuple[object, ...]] = set()
    deduplicated: list[AnchorCandidate] = []
    for anchor in anchors:
        key = _anchor_equivalence_key(anchor)
        if key is not None:
            if key in seen:
                continue
            seen.add(key)
        deduplicated.append(anchor)
    return tuple(deduplicated)


def _anchor_equivalence_key(anchor: AnchorCandidate) -> tuple[object, ...] | None:
    if anchor.circle is not None:
        stroke_key = None
        if anchor.stroke is not None:
            stroke_key = (
                tuple(_round_float(value) for value in anchor.stroke.width_samples),
                anchor.stroke.is_cutout,
                anchor.stroke.cap_style,
                anchor.stroke.join_style,
                anchor.stroke.closed,
            )
        return (
            str(anchor.kind),
            anchor.color,
            _point_key(anchor.circle.center),
            _round_float(anchor.circle.radius),
            stroke_key,
        )
    if anchor.ellipse is not None:
        return (
            str(anchor.kind),
            anchor.color,
            _point_key(anchor.ellipse.center),
            _round_float(anchor.ellipse.rx),
            _round_float(anchor.ellipse.ry),
            _round_float(anchor.ellipse.rotation),
        )
    return None


def _point_key(point: Point) -> tuple[float, float]:
    return (_round_float(point.x), _round_float(point.y))


def _round_float(value: float) -> float:
    return round(float(value), 6)


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
        sum_x = 0
        sum_y = 0
        row_spans: dict[int, tuple[int, int]] = {}
        boundary_indexes: list[int] = []
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
            sum_x += x
            sum_y += y
            if x < min_x:
                min_x = x
            elif x > max_x:
                max_x = x
            if y < min_y:
                min_y = y
            elif y > max_y:
                max_y = y
            if store_pixels:
                pixel_indexes.append(index)
                if _is_boundary_index(mask.pixels, x, y):
                    boundary_indexes.append(index)
                if y not in row_spans:
                    row_spans[y] = (x, x)
                else:
                    row_min_x, row_max_x = row_spans[y]
                    if x < row_min_x:
                        row_spans[y] = (x, row_max_x)
                    elif x > row_max_x:
                        row_spans[y] = (row_min_x, x)
            if max_component_area is not None and area > max_component_area:
                store_pixels = False
                pixel_indexes.clear()
                boundary_indexes.clear()
                row_spans.clear()

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
                centroid_hint=Point(sum_x / area, sum_y / area),
                boundary_pixels_hint=frozenset(
                    _pixel_from_index(index, mask.width)
                    for index in boundary_indexes
                ),
                row_spans_hint=tuple(
                    (y, *row_spans[y]) for y in sorted(row_spans)
                ),
            )
        )

    return ComponentScanResult(
        components=_sort_components(components),
        diagnostics=tuple(diagnostics),
    )


def _is_boundary_index(pixels: frozenset[tuple[int, int]], x: int, y: int) -> bool:
    return (
        (x - 1, y) not in pixels
        or (x + 1, y) not in pixels
        or (x, y - 1) not in pixels
        or (x, y + 1) not in pixels
    )


def _sort_components(components: list[MaskComponent]) -> tuple[MaskComponent, ...]:
    return tuple(
        sorted(components, key=lambda component: component.area, reverse=True)
    )


def _is_neutral_color(color: str) -> bool:
    if len(color) != 7 or not color.startswith("#"):
        return False
    try:
        red = int(color[1:3], 16)
        green = int(color[3:5], 16)
        blue = int(color[5:7], 16)
    except ValueError:
        return False
    return _is_neutral_rgb((red, green, blue))


def _is_neutral_rgb(color: Rgb) -> bool:
    red, green, blue = color
    return max(red, green, blue) - min(red, green, blue) <= 8


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
        arc=anchor.arc,
        ellipse=anchor.ellipse,
        path=anchor.path,
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
        arc=_scale_arc(anchor.arc, factor),
        ellipse=_scale_ellipse(anchor.ellipse, factor),
        path=_scale_path(anchor.path, factor),
        metrics=anchor.metrics,
    )


def _scale_path(path: PathAnchor | None, factor: float) -> PathAnchor | None:
    if path is None:
        return None
    return PathAnchor(
        points=tuple(_scale_point(point, factor) for point in path.points),
        closed=path.closed,
        fallback_reason=path.fallback_reason,
        controls=(
            tuple(
                (_scale_point(c1, factor), _scale_point(c2, factor))
                for c1, c2 in path.controls
            )
            if path.controls is not None
            else None
        ),
        holes=tuple(
            (
                tuple(_scale_point(point, factor) for point in hole_points),
                tuple(
                    (_scale_point(c1, factor), _scale_point(c2, factor))
                    for c1, c2 in hole_controls
                ),
            )
            for hole_points, hole_controls in path.holes
        ),
    )


def _scale_ellipse(
    ellipse: EllipseAnchor | None,
    factor: float,
) -> EllipseAnchor | None:
    if ellipse is None:
        return None
    return EllipseAnchor(
        center=_scale_point(ellipse.center, factor),
        rx=ellipse.rx * factor,
        ry=ellipse.ry * factor,
        rotation=ellipse.rotation,
    )


def _scale_arc(arc: ArcAnchor | None, factor: float) -> ArcAnchor | None:
    if arc is None:
        return None
    return ArcAnchor(
        center=_scale_point(arc.center, factor),
        radius=arc.radius * factor,
        theta_start=arc.theta_start,
        theta_end=arc.theta_end,
        sweep=arc.sweep,
        large_arc=arc.large_arc,
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
        closed=stroke.closed,
    )


def _scale_quad(quad: QuadAnchor | None, factor: float) -> QuadAnchor | None:
    if quad is None:
        return None
    return QuadAnchor(corners=tuple(_scale_point(point, factor) for point in quad.corners))


def _scale_point(point: Point, factor: float) -> Point:
    return Point(point.x * factor, point.y * factor)


def _hex_color(color: Rgb) -> str:
    return f"#{color[0]:02x}{color[1]:02x}{color[2]:02x}"


def _normalize_background_color(color: BackgroundColor) -> Rgb | None:
    if color is None:
        return None
    if isinstance(color, str):
        value = color.removeprefix("#")
        if len(value) != 6:
            raise ValueError("background must be a #rrggbb color")
        try:
            return (
                int(value[0:2], 16),
                int(value[2:4], 16),
                int(value[4:6], 16),
            )
        except ValueError as error:
            raise ValueError("background must be a #rrggbb color") from error
    if isinstance(color, (list, tuple)) and len(color) == 3:
        channels = tuple(int(channel) for channel in color)
        if all(0 <= channel <= 255 for channel in channels):
            return channels
    raise ValueError("background must be a #rrggbb color or RGB triplet")


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
