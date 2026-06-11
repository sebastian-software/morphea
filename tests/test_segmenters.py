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
)


class SegmenterTests(unittest.TestCase):
    def test_flat_color_segmenter_returns_proposals_with_metadata(self):
        image_path = _write_two_color_image()

        proposals = FlatColorSegmenter().propose(image_path)

        self.assertEqual(len(proposals), 2)
        self.assertEqual(proposals[0].source, "flat_color")
        self.assertEqual(proposals[0].confidence, 1.0)
        self.assertEqual(proposals[0].status, "proposed")
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

    def test_proposals_to_manifest_is_json_ready(self):
        image_path = _write_two_color_image()
        proposals = FlatColorSegmenter().propose(image_path)

        manifest = proposals_to_manifest(proposals)

        self.assertEqual(manifest[0]["source"], "flat_color")
        self.assertIsInstance(manifest[0]["bounds"], list)

    def test_mlx_sam_segmenter_reports_not_configured(self):
        with self.assertRaisesRegex(RuntimeError, "not installed/configured"):
            MlxSamSegmenter().propose("missing.png")

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
            self.assertEqual(manifest["config"]["max_component_area"], 10)
            self.assertTrue(manifest["config"]["split_components"])
            self.assertEqual(manifest["proposal_count"], 2)
            self.assertEqual(manifest["proposals"][0]["status"], "deferred")

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
