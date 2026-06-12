import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from morphea.rendering import raster_fidelity_metrics
from morphea.svg_raster import (
    rasterize_svg,
    svg_raster_capability,
    svg_raster_metrics,
)


def _svg(body: str, *, width: int = 64, height: int = 64) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {width} {height}" width="{width}" height="{height}">'
        f"{body}</svg>"
    )


class SvgRasterTests(unittest.TestCase):
    def test_capability_reports_builtin_backend(self):
        capability = svg_raster_capability()

        self.assertEqual(capability["backend"], "builtin")
        self.assertTrue(capability["available"])

    def test_rect_renders_exact_pixels(self):
        svg = _svg('<rect x="8" y="18" width="24" height="25" fill="#003366" />')

        image = rasterize_svg(svg)

        self.assertEqual(image.size, (64, 64))
        self.assertEqual(image.getpixel((8, 18))[:3], (0, 51, 102))
        self.assertEqual(image.getpixel((31, 42))[:3], (0, 51, 102))
        self.assertEqual(image.getpixel((32, 18))[:3], (255, 255, 255))
        self.assertEqual(image.getpixel((7, 18))[:3], (255, 255, 255))

    def test_filled_circle_matches_pil_ellipse(self):
        source = Image.new("RGB", (64, 64), "#ffffff")
        ImageDraw.Draw(source).ellipse((18, 18, 46, 46), fill="#003366")
        svg = _svg('<circle cx="32" cy="32" r="14.5" fill="#003366" />')

        metrics = raster_fidelity_metrics(source=source, rendered=rasterize_svg(svg))

        self.assertLess(metrics["raster_l1_error"], 0.02)

    def test_stroke_path_with_arc_command_renders_curve(self):
        svg = _svg(
            '<path d="M 12 40 A 20 20 0 0 1 52 40" fill="none" '
            'stroke="#003366" stroke-width="4" stroke-linecap="round" '
            'stroke-linejoin="round" />'
        )

        image = rasterize_svg(svg)

        # Arc apex sits above the chord between the endpoints.
        self.assertEqual(image.getpixel((32, 20))[:3], (0, 51, 102))
        self.assertEqual(image.getpixel((12, 40))[:3], (0, 51, 102))
        self.assertEqual(image.getpixel((52, 40))[:3], (0, 51, 102))
        self.assertEqual(image.getpixel((32, 40))[:3], (255, 255, 255))

    def test_quadratic_and_cubic_commands_render(self):
        svg = _svg(
            '<path d="M 8 50 Q 32 8 56 50" fill="none" stroke="#003366" '
            'stroke-width="3" stroke-linecap="round" stroke-linejoin="round" />'
        )

        image = rasterize_svg(svg)

        self.assertEqual(image.getpixel((32, 29))[:3], (0, 51, 102))
        self.assertEqual(image.getpixel((32, 50))[:3], (255, 255, 255))

        cubic = _svg(
            '<path d="M 8 32 C 24 8 40 56 56 32" fill="none" stroke="#003366" '
            'stroke-width="3" stroke-linecap="round" stroke-linejoin="round" />'
        )

        cubic_image = rasterize_svg(cubic)

        self.assertEqual(cubic_image.getpixel((8, 32))[:3], (0, 51, 102))
        self.assertEqual(cubic_image.getpixel((56, 32))[:3], (0, 51, 102))

    def test_negative_mask_export_cuts_hole(self):
        svg = _svg(
            "<defs>"
            '<mask id="morphea-cutout-mask" maskUnits="userSpaceOnUse">'
            '<rect x="0" y="0" width="64" height="64" fill="white" />'
            '<path d="M 18 32 L 46 32" fill="none" stroke="black" '
            'stroke-width="3" stroke-linecap="butt" stroke-linejoin="round" />'
            "</mask>"
            "</defs>"
            '<g mask="url(#morphea-cutout-mask)">'
            '<rect x="8" y="20" width="49" height="25" fill="#003366" />'
            "</g>"
        )

        image = rasterize_svg(svg)

        self.assertEqual(image.getpixel((32, 32))[:3], (255, 255, 255))
        self.assertEqual(image.getpixel((32, 22))[:3], (0, 51, 102))
        self.assertEqual(image.getpixel((10, 32))[:3], (0, 51, 102))

    def test_square_caps_extend_past_endpoints(self):
        svg = _svg(
            '<path d="M 16 32 L 48 32" fill="none" stroke="#003366" '
            'stroke-width="4" stroke-linecap="square" stroke-linejoin="round" />'
        )

        image = rasterize_svg(svg)

        self.assertEqual(image.getpixel((14, 32))[:3], (0, 51, 102))
        self.assertEqual(image.getpixel((49, 32))[:3], (0, 51, 102))
        self.assertEqual(image.getpixel((11, 32))[:3], (255, 255, 255))

    def test_metrics_compare_source_preview_and_svg(self):
        source = Image.new("RGB", (64, 64), "#ffffff")
        ImageDraw.Draw(source).rectangle((8, 18, 31, 42), fill="#003366")
        svg = _svg('<rect x="8" y="18" width="24" height="25" fill="#003366" />')

        metrics = svg_raster_metrics(
            source=source,
            svg_text=svg,
            preview=source.copy(),
        )

        self.assertEqual(metrics["svg_raster_backend"], "builtin")
        self.assertTrue(metrics["svg_render_size_match"])
        self.assertEqual(metrics["svg_raster_l1_error"], 0.0)
        self.assertEqual(metrics["svg_vs_preview_l1_error"], 0.0)

    def test_adjacent_rect_gap_is_visible_to_the_svg_gate(self):
        source = Image.new("RGB", (64, 64), "#ffffff")
        draw = ImageDraw.Draw(source)
        draw.rectangle((8, 18, 31, 42), fill="#003366")
        draw.rectangle((32, 18, 56, 42), fill="#c99700")
        clean = _svg(
            '<rect x="8" y="18" width="24" height="25" fill="#003366" />'
            '<rect x="32" y="18" width="25" height="25" fill="#c99700" />'
        )
        gapped = _svg(
            '<rect x="8" y="18" width="23" height="25" fill="#003366" />'
            '<rect x="33" y="18" width="24" height="25" fill="#c99700" />'
        )

        clean_metrics = svg_raster_metrics(source=source, svg_text=clean)
        gapped_metrics = svg_raster_metrics(source=source, svg_text=gapped)

        self.assertEqual(clean_metrics["svg_raster_l1_error"], 0.0)
        self.assertGreater(gapped_metrics["svg_raster_l1_error"], 0.003)
        self.assertGreater(gapped_metrics["svg_raster_edge_error"], 0.003)

    @unittest.skipUnless(
        shutil.which("rsvg-convert"),
        "rsvg-convert not installed; builtin backend cross-check skipped",
    )
    def test_builtin_backend_matches_rsvg_convert(self):
        svg = _svg(
            '<rect x="8" y="18" width="24" height="25" fill="#003366" />'
            '<circle cx="48" cy="48" r="10" fill="#dd2222" />'
            '<path d="M 12 12 A 14 14 0 0 1 40 12" fill="none" '
            'stroke="#003366" stroke-width="3" stroke-linecap="round" '
            'stroke-linejoin="round" />'
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            svg_path = Path(temp_dir) / "case.svg"
            png_path = Path(temp_dir) / "case.png"
            svg_path.write_text(svg, encoding="utf-8")
            subprocess.run(
                [
                    "rsvg-convert",
                    "--background-color",
                    "#ffffff",
                    "-o",
                    str(png_path),
                    str(svg_path),
                ],
                check=True,
                capture_output=True,
            )
            reference = Image.open(png_path).convert("RGBA")

        metrics = raster_fidelity_metrics(
            source=reference,
            rendered=rasterize_svg(svg),
        )

        self.assertLess(metrics["raster_l1_error"], 0.02)
        self.assertLess(metrics["raster_edge_error"], 0.035)


if __name__ == "__main__":
    unittest.main()
