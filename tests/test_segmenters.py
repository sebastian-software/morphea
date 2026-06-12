import tempfile
import unittest
import json
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from PIL import Image, ImageDraw

from curve.cli import main
from curve.segmenters import (
    FlatColorSegmenter,
    MlxSamSegmenter,
    proposals_to_manifest,
    segmenter_backend_status,
)


class SegmenterTests(unittest.TestCase):
    def test_flat_color_segmenter_returns_proposals_with_metadata(self):
        image_path = _write_two_color_image()

        proposals = FlatColorSegmenter().propose(image_path)

        self.assertEqual(len(proposals), 2)
        self.assertEqual(proposals[0].source, "flat_color")
        self.assertEqual(proposals[0].confidence, 1.0)
        self.assertEqual(proposals[0].status, "proposed")
        self.assertEqual(proposals[0].downstream_status, "pending")
        self.assertIsNone(proposals[0].rejection_reason)
        self.assertGreater(proposals[0].area, 0)

    def test_flat_color_segmenter_splits_same_color_components(self):
        image_path = _write_same_color_component_image()

        proposals = FlatColorSegmenter(min_area=4).propose(image_path)

        self.assertEqual(len(proposals), 2)
        self.assertEqual({proposal.color for proposal in proposals}, {"#dd2222"})
        self.assertTrue(all(proposal.status == "proposed" for proposal in proposals))

    def test_flat_color_segmenter_marks_oversized_components_deferred(self):
        image_path = _write_same_color_component_image()

        proposals = FlatColorSegmenter(
            min_area=4,
            max_component_area=12,
        ).propose(image_path)

        self.assertEqual(len(proposals), 2)
        self.assertIn("deferred", {proposal.status for proposal in proposals})
        self.assertIn("rejected", {proposal.downstream_status for proposal in proposals})
        self.assertIn(
            "max_component_area_exceeded",
            {proposal.rejection_reason for proposal in proposals},
        )

    def test_proposals_to_manifest_is_json_ready(self):
        image_path = _write_two_color_image()
        proposals = FlatColorSegmenter().propose(image_path)

        manifest = proposals_to_manifest(proposals)

        self.assertEqual(manifest[0]["source"], "flat_color")
        self.assertIsInstance(manifest[0]["bounds"], list)
        self.assertEqual(manifest[0]["downstream_status"], "pending")
        self.assertIsNone(manifest[0]["rejection_reason"])

    def test_mlx_sam_segmenter_reports_not_configured(self):
        with self.assertRaisesRegex(RuntimeError, "not installed/configured"):
            MlxSamSegmenter().propose("missing.png")

    def test_mlx_sam_segmenter_reports_runtime_config_in_error(self):
        with self.assertRaisesRegex(RuntimeError, "model_path=models/sam.mlx"):
            MlxSamSegmenter(
                model_path="models/sam.mlx",
                max_masks=12,
                timeout_seconds=3.5,
            ).propose("missing.png")

    def test_segmenter_backend_status_reports_availability(self):
        flat = segmenter_backend_status(FlatColorSegmenter())
        mlx = segmenter_backend_status(
            MlxSamSegmenter(model_path="models/sam.mlx", max_masks=12)
        )

        self.assertTrue(flat["backend_available"])
        self.assertEqual(flat["status"], "available")
        self.assertFalse(mlx["backend_available"])
        self.assertEqual(mlx["status"], "not_configured")
        self.assertEqual(mlx["model_path"], "models/sam.mlx")

    def test_segment_cli_writes_flat_color_manifest_from_config(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image_path = _write_two_color_image()
            output = root / "segments.json"
            config = root / "segment-config.json"
            config.write_text(
                json.dumps(
                    {
                        "segmenter": "flat_color",
                        "min_area": 4,
                        "color_tolerance": 0.0,
                        "max_component_area": 10,
                        "split_components": True,
                    }
                ),
                encoding="utf-8",
            )

            with redirect_stdout(StringIO()):
                main(
                    [
                        "segment",
                        str(image_path),
                        "-o",
                        str(output),
                        "--config",
                        str(config),
                    ]
                )

            manifest = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(manifest["schema_version"], 1)
            self.assertEqual(manifest["config"]["segmenter"], "flat_color")
            self.assertTrue(manifest["backend"]["backend_available"])
            self.assertEqual(manifest["backend"]["source"], "flat_color")
            self.assertEqual(manifest["config"]["max_component_area"], 10)
            self.assertTrue(manifest["config"]["split_components"])
            self.assertEqual(manifest["proposal_count"], 2)
            self.assertEqual(manifest["proposals"][0]["status"], "deferred")
            self.assertEqual(
                manifest["proposals"][0]["downstream_status"],
                "rejected",
            )

    def test_segment_cli_reports_mlx_sam_not_configured(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "segments.json"

            with self.assertRaisesRegex(RuntimeError, "not installed/configured"):
                main(
                    [
                        "segment",
                        str(_write_two_color_image()),
                        "-o",
                        str(output),
                        "--segmenter",
                        "mlx_sam",
                    ]
                )

    def test_segment_cli_accepts_mlx_runtime_config(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output = root / "segments.json"
            config = root / "segment-mlx.json"
            config.write_text(
                json.dumps(
                    {
                        "segmenter": "mlx_sam",
                        "mlx_model_path": "models/sam.mlx",
                        "mlx_score_threshold": 0.7,
                        "mlx_max_masks": 16,
                        "mlx_timeout_seconds": 2.5,
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(RuntimeError, "models/sam.mlx"):
                main(
                    [
                        "segment",
                        str(_write_two_color_image()),
                        "-o",
                        str(output),
                        "--config",
                        str(config),
                    ]
                )


def _write_two_color_image() -> Path:
    temp_dir = tempfile.TemporaryDirectory()
    path = Path(temp_dir.name) / "segments.png"
    image = Image.new("RGB", (20, 12), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((2, 2, 6, 6), fill="#dd2222")
    draw.rectangle((12, 2, 16, 6), fill="#003366")
    image.save(path)
    _TEMP_DIRS.append(temp_dir)
    return path


def _write_same_color_component_image() -> Path:
    temp_dir = tempfile.TemporaryDirectory()
    path = Path(temp_dir.name) / "same-color-components.png"
    image = Image.new("RGB", (24, 12), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((2, 2, 6, 6), fill="#dd2222")
    draw.rectangle((14, 2, 20, 8), fill="#dd2222")
    image.save(path)
    _TEMP_DIRS.append(temp_dir)
    return path


_TEMP_DIRS: list[tempfile.TemporaryDirectory] = []


if __name__ == "__main__":
    unittest.main()
