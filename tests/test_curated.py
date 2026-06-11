import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from PIL import Image, ImageDraw

from curve.cli import main
from curve.curated import (
    check_curated_suite,
    load_curated_suite,
    render_curated_snapshot,
)


class CuratedSuiteTests(unittest.TestCase):
    def test_load_curated_suite_validates_required_fields(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            suite_path = Path(temp_dir) / "suite.json"
            suite_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "cases": [
                            {
                                "id": "simple-circle",
                                "source": "/tmp/simple-circle.png",
                                "recommended_config": {"min_area": 4},
                                "expectations": [
                                    {
                                        "id": "circle-anchor",
                                        "kind": "circle",
                                        "min_count": 1,
                                    }
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            suite = load_curated_suite(suite_path)

            self.assertEqual(suite["cases"][0]["id"], "simple-circle")

    def test_check_curated_suite_can_run_expected_anchor_checks(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "input.png"
            suite_path = Path(temp_dir) / "suite.json"
            output = Path(temp_dir) / "report.json"
            output_dir = Path(temp_dir) / "artifacts"
            snapshot = Path(temp_dir) / "snapshot.json"
            image = Image.new("RGB", (24, 24), "white")
            draw = ImageDraw.Draw(image)
            draw.ellipse((5, 5, 17, 17), fill="#c08011")
            image.save(source)
            suite_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "cases": [
                            {
                                "id": "simple-circle",
                                "source": str(source),
                                "recommended_config": {
                                    "min_area": 8,
                                    "timeout_seconds": 5,
                                },
                                "expectations": [
                                    {
                                        "id": "circle-anchor",
                                        "kind": "circle",
                                        "min_count": 1,
                                    }
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            result = check_curated_suite(
                suite_path,
                output=output,
                output_dir=output_dir,
                run=True,
                snapshot=snapshot,
            )

            self.assertTrue(result["ok"])
            self.assertEqual(result["cases"][0]["status"], "checked")
            self.assertTrue(result["cases"][0]["expectations"][0]["ok"])
            self.assertEqual(result["cases"][0]["anchor_kind_counts"]["circle"], 1)
            self.assertTrue((output_dir / "simple-circle" / "output.svg").exists())
            self.assertTrue((output_dir / "simple-circle" / "debug.svg").exists())
            self.assertTrue((output_dir / "simple-circle" / "manifest.json").exists())
            self.assertTrue((output_dir / "simple-circle" / "report.md").exists())
            self.assertTrue((output_dir / "simple-circle" / "preview.png").exists())
            self.assertTrue((output_dir / "simple-circle" / "input" / "input.png").exists())
            manifest = json.loads(
                (output_dir / "simple-circle" / "manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertIn("raster_l1_error", manifest["metrics"])
            report = json.loads(output.read_text())
            self.assertEqual(report["case_count"], 1)
            self.assertIn("artifacts", report["cases"][0])
            snapshot_report = json.loads(snapshot.read_text(encoding="utf-8"))
            self.assertEqual(snapshot_report["schema_version"], 1)
            self.assertEqual(snapshot_report["cases"][0]["id"], "simple-circle")
            self.assertEqual(
                snapshot_report["cases"][0]["anchor_kind_counts"]["circle"],
                1,
            )
            self.assertIn("editability_score", snapshot_report["cases"][0]["metrics"])

    def test_render_curated_snapshot_sorts_cases_and_expectations(self):
        snapshot = render_curated_snapshot(
            {
                "suite": "suite.json",
                "case_count": 2,
                "ok": True,
                "cases": [
                    {
                        "id": "z-case",
                        "status": "checked",
                        "ok": True,
                        "source_exists": True,
                        "expectations": [
                            {
                                "id": "z-exp",
                                "ok": True,
                                "actual_count": 2,
                                "min_count": 1,
                            },
                            {
                                "id": "a-exp",
                                "ok": True,
                                "actual_count": 1,
                                "min_count": 1,
                            },
                        ],
                    },
                    {
                        "id": "a-case",
                        "status": "missing_source",
                        "ok": False,
                        "source_exists": False,
                        "expectations": [],
                    },
                ],
            }
        )

        self.assertEqual(
            [case["id"] for case in snapshot["cases"]],
            ["a-case", "z-case"],
        )
        self.assertEqual(
            [item["id"] for item in snapshot["cases"][1]["expectations"]],
            ["a-exp", "z-exp"],
        )

    def test_curated_check_cli_writes_report(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "missing.png"
            suite_path = Path(temp_dir) / "suite.json"
            output = Path(temp_dir) / "report.json"
            snapshot = Path(temp_dir) / "snapshot.json"
            suite_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "cases": [
                            {
                                "id": "missing-image",
                                "source": str(source),
                                "expectations": [
                                    {
                                        "id": "circle-anchor",
                                        "kind": "circle",
                                        "min_count": 1,
                                    }
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with redirect_stdout(StringIO()):
                main(
                    [
                        "curated-check",
                        str(suite_path),
                        "-o",
                        str(output),
                        "--snapshot",
                        str(snapshot),
                    ]
                )

            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertTrue(report["ok"])
            self.assertEqual(report["cases"][0]["status"], "missing_source")
            snapshot_report = json.loads(snapshot.read_text(encoding="utf-8"))
            self.assertEqual(snapshot_report["cases"][0]["status"], "missing_source")


if __name__ == "__main__":
    unittest.main()
