import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from curve.anchors import AnchorKind
from curve.images import flat_color_masks_from_image, scene_from_flat_color_image


class FlatColorImageTests(unittest.TestCase):
    def test_flat_color_image_splits_non_background_masks(self):
        image_path = _write_fixture_image()

        masks = flat_color_masks_from_image(image_path)

        self.assertEqual([mask.color for mask in masks], ["#003366", "#c99700", "#dd2222"])

    def test_flat_color_image_vectorizes_base_shapes_with_colors(self):
        image_path = _write_fixture_image()

        scene = scene_from_flat_color_image(image_path)
        kinds_by_color = {anchor.color: anchor.kind for anchor in scene.anchors}
        svg = scene.to_svg()

        self.assertEqual(kinds_by_color["#dd2222"], AnchorKind.CIRCLE)
        self.assertEqual(kinds_by_color["#003366"], AnchorKind.STROKE_POLYLINE)
        self.assertEqual(kinds_by_color["#c99700"], AnchorKind.QUAD)
        self.assertIn('fill="#dd2222"', svg)
        self.assertIn('stroke="#003366"', svg)
        self.assertIn('fill="#c99700"', svg)

    def test_color_tolerance_groups_near_flat_circle_edges(self):
        image_path = _write_near_flat_circle_image()

        strict_masks = flat_color_masks_from_image(image_path)
        tolerant_masks = flat_color_masks_from_image(image_path, color_tolerance=18)
        scene = scene_from_flat_color_image(image_path, color_tolerance=18)

        self.assertGreater(len(strict_masks), len(tolerant_masks))
        self.assertEqual(len(tolerant_masks), 1)
        self.assertEqual(scene.anchors[0].kind, AnchorKind.CIRCLE)
        self.assertEqual(scene.anchors[0].color, "#dd2222")

    def test_white_gap_inside_flat_shape_exports_cutout_stroke(self):
        image_path = _write_cutout_gap_image()

        scene = scene_from_flat_color_image(image_path)
        svg = scene.to_svg()
        cutouts = [
            anchor
            for anchor in scene.anchors
            if anchor.stroke is not None and anchor.stroke.is_cutout
        ]

        self.assertEqual(len(cutouts), 1)
        self.assertEqual(cutouts[0].color, "#ffffff")
        self.assertIn('stroke="#ffffff"', svg)

    def test_max_size_resizes_for_analysis_and_scales_anchor_back(self):
        image_path = _write_large_circle_image()

        scene = scene_from_flat_color_image(image_path, max_size=20)

        self.assertEqual(scene.width, 40)
        self.assertEqual(scene.height, 40)
        self.assertEqual(scene.anchors[0].kind, AnchorKind.CIRCLE)
        self.assertGreater(scene.anchors[0].circle.radius, 10)
        self.assertEqual(scene.diagnostics[0]["code"], "image_resized_for_analysis")

    def test_max_component_area_defers_large_components_after_mask_split(self):
        image_path = _write_large_circle_image()

        scene = scene_from_flat_color_image(image_path, max_component_area=20)

        self.assertEqual(scene.anchors, ())
        self.assertEqual(scene.diagnostics[0]["code"], "color_mask_split_for_components")
        self.assertEqual(scene.diagnostics[0]["color"], "#dd2222")
        self.assertEqual(scene.diagnostics[1]["code"], "component_deferred")

    def test_large_color_mask_can_still_emit_small_components(self):
        image_path = _write_two_small_same_color_dots()

        scene = scene_from_flat_color_image(
            image_path,
            min_area=4,
            max_component_area=30,
        )

        self.assertEqual(len(scene.anchors), 2)
        self.assertEqual(
            [diagnostic["code"] for diagnostic in scene.diagnostics],
            ["color_mask_split_for_components"],
        )
        self.assertEqual(
            [anchor.kind for anchor in scene.anchors],
            [AnchorKind.CIRCLE, AnchorKind.CIRCLE],
        )

    def test_max_colors_quantizes_palette_before_grouping(self):
        image_path = _write_multi_red_circle_image()

        masks = flat_color_masks_from_image(image_path, max_colors=2, color_tolerance=8)

        self.assertEqual(len(masks), 1)

    def test_transparent_background_is_ignored(self):
        image_path = _write_transparent_circle_image()

        scene = scene_from_flat_color_image(image_path)

        self.assertEqual(len(scene.anchors), 1)
        self.assertEqual(scene.anchors[0].kind, AnchorKind.CIRCLE)
        self.assertEqual(scene.anchors[0].color, "#dd2222")


def _write_fixture_image() -> Path:
    temp_dir = tempfile.TemporaryDirectory()
    path = Path(temp_dir.name) / "flat-primitives.png"
    image = Image.new("RGB", (56, 28), "white")
    draw = ImageDraw.Draw(image)
    draw.ellipse((3, 4, 15, 16), fill="#dd2222")
    draw.rectangle((20, 8, 38, 10), fill="#003366")
    draw.polygon(((43, 5), (50, 5), (54, 17), (39, 17)), fill="#c99700")
    image.save(path)
    _TEMP_DIRS.append(temp_dir)
    return path


_TEMP_DIRS: list[tempfile.TemporaryDirectory] = []


def _write_near_flat_circle_image() -> Path:
    temp_dir = tempfile.TemporaryDirectory()
    path = Path(temp_dir.name) / "near-flat-circle.png"
    image = Image.new("RGB", (16, 16), "white")
    draw = ImageDraw.Draw(image)
    draw.ellipse((3, 3, 12, 12), fill="#dd2222")
    draw.point(
        (
            (7, 3),
            (8, 3),
            (3, 7),
            (3, 8),
            (12, 7),
            (12, 8),
            (7, 12),
            (8, 12),
        ),
        fill="#e02a2a",
    )
    image.save(path)
    _TEMP_DIRS.append(temp_dir)
    return path


def _write_cutout_gap_image() -> Path:
    temp_dir = tempfile.TemporaryDirectory()
    path = Path(temp_dir.name) / "cutout-gap.png"
    image = Image.new("RGB", (18, 9), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((2, 2, 15, 6), fill="#003366")
    draw.rectangle((6, 4, 11, 4), fill="white")
    image.save(path)
    _TEMP_DIRS.append(temp_dir)
    return path


def _write_large_circle_image() -> Path:
    temp_dir = tempfile.TemporaryDirectory()
    path = Path(temp_dir.name) / "large-circle.png"
    image = Image.new("RGB", (40, 40), "white")
    draw = ImageDraw.Draw(image)
    draw.ellipse((8, 8, 31, 31), fill="#dd2222")
    image.save(path)
    _TEMP_DIRS.append(temp_dir)
    return path


def _write_multi_red_circle_image() -> Path:
    temp_dir = tempfile.TemporaryDirectory()
    path = Path(temp_dir.name) / "multi-red-circle.png"
    image = Image.new("RGB", (18, 18), "white")
    draw = ImageDraw.Draw(image)
    draw.ellipse((3, 3, 14, 14), fill="#dd2222")
    draw.arc((3, 3, 14, 14), start=0, end=180, fill="#d91f1f", width=2)
    image.save(path)
    _TEMP_DIRS.append(temp_dir)
    return path


def _write_transparent_circle_image() -> Path:
    temp_dir = tempfile.TemporaryDirectory()
    path = Path(temp_dir.name) / "transparent-circle.png"
    image = Image.new("RGBA", (16, 16), (38, 69, 201, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((3, 3, 12, 12), fill="#dd2222")
    image.save(path)
    _TEMP_DIRS.append(temp_dir)
    return path


def _write_two_small_same_color_dots() -> Path:
    temp_dir = tempfile.TemporaryDirectory()
    path = Path(temp_dir.name) / "two-small-dots.png"
    image = Image.new("RGB", (22, 10), "white")
    draw = ImageDraw.Draw(image)
    draw.ellipse((2, 2, 7, 7), fill="#dd2222")
    draw.ellipse((14, 2, 19, 7), fill="#dd2222")
    image.save(path)
    _TEMP_DIRS.append(temp_dir)
    return path


if __name__ == "__main__":
    unittest.main()
