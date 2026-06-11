"""Primitive anchor detection from flat binary mask components."""

from __future__ import annotations

from math import hypot, pi, sqrt

from curve.anchors import (
    AnchorCandidate,
    AnchorKind,
    CircleAnchor,
    Point,
    QuadAnchor,
    ScoringConfig,
    StrokeAnchor,
    choose_best_anchor,
    enrich_anchor_metrics,
)
from curve.classifier import classifier_prior_error
from curve.masks import BinaryMask, MaskComponent, connected_components


def detect_primitive_anchors(
    mask: BinaryMask,
    *,
    min_area: int = 8,
    classifier_model: dict[str, tuple[float, ...]] | None = None,
    scoring: ScoringConfig | None = None,
) -> tuple[AnchorCandidate, ...]:
    """Detect simple primitive anchors from a binary mask."""

    anchors: list[AnchorCandidate] = []
    for component in connected_components(mask, min_area=min_area):
        candidates = primitive_candidates_for_component(
            component,
            classifier_model=classifier_model,
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
            _horizontal_cutout_strokes(
                component,
                min_length=min_length,
                max_thickness=max_thickness,
                color=color,
            )
        )
        cutouts.extend(
            _vertical_cutout_strokes(
                component,
                min_length=min_length,
                max_thickness=max_thickness,
                color=color,
            )
        )
    return tuple(cutouts)


def primitive_candidates_for_component(
    component: MaskComponent,
    *,
    classifier_model: dict[str, tuple[float, ...]] | None = None,
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

    rect = _rect_candidate(component)
    if rect is not None:
        candidates.append(rect)

    rounded_rect = _rounded_rect_candidate(component)
    if rounded_rect is not None:
        candidates.append(rounded_rect)

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
    if classifier_model is not None:
        return tuple(_with_classifier_prior(candidate, classifier_model) for candidate in candidates)
    return tuple(candidates)


def _with_classifier_prior(
    candidate: AnchorCandidate,
    classifier_model: dict[str, tuple[float, ...]],
) -> AnchorCandidate:
    metrics = dict(candidate.metrics)
    metrics["classifier_prior_error"] = classifier_prior_error(
        classifier_model,
        candidate,
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
        metrics=metrics,
    )


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
    coverage = min(component.area / (length * stroke_width), 1.0)
    width_samples = (float(stroke_width),)
    cap_style = "butt" if coverage >= 0.85 else "round"
    candidate = AnchorCandidate(
        kind=AnchorKind.STROKE_POLYLINE,
        raster_error=abs(1.0 - coverage) * 0.1,
        node_count=2,
        parameter_count=5,
        stroke=StrokeAnchor(
            centerline=centerline,
            width_samples=width_samples,
            cap_style=cap_style,
            join_style="round",
        ),
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


def _rect_candidate(component: MaskComponent) -> AnchorCandidate | None:
    if component.width < 3 or component.height < 3:
        return None

    expected_area = component.width * component.height
    fill_error = 1.0 - component.area / expected_area
    if fill_error > 0.08:
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


def _rounded_rect_candidate(component: MaskComponent) -> AnchorCandidate | None:
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
    if abs(widths[0] - widths[-1]) > 1:
        return None

    expected_area = component.width * component.height
    fill_error = 1.0 - component.area / expected_area
    if fill_error > 0.30:
        return None

    min_x, min_y, max_x, max_y = component.bounds
    corner_radius = max(1.0, (max_width - min(widths[0], widths[-1])) / 2)
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


def _horizontal_cutout_strokes(
    component: MaskComponent,
    *,
    min_length: int,
    max_thickness: int,
    color: str,
) -> tuple[AnchorCandidate, ...]:
    min_x, min_y, max_x, max_y = component.bounds
    runs: list[tuple[int, int, int]] = []
    for y in range(min_y + 1, max_y):
        x = min_x + 1
        while x < max_x:
            if (x, y) in component.pixels:
                x += 1
                continue
            start = x
            while x < max_x and (x, y) not in component.pixels:
                x += 1
            end = x - 1
            if (
                end - start + 1 >= min_length
                and (start - 1, y) in component.pixels
                and (end + 1, y) in component.pixels
                and _has_component_neighbor_above_and_below(component, start, end, y)
            ):
                runs.append((y, start, end))
    return _group_horizontal_runs(
        runs,
        min_length=min_length,
        max_thickness=max_thickness,
        color=color,
    )


def _vertical_cutout_strokes(
    component: MaskComponent,
    *,
    min_length: int,
    max_thickness: int,
    color: str,
) -> tuple[AnchorCandidate, ...]:
    min_x, min_y, max_x, max_y = component.bounds
    runs: list[tuple[int, int, int]] = []
    for x in range(min_x + 1, max_x):
        y = min_y + 1
        while y < max_y:
            if (x, y) in component.pixels:
                y += 1
                continue
            start = y
            while y < max_y and (x, y) not in component.pixels:
                y += 1
            end = y - 1
            if (
                end - start + 1 >= min_length
                and (x, start - 1) in component.pixels
                and (x, end + 1) in component.pixels
                and _has_component_neighbor_left_and_right(component, x, start, end)
            ):
                runs.append((x, start, end))
    return _group_vertical_runs(
        runs,
        min_length=min_length,
        max_thickness=max_thickness,
        color=color,
    )


def _group_horizontal_runs(
    runs: list[tuple[int, int, int]],
    *,
    min_length: int,
    max_thickness: int,
    color: str,
) -> tuple[AnchorCandidate, ...]:
    grouped: list[list[tuple[int, int, int]]] = []
    for run in runs:
        y, start, end = run
        if grouped:
            previous_y, previous_start, previous_end = grouped[-1][-1]
            if y == previous_y + 1 and _overlap_length(start, end, previous_start, previous_end) >= min_length:
                grouped[-1].append(run)
                continue
        grouped.append([run])
    candidates: list[AnchorCandidate] = []
    for group in grouped:
        thickness = len(group)
        start = round(sum(run[1] for run in group) / thickness)
        end = round(sum(run[2] for run in group) / thickness)
        length = end - start + 1
        if thickness > max_thickness or length < min_length or thickness / length > 0.35:
            continue
        y = sum(run[0] for run in group) / thickness
        candidates.append(_cutout_candidate(Point(start, y), Point(end, y), thickness, color))
    return tuple(candidates)


def _group_vertical_runs(
    runs: list[tuple[int, int, int]],
    *,
    min_length: int,
    max_thickness: int,
    color: str,
) -> tuple[AnchorCandidate, ...]:
    grouped: list[list[tuple[int, int, int]]] = []
    for run in runs:
        x, start, end = run
        if grouped:
            previous_x, previous_start, previous_end = grouped[-1][-1]
            if x == previous_x + 1 and _overlap_length(start, end, previous_start, previous_end) >= min_length:
                grouped[-1].append(run)
                continue
        grouped.append([run])
    candidates: list[AnchorCandidate] = []
    for group in grouped:
        thickness = len(group)
        start = round(sum(run[1] for run in group) / thickness)
        end = round(sum(run[2] for run in group) / thickness)
        length = end - start + 1
        if thickness > max_thickness or length < min_length or thickness / length > 0.35:
            continue
        x = sum(run[0] for run in group) / thickness
        candidates.append(_cutout_candidate(Point(x, start), Point(x, end), thickness, color))
    return tuple(candidates)


def _cutout_candidate(start: Point, end: Point, width: float, color: str) -> AnchorCandidate:
    candidate = AnchorCandidate(
        kind=AnchorKind.STROKE_POLYLINE,
        raster_error=0.0,
        node_count=2,
        parameter_count=5,
        color=color,
        stroke=StrokeAnchor(
            centerline=(start, end),
            width_samples=(float(width),),
            is_cutout=True,
        ),
    )
    return enrich_anchor_metrics(candidate)


def _has_component_neighbor_above_and_below(
    component: MaskComponent,
    start: int,
    end: int,
    y: int,
) -> bool:
    mid = (start + end) // 2
    return (mid, y - 1) in component.pixels and (mid, y + 1) in component.pixels


def _has_component_neighbor_left_and_right(
    component: MaskComponent,
    x: int,
    start: int,
    end: int,
) -> bool:
    mid = (start + end) // 2
    return (x - 1, mid) in component.pixels and (x + 1, mid) in component.pixels


def _overlap_length(
    first_start: int,
    first_end: int,
    second_start: int,
    second_end: int,
) -> int:
    return max(0, min(first_end, second_end) - max(first_start, second_start) + 1)
