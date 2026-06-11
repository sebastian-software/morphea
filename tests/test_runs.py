import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from curve.images import scene_from_flat_color_image
from curve.runs import (
    create_run_dir,
    render_markdown_report,
    write_markdown_report,
    write_vectorize_run,
)


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
            self.assertTrue(run.preview_path.exists())
            self.assertTrue(run.debug_svg_path.exists())
            manifest = json.loads(run.manifest_path.read_text())
            self.assertEqual(manifest["anchor_count"], 1)

    def test_render_markdown_report_summarizes_anchor_types(self):
        report = render_markdown_report(
            manifest={
                "width": 10,
                "height": 10,
                "anchor_count": 2,
                "anchors": [{"kind": "circle"}, {"kind": "circle"}],
                "layers": [{"name": "filled_primitives", "anchor_count": 2}],
                "diagnostics": [{"level": "warning", "code": "component_deferred"}],
                "groups": [],
                "metrics": {
                    "editability_score": 0.8,
                    "fragmentation_penalty": 0.1,
                },
            },
            config={"command": "vectorize"},
        )

        self.assertIn("# Curve Vectorize Report", report)
        self.assertIn("`circle`: 2", report)
        self.assertIn("- Layers: 1", report)
        self.assertIn("`filled_primitives`: 2", report)
        self.assertIn("`warning` `component_deferred`", report)
        self.assertIn("- Editability score: 0.8", report)
        self.assertIn("`fragmentation_penalty`: 0.1", report)

    def test_write_markdown_report_reads_manifest_and_config(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manifest = Path(temp_dir) / "manifest.json"
            config = Path(temp_dir) / "config.json"
            output = Path(temp_dir) / "report.md"
            manifest.write_text(
                json.dumps(
                    {
                        "width": 16,
                        "height": 16,
                        "anchor_count": 1,
                        "anchors": [{"kind": "circle"}],
                        "groups": [],
                        "diagnostics": [],
                        "metrics": {"editability_score": 1.0},
                    }
                ),
                encoding="utf-8",
            )
            config.write_text(
                json.dumps({"command": "vectorize", "min_area": 8}),
                encoding="utf-8",
            )

            report = write_markdown_report(
                manifest=manifest,
                config=config,
                output=output,
            )

            self.assertTrue(output.exists())
            self.assertIn("`circle`: 1", report)
            self.assertIn('"min_area": 8', output.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
