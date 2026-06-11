import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from PIL import Image, ImageDraw

from curve.cli import main
from curve.sweeps import load_sweep_config, run_sweep


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
            self.assertTrue((output_dir / "baseline" / "manifest.json").exists())
            self.assertTrue((output_dir / "tolerant" / "report.md").exists())
            self.assertTrue((output_dir / "sweep-summary.json").exists())

    def test_sweep_cli_runs_config(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image_path = _write_input_image(root)
            config = _write_sweep_config(root, image_path)
            output_dir = root / "runs"

            with redirect_stdout(StringIO()):
                main(["sweep", str(config), "-o", str(output_dir)])

            summary = json.loads(
                (output_dir / "sweep-summary.json").read_text(encoding="utf-8")
            )
            self.assertEqual(summary["run_count"], 2)


def _write_input_image(root: Path) -> Path:
    image_path = root / "input.png"
    image = Image.new("RGB", (24, 24), "white")
    draw = ImageDraw.Draw(image)
    draw.ellipse((4, 4, 14, 14), fill="#dd2222")
    draw.rectangle((16, 10, 22, 11), fill="#003366")
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
