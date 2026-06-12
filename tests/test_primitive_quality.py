import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from morphea.cli import main
from morphea.primitive_quality import (
    check_primitive_quality,
    render_primitive_quality_markdown,
)


class PrimitiveQualityTests(unittest.TestCase):
    def test_primitive_quality_harness_passes_basic_cases(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            report = check_primitive_quality(output_dir=temp_dir)

            self.assertTrue(report["ok"])
            self.assertEqual(report["case_count"], 9)
            self.assertEqual(report["failed_count"], 0)
            actual_kinds = {
                case["id"]: case["actual_kind"]
                for case in report["cases"]
            }
            self.assertEqual(actual_kinds["filled_square"], "rect")
            self.assertEqual(actual_kinds["filled_circle"], "circle")
            self.assertEqual(actual_kinds["horizontal_stroke"], "stroke_polyline")
            self.assertEqual(actual_kinds["outlined_ring"], "stroke_circle")

            root = Path(temp_dir)
            for case in report["cases"]:
                case_dir = root / case["id"]
                self.assertTrue((case_dir / "input.png").exists())
                self.assertTrue((case_dir / "output.svg").exists())
                self.assertTrue((case_dir / "manifest.json").exists())
                self.assertTrue((case_dir / "preview.png").exists())

    def test_primitive_quality_markdown_summarizes_failures(self):
        markdown = render_primitive_quality_markdown(
            {
                "case_count": 1,
                "passed_count": 0,
                "failed_count": 1,
                "ok": False,
                "cases": [
                    {
                        "id": "filled_square",
                        "ok": False,
                        "actual_kind": "cubic_path",
                        "metrics": {
                            "raster_l1_error": 0.2,
                            "raster_edge_error": 0.1,
                        },
                        "geometry": {"bbox_iou": 0.4},
                        "failures": ["unexpected cubic_path fallback"],
                    }
                ],
            }
        )

        self.assertIn("filled_square", markdown)
        self.assertIn("unexpected cubic_path fallback", markdown)

    def test_primitive_check_cli_writes_report_markdown_and_artifacts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output = root / "primitive-report.json"
            markdown = root / "primitive-report.md"
            artifact_dir = root / "artifacts"

            with redirect_stdout(StringIO()) as stdout:
                main(
                    [
                        "primitive-check",
                        "-o",
                        str(output),
                        "--output-dir",
                        str(artifact_dir),
                        "--markdown",
                        str(markdown),
                    ]
                )

            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertTrue(report["ok"])
            self.assertTrue(markdown.exists())
            self.assertTrue((artifact_dir / "filled_square" / "output.svg").exists())
            self.assertIn("primitive cases", stdout.getvalue())

    def test_primitive_check_cli_accepts_config_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output = root / "primitive-report.json"
            markdown = root / "primitive-report.md"
            artifact_dir = root / "artifacts"
            config = root / "primitive-check.json"
            config.write_text(
                json.dumps(
                    {
                        "output": str(output),
                        "output_dir": str(artifact_dir),
                        "markdown": str(markdown),
                    }
                ),
                encoding="utf-8",
            )

            with redirect_stdout(StringIO()):
                main(["primitive-check", "--config", str(config)])

            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(report["case_count"], 9)
            self.assertTrue(markdown.exists())


if __name__ == "__main__":
    unittest.main()
