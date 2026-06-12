import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from morphea.cli import main
from morphea.primitive_quality import (
    check_primitive_quality,
    primitive_specs,
    render_primitive_quality_markdown,
)


class PrimitiveQualityTests(unittest.TestCase):
    def test_primitive_quality_harness_passes_basic_cases(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            report = check_primitive_quality(output_dir=temp_dir)

            self.assertTrue(report["ok"])
            self.assertEqual(report["case_count"], len(primitive_specs()))
            self.assertEqual(report["failed_count"], 0)
            self.assertEqual(report["selection"], {"cases": [], "filter": None})
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
                self.assertIn("family", case)
                self.assertIn("variant", case)
                self.assertIn("geometry_diff", case)
                self.assertIn("failure_categories", case)
                self.assertIn("failure_details", case)
                self.assertTrue((case_dir / "input.png").exists())
                self.assertTrue((case_dir / "output.svg").exists())
                self.assertTrue((case_dir / "manifest.json").exists())
                self.assertTrue((case_dir / "preview.png").exists())

    def test_primitive_quality_harness_filters_cases(self):
        report = check_primitive_quality(cases=("filled_square",))

        self.assertTrue(report["ok"])
        self.assertEqual(report["case_count"], 1)
        self.assertEqual(report["selected_case_ids"], ["filled_square"])
        self.assertEqual(report["selection"], {"cases": ["filled_square"], "filter": None})

    def test_primitive_quality_harness_filters_by_pattern(self):
        report = check_primitive_quality(filter_pattern="*_stroke_width_1")

        self.assertTrue(report["ok"])
        self.assertEqual(
            report["selected_case_ids"],
            ["horizontal_stroke_width_1", "vertical_stroke_width_1"],
        )

    def test_primitive_specs_have_ten_variants_per_family(self):
        counts: dict[str, int] = {}
        for spec in primitive_specs():
            counts[spec.family or spec.id] = counts.get(spec.family or spec.id, 0) + 1

        self.assertEqual(
            counts,
            {
                "diagonal_stroke": 10,
                "filled_circle": 10,
                "filled_rectangle": 10,
                "filled_square": 10,
                "horizontal_stroke": 10,
                "outlined_ring": 10,
                "rounded_rectangle": 10,
                "simple_quad": 10,
                "vertical_stroke": 10,
            },
        )

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
                        "failure_categories": ["fallback_path"],
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

    def test_primitive_check_cli_filters_cases(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output = root / "primitive-report.json"

            with redirect_stdout(StringIO()):
                main(
                    [
                        "primitive-check",
                        "-o",
                        str(output),
                        "--case",
                        "filled_square",
                    ]
                )

            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertTrue(report["ok"])
            self.assertEqual(report["selected_case_ids"], ["filled_square"])

    def test_primitive_check_cli_exits_nonzero_for_empty_selection(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "primitive-report.json"

            with self.assertRaises(SystemExit) as raised:
                with redirect_stdout(StringIO()):
                    main(
                        [
                            "primitive-check",
                            "-o",
                            str(output),
                            "--filter",
                            "does-not-match",
                        ]
                    )

            self.assertEqual(raised.exception.code, 1)
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertFalse(report["ok"])
            self.assertEqual(report["case_count"], 0)

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
                        "case": "filled_square",
                    }
                ),
                encoding="utf-8",
            )

            with redirect_stdout(StringIO()):
                main(["primitive-check", "--config", str(config)])

            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(report["case_count"], 1)
            self.assertEqual(report["selection"]["cases"], ["filled_square"])
            self.assertTrue(markdown.exists())


if __name__ == "__main__":
    unittest.main()
