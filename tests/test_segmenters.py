import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

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

    def test_proposals_to_manifest_is_json_ready(self):
        image_path = _write_two_color_image()
        proposals = FlatColorSegmenter().propose(image_path)

        manifest = proposals_to_manifest(proposals)

        self.assertEqual(manifest[0]["source"], "flat_color")
        self.assertIsInstance(manifest[0]["bounds"], list)

    def test_mlx_sam_segmenter_reports_not_configured(self):
        with self.assertRaisesRegex(RuntimeError, "not installed/configured"):
            MlxSamSegmenter().propose("missing.png")


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


_TEMP_DIRS: list[tempfile.TemporaryDirectory] = []


if __name__ == "__main__":
    unittest.main()

