"""Primitive anchor detection from flat binary mask components."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from math import asin, atan2, cos, degrees, hypot, pi, radians, sin, sqrt
from statistics import mean, pstdev
from typing import Iterable

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
    enrich_anchor_metrics,
    stroke_width_variance,
)
from morphea.classifier import ClassifierModel, classifier_prior_error
from morphea.masks import BinaryMask, MaskComponent, connected_components


@dataclass(frozen=True)
class AnchorThresholdConfig:
    stroke_circle_min_diameter: int = 6
    stroke_circle_max_aspect_error: float = 0.18
    stroke_circle_min_inner_ratio: float = 0.25
    stroke_circle_max_area_error: float = 0.45
    circle_min_diameter: int = 3
    circle_max_aspect_error: float = 0.22
    circle_max_area_error: float = 0.35
    circle_max_fit_residual: float = 0.06
    stroke_min_length: float = 4.0
    stroke_min_length_width_ratio: float = 3.0
    quad_min_fill_ratio: float = 0.35
    quad_max_fill_error: float = 0.28
    rect_max_fill_error: float = 0.08
    rounded_rect_max_fill_error: float = 0.30


def detect_primitive_anchors(
    mask: BinaryMask,
    *,
    min_area: int = 8,
    classifier_model: ClassifierModel | dict[str, tuple[float, ...]] | None = None,
    classifier_crop_tokens: tuple[tuple[float, float, float, float], ...] | None = None,
    scoring: ScoringConfig | None = None,
    thresholds: AnchorThresholdConfig | None = None,
) -> tuple[AnchorCandidate, ...]:
    """Detect simple primitive anchors from a binary mask."""

    anchors: list[AnchorCandidate] = []
    for component in connected_components(mask, min_area=min_area):
        compound_strokes = _compound_stroke_decomposition(component, thresholds)
        if compound_strokes:
            anchors.extend(compound_strokes)
            continue
        candidates = primitive_candidates_for_component(
            component,
            classifier_model=classifier_model,
            classifier_crop_tokens=classifier_crop_tokens,
            thresholds=thresholds,
        )
        if candidates:
            anchors.append(choose_best_anchor(candidates, scoring=scoring))
    return tuple(anchors)


def detect_cutout_strokes(
    mask: BinaryMask,
    *,
    min_length: int = 4,
    max_thickness: int = 3,
    color: str = "#ffffff",
) -> tuple[AnchorCandidate, ...]:
    """Detect simple background gaps inside filled components as overlay strokes."""

    cutouts: list[AnchorCandidate] = []
    for component in connected_components(mask, min_area=min_length):
        cutouts.extend(
            detect_cutout_strokes_for_component(
                component,
                min_length=min_length,
                max_thickness=max_thickness,
                color=color,
            )
        )
    return tuple(cutouts)


def detect_cutout_strokes_for_component(
    component: MaskComponent,
    *,
    min_length: int = 4,
    max_thickness: int | None = None,
    color: str = "#ffffff",
) -> tuple[AnchorCandidate, ...]:
    """Detect background-gap strokes inside one already-isolated component.

    Every enclosed gap is analyzed as one connected component, so straight,
    diagonal, and curved gaps share a single detection path and cannot
    fragment each other the way separate row/column scans did. The default
    thickness limit scales with the host: a 3 px slit is a hairline in a
    64 px icon but proportionally identical to a 6 px slit in a 128 px one.
    """

    if max_thickness is None:
        max_thickness = max(3, min(8, round(min(component.width, component.height) * 0.05)))
    return _freeform_cutout_strokes(
        component,
        min_length=min_length,
        max_thickness=max_thickness,
        color=color,
    )


def primitive_candidates_for_component(
    component: MaskComponent,
    *,
    classifier_model: ClassifierModel | dict[str, tuple[float, ...]] | None = None,
    classifier_crop_tokens: tuple[tuple[float, float, float, float], ...] | None = None,
    thresholds: AnchorThresholdConfig | None = None,
) -> tuple[AnchorCandidate, ...]:
    """Generate plausible simple-shape candidates for one component."""

    thresholds = thresholds or AnchorThresholdConfig()
    candidates: list[AnchorCandidate] = []
    # Filled primitives cannot express enclosed negative space. Thin slit
    # gaps are fine (cut-out overlay strokes cover them), but a component
    # with bulky holes must not collapse into a solid circle or rect.
    bulky_holes = _has_bulky_enclosed_holes(component)
    stroke_circle = _stroke_circle_candidate(component, thresholds)
    if stroke_circle is not None:
        candidates.append(stroke_circle)

    if not bulky_holes:
        circle = _circle_candidate(component, thresholds)
        if circle is not None:
            candidates.append(circle)

        ellipse = _ellipse_candidate(component, thresholds)
        if ellipse is not None:
            candidates.append(ellipse)

    stroke_ellipse = _stroke_ellipse_candidate(component, thresholds)
    if stroke_ellipse is not None:
        candidates.append(stroke_ellipse)

    arc = _arc_candidate(component, thresholds)
    if arc is not None:
        candidates.append(arc)

    corner_stroke = _axis_aligned_corner_stroke_candidate(component, thresholds)
    if corner_stroke is not None:
        candidates.append(corner_stroke)

    smooth_path = _smooth_stroke_path_candidate(component, thresholds)
    if smooth_path is not None:
        candidates.append(smooth_path)

    stroke = _stroke_candidate(component, thresholds)
    if stroke is not None:
        candidates.append(stroke)

    if not bulky_holes:
        rect = _rect_candidate(component, thresholds)
        if rect is not None:
            candidates.append(rect)

        rounded_rect = _rounded_rect_candidate(component, thresholds)
        if rounded_rect is not None:
            candidates.append(rounded_rect)

        quad = _quad_candidate(component, thresholds)
        if quad is not None:
            candidates.append(quad)

    candidates.append(_organic_fallback_candidate(component))
    if classifier_model is not None:
        return tuple(
            _with_classifier_prior(
                candidate,
                classifier_model,
                classifier_crop_tokens=classifier_crop_tokens,
            )
            for candidate in candidates
        )
    return tuple(candidates)


ORGANIC_FALLBACK_MAX_NODES = 16
# The roadmap ranking demands that the generic fallback only wins when no
# semantic candidate passes its plausibility gates, so the candidate carries
# a flat ranking penalty on top of its node complexity.
ORGANIC_FALLBACK_RANK_PENALTY = 0.35


def _compound_stroke_decomposition(
    component: MaskComponent,
    thresholds: AnchorThresholdConfig | None,
) -> tuple[AnchorCandidate, ...]:
    """Split obvious connected stroke glyphs before organic fallback.

    This is intentionally narrow: it covers lochless plus/x-like glyphs
    whose pixels are almost entirely explained by two constant-width bands.
    More complex icons such as circle-plus-handle compounds need their own
    decomposition later.
    """

    thresholds = thresholds or AnchorThresholdConfig()
    if component.area < max(16, thresholds.stroke_min_length * 4):
        return ()
    density = component.area / max(component.width * component.height, 1)
    node_compound = _multi_circular_node_compound_strokes(component, thresholds)
    if node_compound:
        return node_compound
    circle_compound = _circular_gap_compound_strokes(component, thresholds)
    if circle_compound:
        return circle_compound
    crosshair_compound = _radial_crosshair_compound_strokes(component, thresholds)
    if crosshair_compound:
        return crosshair_compound
    pointer_compound = _mouse_pointer_compound_strokes(component, thresholds)
    if pointer_compound:
        return pointer_compound
    axis_arrows = _axis_aligned_arrow_strokes(component, thresholds)
    if axis_arrows:
        return axis_arrows
    axis_grid = _axis_aligned_grid_strokes(component, thresholds)
    if axis_grid:
        return axis_grid
    if density > 0.48:
        return ()
    if _has_bulky_enclosed_holes(component):
        return ()
    axis_cross = _axis_aligned_cross_strokes(component, thresholds)
    if axis_cross:
        return axis_cross
    return _diagonal_cross_strokes(component, thresholds)


def _axis_aligned_cross_strokes(
    component: MaskComponent,
    thresholds: AnchorThresholdConfig,
) -> tuple[AnchorCandidate, ...]:
    width = component.width
    height = component.height
    if (
        width < thresholds.stroke_min_length * 3
        or height < thresholds.stroke_min_length * 3
        or max(width, height) / max(min(width, height), 1) > 1.45
    ):
        return ()

    row_counts = _component_row_counts(component)
    long_rows = tuple(y for y, count in row_counts if count >= width * 0.72)
    column_counts = _component_column_counts(component)
    long_columns = tuple(
        x for x, count in column_counts if count >= height * 0.72
    )
    if len(long_rows) < 2 or len(long_columns) < 2:
        return ()

    row_set = set(long_rows)
    column_set = set(long_columns)
    explained = sum(
        1 for x, y in component.pixels if y in row_set or x in column_set
    )
    if explained / component.area < 0.92:
        return ()

    stroke_width_h = float(len(long_rows))
    stroke_width_v = float(len(long_columns))
    if min(stroke_width_h, stroke_width_v) <= 0:
        return ()
    if max(stroke_width_h, stroke_width_v) / min(stroke_width_h, stroke_width_v) > 1.6:
        return ()

    min_x, min_y, max_x, max_y = component.bounds
    center_y = sum(long_rows) / len(long_rows)
    center_x = sum(long_columns) / len(long_columns)
    horizontal = _simple_stroke_anchor(
        Point(min_x + stroke_width_h / 2, center_y),
        Point(max_x - stroke_width_h / 2, center_y),
        stroke_width_h,
        kind_metric="axis_cross_horizontal",
    )
    vertical = _simple_stroke_anchor(
        Point(center_x, min_y + stroke_width_v / 2),
        Point(center_x, max_y - stroke_width_v / 2),
        stroke_width_v,
        kind_metric="axis_cross_vertical",
    )
    return (horizontal, vertical)


def _axis_aligned_grid_strokes(
    component: MaskComponent,
    thresholds: AnchorThresholdConfig,
) -> tuple[AnchorCandidate, ...]:
    """Split connected horizontal/vertical stroke grids and stroked frames.

    Lucide-style stroked rectangles, table grids, and frame icons form one
    connected component with large interior gaps. Row/column spans see those
    holes as filled, so this path uses true ink counts per projection band.
    """

    if component.width < thresholds.stroke_min_length * 4:
        return ()
    if component.height < thresholds.stroke_min_length * 4:
        return ()

    min_x, min_y, max_x, max_y = component.bounds
    row_bands = _dense_projection_bands(
        _component_row_counts(component),
        minimum_count=component.width * 0.72,
    )
    column_bands = _dense_projection_bands(
        _component_column_counts(component),
        minimum_count=component.height * 0.72,
    )
    if len(row_bands) + len(column_bands) < 4:
        return ()
    if not row_bands or not column_bands:
        return ()
    if len(row_bands) > 6 or len(column_bands) > 6:
        return ()
    band_widths = [
        bottom - top + 1
        for top, bottom in (*row_bands, *column_bands)
    ]
    if max(band_widths, default=0) > max(
        8.0,
        min(component.width, component.height) * 0.18,
    ):
        return ()
    if (
        len(row_bands) == 2
        and len(column_bands) == 2
        and max(component.width, component.height) <= 24
        and _has_bulky_enclosed_holes(component)
    ):
        return ()

    covered_pixels = _projection_band_pixels(component, row_bands, column_bands)
    if len(covered_pixels) / component.area < 0.55:
        return ()

    anchors: list[AnchorCandidate] = []
    for band in row_bands:
        top, bottom = band
        stroke_width = float(bottom - top + 1)
        center_y = (top + bottom) / 2
        left, right = _row_band_horizontal_extent(
            component,
            band,
            column_bands=column_bands,
            stroke_width=stroke_width,
        )
        anchors.append(
            _simple_stroke_anchor(
                Point(left + stroke_width / 2, center_y),
                Point(right - stroke_width / 2, center_y),
                stroke_width,
                kind_metric="axis_grid_horizontal",
            )
        )
    for band in column_bands:
        left, right = band
        stroke_width = float(right - left + 1)
        center_x = (left + right) / 2
        top, bottom = _column_band_vertical_extent(
            component,
            band,
            row_bands=row_bands,
            stroke_width=stroke_width,
        )
        anchors.append(
            _simple_stroke_anchor(
                Point(center_x, top + stroke_width / 2),
                Point(center_x, bottom - stroke_width / 2),
                stroke_width,
                kind_metric="axis_grid_vertical",
            )
        )

    residual_pixels = frozenset(component.pixels - covered_pixels)
    if residual_pixels:
        residual_area = len(residual_pixels)
        residual_mask = BinaryMask(
            width=max_x + 1,
            height=max_y + 1,
            pixels=residual_pixels,
        )
        residual_anchors = detect_primitive_anchors(
            residual_mask,
            min_area=max(2, int(thresholds.stroke_min_length)),
            thresholds=thresholds,
        )
        if not residual_anchors and residual_area > component.area * 0.08:
            return ()
        anchors.extend(
            _with_metric(anchor, "axis_grid_residual", 1.0)
            for anchor in residual_anchors
        )

    return tuple(anchors)


def _axis_aligned_arrow_strokes(
    component: MaskComponent,
    thresholds: AnchorThresholdConfig,
) -> tuple[AnchorCandidate, ...]:
    if component.width < thresholds.stroke_min_length * 5:
        return ()
    if component.height < thresholds.stroke_min_length * 5:
        return ()
    if component.area / max(component.width * component.height, 1) > 0.44:
        return ()

    row_bands = _dense_projection_bands(
        _component_row_counts(component),
        minimum_count=component.width * 0.86,
    )
    column_bands = _dense_projection_bands(
        _component_column_counts(component),
        minimum_count=component.height * 0.86,
    )
    if not row_bands and not column_bands:
        return ()
    if len(row_bands) > 2 or len(column_bands) > 2:
        return ()

    anchors: list[AnchorCandidate] = []
    arrowheads: list[AnchorCandidate] = []
    for band in row_bands:
        top, bottom = band
        stroke_width = float(bottom - top + 1)
        center_y = (top + bottom) / 2
        anchors.append(
            _simple_stroke_anchor(
                Point(component.bounds[0] + stroke_width / 2, center_y),
                Point(component.bounds[2] - stroke_width / 2, center_y),
                stroke_width,
                kind_metric="axis_arrow_horizontal_shaft",
            )
        )
        for at_start in (True, False):
            head = _horizontal_arrowhead_stroke(
                component,
                row_band=band,
                at_start=at_start,
                stroke_width=stroke_width,
            )
            if head is not None:
                arrowheads.append(head)

    for band in column_bands:
        left, right = band
        stroke_width = float(right - left + 1)
        center_x = (left + right) / 2
        anchors.append(
            _simple_stroke_anchor(
                Point(center_x, component.bounds[1] + stroke_width / 2),
                Point(center_x, component.bounds[3] - stroke_width / 2),
                stroke_width,
                kind_metric="axis_arrow_vertical_shaft",
            )
        )
        for at_start in (True, False):
            head = _vertical_arrowhead_stroke(
                component,
                column_band=band,
                at_start=at_start,
                stroke_width=stroke_width,
            )
            if head is not None:
                arrowheads.append(head)

    if not arrowheads:
        return ()
    return tuple(anchors + arrowheads)


def _mouse_pointer_compound_strokes(
    component: MaskComponent,
    thresholds: AnchorThresholdConfig,
) -> tuple[AnchorCandidate, ...]:
    if min(component.width, component.height) < thresholds.stroke_min_length * 8:
        return ()
    if max(component.width, component.height) > thresholds.stroke_min_length * 20:
        return ()
    aspect_ratio = component.width / max(component.height, 1)
    if aspect_ratio < 0.78 or aspect_ratio > 1.28:
        return ()
    density = component.area / max(component.width * component.height, 1)
    if density < 0.24 or density > 0.42:
        return ()

    min_x, min_y, _, _ = component.bounds
    width = float(component.width)
    height = float(component.height)
    top_left = sum(
        1
        for x, y in component.pixels
        if x <= min_x + width * 0.26 and y <= min_y + height * 0.26
    )
    top_right = sum(
        1
        for x, y in component.pixels
        if x >= min_x + width * 0.65 and y <= min_y + height * 0.35
    )
    bottom_left = sum(
        1
        for x, y in component.pixels
        if x <= min_x + width * 0.35 and y >= min_y + height * 0.65
    )
    bottom_right = sum(
        1
        for x, y in component.pixels
        if x >= min_x + width * 0.70 and y >= min_y + height * 0.70
    )
    center = sum(
        1
        for x, y in component.pixels
        if min_x + width * 0.35 <= x <= min_x + width * 0.65
        and min_y + height * 0.35 <= y <= min_y + height * 0.65
    )
    main_diagonal = sum(
        1
        for x, y in component.pixels
        if abs(((x - min_x) / width) - ((y - min_y) / height)) < 0.12
    )
    anti_diagonal = sum(
        1
        for x, y in component.pixels
        if abs(((x - min_x) / width) + ((y - min_y) / height) - 1.0) < 0.12
    )
    if top_left < component.area * 0.12 or bottom_right < component.area * 0.06:
        return ()
    if top_right > component.area * 0.09 or bottom_left > component.area * 0.09:
        return ()
    if center < component.area * 0.05 or center > component.area * 0.16:
        return ()
    if main_diagonal < max(anti_diagonal * 1.4, component.area * 0.22):
        return ()

    stroke_width = max(2.0, min(width, height) * 0.105)
    outline_points = (
        (0.095, 0.061),
        (0.061, 0.095),
        (0.401, 0.931),
        (0.450, 0.928),
        (0.532, 0.610),
        (0.608, 0.533),
        (0.928, 0.450),
        (0.931, 0.401),
    )
    outline = _simple_stroke_path_anchor(
        tuple(
            Point(min_x + width * x, min_y + height * y)
            for x, y in outline_points
        ),
        stroke_width,
        kind_metric="mouse_pointer_outline",
        closed=True,
    )
    diagonal = _simple_stroke_anchor(
        Point(min_x + width * 0.56, min_y + height * 0.56),
        Point(min_x + width * 0.895, min_y + height * 0.895),
        stroke_width,
        kind_metric="mouse_pointer_diagonal",
    )
    return (outline, diagonal)


def _horizontal_arrowhead_stroke(
    component: MaskComponent,
    *,
    row_band: tuple[int, int],
    at_start: bool,
    stroke_width: float,
) -> AnchorCandidate | None:
    min_x, _, max_x, _ = component.bounds
    top, bottom = row_band
    center_y = (top + bottom) / 2
    window = max(stroke_width * 3.2, component.width * 0.32)
    cross_window = max(stroke_width * 2.4, min(component.width, component.height) * 0.24)
    if at_start:
        patch = [
            (x, y)
            for x, y in component.pixels
            if x <= min_x + window
            and abs(y - center_y) <= cross_window
            and not top <= y <= bottom
        ]
        tip = Point(min_x + stroke_width / 2, center_y)
    else:
        patch = [
            (x, y)
            for x, y in component.pixels
            if x >= max_x - window
            and abs(y - center_y) <= cross_window
            and not top <= y <= bottom
        ]
        tip = Point(max_x - stroke_width / 2, center_y)
    upper = [(x, y) for x, y in patch if y < top]
    lower = [(x, y) for x, y in patch if y > bottom]
    if min(len(upper), len(lower)) < max(4, int(stroke_width * 1.2)):
        return None
    if not _pixels_follow_diagonal_arm(upper):
        return None
    if not _pixels_follow_diagonal_arm(lower):
        return None

    if at_start:
        upper_x = max(x for x, _ in upper)
        lower_x = max(x for x, _ in lower)
        arm_x = (upper_x + lower_x) / 2
        if arm_x - tip.x < stroke_width * 1.1:
            return None
    else:
        upper_x = min(x for x, _ in upper)
        lower_x = min(x for x, _ in lower)
        arm_x = (upper_x + lower_x) / 2
        if tip.x - arm_x < stroke_width * 1.1:
            return None

    upper_point = Point(arm_x, min(y for _, y in upper) + stroke_width / 2)
    lower_point = Point(arm_x, max(y for _, y in lower) - stroke_width / 2)
    if min(upper_point.distance_to(tip), lower_point.distance_to(tip)) < stroke_width:
        return None
    return _simple_stroke_path_anchor(
        (upper_point, tip, lower_point),
        stroke_width,
        kind_metric="axis_arrow_head",
    )


def _vertical_arrowhead_stroke(
    component: MaskComponent,
    *,
    column_band: tuple[int, int],
    at_start: bool,
    stroke_width: float,
) -> AnchorCandidate | None:
    _, min_y, _, max_y = component.bounds
    left, right = column_band
    center_x = (left + right) / 2
    window = max(stroke_width * 3.2, component.height * 0.32)
    cross_window = max(stroke_width * 2.4, min(component.width, component.height) * 0.24)
    if at_start:
        patch = [
            (x, y)
            for x, y in component.pixels
            if y <= min_y + window
            and abs(x - center_x) <= cross_window
            and not left <= x <= right
        ]
        tip = Point(center_x, min_y + stroke_width / 2)
    else:
        patch = [
            (x, y)
            for x, y in component.pixels
            if y >= max_y - window
            and abs(x - center_x) <= cross_window
            and not left <= x <= right
        ]
        tip = Point(center_x, max_y - stroke_width / 2)
    left_arm = [(x, y) for x, y in patch if x < left]
    right_arm = [(x, y) for x, y in patch if x > right]
    if min(len(left_arm), len(right_arm)) < max(4, int(stroke_width * 1.2)):
        return None
    if not _pixels_follow_diagonal_arm(left_arm):
        return None
    if not _pixels_follow_diagonal_arm(right_arm):
        return None

    if at_start:
        left_y = max(y for _, y in left_arm)
        right_y = max(y for _, y in right_arm)
        arm_y = (left_y + right_y) / 2
        if arm_y - tip.y < stroke_width * 1.1:
            return None
    else:
        left_y = min(y for _, y in left_arm)
        right_y = min(y for _, y in right_arm)
        arm_y = (left_y + right_y) / 2
        if tip.y - arm_y < stroke_width * 1.1:
            return None

    left_point = Point(min(x for x, _ in left_arm) + stroke_width / 2, arm_y)
    right_point = Point(max(x for x, _ in right_arm) - stroke_width / 2, arm_y)
    if min(left_point.distance_to(tip), right_point.distance_to(tip)) < stroke_width:
        return None
    return _simple_stroke_path_anchor(
        (left_point, tip, right_point),
        stroke_width,
        kind_metric="axis_arrow_head",
    )


def _pixels_follow_diagonal_arm(pixels: list[tuple[int, int]]) -> bool:
    if len(pixels) < 4:
        return False
    component = MaskComponent(frozenset(pixels))
    if min(component.width, component.height) < 3:
        return False
    axis = _principal_axis(component)
    if axis is None:
        return False
    _, direction, *_ = axis
    dx, dy = direction
    return min(abs(dx), abs(dy)) >= 0.32


def _circular_gap_compound_strokes(
    component: MaskComponent,
    thresholds: AnchorThresholdConfig,
) -> tuple[AnchorCandidate, ...]:
    gaps = tuple(
        gap
        for gap in _interior_gap_components(component, min_area=16)
        if not _gap_open_to_background(gap, component)
    )
    if not gaps:
        return ()
    gap = max(gaps, key=lambda candidate: candidate.area)
    if gap.area < component.area * 0.2:
        return ()
    if max(gap.width, gap.height) < thresholds.stroke_circle_min_diameter:
        return ()
    gap_aspect_error = abs(gap.width - gap.height) / max(gap.width, gap.height)
    if gap_aspect_error > 0.12:
        return ()

    center, inner_radius, gap_fit_residual = _fit_circle_from_boundary(
        gap,
        fallback_radius=max(gap.width, gap.height) / 2,
    )
    if gap_fit_residual > 0.05:
        return ()

    min_x, min_y, max_x, max_y = component.bounds
    gap_min_x, gap_min_y, gap_max_x, gap_max_y = gap.bounds
    side_widths = [
        gap_min_x - min_x,
        gap_min_y - min_y,
        max_x - gap_max_x,
        max_y - gap_max_y,
    ]
    positive_widths = [width for width in side_widths if width > 0]
    if not positive_widths:
        return ()
    stroke_width = float(min(positive_widths))
    if stroke_width < 2.0 or stroke_width > inner_radius * 0.8:
        return ()

    radius = inner_radius + stroke_width / 2
    circle = AnchorCandidate(
        kind=AnchorKind.STROKE_CIRCLE,
        raster_error=gap_fit_residual + gap_aspect_error,
        node_count=1,
        parameter_count=4,
        circle=CircleAnchor(
            center=center,
            radius=radius,
            samples=tuple(Point(x, y) for x, y in component.boundary_pixels),
        ),
        stroke=StrokeAnchor(centerline=(), width_samples=(stroke_width,)),
        metrics={
            "circular_gap_compound": 1.0,
            "circle_fit_residual_error": gap_fit_residual,
        },
    )
    anchors = [enrich_anchor_metrics(circle)]

    band_tolerance = stroke_width * 0.78
    circle_pixels = frozenset(
        (x, y)
        for x, y in component.pixels
        if abs(Point(x, y).distance_to(center) - radius) <= band_tolerance
    )
    if len(circle_pixels) < component.area * 0.35:
        return ()
    residual_pixels = frozenset(component.pixels - circle_pixels)
    if residual_pixels and _balanced_residual_lobes(
        side_widths,
        residual_ratio=len(residual_pixels) / component.area,
    ):
        irregular_outline = _irregular_circular_outline_path(component, stroke_width)
        if irregular_outline is not None:
            return (irregular_outline,)
    if (
        not residual_pixels
        and max(component.width, component.height) > thresholds.stroke_circle_min_diameter + 4
        and _stroke_circle_candidate(component, thresholds) is not None
    ):
        return ()
    if residual_pixels:
        if (
            max(component.width, component.height) >= 96
            and len(residual_pixels) < component.area * 0.25
        ):
            return tuple(anchors)
        residual_mask = BinaryMask(
            width=max_x + 1,
            height=max_y + 1,
            pixels=residual_pixels,
        )
        residual_anchors = _circular_gap_residual_anchors(
            residual_mask,
            center=center,
            stroke_width=stroke_width,
            thresholds=thresholds,
        )
        if not residual_anchors and len(residual_pixels) > component.area * 0.08:
            return ()
        anchors.extend(
            _with_metric(anchor, "circular_gap_residual", 1.0)
            for anchor in residual_anchors
        )

    return tuple(anchors)


def _balanced_residual_lobes(
    side_widths: list[int],
    *,
    residual_ratio: float,
) -> bool:
    positive = [width for width in side_widths if width > 0]
    if not positive:
        return False
    return residual_ratio <= 0.05 and max(positive) / min(positive) <= 1.25


def _irregular_circular_outline_path(
    component: MaskComponent,
    stroke_width: float,
) -> AnchorCandidate | None:
    outline = _traced_outline(component)
    if outline is None or len(outline) < 32:
        return None
    corners = _detect_outline_corners(outline)
    smoothed = _smoothed_closed_outline(outline, window=2, pinned=corners)
    points, _, fit_error = _fit_closed_bezier_outline(
        smoothed,
        max_segments=16,
        corners=corners,
    )
    if len(points) < 10 or len(corners) > 2:
        return None
    anchor = _simple_stroke_path_anchor(
        tuple(points),
        stroke_width,
        kind_metric="irregular_circular_outline",
        closed=True,
    )
    return _with_metric(anchor, "closed_outline_fit_error", fit_error)


def _circular_gap_residual_anchors(
    mask: BinaryMask,
    *,
    center: Point,
    stroke_width: float,
    thresholds: AnchorThresholdConfig,
) -> tuple[AnchorCandidate, ...]:
    anchors: list[AnchorCandidate] = []
    min_area = max(2, int(thresholds.stroke_min_length))
    for component in connected_components(mask, min_area=min_area):
        stub = _circular_gap_residual_stub(
            component,
            center=center,
            stroke_width=stroke_width,
        )
        if stub is not None:
            anchors.append(stub)
            continue
        anchors.extend(
            detect_primitive_anchors(
                BinaryMask(
                    width=mask.width,
                    height=mask.height,
                    pixels=component.pixels,
                ),
                min_area=min_area,
                thresholds=thresholds,
            )
        )
    return tuple(anchors)


def _circular_gap_residual_stub(
    component: MaskComponent,
    *,
    center: Point,
    stroke_width: float,
) -> AnchorCandidate | None:
    if min(component.width, component.height) < 3:
        return None
    if max(component.width, component.height) > max(10.0, stroke_width * 2.2):
        return None
    aspect_ratio = max(component.width, component.height) / min(
        component.width,
        component.height,
    )
    if aspect_ratio > 1.6:
        return None
    density = component.area / max(component.width * component.height, 1)
    if density < 0.4 or density > 0.9:
        return None
    horizontal_offset = component.centroid.x - center.x
    if abs(horizontal_offset) < max(component.width, stroke_width):
        return None
    if component.centroid.y <= center.y + max(component.height, stroke_width) * 0.75:
        return None

    min_x, min_y, max_x, max_y = component.bounds
    stub_width = min(
        max(stroke_width, min(component.width, component.height) * 0.7),
        max(component.width, component.height) * 0.85,
    )
    near_y = min_y - stub_width * 0.25
    far_y = max_y - stub_width * 0.35
    if horizontal_offset < 0:
        start = Point(max_x + stub_width * 0.25, near_y)
        end = Point(min_x + stub_width * 0.4, far_y)
    else:
        start = Point(min_x - stub_width * 0.25, near_y)
        end = Point(max_x - stub_width * 0.4, far_y)
    if start.distance_to(end) < max(3.0, stroke_width * 0.7):
        return None
    return _simple_stroke_anchor(
        start,
        end,
        stub_width,
        kind_metric="circular_gap_residual_stub",
    )


def _radial_crosshair_residual_anchors(
    mask: BinaryMask,
    *,
    center: Point,
    thresholds: AnchorThresholdConfig,
) -> tuple[AnchorCandidate, ...]:
    anchors: list[AnchorCandidate] = []
    min_area = max(2, int(thresholds.stroke_min_length))
    for component in connected_components(mask, min_area=min_area):
        stub = _axis_aligned_stub_stroke(
            component,
            kind_metric="radial_crosshair_stub",
            radial_center=center,
        )
        if stub is not None:
            anchors.append(stub)
            continue
        anchors.extend(
            detect_primitive_anchors(
                BinaryMask(
                    width=mask.width,
                    height=mask.height,
                    pixels=component.pixels,
                ),
                min_area=min_area,
                thresholds=thresholds,
            )
        )
    return tuple(anchors)


def _radial_crosshair_band_stubs(
    component: MaskComponent,
    *,
    row_band: tuple[int, int],
    column_band: tuple[int, int],
    stroke_width: float,
) -> tuple[AnchorCandidate, ...]:
    anchors: list[AnchorCandidate] = []
    center_y = (row_band[0] + row_band[1]) / 2
    for left, right in _coordinate_clusters(
        x for x, y in component.pixels if row_band[0] <= y <= row_band[1]
    ):
        if right - left + 1 < stroke_width * 1.5:
            continue
        anchors.append(
            _simple_stroke_anchor(
                Point(left + stroke_width / 2, center_y),
                Point(right - stroke_width / 2, center_y),
                stroke_width,
                kind_metric="radial_crosshair_stub",
            )
        )
    center_x = (column_band[0] + column_band[1]) / 2
    for top, bottom in _coordinate_clusters(
        y for x, y in component.pixels if column_band[0] <= x <= column_band[1]
    ):
        if bottom - top + 1 < stroke_width * 1.5:
            continue
        anchors.append(
            _simple_stroke_anchor(
                Point(center_x, top + stroke_width / 2),
                Point(center_x, bottom - stroke_width / 2),
                stroke_width,
                kind_metric="radial_crosshair_stub",
            )
        )
    return tuple(anchors)


def _coordinate_clusters(coordinates: Iterable[int]) -> tuple[tuple[int, int], ...]:
    clusters: list[tuple[int, int]] = []
    start: int | None = None
    previous: int | None = None
    for coordinate in sorted(set(coordinates)):
        if start is None:
            start = previous = coordinate
            continue
        if previous is not None and coordinate == previous + 1:
            previous = coordinate
            continue
        if previous is not None:
            clusters.append((start, previous))
        start = previous = coordinate
    if start is not None and previous is not None:
        clusters.append((start, previous))
    return tuple(clusters)


def _axis_aligned_stub_stroke(
    component: MaskComponent,
    *,
    kind_metric: str,
    radial_center: Point | None = None,
) -> AnchorCandidate | None:
    horizontal = component.width >= component.height * 1.5
    vertical = component.height >= component.width * 1.5
    if (
        radial_center is not None
        and max(component.width, component.height) <= 8
    ):
        offset_x = abs(component.centroid.x - radial_center.x)
        offset_y = abs(component.centroid.y - radial_center.y)
        horizontal = offset_x >= offset_y
        vertical = not horizontal
    if horizontal and component.height <= 8:
        min_x, min_y, max_x, max_y = component.bounds
        stroke_width = float(component.height)
        center_y = (min_y + max_y) / 2
        return _simple_stroke_anchor(
            Point(min_x + stroke_width / 2, center_y),
            Point(max_x - stroke_width / 2, center_y),
            stroke_width,
            kind_metric=kind_metric,
        )
    if vertical and component.width <= 8:
        min_x, min_y, max_x, max_y = component.bounds
        stroke_width = float(component.width)
        center_x = (min_x + max_x) / 2
        return _simple_stroke_anchor(
            Point(center_x, min_y + stroke_width / 2),
            Point(center_x, max_y - stroke_width / 2),
            stroke_width,
            kind_metric=kind_metric,
        )
    return None


def _multi_circular_node_compound_strokes(
    component: MaskComponent,
    thresholds: AnchorThresholdConfig,
) -> tuple[AnchorCandidate, ...]:
    gap_fits: list[tuple[MaskComponent, Point, float, float]] = []
    for gap in _interior_gap_components(component, min_area=16):
        if _gap_open_to_background(gap, component):
            continue
        if max(gap.width, gap.height) < thresholds.stroke_circle_min_diameter:
            continue
        aspect_error = abs(gap.width - gap.height) / max(gap.width, gap.height)
        if aspect_error > 0.25:
            continue
        center, inner_radius, fit_residual = _fit_circle_from_boundary(
            gap,
            fallback_radius=max(gap.width, gap.height) / 2,
        )
        if fit_residual > 0.08:
            continue
        gap_fits.append((gap, center, inner_radius, fit_residual))
    if len(gap_fits) < 3:
        return ()

    min_x, _, max_x, max_y = component.bounds
    anchors: list[AnchorCandidate] = []
    circle_pixels: set[tuple[int, int]] = set()
    for gap, center, inner_radius, fit_residual in gap_fits:
        stroke_width = max(3.0, min(8.0, inner_radius * 1.2))
        radius = inner_radius + stroke_width / 2
        circle = AnchorCandidate(
            kind=AnchorKind.STROKE_CIRCLE,
            raster_error=fit_residual,
            node_count=1,
            parameter_count=4,
            circle=CircleAnchor(
                center=center,
                radius=radius,
                samples=tuple(Point(x, y) for x, y in gap.boundary_pixels),
            ),
            stroke=StrokeAnchor(centerline=(), width_samples=(stroke_width,)),
            metrics={
                "multi_circular_node_compound": 1.0,
                "circle_fit_residual_error": fit_residual,
            },
        )
        anchors.append(enrich_anchor_metrics(circle))
        band_tolerance = stroke_width * 0.85
        circle_pixels.update(
            (x, y)
            for x, y in component.pixels
            if abs(Point(x, y).distance_to(center) - radius) <= band_tolerance
        )

    if len(circle_pixels) < component.area * 0.4:
        return ()
    residual_pixels = frozenset(component.pixels - circle_pixels)
    if residual_pixels:
        residual_mask = BinaryMask(
            width=max_x + 1,
            height=max_y + 1,
            pixels=residual_pixels,
        )
        residual_anchors = detect_primitive_anchors(
            residual_mask,
            min_area=max(2, int(thresholds.stroke_min_length)),
            thresholds=thresholds,
        )
        if not residual_anchors and len(residual_pixels) > component.area * 0.08:
            return ()
        anchors.extend(
            _with_metric(anchor, "multi_circular_node_residual", 1.0)
            for anchor in residual_anchors
        )

    return tuple(anchors)


def _radial_crosshair_compound_strokes(
    component: MaskComponent,
    thresholds: AnchorThresholdConfig,
) -> tuple[AnchorCandidate, ...]:
    if max(component.width, component.height) < thresholds.stroke_min_length * 8:
        return ()
    aspect_error = abs(component.width - component.height) / max(component.width, component.height)
    if aspect_error > 0.12:
        return ()
    gaps = tuple(
        gap
        for gap in _interior_gap_components(component, min_area=16)
        if not _gap_open_to_background(gap, component)
    )
    if not gaps or max(gap.area for gap in gaps) < component.area * 0.6:
        return ()

    min_x, min_y, max_x, max_y = component.bounds
    center = Point((min_x + max_x) / 2, (min_y + max_y) / 2)
    row_bands = _dense_projection_bands(
        _component_row_counts(component),
        minimum_count=component.width * 0.45,
    )
    column_bands = _dense_projection_bands(
        _component_column_counts(component),
        minimum_count=component.height * 0.45,
    )
    central_rows = [
        band
        for band in row_bands
        if abs(((band[0] + band[1]) / 2) - center.y) <= component.height * 0.12
    ]
    central_columns = [
        band
        for band in column_bands
        if abs(((band[0] + band[1]) / 2) - center.x) <= component.width * 0.12
    ]
    if len(central_rows) != 1 or len(central_columns) != 1:
        return ()
    row_width = central_rows[0][1] - central_rows[0][0] + 1
    column_width = central_columns[0][1] - central_columns[0][0] + 1
    if max(row_width, column_width) / max(min(row_width, column_width), 1) > 1.8:
        return ()

    stroke_width = float((row_width + column_width) / 2)
    outer_radius = min(component.width, component.height) / 2 + 0.5
    radius = outer_radius - stroke_width / 2
    if radius <= stroke_width:
        return ()
    circle = AnchorCandidate(
        kind=AnchorKind.STROKE_CIRCLE,
        raster_error=aspect_error,
        node_count=1,
        parameter_count=4,
        circle=CircleAnchor(
            center=center,
            radius=radius,
            samples=tuple(Point(x, y) for x, y in component.boundary_pixels),
        ),
        stroke=StrokeAnchor(centerline=(), width_samples=(stroke_width,)),
        metrics={
            "radial_crosshair_compound": 1.0,
            "circle_fit_residual_error": aspect_error,
        },
    )
    anchors = [enrich_anchor_metrics(circle)]
    band_tolerance = stroke_width * 0.78
    circle_pixels = frozenset(
        (x, y)
        for x, y in component.pixels
        if abs(Point(x, y).distance_to(center) - radius) <= band_tolerance
    )
    if len(circle_pixels) < component.area * 0.35:
        return ()
    stub_anchors = _radial_crosshair_band_stubs(
        component,
        row_band=central_rows[0],
        column_band=central_columns[0],
        stroke_width=stroke_width,
    )
    if len(stub_anchors) >= 4:
        anchors.extend(stub_anchors)
        return tuple(anchors)
    residual_pixels = frozenset(component.pixels - circle_pixels)
    if residual_pixels:
        residual_mask = BinaryMask(
            width=max_x + 1,
            height=max_y + 1,
            pixels=residual_pixels,
        )
        residual_anchors = _radial_crosshair_residual_anchors(
            residual_mask,
            center=center,
            thresholds=thresholds,
        )
        if not residual_anchors and len(residual_pixels) > component.area * 0.08:
            return ()
        anchors.extend(
            _with_metric(anchor, "radial_crosshair_residual", 1.0)
            for anchor in residual_anchors
        )

    return tuple(anchors)


def _row_band_horizontal_extent(
    component: MaskComponent,
    band: tuple[int, int],
    *,
    column_bands: tuple[tuple[int, int], ...],
    stroke_width: float,
) -> tuple[int, int]:
    top, bottom = band
    xs = [x for x, y in component.pixels if top <= y <= bottom]
    column_coordinates = {
        coordinate
        for left, right in column_bands
        for coordinate in range(left, right + 1)
    }
    core_xs = [
        x
        for x, y in component.pixels
        if top <= y <= bottom and x not in column_coordinates
    ]
    return _band_extent_with_core(xs, core_xs, stroke_width=stroke_width)


def _column_band_vertical_extent(
    component: MaskComponent,
    band: tuple[int, int],
    *,
    row_bands: tuple[tuple[int, int], ...],
    stroke_width: float,
) -> tuple[int, int]:
    left, right = band
    ys = [y for x, y in component.pixels if left <= x <= right]
    row_coordinates = {
        coordinate
        for top, bottom in row_bands
        for coordinate in range(top, bottom + 1)
    }
    core_ys = [
        y
        for x, y in component.pixels
        if left <= x <= right and y not in row_coordinates
    ]
    return _band_extent_with_core(ys, core_ys, stroke_width=stroke_width)


def _band_extent_with_core(
    values: list[int],
    core_values: list[int],
    *,
    stroke_width: float,
) -> tuple[int, int]:
    lower = min(values)
    upper = max(values)
    if not core_values:
        return lower, upper
    core_lower = min(core_values)
    core_upper = max(core_values)
    cap_allowance = stroke_width * 1.5
    if core_lower - lower > cap_allowance:
        lower = max(lower, round(core_lower - stroke_width))
    if upper - core_upper > cap_allowance:
        upper = min(upper, round(core_upper + stroke_width))
    return lower, upper


def _axis_aligned_corner_stroke_candidate(
    component: MaskComponent,
    thresholds: AnchorThresholdConfig,
) -> AnchorCandidate | None:
    if component.width < thresholds.stroke_min_length * 2:
        return None
    if component.height < thresholds.stroke_min_length * 2:
        return None
    density = component.area / max(component.width * component.height, 1)
    if density < 0.3 or density > 0.72:
        return None

    row_bands = _dense_projection_bands(
        _component_row_counts(component),
        minimum_count=component.width * 0.45,
    )
    column_bands = _dense_projection_bands(
        _component_column_counts(component),
        minimum_count=component.height * 0.45,
    )
    if len(row_bands) != 1 or len(column_bands) != 1:
        return None
    row_band = row_bands[0]
    column_band = column_bands[0]
    row_width = row_band[1] - row_band[0] + 1
    column_width = column_band[1] - column_band[0] + 1
    if min(row_width, column_width) < 2:
        return None
    if max(row_width, column_width) / min(row_width, column_width) > 1.8:
        return None

    covered = _projection_band_pixels(component, row_bands, column_bands)
    if len(covered) / component.area < 0.88:
        return None

    min_x, min_y, max_x, max_y = component.bounds
    row_center = (row_band[0] + row_band[1]) / 2
    column_center = (column_band[0] + column_band[1]) / 2
    near_top = row_center <= min_y + component.height * 0.35
    near_bottom = row_center >= max_y - component.height * 0.35
    near_left = column_center <= min_x + component.width * 0.35
    near_right = column_center >= max_x - component.width * 0.35
    if not (near_top or near_bottom) or not (near_left or near_right):
        return None

    stroke_width = float((row_width + column_width) / 2)
    horizontal_left, horizontal_right = _row_band_horizontal_extent(
        component,
        row_band,
        column_bands=column_bands,
        stroke_width=stroke_width,
    )
    vertical_top, vertical_bottom = _column_band_vertical_extent(
        component,
        column_band,
        row_bands=row_bands,
        stroke_width=stroke_width,
    )
    horizontal_far = (
        Point(horizontal_right - stroke_width / 2, row_center)
        if near_left
        else Point(horizontal_left + stroke_width / 2, row_center)
    )
    vertical_far = (
        Point(column_center, vertical_bottom - stroke_width / 2)
        if near_top
        else Point(column_center, vertical_top + stroke_width / 2)
    )
    corner = Point(column_center, row_center)
    stroke = StrokeAnchor(
        centerline=(vertical_far, corner, horizontal_far),
        width_samples=(stroke_width,),
        cap_style="round",
        join_style="round",
    )
    if _stroke_bounds_exceed_component(stroke, component):
        return None
    candidate = AnchorCandidate(
        kind=AnchorKind.STROKE_PATH,
        raster_error=0.0,
        node_count=3,
        parameter_count=7,
        stroke=stroke,
        metrics={
            "axis_aligned_corner_stroke": 1.0,
            "stroke_width_variance": 0.0,
        },
    )
    return enrich_anchor_metrics(candidate)


def _dense_projection_bands(
    counts: tuple[tuple[int, int], ...],
    *,
    minimum_count: float,
) -> tuple[tuple[int, int], ...]:
    bands: list[tuple[int, int]] = []
    start: int | None = None
    previous: int | None = None
    for coordinate, count in counts:
        if count >= minimum_count:
            if start is None:
                start = coordinate
            previous = coordinate
            continue
        if start is not None and previous is not None:
            bands.append((start, previous))
        start = None
        previous = None
    if start is not None and previous is not None:
        bands.append((start, previous))
    return tuple(band for band in bands if band[1] - band[0] + 1 >= 2)


def _projection_band_pixels(
    component: MaskComponent,
    row_bands: tuple[tuple[int, int], ...],
    column_bands: tuple[tuple[int, int], ...],
) -> frozenset[tuple[int, int]]:
    row_ranges = tuple(range(top, bottom + 1) for top, bottom in row_bands)
    column_ranges = tuple(range(left, right + 1) for left, right in column_bands)
    row_coordinates = {coordinate for band in row_ranges for coordinate in band}
    column_coordinates = {
        coordinate for band in column_ranges for coordinate in band
    }
    return frozenset(
        (x, y)
        for x, y in component.pixels
        if y in row_coordinates or x in column_coordinates
    )


def _diagonal_cross_strokes(
    component: MaskComponent,
    thresholds: AnchorThresholdConfig,
) -> tuple[AnchorCandidate, ...]:
    width = component.width
    height = component.height
    if (
        width < thresholds.stroke_min_length * 3
        or height < thresholds.stroke_min_length * 3
        or max(width, height) / max(min(width, height), 1) > 1.35
    ):
        return ()

    center = component.centroid
    sqrt2 = sqrt(2.0)
    d1_values = []
    d2_values = []
    closest_distances = []
    first_band: list[tuple[int, int]] = []
    second_band: list[tuple[int, int]] = []
    for x, y in component.pixels:
        dx = x - center.x
        dy = y - center.y
        d1 = abs((dy - dx) / sqrt2)
        d2 = abs((dy + dx) / sqrt2)
        d1_values.append(d1)
        d2_values.append(d2)
        closest_distances.append(min(d1, d2))
        if d1 <= d2:
            first_band.append((x, y))
        else:
            second_band.append((x, y))

    size = min(width, height)
    if max(closest_distances) > max(4.0, size * 0.16):
        return ()
    if len(first_band) < component.area * 0.25 or len(second_band) < component.area * 0.25:
        return ()
    # A plus sign also has many pixels near the diagonals at the crossing,
    # but its tails sit far from both diagonal bands and fail the max-distance
    # gate above. Remaining accepted glyphs should be split fairly evenly.
    balance = max(len(first_band), len(second_band)) / min(len(first_band), len(second_band))
    if balance > 1.8:
        return ()

    first = _diagonal_band_anchor(
        first_band,
        center,
        direction=(1 / sqrt2, 1 / sqrt2),
        kind_metric="diagonal_cross_down",
    )
    second = _diagonal_band_anchor(
        second_band,
        center,
        direction=(1 / sqrt2, -1 / sqrt2),
        kind_metric="diagonal_cross_up",
    )
    if first is None or second is None:
        return ()
    return (first, second)


def _diagonal_band_anchor(
    pixels: list[tuple[int, int]],
    center: Point,
    *,
    direction: tuple[float, float],
    kind_metric: str,
) -> AnchorCandidate | None:
    dx, dy = direction
    nx, ny = -dy, dx
    projections = []
    distances = []
    for x, y in pixels:
        offset_x = x - center.x
        offset_y = y - center.y
        projections.append(offset_x * dx + offset_y * dy)
        distances.append(abs(offset_x * nx + offset_y * ny))
    if not projections:
        return None
    length = max(projections) - min(projections) + 1
    if length <= 0:
        return None
    width = max(len(pixels) / length, 1.0)
    start_projection = min(projections) + width / 2
    end_projection = max(projections) - width / 2
    if end_projection <= start_projection:
        return None
    return _simple_stroke_anchor(
        Point(center.x + dx * start_projection, center.y + dy * start_projection),
        Point(center.x + dx * end_projection, center.y + dy * end_projection),
        width,
        kind_metric=kind_metric,
    )


def _simple_stroke_anchor(
    start: Point,
    end: Point,
    width: float,
    *,
    kind_metric: str,
) -> AnchorCandidate:
    candidate = AnchorCandidate(
        kind=AnchorKind.STROKE_POLYLINE,
        raster_error=0.0,
        node_count=2,
        parameter_count=5,
        stroke=StrokeAnchor(
            centerline=(start, end),
            width_samples=(float(width),),
            cap_style="round",
            join_style="round",
        ),
        metrics={
            "compound_stroke_decomposition": 1.0,
            kind_metric: 1.0,
        },
    )
    return enrich_anchor_metrics(candidate)


def _simple_stroke_path_anchor(
    centerline: tuple[Point, ...],
    width: float,
    *,
    kind_metric: str,
    closed: bool = False,
) -> AnchorCandidate:
    candidate = AnchorCandidate(
        kind=AnchorKind.STROKE_PATH,
        raster_error=0.0,
        node_count=len(centerline),
        parameter_count=1 + len(centerline) * 2,
        stroke=StrokeAnchor(
            centerline=centerline,
            width_samples=(float(width),),
            cap_style="round",
            join_style="round",
            closed=closed,
        ),
        metrics={
            "compound_stroke_decomposition": 1.0,
            kind_metric: 1.0,
            "stroke_width_variance": 0.0,
        },
    )
    return enrich_anchor_metrics(candidate)


def _component_column_spans(
    component: MaskComponent,
) -> tuple[tuple[int, int, int], ...]:
    spans: dict[int, tuple[int, int]] = {}
    for x, y in component.pixels:
        if x not in spans:
            spans[x] = (y, y)
            continue
        top, bottom = spans[x]
        if y < top:
            spans[x] = (y, bottom)
        elif y > bottom:
            spans[x] = (top, y)
    return tuple((x, top, bottom) for x, (top, bottom) in sorted(spans.items()))


def _component_row_counts(
    component: MaskComponent,
) -> tuple[tuple[int, int], ...]:
    counts: dict[int, int] = {}
    for _, y in component.pixels:
        counts[y] = counts.get(y, 0) + 1
    return tuple((y, counts[y]) for y in sorted(counts))


def _component_column_counts(
    component: MaskComponent,
) -> tuple[tuple[int, int], ...]:
    counts: dict[int, int] = {}
    for x, _ in component.pixels:
        counts[x] = counts.get(x, 0) + 1
    return tuple((x, counts[x]) for x in sorted(counts))


def _has_bulky_enclosed_holes(component: MaskComponent) -> bool:
    slit_limit = max(
        3,
        min(8, round(min(component.width, component.height) * 0.05)),
    )
    for gap in _interior_gap_components(component, min_area=16):
        if _gap_open_to_background(gap, component):
            continue
        ink_width = gap.area / max(max(gap.width, gap.height), 1)
        if ink_width > slit_limit and gap.area >= component.area * 0.02:
            return True
    return False


def _organic_fallback_candidate(component: MaskComponent) -> AnchorCandidate:
    """Controlled organic outline fallback with a bounded node count."""

    outline = _traced_outline(component)
    if outline is None:
        # Degenerate components fall back to their bounding box.
        min_x, min_y, max_x, max_y = component.bounds
        outline = (
            Point(min_x, min_y),
            Point(max_x, min_y),
            Point(max_x, max_y),
            Point(min_x, max_y),
        )
    # Smooth away pixel staircase noise, then least-squares-fit cubic Bezier
    # segments to the whole contour. Approximation averages the remaining
    # noise out, unlike interpolation through individual contour pixels, and
    # the adaptive splits land segment joints at the curvature extrema.
    # Corners are detected on the raw trace (smoothing spreads them out)
    # and pinned through the smoothing so apexes stay sharp.
    corners = _detect_outline_corners(outline)
    smoothed = _smoothed_closed_outline(outline, window=2, pinned=corners)
    perimeter = sum(
        smoothed[index].distance_to(smoothed[(index + 1) % len(smoothed)])
        for index in range(len(smoothed))
    )
    # One node per ~12 px of contour: a 64 px fixture blob keeps the 16-node
    # budget while a large detailed silhouette earns enough segments to keep
    # noses and lobes instead of melting them into the tolerance.
    node_budget = min(64, max(ORGANIC_FALLBACK_MAX_NODES, round(perimeter / 12)))
    points, controls, fit_error = _fit_closed_bezier_outline(
        smoothed,
        max_segments=node_budget,
        corners=corners,
    )
    smoothness = _curvature_jitter(points + points[:2])
    holes = _fitted_hole_subpaths(component)
    hole_nodes = sum(len(hole_points) for hole_points, _ in holes)
    # Rank as if the outline used its full node budget: a compact fit must
    # not make the generic fallback cheaper against semantic candidates.
    saved_nodes = max(0, node_budget - len(points))
    rank_penalty = ORGANIC_FALLBACK_RANK_PENALTY + saved_nodes * 0.035
    return AnchorCandidate(
        kind=AnchorKind.CUBIC_PATH,
        raster_error=rank_penalty,
        node_count=len(points) + hole_nodes,
        parameter_count=(len(points) + hole_nodes) * 2,
        path=PathAnchor(
            points=points,
            closed=True,
            controls=controls,
            holes=holes,
        ),
        metrics={
            "path_node_count": float(len(points) + hole_nodes),
            "path_hole_count": float(len(holes)),
            "path_smoothness": smoothness,
            "path_fit_max_error_px": fit_error,
        },
    )


def _fitted_hole_subpaths(
    component: MaskComponent,
) -> tuple[tuple[tuple[Point, ...], tuple[tuple[Point, Point], ...]], ...]:
    """Fit enclosed gaps too bulky for slit cut-outs as even-odd holes.

    Thin slits stay editable overlay strokes (the established cut-out
    contract); anything wider is real negative space that the filled
    outline must not paint over.
    """

    slit_limit = max(
        3,
        min(8, round(min(component.width, component.height) * 0.05)),
    )
    holes = []
    for gap in _interior_gap_components(component, min_area=16):
        if _gap_open_to_background(gap, component):
            continue
        ink_width = gap.area / max(max(gap.width, gap.height), 1)
        if ink_width <= slit_limit:
            # Slit territory; the cut-out detector owns it.
            continue
        outline = _traced_outline(gap)
        if outline is None or len(outline) < 4:
            continue
        corners = _detect_outline_corners(outline)
        smoothed = _smoothed_closed_outline(outline, window=2, pinned=corners)
        perimeter = sum(
            smoothed[index].distance_to(smoothed[(index + 1) % len(smoothed)])
            for index in range(len(smoothed))
        )
        budget = min(24, max(8, round(perimeter / 12)))
        hole_points, hole_controls, _ = _fit_closed_bezier_outline(
            smoothed,
            max_segments=budget,
            corners=corners,
        )
        holes.append((hole_points, hole_controls))
    return tuple(holes)


def _traced_outline(component: MaskComponent) -> tuple[Point, ...] | None:
    """Moore-neighbor boundary trace returning an ordered closed outline."""

    pixels = component.pixels
    if len(pixels) < 4:
        return None
    start = min(pixels, key=lambda pixel: (pixel[1], pixel[0]))
    # Clockwise Moore neighborhood starting west.
    offsets = ((-1, 0), (-1, -1), (0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1))
    contour: list[Point] = [Point(*start)]
    current = start
    entry = 0
    max_steps = len(pixels) * 4 + 16
    for _ in range(max_steps):
        found = False
        for step in range(8):
            index = (entry + step) % 8
            dx, dy = offsets[index]
            candidate = (current[0] + dx, current[1] + dy)
            if candidate in pixels:
                if candidate == start and len(contour) > 2:
                    return tuple(contour)
                contour.append(Point(*candidate))
                current = candidate
                entry = (index + 5) % 8
                found = True
                break
        if not found:
            return tuple(contour) if len(contour) > 3 else None
    return tuple(contour) if len(contour) > 3 else None


def _smoothed_closed_outline(
    outline: tuple[Point, ...],
    *,
    window: int,
    pinned: tuple[int, ...] = (),
) -> tuple[Point, ...]:
    """Circular moving average; removes staircase jitter before fitting.

    ``pinned`` indices keep their raw position: averaging a star tip or
    arrow head shaves the apex off and halves the tangent break the
    corner-aware fit needs downstream.
    """

    count = len(outline)
    if count < window * 2 + 3:
        return outline
    pinned_set = set(pinned)
    smoothed = []
    for index in range(count):
        if index in pinned_set:
            smoothed.append(outline[index])
            continue
        xs = 0.0
        ys = 0.0
        for offset in range(-window, window + 1):
            point = outline[(index + offset) % count]
            xs += point.x
            ys += point.y
        size = window * 2 + 1
        smoothed.append(Point(xs / size, ys / size))
    return tuple(smoothed)


BezierSegment = tuple["Point", "Point", "Point", "Point"]


def _fit_closed_bezier_outline(
    outline: tuple[Point, ...],
    *,
    max_segments: int,
    corners: tuple[int, ...] | None = None,
) -> tuple[tuple[Point, ...], tuple[tuple[Point, Point], ...], float]:
    """Least-squares cubic Bezier fit of a closed contour (Schneider).

    Returns on-curve points, per-segment control pairs, and the maximum
    fit error in pixels. The error tolerance widens until the segment
    budget holds. Sharp direction breaks (star tips, arrow heads) become
    segment boundaries with free tangents, so corners stay corners
    instead of being blended into C1 bulges. Pass ``corners`` detected on
    the raw outline (same indexing); detecting here on a smoothed contour
    misses shallow corners the smoothing already spread out.
    """

    count = len(outline)
    if count < 8:
        controls = tuple(
            _line_controls(outline[index], outline[(index + 1) % count])
            for index in range(count)
        )
        return outline, controls, 0.0

    if corners is None:
        corners = _detect_outline_corners(outline, max_corners=max_segments)
    else:
        corners = tuple(index for index in corners if index < count)[
            :max_segments
        ]
    if len(corners) == 2:
        # Two corners alone (a crescent's tips) would yield a fragile
        # two-node path; split each arc at its chord-distance apex so the
        # shape keeps editable nodes at the curvature extrema.
        corners = tuple(sorted(set(corners) | {
            apex
            for apex in (
                _chord_apex_index(outline, corners[0], corners[1]),
                _chord_apex_index(outline, corners[1], corners[0]),
            )
            if apex is not None
        }))
    if len(corners) >= 2:
        pieces = []
        for position, start in enumerate(corners):
            end = corners[(position + 1) % len(corners)]
            if end > start:
                piece = outline[start : end + 1]
            else:
                piece = outline[start:] + outline[: end + 1]
            pieces.append(piece)
        joint_tangents = None
    else:
        anchor_a = max(
            range(count),
            key=lambda index: outline[index].distance_to(outline[0]),
        )
        anchor_b = max(
            range(count),
            key=lambda index: outline[index].distance_to(outline[anchor_a]),
        )
        first, second = sorted((anchor_a, anchor_b))
        pieces = [
            outline[first : second + 1],
            outline[second:] + outline[: first + 1],
        ]
        # Shared joint tangents keep the two halves C1-continuous.
        joint_tangents = (
            _normalized_direction(
                outline[(first + 1) % count],
                outline[(first - 1) % count],
            ),
            _normalized_direction(
                outline[(second + 1) % count],
                outline[(second - 1) % count],
            ),
        )

    tolerance = 0.45
    segments: list[BezierSegment] = []
    for _ in range(8):
        segments = []
        for index, piece in enumerate(pieces):
            if joint_tangents is not None:
                left = joint_tangents[index]
                right = _negated(joint_tangents[(index + 1) % 2])
            else:
                # Free chord tangents at the corners; sharing them with
                # the neighbour piece would round the corner off.
                left = _normalized_direction(
                    piece[min(2, len(piece) - 1)],
                    piece[0],
                )
                right = _normalized_direction(
                    piece[max(len(piece) - 3, 0)],
                    piece[-1],
                )
            segments.extend(_fit_cubic(piece, left, right, tolerance))
        if len(segments) <= max_segments:
            break
        tolerance *= 1.5

    points = tuple(segment[0] for segment in segments)
    controls = tuple((segment[1], segment[2]) for segment in segments)
    max_error = 0.0
    for sample in outline:
        best = min(
            _point_to_bezier_distance(sample, segment)
            for segment in segments
        )
        max_error = max(max_error, best)
    return points, controls, round(max_error, 4)


def _detect_outline_corners(
    outline: tuple[Point, ...],
    *,
    span: int = 4,
    min_turn: float = 0.65,
    max_corners: int = 16,
) -> tuple[int, ...]:
    """Indices where the contour direction breaks sharply.

    Measure on the RAW traced outline: smoothing spreads a corner across
    several points and pushes its turn below any usable threshold. Two
    chord scales separate corners from curvature: a genuine corner keeps
    its turn when the chord doubles, while smooth curvature roughly
    doubles with it. Staircase jitter stays far below the threshold at
    both scales. Returns non-maximum-suppressed indices in contour order;
    an empty tuple means the contour is smooth everywhere.
    """

    count = len(outline)
    if count < span * 4 + 4:
        return ()
    turns_small = _chord_turns(outline, span)
    turns_large = _chord_turns(outline, span * 2)

    kept: list[int] = []
    for index in sorted(
        (i for i in range(count) if turns_small[i] >= min_turn),
        key=lambda i: -turns_small[i],
    ):
        if turns_large[index] > turns_small[index] + 0.35:
            continue
        distance_ok = all(
            min(abs(index - other), count - abs(index - other)) > span * 2
            for other in kept
        )
        if distance_ok:
            kept.append(index)
        if len(kept) >= max_corners:
            break
    return tuple(sorted(kept))


def _chord_apex_index(
    outline: tuple[Point, ...],
    start: int,
    end: int,
) -> int | None:
    """Index of the point farthest from the start-end chord, walking forward."""

    count = len(outline)
    size = (end - start) % count
    if size < 10:
        return None
    chord_start = outline[start]
    chord_end = outline[end]
    best_index = None
    best_distance = 0.0
    for offset in range(1, size):
        index = (start + offset) % count
        distance = _point_line_distance(outline[index], chord_start, chord_end)
        if distance > best_distance:
            best_distance = distance
            best_index = index
    if best_distance < 1.5:
        return None
    return best_index


def _chord_turns(outline: tuple[Point, ...], span: int) -> list[float]:
    count = len(outline)
    turns = []
    for index in range(count):
        before = outline[(index - span) % count]
        here = outline[index]
        after = outline[(index + span) % count]
        in_dx = here.x - before.x
        in_dy = here.y - before.y
        out_dx = after.x - here.x
        out_dy = after.y - here.y
        if hypot(in_dx, in_dy) <= 0 or hypot(out_dx, out_dy) <= 0:
            turns.append(0.0)
            continue
        cross = in_dx * out_dy - in_dy * out_dx
        dot = in_dx * out_dx + in_dy * out_dy
        turns.append(abs(atan2(cross, dot)))
    return turns


def _line_controls(start: Point, end: Point) -> tuple[Point, Point]:
    return (
        Point(start.x + (end.x - start.x) / 3, start.y + (end.y - start.y) / 3),
        Point(start.x + (end.x - start.x) * 2 / 3, start.y + (end.y - start.y) * 2 / 3),
    )


def _normalized_direction(toward: Point, away: Point) -> Point:
    dx = toward.x - away.x
    dy = toward.y - away.y
    length = hypot(dx, dy)
    if length <= 0:
        return Point(1.0, 0.0)
    return Point(dx / length, dy / length)


def _negated(direction: Point) -> Point:
    return Point(-direction.x, -direction.y)


def _fit_cubic(
    points: tuple[Point, ...],
    left_tangent: Point,
    right_tangent: Point,
    tolerance: float,
) -> list[BezierSegment]:
    if len(points) == 2:
        distance = points[0].distance_to(points[1]) / 3
        return [
            (
                points[0],
                Point(
                    points[0].x + left_tangent.x * distance,
                    points[0].y + left_tangent.y * distance,
                ),
                Point(
                    points[1].x + right_tangent.x * distance,
                    points[1].y + right_tangent.y * distance,
                ),
                points[1],
            )
        ]

    parameters = _chord_length_parameterize(points)
    segment = _generate_bezier(points, parameters, left_tangent, right_tangent)
    max_error, split_index = _max_fit_error(points, segment, parameters)
    if max_error < tolerance:
        return [segment]

    if max_error < tolerance * 4:
        for _ in range(4):
            parameters = tuple(
                _refine_parameter(point, segment, u)
                for point, u in zip(points, parameters)
            )
            segment = _generate_bezier(
                points,
                parameters,
                left_tangent,
                right_tangent,
            )
            max_error, split_index = _max_fit_error(points, segment, parameters)
            if max_error < tolerance:
                return [segment]

    split_index = min(max(split_index, 1), len(points) - 2)
    center_tangent = _normalized_direction(
        points[split_index - 1],
        points[split_index + 1],
    )
    return _fit_cubic(
        points[: split_index + 1],
        left_tangent,
        center_tangent,
        tolerance,
    ) + _fit_cubic(
        points[split_index:],
        _negated(center_tangent),
        right_tangent,
        tolerance,
    )


def _chord_length_parameterize(points: tuple[Point, ...]) -> tuple[float, ...]:
    distances = [0.0]
    for previous, current in zip(points, points[1:]):
        distances.append(distances[-1] + previous.distance_to(current))
    total = distances[-1] or 1.0
    return tuple(distance / total for distance in distances)


def _generate_bezier(
    points: tuple[Point, ...],
    parameters: tuple[float, ...],
    left_tangent: Point,
    right_tangent: Point,
) -> BezierSegment:
    start = points[0]
    end = points[-1]
    c00 = c01 = c11 = 0.0
    x0 = x1 = 0.0
    for point, u in zip(points, parameters):
        b0 = (1 - u) ** 3
        b1 = 3 * u * (1 - u) ** 2
        b2 = 3 * u * u * (1 - u)
        b3 = u**3
        a0x = left_tangent.x * b1
        a0y = left_tangent.y * b1
        a1x = right_tangent.x * b2
        a1y = right_tangent.y * b2
        c00 += a0x * a0x + a0y * a0y
        c01 += a0x * a1x + a0y * a1y
        c11 += a1x * a1x + a1y * a1y
        tx = point.x - (b0 + b1) * start.x - (b2 + b3) * end.x
        ty = point.y - (b0 + b1) * start.y - (b2 + b3) * end.y
        x0 += a0x * tx + a0y * ty
        x1 += a1x * tx + a1y * ty
    determinant = c00 * c11 - c01 * c01
    if abs(determinant) > 1e-9:
        alpha_left = (x0 * c11 - x1 * c01) / determinant
        alpha_right = (c00 * x1 - c01 * x0) / determinant
    else:
        alpha_left = alpha_right = 0.0
    segment_length = start.distance_to(end)
    epsilon = 1e-6 * segment_length
    if alpha_left < epsilon or alpha_right < epsilon:
        alpha_left = alpha_right = segment_length / 3
    return (
        start,
        Point(
            start.x + left_tangent.x * alpha_left,
            start.y + left_tangent.y * alpha_left,
        ),
        Point(
            end.x + right_tangent.x * alpha_right,
            end.y + right_tangent.y * alpha_right,
        ),
        end,
    )


def _bezier_point(segment: BezierSegment, u: float) -> Point:
    p0, p1, p2, p3 = segment
    v = 1 - u
    return Point(
        v**3 * p0.x + 3 * v * v * u * p1.x + 3 * v * u * u * p2.x + u**3 * p3.x,
        v**3 * p0.y + 3 * v * v * u * p1.y + 3 * v * u * u * p2.y + u**3 * p3.y,
    )


def _max_fit_error(
    points: tuple[Point, ...],
    segment: BezierSegment,
    parameters: tuple[float, ...],
) -> tuple[float, int]:
    worst = 0.0
    worst_index = len(points) // 2
    for index in range(1, len(points) - 1):
        distance = points[index].distance_to(
            _bezier_point(segment, parameters[index])
        )
        if distance > worst:
            worst = distance
            worst_index = index
    return worst, worst_index


def _refine_parameter(point: Point, segment: BezierSegment, u: float) -> float:
    """One Newton-Raphson step moving u toward the closest curve point."""

    p0, p1, p2, p3 = segment
    q = _bezier_point(segment, u)
    v = 1 - u
    d1x = 3 * (v * v * (p1.x - p0.x) + 2 * v * u * (p2.x - p1.x) + u * u * (p3.x - p2.x))
    d1y = 3 * (v * v * (p1.y - p0.y) + 2 * v * u * (p2.y - p1.y) + u * u * (p3.y - p2.y))
    d2x = 6 * (v * (p2.x - 2 * p1.x + p0.x) + u * (p3.x - 2 * p2.x + p1.x))
    d2y = 6 * (v * (p2.y - 2 * p1.y + p0.y) + u * (p3.y - 2 * p2.y + p1.y))
    numerator = (q.x - point.x) * d1x + (q.y - point.y) * d1y
    denominator = d1x * d1x + d1y * d1y + (q.x - point.x) * d2x + (q.y - point.y) * d2y
    if abs(denominator) < 1e-9:
        return u
    refined = u - numerator / denominator
    return min(max(refined, 0.0), 1.0)


def _point_to_bezier_distance(point: Point, segment: BezierSegment) -> float:
    best = float("inf")
    best_u = 0.0
    for step in range(25):
        u = step / 24
        distance = point.distance_to(_bezier_point(segment, u))
        if distance < best:
            best = distance
            best_u = u
    refined_u = _refine_parameter(point, segment, best_u)
    return min(best, point.distance_to(_bezier_point(segment, refined_u)))




def _with_classifier_prior(
    candidate: AnchorCandidate,
    classifier_model: ClassifierModel | dict[str, tuple[float, ...]],
    *,
    classifier_crop_tokens: tuple[tuple[float, float, float, float], ...] | None,
) -> AnchorCandidate:
    metrics = dict(candidate.metrics)
    metrics["classifier_prior_error"] = classifier_prior_error(
        classifier_model,
        candidate,
        crop_tokens=classifier_crop_tokens,
    )
    return AnchorCandidate(
        kind=candidate.kind,
        raster_error=candidate.raster_error,
        node_count=candidate.node_count,
        parameter_count=candidate.parameter_count,
        color=candidate.color,
        circle=candidate.circle,
        stroke=candidate.stroke,
        quad=candidate.quad,
        arc=candidate.arc,
        ellipse=candidate.ellipse,
        path=candidate.path,
        metrics=metrics,
    )


def _stroke_circle_candidate(
    component: MaskComponent,
    thresholds: AnchorThresholdConfig,
) -> AnchorCandidate | None:
    width = component.width
    height = component.height
    diameter = max(width, height)
    if diameter < thresholds.stroke_circle_min_diameter:
        return None

    aspect_error = abs(width - height) / diameter
    if aspect_error > thresholds.stroke_circle_max_aspect_error:
        return None

    center, _, fit_residual = _fit_circle_from_boundary(
        component,
        fallback_radius=diameter / 2,
    )
    distances = [Point(x, y).distance_to(center) for x, y in component.pixels]
    inner_radius = min(distances)
    outer_radius = max(distances)
    if (
        outer_radius <= 0
        or inner_radius / outer_radius < thresholds.stroke_circle_min_inner_ratio
    ):
        return None

    stroke_width = outer_radius - inner_radius + 1
    if stroke_width <= 0:
        return None

    expected_area = pi * (outer_radius**2 - inner_radius**2)
    if expected_area <= 0:
        return None
    area_error = abs(component.area - expected_area) / expected_area
    if area_error > thresholds.stroke_circle_max_area_error:
        return None
    max_fit_residual = (
        0.2
        if diameter <= thresholds.stroke_circle_min_diameter + 4
        else 0.12
    )
    small_regular_ring = (
        diameter <= 24
        and area_error <= 0.18
        and fit_residual <= 0.26
    )
    regular_ring = area_error <= 0.08 and fit_residual <= 0.18
    if fit_residual > max_fit_residual and not (small_regular_ring or regular_ring):
        return None

    # A ring severed by a channel (a bay open to the background) still
    # passes the area gates because the cut costs only a few percent, but
    # a closed stroke circle would paint the channel shut. Reject when the
    # angular coverage has a real gap, measured as arc length: pixel
    # discretization on small rings opens angular gaps of 1/r while a
    # genuine channel is several pixels wide at any radius.
    angles = sorted(
        atan2(y - center.y, x - center.x) for x, y in component.pixels
    )
    angular_gap = max(
        (b - a for a, b in zip(angles, angles[1:])),
        default=0.0,
    )
    wraparound = angles[0] + 2 * pi - angles[-1]
    mid_radius = (inner_radius + outer_radius) / 2
    if max(angular_gap, wraparound) * mid_radius > 2.5:
        return None

    radius = (inner_radius + outer_radius) / 2
    candidate = AnchorCandidate(
        kind=AnchorKind.STROKE_CIRCLE,
        raster_error=area_error + aspect_error + fit_residual,
        node_count=1,
        parameter_count=4,
        circle=CircleAnchor(
            center=center,
            radius=radius,
            samples=tuple(Point(x, y) for x, y in component.boundary_pixels),
        ),
        stroke=StrokeAnchor(centerline=(), width_samples=(stroke_width,)),
    )
    return _with_metric(
        enrich_anchor_metrics(candidate),
        "circle_fit_residual_error",
        fit_residual,
    )


def _circle_candidate(
    component: MaskComponent,
    thresholds: AnchorThresholdConfig,
) -> AnchorCandidate | None:
    width = component.width
    height = component.height
    diameter = max(width, height)
    if diameter < thresholds.circle_min_diameter:
        return None

    aspect_error = abs(width - height) / diameter
    if aspect_error > thresholds.circle_max_aspect_error:
        return None

    fallback_radius = sqrt(component.area / pi)
    expected_area = pi * (diameter / 2) ** 2
    area_error = abs(component.area - expected_area) / expected_area
    if area_error > thresholds.circle_max_area_error:
        return None

    center, radius, fit_residual = _fit_circle_from_boundary(
        component,
        fallback_radius=fallback_radius,
    )
    bounds_center, bounds_radius, bounds_residual = _bounds_regularized_circle(
        component,
    )
    roundness_samples = tuple(component.boundary_pixels)
    if fit_residual > thresholds.circle_max_fit_residual:
        # Interior cut-out gaps add inner boundary pixels that wreck the fit;
        # retry against the outer boundary only.
        gap_free = _boundary_without_gap_edges(component)
        if gap_free is not None and len(gap_free[0]) >= len(
            component.boundary_pixels
        ) * 0.6:
            outer, gap_area = gap_free
            center, radius, fit_residual = _fit_circle_from_samples(
                outer,
                fallback_center=component.centroid,
                fallback_radius=fallback_radius,
            )
            bounds_center, bounds_radius, bounds_residual = (
                _bounds_regularized_circle(component, samples=outer)
            )
            roundness_samples = outer
            # The retried circle minus its enclosed gaps must still account
            # for the filled area closely; a lens refit through its two flat
            # arcs lands far off while a cut circle host stays within a few
            # percent.
            refit_area = pi * radius * radius - gap_area
            if (
                refit_area <= 0
                or abs(component.area - refit_area) / refit_area > 0.12
            ):
                return None
    if bounds_residual <= max(
        thresholds.circle_max_fit_residual,
        fit_residual + 0.02,
    ):
        center = bounds_center
        radius = bounds_radius
        fit_residual = bounds_residual
    if diameter >= 12 and fit_residual > thresholds.circle_max_fit_residual:
        return None
    samples = tuple(Point(x, y) for x, y in component.boundary_pixels)
    distances = [
        center.distance_to(Point(x, y)) for x, y in roundness_samples
    ]
    if distances and radius > 0:
        spread = pstdev(distances) / radius
        # Real circles measure <= 0.08 here even anti-aliased; lens and blob
        # outlines spread far wider and must fall through to the organic path.
        if diameter >= 12 and spread > 0.12:
            return None
    candidate = AnchorCandidate(
        kind=AnchorKind.CIRCLE,
        raster_error=area_error + aspect_error + fit_residual,
        node_count=1,
        parameter_count=3,
        circle=CircleAnchor(center=center, radius=radius, samples=samples),
    )
    return _with_metric(
        enrich_anchor_metrics(candidate),
        "circle_fit_residual_error",
        fit_residual,
    )


def _ellipse_candidate(
    component: MaskComponent,
    thresholds: AnchorThresholdConfig,
) -> AnchorCandidate | None:
    """Fit a filled axis-aligned ellipse to a non-circular oval component."""

    width = component.width
    height = component.height
    # Below ~9 px the row quantization of a stadium or rounded rect is
    # indistinguishable from an ellipse, so stay out of that regime.
    if min(width, height) < 9:
        return None
    aspect_error = abs(width - height) / max(width, height)
    if max(width, height) <= 12 and aspect_error < 0.15:
        # At downsampled real-image scale a one-pixel box difference often
        # comes from raster quantization, not a deliberate oval.
        return None
    if aspect_error < 0.1:
        # Circle territory for the aligned fit, but a tilted ellipse can
        # have a near-square box (45 degrees); the rotated fit rejects
        # genuinely round shapes via its own in-frame aspect gate.
        return _rotated_ellipse_candidate(component)

    rx = (width - 1) / 2 + 0.5
    ry = (height - 1) / 2 + 0.5
    min_x, min_y, _, _ = component.bounds
    center = Point(min_x + (width - 1) / 2, min_y + (height - 1) / 2)
    expected_area = pi * rx * ry
    area_error = abs(component.area - expected_area) / expected_area
    if area_error > 0.12:
        return _rotated_ellipse_candidate(component)
    fit_residual_px = _ellipse_boundary_residual(component, center, rx, ry)
    if fit_residual_px > 0.75:
        return _rotated_ellipse_candidate(component)

    candidate = AnchorCandidate(
        kind=AnchorKind.ELLIPSE,
        raster_error=area_error + fit_residual_px * 0.05,
        node_count=1,
        parameter_count=4,
        ellipse=EllipseAnchor(center=center, rx=rx, ry=ry),
        metrics={
            # raster_error already carries both terms; keep the metric names
            # free of the _error suffix to avoid double counting.
            "ellipse_fit_residual_px": fit_residual_px,
            "ellipse_area_mismatch": area_error,
        },
    )
    return candidate


def _rotated_ellipse_candidate(
    component: MaskComponent,
) -> AnchorCandidate | None:
    """Fit a tilted filled ellipse via the principal axis of the ink.

    Reached when the axis-aligned fit fails: a tilted ellipse fills its
    bounding box poorly and misses the aligned area gate, while its
    pixel covariance still points exactly along the true major axis.
    """

    axis = _principal_axis(component)
    if axis is None:
        return None
    centroid, (axis_x, axis_y) = axis[0], axis[1]
    theta = atan2(axis_y, axis_x)
    # Fold onto (-pi/2, pi/2]: an ellipse is symmetric under 180 degrees.
    if theta <= -pi / 2:
        theta += pi
    elif theta > pi / 2:
        theta -= pi
    # Near-axis-aligned shapes already had their chance in the aligned
    # fit; refitting them rotated would only relabel the same rejection.
    if min(abs(theta), abs(abs(theta) - pi / 2)) < radians(4.0):
        return None

    cos_t = cos(theta)
    sin_t = sin(theta)
    us = []
    vs = []
    for x, y in component.pixels:
        dx = x - centroid.x
        dy = y - centroid.y
        us.append(dx * cos_t + dy * sin_t)
        vs.append(-dx * sin_t + dy * cos_t)
    min_u, max_u = min(us), max(us)
    min_v, max_v = min(vs), max(vs)
    rx = (max_u - min_u) / 2 + 0.5
    ry = (max_v - min_v) / 2 + 0.5
    if min(rx, ry) < 4.5:
        return None
    aspect_error = abs(rx - ry) / max(rx, ry)
    if aspect_error < 0.1:
        # Circle territory; rotation is meaningless there.
        return None

    center_u = (min_u + max_u) / 2
    center_v = (min_v + max_v) / 2
    center = Point(
        centroid.x + center_u * cos_t - center_v * sin_t,
        centroid.y + center_u * sin_t + center_v * cos_t,
    )
    expected_area = pi * rx * ry
    area_error = abs(component.area - expected_area) / expected_area
    if area_error > 0.12:
        return None
    fit_residual_px, residual_p95 = _ellipse_residual_profile(
        component,
        center,
        rx,
        ry,
        rotation=theta,
    )
    # A tilted outline staircases diagonally, so its quantization noise sits
    # near one pixel where the aligned fit sees 0.75; straight-flanked shapes
    # (rotated stadiums, wedges) still measure well above this. The tail
    # percentile separates uniform staircase noise from the local spikes of
    # leaf-like blobs whose mean residual overlaps genuine ellipses.
    if fit_residual_px > 1.1 or residual_p95 > 1.7:
        return None

    return AnchorCandidate(
        kind=AnchorKind.ELLIPSE,
        raster_error=area_error + fit_residual_px * 0.05,
        node_count=1,
        parameter_count=5,
        ellipse=EllipseAnchor(center=center, rx=rx, ry=ry, rotation=theta),
        metrics={
            "ellipse_fit_residual_px": fit_residual_px,
            "ellipse_area_mismatch": area_error,
            "ellipse_rotation_deg": degrees(theta),
        },
    )


def _stroke_ellipse_candidate(
    component: MaskComponent,
    thresholds: AnchorThresholdConfig,
) -> AnchorCandidate | None:
    """Fit an elliptical ring as a centerline ellipse with a stroke width."""

    width = component.width
    height = component.height
    if min(width, height) < 8:
        return None
    aspect_error = abs(width - height) / max(width, height)
    # Up to the stroke-circle aspect tolerance the ring stays a circle.
    if aspect_error < 0.18:
        return None

    outer_rx = (width - 1) / 2 + 0.5
    outer_ry = (height - 1) / 2 + 0.5
    min_x, min_y, _, _ = component.bounds
    center = Point(min_x + (width - 1) / 2, min_y + (height - 1) / 2)
    # Normalized elliptical distance: 1.0 on the outer boundary.
    distances = [
        _normalized_ellipse_distance(Point(x, y), center, outer_rx, outer_ry)
        for x, y in component.pixels
    ]
    inner = min(distances)
    outer = max(distances)
    if inner < 0.3 or outer > 1.2:
        return None
    mean_radius = (outer_rx + outer_ry) / 2
    stroke_width = max((outer - inner) * mean_radius, 1.0)
    if stroke_width > mean_radius * 0.8:
        return None
    mid = (inner + outer) / 2
    band_residual = sum(abs(d - mid) for d in distances) / len(distances)
    if band_residual * mean_radius > stroke_width * 0.5 + 0.5:
        return None
    ring_area = pi * (outer_rx * outer_ry - (outer_rx - stroke_width) * (outer_ry - stroke_width))
    if ring_area <= 0:
        return None
    area_error = abs(component.area - ring_area) / ring_area
    if area_error > 0.45:
        return None

    candidate = AnchorCandidate(
        kind=AnchorKind.STROKE_ELLIPSE,
        raster_error=area_error * 0.2 + band_residual,
        node_count=1,
        parameter_count=5,
        ellipse=EllipseAnchor(
            center=center,
            rx=outer_rx * mid,
            ry=outer_ry * mid,
        ),
        stroke=StrokeAnchor(centerline=(), width_samples=(stroke_width,)),
        metrics={
            "stroke_ellipse_band_residual_error": band_residual,
            "stroke_ellipse_area_error": area_error * 0.2,
        },
    )
    return candidate


def _ellipse_boundary_residual(
    component: MaskComponent,
    center: Point,
    rx: float,
    ry: float,
    *,
    rotation: float = 0.0,
) -> float:
    """Mean pixel distance from boundary pixels to the ellipse along rays.

    Normalized residuals over-penalize small or flat ellipses where half a
    pixel of quantization is a large fraction of the minor radius, so compare
    actual ray length against the ellipse ray length in pixels. ``rotation``
    rotates the measurement frame for tilted ellipses.
    """

    samples = tuple(component.boundary_pixels)
    if not samples:
        return 0.0
    cos_t = cos(rotation)
    sin_t = sin(rotation)
    total = 0.0
    for x, y in samples:
        raw_dx = x - center.x
        raw_dy = y - center.y
        dx = raw_dx * cos_t + raw_dy * sin_t
        dy = -raw_dx * sin_t + raw_dy * cos_t
        actual = sqrt(dx * dx + dy * dy)
        if actual <= 0:
            continue
        denominator = sqrt((ry * dx) ** 2 + (rx * dy) ** 2)
        ray = rx * ry * actual / denominator if denominator > 0 else 0.0
        total += abs(actual - ray)
    return total / len(samples)


def _ellipse_residual_profile(
    component: MaskComponent,
    center: Point,
    rx: float,
    ry: float,
    *,
    rotation: float,
) -> tuple[float, float]:
    """Mean and 95th-percentile ray residual of boundary pixels."""

    samples = tuple(component.boundary_pixels)
    if not samples:
        return 0.0, 0.0
    cos_t = cos(rotation)
    sin_t = sin(rotation)
    deltas = []
    for x, y in samples:
        raw_dx = x - center.x
        raw_dy = y - center.y
        dx = raw_dx * cos_t + raw_dy * sin_t
        dy = -raw_dx * sin_t + raw_dy * cos_t
        actual = sqrt(dx * dx + dy * dy)
        if actual <= 0:
            continue
        denominator = sqrt((ry * dx) ** 2 + (rx * dy) ** 2)
        ray = rx * ry * actual / denominator if denominator > 0 else 0.0
        deltas.append(abs(actual - ray))
    if not deltas:
        return 0.0, 0.0
    deltas.sort()
    return (
        sum(deltas) / len(deltas),
        deltas[min(len(deltas) - 1, int(len(deltas) * 0.95))],
    )


def _normalized_ellipse_distance(
    point: Point,
    center: Point,
    rx: float,
    ry: float,
) -> float:
    nx = (point.x - center.x) / max(rx, 0.5)
    ny = (point.y - center.y) / max(ry, 0.5)
    return sqrt(nx * nx + ny * ny)


def _bounds_regularized_circle(
    component: MaskComponent,
    *,
    samples: tuple[tuple[int, int], ...] | None = None,
) -> tuple[Point, float, float]:
    min_x, min_y, max_x, max_y = component.bounds
    diameter = max(max_x - min_x, max_y - min_y)
    radius = max(diameter / 2, 0.5)
    center = Point((min_x + max_x) / 2, (min_y + max_y) / 2)
    if samples is None:
        samples = tuple(component.boundary_pixels)
    if not samples:
        return center, radius, 0.0
    residual = (
        sum(
            abs(Point(x, y).distance_to(center) - radius)
            for x, y in samples
        )
        / len(samples)
        / radius
    )
    return center, radius, residual


def _boundary_without_gap_edges(
    component: MaskComponent,
) -> tuple[tuple[tuple[int, int], ...], int] | None:
    """Boundary pixels away from enclosed interior gaps, plus the gap area.

    Single-pixel jaggies along pointed organic outlines must not count as
    gaps, otherwise this retry would shave off exactly the boundary parts
    that disqualify a lens from being a circle.
    """

    gaps = tuple(
        gap
        for gap in _interior_gap_components(component, min_area=4)
        if not _gap_open_to_background(gap, component)
    )
    if not gaps:
        return None
    gap_pixels = frozenset(
        pixel
        for gap in gaps
        for pixel in gap.pixels
    )
    outer = tuple(
        (x, y)
        for x, y in component.boundary_pixels
        if not any(
            (x + dx, y + dy) in gap_pixels
            for dx in (-1, 0, 1)
            for dy in (-1, 0, 1)
        )
    )
    if len(outer) < 8:
        return None
    return outer, len(gap_pixels)


def _fit_circle_from_boundary(
    component: MaskComponent,
    *,
    fallback_radius: float,
) -> tuple[Point, float, float]:
    return _fit_circle_from_samples(
        tuple(component.boundary_pixels),
        fallback_center=component.centroid,
        fallback_radius=fallback_radius,
    )


def _fit_circle_from_samples(
    samples: tuple[tuple[int, int], ...],
    *,
    fallback_center: Point,
    fallback_radius: float,
) -> tuple[Point, float, float]:
    if len(samples) < 3:
        return fallback_center, fallback_radius, 0.0

    n = float(len(samples))
    sum_x = sum(float(x) for x, _ in samples)
    sum_y = sum(float(y) for _, y in samples)
    sum_xx = sum(float(x * x) for x, _ in samples)
    sum_yy = sum(float(y * y) for _, y in samples)
    sum_xy = sum(float(x * y) for x, y in samples)
    sum_z = sum(float(x * x + y * y) for x, y in samples)
    sum_xz = sum(float(x * (x * x + y * y)) for x, y in samples)
    sum_yz = sum(float(y * (x * x + y * y)) for x, y in samples)

    matrix = (
        (sum_xx, sum_xy, sum_x),
        (sum_xy, sum_yy, sum_y),
        (sum_x, sum_y, n),
    )
    rhs = (sum_xz, sum_yz, sum_z)
    solved = _solve_3x3(matrix, rhs)
    if solved is None:
        return fallback_center, fallback_radius, 0.0

    a, b, c = solved
    center = Point(a / 2, b / 2)
    radius_squared = c + center.x**2 + center.y**2
    if radius_squared <= 0:
        return fallback_center, fallback_radius, 0.0
    radius = sqrt(radius_squared)
    if radius <= 0:
        return fallback_center, fallback_radius, 0.0
    residual = (
        sum(
            abs(Point(x, y).distance_to(center) - radius)
            for x, y in samples
        )
        / len(samples)
        / radius
    )
    return center, radius, residual


def _solve_3x3(
    matrix: tuple[tuple[float, float, float], ...],
    rhs: tuple[float, float, float],
) -> tuple[float, float, float] | None:
    determinant = _determinant_3x3(matrix)
    if abs(determinant) < 1e-9:
        return None
    columns = tuple(zip(*matrix, strict=True))
    return tuple(
        _determinant_3x3(
            tuple(
                tuple(
                    rhs[row] if column == replace_column else columns[column][row]
                    for column in range(3)
                )
                for row in range(3)
            )
        )
        / determinant
        for replace_column in range(3)
    )


def _determinant_3x3(matrix: tuple[tuple[float, float, float], ...]) -> float:
    return (
        matrix[0][0] * (matrix[1][1] * matrix[2][2] - matrix[1][2] * matrix[2][1])
        - matrix[0][1] * (matrix[1][0] * matrix[2][2] - matrix[1][2] * matrix[2][0])
        + matrix[0][2] * (matrix[1][0] * matrix[2][1] - matrix[1][1] * matrix[2][0])
    )


def _with_metric(
    candidate: AnchorCandidate,
    key: str,
    value: float,
) -> AnchorCandidate:
    metrics = dict(candidate.metrics)
    metrics[key] = value
    return AnchorCandidate(
        kind=candidate.kind,
        raster_error=candidate.raster_error,
        node_count=candidate.node_count,
        parameter_count=candidate.parameter_count,
        color=candidate.color,
        circle=candidate.circle,
        stroke=candidate.stroke,
        quad=candidate.quad,
        arc=candidate.arc,
        ellipse=candidate.ellipse,
        path=candidate.path,
        metrics=metrics,
    )


def _stroke_candidate(
    component: MaskComponent,
    thresholds: AnchorThresholdConfig,
) -> AnchorCandidate | None:
    axis = _principal_axis(component)
    if axis is None:
        return None

    center, direction, min_major, max_major, min_minor, max_minor = axis
    length = max_major - min_major + 1
    stroke_width = max(max_minor - min_minor + 1, 1.0)
    if length < thresholds.stroke_min_length:
        return None

    dx, dy = direction
    straight_centerline = (
        Point(center.x + dx * min_major, center.y + dy * min_major),
        Point(center.x + dx * max_major, center.y + dy * max_major),
    )
    # The oriented minor span absorbs any bow, so it cannot serve as the bow
    # reference; area / length estimates the true ink width instead.
    ink_width = max(component.area / max(length, 1.0), 1.0)
    centerline = _stroke_polyline_centerline(
        component,
        straight_centerline,
        stroke_width=ink_width,
    )
    coverage = min(component.area / (length * stroke_width), 1.0)
    length_width_ratio = length / stroke_width
    if length_width_ratio < thresholds.stroke_min_length_width_ratio and not (
        length_width_ratio >= 2.0
        and stroke_width <= 8.0
        and coverage >= 0.72
        and component.area / max(component.width * component.height, 1) <= 0.65
        and not _axis_aligned_filled_rect_component(component)
    ):
        return None
    if (
        coverage >= 0.98
        and stroke_width > 8.0
        and _axis_aligned_filled_rect_component(component)
    ):
        return None
    # A wide, compact, nearly full block is a filled shape fragment (for
    # example a rect sliced by a curved occluder), not a stroke.
    if stroke_width > 8.0 and coverage >= 0.85 and length / stroke_width < 4.0:
        return None
    # A wide wedge whose cross width swings along its length is a curve-cut
    # fill fragment, not a constant-width stroke.
    if stroke_width > 8.0 and len(centerline) == 2:
        quarter = _cross_width_at(component, centerline, 0.25)
        three_quarter = _cross_width_at(component, centerline, 0.75)
        reference = max(quarter, three_quarter, 1.0)
        if abs(quarter - three_quarter) / reference > 0.4:
            return None
    # A straight-stroke story that covers less than 45% of its own oriented
    # box is not a stroke; curved bands belong to arc or stroke_path.
    if len(centerline) == 2 and coverage < 0.45:
        return None
    # Honest thick strokes fill their oriented box almost completely; a wide
    # band at sub-0.9 coverage is usually a filled oval or capsule instead.
    thick_underfilled = (
        len(centerline) == 2 and stroke_width > 8.0 and coverage < 0.9
    )
    width_samples = _stroke_width_samples_along_centerline(
        component,
        centerline,
        fallback_width=stroke_width,
    )
    cap_style = _straight_stroke_cap_style(centerline, coverage)
    stroke = StrokeAnchor(
        centerline=centerline,
        width_samples=width_samples,
        cap_style=cap_style,
        join_style="round",
    )
    if _stroke_bounds_exceed_component(stroke, component):
        return None
    # Low oriented-box coverage means the straight-stroke story is poor (for
    # example a curved band absorbed into an inflated width); penalize it
    # enough that an honest arc fit wins the ranking.
    coverage_weight = 0.1 if len(centerline) > 2 or coverage >= 0.7 else 0.3
    if thick_underfilled:
        coverage_weight = max(coverage_weight, 0.3)
    candidate = AnchorCandidate(
        kind=AnchorKind.STROKE_POLYLINE,
        raster_error=abs(1.0 - coverage) * coverage_weight,
        node_count=len(centerline),
        parameter_count=len(width_samples) + len(centerline) * 2,
        stroke=stroke,
    )
    return enrich_anchor_metrics(candidate)


def _cross_width_at(
    component: MaskComponent,
    centerline: tuple[Point, ...],
    fraction: float,
) -> float:
    start = centerline[0]
    end = centerline[-1]
    dx = end.x - start.x
    dy = end.y - start.y
    length = hypot(dx, dy)
    if length <= 0:
        return 1.0
    dx /= length
    dy /= length
    anchor_x = start.x + dx * length * fraction
    anchor_y = start.y + dy * length * fraction
    spans = [
        abs((x - anchor_x) * -dy + (y - anchor_y) * dx)
        for x, y in component.pixels
        if abs((x - anchor_x) * dx + (y - anchor_y) * dy) <= 1.5
    ]
    if not spans:
        return 1.0
    return max(spans) * 2 + 1


def _straight_stroke_cap_style(
    centerline: tuple[Point, ...],
    coverage: float,
) -> str:
    if len(centerline) != 2:
        return "round"
    # Oblique raster strokes have stair-stepped edges, so their oriented-box
    # coverage lands below the ideal filled-rectangle value even with flat caps.
    return "butt" if coverage >= 0.76 else "round"


def _stroke_polyline_centerline(
    component: MaskComponent,
    straight_centerline: tuple[Point, Point],
    *,
    stroke_width: float,
) -> tuple[Point, ...]:
    start, end = straight_centerline
    if start.distance_to(end) <= 0:
        return straight_centerline
    control = max(
        (Point(x, y) for x, y in component.pixels),
        key=lambda point: _point_line_distance(point, start, end),
    )
    deviation = _point_line_distance(control, start, end)
    # stroke_width here is the ink width (area / length); staircase corner
    # pixels of straight oblique strokes sit up to half a width plus over a
    # pixel away from the axis, hence the extra margin.
    if deviation < max(0.75, stroke_width * 0.5 + 1.25):
        return straight_centerline
    return (start, control, end)


def _stroke_width_samples_along_centerline(
    component: MaskComponent,
    centerline: tuple[Point, ...],
    *,
    fallback_width: float,
) -> tuple[float, ...]:
    if len(centerline) <= 2:
        return (float(fallback_width),)
    return tuple(
        _local_stroke_width_sample(
            component,
            centerline,
            index,
            fallback_width=fallback_width,
        )
        for index in range(len(centerline))
    )


def _local_stroke_width_sample(
    component: MaskComponent,
    centerline: tuple[Point, ...],
    index: int,
    *,
    fallback_width: float,
) -> float:
    point = centerline[index]
    if index == 0:
        tangent_end = centerline[1]
        tangent_x = tangent_end.x - point.x
        tangent_y = tangent_end.y - point.y
    elif index == len(centerline) - 1:
        tangent_start = centerline[index - 1]
        tangent_x = point.x - tangent_start.x
        tangent_y = point.y - tangent_start.y
    else:
        tangent_start = centerline[index - 1]
        tangent_end = centerline[index + 1]
        tangent_x = tangent_end.x - tangent_start.x
        tangent_y = tangent_end.y - tangent_start.y

    tangent_length = hypot(tangent_x, tangent_y)
    if tangent_length <= 0:
        return float(fallback_width)
    tangent_x /= tangent_length
    tangent_y /= tangent_length
    normal_x = -tangent_y
    normal_y = tangent_x
    window = max(float(fallback_width) * 1.5, 2.0)
    distances = []
    for x, y in component.pixels:
        offset_x = x - point.x
        offset_y = y - point.y
        along = abs((offset_x * tangent_x) + (offset_y * tangent_y))
        if along > window:
            continue
        distances.append(abs((offset_x * normal_x) + (offset_y * normal_y)))
    if not distances:
        return float(fallback_width)
    return max(1.0, (max(distances) * 2.0) + 1.0)


def _arc_candidate(
    component: MaskComponent,
    thresholds: AnchorThresholdConfig,
) -> AnchorCandidate | None:
    width = component.width
    height = component.height
    chord_length = max(width, height) - 1
    if chord_length < thresholds.stroke_min_length or min(width, height) < 3:
        return None

    density = component.area / max(width * height, 1)
    if density > 0.55:
        return None

    fit = _fit_circular_arc(component)
    if fit is None:
        return None

    start = fit["start"]
    apex = fit["apex"]
    end = fit["end"]
    if start.distance_to(end) < thresholds.stroke_min_length:
        return None
    bow = _point_line_distance(apex, start, end)
    bow_ratio = bow / max(start.distance_to(end), 1.0)
    if bow < 1.0 or bow_ratio < 0.1:
        return None

    stroke_width = float(fit["stroke_width"])
    centerline = (start, apex, end)
    width_samples = (stroke_width,)
    stroke = StrokeAnchor(
        centerline=centerline,
        width_samples=width_samples,
        cap_style="round",
        join_style="round",
    )
    if _stroke_bounds_exceed_component(stroke, component):
        return None
    candidate = AnchorCandidate(
        kind=AnchorKind.ARC,
        raster_error=float(fit["band_residual_error"]),
        node_count=3,
        parameter_count=7,
        stroke=stroke,
        arc=ArcAnchor(
            center=fit["center"],
            radius=float(fit["radius"]),
            theta_start=float(fit["theta_start"]),
            theta_end=float(fit["theta_end"]),
            sweep=bool(fit["sweep"]),
            large_arc=bool(fit["large_arc"]),
        ),
        metrics={
            "arc_bow_ratio": bow_ratio,
            "arc_center_x": fit["center"].x,
            "arc_center_y": fit["center"].y,
            "arc_radius": float(fit["radius"]),
            "arc_theta_start": float(fit["theta_start"]),
            "arc_theta_end": float(fit["theta_end"]),
            "arc_sweep": float(fit["sweep"]),
            "arc_large_arc": float(fit["large_arc"]),
            "arc_angular_span": float(fit["angular_span"]),
            "arc_fit_residual_error": float(fit["band_residual_error"]),
            "stroke_width_variance": stroke_width_variance(width_samples),
        },
    )
    return candidate


def _fit_circular_arc(component: MaskComponent) -> dict[str, object] | None:
    """Fit a circular stroke band to a thin curved component.

    Returns centerline endpoints, apex, radius, angular range, and stroke
    width, or None when the component does not look like a single open
    circular arc band.
    """

    pixels = tuple(component.pixels)
    if len(pixels) < 8:
        return None
    center, radius = _kasa_circle_fit(pixels)
    if center is None or radius is None:
        return None
    max_span = float(max(component.width, component.height))
    if radius < 2.0 or radius > max_span * 4.0:
        return None

    distances = [Point(x, y).distance_to(center) for x, y in pixels]
    inner = min(distances)
    outer = max(distances)
    band_width = max(outer - inner, 1.0)
    if band_width > radius * 0.9:
        return None
    mid_radius = (inner + outer) / 2
    band_residual = sum(abs(d - mid_radius) for d in distances) / len(distances)
    # A uniformly filled band has mean radial deviation near width / 4.
    if band_residual > band_width * 0.5 + 0.5:
        return None

    angles = [
        atan2(y - center.y, x - center.x)
        for x, y in pixels
    ]
    mean_angle = atan2(
        sum(sin(a) for a in angles),
        sum(cos(a) for a in angles),
    )
    centered = sorted(_wrapped_angle(a - mean_angle) for a in angles)
    theta_min = centered[0]
    theta_max = centered[-1]
    span = theta_max - theta_min
    if span < 0.3 or span > 5.9:
        return None
    largest_gap = max(
        (b - a for a, b in zip(centered, centered[1:])),
        default=0.0,
    )
    if largest_gap > max(0.35, span * 0.2):
        return None

    # The whole-band Kåsa fit underestimates the radius on shallow arcs, so
    # refit through per-angle-bin centerline midpoints which sit on the true
    # stroke centerline.
    refit = _refit_arc_through_bin_midpoints(
        pixels,
        center=center,
        mean_angle=mean_angle,
        theta_min=theta_min,
        theta_max=theta_max,
    )
    if refit is None:
        return None
    center, mid_radius, bin_midpoints = refit
    angles = [atan2(y - center.y, x - center.x) for x, y in pixels]
    mean_angle = atan2(
        sum(sin(a) for a in angles),
        sum(cos(a) for a in angles),
    )
    centered = sorted(_wrapped_angle(a - mean_angle) for a in angles)
    theta_min = centered[0]
    theta_max = centered[-1]
    span = theta_max - theta_min
    if span < 0.3 or span > 5.9:
        return None
    # The bin midpoints sit on the stroke centerline. On a true circular arc
    # they deviate from the refit circle only by sampling noise (measured
    # <= 0.35 px across the fixture suite); parabolic and asymmetric curves
    # keep a systematic residual and belong to stroke_path instead.
    midpoint_residual = sum(
        abs(hypot(x - center.x, y - center.y) - mid_radius)
        for x, y in bin_midpoints
    ) / len(bin_midpoints)
    if midpoint_residual > 0.42:
        return None
    # A constant-width stroke band keeps a uniform radial spread along the
    # arc; crescents and other tapered fills swing from thick to thin. Below
    # ~4 px of band the per-bin spread is dominated by pixel quantization
    # (half a pixel is up to half the width), so the test carries no signal.
    if band_width >= 4.0 and _radial_band_uniformity(
        pixels,
        center,
        mean_angle,
        theta_min,
        span,
    ) > 1.8:
        return None

    # Two width estimators with opposite biases: area / arc-length counts cap
    # angles into the length and underestimates wide strokes, while the radial
    # 10th-90th percentile band spans pixel centers (width - 1) plus staircase
    # noise and overestimates thin ones. Their mean tracks the drawn width.
    arc_length = max(span * mid_radius, 1.0)
    area_width = len(pixels) / arc_length
    refit_distances = sorted(Point(x, y).distance_to(center) for x, y in pixels)
    p10 = refit_distances[int(len(refit_distances) * 0.1)]
    p90 = refit_distances[min(int(len(refit_distances) * 0.9), len(refit_distances) - 1)]
    band_width = (p90 - p10) / 0.8 + 1.0
    stroke_width = max((area_width + band_width) / 2, 1.0)

    # Round caps extend the pixel band past the true centerline endpoints by
    # half a stroke width. Inside the outermost cap_angle window a full band
    # cross section would hold cap_angle * R * width pixels while a round cap
    # half-disk holds only pi/4 of that, so a taper below 0.9 marks a cap.
    cap_angle = asin(min(0.95, (stroke_width / 2) / max(mid_radius, 1.0)))
    if cap_angle > 0.01 and stroke_width >= 4.0:
        expected_window_pixels = max(cap_angle * mid_radius * stroke_width, 1.0)
        start_count = sum(1 for a in centered if a < theta_min + cap_angle)
        end_count = sum(1 for a in centered if a > theta_max - cap_angle)
        if start_count / expected_window_pixels < 0.9:
            theta_min += cap_angle
        if end_count / expected_window_pixels < 0.9:
            theta_max -= cap_angle
        span = theta_max - theta_min
        if span < 0.3:
            return None

    theta_start = theta_min + mean_angle
    theta_end = theta_max + mean_angle
    start = _arc_point(center, mid_radius, theta_start)
    end = _arc_point(center, mid_radius, theta_end)
    apex = _arc_point(center, mid_radius, (theta_start + theta_end) / 2)
    if (abs(end.x - start.x) >= abs(end.y - start.y) and end.x < start.x) or (
        abs(end.y - start.y) > abs(end.x - start.x) and end.y < start.y
    ):
        start, end = end, start
        theta_start, theta_end = theta_end, theta_start
    # SVG sweep=1 follows increasing angles (clockwise with y pointing down).
    return {
        "center": center,
        "radius": mid_radius,
        "stroke_width": stroke_width,
        "band_residual_error": band_residual / max(band_width, 1.0) * 0.1,
        "theta_start": theta_start,
        "theta_end": theta_end,
        "angular_span": span,
        "sweep": 1 if theta_end > theta_start else 0,
        "large_arc": 1 if span > pi else 0,
        "start": start,
        "apex": apex,
        "end": end,
    }


def _radial_band_uniformity(
    pixels: tuple[tuple[int, int], ...],
    center: Point,
    mean_angle: float,
    theta_min: float,
    span: float,
) -> float:
    """Max/min ratio of radial band widths across eight angular bins.

    Coarser windows let crescent horns blend into their thick neighbors;
    eight bins keep the taper visible while staying noise-tolerant through
    the 10th-90th percentile spread.
    """

    if span <= 0:
        return 1.0
    bin_count = 8
    bins: list[list[float]] = [[] for _ in range(bin_count)]
    for x, y in pixels:
        offset = _wrapped_angle(atan2(y - center.y, x - center.x) - mean_angle)
        position = (offset - theta_min) / span
        index = min(bin_count - 1, max(0, int(position * bin_count)))
        bins[index].append(hypot(x - center.x, y - center.y))
    widths = []
    for bucket in bins:
        if len(bucket) < 6:
            continue
        bucket.sort()
        p10 = bucket[int(len(bucket) * 0.1)]
        p90 = bucket[min(int(len(bucket) * 0.9), len(bucket) - 1)]
        widths.append(max(p90 - p10, 0.5))
    if len(widths) < 3:
        return 1.0
    return max(widths) / min(widths)


def _refit_arc_through_bin_midpoints(
    pixels: tuple[tuple[int, int], ...],
    *,
    center: Point,
    mean_angle: float,
    theta_min: float,
    theta_max: float,
) -> tuple[Point, float, tuple[tuple[float, float], ...]] | None:
    span = theta_max - theta_min
    if span <= 0:
        return None
    bin_count = max(8, min(48, int(len(pixels) / 4)))
    bins: list[list[tuple[float, float]]] = [[] for _ in range(bin_count)]
    for x, y in pixels:
        offset = _wrapped_angle(atan2(y - center.y, x - center.x) - mean_angle)
        index = int((offset - theta_min) / span * (bin_count - 1) + 0.5)
        if 0 <= index < bin_count:
            bins[index].append((float(x), float(y)))
    midpoints = tuple(
        (
            sum(x for x, _ in bucket) / len(bucket),
            sum(y for _, y in bucket) / len(bucket),
        )
        for bucket in bins
        if bucket
    )
    if len(midpoints) < 5:
        return None
    refit_center, refit_radius = _kasa_circle_fit(midpoints)
    if refit_center is None or refit_radius is None or refit_radius < 2.0:
        return None
    return refit_center, refit_radius, midpoints


def _kasa_circle_fit(
    pixels: tuple[tuple[float, float], ...],
) -> tuple[Point | None, float | None]:
    n = float(len(pixels))
    sum_x = sum(float(x) for x, _ in pixels)
    sum_y = sum(float(y) for _, y in pixels)
    sum_xx = sum(float(x * x) for x, _ in pixels)
    sum_yy = sum(float(y * y) for _, y in pixels)
    sum_xy = sum(float(x * y) for x, y in pixels)
    sum_z = sum(float(x * x + y * y) for x, y in pixels)
    sum_xz = sum(float(x * (x * x + y * y)) for x, y in pixels)
    sum_yz = sum(float(y * (x * x + y * y)) for x, y in pixels)
    matrix = (
        (sum_xx, sum_xy, sum_x),
        (sum_xy, sum_yy, sum_y),
        (sum_x, sum_y, n),
    )
    solved = _solve_3x3(matrix, (sum_xz, sum_yz, sum_z))
    if solved is None:
        return None, None
    a, b, c = solved
    center = Point(a / 2, b / 2)
    radius_squared = c + center.x**2 + center.y**2
    if radius_squared <= 0:
        return None, None
    return center, sqrt(radius_squared)


def _wrapped_angle(angle: float) -> float:
    while angle <= -pi:
        angle += 2 * pi
    while angle > pi:
        angle -= 2 * pi
    return angle


def _arc_point(center: Point, radius: float, theta: float) -> Point:
    return Point(
        center.x + radius * cos(theta),
        center.y + radius * sin(theta),
    )


def _smooth_stroke_path_candidate(
    component: MaskComponent,
    thresholds: AnchorThresholdConfig,
) -> AnchorCandidate | None:
    """Fit a bounded-control-point smooth centerline to a thin curved band.

    Covers S-curves, waves, and asymmetric curves that a single circular arc
    cannot represent. The centerline is extracted as per-column (or per-row)
    means along the dominant axis, so the component must be functional along
    that axis.
    """

    width = component.width
    height = component.height
    if max(width, height) < thresholds.stroke_min_length * 2:
        return None
    density = component.area / max(width * height, 1)
    if density > 0.55:
        return None

    horizontal = width >= height
    samples = _functional_centerline_samples(component, horizontal=horizontal)
    if samples is None or len(samples) < 5:
        return None

    # A smooth band has at most the four cap corners of its butt ends.
    # More sharp outline corners mean spikes or kinks (star tips, chevron
    # bends) that a smooth centerline would blur into bulges.
    outline = _traced_outline(component)
    if outline is not None and len(outline) >= 16:
        if len(_detect_outline_corners(outline)) > 4:
            return None

    path_length = sum(
        a.distance_to(b) for a, b in zip(samples, samples[1:])
    )
    if path_length < thresholds.stroke_min_length * 2:
        return None
    stroke_width = max(component.area / max(path_length, 1.0), 1.0)
    if stroke_width > min(width, height) * 0.8:
        return None
    if path_length / stroke_width < thresholds.stroke_min_length_width_ratio:
        return None

    cap_style = _smooth_path_cap_style(component, samples, stroke_width)
    if cap_style == "round" and stroke_width >= 4.0:
        # Round caps extend the pixel columns past the true curve endpoints
        # by half a stroke width; trim that overhang off the centerline
        # before judging curvature, otherwise a straight capped stroke looks
        # tilted against its own chord.
        trimmed = _trimmed_centerline_samples(samples, stroke_width / 2)
        if len(trimmed) >= 5:
            samples = trimmed

    control_points = _downsampled_control_points(samples, maximum=7)
    chord = control_points[0].distance_to(control_points[-1])
    # Caps distort the outermost column means on straight strokes, so only
    # interior control points may claim curvature.
    bow = max(
        _point_line_distance(point, control_points[0], control_points[-1])
        for point in control_points[1:-1]
    )
    if chord <= 0 or bow / max(chord, 1.0) < 0.03:
        return None

    width_samples = _functional_width_samples(
        component,
        control_points,
        horizontal=horizontal,
        fallback_width=stroke_width,
    )
    # A smooth stroke keeps a near-constant width; tapered fills such as
    # crescents swing far wider and belong to the organic path fallback.
    if stroke_width_variance(width_samples) > 0.35:
        return None
    stroke = StrokeAnchor(
        centerline=control_points,
        width_samples=width_samples,
        cap_style=cap_style,
        join_style="round",
    )
    if _stroke_bounds_exceed_component(stroke, component):
        return None
    residual = _centerline_fit_residual(samples, control_points)
    # Direction change along a smooth curve is intent, not noise, so the
    # generic line_smoothness_error does not apply here. Quality is the
    # centerline fit residual plus turn-angle jitter (second differences).
    return AnchorCandidate(
        kind=AnchorKind.STROKE_PATH,
        raster_error=residual * 0.1,
        node_count=len(control_points),
        parameter_count=len(width_samples) + len(control_points) * 2,
        stroke=stroke,
        metrics={
            # The residual already enters the ranking as raster_error, and
            # direction change along a deliberate curve is intent rather than
            # a defect, so neither metric carries the _error suffix that
            # quality_metric_error would charge to the ranking.
            "smooth_path_fit_residual": residual,
            "smooth_path_bow_ratio": bow / max(chord, 1.0),
            "curvature_jitter": _curvature_jitter(control_points),
            "stroke_width_variance": stroke_width_variance(width_samples),
        },
    )


def _curvature_jitter(points: tuple[Point, ...]) -> float:
    """Mean absolute second difference of segment turn angles."""

    if len(points) < 4:
        return 0.0
    turns: list[float] = []
    for previous, current, following in zip(points, points[1:], points[2:]):
        first = atan2(current.y - previous.y, current.x - previous.x)
        second = atan2(following.y - current.y, following.x - current.x)
        turns.append(_wrapped_angle(second - first))
    diffs = [abs(b - a) for a, b in zip(turns, turns[1:])]
    if not diffs:
        return 0.0
    return sum(diffs) / len(diffs)


def _functional_centerline_samples(
    component: MaskComponent,
    *,
    horizontal: bool,
) -> tuple[Point, ...] | None:
    columns: dict[int, list[int]] = {}
    for x, y in component.pixels:
        key, value = (x, y) if horizontal else (y, x)
        columns.setdefault(key, []).append(value)

    if len(columns) < 5:
        return None
    spans = []
    means = []
    for key in sorted(columns):
        values = columns[key]
        spans.append(max(values) - min(values) + 1)
        means.append((key, sum(values) / len(values)))
    typical_span = sorted(spans)[len(spans) // 2]
    # Multi-valued columns mean the curve folds back along this axis (for
    # example a steep arc); the per-column mean would cut across the fold.
    wild_columns = sum(1 for span in spans if span > typical_span * 2 + 2)
    if wild_columns > len(spans) * 0.1:
        return None

    smoothed: list[Point] = []
    for index, (key, value) in enumerate(means):
        window = means[max(0, index - 1) : index + 2]
        smoothed_value = sum(item[1] for item in window) / len(window)
        point = (
            Point(float(key), smoothed_value)
            if horizontal
            else Point(smoothed_value, float(key))
        )
        smoothed.append(point)
    return tuple(smoothed)


def _trimmed_centerline_samples(
    samples: tuple[Point, ...],
    overhang: float,
) -> tuple[Point, ...]:
    if overhang <= 0 or len(samples) < 3:
        return samples
    front = 0
    travelled = 0.0
    while front < len(samples) - 1 and travelled < overhang:
        travelled += samples[front].distance_to(samples[front + 1])
        front += 1
    back = len(samples) - 1
    travelled = 0.0
    while back > 0 and travelled < overhang:
        travelled += samples[back].distance_to(samples[back - 1])
        back -= 1
    if back <= front:
        return samples
    return samples[front : back + 1]


def _downsampled_control_points(
    samples: tuple[Point, ...],
    *,
    maximum: int,
) -> tuple[Point, ...]:
    if len(samples) <= maximum:
        return samples
    last = len(samples) - 1
    return tuple(
        samples[round(last * index / (maximum - 1))]
        for index in range(maximum)
    )


def _functional_width_samples(
    component: MaskComponent,
    control_points: tuple[Point, ...],
    *,
    horizontal: bool,
    fallback_width: float,
) -> tuple[float, ...]:
    columns: dict[int, int] = {}
    for x, y in component.pixels:
        key = x if horizontal else y
        columns[key] = columns.get(key, 0) + 1

    samples = []
    last = len(control_points) - 1
    # Sample away from the endpoints (the outermost columns only contain the
    # cap tip) but densely enough that tapered fills cannot hide their swing
    # between probes.
    for index in (
        round(last * 0.1),
        round(last * 0.3),
        last // 2,
        round(last * 0.7),
        round(last * 0.9),
    ):
        point = control_points[index]
        key = round(point.x if horizontal else point.y)
        count = columns.get(key, 0)
        if count <= 0:
            samples.append(float(fallback_width))
            continue
        slope = _local_centerline_slope(control_points, index, horizontal=horizontal)
        samples.append(max(count / sqrt(1 + slope * slope), 1.0))
    return tuple(samples)


def _local_centerline_slope(
    control_points: tuple[Point, ...],
    index: int,
    *,
    horizontal: bool,
) -> float:
    previous = control_points[max(0, index - 1)]
    following = control_points[min(len(control_points) - 1, index + 1)]
    run = (following.x - previous.x) if horizontal else (following.y - previous.y)
    rise = (following.y - previous.y) if horizontal else (following.x - previous.x)
    if abs(run) < 1e-6:
        return 0.0
    return rise / run


def _smooth_path_cap_style(
    component: MaskComponent,
    samples: tuple[Point, ...],
    stroke_width: float,
) -> str:
    """Classify stroke ends by taper: round caps thin out, flat ones do not.

    Square caps are indistinguishable from butt caps here because the
    column-mean centerline already extends through the cap, so flat ends
    report `butt` with accordingly longer endpoints.
    """

    if stroke_width < 4.0:
        return "round"
    horizontal = component.width >= component.height
    columns: dict[int, int] = {}
    for x, y in component.pixels:
        key = x if horizontal else y
        columns[key] = columns.get(key, 0) + 1
    keys = sorted(columns)
    if len(keys) < 6:
        return "round"
    interior = sorted(columns[key] for key in keys[2:-2])
    typical = interior[len(interior) // 2]
    if typical <= 0:
        return "round"
    end_counts = (columns[keys[0]], columns[keys[-1]])
    if all(count >= typical * 0.75 for count in end_counts):
        return "butt"
    return "round"


def _centerline_fit_residual(
    samples: tuple[Point, ...],
    control_points: tuple[Point, ...],
) -> float:
    if len(control_points) < 2:
        return 1.0
    total = 0.0
    for sample in samples:
        best = min(
            _point_segment_distance_points(sample, a, b)
            for a, b in zip(control_points, control_points[1:])
        )
        total += best
    return total / len(samples)


def _point_segment_distance_points(point: Point, start: Point, end: Point) -> float:
    dx = end.x - start.x
    dy = end.y - start.y
    length_squared = dx * dx + dy * dy
    if length_squared <= 0:
        return point.distance_to(start)
    t = ((point.x - start.x) * dx + (point.y - start.y) * dy) / length_squared
    t = max(0.0, min(1.0, t))
    return point.distance_to(Point(start.x + dx * t, start.y + dy * t))


def _stroke_bounds_exceed_component(
    stroke: StrokeAnchor,
    component: MaskComponent,
    *,
    max_area_ratio: float = 2.25,
    max_side_ratio: float = 1.7,
) -> bool:
    if not stroke.centerline:
        return False
    width = mean(stroke.width_samples) if stroke.width_samples else 1.0
    pad = width / 2
    xs = [point.x for point in stroke.centerline]
    ys = [point.y for point in stroke.centerline]
    stroke_width = max(xs) - min(xs) + width
    stroke_height = max(ys) - min(ys) + width
    component_width = max(component.width, 1)
    component_height = max(component.height, 1)
    stroke_area = max(stroke_width, 0.0) * max(stroke_height, 0.0)
    component_area = component_width * component_height
    if stroke_area / component_area > max_area_ratio:
        return True
    if stroke_width / component_width > max_side_ratio:
        return True
    if stroke_height / component_height > max_side_ratio:
        return True
    min_x, min_y, max_x, max_y = component.bounds
    x_tolerance = max(1.0, component_width * 0.35)
    y_tolerance = max(1.0, component_height * 0.35)
    return (
        min(xs) - pad < min_x - x_tolerance
        or max(xs) + pad > max_x + x_tolerance
        or min(ys) - pad < min_y - y_tolerance
        or max(ys) + pad > max_y + y_tolerance
    )


def _axis_aligned_filled_rect_component(component: MaskComponent) -> bool:
    if component.area != component.width * component.height:
        return False
    min_x, min_y, max_x, max_y = component.bounds
    return all(
        min_y <= y <= max_y and left == min_x and right == max_x
        for y, left, right in component.row_spans()
    )


def _arc_endpoints(component: MaskComponent) -> tuple[Point, Point]:
    min_x, min_y, max_x, max_y = component.bounds
    if component.width >= component.height:
        left = [y for x, y in component.pixels if x == min_x]
        right = [y for x, y in component.pixels if x == max_x]
        return (
            Point(min_x, sum(left) / len(left)),
            Point(max_x, sum(right) / len(right)),
        )
    top = [x for x, y in component.pixels if y == min_y]
    bottom = [x for x, y in component.pixels if y == max_y]
    return (
        Point(sum(top) / len(top), min_y),
        Point(sum(bottom) / len(bottom), max_y),
    )


def _point_line_distance(point: Point, start: Point, end: Point) -> float:
    return abs(_signed_point_line_distance(point, start, end))


def _signed_point_line_distance(point: Point, start: Point, end: Point) -> float:
    dx = end.x - start.x
    dy = end.y - start.y
    denominator = hypot(dx, dy)
    if denominator == 0:
        return point.distance_to(start)
    return (
        dy * point.x - dx * point.y + end.x * start.y - end.y * start.x
    ) / denominator


def _principal_axis(
    component: MaskComponent,
) -> tuple[Point, tuple[float, float], float, float, float, float] | None:
    if component.area < 2:
        return None

    center = component.centroid
    xx = 0.0
    yy = 0.0
    xy = 0.0
    for x, y in component.pixels:
        centered_x = x - center.x
        centered_y = y - center.y
        xx += centered_x * centered_x
        yy += centered_y * centered_y
        xy += centered_x * centered_y

    if xx == 0 and yy == 0:
        return None

    if xy == 0:
        direction = (1.0, 0.0) if xx >= yy else (0.0, 1.0)
    else:
        trace = xx + yy
        determinant = xx * yy - xy * xy
        eigenvalue = trace / 2 + sqrt(max((trace / 2) ** 2 - determinant, 0.0))
        dx = xy
        dy = eigenvalue - xx
        length = hypot(dx, dy)
        if length == 0:
            direction = (1.0, 0.0)
        else:
            direction = (dx / length, dy / length)

    dx, dy = direction
    minor = (-dy, dx)
    min_major = max_major = min_minor = max_minor = 0.0
    for index, (x, y) in enumerate(component.pixels):
        centered_x = x - center.x
        centered_y = y - center.y
        major_projection = centered_x * dx + centered_y * dy
        minor_projection = centered_x * minor[0] + centered_y * minor[1]
        if index == 0:
            min_major = max_major = major_projection
            min_minor = max_minor = minor_projection
            continue
        if major_projection < min_major:
            min_major = major_projection
        elif major_projection > max_major:
            max_major = major_projection
        if minor_projection < min_minor:
            min_minor = minor_projection
        elif minor_projection > max_minor:
            max_minor = minor_projection

    return (
        center,
        direction,
        min_major,
        max_major,
        min_minor,
        max_minor,
    )


def _quad_candidate(
    component: MaskComponent,
    thresholds: AnchorThresholdConfig,
) -> AnchorCandidate | None:
    if component.width < 3 or component.height < 3:
        return None
    if (
        component.area
        < component.width * component.height * thresholds.quad_min_fill_ratio
    ):
        return None

    if len(component.boundary_pixels) < 4:
        return None

    quad = _extreme_quad(component)
    if quad is None:
        return None
    fill_error = _scanline_quad_fill_error(component, quad)
    if fill_error > thresholds.quad_max_fill_error:
        return None
    if _has_compact_fill_defect(component, _quad_inside_predicate(quad)):
        return None

    candidate = AnchorCandidate(
        kind=AnchorKind.QUAD,
        raster_error=fill_error,
        node_count=4,
        parameter_count=8,
        quad=quad,
        metrics=_quad_subtype_metrics(quad),
    )
    return enrich_anchor_metrics(candidate)


def _quad_inside_predicate(quad: QuadAnchor):
    corners = quad.corners

    def inside(x: float, y: float) -> bool:
        sign = 0
        for index in range(4):
            ax, ay = corners[index].x, corners[index].y
            bx, by = corners[(index + 1) % 4].x, corners[(index + 1) % 4].y
            cross = (bx - ax) * (y - ay) - (by - ay) * (x - ax)
            if abs(cross) < 1e-9:
                continue
            current = 1 if cross > 0 else -1
            if sign == 0:
                sign = current
            elif sign != current:
                return False
        return True

    return inside


def _has_compact_fill_defect(component: MaskComponent, inside) -> bool:
    """True when the candidate shape covers a chunky region the ink lacks.

    Notches and star valleys cost only a few percent of fill error, but
    they form one compact missing region; anti-aliased edge fringes are
    thin and stay below the thickness cut. Regions are measured against
    the bounding box (not the fitted polygon): a rectangular missing
    block flush with a box edge is the occlusion pattern the fragment
    promotion resolves later, so it must not disqualify the candidate.
    The ``inside`` predicate then decides whether a genuinely concave
    region affects this candidate's shape at all (wedge quads leave the
    box-corner triangles outside their polygon). Large components skip
    the scan to keep candidate generation cheap.
    """

    min_x, min_y, max_x, max_y = component.bounds
    window_area = (max_x - min_x + 1) * (max_y - min_y + 1)
    if window_area > 100_000:
        return False
    pixels = component.pixels
    missing = {
        (x, y)
        for y in range(min_y, max_y + 1)
        for x in range(min_x, max_x + 1)
        if (x, y) not in pixels
    }
    min_area = max(16, component.area * 0.02)
    while missing:
        seed = missing.pop()
        region = [seed]
        queue = [seed]
        while queue:
            cx, cy = queue.pop()
            for nx, ny in (
                (cx - 1, cy),
                (cx + 1, cy),
                (cx, cy - 1),
                (cx, cy + 1),
            ):
                if (nx, ny) in missing:
                    missing.remove((nx, ny))
                    region.append((nx, ny))
                    queue.append((nx, ny))
        if len(region) < min_area:
            continue
        xs = [x for x, _ in region]
        ys = [y for _, y in region]
        region_w = max(xs) - min(xs) + 1
        region_h = max(ys) - min(ys) + 1
        # Thickness via perimeter (a thin band's perimeter is roughly twice
        # its length): the box extent underestimates the length of slits
        # that wind diagonally, misclassifying an S-shaped cut as chunky.
        region_set = set(region)
        perimeter = sum(
            1
            for x, y in region
            if (x - 1, y) not in region_set
            or (x + 1, y) not in region_set
            or (x, y - 1) not in region_set
            or (x, y + 1) not in region_set
        )
        if 2 * len(region) / max(perimeter, 1) <= 3.0:
            continue
        rectangular = len(region) / (region_w * region_h) >= 0.85
        touches_edge = (
            min(xs) <= min_x
            or max(xs) >= max_x
            or min(ys) <= min_y
            or max(ys) >= max_y
        )
        if rectangular and touches_edge:
            continue
        covered = sum(1 for x, y in region if inside(x, y))
        if covered >= max(min_area, len(region) * 0.5):
            return True
    return False


def _extreme_quad(component: MaskComponent) -> QuadAnchor | None:
    points = [Point(x, y) for x, y in component.boundary_pixels]
    top_left = min(points, key=lambda point: (point.x + point.y, point.y, point.x))
    top_right = max(points, key=lambda point: (point.x - point.y, -point.y, point.x))
    bottom_right = max(points, key=lambda point: (point.x + point.y, point.y, point.x))
    bottom_left = min(points, key=lambda point: (point.x - point.y, -point.x, point.y))
    corners = (top_left, top_right, bottom_right, bottom_left)
    unique = {(point.x, point.y) for point in corners}
    if len(unique) < 4:
        return None
    return QuadAnchor(corners=corners)


def _quad_subtype_metrics(quad: QuadAnchor) -> dict[str, float]:
    corners = quad.corners
    top_width = corners[0].distance_to(corners[1])
    bottom_width = corners[3].distance_to(corners[2])
    left_shift = corners[3].x - corners[0].x
    right_shift = corners[2].x - corners[1].x
    if (
        abs(top_width - bottom_width) <= 1.0
        and abs(left_shift - right_shift) <= 1.0
        and abs(left_shift) > 0.5
    ):
        return {"quad_subtype_code": 2.0}
    if abs(top_width - bottom_width) > 1.0:
        return {"quad_subtype_code": 1.0}
    return {}


def _rect_candidate(
    component: MaskComponent,
    thresholds: AnchorThresholdConfig,
) -> AnchorCandidate | None:
    if component.width < 3 or component.height < 3:
        return None

    expected_area = component.width * component.height
    fill_error = 1.0 - component.area / expected_area
    if fill_error > thresholds.rect_max_fill_error:
        return None

    min_x, min_y, max_x, max_y = component.bounds
    for y, left, right in component.row_spans():
        if y < min_y or y > max_y:
            return None
        if abs(left - min_x) > 1 or abs(right - max_x) > 1:
            return None

    # Row spans only see the leftmost/rightmost ink per row, so an interior
    # notch biting in from an edge stays invisible to the checks above.
    if _has_compact_fill_defect(component, lambda x, y: True):
        return None

    quad = QuadAnchor(
        corners=(
            Point(min_x, min_y),
            Point(max_x, min_y),
            Point(max_x, max_y),
            Point(min_x, max_y),
        )
    )
    candidate = AnchorCandidate(
        kind=AnchorKind.RECT,
        raster_error=fill_error,
        node_count=4,
        parameter_count=4,
        quad=quad,
        metrics={"rect_fill_error": fill_error},
    )
    return enrich_anchor_metrics(candidate)


def _rounded_rect_candidate(
    component: MaskComponent,
    thresholds: AnchorThresholdConfig,
) -> AnchorCandidate | None:
    if component.width < 6 or component.height < 5:
        return None

    spans = component.row_spans()
    if len(spans) < 5:
        return None

    widths = [right - left + 1 for _, left, right in spans]
    max_width = max(widths)
    min_width = min(widths)
    if max_width < component.width - 1:
        return None
    if max_width - min_width < 2:
        return None

    mid_width = widths[len(widths) // 2]
    if mid_width < max_width - 1:
        return None
    if widths[0] >= mid_width - 1 or widths[-1] >= mid_width - 1:
        return None
    symmetry_tolerance = max(1, len(widths) // 8)
    if abs(widths[0] - widths[-1]) > symmetry_tolerance:
        return None

    expected_area = component.width * component.height
    fill_error = 1.0 - component.area / expected_area
    if fill_error > thresholds.rounded_rect_max_fill_error:
        return None

    min_x, min_y, max_x, max_y = component.bounds
    corner_radius = _rounded_rect_corner_radius(widths)
    quad = QuadAnchor(
        corners=(
            Point(min_x, min_y),
            Point(max_x, min_y),
            Point(max_x, max_y),
            Point(min_x, max_y),
        )
    )
    candidate = AnchorCandidate(
        kind=AnchorKind.ROUNDED_RECT,
        raster_error=fill_error,
        node_count=4,
        parameter_count=5,
        quad=quad,
        metrics={
            "corner_radius": float(corner_radius),
            "rounded_rect_fill_error": fill_error,
        },
    )
    return candidate


def _rounded_rect_corner_radius(widths: list[int]) -> float:
    max_width = max(widths)
    width_radius = (max_width - min(widths[0], widths[-1])) / 2
    top_taper = _taper_rows_to_full_width(widths)
    bottom_taper = _taper_rows_to_full_width(list(reversed(widths)))
    return max(1.0, float(width_radius), float(top_taper), float(bottom_taper))


def _taper_rows_to_full_width(widths: list[int]) -> int:
    max_width = max(widths)
    for index, width in enumerate(widths):
        if width >= max_width:
            return index
    return 0


def _scanline_quad_fill_error(component: MaskComponent, quad: QuadAnchor) -> float:
    corners = quad.corners
    min_y = int(min(point.y for point in corners))
    max_y = int(max(point.y for point in corners))
    if max_y <= min_y:
        return 1.0

    expected = 0
    missing = 0
    extra = 0
    row_pixels: dict[int, set[int]] = {}
    for x, pixel_y in component.pixels:
        row_pixels.setdefault(pixel_y, set()).add(x)
    for y in range(min_y, max_y + 1):
        row_span = _quad_row_span(corners, float(y))
        if row_span is None:
            continue
        left, right = row_span
        actual_xs = row_pixels.get(y, set())
        expected += right - left + 1
        missing += sum(1 for x in range(left, right + 1) if x not in actual_xs)
        extra += sum(1 for x in actual_xs if x < left or x > right)

    if expected == 0:
        return 1.0
    return (missing + extra) / expected


def _quad_row_span(
    corners: tuple[Point, Point, Point, Point],
    y: float,
) -> tuple[int, int] | None:
    intersections: list[float] = []
    for index, start in enumerate(corners):
        end = corners[(index + 1) % len(corners)]
        if start.y == end.y:
            if y == start.y:
                intersections.extend((start.x, end.x))
            continue
        min_y = min(start.y, end.y)
        max_y = max(start.y, end.y)
        if y < min_y or y > max_y:
            continue
        t = (y - start.y) / (end.y - start.y)
        if 0.0 <= t <= 1.0:
            intersections.append(start.x + (end.x - start.x) * t)
    if len(intersections) < 2:
        return None
    left = round(min(intersections))
    right = round(max(intersections))
    if left > right:
        left, right = right, left
    return left, right






def _freeform_cutout_strokes(
    component: MaskComponent,
    *,
    min_length: int,
    max_thickness: int,
    color: str,
) -> tuple[AnchorCandidate, ...]:
    min_x, min_y, max_x, max_y = component.bounds
    if max_x - min_x < min_length or max_y - min_y < 3:
        return ()

    candidates: list[AnchorCandidate] = []
    for gap in _interior_gap_components(component, min_area=min_length):
        if _gap_open_to_background(gap, component):
            continue
        candidate = _freeform_cutout_candidate(
            gap,
            host_bounds=component.bounds,
            min_length=min_length,
            max_thickness=max_thickness,
            color=color,
        )
        if candidate is not None:
            candidates.append(candidate)
    return tuple(candidates)


def _gap_open_to_background(
    gap: MaskComponent,
    component: MaskComponent,
) -> bool:
    """Detect interior-window gaps that actually leak to the background.

    The interior scan only inspects pixels strictly inside the host bounds, so
    a concave region (for example below or above a shallow arc) shows up as a
    gap component even though it connects to the outside. A real hole is
    sealed by host pixels just outside the interior window.
    """

    min_x, min_y, max_x, max_y = component.bounds
    for x, y in gap.pixels:
        if x == min_x + 1 and (min_x, y) not in component.pixels:
            return True
        if x == max_x - 1 and (max_x, y) not in component.pixels:
            return True
        if y == min_y + 1 and (x, min_y) not in component.pixels:
            return True
        if y == max_y - 1 and (x, max_y) not in component.pixels:
            return True
    return False


def _interior_gap_components(
    component: MaskComponent,
    *,
    min_area: int,
) -> tuple[MaskComponent, ...]:
    min_x, min_y, max_x, max_y = component.bounds
    interior_width = max_x - min_x - 1
    interior_height = max_y - min_y - 1
    if interior_width <= 0 or interior_height <= 0:
        return ()

    host_pixels = component.pixels
    grid = bytearray(interior_width * interior_height)
    has_gap = False
    for local_y, y in enumerate(range(min_y + 1, max_y)):
        row_offset = local_y * interior_width
        for local_x, x in enumerate(range(min_x + 1, max_x)):
            if (x, y) in host_pixels:
                continue
            index = row_offset + local_x
            grid[index] = 1
            has_gap = True
    if not has_gap:
        return ()

    components: list[MaskComponent] = []
    for seed in range(len(grid)):
        if not grid[seed]:
            continue
        grid[seed] = 0
        pixels: list[tuple[int, int]] = []
        local_start_x = seed % interior_width
        local_start_y = seed // interior_width
        start_x = min_x + 1 + local_start_x
        start_y = min_y + 1 + local_start_y
        component_min_x = component_max_x = start_x
        component_min_y = component_max_y = start_y
        sum_x = 0
        sum_y = 0
        queue: deque[int] = deque([seed])
        while queue:
            index = queue.popleft()
            local_x = index % interior_width
            local_y = index // interior_width
            x = min_x + 1 + local_x
            y = min_y + 1 + local_y
            pixels.append((x, y))
            sum_x += x
            sum_y += y
            if x < component_min_x:
                component_min_x = x
            elif x > component_max_x:
                component_max_x = x
            if y < component_min_y:
                component_min_y = y
            elif y > component_max_y:
                component_max_y = y
            can_left = local_x > 0
            can_right = local_x < interior_width - 1
            can_up = local_y > 0
            can_down = local_y < interior_height - 1
            if can_up:
                top = index - interior_width
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
                bottom = index + interior_width
                if grid[bottom]:
                    grid[bottom] = 0
                    queue.append(bottom)
                if can_left and grid[bottom - 1]:
                    grid[bottom - 1] = 0
                    queue.append(bottom - 1)
                if can_right and grid[bottom + 1]:
                    grid[bottom + 1] = 0
                    queue.append(bottom + 1)
        if len(pixels) >= min_area:
            area = len(pixels)
            components.append(
                MaskComponent(
                    frozenset(pixels),
                    bounds_hint=(
                        component_min_x,
                        component_min_y,
                        component_max_x,
                        component_max_y,
                    ),
                    centroid_hint=Point(sum_x / area, sum_y / area),
                )
            )

    return tuple(sorted(components, key=lambda item: item.area, reverse=True))


def _freeform_cutout_candidate(
    component: MaskComponent,
    *,
    host_bounds: tuple[int, int, int, int],
    min_length: int,
    max_thickness: int,
    color: str,
) -> AnchorCandidate | None:
    if _touches_bounds(component, host_bounds):
        return None

    horizontal = component.width >= component.height
    samples = _functional_centerline_samples(component, horizontal=horizontal)
    if samples is None or len(samples) < 2:
        # Strongly curved slits fold back along both axes, so no functional
        # centerline exists; the circular arc fit works directly on pixels
        # and angles and does not need one.
        arc_fit = _fit_circular_arc(component)
        if arc_fit is None:
            return None
        arc_width = float(arc_fit["stroke_width"])
        arc_length = float(arc_fit["angular_span"]) * float(arc_fit["radius"])
        if arc_width > max_thickness or arc_length < min_length:
            return None
        return _arc_cutout_candidate(arc_fit, arc_width, color)
    path_length = sum(a.distance_to(b) for a, b in zip(samples, samples[1:]))
    path_length = max(path_length, float(len(samples)))
    # Ink width (area / length) measures the actual slit thickness and also
    # rejects bulky holes like ring interiors.
    stroke_width = max(component.area / path_length, 1.0)
    if path_length < min_length or stroke_width > max_thickness:
        return None

    start = samples[0]
    end = samples[-1]
    # A slit with an inflection (S or wave) bends to both sides of its
    # chord; one circular arc cannot follow the sign change and a single
    # midpoint control sags to one side, so the centerline keeps enough
    # points to trace each bend.
    deviation_limit = max(1.0, stroke_width * 0.6)
    signed = [
        _signed_point_line_distance(point, start, end) for point in samples
    ]
    if max(signed) >= deviation_limit and -min(signed) >= deviation_limit:
        centerline = _downsampled_control_points(samples, maximum=7)
        return _cutout_centerline_candidate(centerline, stroke_width, color)
    control = max(
        samples,
        key=lambda point: _point_line_distance(point, start, end),
    )
    bow = _point_line_distance(control, start, end)
    bowed = bow >= max(1.0, stroke_width * 0.75)
    if bowed:
        # A bowed gap is usually a circular slit (for example concentric to a
        # ring band); a true arc fit follows that curvature exactly where a
        # three-point spline sags flat.
        arc_fit = _fit_circular_arc(component)
        if arc_fit is not None:
            arc_candidate = _arc_cutout_candidate(arc_fit, stroke_width, color)
            if arc_candidate is not None:
                return arc_candidate
    centerline = (start, control, end) if bowed else (start, end)
    return _cutout_centerline_candidate(centerline, stroke_width, color)


def _arc_cutout_candidate(
    fit: dict[str, object],
    stroke_width: float,
    color: str,
) -> AnchorCandidate | None:
    start = fit["start"]
    apex = fit["apex"]
    end = fit["end"]
    if start.distance_to(end) <= 0:
        return None
    candidate = AnchorCandidate(
        kind=AnchorKind.ARC,
        raster_error=float(fit["band_residual_error"]),
        node_count=3,
        parameter_count=7,
        color=color,
        stroke=StrokeAnchor(
            centerline=(start, apex, end),
            width_samples=(stroke_width,),
            is_cutout=True,
            cap_style="round",
            join_style="round",
        ),
        arc=ArcAnchor(
            center=fit["center"],
            radius=float(fit["radius"]),
            theta_start=float(fit["theta_start"]),
            theta_end=float(fit["theta_end"]),
            sweep=bool(fit["sweep"]),
            large_arc=bool(fit["large_arc"]),
        ),
        metrics={
            "arc_fit_residual_error": float(fit["band_residual_error"]),
        },
    )
    return candidate



def _cutout_centerline_candidate(
    centerline: tuple[Point, ...],
    width: float,
    color: str,
) -> AnchorCandidate:
    # Bowed cut-outs export as smooth stroke paths so the overlay follows
    # the curved gap instead of kinking across it.
    kind = (
        AnchorKind.STROKE_PATH
        if len(centerline) >= 3
        else AnchorKind.STROKE_POLYLINE
    )
    candidate = AnchorCandidate(
        kind=kind,
        raster_error=0.0,
        node_count=len(centerline),
        parameter_count=max(5, len(centerline) * 2 + 1),
        color=color,
        stroke=StrokeAnchor(
            centerline=centerline,
            width_samples=(float(width),),
            is_cutout=True,
            cap_style="butt" if len(centerline) == 2 else "round",
        ),
    )
    return enrich_anchor_metrics(candidate)


def _touches_bounds(
    component: MaskComponent,
    bounds: tuple[int, int, int, int],
) -> bool:
    min_x, min_y, max_x, max_y = bounds
    component_min_x, component_min_y, component_max_x, component_max_y = (
        component.bounds
    )
    return (
        component_min_x <= min_x
        or component_max_x >= max_x
        or component_min_y <= min_y
        or component_max_y >= max_y
    )
