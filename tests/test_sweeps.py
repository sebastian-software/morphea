import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from PIL import Image, ImageDraw

from curve.cli import main
from curve.sweeps import load_sweep_config, render_sweep_markdown, run_sweep


class SweepTests(unittest.TestCase):
    def test_load_sweep_config_validates_required_fields(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = Path(temp_dir) / "sweep.json"
            config.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "input": "/tmp/input.png",
                        "runs": [
                            {"id": "baseline", "config": {"min_area": 8}},
                        ],
                    }
                ),
                encoding="utf-8",
            )

            loaded = load_sweep_config(config)

            self.assertEqual(loaded["runs"][0]["id"], "baseline")

    def test_run_sweep_writes_runs_and_summary(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image_path = _write_input_image(root)
            config = _write_sweep_config(root, image_path)
            output_dir = root / "runs"

            summary = run_sweep(config, output_dir=output_dir)

            self.assertEqual(summary["schema_version"], 1)
            self.assertEqual(summary["run_count"], 2)
            self.assertIn("layer_count", summary["runs"][0])
            self.assertIn("editability_score", summary["runs"][0])
            self.assertIn("fragmentation_penalty", summary["runs"][0])
            self.assertIn("raster_l1_error", summary["runs"][0])
            self.assertIn("raster_edge_error", summary["runs"][0])
            self.assertIn("semantic_rank", summary["runs"][0])
            self.assertIn("diagnostic_stage_counts", summary["runs"][0])
            self.assertEqual(len(summary["ranking"]), 2)
            self.assertEqual(summary["ranking"][0]["rank"], 1)
            self.assertIn(
                summary["ranking"][0]["id"],
                {run["id"] for run in summary["runs"]},
            )
            self.assertTrue((output_dir / "baseline" / "manifest.json").exists())
            self.assertTrue((output_dir / "tolerant" / "report.md").exists())
            self.assertTrue((output_dir / "sweep-summary.json").exists())

    def test_run_sweep_can_write_markdown_comparison(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image_path = _write_input_image(root)
            config = _write_sweep_config(root, image_path)
            output_dir = root / "runs"
            markdown = root / "sweep.md"

            run_sweep(config, output_dir=output_dir, markdown=markdown)

            self.assertTrue(markdown.exists())
            text = markdown.read_text(encoding="utf-8")
            self.assertIn("# Curve Sweep Summary", text)
            self.assertIn("| Rank | Run | Editability |", text)
            self.assertIn("Diagnostic Stages", text)

    def test_run_sweep_summarizes_diagnostic_stages(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image_path = _write_input_image(root)
            config = root / "sweep.json"
            config.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "input": str(image_path),
                        "runs": [
                            {
                                "id": "deferred",
                                "config": {
                                    "min_area": 8,
                                    "max_component_area": 4,
                                },
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            output_dir = root / "runs"
            markdown = root / "summary.md"

            summary = run_sweep(config, output_dir=output_dir, markdown=markdown)

            self.assertEqual(
                summary["runs"][0]["diagnostic_stage_counts"]["segmentation"],
                4,
            )
            self.assertIn(
                "segmentation: 4",
                markdown.read_text(encoding="utf-8"),
            )

    def test_run_sweep_passes_cutout_export_to_output_svg(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image_path = _write_cutout_image(root)
            config = root / "sweep.json"
            config.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "input": str(image_path),
                        "runs": [
                            {
                                "id": "mask-export",
                                "config": {
                                    "min_area": 8,
                                    "cutout_export": "negative_mask",
                                },
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            output_dir = root / "runs"

            summary = run_sweep(config, output_dir=output_dir)

            svg = (output_dir / "mask-export" / "output.svg").read_text(
                encoding="utf-8"
            )
            run_config = json.loads(
                (output_dir / "mask-export" / "config.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(summary["run_count"], 1)
            self.assertEqual(run_config["cutout_export"], "negative_mask")
            self.assertIn('<mask id="curve-cutout-mask"', svg)

    def test_run_sweep_passes_background_to_vectorize_config(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image_path = _write_top_left_foreground_image(root)
            config = root / "sweep.json"
            config.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "input": str(image_path),
                        "runs": [
                            {
                                "id": "explicit-bg",
                                "config": {
                                    "background": "#f6f6f6",
                                    "min_area": 4,
                                },
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            output_dir = root / "runs"

            summary = run_sweep(config, output_dir=output_dir)

            run_config = json.loads(
                (output_dir / "explicit-bg" / "config.json").read_text(
                    encoding="utf-8"
                )
            )
            manifest = json.loads(
                (output_dir / "explicit-bg" / "manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(summary["run_count"], 1)
            self.assertEqual(run_config["background"], "#f6f6f6")
            self.assertEqual(manifest["anchors"][0]["color"], "#003366")

    def test_render_sweep_markdown_ranks_by_editability_then_raster_error(self):
        markdown = render_sweep_markdown(
            {
                "run_count": 2,
                "input": "input.png",
                "runs": [
                    {
                        "id": "low",
                        "run_dir": "/tmp/low",
                        "editability_score": 0.5,
                        "raster_l1_error": 0.0,
                    },
                    {
                        "id": "high",
                        "run_dir": "/tmp/high",
                        "editability_score": 0.9,
                        "raster_l1_error": 0.5,
                    },
                ],
            }
        )

        self.assertLess(markdown.index("`high`"), markdown.index("`low`"))

    def test_sweep_cli_runs_config(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image_path = _write_input_image(root)
            config = _write_sweep_config(root, image_path)
            output_dir = root / "runs"
            markdown = root / "summary.md"

            with redirect_stdout(StringIO()):
                main(
                    [
                        "sweep",
                        str(config),
                        "-o",
                        str(output_dir),
                        "--markdown",
                        str(markdown),
                    ]
                )

            summary = json.loads(
                (output_dir / "sweep-summary.json").read_text(encoding="utf-8")
            )
            self.assertEqual(summary["run_count"], 2)
            self.assertTrue(markdown.exists())


def _write_input_image(root: Path) -> Path:
    image_path = root / "input.png"
    image = Image.new("RGB", (24, 24), "white")
    draw = ImageDraw.Draw(image)
    draw.ellipse((4, 4, 14, 14), fill="#dd2222")
    draw.rectangle((16, 10, 22, 11), fill="#003366")
    image.save(image_path)
    return image_path


def _write_cutout_image(root: Path) -> Path:
    image_path = root / "cutout.png"
    image = Image.new("RGB", (18, 9), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((2, 2, 15, 6), fill="#003366")
    draw.rectangle((6, 4, 11, 4), fill="white")
    image.save(image_path)
    return image_path


def _write_top_left_foreground_image(root: Path) -> Path:
    image_path = root / "top-left-foreground.png"
    image = Image.new("RGB", (18, 14), "#f6f6f6")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 8, 5), fill="#003366")
    image.save(image_path)
    return image_path


def _write_sweep_config(root: Path, image_path: Path) -> Path:
    config = root / "sweep.json"
    config.write_text(
        json.dumps(
            {
                "version": 1,
                "input": str(image_path),
                "runs": [
                    {
                        "id": "baseline",
                        "config": {"min_area": 8, "timeout_seconds": 5},
                    },
                    {
                        "id": "tolerant",
                        "config": {
                            "min_area": 8,
                            "color_tolerance": 10,
                            "timeout_seconds": 5,
                        },
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    return config


if __name__ == "__main__":
    unittest.main()
