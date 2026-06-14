import tempfile
import unittest
import json
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageDraw

from morphea.cli import main
from morphea.segmenters import (
    FlatColorSegmenter,
    MLX_SAM_ADAPTER_PENDING_ACTION,
    MLX_SAM_MODEL_CONFIG_ACTION,
    MLX_SAM_MODEL_MISSING_ACTION,
    MLX_SAM_RUNTIME_INSTALL_ACTION,
    MlxSamSegmenter,
    SegmentProposal,
    gate_segment_proposals,
    mlx_sam_runtime_status,
    proposals_to_manifest,
    render_segment_proposal_markdown,
    segment_proposal_groups,
    segment_proposal_summary,
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
        self.assertEqual(proposals[0].anchor_kind, "rect")
        self.assertIsNotNone(proposals[0].anchor_metrics)
        self.assertEqual(proposals[0].anchor_parameter_count, 4)
        self.assertTrue(proposals[0].anchor_reserved)
        self.assertEqual(proposals[0].reservation_reason, "simple_shape_anchor")
        self.assertEqual(proposals[0].reservation_bounds, proposals[0].bounds)

    def test_flat_color_segmenter_splits_same_color_components(self):
        image_path = _write_same_color_component_image()

        proposals = FlatColorSegmenter(min_area=4).propose(image_path)

        self.assertEqual(len(proposals), 2)
        self.assertEqual({proposal.color for proposal in proposals}, {"#dd2222"})
        self.assertTrue(all(proposal.status == "proposed" for proposal in proposals))

    def test_flat_color_segmenter_accepts_explicit_background(self):
        image_path = _write_top_left_foreground_image()

        proposals = FlatColorSegmenter(background="#f6f6f6", min_area=4).propose(
            image_path
        )

        self.assertEqual(len(proposals), 1)
        self.assertEqual(proposals[0].color, "#003366")

    def test_flat_color_segmenter_scales_bounds_from_analysis_size(self):
        image_path = _write_scaled_segment_image()

        proposals = FlatColorSegmenter(
            background="#ffffff",
            min_area=2,
            max_size=20,
        ).propose(image_path)

        self.assertEqual(len(proposals), 1)
        self.assertEqual(proposals[0].bounds, (10, 4, 29, 15))
        self.assertEqual(proposals[0].area, 240)

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
        self.assertTrue(
            all(
                proposal.anchor_kind is None
                for proposal in proposals
                if proposal.status == "deferred"
            )
        )
        self.assertTrue(
            all(
                not proposal.anchor_reserved
                for proposal in proposals
                if proposal.status == "deferred"
            )
        )

    def test_proposals_to_manifest_is_json_ready(self):
        image_path = _write_two_color_image()
        proposals = FlatColorSegmenter().propose(image_path)

        manifest = proposals_to_manifest(proposals)

        self.assertEqual(manifest[0]["source"], "flat_color")
        self.assertIsInstance(manifest[0]["bounds"], list)
        self.assertEqual(manifest[0]["downstream_status"], "pending")
        self.assertIsNone(manifest[0]["rejection_reason"])
        self.assertEqual(manifest[0]["anchor_kind"], "rect")
        self.assertIn("rect_fill_error", manifest[0]["anchor_metrics"])
        self.assertEqual(manifest[0]["anchor_parameter_count"], 4)
        self.assertTrue(manifest[0]["anchor_reserved"])
        self.assertEqual(manifest[0]["reservation_reason"], "simple_shape_anchor")
        self.assertEqual(manifest[0]["reservation_bounds"], manifest[0]["bounds"])
        self.assertIsNone(manifest[0]["anchor_quality_error"])
        self.assertIsNone(manifest[0]["downstream_decision_reason"])

    def test_segment_proposal_summary_counts_statuses_and_anchor_kinds(self):
        image_path = _write_same_color_component_image()
        proposals = FlatColorSegmenter(
            min_area=4,
            max_component_area=30,
        ).propose(image_path)

        summary = segment_proposal_summary(proposals)

        self.assertEqual(summary["status_counts"]["deferred"], 1)
        self.assertEqual(summary["status_counts"]["proposed"], 1)
        self.assertEqual(summary["downstream_status_counts"]["pending"], 1)
        self.assertEqual(summary["downstream_status_counts"]["rejected"], 1)
        self.assertEqual(summary["anchor_kind_counts"]["rect"], 1)
        self.assertEqual(summary["reserved_anchor_count"], 1)

    def test_segment_proposal_groups_detects_tile_grid(self):
        image_path = _write_tile_grid_image()
        proposals = FlatColorSegmenter(min_area=4).propose(image_path)

        groups = segment_proposal_groups(proposals)
        summary = segment_proposal_summary(proposals, groups)

        self.assertEqual(len(groups), 1)
        group = groups[0]
        self.assertEqual(group["kind"], "proposal_tile_grid")
        self.assertEqual(len(group["proposal_ids"]), 4)
        self.assertEqual(group["metrics"]["row_count"], 2.0)
        self.assertEqual(group["metrics"]["column_count"], 2.0)
        self.assertEqual(group["metrics"]["grid_occupancy_ratio"], 1.0)
        self.assertEqual(summary["proposal_group_counts"]["proposal_tile_grid"], 1)

    def test_gate_segment_proposals_accepts_simple_anchor(self):
        image_path = _write_two_color_image()
        proposals = FlatColorSegmenter().propose(image_path)

        gated = gate_segment_proposals(
            proposals,
            max_anchor_quality_error=1.0,
            require_reserved_anchor=True,
        )

        self.assertEqual(gated[0].downstream_status, "accepted")
        self.assertEqual(gated[0].downstream_decision_reason, "geometry_gate_passed")
        self.assertEqual(gated[0].anchor_quality_error, 0.0)
        self.assertIsNone(gated[0].rejection_reason)

    def test_gate_segment_proposals_rejects_noisy_anchor_metrics(self):
        proposal = SegmentProposal(
            id="proposal-0001",
            source="test",
            confidence=0.8,
            color="#003366",
            bounds=(0, 0, 10, 10),
            area=100,
            anchor_kind="circle",
            anchor_metrics={"circle_roundness_error": 2.0},
            anchor_parameter_count=3,
            anchor_reserved=True,
            reservation_reason="simple_shape_anchor",
            reservation_bounds=(0, 0, 10, 10),
        )

        gated = gate_segment_proposals(
            (proposal,),
            max_anchor_quality_error=0.5,
        )

        self.assertEqual(gated[0].downstream_status, "rejected")
        self.assertEqual(gated[0].rejection_reason, "anchor_quality_error_too_high")
        self.assertEqual(
            gated[0].downstream_decision_reason,
            "anchor_quality_error_too_high",
        )
        self.assertEqual(gated[0].anchor_quality_error, 2.0)

    def test_render_segment_proposal_markdown_summarizes_reservations(self):
        image_path = _write_two_color_image()
        proposals = FlatColorSegmenter().propose(image_path)
        manifest = {
            "input": str(image_path),
            "backend": {"source": "flat_color", "status": "available"},
            "proposal_count": len(proposals),
            "summary": segment_proposal_summary(proposals),
            "proposals": proposals_to_manifest(proposals),
        }

        markdown = render_segment_proposal_markdown(manifest)

        self.assertIn("# Morphēa Segment Proposals", markdown)
        self.assertIn("- Reserved anchors: `2`", markdown)
        self.assertIn("`rect`", markdown)
        self.assertIn("simple_shape_anchor", markdown)

    def test_mlx_sam_segmenter_reports_not_configured(self):
        with patch("morphea.segmenters.is_mlx_runtime_available", return_value=False):
            with self.assertRaisesRegex(RuntimeError, "status=not_installed"):
                MlxSamSegmenter().propose("missing.png")

    def test_mlx_sam_runtime_status_reports_package_and_model_state(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            model_path = Path(temp_dir) / "sam.mlx"
            model_path.write_text("placeholder", encoding="utf-8")

            with patch("morphea.segmenters.is_mlx_runtime_available", return_value=True):
                missing_model = mlx_sam_runtime_status(
                    MlxSamSegmenter(model_path=str(model_path.with_name("missing.mlx")))
                )
                configured = mlx_sam_runtime_status(
                    MlxSamSegmenter(model_path=str(model_path))
                )

            self.assertEqual(missing_model["status"], "model_missing")
            self.assertTrue(missing_model["package_available"])
            self.assertFalse(missing_model["model_exists"])
            self.assertEqual(
                missing_model["next_action"],
                MLX_SAM_MODEL_MISSING_ACTION,
            )
            self.assertEqual(configured["status"], "adapter_pending")
            self.assertTrue(configured["model_exists"])
            self.assertFalse(configured["backend_available"])
            self.assertEqual(
                configured["next_action"],
                MLX_SAM_ADAPTER_PENDING_ACTION,
            )
            self.assertEqual(
                configured["capabilities"]["live_sam_model_adapter"]["status"],
                "pending_implementation",
            )
            self.assertEqual(
                configured["capabilities"]["live_sam_model_adapter"]["next_action"],
                MLX_SAM_ADAPTER_PENDING_ACTION,
            )
            self.assertFalse(
                configured["capabilities"]["live_sam_model_adapter"]["available"]
            )

    def test_mlx_sam_runtime_status_reports_package_adapter_available(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            model_path = Path(temp_dir) / "sam.safetensors"
            model_path.write_text("placeholder", encoding="utf-8")

            with (
                patch("morphea.segmenters.is_mlx_runtime_available", return_value=True),
                patch(
                    "morphea.segmenters.is_mlx_sam_package_available",
                    return_value=True,
                ),
            ):
                status = mlx_sam_runtime_status(
                    MlxSamSegmenter(
                        model_path=str(model_path),
                        max_component_area=12000,
                    )
                )

            self.assertEqual(status["status"], "mlx_sam_package_available")
            self.assertTrue(status["backend_available"])
            self.assertEqual(status["adapter"], "mlx_sam_grid_points")
            self.assertEqual(status["max_component_area"], 12000)
            self.assertTrue(status["sam_package_available"])
            self.assertEqual(
                status["model_sidecar_path"],
                str(model_path) + ".json",
            )
            self.assertFalse(status["model_sidecar_exists"])
            self.assertIsNone(status["next_action"])
            self.assertTrue(
                status["capabilities"]["live_sam_model_adapter"]["available"]
            )
            self.assertIsNone(
                status["capabilities"]["live_sam_model_adapter"]["next_action"]
            )

    def test_mlx_sam_runtime_status_reports_checkpoint_sidecar(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            model_path = Path(temp_dir) / "sam.safetensors"
            sidecar_path = Path(str(model_path) + ".json")
            model_path.write_text("placeholder", encoding="utf-8")
            sidecar_path.write_text("{}", encoding="utf-8")

            with (
                patch("morphea.segmenters.is_mlx_runtime_available", return_value=True),
                patch(
                    "morphea.segmenters.is_mlx_sam_package_available",
                    return_value=True,
                ),
            ):
                status = mlx_sam_runtime_status(
                    MlxSamSegmenter(model_path=str(model_path))
                )

            self.assertEqual(status["status"], "mlx_sam_package_available")
            self.assertEqual(status["model_sidecar_path"], str(sidecar_path))
            self.assertTrue(status["model_sidecar_exists"])

    def test_mlx_sam_runtime_status_reports_missing_sam_package_action(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            model_path = Path(temp_dir) / "sam.safetensors"
            model_path.write_text("placeholder", encoding="utf-8")

            with (
                patch("morphea.segmenters.is_mlx_runtime_available", return_value=True),
                patch(
                    "morphea.segmenters.is_mlx_sam_package_available",
                    return_value=False,
                ),
            ):
                status = mlx_sam_runtime_status(
                    MlxSamSegmenter(model_path=str(model_path))
                )

            self.assertEqual(status["status"], "mlx_sam_package_missing")
            self.assertFalse(status["backend_available"])
            self.assertEqual(status["next_action"], MLX_SAM_RUNTIME_INSTALL_ACTION)
            self.assertEqual(
                status["capabilities"]["live_sam_model_adapter"]["status"],
                "mlx_sam_package_missing",
            )
            self.assertEqual(
                status["capabilities"]["live_sam_model_adapter"]["next_action"],
                MLX_SAM_RUNTIME_INSTALL_ACTION,
            )

    def test_mlx_sam_runtime_status_requires_model_configuration(self):
        with patch("morphea.segmenters.is_mlx_runtime_available", return_value=True):
            status = mlx_sam_runtime_status(MlxSamSegmenter())

        self.assertEqual(status["status"], "not_configured")
        self.assertTrue(status["package_available"])
        self.assertFalse(status["model_configured"])
        self.assertEqual(status["next_action"], MLX_SAM_MODEL_CONFIG_ACTION)
        self.assertEqual(
            status["capabilities"]["live_sam_model_adapter"]["status"],
            "not_configured",
        )
        self.assertEqual(
            status["capabilities"]["live_sam_model_adapter"]["next_action"],
            MLX_SAM_MODEL_CONFIG_ACTION,
        )

    def test_mlx_sam_segmenter_keeps_adapter_pending_non_operational(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            model_path = Path(temp_dir) / "sam.mlx"
            model_path.write_text("placeholder", encoding="utf-8")

            with patch("morphea.segmenters.is_mlx_runtime_available", return_value=True):
                with self.assertRaisesRegex(RuntimeError, "status=adapter_pending"):
                    MlxSamSegmenter(model_path=str(model_path)).propose("input.png")

    def test_mlx_sam_json_adapter_reports_available_without_mlx_package(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            model_path = Path(temp_dir) / "sam-proposals.json"
            model_path.write_text(json.dumps({"proposals": []}), encoding="utf-8")

            with patch("morphea.segmenters.is_mlx_runtime_available", return_value=False):
                status = mlx_sam_runtime_status(
                    MlxSamSegmenter(model_path=str(model_path))
                )

            self.assertEqual(status["status"], "json_adapter_available")
            self.assertTrue(status["backend_available"])
            self.assertEqual(status["adapter"], "json_proposals")
            self.assertFalse(status["package_available"])
            self.assertIsNone(status["next_action"])
            self.assertTrue(
                status["capabilities"]["json_proposal_adapter"]["available"]
            )
            self.assertIsNone(
                status["capabilities"]["json_proposal_adapter"]["next_action"]
            )
            self.assertEqual(
                status["capabilities"]["live_sam_model_adapter"]["status"],
                "not_installed",
            )
            self.assertEqual(
                status["capabilities"]["live_sam_model_adapter"]["next_action"],
                MLX_SAM_RUNTIME_INSTALL_ACTION,
            )

    def test_mlx_sam_json_adapter_filters_and_limits_proposals(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            model_path = Path(temp_dir) / "sam-proposals.json"
            model_path.write_text(
                json.dumps(
                    {
                        "proposals": [
                            {
                                "bounds": [1, 1, 6, 6],
                                "confidence": 0.95,
                                "color": "#003366",
                            },
                            {
                                "bounds": [8, 1, 11, 4],
                                "confidence": 0.50,
                            },
                            {
                                "bbox": [12, 1, 4, 4],
                                "confidence": 0.90,
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )
            segmenter = MlxSamSegmenter(
                model_path=str(model_path),
                score_threshold=0.75,
                max_masks=1,
            )

            proposals = segmenter.propose("input.png")

            self.assertEqual(len(proposals), 1)
            self.assertEqual(proposals[0].source, "mlx_sam")
            self.assertEqual(proposals[0].confidence, 0.95)
            self.assertEqual(proposals[0].bounds, (1, 1, 6, 6))
            self.assertEqual(proposals[0].anchor_kind, "rect")
            self.assertTrue(proposals[0].anchor_reserved)

    def test_mlx_sam_json_adapter_accepts_mask_payloads(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            model_path = Path(temp_dir) / "sam-masks.json"
            model_path.write_text(
                json.dumps(
                    {
                        "proposals": [
                            {
                                "mask": {
                                    "x": 6,
                                    "y": 4,
                                    "rows": [
                                        ".##.",
                                        "####",
                                        ".##.",
                                    ],
                                },
                                "confidence": 0.91,
                            },
                            {
                                "mask": [
                                    [0, 1, 0],
                                    [1, 1, 1],
                                ],
                                "x": 20,
                                "y": 10,
                                "score": 0.82,
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            proposals = MlxSamSegmenter(model_path=str(model_path)).propose("input.png")

            self.assertEqual(len(proposals), 2)
            self.assertEqual(proposals[0].bounds, (6, 4, 9, 6))
            self.assertEqual(proposals[0].area, 8)
            self.assertEqual(proposals[1].bounds, (20, 10, 22, 11))
            self.assertEqual(proposals[1].area, 4)

    def test_mlx_sam_json_adapter_honors_timeout(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            model_path = Path(temp_dir) / "sam-proposals.json"
            model_path.write_text(
                json.dumps(
                    {
                        "proposals": [
                            {
                                "bounds": [1, 1, 6, 6],
                                "confidence": 0.95,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            segmenter = MlxSamSegmenter(
                model_path=str(model_path),
                timeout_seconds=0.0,
            )

            proposals = segmenter.propose("input.png")

            self.assertEqual(proposals, ())

    def test_mlx_sam_segmenter_reports_runtime_config_in_error(self):
        with patch("morphea.segmenters.is_mlx_runtime_available", return_value=False):
            with self.assertRaisesRegex(RuntimeError, "model_path=models/sam.mlx"):
                MlxSamSegmenter(
                    model_path="models/sam.mlx",
                    max_masks=12,
                    timeout_seconds=3.5,
                ).propose("missing.png")

    def test_segmenter_backend_status_reports_availability(self):
        flat = segmenter_backend_status(FlatColorSegmenter())
        with patch("morphea.segmenters.is_mlx_runtime_available", return_value=False):
            mlx = segmenter_backend_status(
                MlxSamSegmenter(model_path="models/sam.mlx", max_masks=12)
            )

        self.assertTrue(flat["backend_available"])
        self.assertEqual(flat["status"], "available")
        self.assertFalse(mlx["backend_available"])
        self.assertEqual(mlx["status"], "not_installed")
        self.assertFalse(mlx["package_available"])
        self.assertEqual(mlx["model_path"], "models/sam.mlx")
        self.assertEqual(mlx["next_action"], MLX_SAM_RUNTIME_INSTALL_ACTION)

    def test_mlx_sam_segmenter_reports_not_configured_legacy_regex(self):
        with self.assertRaisesRegex(RuntimeError, "not installed/configured"):
            MlxSamSegmenter().propose("missing.png")

    def test_segment_cli_writes_flat_color_manifest_from_config(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image_path = _write_two_color_image()
            output = root / "segments.json"
            markdown = root / "segments.md"
            config = root / "segment-config.json"
            config.write_text(
                json.dumps(
                    {
                        "segmenter": "flat_color",
                        "background": "#ffffff",
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
                        "--markdown",
                        str(markdown),
                        "--config",
                        str(config),
                    ]
                )

            manifest = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(manifest["schema_version"], 1)
            self.assertEqual(manifest["config"]["segmenter"], "flat_color")
            self.assertEqual(manifest["config"]["background"], "#ffffff")
            self.assertTrue(manifest["backend"]["backend_available"])
            self.assertEqual(manifest["backend"]["source"], "flat_color")
            self.assertEqual(manifest["config"]["max_component_area"], 10)
            self.assertTrue(manifest["config"]["split_components"])
            self.assertEqual(manifest["proposal_count"], 2)
            self.assertEqual(manifest["summary"]["status_counts"]["deferred"], 2)
            self.assertEqual(
                manifest["summary"]["downstream_status_counts"]["rejected"],
                2,
            )
            self.assertEqual(manifest["summary"]["anchor_kind_counts"], {})
            self.assertEqual(manifest["summary"]["reserved_anchor_count"], 0)
            self.assertEqual(manifest["proposals"][0]["status"], "deferred")
            self.assertEqual(
                manifest["proposals"][0]["downstream_status"],
                "rejected",
            )
            self.assertIsNone(manifest["proposals"][0]["anchor_kind"])
            self.assertFalse(manifest["proposals"][0]["anchor_reserved"])
            report = markdown.read_text(encoding="utf-8")
            self.assertIn("# Morphēa Segment Proposals", report)
            self.assertIn("- Reserved anchors: `0`", report)

    def test_segment_cli_reads_artifact_paths_from_config(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image_path = _write_two_color_image()
            output = root / "segments.json"
            markdown = root / "segments.md"
            config = root / "segment-config.json"
            config.write_text(
                json.dumps(
                    {
                        "input": str(image_path),
                        "output": str(output),
                        "markdown": str(markdown),
                        "segmenter": "flat_color",
                        "background": "#ffffff",
                        "min_area": 4,
                    }
                ),
                encoding="utf-8",
            )

            with redirect_stdout(StringIO()):
                main(["segment", "--config", str(config)])

            manifest = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(manifest["input"], str(image_path))
            self.assertEqual(manifest["config"]["background"], "#ffffff")
            self.assertTrue(markdown.exists())

    def test_segment_cli_args_override_config_artifact_paths(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_input = root / "config-input.png"
            Image.new("RGB", (8, 8), "white").save(config_input)
            override_input = _write_two_color_image()
            config_output = root / "config-segments.json"
            output = root / "override-segments.json"
            config = root / "segment-config.json"
            config.write_text(
                json.dumps(
                    {
                        "input": str(config_input),
                        "output": str(config_output),
                        "segmenter": "flat_color",
                        "background": "#ffffff",
                        "min_area": 999,
                    }
                ),
                encoding="utf-8",
            )

            with redirect_stdout(StringIO()):
                main(
                    [
                        "segment",
                        str(override_input),
                        "-o",
                        str(output),
                        "--config",
                        str(config),
                        "--min-area",
                        "4",
                    ]
                )

            manifest = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(manifest["input"], str(override_input))
            self.assertEqual(manifest["proposal_count"], 2)
            self.assertFalse(config_output.exists())

    def test_segment_cli_can_gate_proposals_by_geometry(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image_path = _write_two_color_image()
            output = root / "segments.json"
            markdown = root / "segments.md"
            config = root / "segment-config.json"
            config.write_text(
                json.dumps(
                    {
                        "segmenter": "flat_color",
                        "background": "#ffffff",
                        "min_area": 4,
                        "geometry_gate": True,
                        "max_anchor_quality_error": 1.0,
                        "require_reserved_anchor": True,
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
                        "--markdown",
                        str(markdown),
                        "--config",
                        str(config),
                    ]
                )

            manifest = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(
                manifest["summary"]["downstream_status_counts"]["accepted"],
                2,
            )
            self.assertEqual(
                manifest["summary"]["downstream_decision_reason_counts"][
                    "geometry_gate_passed"
                ],
                2,
            )
            self.assertEqual(
                manifest["proposals"][0]["downstream_decision_reason"],
                "geometry_gate_passed",
            )
            self.assertEqual(manifest["proposals"][0]["anchor_quality_error"], 0.0)
            report = markdown.read_text(encoding="utf-8")
            self.assertIn("- Decision reason counts: `geometry_gate_passed: 2`", report)
            self.assertIn("geometry_gate_passed", report)

    def test_segment_cli_runs_mlx_sam_json_adapter_with_geometry_gate(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image_path = _write_two_color_image()
            model_path = root / "sam-proposals.json"
            output = root / "segments.json"
            markdown = root / "segments.md"
            config = root / "segment-config.json"
            model_path.write_text(
                json.dumps(
                    {
                        "proposals": [
                            {
                                "bounds": [1, 1, 6, 6],
                                "confidence": 0.92,
                                "color": "#003366",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            config.write_text(
                json.dumps(
                    {
                        "input": str(image_path),
                        "output": str(output),
                        "markdown": str(markdown),
                        "segmenter": "mlx_sam",
                        "mlx_model_path": str(model_path),
                        "geometry_gate": True,
                        "require_reserved_anchor": True,
                    }
                ),
                encoding="utf-8",
            )

            with patch("morphea.segmenters.is_mlx_runtime_available", return_value=False):
                with redirect_stdout(StringIO()):
                    main(["segment", "--config", str(config)])

            manifest = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(manifest["backend"]["status"], "json_adapter_available")
            self.assertEqual(manifest["backend"]["adapter"], "json_proposals")
            self.assertEqual(manifest["proposal_count"], 1)
            self.assertEqual(
                manifest["summary"]["downstream_status_counts"]["accepted"],
                1,
            )
            self.assertEqual(
                manifest["proposals"][0]["downstream_decision_reason"],
                "geometry_gate_passed",
            )
            self.assertIn("json_adapter_available", markdown.read_text(encoding="utf-8"))

    def test_segment_cli_applies_max_component_area_to_mlx_sam_adapter(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image_path = _write_two_color_image()
            model_path = root / "sam-proposals.json"
            output = root / "segments.json"
            config = root / "segment-config.json"
            model_path.write_text(
                json.dumps(
                    {
                        "proposals": [
                            {
                                "bounds": [0, 0, 19, 11],
                                "confidence": 0.92,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            config.write_text(
                json.dumps(
                    {
                        "input": str(image_path),
                        "output": str(output),
                        "segmenter": "mlx_sam",
                        "mlx_model_path": str(model_path),
                        "max_component_area": 10,
                        "geometry_gate": True,
                        "require_reserved_anchor": True,
                    }
                ),
                encoding="utf-8",
            )

            with patch("morphea.segmenters.is_mlx_runtime_available", return_value=False):
                with redirect_stdout(StringIO()):
                    main(["segment", "--config", str(config)])

            manifest = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(manifest["config"]["max_component_area"], 10)
            self.assertEqual(manifest["summary"]["status_counts"]["deferred"], 1)
            self.assertEqual(
                manifest["summary"]["downstream_status_counts"]["rejected"],
                1,
            )
            proposal = manifest["proposals"][0]
            self.assertEqual(proposal["status"], "deferred")
            self.assertEqual(proposal["downstream_status"], "rejected")
            self.assertEqual(
                proposal["rejection_reason"],
                "max_component_area_exceeded",
            )
            self.assertIsNone(proposal["anchor_kind"])
            self.assertIsNone(proposal["downstream_decision_reason"])

    def test_segment_cli_serializes_cli_mlx_model_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image_path = _write_two_color_image()
            model_path = root / "sam-proposals.json"
            output = root / "segments.json"
            model_path.write_text(
                json.dumps(
                    {
                        "proposals": [
                            {
                                "bounds": [1, 1, 6, 6],
                                "confidence": 0.92,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            with patch("morphea.segmenters.is_mlx_runtime_available", return_value=False):
                with redirect_stdout(StringIO()):
                    main(
                        [
                            "segment",
                            str(image_path),
                            "-o",
                            str(output),
                            "--segmenter",
                            "mlx_sam",
                            "--mlx-model-path",
                            str(model_path),
                        ]
                    )

            manifest = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(
                manifest["config"]["mlx_model_path"],
                str(model_path),
            )
            self.assertEqual(manifest["backend"]["status"], "json_adapter_available")

    def test_segment_cli_writes_tile_grid_proposal_groups(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image_path = _write_tile_grid_image()
            output = root / "segments.json"
            markdown = root / "segments.md"

            with redirect_stdout(StringIO()):
                main(
                    [
                        "segment",
                        str(image_path),
                        "-o",
                        str(output),
                        "--markdown",
                        str(markdown),
                        "--min-area",
                        "4",
                    ]
                )

            manifest = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(manifest["proposal_count"], 4)
            self.assertEqual(
                manifest["proposal_groups"][0]["kind"],
                "proposal_tile_grid",
            )
            self.assertEqual(
                manifest["summary"]["proposal_group_counts"]["proposal_tile_grid"],
                1,
            )
            report = markdown.read_text(encoding="utf-8")
            self.assertIn("## Proposal Groups", report)
            self.assertIn("`proposal_tile_grid`", report)

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

    def test_checked_in_mlx_sam_smoke_configs_are_repeatable(self):
        repo_root = Path(__file__).resolve().parents[1]
        config_dir = repo_root / "docs" / "real-images" / "mlx-sam-smoke"
        status_config = json.loads(
            (config_dir / "status.json").read_text(encoding="utf-8")
        )
        flat_config_path = config_dir / "flat-color-segment.json"
        flat_config = json.loads(flat_config_path.read_text(encoding="utf-8"))
        mlx_config = json.loads(
            (config_dir / "mlx-sam-segment.json").read_text(encoding="utf-8")
        )
        compare_config = json.loads(
            (config_dir / "compare-segments.json").read_text(encoding="utf-8")
        )

        self.assertEqual(flat_config["segmenter"], "flat_color")
        self.assertEqual(mlx_config["segmenter"], "mlx_sam")
        self.assertEqual(flat_config["input"], mlx_config["input"])
        self.assertEqual(
            flat_config["input"],
            "assets/curated/terminaro-opaque-table-grid.png",
        )
        self.assertTrue((repo_root / flat_config["input"]).exists())
        self.assertEqual(mlx_config["mlx_max_masks"], 4)
        self.assertEqual(mlx_config["mlx_score_threshold"], 0.01)
        self.assertEqual(mlx_config["max_component_area"], 12000)
        self.assertEqual(
            mlx_config["mlx_model_path"],
            status_config["mlx_sam_model_path"],
        )
        self.assertEqual(compare_config["before"], flat_config["output"])
        self.assertEqual(compare_config["after"], mlx_config["output"])

        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "flat-color-segments.json"
            markdown = Path(temp_dir) / "flat-color-segments.md"

            with redirect_stdout(StringIO()) as stdout:
                main(
                    [
                        "segment",
                        "--config",
                        str(flat_config_path),
                        "-o",
                        str(output),
                        "--markdown",
                        str(markdown),
                    ]
                )

            manifest = json.loads(output.read_text(encoding="utf-8"))
            self.assertIn("wrote 41 segment proposals", stdout.getvalue())
            self.assertEqual(manifest["proposal_count"], 41)
            self.assertEqual(manifest["config"]["segmenter"], "flat_color")
            self.assertTrue(manifest["config"]["geometry_gate"])
            self.assertTrue(manifest["config"]["require_reserved_anchor"])
            self.assertEqual(
                manifest["summary"]["downstream_status_counts"]["accepted"],
                29,
            )
            self.assertTrue(markdown.exists())


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


def _write_top_left_foreground_image() -> Path:
    temp_dir = tempfile.TemporaryDirectory()
    path = Path(temp_dir.name) / "top-left-foreground.png"
    image = Image.new("RGB", (18, 14), "#f6f6f6")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 8, 5), fill="#003366")
    image.save(path)
    _TEMP_DIRS.append(temp_dir)
    return path


def _write_scaled_segment_image() -> Path:
    temp_dir = tempfile.TemporaryDirectory()
    path = Path(temp_dir.name) / "scaled-segment.png"
    image = Image.new("RGB", (40, 20), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((10, 4, 29, 15), fill="#dd2222")
    image.save(path)
    _TEMP_DIRS.append(temp_dir)
    return path


def _write_tile_grid_image() -> Path:
    temp_dir = tempfile.TemporaryDirectory()
    path = Path(temp_dir.name) / "tile-grid.png"
    image = Image.new("RGB", (26, 26), "white")
    draw = ImageDraw.Draw(image)
    colors = ("#dd2222", "#003366", "#c48800", "#226644")
    boxes = (
        (2, 2, 8, 8),
        (14, 2, 20, 8),
        (2, 14, 8, 20),
        (14, 14, 20, 20),
    )
    for color, box in zip(colors, boxes):
        draw.rectangle(box, fill=color)
    image.save(path)
    _TEMP_DIRS.append(temp_dir)
    return path


_TEMP_DIRS: list[tempfile.TemporaryDirectory] = []


if __name__ == "__main__":
    unittest.main()
