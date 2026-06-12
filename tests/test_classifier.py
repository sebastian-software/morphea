import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from curve.classifier import (
    FEATURE_NAMES,
    anchors_from_dataset,
    classifier_prior_error,
    evaluate_classifier_ranking,
    examples_from_dataset,
    features_from_anchor,
    load_centroid_model,
    train_centroid_classifier,
)
from curve.cli import main
from curve.dataset import generate_synthetic_dataset
from curve.anchors import AnchorCandidate, AnchorKind, CircleAnchor, Point
from curve.mlx_classifier import (
    MLX_MODEL_TYPE,
    MlxClassifierTrainingConfig,
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
                with self.assertRaisesRegex(RuntimeError, "MLX primitive classifier"):
                    train_mlx_transformer_classifier(
                        Path(temp_dir) / "dataset.json",
                        output=Path(temp_dir) / "mlx-model.json",
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
