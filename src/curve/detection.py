"""Primitive anchor detection from flat binary mask components."""

from __future__ import annotations

from math import hypot, pi, sqrt

from curve.anchors import (
    AnchorCandidate,
    AnchorKind,
    CircleAnchor,
    Point,
    QuadAnchor,
    StrokeAnchor,
    choose_best_anchor,
    enrich_anchor_metrics,
)
from curve.masks import BinaryMask, MaskComponent, connected_components


def detect_primitive_anchors(mask: BinaryMask, *, min_area: int = 8) -> tuple[AnchorCandidate, ...]:
    """Detect simple primitive anchors from a binary mask."""

    anchors: list[AnchorCandidate] = []
    for component in connected_components(mask, min_area=min_area):
        candidates = primitive_candidates_for_component(component)
        if candidates:
            anchors.append(choose_best_anchor(candidates))
    return tuple(anchors)


def primitive_candidates_for_component(
    component: MaskComponent,
) -> tuple[AnchorCandidate, ...]:
    """Generate plausible simple-shape candidates for one component."""

    candidates: list[AnchorCandidate] = []
    stroke_circle = _stroke_circle_candidate(component)
    if stroke_circle is not None:
        candidates.append(stroke_circle)

    circle = _circle_candidate(component)
    if circle is not None:
        candidates.append(circle)

    stroke = _stroke_candidate(component)
    if stroke is not None:
        candidates.append(stroke)

    quad = _quad_candidate(component)
    if quad is not None:
        candidates.append(quad)

    fallback = AnchorCandidate(
        kind=AnchorKind.CUBIC_PATH,
        raster_error=0.0,
        node_count=max(4, min(component.area, len(component.boundary_pixels))),
        parameter_count=max(8, min(component.area * 2, len(component.boundary_pixels) * 2)),
    )
    candidates.append(fallback)
    return tuple(candidates)


def _stroke_circle_candidate(component: MaskComponent) -> AnchorCandidate | None:
    width = component.width
    height = component.height
    diameter = max(width, height)
    if diameter < 6:
        return None

    aspect_error = abs(width - height) / diameter
    if aspect_error > 0.18:
        return None

    center = component.centroid
    distances = [Point(x, y).distance_to(center) for x, y in component.pixels]
    inner_radius = min(distances)
    outer_radius = max(distances)
    if outer_radius <= 0 or inner_radius / outer_radius < 0.45:
        return None

    stroke_width = outer_radius - inner_radius + 1
    if stroke_width <= 0:
        return None

    expected_area = pi * (outer_radius**2 - inner_radius**2)
    if expected_area <= 0:
        return None
    area_error = abs(component.area - expected_area) / expected_area
    if area_error > 0.45:
        return None

    radius = (inner_radius + outer_radius) / 2
    candidate = AnchorCandidate(
        kind=AnchorKind.STROKE_CIRCLE,
        raster_error=area_error + aspect_error,
        node_count=1,
        parameter_count=4,
        circle=CircleAnchor(
            center=center,
            radius=radius,
            samples=tuple(Point(x, y) for x, y in component.boundary_pixels),
        ),
        stroke=StrokeAnchor(centerline=(), width_samples=(stroke_width,)),
    )
    return enrich_anchor_metrics(candidate)


def _circle_candidate(component: MaskComponent) -> AnchorCandidate | None:
    width = component.width
    height = component.height
    diameter = max(width, height)
    if diameter < 3:
        return None

    aspect_error = abs(width - height) / diameter
    if aspect_error > 0.22:
        return None

    radius = sqrt(component.area / pi)
    expected_area = pi * (diameter / 2) ** 2
    area_error = abs(component.area - expected_area) / expected_area
    if area_error > 0.35:
        return None

    center = component.centroid
    samples = tuple(Point(x, y) for x, y in component.boundary_pixels)
    candidate = AnchorCandidate(
        kind=AnchorKind.CIRCLE,
        raster_error=area_error + aspect_error,
        node_count=1,
        parameter_count=3,
        circle=CircleAnchor(center=center, radius=radius, samples=samples),
    )
    return enrich_anchor_metrics(candidate)


def _stroke_candidate(component: MaskComponent) -> AnchorCandidate | None:
    axis = _principal_axis(component)
    if axis is None:
        return None

    center, direction, min_major, max_major, min_minor, max_minor = axis
    length = max_major - min_major + 1
    stroke_width = max(max_minor - min_minor + 1, 1.0)
    if length < 4 or length / stroke_width < 3.0:
        return None

    dx, dy = direction
    centerline = (
        Point(center.x + dx * min_major, center.y + dy * min_major),
        Point(center.x + dx * max_major, center.y + dy * max_major),
    )
    width_samples = (float(stroke_width),)

    coverage = min(component.area / (length * stroke_width), 1.0)
    candidate = AnchorCandidate(
        kind=AnchorKind.STROKE_POLYLINE,
        raster_error=abs(1.0 - coverage) * 0.1,
        node_count=2,
        parameter_count=5,
        stroke=StrokeAnchor(centerline=centerline, width_samples=width_samples),
    )
    return enrich_anchor_metrics(candidate)


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
    major_projections: list[float] = []
    minor_projections: list[float] = []
    for x, y in component.pixels:
        centered_x = x - center.x
        centered_y = y - center.y
        major_projections.append(centered_x * dx + centered_y * dy)
        minor_projections.append(centered_x * minor[0] + centered_y * minor[1])

    return (
        center,
        direction,
        min(major_projections),
        max(major_projections),
        min(minor_projections),
        max(minor_projections),
    )


def _quad_candidate(component: MaskComponent) -> AnchorCandidate | None:
    if component.width < 3 or component.height < 3:
        return None
    if component.area < component.width * component.height * 0.35:
        return None

    spans = component.row_spans()
    if len(spans) < 3:
        return None

    top_y, top_left, top_right = spans[0]
    bottom_y, bottom_left, bottom_right = spans[-1]
    quad = QuadAnchor(
        corners=(
            Point(top_left, top_y),
            Point(top_right, top_y),
            Point(bottom_right, bottom_y),
            Point(bottom_left, bottom_y),
        )
    )
    fill_error = _scanline_quad_fill_error(component, quad)
    if fill_error > 0.28:
        return None

    candidate = AnchorCandidate(
        kind=AnchorKind.QUAD,
        raster_error=fill_error,
        node_count=4,
        parameter_count=8,
        quad=quad,
    )
    return enrich_anchor_metrics(candidate)


def _scanline_quad_fill_error(component: MaskComponent, quad: QuadAnchor) -> float:
    corners = quad.corners
    top_y = corners[0].y
    bottom_y = corners[3].y
    if bottom_y <= top_y:
        return 1.0

    expected = 0
    missing = 0
    extra = 0
    row_lookup = {y: (left, right) for y, left, right in component.row_spans()}
    for y in range(int(top_y), int(bottom_y) + 1):
        t = (y - top_y) / (bottom_y - top_y)
        left = round(corners[0].x + (corners[3].x - corners[0].x) * t)
        right = round(corners[1].x + (corners[2].x - corners[1].x) * t)
        if left > right:
            left, right = right, left
        expected += right - left + 1
        actual = row_lookup.get(y)
        if actual is None:
            missing += right - left + 1
            continue
        actual_left, actual_right = actual
        missing += max(0, actual_left - left) + max(0, right - actual_right)
        extra += max(0, left - actual_left) + max(0, actual_right - right)

    if expected == 0:
        return 1.0
    return (missing + extra) / expected
