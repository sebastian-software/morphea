import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from PIL import Image, ImageDraw

from morphea.cli import main
from morphea.curated import (
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
            self.assertTrue((output_dir / "simple-circle" / "contact-sheet.png").exists())
            self.assertTrue((output_dir / "simple-circle" / "input" / "input.png").exists())
            with Image.open(output_dir / "simple-circle" / "contact-sheet.png") as sheet:
                self.assertEqual(sheet.size, (1636, 268))
            promoted_svg = (output_dir / "simple-circle" / "promoted.svg").read_text(
                encoding="utf-8"
            )
            fallback_svg = (output_dir / "simple-circle" / "fallback.svg").read_text(
                encoding="utf-8"
            )
            self.assertIn("<circle", promoted_svg)
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
            report = json.loads(output.read_text())
            self.assertEqual(report["case_count"], 1)
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
            self.assertEqual(
                report["cases"][0]["promotion_summary"]["decision"],
                "promoted",
            )
            self.assertFalse(
                [
                    gate
                    for gate in report["cases"][0]["promotion_gates"]
                    if not gate["ok"]
                ]
            )
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
            promotion_review = (
                output_dir / "two-circles" / "promotion-review.md"
            ).read_text(encoding="utf-8")
            self.assertIn(
                "- Anchor states: `promoted`=1, `rejected`=1",
                promotion_review,
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
        self.assertIn(
            "| `simple-circle` | `rejected` | `red` | `current_quality_label`, `circle-shape-class` |",
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
            "- Promotion gates: decision=`rejected`, failed=`current_quality_label`, `circle-shape-class`",
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
                    "id": "circle-topology",
                    "gate_type": "topology",
                    "bounds": [4, 4, 18, 18],
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
            self.assertEqual(region_by_id["circle-region"]["state"], "promoted")
            self.assertEqual(
                region_by_id["circle-region"]["selected_anchor_indexes"],
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
            components = result["cases"][0]["metrics"]["editability_v10_components"]
            self.assertEqual(
                components["shape_identity_confidence"]["score"],
                0.0,
            )
            self.assertEqual(
                components["shape_identity_confidence"]["failed_gates"],
                ["empty-region"],
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

    def test_curated_check_cli_accepts_config_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "missing.png"
            suite_path = root / "suite.json"
            output = root / "report.json"
            snapshot = root / "snapshot.json"
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
            config.write_text(
                json.dumps(
                    {
                        "suite": str(suite_path),
                        "output": str(output),
                        "snapshot": str(snapshot),
                        "markdown": str(markdown),
                    }
                ),
                encoding="utf-8",
            )

            with redirect_stdout(StringIO()):
                main(["curated-check", "--config", str(config)])

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
