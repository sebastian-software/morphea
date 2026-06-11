import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()

