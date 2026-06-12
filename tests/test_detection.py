import unittest

from PIL import Image, ImageDraw

from morphea.anchors import AnchorKind
from morphea.anchors import Point
from morphea.detection import (
    AnchorThresholdConfig,
    _fit_circle_from_boundary,
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
        self.assertEqual(len(anchors[0].stroke.width_samples), 3)
        self.assertEqual(anchors[0].parameter_count, 9)
        self.assertIn("arc_bow_ratio", anchors[0].metrics)

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
