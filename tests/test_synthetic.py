import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from curve.anchors import AnchorKind
from curve.cli import main
from curve.synthetic import generate_synthetic_sample


class SyntheticGeneratorTests(unittest.TestCase):
    def test_generate_synthetic_sample_contains_core_ground_truth_shapes(self):
        sample = generate_synthetic_sample(seed=7, width=96, height=96)

        kinds = {anchor.kind for anchor in sample.scene.anchors}

        self.assertIn(AnchorKind.CIRCLE, kinds)
        self.assertIn(AnchorKind.STROKE_CIRCLE, kinds)
        self.assertIn(AnchorKind.STROKE_POLYLINE, kinds)
        self.assertIn(AnchorKind.STROKE_PATH, kinds)
        self.assertIn(AnchorKind.ARC, kinds)
        self.assertIn(AnchorKind.RECT, kinds)
        self.assertIn(AnchorKind.ROUNDED_RECT, kinds)
        self.assertIn(AnchorKind.QUAD, kinds)
        self.assertGreaterEqual(
            sum(1 for anchor in sample.scene.anchors if anchor.kind == AnchorKind.QUAD),
            5,
        )
        self.assertTrue(
            any(
                anchor.circle is not None and anchor.circle.radius <= 4
                for anchor in sample.scene.anchors
                if anchor.kind == AnchorKind.CIRCLE
            )
        )
        self.assertTrue(
            any(anchor.stroke is not None and anchor.stroke.is_cutout for anchor in sample.scene.anchors)
        )

    def test_synthetic_sample_write_outputs_png_and_manifest(self):
        sample = generate_synthetic_sample(seed=11, width=64, height=64)
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path, manifest_path = sample.write(temp_dir, "sample")

            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

            self.assertTrue(image_path.exists())
            self.assertEqual(manifest["seed"], 11)
            self.assertEqual(manifest["difficulty"], "basic")
            self.assertEqual(manifest["anchor_count"], 14)

    def test_dense_synthetic_sample_adds_parallel_stroke_group(self):
        sample = generate_synthetic_sample(
            seed=12,
            width=96,
            height=96,
            difficulty="dense",
        )

        parallel = [
            anchor
            for anchor in sample.scene.anchors
            if anchor.stroke is not None
            and anchor.stroke.parallel_group_id == "synthetic-parallel-0"
        ]

        self.assertEqual(len(parallel), 3)
        self.assertEqual(len(sample.scene.anchors), 17)

    def test_logo_synthetic_sample_adds_logo_like_composition(self):
        sample = generate_synthetic_sample(
            seed=13,
            width=96,
            height=96,
            difficulty="logo",
        )

        logo_elements = [
            anchor.metrics.get("logo_element")
            for anchor in sample.scene.anchors
            if "logo_element" in anchor.metrics
        ]
        kinds = {
            anchor.kind
            for anchor in sample.scene.anchors
            if "logo_element" in anchor.metrics
        }

        self.assertEqual(len(sample.scene.anchors), 18)
        self.assertEqual(
            set(logo_elements),
            {"accent_dot", "diagonal_stroke", "mark_ring", "wordmark_bar"},
        )
        self.assertIn(AnchorKind.STROKE_CIRCLE, kinds)
        self.assertIn(AnchorKind.ROUNDED_RECT, kinds)

    def test_unknown_synthetic_difficulty_fails(self):
        with self.assertRaisesRegex(ValueError, "unsupported synthetic difficulty"):
            generate_synthetic_sample(seed=1, difficulty="unknown")

    def test_generate_cli_writes_numbered_samples(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with redirect_stdout(StringIO()):
                main(
                    [
                        "generate",
                        "-o",
                        temp_dir,
                        "--count",
                        "2",
                        "--seed",
                        "20",
                        "--width",
                        "64",
                        "--height",
                        "64",
                        "--val-count",
                        "0",
                        "--test-count",
                        "1",
                    ]
                )

            output = Path(temp_dir)
            self.assertTrue((output / "train" / "sample-0000.png").exists())
            self.assertTrue((output / "train" / "sample-0000.json").exists())
            self.assertTrue((output / "test" / "sample-0001.png").exists())
            self.assertTrue((output / "test" / "sample-0001.json").exists())

    def test_generate_cli_accepts_logo_difficulty(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with redirect_stdout(StringIO()):
                main(
                    [
                        "generate",
                        "-o",
                        temp_dir,
                        "--count",
                        "1",
                        "--seed",
                        "30",
                        "--difficulty",
                        "logo",
                        "--val-count",
                        "0",
                        "--test-count",
                        "0",
                    ]
                )

            manifest = json.loads(
                (Path(temp_dir) / "train" / "sample-0000.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(manifest["difficulty"], "logo")
            self.assertTrue(
                any(
                    "logo_element" in anchor.get("metrics", {})
                    for anchor in manifest["anchors"]
                )
            )


if __name__ == "__main__":
    unittest.main()
