import unittest

from morphea.images import _bounded_connected_components
from morphea.masks import BinaryMask, connected_components


class MaskComponentHintTests(unittest.TestCase):
    def test_connected_components_populates_geometry_hints(self):
        mask = BinaryMask.from_rows(
            [
                "##.",
                ".##",
                "...",
            ]
        )

        components = connected_components(mask)

        self.assertEqual(len(components), 1)
        component = components[0]
        self.assertEqual(component.bounds_hint, (0, 0, 2, 1))
        self.assertEqual(component.row_spans_hint, ((0, 0, 1), (1, 1, 2)))
        self.assertEqual(
            component.boundary_pixels_hint,
            frozenset({(0, 0), (1, 0), (1, 1), (2, 1)}),
        )
        self.assertIs(component.boundary_pixels, component.boundary_pixels_hint)
        self.assertAlmostEqual(component.centroid.x, 1.0)
        self.assertAlmostEqual(component.centroid.y, 0.5)

    def test_bounded_components_keeps_hints_for_retained_components(self):
        mask = BinaryMask.from_rows(
            [
                "##..",
                ".#..",
                "...#",
            ]
        )

        result = _bounded_connected_components(
            mask,
            min_area=1,
            max_component_area=4,
            started_at=0.0,
            timeout_seconds=None,
            color="#003366",
        )

        self.assertEqual(len(result.components), 2)
        largest = result.components[0]
        self.assertEqual(largest.bounds_hint, (0, 0, 1, 1))
        self.assertEqual(largest.row_spans_hint, ((0, 0, 1), (1, 1, 1)))
        self.assertEqual(
            largest.boundary_pixels_hint,
            frozenset({(0, 0), (1, 0), (1, 1)}),
        )
        self.assertIs(largest.boundary_pixels, largest.boundary_pixels_hint)
        self.assertAlmostEqual(largest.centroid.x, 2 / 3)
        self.assertAlmostEqual(largest.centroid.y, 1 / 3)

    def test_bounded_components_defers_large_component_without_retained_pixels(self):
        mask = BinaryMask.from_rows(
            [
                "###",
                "###",
            ]
        )

        result = _bounded_connected_components(
            mask,
            min_area=1,
            max_component_area=3,
            started_at=0.0,
            timeout_seconds=None,
            color="#003366",
        )

        self.assertEqual(result.components, ())
        self.assertEqual(result.diagnostics[0]["code"], "component_deferred")
        self.assertEqual(result.diagnostics[0]["area"], 6)


if __name__ == "__main__":
    unittest.main()
