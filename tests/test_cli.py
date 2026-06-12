import tempfile
import unittest
import json
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageDraw

from curve.cli import main
from curve.dataset import generate_synthetic_dataset
from curve.classifier import train_centroid_classifier


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

    def test_status_cli_writes_json_and_markdown(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "status.json"
            markdown = Path(temp_dir) / "status.md"

            with (
                patch("curve.segmenters.is_mlx_runtime_available", return_value=False),
                redirect_stdout(StringIO()),
            ):
                main(["status", "-o", str(output), "--markdown", str(markdown)])

            status = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(status["schema_version"], 1)
            self.assertIn("flat_color", status["segmenters"])
            self.assertIn("mlx", status["classifiers"])
            self.assertTrue(markdown.exists())

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

    def test_vectorize_reads_runtime_config_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "input.png"
            output_path = Path(temp_dir) / "output.svg"
            config_path = Path(temp_dir) / "vectorize.json"
            image = Image.new("RGB", (16, 16), "white")
            draw = ImageDraw.Draw(image)
            draw.ellipse((3, 3, 12, 12), fill="#dd2222")
            draw.point(((7, 3), (8, 12)), fill="#e02a2a")
            image.save(input_path)
            config_path.write_text(
                json.dumps({"color_tolerance": 18, "min_area": 8}),
                encoding="utf-8",
            )

            with redirect_stdout(StringIO()):
                main(
                    [
                        "vectorize",
                        str(input_path),
                        "-o",
                        str(output_path),
                        "--config",
                        str(config_path),
                    ]
                )

            manifest = json.loads(output_path.with_suffix(".json").read_text())
            self.assertEqual(manifest["anchor_count"], 1)

    def test_vectorize_cli_args_override_config_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "input.png"
            output_path = Path(temp_dir) / "output.svg"
            config_path = Path(temp_dir) / "vectorize.json"
            image = Image.new("RGB", (16, 16), "white")
            draw = ImageDraw.Draw(image)
            draw.ellipse((3, 3, 12, 12), fill="#dd2222")
            image.save(input_path)
            config_path.write_text(json.dumps({"min_area": 999}), encoding="utf-8")

            with redirect_stdout(StringIO()):
                main(
                    [
                        "vectorize",
                        str(input_path),
                        "-o",
                        str(output_path),
                        "--config",
                        str(config_path),
                        "--min-area",
                        "8",
                    ]
                )

            manifest = json.loads(output_path.with_suffix(".json").read_text())
            self.assertEqual(manifest["anchor_count"], 1)

    def test_vectorize_config_accepts_explicit_background(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "input.png"
            output_path = Path(temp_dir) / "output.svg"
            config_path = Path(temp_dir) / "vectorize.json"
            image = Image.new("RGB", (18, 14), "#f6f6f6")
            draw = ImageDraw.Draw(image)
            draw.rectangle((0, 0, 8, 5), fill="#003366")
            image.save(input_path)
            config_path.write_text(
                json.dumps({"background": "#f6f6f6", "min_area": 4}),
                encoding="utf-8",
            )

            with redirect_stdout(StringIO()):
                main(
                    [
                        "vectorize",
                        str(input_path),
                        "-o",
                        str(output_path),
                        "--config",
                        str(config_path),
                    ]
                )

            manifest = json.loads(output_path.with_suffix(".json").read_text())
            self.assertEqual(manifest["anchor_count"], 1)
            self.assertEqual(manifest["anchors"][0]["color"], "#003366")

    def test_vectorize_config_rejects_unknown_keys(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "input.png"
            output_path = Path(temp_dir) / "output.svg"
            config_path = Path(temp_dir) / "vectorize.json"
            Image.new("RGB", (8, 8), "white").save(input_path)
            config_path.write_text(json.dumps({"unknown": 1}), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "unsupported vectorize config keys"):
                main(
                    [
                        "vectorize",
                        str(input_path),
                        "-o",
                        str(output_path),
                        "--config",
                        str(config_path),
                    ]
                )

    def test_vectorize_reads_cutout_export_from_config_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "input.png"
            output_path = Path(temp_dir) / "output.svg"
            config_path = Path(temp_dir) / "vectorize.json"
            image = Image.new("RGB", (18, 9), "white")
            draw = ImageDraw.Draw(image)
            draw.rectangle((2, 2, 15, 6), fill="#003366")
            draw.rectangle((6, 4, 11, 4), fill="white")
            image.save(input_path)
            config_path.write_text(
                json.dumps({"min_area": 8, "cutout_export": "negative_mask"}),
                encoding="utf-8",
            )

            with redirect_stdout(StringIO()):
                main(
                    [
                        "vectorize",
                        str(input_path),
                        "-o",
                        str(output_path),
                        "--config",
                        str(config_path),
                    ]
                )

            svg = output_path.read_text(encoding="utf-8")
            self.assertIn('<mask id="curve-cutout-mask"', svg)

    def test_vectorize_cutout_export_flag_overrides_config_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "input.png"
            output_path = Path(temp_dir) / "output.svg"
            config_path = Path(temp_dir) / "vectorize.json"
            image = Image.new("RGB", (18, 9), "white")
            draw = ImageDraw.Draw(image)
            draw.rectangle((2, 2, 15, 6), fill="#003366")
            draw.rectangle((6, 4, 11, 4), fill="white")
            image.save(input_path)
            config_path.write_text(
                json.dumps({"min_area": 8, "cutout_export": "negative_mask"}),
                encoding="utf-8",
            )

            with redirect_stdout(StringIO()):
                main(
                    [
                        "vectorize",
                        str(input_path),
                        "-o",
                        str(output_path),
                        "--config",
                        str(config_path),
                        "--cutout-export",
                        "overlay_stroke",
                    ]
                )

            svg = output_path.read_text(encoding="utf-8")
            self.assertNotIn('<mask id="curve-cutout-mask"', svg)
            self.assertIn('stroke="#ffffff"', svg)

    def test_vectorize_manifest_includes_cutout_strokes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "input.png"
            output_path = Path(temp_dir) / "output.svg"
            image = Image.new("RGB", (18, 9), "white")
            draw = ImageDraw.Draw(image)
            draw.rectangle((2, 2, 15, 6), fill="#003366")
            draw.rectangle((6, 4, 11, 4), fill="white")
            image.save(input_path)

            with redirect_stdout(StringIO()):
                main(["vectorize", str(input_path), "-o", str(output_path)])

            manifest = json.loads(output_path.with_suffix(".json").read_text())
            cutouts = [
                anchor
                for anchor in manifest["anchors"]
                if anchor.get("stroke", {}).get("is_cutout")
            ]
            self.assertEqual(len(cutouts), 1)
            self.assertEqual(cutouts[0]["color"], "#ffffff")

    def test_vectorize_can_export_cutouts_as_negative_mask(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "input.png"
            output_path = Path(temp_dir) / "output.svg"
            image = Image.new("RGB", (18, 9), "white")
            draw = ImageDraw.Draw(image)
            draw.rectangle((2, 2, 15, 6), fill="#003366")
            draw.rectangle((6, 4, 11, 4), fill="white")
            image.save(input_path)

            with redirect_stdout(StringIO()):
                main(
                    [
                        "vectorize",
                        str(input_path),
                        "-o",
                        str(output_path),
                        "--cutout-export",
                        "negative_mask",
                    ]
                )

            svg = output_path.read_text(encoding="utf-8")
            manifest = json.loads(output_path.with_suffix(".json").read_text())
            self.assertIn('<mask id="curve-cutout-mask"', svg)
            self.assertIn('mask="url(#curve-cutout-mask)"', svg)
            self.assertIn('stroke="black"', svg)
            self.assertNotIn('stroke="#ffffff"', svg)
            self.assertEqual(
                manifest["metrics"]["negative_mask_candidate_count"],
                1,
            )

    def test_vectorize_writes_runtime_diagnostics(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "input.png"
            output_path = Path(temp_dir) / "output.svg"
            image = Image.new("RGB", (40, 40), "white")
            draw = ImageDraw.Draw(image)
            draw.ellipse((8, 8, 31, 31), fill="#dd2222")
            image.save(input_path)

            with redirect_stdout(StringIO()):
                main(
                    [
                        "vectorize",
                        str(input_path),
                        "-o",
                        str(output_path),
                        "--max-size",
                        "20",
                        "--max-component-area",
                        "20",
                        "--timeout-seconds",
                        "5",
                    ]
                )

            manifest = json.loads(output_path.with_suffix(".json").read_text())
            codes = [diagnostic["code"] for diagnostic in manifest["diagnostics"]]
            self.assertIn("image_resized_for_analysis", codes)
            self.assertIn("color_mask_split_for_components", codes)
            self.assertIn("component_deferred", codes)

    def test_vectorize_can_write_run_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "input.png"
            output_path = Path(temp_dir) / "ignored.svg"
            run_root = Path(temp_dir) / "runs"
            image = Image.new("RGB", (24, 16), "white")
            draw = ImageDraw.Draw(image)
            draw.ellipse((2, 2, 10, 10), fill="#dd2222")
            image.save(input_path)

            with redirect_stdout(StringIO()):
                main(
                    [
                        "vectorize",
                        str(input_path),
                        "-o",
                        str(output_path),
                        "--run-dir",
                        str(run_root),
                    ]
                )

            run_dirs = list(run_root.iterdir())
            self.assertEqual(len(run_dirs), 1)
            self.assertTrue((run_dirs[0] / "input" / "input.png").exists())
            self.assertTrue((run_dirs[0] / "output.svg").exists())
            self.assertTrue((run_dirs[0] / "manifest.json").exists())
            self.assertTrue((run_dirs[0] / "config.json").exists())
            self.assertTrue((run_dirs[0] / "report.md").exists())
            self.assertTrue((run_dirs[0] / "debug.svg").exists())

    def test_vectorize_config_accepts_scoring_weights(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_path = root / "input.png"
            output_path = root / "ignored.svg"
            run_root = root / "runs"
            config_path = root / "vectorize-config.json"
            image = Image.new("RGB", (24, 16), "white")
            draw = ImageDraw.Draw(image)
            draw.ellipse((2, 2, 10, 10), fill="#dd2222")
            image.save(input_path)
            config_path.write_text(
                json.dumps(
                    {
                        "min_area": 4,
                        "simple_shape_bonus_weight": 2.0,
                        "node_complexity_weight": 0.02,
                    }
                ),
                encoding="utf-8",
            )

            with redirect_stdout(StringIO()):
                main(
                    [
                        "vectorize",
                        str(input_path),
                        "-o",
                        str(output_path),
                        "--run-dir",
                        str(run_root),
                        "--config",
                        str(config_path),
                    ]
                )

            run_dir = next(run_root.iterdir())
            config = json.loads((run_dir / "config.json").read_text(encoding="utf-8"))
            self.assertEqual(config["simple_shape_bonus_weight"], 2.0)
            self.assertEqual(config["node_complexity_weight"], 0.02)

    def test_vectorize_config_accepts_anchor_thresholds(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_path = root / "input.png"
            output_path = root / "ignored.svg"
            run_root = root / "runs"
            config_path = root / "vectorize-config.json"
            image = Image.new("RGB", (24, 16), "white")
            draw = ImageDraw.Draw(image)
            draw.rectangle((4, 4, 14, 8), fill="#003366")
            image.save(input_path)
            config_path.write_text(
                json.dumps(
                    {
                        "min_area": 4,
                        "rect_max_fill_error": 0.05,
                        "stroke_min_length_width_ratio": 4.0,
                    }
                ),
                encoding="utf-8",
            )

            with redirect_stdout(StringIO()):
                main(
                    [
                        "vectorize",
                        str(input_path),
                        "-o",
                        str(output_path),
                        "--run-dir",
                        str(run_root),
                        "--config",
                        str(config_path),
                    ]
                )

            run_dir = next(run_root.iterdir())
            config = json.loads((run_dir / "config.json").read_text(encoding="utf-8"))
            self.assertEqual(config["rect_max_fill_error"], 0.05)
            self.assertEqual(config["stroke_min_length_width_ratio"], 4.0)

    def test_vectorize_can_write_debug_svg(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "input.png"
            output_path = Path(temp_dir) / "output.svg"
            debug_path = Path(temp_dir) / "debug.svg"
            image = Image.new("RGB", (24, 16), "white")
            draw = ImageDraw.Draw(image)
            draw.ellipse((2, 2, 10, 10), fill="#dd2222")
            image.save(input_path)

            with redirect_stdout(StringIO()):
                main(
                    [
                        "vectorize",
                        str(input_path),
                        "-o",
                        str(output_path),
                        "--debug-svg",
                        str(debug_path),
                    ]
                )

            debug_svg = debug_path.read_text(encoding="utf-8")
            self.assertIn('id="anchor-0000"', debug_svg)
            self.assertIn("anchor-0000:circle", debug_svg)

    def test_vectorize_accepts_classifier_model_prior(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            generate_synthetic_dataset(
                output_dir=Path(temp_dir) / "dataset",
                count=4,
                seed=40,
                width=64,
                height=64,
                val_count=1,
                test_count=1,
            )
            model_path = Path(temp_dir) / "model.json"
            train_centroid_classifier(Path(temp_dir) / "dataset" / "dataset.json", output=model_path)
            input_path = Path(temp_dir) / "input.png"
            output_path = Path(temp_dir) / "output.svg"
            image = Image.new("RGB", (24, 16), "white")
            draw = ImageDraw.Draw(image)
            draw.ellipse((2, 2, 10, 10), fill="#dd2222")
            image.save(input_path)

            with redirect_stdout(StringIO()):
                main(
                    [
                        "vectorize",
                        str(input_path),
                        "-o",
                        str(output_path),
                        "--classifier-model",
                        str(model_path),
                    ]
                )

            manifest = json.loads(output_path.with_suffix(".json").read_text())
            self.assertIn(
                "classifier_prior_error",
                manifest["anchors"][0]["metrics"],
            )

    def test_vectorize_accepts_mlx_feature_head_classifier_model(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            model_path = Path(temp_dir) / "mlx-model.json"
            model_path.write_text(
                json.dumps(
                    {
                        "model_type": "mlx_transformer_primitive_classifier",
                        "classes": ["circle", "cubic_path"],
                        "fallback_centroids": {},
                        "mlx_training": {
                            "weight_format": "mlx_feature_head_v1",
                            "labels": ["circle", "cubic_path"],
                            "weights": [
                                [
                                    0.0, 0.0, 8.0, 0.0, 0.0, 0.0,
                                    0.0, 0.0, 0.0, 0.0, 0.0,
                                ],
                                [
                                    0.0, 0.0, -8.0, 0.0, 0.0, 0.0,
                                    0.0, 0.0, 0.0, 0.0, 0.0,
                                ],
                            ],
                            "bias": [0.0, 0.0],
                            "normalization": {
                                "mean": [0.0] * 11,
                                "scale": [1.0] * 11,
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )
            input_path = Path(temp_dir) / "input.png"
            output_path = Path(temp_dir) / "output.svg"
            image = Image.new("RGB", (24, 16), "white")
            draw = ImageDraw.Draw(image)
            draw.ellipse((2, 2, 10, 10), fill="#dd2222")
            image.save(input_path)

            with redirect_stdout(StringIO()):
                main(
                    [
                        "vectorize",
                        str(input_path),
                        "-o",
                        str(output_path),
                        "--classifier-model",
                        str(model_path),
                    ]
                )

            manifest = json.loads(output_path.with_suffix(".json").read_text())
            self.assertEqual(
                manifest["anchors"][0]["metrics"]["classifier_prior_error"],
                0.0,
            )

    def test_report_cli_writes_markdown_report(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manifest = Path(temp_dir) / "manifest.json"
            output = Path(temp_dir) / "report.md"
            manifest.write_text(
                json.dumps(
                    {
                        "width": 12,
                        "height": 12,
                        "anchor_count": 1,
                        "anchors": [{"kind": "quad"}],
                        "groups": [],
                        "diagnostics": [],
                    }
                ),
                encoding="utf-8",
            )

            with redirect_stdout(StringIO()):
                main(["report", str(manifest), "-o", str(output)])

            self.assertIn(
                "`quad`: 1",
                output.read_text(encoding="utf-8"),
            )

    def test_report_cli_writes_html_report(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manifest = Path(temp_dir) / "manifest.json"
            output = Path(temp_dir) / "report.html"
            manifest.write_text(
                json.dumps(
                    {
                        "width": 12,
                        "height": 12,
                        "anchor_count": 1,
                        "anchors": [{"kind": "quad"}],
                        "layers": [],
                        "groups": [],
                        "diagnostics": [],
                        "metrics": {"editability_score": 0.5},
                    }
                ),
                encoding="utf-8",
            )

            with redirect_stdout(StringIO()):
                main(["report", str(manifest), "-o", str(output)])

            html = output.read_text(encoding="utf-8")
            self.assertIn("<h1>Curve Vectorize Report</h1>", html)
            self.assertIn("<code>quad</code>", html)


if __name__ == "__main__":
    unittest.main()
