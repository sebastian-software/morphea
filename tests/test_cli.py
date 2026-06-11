import tempfile
import unittest
import json
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from PIL import Image, ImageDraw

from curve.cli import main


class CliTests(unittest.TestCase):
    def test_vectorize_writes_svg_for_flat_color_image(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "input.png"
            output_path = Path(temp_dir) / "output.svg"
            manifest_path = Path(temp_dir) / "output.json"
            image = Image.new("RGB", (24, 16), "white")
            draw = ImageDraw.Draw(image)
            draw.ellipse((2, 2, 10, 10), fill="#dd2222")
            draw.rectangle((13, 5, 22, 6), fill="#003366")
            image.save(input_path)

            with redirect_stdout(StringIO()):
                main(["vectorize", str(input_path), "-o", str(output_path)])

            svg = output_path.read_text(encoding="utf-8")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertIn("<svg", svg)
            self.assertIn("<circle ", svg)
            self.assertIn("<path ", svg)
            self.assertIn('fill="#dd2222"', svg)
            self.assertIn('stroke="#003366"', svg)
            self.assertEqual(manifest["anchor_count"], 2)
            self.assertEqual(
                [anchor["kind"] for anchor in manifest["anchors"]],
                ["stroke_polyline", "circle"],
            )

    def test_vectorize_accepts_color_tolerance(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "input.png"
            output_path = Path(temp_dir) / "output.svg"
            image = Image.new("RGB", (16, 16), "white")
            draw = ImageDraw.Draw(image)
            draw.ellipse((3, 3, 12, 12), fill="#dd2222")
            draw.point(((7, 3), (8, 12)), fill="#e02a2a")
            image.save(input_path)

            with redirect_stdout(StringIO()):
                main(
                    [
                        "vectorize",
                        str(input_path),
                        "-o",
                        str(output_path),
                        "--color-tolerance",
                        "18",
                    ]
                )

            manifest = json.loads(output_path.with_suffix(".json").read_text())
            self.assertEqual(manifest["anchor_count"], 1)
            self.assertEqual(manifest["anchors"][0]["kind"], "circle")


if __name__ == "__main__":
    unittest.main()
