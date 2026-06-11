import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from curve.images import scene_from_flat_color_image
from curve.runs import create_run_dir, render_markdown_report, write_vectorize_run


class RunWriterTests(unittest.TestCase):
    def test_write_vectorize_run_creates_expected_artifacts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "input.png"
            image = Image.new("RGB", (24, 16), "white")
            draw = ImageDraw.Draw(image)
            draw.ellipse((2, 2, 10, 10), fill="#dd2222")
            image.save(input_path)

            scene = scene_from_flat_color_image(input_path)
            run_dir = create_run_dir(Path(temp_dir) / "runs")
            run = write_vectorize_run(
                run_dir=run_dir,
                input_path=input_path,
                scene=scene,
                config={"command": "vectorize", "min_area": 8},
            )

            self.assertTrue(run.input_path.exists())
            self.assertTrue(run.svg_path.exists())
            self.assertTrue(run.manifest_path.exists())
            self.assertTrue(run.config_path.exists())
            self.assertTrue(run.report_path.exists())
            manifest = json.loads(run.manifest_path.read_text())
            self.assertEqual(manifest["anchor_count"], 1)

    def test_render_markdown_report_summarizes_anchor_types(self):
        report = render_markdown_report(
            manifest={
                "width": 10,
                "height": 10,
                "anchor_count": 2,
                "anchors": [{"kind": "circle"}, {"kind": "circle"}],
                "diagnostics": [{"level": "warning", "code": "component_deferred"}],
                "groups": [],
            },
            config={"command": "vectorize"},
        )

        self.assertIn("# Curve Vectorize Report", report)
        self.assertIn("`circle`: 2", report)
        self.assertIn("`warning` `component_deferred`", report)


if __name__ == "__main__":
    unittest.main()

