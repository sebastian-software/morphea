import importlib
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class CompatibilityTests(unittest.TestCase):
    def test_morphea_cli_import_is_primary(self):
        from morphea.cli import main

        self.assertTrue(callable(main))

    def test_curve_cli_import_remains_available(self):
        from curve.cli import main

        self.assertTrue(callable(main))

    def test_curve_submodule_alias_points_to_morphea_module(self):
        morphea_segmenters = importlib.import_module("morphea.segmenters")
        curve_segmenters = importlib.import_module("curve.segmenters")

        self.assertIs(curve_segmenters, morphea_segmenters)

    def test_legacy_curve_module_entrypoint_still_runs(self):
        root = Path(__file__).resolve().parents[1]
        env = os.environ.copy()
        env["PYTHONPATH"] = str(root / "src")
        with tempfile.TemporaryDirectory() as temp_dir:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "curve.cli",
                    "status",
                    "-o",
                    str(Path(temp_dir) / "status.json"),
                ],
                cwd=root,
                env=env,
                capture_output=True,
                text=True,
                timeout=10,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("capability blockers", result.stdout)


if __name__ == "__main__":
    unittest.main()
