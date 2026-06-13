"""Primitive anchor model and semantic-first candidate ranking."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from math import cos, hypot, sin
from statistics import mean, pstdev
from typing import Iterable, Sequence


class AnchorKind(StrEnum):
    CIRCLE = "circle"
    STROKE_CIRCLE = "stroke_circle"
    ELLIPSE = "ellipse"
    STROKE_ELLIPSE = "stroke_ellipse"
    STROKE_PATH = "stroke_path"
    STROKE_POLYLINE = "stroke_polyline"
    RECT = "rect"
    ROUNDED_RECT = "rounded_rect"
    ARC = "arc"
    QUAD = "quad"
    PERSPECTIVE_GRID = "perspective_grid"
    CUBIC_PATH = "cubic_path"


@dataclass(frozen=True)
class ScoringConfig:
    raster_error_weight: float = 1.0
    quality_error_weight: float = 1.0
    node_complexity_weight: float = 0.015
    parameter_complexity_weight: float = 0.01
    simple_shape_bonus_weight: float = 1.0


@dataclass(frozen=True)
class Point:
    x: float
    y: float

    def distance_to(self, other: Point) -> float:
        return hypot(self.x - other.x, self.y - other.y)


@dataclass(frozen=True)
class CircleAnchor:
    center: Point
    radius: float
    samples: tuple[Point, ...] = ()


@dataclass(frozen=True)
class ArcAnchor:
    """Circular arc parameters for smooth SVG `A` command export."""

    center: Point
    radius: float
    theta_start: float
    theta_end: float
    sweep: bool
    large_arc: bool

    @property
    def start(self) -> Point:
        return self._point_at(self.theta_start)

    @property
    def end(self) -> Point:
        return self._point_at(self.theta_end)

    def _point_at(self, theta: float) -> Point:
        return Point(
            self.center.x + self.radius * cos(theta),
            self.center.y + self.radius * sin(theta),
        )


@dataclass(frozen=True)
class EllipseAnchor:
    """Axis-aligned ellipse; rotation stays zero until rotated fixtures land."""

    center: Point
    rx: float
    ry: float
    rotation: float = 0.0


@dataclass(frozen=True)
class StrokeAnchor:
    centerline: tuple[Point, ...]
    width_samples: tuple[float, ...]
    is_cutout: bool = False
    parallel_group_id: str | None = None
    cap_style: str = "round"
    join_style: str = "round"
    closed: bool = False


@dataclass(frozen=True)
class QuadAnchor:
    corners: tuple[Point, Point, Point, Point]


@dataclass(frozen=True)
class PathAnchor:
    """Controlled organic fallback outline with a bounded node count.

    When ``controls`` is present it holds one cubic Bezier control pair per
    segment (segment ``i`` runs from ``points[i]`` to ``points[(i+1) % n]``)
    produced by a least-squares fit; otherwise consumers derive a smooth
    closed Catmull-Rom curve through ``points``.
    """

    points: tuple[Point, ...]
    closed: bool = True
    fallback_reason: str = "organic_boundary_fit"
    controls: tuple[tuple[Point, Point], ...] | None = None
    # Enclosed holes too bulky to stay overlay slit strokes; each entry is a
    # fitted closed subpath (points plus control pairs) rendered even-odd.
    holes: tuple[tuple[tuple[Point, ...], tuple[tuple[Point, Point], ...]], ...] = ()


@dataclass(frozen=True)
class AnchorCandidate:
    kind: AnchorKind
    raster_error: float
    node_count: int
    parameter_count: int
    color: str | None = None
    circle: CircleAnchor | None = None
    stroke: StrokeAnchor | None = None
    quad: QuadAnchor | None = None
    arc: ArcAnchor | None = None
    ellipse: EllipseAnchor | None = None
    path: PathAnchor | None = None
    metrics: dict[str, float] = field(default_factory=dict)

    @property
    def is_simple_shape(self) -> bool:
        return self.kind in {
            AnchorKind.CIRCLE,
            AnchorKind.STROKE_CIRCLE,
            AnchorKind.ELLIPSE,
            AnchorKind.STROKE_ELLIPSE,
            AnchorKind.STROKE_PATH,
            AnchorKind.STROKE_POLYLINE,
            AnchorKind.RECT,
            AnchorKind.ROUNDED_RECT,
            AnchorKind.ARC,
            AnchorKind.QUAD,
            AnchorKind.PERSPECTIVE_GRID,
        }


def circle_roundness_error(circle: CircleAnchor) -> float:
    """Return normalized radius variance for sampled circle contours."""

    if circle.radius <= 0:
        return 1.0
    if not circle.samples:
        return 0.0
    distances = [circle.center.distance_to(point) for point in circle.samples]
    return pstdev(distances) / circle.radius


def line_smoothness_error(points: Sequence[Point]) -> float:
    """Measure centerline jitter as average turn-angle instability."""

    if len(points) < 3:
        return 0.0

    segment_angles: list[float] = []
    for a, b in zip(points, points[1:]):
        dx = b.x - a.x
        dy = b.y - a.y
        length = hypot(dx, dy)
        if length > 0:
            segment_angles.append(dy / length)

    if len(segment_angles) < 2:
        return 0.0

    return pstdev(segment_angles)


def stroke_width_variance(width_samples: Sequence[float]) -> float:
    """Return normalized stroke width variance."""

    if not width_samples:
        return 0.0
    avg = mean(width_samples)
    if avg <= 0:
        return 1.0
    return pstdev(width_samples) / avg


def parallel_spacing_error(centerlines: Sequence[Sequence[Point]]) -> float:
    """Estimate uneven spacing for roughly parallel line groups."""

    if len(centerlines) < 2:
        return 0.0

    midpoints = [_polyline_midpoint(line) for line in centerlines if line]
    if len(midpoints) < 2:
        return 0.0

    spacings = [
        midpoints[index].distance_to(midpoints[index + 1])
        for index in range(len(midpoints) - 1)
    ]
    avg = mean(spacings)
    if avg <= 0:
        return 1.0
    return pstdev(spacings) / avg


def cutout_anchor_error(stroke: StrokeAnchor) -> float:
    """Apply stroke quality rules to cut-out-looking overlay strokes."""

    if not stroke.is_cutout:
        return 0.0
    return (
        line_smoothness_error(stroke.centerline)
        + stroke_width_variance(stroke.width_samples)
    ) / 2


def quad_edge_straightness_error(quad: QuadAnchor) -> float:
    """Closed quads have straight parametric edges by construction."""

    return 0.0 if _quad_area(quad.corners) > 0 else 1.0


def quad_corner_consistency_error(quad: QuadAnchor) -> float:
    """Penalize degenerate or extremely uneven quadrilateral corners."""

    corners = quad.corners
    edges = [
        corners[index].distance_to(corners[(index + 1) % 4])
        for index in range(4)
    ]
    avg = mean(edges)
    if avg <= 0:
        return 1.0
    return min(pstdev(edges) / avg, 1.0)


def perspective_grid_consistency_error(quads: Sequence[QuadAnchor]) -> float:
    """Estimate consistency for a family of perspective tiles."""

    if len(quads) < 2:
        return 0.0

    top_widths = [
        quad.corners[0].distance_to(quad.corners[1])
        for quad in quads
    ]
    bottom_widths = [
        quad.corners[3].distance_to(quad.corners[2])
        for quad in quads
    ]
    ratios = [
        top / bottom
        for top, bottom in zip(top_widths, bottom_widths)
        if bottom > 0
    ]
    if len(ratios) < 2:
        return 0.0
    avg = mean(ratios)
    if avg <= 0:
        return 1.0
    return pstdev(ratios) / avg


def simple_shape_priority_bonus(candidate: AnchorCandidate) -> float:
    """Reward simple editable primitives over generic path substitutes."""

    if not candidate.is_simple_shape:
        return 0.0
    if candidate.kind in {AnchorKind.CIRCLE, AnchorKind.STROKE_CIRCLE}:
        return 0.35
    if candidate.kind in {
        AnchorKind.ELLIPSE,
        AnchorKind.STROKE_ELLIPSE,
        AnchorKind.STROKE_PATH,
        AnchorKind.STROKE_POLYLINE,
        AnchorKind.RECT,
        AnchorKind.ROUNDED_RECT,
        AnchorKind.ARC,
        AnchorKind.QUAD,
        AnchorKind.PERSPECTIVE_GRID,
    }:
        return 0.25
    return 0.15


def semantic_anchor_score(
    candidate: AnchorCandidate,
    config: ScoringConfig | None = None,
) -> float:
    """Lower is better; semantic quality dominates small raster differences."""

    config = config or ScoringConfig()
    quality_error = quality_metric_error(candidate.metrics)
    complexity = (
        config.node_complexity_weight * candidate.node_count
        + config.parameter_complexity_weight * candidate.parameter_count
    )
    bonus = simple_shape_priority_bonus(candidate)
    return (
        config.raster_error_weight * candidate.raster_error
        + config.quality_error_weight * quality_error
        + complexity
        - config.simple_shape_bonus_weight * bonus
    )


def quality_metric_error(metrics: dict[str, float]) -> float:
    """Return the score contribution from metrics that represent errors."""

    return sum(
        value
        for name, value in metrics.items()
        if _is_quality_error_metric(name)
    )


def _is_quality_error_metric(name: str) -> bool:
    return (
        name.endswith("_error")
        or name in {"stroke_width_variance", "classifier_prior_error"}
    )


def choose_best_anchor(
    candidates: Iterable[AnchorCandidate],
    *,
    scoring: ScoringConfig | None = None,
) -> AnchorCandidate:
    """Choose the semantic-first anchor candidate."""

    candidates = list(candidates)
    if not candidates:
        msg = "choose_best_anchor requires at least one candidate"
        raise ValueError(msg)
    return min(
        candidates,
        key=lambda candidate: semantic_anchor_score(candidate, scoring),
    )


def enrich_anchor_metrics(candidate: AnchorCandidate) -> AnchorCandidate:
    """Return a candidate with anchor metrics derived from attached geometry."""

    metrics = dict(candidate.metrics)
    if candidate.circle is not None:
        metrics["circle_roundness_error"] = circle_roundness_error(candidate.circle)
    if candidate.stroke is not None:
        metrics["line_smoothness_error"] = line_smoothness_error(
            candidate.stroke.centerline
        )
        metrics["stroke_width_variance"] = stroke_width_variance(
            candidate.stroke.width_samples
        )
        metrics["cutout_anchor_error"] = cutout_anchor_error(candidate.stroke)
    if candidate.quad is not None:
        metrics["quad_edge_straightness_error"] = quad_edge_straightness_error(
            candidate.quad
        )
        metrics["quad_corner_consistency_error"] = quad_corner_consistency_error(
            candidate.quad
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


def _polyline_midpoint(points: Sequence[Point]) -> Point:
    xs = [point.x for point in points]
    ys = [point.y for point in points]
    return Point(mean(xs), mean(ys))


def _quad_area(corners: tuple[Point, Point, Point, Point]) -> float:
    area = 0.0
    for index, point in enumerate(corners):
        next_point = corners[(index + 1) % 4]
        area += point.x * next_point.y
        area -= next_point.x * point.y
    return abs(area) / 2
