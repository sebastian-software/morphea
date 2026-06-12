import tempfile
import unittest
from pathlib import Path

from PIL import Image

from morphea.rendering import (
    raster_fidelity_metrics,
    render_manifest_image,
    write_manifest_preview,
)


class RenderingTests(unittest.TestCase):
    def test_render_manifest_image_draws_supported_primitives(self):
        manifest = {
            "width": 32,
            "height": 32,
            "anchors": [
                {
                    "kind": "circle",
                    "color": "#dd2222",
                    "circle": {"cx": 6, "cy": 6, "r": 4},
                },
                {
                    "kind": "stroke_polyline",
                    "color": "#003366",
                    "stroke": {
                        "centerline": [{"x": 12, "y": 4}, {"x": 20, "y": 4}],
                        "width_samples": [2, 2],
                    },
                },
                {
                    "kind": "quad",
                    "color": "#c99700",
                    "quad": {
                        "corners": [
                            {"x": 4, "y": 14},
                            {"x": 12, "y": 14},
                            {"x": 14, "y": 20},
                            {"x": 2, "y": 20},
                        ]
                    },
                },
                {
                    "kind": "arc",
                    "color": "#c99700",
                    "stroke": {
                        "centerline": [
                            {"x": 16, "y": 8},
                            {"x": 20, "y": 10},
                            {"x": 24, "y": 8},
                        ],
                        "width_samples": [2, 2, 2],
                    },
                },
                {
                    "kind": "rect",
                    "color": "#003366",
                    "quad": {
                        "corners": [
                            {"x": 18, "y": 14},
                            {"x": 28, "y": 14},
                            {"x": 28, "y": 18},
                            {"x": 18, "y": 18},
                        ]
                    },
                },
                {
                    "kind": "rounded_rect",
                    "color": "#dd2222",
                    "quad": {
                        "corners": [
                            {"x": 18, "y": 22},
                            {"x": 30, "y": 22},
                            {"x": 30, "y": 28},
                            {"x": 18, "y": 28},
                        ]
                    },
                },
            ],
        }

        image = render_manifest_image(manifest)

        self.assertEqual(image.size, (32, 32))
        self.assertEqual(image.getpixel((6, 6)), (221, 34, 34, 255))
        self.assertEqual(image.getpixel((14, 4)), (0, 51, 102, 255))
        self.assertEqual(image.getpixel((7, 17)), (201, 151, 0, 255))
        self.assertEqual(image.getpixel((20, 10)), (201, 151, 0, 255))
        self.assertEqual(image.getpixel((23, 16)), (0, 51, 102, 255))
        self.assertEqual(image.getpixel((24, 25)), (221, 34, 34, 255))

    def test_write_manifest_preview_saves_png(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "preview.png"
            path = write_manifest_preview(
                manifest={"width": 4, "height": 4, "anchors": []},
                output=output,
            )

            self.assertEqual(path, output)
            self.assertTrue(output.exists())

    def test_raster_fidelity_metrics_report_pixel_and_edge_error(self):
        source = Image.new("RGBA", (4, 4), "white")
        rendered = Image.new("RGBA", (4, 4), "white")

        identical = raster_fidelity_metrics(source=source, rendered=rendered)
        rendered.putpixel((1, 1), (0, 0, 0, 255))
        changed = raster_fidelity_metrics(source=source, rendered=rendered)

        self.assertTrue(identical["raster_size_match"])
        self.assertEqual(identical["raster_l1_error"], 0.0)
        self.assertEqual(identical["raster_edge_error"], 0.0)
        self.assertGreater(changed["raster_l1_error"], 0.0)
        self.assertGreater(changed["raster_edge_error"], 0.0)

    def test_raster_fidelity_ignores_rgb_when_both_pixels_are_transparent(self):
        source = Image.new("RGBA", (2, 2), (0, 0, 0, 0))
        rendered = Image.new("RGBA", (2, 2), (255, 255, 255, 0))

        metrics = raster_fidelity_metrics(source=source, rendered=rendered)

        self.assertEqual(metrics["raster_l1_error"], 0.0)
        self.assertEqual(metrics["raster_alpha_error"], 0.0)


if __name__ == "__main__":
    unittest.main()
