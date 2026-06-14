import tempfile
import unittest
from math import cos, pi, sin
from pathlib import Path

from PIL import Image, ImageDraw

from morphea.anchors import AnchorKind
from morphea.images import flat_color_masks_from_image, scene_from_flat_color_image


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

    def test_explicit_background_preserves_top_left_foreground_shape(self):
        image_path = _write_top_left_foreground_image()

        masks = flat_color_masks_from_image(image_path, background="#f6f6f6")
        scene = scene_from_flat_color_image(image_path, background="#f6f6f6")

        self.assertEqual([mask.color for mask in masks], ["#003366"])
        self.assertEqual(len(scene.anchors), 1)
        self.assertEqual(scene.anchors[0].color, "#003366")

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

    def test_timeout_can_stop_during_component_scanning(self):
        image_path = _write_large_circle_image()

        scene = scene_from_flat_color_image(image_path, timeout_seconds=0)

        self.assertEqual(scene.anchors, ())
        self.assertEqual(scene.diagnostics[0]["code"], "timeout_reached")

    def test_max_colors_quantizes_palette_before_grouping(self):
        image_path = _write_multi_red_circle_image()

        masks = flat_color_masks_from_image(image_path, max_colors=2, color_tolerance=8)

        self.assertEqual(len(masks), 1)

    def test_antialiased_neutral_radio_ring_vectorizes_as_stroke_circle(self):
        image_path = _write_antialiased_radio_ring_image()

        scene = scene_from_flat_color_image(
            image_path,
            min_area=8,
            color_tolerance=10,
            max_colors=8,
        )

        self.assertIn(
            AnchorKind.STROKE_CIRCLE,
            [anchor.kind for anchor in scene.anchors],
        )

    def test_irregular_neutral_badge_outline_stays_stroke_path(self):
        image_path = _write_irregular_badge_outline_image()

        scene = scene_from_flat_color_image(
            image_path,
            min_area=2,
            color_tolerance=48,
            max_colors=3,
        )

        self.assertEqual(
            [anchor.kind for anchor in scene.anchors],
            [AnchorKind.STROKE_PATH],
        )
        self.assertTrue(scene.anchors[0].stroke.closed)
        self.assertEqual(
            scene.anchors[0].metrics["irregular_circular_outline"],
            1.0,
        )

    def test_transparent_background_is_ignored(self):
        image_path = _write_transparent_circle_image()

        scene = scene_from_flat_color_image(image_path)

        self.assertEqual(len(scene.anchors), 1)
        self.assertEqual(scene.anchors[0].kind, AnchorKind.CIRCLE)
        self.assertEqual(scene.anchors[0].color, "#dd2222")
        self.assertEqual(scene.diagnostics[0]["code"], "transparent_pixels_ignored")

    def test_partial_alpha_pixels_are_flattened_before_grouping(self):
        image_path = _write_partial_alpha_circle_image()

        scene = scene_from_flat_color_image(image_path)

        self.assertEqual(len(scene.anchors), 1)
        self.assertEqual(scene.anchors[0].kind, AnchorKind.CIRCLE)
        self.assertEqual(scene.anchors[0].color, "#ee9090")
        self.assertEqual(
            [diagnostic["code"] for diagnostic in scene.diagnostics],
            ["transparent_pixels_ignored", "partial_alpha_flattened"],
        )

    def test_compact_filled_rectangle_vectorizes_as_rect(self):
        image_path = _write_rect_image()

        scene = scene_from_flat_color_image(image_path)

        self.assertEqual(len(scene.anchors), 1)
        self.assertEqual(scene.anchors[0].kind, AnchorKind.RECT)
        self.assertEqual(scene.anchors[0].color, "#003366")
        self.assertEqual(scene.to_manifest()["anchors"][0]["layer"], "filled_primitives")

    def test_compact_rounded_rectangle_vectorizes_as_rounded_rect(self):
        image_path = _write_rounded_rect_image()

        scene = scene_from_flat_color_image(image_path)

        self.assertEqual(len(scene.anchors), 1)
        self.assertEqual(scene.anchors[0].kind, AnchorKind.ROUNDED_RECT)
        self.assertEqual(scene.anchors[0].color, "#c99700")
        self.assertIn("corner_radius", scene.anchors[0].metrics)


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


def _write_top_left_foreground_image() -> Path:
    temp_dir = tempfile.TemporaryDirectory()
    path = Path(temp_dir.name) / "top-left-foreground.png"
    image = Image.new("RGB", (18, 14), "#f6f6f6")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 8, 5), fill="#003366")
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


def _write_antialiased_radio_ring_image() -> Path:
    temp_dir = tempfile.TemporaryDirectory()
    path = Path(temp_dir.name) / "radio-ring.png"
    image = Image.new("RGB", (96, 48), "white")
    high_res = Image.new("RGB", (384, 192), "white")
    draw = ImageDraw.Draw(high_res)
    draw.ellipse((48, 48, 144, 144), outline="#000000", width=5)
    image = high_res.resize(image.size, Image.Resampling.LANCZOS)
    image.save(path)
    _TEMP_DIRS.append(temp_dir)
    return path


def _write_irregular_badge_outline_image() -> Path:
    temp_dir = tempfile.TemporaryDirectory()
    path = Path(temp_dir.name) / "irregular-badge-outline.png"
    scale = 4
    size = 64
    center = size * scale / 2
    high_res = Image.new("RGB", (size * scale, size * scale), "white")
    draw = ImageDraw.Draw(high_res)
    points = []
    for index in range(64):
        theta = index * 2 * pi / 64
        radius = (26 + sin(8 * theta)) * scale
        points.append(
            (
                center + cos(theta) * radius,
                center + sin(theta) * radius,
            )
        )
    draw.line(points + [points[0]], fill="black", width=5 * scale, joint="curve")
    image = high_res.resize((size, size), Image.Resampling.LANCZOS)
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


def _write_partial_alpha_circle_image() -> Path:
    temp_dir = tempfile.TemporaryDirectory()
    path = Path(temp_dir.name) / "partial-alpha-circle.png"
    image = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((3, 3, 12, 12), fill=(221, 34, 34, 128))
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


def _write_rect_image() -> Path:
    temp_dir = tempfile.TemporaryDirectory()
    path = Path(temp_dir.name) / "rect.png"
    image = Image.new("RGB", (18, 14), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((4, 3, 13, 10), fill="#003366")
    image.save(path)
    _TEMP_DIRS.append(temp_dir)
    return path


def _write_rounded_rect_image() -> Path:
    temp_dir = tempfile.TemporaryDirectory()
    path = Path(temp_dir.name) / "rounded-rect.png"
    image = Image.new("RGB", (18, 14), "white")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((3, 3, 14, 10), radius=2, fill="#c99700")
    image.save(path)
    _TEMP_DIRS.append(temp_dir)
    return path


if __name__ == "__main__":
    unittest.main()
