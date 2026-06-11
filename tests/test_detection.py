import unittest

from curve.anchors import AnchorKind
from curve.detection import detect_primitive_anchors
from curve.detection import detect_cutout_strokes
from curve.masks import BinaryMask, connected_components


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


if __name__ == "__main__":
    unittest.main()
