"""Synthetic flat-color scene generation for training and evaluation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from math import cos, radians, sin
from pathlib import Path
from random import Random

from PIL import Image, ImageDraw

from morphea.anchors import (
    AnchorCandidate,
    AnchorKind,
    CircleAnchor,
    Point,
    QuadAnchor,
    StrokeAnchor,
)
from morphea.scene import Scene


PALETTE = ("#003366", "#c99700", "#dd2222", "#e7d8ca")


@dataclass(frozen=True)
class SyntheticSample:
    scene: Scene
    image: Image.Image
    seed: int
    difficulty: str = "basic"

    def write(self, output_dir: str | Path, name: str) -> tuple[Path, Path]:
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        image_path = output / f"{name}.png"
        manifest_path = output / f"{name}.json"
        self.image.save(image_path)
        manifest = self.scene.to_manifest()
        manifest["seed"] = self.seed
        manifest["difficulty"] = self.difficulty
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return image_path, manifest_path


def generate_synthetic_sample(
    *,
    seed: int,
    width: int = 96,
    height: int = 96,
    difficulty: str = "basic",
) -> SyntheticSample:
    if difficulty not in {"basic", "dense", "grid", "logo"}:
        msg = f"unsupported synthetic difficulty: {difficulty}"
        raise ValueError(msg)

    rng = Random(seed)
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    anchors: list[AnchorCandidate] = []

    anchors.append(_draw_circle(draw, rng, width, height))
    anchors.append(_draw_dot(draw, rng, width, height))
    anchors.append(_draw_stroke_circle(draw, rng, width, height))
    anchors.append(_draw_stroke(draw, rng, width, height))
    anchors.append(_draw_curved_stroke(draw, rng, width, height))
    anchors.append(_draw_arc(draw, rng, width, height))
    anchors.append(_draw_rect(draw, rng, width, height))
    anchors.append(_draw_rounded_rect(draw, rng, width, height))
    anchors.append(_draw_quad(draw, rng, width, height))
    anchors.append(_draw_parallelogram(draw, rng, width, height))
    anchors.extend(_draw_tile_grid(draw, rng, width, height))
    anchors.append(_draw_cutout_stroke(draw, width, height))
    if difficulty == "dense":
        anchors.extend(_draw_parallel_stroke_group(draw, rng, width, height))
    if difficulty == "grid":
        anchors.extend(_draw_large_perspective_tile_grid(draw, rng, width, height))
    if difficulty == "logo":
        anchors.extend(_draw_logo_composition(draw, rng, width, height))

    return SyntheticSample(
        scene=Scene(width=width, height=height, anchors=tuple(anchors)),
        image=image,
        seed=seed,
        difficulty=difficulty,
    )


def _draw_circle(
    draw: ImageDraw.ImageDraw,
    rng: Random,
    width: int,
    height: int,
) -> AnchorCandidate:
    radius = rng.randint(5, 10)
    center = Point(rng.randint(radius + 2, width // 2), rng.randint(radius + 2, height // 2))
    color = rng.choice(PALETTE)
    draw.ellipse(
        (
            center.x - radius,
            center.y - radius,
            center.x + radius,
            center.y + radius,
        ),
        fill=color,
    )
    return AnchorCandidate(
        kind=AnchorKind.CIRCLE,
        raster_error=0.0,
        node_count=1,
        parameter_count=3,
        color=color,
        circle=CircleAnchor(center=center, radius=radius),
    )


def _draw_dot(
    draw: ImageDraw.ImageDraw,
    rng: Random,
    width: int,
    height: int,
) -> AnchorCandidate:
    radius = rng.randint(2, 4)
    center = Point(
        _clamp(width * 0.50 + rng.randint(-3, 3), radius + 1, width - radius - 1),
        _clamp(height * 0.38 + rng.randint(-3, 3), radius + 1, height - radius - 1),
    )
    color = rng.choice(PALETTE)
    draw.ellipse(
        (
            center.x - radius,
            center.y - radius,
            center.x + radius,
            center.y + radius,
        ),
        fill=color,
    )
    return AnchorCandidate(
        kind=AnchorKind.CIRCLE,
        raster_error=0.0,
        node_count=1,
        parameter_count=3,
        color=color,
        circle=CircleAnchor(center=center, radius=radius),
        metrics={"dot_radius": float(radius)},
    )


def _draw_stroke_circle(
    draw: ImageDraw.ImageDraw,
    rng: Random,
    width: int,
    height: int,
) -> AnchorCandidate:
    radius = rng.randint(10, 16)
    stroke_width = rng.randint(2, 4)
    center = Point(
        rng.randint(width // 2, width - radius - 3),
        rng.randint(radius + 3, height // 2),
    )
    color = rng.choice(PALETTE)
    draw.ellipse(
        (
            center.x - radius,
            center.y - radius,
            center.x + radius,
            center.y + radius,
        ),
        outline=color,
        width=stroke_width,
    )
    return AnchorCandidate(
        kind=AnchorKind.STROKE_CIRCLE,
        raster_error=0.0,
        node_count=1,
        parameter_count=4,
        color=color,
        circle=CircleAnchor(center=center, radius=radius),
        stroke=StrokeAnchor(centerline=(), width_samples=(float(stroke_width),)),
    )


def _draw_stroke(
    draw: ImageDraw.ImageDraw,
    rng: Random,
    width: int,
    height: int,
) -> AnchorCandidate:
    start = Point(rng.randint(8, width // 3), rng.randint(height // 2, height - 10))
    end = Point(rng.randint(width // 2, width - 8), rng.randint(height // 2, height - 10))
    stroke_width = rng.randint(2, 4)
    color = rng.choice(PALETTE)
    draw.line((start.x, start.y, end.x, end.y), fill=color, width=stroke_width)
    return AnchorCandidate(
        kind=AnchorKind.STROKE_POLYLINE,
        raster_error=0.0,
        node_count=2,
        parameter_count=5,
        color=color,
        stroke=StrokeAnchor(
            centerline=(start, end),
            width_samples=(float(stroke_width),),
        ),
    )


def _draw_curved_stroke(
    draw: ImageDraw.ImageDraw,
    rng: Random,
    width: int,
    height: int,
) -> AnchorCandidate:
    start = Point(width * 0.09, height * 0.72)
    control = Point(width * 0.24, height * (0.60 + rng.random() * 0.08))
    end = Point(width * 0.43, height * 0.76)
    points = tuple(
        _quadratic_bezier(start, control, end, index / 5)
        for index in range(6)
    )
    stroke_width = rng.randint(2, 4)
    color = rng.choice(PALETTE)
    draw.line(_point_xy(points), fill=color, width=stroke_width, joint="curve")
    return AnchorCandidate(
        kind=AnchorKind.STROKE_PATH,
        raster_error=0.0,
        node_count=len(points),
        parameter_count=8,
        color=color,
        stroke=StrokeAnchor(
            centerline=points,
            width_samples=(float(stroke_width),) * len(points),
            cap_style="round",
            join_style="round",
        ),
    )


def _draw_arc(
    draw: ImageDraw.ImageDraw,
    rng: Random,
    width: int,
    height: int,
) -> AnchorCandidate:
    stroke_width = rng.randint(2, 4)
    color = rng.choice(PALETTE)
    bbox = (
        width * 0.58,
        height * 0.16,
        width * 0.88,
        height * 0.45,
    )
    start_angle = 205
    end_angle = 330
    draw.arc(bbox, start=start_angle, end=end_angle, fill=color, width=stroke_width)
    cx = (bbox[0] + bbox[2]) / 2
    cy = (bbox[1] + bbox[3]) / 2
    rx = (bbox[2] - bbox[0]) / 2
    ry = (bbox[3] - bbox[1]) / 2
    points = tuple(
        Point(
            cx + rx * cos(radians(start_angle + (end_angle - start_angle) * step / 5)),
            cy + ry * sin(radians(start_angle + (end_angle - start_angle) * step / 5)),
        )
        for step in range(6)
    )
    return AnchorCandidate(
        kind=AnchorKind.ARC,
        raster_error=0.0,
        node_count=len(points),
        parameter_count=6,
        color=color,
        stroke=StrokeAnchor(
            centerline=points,
            width_samples=(float(stroke_width),) * len(points),
            cap_style="round",
            join_style="round",
        ),
    )


def _draw_rect(
    draw: ImageDraw.ImageDraw,
    rng: Random,
    width: int,
    height: int,
) -> AnchorCandidate:
    x0 = width * 0.56
    y0 = height * 0.50
    x1 = width * 0.82
    y1 = height * 0.62
    color = rng.choice(PALETTE)
    draw.rectangle((x0, y0, x1, y1), fill=color)
    corners = _axis_aligned_corners(x0, y0, x1, y1)
    return AnchorCandidate(
        kind=AnchorKind.RECT,
        raster_error=0.0,
        node_count=4,
        parameter_count=4,
        color=color,
        quad=QuadAnchor(corners=corners),
    )


def _draw_rounded_rect(
    draw: ImageDraw.ImageDraw,
    rng: Random,
    width: int,
    height: int,
) -> AnchorCandidate:
    x0 = width * 0.66
    y0 = height * 0.66
    x1 = width * 0.93
    y1 = height * 0.82
    radius = max(2.0, min(width, height) * 0.045)
    color = rng.choice(PALETTE)
    draw.rounded_rectangle((x0, y0, x1, y1), radius=radius, fill=color)
    corners = _axis_aligned_corners(x0, y0, x1, y1)
    return AnchorCandidate(
        kind=AnchorKind.ROUNDED_RECT,
        raster_error=0.0,
        node_count=4,
        parameter_count=5,
        color=color,
        quad=QuadAnchor(corners=corners),
        metrics={"corner_radius": float(radius)},
    )


def _draw_quad(
    draw: ImageDraw.ImageDraw,
    rng: Random,
    width: int,
    height: int,
) -> AnchorCandidate:
    top_y = rng.randint(height // 2, height - 28)
    bottom_y = top_y + rng.randint(12, 22)
    left = rng.randint(6, width // 3)
    top_width = rng.randint(12, 22)
    bottom_width = top_width + rng.randint(4, 12)
    skew = rng.randint(-5, 5)
    corners = (
        Point(left, top_y),
        Point(left + top_width, top_y),
        Point(left + top_width + skew + bottom_width - top_width, bottom_y),
        Point(left + skew - (bottom_width - top_width) // 2, bottom_y),
    )
    color = rng.choice(PALETTE)
    draw.polygon([(point.x, point.y) for point in corners], fill=color)
    return AnchorCandidate(
        kind=AnchorKind.QUAD,
        raster_error=0.0,
        node_count=4,
        parameter_count=8,
        color=color,
        quad=QuadAnchor(corners=corners),
        metrics={"quad_subtype_code": 1.0},
    )


def _draw_parallelogram(
    draw: ImageDraw.ImageDraw,
    rng: Random,
    width: int,
    height: int,
) -> AnchorCandidate:
    x0 = width * 0.08
    y0 = height * 0.45
    box_width = width * 0.18
    box_height = height * 0.12
    skew = width * 0.06
    corners = (
        Point(x0 + skew, y0),
        Point(x0 + skew + box_width, y0),
        Point(x0 + box_width, y0 + box_height),
        Point(x0, y0 + box_height),
    )
    color = rng.choice(PALETTE)
    draw.polygon(_point_xy(corners), fill=color)
    return AnchorCandidate(
        kind=AnchorKind.QUAD,
        raster_error=0.0,
        node_count=4,
        parameter_count=8,
        color=color,
        quad=QuadAnchor(corners=corners),
        metrics={"quad_subtype_code": 2.0},
    )


def _draw_tile_grid(
    draw: ImageDraw.ImageDraw,
    rng: Random,
    width: int,
    height: int,
) -> tuple[AnchorCandidate, ...]:
    left_top = Point(width * 0.35, height * 0.67)
    right_top = Point(width * 0.65, height * 0.67)
    left_bottom = Point(width * 0.18, height * 0.93)
    right_bottom = Point(width * 0.82, height * 0.93)
    rows = (
        (
            _lerp_point(left_top, left_bottom, 0.0),
            _lerp_point(right_top, right_bottom, 0.0),
        ),
        (
            _lerp_point(left_top, left_bottom, 0.48),
            _lerp_point(right_top, right_bottom, 0.48),
        ),
        (
            _lerp_point(left_top, left_bottom, 1.0),
            _lerp_point(right_top, right_bottom, 1.0),
        ),
    )
    anchors: list[AnchorCandidate] = []
    for row_index in range(2):
        for col_index in range(2):
            left_a, right_a = rows[row_index]
            left_b, right_b = rows[row_index + 1]
            col_a = col_index / 2
            col_b = (col_index + 1) / 2
            corners = (
                _lerp_point(left_a, right_a, col_a),
                _lerp_point(left_a, right_a, col_b),
                _lerp_point(left_b, right_b, col_b),
                _lerp_point(left_b, right_b, col_a),
            )
            color = PALETTE[
                (row_index * 2 + col_index + rng.randint(0, 3)) % len(PALETTE)
            ]
            draw.polygon(_point_xy(corners), fill=color, outline="white")
            anchors.append(
                AnchorCandidate(
                    kind=AnchorKind.QUAD,
                    raster_error=0.0,
                    node_count=4,
                    parameter_count=8,
                    color=color,
                    quad=QuadAnchor(corners=corners),
                    metrics={"grid_row": float(row_index), "grid_col": float(col_index)},
                )
            )
    return tuple(anchors)


def _draw_large_perspective_tile_grid(
    draw: ImageDraw.ImageDraw,
    rng: Random,
    width: int,
    height: int,
) -> tuple[AnchorCandidate, ...]:
    left_top = Point(width * 0.16, height * 0.42)
    right_top = Point(width * 0.84, height * 0.42)
    left_bottom = Point(width * 0.03, height * 0.96)
    right_bottom = Point(width * 0.97, height * 0.96)
    row_count = 3
    column_count = 4
    row_guides = tuple(
        (
            _lerp_point(left_top, left_bottom, row_index / row_count),
            _lerp_point(right_top, right_bottom, row_index / row_count),
        )
        for row_index in range(row_count + 1)
    )
    anchors: list[AnchorCandidate] = []
    for row_index in range(row_count):
        for column_index in range(column_count):
            left_a, right_a = row_guides[row_index]
            left_b, right_b = row_guides[row_index + 1]
            col_a = column_index / column_count
            col_b = (column_index + 1) / column_count
            corners = (
                _lerp_point(left_a, right_a, col_a),
                _lerp_point(left_a, right_a, col_b),
                _lerp_point(left_b, right_b, col_b),
                _lerp_point(left_b, right_b, col_a),
            )
            color = PALETTE[
                (row_index + column_index + rng.randint(0, 2)) % len(PALETTE)
            ]
            draw.polygon(_point_xy(corners), fill=color, outline="white")
            anchors.append(
                AnchorCandidate(
                    kind=AnchorKind.QUAD,
                    raster_error=0.0,
                    node_count=4,
                    parameter_count=8,
                    color=color,
                    quad=QuadAnchor(corners=corners),
                    metrics={
                        "grid_row": float(row_index),
                        "grid_col": float(column_index),
                        "synthetic_grid_family": 1.0,
                        "synthetic_grid_row_count": float(row_count),
                        "synthetic_grid_column_count": float(column_count),
                    },
                )
            )
    return tuple(anchors)


def _draw_cutout_stroke(
    draw: ImageDraw.ImageDraw,
    width: int,
    height: int,
) -> AnchorCandidate:
    start = Point(width * 0.68, height * 0.56)
    end = Point(width * 0.90, height * 0.70)
    stroke_width = max(2, int(min(width, height) * 0.04))
    draw.line((start.x, start.y, end.x, end.y), fill="white", width=stroke_width)
    return AnchorCandidate(
        kind=AnchorKind.STROKE_POLYLINE,
        raster_error=0.0,
        node_count=2,
        parameter_count=5,
        color="#ffffff",
        stroke=StrokeAnchor(
            centerline=(start, end),
            width_samples=(float(stroke_width),),
            is_cutout=True,
            cap_style="butt",
            join_style="round",
        ),
        metrics={"cutout_anchor_error": 0.0},
    )


def _draw_parallel_stroke_group(
    draw: ImageDraw.ImageDraw,
    rng: Random,
    width: int,
    height: int,
) -> tuple[AnchorCandidate, ...]:
    stroke_width = rng.randint(2, 3)
    color = rng.choice(PALETTE)
    group_id = "synthetic-parallel-0"
    anchors: list[AnchorCandidate] = []
    for index in range(3):
        y = height * (0.12 + index * 0.055)
        start = Point(width * 0.10, y)
        end = Point(width * 0.44, y + height * 0.025)
        draw.line((start.x, start.y, end.x, end.y), fill=color, width=stroke_width)
        anchors.append(
            AnchorCandidate(
                kind=AnchorKind.STROKE_POLYLINE,
                raster_error=0.0,
                node_count=2,
                parameter_count=5,
                color=color,
                stroke=StrokeAnchor(
                    centerline=(start, end),
                    width_samples=(float(stroke_width),),
                    parallel_group_id=group_id,
                    cap_style="round",
                    join_style="round",
                ),
                metrics={"synthetic_dense_parallel_index": float(index)},
            )
        )
    return tuple(anchors)


def _draw_logo_composition(
    draw: ImageDraw.ImageDraw,
    rng: Random,
    width: int,
    height: int,
) -> tuple[AnchorCandidate, ...]:
    brand_color = rng.choice(("#003366", "#c99700", "#dd2222"))
    accent_color = rng.choice([color for color in PALETTE if color != brand_color])
    center = Point(width * 0.22, height * 0.22)
    ring_radius = max(7.0, min(width, height) * 0.095)
    ring_width = max(2, int(min(width, height) * 0.035))
    draw.ellipse(
        (
            center.x - ring_radius,
            center.y - ring_radius,
            center.x + ring_radius,
            center.y + ring_radius,
        ),
        outline=brand_color,
        width=ring_width,
    )
    dot_radius = max(2.0, ring_radius * 0.28)
    dot_center = Point(center.x + ring_radius * 0.62, center.y - ring_radius * 0.58)
    draw.ellipse(
        (
            dot_center.x - dot_radius,
            dot_center.y - dot_radius,
            dot_center.x + dot_radius,
            dot_center.y + dot_radius,
        ),
        fill=accent_color,
    )
    stroke_start = Point(center.x - ring_radius * 0.72, center.y + ring_radius * 0.72)
    stroke_end = Point(center.x + ring_radius * 1.25, center.y - ring_radius * 0.85)
    draw.line(
        (stroke_start.x, stroke_start.y, stroke_end.x, stroke_end.y),
        fill=accent_color,
        width=max(2, ring_width - 1),
    )
    word_x0 = width * 0.38
    word_y0 = height * 0.16
    word_x1 = width * 0.84
    word_y1 = height * 0.29
    word_radius = max(2.0, min(width, height) * 0.025)
    draw.rounded_rectangle(
        (word_x0, word_y0, word_x1, word_y1),
        radius=word_radius,
        fill=brand_color,
    )
    return (
        AnchorCandidate(
            kind=AnchorKind.STROKE_CIRCLE,
            raster_error=0.0,
            node_count=1,
            parameter_count=4,
            color=brand_color,
            circle=CircleAnchor(center=center, radius=ring_radius),
            stroke=StrokeAnchor(
                centerline=(),
                width_samples=(float(ring_width),),
                cap_style="round",
                join_style="round",
            ),
            metrics={"logo_element": "mark_ring"},
        ),
        AnchorCandidate(
            kind=AnchorKind.CIRCLE,
            raster_error=0.0,
            node_count=1,
            parameter_count=3,
            color=accent_color,
            circle=CircleAnchor(center=dot_center, radius=dot_radius),
            metrics={"logo_element": "accent_dot"},
        ),
        AnchorCandidate(
            kind=AnchorKind.STROKE_POLYLINE,
            raster_error=0.0,
            node_count=2,
            parameter_count=5,
            color=accent_color,
            stroke=StrokeAnchor(
                centerline=(stroke_start, stroke_end),
                width_samples=(float(max(2, ring_width - 1)),),
                cap_style="round",
                join_style="round",
            ),
            metrics={"logo_element": "diagonal_stroke"},
        ),
        AnchorCandidate(
            kind=AnchorKind.ROUNDED_RECT,
            raster_error=0.0,
            node_count=4,
            parameter_count=5,
            color=brand_color,
            quad=QuadAnchor(
                corners=_axis_aligned_corners(word_x0, word_y0, word_x1, word_y1)
            ),
            metrics={
                "corner_radius": float(word_radius),
                "logo_element": "wordmark_bar",
            },
        ),
    )


def _quadratic_bezier(start: Point, control: Point, end: Point, t: float) -> Point:
    inverse = 1 - t
    return Point(
        inverse * inverse * start.x + 2 * inverse * t * control.x + t * t * end.x,
        inverse * inverse * start.y + 2 * inverse * t * control.y + t * t * end.y,
    )


def _axis_aligned_corners(
    x0: float,
    y0: float,
    x1: float,
    y1: float,
) -> tuple[Point, Point, Point, Point]:
    return (
        Point(x0, y0),
        Point(x1, y0),
        Point(x1, y1),
        Point(x0, y1),
    )


def _lerp_point(start: Point, end: Point, amount: float) -> Point:
    return Point(
        start.x + (end.x - start.x) * amount,
        start.y + (end.y - start.y) * amount,
    )


def _point_xy(points: tuple[Point, ...]) -> list[tuple[float, float]]:
    return [(point.x, point.y) for point in points]


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))
