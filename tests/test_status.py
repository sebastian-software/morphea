import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from morphea.mlx_classifier import MLX_TRAINING_IMPLEMENTATION
from morphea.raster_target_model import RASTER_TARGET_MLX_TRAINING_IMPLEMENTATION
from morphea.segmenters import MLX_SAM_RUNTIME_INSTALL_ACTION
from morphea.status import collect_runtime_status, render_runtime_status_markdown


class RuntimeStatusTests(unittest.TestCase):
    def test_collect_runtime_status_writes_json_with_blockers(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "status.json"

            with (
                patch("morphea.segmenters.is_mlx_runtime_available", return_value=False),
                patch(
                    "morphea.status.mlx_classifier_runtime_status",
                    return_value={
                        "backend": "mlx",
                        "backend_available": False,
                        "status": "not_installed",
                        "reason": "missing",
                    },
                ),
                patch(
                    "morphea.status.raster_target_runtime_status",
                    return_value={
                        "backend": "mlx",
                        "backend_available": True,
                        "status": "available",
                        "reason": None,
                        "training_implementation": (
                            RASTER_TARGET_MLX_TRAINING_IMPLEMENTATION
                        ),
                        "core_available": True,
                        "autograd_available": True,
                        "missing_symbols": [],
                    },
                ),
                patch(
                    "morphea.status.available_refinement_backends",
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
            self.assertEqual(
                written["classifiers"]["raster_target"]["training_implementation"],
                RASTER_TARGET_MLX_TRAINING_IMPLEMENTATION,
            )
            self.assertIn(
                {
                    "area": "classifier",
                    "backend": "mlx",
                    "status": "not_installed",
                    "available": False,
                    "reason": "missing",
                    "next_action": None,
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
                    "next_action": MLX_SAM_RUNTIME_INSTALL_ACTION,
                },
                written["blocked_capabilities"],
            )

    def test_collect_runtime_status_treats_json_adapter_as_available(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            model_path = root / "sam-proposals.json"
            model_path.write_text(json.dumps({"proposals": []}), encoding="utf-8")

            with (
                patch("morphea.segmenters.is_mlx_runtime_available", return_value=False),
                patch(
                    "morphea.status.mlx_classifier_runtime_status",
                    return_value={
                        "backend": "mlx",
                        "backend_available": True,
                        "status": "available",
                        "reason": None,
                    },
                ),
                patch(
                    "morphea.status.raster_target_runtime_status",
                    return_value={
                        "backend": "mlx",
                        "backend_available": True,
                        "status": "available",
                        "reason": None,
                        "training_implementation": (
                            RASTER_TARGET_MLX_TRAINING_IMPLEMENTATION
                        ),
                    },
                ),
                patch(
                    "morphea.status.available_refinement_backends",
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
                    "next_action": None,
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
                    "next_action": MLX_SAM_RUNTIME_INSTALL_ACTION,
                },
                result["blocked_capabilities"],
            )

    def test_collect_runtime_status_treats_mlx_sam_package_adapter_as_available(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            model_path = root / "sam.safetensors"
            model_path.write_text("placeholder", encoding="utf-8")

            with (
                patch("morphea.segmenters.is_mlx_runtime_available", return_value=True),
                patch(
                    "morphea.segmenters.is_mlx_sam_package_available",
                    return_value=True,
                ),
                patch(
                    "morphea.status.mlx_classifier_runtime_status",
                    return_value={
                        "backend": "mlx",
                        "backend_available": True,
                        "status": "available",
                        "reason": None,
                    },
                ),
                patch(
                    "morphea.status.raster_target_runtime_status",
                    return_value={
                        "backend": "mlx",
                        "backend_available": True,
                        "status": "available",
                        "reason": None,
                        "training_implementation": (
                            RASTER_TARGET_MLX_TRAINING_IMPLEMENTATION
                        ),
                    },
                ),
                patch(
                    "morphea.status.available_refinement_backends",
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
            self.assertEqual(mlx_sam["status"], "mlx_sam_package_available")
            self.assertTrue(mlx_sam["backend_available"])
            self.assertEqual(mlx_sam["adapter"], "mlx_sam_grid_points")
            self.assertEqual(
                mlx_sam["model_sidecar_path"],
                str(model_path) + ".json",
            )
            self.assertFalse(mlx_sam["model_sidecar_exists"])
            self.assertEqual(result["blocked_backends"], [])
            self.assertNotIn(
                {
                    "area": "segmenter",
                    "backend": "mlx_sam",
                    "capability": "live_sam_model_adapter",
                    "status": "available",
                    "available": True,
                    "reason": None,
                    "next_action": None,
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
                        "adapter": "mlx_sam_grid_points",
                        "model_path": "checkpoints/sam.safetensors",
                        "model_exists": True,
                        "model_configured": True,
                        "model_sidecar_path": "checkpoints/sam.safetensors.json",
                        "model_sidecar_exists": False,
                        "score_threshold": 0.01,
                        "max_masks": 4,
                        "timeout_seconds": 45,
                        "max_component_area": 12000,
                        "prompt_strategy": "grid_points",
                        "prompt_min_area": 4,
                        "prompt_color_tolerance": 18,
                        "prompt_max_size": 256,
                        "prompt_max_colors": 10,
                    },
                },
                "classifiers": {
                    "mlx": {
                        "backend_available": True,
                        "status": "available",
                        "reason": None,
                        "core_available": True,
                        "backend_version": "test-mlx",
                        "autograd_available": True,
                        "missing_autograd_symbols": [],
                        "training_implementation": MLX_TRAINING_IMPLEMENTATION,
                    },
                    "raster_target": {
                        "backend_available": True,
                        "status": "available",
                        "reason": None,
                        "core_available": True,
                        "backend_version": "test-mlx",
                        "autograd_available": True,
                        "missing_symbols": [],
                        "training_implementation": (
                            RASTER_TARGET_MLX_TRAINING_IMPLEMENTATION
                        ),
                    }
                },
                "refinement": {"details": {}},
                "blocked_backends": [
                    {
                        "area": "segmenter",
                        "backend": "mlx_sam",
                        "status": "not_configured",
                        "available": False,
                        "reason": "model missing",
                        "next_action": "configure a model",
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
                        "next_action": "finish attention training",
                    }
                ],
            }
        )

        self.assertIn("# Morphēa Runtime Status", markdown)
        self.assertIn("`flat_color`", markdown)
        self.assertIn("## Backend Diagnostics", markdown)
        self.assertIn("| segmenter | `mlx_sam` | `adapter` | `mlx_sam_grid_points` |", markdown)
        self.assertIn(
            "| segmenter | `mlx_sam` | `prompt_strategy` | `grid_points` |",
            markdown,
        )
        self.assertIn(
            "| segmenter | `mlx_sam` | `model_sidecar_exists` | `false` |",
            markdown,
        )
        self.assertIn(
            "| segmenter | `mlx_sam` | `model_configured` | `true` |",
            markdown,
        )
        self.assertIn(
            "| segmenter | `mlx_sam` | `score_threshold` | `0.01` |",
            markdown,
        )
        self.assertIn(
            "| segmenter | `mlx_sam` | `max_masks` | `4` |",
            markdown,
        )
        self.assertIn(
            "| segmenter | `mlx_sam` | `timeout_seconds` | `45` |",
            markdown,
        )
        self.assertIn(
            "| segmenter | `mlx_sam` | `prompt_max_colors` | `10` |",
            markdown,
        )
        self.assertIn(
            "| classifier | `mlx` | `core_available` | `true` |",
            markdown,
        )
        self.assertIn(
            "| classifier | `mlx` | `backend_version` | `test-mlx` |",
            markdown,
        )
        self.assertIn(
            "| classifier | `mlx` | `autograd_available` | `true` |",
            markdown,
        )
        self.assertIn(
            "| classifier | `mlx` | `missing_autograd_symbols` | `[]` |",
            markdown,
        )
        self.assertIn(
            "| classifier | `mlx` | `training_implementation` | "
            f"`{MLX_TRAINING_IMPLEMENTATION}` |",
            markdown,
        )
        self.assertIn(
            "| classifier | `raster_target` | `training_implementation` | "
            f"`{RASTER_TARGET_MLX_TRAINING_IMPLEMENTATION}` |",
            markdown,
        )
        self.assertIn(
            "| classifier | `raster_target` | `missing_symbols` | `[]` |",
            markdown,
        )
        self.assertIn("segmenter/mlx_sam: not_configured", markdown)
        self.assertIn("next action: configure a model", markdown)
        self.assertIn(
            "classifier/mlx/end_to_end_attention_training: pending_implementation",
            markdown,
        )
        self.assertIn("next action: finish attention training", markdown)


if __name__ == "__main__":
    unittest.main()
