"""Deterministic primitive round-trip quality checks."""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass, field, replace
from fnmatch import fnmatch
from math import ceil, cos, hypot, pi, radians, sin
from pathlib import Path
from statistics import mean
from typing import Any, Callable, Iterable

from PIL import Image, ImageDraw

from morphea.images import scene_from_flat_color_image
from morphea.refinement import RefinementConfig, refine_manifest
from morphea.rendering import raster_fidelity_metrics, render_manifest_image
from morphea.scene import SvgStyle
from morphea.svg_raster import (
    rasterize_svg,
    svg_raster_capability,
    svg_raster_metrics,
)


Geometry = dict[str, Any]
DrawFunction = Callable[[ImageDraw.ImageDraw], None]
SourceFunction = Callable[[], Image.Image]
BLUE = "#003366"

CURVE_ANCHOR_KINDS = (
    "arc",
    "stroke_path",
    "ellipse",
    "stroke_ellipse",
    "cubic_path",
)

# The exported SVG is rasterized with the builtin supersampling backend and
# compared against the source. SVG strokes center on the centerline and
# polygons cover the mathematical area, while the PIL-drawn sources and
# previews use inclusive pixel conventions, so derived defaults allow a small
# documented offset on top of each family's manifest-preview thresholds.
# Families can pin stricter explicit values.
SVG_L1_TOLERANCE_OFFSET = 0.03
SVG_EDGE_TOLERANCE_OFFSET = 0.035
SVG_ALPHA_TOLERANCE_OFFSET = 0.02
SVG_VS_PREVIEW_TOLERANCE_OFFSET = 0.02

# Simple arcs export as one smooth SVG `A` path and the preview samples the
# same fitted circle, so both gates run tight.
ARC_MAX_RASTER_L1_ERROR = 0.02
ARC_MAX_RASTER_EDGE_ERROR = 0.025
ARC_MAX_SVG_RASTER_L1_ERROR = 0.025
ARC_MAX_SVG_RASTER_EDGE_ERROR = 0.03
ARC_MAX_SVG_VS_PREVIEW_L1_ERROR = 0.02


@dataclass(frozen=True)
class ExpectedPrimitive:
    id: str
    expected_kinds: tuple[str, ...]
    geometry_type: str
    geometry: Geometry
    color: str = BLUE
    color_tolerance: float = 0.0
    coordinate_tolerance: float | None = None
    min_bbox_iou: float | None = None


@dataclass(frozen=True)
class PrimitiveSpec:
    id: str
    expected_kinds: tuple[str, ...]
    geometry_type: str
    geometry: Geometry
    draw: DrawFunction
    family: str | None = None
    variant: str = "fixed"
    source_factory: SourceFunction | None = None
    vectorize_config: dict[str, Any] = field(default_factory=dict)
    width: int = 64
    height: int = 64
    background: str = "#ffffff"
    color: str = "#003366"
    color_tolerance: float = 0.0
    expected_primitives: tuple[ExpectedPrimitive, ...] = ()
    expected_groups: tuple[dict[str, Any], ...] = ()
    compare_cutout_exports: bool = False
    min_area: int = 4
    coordinate_tolerance: float = 1.5
    max_raster_l1_error: float = 0.02
    max_raster_edge_error: float = 0.03
    max_raster_alpha_error: float = 0.001
    max_svg_raster_l1_error: float | None = None
    max_svg_raster_edge_error: float | None = None
    max_svg_alpha_error: float | None = None
    max_svg_vs_preview_l1_error: float | None = None
    min_bbox_iou: float = 0.9
    max_anchor_count: int = 1
    allow_cubic_path: bool = False


def primitive_specs() -> tuple[PrimitiveSpec, ...]:
    specs: list[PrimitiveSpec] = []
    specs.extend(
        _square_spec(case_id, variant, box)
        for case_id, variant, box in (
            ("filled_square", "base", (16, 16, 47, 47)),
            ("filled_square_small_top_left", "small_top_left", (8, 8, 25, 25)),
            ("filled_square_small_bottom_right", "small_bottom_right", (38, 34, 55, 51)),
            ("filled_square_medium_left", "medium_left", (6, 24, 29, 47)),
            ("filled_square_medium_right", "medium_right", (35, 10, 58, 33)),
            ("filled_square_large_center", "large_center", (10, 10, 53, 53)),
            ("filled_square_near_top", "near_top", (24, 2, 45, 23)),
            ("filled_square_near_bottom", "near_bottom", (20, 40, 41, 61)),
            ("filled_square_tiny_center", "tiny_center", (27, 27, 38, 38)),
            ("filled_square_offset_center", "offset_center", (18, 11, 44, 37)),
        )
    )
    specs.extend(
        _rectangle_spec(case_id, variant, box)
        for case_id, variant, box in (
            ("filled_rectangle", "base", (12, 20, 52, 38)),
            ("filled_rectangle_tall", "tall", (18, 8, 38, 56)),
            ("filled_rectangle_wide", "wide", (6, 24, 58, 38)),
            ("filled_rectangle_wide_thick", "wide_thick", (4, 22, 60, 36)),
            ("filled_rectangle_narrow_tall", "narrow_tall", (26, 4, 40, 60)),
            ("filled_rectangle_small", "small", (8, 8, 28, 22)),
            ("filled_rectangle_bottom", "bottom", (18, 42, 54, 58)),
            ("filled_rectangle_top_strip", "top_strip", (10, 4, 54, 16)),
            ("filled_rectangle_right", "right", (38, 12, 58, 50)),
            ("filled_rectangle_near_square", "near_square", (20, 16, 48, 42)),
        )
    )
    specs.extend(
        _circle_spec(case_id, variant, box)
        for case_id, variant, box in (
            ("filled_circle", "base", (18, 18, 46, 46)),
            ("filled_circle_small_top_left", "small_top_left", (8, 8, 28, 28)),
            ("filled_circle_small_top_right", "small_top_right", (34, 8, 56, 30)),
            ("filled_circle_small_bottom_left", "small_bottom_left", (8, 34, 30, 56)),
            ("filled_circle_large_top_right", "large_top_right", (24, 4, 60, 40)),
            ("filled_circle_large_bottom_left", "large_bottom_left", (4, 24, 36, 56)),
            ("filled_circle_medium_center", "medium_center", (20, 20, 44, 44)),
            ("filled_circle_large_center", "large_center", (10, 14, 50, 54)),
            ("filled_circle_near_origin", "near_origin", (2, 2, 30, 30)),
            ("filled_circle_near_corner", "near_corner", (32, 32, 60, 60)),
        )
    )
    specs.extend(
        _horizontal_stroke_spec(case_id, variant, line, width)
        for case_id, variant, line, width in (
            ("horizontal_stroke", "base", (12, 32, 52, 32), 4),
            ("horizontal_stroke_width_1", "width_1", (8, 14, 56, 14), 1),
            ("horizontal_stroke_width_2", "width_2", (8, 20, 56, 20), 2),
            ("horizontal_stroke_width_3", "width_3", (10, 26, 54, 26), 3),
            ("horizontal_stroke_width_5", "width_5", (8, 38, 56, 38), 5),
            ("horizontal_stroke_width_6", "width_6", (12, 46, 52, 46), 6),
            ("horizontal_stroke_width_8", "width_8", (10, 54, 54, 54), 8),
            ("horizontal_stroke_short", "short", (18, 10, 42, 10), 4),
            ("horizontal_stroke_left", "left", (4, 32, 34, 32), 4),
            ("horizontal_stroke_right", "right", (30, 32, 60, 32), 4),
        )
    )
    specs.extend(
        _vertical_stroke_spec(case_id, variant, line, width)
        for case_id, variant, line, width in (
            ("vertical_stroke", "base", (32, 12, 32, 52), 4),
            ("vertical_stroke_width_1", "width_1", (14, 8, 14, 56), 1),
            ("vertical_stroke_width_2", "width_2", (20, 8, 20, 56), 2),
            ("vertical_stroke_width_3", "width_3", (26, 10, 26, 54), 3),
            ("vertical_stroke_width_5", "width_5", (38, 8, 38, 56), 5),
            ("vertical_stroke_width_6", "width_6", (46, 12, 46, 52), 6),
            ("vertical_stroke_width_8", "width_8", (54, 10, 54, 54), 8),
            ("vertical_stroke_short", "short", (10, 18, 10, 42), 4),
            ("vertical_stroke_top", "top", (32, 4, 32, 34), 4),
            ("vertical_stroke_bottom", "bottom", (32, 30, 32, 60), 4),
        )
    )
    specs.extend(
        _diagonal_stroke_spec(case_id, variant, line, width)
        for case_id, variant, line, width in (
            ("diagonal_stroke", "base", (14, 50, 50, 14), 3),
            ("diagonal_stroke_width_2", "width_2", (12, 52, 52, 12), 2),
            ("diagonal_stroke_width_3", "width_3", (10, 50, 54, 14), 3),
            ("diagonal_stroke_width_4", "width_4", (8, 48, 56, 20), 4),
            ("diagonal_stroke_width_5", "width_5", (12, 12, 52, 52), 5),
            ("diagonal_stroke_width_6", "width_6", (8, 56, 56, 8), 6),
            ("diagonal_stroke_width_7", "width_7", (16, 54, 50, 10), 7),
            ("diagonal_stroke_width_8", "width_8", (10, 16, 54, 48), 8),
            ("diagonal_stroke_shallow", "shallow", (8, 44, 56, 24), 4),
            ("diagonal_stroke_steep", "steep", (24, 56, 42, 8), 4),
        )
    )
    specs.extend(
        _ring_spec(case_id, variant, box, width)
        for case_id, variant, box, width in (
            ("outlined_ring", "base", (18, 18, 46, 46), 4),
            ("outlined_ring_thin", "thin", (18, 18, 46, 46), 2),
            ("outlined_ring_medium", "medium", (16, 16, 48, 48), 4),
            ("outlined_ring_thick", "thick", (16, 16, 48, 48), 6),
            ("outlined_ring_large_thick", "large_thick", (10, 10, 54, 54), 8),
            ("outlined_ring_small_left", "small_left", (6, 18, 34, 46), 4),
            ("outlined_ring_small_right", "small_right", (30, 18, 58, 46), 4),
            ("outlined_ring_top", "top", (18, 4, 46, 32), 4),
            ("outlined_ring_bottom", "bottom", (18, 30, 46, 58), 4),
            ("outlined_ring_large", "large", (8, 8, 56, 56), 5),
        )
    )
    specs.extend(
        _rounded_rectangle_spec(case_id, variant, box, radius)
        for case_id, variant, box, radius in (
            ("rounded_rectangle", "base", (14, 20, 50, 44), 6),
            ("rounded_rectangle_small_radius", "small_radius", (8, 8, 38, 30), 4),
            ("rounded_rectangle_medium_radius", "medium_radius", (10, 18, 54, 46), 10),
            ("rounded_rectangle_tall", "tall", (20, 8, 50, 56), 8),
            ("rounded_rectangle_wide", "wide", (6, 24, 58, 42), 6),
            ("rounded_rectangle_small", "small", (12, 10, 36, 28), 5),
            ("rounded_rectangle_bottom", "bottom", (14, 36, 52, 58), 7),
            ("rounded_rectangle_top", "top", (14, 4, 52, 26), 7),
            ("rounded_rectangle_right", "right", (30, 12, 58, 48), 8),
            ("rounded_rectangle_left", "left", (6, 12, 34, 48), 8),
        )
    )
    specs.extend(
        _quad_spec(case_id, variant, corners)
        for case_id, variant, corners in (
            ("simple_quad", "base", ((20, 18), (46, 18), (54, 44), (12, 44))),
            ("simple_quad_trapezoid_1", "trapezoid_1", ((18, 18), (46, 18), (52, 44), (12, 44))),
            ("simple_quad_trapezoid_2", "trapezoid_2", ((14, 14), (50, 14), (54, 48), (10, 48))),
            ("simple_quad_trapezoid_3", "trapezoid_3", ((18, 12), (42, 12), (50, 52), (10, 52))),
            ("simple_quad_trapezoid_4", "trapezoid_4", ((10, 20), (54, 20), (48, 48), (16, 48))),
            ("simple_quad_trapezoid_5", "trapezoid_5", ((20, 10), (44, 10), (56, 42), (8, 42))),
            ("simple_quad_trapezoid_6", "trapezoid_6", ((8, 12), (56, 12), (50, 32), (16, 32))),
            ("simple_quad_trapezoid_7", "trapezoid_7", ((16, 30), (48, 30), (58, 56), (6, 56))),
            ("simple_quad_trapezoid_8", "trapezoid_8", ((24, 8), (54, 8), (48, 40), (12, 40))),
            ("simple_quad_trapezoid_9", "trapezoid_9", ((12, 24), (52, 24), (44, 54), (20, 54))),
        )
    )
    specs.extend(
        _arc_spec(case_id, family, variant, arc)
        for case_id, family, variant, arc in (
            ("arc_up", "arc_up", "base", (32, 40, 20, -150, -30, 3)),
            ("arc_up_small", "arc_up", "small", (30, 38, 17, -150, -30, 3)),
            ("arc_up_large", "arc_up", "large", (33, 42, 22, -152, -28, 3)),
            ("arc_down", "arc_down", "base", (32, 24, 20, 30, 150, 3)),
            ("arc_down_small", "arc_down", "small", (30, 22, 17, 30, 150, 3)),
            ("arc_down_large", "arc_down", "large", (33, 26, 22, 28, 152, 3)),
            ("arc_left", "arc_left", "base", (40, 32, 20, 120, 240, 3)),
            ("arc_left_small", "arc_left", "small", (38, 30, 17, 120, 240, 3)),
            ("arc_left_large", "arc_left", "large", (42, 33, 22, 122, 238, 3)),
            ("arc_right", "arc_right", "base", (24, 32, 20, -60, 60, 3)),
            ("arc_right_small", "arc_right", "small", (22, 30, 17, -60, 60, 3)),
            ("arc_right_large", "arc_right", "large", (26, 33, 22, -58, 58, 3)),
            ("arc_shallow", "arc_shallow", "base", (32, 50, 26, -125, -55, 3)),
            ("arc_shallow_small", "arc_shallow", "small", (32, 48, 24, -122, -58, 3)),
            ("arc_shallow_large", "arc_shallow", "large", (31, 52, 28, -126, -54, 3)),
            ("arc_steep", "arc_steep", "base", (32, 36, 17, -170, -10, 3)),
            ("arc_steep_small", "arc_steep", "small", (32, 35, 15, -168, -12, 3)),
            ("arc_steep_large", "arc_steep", "large", (32, 38, 19, -166, -14, 3)),
            ("arc_thick", "arc_thick", "base", (32, 40, 19, -150, -30, 6)),
            ("arc_thick_medium", "arc_thick", "medium", (32, 38, 17, -148, -32, 5)),
            ("arc_thick_wide", "arc_thick", "wide", (32, 42, 20, -152, -28, 7)),
            ("arc_small_radius", "arc_small_radius", "base", (32, 36, 10, -160, -20, 3)),
            ("arc_small_radius_left", "arc_small_radius", "left", (24, 30, 9, -158, -22, 3)),
            ("arc_small_radius_right", "arc_small_radius", "right", (40, 34, 11, -162, -18, 3)),
        )
    )
    specs.extend(
        _smooth_curve_spec(case_id, family, variant, controls, width, cap, *extra)
        for case_id, family, variant, controls, width, cap, *extra in (
            ("curve_quadratic", "curve_quadratic", "base", ((8, 46), (32, 10), (56, 46)), 3, "round"),
            ("curve_quadratic_narrow", "curve_quadratic", "narrow", ((12, 48), (32, 14), (52, 48)), 3, "round"),
            ("curve_quadratic_offset", "curve_quadratic", "offset", ((8, 42), (28, 8), (54, 46)), 3, "round"),
            ("curve_s", "curve_s", "base", ((8, 44), (28, 10), (36, 54), (56, 20)), 3, "round"),
            ("curve_s_mirrored", "curve_s", "mirrored", ((8, 20), (28, 54), (36, 10), (56, 44)), 3, "round"),
            ("curve_s_tight", "curve_s", "tight", ((10, 46), (26, 14), (38, 52), (54, 18)), 3, "round"),
            ("curve_wave", "curve_wave", "base", ((6, 32), (18, 14), (32, 50), (46, 14), (58, 32)), 3, "round"),
            ("curve_wave_inverted", "curve_wave", "inverted", ((6, 32), (18, 50), (32, 14), (46, 50), (58, 32)), 3, "round"),
            ("curve_wave_offset", "curve_wave", "offset", ((8, 30), (20, 12), (32, 48), (44, 16), (56, 34)), 3, "round"),
            ("curve_asymmetric", "curve_asymmetric", "base", ((8, 50), (16, 12), (56, 38)), 3, "round"),
            ("curve_asymmetric_right", "curve_asymmetric", "right", ((8, 38), (48, 10), (56, 50)), 3, "round"),
            ("curve_asymmetric_low", "curve_asymmetric", "low", ((8, 36), (20, 8), (58, 46)), 3, "round"),
            ("curve_diagonal", "curve_diagonal", "base", ((10, 54), (24, 40), (44, 34), (54, 10)), 3, "round", 0.04),
            ("curve_diagonal_up", "curve_diagonal", "up", ((10, 10), (24, 24), (44, 30), (54, 54)), 3, "round", 0.04),
            ("curve_diagonal_steep", "curve_diagonal", "steep", ((8, 52), (22, 36), (46, 30), (56, 8)), 3, "round", 0.04),
            ("curve_square_caps", "curve_square_caps", "base", ((8, 44), (22, 44), (42, 16), (56, 16)), 5, "square"),
            ("curve_square_caps_down", "curve_square_caps", "down", ((8, 20), (22, 20), (42, 46), (56, 46)), 5, "square"),
            ("curve_square_caps_long", "curve_square_caps", "long", ((8, 40), (24, 40), (40, 14), (58, 14)), 5, "square"),
            ("curve_round_caps", "curve_round_caps", "base", ((8, 44), (22, 44), (42, 16), (56, 16)), 5, "round"),
            ("curve_round_caps_down", "curve_round_caps", "down", ((8, 20), (22, 20), (42, 46), (56, 46)), 5, "round"),
            ("curve_round_caps_long", "curve_round_caps", "long", ((8, 40), (24, 40), (40, 14), (58, 14)), 5, "round"),
        )
    )
    specs.extend(
        _ellipse_spec(case_id, family, variant, box)
        for case_id, family, variant, box in (
            ("ellipse_horizontal", "ellipse_horizontal", "base", (10, 20, 54, 44)),
            ("ellipse_horizontal_flat", "ellipse_horizontal", "flat", (8, 22, 56, 42)),
            ("ellipse_horizontal_tall", "ellipse_horizontal", "tall", (12, 18, 52, 46)),
            ("ellipse_vertical", "ellipse_vertical", "base", (20, 10, 44, 54)),
            ("ellipse_vertical_narrow", "ellipse_vertical", "narrow", (22, 8, 42, 56)),
            ("ellipse_vertical_wide", "ellipse_vertical", "wide", (18, 12, 46, 52)),
            ("ellipse_small", "ellipse_small", "base", (22, 26, 42, 38)),
            ("ellipse_small_top_left", "ellipse_small", "top_left", (10, 14, 30, 26)),
            ("ellipse_small_bottom_right", "ellipse_small", "bottom_right", (32, 36, 52, 48)),
            ("ellipse_large", "ellipse_large", "base", (4, 12, 60, 52)),
            ("ellipse_large_tall", "ellipse_large", "tall", (8, 4, 52, 60)),
            ("ellipse_large_low", "ellipse_large", "low", (3, 16, 61, 54)),
            ("ellipse_wide", "ellipse_wide", "base", (6, 26, 58, 38)),
            ("ellipse_wide_thin", "ellipse_wide", "thin", (8, 24, 56, 36)),
            ("ellipse_wide_thick", "ellipse_wide", "thick", (4, 26, 60, 42)),
        )
    )
    specs.extend(
        _stroked_ellipse_spec(case_id, variant, box, width)
        for case_id, variant, box, width in (
            ("stroked_ellipse", "base", (10, 20, 54, 44), 4),
            ("stroked_ellipse_thin", "thin", (12, 18, 52, 46), 3),
            ("stroked_ellipse_thick", "thick", (8, 16, 56, 48), 5),
        )
    )
    specs.extend(
        _antialiased_ellipse_spec(case_id, variant, box)
        for case_id, variant, box in (
            ("antialiased_ellipse", "base", (10, 20, 54, 44)),
            ("antialiased_ellipse_narrow", "narrow", (14, 22, 50, 42)),
            ("antialiased_ellipse_vertical", "vertical", (20, 12, 44, 52)),
        )
    )
    specs.extend(
        _antialiased_arc_spec(case_id, variant, arc)
        for case_id, variant, arc in (
            ("antialiased_arc", "base", (32, 40, 20, -150, -30, 3)),
            ("antialiased_arc_steep", "steep", (32, 36, 17, -166, -14, 3)),
            ("antialiased_arc_thick", "thick", (32, 40, 19, -150, -30, 6)),
        )
    )
    specs.extend(
        _antialiased_curve_spec(case_id, variant, controls, width)
        for case_id, variant, controls, width in (
            ("antialiased_curve_s", "s", ((8, 44), (28, 10), (36, 54), (56, 20)), 3),
            ("antialiased_curve_wave", "wave", ((6, 32), (18, 14), (32, 50), (46, 14), (58, 32)), 3),
            ("antialiased_curve_quadratic", "quadratic", ((8, 46), (32, 10), (56, 46)), 3),
        )
    )
    specs.extend(
        _drift_curve_spec(case_id, variant, controls, width, drift)
        for case_id, variant, controls, width, drift in (
            (
                "drift_curve_s",
                "s",
                ((8, 44), (28, 10), (36, 54), (56, 20)),
                3,
                (((16, 33), "#07396c"), ((32, 32), "#002f61"), ((48, 28), "#0b3868")),
            ),
            (
                "drift_curve_quadratic",
                "quadratic",
                ((8, 46), (32, 10), (56, 46)),
                3,
                (((14, 38), "#083a6d"), ((32, 28), "#003064"), ((50, 38), "#0a3766")),
            ),
            (
                "drift_curve_wave",
                "wave",
                ((6, 32), (18, 14), (32, 50), (46, 14), (58, 32)),
                3,
                (((14, 22), "#073a6b"), ((32, 40), "#013263"), ((50, 22), "#0c3969")),
            ),
        )
    )
    specs.extend(
        _transparent_arc_spec(case_id, variant, arc)
        for case_id, variant, arc in (
            ("transparent_arc", "base", (32, 40, 20, -150, -30, 3)),
            ("transparent_arc_small", "small", (30, 38, 17, -150, -30, 3)),
            ("transparent_arc_thick", "thick", (32, 40, 19, -150, -30, 6)),
        )
    )
    specs.extend(
        _transparent_curve_spec(case_id, variant, controls, width)
        for case_id, variant, controls, width in (
            ("transparent_curve_s", "s", ((8, 44), (28, 10), (36, 54), (56, 20)), 3),
            ("transparent_curve_wave", "wave", ((6, 32), (18, 14), (32, 50), (46, 14), (58, 32)), 3),
            ("transparent_curve_diagonal", "diagonal", ((10, 54), (24, 40), (44, 34), (54, 10)), 3),
        )
    )
    specs.extend(
        _antialiased_circle_spec(case_id, variant, box)
        for case_id, variant, box in (
            ("antialiased_circle", "base", (18, 18, 46, 46)),
            ("antialiased_circle_small", "small", (10, 10, 32, 32)),
            ("antialiased_circle_large", "large", (8, 8, 56, 56)),
        )
    )
    specs.extend(
        _antialiased_ring_spec(case_id, variant, box, width)
        for case_id, variant, box, width in (
            ("antialiased_ring", "base", (18, 18, 46, 46), 4),
            ("antialiased_ring_medium", "medium", (14, 14, 50, 50), 5),
            ("antialiased_ring_large", "large", (10, 10, 54, 54), 6),
        )
    )
    specs.extend(
        _antialiased_stroke_spec(case_id, variant, line, width)
        for case_id, variant, line, width in (
            ("antialiased_stroke_horizontal", "horizontal", (8, 32, 56, 32), 4),
            ("antialiased_stroke_vertical", "vertical", (32, 8, 32, 56), 5),
            ("antialiased_stroke_diagonal", "diagonal", (12, 52, 52, 12), 4),
        )
    )
    specs.extend(
        _palette_drift_spec(case_id, variant, box, drift_pixels)
        for case_id, variant, box, drift_pixels in (
            (
                "palette_drift_square",
                "square",
                (16, 16, 47, 47),
                (((18, 18), "#073a6d"), ((30, 30), "#002f62"), ((42, 42), "#0b3867")),
            ),
            (
                "palette_drift_rectangle",
                "rectangle",
                (10, 22, 54, 38),
                (((12, 24), "#083b70"), ((32, 30), "#003061"), ((50, 36), "#0d3a69")),
            ),
            (
                "palette_drift_circle",
                "circle",
                (18, 18, 46, 46),
                (((32, 20), "#07396c"), ((26, 32), "#002f61"), ((38, 38), "#0b3968")),
            ),
        )
    )
    specs.extend(
        _transparent_circle_spec(case_id, variant, box)
        for case_id, variant, box in (
            ("transparent_circle", "base", (18, 18, 46, 46)),
            ("transparent_circle_small", "small", (10, 10, 32, 32)),
            ("transparent_circle_offset", "offset", (30, 18, 56, 44)),
        )
    )
    specs.extend(
        _composition_spec(case_id, "composition_same_color_separated", variant, primitives)
        for case_id, variant, primitives in (
            (
                "composition_same_color_two_squares",
                "two_squares",
                (
                    _rect_primitive("left_square", (8, 12, 24, 28)),
                    _rect_primitive("right_square", (40, 34, 56, 50)),
                ),
            ),
            (
                "composition_same_color_square_circle",
                "square_circle",
                (
                    _rect_primitive("square", (8, 34, 24, 50)),
                    _circle_primitive("circle", (38, 10, 56, 28)),
                ),
            ),
            (
                "composition_same_color_rect_circle",
                "rect_circle",
                (
                    _rect_primitive("rect", (6, 12, 30, 24)),
                    _circle_primitive("circle", (40, 36, 56, 52)),
                ),
            ),
        )
    )
    specs.extend(
        _composition_spec(case_id, "composition_different_color_separated", variant, primitives)
        for case_id, variant, primitives in (
            (
                "composition_different_color_square_circle",
                "square_circle",
                (
                    _rect_primitive("blue_square", (8, 10, 26, 28), color=BLUE),
                    _circle_primitive("red_circle", (38, 34, 56, 52), color="#dd2222"),
                ),
            ),
            (
                "composition_different_color_two_rects",
                "two_rects",
                (
                    _rect_primitive("blue_rect", (6, 36, 28, 50), color=BLUE),
                    _rect_primitive("gold_rect", (36, 10, 58, 24), color="#c99700"),
                ),
            ),
            (
                "composition_different_color_circle_rect",
                "circle_rect",
                (
                    _circle_primitive("red_circle", (8, 8, 28, 28), color="#dd2222"),
                    _rect_primitive("blue_rect", (34, 36, 58, 50), color=BLUE),
                ),
            ),
        )
    )
    specs.extend(
        _composition_spec(case_id, "composition_circle_plus_stroke", variant, primitives)
        for case_id, variant, primitives in (
            (
                "composition_circle_plus_horizontal_stroke",
                "horizontal",
                (
                    _circle_primitive("circle", (8, 8, 28, 28)),
                    _stroke_primitive("stroke", (36, 42, 58, 42), 4),
                ),
            ),
            (
                "composition_circle_plus_vertical_stroke",
                "vertical",
                (
                    _circle_primitive("circle", (36, 8, 56, 28)),
                    _stroke_primitive("stroke", (16, 34, 16, 58), 4),
                ),
            ),
            (
                "composition_circle_plus_diagonal_stroke",
                "diagonal",
                (
                    _circle_primitive("circle", (8, 36, 26, 54)),
                    _stroke_primitive("stroke", (38, 28, 58, 8), 4, tolerance=2.75),
                ),
            ),
        )
    )
    specs.extend(
        _composition_spec(case_id, "composition_square_plus_circle", variant, primitives)
        for case_id, variant, primitives in (
            (
                "composition_square_plus_circle_a",
                "a",
                (
                    _rect_primitive("square", (8, 8, 26, 26)),
                    _circle_primitive("circle", (38, 38, 56, 56)),
                ),
            ),
            (
                "composition_square_plus_circle_b",
                "b",
                (
                    _rect_primitive("square", (38, 8, 56, 26)),
                    _circle_primitive("circle", (8, 38, 26, 56)),
                ),
            ),
            (
                "composition_square_plus_circle_c",
                "c",
                (
                    _rect_primitive("square", (22, 8, 40, 26)),
                    _circle_primitive("circle", (8, 38, 26, 56)),
                ),
            ),
        )
    )
    specs.extend(
        _composition_spec(case_id, "composition_ring_plus_dot", variant, primitives)
        for case_id, variant, primitives in (
            (
                "composition_ring_plus_dot_a",
                "a",
                (
                    _ring_primitive("ring", (8, 8, 34, 34), 4),
                    _circle_primitive("dot", (46, 46, 56, 56)),
                ),
            ),
            (
                "composition_ring_plus_dot_b",
                "b",
                (
                    _ring_primitive("ring", (30, 8, 56, 34), 4),
                    _circle_primitive("dot", (8, 46, 18, 56)),
                ),
            ),
            (
                "composition_ring_plus_dot_c",
                "c",
                (
                    _ring_primitive("ring", (8, 30, 34, 56), 4),
                    _circle_primitive("dot", (46, 8, 56, 18)),
                ),
            ),
        )
    )
    specs.extend(
        _composition_spec(case_id, "composition_dot_row", variant, primitives)
        for case_id, variant, primitives in (
            (
                "composition_dot_row_three",
                "three",
                tuple(_circle_primitive(f"dot_{index}", box) for index, box in enumerate(((8, 28, 16, 36), (28, 28, 36, 36), (48, 28, 56, 36)))),
            ),
            (
                "composition_dot_row_four",
                "four",
                tuple(_circle_primitive(f"dot_{index}", box) for index, box in enumerate(((6, 28, 14, 36), (22, 28, 30, 36), (38, 28, 46, 36), (54, 28, 62, 36)))),
            ),
            (
                "composition_dot_column_three",
                "column_three",
                tuple(_circle_primitive(f"dot_{index}", box) for index, box in enumerate(((28, 6, 36, 14), (28, 28, 36, 36), (28, 50, 36, 58)))),
            ),
        )
    )
    specs.extend(
        _composition_spec(case_id, "composition_multiple_strokes", variant, primitives)
        for case_id, variant, primitives in (
            (
                "composition_multiple_horizontal_strokes",
                "horizontal",
                (
                    _stroke_primitive("top", (8, 18, 56, 18), 3),
                    _stroke_primitive("bottom", (8, 44, 56, 44), 3),
                ),
            ),
            (
                "composition_multiple_vertical_strokes",
                "vertical",
                (
                    _stroke_primitive("left", (18, 8, 18, 56), 3),
                    _stroke_primitive("right", (46, 8, 46, 56), 3),
                ),
            ),
            (
                "composition_multiple_mixed_strokes",
                "mixed",
                (
                    _stroke_primitive("horizontal", (8, 18, 34, 18), 3),
                    _stroke_primitive("vertical", (50, 30, 50, 58), 3),
                    _stroke_primitive("diagonal", (8, 54, 30, 32), 3, tolerance=2.75),
                ),
            ),
        )
    )
    specs.extend(
        _composition_spec(case_id, "adjacent_different_color_rects", variant, primitives)
        for case_id, variant, primitives in (
            (
                "adjacent_different_color_rects_horizontal",
                "horizontal",
                (
                    _rect_primitive("blue_rect", (8, 18, 31, 42), color=BLUE),
                    _rect_primitive("gold_rect", (32, 18, 56, 42), color="#c99700"),
                ),
            ),
            (
                "adjacent_different_color_rects_vertical",
                "vertical",
                (
                    _rect_primitive("red_rect", (18, 8, 42, 31), color="#dd2222"),
                    _rect_primitive("blue_rect", (18, 32, 42, 56), color=BLUE),
                ),
            ),
            (
                "adjacent_different_color_rects_offset",
                "offset",
                (
                    _rect_primitive("blue_rect", (8, 12, 32, 34), color=BLUE),
                    _rect_primitive("red_rect", (33, 20, 56, 42), color="#dd2222"),
                ),
            ),
        )
    )
    specs.extend(
        _composition_spec(case_id, "adjacent_same_color_rects_merge", variant, primitives)
        for case_id, variant, primitives in (
            (
                "adjacent_same_color_rects_merge_horizontal",
                "horizontal",
                (_rect_primitive("merged_rect", (8, 18, 56, 42)),),
            ),
            (
                "adjacent_same_color_rects_merge_vertical",
                "vertical",
                (_rect_primitive("merged_rect", (18, 8, 42, 56)),),
            ),
            (
                "adjacent_same_color_rects_merge_wide",
                "wide",
                (_rect_primitive("merged_rect", (6, 24, 58, 38)),),
            ),
        )
    )
    specs.extend(
        _composition_spec(case_id, "adjacent_small_gap_rects", variant, primitives)
        for case_id, variant, primitives in (
            (
                "adjacent_small_gap_rects_horizontal",
                "horizontal_gap",
                (
                    _rect_primitive("left_rect", (8, 18, 29, 42)),
                    _rect_primitive("right_rect", (34, 18, 56, 42)),
                ),
            ),
            (
                "adjacent_small_gap_rects_vertical",
                "vertical_gap",
                (
                    _rect_primitive("top_rect", (18, 8, 42, 29)),
                    _rect_primitive("bottom_rect", (18, 34, 42, 56)),
                ),
            ),
            (
                "adjacent_small_gap_rects_offset",
                "offset_gap",
                (
                    _rect_primitive("left_rect", (8, 14, 29, 36)),
                    _rect_primitive("right_rect", (34, 22, 56, 44)),
                ),
            ),
        )
    )
    specs.extend(
        _composition_spec(
            case_id,
            "touching_circle_stroke",
            variant,
            primitives,
            (
                {
                    "kind": "primitive_contact_pair",
                    "anchor_count": 2,
                    "relation": "touching",
                    "separation_policy": "separate_by_color",
                },
            ),
        )
        for case_id, variant, primitives in (
            (
                "touching_circle_stroke_right",
                "right",
                (
                    _circle_primitive("circle", (12, 22, 32, 42), color=BLUE),
                    _stroke_primitive("stroke", (32, 32, 54, 32), 4, color="#dd2222"),
                ),
            ),
            (
                "touching_circle_stroke_left",
                "left",
                (
                    _circle_primitive("circle", (32, 22, 52, 42), color=BLUE),
                    _stroke_primitive("stroke", (10, 32, 32, 32), 4, color="#dd2222"),
                ),
            ),
            (
                "touching_circle_stroke_bottom",
                "bottom",
                (
                    _circle_primitive("circle", (22, 12, 42, 32), color=BLUE),
                    _stroke_primitive("stroke", (32, 32, 32, 54), 4, color="#dd2222"),
                ),
            ),
        )
    )
    specs.extend(
        _composition_spec(
            case_id,
            "stroke_crossing_rectangle",
            variant,
            primitives,
            (
                {
                    "kind": "primitive_contact_pair",
                    "anchor_count": 2,
                    "relation": "overlapping",
                    "separation_policy": "separate_by_color",
                },
            ),
        )
        for case_id, variant, primitives in (
            (
                "stroke_crossing_rectangle_horizontal",
                "horizontal",
                (
                    _rect_primitive("base_rect", (12, 20, 52, 44)),
                    _stroke_primitive("stroke", (8, 32, 56, 32), 4, color="#dd2222"),
                ),
            ),
            (
                "stroke_crossing_rectangle_vertical",
                "vertical",
                (
                    _rect_primitive("base_rect", (20, 12, 44, 52)),
                    _stroke_primitive("stroke", (32, 8, 32, 56), 4, color="#dd2222"),
                ),
            ),
            (
                "stroke_crossing_rectangle_low",
                "low_horizontal",
                (
                    _rect_primitive("base_rect", (10, 14, 54, 50)),
                    _stroke_primitive("stroke", (6, 38, 58, 38), 4, color="#dd2222"),
                ),
            ),
        )
    )
    specs.extend(
        _composition_spec(
            case_id,
            "overlapping_rectangles_ordered",
            variant,
            primitives,
            (
                {
                    "kind": "primitive_contact_pair",
                    "anchor_count": 2,
                    "relation": "overlapping",
                    "separation_policy": "ordered_overlap",
                },
            ),
        )
        for case_id, variant, primitives in (
            (
                "overlapping_rectangles_bottom_right",
                "bottom_right",
                (
                    _rect_primitive("base_rect", (10, 16, 42, 48), color=BLUE),
                    _rect_primitive("overlay_rect", (28, 26, 56, 54), color="#c99700"),
                ),
            ),
            (
                "overlapping_rectangles_top_left",
                "top_left",
                (
                    _rect_primitive("base_rect", (20, 18, 56, 52), color=BLUE),
                    _rect_primitive("overlay_rect", (8, 8, 34, 34), color="#c99700"),
                ),
            ),
            (
                "overlapping_rectangles_side",
                "side",
                (
                    _rect_primitive("base_rect", (12, 8, 36, 56), color=BLUE),
                    _rect_primitive("overlay_rect", (28, 16, 52, 48), color="#dd2222"),
                ),
            ),
        )
    )
    specs.extend(
        _composition_spec(
            case_id,
            "cutout_horizontal_gap",
            variant,
            primitives,
            compare_cutout_exports=True,
        )
        for case_id, variant, primitives in (
            (
                "cutout_horizontal_gap_center",
                "center",
                (
                    _rect_primitive("fill", (8, 20, 56, 44)),
                    _cutout_stroke_primitive("cutout", (18, 32, 46, 32), 1),
                ),
            ),
            (
                "cutout_horizontal_gap_top",
                "top",
                (
                    _rect_primitive("fill", (10, 14, 54, 40)),
                    _cutout_stroke_primitive("cutout", (20, 24, 44, 24), 1),
                ),
            ),
            (
                "cutout_horizontal_gap_bottom",
                "bottom",
                (
                    _rect_primitive("fill", (10, 24, 54, 50)),
                    _cutout_stroke_primitive("cutout", (20, 40, 44, 40), 1),
                ),
            ),
        )
    )
    specs.extend(
        _composition_spec(
            case_id,
            "cutout_diagonal_gap",
            variant,
            primitives,
            compare_cutout_exports=True,
        )
        for case_id, variant, primitives in (
            (
                "cutout_diagonal_gap_down",
                "down",
                (
                    _rect_primitive("fill", (8, 14, 56, 50)),
                    _cutout_stroke_primitive("cutout", (22, 24, 38, 40), 1, tolerance=2.25),
                ),
            ),
            (
                "cutout_diagonal_gap_up",
                "up",
                (
                    _rect_primitive("fill", (8, 14, 56, 50)),
                    _cutout_stroke_primitive("cutout", (22, 40, 38, 24), 1, tolerance=2.25),
                ),
            ),
            (
                "cutout_diagonal_gap_short",
                "short",
                (
                    _rect_primitive("fill", (12, 16, 52, 48)),
                    _cutout_stroke_primitive("cutout", (26, 26, 38, 38), 1, tolerance=2.25),
                ),
            ),
        )
    )
    specs.extend(
        _organic_fallback_spec(case_id, family, variant, mode, params)
        for case_id, family, variant, mode, params in (
            ("organic_blob", "organic_blob", "base", "blob",
             (32, 32, 18, ((3, 0.18, 0.5), (5, 0.08, 1.2)))),
            ("organic_blob_soft", "organic_blob", "soft", "blob",
             (32, 32, 19, ((3, 0.12, 1.8), (4, 0.1, 0.4)))),
            ("organic_blob_lumpy", "organic_blob", "lumpy", "blob",
             (31, 33, 17, ((2, 0.14, 0.9), (5, 0.12, 2.2)))),
            ("organic_leaf", "organic_leaf", "base", "blob",
             (32, 32, 19, ((2, 0.35, 0.0),))),
            ("organic_leaf_narrow", "organic_leaf", "narrow", "blob",
             (32, 32, 18, ((2, 0.42, 0.0),))),
            ("organic_leaf_tilted", "organic_leaf", "tilted", "blob",
             (32, 32, 19, ((2, 0.35, 0.7),))),
            ("organic_asymmetric", "organic_asymmetric", "base", "blob",
             (32, 32, 17, ((1, 0.18, 0.8), (3, 0.22, 2.0)))),
            ("organic_asymmetric_heavy", "organic_asymmetric", "heavy", "blob",
             (32, 33, 16, ((1, 0.22, 1.6), (3, 0.18, 0.3)))),
            ("organic_asymmetric_soft", "organic_asymmetric", "soft", "blob",
             (33, 31, 16, ((1, 0.2, 2.4), (4, 0.24, 1.0)))),
            ("organic_crescent", "organic_crescent", "base", "crescent",
             ((10, 10, 54, 54), (16, 4, 60, 48))),
            ("organic_crescent_low", "organic_crescent", "low", "crescent",
             ((8, 12, 52, 56), (14, 6, 58, 50))),
            ("organic_crescent_high", "organic_crescent", "high", "crescent",
             ((12, 8, 56, 52), (18, 14, 62, 58))),
            ("organic_compound", "organic_compound", "base", "compound",
             ((24, 30, 14, ((3, 0.15, 0.3),)), (40, 36, 13, ((4, 0.12, 1.1),)))),
            ("organic_compound_tall", "organic_compound", "tall", "compound",
             ((30, 24, 13, ((3, 0.14, 1.0),)), (34, 42, 12, ((4, 0.1, 0.2),)))),
            ("organic_compound_wide", "organic_compound", "wide", "compound",
             ((22, 27, 12, ((2, 0.16, 0.6),)), (42, 37, 13, ((3, 0.18, 1.4),)))),
        )
    )
    specs.extend(
        _composition_spec(case_id, "composition_arc_circle", variant, primitives)
        for case_id, variant, primitives in (
            (
                "composition_arc_circle",
                "base",
                (
                    _arc_primitive("arc", (32, 26, 18, -150, -30, 3)),
                    _circle_primitive("circle", (24, 40, 40, 56), color="#dd2222"),
                ),
            ),
            (
                "composition_arc_circle_left",
                "left",
                (
                    _arc_primitive("arc", (40, 24, 16, -150, -30, 3)),
                    _circle_primitive("circle", (8, 38, 26, 56), color="#dd2222"),
                ),
            ),
            (
                "composition_arc_circle_small",
                "small",
                (
                    _arc_primitive("arc", (30, 22, 14, -150, -30, 3)),
                    _circle_primitive("circle", (40, 42, 54, 56), color="#dd2222"),
                ),
            ),
        )
    )
    specs.extend(
        _composition_spec(case_id, "composition_arc_rect", variant, primitives)
        for case_id, variant, primitives in (
            (
                "composition_arc_rect",
                "base",
                (
                    _arc_primitive("arc", (32, 24, 17, -150, -30, 3)),
                    _rect_primitive("rect", (14, 38, 50, 56), color="#c99700"),
                ),
            ),
            (
                "composition_arc_rect_side",
                "side",
                (
                    _arc_primitive("arc", (22, 26, 15, -150, -30, 3)),
                    _rect_primitive("rect", (40, 12, 58, 52), color="#c99700"),
                ),
            ),
            (
                "composition_arc_rect_low",
                "low",
                (
                    _arc_primitive("arc", (32, 52, 18, -145, -35, 3)),
                    _rect_primitive("rect", (12, 6, 52, 22), color="#c99700"),
                ),
            ),
        )
    )
    specs.extend(
        _composition_spec(
            case_id,
            "composition_curve_crossing_rect",
            variant,
            primitives,
            (
                {
                    "kind": "primitive_contact_pair",
                    "anchor_count": 2,
                    "relation": "overlapping",
                    "separation_policy": "separate_by_color",
                },
            ),
        )
        for case_id, variant, primitives in (
            (
                "composition_curve_crossing_rect",
                "base",
                (
                    _rect_primitive("rect", (12, 20, 52, 44)),
                    _curve_primitive(
                        "curve",
                        ((6, 40), (24, 14), (44, 46), (58, 22)),
                        3,
                        color="#dd2222",
                    ),
                ),
            ),
            (
                "composition_curve_crossing_rect_high",
                "high",
                (
                    _rect_primitive("rect", (12, 26, 52, 50)),
                    _curve_primitive(
                        "curve",
                        ((6, 46), (24, 20), (44, 52), (58, 28)),
                        3,
                        color="#dd2222",
                    ),
                ),
            ),
            (
                "composition_curve_crossing_rect_wide",
                "wide",
                (
                    _rect_primitive("rect", (8, 22, 56, 46)),
                    _curve_primitive(
                        "curve",
                        ((4, 42), (22, 14), (44, 50), (60, 22)),
                        3,
                        color="#dd2222",
                    ),
                ),
            ),
        )
    )
    specs.extend(
        _composition_spec(
            case_id,
            "composition_curve_touching_circle",
            variant,
            primitives,
            (
                {
                    "kind": "primitive_contact_pair",
                    "anchor_count": 2,
                    # The contact relation works on anchor bounds; a bowed
                    # curve whose endpoint touches the circle always has
                    # overlapping bounds.
                    "relation": "overlapping",
                    "separation_policy": "separate_by_color",
                },
            ),
        )
        for case_id, variant, primitives in (
            (
                "composition_curve_touching_circle",
                "base",
                (
                    _circle_primitive("circle", (44, 24, 60, 40), color=BLUE),
                    _curve_primitive(
                        "curve",
                        ((6, 44), (18, 18), (32, 44), (44, 32)),
                        3,
                        color="#dd2222",
                    ),
                ),
            ),
            (
                "composition_curve_touching_circle_low",
                "low",
                (
                    _circle_primitive("circle", (44, 38, 60, 54), color=BLUE),
                    _curve_primitive(
                        "curve",
                        ((6, 52), (18, 26), (32, 52), (44, 46)),
                        3,
                        color="#dd2222",
                    ),
                ),
            ),
            (
                "composition_curve_touching_circle_left",
                "left",
                (
                    _circle_primitive("circle", (4, 24, 20, 40), color=BLUE),
                    _curve_primitive(
                        "curve",
                        ((20, 32), (32, 16), (44, 48), (58, 30)),
                        3,
                        color="#dd2222",
                    ),
                ),
            ),
        )
    )
    specs.extend(
        _composition_spec(case_id, "composition_ellipse_stroke", variant, primitives)
        for case_id, variant, primitives in (
            (
                "composition_ellipse_stroke",
                "base",
                (
                    _ellipse_primitive("ellipse", (8, 10, 50, 32)),
                    _stroke_primitive("stroke", (12, 48, 52, 48), 4, color="#dd2222"),
                ),
            ),
            (
                "composition_ellipse_stroke_vertical",
                "vertical",
                (
                    _ellipse_primitive("ellipse", (8, 18, 32, 54)),
                    _stroke_primitive("stroke", (48, 12, 48, 52), 4, color="#dd2222"),
                ),
            ),
            (
                "composition_ellipse_stroke_wide",
                "wide",
                (
                    _ellipse_primitive("ellipse", (6, 36, 58, 56)),
                    _stroke_primitive("stroke", (10, 16, 54, 16), 4, color="#dd2222"),
                ),
            ),
        )
    )
    specs.extend(
        _composition_spec(
            case_id,
            "composition_parallel_arcs",
            variant,
            primitives,
            ({"kind": "parallel_stroke_group", "anchor_count": len(primitives)},),
        )
        for case_id, variant, primitives in (
            (
                "composition_parallel_arcs",
                "base",
                (
                    _arc_primitive("outer", (32, 38, 22, -150, -30, 3)),
                    _arc_primitive("inner", (32, 38, 13, -150, -30, 3)),
                ),
            ),
            (
                "composition_parallel_arcs_tight",
                "tight",
                (
                    _arc_primitive("outer", (32, 40, 24, -145, -35, 3)),
                    _arc_primitive("inner", (32, 40, 16, -145, -35, 3)),
                ),
            ),
            (
                "composition_parallel_arcs_three",
                "three",
                (
                    _arc_primitive("outer", (32, 44, 26, -140, -40, 3)),
                    _arc_primitive("middle", (32, 44, 18, -140, -40, 3)),
                    _arc_primitive("inner", (32, 44, 10, -140, -40, 3)),
                ),
            ),
        )
    )
    specs.extend(
        _composition_spec(
            case_id,
            "composition_curve_group",
            variant,
            primitives,
            (
                {
                    "kind": "same_color_fragment_group",
                    "anchor_count": len(primitives),
                    "color": BLUE,
                },
            ),
        )
        for case_id, variant, primitives in (
            (
                "composition_curve_group",
                "base",
                (
                    _curve_primitive("top", ((8, 22), (24, 4), (36, 32), (56, 8)), 3),
                    _curve_primitive("bottom", ((8, 52), (24, 34), (36, 62), (56, 38)), 3),
                ),
            ),
            (
                "composition_curve_group_waves",
                "waves",
                (
                    _curve_primitive("top", ((6, 20), (18, 8), (32, 28), (46, 8), (58, 20)), 3),
                    _curve_primitive("bottom", ((6, 48), (18, 36), (32, 56), (46, 36), (58, 48)), 3),
                ),
            ),
            (
                "composition_curve_group_mixed",
                "mixed",
                (
                    _curve_primitive("s", ((8, 24), (24, 4), (36, 38), (56, 12)), 3),
                    _curve_primitive("low", ((8, 56), (24, 40), (36, 62), (56, 44)), 3),
                ),
            ),
        )
    )
    specs.extend(
        _curved_cutout_spec(case_id, family, variant, host, arc, extra, config)
        for case_id, family, variant, host, arc, extra, config in (
            ("cutout_curve_rect", "cutout_curve_rect", "base",
             ("rect", (8, 18, 56, 46)), (32, 52, 24, -125, -55, 2), None, {}),
            ("cutout_curve_rect_high", "cutout_curve_rect", "high",
             ("rect", (10, 16, 54, 44)), (32, 50, 23, -122, -58, 2), None, {}),
            ("cutout_curve_rect_low", "cutout_curve_rect", "low",
             ("rect", (8, 20, 56, 48)), (32, 56, 26, -126, -54, 2), None, {}),
            ("cutout_curve_circle", "cutout_curve_circle", "base",
             ("circle", (12, 12, 52, 52)), (32, 56, 24, -120, -60, 2), None, {}),
            ("cutout_curve_circle_large", "cutout_curve_circle", "large",
             ("circle", (10, 10, 54, 54)), (32, 58, 26, -122, -58, 2), None, {}),
            ("cutout_curve_circle_offset", "cutout_curve_circle", "offset",
             ("circle", (14, 12, 54, 52)), (34, 56, 24, -118, -62, 2), None, {}),
            ("cutout_curve_ring", "cutout_curve_ring", "base",
             ("ring", (8, 8, 56, 56), 10), (32, 32, 19, -150, -30, 2), None, {}),
            ("cutout_curve_ring_thick", "cutout_curve_ring", "thick",
             ("ring", (6, 6, 58, 58), 11), (32, 32, 20, -145, -35, 2), None, {}),
            ("cutout_curve_ring_offset", "cutout_curve_ring", "offset",
             ("ring", (8, 10, 54, 56), 10), (31, 33, 18, -148, -32, 2), None, {}),
            ("cutout_curve_crossing", "cutout_curve_crossing", "base",
             ("rect", (6, 20, 44, 46)), (25, 52, 22, -120, -60, 2),
             ("circle", (48, 8, 60, 20), "#dd2222"), {}),
            ("cutout_curve_crossing_low", "cutout_curve_crossing", "low",
             ("rect", (6, 14, 44, 40)), (25, 46, 22, -120, -60, 2),
             ("circle", (48, 44, 60, 56), "#dd2222"), {}),
            ("cutout_curve_crossing_right", "cutout_curve_crossing", "right",
             ("rect", (20, 20, 58, 46)), (39, 52, 22, -120, -60, 2),
             ("circle", (4, 8, 16, 20), "#dd2222"), {}),
            ("cutout_near_background", "cutout_near_background", "base",
             ("rect", (8, 18, 56, 46)), (32, 52, 24, -125, -55, 2), None,
             {"cutout_color": "#fafafa", "color_tolerance": 12.0}),
            ("cutout_near_background_light", "cutout_near_background", "light",
             ("rect", (10, 16, 54, 44)), (32, 50, 23, -122, -58, 2), None,
             {"cutout_color": "#f6f6f6", "color_tolerance": 16.0}),
            ("cutout_near_background_offwhite", "cutout_near_background", "offwhite",
             ("rect", (8, 20, 56, 48)), (32, 56, 26, -126, -54, 2), None,
             {"cutout_color": "#fbfbfb", "color_tolerance": 10.0}),
        )
    )
    specs.extend(
        _composition_spec(
            case_id,
            "group_parallel_strokes",
            variant,
            primitives,
            ({"kind": "parallel_stroke_group", "anchor_count": len(primitives)},),
        )
        for case_id, variant, primitives in (
            (
                "group_parallel_strokes_horizontal",
                "horizontal",
                (
                    _stroke_primitive("top", (8, 18, 56, 18), 3),
                    _stroke_primitive("bottom", (8, 44, 56, 44), 3),
                ),
            ),
            (
                "group_parallel_strokes_vertical",
                "vertical",
                (
                    _stroke_primitive("left", (18, 8, 18, 56), 3),
                    _stroke_primitive("right", (46, 8, 46, 56), 3),
                ),
            ),
            (
                "group_parallel_strokes_diagonal",
                "diagonal",
                (
                    _stroke_primitive("a", (10, 50, 34, 26), 3, tolerance=2.75),
                    _stroke_primitive("b", (30, 56, 54, 32), 3, tolerance=2.75),
                ),
            ),
        )
    )
    specs.extend(
        _composition_spec(
            case_id,
            "group_dot_row",
            variant,
            primitives,
            ({"kind": "same_color_fragment_group", "anchor_count": len(primitives), "color": BLUE},),
        )
        for case_id, variant, primitives in (
            (
                "group_dot_row_three",
                "three",
                tuple(_circle_primitive(f"dot_{index}", box) for index, box in enumerate(((8, 28, 16, 36), (28, 28, 36, 36), (48, 28, 56, 36)))),
            ),
            (
                "group_dot_row_four",
                "four",
                tuple(_circle_primitive(f"dot_{index}", box) for index, box in enumerate(((6, 28, 14, 36), (22, 28, 30, 36), (38, 28, 46, 36), (54, 28, 62, 36)))),
            ),
            (
                "group_dot_column_three",
                "column",
                tuple(_circle_primitive(f"dot_{index}", box) for index, box in enumerate(((28, 6, 36, 14), (28, 28, 36, 36), (28, 50, 36, 58)))),
            ),
        )
    )
    specs.extend(
        _composition_spec(
            case_id,
            "group_quad_grid",
            variant,
            primitives,
            (
                {
                    "kind": "perspective_grid",
                    "anchor_count": len(primitives),
                    "row_count": rows,
                    "column_count": columns,
                },
            ),
        )
        for case_id, variant, rows, columns, primitives in (
            (
                "group_quad_grid_row",
                "row",
                1,
                3,
                (
                    _quad_primitive("tile_0", ((4, 20), (18, 20), (20, 38), (2, 38))),
                    _quad_primitive("tile_1", ((24, 20), (38, 20), (40, 38), (22, 38))),
                    _quad_primitive("tile_2", ((44, 20), (58, 20), (60, 38), (42, 38))),
                ),
            ),
            (
                "group_quad_grid_two_by_two",
                "two_by_two",
                2,
                2,
                (
                    _quad_primitive("tile_0", ((6, 8), (24, 8), (26, 26), (4, 26))),
                    _quad_primitive("tile_1", ((38, 8), (56, 8), (60, 26), (36, 26))),
                    _quad_primitive("tile_2", ((4, 36), (26, 36), (28, 56), (2, 56))),
                    _quad_primitive("tile_3", ((36, 36), (60, 36), (62, 56), (34, 56))),
                ),
            ),
            (
                "group_quad_grid_column",
                "column",
                3,
                1,
                (
                    _quad_primitive("tile_0", ((22, 4), (42, 4), (40, 20), (24, 20))),
                    _quad_primitive("tile_1", ((20, 22), (44, 22), (42, 38), (22, 38))),
                    _quad_primitive("tile_2", ((18, 40), (46, 40), (44, 58), (20, 58))),
                ),
            ),
        )
    )
    return tuple(specs)


def _square_spec(
    case_id: str,
    variant: str,
    box: tuple[int, int, int, int],
) -> PrimitiveSpec:
    return _rectangle_spec(case_id, variant, box, family="filled_square")


def _rectangle_spec(
    case_id: str,
    variant: str,
    box: tuple[int, int, int, int],
    *,
    family: str = "filled_rectangle",
) -> PrimitiveSpec:
    x0, y0, x1, y1 = box
    return PrimitiveSpec(
        id=case_id,
        family=family,
        variant=variant,
        expected_kinds=("rect", "quad"),
        geometry_type="quad",
        geometry={"corners": ((x0, y0), (x1, y0), (x1, y1), (x0, y1))},
        draw=lambda draw, box=box: draw.rectangle(box, fill=BLUE),
        max_raster_l1_error=0.001,
        max_raster_edge_error=0.001,
    )


def _circle_spec(
    case_id: str,
    variant: str,
    box: tuple[int, int, int, int],
) -> PrimitiveSpec:
    x0, y0, x1, y1 = box
    radius = (x1 - x0) / 2
    return PrimitiveSpec(
        id=case_id,
        family="filled_circle",
        variant=variant,
        expected_kinds=("circle",),
        geometry_type="circle",
        geometry={"cx": (x0 + x1) / 2, "cy": (y0 + y1) / 2, "r": radius},
        draw=lambda draw, box=box: draw.ellipse(box, fill=BLUE),
        max_raster_l1_error=0.018,
        max_raster_edge_error=0.024,
        min_bbox_iou=0.9,
    )


def _horizontal_stroke_spec(
    case_id: str,
    variant: str,
    line: tuple[int, int, int, int],
    width: int,
) -> PrimitiveSpec:
    x0, y0, x1, y1 = line
    center_y = y0 + (0.5 if width % 2 == 0 else 0.0)
    return PrimitiveSpec(
        id=case_id,
        family="horizontal_stroke",
        variant=variant,
        expected_kinds=("stroke_polyline",),
        geometry_type="stroke",
        geometry={"centerline": ((float(x0), center_y), (float(x1), center_y)), "width": float(width)},
        draw=lambda draw, line=line, width=width: draw.line(line, fill=BLUE, width=width),
        coordinate_tolerance=1.75,
        max_raster_l1_error=0.002,
        max_raster_edge_error=0.002,
    )


def _vertical_stroke_spec(
    case_id: str,
    variant: str,
    line: tuple[int, int, int, int],
    width: int,
) -> PrimitiveSpec:
    x0, y0, x1, y1 = line
    center_x = x0 + (0.5 if width % 2 == 0 else 0.0)
    return PrimitiveSpec(
        id=case_id,
        family="vertical_stroke",
        variant=variant,
        expected_kinds=("stroke_polyline",),
        geometry_type="stroke",
        geometry={"centerline": ((center_x, float(y0)), (center_x, float(y1))), "width": float(width)},
        draw=lambda draw, line=line, width=width: draw.line(line, fill=BLUE, width=width),
        coordinate_tolerance=1.75,
        max_raster_l1_error=0.002,
        max_raster_edge_error=0.002,
    )


def _diagonal_stroke_spec(
    case_id: str,
    variant: str,
    line: tuple[int, int, int, int],
    width: int,
) -> PrimitiveSpec:
    x0, y0, x1, y1 = line
    return PrimitiveSpec(
        id=case_id,
        family="diagonal_stroke",
        variant=variant,
        expected_kinds=("stroke_polyline",),
        geometry_type="stroke",
        geometry={
            "centerline": ((float(x0), float(y0)), (float(x1), float(y1))),
            "width": float(width),
        },
        draw=lambda draw, line=line, width=width: draw.line(line, fill=BLUE, width=width),
        coordinate_tolerance=2.75,
        max_raster_l1_error=0.035,
        max_raster_edge_error=0.055,
        min_bbox_iou=0.78,
    )


def _ring_spec(
    case_id: str,
    variant: str,
    box: tuple[int, int, int, int],
    width: int,
) -> PrimitiveSpec:
    x0, y0, x1, y1 = box
    outer_radius = (x1 - x0) / 2
    return PrimitiveSpec(
        id=case_id,
        family="outlined_ring",
        variant=variant,
        expected_kinds=("stroke_circle",),
        geometry_type="stroke_circle",
        geometry={
            "cx": (x0 + x1) / 2,
            "cy": (y0 + y1) / 2,
            "r": outer_radius - width / 2 + 0.5,
            "width": width + 0.5,
        },
        draw=lambda draw, box=box, width=width: draw.ellipse(
            box,
            outline=BLUE,
            width=width,
        ),
        coordinate_tolerance=2.0,
        max_raster_l1_error=0.18,
        max_raster_edge_error=0.08,
        min_bbox_iou=0.8,
    )


def _rounded_rectangle_spec(
    case_id: str,
    variant: str,
    box: tuple[int, int, int, int],
    radius: int,
) -> PrimitiveSpec:
    x0, y0, x1, y1 = box
    return PrimitiveSpec(
        id=case_id,
        family="rounded_rectangle",
        variant=variant,
        expected_kinds=("rounded_rect",),
        geometry_type="quad",
        geometry={
            "corners": ((x0, y0), (x1, y0), (x1, y1), (x0, y1)),
            "corner_radius": float(radius),
        },
        draw=lambda draw: None,
        source_factory=lambda box=box, radius=radius: _antialiased_source(
            lambda draw, scale: draw.rounded_rectangle(
                tuple(value * scale for value in box),
                radius=radius * scale,
                fill=BLUE,
            )
        ),
        vectorize_config={"max_colors": 2},
        coordinate_tolerance=3.25,
        max_raster_l1_error=0.05,
        max_raster_edge_error=0.035,
        min_bbox_iou=0.86,
    )


def _quad_spec(
    case_id: str,
    variant: str,
    corners: tuple[tuple[int, int], tuple[int, int], tuple[int, int], tuple[int, int]],
) -> PrimitiveSpec:
    return PrimitiveSpec(
        id=case_id,
        family="simple_quad",
        variant=variant,
        expected_kinds=("quad",),
        geometry_type="quad",
        geometry={"corners": corners},
        draw=lambda draw, corners=corners: draw.polygon(corners, fill=BLUE),
        max_raster_l1_error=0.002,
        max_raster_edge_error=0.002,
        min_bbox_iou=0.9,
    )


ArcParams = tuple[float, float, float, float, float, int]
CurveControls = tuple[tuple[float, float], ...]

# Smooth stroke paths export Catmull-Rom cubic segments; preview and SVG
# sample the same spline.
CURVE_MAX_RASTER_L1_ERROR = 0.025
CURVE_MAX_RASTER_EDGE_ERROR = 0.032
CURVE_MAX_SVG_RASTER_L1_ERROR = 0.032
CURVE_MAX_SVG_RASTER_EDGE_ERROR = 0.032
CURVE_MAX_SVG_VS_PREVIEW_L1_ERROR = 0.02
CURVE_MAX_CONTROL_POINTS = 9
CURVE_MAX_CURVATURE_JITTER = 0.6
CURVE_MAX_WIDTH_VARIANCE = 0.25


def _smooth_curve_spec(
    case_id: str,
    family: str,
    variant: str,
    controls: CurveControls,
    width: int,
    cap: str,
    max_edge: float = CURVE_MAX_RASTER_EDGE_ERROR,
) -> PrimitiveSpec:
    samples = _bezier_samples(controls, steps=32)
    expected_cap = "butt" if cap in {"square", "butt"} else "round"
    start, end = samples[0], samples[-1]
    if cap == "square":
        # The detected centerline runs through the flat cap, so expected
        # endpoints extend half a width along the end tangents and the
        # reference curve gains those extensions for control-point matching.
        start = _extended_endpoint(samples[0], samples[1], width / 2)
        end = _extended_endpoint(samples[-1], samples[-2], width / 2)
        samples = (start, *samples, end)
    return PrimitiveSpec(
        id=case_id,
        family=family,
        variant=variant,
        expected_kinds=("stroke_path",),
        geometry_type="stroke_path",
        geometry={
            "curve_samples": samples,
            "start": start,
            "end": end,
            "width": float(width),
            "width_tolerance": 1.5,
            "cap_style": expected_cap,
            "max_control_points": CURVE_MAX_CONTROL_POINTS,
        },
        draw=lambda draw, controls=controls, width=width, cap=cap: _draw_smooth_curve(
            draw,
            controls,
            width,
            cap,
        ),
        coordinate_tolerance=2.75,
        max_raster_l1_error=CURVE_MAX_RASTER_L1_ERROR,
        max_raster_edge_error=max_edge,
        max_svg_raster_l1_error=CURVE_MAX_SVG_RASTER_L1_ERROR,
        max_svg_raster_edge_error=max(CURVE_MAX_SVG_RASTER_EDGE_ERROR, max_edge),
        max_svg_vs_preview_l1_error=CURVE_MAX_SVG_VS_PREVIEW_L1_ERROR,
        min_bbox_iou=0.72,
    )


def _bezier_samples(
    controls: CurveControls,
    *,
    steps: int,
) -> tuple[tuple[float, float], ...]:
    degree = len(controls) - 1
    samples = []
    for index in range(steps + 1):
        t = index / steps
        x = 0.0
        y = 0.0
        for k, (px, py) in enumerate(controls):
            weight = _binomial(degree, k) * (1 - t) ** (degree - k) * t**k
            x += weight * px
            y += weight * py
        samples.append((x, y))
    return tuple(samples)


def _binomial(n: int, k: int) -> int:
    result = 1
    for index in range(1, k + 1):
        result = result * (n - index + 1) // index
    return result


def _extended_endpoint(
    end: tuple[float, float],
    inner: tuple[float, float],
    distance: float,
) -> tuple[float, float]:
    dx = end[0] - inner[0]
    dy = end[1] - inner[1]
    length = hypot(dx, dy)
    if length <= 0:
        return end
    return (end[0] + dx / length * distance, end[1] + dy / length * distance)


def _draw_smooth_curve(
    draw: ImageDraw.ImageDraw,
    controls: CurveControls,
    width: int,
    cap: str,
    *,
    color: str = BLUE,
) -> None:
    points = list(_bezier_samples(controls, steps=64))
    draw.line(points, fill=color, width=width, joint="curve")
    half = width / 2
    if cap == "round":
        for point in (points[0], points[-1]):
            draw.ellipse(
                (point[0] - half, point[1] - half, point[0] + half - 1, point[1] + half - 1),
                fill=color,
            )
    elif cap == "square":
        for end, inner in ((points[0], points[1]), (points[-1], points[-2])):
            dx = end[0] - inner[0]
            dy = end[1] - inner[1]
            length = hypot(dx, dy)
            if length <= 0:
                continue
            dx /= length
            dy /= length
            tip = (end[0] + dx * half, end[1] + dy * half)
            normal = (-dy * half, dx * half)
            draw.polygon(
                [
                    (end[0] + normal[0], end[1] + normal[1]),
                    (tip[0] + normal[0], tip[1] + normal[1]),
                    (tip[0] - normal[0], tip[1] - normal[1]),
                    (end[0] - normal[0], end[1] - normal[1]),
                ],
                fill=color,
            )


def _arc_spec(
    case_id: str,
    family: str,
    variant: str,
    arc: ArcParams,
) -> PrimitiveSpec:
    cx, cy, radius, start_deg, end_deg, width = arc
    start = _arc_point_xy(cx, cy, radius, start_deg)
    end = _arc_point_xy(cx, cy, radius, end_deg)
    apex = _arc_point_xy(cx, cy, radius, (start_deg + end_deg) / 2)
    chord_mid = ((start[0] + end[0]) / 2, (start[1] + end[1]) / 2)
    bow = hypot(apex[0] - chord_mid[0], apex[1] - chord_mid[1])
    return PrimitiveSpec(
        id=case_id,
        family=family,
        variant=variant,
        expected_kinds=("arc",),
        geometry_type="arc",
        geometry={
            "start": start,
            "end": end,
            "apex": apex,
            "bow": bow,
            "bow_direction": _bow_direction(apex, chord_mid),
            "width": float(width),
            "cx": cx,
            "cy": cy,
            "r": float(radius),
        },
        draw=lambda draw, arc=arc: _draw_circular_arc(draw, arc),
        coordinate_tolerance=2.5,
        max_raster_l1_error=ARC_MAX_RASTER_L1_ERROR,
        max_raster_edge_error=ARC_MAX_RASTER_EDGE_ERROR,
        max_svg_raster_l1_error=ARC_MAX_SVG_RASTER_L1_ERROR,
        max_svg_raster_edge_error=ARC_MAX_SVG_RASTER_EDGE_ERROR,
        max_svg_vs_preview_l1_error=ARC_MAX_SVG_VS_PREVIEW_L1_ERROR,
        # Thin arc bounding strips lose over 10% IoU per pixel of drift; the
        # endpoint, bow, and width contracts carry the strict geometry here.
        min_bbox_iou=0.72,
    )


def _arc_point_xy(
    cx: float,
    cy: float,
    radius: float,
    angle_deg: float,
) -> tuple[float, float]:
    angle = radians(angle_deg)
    return (cx + radius * cos(angle), cy + radius * sin(angle))


def _bow_direction(
    apex: tuple[float, float],
    chord_mid: tuple[float, float],
) -> str:
    dx = apex[0] - chord_mid[0]
    dy = apex[1] - chord_mid[1]
    if abs(dx) >= abs(dy):
        return "right" if dx > 0 else "left"
    return "down" if dy > 0 else "up"


def _draw_circular_arc(draw: ImageDraw.ImageDraw, arc: ArcParams) -> None:
    cx, cy, radius, start_deg, end_deg, width = arc
    steps = max(24, ceil(radius * abs(end_deg - start_deg) / 360 * 2 * pi))
    points = []
    for index in range(steps + 1):
        angle = radians(start_deg + (end_deg - start_deg) * index / steps)
        points.append((cx + radius * cos(angle), cy + radius * sin(angle)))
    draw.line(points, fill=BLUE, width=width, joint="curve")
    half = width / 2
    for point in (points[0], points[-1]):
        draw.ellipse(
            (point[0] - half, point[1] - half, point[0] + half - 1, point[1] + half - 1),
            fill=BLUE,
        )


def _ellipse_spec(
    case_id: str,
    family: str,
    variant: str,
    box: tuple[int, int, int, int],
) -> PrimitiveSpec:
    x0, y0, x1, y1 = box
    return PrimitiveSpec(
        id=case_id,
        family=family,
        variant=variant,
        expected_kinds=("ellipse",),
        geometry_type="ellipse",
        geometry={
            "cx": (x0 + x1) / 2,
            "cy": (y0 + y1) / 2,
            "rx": (x1 - x0) / 2,
            "ry": (y1 - y0) / 2,
        },
        draw=lambda draw, box=box: draw.ellipse(box, fill=BLUE),
        coordinate_tolerance=1.75,
        max_raster_l1_error=0.025,
        max_raster_edge_error=0.03,
        # The detector reports pixel-extent radii (+0.5 vs the geometric
        # box), which costs small ellipses ~0.88 IoU by itself.
        min_bbox_iou=0.86,
    )


def _stroked_ellipse_spec(
    case_id: str,
    variant: str,
    box: tuple[int, int, int, int],
    width: int,
) -> PrimitiveSpec:
    x0, y0, x1, y1 = box
    return PrimitiveSpec(
        id=case_id,
        family="stroked_ellipse",
        variant=variant,
        expected_kinds=("stroke_ellipse",),
        geometry_type="stroke_ellipse",
        geometry={
            "cx": (x0 + x1) / 2,
            "cy": (y0 + y1) / 2,
            # PIL paints the outline inward from the box, so the centerline
            # ellipse sits half a width inside the outer radius.
            "rx": (x1 - x0) / 2 - width / 2 + 0.5,
            "ry": (y1 - y0) / 2 - width / 2 + 0.5,
            "width": width + 0.5,
        },
        draw=lambda draw, box=box, width=width: draw.ellipse(
            box,
            outline=BLUE,
            width=width,
        ),
        coordinate_tolerance=2.0,
        max_raster_l1_error=0.06,
        max_raster_edge_error=0.05,
        min_bbox_iou=0.85,
    )


def _antialiased_ellipse_spec(
    case_id: str,
    variant: str,
    box: tuple[int, int, int, int],
) -> PrimitiveSpec:
    x0, y0, x1, y1 = box
    return PrimitiveSpec(
        id=case_id,
        family="antialiased_ellipse",
        variant=variant,
        expected_kinds=("ellipse",),
        geometry_type="ellipse",
        geometry={
            "cx": (x0 + x1) / 2,
            "cy": (y0 + y1) / 2,
            "rx": (x1 - x0) / 2,
            "ry": (y1 - y0) / 2,
        },
        draw=lambda draw: None,
        source_factory=lambda box=box: _antialiased_source(
            lambda draw, scale: draw.ellipse(
                tuple(value * scale for value in box),
                fill=BLUE,
            )
        ),
        vectorize_config={"max_colors": 2},
        coordinate_tolerance=2.0,
        max_raster_l1_error=0.055,
        max_raster_edge_error=0.035,
        min_bbox_iou=0.86,
    )


def _organic_fallback_spec(
    case_id: str,
    family: str,
    variant: str,
    mode: str,
    params: tuple,
) -> PrimitiveSpec:
    if mode == "blob":
        polygon = _blob_polygon(*params)
        draw_fn = lambda draw, polygon=polygon: draw.polygon(polygon, fill=BLUE)
        xs = [x for x, _ in polygon]
        ys = [y for _, y in polygon]
    elif mode == "compound":
        polygons = [_blob_polygon(*blob) for blob in params]
        def draw_fn(draw, polygons=polygons):
            for polygon in polygons:
                draw.polygon(polygon, fill=BLUE)
        xs = [x for polygon in polygons for x, _ in polygon]
        ys = [y for polygon in polygons for _, y in polygon]
    else:
        outer, inner = params
        def draw_fn(draw, outer=outer, inner=inner):
            draw.ellipse(outer, fill=BLUE)
            draw.ellipse(inner, fill="#ffffff")
        xs = [outer[0], outer[2]]
        ys = [outer[1], outer[3]]
    bounds = (min(xs), min(ys), max(xs), max(ys))
    return PrimitiveSpec(
        id=case_id,
        family=family,
        variant=variant,
        expected_kinds=("cubic_path",),
        geometry_type="cubic_path",
        geometry={
            "bounds": bounds,
            "max_nodes": 16,
            # Crescents only keep the part of the outer disk the inner disk
            # leaves visible, so their tracked bounds stay loose.
            "loose_bounds": mode == "crescent",
        },
        draw=draw_fn,
        allow_cubic_path=True,
        coordinate_tolerance=2.5,
        max_raster_l1_error=0.05,
        max_raster_edge_error=0.05,
        max_svg_raster_l1_error=0.06,
        max_svg_raster_edge_error=0.06,
        max_svg_vs_preview_l1_error=0.03,
        min_bbox_iou=0.55 if mode == "crescent" else 0.85,
    )


def _blob_polygon(
    cx: float,
    cy: float,
    radius: float,
    harmonics: tuple[tuple[int, float, float], ...],
    *,
    steps: int = 180,
) -> list[tuple[float, float]]:
    points = []
    for index in range(steps):
        t = 2 * pi * index / steps
        r = radius * (
            1
            + sum(
                amplitude * sin(order * t + phase)
                for order, amplitude, phase in harmonics
            )
        )
        points.append((cx + r * cos(t), cy + r * sin(t)))
    return points


def _antialiased_arc_spec(
    case_id: str,
    variant: str,
    arc: ArcParams,
) -> PrimitiveSpec:
    base = _arc_spec(case_id, "antialiased_arc", variant, arc)
    return replace(
        base,
        draw=lambda draw: None,
        source_factory=lambda arc=arc: _antialiased_source(
            lambda draw, scale: _draw_circular_arc(
                draw,
                _scaled_arc(arc, scale),
            )
        ),
        vectorize_config={"max_colors": 2},
        color_tolerance=45.0,
        coordinate_tolerance=3.0,
        max_raster_l1_error=0.035,
        max_raster_edge_error=0.035,
        max_svg_raster_l1_error=0.045,
        max_svg_raster_edge_error=0.045,
        max_svg_vs_preview_l1_error=0.025,
        min_bbox_iou=0.7,
    )


def _scaled_arc(arc: ArcParams, scale: int) -> ArcParams:
    cx, cy, radius, start_deg, end_deg, width = arc
    return (cx * scale, cy * scale, radius * scale, start_deg, end_deg, width * scale)


def _antialiased_curve_spec(
    case_id: str,
    variant: str,
    controls: CurveControls,
    width: int,
) -> PrimitiveSpec:
    base = _smooth_curve_spec(case_id, "antialiased_curve", variant, controls, width, "round")
    return replace(
        base,
        draw=lambda draw: None,
        source_factory=lambda controls=controls, width=width: _antialiased_source(
            lambda draw, scale: _draw_smooth_curve(
                draw,
                tuple((x * scale, y * scale) for x, y in controls),
                width * scale,
                "round",
            )
        ),
        vectorize_config={"max_colors": 2},
        color_tolerance=45.0,
        coordinate_tolerance=3.0,
        max_raster_l1_error=0.035,
        max_raster_edge_error=0.04,
        max_svg_raster_l1_error=0.045,
        max_svg_raster_edge_error=0.05,
        max_svg_vs_preview_l1_error=0.025,
        min_bbox_iou=0.66,
    )


def _drift_curve_spec(
    case_id: str,
    variant: str,
    controls: CurveControls,
    width: int,
    drift_pixels: tuple[tuple[tuple[int, int], str], ...],
) -> PrimitiveSpec:
    base = _smooth_curve_spec(case_id, "drift_curve", variant, controls, width, "round")

    def _source(
        controls: CurveControls = controls,
        width: int = width,
        drift_pixels: tuple = drift_pixels,
    ) -> Image.Image:
        image = Image.new("RGB", (64, 64), "#ffffff")
        draw = ImageDraw.Draw(image)
        _draw_smooth_curve(draw, controls, width, "round")
        for point, color in drift_pixels:
            draw.point(point, fill=color)
        return image

    return replace(
        base,
        draw=lambda draw: None,
        source_factory=_source,
        vectorize_config={"color_tolerance": 18.0},
        color_tolerance=15.0,
        max_raster_l1_error=0.03,
        max_raster_edge_error=0.035,
    )


def _transparent_arc_spec(
    case_id: str,
    variant: str,
    arc: ArcParams,
) -> PrimitiveSpec:
    base = _arc_spec(case_id, "transparent_arc", variant, arc)

    def _source(arc: ArcParams = arc) -> Image.Image:
        image = Image.new("RGBA", (64, 64), (255, 255, 255, 0))
        _draw_circular_arc(ImageDraw.Draw(image), arc)
        return image

    return replace(
        base,
        draw=lambda draw: None,
        source_factory=_source,
        vectorize_config={"background": "#ffffff"},
        background="#ffffff00",
        max_raster_alpha_error=0.03,
    )


def _transparent_curve_spec(
    case_id: str,
    variant: str,
    controls: CurveControls,
    width: int,
) -> PrimitiveSpec:
    base = _smooth_curve_spec(
        case_id,
        "transparent_curve",
        variant,
        controls,
        width,
        "round",
    )

    def _source(
        controls: CurveControls = controls,
        width: int = width,
    ) -> Image.Image:
        image = Image.new("RGBA", (64, 64), (255, 255, 255, 0))
        _draw_smooth_curve(ImageDraw.Draw(image), controls, width, "round")
        return image

    return replace(
        base,
        draw=lambda draw: None,
        source_factory=_source,
        vectorize_config={"background": "#ffffff"},
        background="#ffffff00",
        max_raster_alpha_error=0.03,
    )


def _antialiased_circle_spec(
    case_id: str,
    variant: str,
    box: tuple[int, int, int, int],
) -> PrimitiveSpec:
    x0, y0, x1, y1 = box
    return PrimitiveSpec(
        id=case_id,
        family="antialiased_circle",
        variant=variant,
        expected_kinds=("circle",),
        geometry_type="circle",
        geometry={"cx": (x0 + x1) / 2, "cy": (y0 + y1) / 2, "r": (x1 - x0) / 2},
        draw=lambda draw: None,
        source_factory=lambda box=box: _antialiased_source(
            lambda draw, scale: draw.ellipse(
                tuple(value * scale for value in box),
                fill=BLUE,
            )
        ),
        vectorize_config={"max_colors": 2},
        coordinate_tolerance=2.0,
        max_raster_l1_error=0.055,
        max_raster_edge_error=0.03,
        min_bbox_iou=0.84,
    )


def _antialiased_ring_spec(
    case_id: str,
    variant: str,
    box: tuple[int, int, int, int],
    width: int,
) -> PrimitiveSpec:
    x0, y0, x1, y1 = box
    outer_radius = (x1 - x0) / 2
    return PrimitiveSpec(
        id=case_id,
        family="antialiased_ring",
        variant=variant,
        expected_kinds=("stroke_circle",),
        geometry_type="stroke_circle",
        geometry={
            "cx": (x0 + x1) / 2,
            "cy": (y0 + y1) / 2,
            "r": outer_radius - width / 2 + 0.5,
            "width": width + 0.5,
        },
        draw=lambda draw: None,
        source_factory=lambda box=box, width=width: _antialiased_source(
            lambda draw, scale: draw.ellipse(
                tuple(value * scale for value in box),
                outline=BLUE,
                width=width * scale,
            )
        ),
        vectorize_config={"max_colors": 2},
        color_tolerance=35.0,
        coordinate_tolerance=2.5,
        max_raster_l1_error=0.16,
        max_raster_edge_error=0.075,
        min_bbox_iou=0.78,
    )


def _antialiased_stroke_spec(
    case_id: str,
    variant: str,
    line: tuple[int, int, int, int],
    width: int,
) -> PrimitiveSpec:
    x0, y0, x1, y1 = line
    return PrimitiveSpec(
        id=case_id,
        family="antialiased_stroke",
        variant=variant,
        expected_kinds=("stroke_polyline",),
        geometry_type="stroke",
        geometry={
            "centerline": ((float(x0), float(y0)), (float(x1), float(y1))),
            "width": float(width),
        },
        draw=lambda draw: None,
        source_factory=lambda line=line, width=width: _antialiased_source(
            lambda draw, scale: draw.line(
                tuple(value * scale for value in line),
                fill=BLUE,
                width=width * scale,
            )
        ),
        vectorize_config={"max_colors": 2},
        color_tolerance=45.0,
        coordinate_tolerance=2.5,
        max_raster_l1_error=0.035,
        max_raster_edge_error=0.04,
        min_bbox_iou=0.74,
    )


def _palette_drift_spec(
    case_id: str,
    variant: str,
    box: tuple[int, int, int, int],
    drift_pixels: tuple[tuple[tuple[int, int], str], ...],
) -> PrimitiveSpec:
    if "circle" in case_id:
        base = _circle_spec(case_id, variant, box)
        geometry_type = "circle"
        expected_kinds = ("circle",)
        geometry = base.geometry
        draw_shape = lambda draw, box=box: draw.ellipse(box, fill=BLUE)
    else:
        base = _rectangle_spec(case_id, variant, box, family="palette_drift_primitive")
        geometry_type = "quad"
        expected_kinds = ("rect", "quad")
        geometry = base.geometry
        draw_shape = lambda draw, box=box: draw.rectangle(box, fill=BLUE)
    return PrimitiveSpec(
        id=case_id,
        family="palette_drift_primitive",
        variant=variant,
        expected_kinds=expected_kinds,
        geometry_type=geometry_type,
        geometry=geometry,
        draw=lambda draw: None,
        source_factory=lambda draw_shape=draw_shape, drift_pixels=drift_pixels: _palette_drift_source(
            draw_shape,
            drift_pixels,
        ),
        vectorize_config={"color_tolerance": 18.0},
        coordinate_tolerance=1.75,
        max_raster_l1_error=0.01,
        max_raster_edge_error=0.015,
        min_bbox_iou=0.88,
    )


def _transparent_circle_spec(
    case_id: str,
    variant: str,
    box: tuple[int, int, int, int],
) -> PrimitiveSpec:
    x0, y0, x1, y1 = box
    return PrimitiveSpec(
        id=case_id,
        family="transparent_circle",
        variant=variant,
        expected_kinds=("circle",),
        geometry_type="circle",
        geometry={"cx": (x0 + x1) / 2, "cy": (y0 + y1) / 2, "r": (x1 - x0) / 2},
        draw=lambda draw: None,
        source_factory=lambda box=box: _transparent_circle_source(box),
        vectorize_config={"background": "#ffffff"},
        background="#ffffff00",
        coordinate_tolerance=1.75,
        max_raster_l1_error=0.018,
        max_raster_edge_error=0.024,
        max_raster_alpha_error=0.02,
        min_bbox_iou=0.88,
    )


def _antialiased_source(
    draw_function: Callable[[ImageDraw.ImageDraw, int], None],
    *,
    scale: int = 4,
) -> Image.Image:
    high_res = Image.new("RGB", (64 * scale, 64 * scale), "#ffffff")
    draw = ImageDraw.Draw(high_res)
    draw_function(draw, scale)
    return high_res.resize((64, 64), Image.Resampling.LANCZOS)


def _palette_drift_source(
    draw_shape: DrawFunction,
    drift_pixels: tuple[tuple[tuple[int, int], str], ...],
) -> Image.Image:
    image = Image.new("RGB", (64, 64), "#ffffff")
    draw = ImageDraw.Draw(image)
    draw_shape(draw)
    for point, color in drift_pixels:
        draw.point(point, fill=color)
    return image


def _transparent_circle_source(box: tuple[int, int, int, int]) -> Image.Image:
    image = Image.new("RGBA", (64, 64), (255, 255, 255, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse(box, fill=BLUE)
    return image


def _composition_spec(
    case_id: str,
    family: str,
    variant: str,
    primitives: tuple[ExpectedPrimitive, ...],
    expected_groups: tuple[dict[str, Any], ...] = (),
    *,
    compare_cutout_exports: bool = False,
) -> PrimitiveSpec:
    first = primitives[0]
    has_curves = any(
        primitive.geometry_type in {"arc", "stroke_path"}
        for primitive in primitives
    )
    max_l1 = 0.08 if "ring" in family else (0.035 if has_curves else 0.025)
    max_edge = 0.06 if "ring" in family else (0.045 if has_curves else 0.03)
    return PrimitiveSpec(
        id=case_id,
        family=family,
        variant=variant,
        expected_kinds=first.expected_kinds,
        geometry_type=first.geometry_type,
        geometry=first.geometry,
        color=first.color,
        expected_primitives=primitives,
        expected_groups=expected_groups,
        compare_cutout_exports=compare_cutout_exports,
        draw=lambda draw, primitives=primitives: _draw_expected_primitives(draw, primitives),
        max_anchor_count=len(primitives),
        max_raster_l1_error=max_l1,
        max_raster_edge_error=max_edge,
        min_bbox_iou=0.82,
    )


CutoutHost = tuple
CutoutArc = tuple[float, float, float, float, float, int]


def _curved_cutout_spec(
    case_id: str,
    family: str,
    variant: str,
    host: CutoutHost,
    arc: CutoutArc,
    extra: tuple | None,
    config: dict[str, Any],
) -> PrimitiveSpec:
    cutout_color = str(config.get("cutout_color", "#ffffff"))
    vectorize_config: dict[str, Any] = {}
    if "color_tolerance" in config:
        vectorize_config["color_tolerance"] = float(config["color_tolerance"])

    host_kind = host[0]
    if host_kind == "rect":
        host_primitive = _rect_primitive("host", host[1])
    elif host_kind == "circle":
        host_primitive = _circle_primitive("host", host[1])
    else:
        host_primitive = _ring_primitive("host", host[1], host[2])

    cx, cy, radius, start_deg, end_deg, width = arc
    start = _arc_point_xy(cx, cy, radius, start_deg)
    apex = _arc_point_xy(cx, cy, radius, (start_deg + end_deg) / 2)
    end = _arc_point_xy(cx, cy, radius, end_deg)
    cutout_primitive = ExpectedPrimitive(
        id="cutout",
        expected_kinds=("stroke_path",),
        geometry_type="stroke",
        geometry={
            "centerline": (start, apex, end),
            "width": float(width),
            "is_cutout": True,
            "draw": ("arc_line", arc, cutout_color),
        },
        color="#ffffff",
        color_tolerance=12.0,
        # Gap endpoints quantize softly inside a 2 px slit; the visual gates
        # keep the export honest while the centerline tolerance absorbs it.
        coordinate_tolerance=3.0,
        min_bbox_iou=0.55,
    )

    primitives = [host_primitive, cutout_primitive]
    if extra is not None:
        primitives.append(
            _circle_primitive("foreground", extra[1], color=extra[2])
        )

    is_ring = host_kind == "ring"
    return PrimitiveSpec(
        id=case_id,
        family=family,
        variant=variant,
        expected_kinds=host_primitive.expected_kinds,
        geometry_type=host_primitive.geometry_type,
        geometry=host_primitive.geometry,
        color=host_primitive.color,
        expected_primitives=tuple(primitives),
        compare_cutout_exports=True,
        vectorize_config=vectorize_config,
        draw=lambda draw, primitives=tuple(primitives): _draw_expected_primitives(
            draw,
            primitives,
        ),
        max_anchor_count=len(primitives),
        coordinate_tolerance=2.0,
        max_raster_l1_error=0.1 if is_ring else 0.035,
        max_raster_edge_error=0.08 if is_ring else 0.035,
        min_bbox_iou=0.78,
    )


def _rect_primitive(
    primitive_id: str,
    box: tuple[int, int, int, int],
    *,
    color: str = BLUE,
) -> ExpectedPrimitive:
    x0, y0, x1, y1 = box
    return ExpectedPrimitive(
        id=primitive_id,
        expected_kinds=("rect", "quad"),
        geometry_type="quad",
        geometry={
            "corners": ((x0, y0), (x1, y0), (x1, y1), (x0, y1)),
            "draw": ("rect", box),
        },
        color=color,
        min_bbox_iou=0.88,
    )


def _circle_primitive(
    primitive_id: str,
    box: tuple[int, int, int, int],
    *,
    color: str = BLUE,
) -> ExpectedPrimitive:
    x0, y0, x1, y1 = box
    return ExpectedPrimitive(
        id=primitive_id,
        expected_kinds=("circle",),
        geometry_type="circle",
        geometry={
            "cx": (x0 + x1) / 2,
            "cy": (y0 + y1) / 2,
            "r": (x1 - x0) / 2,
            "draw": ("circle", box),
        },
        color=color,
        coordinate_tolerance=1.75,
        min_bbox_iou=0.86,
    )


def _stroke_primitive(
    primitive_id: str,
    line: tuple[int, int, int, int],
    width: int,
    *,
    color: str = BLUE,
    tolerance: float = 1.75,
) -> ExpectedPrimitive:
    x0, y0, x1, y1 = line
    centerline = _expected_line_centerline(line, width)
    return ExpectedPrimitive(
        id=primitive_id,
        expected_kinds=("stroke_polyline",),
        geometry_type="stroke",
        geometry={
            "centerline": centerline,
            "width": float(width),
            "draw": ("stroke", line, width),
        },
        color=color,
        coordinate_tolerance=tolerance,
        min_bbox_iou=0.76,
    )


def _ring_primitive(
    primitive_id: str,
    box: tuple[int, int, int, int],
    width: int,
    *,
    color: str = BLUE,
) -> ExpectedPrimitive:
    x0, y0, x1, y1 = box
    outer_radius = (x1 - x0) / 2
    return ExpectedPrimitive(
        id=primitive_id,
        expected_kinds=("stroke_circle",),
        geometry_type="stroke_circle",
        geometry={
            "cx": (x0 + x1) / 2,
            "cy": (y0 + y1) / 2,
            "r": outer_radius - width / 2 + 0.5,
            "width": width + 0.5,
            "draw": ("ring", box, width),
        },
        color=color,
        coordinate_tolerance=2.0,
        min_bbox_iou=0.78,
    )


def _quad_primitive(
    primitive_id: str,
    corners: tuple[tuple[int, int], tuple[int, int], tuple[int, int], tuple[int, int]],
    *,
    color: str = BLUE,
) -> ExpectedPrimitive:
    return ExpectedPrimitive(
        id=primitive_id,
        expected_kinds=("quad",),
        geometry_type="quad",
        geometry={"corners": corners, "draw": ("quad", corners)},
        color=color,
        coordinate_tolerance=1.75,
        min_bbox_iou=0.86,
    )


def _arc_primitive(
    primitive_id: str,
    arc: ArcParams,
    *,
    color: str = BLUE,
) -> ExpectedPrimitive:
    cx, cy, radius, start_deg, end_deg, width = arc
    start = _arc_point_xy(cx, cy, radius, start_deg)
    end = _arc_point_xy(cx, cy, radius, end_deg)
    apex = _arc_point_xy(cx, cy, radius, (start_deg + end_deg) / 2)
    chord_mid = ((start[0] + end[0]) / 2, (start[1] + end[1]) / 2)
    bow = hypot(apex[0] - chord_mid[0], apex[1] - chord_mid[1])
    return ExpectedPrimitive(
        id=primitive_id,
        expected_kinds=("arc",),
        geometry_type="arc",
        geometry={
            "start": start,
            "end": end,
            "apex": apex,
            "bow": bow,
            "bow_direction": _bow_direction(apex, chord_mid),
            "width": float(width),
            "draw": ("arc_line", arc, color),
        },
        color=color,
        coordinate_tolerance=2.5,
        min_bbox_iou=0.66,
    )


def _curve_primitive(
    primitive_id: str,
    controls: CurveControls,
    width: int,
    *,
    color: str = BLUE,
) -> ExpectedPrimitive:
    samples = _bezier_samples(controls, steps=32)
    return ExpectedPrimitive(
        id=primitive_id,
        expected_kinds=("stroke_path",),
        geometry_type="stroke_path",
        geometry={
            "curve_samples": samples,
            "start": samples[0],
            "end": samples[-1],
            "width": float(width),
            "width_tolerance": 1.5,
            "cap_style": "round",
            "max_control_points": CURVE_MAX_CONTROL_POINTS,
            "draw": ("smooth_curve", controls, width, color),
        },
        color=color,
        coordinate_tolerance=2.75,
        min_bbox_iou=0.62,
    )


def _ellipse_primitive(
    primitive_id: str,
    box: tuple[int, int, int, int],
    *,
    color: str = BLUE,
) -> ExpectedPrimitive:
    x0, y0, x1, y1 = box
    return ExpectedPrimitive(
        id=primitive_id,
        expected_kinds=("ellipse",),
        geometry_type="ellipse",
        geometry={
            "cx": (x0 + x1) / 2,
            "cy": (y0 + y1) / 2,
            "rx": (x1 - x0) / 2,
            "ry": (y1 - y0) / 2,
            "draw": ("ellipse_fill", box),
        },
        color=color,
        coordinate_tolerance=1.75,
        min_bbox_iou=0.85,
    )


def _cutout_stroke_primitive(
    primitive_id: str,
    line: tuple[int, int, int, int],
    width: int,
    *,
    tolerance: float = 1.75,
) -> ExpectedPrimitive:
    primitive = _stroke_primitive(
        primitive_id,
        line,
        width,
        color="#ffffff",
        tolerance=tolerance,
    )
    geometry = dict(primitive.geometry)
    geometry["is_cutout"] = True
    return ExpectedPrimitive(
        id=primitive.id,
        expected_kinds=primitive.expected_kinds,
        geometry_type=primitive.geometry_type,
        geometry=geometry,
        color=primitive.color,
        coordinate_tolerance=primitive.coordinate_tolerance,
        min_bbox_iou=0.7,
    )


def _expected_line_centerline(
    line: tuple[int, int, int, int],
    width: int,
) -> tuple[tuple[float, float], tuple[float, float]]:
    x0, y0, x1, y1 = line
    if y0 == y1:
        center_y = y0 + (0.5 if width % 2 == 0 else 0.0)
        return (float(x0), center_y), (float(x1), center_y)
    if x0 == x1:
        center_x = x0 + (0.5 if width % 2 == 0 else 0.0)
        return (center_x, float(y0)), (center_x, float(y1))
    return (float(x0), float(y0)), (float(x1), float(y1))


def _draw_expected_primitives(
    draw: ImageDraw.ImageDraw,
    primitives: tuple[ExpectedPrimitive, ...],
) -> None:
    for primitive in primitives:
        draw_instruction = primitive.geometry.get("draw")
        if not isinstance(draw_instruction, tuple):
            continue
        kind = draw_instruction[0]
        if kind == "rect":
            draw.rectangle(draw_instruction[1], fill=primitive.color)
        elif kind == "circle":
            draw.ellipse(draw_instruction[1], fill=primitive.color)
        elif kind == "stroke":
            _, line, width = draw_instruction
            draw.line(line, fill=primitive.color, width=width)
        elif kind == "ring":
            _, box, width = draw_instruction
            draw.ellipse(box, outline=primitive.color, width=width)
        elif kind == "quad":
            draw.polygon(draw_instruction[1], fill=primitive.color)
        elif kind == "arc_line":
            _, arc, color = draw_instruction
            _draw_arc_line(draw, arc, color)
        elif kind == "smooth_curve":
            _, controls, width, color = draw_instruction
            _draw_smooth_curve(draw, controls, width, "round", color=color)
        elif kind == "ellipse_fill":
            draw.ellipse(draw_instruction[1], fill=primitive.color)


def _draw_arc_line(
    draw: ImageDraw.ImageDraw,
    arc: CutoutArc,
    color: str,
) -> None:
    cx, cy, radius, start_deg, end_deg, width = arc
    steps = max(24, ceil(radius * abs(end_deg - start_deg) / 360 * 2 * pi))
    points = [
        _arc_point_xy(cx, cy, radius, start_deg + (end_deg - start_deg) * index / steps)
        for index in range(steps + 1)
    ]
    draw.line(points, fill=color, width=width, joint="curve")


def check_primitive_quality(
    *,
    output_dir: str | Path | None = None,
    cases: Iterable[str] = (),
    filter_pattern: str | None = None,
    refine: bool = False,
    refinement_iterations: int = 1,
) -> dict[str, Any]:
    requested_cases = tuple(cases)
    output_root = Path(output_dir) if output_dir is not None else None
    if output_root is not None:
        output_root.mkdir(parents=True, exist_ok=True)
    specs = _selected_specs(
        primitive_specs(),
        requested_cases=requested_cases,
        filter_pattern=filter_pattern,
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        case_results = [
            _run_case(
                spec,
                output_root=output_root,
                temp_root=temp_root,
                refine=refine,
                refinement_iterations=refinement_iterations,
            )
            for spec in specs
        ]

    failed = [case for case in case_results if not case["ok"]]
    family_summaries = _family_summaries(case_results)
    anchor_kind_counts = _aggregated_anchor_kind_counts(case_results)
    return {
        "schema_version": 1,
        "case_count": len(case_results),
        "passed_count": len(case_results) - len(failed),
        "failed_count": len(failed),
        "ok": bool(case_results) and not failed,
        "selected_case_ids": [case["id"] for case in case_results],
        "family_summaries": family_summaries,
        "anchor_kind_counts": anchor_kind_counts,
        "curve_anchor_kind_counts": {
            kind: anchor_kind_counts.get(kind, 0)
            for kind in CURVE_ANCHOR_KINDS
        },
        "svg_raster_capability": svg_raster_capability(),
        "selection": {
            "cases": list(requested_cases),
            "filter": filter_pattern,
            "refine": refine,
            "refinement_iterations": refinement_iterations,
        },
        "cases": case_results,
    }


def write_primitive_quality_report(
    *,
    output: str | Path,
    output_dir: str | Path | None = None,
    markdown: str | Path | None = None,
    cases: Iterable[str] = (),
    filter_pattern: str | None = None,
    refine: bool = False,
    refinement_iterations: int = 1,
) -> dict[str, Any]:
    report = check_primitive_quality(
        output_dir=output_dir,
        cases=cases,
        filter_pattern=filter_pattern,
        refine=refine,
        refinement_iterations=refinement_iterations,
    )
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    if markdown is not None:
        markdown_path = Path(markdown)
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(render_primitive_quality_markdown(report), encoding="utf-8")
    return report


def render_primitive_quality_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Morphea Primitive Quality Check",
        "",
        f"- Cases: {report.get('case_count', 0)}",
        f"- Passed: {report.get('passed_count', 0)}",
        f"- Failed: {report.get('failed_count', 0)}",
        f"- OK: `{str(report.get('ok', False)).lower()}`",
        "",
        "| Family | Cases | Passed | Failed |",
        "| --- | ---: | ---: | ---: |",
    ]
    for family in report.get("family_summaries", []):
        lines.append(
            "| "
            f"`{family.get('family')}` | "
            f"{family.get('case_count', 0)} | "
            f"{family.get('passed_count', 0)} | "
            f"{family.get('failed_count', 0)} |"
        )
    lines.extend(
        [
            "",
        "| Case | OK | Actual | L1 | Edge | SVG L1 | SVG Edge | IoU | Failures |",
        "| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for case in report.get("cases", []):
        metrics = case.get("metrics", {})
        svg_metrics = case.get("svg_metrics") or {}
        geometry = case.get("geometry", {})
        failures = case.get("failures", [])
        failure_categories = case.get("failure_categories", [])
        failure_text = "; ".join(failures) if failures else "n/a"
        if failure_categories:
            failure_text = f"{', '.join(failure_categories)}: {failure_text}"
        lines.append(
            "| "
            f"`{case.get('id')}` | "
            f"`{str(case.get('ok', False)).lower()}` | "
            f"`{case.get('actual_kind', 'n/a')}` | "
            f"{metrics.get('raster_l1_error', 'n/a')} | "
            f"{metrics.get('raster_edge_error', 'n/a')} | "
            f"{svg_metrics.get('svg_raster_l1_error', 'n/a')} | "
            f"{svg_metrics.get('svg_raster_edge_error', 'n/a')} | "
            f"{geometry.get('bbox_iou', 'n/a')} | "
            f"{failure_text} |"
        )
    return "\n".join(lines) + "\n"


def _selected_specs(
    specs: tuple[PrimitiveSpec, ...],
    *,
    requested_cases: tuple[str, ...],
    filter_pattern: str | None,
) -> tuple[PrimitiveSpec, ...]:
    selected = specs
    if requested_cases:
        requested = set(requested_cases)
        selected = tuple(
            spec
            for spec in selected
            if spec.id in requested
        )
    if filter_pattern:
        selected = tuple(
            spec
            for spec in selected
            if fnmatch(spec.id, filter_pattern)
            or fnmatch(_spec_family(spec), filter_pattern)
        )
    return selected


def _aggregated_anchor_kind_counts(
    cases: list[dict[str, Any]],
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for case in cases:
        case_counts = case.get("anchor_kind_counts", {})
        if not isinstance(case_counts, dict):
            continue
        for kind, count in case_counts.items():
            counts[str(kind)] = counts.get(str(kind), 0) + int(count)
    return dict(sorted(counts.items()))


def _family_summaries(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_family: dict[str, list[dict[str, Any]]] = {}
    for case in cases:
        by_family.setdefault(str(case.get("family", case.get("id"))), []).append(case)
    summaries = []
    for family in sorted(by_family):
        family_cases = by_family[family]
        failed = [case for case in family_cases if not case["ok"]]
        summaries.append(
            {
                "family": family,
                "case_count": len(family_cases),
                "passed_count": len(family_cases) - len(failed),
                "failed_count": len(failed),
                "ok": not failed,
            }
        )
    return summaries


def _run_case(
    spec: PrimitiveSpec,
    *,
    output_root: Path | None,
    temp_root: Path,
    refine: bool,
    refinement_iterations: int,
) -> dict[str, Any]:
    case_root = output_root / spec.id if output_root is not None else temp_root / spec.id
    case_root.mkdir(parents=True, exist_ok=True)
    input_path = case_root / "input.png"
    source = _draw_source(spec)
    source.save(input_path)

    scene = scene_from_flat_color_image(
        input_path,
        min_area=spec.min_area,
        **spec.vectorize_config,
    )
    manifest = scene.to_manifest()
    preview = render_manifest_image(manifest, background=spec.background)
    metrics = raster_fidelity_metrics(source=source, rendered=preview)
    manifest.setdefault("metrics", {}).update(metrics)

    svg_path = case_root / "output.svg"
    debug_svg_path = case_root / "debug.svg"
    svg_render_path = case_root / "svg-render.png"
    negative_mask_svg_path = case_root / "negative-mask.svg"
    manifest_path = case_root / "manifest.json"
    preview_path = case_root / "preview.png"
    overlay_svg = scene.to_svg(SvgStyle(cutout_strategy="overlay_stroke"))
    svg_metrics = svg_raster_metrics(
        source=source,
        svg_text=overlay_svg,
        preview=preview,
        background=spec.background,
    )
    manifest["metrics"].update(
        {
            key: value
            for key, value in svg_metrics.items()
            if key != "svg_raster_backend"
        }
    )
    if output_root is not None:
        svg_path.write_text(overlay_svg, encoding="utf-8")
        debug_svg_path.write_text(scene.to_debug_svg(), encoding="utf-8")
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        preview.save(preview_path)
        rasterize_svg(overlay_svg, background=spec.background).save(svg_render_path)

    case = _evaluate_case(spec, manifest, metrics, svg_metrics=svg_metrics)
    if spec.compare_cutout_exports:
        export_result = _compare_cutout_exports(
            spec=spec,
            scene=scene,
            manifest=manifest,
            overlay_svg=overlay_svg,
            negative_mask_svg_path=(
                negative_mask_svg_path if output_root is not None else None
            ),
        )
        case["export_comparison"] = export_result["summary"]
        if export_result["failure_details"]:
            case["failure_details"].extend(export_result["failure_details"])
            case["failures"].extend(
                failure["message"] for failure in export_result["failure_details"]
            )
            case["failure_categories"] = sorted(
                {
                    *case["failure_categories"],
                    *(
                        failure["category"]
                        for failure in export_result["failure_details"]
                    ),
                }
            )
            case["ok"] = False
    if refine:
        refinement_result = _run_refinement_gate(
            manifest=manifest,
            input_path=input_path,
            case_root=case_root,
            background=spec.background,
            source=source,
            iterations=refinement_iterations,
        )
        case["refinement"] = refinement_result["summary"]
        if refinement_result["failure_details"]:
            case["failure_details"].extend(refinement_result["failure_details"])
            case["failures"].extend(
                failure["message"] for failure in refinement_result["failure_details"]
            )
            case["failure_categories"] = sorted(
                {
                    *case["failure_categories"],
                    *(
                        failure["category"]
                        for failure in refinement_result["failure_details"]
                    ),
                }
            )
            case["ok"] = False
    if output_root is not None:
        case["artifacts"] = {
            "input": str(input_path),
            "output_svg": str(svg_path),
            "debug_svg": str(debug_svg_path),
            "manifest": str(manifest_path),
            "preview": str(preview_path),
            "svg_render": str(svg_render_path),
        }
        if spec.compare_cutout_exports:
            case["artifacts"]["negative_mask_svg"] = str(negative_mask_svg_path)
    return case


def _compare_cutout_exports(
    *,
    spec: PrimitiveSpec,
    scene: Any,
    manifest: dict[str, Any],
    overlay_svg: str,
    negative_mask_svg_path: Path | None,
) -> dict[str, Any]:
    negative_svg = scene.to_svg(SvgStyle(cutout_strategy="negative_mask"))
    if negative_mask_svg_path is not None:
        negative_mask_svg_path.write_text(negative_svg, encoding="utf-8")
    cutout_count = int(manifest.get("metrics", {}).get("cutout_anchor_count", 0))
    overlay_has_visible_cutout = 'stroke="#ffffff"' in overlay_svg
    overlay_has_mask = '<mask id="morphea-cutout-mask"' in overlay_svg
    negative_has_mask = '<mask id="morphea-cutout-mask"' in negative_svg
    negative_uses_mask_group = 'mask="url(#morphea-cutout-mask)"' in negative_svg
    negative_has_editable_mask_stroke = 'stroke="black"' in negative_svg
    negative_has_visible_cutout = 'stroke="#ffffff"' in negative_svg
    same_viewbox = _svg_viewbox(overlay_svg) == _svg_viewbox(negative_svg)
    failure_details: list[dict[str, str]] = []
    if cutout_count <= 0:
        failure_details.append(
            _failure("export_drift", f"{spec.id}: expected at least one cut-out anchor")
        )
    if not overlay_has_visible_cutout:
        failure_details.append(
            _failure("export_drift", f"{spec.id}: overlay export lacks visible cut-out stroke")
        )
    if overlay_has_mask:
        failure_details.append(
            _failure("export_drift", f"{spec.id}: overlay export unexpectedly contains mask")
        )
    if not negative_has_mask:
        failure_details.append(
            _failure("export_drift", f"{spec.id}: negative-mask export lacks mask definition")
        )
    if not negative_uses_mask_group:
        failure_details.append(
            _failure("export_drift", f"{spec.id}: negative-mask export lacks masked group")
        )
    if not negative_has_editable_mask_stroke:
        failure_details.append(
            _failure("export_drift", f"{spec.id}: negative-mask export lacks editable mask stroke")
        )
    if negative_has_visible_cutout:
        failure_details.append(
            _failure("export_drift", f"{spec.id}: negative-mask export still paints white cut-out")
        )
    if not same_viewbox:
        failure_details.append(
            _failure("export_drift", f"{spec.id}: cut-out exports use different viewBox")
        )
    return {
        "summary": {
            "ok": not failure_details,
            "cutout_anchor_count": cutout_count,
            "overlay_stroke": {
                "has_visible_cutout_stroke": overlay_has_visible_cutout,
                "has_mask": overlay_has_mask,
            },
            "negative_mask": {
                "has_mask": negative_has_mask,
                "uses_mask_group": negative_uses_mask_group,
                "has_editable_mask_stroke": negative_has_editable_mask_stroke,
                "has_visible_cutout_stroke": negative_has_visible_cutout,
            },
            "same_viewbox": same_viewbox,
        },
        "failure_details": failure_details,
    }


def _svg_viewbox(svg: str) -> str | None:
    marker = 'viewBox="'
    start = svg.find(marker)
    if start < 0:
        return None
    start += len(marker)
    end = svg.find('"', start)
    if end < 0:
        return None
    return svg[start:end]


def _run_refinement_gate(
    *,
    manifest: dict[str, Any],
    input_path: Path,
    case_root: Path,
    background: str,
    source: Image.Image,
    iterations: int,
) -> dict[str, Any]:
    manifest_path = case_root / "refinement-input.json"
    refined_path = case_root / "refined-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    refined_manifest = refine_manifest(
        manifest=manifest_path,
        output=refined_path,
        config=RefinementConfig(
            max_iterations=iterations,
            source_image=input_path,
        ),
    )
    refined_preview = render_manifest_image(refined_manifest, background=background)
    refined_metrics = raster_fidelity_metrics(source=source, rendered=refined_preview)
    initial_metrics = manifest.get("metrics", {})
    structure_audit = refined_manifest.get("refinement", {}).get("structure_audit", {})
    failure_details: list[dict[str, str]] = []
    if not structure_audit.get("structure_preserved", False):
        failure_details.append(_failure("refinement_drift", "refinement changed structure"))
    if not structure_audit.get("editability_preserved", False):
        failure_details.append(_failure("refinement_drift", "refinement changed editability"))
    if float(refined_metrics.get("raster_l1_error", 1.0)) > float(
        initial_metrics.get("raster_l1_error", 1.0)
    ) + 0.001:
        failure_details.append(_failure("refinement_drift", "refinement worsened raster_l1_error"))
    if float(refined_metrics.get("raster_edge_error", 1.0)) > float(
        initial_metrics.get("raster_edge_error", 1.0)
    ) + 0.001:
        failure_details.append(_failure("refinement_drift", "refinement worsened raster_edge_error"))
    return {
        "summary": {
            "iterations": iterations,
            "structure_audit": structure_audit,
            "initial_metrics": initial_metrics,
            "refined_metrics": refined_metrics,
            "ok": not failure_details,
        },
        "failure_details": failure_details,
    }


def _draw_source(spec: PrimitiveSpec) -> Image.Image:
    if spec.source_factory is not None:
        return spec.source_factory()
    image = Image.new("RGB", (spec.width, spec.height), spec.background)
    draw = ImageDraw.Draw(image)
    spec.draw(draw)
    return image


def _evaluate_case(
    spec: PrimitiveSpec,
    manifest: dict[str, Any],
    metrics: dict[str, Any],
    *,
    svg_metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    anchors = list(manifest.get("anchors", []))
    failure_details: list[dict[str, str]] = []
    for anchor in anchors:
        if anchor.get("kind") == "cubic_path" and not spec.allow_cubic_path:
            failure_details.append(
                _failure("fallback_path", "unexpected cubic_path fallback")
            )
        bounds = _anchor_visual_bounds(anchor)
        if _bounds_outside_canvas(
            bounds,
            width=spec.width,
            height=spec.height,
            tolerance=spec.coordinate_tolerance,
        ):
            failure_details.append(
                _failure(
                    "bounds_escape",
                    f"anchor bounds outside canvas: {_rounded_bounds(bounds)}",
                )
            )

    if not bool(metrics.get("raster_size_match", False)):
        failure_details.append(
            _failure("visual_drift", "rendered size does not match source")
        )
    if float(metrics.get("raster_l1_error", 1.0)) > spec.max_raster_l1_error:
        failure_details.append(
            _failure(
                "visual_drift",
                "raster_l1_error "
                f"{metrics.get('raster_l1_error')} exceeds {spec.max_raster_l1_error}",
            )
        )
    if float(metrics.get("raster_edge_error", 1.0)) > spec.max_raster_edge_error:
        failure_details.append(
            _failure(
                "visual_drift",
                "raster_edge_error "
                f"{metrics.get('raster_edge_error')} exceeds {spec.max_raster_edge_error}",
            )
        )
    if float(metrics.get("raster_alpha_error", 1.0)) > spec.max_raster_alpha_error:
        failure_details.append(
            _failure(
                "visual_drift",
                "raster_alpha_error "
                f"{metrics.get('raster_alpha_error')} exceeds {spec.max_raster_alpha_error}",
            )
        )
    if svg_metrics is not None:
        failure_details.extend(_svg_gate_failures(spec, svg_metrics))

    match_result = _match_expected_primitives(spec, anchors)
    failure_details.extend(match_result["failure_details"])
    group_result = _match_expected_groups(spec, manifest.get("groups", []))
    failure_details.extend(group_result["failure_details"])
    anchor = match_result["primary_anchor"]
    bbox_iou = match_result["primary_bbox_iou"]
    return _case_result(
        spec,
        anchor,
        metrics,
        failure_details,
        bbox_iou=bbox_iou,
        anchor_count=len(anchors),
        anchor_kind_counts=_anchor_kind_counts(anchors),
        svg_metrics=svg_metrics,
        matches=match_result["matches"],
        unmatched_expected=match_result["unmatched_expected"],
        unexpected_actual=match_result["unexpected_actual"],
        group_matches=group_result["matches"],
    )


def effective_svg_thresholds(spec: PrimitiveSpec) -> dict[str, float]:
    """Resolve the SVG raster gate thresholds for one fixture spec."""

    return {
        "svg_raster_l1_error": (
            spec.max_svg_raster_l1_error
            if spec.max_svg_raster_l1_error is not None
            else spec.max_raster_l1_error + SVG_L1_TOLERANCE_OFFSET
        ),
        "svg_raster_edge_error": (
            spec.max_svg_raster_edge_error
            if spec.max_svg_raster_edge_error is not None
            else spec.max_raster_edge_error + SVG_EDGE_TOLERANCE_OFFSET
        ),
        "svg_alpha_error": (
            spec.max_svg_alpha_error
            if spec.max_svg_alpha_error is not None
            else spec.max_raster_alpha_error + SVG_ALPHA_TOLERANCE_OFFSET
        ),
        "svg_vs_preview_l1_error": (
            spec.max_svg_vs_preview_l1_error
            if spec.max_svg_vs_preview_l1_error is not None
            else spec.max_raster_l1_error + SVG_VS_PREVIEW_TOLERANCE_OFFSET
        ),
    }


def _svg_gate_failures(
    spec: PrimitiveSpec,
    svg_metrics: dict[str, Any],
) -> list[dict[str, str]]:
    failures: list[dict[str, str]] = []
    if not bool(svg_metrics.get("svg_render_size_match", False)):
        failures.append(
            _failure("svg_visual_drift", "exported SVG render size does not match source")
        )
    thresholds = effective_svg_thresholds(spec)
    for key, threshold in thresholds.items():
        if key not in svg_metrics:
            continue
        value = float(svg_metrics.get(key, 1.0))
        if value > threshold:
            failures.append(
                _failure(
                    "svg_visual_drift",
                    f"{key} {value} exceeds {round(threshold, 6)}",
                )
            )
    return failures


def _anchor_kind_counts(anchors: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for anchor in anchors:
        kind = str(anchor.get("kind"))
        counts[kind] = counts.get(kind, 0) + 1
    return dict(sorted(counts.items()))


def _case_result(
    spec: PrimitiveSpec,
    anchor: dict[str, Any] | None,
    metrics: dict[str, Any],
    failure_details: list[dict[str, str]],
    *,
    bbox_iou: float,
    anchor_count: int,
    anchor_kind_counts: dict[str, int],
    svg_metrics: dict[str, Any] | None,
    matches: list[dict[str, Any]],
    unmatched_expected: list[dict[str, Any]],
    unexpected_actual: list[dict[str, Any]],
    group_matches: list[dict[str, Any]],
) -> dict[str, Any]:
    failures = [failure["message"] for failure in failure_details]
    categories = sorted({failure["category"] for failure in failure_details})
    return {
        "id": spec.id,
        "family": _spec_family(spec),
        "variant": spec.variant,
        "ok": not failure_details,
        "expected_kinds": list(spec.expected_kinds),
        "actual_kind": anchor.get("kind") if anchor is not None else None,
        "anchor_count": anchor_count,
        "anchor_kind_counts": anchor_kind_counts,
        "metrics": metrics,
        "svg_metrics": dict(svg_metrics) if svg_metrics is not None else None,
        "svg_thresholds": {
            key: round(value, 6)
            for key, value in effective_svg_thresholds(spec).items()
        },
        "geometry": {
            "expected_bounds": _rounded_bounds(_expected_visual_bounds(spec)),
            "actual_bounds": (
                _rounded_bounds(_anchor_visual_bounds(anchor))
                if anchor is not None
                else None
            ),
            "bbox_iou": round(bbox_iou, 6),
        },
        "geometry_diff": _geometry_diff(spec, anchor),
        "matches": matches,
        "unmatched_expected": unmatched_expected,
        "unexpected_actual": unexpected_actual,
        "group_matches": group_matches,
        "failures": failures,
        "failure_categories": categories,
        "failure_details": failure_details,
    }


def _match_expected_primitives(
    spec: PrimitiveSpec,
    anchors: list[dict[str, Any]],
) -> dict[str, Any]:
    expected_primitives = _expected_primitives(spec)
    unmatched_actual = set(range(len(anchors)))
    matches: list[dict[str, Any]] = []
    unmatched_expected: list[dict[str, Any]] = []
    failure_details: list[dict[str, str]] = []

    for expected in expected_primitives:
        expected_spec = _expected_to_spec(spec, expected)
        best: tuple[int, list[dict[str, str]], float] | None = None
        for index in sorted(unmatched_actual):
            anchor = anchors[index]
            candidate_failures, bbox_iou = _anchor_contract_failures(
                expected_spec,
                anchor,
            )
            score = (len(candidate_failures), -bbox_iou)
            if best is None or score < (len(best[1]), -best[2]):
                best = (index, candidate_failures, bbox_iou)
        if best is None:
            failure_details.append(
                _failure("wrong_count", f"expected primitive {expected.id} was not detected")
            )
            unmatched_expected.append({"id": expected.id, "reason": "no_actual_anchor"})
            continue
        index, candidate_failures, bbox_iou = best
        if candidate_failures:
            failure_details.append(
                _failure("wrong_count", f"expected primitive {expected.id} was not matched")
            )
            failure_details.extend(
                _prefix_failures(expected.id, candidate_failures)
            )
            unmatched_expected.append(
                {
                    "id": expected.id,
                    "best_actual_index": index,
                    "best_actual_kind": anchors[index].get("kind"),
                    "failure_categories": sorted(
                        {failure["category"] for failure in candidate_failures}
                    ),
                    "failures": [failure["message"] for failure in candidate_failures],
                }
            )
            continue
        unmatched_actual.remove(index)
        matches.append(
            {
                "expected_id": expected.id,
                "actual_index": index,
                "actual_kind": anchors[index].get("kind"),
                "bbox_iou": round(bbox_iou, 6),
                "geometry_diff": _geometry_diff(expected_spec, anchors[index]),
            }
        )

    unexpected_actual = [
        {
            "actual_index": index,
            "actual_kind": anchors[index].get("kind"),
            "bounds": _rounded_bounds(_anchor_visual_bounds(anchors[index])),
        }
        for index in sorted(unmatched_actual)
    ]
    for actual in unexpected_actual:
        failure_details.append(
            _failure(
                "wrong_count",
                "unexpected actual primitive "
                f"{actual['actual_kind']} at index {actual['actual_index']}",
            )
        )

    primary_anchor = anchors[matches[0]["actual_index"]] if matches else (anchors[0] if anchors else None)
    primary_bbox_iou = float(matches[0]["bbox_iou"]) if matches else 0.0
    return {
        "matches": matches,
        "unmatched_expected": unmatched_expected,
        "unexpected_actual": unexpected_actual,
        "failure_details": failure_details,
        "primary_anchor": primary_anchor,
        "primary_bbox_iou": primary_bbox_iou,
    }


def _match_expected_groups(
    spec: PrimitiveSpec,
    groups_value: object,
) -> dict[str, Any]:
    if not spec.expected_groups:
        return {"matches": [], "failure_details": []}
    groups = groups_value if isinstance(groups_value, list) else []
    unused = set(range(len(groups)))
    matches: list[dict[str, Any]] = []
    failure_details: list[dict[str, str]] = []
    for expected in spec.expected_groups:
        best_index = None
        best_failures: list[str] | None = None
        for index in sorted(unused):
            group = groups[index]
            if not isinstance(group, dict):
                continue
            failures = _group_contract_failures(expected, group)
            if best_failures is None or len(failures) < len(best_failures):
                best_index = index
                best_failures = failures
        if best_index is None or best_failures is None:
            failure_details.append(
                _failure("group_drift", f"expected group {expected.get('kind')} missing")
            )
            continue
        if best_failures:
            failure_details.extend(
                _failure("group_drift", failure)
                for failure in best_failures
            )
            continue
        unused.remove(best_index)
        group = groups[best_index]
        matches.append(
            {
                "expected_kind": expected.get("kind"),
                "group_index": best_index,
                "anchor_count": len(group.get("anchor_indexes", [])),
            }
        )
    return {"matches": matches, "failure_details": failure_details}


def _group_contract_failures(
    expected: dict[str, Any],
    group: dict[str, Any],
) -> list[str]:
    failures: list[str] = []
    if group.get("kind") != expected.get("kind"):
        failures.append(f"expected group kind {expected.get('kind')}, got {group.get('kind')}")
        return failures
    anchor_count = len(group.get("anchor_indexes", []))
    if "anchor_count" in expected and anchor_count != int(expected["anchor_count"]):
        failures.append(f"expected group anchor_count {expected['anchor_count']}, got {anchor_count}")
    if "min_anchor_count" in expected and anchor_count < int(expected["min_anchor_count"]):
        failures.append(f"expected group min_anchor_count {expected['min_anchor_count']}, got {anchor_count}")
    for key in (
        "row_count",
        "column_count",
        "color",
        "relation",
        "separation_policy",
        "base_color",
        "target_kind",
        "draw_order",
        "occlusion_policy",
    ):
        if key in expected and group.get(key) != expected[key]:
            failures.append(f"expected group {key} {expected[key]}, got {group.get(key)}")
    metrics = group.get("metrics", {})
    metrics = metrics if isinstance(metrics, dict) else {}
    for key in ("fragment_count", "occluder_count"):
        if key in expected and int(metrics.get(key, -1)) != int(expected[key]):
            failures.append(
                f"expected group {key} {expected[key]}, got {metrics.get(key)}"
            )
    return failures


def _anchor_contract_failures(
    expected_spec: PrimitiveSpec,
    anchor: dict[str, Any],
) -> tuple[list[dict[str, str]], float]:
    failures: list[dict[str, str]] = []
    actual_kind = str(anchor.get("kind"))
    if actual_kind not in expected_spec.expected_kinds:
        failures.append(
            _failure(
                "wrong_kind",
                "expected kind "
                f"{'/'.join(expected_spec.expected_kinds)}, got {actual_kind}",
            )
        )
    actual_color = str(anchor.get("color"))
    color_delta = _color_distance(actual_color, expected_spec.color)
    if color_delta > expected_spec.color_tolerance:
        failures.append(
            _failure(
                "color_drift",
                f"expected color {expected_spec.color}, got {anchor.get('color')}",
            )
        )
    expected_bounds = _expected_visual_bounds(expected_spec)
    actual_bounds = _anchor_visual_bounds(anchor)
    bbox_iou = _bbox_iou(expected_bounds, actual_bounds)
    if bbox_iou < expected_spec.min_bbox_iou:
        failures.append(
            _failure(
                "geometry_drift",
                f"bbox_iou {bbox_iou} below {expected_spec.min_bbox_iou}",
            )
        )
    failures.extend(_geometry_failures(expected_spec, anchor))
    expected_cutout = expected_spec.geometry.get("is_cutout")
    if expected_cutout is not None:
        stroke = anchor.get("stroke")
        actual_cutout = isinstance(stroke, dict) and bool(stroke.get("is_cutout"))
        if actual_cutout != bool(expected_cutout):
            failures.append(
                _failure(
                    "geometry_drift",
                    f"expected is_cutout {bool(expected_cutout)}, got {actual_cutout}",
                )
            )
    return failures, bbox_iou


def _expected_primitives(spec: PrimitiveSpec) -> tuple[ExpectedPrimitive, ...]:
    if spec.expected_primitives:
        return spec.expected_primitives
    return (
        ExpectedPrimitive(
            id=spec.id,
            expected_kinds=spec.expected_kinds,
            geometry_type=spec.geometry_type,
            geometry=spec.geometry,
            color=spec.color,
            color_tolerance=spec.color_tolerance,
            coordinate_tolerance=spec.coordinate_tolerance,
            min_bbox_iou=spec.min_bbox_iou,
        ),
    )


def _expected_to_spec(
    spec: PrimitiveSpec,
    expected: ExpectedPrimitive,
) -> PrimitiveSpec:
    return replace(
        spec,
        id=expected.id,
        expected_kinds=expected.expected_kinds,
        geometry_type=expected.geometry_type,
        geometry=expected.geometry,
        color=expected.color,
        color_tolerance=expected.color_tolerance,
        coordinate_tolerance=(
            expected.coordinate_tolerance
            if expected.coordinate_tolerance is not None
            else spec.coordinate_tolerance
        ),
        min_bbox_iou=(
            expected.min_bbox_iou
            if expected.min_bbox_iou is not None
            else spec.min_bbox_iou
        ),
        expected_primitives=(),
    )


def _prefix_failures(
    expected_id: str,
    failures: list[dict[str, str]],
) -> list[dict[str, str]]:
    return [
        _failure(failure["category"], f"{expected_id}: {failure['message']}")
        for failure in failures
    ]


def _geometry_failures(spec: PrimitiveSpec, anchor: dict[str, Any]) -> list[dict[str, str]]:
    if spec.geometry_type == "quad":
        return _quad_failures(spec, anchor)
    if spec.geometry_type == "circle":
        return _circle_failures(spec, anchor)
    if spec.geometry_type == "stroke_circle":
        return _circle_failures(spec, anchor) + _stroke_width_failures(spec, anchor)
    if spec.geometry_type == "stroke":
        return _stroke_failures(spec, anchor)
    if spec.geometry_type == "arc":
        return _arc_failures(spec, anchor)
    if spec.geometry_type == "stroke_path":
        return _stroke_path_failures(spec, anchor)
    if spec.geometry_type == "cubic_path":
        return _cubic_path_failures(spec, anchor)
    if spec.geometry_type == "ellipse":
        return _ellipse_geometry_failures(spec, anchor)
    if spec.geometry_type == "stroke_ellipse":
        return _ellipse_geometry_failures(spec, anchor) + _stroke_width_failures(
            spec,
            anchor,
        )
    return [_failure("geometry_drift", f"unsupported geometry contract {spec.geometry_type}")]


def _ellipse_geometry_failures(
    spec: PrimitiveSpec,
    anchor: dict[str, Any],
) -> list[dict[str, str]]:
    ellipse = anchor.get("ellipse")
    if not isinstance(ellipse, dict):
        return [_failure("geometry_drift", "missing ellipse geometry")]
    failures = []
    for key in ("cx", "cy", "rx", "ry"):
        actual = float(ellipse.get(key, 0.0))
        expected = float(spec.geometry[key])
        if abs(actual - expected) > spec.coordinate_tolerance:
            failures.append(
                _failure(
                    "geometry_drift",
                    f"{key} delta {round(abs(actual - expected), 6)} exceeds "
                    f"{spec.coordinate_tolerance}",
                )
            )
    return failures


def _stroke_path_failures(
    spec: PrimitiveSpec,
    anchor: dict[str, Any],
) -> list[dict[str, str]]:
    stroke = anchor.get("stroke")
    if not isinstance(stroke, dict):
        return [_failure("geometry_drift", "missing stroke path geometry")]
    centerline = tuple(
        (float(point.get("x", 0.0)), float(point.get("y", 0.0)))
        for point in stroke.get("centerline", [])
    )
    failures: list[dict[str, str]] = []
    max_controls = int(spec.geometry.get("max_control_points", CURVE_MAX_CONTROL_POINTS))
    if not 3 <= len(centerline) <= max_controls:
        failures.append(
            _failure(
                "editability_drift",
                f"expected 3..{max_controls} control points, got {len(centerline)}",
            )
        )
    if len(centerline) < 2:
        return failures

    curve = tuple(
        (float(x), float(y)) for x, y in spec.geometry["curve_samples"]
    )
    worst_control_distance = max(
        _point_polyline_distance(point, curve) for point in centerline
    )
    if worst_control_distance > spec.coordinate_tolerance:
        failures.append(
            _failure(
                "geometry_drift",
                "control point distance to curve "
                f"{round(worst_control_distance, 6)} exceeds {spec.coordinate_tolerance}",
            )
        )

    expected_start = tuple(float(value) for value in spec.geometry["start"])
    expected_end = tuple(float(value) for value in spec.geometry["end"])
    endpoint_error = min(
        max(
            _point_distance(centerline[0], expected_start),
            _point_distance(centerline[-1], expected_end),
        ),
        max(
            _point_distance(centerline[0], expected_end),
            _point_distance(centerline[-1], expected_start),
        ),
    )
    if endpoint_error > spec.coordinate_tolerance:
        failures.append(
            _failure(
                "geometry_drift",
                f"curve endpoint distance {round(endpoint_error, 6)} exceeds "
                f"{spec.coordinate_tolerance}",
            )
        )

    expected_cap = str(spec.geometry.get("cap_style", "round"))
    actual_cap = str(stroke.get("cap_style", "round"))
    if actual_cap != expected_cap:
        failures.append(
            _failure(
                "geometry_drift",
                f"expected cap_style {expected_cap}, got {actual_cap}",
            )
        )

    width_samples = [float(sample) for sample in stroke.get("width_samples", [])]
    actual_width = mean(width_samples) if width_samples else 1.0
    expected_width = float(spec.geometry["width"])
    width_tolerance = float(spec.geometry.get("width_tolerance", 1.5))
    if abs(actual_width - expected_width) > width_tolerance:
        failures.append(
            _failure(
                "geometry_drift",
                f"stroke width delta {round(abs(actual_width - expected_width), 6)} "
                f"exceeds {width_tolerance}",
            )
        )

    metrics = anchor.get("metrics", {})
    metrics = metrics if isinstance(metrics, dict) else {}
    jitter = float(metrics.get("curvature_jitter", 0.0))
    if jitter > CURVE_MAX_CURVATURE_JITTER:
        failures.append(
            _failure(
                "geometry_drift",
                f"curvature jitter {round(jitter, 6)} exceeds {CURVE_MAX_CURVATURE_JITTER}",
            )
        )
    width_variance = float(metrics.get("stroke_width_variance", 0.0))
    if width_variance > CURVE_MAX_WIDTH_VARIANCE:
        failures.append(
            _failure(
                "geometry_drift",
                f"stroke width variance {round(width_variance, 6)} exceeds "
                f"{CURVE_MAX_WIDTH_VARIANCE}",
            )
        )
    return failures


def _cubic_path_failures(
    spec: PrimitiveSpec,
    anchor: dict[str, Any],
) -> list[dict[str, str]]:
    path = anchor.get("path")
    if not isinstance(path, dict):
        return [_failure("geometry_drift", "missing organic path geometry")]
    failures: list[dict[str, str]] = []
    node_count = int(path.get("node_count", 0))
    max_nodes = int(spec.geometry.get("max_nodes", 16))
    if not 4 <= node_count <= max_nodes:
        failures.append(
            _failure(
                "editability_drift",
                f"expected 4..{max_nodes} path nodes, got {node_count}",
            )
        )
    if not str(path.get("fallback_reason", "")):
        failures.append(
            _failure("editability_drift", "organic path lacks fallback_reason")
        )
    metrics = anchor.get("metrics", {})
    metrics = metrics if isinstance(metrics, dict) else {}
    if "path_smoothness" not in metrics:
        failures.append(
            _failure("editability_drift", "organic path lacks path_smoothness metric")
        )
    return failures


def _point_polyline_distance(
    point: tuple[float, float],
    polyline: tuple[tuple[float, float], ...],
) -> float:
    return min(
        _point_segment_distance_xy(point, a, b)
        for a, b in zip(polyline, polyline[1:])
    )


def _point_segment_distance_xy(
    point: tuple[float, float],
    start: tuple[float, float],
    end: tuple[float, float],
) -> float:
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length_squared = dx * dx + dy * dy
    if length_squared <= 0:
        return _point_distance(point, start)
    t = ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / length_squared
    t = max(0.0, min(1.0, t))
    return _point_distance(point, (start[0] + dx * t, start[1] + dy * t))


def _arc_failures(spec: PrimitiveSpec, anchor: dict[str, Any]) -> list[dict[str, str]]:
    stroke = anchor.get("stroke")
    if not isinstance(stroke, dict):
        return [_failure("geometry_drift", "missing arc stroke geometry")]
    centerline = tuple(
        (float(point.get("x", 0.0)), float(point.get("y", 0.0)))
        for point in stroke.get("centerline", [])
    )
    if len(centerline) < 2:
        return [_failure("geometry_drift", "arc centerline has fewer than 2 points")]

    failures: list[dict[str, str]] = []
    expected_start = tuple(float(value) for value in spec.geometry["start"])
    expected_end = tuple(float(value) for value in spec.geometry["end"])
    actual_start = centerline[0]
    actual_end = centerline[-1]
    endpoint_error = min(
        max(
            _point_distance(actual_start, expected_start),
            _point_distance(actual_end, expected_end),
        ),
        max(
            _point_distance(actual_start, expected_end),
            _point_distance(actual_end, expected_start),
        ),
    )
    if endpoint_error > spec.coordinate_tolerance:
        failures.append(
            _failure(
                "geometry_drift",
                f"arc endpoint distance {round(endpoint_error, 6)} exceeds "
                f"{spec.coordinate_tolerance}",
            )
        )

    chord_mid = (
        (actual_start[0] + actual_end[0]) / 2,
        (actual_start[1] + actual_end[1]) / 2,
    )
    apex = max(
        centerline,
        key=lambda point: _point_segment_distance(point, actual_start, actual_end),
    )
    actual_bow = _point_segment_distance(apex, actual_start, actual_end)
    expected_bow = float(spec.geometry["bow"])
    bow_tolerance = spec.coordinate_tolerance + 0.5
    if abs(actual_bow - expected_bow) > bow_tolerance:
        failures.append(
            _failure(
                "geometry_drift",
                f"arc bow delta {round(abs(actual_bow - expected_bow), 6)} exceeds "
                f"{bow_tolerance}",
            )
        )
    expected_direction = str(spec.geometry["bow_direction"])
    actual_direction = _bow_direction(apex, chord_mid)
    if actual_direction != expected_direction:
        failures.append(
            _failure(
                "geometry_drift",
                f"arc bow direction expected {expected_direction}, got {actual_direction}",
            )
        )
    actual_cap = str(stroke.get("cap_style", "round"))
    if actual_cap != "round":
        failures.append(
            _failure("geometry_drift", f"expected cap_style round, got {actual_cap}")
        )
    failures.extend(_stroke_width_failures(spec, anchor))
    return failures


def _point_segment_distance(
    point: tuple[float, float],
    start: tuple[float, float],
    end: tuple[float, float],
) -> float:
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    denominator = hypot(dx, dy)
    if denominator == 0:
        return _point_distance(point, start)
    return abs(
        dy * point[0] - dx * point[1] + end[0] * start[1] - end[1] * start[0]
    ) / denominator


def _quad_failures(spec: PrimitiveSpec, anchor: dict[str, Any]) -> list[dict[str, str]]:
    quad = anchor.get("quad")
    if not isinstance(quad, dict):
        return [_failure("geometry_drift", "missing quad geometry")]
    actual = tuple(
        (float(point.get("x", 0.0)), float(point.get("y", 0.0)))
        for point in quad.get("corners", [])
    )
    expected = tuple(
        (float(x), float(y)) for x, y in spec.geometry["corners"]
    )
    if len(actual) != len(expected):
        return [
            _failure("geometry_drift", f"expected {len(expected)} corners, got {len(actual)}")
        ]
    failures = []
    for index, (left, right) in enumerate(zip(actual, expected, strict=True)):
        if _point_distance(left, right) > spec.coordinate_tolerance:
            failures.append(
                _failure(
                    "geometry_drift",
                    f"corner {index} distance "
                    f"{round(_point_distance(left, right), 6)} exceeds "
                    f"{spec.coordinate_tolerance}",
                )
            )
    failures.extend(_corner_radius_failures(spec, anchor))
    return failures


def _corner_radius_failures(
    spec: PrimitiveSpec,
    anchor: dict[str, Any],
) -> list[dict[str, str]]:
    if "corner_radius" not in spec.geometry:
        return []
    metrics = anchor.get("metrics", {})
    if not isinstance(metrics, dict) or "corner_radius" not in metrics:
        return [_failure("geometry_drift", "missing rounded corner radius")]
    actual = float(metrics.get("corner_radius", 0.0))
    expected = float(spec.geometry["corner_radius"])
    if abs(actual - expected) > spec.coordinate_tolerance:
        return [
            _failure(
                "geometry_drift",
                f"corner radius delta {round(abs(actual - expected), 6)} exceeds "
                f"{spec.coordinate_tolerance}",
            )
        ]
    return []


def _circle_failures(spec: PrimitiveSpec, anchor: dict[str, Any]) -> list[dict[str, str]]:
    circle = anchor.get("circle")
    if not isinstance(circle, dict):
        return [_failure("geometry_drift", "missing circle geometry")]
    failures = []
    for key in ("cx", "cy", "r"):
        actual = float(circle.get(key, 0.0))
        expected = float(spec.geometry[key])
        if abs(actual - expected) > spec.coordinate_tolerance:
            failures.append(
                _failure(
                    "geometry_drift",
                    f"{key} delta {round(abs(actual - expected), 6)} exceeds "
                    f"{spec.coordinate_tolerance}",
                )
            )
    return failures


def _stroke_width_failures(
    spec: PrimitiveSpec,
    anchor: dict[str, Any],
) -> list[dict[str, str]]:
    stroke = anchor.get("stroke")
    if not isinstance(stroke, dict):
        return [_failure("geometry_drift", "missing stroke geometry")]
    actual = _stroke_width(anchor)
    expected = float(spec.geometry["width"])
    if abs(actual - expected) > spec.coordinate_tolerance:
        return [
            _failure(
                "geometry_drift",
                f"stroke width delta {round(abs(actual - expected), 6)} exceeds "
                f"{spec.coordinate_tolerance}",
            )
        ]
    return []


def _stroke_failures(spec: PrimitiveSpec, anchor: dict[str, Any]) -> list[dict[str, str]]:
    stroke = anchor.get("stroke")
    if not isinstance(stroke, dict):
        return [_failure("geometry_drift", "missing stroke geometry")]
    actual = tuple(
        (float(point.get("x", 0.0)), float(point.get("y", 0.0)))
        for point in stroke.get("centerline", [])
    )
    expected = tuple(
        (float(x), float(y)) for x, y in spec.geometry["centerline"]
    )
    failures = []
    if len(actual) != len(expected):
        failures.append(
            _failure(
                "geometry_drift",
                f"expected {len(expected)} centerline points, got {len(actual)}",
            )
        )
    elif _oriented_line_error(actual, expected) > spec.coordinate_tolerance:
        failures.append(
            _failure(
                "geometry_drift",
                "centerline endpoint distance "
                f"{round(_oriented_line_error(actual, expected), 6)} exceeds "
                f"{spec.coordinate_tolerance}",
            )
        )
    expected_cap = spec.geometry.get("cap_style")
    if expected_cap is None and len(expected) == 2:
        expected_cap = "butt"
    actual_cap = str(stroke.get("cap_style", "round"))
    if expected_cap is not None and actual_cap != str(expected_cap):
        failures.append(
            _failure(
                "geometry_drift",
                f"expected cap_style {expected_cap}, got {actual_cap}",
            )
        )
    failures.extend(_stroke_width_failures(spec, anchor))
    return failures


def _expected_visual_bounds(spec: PrimitiveSpec) -> tuple[float, float, float, float]:
    if spec.geometry_type == "quad":
        points = spec.geometry["corners"]
        xs = [float(x) for x, _ in points]
        ys = [float(y) for _, y in points]
        return min(xs), min(ys), max(xs), max(ys)
    if spec.geometry_type in {"circle", "stroke_circle"}:
        cx = float(spec.geometry["cx"])
        cy = float(spec.geometry["cy"])
        radius = float(spec.geometry["r"])
        if spec.geometry_type == "stroke_circle":
            radius += float(spec.geometry["width"]) / 2
        return cx - radius, cy - radius, cx + radius, cy + radius
    if spec.geometry_type in {"ellipse", "stroke_ellipse"}:
        cx = float(spec.geometry["cx"])
        cy = float(spec.geometry["cy"])
        rx = float(spec.geometry["rx"])
        ry = float(spec.geometry["ry"])
        if spec.geometry_type == "stroke_ellipse":
            rx += float(spec.geometry["width"]) / 2
            ry += float(spec.geometry["width"]) / 2
        return cx - rx, cy - ry, cx + rx, cy + ry
    if spec.geometry_type == "stroke":
        points = spec.geometry["centerline"]
        width = float(spec.geometry["width"])
        return _stroke_visual_bounds(
            tuple((float(x), float(y)) for x, y in points),
            width,
            str(spec.geometry.get("cap_style", "butt")),
        )
    if spec.geometry_type == "arc":
        points = tuple(
            (float(x), float(y))
            for x, y in (
                spec.geometry["start"],
                spec.geometry["apex"],
                spec.geometry["end"],
            )
        )
        return _stroke_visual_bounds(points, float(spec.geometry["width"]), "round")
    if spec.geometry_type == "stroke_path":
        points = tuple(
            (float(x), float(y)) for x, y in spec.geometry["curve_samples"]
        )
        return _stroke_visual_bounds(points, float(spec.geometry["width"]), "round")
    if spec.geometry_type == "cubic_path":
        bounds = spec.geometry["bounds"]
        return (
            float(bounds[0]),
            float(bounds[1]),
            float(bounds[2]),
            float(bounds[3]),
        )
    return 0.0, 0.0, 0.0, 0.0


def _anchor_visual_bounds(anchor: dict[str, Any]) -> tuple[float, float, float, float]:
    path = anchor.get("path")
    if isinstance(path, dict) and path.get("points"):
        xs = [float(point.get("x", 0.0)) for point in path["points"]]
        ys = [float(point.get("y", 0.0)) for point in path["points"]]
        return min(xs), min(ys), max(xs), max(ys)
    ellipse = anchor.get("ellipse")
    if isinstance(ellipse, dict):
        rx = float(ellipse.get("rx", 0.0))
        ry = float(ellipse.get("ry", 0.0))
        if anchor.get("kind") == "stroke_ellipse":
            half = _stroke_width(anchor) / 2
            rx += half
            ry += half
        cx = float(ellipse.get("cx", 0.0))
        cy = float(ellipse.get("cy", 0.0))
        return cx - rx, cy - ry, cx + rx, cy + ry
    circle = anchor.get("circle")
    if isinstance(circle, dict):
        radius = float(circle.get("r", 0.0))
        if anchor.get("kind") == "stroke_circle":
            radius += _stroke_width(anchor) / 2
        cx = float(circle.get("cx", 0.0))
        cy = float(circle.get("cy", 0.0))
        return cx - radius, cy - radius, cx + radius, cy + radius
    quad = anchor.get("quad")
    if isinstance(quad, dict):
        points = quad.get("corners", [])
        xs = [float(point.get("x", 0.0)) for point in points]
        ys = [float(point.get("y", 0.0)) for point in points]
        if xs and ys:
            return min(xs), min(ys), max(xs), max(ys)
    stroke = anchor.get("stroke")
    if isinstance(stroke, dict):
        points = stroke.get("centerline", [])
        parsed_points = tuple(
            (float(point.get("x", 0.0)), float(point.get("y", 0.0)))
            for point in points
            if isinstance(point, dict)
        )
        if parsed_points:
            return _stroke_visual_bounds(
                parsed_points,
                _stroke_width(anchor),
                str(stroke.get("cap_style", "round")),
            )
    return 0.0, 0.0, 0.0, 0.0


def _stroke_width(anchor: dict[str, Any]) -> float:
    stroke = anchor.get("stroke")
    if not isinstance(stroke, dict):
        return 1.0
    samples = [float(sample) for sample in stroke.get("width_samples", [])]
    return mean(samples) if samples else 1.0


def _stroke_visual_bounds(
    points: tuple[tuple[float, float], ...],
    width: float,
    cap_style: str,
) -> tuple[float, float, float, float]:
    if len(points) < 2:
        x, y = points[0]
        pad = width / 2
        return x - pad, y - pad, x + pad, y + pad
    if cap_style != "butt" or len(points) != 2:
        xs = [x for x, _ in points]
        ys = [y for _, y in points]
        pad = width / 2
        return min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad

    (start_x, start_y), (end_x, end_y) = points
    dx = end_x - start_x
    dy = end_y - start_y
    length = (dx * dx + dy * dy) ** 0.5
    if length <= 0.0:
        pad = width / 2
        return start_x - pad, start_y - pad, start_x + pad, start_y + pad
    normal_x = -dy / length
    normal_y = dx / length
    pad = width / 2
    corners = (
        (start_x + normal_x * pad, start_y + normal_y * pad),
        (start_x - normal_x * pad, start_y - normal_y * pad),
        (end_x + normal_x * pad, end_y + normal_y * pad),
        (end_x - normal_x * pad, end_y - normal_y * pad),
    )
    xs = [x for x, _ in corners]
    ys = [y for _, y in corners]
    return min(xs), min(ys), max(xs), max(ys)


def _bounds_outside_canvas(
    bounds: tuple[float, float, float, float],
    *,
    width: int,
    height: int,
    tolerance: float,
) -> bool:
    min_x, min_y, max_x, max_y = bounds
    return (
        min_x < -tolerance
        or min_y < -tolerance
        or max_x > width - 1 + tolerance
        or max_y > height - 1 + tolerance
    )


def _bbox_iou(
    left: tuple[float, float, float, float],
    right: tuple[float, float, float, float],
) -> float:
    left_x0, left_y0, left_x1, left_y1 = left
    right_x0, right_y0, right_x1, right_y1 = right
    inter_x0 = max(left_x0, right_x0)
    inter_y0 = max(left_y0, right_y0)
    inter_x1 = min(left_x1, right_x1)
    inter_y1 = min(left_y1, right_y1)
    intersection = max(0.0, inter_x1 - inter_x0) * max(0.0, inter_y1 - inter_y0)
    left_area = max(0.0, left_x1 - left_x0) * max(0.0, left_y1 - left_y0)
    right_area = max(0.0, right_x1 - right_x0) * max(0.0, right_y1 - right_y0)
    union = left_area + right_area - intersection
    return round(intersection / union, 6) if union > 0 else 0.0


def _point_distance(
    left: tuple[float, float],
    right: tuple[float, float],
) -> float:
    return hypot(left[0] - right[0], left[1] - right[1])


def _oriented_line_error(
    actual: tuple[tuple[float, float], ...],
    expected: tuple[tuple[float, float], ...],
) -> float:
    forward = sum(
        _point_distance(left, right)
        for left, right in zip(actual, expected, strict=True)
    )
    reverse = sum(
        _point_distance(left, right)
        for left, right in zip(reversed(actual), expected, strict=True)
    )
    return min(forward, reverse) / len(expected)


def _rounded_bounds(bounds: tuple[float, float, float, float]) -> list[float]:
    return [round(value, 6) for value in bounds]


def _geometry_diff(
    spec: PrimitiveSpec,
    anchor: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "expected": {
            "kinds": list(spec.expected_kinds),
            "type": spec.geometry_type,
            "geometry": _rounded_geometry(spec.geometry),
        },
        "actual": _actual_geometry(anchor),
    }


def _actual_geometry(anchor: dict[str, Any] | None) -> dict[str, Any] | None:
    if anchor is None:
        return None
    circle = anchor.get("circle")
    if isinstance(circle, dict):
        return {
            "kind": anchor.get("kind"),
            "type": "circle",
            "geometry": {
                "cx": round(float(circle.get("cx", 0.0)), 6),
                "cy": round(float(circle.get("cy", 0.0)), 6),
                "r": round(float(circle.get("r", 0.0)), 6),
                "width": round(_stroke_width(anchor), 6)
                if anchor.get("kind") == "stroke_circle"
                else None,
            },
        }
    quad = anchor.get("quad")
    if isinstance(quad, dict):
        return {
            "kind": anchor.get("kind"),
            "type": "quad",
            "geometry": {
                "corners": _rounded_points(
                    (
                        (float(point.get("x", 0.0)), float(point.get("y", 0.0)))
                        for point in quad.get("corners", [])
                    )
                )
            },
        }
    stroke = anchor.get("stroke")
    if isinstance(stroke, dict):
        return {
            "kind": anchor.get("kind"),
            "type": "stroke",
            "geometry": {
                "centerline": _rounded_points(
                    (
                        (float(point.get("x", 0.0)), float(point.get("y", 0.0)))
                        for point in stroke.get("centerline", [])
                    )
                ),
                "width": round(_stroke_width(anchor), 6),
            },
        }
    return {"kind": anchor.get("kind"), "type": "unknown", "geometry": {}}


def _rounded_geometry(geometry: Geometry) -> Geometry:
    rounded: Geometry = {}
    for key, value in geometry.items():
        if key == "draw":
            continue
        if _is_number_tuple(value):
            rounded[key] = [round(float(item), 6) for item in value]
        elif isinstance(value, tuple):
            rounded[key] = _rounded_points(value)
        elif isinstance(value, float | int):
            rounded[key] = round(float(value), 6)
        else:
            rounded[key] = value
    return rounded


def _is_number_tuple(value: object) -> bool:
    return (
        isinstance(value, tuple)
        and bool(value)
        and all(isinstance(item, (int, float)) for item in value)
    )


def _rounded_points(points: Iterable[tuple[float, float]]) -> list[list[float]]:
    return [[round(float(x), 6), round(float(y), 6)] for x, y in points]


def _spec_family(spec: PrimitiveSpec) -> str:
    return spec.family or spec.id


def _failure(category: str, message: str) -> dict[str, str]:
    return {"category": category, "message": message}


def _color_distance(left: str, right: str) -> float:
    try:
        left_rgb = _hex_rgb(left)
        right_rgb = _hex_rgb(right)
    except ValueError:
        return float("inf")
    return (
        (left_rgb[0] - right_rgb[0]) ** 2
        + (left_rgb[1] - right_rgb[1]) ** 2
        + (left_rgb[2] - right_rgb[2]) ** 2
    ) ** 0.5


def _hex_rgb(color: str) -> tuple[int, int, int]:
    value = color.strip().removeprefix("#")
    if len(value) not in {6, 8}:
        raise ValueError("expected #rrggbb or #rrggbbaa color")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)
