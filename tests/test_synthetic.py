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
        self.assertIn(AnchorKind.QUAD, kinds)

    def test_synthetic_sample_write_outputs_png_and_manifest(self):
        sample = generate_synthetic_sample(seed=11, width=64, height=64)
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path, manifest_path = sample.write(temp_dir, "sample")

            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

            self.assertTrue(image_path.exists())
            self.assertEqual(manifest["seed"], 11)
            self.assertEqual(manifest["anchor_count"], 4)

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
                    ]
                )

            output = Path(temp_dir)
            self.assertTrue((output / "sample-0000.png").exists())
            self.assertTrue((output / "sample-0000.json").exists())
            self.assertTrue((output / "sample-0001.png").exists())
            self.assertTrue((output / "sample-0001.json").exists())


if __name__ == "__main__":
    unittest.main()

