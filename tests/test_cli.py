import tempfile
import unittest
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
            image = Image.new("RGB", (24, 16), "white")
            draw = ImageDraw.Draw(image)
            draw.ellipse((2, 2, 10, 10), fill="#dd2222")
            draw.rectangle((13, 5, 22, 6), fill="#003366")
            image.save(input_path)

            with redirect_stdout(StringIO()):
                main(["vectorize", str(input_path), "-o", str(output_path)])

            svg = output_path.read_text(encoding="utf-8")
            self.assertIn("<svg", svg)
            self.assertIn("<circle ", svg)
            self.assertIn("<path ", svg)
            self.assertIn('fill="#dd2222"', svg)
            self.assertIn('stroke="#003366"', svg)


if __name__ == "__main__":
    unittest.main()
