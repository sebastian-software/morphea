import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from curve.classifier import (
    classifier_prior_error,
    examples_from_dataset,
    features_from_anchor,
    load_centroid_model,
    train_centroid_classifier,
)
from curve.cli import main
from curve.dataset import generate_synthetic_dataset
from curve.anchors import AnchorCandidate, AnchorKind, CircleAnchor, Point


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

            self.assertEqual(len(examples), 4)
            self.assertEqual({example.label for example in examples}, {
                "circle",
                "quad",
                "stroke_circle",
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
            self.assertEqual(model["train_examples"], 8)

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
