import unittest

from curve.anchors import (
    AnchorCandidate,
    AnchorKind,
    CircleAnchor,
    Point,
    QuadAnchor,
    StrokeAnchor,
    choose_best_anchor,
    circle_roundness_error,
    cutout_anchor_error,
    enrich_anchor_metrics,
    line_smoothness_error,
    parallel_spacing_error,
    perspective_grid_consistency_error,
    quad_corner_consistency_error,
    simple_shape_priority_bonus,
    stroke_width_variance,
)


class AnchorMetricTests(unittest.TestCase):
    def test_perfect_circle_has_lower_roundness_error_than_egg_shape(self):
        perfect = CircleAnchor(
            center=Point(0, 0),
            radius=10,
            samples=(
                Point(10, 0),
                Point(0, 10),
                Point(-10, 0),
                Point(0, -10),
            ),
        )
        egg = CircleAnchor(
            center=Point(0, 0),
            radius=10,
            samples=(
                Point(12, 0),
                Point(0, 8),
                Point(-11, 0),
                Point(0, -9),
            ),
        )

        self.assertEqual(circle_roundness_error(perfect), 0.0)
        self.assertGreater(circle_roundness_error(egg), circle_roundness_error(perfect))

    def test_smooth_line_has_lower_error_than_jittery_line(self):
        smooth = (Point(0, 0), Point(10, 0), Point(20, 0), Point(30, 0))
        jittery = (Point(0, 0), Point(10, 4), Point(20, -3), Point(30, 2))

        self.assertLess(line_smoothness_error(smooth), line_smoothness_error(jittery))

    def test_constant_stroke_width_has_lower_variance(self):
        self.assertEqual(stroke_width_variance((4, 4, 4, 4)), 0.0)
        self.assertGreater(stroke_width_variance((2, 4, 7, 3)), 0.0)

    def test_cutout_anchor_uses_stroke_quality_rules(self):
        cutout = StrokeAnchor(
            centerline=(Point(0, 0), Point(10, 2), Point(20, -2), Point(30, 1)),
            width_samples=(2, 5, 2),
            is_cutout=True,
        )

        self.assertGreater(cutout_anchor_error(cutout), 0.0)

    def test_parallel_spacing_error_rewards_even_groups(self):
        even = (
            (Point(0, 0), Point(10, 0)),
            (Point(0, 5), Point(10, 5)),
            (Point(0, 10), Point(10, 10)),
        )
        uneven = (
            (Point(0, 0), Point(10, 0)),
            (Point(0, 4), Point(10, 4)),
            (Point(0, 13), Point(10, 13)),
        )

        self.assertLess(parallel_spacing_error(even), parallel_spacing_error(uneven))

    def test_quad_corner_consistency_penalizes_irregular_quad(self):
        regular = QuadAnchor(
            corners=(Point(0, 0), Point(10, 0), Point(10, 8), Point(0, 8))
        )
        irregular = QuadAnchor(
            corners=(Point(0, 0), Point(20, 0), Point(13, 4), Point(0, 12))
        )

        self.assertLess(
            quad_corner_consistency_error(regular),
            quad_corner_consistency_error(irregular),
        )

    def test_perspective_grid_consistency_rewards_matching_tiles(self):
        consistent = (
            QuadAnchor(
                corners=(Point(0, 0), Point(10, 0), Point(12, 10), Point(-2, 10))
            ),
            QuadAnchor(
                corners=(Point(10, 0), Point(20, 0), Point(22, 10), Point(12, 10))
            ),
        )
        inconsistent = (
            QuadAnchor(
                corners=(Point(0, 0), Point(10, 0), Point(12, 10), Point(-2, 10))
            ),
            QuadAnchor(
                corners=(Point(10, 0), Point(30, 0), Point(22, 10), Point(12, 10))
            ),
        )

        self.assertLess(
            perspective_grid_consistency_error(consistent),
            perspective_grid_consistency_error(inconsistent),
        )


class AnchorRankingTests(unittest.TestCase):
    def test_simple_shape_candidate_beats_jittery_path_with_small_fidelity_gain(self):
        circle = enrich_anchor_metrics(
            AnchorCandidate(
                kind=AnchorKind.CIRCLE,
                raster_error=0.08,
                node_count=1,
                parameter_count=3,
                circle=CircleAnchor(center=Point(0, 0), radius=10),
            )
        )
        path = AnchorCandidate(
            kind=AnchorKind.CUBIC_PATH,
            raster_error=0.04,
            node_count=24,
            parameter_count=48,
            metrics={"line_smoothness_error": 0.2},
        )

        self.assertIs(choose_best_anchor((circle, path)), circle)

    def test_stroke_priority_bonus_exists_for_stroke_circle(self):
        stroke_circle = AnchorCandidate(
            kind=AnchorKind.STROKE_CIRCLE,
            raster_error=0.0,
            node_count=1,
            parameter_count=4,
        )

        self.assertGreater(simple_shape_priority_bonus(stroke_circle), 0.0)


if __name__ == "__main__":
    unittest.main()

