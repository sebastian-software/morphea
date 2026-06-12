"""Primitive anchor detection from flat binary mask components."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from math import asin, atan2, cos, hypot, pi, sin, sqrt
from statistics import mean

from morphea.anchors import (
    AnchorCandidate,
    AnchorKind,
    ArcAnchor,
    CircleAnchor,
    EllipseAnchor,
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
    stroke_circle_min_inner_ratio: float = 0.45
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
    max_thickness: int = 3,
    color: str = "#ffffff",
) -> tuple[AnchorCandidate, ...]:
    """Detect background-gap strokes inside one already-isolated component.

    Every enclosed gap is analyzed as one connected component, so straight,
    diagonal, and curved gaps share a single detection path and cannot
    fragment each other the way separate row/column scans did.
    """

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
    stroke_circle = _stroke_circle_candidate(component, thresholds)
    if stroke_circle is not None:
        candidates.append(stroke_circle)

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

    smooth_path = _smooth_stroke_path_candidate(component, thresholds)
    if smooth_path is not None:
        candidates.append(smooth_path)

    stroke = _stroke_candidate(component, thresholds)
    if stroke is not None:
        candidates.append(stroke)

    rect = _rect_candidate(component, thresholds)
    if rect is not None:
        candidates.append(rect)

    rounded_rect = _rounded_rect_candidate(component, thresholds)
    if rounded_rect is not None:
        candidates.append(rounded_rect)

    quad = _quad_candidate(component, thresholds)
    if quad is not None:
        candidates.append(quad)

    fallback = AnchorCandidate(
        kind=AnchorKind.CUBIC_PATH,
        raster_error=0.0,
        node_count=max(4, min(component.area, len(component.boundary_pixels))),
        parameter_count=max(8, min(component.area * 2, len(component.boundary_pixels) * 2)),
    )
    candidates.append(fallback)
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
    if fit_residual > thresholds.circle_max_fit_residual:
        # Interior cut-out gaps add inner boundary pixels that wreck the fit;
        # retry against the outer boundary only.
        outer = _boundary_without_gap_edges(component)
        if outer is not None:
            center, radius, fit_residual = _fit_circle_from_samples(
                outer,
                fallback_center=component.centroid,
                fallback_radius=fallback_radius,
            )
            bounds_center, bounds_radius, bounds_residual = (
                _bounds_regularized_circle(component, samples=outer)
            )
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
    if aspect_error < 0.1:
        # Circle territory; let the circle candidate own near-round shapes.
        return None

    rx = (width - 1) / 2 + 0.5
    ry = (height - 1) / 2 + 0.5
    min_x, min_y, _, _ = component.bounds
    center = Point(min_x + (width - 1) / 2, min_y + (height - 1) / 2)
    expected_area = pi * rx * ry
    area_error = abs(component.area - expected_area) / expected_area
    if area_error > 0.12:
        return None
    fit_residual_px = _ellipse_boundary_residual(component, center, rx, ry)
    if fit_residual_px > 0.75:
        return None

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
) -> float:
    """Mean pixel distance from boundary pixels to the ellipse along rays.

    Normalized residuals over-penalize small or flat ellipses where half a
    pixel of quantization is a large fraction of the minor radius, so compare
    actual ray length against the ellipse ray length in pixels.
    """

    samples = tuple(component.boundary_pixels)
    if not samples:
        return 0.0
    total = 0.0
    for x, y in samples:
        dx = x - center.x
        dy = y - center.y
        actual = sqrt(dx * dx + dy * dy)
        if actual <= 0:
            continue
        denominator = sqrt((ry * dx) ** 2 + (rx * dy) ** 2)
        ray = rx * ry * actual / denominator if denominator > 0 else 0.0
        total += abs(actual - ray)
    return total / len(samples)


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
) -> tuple[tuple[int, int], ...] | None:
    """Boundary pixels that do not border an enclosed interior gap."""

    gaps = _interior_gap_components(component, min_area=1)
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
    return outer if len(outer) >= 8 else None


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
    if (
        length < thresholds.stroke_min_length
        or length / stroke_width < thresholds.stroke_min_length_width_ratio
    ):
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
    if (
        coverage >= 0.98
        and stroke_width > 8.0
        and _axis_aligned_filled_rect_component(component)
    ):
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
            # The residual already enters the ranking as raster_error; keep
            # the metric name free of the _error suffix to avoid counting it
            # twice in quality_metric_error.
            "smooth_path_fit_residual": residual,
            "smooth_path_bow_ratio": bow / max(chord, 1.0),
            "curvature_jitter_error": _curvature_jitter(control_points),
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
    # Sample away from the endpoints: the outermost columns only contain the
    # cap tip and would report a sliver width.
    for index in (round(last * 0.15), last // 2, round(last * 0.85)):
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
    dx = end.x - start.x
    dy = end.y - start.y
    denominator = hypot(dx, dy)
    if denominator == 0:
        return point.distance_to(start)
    return (
        abs(dy * point.x - dx * point.y + end.x * start.y - end.y * start.x)
        / denominator
    )


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

    candidate = AnchorCandidate(
        kind=AnchorKind.QUAD,
        raster_error=fill_error,
        node_count=4,
        parameter_count=8,
        quad=quad,
        metrics=_quad_subtype_metrics(quad),
    )
    return enrich_anchor_metrics(candidate)


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
        return None
    path_length = sum(a.distance_to(b) for a, b in zip(samples, samples[1:]))
    path_length = max(path_length, float(len(samples)))
    # Ink width (area / length) measures the actual slit thickness and also
    # rejects bulky holes like ring interiors.
    stroke_width = max(component.area / path_length, 1.0)
    if path_length < min_length or stroke_width > max_thickness:
        return None

    start = samples[0]
    end = samples[-1]
    control = max(
        samples,
        key=lambda point: _point_line_distance(point, start, end),
    )
    bow = _point_line_distance(control, start, end)
    bowed = bow >= max(1.0, stroke_width * 0.75)
    centerline = (start, control, end) if bowed else (start, end)
    return _cutout_centerline_candidate(centerline, stroke_width, color)



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
