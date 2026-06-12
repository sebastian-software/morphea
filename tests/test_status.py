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
            self.assertIn(
                {
                    "area": "segmenter",
                    "backend": "mlx_sam",
                    "capability": "live_sam_model_adapter",
                    "status": "not_installed",
                    "available": False,
                    "reason": "MLX runtime package is not installed",
                },
                written["blocked_capabilities"],
            )

    def test_collect_runtime_status_treats_json_adapter_as_available(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            model_path = root / "sam-proposals.json"
            model_path.write_text(json.dumps({"proposals": []}), encoding="utf-8")

            with (
                patch("curve.segmenters.is_mlx_runtime_available", return_value=False),
                patch(
                    "curve.status.mlx_classifier_runtime_status",
                    return_value={
                        "backend": "mlx",
                        "backend_available": True,
                        "status": "available",
                        "reason": None,
                    },
                ),
                patch(
                    "curve.status.available_refinement_backends",
                    return_value={
                        "local": ["local_metric"],
                        "optional": [],
                        "details": {
                            "local_metric": {
                                "backend_available": True,
                                "status": "available",
                                "reason": None,
                            },
                        },
                    },
                ),
            ):
                result = collect_runtime_status(mlx_sam_model_path=model_path)

            mlx_sam = result["segmenters"]["mlx_sam"]
            self.assertEqual(mlx_sam["status"], "json_adapter_available")
            self.assertTrue(mlx_sam["backend_available"])
            self.assertEqual(mlx_sam["adapter"], "json_proposals")
            self.assertNotIn(
                {
                    "area": "segmenter",
                    "backend": "mlx_sam",
                    "status": "json_adapter_available",
                    "available": True,
                    "reason": None,
                },
                result["blocked_backends"],
            )
            self.assertIn(
                {
                    "area": "segmenter",
                    "backend": "mlx_sam",
                    "capability": "live_sam_model_adapter",
                    "status": "not_installed",
                    "available": False,
                    "reason": "MLX runtime package is not installed",
                },
                result["blocked_capabilities"],
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
                "blocked_capabilities": [
                    {
                        "area": "classifier",
                        "backend": "mlx",
                        "capability": "end_to_end_attention_training",
                        "status": "pending_implementation",
                        "available": False,
                        "reason": "attention training pending",
                    }
                ],
            }
        )

        self.assertIn("# Curve Runtime Status", markdown)
        self.assertIn("`flat_color`", markdown)
        self.assertIn("segmenter/mlx_sam: not_configured", markdown)
        self.assertIn(
            "classifier/mlx/end_to_end_attention_training: pending_implementation",
            markdown,
        )


if __name__ == "__main__":
    unittest.main()
