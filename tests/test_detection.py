import unittest
from math import cos, pi, sin

from PIL import Image, ImageDraw

from morphea.anchors import AnchorKind
from morphea.anchors import Point
from morphea.detection import (
    AnchorThresholdConfig,
    _fit_circle_from_boundary,
    _organic_fallback_candidate,
    _stroke_polyline_centerline,
    _stroke_width_samples_along_centerline,
    detect_cutout_strokes_for_component,
    detect_primitive_anchors,
)
from morphea.detection import detect_cutout_strokes
from morphea.masks import BinaryMask, MaskComponent, connected_components


class MaskComponentTests(unittest.TestCase):
    def test_connected_components_splits_separate_shapes(self):
        mask = BinaryMask.from_rows(
            (
                "##....",
                "##....",
                "....##",
                "....##",
            )
        )

        components = connected_components(mask)

        self.assertEqual(len(components), 2)
        self.assertEqual([component.area for component in components], [4, 4])

    def test_connected_components_preserve_bounds_and_row_spans(self):
        mask = BinaryMask.from_rows(
            (
                "......",
                "..###.",
                "..##..",
                "......",
            )
        )

        component = connected_components(mask)[0]

        self.assertEqual(component.bounds, (2, 1, 4, 2))
        self.assertEqual(component.width, 3)
        self.assertEqual(component.height, 2)
        self.assertEqual(component.row_spans(), ((1, 2, 4), (2, 2, 3)))

    def test_mask_component_caches_derived_geometry(self):
        mask = BinaryMask.from_rows(
            (
                "......",
                "..###.",
                "..##..",
                "......",
            )
        )

        component = connected_components(mask)[0]

        self.assertIs(component.centroid, component.centroid)
        self.assertIs(component.boundary_pixels, component.boundary_pixels)
        self.assertIs(component.row_spans(), component.row_spans())

    def test_large_organic_fallback_respects_node_budget_cap(self):
        image = Image.new("RGB", (180, 180), "white")
        draw = ImageDraw.Draw(image)
        points = []
        for index in range(32):
            angle = index / 32 * 2 * pi
            radius = 68 if index % 2 == 0 else 48
            points.append(
                (
                    90 + radius * cos(angle),
                    90 + radius * sin(angle),
                )
            )
        draw.polygon(points, fill="black")
        component = connected_components(_mask_from_non_white_pixels(image))[0]

        anchor = _organic_fallback_candidate(component)

        self.assertEqual(anchor.kind, AnchorKind.CUBIC_PATH)
        self.assertLessEqual(anchor.node_count, 36)

    def test_connected_components_keep_diagonal_neighbors_connected(self):
        mask = BinaryMask.from_rows(
            (
                "#..",
                ".#.",
                "..#",
            )
        )

        components = connected_components(mask)

        self.assertEqual(len(components), 1)
        self.assertEqual(components[0].area, 3)


class PrimitiveDetectionTests(unittest.TestCase):
    def test_filled_dot_is_detected_as_circle_anchor(self):
        mask = BinaryMask.from_rows(
            (
                "...###...",
                "..#####..",
                ".#######.",
                "#########",
                "#########",
                "#########",
                ".#######.",
                "..#####..",
                "...###...",
            )
        )

        anchors = detect_primitive_anchors(mask)

        self.assertEqual(len(anchors), 1)
        self.assertEqual(anchors[0].kind, AnchorKind.CIRCLE)
        self.assertIn("circle_roundness_error", anchors[0].metrics)

    def test_pillow_style_filled_circle_regularizes_to_mask_bounds(self):
        image = Image.new("RGB", (64, 64), "white")
        draw = ImageDraw.Draw(image)
        draw.ellipse((12, 22, 32, 42), fill="black")
        mask = _mask_from_non_white_pixels(image)

        anchors = detect_primitive_anchors(mask, min_area=4)

        self.assertEqual(len(anchors), 1)
        self.assertEqual(anchors[0].kind, AnchorKind.CIRCLE)
        self.assertAlmostEqual(anchors[0].circle.center.x, 22.0)
        self.assertAlmostEqual(anchors[0].circle.center.y, 32.0)
        self.assertAlmostEqual(anchors[0].circle.radius, 10.0)

    def test_circle_threshold_config_can_reject_loose_circle_candidate(self):
        mask = BinaryMask.from_rows(
            (
                "...###...",
                "..#####..",
                ".#######.",
                "#########",
                "#########",
                "#########",
                ".#######.",
                "..#####..",
                "...###...",
            )
        )

        anchors = detect_primitive_anchors(
            mask,
            thresholds=AnchorThresholdConfig(circle_max_area_error=0.01),
        )

        self.assertNotEqual(anchors[0].kind, AnchorKind.CIRCLE)

    def test_connected_axis_cross_decomposes_to_two_strokes(self):
        image = Image.new("RGB", (64, 64), "white")
        draw = ImageDraw.Draw(image)
        draw.line((14, 32, 50, 32), fill="black", width=6)
        draw.line((32, 14, 32, 50), fill="black", width=6)
        mask = _mask_from_non_white_pixels(image)

        anchors = detect_primitive_anchors(mask, min_area=4)

        self.assertEqual(len(anchors), 2)
        self.assertEqual([anchor.kind for anchor in anchors], [
            AnchorKind.STROKE_POLYLINE,
            AnchorKind.STROKE_POLYLINE,
        ])
        self.assertTrue(
            all("compound_stroke_decomposition" in anchor.metrics for anchor in anchors)
        )

    def test_connected_diagonal_cross_decomposes_to_two_strokes(self):
        image = Image.new("RGB", (64, 64), "white")
        draw = ImageDraw.Draw(image)
        draw.line((16, 16, 48, 48), fill="black", width=5)
        draw.line((16, 48, 48, 16), fill="black", width=5)
        mask = _mask_from_non_white_pixels(image)

        anchors = detect_primitive_anchors(mask, min_area=4)

        self.assertEqual(len(anchors), 2)
        self.assertEqual([anchor.kind for anchor in anchors], [
            AnchorKind.STROKE_POLYLINE,
            AnchorKind.STROKE_POLYLINE,
        ])
        self.assertTrue(
            all("compound_stroke_decomposition" in anchor.metrics for anchor in anchors)
        )

    def test_axis_aligned_arrow_decomposes_to_shaft_and_head(self):
        image = Image.new("RGB", (64, 64), "white")
        draw = ImageDraw.Draw(image)
        draw.line((10, 32, 54, 32), fill="black", width=5)
        draw.line((10, 32, 22, 20), fill="black", width=5)
        draw.line((10, 32, 22, 44), fill="black", width=5)
        mask = _mask_from_non_white_pixels(image)

        anchors = detect_primitive_anchors(mask, min_area=4)
        kinds = [anchor.kind for anchor in anchors]

        self.assertEqual(kinds.count(AnchorKind.STROKE_POLYLINE), 1)
        self.assertEqual(kinds.count(AnchorKind.STROKE_PATH), 1)
        self.assertTrue(any("axis_arrow_head" in anchor.metrics for anchor in anchors))
        self.assertNotIn(AnchorKind.CUBIC_PATH, kinds)

    def test_four_way_move_decomposes_to_axes_and_arrowheads(self):
        image = Image.new("RGB", (64, 64), "white")
        draw = ImageDraw.Draw(image)
        draw.line((6, 32, 58, 32), fill="black", width=6)
        draw.line((32, 6, 32, 58), fill="black", width=6)
        draw.line((6, 32, 15, 23), fill="black", width=6)
        draw.line((6, 32, 15, 41), fill="black", width=6)
        draw.line((58, 32, 49, 23), fill="black", width=6)
        draw.line((58, 32, 49, 41), fill="black", width=6)
        draw.line((32, 6, 23, 15), fill="black", width=6)
        draw.line((32, 6, 41, 15), fill="black", width=6)
        draw.line((32, 58, 23, 49), fill="black", width=6)
        draw.line((32, 58, 41, 49), fill="black", width=6)
        mask = _mask_from_non_white_pixels(image)

        anchors = detect_primitive_anchors(mask, min_area=4)
        kinds = [anchor.kind for anchor in anchors]

        self.assertEqual(kinds.count(AnchorKind.STROKE_POLYLINE), 2)
        self.assertEqual(kinds.count(AnchorKind.STROKE_PATH), 4)
        self.assertTrue(
            all("compound_stroke_decomposition" in anchor.metrics for anchor in anchors)
        )
        self.assertNotIn(AnchorKind.CUBIC_PATH, kinds)

    def test_stroked_rounded_rect_decomposes_to_axis_grid_strokes(self):
        image = Image.new("RGB", (64, 64), "white")
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((5, 5, 58, 58), radius=6, outline="black", width=6)
        mask = _mask_from_non_white_pixels(image)

        anchors = detect_primitive_anchors(mask, min_area=4)

        self.assertEqual(len(anchors), 4)
        self.assertEqual(
            [anchor.kind for anchor in anchors],
            [
                AnchorKind.STROKE_POLYLINE,
                AnchorKind.STROKE_POLYLINE,
                AnchorKind.STROKE_POLYLINE,
                AnchorKind.STROKE_POLYLINE,
            ],
        )
        self.assertLessEqual(sum(anchor.node_count for anchor in anchors), 8)
        self.assertTrue(
            all("compound_stroke_decomposition" in anchor.metrics for anchor in anchors)
        )

    def test_axis_aligned_frame_grid_decomposes_to_four_strokes(self):
        image = Image.new("RGB", (64, 64), "white")
        draw = ImageDraw.Draw(image)
        draw.line((2, 16, 61, 16), fill="black", width=6)
        draw.line((2, 48, 61, 48), fill="black", width=6)
        draw.line((16, 2, 16, 61), fill="black", width=6)
        draw.line((48, 2, 48, 61), fill="black", width=6)
        mask = _mask_from_non_white_pixels(image)

        anchors = detect_primitive_anchors(mask, min_area=4)

        self.assertEqual(len(anchors), 4)
        self.assertTrue(all(anchor.kind == AnchorKind.STROKE_POLYLINE for anchor in anchors))
        self.assertEqual(sum(anchor.node_count for anchor in anchors), 8)
        self.assertTrue(
            any("axis_grid_horizontal" in anchor.metrics for anchor in anchors)
        )
        self.assertTrue(any("axis_grid_vertical" in anchor.metrics for anchor in anchors))

    def test_axis_grid_uses_local_band_extents(self):
        image = Image.new("RGB", (64, 64), "white")
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((5, 5, 58, 58), radius=6, outline="black", width=6)
        draw.line((24, 21, 24, 58), fill="black", width=6)
        mask = _mask_from_non_white_pixels(image)

        anchors = detect_primitive_anchors(mask, min_area=4)

        verticals = [
            anchor
            for anchor in anchors
            if "axis_grid_vertical" in anchor.metrics
            and anchor.stroke is not None
        ]
        internal = min(
            verticals,
            key=lambda anchor: abs(anchor.stroke.centerline[0].x - 24),
        )
        self.assertGreater(internal.stroke.centerline[0].y, 15)

    def test_axis_aligned_corner_stroke_is_detected_as_stroke_path(self):
        image = Image.new("RGB", (64, 64), "white")
        draw = ImageDraw.Draw(image)
        draw.line((8, 8, 8, 22), fill="black", width=6)
        draw.line((8, 8, 22, 8), fill="black", width=6)
        mask = _mask_from_non_white_pixels(image)

        anchors = detect_primitive_anchors(mask, min_area=4)

        self.assertEqual(len(anchors), 1)
        self.assertEqual(anchors[0].kind, AnchorKind.STROKE_PATH)
        self.assertEqual(len(anchors[0].stroke.centerline), 3)
        self.assertIn("axis_aligned_corner_stroke", anchors[0].metrics)

    def test_ring_with_attached_handle_decomposes_to_circle_and_stroke(self):
        image = Image.new("RGB", (64, 64), "white")
        draw = ImageDraw.Draw(image)
        draw.ellipse((5, 5, 51, 51), outline="black", width=6)
        draw.line((45, 45, 58, 58), fill="black", width=6)
        mask = _mask_from_non_white_pixels(image)

        anchors = detect_primitive_anchors(mask, min_area=4)
        kinds = [anchor.kind for anchor in anchors]

        self.assertIn(AnchorKind.STROKE_CIRCLE, kinds)
        self.assertIn(AnchorKind.STROKE_POLYLINE, kinds)
        self.assertTrue(
            any("circular_gap_compound" in anchor.metrics for anchor in anchors)
        )

    def test_ring_with_lower_diagonal_stubs_keeps_editable_strokes(self):
        image = Image.new("RGB", (64, 64), "white")
        draw = ImageDraw.Draw(image)
        draw.ellipse((10, 15, 54, 59), outline="black", width=5)
        draw.line((17, 50, 11, 56), fill="black", width=5)
        draw.line((47, 50, 53, 56), fill="black", width=5)
        draw.line((32, 29, 32, 40), fill="black", width=5)
        draw.line((32, 40, 42, 40), fill="black", width=5)
        mask = _mask_from_non_white_pixels(image)

        anchors = detect_primitive_anchors(mask, min_area=4)
        kinds = [anchor.kind for anchor in anchors]

        self.assertIn(AnchorKind.STROKE_CIRCLE, kinds)
        self.assertIn(AnchorKind.STROKE_PATH, kinds)
        self.assertNotIn(AnchorKind.CIRCLE, kinds)
        self.assertNotIn(AnchorKind.CUBIC_PATH, kinds)
        self.assertGreaterEqual(kinds.count(AnchorKind.STROKE_POLYLINE), 2)
        self.assertTrue(
            any("circular_gap_residual_stub" in anchor.metrics for anchor in anchors)
        )

    def test_small_thick_ring_prefers_stroke_circle_over_axis_grid(self):
        image = Image.new("RGB", (64, 64), "white")
        draw = ImageDraw.Draw(image)
        draw.ellipse((16, 16, 31, 31), outline="black", width=5)
        mask = _mask_from_non_white_pixels(image)

        anchors = detect_primitive_anchors(mask, min_area=4)

        self.assertEqual(len(anchors), 1)
        self.assertEqual(anchors[0].kind, AnchorKind.STROKE_CIRCLE)

    def test_connected_ring_nodes_decompose_to_circles_and_connectors(self):
        image = Image.new("RGB", (64, 64), "white")
        draw = ImageDraw.Draw(image)
        draw.ellipse((8, 24, 24, 40), outline="black", width=5)
        draw.ellipse((40, 6, 56, 22), outline="black", width=5)
        draw.ellipse((40, 42, 56, 58), outline="black", width=5)
        draw.line((21, 29, 43, 17), fill="black", width=5)
        draw.line((21, 35, 43, 47), fill="black", width=5)
        mask = _mask_from_non_white_pixels(image)

        anchors = detect_primitive_anchors(mask, min_area=4)
        kinds = [anchor.kind for anchor in anchors]

        self.assertGreaterEqual(kinds.count(AnchorKind.STROKE_CIRCLE), 3)
        self.assertGreaterEqual(kinds.count(AnchorKind.STROKE_POLYLINE), 2)

    def test_crosshair_decomposes_to_circle_and_radial_strokes(self):
        image = Image.new("RGB", (64, 64), "white")
        draw = ImageDraw.Draw(image)
        draw.ellipse((2, 2, 61, 61), outline="black", width=6)
        draw.line((2, 32, 16, 32), fill="black", width=6)
        draw.line((48, 32, 61, 32), fill="black", width=6)
        draw.line((32, 2, 32, 16), fill="black", width=6)
        draw.line((32, 48, 32, 61), fill="black", width=6)
        mask = _mask_from_non_white_pixels(image)

        anchors = detect_primitive_anchors(mask, min_area=4)
        kinds = [anchor.kind for anchor in anchors]

        self.assertIn(AnchorKind.STROKE_CIRCLE, kinds)
        self.assertGreaterEqual(kinds.count(AnchorKind.STROKE_POLYLINE), 4)

    def test_short_diagonal_capsule_is_detected_as_stroke(self):
        image = Image.new("RGB", (64, 64), "white")
        draw = ImageDraw.Draw(image)
        draw.line((45, 45, 58, 58), fill="black", width=6)
        mask = _mask_from_non_white_pixels(image)

        anchors = detect_primitive_anchors(mask, min_area=4)

        self.assertEqual(len(anchors), 1)
        self.assertEqual(anchors[0].kind, AnchorKind.STROKE_POLYLINE)
        self.assertLessEqual(anchors[0].stroke.width_samples[0], 8.0)

    def test_mouse_pointer_decomposes_to_closed_outline_and_diagonal_stroke(self):
        image = Image.new("RGB", (64, 64), "white")
        draw = ImageDraw.Draw(image)
        outline = [
            (9.8, 8.1),
            (8.1, 9.8),
            (25.4, 52.5),
            (28.0, 52.3),
            (32.1, 36.1),
            (36.0, 32.2),
            (52.3, 28.0),
            (52.5, 25.4),
            (9.8, 8.1),
        ]
        draw.line(outline, fill="black", width=5, joint="curve")
        draw.line((33.6, 33.6, 50.7, 50.7), fill="black", width=5)
        mask = _mask_from_non_white_pixels(image)

        anchors = detect_primitive_anchors(mask, min_area=4)
        kinds = [anchor.kind for anchor in anchors]

        self.assertEqual(kinds.count(AnchorKind.STROKE_PATH), 1)
        self.assertEqual(kinds.count(AnchorKind.STROKE_POLYLINE), 1)
        outline_anchor = next(anchor for anchor in anchors if anchor.kind == AnchorKind.STROKE_PATH)
        self.assertTrue(outline_anchor.stroke.closed)
        self.assertIn("mouse_pointer_outline", outline_anchor.metrics)

    def test_circle_fit_uses_boundary_samples_over_centroid_fallback(self):
        component = MaskComponent(
            pixels=frozenset({(3, 0), (0, 3), (-3, 0), (0, -3), (0, 0)}),
            centroid_hint=Point(10, 10),
            boundary_pixels_hint=frozenset({(3, 0), (0, 3), (-3, 0), (0, -3)}),
        )

        center, radius, residual = _fit_circle_from_boundary(
            component,
            fallback_radius=1.0,
        )

        self.assertAlmostEqual(center.x, 0.0)
        self.assertAlmostEqual(center.y, 0.0)
        self.assertAlmostEqual(radius, 3.0)
        self.assertAlmostEqual(residual, 0.0)

    def test_circle_ring_is_detected_as_stroke_circle_anchor(self):
        mask = BinaryMask.from_rows(
            (
                "...#######...",
                "..#########..",
                ".####...####.",
                "###.......###",
                "##.........##",
                "##.........##",
                "##.........##",
                "###.......###",
                ".####...####.",
                "..#########..",
                "...#######...",
            )
        )

        anchors = detect_primitive_anchors(mask)

        self.assertEqual(len(anchors), 1)
        self.assertEqual(anchors[0].kind, AnchorKind.STROKE_CIRCLE)
        self.assertGreater(anchors[0].stroke.width_samples[0], 1)

    def test_pillow_style_ring_prefers_stroke_circle_over_oversized_arc(self):
        image = Image.new("RGB", (64, 64), "white")
        draw = ImageDraw.Draw(image)
        draw.ellipse((18, 18, 46, 46), outline="black", width=4)
        mask = _mask_from_non_white_pixels(image)

        anchors = detect_primitive_anchors(mask, min_area=4)

        self.assertEqual(len(anchors), 1)
        self.assertEqual(anchors[0].kind, AnchorKind.STROKE_CIRCLE)
        self.assertLess(anchors[0].stroke.width_samples[0], 8.0)

    def test_straight_horizontal_component_is_detected_as_stroke(self):
        mask = BinaryMask.from_rows(
            (
                "............",
                ".##########.",
                ".##########.",
                "............",
            )
        )

        anchors = detect_primitive_anchors(mask)

        self.assertEqual(len(anchors), 1)
        self.assertEqual(anchors[0].kind, AnchorKind.STROKE_POLYLINE)
        self.assertIn("line_smoothness_error", anchors[0].metrics)
        self.assertEqual(anchors[0].stroke.width_samples, (2.0,))
        self.assertEqual(anchors[0].stroke.cap_style, "butt")
        self.assertEqual(anchors[0].stroke.join_style, "round")

    def test_pillow_style_horizontal_stroke_remains_two_point_stroke(self):
        image = Image.new("RGB", (64, 64), "white")
        draw = ImageDraw.Draw(image)
        draw.line((12, 32, 52, 32), fill="black", width=4)
        mask = _mask_from_non_white_pixels(image)

        anchors = detect_primitive_anchors(mask, min_area=4)

        self.assertEqual(len(anchors), 1)
        self.assertEqual(anchors[0].kind, AnchorKind.STROKE_POLYLINE)
        self.assertEqual(len(anchors[0].stroke.centerline), 2)
        self.assertEqual(anchors[0].stroke.width_samples, (4.0,))

    def test_pillow_style_diagonal_stroke_uses_flat_caps(self):
        image = Image.new("RGB", (64, 64), "white")
        draw = ImageDraw.Draw(image)
        draw.line((16, 54, 50, 10), fill="black", width=7)
        mask = _mask_from_non_white_pixels(image)

        anchors = detect_primitive_anchors(mask, min_area=4)

        self.assertEqual(len(anchors), 1)
        self.assertEqual(anchors[0].kind, AnchorKind.STROKE_POLYLINE)
        self.assertEqual(len(anchors[0].stroke.centerline), 2)
        self.assertEqual(anchors[0].stroke.cap_style, "butt")

    def test_round_capped_diagonal_stroke_keeps_round_caps(self):
        image = Image.new("RGB", (64, 64), "white")
        draw = ImageDraw.Draw(image)
        line = (16, 54, 50, 10)
        width = 7
        draw.line(line, fill="black", width=width)
        radius = width / 2
        for x, y in ((line[0], line[1]), (line[2], line[3])):
            draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill="black")
        mask = _mask_from_non_white_pixels(image)

        anchors = detect_primitive_anchors(mask, min_area=4)

        self.assertEqual(len(anchors), 1)
        self.assertEqual(anchors[0].kind, AnchorKind.STROKE_POLYLINE)
        self.assertEqual(anchors[0].stroke.cap_style, "round")

    def test_one_pixel_horizontal_stroke_remains_stroke(self):
        image = Image.new("RGB", (64, 64), "white")
        draw = ImageDraw.Draw(image)
        draw.line((8, 32, 56, 32), fill="black", width=1)
        mask = _mask_from_non_white_pixels(image)

        anchors = detect_primitive_anchors(mask, min_area=1)

        self.assertEqual(len(anchors), 1)
        self.assertEqual(anchors[0].kind, AnchorKind.STROKE_POLYLINE)
        self.assertEqual(len(anchors[0].stroke.centerline), 2)
        self.assertEqual(anchors[0].stroke.width_samples, (1.0,))

    def test_filled_wide_rectangle_prefers_rect_over_stroke(self):
        image = Image.new("RGB", (64, 64), "white")
        draw = ImageDraw.Draw(image)
        draw.rectangle((4, 24, 58, 34), fill="black")
        mask = _mask_from_non_white_pixels(image)

        anchors = detect_primitive_anchors(mask, min_area=4)

        self.assertEqual(len(anchors), 1)
        self.assertEqual(anchors[0].kind, AnchorKind.RECT)

    def test_skewed_quad_does_not_become_circle(self):
        image = Image.new("RGB", (64, 64), "white")
        draw = ImageDraw.Draw(image)
        draw.polygon(((20, 12), (50, 20), (44, 52), (12, 44)), fill="black")
        mask = _mask_from_non_white_pixels(image)

        anchors = detect_primitive_anchors(mask, min_area=4)

        self.assertEqual(len(anchors), 1)
        self.assertEqual(anchors[0].kind, AnchorKind.QUAD)

    def test_stroke_threshold_config_can_require_longer_thin_shapes(self):
        mask = BinaryMask.from_rows(
            (
                "............",
                ".##########.",
                ".##########.",
                "............",
            )
        )

        anchors = detect_primitive_anchors(
            mask,
            thresholds=AnchorThresholdConfig(stroke_min_length_width_ratio=10.0),
        )

        self.assertNotEqual(anchors[0].kind, AnchorKind.STROKE_POLYLINE)

    def test_straight_diagonal_component_is_detected_as_stroke(self):
        mask = BinaryMask.from_rows(
            (
                "#..........",
                ".#.........",
                "..#........",
                "...#.......",
                "....#......",
                ".....#.....",
                "......#....",
                ".......#...",
                "........#..",
                ".........#.",
                "..........#",
            )
        )

        anchors = detect_primitive_anchors(mask, min_area=4)

        self.assertEqual(len(anchors), 1)
        self.assertEqual(anchors[0].kind, AnchorKind.STROKE_POLYLINE)
        self.assertLess(anchors[0].metrics["line_smoothness_error"], 0.01)

    def test_straight_stroke_centerline_remains_two_points(self):
        component = MaskComponent(
            pixels=frozenset({(0, 0), (1, 0), (2, 0), (3, 0)}),
        )

        centerline = _stroke_polyline_centerline(
            component,
            (Point(0, 0), Point(3, 0)),
            stroke_width=1.0,
        )

        self.assertEqual(centerline, (Point(0, 0), Point(3, 0)))

    def test_curved_stroke_centerline_adds_control_point(self):
        component = MaskComponent(
            pixels=frozenset(
                {
                    (0, 0),
                    (1, 0),
                    (2, 2),
                    (3, 2),
                    (4, 0),
                    (5, 0),
                }
            ),
        )

        centerline = _stroke_polyline_centerline(
            component,
            (Point(0, 0), Point(5, 0)),
            stroke_width=1.0,
        )

        self.assertEqual(len(centerline), 3)
        self.assertIn(centerline[1], {Point(2, 2), Point(3, 2)})

    def test_curved_stroke_width_samples_follow_centerline_points(self):
        component = MaskComponent(
            pixels=frozenset(
                {
                    (0, 0),
                    (1, 0),
                    (2, 1),
                    (2, 2),
                    (2, 3),
                    (3, 1),
                    (3, 2),
                    (3, 3),
                    (4, 0),
                    (5, 0),
                }
            ),
        )

        samples = _stroke_width_samples_along_centerline(
            component,
            (Point(0, 0), Point(2.5, 2), Point(5, 0)),
            fallback_width=1.0,
        )

        self.assertEqual(len(samples), 3)
        self.assertGreater(samples[1], samples[0])
        self.assertGreater(samples[1], samples[2])

    def test_thin_curved_component_is_detected_as_arc(self):
        mask = BinaryMask.from_rows(
            (
                ".....#.....",
                "...##.##...",
                "..#.....#..",
                ".#.......#.",
            )
        )

        anchors = detect_primitive_anchors(mask, min_area=8)

        self.assertEqual(len(anchors), 1)
        self.assertEqual(anchors[0].kind, AnchorKind.ARC)
        self.assertEqual(len(anchors[0].stroke.centerline), 3)
        self.assertEqual(len(anchors[0].stroke.width_samples), 1)
        self.assertEqual(anchors[0].parameter_count, 7)
        self.assertIn("arc_bow_ratio", anchors[0].metrics)
        self.assertIn("arc_radius", anchors[0].metrics)
        self.assertIn("arc_center_x", anchors[0].metrics)
        self.assertIn("arc_theta_start", anchors[0].metrics)
        self.assertIn("arc_sweep", anchors[0].metrics)
        self.assertGreater(anchors[0].metrics["arc_radius"], 2.0)

    def test_filled_axis_aligned_block_is_detected_as_rect(self):
        mask = BinaryMask.from_rows(
            (
                "..........",
                "..######..",
                "..######..",
                "..######..",
                "..######..",
                "..........",
            )
        )

        anchors = detect_primitive_anchors(mask)

        self.assertEqual(len(anchors), 1)
        self.assertEqual(anchors[0].kind, AnchorKind.RECT)
        self.assertEqual(anchors[0].parameter_count, 4)
        self.assertIn("rect_fill_error", anchors[0].metrics)

    def test_filled_rounded_block_is_detected_as_rounded_rect(self):
        mask = BinaryMask.from_rows(
            (
                "..########..",
                ".##########.",
                "############",
                "############",
                ".##########.",
                "..########..",
            )
        )

        anchors = detect_primitive_anchors(mask)

        self.assertEqual(len(anchors), 1)
        self.assertEqual(anchors[0].kind, AnchorKind.ROUNDED_RECT)
        self.assertEqual(anchors[0].parameter_count, 5)
        self.assertIn("corner_radius", anchors[0].metrics)

    def test_perspective_tile_is_detected_as_quad_anchor(self):
        mask = BinaryMask.from_rows(
            (
                "....####....",
                "...######...",
                "..########..",
                ".##########.",
                "############",
            )
        )

        anchors = detect_primitive_anchors(mask)

        self.assertEqual(len(anchors), 1)
        self.assertEqual(anchors[0].kind, AnchorKind.QUAD)
        self.assertIn("quad_edge_straightness_error", anchors[0].metrics)
        self.assertEqual(anchors[0].metrics["quad_subtype_code"], 1.0)

    def test_shifted_equal_width_tile_is_marked_as_parallelogram(self):
        mask = BinaryMask.from_rows(
            (
                "...####....",
                "..####.....",
                ".####......",
            )
        )

        anchors = detect_primitive_anchors(mask)

        self.assertEqual(len(anchors), 1)
        self.assertEqual(anchors[0].kind, AnchorKind.QUAD)
        self.assertEqual(anchors[0].metrics["quad_subtype_code"], 2.0)

    def test_simple_quad_anchor_beats_generic_path_for_tile(self):
        mask = BinaryMask.from_rows(
            (
                "..######..",
                ".########.",
                "##########",
                "##########",
                ".########.",
            )
        )

        anchor = detect_primitive_anchors(mask)[0]

        self.assertEqual(anchor.kind, AnchorKind.QUAD)
        self.assertLess(anchor.node_count, 8)


class EllipseDetectionTests(unittest.TestCase):
    def test_capsule_is_not_detected_as_ellipse(self):
        image = Image.new("RGB", (64, 64), "white")
        draw = ImageDraw.Draw(image)
        # Stadium shape: straight long sides with semicircular ends.
        draw.rectangle((18, 24, 46, 40), fill="black")
        draw.ellipse((10, 24, 26, 40), fill="black")
        draw.ellipse((38, 24, 54, 40), fill="black")
        mask = _mask_from_non_white_pixels(image)

        anchors = detect_primitive_anchors(mask, min_area=4)

        self.assertEqual(len(anchors), 1)
        self.assertNotEqual(anchors[0].kind, AnchorKind.ELLIPSE)
        self.assertNotEqual(anchors[0].kind, AnchorKind.STROKE_ELLIPSE)

    def test_filled_oval_is_detected_as_ellipse(self):
        image = Image.new("RGB", (64, 64), "white")
        ImageDraw.Draw(image).ellipse((10, 20, 54, 44), fill="black")
        mask = _mask_from_non_white_pixels(image)

        anchors = detect_primitive_anchors(mask, min_area=4)

        self.assertEqual(len(anchors), 1)
        self.assertEqual(anchors[0].kind, AnchorKind.ELLIPSE)
        self.assertAlmostEqual(anchors[0].ellipse.center.x, 32.0, delta=1.0)
        self.assertAlmostEqual(anchors[0].ellipse.rx, 22.5, delta=1.0)
        self.assertAlmostEqual(anchors[0].ellipse.ry, 12.5, delta=1.0)

    def test_tiny_near_round_dot_stays_circle_after_downsample_quantization(self):
        image = Image.new("RGB", (16, 16), "white")
        ImageDraw.Draw(image).ellipse((3, 3, 11, 12), fill="black")
        mask = _mask_from_non_white_pixels(image)

        anchors = detect_primitive_anchors(mask, min_area=4)

        self.assertEqual(len(anchors), 1)
        self.assertEqual(anchors[0].kind, AnchorKind.CIRCLE)


class CutoutDetectionTests(unittest.TestCase):
    def test_horizontal_gap_inside_component_becomes_cutout_stroke(self):
        mask = BinaryMask.from_rows(
            (
                "############",
                "############",
                "###......###",
                "############",
                "############",
            )
        )

        cutouts = detect_cutout_strokes(mask, min_length=4)

        self.assertEqual(len(cutouts), 1)
        self.assertEqual(cutouts[0].kind, AnchorKind.STROKE_POLYLINE)
        self.assertEqual(cutouts[0].color, "#ffffff")
        self.assertTrue(cutouts[0].stroke.is_cutout)
        self.assertEqual(cutouts[0].stroke.width_samples, (1.0,))

    def test_diagonal_gap_inside_component_becomes_cutout_stroke(self):
        mask = BinaryMask.from_rows(
            (
                "############",
                "############",
                "##.#########",
                "###.########",
                "####.#######",
                "#####.######",
                "######.#####",
                "############",
                "############",
            )
        )

        cutouts = detect_cutout_strokes(mask, min_length=4)

        self.assertEqual(len(cutouts), 1)
        self.assertEqual(cutouts[0].kind, AnchorKind.STROKE_POLYLINE)
        self.assertTrue(cutouts[0].stroke.is_cutout)
        self.assertEqual(cutouts[0].color, "#ffffff")
        start, end = cutouts[0].stroke.centerline[:2]
        self.assertGreater(abs(end.x - start.x), 0)
        self.assertGreater(abs(end.y - start.y), 0)

    def test_component_cutout_detection_uses_existing_component(self):
        mask = BinaryMask.from_rows(
            (
                "############",
                "############",
                "##.#########",
                "###.########",
                "####.#######",
                "#####.######",
                "######.#####",
                "############",
                "############",
            )
        )
        component = connected_components(mask)[0]

        cutouts = detect_cutout_strokes_for_component(component, min_length=4)

        self.assertEqual(len(cutouts), 1)
        self.assertTrue(cutouts[0].stroke.is_cutout)
        start, end = cutouts[0].stroke.centerline[:2]
        self.assertGreater(abs(end.x - start.x), 0)
        self.assertGreater(abs(end.y - start.y), 0)

    def test_large_hole_is_not_treated_as_thin_cutout_stroke(self):
        mask = BinaryMask.from_rows(
            (
                "############",
                "############",
                "###......###",
                "###......###",
                "###......###",
                "###......###",
                "############",
                "############",
            )
        )

        self.assertEqual(detect_cutout_strokes(mask, min_length=4), ())


def _mask_from_non_white_pixels(image: Image.Image) -> BinaryMask:
    pixels = {
        (x, y)
        for y in range(image.height)
        for x in range(image.width)
        if image.getpixel((x, y)) != (255, 255, 255)
    }
    return BinaryMask(width=image.width, height=image.height, pixels=frozenset(pixels))


if __name__ == "__main__":
    unittest.main()
