import json
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from morphea.classifier import (
    FEATURE_NAMES,
    RasterRankingExample,
    anchors_from_dataset,
    classifier_prior_error,
    component_raster_tokens,
    evaluate_classifier_model,
    evaluate_classifier_ranking,
    evaluate_raster_classifier,
    evaluate_raster_classifier_ranking,
    examples_from_dataset,
    feature_importance_from_centroids,
    features_from_anchor,
    features_from_candidate,
    load_classifier_model,
    load_centroid_model,
    predict_classifier_label,
    predict_label,
    raster_examples_from_dataset,
    raster_ranking_examples_from_dataset,
    train_centroid_classifier,
)
from morphea.cli import main
from morphea.dataset import generate_synthetic_dataset
from morphea.anchors import AnchorCandidate, AnchorKind, CircleAnchor, Point
from morphea.masks import BinaryMask, connected_components
from morphea.mlx_classifier import (
    MLX_AUTOGRAD_SYMBOLS,
    MLX_CLASSIFIER_INSTALL_ACTION,
    MLX_CLASSIFIER_UPGRADE_ACTION,
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
        subtype_index = FEATURE_NAMES.index("quad_subtype_code")
        self.assertEqual(features[subtype_index], 2.0)

    def test_features_from_anchor_include_group_context_features(self):
        features = features_from_anchor(
            {
                "kind": "quad",
                "node_count": 4,
                "parameter_count": 8,
                "group_context": [
                    {"kind": "perspective_grid"},
                    {"kind": "text_like_fragment_group"},
                    {"kind": "primitive_anchor_reservation"},
                ],
            }
        )

        self.assertEqual(features[FEATURE_NAMES.index("group_count")], 3.0)
        self.assertEqual(features[FEATURE_NAMES.index("in_perspective_grid")], 1.0)
        self.assertEqual(
            features[FEATURE_NAMES.index("in_text_like_fragment_group")],
            1.0,
        )
        self.assertEqual(
            features[FEATURE_NAMES.index("in_primitive_anchor_reservation")],
            1.0,
        )
        self.assertEqual(
            features[FEATURE_NAMES.index("in_parallel_stroke_group")],
            0.0,
        )

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

    def test_examples_from_dataset_adds_manifest_group_context_features(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest_path = root / "sample.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "anchors": [
                            {
                                "kind": "quad",
                                "node_count": 4,
                                "parameter_count": 8,
                            },
                            {
                                "kind": "quad",
                                "node_count": 4,
                                "parameter_count": 8,
                            },
                        ],
                        "groups": [
                            {
                                "id": "grid-1",
                                "kind": "perspective_grid",
                                "anchor_indexes": [0, 1],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            dataset_path = root / "dataset.json"
            dataset_path.write_text(
                json.dumps(
                    {
                        "samples": [
                            {
                                "id": "sample-0000",
                                "split": "train",
                                "manifest": "sample.json",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            examples = examples_from_dataset(dataset_path)

            self.assertEqual(len(examples), 2)
            for example in examples:
                self.assertEqual(
                    example.features[FEATURE_NAMES.index("group_count")],
                    1.0,
                )
                self.assertEqual(
                    example.features[FEATURE_NAMES.index("in_perspective_grid")],
                    1.0,
                )

    def test_predict_label_aligns_new_features_to_legacy_centroids(self):
        centroids = {
            "circle": (1.0, 0.0),
            "quad": (9.0, 9.0),
        }

        predicted = predict_label(centroids, (1.0, 0.0, 1.0))

        self.assertEqual(predicted, "circle")

    def test_feature_importance_from_centroids_sorts_by_feature_spread(self):
        importance = feature_importance_from_centroids(
            {
                "circle": (1.0, 0.0, 1.0),
                "quad": (5.0, 0.0, 0.0),
            }
        )

        self.assertEqual(importance[0]["feature"], "node_count")
        self.assertEqual(importance[0]["spread"], 4.0)
        self.assertEqual(importance[0]["min"], 1.0)
        self.assertEqual(importance[0]["max"], 5.0)

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
            self.assertIn("feature_importance", model)
            self.assertTrue(
                any(
                    item["feature"] == "node_count"
                    for item in model["feature_importance"]
                )
            )
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

            with patch("morphea.mlx_classifier.is_mlx_available", return_value=False):
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

    def test_train_mlx_rejects_invalid_transformer_shape(self):
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

            with self.assertRaisesRegex(ValueError, "hidden_dim must be positive"):
                train_mlx_transformer_classifier(
                    Path(temp_dir) / "dataset.json",
                    output=Path(temp_dir) / "mlx-model.json",
                    config=MlxClassifierTrainingConfig(
                        hidden_dim=0,
                        allow_unavailable=True,
                    ),
                )
            with self.assertRaisesRegex(ValueError, "num_layers must be positive"):
                train_mlx_transformer_classifier(
                    Path(temp_dir) / "dataset.json",
                    output=Path(temp_dir) / "mlx-model.json",
                    config=MlxClassifierTrainingConfig(
                        num_layers=0,
                        allow_unavailable=True,
                    ),
                )

    def test_mlx_classifier_runtime_status_reports_package_state(self):
        with patch("morphea.mlx_classifier.is_mlx_available", return_value=False):
            unavailable = mlx_classifier_runtime_status()
        mlx_module = types.ModuleType("mlx")
        mlx_core = types.ModuleType("mlx.core")
        mlx_core.__version__ = "test-mlx"
        for symbol in MLX_AUTOGRAD_SYMBOLS:
            setattr(mlx_core, symbol, object())
        mlx_module.core = mlx_core
        with (
            patch("morphea.mlx_classifier.is_mlx_available", return_value=True),
            patch.dict(sys.modules, {"mlx": mlx_module, "mlx.core": mlx_core}),
        ):
            available = mlx_classifier_runtime_status()
        missing_autograd_core = types.ModuleType("mlx.core")
        missing_autograd_core.__version__ = "test-mlx"
        missing_autograd_module = types.ModuleType("mlx")
        missing_autograd_module.core = missing_autograd_core
        with (
            patch("morphea.mlx_classifier.is_mlx_available", return_value=True),
            patch.dict(
                sys.modules,
                {"mlx": missing_autograd_module, "mlx.core": missing_autograd_core},
            ),
        ):
            partial = mlx_classifier_runtime_status()

        self.assertEqual(unavailable["status"], "not_installed")
        self.assertFalse(unavailable["backend_available"])
        self.assertEqual(unavailable["training_implementation"], "centroid_fallback")
        self.assertEqual(unavailable["next_action"], MLX_CLASSIFIER_INSTALL_ACTION)
        self.assertEqual(
            unavailable["capabilities"]["feature_head_training"]["next_action"],
            MLX_CLASSIFIER_INSTALL_ACTION,
        )
        self.assertEqual(available["status"], "available")
        self.assertTrue(available["backend_available"])
        self.assertEqual(available["training_implementation"], "mlx_feature_head")
        self.assertIsNone(available["next_action"])
        self.assertTrue(
            available["capabilities"]["feature_head_training"]["available"]
        )
        self.assertIsNone(
            available["capabilities"]["feature_head_training"]["next_action"]
        )
        self.assertTrue(
            available["capabilities"][
                "end_to_end_token_projection_training"
            ]["available"]
        )
        self.assertEqual(
            available["capabilities"]["end_to_end_attention_training"]["status"],
            "available",
        )
        self.assertTrue(
            available["capabilities"]["end_to_end_attention_training"]["available"]
        )
        self.assertTrue(available["autograd_available"])
        self.assertEqual(available["missing_autograd_symbols"], [])
        self.assertEqual(partial["status"], "available")
        self.assertTrue(partial["backend_available"])
        self.assertFalse(partial["autograd_available"])
        self.assertIn("value_and_grad", partial["missing_autograd_symbols"])
        self.assertEqual(
            partial["capabilities"]["end_to_end_attention_training"]["status"],
            "autograd_unavailable",
        )
        self.assertFalse(
            partial["capabilities"]["end_to_end_attention_training"]["available"]
        )
        self.assertEqual(
            partial["capabilities"]["end_to_end_attention_training"]["next_action"],
            MLX_CLASSIFIER_UPGRADE_ACTION,
        )

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

            with patch("morphea.mlx_classifier.is_mlx_available", return_value=False):
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
            self.assertIn("feature_importance", model)
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

            with patch("morphea.mlx_classifier.is_mlx_available", return_value=False):
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
                patch("morphea.mlx_classifier.is_mlx_available", return_value=True),
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
                "token_transformer_encoder_serialized",
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
            fusion = model["mlx_training"]["feature_raster_fusion"]
            self.assertEqual(
                fusion["weight_format"],
                "mlx_feature_raster_fusion_v1",
            )
            self.assertEqual(fusion["fusion"]["heads"], 4)
            self.assertEqual(len(fusion["raster_embedding_names"]), 28)
            self.assertEqual(len(fusion["loss_history"]), 1)
            self.assertGreater(fusion["parameter_count"], 0)
            transformer = model["mlx_training"]["token_transformer"]
            self.assertEqual(transformer["weight_format"], "mlx_token_transformer_v1")
            self.assertEqual(transformer["encoder"]["hidden_dim"], 32)
            self.assertEqual(transformer["encoder"]["num_heads"], 4)
            self.assertEqual(transformer["encoder"]["num_layers"], 1)
            self.assertEqual(transformer["tokenization"]["raster_token_count"], 16)
            self.assertEqual(
                transformer["projection_calibration"]["strategy"],
                "between_class_encoder_output_calibration",
            )
            self.assertEqual(
                len(transformer["projection_calibration"]["scale"]),
                32,
            )
            self.assertEqual(
                len(transformer["projection_calibration"]["bias"]),
                32,
            )
            self.assertEqual(len(transformer["loss_history"]), 1)
            self.assertGreater(transformer["parameter_count"], 0)
            summary = model["mlx_training"]["component_summary"]
            self.assertEqual(summary["component_count"], 4)
            self.assertEqual(summary["trainable_component_count"], 4)
            self.assertEqual(summary["mlx_autograd_component_count"], 0)
            self.assertEqual(
                summary["inference_order_with_crop_tokens"][0],
                "token_transformer",
            )
            components = {
                component["name"]: component
                for component in summary["components"]
            }
            self.assertEqual(
                components["feature_head"]["parameter_count"],
                model["mlx_training"]["feature_head_parameter_count"],
            )
            self.assertEqual(
                components["feature_head"]["training_example_count"],
                model["train_examples"],
            )
            self.assertEqual(
                components["token_transformer"]["training_runtime"],
                "python_serialized",
            )
            self.assertEqual(
                components["token_transformer"]["training_example_count"],
                model["train_examples"],
            )
            self.assertTrue(components["feature_raster_fusion"]["uses_raster_tokens"])

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
                patch("morphea.mlx_classifier.is_mlx_available", return_value=True),
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
            self.assertIsInstance(classifier["feature_raster_fusion"], dict)
            self.assertIsInstance(classifier["token_transformer"], dict)
            self.assertEqual(
                classifier["token_transformer"]["projection_calibration"]["strategy"],
                "between_class_encoder_output_calibration",
            )
            self.assertIn(predicted, classifier["labels"])

    def test_load_classifier_model_preserves_token_projection(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            model_path = Path(temp_dir) / "mlx-model.json"
            model_path.write_text(
                json.dumps(
                    {
                        "model_type": MLX_MODEL_TYPE,
                        "fallback_centroids": {},
                        "mlx_training": {
                            "weight_format": "mlx_feature_head_v1",
                            "labels": ["circle", "cubic_path"],
                            "weights": [
                                [0.0 for _ in FEATURE_NAMES],
                                [0.0 for _ in FEATURE_NAMES],
                            ],
                            "bias": [0.0, 0.0],
                            "normalization": {
                                "mean": [0.0 for _ in FEATURE_NAMES],
                                "scale": [1.0 for _ in FEATURE_NAMES],
                            },
                            "token_transformer": {
                                "weight_format": "mlx_token_transformer_v1",
                                "labels": ["circle", "cubic_path"],
                                "weights": [[1.0], [-1.0]],
                                "bias": [0.0, 0.0],
                                "normalization": {
                                    "mean": [0.0],
                                    "scale": [1.0],
                                },
                                "tokenization": {
                                    "crop_size": 2,
                                    "raster_grid_size": 2,
                                },
                                "encoder": {
                                    "hidden_dim": 1,
                                    "num_heads": 1,
                                    "num_layers": 1,
                                },
                                "projection_calibration": {
                                    "scale": [1.0],
                                    "bias": [0.0],
                                    "strategy": "identity_after_learned_token_projection",
                                },
                                "token_projection": {
                                    "weight_format": "mlx_token_projection_v1",
                                    "input_names": ["red_or_feature"],
                                    "weights": [[0.0] * 8],
                                    "bias": [1.0],
                                    "trained_examples": 2,
                                },
                                "attention_parameters": {
                                    "weight_format": "mlx_attention_diagonal_v1",
                                    "trained_examples": 2,
                                    "layers": [
                                        {
                                            "query_scale": [1.0],
                                            "key_scale": [1.0],
                                            "value_scale": [1.0],
                                            "output_scale": [1.0],
                                            "output_bias": [0.25],
                                        }
                                    ],
                                },
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )

            classifier = load_classifier_model(model_path)

            projection = classifier["token_transformer"]["token_projection"]
            self.assertEqual(projection["weights"], ((0.0,) * 8,))
            self.assertEqual(projection["bias"], (1.0,))
            self.assertEqual(projection["trained_examples"], 2)
            attention = classifier["token_transformer"]["attention_parameters"]
            self.assertEqual(attention["weight_format"], "mlx_attention_diagonal_v1")
            self.assertEqual(attention["layers"][0]["output_bias"], (0.25,))

    def test_mlx_token_transformer_uses_learned_attention_parameters(self):
        classifier = {
            "classifier_backend": "mlx_feature_head",
            "labels": ("circle", "cubic_path"),
            "weights": (
                (0.0,) * len(FEATURE_NAMES),
                (0.0,) * len(FEATURE_NAMES),
            ),
            "bias": (0.0, 0.0),
            "normalization": {
                "mean": (0.0,) * len(FEATURE_NAMES),
                "scale": (1.0,) * len(FEATURE_NAMES),
            },
            "crop_token_spec": {"crop_size": 2},
            "token_transformer": {
                "labels": ("circle", "cubic_path"),
                "weights": ((10.0,), (-10.0,)),
                "bias": (0.0, 0.0),
                "normalization": {
                    "mean": (0.0,),
                    "scale": (1.0,),
                },
                "tokenization": {
                    "crop_size": 2,
                    "raster_grid_size": 2,
                },
                "encoder": {
                    "hidden_dim": 1,
                    "num_heads": 1,
                    "num_layers": 1,
                },
                "projection_calibration": {
                    "scale": (1.0,),
                    "bias": (0.0,),
                    "strategy": "identity_after_learned_token_projection",
                },
                "token_projection": {
                    "weights": ((0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),),
                    "bias": (0.0,),
                },
                "attention_parameters": {
                    "layers": (
                        {
                            "query_scale": (1.0,),
                            "key_scale": (1.0,),
                            "value_scale": (1.0,),
                            "output_scale": (1.0,),
                            "output_bias": (1.0,),
                        },
                    ),
                },
            },
        }

        predicted = predict_classifier_label(
            classifier,
            (0.0,) * len(FEATURE_NAMES),
            crop_tokens=(
                (1.0, 1.0, 1.0, 1.0),
                (1.0, 1.0, 1.0, 1.0),
                (1.0, 1.0, 1.0, 1.0),
                (1.0, 1.0, 1.0, 1.0),
            ),
        )

        self.assertEqual(predicted, "circle")

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

    def test_mlx_token_transformer_wins_when_crop_tokens_are_available(self):
        classifier = {
            "classifier_backend": "mlx_feature_head",
            "labels": ("circle", "cubic_path"),
            "weights": (
                (0.0, 0.0, -8.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
                (0.0, 0.0, 8.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
            ),
            "bias": (0.0, 0.0),
            "normalization": {
                "mean": (0.0,) * 11,
                "scale": (1.0,) * 11,
            },
            "crop_token_spec": {"crop_size": 2},
            "feature_raster_fusion": {
                "labels": ("circle", "cubic_path"),
                "weights": (
                    (*((0.0,) * 17), -20.0),
                    (*((0.0,) * 17), 20.0),
                ),
                "bias": (0.0, 0.0),
                "normalization": {
                    "mean": (0.0,) * 18,
                    "scale": (1.0,) * 18,
                },
                "raster_embedding_names": (
                    "head_0_red",
                    "head_0_green",
                    "head_0_blue",
                    "head_0_alpha",
                    "head_0_x",
                    "head_0_y",
                    "head_0_foreground",
                ),
                "fusion": {
                    "heads": 1,
                    "strategy": "concat_feature_and_raster_attention",
                },
            },
            "token_transformer": {
                "labels": ("circle", "cubic_path"),
                "weights": (
                    (0.0, 0.0, 0.0),
                    (0.0, 0.0, 0.0),
                ),
                "bias": (10.0, -10.0),
                "normalization": {
                    "mean": (0.0, 0.0, 0.0),
                    "scale": (1.0, 1.0, 1.0),
                },
                "tokenization": {
                    "crop_size": 2,
                    "raster_grid_size": 2,
                },
                "encoder": {
                    "hidden_dim": 3,
                    "num_heads": 1,
                    "num_layers": 1,
                },
                "projection_calibration": {
                    "scale": (1.0, 1.0, 1.0),
                    "bias": (0.0, 0.0, 0.0),
                    "strategy": "test_projection",
                },
            },
        }

        predicted = predict_classifier_label(
            classifier,
            (0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
            crop_tokens=(
                (0.0, 0.0, 0.0, 1.0),
                (1.0, 1.0, 1.0, 1.0),
                (1.0, 1.0, 1.0, 1.0),
                (1.0, 1.0, 1.0, 1.0),
            ),
        )

        self.assertEqual(predicted, "circle")

    def test_mlx_token_transformer_uses_learned_token_projection(self):
        classifier = {
            "classifier_backend": "mlx_feature_head",
            "labels": ("circle", "cubic_path"),
            "weights": (
                (0.0,) * len(FEATURE_NAMES),
                (0.0,) * len(FEATURE_NAMES),
            ),
            "bias": (0.0, 0.0),
            "normalization": {
                "mean": (0.0,) * len(FEATURE_NAMES),
                "scale": (1.0,) * len(FEATURE_NAMES),
            },
            "crop_token_spec": {"crop_size": 2},
            "token_transformer": {
                "labels": ("circle", "cubic_path"),
                "weights": ((10.0,), (-10.0,)),
                "bias": (0.0, 0.0),
                "normalization": {
                    "mean": (0.0,),
                    "scale": (1.0,),
                },
                "tokenization": {
                    "crop_size": 2,
                    "raster_grid_size": 2,
                },
                "encoder": {
                    "hidden_dim": 1,
                    "num_heads": 1,
                    "num_layers": 1,
                },
                "projection_calibration": {
                    "scale": (1.0,),
                    "bias": (0.0,),
                    "strategy": "identity_after_learned_token_projection",
                },
                "token_projection": {
                    "weights": ((0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),),
                    "bias": (1.0,),
                },
            },
        }

        predicted = predict_classifier_label(
            classifier,
            (0.0,) * len(FEATURE_NAMES),
            crop_tokens=(
                (1.0, 1.0, 1.0, 1.0),
                (1.0, 1.0, 1.0, 1.0),
                (1.0, 1.0, 1.0, 1.0),
                (1.0, 1.0, 1.0, 1.0),
            ),
        )

        self.assertEqual(predicted, "circle")

    def test_raster_classifier_ranking_uses_crop_tokens(self):
        classifier = {
            "classifier_backend": "mlx_feature_head",
            "labels": ("circle", "stroke_circle"),
            "weights": (
                (0.0,) * len(FEATURE_NAMES),
                (0.0,) * len(FEATURE_NAMES),
            ),
            "bias": (0.0, 0.0),
            "normalization": {
                "mean": (0.0,) * len(FEATURE_NAMES),
                "scale": (1.0,) * len(FEATURE_NAMES),
            },
            "crop_token_spec": {"crop_size": 2},
            "token_transformer": {
                "labels": ("circle", "stroke_circle"),
                "weights": (
                    (0.0, 0.0, 0.0),
                    (0.0, 0.0, 0.0),
                ),
                "bias": (10.0, -10.0),
                "normalization": {
                    "mean": (0.0, 0.0, 0.0),
                    "scale": (1.0, 1.0, 1.0),
                },
                "tokenization": {
                    "crop_size": 2,
                    "raster_grid_size": 2,
                },
                "encoder": {
                    "hidden_dim": 3,
                    "num_heads": 1,
                    "num_layers": 1,
                },
                "projection_calibration": {
                    "scale": (1.0, 1.0, 1.0),
                    "bias": (0.0, 0.0, 0.0),
                },
            },
        }
        anchor = {
            "kind": "circle",
            "node_count": 1,
            "parameter_count": 3,
            "circle": {"cx": 5.0, "cy": 5.0, "r": 3.0},
            "color": "#dd2222",
            "metrics": {},
        }
        examples = (
            RasterRankingExample(
                label="circle",
                anchor=anchor,
                crop_tokens=(
                    (0.0, 0.0, 0.0, 1.0),
                    (1.0, 1.0, 1.0, 1.0),
                    (1.0, 1.0, 1.0, 1.0),
                    (1.0, 1.0, 1.0, 1.0),
                ),
                sample_id="sample-0000",
                anchor_index=0,
            ),
        )

        ranking = evaluate_raster_classifier_ranking(classifier, examples)

        self.assertTrue(ranking["uses_raster_tokens"])
        self.assertEqual(ranking["examples"], 1)
        self.assertEqual(ranking["decisions"][0]["classifier"], "circle")
        self.assertTrue(ranking["decisions"][0]["uses_raster_tokens"])

    def test_mlx_feature_raster_fusion_wins_when_crop_tokens_are_available(self):
        classifier = {
            "classifier_backend": "mlx_feature_head",
            "labels": ("circle", "cubic_path"),
            "weights": (
                (0.0, 0.0, -8.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
                (0.0, 0.0, 8.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
            ),
            "bias": (0.0, 0.0),
            "normalization": {
                "mean": (0.0,) * 11,
                "scale": (1.0,) * 11,
            },
            "crop_token_spec": {"crop_size": 2},
            "raster_token_mixer": {
                "labels": ("circle", "cubic_path"),
                "weights": (
                    (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, -8.0),
                    (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 8.0),
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
            "feature_raster_fusion": {
                "labels": ("circle", "cubic_path"),
                "weights": (
                    (*((0.0,) * 17), 20.0),
                    (*((0.0,) * 17), -20.0),
                ),
                "bias": (0.0, 0.0),
                "normalization": {
                    "mean": (0.0,) * 18,
                    "scale": (1.0,) * 18,
                },
                "raster_embedding_names": (
                    "head_0_red",
                    "head_0_green",
                    "head_0_blue",
                    "head_0_alpha",
                    "head_0_x",
                    "head_0_y",
                    "head_0_foreground",
                ),
                "fusion": {
                    "heads": 1,
                    "strategy": "concat_feature_and_raster_attention",
                },
            },
        }

        predicted = predict_classifier_label(
            classifier,
            (0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
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
            self.assertIn("feature_importance", report)
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
            markdown = markdown_path.read_text(encoding="utf-8")
            self.assertIn("# Morphēa Classifier Evaluation", markdown)
            self.assertIn("- Direct raster tokens: `False`", markdown)
            self.assertIn("- Ranking raster tokens: `False`", markdown)
            self.assertIn("## Feature Importance", markdown)

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
            markdown_path = Path(temp_dir) / "classifier-eval.md"
            mlx_module = types.ModuleType("mlx")
            mlx_core = types.ModuleType("mlx.core")
            mlx_core.__version__ = "test-mlx"
            mlx_module.core = mlx_core
            with (
                patch("morphea.mlx_classifier.is_mlx_available", return_value=True),
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
                markdown=markdown_path,
                splits=("val",),
            )

            self.assertTrue(report["uses_raster_tokens"])
            self.assertTrue(report["ranking_uses_raster_tokens"])
            self.assertEqual(report["classifier_backend"], "mlx_feature_head")
            self.assertEqual(
                report["training_component_summary"]["component_count"],
                4,
            )
            self.assertEqual(
                report["training_component_summary"][
                    "inference_order_with_crop_tokens"
                ][0],
                "token_transformer",
            )
            self.assertIn("val", report["evaluation"])
            self.assertTrue(report["ranking_evaluation"]["val"]["uses_raster_tokens"])
            self.assertTrue(
                report["ranking_evaluation"]["val"]["decisions"][0][
                    "uses_raster_tokens"
                ]
            )
            self.assertTrue(report_path.exists())
            markdown = markdown_path.read_text(encoding="utf-8")
            self.assertIn("- Direct raster tokens: `True`", markdown)
            self.assertIn("- Ranking raster tokens: `True`", markdown)
            self.assertIn("## MLX Training Components", markdown)
            self.assertIn("Training examples", markdown)
            self.assertIn("`token_transformer`", markdown)

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
