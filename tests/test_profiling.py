import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from PIL import Image, ImageDraw

from curve.cli import main
from curve.profiling import profile_vectorize


class ProfilingTests(unittest.TestCase):
    def test_profile_vectorize_writes_timing_report(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image_path = _write_profile_image(root)
            output = root / "profile.json"

            report = profile_vectorize(
                image_path,
                output=output,
                repeats=2,
                config={"min_area": 4},
            )

            self.assertTrue(output.exists())
            self.assertEqual(report["repeat_count"], 2)
            self.assertEqual(len(report["runs"]), 2)
            self.assertIn("mean_elapsed_seconds", report["summary"])
            self.assertGreaterEqual(report["runs"][0]["anchor_count"], 1)

    def test_profile_vectorize_records_diagnostic_stage_counts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image_path = _write_profile_image(root)
            output = root / "profile.json"

            report = profile_vectorize(
                image_path,
                output=output,
                repeats=1,
                config={"min_area": 4, "max_component_area": 8},
            )

            self.assertEqual(
                report["runs"][0]["diagnostic_stage_counts"]["segmentation"],
                2,
            )

    def test_profile_cli_writes_report_with_vectorize_config(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image_path = _write_profile_image(root)
            output = root / "profile.json"
            config = root / "vectorize-config.json"
            config.write_text(
                json.dumps({"min_area": 4, "timeout_seconds": 5}),
                encoding="utf-8",
            )

            with redirect_stdout(StringIO()):
                main(
                    [
                        "profile",
                        str(image_path),
                        "-o",
                        str(output),
                        "--repeats",
                        "1",
                        "--config",
                        str(config),
                    ]
                )

            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(report["repeat_count"], 1)
            self.assertEqual(report["config"]["timeout_seconds"], 5)

    def test_profile_rejects_zero_repeats(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)

            with self.assertRaisesRegex(ValueError, "at least 1"):
                profile_vectorize(
                    _write_profile_image(root),
                    output=root / "profile.json",
                    repeats=0,
                )


def _write_profile_image(root: Path) -> Path:
    path = root / "profile.png"
    image = Image.new("RGB", (20, 16), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((4, 4, 14, 10), fill="#003366")
    image.save(path)
    return path


if __name__ == "__main__":
    unittest.main()
