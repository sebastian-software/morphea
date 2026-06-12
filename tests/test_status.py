import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from curve.status import collect_runtime_status, render_runtime_status_markdown


class RuntimeStatusTests(unittest.TestCase):
    def test_collect_runtime_status_writes_json_with_blockers(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "status.json"

            with (
                patch("curve.segmenters.is_mlx_runtime_available", return_value=False),
                patch(
                    "curve.status.mlx_classifier_runtime_status",
                    return_value={
                        "backend": "mlx",
                        "backend_available": False,
                        "status": "not_installed",
                        "reason": "missing",
                    },
                ),
                patch(
                    "curve.status.available_refinement_backends",
                    return_value={
                        "local": ["local_metric"],
                        "optional": ["diffvg"],
                        "details": {
                            "local_metric": {
                                "backend_available": True,
                                "status": "available",
                                "reason": None,
                            },
                            "diffvg": {
                                "backend_available": False,
                                "status": "not_installed",
                                "reason": "missing",
                            },
                        },
                    },
                ),
            ):
                result = collect_runtime_status(output=output)

            written = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(result["schema_version"], 1)
            self.assertEqual(written["segmenters"]["flat_color"]["status"], "available")
            self.assertEqual(written["classifiers"]["mlx"]["status"], "not_installed")
            self.assertIn(
                {
                    "area": "classifier",
                    "backend": "mlx",
                    "status": "not_installed",
                    "available": False,
                    "reason": "missing",
                },
                written["blocked_backends"],
            )

    def test_runtime_status_markdown_summarizes_backends(self):
        markdown = render_runtime_status_markdown(
            {
                "segmenters": {
                    "flat_color": {
                        "backend_available": True,
                        "status": "available",
                        "reason": None,
                    },
                    "mlx_sam": {
                        "backend_available": False,
                        "status": "not_configured",
                        "reason": "model missing",
                    },
                },
                "classifiers": {},
                "refinement": {"details": {}},
                "blocked_backends": [
                    {
                        "area": "segmenter",
                        "backend": "mlx_sam",
                        "status": "not_configured",
                        "available": False,
                        "reason": "model missing",
                    }
                ],
            }
        )

        self.assertIn("# Curve Runtime Status", markdown)
        self.assertIn("`flat_color`", markdown)
        self.assertIn("segmenter/mlx_sam: not_configured", markdown)


if __name__ == "__main__":
    unittest.main()
