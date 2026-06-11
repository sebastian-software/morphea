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


if __name__ == "__main__":
    unittest.main()
