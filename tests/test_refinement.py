import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from PIL import Image, ImageDraw

from curve.cli import main
from curve.refinement import RefinementConfig, refine_manifest


class RefinementTests(unittest.TestCase):
    def test_refine_manifest_preserves_anchor_kind_and_adds_metadata(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manifest = _write_manifest(Path(temp_dir))
            output = Path(temp_dir) / "refined.json"

            result = refine_manifest(
                manifest=manifest,
                output=output,
                config=RefinementConfig(max_iterations=3, timeout_seconds=1.0),
            )

            self.assertEqual(result["anchors"][0]["kind"], "circle")
            self.assertTrue(result["refinement"]["structure_preserving"])
            self.assertEqual(
                result["anchors"][0]["metrics"]["refinement_iterations"],
                3.0,
            )
            self.assertTrue(output.exists())

    def test_refine_cli_writes_output(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manifest = _write_manifest(Path(temp_dir))
            output = Path(temp_dir) / "refined.json"

            with redirect_stdout(StringIO()):
                main(["refine", str(manifest), "-o", str(output)])

            result = json.loads(output.read_text())
            self.assertEqual(result["refinement"]["backend"], "local_metric")

    def test_local_metric_refinement_adjusts_circle_radius_from_source(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest = _write_circle_manifest(root, radius=3)
            source = _write_circle_source(root, radius=4)
            output = root / "refined.json"

            result = refine_manifest(
                manifest=manifest,
                output=output,
                config=RefinementConfig(
                    max_iterations=3,
                    timeout_seconds=1.0,
                    source_image=source,
                ),
            )

            self.assertEqual(result["anchors"][0]["kind"], "circle")
            self.assertEqual(result["anchors"][0]["circle"]["r"], 4.0)
            self.assertLess(
                result["refinement"]["optimizer"]["final_raster_l1_error"],
                result["refinement"]["optimizer"]["initial_raster_l1_error"],
            )
            self.assertEqual(
                result["anchors"][0]["metrics"]["refinement_radius_delta"],
                1.0,
            )

    def test_refine_cli_accepts_source_image(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest = _write_circle_manifest(root, radius=3)
            source = _write_circle_source(root, radius=4)
            output = root / "refined.json"

            with redirect_stdout(StringIO()):
                main(
                    [
                        "refine",
                        str(manifest),
                        "-o",
                        str(output),
                        "--max-iterations",
                        "2",
                        "--source-image",
                        str(source),
                    ]
                )

            result = json.loads(output.read_text())
            self.assertTrue(result["refinement"]["optimizer"]["attempted"])

    def test_unknown_refinement_backend_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manifest = _write_manifest(Path(temp_dir))

            with self.assertRaisesRegex(ValueError, "unsupported refinement backend"):
                refine_manifest(
                    manifest=manifest,
                    output=Path(temp_dir) / "refined.json",
                    config=RefinementConfig(backend="diffvg"),
                )


def _write_manifest(root: Path) -> Path:
    manifest = root / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "anchors": [
                    {
                        "kind": "circle",
                        "metrics": {},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return manifest


def _write_circle_manifest(root: Path, *, radius: float) -> Path:
    manifest = root / "circle-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "width": 16,
                "height": 16,
                "anchor_count": 1,
                "anchors": [
                    {
                        "kind": "circle",
                        "circle": {"cx": 8, "cy": 8, "r": radius},
                        "color": "#dd2222",
                        "metrics": {},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return manifest


def _write_circle_source(root: Path, *, radius: int) -> Path:
    source = root / "source.png"
    image = Image.new("RGB", (16, 16), "white")
    draw = ImageDraw.Draw(image)
    draw.ellipse((8 - radius, 8 - radius, 8 + radius, 8 + radius), fill="#dd2222")
    image.save(source)
    return source


if __name__ == "__main__":
    unittest.main()
