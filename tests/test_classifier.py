import json
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from curve.classifier import (
    FEATURE_NAMES,
    anchors_from_dataset,
    classifier_prior_error,
    component_raster_tokens,
    evaluate_classifier_model,
    evaluate_classifier_ranking,
    evaluate_raster_classifier,
    examples_from_dataset,
    features_from_anchor,
    features_from_candidate,
    load_classifier_model,
    load_centroid_model,
    predict_classifier_label,
    raster_examples_from_dataset,
    train_centroid_classifier,
)
from curve.cli import main
from curve.dataset import generate_synthetic_dataset
from curve.anchors import AnchorCandidate, AnchorKind, CircleAnchor, Point
from curve.masks import BinaryMask, connected_components
from curve.mlx_classifier import (
    MLX_MODEL_TYPE,
    MlxClassifierTrainingConfig,
    mlx_classifier_runtime_status,
    train_mlx_transformer_classifier,
)


class PrimitiveClassifierTests(unittest.TestCase):
    def test_features_from_anchor_marks_circle_geometry(self):
        features = features_from_anchor(
            {
                "kind": "circle",
                "node_count": 1,
                "parameter_count": 3,
                "circle": {"cx": 10, "cy": 12, "r": 6},
            }
        )

        self.assertEqual(features[0], 1.0)
        self.assertEqual(features[2], 1.0)
        self.assertEqual(features[3], 6.0)

    def test_features_from_anchor_include_quad_subtype_code(self):
        features = features_from_anchor(
            {
                "kind": "quad",
                "node_count": 4,
                "parameter_count": 8,
                "quad": {
                    "corners": [
                        {"x": 1, "y": 2},
                        {"x": 17, "y": 3},
                        {"x": 15, "y": 12},
                        {"x": 3, "y": 11},
                    ]
                },
                "metrics": {"quad_subtype_code": 2.0},
            }
        )

        self.assertEqual(len(features), len(FEATURE_NAMES))
        self.assertEqual(FEATURE_NAMES[-1], "quad_subtype_code")
        self.assertEqual(features[-1], 2.0)

    def test_examples_from_dataset_reads_train_split_manifests(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            generate_synthetic_dataset(
                output_dir=temp_dir,
                count=3,
                seed=1,
                width=64,
                height=64,
                val_count=1,
                test_count=1,
            )

            examples = examples_from_dataset(Path(temp_dir) / "dataset.json")
            anchors = anchors_from_dataset(Path(temp_dir) / "dataset.json")

            self.assertEqual(len(examples), 15)
            self.assertEqual(len(anchors), 15)
            self.assertEqual({example.label for example in examples}, {
                "arc",
                "circle",
                "quad",
                "rect",
                "rounded_rect",
                "stroke_circle",
                "stroke_path",
                "stroke_polyline",
            })

    def test_raster_examples_from_dataset_reads_rgba_crop_tokens(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            generate_synthetic_dataset(
                output_dir=temp_dir,
                count=3,
                seed=2,
                width=64,
                height=64,
                val_count=1,
                test_count=1,
            )

            examples = raster_examples_from_dataset(
                Path(temp_dir) / "dataset.json",
                crop_size=4,
            )

            self.assertEqual(len(examples), 15)
            self.assertEqual(len(examples[0].crop_tokens), 16)
            self.assertEqual(len(examples[0].crop_tokens[0]), 4)
            self.assertTrue(
                all(0.0 <= value <= 1.0 for value in examples[0].crop_tokens[0])
            )
            self.assertGreater(examples[0].bounds[2], examples[0].bounds[0])
            self.assertEqual(examples[0].sample_id, "sample-0000")

    def test_component_raster_tokens_sample_runtime_mask_crop(self):
        mask = BinaryMask.from_rows(
            [
                "....",
                ".##.",
                ".##.",
                "....",
            ]
        )
        component = connected_components(mask)[0]

        tokens = component_raster_tokens(component, color="#dd2222", crop_size=4)

        self.assertEqual(len(tokens), 16)
        self.assertIn((221 / 255, 34 / 255, 34 / 255, 1.0), tokens)
        self.assertIn((1.0, 1.0, 1.0, 1.0), tokens)

    def test_train_centroid_classifier_writes_model_with_evaluation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            generate_synthetic_dataset(
                output_dir=temp_dir,
                count=4,
                seed=10,
                width=64,
                height=64,
                val_count=1,
                test_count=1,
            )
            model_path = Path(temp_dir) / "model.json"

            model = train_centroid_classifier(
                Path(temp_dir) / "dataset.json",
                output=model_path,
            )

            self.assertTrue(model_path.exists())
            self.assertEqual(model["model_type"], "centroid_primitive_classifier")
            self.assertIn("circle", model["classes"])
            self.assertIn("val", model["evaluation"])
            self.assertIn("val", model["ranking_evaluation"])
            self.assertGreaterEqual(
                model["ranking_evaluation"]["val"]["classifier_accuracy"],
                model["ranking_evaluation"]["val"]["heuristic_accuracy"],
            )

    def test_train_cli_writes_model(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            generate_synthetic_dataset(
                output_dir=temp_dir,
                count=4,
                seed=20,
                width=64,
                height=64,
                val_count=1,
                test_count=1,
            )
            model_path = Path(temp_dir) / "model.json"

            with redirect_stdout(StringIO()):
                main(["train", str(Path(temp_dir) / "dataset.json"), "-o", str(model_path)])

            model = json.loads(model_path.read_text())
            self.assertEqual(model["train_examples"], 30)
            self.assertIn("ranking_evaluation", model)

    def test_train_cli_accepts_config_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            generate_synthetic_dataset(
                output_dir=temp_dir,
                count=4,
                seed=21,
                width=64,
                height=64,
                val_count=1,
                test_count=1,
            )
            root = Path(temp_dir)
            model_path = root / "model.json"
            config = root / "train-config.json"
            config.write_text(
                json.dumps(
                    {
                        "dataset": str(root / "dataset.json"),
                        "output": str(model_path),
                    }
                ),
                encoding="utf-8",
            )

            with redirect_stdout(StringIO()):
                main(["train", "--config", str(config)])

            model = json.loads(model_path.read_text(encoding="utf-8"))
            self.assertEqual(model["train_examples"], 30)

    def test_train_mlx_requires_backend_by_default(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            generate_synthetic_dataset(
                output_dir=temp_dir,
                count=4,
                seed=22,
                width=64,
                height=64,
                val_count=1,
                test_count=1,
            )

            with patch("curve.mlx_classifier.is_mlx_available", return_value=False):
                with self.assertRaisesRegex(RuntimeError, "status=not_installed"):
                    train_mlx_transformer_classifier(
                        Path(temp_dir) / "dataset.json",
                        output=Path(temp_dir) / "mlx-model.json",
                    )

    def test_train_mlx_rejects_invalid_crop_size(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            generate_synthetic_dataset(
                output_dir=temp_dir,
                count=3,
                seed=22,
                width=64,
                height=64,
                val_count=1,
                test_count=1,
            )

            with self.assertRaisesRegex(ValueError, "crop_size must be positive"):
                train_mlx_transformer_classifier(
                    Path(temp_dir) / "dataset.json",
                    output=Path(temp_dir) / "mlx-model.json",
                    config=MlxClassifierTrainingConfig(
                        crop_size=0,
                        allow_unavailable=True,
                    ),
                )

    def test_train_mlx_rejects_invalid_head_count(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            generate_synthetic_dataset(
                output_dir=temp_dir,
                count=3,
                seed=22,
                width=64,
                height=64,
                val_count=1,
                test_count=1,
            )

            with self.assertRaisesRegex(ValueError, "num_heads must be positive"):
                train_mlx_transformer_classifier(
                    Path(temp_dir) / "dataset.json",
                    output=Path(temp_dir) / "mlx-model.json",
                    config=MlxClassifierTrainingConfig(
                        num_heads=0,
                        allow_unavailable=True,
                    ),
                )

    def test_mlx_classifier_runtime_status_reports_package_state(self):
        with patch("curve.mlx_classifier.is_mlx_available", return_value=False):
            unavailable = mlx_classifier_runtime_status()
        with patch("curve.mlx_classifier.is_mlx_available", return_value=True):
            available = mlx_classifier_runtime_status()

        self.assertEqual(unavailable["status"], "not_installed")
        self.assertFalse(unavailable["backend_available"])
        self.assertEqual(unavailable["training_implementation"], "centroid_fallback")
        self.assertEqual(available["status"], "available")
        self.assertTrue(available["backend_available"])
        self.assertEqual(available["training_implementation"], "mlx_feature_head")

    def test_train_mlx_can_write_unavailable_fallback_artifact(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            generate_synthetic_dataset(
                output_dir=temp_dir,
                count=4,
                seed=23,
                width=64,
                height=64,
                val_count=1,
                test_count=1,
            )
            model_path = Path(temp_dir) / "mlx-model.json"

            with patch("curve.mlx_classifier.is_mlx_available", return_value=False):
                model = train_mlx_transformer_classifier(
                    Path(temp_dir) / "dataset.json",
                    output=model_path,
                    config=MlxClassifierTrainingConfig(
                        epochs=3,
                        hidden_dim=16,
                        num_heads=2,
                        allow_unavailable=True,
                    ),
                )
            centroids = load_centroid_model(model_path)

            self.assertTrue(model_path.exists())
            self.assertEqual(model["model_type"], MLX_MODEL_TYPE)
            self.assertEqual(model["status"], "unavailable")
            self.assertEqual(model["runtime"]["status"], "not_installed")
            self.assertEqual(model["training_implementation"], "centroid_fallback")
            self.assertEqual(model["training_config"]["epochs"], 3)
            self.assertIn("circle", model["fallback_centroids"])
            self.assertIn("circle", centroids)
            self.assertIn("ranking_evaluation", model)

    def test_train_mlx_cli_accepts_config_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            generate_synthetic_dataset(
                output_dir=temp_dir,
                count=4,
                seed=24,
                width=64,
                height=64,
                val_count=1,
                test_count=1,
            )
            root = Path(temp_dir)
            model_path = root / "mlx-model.json"
            config = root / "train-mlx.json"
            config.write_text(
                json.dumps(
                    {
                        "dataset": str(root / "dataset.json"),
                        "output": str(model_path),
                        "epochs": 2,
                        "hidden_dim": 12,
                        "num_heads": 2,
                        "num_layers": 1,
                        "learning_rate": 0.002,
                        "crop_size": 6,
                        "allow_unavailable": True,
                    }
                ),
                encoding="utf-8",
            )

            with patch("curve.mlx_classifier.is_mlx_available", return_value=False):
                with redirect_stdout(StringIO()):
                    main(["train-mlx", "--config", str(config)])

            model = json.loads(model_path.read_text(encoding="utf-8"))
            self.assertEqual(model["model_type"], MLX_MODEL_TYPE)
            self.assertEqual(model["training_config"]["learning_rate"], 0.002)
            self.assertEqual(model["training_config"]["crop_size"], 6)

    def test_train_mlx_records_available_runtime_with_trained_feature_head(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            generate_synthetic_dataset(
                output_dir=temp_dir,
                count=4,
                seed=25,
                width=64,
                height=64,
                val_count=1,
                test_count=1,
            )
            model_path = Path(temp_dir) / "mlx-model.json"
            mlx_module = types.ModuleType("mlx")
            mlx_core = types.ModuleType("mlx.core")
            mlx_core.__version__ = "test-mlx"
            mlx_module.core = mlx_core

            with (
                patch("curve.mlx_classifier.is_mlx_available", return_value=True),
                patch.dict(sys.modules, {"mlx": mlx_module, "mlx.core": mlx_core}),
            ):
                model = train_mlx_transformer_classifier(
                    Path(temp_dir) / "dataset.json",
                    output=model_path,
                    config=MlxClassifierTrainingConfig(epochs=1, crop_size=6),
                )

            self.assertEqual(model["status"], "trained")
            self.assertEqual(model["runtime"]["status"], "available")
            self.assertEqual(model["training_implementation"], "mlx_feature_head")
            self.assertEqual(
                model["mlx_training"]["weight_format"],
                "mlx_feature_head_v1",
            )
            self.assertGreater(model["mlx_training"]["parameter_count"], 0)
            self.assertEqual(model["mlx_training"]["backend_version"], "test-mlx")
            self.assertEqual(len(model["mlx_training"]["loss_history"]), 1)
            self.assertIn("weights", model["mlx_training"])
            self.assertEqual(
                model["mlx_training"]["transformer_status"],
                "raster_token_mixer_trained_attention_block_pending",
            )
            self.assertEqual(model["mlx_training"]["crop_token_spec"]["crop_size"], 6)
            self.assertEqual(
                model["mlx_training"]["crop_token_spec"]["token_shape"],
                [36, 4],
            )
            self.assertEqual(
                model["mlx_training"]["crop_token_summary"]["raster_example_count"],
                model["train_examples"],
            )
            mixer = model["mlx_training"]["raster_token_mixer"]
            self.assertEqual(mixer["weight_format"], "raster_token_mixer_v1")
            self.assertEqual(mixer["attention"]["heads"], 4)
            self.assertEqual(len(mixer["attention"]["embedding_names"]), 28)
            self.assertEqual(len(mixer["loss_history"]), 1)
            self.assertGreater(mixer["parameter_count"], 0)

    def test_load_classifier_model_uses_mlx_feature_head_predictor(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            generate_synthetic_dataset(
                output_dir=temp_dir,
                count=4,
                seed=26,
                width=64,
                height=64,
                val_count=1,
                test_count=1,
            )
            model_path = Path(temp_dir) / "mlx-model.json"
            mlx_module = types.ModuleType("mlx")
            mlx_core = types.ModuleType("mlx.core")
            mlx_core.__version__ = "test-mlx"
            mlx_module.core = mlx_core
            candidate = AnchorCandidate(
                kind=AnchorKind.CIRCLE,
                raster_error=0.0,
                node_count=1,
                parameter_count=3,
                circle=CircleAnchor(center=Point(10, 10), radius=6),
            )

            with (
                patch("curve.mlx_classifier.is_mlx_available", return_value=True),
                patch.dict(sys.modules, {"mlx": mlx_module, "mlx.core": mlx_core}),
            ):
                train_mlx_transformer_classifier(
                    Path(temp_dir) / "dataset.json",
                    output=model_path,
                    config=MlxClassifierTrainingConfig(epochs=1, crop_size=6),
                )

            classifier = load_classifier_model(model_path)
            predicted = predict_classifier_label(
                classifier,
                features_from_candidate(candidate),
            )

            self.assertEqual(classifier["classifier_backend"], "mlx_feature_head")
            self.assertIn(predicted, classifier["labels"])

    def test_mlx_feature_head_can_predict_with_raster_tokens(self):
        classifier = {
            "classifier_backend": "mlx_feature_head",
            "labels": ("circle", "cubic_path"),
            "weights": ((0.0,) * 11, (0.0,) * 11),
            "bias": (0.0, 0.0),
            "normalization": {
                "mean": (0.0,) * 11,
                "scale": (1.0,) * 11,
            },
            "crop_token_spec": {"crop_size": 2},
            "raster_token_mixer": {
                "labels": ("circle", "cubic_path"),
                "weights": (
                    (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 8.0),
                    (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, -8.0),
                ),
                "bias": (0.0, 0.0),
                "normalization": {
                    "mean": (0.0,) * 7,
                    "scale": (1.0,) * 7,
                },
                "attention": {
                    "heads": 1,
                    "embedding_names": (
                        "head_0_red",
                        "head_0_green",
                        "head_0_blue",
                        "head_0_alpha",
                        "head_0_x",
                        "head_0_y",
                        "head_0_foreground",
                    ),
                },
            },
        }

        predicted = predict_classifier_label(
            classifier,
            (0.0,) * 11,
            crop_tokens=(
                (0.0, 0.0, 0.0, 1.0),
                (1.0, 1.0, 1.0, 1.0),
                (1.0, 1.0, 1.0, 1.0),
                (1.0, 1.0, 1.0, 1.0),
            ),
        )

        self.assertEqual(predicted, "circle")

    def test_empty_mlx_fallback_prior_degrades_to_no_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            model_path = Path(temp_dir) / "mlx-model.json"
            model_path.write_text(
                json.dumps(
                    {
                        "model_type": "mlx_transformer_primitive_classifier",
                        "fallback_centroids": {},
                    }
                ),
                encoding="utf-8",
            )
            classifier = load_classifier_model(model_path)
            candidate = AnchorCandidate(
                kind=AnchorKind.CIRCLE,
                raster_error=0.0,
                node_count=1,
                parameter_count=3,
                circle=CircleAnchor(center=Point(10, 10), radius=6),
            )

            self.assertEqual(classifier_prior_error(classifier, candidate), 0.0)

    def test_classifier_ranking_compares_heuristic_and_prior(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            generate_synthetic_dataset(
                output_dir=temp_dir,
                count=4,
                seed=40,
                width=64,
                height=64,
                val_count=1,
                test_count=1,
            )
            dataset = Path(temp_dir) / "dataset.json"
            model_path = Path(temp_dir) / "model.json"
            train_centroid_classifier(dataset, output=model_path)

            ranking = evaluate_classifier_ranking(
                load_centroid_model(model_path),
                anchors_from_dataset(dataset, splits=("val",)),
            )

            self.assertEqual(ranking["examples"], 15)
            self.assertGreaterEqual(
                ranking["classifier_accuracy"],
                ranking["heuristic_accuracy"],
            )
            self.assertGreater(ranking["changed_decisions"], 0)

    def test_evaluate_classifier_model_writes_report(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            generate_synthetic_dataset(
                output_dir=temp_dir,
                count=4,
                seed=41,
                width=64,
                height=64,
                val_count=1,
                test_count=1,
            )
            dataset = Path(temp_dir) / "dataset.json"
            model_path = Path(temp_dir) / "model.json"
            report_path = Path(temp_dir) / "classifier-eval.json"
            train_centroid_classifier(dataset, output=model_path)

            report = evaluate_classifier_model(
                model_path,
                dataset,
                output=report_path,
                splits=("val",),
            )

            self.assertTrue(report_path.exists())
            self.assertEqual(report["schema_version"], 1)
            self.assertEqual(report["splits"], ["val"])
            self.assertEqual(report["evaluation"]["val"]["examples"], 15)
            self.assertEqual(report["ranking_evaluation"]["val"]["examples"], 15)

    def test_eval_classifier_cli_writes_report(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            generate_synthetic_dataset(
                output_dir=temp_dir,
                count=4,
                seed=42,
                width=64,
                height=64,
                val_count=1,
                test_count=1,
            )
            dataset = Path(temp_dir) / "dataset.json"
            model_path = Path(temp_dir) / "model.json"
            report_path = Path(temp_dir) / "classifier-eval.json"
            markdown_path = Path(temp_dir) / "classifier-eval.md"
            train_centroid_classifier(dataset, output=model_path)

            with redirect_stdout(StringIO()):
                main(
                    [
                        "eval-classifier",
                        str(model_path),
                        str(dataset),
                        "-o",
                        str(report_path),
                        "--markdown",
                        str(markdown_path),
                        "--splits",
                        "test",
                    ]
                )

            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["splits"], ["test"])
            self.assertIn("test", report["evaluation"])
            self.assertIn("test", report["ranking_evaluation"])
            self.assertFalse(report["uses_raster_tokens"])
            self.assertIn(
                "# Curve Classifier Evaluation",
                markdown_path.read_text(encoding="utf-8"),
            )

    def test_eval_classifier_model_uses_raster_tokens_for_mlx_mixer(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            generate_synthetic_dataset(
                output_dir=temp_dir,
                count=4,
                seed=44,
                width=64,
                height=64,
                val_count=1,
                test_count=1,
            )
            dataset = Path(temp_dir) / "dataset.json"
            model_path = Path(temp_dir) / "mlx-model.json"
            report_path = Path(temp_dir) / "classifier-eval.json"
            mlx_module = types.ModuleType("mlx")
            mlx_core = types.ModuleType("mlx.core")
            mlx_core.__version__ = "test-mlx"
            mlx_module.core = mlx_core
            with (
                patch("curve.mlx_classifier.is_mlx_available", return_value=True),
                patch.dict(sys.modules, {"mlx": mlx_module, "mlx.core": mlx_core}),
            ):
                train_mlx_transformer_classifier(
                    dataset,
                    output=model_path,
                    config=MlxClassifierTrainingConfig(epochs=1, crop_size=6),
                )

            report = evaluate_classifier_model(
                model_path,
                dataset,
                output=report_path,
                splits=("val",),
            )

            self.assertTrue(report["uses_raster_tokens"])
            self.assertEqual(report["classifier_backend"], "mlx_feature_head")
            self.assertIn("val", report["evaluation"])
            self.assertTrue(report_path.exists())

    def test_eval_classifier_cli_accepts_config_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            generate_synthetic_dataset(
                output_dir=temp_dir,
                count=4,
                seed=43,
                width=64,
                height=64,
                val_count=1,
                test_count=1,
            )
            root = Path(temp_dir)
            dataset = root / "dataset.json"
            model_path = root / "model.json"
            report_path = root / "classifier-eval.json"
            markdown_path = root / "classifier-eval.md"
            config = root / "eval-classifier.json"
            train_centroid_classifier(dataset, output=model_path)
            config.write_text(
                json.dumps(
                    {
                        "model": str(model_path),
                        "dataset": str(dataset),
                        "output": str(report_path),
                        "markdown": str(markdown_path),
                        "splits": ["val"],
                    }
                ),
                encoding="utf-8",
            )

            with redirect_stdout(StringIO()):
                main(["eval-classifier", "--config", str(config)])

            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["splits"], ["val"])
            self.assertIn("val", report["evaluation"])
            self.assertTrue(markdown_path.exists())

    def test_load_model_and_score_matching_candidate(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            generate_synthetic_dataset(
                output_dir=temp_dir,
                count=4,
                seed=30,
                width=64,
                height=64,
                val_count=1,
                test_count=1,
            )
            model_path = Path(temp_dir) / "model.json"
            train_centroid_classifier(Path(temp_dir) / "dataset.json", output=model_path)
            centroids = load_centroid_model(model_path)
            candidate = AnchorCandidate(
                kind=AnchorKind.CIRCLE,
                raster_error=0.0,
                node_count=1,
                parameter_count=3,
                circle=CircleAnchor(center=Point(10, 10), radius=6),
            )

            self.assertEqual(classifier_prior_error(centroids, candidate), 0.0)


if __name__ == "__main__":
    unittest.main()
