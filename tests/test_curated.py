import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from PIL import Image, ImageDraw

from morphea.cli import main
from morphea.curated import (
    _promotion_region_results,
    _structure_threshold_promotion_gate,
    check_curated_suite,
    load_curated_suite,
    render_curated_markdown,
    render_curated_snapshot,
)


def _promotion_metadata(label: str) -> dict[str, object]:
    return {
        "stress_family": "test_fixture",
        "source_provenance": "generated test fixture",
        "licensing_status": "test_fixture",
        "expected_promotion_families": ["circle"],
        "current_quality_label": label,
        "current_status": "checked",
        "current_issues": ["fragmentation"] if label != "green" else [],
        "visual_audit_status": "run_artifacts_only",
        "visual_thresholds": {
            "family": "test_fixture",
            "max_raster_l1_error": 1.0,
            "max_raster_edge_error": 1.0,
            "severity": "red",
            "description": "Synthetic fixture visual thresholds should pass when run artifacts exist.",
        },
        "structure_thresholds": {
            "max_fragmentation_penalty": 1.0,
            "max_layer_count": 10,
            "severity": "red",
            "description": "Synthetic fixture structure thresholds should pass.",
        },
        "review_notes": ["synthetic metadata fixture"],
        "hard_gates": [
            {
                "id": "circle-shape-class",
                "gate_type": "shape_class",
                "expectation_ids": ["circle-anchor"],
                "severity": "red",
                "description": "Circle fixture must remain a circle anchor.",
            }
        ],
        "region_gates": [
            {
                "id": "circle-region",
                "gate_type": "shape_class",
                "bounds": [4, 4, 18, 18],
                "expected_kinds": ["circle"],
                "min_iou": 0.3,
                "min_count": 1,
                "severity": "red",
                "description": "Circle fixture region should promote one circle anchor.",
            }
        ],
    }


class CuratedSuiteTests(unittest.TestCase):
    def test_load_curated_suite_validates_required_fields(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            suite_path = Path(temp_dir) / "suite.json"
            suite_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "cases": [
                            {
                                "id": "simple-circle",
                                "source": "/tmp/simple-circle.png",
                                "promotion": _promotion_metadata("green"),
                                "recommended_config": {"min_area": 4},
                                "expectations": [
                                    {
                                        "id": "circle-anchor",
                                        "kind": "circle",
                                        "min_count": 1,
                                    },
                                    {
                                        "id": "editable-enough",
                                        "metric": "editability_score",
                                        "min_value": 0.0,
                                    }
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            suite = load_curated_suite(suite_path)

            self.assertEqual(suite["cases"][0]["id"], "simple-circle")
            self.assertEqual(
                suite["cases"][0]["promotion"]["current_quality_label"],
                "green",
            )

    def test_check_curated_suite_can_run_expected_anchor_checks(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "input.png"
            suite_path = Path(temp_dir) / "suite.json"
            output = Path(temp_dir) / "report.json"
            output_dir = Path(temp_dir) / "artifacts"
            snapshot = Path(temp_dir) / "snapshot.json"
            image = Image.new("RGB", (24, 24), "white")
            draw = ImageDraw.Draw(image)
            draw.ellipse((5, 5, 17, 17), fill="#c08011")
            image.save(source)
            suite_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "cases": [
                            {
                                "id": "simple-circle",
                                "source": str(source),
                                "promotion": _promotion_metadata("green"),
                                "recommended_config": {
                                    "min_area": 8,
                                    "timeout_seconds": 5,
                                },
                                "expectations": [
                                    {
                                        "id": "circle-anchor",
                                        "kind": "circle",
                                        "min_count": 1,
                                    },
                                    {
                                        "id": "editable-enough",
                                        "metric": "editability_score",
                                        "min_value": 0.0,
                                    },
                                    {
                                        "id": "bounded-fragmentation",
                                        "metric": "fragmentation_penalty",
                                        "max_value": 1.0,
                                    }
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            result = check_curated_suite(
                suite_path,
                output=output,
                output_dir=output_dir,
                run=True,
                snapshot=snapshot,
            )

            self.assertTrue(result["ok"])
            self.assertEqual(
                result["family_summary"]["test_fixture"],
                {
                    "case_count": 1,
                    "checked_count": 1,
                    "passed_count": 1,
                    "failed_count": 0,
                    "missing_source_count": 0,
                },
            )
            self.assertEqual(result["cases"][0]["status"], "checked")
            self.assertTrue(result["cases"][0]["expectations"][0]["ok"])
            self.assertTrue(result["cases"][0]["expectations"][1]["ok"])
            self.assertIn("actual_value", result["cases"][0]["expectations"][1])
            self.assertTrue(result["cases"][0]["expectations"][2]["ok"])
            self.assertEqual(result["cases"][0]["anchor_kind_counts"]["circle"], 1)
            self.assertGreaterEqual(result["cases"][0]["layer_count"], 1)
            self.assertTrue((output_dir / "simple-circle" / "output.svg").exists())
            self.assertTrue((output_dir / "simple-circle" / "debug.svg").exists())
            self.assertTrue((output_dir / "simple-circle" / "manifest.json").exists())
            self.assertTrue((output_dir / "simple-circle" / "report.md").exists())
            self.assertTrue((output_dir / "simple-circle" / "report.html").exists())
            self.assertTrue((output_dir / "simple-circle" / "preview.png").exists())
            self.assertTrue((output_dir / "simple-circle" / "svg-render.png").exists())
            self.assertTrue((output_dir / "simple-circle" / "diff.png").exists())
            self.assertTrue((output_dir / "simple-circle" / "anchor-overlay.png").exists())
            self.assertTrue((output_dir / "simple-circle" / "promoted.svg").exists())
            self.assertTrue((output_dir / "simple-circle" / "fallback.svg").exists())
            self.assertTrue((output_dir / "simple-circle" / "promotion-export.json").exists())
            self.assertTrue((output_dir / "simple-circle" / "promotion-regions.json").exists())
            self.assertTrue((output_dir / "simple-circle" / "promotion-review.md").exists())
            self.assertTrue((output_dir / "simple-circle" / "editability-review.md").exists())
            self.assertTrue((output_dir / "simple-circle" / "review-decision.json").exists())
            self.assertTrue((output_dir / "simple-circle" / "contact-sheet.png").exists())
            self.assertTrue((output_dir / "simple-circle" / "input" / "input.png").exists())
            self.assertTrue((output_dir / "review-gallery.html").exists())
            with Image.open(output_dir / "simple-circle" / "contact-sheet.png") as sheet:
                self.assertEqual(sheet.size, (1636, 268))
            promoted_svg = (output_dir / "simple-circle" / "promoted.svg").read_text(
                encoding="utf-8"
            )
            fallback_svg = (output_dir / "simple-circle" / "fallback.svg").read_text(
                encoding="utf-8"
            )
            self.assertIn("<circle", promoted_svg)
            self.assertIn('id="morphea-anchor-0000-anchor-0000"', promoted_svg)
            self.assertIn('data-morphea-anchor-id="anchor-0000"', promoted_svg)
            self.assertIn('data-anchor-index="0"', promoted_svg)
            self.assertIn('data-promotion-state="promoted"', promoted_svg)
            self.assertIn('data-promotion-regions="circle-region"', promoted_svg)
            self.assertIn('data-review-decision="pending"', promoted_svg)
            self.assertNotIn("<circle", fallback_svg)
            promotion_export = json.loads(
                (output_dir / "simple-circle" / "promotion-export.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(promotion_export["region_state_counts"]["promoted"], 1)
            self.assertEqual(promotion_export["promoted_anchor_indexes"], [0])
            self.assertEqual(promotion_export["fallback_anchor_indexes"], [])
            self.assertEqual(promotion_export["fallback_only_anchor_indexes"], [])
            self.assertEqual(promotion_export["rejected_anchor_indexes"], [])
            self.assertEqual(
                promotion_export["anchor_state_counts"],
                {"promoted": 1},
            )
            self.assertEqual(
                promotion_export["export_summary"]["promoted_anchor_count"],
                1,
            )
            promotion_regions = json.loads(
                (output_dir / "simple-circle" / "promotion-regions.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(
                promotion_regions["regions"][0]["selected_anchor_indexes"],
                [0],
            )
            promotion_review = (
                output_dir / "simple-circle" / "promotion-review.md"
            ).read_text(encoding="utf-8")
            self.assertIn("| `circle-region` | `promoted` |", promotion_review)
            self.assertIn("## Candidate Rejections", promotion_review)
            self.assertIn("| n/a | n/a | n/a | n/a | n/a |", promotion_review)
            editability_review = (
                output_dir / "simple-circle" / "editability-review.md"
            ).read_text(encoding="utf-8")
            self.assertIn("- Decision: `accepted`", editability_review)
            self.assertIn("## Required Thresholds", editability_review)
            self.assertIn("| `topology_consistency` |", editability_review)
            self.assertIn("| n/a | n/a | n/a | `none` |", editability_review)
            review_decision = json.loads(
                (output_dir / "simple-circle" / "review-decision.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(review_decision["decision"], "pending")
            self.assertEqual(review_decision["suggested_decision"], "accepted")
            self.assertEqual(
                review_decision["quality_label_policy"]["mode"],
                "sidecar_only",
            )
            self.assertFalse(
                review_decision["quality_label_policy"][
                    "updates_current_quality_label"
                ]
            )
            self.assertEqual(
                review_decision["allowed_decisions"],
                ["accepted", "corrected", "rejected", "deferred"],
            )
            self.assertEqual(review_decision["issue_tags"], [])
            manifest = json.loads(
                (output_dir / "simple-circle" / "manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertIn("raster_l1_error", manifest["metrics"])
            self.assertEqual(
                manifest["promotion"]["regions"][0]["state"],
                "promoted",
            )
            self.assertEqual(
                manifest["anchors"][0]["promotion_state"],
                "promoted",
            )
            self.assertEqual(
                manifest["anchors"][0]["promotion_regions"][0]["region_id"],
                "circle-region",
            )
            self.assertIn(
                "editability_review",
                manifest["promotion"]["artifacts"],
            )
            self.assertIn(
                "review_decision",
                manifest["promotion"]["artifacts"],
            )
            self.assertEqual(
                manifest["review_decision"]["suggested_decision"],
                "accepted",
            )
            report = json.loads(output.read_text())
            self.assertEqual(report["case_count"], 1)
            self.assertIn("review_gallery", report["artifacts"])
            self.assertIn("raster_l1_error", report["cases"][0]["metrics"])
            self.assertIn("raster_edge_error", report["cases"][0]["metrics"])
            self.assertIn("artifacts", report["cases"][0])
            self.assertIn("anchor_overlay", report["cases"][0]["artifacts"])
            self.assertIn("contact_sheet", report["cases"][0]["artifacts"])
            self.assertIn("promoted_svg", report["cases"][0]["artifacts"])
            self.assertIn("fallback_svg", report["cases"][0]["artifacts"])
            self.assertIn("promotion_export", report["cases"][0]["artifacts"])
            self.assertIn("promotion_regions", report["cases"][0]["artifacts"])
            self.assertIn("promotion_review", report["cases"][0]["artifacts"])
            self.assertIn("editability_review", report["cases"][0]["artifacts"])
            self.assertIn("review_decision", report["cases"][0]["artifacts"])
            self.assertEqual(
                report["cases"][0]["promotion_summary"]["decision"],
                "promoted",
            )
            self.assertEqual(
                report["cases"][0]["editability_review"]["decision"],
                "accepted",
            )
            self.assertTrue(report["cases"][0]["editability_review"]["accepted"])
            self.assertEqual(
                report["cases"][0]["review_decision"]["suggested_decision"],
                "accepted",
            )
            self.assertFalse(
                [
                    gate
                    for gate in report["cases"][0]["promotion_gates"]
                    if not gate["ok"]
                ]
            )
            review_gallery = (output_dir / "review-gallery.html").read_text(
                encoding="utf-8"
            )
            self.assertIn("Morphēa review gallery", review_gallery)
            self.assertIn('<article class="case-card green">', review_gallery)
            self.assertIn("simple-circle/contact-sheet.png", review_gallery)
            self.assertIn("Promotion review", review_gallery)
            self.assertIn("review-packet.md", review_gallery)
            self.assertNotIn("review queue", review_gallery)
            gate_by_id = {
                gate["id"]: gate for gate in report["cases"][0]["promotion_gates"]
            }
            self.assertEqual(
                gate_by_id["circle-shape-class"]["gate_type"],
                "shape_class",
            )
            self.assertTrue(gate_by_id["circle-shape-class"]["ok"])
            self.assertTrue(gate_by_id["fragmentation_layer_thresholds"]["ok"])
            self.assertIn(
                "layer_count",
                gate_by_id["fragmentation_layer_thresholds"]["evidence"]["actual"],
            )
            self.assertTrue(gate_by_id["visual_fidelity_thresholds"]["ok"])
            self.assertEqual(
                gate_by_id["visual_fidelity_thresholds"]["evidence"]["family"],
                "test_fixture",
            )
            self.assertEqual(
                report["cases"][0]["promotion"]["current_quality_label"],
                "green",
            )
            snapshot_report = json.loads(snapshot.read_text(encoding="utf-8"))
            self.assertEqual(snapshot_report["schema_version"], 1)
            self.assertEqual(snapshot_report["cases"][0]["id"], "simple-circle")
            self.assertEqual(
                snapshot_report["cases"][0]["anchor_kind_counts"]["circle"],
                1,
            )
            metric_expectations = {
                item["id"]: item
                for item in snapshot_report["cases"][0]["expectations"]
            }
            self.assertIn("actual_value", metric_expectations["editable-enough"])
            self.assertEqual(
                metric_expectations["editable-enough"]["metric"],
                "editability_score",
            )
            self.assertIn("editability_score", snapshot_report["cases"][0]["metrics"])
            self.assertIn("layer_count", snapshot_report["cases"][0])
            self.assertEqual(
                snapshot_report["cases"][0]["promotion"]["stress_family"],
                "test_fixture",
            )
            self.assertEqual(
                snapshot_report["cases"][0]["promotion_summary"]["decision"],
                "promoted",
            )
            self.assertEqual(
                snapshot_report["cases"][0]["editability_review"]["decision"],
                "accepted",
            )
            self.assertEqual(
                snapshot_report["cases"][0]["review_decision"]["suggested_decision"],
                "accepted",
            )

    def test_quality_label_review_policy_defers_mechanically_green_case(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "input.png"
            suite_path = Path(temp_dir) / "suite.json"
            output_dir = Path(temp_dir) / "artifacts"
            image = Image.new("RGB", (24, 24), "white")
            draw = ImageDraw.Draw(image)
            draw.ellipse((5, 5, 17, 17), fill="#c08011")
            image.save(source)
            promotion = _promotion_metadata("red")
            promotion["quality_label_review_policy"] = "manual_review_pending"
            promotion["current_issues"] = ["manual_review_pending"]
            suite_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "cases": [
                            {
                                "id": "simple-circle",
                                "source": str(source),
                                "promotion": promotion,
                                "recommended_config": {
                                    "min_area": 8,
                                    "timeout_seconds": 5,
                                },
                                "expectations": [
                                    {
                                        "id": "circle-anchor",
                                        "kind": "circle",
                                        "min_count": 1,
                                    }
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            result = check_curated_suite(
                suite_path,
                output_dir=output_dir,
                run=True,
            )

            self.assertIn("review_packet", result["artifacts"])
            self.assertIn("review_packet_markdown", result["artifacts"])
            self.assertIn("review_gallery", result["artifacts"])
            case = result["cases"][0]
            self.assertTrue(case["ok"])
            self.assertEqual(case["promotion_summary"]["decision"], "deferred")
            self.assertEqual(case["promotion_summary"]["red_gate_count"], 0)
            self.assertEqual(case["promotion_summary"]["yellow_gate_count"], 1)
            self.assertEqual(case["editability_review"]["decision"], "manual_review")
            self.assertEqual(case["editability_review"]["failed_components"], [])
            self.assertEqual(case["review_decision"]["suggested_decision"], "deferred")
            gate_by_id = {gate["id"]: gate for gate in case["promotion_gates"]}
            self.assertFalse(gate_by_id["current_quality_label"]["ok"])
            self.assertEqual(gate_by_id["current_quality_label"]["severity"], "yellow")
            self.assertEqual(
                gate_by_id["current_quality_label"]["reason"],
                "current quality label is red; manual review pending",
            )
            manifest = json.loads(
                (output_dir / "simple-circle" / "manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(
                manifest["promotion"]["regions"][0]["state"],
                "deferred",
            )
            self.assertEqual(
                manifest["anchors"][0]["promotion_state"],
                "deferred",
            )
            review_templates = case["artifacts"]["review_templates"]
            self.assertEqual(
                sorted(review_templates),
                ["accepted", "corrected", "deferred", "rejected"],
            )
            accepted_template = json.loads(
                Path(review_templates["accepted"]).read_text(encoding="utf-8")
            )
            self.assertEqual(accepted_template["decision"], "accepted")
            self.assertEqual(accepted_template["case_id"], "simple-circle")
            self.assertEqual(
                accepted_template["suggested_decision"],
                "deferred",
            )
            self.assertEqual(
                accepted_template["allowed_decisions"],
                ["accepted", "corrected", "rejected", "deferred"],
            )
            self.assertEqual(
                accepted_template["quality_label_policy"]["mode"],
                "sidecar_only",
            )
            self.assertFalse(
                accepted_template["quality_label_policy"][
                    "updates_current_quality_label"
                ]
            )
            self.assertTrue(
                accepted_template["template_guidance"]["accepted_for_promotion"]
            )
            self.assertFalse(
                accepted_template["template_guidance"][
                    "matches_suggested_decision"
                ]
            )
            corrected_template = json.loads(
                Path(review_templates["corrected"]).read_text(encoding="utf-8")
            )
            self.assertTrue(
                corrected_template["template_guidance"][
                    "requires_corrected_artifacts"
                ]
            )
            deferred_template = json.loads(
                Path(review_templates["deferred"]).read_text(encoding="utf-8")
            )
            self.assertEqual(deferred_template["decision"], "deferred")
            self.assertTrue(
                deferred_template["template_guidance"][
                    "matches_suggested_decision"
                ]
            )
            self.assertEqual(
                manifest["promotion"]["artifacts"]["review_templates"]["deferred"],
                review_templates["deferred"],
            )
            review_packet = json.loads(
                (output_dir / "review-packet.json").read_text(encoding="utf-8")
            )
            self.assertEqual(review_packet["case_count"], 1)
            self.assertEqual(review_packet["deferred_count"], 1)
            self.assertEqual(review_packet["manual_review_count"], 1)
            self.assertEqual(
                review_packet["issue_groups"],
                {"manual_review_pending": ["simple-circle"]},
            )
            self.assertEqual(
                review_packet["failed_gate_groups"],
                {"current_quality_label": ["simple-circle"]},
            )
            self.assertEqual(
                review_packet["cases"][0]["case_id"],
                "simple-circle",
            )
            self.assertEqual(
                review_packet["cases"][0]["suggested_review_decision"],
                "deferred",
            )
            self.assertEqual(
                review_packet["cases"][0]["quality_label_policy"]["mode"],
                "sidecar_only",
            )
            self.assertFalse(
                review_packet["cases"][0]["quality_label_policy"][
                    "updates_current_quality_label"
                ]
            )
            self.assertIn(
                "review_decision",
                review_packet["cases"][0]["artifacts"],
            )
            self.assertEqual(
                review_packet["cases"][0]["artifacts"]["review_templates"],
                review_templates,
            )
            review_packet_markdown = (
                output_dir / "review-packet.md"
            ).read_text(encoding="utf-8")
            self.assertIn("# Morphēa Review Packet", review_packet_markdown)
            self.assertIn(
                "| `manual_review_pending` | `simple-circle` |",
                review_packet_markdown,
            )
            self.assertIn(
                "| `current_quality_label` | `simple-circle` |",
                review_packet_markdown,
            )
            self.assertIn("| `simple-circle` | `deferred` |", review_packet_markdown)
            self.assertIn("- Review decision: `", review_packet_markdown)
            self.assertIn("- Decision templates: accepted=`", review_packet_markdown)
            review_gallery = (output_dir / "review-gallery.html").read_text(
                encoding="utf-8"
            )
            self.assertIn('<article class="case-card red">', review_gallery)
            self.assertIn("review queue", review_gallery)
            self.assertIn("manual_review_pending", review_gallery)
            self.assertIn("current_quality_label", review_gallery)
            self.assertIn("simple-circle/contact-sheet.png", review_gallery)
            self.assertIn(
                "simple-circle/review-templates/deferred.json",
                review_gallery,
            )

    def test_promotion_export_artifacts_partition_rejected_anchors(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "input.png"
            suite_path = Path(temp_dir) / "suite.json"
            output_dir = Path(temp_dir) / "artifacts"
            image = Image.new("RGB", (40, 24), "white")
            draw = ImageDraw.Draw(image)
            draw.ellipse((5, 5, 17, 17), fill="#c08011")
            draw.ellipse((23, 5, 35, 17), fill="#003366")
            image.save(source)
            promotion = _promotion_metadata("green")
            promotion["region_gates"] = [
                {
                    "id": "left-circle-region",
                    "gate_type": "shape_class",
                    "bounds": [4, 4, 18, 18],
                    "expected_kinds": ["circle"],
                    "min_iou": 0.3,
                    "min_count": 1,
                    "severity": "red",
                },
                {
                    "id": "right-circle-topology",
                    "gate_type": "topology",
                    "bounds": [22, 4, 36, 18],
                    "expected_kinds": ["circle"],
                    "min_iou": 0.3,
                    "min_count": 1,
                    "max_closed_anchors": 0,
                    "severity": "red",
                },
            ]
            suite_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "cases": [
                            {
                                "id": "two-circles",
                                "source": str(source),
                                "promotion": promotion,
                                "recommended_config": {
                                    "min_area": 8,
                                    "timeout_seconds": 5,
                                },
                                "expectations": [
                                    {
                                        "id": "circle-anchor",
                                        "kind": "circle",
                                        "min_count": 2,
                                    }
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            result = check_curated_suite(
                suite_path,
                output_dir=output_dir,
                run=True,
            )

            case = result["cases"][0]
            region_by_id = {
                region["id"]: region
                for region in case["promotion_regions"]
            }
            self.assertEqual(
                region_by_id["left-circle-region"]["state"],
                "promoted",
            )
            self.assertEqual(
                region_by_id["right-circle-topology"]["state"],
                "rejected",
            )
            promotion_export = json.loads(
                (output_dir / "two-circles" / "promotion-export.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(len(promotion_export["promoted_anchor_indexes"]), 1)
            self.assertEqual(len(promotion_export["rejected_anchor_indexes"]), 1)
            self.assertEqual(promotion_export["fallback_only_anchor_indexes"], [])
            self.assertEqual(
                sorted(
                    promotion_export["promoted_anchor_indexes"]
                    + promotion_export["rejected_anchor_indexes"]
                ),
                [0, 1],
            )
            self.assertEqual(
                promotion_export["anchor_state_counts"],
                {"promoted": 1, "rejected": 1},
            )
            self.assertEqual(
                promotion_export["fallback_anchor_indexes"],
                promotion_export["rejected_anchor_indexes"],
            )
            self.assertEqual(
                promotion_export["export_summary"],
                {
                    "deferred_anchor_count": 0,
                    "deferred_region_count": 0,
                    "fallback_anchor_count": 0,
                    "fallback_region_count": 0,
                    "promoted_anchor_count": 1,
                    "promoted_region_count": 1,
                    "rejected_anchor_count": 1,
                    "rejected_region_count": 1,
                },
            )
            promoted_svg = (output_dir / "two-circles" / "promoted.svg").read_text(
                encoding="utf-8"
            )
            fallback_svg = (output_dir / "two-circles" / "fallback.svg").read_text(
                encoding="utf-8"
            )
            self.assertIn('data-promotion-state="promoted"', promoted_svg)
            self.assertIn('data-promotion-regions="left-circle-region"', promoted_svg)
            self.assertIn('data-review-decision="pending"', promoted_svg)
            self.assertIn('data-promotion-state="rejected"', fallback_svg)
            self.assertIn(
                'data-promotion-regions="right-circle-topology"',
                fallback_svg,
            )
            promotion_review = (
                output_dir / "two-circles" / "promotion-review.md"
            ).read_text(encoding="utf-8")
            self.assertIn(
                "- Anchor states: `promoted`=1, `rejected`=1",
                promotion_review,
            )
            self.assertIn("## Candidate Rejections", promotion_review)
            self.assertIn(
                "| `right-circle-topology` | `anchor-0000` | `circle` | "
                "`topology_failure` | `closed_anchor_count 1 > 0` |",
                promotion_review,
            )
            editability_review = (
                output_dir / "two-circles" / "editability-review.md"
            ).read_text(encoding="utf-8")
            self.assertIn("- Decision: `rejected`", editability_review)
            self.assertIn("`gate_blocked_components`", editability_review)
            self.assertIn("| `topology_consistency` |", editability_review)
            self.assertIn("`right-circle-topology`", editability_review)
            review_decision = json.loads(
                (output_dir / "two-circles" / "review-decision.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(review_decision["suggested_decision"], "rejected")
            self.assertEqual(
                review_decision["failed_gates"][0]["id"],
                "right-circle-topology",
            )
            manifest = json.loads(
                (output_dir / "two-circles" / "manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(
                sorted(anchor["promotion_state"] for anchor in manifest["anchors"]),
                ["promoted", "rejected"],
            )
            self.assertEqual(
                manifest["editability_review"]["decision"],
                "rejected",
            )
            self.assertFalse(manifest["editability_review"]["accepted"])
            manifest_components = manifest["metrics"]["editability_v10_components"]
            self.assertEqual(
                manifest_components["topology_consistency"]["score"],
                0.0,
            )
            self.assertTrue(
                manifest_components["topology_consistency"]["gate_blocked"],
            )
            self.assertEqual(
                manifest_components["topology_consistency"]["failed_gates"],
                ["right-circle-topology"],
            )

    def test_editability_review_flags_component_regression(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "input.png"
            suite_path = root / "suite.json"
            baseline = root / "baseline.json"
            output_dir = root / "artifacts"
            image = Image.new("RGB", (24, 24), "white")
            draw = ImageDraw.Draw(image)
            draw.ellipse((5, 5, 17, 17), fill="#c08011")
            image.save(source)
            suite_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "cases": [
                            {
                                "id": "simple-circle",
                                "source": str(source),
                                "promotion": _promotion_metadata("green"),
                                "recommended_config": {
                                    "min_area": 8,
                                    "timeout_seconds": 5,
                                },
                                "expectations": [
                                    {
                                        "id": "circle-anchor",
                                        "kind": "circle",
                                        "min_count": 1,
                                    }
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            baseline.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "cases": [
                            {
                                "id": "simple-circle",
                                "editability_review": {
                                    "component_scores": {
                                        "shape_identity_confidence": 1.0,
                                        "parameter_economy": 1.0,
                                        "node_economy": 1.0,
                                        "topology_consistency": 1.0,
                                        "grouping_quality": 1.0,
                                        "fragmentation": 1.0,
                                        "raster_fidelity": 1.0,
                                        "provenance_confidence": 1.0,
                                    }
                                },
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            result = check_curated_suite(
                suite_path,
                output_dir=output_dir,
                run=True,
                baseline_snapshot=baseline,
            )

            review = result["cases"][0]["editability_review"]
            self.assertEqual(review["decision"], "manual_review")
            self.assertFalse(review["accepted"])
            self.assertEqual(review["regression_delta_status"], "failed")
            regressed = {
                item["id"]: item for item in review["regressed_components"]
            }
            self.assertIn("parameter_economy", regressed)
            self.assertLess(regressed["parameter_economy"]["delta"], -0.05)
            manifest = json.loads(
                (output_dir / "simple-circle" / "manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(
                manifest["editability_review"]["regression_delta_status"],
                "failed",
            )
            editability_review = (
                output_dir / "simple-circle" / "editability-review.md"
            ).read_text(encoding="utf-8")
            self.assertIn("- Regression delta status: `failed`", editability_review)
            self.assertIn("| `parameter_economy` |", editability_review)
            self.assertIn("`failed` |", editability_review)
            review_decision = json.loads(
                (output_dir / "simple-circle" / "review-decision.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(review_decision["suggested_decision"], "deferred")
            self.assertIn(
                "parameter_economy",
                {
                    item["id"]
                    for item in review_decision["regressed_components"]
                },
            )

    def test_render_curated_markdown_summarizes_cases_and_expectations(self):
        markdown = render_curated_markdown(
            {
                "suite": "suite.json",
                "run": True,
                "case_count": 1,
                "ok": False,
                "cases": [
                    {
                        "id": "simple-circle",
                        "status": "checked",
                        "ok": False,
                        "promotion": _promotion_metadata("red"),
                        "promotion_gates": [
                            {
                                "id": "current_quality_label",
                                "gate_type": "review_safety",
                                "ok": False,
                                "severity": "red",
                                "reason": "current quality label is red",
                                "evidence": "red",
                            },
                            {
                                "id": "circle-shape-class",
                                "gate_type": "shape_class",
                                "ok": False,
                                "severity": "red",
                                "reason": "failed expectations: circle-anchor",
                                "evidence": {
                                    "expectation_ids": ["circle-anchor"],
                                    "description": "Circle fixture must stay a circle.",
                                },
                            }
                        ],
                        "promotion_summary": {
                            "decision": "rejected",
                            "failed_gate_count": 2,
                            "red_gate_count": 2,
                            "yellow_gate_count": 0,
                        },
                        "editability_review": {
                            "decision": "rejected",
                            "accepted": False,
                            "regression_delta_status": "not_configured",
                            "reasons": [
                                "promotion_decision_rejected",
                                "gate_blocked_components",
                            ],
                            "failed_components": [
                                {
                                    "id": "shape_identity_confidence",
                                    "score": 0.0,
                                    "threshold": 0.65,
                                }
                            ],
                            "gate_blocked_components": [
                                {
                                    "id": "shape_identity_confidence",
                                    "failed_gates": ["circle-shape-class"],
                                }
                            ],
                        },
                        "review_decision": {
                            "decision": "pending",
                            "suggested_decision": "rejected",
                            "issue_tags": ["fragmentation"],
                        },
                        "anchor_count": 1,
                        "diagnostic_count": 0,
                        "anchor_kind_counts": {"circle": 1},
                        "group_kind_counts": {"primitive_anchor_reservation": 1},
                        "metrics": {
                            "editability_score": 0.75,
                            "simple_shape_ratio": 1.0,
                            "fragmentation_penalty": 0.0,
                            "editability_components": {
                                "simple_shape_ratio": 1.0,
                                "fragmentation_penalty": 0.0,
                                "diagnostic_penalty": 0.05,
                                "generic_path_penalty": 0.2,
                                "unclipped_score": 0.75,
                                "clipped_score": 0.75,
                            },
                            "editability_v10_components": {
                                "shape_identity_confidence": {"score": 1.0},
                                "parameter_economy": {"score": 0.8},
                                "node_economy": {"score": 0.9},
                                "raster_fidelity": {"score": 0.7},
                            },
                        },
                        "artifacts": {"run_dir": "runs/simple-circle"},
                        "expectations": [
                            {
                                "id": "circle-anchor",
                                "kind": "circle",
                                "actual_count": 1,
                                "min_count": 1,
                                "ok": True,
                            },
                            {
                                "id": "editable-enough",
                                "metric": "editability_score",
                                "actual_value": 0.75,
                                "min_value": 0.9,
                                "ok": False,
                            },
                        ],
                    }
                ],
            }
        )

        self.assertIn("# Morphēa Curated Check", markdown)
        self.assertIn("## Families", markdown)
        self.assertIn("| `test_fixture` | 1 | 1 | 0 | 1 | 0 |", markdown)
        self.assertIn("## Corpus Ledger", markdown)
        self.assertIn(
            "| `simple-circle` | `red` | `checked` | `test_fixture` | "
            "`circle` | `fragmentation` | `test_fixture` |",
            markdown,
        )
        self.assertIn(
            "| `simple-circle` | `rejected` | `red` | `current_quality_label`, `circle-shape-class` |",
            markdown,
        )
        self.assertIn(
            "| `simple-circle` | `rejected` | `false` | "
            "`not_configured` | "
            "`shape_identity_confidence` 0 < 0.65 | "
            "`shape_identity_confidence` via `circle-shape-class` |",
            markdown,
        )
        self.assertIn(
            "| `simple-circle` | `checked` | `red` | `false` | 1 | 0 | `editable-enough` |",
            markdown,
        )
        self.assertIn(
            "- Promotion: quality=`red`, stress=`test_fixture`, issues=`fragmentation`",
            markdown,
        )
        self.assertIn(
            "- Source provenance: `generated test fixture`",
            markdown,
        )
        self.assertIn(
            "- Expected promotion families: `circle`",
            markdown,
        )
        self.assertIn("- Licensing: `test_fixture`", markdown)
        self.assertIn(
            "- Promotion gates: decision=`rejected`, failed=`current_quality_label`, `circle-shape-class`",
            markdown,
        )
        self.assertIn(
            "- Editability review: decision=`rejected`, accepted=`false`, "
            "reasons=`promotion_decision_rejected`, `gate_blocked_components`",
            markdown,
        )
        self.assertIn(
            "- Review decision: state=`pending`, suggested=`rejected`, "
            "issues=`fragmentation`",
            markdown,
        )
        self.assertIn("## simple-circle", markdown)
        self.assertIn("`circle`=1", markdown)
        self.assertIn(
            "- Editability components: `simple_shape_ratio`=1, "
            "`fragmentation_penalty`=0, `diagnostic_penalty`=0.05, "
            "`generic_path_penalty`=0.2, `unclipped_score`=0.75, "
            "`clipped_score`=0.75",
            markdown,
        )
        self.assertIn(
            "- Editability v10 components: `shape_identity_confidence`=1, "
            "`parameter_economy`=0.8, `node_economy`=0.9",
            markdown,
        )
        self.assertIn("| `editable-enough` | `metric:editability_score` | 0.75 | >= 0.9 | `false` |", markdown)

    def test_check_curated_suite_applies_config_overrides(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "input.png"
            suite_path = Path(temp_dir) / "suite.json"
            output = Path(temp_dir) / "report.json"
            model = Path(temp_dir) / "model.json"
            image = Image.new("RGB", (24, 24), "white")
            draw = ImageDraw.Draw(image)
            draw.ellipse((5, 5, 17, 17), fill="#c08011")
            image.save(source)
            model.write_text(
                json.dumps(
                    {
                        "model_type": "centroid_primitive_classifier",
                        "feature_names": [],
                        "classes": [],
                        "centroids": {},
                    }
                ),
                encoding="utf-8",
            )
            suite_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "cases": [
                            {
                                "id": "simple-circle",
                                "source": str(source),
                                "recommended_config": {"min_area": 8},
                                "expectations": [
                                    {
                                        "id": "circle-anchor",
                                        "kind": "circle",
                                        "min_count": 1,
                                    }
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            result = check_curated_suite(
                suite_path,
                output=output,
                run=True,
                config_overrides={"classifier_model": model},
            )

            self.assertEqual(result["config_overrides"]["classifier_model"], str(model))
            self.assertEqual(
                result["cases"][0]["config"]["classifier_model"],
                str(model),
            )
            written = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(
                written["config_overrides"]["classifier_model"],
                str(model),
            )

    def test_duplicate_kind_expectations_require_distinct_curated_anchors(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "input.png"
            suite_path = Path(temp_dir) / "suite.json"
            output = Path(temp_dir) / "report.json"
            image = Image.new("RGB", (24, 24), "white")
            draw = ImageDraw.Draw(image)
            draw.ellipse((5, 5, 17, 17), fill="#c08011")
            image.save(source)
            suite_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "cases": [
                            {
                                "id": "single-circle",
                                "source": str(source),
                                "recommended_config": {
                                    "min_area": 8,
                                    "timeout_seconds": 5,
                                },
                                "expectations": [
                                    {
                                        "id": "first-circle",
                                        "kind": "circle",
                                        "min_count": 1,
                                    },
                                    {
                                        "id": "second-circle",
                                        "kind": "circle",
                                        "min_count": 1,
                                    },
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            result = check_curated_suite(suite_path, output=output, run=True)

            expectations = result["cases"][0]["expectations"]
            self.assertTrue(expectations[0]["ok"])
            self.assertFalse(expectations[1]["ok"])
            self.assertEqual(expectations[1]["actual_count"], 1)
            self.assertEqual(expectations[1]["cumulative_min_count"], 2)
            written = json.loads(output.read_text(encoding="utf-8"))
            self.assertFalse(written["ok"])

    def test_kind_set_expectation_counts_multiple_anchor_kinds(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "input.png"
            suite_path = Path(temp_dir) / "suite.json"
            output = Path(temp_dir) / "report.json"
            image = Image.new("RGB", (50, 20), "white")
            draw = ImageDraw.Draw(image)
            draw.rectangle((4, 4, 24, 6), fill="#003366")
            draw.arc((28, 4, 46, 18), start=180, end=360, fill="#c99700", width=3)
            image.save(source)
            suite_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "cases": [
                            {
                                "id": "mixed-strokes",
                                "source": str(source),
                                "recommended_config": {
                                    "min_area": 4,
                                    "timeout_seconds": 5,
                                },
                                "expectations": [
                                    {
                                        "id": "editable-strokes",
                                        "kinds": ["stroke_polyline", "stroke_path", "arc"],
                                        "min_count": 2,
                                    }
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            result = check_curated_suite(suite_path, output=output, run=True)

            expectation = result["cases"][0]["expectations"][0]
            self.assertTrue(expectation["ok"])
            self.assertEqual(
                expectation["kinds"],
                ["stroke_polyline", "stroke_path", "arc"],
            )
            self.assertGreaterEqual(expectation["actual_count"], 2)
            snapshot = render_curated_snapshot(result)
            self.assertEqual(
                snapshot["cases"][0]["expectations"][0]["kinds"],
                ["stroke_polyline", "stroke_path", "arc"],
            )
            markdown = render_curated_markdown(result)
            self.assertIn("`kinds:stroke_polyline,stroke_path,arc`", markdown)

    def test_region_promotion_gates_check_anchor_kind_inside_bounds(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "input.png"
            suite_path = Path(temp_dir) / "suite.json"
            output = Path(temp_dir) / "report.json"
            image = Image.new("RGB", (24, 24), "white")
            draw = ImageDraw.Draw(image)
            draw.ellipse((5, 5, 17, 17), fill="#c08011")
            image.save(source)
            promotion = _promotion_metadata("green")
            promotion["region_gates"] = [
                {
                    "id": "circle-region",
                    "gate_type": "shape_class",
                    "bounds": [4, 4, 18, 18],
                    "expected_kinds": ["circle"],
                    "min_iou": 0.3,
                    "min_count": 1,
                    "severity": "red",
                },
                {
                    "id": "empty-region",
                    "gate_type": "shape_class",
                    "bounds": [0, 0, 4, 4],
                    "expected_kinds": ["circle"],
                    "min_iou": 0.1,
                    "min_count": 1,
                    "severity": "red",
                },
                {
                    "id": "wide-circle-region",
                    "gate_type": "shape_class",
                    "bounds": [0, 0, 24, 24],
                    "expected_kinds": ["circle"],
                    "min_anchor_coverage": 0.8,
                    "min_count": 1,
                    "severity": "red",
                },
                {
                    "id": "circle-topology",
                    "gate_type": "topology",
                    "bounds": [4, 4, 18, 18],
                    "expected_kinds": ["circle"],
                    "min_iou": 0.3,
                    "min_count": 1,
                    "max_closed_anchors": 0,
                    "severity": "red",
                },
                {
                    "id": "forbid-circle-region",
                    "gate_type": "shape_class",
                    "bounds": [4, 4, 18, 18],
                    "expected_kinds": ["circle"],
                    "forbidden_kinds": ["circle"],
                    "min_iou": 0.3,
                    "min_count": 1,
                    "severity": "red",
                },
            ]
            suite_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "cases": [
                            {
                                "id": "single-circle",
                                "source": str(source),
                                "promotion": promotion,
                                "recommended_config": {
                                    "min_area": 8,
                                    "timeout_seconds": 5,
                                },
                                "expectations": [
                                    {
                                        "id": "circle-anchor",
                                        "kind": "circle",
                                        "min_count": 1,
                                    }
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            result = check_curated_suite(suite_path, output=output, run=True)

            gate_by_id = {
                gate["id"]: gate for gate in result["cases"][0]["promotion_gates"]
            }
            region_by_id = {
                region["id"]: region
                for region in result["cases"][0]["promotion_regions"]
            }
            self.assertTrue(gate_by_id["circle-region"]["ok"])
            self.assertEqual(
                gate_by_id["circle-region"]["evidence"]["matching_count"],
                1,
            )
            self.assertEqual(
                gate_by_id["circle-region"]["evidence"]["candidate_rejections"],
                [],
            )
            self.assertTrue(gate_by_id["wide-circle-region"]["ok"])
            self.assertEqual(
                gate_by_id["wide-circle-region"]["evidence"]["matching_count"],
                1,
            )
            self.assertEqual(
                gate_by_id["wide-circle-region"]["evidence"]["min_anchor_coverage"],
                0.8,
            )
            self.assertEqual(
                gate_by_id["wide-circle-region"]["evidence"]["min_iou"],
                0.0,
            )
            self.assertGreaterEqual(
                gate_by_id["wide-circle-region"]["evidence"]["selected_anchors"][0][
                    "anchor_coverage"
                ],
                0.8,
            )
            self.assertEqual(region_by_id["circle-region"]["state"], "promoted")
            self.assertEqual(
                region_by_id["circle-region"]["selected_anchor_indexes"],
                [0],
            )
            self.assertEqual(
                region_by_id["circle-region"]["layer_roles"],
                ["filled_primitives"],
            )
            self.assertEqual(region_by_id["circle-region"]["region_layer_count"], 1)
            self.assertEqual(
                region_by_id["circle-region"]["structural_layer_roles"],
                ["filled_primitives"],
            )
            self.assertEqual(
                region_by_id["circle-region"]["structural_layer_count"],
                1,
            )
            self.assertEqual(
                region_by_id["circle-region"]["selected_anchor_kind_counts"],
                {"circle": 1},
            )
            self.assertEqual(
                region_by_id["circle-region"]["selected_simple_anchor_count"],
                1,
            )
            self.assertEqual(
                region_by_id["circle-region"]["selected_generic_path_anchor_count"],
                0,
            )
            self.assertEqual(
                region_by_id["wide-circle-region"]["selected_anchor_indexes"],
                [0],
            )
            topology = gate_by_id["circle-region"]["evidence"]["topology_summary"]
            self.assertEqual(topology["closed_anchor_count"], 1)
            self.assertEqual(topology["open_anchor_count"], 0)
            self.assertFalse(gate_by_id["empty-region"]["ok"])
            self.assertEqual(region_by_id["empty-region"]["state"], "rejected")
            self.assertIn(
                "matching anchors in region: 0 < 1",
                gate_by_id["empty-region"]["reason"],
            )
            self.assertFalse(gate_by_id["circle-topology"]["ok"])
            self.assertEqual(region_by_id["circle-topology"]["state"], "rejected")
            self.assertIn(
                "closed_anchor_count 1 > 0",
                gate_by_id["circle-topology"]["reason"],
            )
            topology_rejection = gate_by_id["circle-topology"]["evidence"][
                "candidate_rejections"
            ][0]
            self.assertEqual(topology_rejection["id"], "anchor-0000")
            self.assertEqual(topology_rejection["kind"], "circle")
            self.assertEqual(topology_rejection["reasons"], ["topology_failure"])
            self.assertEqual(
                topology_rejection["topology_failures"],
                ["closed_anchor_count 1 > 0"],
            )
            self.assertFalse(gate_by_id["forbid-circle-region"]["ok"])
            forbidden_rejection = gate_by_id["forbid-circle-region"]["evidence"][
                "candidate_rejections"
            ][0]
            self.assertEqual(forbidden_rejection["id"], "anchor-0000")
            self.assertEqual(forbidden_rejection["reasons"], ["forbidden_kind"])
            components = result["cases"][0]["metrics"]["editability_v10_components"]
            self.assertEqual(
                components["shape_identity_confidence"]["score"],
                0.0,
            )
            self.assertEqual(
                components["shape_identity_confidence"]["failed_gates"],
                ["empty-region", "forbid-circle-region"],
            )
            self.assertEqual(
                components["topology_consistency"]["score"],
                0.0,
            )
            self.assertEqual(
                components["topology_consistency"]["failed_gates"],
                ["circle-topology"],
            )
            self.assertEqual(
                result["cases"][0]["promotion_summary"]["decision"],
                "rejected",
            )
            self.assertEqual(
                result["cases"][0]["editability_review"]["decision"],
                "rejected",
            )
            self.assertIn(
                "gate_blocked_components",
                result["cases"][0]["editability_review"]["reasons"],
            )
            markdown = render_curated_markdown(result)
            self.assertIn("## Region Truth", markdown)
            self.assertIn(
                "| `single-circle` | `circle-region` | `promoted` | "
                "`shape_class` | `4,4,18,18` | kinds=`circle`, "
                "min_iou=0.3 | matching=1, selected=1, forbidden=0, rejected=0 | "
                "layers=1, structural=1, roles=`filled_primitives`, "
                "kinds=`circle`=1 | "
                "closed=1, open=0, holes=0, cutouts=0, failures=n/a |",
                markdown,
            )
            self.assertIn(
                "| `single-circle` | `empty-region` | `rejected` | "
                "`shape_class` | `0,0,4,4` | kinds=`circle`, "
                "min_iou=0.1 | matching=0, selected=0, forbidden=0, rejected=0 | "
                "layers=0, structural=0, roles=`none`, kinds=`none` |",
                markdown,
            )
            self.assertIn(
                "| `single-circle` | `circle-topology` | `rejected` | "
                "`topology` | `4,4,18,18` | kinds=`circle`, min_iou=0.3 | "
                "matching=1, selected=1, forbidden=0, rejected=1 | "
                "layers=1, structural=1, roles=`filled_primitives`, "
                "kinds=`circle`=1 | "
                "closed=1, open=0, holes=0, cutouts=0, "
                "failures=`closed_anchor_count 1 > 0` |",
                markdown,
            )

    def test_structure_threshold_can_ignore_non_structural_layer_roles(self):
        gate = _structure_threshold_promotion_gate(
            {
                "status": "checked",
                "layer_count": 4,
                "layer_anchor_counts": {
                    "cutout_overlays": 12,
                    "filled_primitives": 21,
                    "generic_paths": 13,
                    "strokes": 16,
                },
                "metrics": {"fragmentation_penalty": 0.4},
            },
            {
                "stress_family": "generated_illustration",
                "structure_thresholds": {
                    "max_fragmentation_penalty": 0.6,
                    "max_structural_layer_count": 3,
                    "non_structural_layer_roles": ["cutout_overlays"],
                    "severity": "red",
                    "description": "Cutout overlays should not count as core layer depth.",
                },
            },
        )

        self.assertIsNotNone(gate)
        self.assertTrue(gate["ok"])
        self.assertEqual(
            gate["evidence"]["actual"],
            {
                "fragmentation_penalty": 0.4,
                "structural_layer_count": 3,
            },
        )
        self.assertEqual(
            gate["evidence"]["non_structural_layer_roles"],
            ["cutout_overlays"],
        )

    def test_promotion_region_results_report_region_layer_depth(self):
        regions = _promotion_region_results(
            {
                "id": "layered-case",
                "status": "checked",
                "promotion": {
                    "current_quality_label": "green",
                    "structure_thresholds": {
                        "non_structural_layer_roles": ["cutout_overlays"]
                    },
                    "region_gates": [
                        {
                            "id": "layered-region",
                            "gate_type": "shape_class",
                            "bounds": [0, 0, 10, 10],
                            "expected_kinds": ["circle"],
                        }
                    ],
                },
                "promotion_gates": [
                    {
                        "id": "layered-region",
                        "gate_type": "shape_class",
                        "ok": True,
                        "severity": "red",
                        "reason": "matching anchors in region: 2",
                        "evidence": {
                            "selected_anchors": [
                                {"id": "anchor-0000"},
                                {"id": "anchor-0002"},
                            ]
                        },
                    }
                ],
            },
            manifest={
                "anchors": [
                    {"kind": "circle", "layer": "filled_primitives"},
                    {"layer": "strokes"},
                    {"kind": "stroke_path", "layer": "cutout_overlays"},
                ],
                "layers": [
                    {
                        "name": "filled_primitives",
                        "anchor_indexes": [0],
                        "anchor_count": 1,
                    },
                    {
                        "name": "cutout_overlays",
                        "anchor_indexes": [2],
                        "anchor_count": 1,
                    },
                ],
            },
        )

        self.assertEqual(regions[0]["state"], "promoted")
        self.assertEqual(regions[0]["selected_anchor_indexes"], [0, 2])
        self.assertEqual(
            regions[0]["layer_role_counts"],
            {"cutout_overlays": 1, "filled_primitives": 1},
        )
        self.assertEqual(
            regions[0]["layer_roles"],
            ["cutout_overlays", "filled_primitives"],
        )
        self.assertEqual(regions[0]["region_layer_count"], 2)
        self.assertEqual(regions[0]["structural_layer_roles"], ["filled_primitives"])
        self.assertEqual(regions[0]["structural_layer_count"], 1)
        self.assertEqual(regions[0]["non_structural_layer_roles"], ["cutout_overlays"])
        self.assertEqual(
            regions[0]["selected_anchor_kind_counts"],
            {"circle": 1, "stroke_path": 1},
        )
        self.assertEqual(regions[0]["selected_simple_anchor_count"], 2)
        self.assertEqual(regions[0]["selected_stroke_anchor_count"], 1)
        self.assertEqual(regions[0]["selected_generic_path_anchor_count"], 0)

    def test_group_promotion_gates_check_group_membership(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "input.png"
            suite_path = Path(temp_dir) / "suite.json"
            output_dir = Path(temp_dir) / "artifacts"
            image = Image.new("RGB", (24, 24), "white")
            draw = ImageDraw.Draw(image)
            draw.ellipse((5, 5, 17, 17), fill="#c08011")
            image.save(source)
            promotion = _promotion_metadata("green")
            promotion["group_gates"] = [
                {
                    "id": "reservation-group",
                    "gate_type": "grouping",
                    "expected_group_kinds": ["primitive_anchor_reservation"],
                    "min_count": 1,
                    "min_member_count": 1,
                    "severity": "red",
                },
                {
                    "id": "missing-grid-group",
                    "gate_type": "grouping",
                    "expected_group_kinds": ["perspective_grid"],
                    "min_count": 1,
                    "min_member_count": 4,
                    "severity": "red",
                },
            ]
            suite_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "cases": [
                            {
                                "id": "single-circle",
                                "source": str(source),
                                "promotion": promotion,
                                "recommended_config": {
                                    "min_area": 8,
                                    "timeout_seconds": 5,
                                },
                                "expectations": [
                                    {
                                        "id": "circle-anchor",
                                        "kind": "circle",
                                        "min_count": 1,
                                    }
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            result = check_curated_suite(
                suite_path,
                output_dir=output_dir,
                run=True,
            )

            gate_by_id = {
                gate["id"]: gate for gate in result["cases"][0]["promotion_gates"]
            }
            self.assertTrue(gate_by_id["reservation-group"]["ok"])
            self.assertEqual(
                gate_by_id["reservation-group"]["evidence"]["best_member_count"],
                1,
            )
            self.assertFalse(gate_by_id["missing-grid-group"]["ok"])
            self.assertIn(
                "group_count 0 < 1",
                gate_by_id["missing-grid-group"]["reason"],
            )

    def test_load_curated_suite_rejects_metric_expectation_without_bounds(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            suite_path = Path(temp_dir) / "suite.json"
            suite_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "cases": [
                            {
                                "id": "bad-metric",
                                "source": "/tmp/simple-circle.png",
                                "expectations": [
                                    {
                                        "id": "editable-enough",
                                        "metric": "editability_score",
                                    }
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "min_value or max_value"):
                load_curated_suite(suite_path)

    def test_load_curated_suite_rejects_empty_kind_set_expectation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            suite_path = Path(temp_dir) / "suite.json"
            suite_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "cases": [
                            {
                                "id": "bad-kinds",
                                "source": "/tmp/simple-circle.png",
                                "expectations": [
                                    {
                                        "id": "editable-strokes",
                                        "kinds": [],
                                        "min_count": 1,
                                    }
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "kind, kinds, group_kind, or metric"):
                load_curated_suite(suite_path)

    def test_load_curated_suite_rejects_invalid_promotion_label(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            suite_path = Path(temp_dir) / "suite.json"
            suite_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "cases": [
                            {
                                "id": "simple-circle",
                                "source": "/tmp/simple-circle.png",
                                "promotion": _promotion_metadata("blue"),
                                "expectations": [
                                    {
                                        "id": "circle-anchor",
                                        "kind": "circle",
                                        "min_count": 1,
                                    }
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "current_quality_label"):
                load_curated_suite(suite_path)

    def test_load_curated_suite_rejects_invalid_quality_label_review_policy(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            suite_path = Path(temp_dir) / "suite.json"
            metadata = _promotion_metadata("red")
            metadata["quality_label_review_policy"] = "auto_accept"
            suite_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "cases": [
                            {
                                "id": "simple-circle",
                                "source": "/tmp/simple-circle.png",
                                "promotion": metadata,
                                "expectations": [
                                    {
                                        "id": "circle-anchor",
                                        "kind": "circle",
                                        "min_count": 1,
                                    }
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "quality_label_review_policy"):
                load_curated_suite(suite_path)

    def test_load_curated_suite_rejects_unknown_hard_gate_expectation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            suite_path = Path(temp_dir) / "suite.json"
            metadata = _promotion_metadata("green")
            metadata["hard_gates"] = [
                {
                    "id": "missing-reference",
                    "gate_type": "shape_class",
                    "expectation_ids": ["not-an-expectation"],
                    "severity": "red",
                }
            ]
            suite_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "cases": [
                            {
                                "id": "simple-circle",
                                "source": "/tmp/simple-circle.png",
                                "promotion": metadata,
                                "expectations": [
                                    {
                                        "id": "circle-anchor",
                                        "kind": "circle",
                                        "min_count": 1,
                                    }
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "unknown expectation id"):
                load_curated_suite(suite_path)

    def test_load_curated_suite_rejects_invalid_region_topology_limit(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            suite_path = Path(temp_dir) / "suite.json"
            metadata = _promotion_metadata("green")
            metadata["region_gates"] = [
                {
                    "id": "bad-topology-limit",
                    "gate_type": "topology",
                    "bounds": [0, 0, 10, 10],
                    "expected_kinds": ["circle"],
                    "max_closed_anchors": -1,
                }
            ]
            suite_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "cases": [
                            {
                                "id": "simple-circle",
                                "source": "/tmp/simple-circle.png",
                                "promotion": metadata,
                                "expectations": [
                                    {
                                        "id": "circle-anchor",
                                        "kind": "circle",
                                        "min_count": 1,
                                    }
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "max_closed_anchors"):
                load_curated_suite(suite_path)

    def test_load_curated_suite_rejects_invalid_region_anchor_coverage(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            suite_path = Path(temp_dir) / "suite.json"
            metadata = _promotion_metadata("green")
            metadata["region_gates"] = [
                {
                    "id": "bad-anchor-coverage",
                    "gate_type": "shape_class",
                    "bounds": [0, 0, 10, 10],
                    "expected_kinds": ["circle"],
                    "min_anchor_coverage": 1.2,
                }
            ]
            suite_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "cases": [
                            {
                                "id": "simple-circle",
                                "source": "/tmp/simple-circle.png",
                                "promotion": metadata,
                                "expectations": [
                                    {
                                        "id": "circle-anchor",
                                        "kind": "circle",
                                        "min_count": 1,
                                    }
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "min_anchor_coverage"):
                load_curated_suite(suite_path)

    def test_load_curated_suite_rejects_invalid_visual_thresholds(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            suite_path = Path(temp_dir) / "suite.json"
            metadata = _promotion_metadata("green")
            metadata["visual_thresholds"] = {
                "family": "test_fixture",
                "max_raster_l1_error": -0.1,
            }
            suite_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "cases": [
                            {
                                "id": "simple-circle",
                                "source": "/tmp/simple-circle.png",
                                "promotion": metadata,
                                "expectations": [
                                    {
                                        "id": "circle-anchor",
                                        "kind": "circle",
                                        "min_count": 1,
                                    }
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "max_raster_l1_error"):
                load_curated_suite(suite_path)

    def test_load_curated_suite_rejects_invalid_group_gate(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            suite_path = Path(temp_dir) / "suite.json"
            metadata = _promotion_metadata("green")
            metadata["group_gates"] = [
                {
                    "id": "bad-group",
                    "gate_type": "grouping",
                    "expected_group_kinds": [],
                }
            ]
            suite_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "cases": [
                            {
                                "id": "simple-circle",
                                "source": "/tmp/simple-circle.png",
                                "promotion": metadata,
                                "expectations": [
                                    {
                                        "id": "circle-anchor",
                                        "kind": "circle",
                                        "min_count": 1,
                                    }
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "expected_group_kinds"):
                load_curated_suite(suite_path)

    def test_load_curated_suite_rejects_invalid_structure_thresholds(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            suite_path = Path(temp_dir) / "suite.json"
            metadata = _promotion_metadata("green")
            metadata["structure_thresholds"] = {
                "max_layer_count": -1,
            }
            suite_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "cases": [
                            {
                                "id": "simple-circle",
                                "source": "/tmp/simple-circle.png",
                                "promotion": metadata,
                                "expectations": [
                                    {
                                        "id": "circle-anchor",
                                        "kind": "circle",
                                        "min_count": 1,
                                    }
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "max_layer_count"):
                load_curated_suite(suite_path)

    def test_load_curated_suite_rejects_invalid_non_structural_layer_roles(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            suite_path = Path(temp_dir) / "suite.json"
            metadata = _promotion_metadata("green")
            metadata["structure_thresholds"] = {
                "max_structural_layer_count": 3,
                "non_structural_layer_roles": ["cutout_overlays", ""],
            }
            suite_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "cases": [
                            {
                                "id": "simple-circle",
                                "source": "/tmp/simple-circle.png",
                                "promotion": metadata,
                                "expectations": [
                                    {
                                        "id": "circle-anchor",
                                        "kind": "circle",
                                        "min_count": 1,
                                    }
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "non_structural_layer_roles"):
                load_curated_suite(suite_path)

    def test_render_curated_snapshot_sorts_cases_and_expectations(self):
        snapshot = render_curated_snapshot(
            {
                "suite": "suite.json",
                "case_count": 2,
                "ok": True,
                "cases": [
                    {
                        "id": "z-case",
                        "status": "checked",
                        "ok": True,
                        "source_exists": True,
                        "promotion_gates": [
                            {
                                "id": "source_available",
                                "gate_type": "provenance",
                                "ok": True,
                                "severity": "red",
                                "reason": "source image is available",
                                "evidence": "/tmp/local-source.png",
                            },
                            {
                                "id": "visual_contact_sheet",
                                "gate_type": "visual_fidelity",
                                "ok": True,
                                "severity": "yellow",
                                "reason": "contact sheet available",
                                "evidence": "/tmp/case/contact-sheet.png",
                            },
                        ],
                        "expectations": [
                            {
                                "id": "z-exp",
                                "ok": True,
                                "actual_count": 2,
                                "min_count": 1,
                            },
                            {
                                "id": "a-exp",
                                "ok": True,
                                "actual_count": 1,
                                "min_count": 1,
                            },
                            {
                                "id": "metric-exp",
                                "ok": True,
                                "metric": "editability_score",
                                "actual_value": 0.5,
                                "min_value": 0.25,
                            },
                        ],
                    },
                    {
                        "id": "a-case",
                        "status": "missing_source",
                        "ok": False,
                        "source_exists": False,
                        "expectations": [],
                    },
                ],
            }
        )

        self.assertEqual(
            [case["id"] for case in snapshot["cases"]],
            ["a-case", "z-case"],
        )
        self.assertEqual(
            [item["id"] for item in snapshot["cases"][1]["expectations"]],
            ["a-exp", "metric-exp", "z-exp"],
        )
        self.assertEqual(
            snapshot["cases"][1]["expectations"][1]["actual_value"],
            0.5,
        )
        gates = {
            gate["id"]: gate
            for gate in snapshot["cases"][1]["promotion_gates"]
        }
        self.assertEqual(
            gates["source_available"]["evidence"],
            {"source_exists": True},
        )
        self.assertEqual(
            gates["visual_contact_sheet"]["evidence"],
            {"contact_sheet_path_recorded": True},
        )

    def test_curated_check_cli_writes_report(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "missing.png"
            suite_path = Path(temp_dir) / "suite.json"
            output = Path(temp_dir) / "report.json"
            snapshot = Path(temp_dir) / "snapshot.json"
            markdown = Path(temp_dir) / "report.md"
            suite_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "cases": [
                            {
                                "id": "missing-image",
                                "source": str(source),
                                "expectations": [
                                    {
                                        "id": "circle-anchor",
                                        "kind": "circle",
                                        "min_count": 1,
                                    }
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with redirect_stdout(StringIO()):
                main(
                    [
                        "curated-check",
                        str(suite_path),
                        "-o",
                        str(output),
                        "--snapshot",
                        str(snapshot),
                        "--markdown",
                        str(markdown),
                    ]
                )

            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertTrue(report["ok"])
            self.assertEqual(report["cases"][0]["status"], "missing_source")
            snapshot_report = json.loads(snapshot.read_text(encoding="utf-8"))
            self.assertEqual(snapshot_report["cases"][0]["status"], "missing_source")
            self.assertIn(
                "# Morphēa Curated Check",
                markdown.read_text(encoding="utf-8"),
            )

    def test_missing_source_promotion_case_is_deferred(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "missing.png"
            suite = root / "suite.json"
            suite.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "cases": [
                            {
                                "id": "missing-promotion-image",
                                "source": str(source),
                                "promotion": {
                                    **_promotion_metadata("red"),
                                    "current_status": "missing_source",
                                    "current_issues": ["missing_local_source"],
                                },
                                "expectations": [
                                    {
                                        "id": "circle-anchor",
                                        "kind": "circle",
                                        "min_count": 1,
                                    }
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            result = check_curated_suite(suite, run=True)

            case = result["cases"][0]
            self.assertFalse(case["ok"])
            self.assertEqual(case["status"], "missing_source")
            self.assertEqual(case["promotion_summary"]["decision"], "deferred")
            self.assertEqual(
                case["promotion_summary"]["deferred_reason"],
                "missing_source",
            )
            self.assertGreater(case["promotion_summary"]["red_gate_count"], 0)
            self.assertEqual(
                case["review_decision"]["suggested_decision"],
                "deferred",
            )

    def test_curated_check_cli_accepts_config_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "missing.png"
            suite_path = root / "suite.json"
            output = root / "report.json"
            snapshot = root / "snapshot.json"
            baseline = root / "baseline.json"
            markdown = root / "report.md"
            config = root / "curated-check.json"
            suite_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "cases": [
                            {
                                "id": "missing-image",
                                "source": str(source),
                                "expectations": [
                                    {
                                        "id": "circle-anchor",
                                        "kind": "circle",
                                        "min_count": 1,
                                    }
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            baseline.write_text(
                json.dumps({"schema_version": 1, "cases": []}),
                encoding="utf-8",
            )
            config.write_text(
                json.dumps(
                    {
                        "suite": str(suite_path),
                        "output": str(output),
                        "snapshot": str(snapshot),
                        "baseline_snapshot": str(baseline),
                        "markdown": str(markdown),
                    }
                ),
                encoding="utf-8",
            )

            with redirect_stdout(StringIO()):
                main(["curated-check", "--config", str(config)])

            self.assertEqual(
                json.loads(output.read_text(encoding="utf-8"))["baseline_snapshot"],
                str(baseline),
            )
            self.assertEqual(
                json.loads(output.read_text(encoding="utf-8"))["case_count"],
                1,
            )
            self.assertTrue(snapshot.exists())
            self.assertIn("# Morphēa Curated Check", markdown.read_text(encoding="utf-8"))


class CuratedAssetsSuiteTests(unittest.TestCase):
    def test_checked_in_curated_suite_passes_with_run(self):
        """Hand-made real-image cases live in assets/curated/suite.json."""

        from morphea.curated import check_curated_suite

        report = check_curated_suite(
            Path("assets/curated/suite.json"),
            run=True,
        )

        self.assertTrue(
            report["ok"],
            [
                (case["id"], case.get("expectations"))
                for case in report["cases"]
                if not case["ok"]
            ],
        )


if __name__ == "__main__":
    unittest.main()
