import unittest

from curve.masks import BinaryMask
from curve.scene import SvgStyle, scene_from_mask


class SceneExportTests(unittest.TestCase):
    def test_circle_mask_exports_editable_svg_circle(self):
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

        svg = scene_from_mask(mask).to_svg(SvgStyle(fill="#123456"))

        self.assertIn("<circle ", svg)
        self.assertIn('fill="#123456"', svg)
        self.assertNotIn("<polygon", svg)

    def test_stroke_mask_exports_editable_svg_stroke_path(self):
        mask = BinaryMask.from_rows(
            (
                "............",
                ".##########.",
                ".##########.",
                "............",
            )
        )

        svg = scene_from_mask(mask).to_svg(SvgStyle(stroke="#ffffff"))

        self.assertIn("<path ", svg)
        self.assertIn('fill="none"', svg)
        self.assertIn('stroke="#ffffff"', svg)
        self.assertIn('stroke-linecap="round"', svg)

    def test_circle_ring_exports_editable_svg_stroke_circle(self):
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

        svg = scene_from_mask(mask).to_svg(SvgStyle(stroke="#c99700"))

        self.assertIn("<circle ", svg)
        self.assertIn('fill="none"', svg)
        self.assertIn('stroke="#c99700"', svg)
        self.assertIn("stroke-width=", svg)

    def test_perspective_quad_exports_editable_svg_polygon(self):
        mask = BinaryMask.from_rows(
            (
                "....####....",
                "...######...",
                "..########..",
                ".##########.",
                "############",
            )
        )

        svg = scene_from_mask(mask).to_svg(SvgStyle(fill="#d0a21a"))

        self.assertIn("<polygon ", svg)
        self.assertIn('fill="#d0a21a"', svg)
        self.assertNotIn("unsupported anchor", svg)

    def test_multiple_quads_are_reported_as_grid_group(self):
        tile = BinaryMask.from_rows(
            (
                "....####....",
                "...######...",
                "..########..",
                ".##########.",
                "############",
            )
        )
        shifted_pixels = {(x + 16, y) for x, y in tile.pixels}
        mask = BinaryMask(
            width=28,
            height=5,
            pixels=tile.pixels | frozenset(shifted_pixels),
        )

        manifest = scene_from_mask(mask).to_manifest()

        self.assertEqual(manifest["groups"][0]["kind"], "perspective_grid")
        self.assertEqual(manifest["groups"][0]["anchor_indexes"], [0, 1])
        self.assertIn(
            "perspective_grid_consistency_error",
            manifest["groups"][0]["metrics"],
        )


if __name__ == "__main__":
    unittest.main()
