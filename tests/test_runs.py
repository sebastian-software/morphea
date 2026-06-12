import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from curve.images import scene_from_flat_color_image
from curve.runs import (
    create_run_dir,
    render_html_report,
    render_markdown_report,
    write_html_report,
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
            self.assertTrue(run.html_report_path.exists())
            self.assertTrue(run.preview_path.exists())
            self.assertTrue(run.debug_svg_path.exists())
            self.assertTrue(run.anchors_path.exists())
            self.assertTrue(run.palette_path.exists())
            self.assertTrue(run.mask_summary_path.exists())
            manifest = json.loads(run.manifest_path.read_text())
            self.assertEqual(manifest["anchor_count"], 1)
            self.assertIn("raster_l1_error", manifest["metrics"])
            self.assertIn("raster_edge_error", manifest["metrics"])
            anchors = json.loads(run.anchors_path.read_text(encoding="utf-8"))
            palette = json.loads(run.palette_path.read_text(encoding="utf-8"))
            masks = json.loads(run.mask_summary_path.read_text(encoding="utf-8"))
            self.assertEqual(anchors["anchor_count"], 1)
            self.assertEqual(palette["colors"][0]["color"], "#dd2222")
            self.assertEqual(palette["colors"][0]["kinds"], {"circle": 1})
            self.assertEqual(masks["mask_count"], 1)
            self.assertEqual(masks["masks"][0]["id"], "mask-0000")
            self.assertEqual(masks["masks"][0]["anchor_id"], "anchor-0000")
            self.assertEqual(masks["masks"][0]["source"], "reserved_bounds")
            self.assertGreater(masks["masks"][0]["bounds_area"], 0.0)
            self.assertIn(
                "`raster_l1_error`",
                run.report_path.read_text(encoding="utf-8"),
            )
            self.assertIn(
                "Curve Vectorize Report",
                run.html_report_path.read_text(encoding="utf-8"),
            )

    def test_write_vectorize_run_applies_negative_mask_export_config(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "input.png"
            image = Image.new("RGB", (18, 9), "white")
            draw = ImageDraw.Draw(image)
            draw.rectangle((2, 2, 15, 6), fill="#003366")
            draw.rectangle((6, 4, 11, 4), fill="white")
            image.save(input_path)

            scene = scene_from_flat_color_image(input_path)
            run_dir = create_run_dir(Path(temp_dir) / "runs")
            run = write_vectorize_run(
                run_dir=run_dir,
                input_path=input_path,
                scene=scene,
                config={
                    "command": "vectorize",
                    "min_area": 8,
                    "cutout_export": "negative_mask",
                },
            )

            svg = run.svg_path.read_text(encoding="utf-8")
            self.assertIn('<mask id="curve-cutout-mask"', svg)
            self.assertIn('mask="url(#curve-cutout-mask)"', svg)
            self.assertNotIn('stroke="#ffffff"', svg)

    def test_render_markdown_report_summarizes_anchor_types(self):
        report = render_markdown_report(
            manifest={
                "width": 10,
                "height": 10,
                "anchor_count": 2,
                "anchors": [{"kind": "circle"}, {"kind": "circle"}],
                "layers": [{"name": "filled_primitives", "anchor_count": 2}],
                "diagnostics": [{"level": "warning", "code": "component_deferred"}],
                "groups": [
                    {
                        "kind": "same_color_fragment_group",
                        "color": "#dd2222",
                        "anchor_indexes": [0, 1],
                        "merge_plan": {
                            "action": "merge_adjacent_fragments",
                            "decision_reason": "compact_same_color_bounds",
                        },
                    }
                ],
                "metrics": {
                    "editability_score": 0.8,
                    "fragmentation_penalty": 0.1,
                    "anchor_quality_error_mean": 0.05,
                    "anchor_quality_error_max": 0.2,
                    "anchor_scoring_summary": {
                        "simple_shape_priority_bonus_total": 0.7,
                        "semantic_anchor_score_mean": -0.1,
                    },
                    "raster_l1_error": 0.2,
                },
            },
            config={"command": "vectorize"},
        )

        self.assertIn("# Curve Vectorize Report", report)
        self.assertIn("`circle`: 2", report)
        self.assertIn("- Layers: 1", report)
        self.assertIn("`filled_primitives`: 2", report)
        self.assertIn("`same_color_fragment_group`: 2 anchors, color #dd2222", report)
        self.assertIn("action merge_adjacent_fragments", report)
        self.assertIn("reason compact_same_color_bounds", report)
        self.assertIn("## Pipeline Stages", report)
        self.assertIn("`segmentation`: 1", report)
        self.assertIn("`warning` `component_deferred`", report)
        self.assertIn("- Editability score: 0.8", report)
        self.assertIn("- Anchor quality error mean: 0.05", report)
        self.assertIn("- Anchor quality error max: 0.2", report)
        self.assertIn("- Simple-shape priority bonus total: 0.7", report)
        self.assertIn("- Semantic anchor score mean: -0.1", report)
        self.assertIn("`fragmentation_penalty`: 0.1", report)
        self.assertIn("`raster_l1_error`: 0.2", report)

    def test_render_html_report_summarizes_anchor_types(self):
        report = render_html_report(
            manifest={
                "width": 10,
                "height": 10,
                "anchor_count": 2,
                "anchors": [{"kind": "circle"}, {"kind": "circle"}],
                "layers": [{"name": "filled_primitives", "anchor_count": 2}],
                "diagnostics": [{"level": "warning", "code": "component_deferred"}],
                "groups": [
                    {
                        "kind": "same_color_fragment_group",
                        "color": "#dd2222",
                        "anchor_indexes": [0, 1],
                        "merge_plan": {
                            "action": "merge_adjacent_fragments",
                            "decision_reason": "compact_same_color_bounds",
                        },
                    }
                ],
                "metrics": {
                    "editability_score": 0.8,
                    "fragmentation_penalty": 0.1,
                    "anchor_quality_error_mean": 0.05,
                    "anchor_quality_error_max": 0.2,
                    "anchor_scoring_summary": {
                        "simple_shape_priority_bonus_total": 0.7,
                        "semantic_anchor_score_mean": -0.1,
                    },
                    "raster_l1_error": 0.2,
                },
            },
            config={"command": "vectorize"},
        )

        self.assertIn("<h1>Curve Vectorize Report</h1>", report)
        self.assertIn("<code>circle</code>", report)
        self.assertIn("<td>2</td>", report)
        self.assertIn("<code>filled_primitives</code>", report)
        self.assertIn("<code>same_color_fragment_group</code>", report)
        self.assertIn("2 anchors, color #dd2222", report)
        self.assertIn("action merge_adjacent_fragments", report)
        self.assertIn("reason compact_same_color_bounds", report)
        self.assertIn("Anchor quality error mean", report)
        self.assertIn("Anchor quality error max", report)
        self.assertIn("Simple-shape priority bonus total", report)
        self.assertIn("Semantic anchor score mean", report)
        self.assertIn("<h2>Pipeline Stages</h2>", report)
        self.assertIn("<code>segmentation</code>", report)
        self.assertIn("<td>component_deferred</td>", report)
        self.assertIn("<code>raster_l1_error</code>", report)

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

    def test_write_html_report_reads_manifest_and_config(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manifest = Path(temp_dir) / "manifest.json"
            config = Path(temp_dir) / "config.json"
            output = Path(temp_dir) / "report.html"
            manifest.write_text(
                json.dumps(
                    {
                        "width": 16,
                        "height": 16,
                        "anchor_count": 1,
                        "anchors": [{"kind": "circle"}],
                        "layers": [],
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

            report = write_html_report(
                manifest=manifest,
                config=config,
                output=output,
            )

            self.assertTrue(output.exists())
            self.assertIn("<code>circle</code>", report)
            self.assertIn("&quot;min_area&quot;: 8", output.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
