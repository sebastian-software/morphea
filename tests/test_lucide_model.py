import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageDraw

from morphea.cli import main
from morphea.lucide_model import (
    LucideTargetTrainingConfig,
    train_lucide_target_model,
)
from morphea.raster_target_model import (
    RASTER_TARGET_FALLBACK_TRAINING_IMPLEMENTATION,
    RASTER_TARGET_MLX_TRAINING_IMPLEMENTATION,
    RASTER_TARGET_MODEL_TYPE,
    raster_target_runtime_status,
)


MLX_TARGET_RUNTIME_AVAILABLE = bool(
    raster_target_runtime_status()["backend_available"]
)


class LucideModelTests(unittest.TestCase):
    @unittest.skipUnless(MLX_TARGET_RUNTIME_AVAILABLE, "requires MLX target runtime")
    def test_train_lucide_target_model_writes_mlx_artifact(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            corpus = _write_lucide_target_corpus(root)
            output = root / "model.json"
            markdown = root / "model.md"

            model = train_lucide_target_model(
                corpus,
                output=output,
                markdown=markdown,
            )

            self.assertEqual(model["model_type"], RASTER_TARGET_MODEL_TYPE)
            self.assertEqual(
                model["training_implementation"],
                RASTER_TARGET_MLX_TRAINING_IMPLEMENTATION,
            )
            self.assertEqual(model["target_label_key"], "anchor_kind_targets")
            self.assertEqual(model["train_examples"], 2)
            self.assertEqual(
                model["target_names"],
                ["stroke_circle", "stroke_polyline"],
            )
            self.assertEqual(
                model["target_summary"],
                {"stroke_circle": 1, "stroke_polyline": 1},
            )
            self.assertEqual(
                model["target_models"]["stroke_circle"]["positive_examples"],
                1,
            )
            self.assertEqual(
                model["target_models"]["stroke_circle"]["negative_examples"],
                1,
            )
            self.assertEqual(
                model["evaluation"]["train"]["exact_match_accuracy"],
                1.0,
            )
            self.assertEqual(
                model["mlx_training"]["training_runtime"],
                "mlx_autograd",
            )
            self.assertGreater(model["mlx_training"]["parameter_count"], 0)
            saved = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(saved["model_type"], RASTER_TARGET_MODEL_TYPE)
            self.assertIn("# Morphea Raster Target Model", markdown.read_text())

    @unittest.skipUnless(MLX_TARGET_RUNTIME_AVAILABLE, "requires MLX target runtime")
    def test_train_lucide_targets_cli_writes_model(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            corpus = _write_lucide_target_corpus(root)
            output = root / "model.json"

            with redirect_stdout(StringIO()):
                main(
                    [
                        "train-lucide-targets",
                        str(corpus),
                        "-o",
                        str(output),
                        "--epochs",
                        "20",
                        "--hidden-dim",
                        "12",
                    ]
                )

            model = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(model["model_type"], RASTER_TARGET_MODEL_TYPE)
            self.assertEqual(model["train_examples"], 2)
            self.assertEqual(model["training_config"]["epochs"], 20)
            self.assertEqual(model["training_config"]["hidden_dim"], 12)
            self.assertEqual(model["mlx_training"]["hidden_dim"], 12)
            self.assertEqual(
                model["training_implementation"],
                RASTER_TARGET_MLX_TRAINING_IMPLEMENTATION,
            )

    def test_train_lucide_target_model_can_write_explicit_fallback(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            corpus = _write_lucide_target_corpus(root)
            output = root / "model.json"

            with patch(
                "morphea.raster_target_model.raster_target_runtime_status",
                return_value={
                    "backend": "mlx",
                    "backend_available": False,
                    "status": "not_installed",
                    "reason": "test unavailable",
                    "next_action": "install",
                },
            ):
                model = train_lucide_target_model(
                    corpus,
                    output=output,
                    config=LucideTargetTrainingConfig(allow_unavailable=True),
                )

            self.assertEqual(model["model_type"], RASTER_TARGET_MODEL_TYPE)
            self.assertEqual(model["status"], "unavailable")
            self.assertEqual(
                model["training_implementation"],
                RASTER_TARGET_FALLBACK_TRAINING_IMPLEMENTATION,
            )
            self.assertNotIn("mlx_training", model)
            self.assertEqual(
                model["evaluation"]["train"]["exact_match_accuracy"],
                1.0,
            )


def _write_lucide_target_corpus(root: Path) -> Path:
    output_dir = root / "corpus"
    line_dir = output_dir / "minus"
    circle_dir = output_dir / "circle"
    line_dir.mkdir(parents=True)
    circle_dir.mkdir(parents=True)
    _write_line_png(line_dir / "input.png")
    _write_circle_png(circle_dir / "input.png")
    corpus = root / "corpus.json"
    corpus.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "source": "lucide_suite",
                "source_package": "lucide-static",
                "source_version": "test",
                "output_dir": str(output_dir),
                "examples": [
                    {
                        "id": "minus",
                        "split": "train",
                        "family": "simple_stroke_glyphs",
                        "status": "rendered",
                        "input_png": str(line_dir / "input.png"),
                        "labels": {
                            "anchor_kind_targets": {"stroke_polyline": 1},
                        },
                    },
                    {
                        "id": "circle",
                        "split": "train",
                        "family": "circle_compound_strokes",
                        "status": "rendered",
                        "input_png": str(circle_dir / "input.png"),
                        "labels": {
                            "anchor_kind_targets": {"stroke_circle": 1},
                        },
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    return corpus


def _write_line_png(path: Path) -> None:
    image = Image.new("RGBA", (64, 64), "white")
    draw = ImageDraw.Draw(image)
    draw.line((12, 32, 52, 32), fill="black", width=5)
    image.save(path)


def _write_circle_png(path: Path) -> None:
    image = Image.new("RGBA", (64, 64), "white")
    draw = ImageDraw.Draw(image)
    draw.ellipse((16, 16, 48, 48), outline="black", width=5)
    image.save(path)


if __name__ == "__main__":
    unittest.main()
