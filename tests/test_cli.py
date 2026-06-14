import tempfile
import unittest
import json
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageDraw

from morphea.cli import main
from morphea.dataset import generate_synthetic_dataset
from morphea.classifier import train_centroid_classifier


class CliTests(unittest.TestCase):
    def test_vectorize_writes_svg_for_flat_color_image(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "input.png"
            output_path = Path(temp_dir) / "output.svg"
            manifest_path = Path(temp_dir) / "output.json"
            image = Image.new("RGB", (24, 16), "white")
            draw = ImageDraw.Draw(image)
            draw.ellipse((2, 2, 10, 10), fill="#dd2222")
            draw.rectangle((13, 5, 22, 6), fill="#003366")
            image.save(input_path)

            with redirect_stdout(StringIO()):
                main(["vectorize", str(input_path), "-o", str(output_path)])

            svg = output_path.read_text(encoding="utf-8")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertIn("<svg", svg)
            self.assertIn("<circle ", svg)
            self.assertIn("<path ", svg)
            self.assertIn('fill="#dd2222"', svg)
            self.assertIn('stroke="#003366"', svg)
            self.assertEqual(manifest["anchor_count"], 2)
            self.assertEqual(
                [anchor["kind"] for anchor in manifest["anchors"]],
                ["stroke_polyline", "circle"],
            )

    def test_promotion_export_cli_filters_manifest_anchors(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest = root / "manifest.json"
            promoted_svg = root / "promoted.svg"
            fallback_svg = root / "fallback.svg"
            output = root / "promotion-export.json"
            markdown = root / "promotion-export.md"
            manifest.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "width": 32,
                        "height": 24,
                        "anchors": [
                            {
                                "id": "anchor-0000",
                                "kind": "circle",
                                "color": "#dd2222",
                                "promotion_state": "promoted",
                                "circle": {"cx": 8, "cy": 8, "r": 4},
                            },
                            {
                                "id": "anchor-0001",
                                "kind": "circle",
                                "color": "#003366",
                                "promotion_state": "fallback",
                                "circle": {"cx": 16, "cy": 16, "r": 3},
                            },
                            {
                                "id": "anchor-0002",
                                "kind": "circle",
                                "color": "#229944",
                                "promotion_state": "rejected",
                                "circle": {"cx": 24, "cy": 8, "r": 3},
                            },
                        ],
                        "promotion": {
                            "regions": [
                                {
                                    "id": "circle-region",
                                    "state": "promoted",
                                    "selected_anchor_indexes": [0],
                                },
                                {
                                    "id": "failed-region",
                                    "state": "rejected",
                                    "selected_anchor_indexes": [2],
                                    "gate_id": "failed-gate",
                                    "reason": "failed topology gate",
                                }
                            ]
                        },
                        "review_decision_applied": {
                            "case_id": "case-a",
                            "decision": "accepted",
                            "source_review_decision": "review-decision.json",
                        },
                    }
                ),
                encoding="utf-8",
            )

            with redirect_stdout(StringIO()) as stdout:
                main(
                    [
                        "promotion-export",
                        str(manifest),
                        "--promoted-svg",
                        str(promoted_svg),
                        "--fallback-svg",
                        str(fallback_svg),
                        "-o",
                        str(output),
                        "--markdown",
                        str(markdown),
                    ]
                )

            self.assertIn("promoted=1", stdout.getvalue())
            promoted_text = promoted_svg.read_text(encoding="utf-8")
            fallback_text = fallback_svg.read_text(encoding="utf-8")
            self.assertIn("#dd2222", promoted_text)
            self.assertNotIn("#003366", promoted_text)
            self.assertIn('id="morphea-anchor-0000-anchor-0000"', promoted_text)
            self.assertIn('data-morphea-anchor-id="anchor-0000"', promoted_text)
            self.assertIn('data-anchor-index="0"', promoted_text)
            self.assertIn('data-promotion-state="promoted"', promoted_text)
            self.assertIn('data-promotion-regions="circle-region"', promoted_text)
            self.assertIn('data-review-decision="accepted"', promoted_text)
            self.assertIn('data-review-case-id="case-a"', promoted_text)
            self.assertIn("#003366", fallback_text)
            self.assertIn("#229944", fallback_text)
            self.assertIn('data-promotion-state="rejected"', fallback_text)
            self.assertIn('data-promotion-regions="failed-region"', fallback_text)
            result = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(result["promoted_anchor_indexes"], [0])
            self.assertEqual(result["fallback_anchor_indexes"], [1, 2])
            self.assertEqual(result["fallback_only_anchor_indexes"], [1])
            self.assertEqual(result["rejected_anchor_indexes"], [2])
            self.assertEqual(
                result["anchor_state_counts"],
                {"fallback": 1, "promoted": 1, "rejected": 1},
            )
            self.assertEqual(
                result["export_summary"],
                {
                    "deferred_anchor_count": 0,
                    "deferred_region_count": 0,
                    "fallback_anchor_count": 1,
                    "fallback_region_count": 0,
                    "promoted_anchor_count": 1,
                    "promoted_region_count": 1,
                    "rejected_anchor_count": 1,
                    "rejected_region_count": 1,
                },
            )
            self.assertEqual(result["regions"][1]["reason"], "failed topology gate")
            report = markdown.read_text(encoding="utf-8")
            self.assertIn("# Morphēa Promotion Export", report)
            self.assertIn("| `promoted` | 1 | 1 |", report)
            self.assertIn("| `fallback` | `1` | `none` | `n/a` |", report)
            self.assertIn(
                "| `rejected` | `2` | `failed-region` | failed topology gate |",
                report,
            )

    def test_promotion_apply_review_cli_applies_terminal_decision(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            review_decision = root / "review-decision.json"
            output = root / "applied-review.json"
            markdown = root / "applied-review.md"
            manifest = root / "manifest.json"
            review_decision.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "case_id": "real-case",
                        "decision": "corrected",
                        "suggested_decision": "deferred",
                        "reviewer": "qa",
                        "reason": "corrected topology",
                        "correction_notes": "merged duplicate control",
                        "corrected_artifacts": ["corrected.svg"],
                        "issue_tags": ["topology_mismatch"],
                        "source_decisions": {
                            "editability_decision": "manual_review",
                        },
                        "review_artifacts": {
                            "promotion_regions": "promotion-regions.json",
                            "promotion_review": "promotion-review.md",
                            "editability_review": "editability-review.md",
                        },
                        "failed_gates": [
                            {
                                "id": "radio-control-region-topology",
                                "gate_type": "topology",
                                "severity": "red",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            manifest.write_text(
                json.dumps({"schema_version": 1, "promotion": {}}),
                encoding="utf-8",
            )

            with redirect_stdout(StringIO()) as stdout:
                main(
                    [
                        "promotion-apply-review",
                        str(review_decision),
                        "-o",
                        str(output),
                        "--markdown",
                        str(markdown),
                        "--manifest",
                        str(manifest),
                    ]
                )

            self.assertIn("decision=corrected", stdout.getvalue())
            result = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(result["decision"], "corrected")
            self.assertTrue(result["accepted_for_promotion"])
            self.assertFalse(result["matches_suggestion"])
            self.assertEqual(result["issue_tags"], ["topology_mismatch"])
            self.assertEqual(
                result["failed_gates"][0]["id"],
                "radio-control-region-topology",
            )
            self.assertEqual(
                result["review_artifacts"]["promotion_review"],
                "promotion-review.md",
            )
            self.assertEqual(result["quality_label_policy"]["mode"], "sidecar_only")
            self.assertFalse(
                result["quality_label_policy"]["updates_current_quality_label"]
            )
            manifest_data = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertEqual(
                manifest_data["review_decision_applied"]["decision"],
                "corrected",
            )
            self.assertEqual(
                manifest_data["review_decision_applied"]["manifest"],
                str(manifest),
            )
            self.assertEqual(
                manifest_data["review_decision_applied"]["review_artifacts"][
                    "promotion_regions"
                ],
                "promotion-regions.json",
            )
            self.assertEqual(
                manifest_data["promotion"]["review_decision_applied"]["decision"],
                "corrected",
            )
            self.assertFalse(
                manifest_data["promotion"]["review_decision_applied"][
                    "quality_label_policy"
                ]["updates_current_quality_label"]
            )
            self.assertIn(
                "- Accepted for promotion: `true`",
                markdown.read_text(encoding="utf-8"),
            )
            self.assertIn(
                "- Quality label policy: `sidecar_only`",
                markdown.read_text(encoding="utf-8"),
            )
            self.assertIn(
                "- Updates `current_quality_label`: `false`",
                markdown.read_text(encoding="utf-8"),
            )
            self.assertIn(
                "## Review Artifacts",
                markdown.read_text(encoding="utf-8"),
            )
            self.assertIn(
                "| `promotion_review` | `promotion-review.md` |",
                markdown.read_text(encoding="utf-8"),
            )

    def test_promotion_apply_review_cli_rejects_pending_decision(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            review_decision = Path(temp_dir) / "review-decision.json"
            review_decision.write_text(
                json.dumps({"case_id": "case", "decision": "pending"}),
                encoding="utf-8",
            )

            with self.assertRaises(ValueError):
                main(["promotion-apply-review", str(review_decision)])

    def test_promotion_apply_review_cli_requires_reviewer_and_reason(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            review_decision = Path(temp_dir) / "review-decision.json"
            review_decision.write_text(
                json.dumps({"case_id": "case", "decision": "accepted"}),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "requires reviewer"):
                main(["promotion-apply-review", str(review_decision)])

    def test_promotion_apply_review_cli_accepts_review_evidence_overrides(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            review_decision = root / "accepted-template.json"
            review_decision.write_text(
                json.dumps(
                    {
                        "case_id": "case",
                        "decision": "accepted",
                        "reviewer": "",
                        "reason": "",
                    }
                ),
                encoding="utf-8",
            )
            output = root / "applied-review.json"
            markdown = root / "applied-review.md"

            with redirect_stdout(StringIO()) as stdout:
                main(
                    [
                        "promotion-apply-review",
                        str(review_decision),
                        "-o",
                        str(output),
                        "--markdown",
                        str(markdown),
                        "--reviewer",
                        "qa",
                        "--reason",
                        "reviewed terminal template",
                    ]
                )

            self.assertIn("decision=accepted", stdout.getvalue())
            result = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(result["reviewer"], "qa")
            self.assertEqual(result["reason"], "reviewed terminal template")
            self.assertEqual(result["review_overrides"], ["reason", "reviewer"])
            rendered = markdown.read_text(encoding="utf-8")
            self.assertIn("- Reviewer: `qa`", rendered)
            self.assertIn("- Reason: `reviewed terminal template`", rendered)

    def test_promotion_apply_review_cli_requires_corrected_evidence(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            review_decision = Path(temp_dir) / "review-decision.json"
            review_decision.write_text(
                json.dumps(
                    {
                        "case_id": "case",
                        "decision": "corrected",
                        "reviewer": "qa",
                        "reason": "requires corrected evidence",
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "correction_notes"):
                main(["promotion-apply-review", str(review_decision)])

    def test_promotion_apply_review_cli_accepts_corrected_evidence_overrides(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            review_decision = root / "corrected-template.json"
            review_decision.write_text(
                json.dumps(
                    {
                        "case_id": "case",
                        "decision": "corrected",
                        "reviewer": "",
                        "reason": "",
                        "correction_notes": "",
                        "corrected_artifacts": [],
                    }
                ),
                encoding="utf-8",
            )
            output = root / "applied-review.json"

            with redirect_stdout(StringIO()):
                main(
                    [
                        "promotion-apply-review",
                        str(review_decision),
                        "-o",
                        str(output),
                        "--reviewer",
                        "qa",
                        "--reason",
                        "corrected reviewed evidence",
                        "--correction-notes",
                        "replace fallback path with corrected SVG",
                        "--corrected-artifact",
                        "corrected.svg",
                    ]
                )

            result = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(result["decision"], "corrected")
            self.assertEqual(
                result["correction_notes"],
                "replace fallback path with corrected SVG",
            )
            self.assertEqual(result["corrected_artifacts"], ["corrected.svg"])
            self.assertEqual(
                result["review_overrides"],
                [
                    "corrected_artifacts",
                    "correction_notes",
                    "reason",
                    "reviewer",
                ],
            )

    def test_promotion_review_harvest_cli_applies_decision_and_writes_config(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            suite = root / "suite.json"
            run_root = root / "runs"
            case_dir = run_root / "real-case"
            case_dir.mkdir(parents=True)
            manifest = case_dir / "manifest.json"
            manifest.write_text(
                json.dumps({"schema_version": 1, "promotion": {}, "anchors": []}),
                encoding="utf-8",
            )
            review_packet = root / "review-packet.json"
            review_packet.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "suite": str(suite),
                        "cases": [
                            {
                                "case_id": "real-case",
                                "suggested_review_decision": "deferred",
                                "review_decision_state": "pending",
                                "artifacts": {"manifest": str(manifest)},
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            terminal_decision = root / "accepted.json"
            terminal_decision.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "case_id": "real-case",
                        "decision": "accepted",
                        "suggested_decision": "deferred",
                        "reviewer": "qa",
                        "reason": "reviewed current deferred evidence",
                        "issue_tags": ["manual_review_pending"],
                    }
                ),
                encoding="utf-8",
            )
            output = root / "review-harvest.json"
            markdown = root / "review-harvest.md"
            harvest_config = root / "harvest-curated.json"

            with redirect_stdout(StringIO()) as stdout:
                main(
                    [
                        "promotion-review-harvest",
                        str(review_packet),
                        "-o",
                        str(output),
                        "--markdown",
                        str(markdown),
                        "--harvest-config",
                        str(harvest_config),
                        "--run-root",
                        str(run_root),
                        "--decision",
                        f"real-case={terminal_decision}",
                    ]
                )

            self.assertIn("applied=1", stdout.getvalue())
            result = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(result["newly_applied_decision_count"], 1)
            self.assertEqual(result["applied_case_count"], 1)
            self.assertEqual(result["harvestable_case_count"], 1)
            self.assertEqual(result["pending_case_count"], 0)
            manifest_data = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertEqual(
                manifest_data["review_decision_applied"]["decision"],
                "accepted",
            )
            self.assertEqual(
                manifest_data["promotion"]["review_decision_applied"]["decision"],
                "accepted",
            )
            config = json.loads(harvest_config.read_text(encoding="utf-8"))
            self.assertEqual(config["suite"], str(suite))
            self.assertEqual(config["run_root"], str(run_root))
            self.assertTrue(config["require_applied_review"])
            self.assertIn(
                "harvest-curated --config",
                markdown.read_text(encoding="utf-8"),
            )

    def test_promotion_review_harvest_cli_resolves_decision_choice(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            suite = root / "suite.json"
            run_root = root / "runs"
            case_dir = run_root / "real-case"
            case_dir.mkdir(parents=True)
            manifest = case_dir / "manifest.json"
            manifest.write_text(
                json.dumps({"schema_version": 1, "promotion": {}, "anchors": []}),
                encoding="utf-8",
            )
            accepted_decision = root / "accepted.json"
            accepted_decision.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "case_id": "real-case",
                        "decision": "accepted",
                        "reviewer": "qa",
                        "reason": "accepted by choice",
                    }
                ),
                encoding="utf-8",
            )
            rejected_decision = root / "rejected.json"
            rejected_decision.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "case_id": "real-case",
                        "decision": "rejected",
                        "reviewer": "qa",
                        "reason": "not selected",
                    }
                ),
                encoding="utf-8",
            )
            review_packet = root / "review-packet.json"
            review_packet.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "suite": str(suite),
                        "cases": [
                            {
                                "case_id": "real-case",
                                "suggested_review_decision": "deferred",
                                "review_decision_state": "pending",
                                "artifacts": {
                                    "manifest": str(manifest),
                                    "review_templates": {
                                        "accepted": str(accepted_decision),
                                        "rejected": str(rejected_decision),
                                    },
                                },
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            output = root / "review-harvest.json"

            with redirect_stdout(StringIO()) as stdout:
                main(
                    [
                        "promotion-review-harvest",
                        str(review_packet),
                        "-o",
                        str(output),
                        "--run-root",
                        str(run_root),
                        "--decision-choice",
                        "real-case=accepted",
                    ]
                )

            self.assertIn("harvestable=1", stdout.getvalue())
            result = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(
                result["newly_applied_decisions"][0]["decision"],
                "accepted",
            )
            manifest_data = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertEqual(
                manifest_data["review_decision_applied"]["source_review_decision"],
                str(accepted_decision),
            )

    def test_promotion_review_harvest_cli_accepts_config_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            suite = root / "suite.json"
            run_root = root / "runs"
            case_dir = run_root / "real-case"
            case_dir.mkdir(parents=True)
            manifest = case_dir / "manifest.json"
            manifest.write_text(
                json.dumps({"schema_version": 1, "promotion": {}, "anchors": []}),
                encoding="utf-8",
            )
            review_packet = root / "review-packet.json"
            review_packet.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "suite": str(suite),
                        "cases": [
                            {
                                "case_id": "real-case",
                                "suggested_review_decision": "deferred",
                                "review_decision_state": "pending",
                                "artifacts": {"manifest": str(manifest)},
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            deferred_decision = root / "deferred.json"
            deferred_decision.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "case_id": "real-case",
                        "decision": "deferred",
                        "reviewer": "qa",
                        "reason": "defer from config",
                    }
                ),
                encoding="utf-8",
            )
            accepted_decision = root / "accepted.json"
            accepted_decision.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "case_id": "real-case",
                        "decision": "accepted",
                        "reviewer": "qa",
                        "reason": "accepted override",
                    }
                ),
                encoding="utf-8",
            )
            output = root / "configured-review-harvest.json"
            harvest_config = root / "configured-harvest-curated.json"
            config = root / "promotion-review-harvest.json"
            config.write_text(
                json.dumps(
                    {
                        "review_packet": str(review_packet),
                        "output": str(output),
                        "harvest_config": str(harvest_config),
                        "run_root": str(run_root),
                        "decisions": {"real-case": str(deferred_decision)},
                    }
                ),
                encoding="utf-8",
            )

            with redirect_stdout(StringIO()) as stdout:
                main(
                    [
                        "promotion-review-harvest",
                        "--config",
                        str(config),
                        "--decision",
                        f"real-case={accepted_decision}",
                    ]
                )

            self.assertIn("harvestable=1", stdout.getvalue())
            result = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(
                result["newly_applied_decisions"][0]["decision"],
                "accepted",
            )
            self.assertEqual(result["harvest_config_path"], str(harvest_config))
            manifest_data = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertEqual(
                manifest_data["review_decision_applied"]["source_review_decision"],
                str(accepted_decision),
            )
            self.assertTrue(
                json.loads(harvest_config.read_text(encoding="utf-8"))[
                    "require_applied_review"
                ]
            )

    def test_promotion_review_harvest_cli_resolves_config_decision_choice(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            suite = root / "suite.json"
            run_root = root / "runs"
            case_dir = run_root / "real-case"
            case_dir.mkdir(parents=True)
            manifest = case_dir / "manifest.json"
            manifest.write_text(
                json.dumps({"schema_version": 1, "promotion": {}, "anchors": []}),
                encoding="utf-8",
            )
            review_packet = root / "review-packet.json"
            review_packet.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "suite": str(suite),
                        "cases": [
                            {
                                "case_id": "real-case",
                                "suggested_review_decision": "deferred",
                                "review_decision_state": "pending",
                                "artifacts": {"manifest": str(manifest)},
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            deferred_decision = root / "deferred.json"
            deferred_decision.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "case_id": "real-case",
                        "decision": "deferred",
                        "reviewer": "qa",
                        "reason": "defer from config choice",
                    }
                ),
                encoding="utf-8",
            )
            accepted_decision = root / "accepted.json"
            accepted_decision.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "case_id": "real-case",
                        "decision": "accepted",
                        "reviewer": "qa",
                        "reason": "accepted override choice",
                    }
                ),
                encoding="utf-8",
            )
            output = root / "configured-review-harvest.json"
            config = root / "promotion-review-harvest.json"
            config.write_text(
                json.dumps(
                    {
                        "review_packet": str(review_packet),
                        "output": str(output),
                        "run_root": str(run_root),
                        "decision_choices": {"real-case": "deferred"},
                        "decision_templates": {
                            "real-case": {
                                "accepted": str(accepted_decision),
                                "deferred": str(deferred_decision),
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )

            with redirect_stdout(StringIO()) as stdout:
                main(
                    [
                        "promotion-review-harvest",
                        "--config",
                        str(config),
                        "--decision-choice",
                        "real-case=accepted",
                    ]
                )

            self.assertIn("harvestable=1", stdout.getvalue())
            result = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(
                result["newly_applied_decisions"][0]["decision"],
                "accepted",
            )
            manifest_data = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertEqual(
                manifest_data["review_decision_applied"]["source_review_decision"],
                str(accepted_decision),
            )

    def test_promotion_review_harvest_cli_applies_config_review_overrides(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            suite = root / "suite.json"
            run_root = root / "runs"
            case_dir = run_root / "real-case"
            case_dir.mkdir(parents=True)
            manifest = case_dir / "manifest.json"
            manifest.write_text(
                json.dumps({"schema_version": 1, "promotion": {}, "anchors": []}),
                encoding="utf-8",
            )
            review_packet = root / "review-packet.json"
            review_packet.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "suite": str(suite),
                        "cases": [
                            {
                                "case_id": "real-case",
                                "suggested_review_decision": "deferred",
                                "review_decision_state": "pending",
                                "artifacts": {"manifest": str(manifest)},
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            accepted_decision = root / "accepted.json"
            accepted_decision.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "case_id": "real-case",
                        "decision": "accepted",
                        "reviewer": "",
                        "reason": "",
                    }
                ),
                encoding="utf-8",
            )
            output = root / "configured-review-harvest.json"
            config = root / "promotion-review-harvest.json"
            config.write_text(
                json.dumps(
                    {
                        "review_packet": str(review_packet),
                        "output": str(output),
                        "run_root": str(run_root),
                        "decision_choices": {"real-case": "accepted"},
                        "decision_templates": {
                            "real-case": {"accepted": str(accepted_decision)}
                        },
                        "decision_overrides": {
                            "real-case": {
                                "reviewer": "qa",
                                "reason": "accepted through config evidence",
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )

            with redirect_stdout(StringIO()) as stdout:
                main(["promotion-review-harvest", "--config", str(config)])

            self.assertIn("harvestable=1", stdout.getvalue())
            result = json.loads(output.read_text(encoding="utf-8"))
            self.assertTrue(
                result["decision_template_readiness"]["real-case"]["accepted"][
                    "ready"
                ]
            )
            self.assertEqual(
                result["newly_applied_decisions"][0]["review_overrides"],
                ["reason", "reviewer"],
            )
            manifest_data = json.loads(manifest.read_text(encoding="utf-8"))
            applied = manifest_data["review_decision_applied"]
            self.assertEqual(applied["decision"], "accepted")
            self.assertEqual(applied["reviewer"], "qa")
            self.assertEqual(applied["reason"], "accepted through config evidence")
            self.assertEqual(applied["review_overrides"], ["reason", "reviewer"])

    def test_promotion_review_harvest_cli_applies_corrected_config_overrides(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            suite = root / "suite.json"
            run_root = root / "runs"
            case_dir = run_root / "real-case"
            case_dir.mkdir(parents=True)
            manifest = case_dir / "manifest.json"
            manifest.write_text(
                json.dumps({"schema_version": 1, "promotion": {}, "anchors": []}),
                encoding="utf-8",
            )
            review_packet = root / "review-packet.json"
            review_packet.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "suite": str(suite),
                        "cases": [
                            {
                                "case_id": "real-case",
                                "suggested_review_decision": "corrected",
                                "review_decision_state": "pending",
                                "artifacts": {"manifest": str(manifest)},
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            corrected_decision = root / "corrected.json"
            corrected_decision.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "case_id": "real-case",
                        "decision": "corrected",
                        "reviewer": "",
                        "reason": "",
                        "correction_notes": "",
                        "corrected_artifacts": [],
                    }
                ),
                encoding="utf-8",
            )
            output = root / "configured-review-harvest.json"
            config = root / "promotion-review-harvest.json"
            config.write_text(
                json.dumps(
                    {
                        "review_packet": str(review_packet),
                        "output": str(output),
                        "run_root": str(run_root),
                        "decision_choices": {"real-case": "corrected"},
                        "decision_templates": {
                            "real-case": {"corrected": str(corrected_decision)}
                        },
                        "decision_overrides": {
                            "real-case": {
                                "reviewer": "qa",
                                "reason": "corrected through config evidence",
                                "correction_notes": "use corrected artifact",
                                "corrected_artifacts": ["corrected.svg"],
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )

            with redirect_stdout(StringIO()):
                main(["promotion-review-harvest", "--config", str(config)])

            result = json.loads(output.read_text(encoding="utf-8"))
            self.assertTrue(
                result["decision_template_readiness"]["real-case"]["corrected"][
                    "ready"
                ]
            )
            self.assertEqual(
                result["newly_applied_decisions"][0]["review_overrides"],
                [
                    "corrected_artifacts",
                    "correction_notes",
                    "reason",
                    "reviewer",
                ],
            )
            manifest_data = json.loads(manifest.read_text(encoding="utf-8"))
            applied = manifest_data["review_decision_applied"]
            self.assertEqual(applied["decision"], "corrected")
            self.assertEqual(applied["correction_notes"], "use corrected artifact")
            self.assertEqual(applied["corrected_artifacts"], ["corrected.svg"])

    def test_promotion_review_harvest_cli_reports_pending_packet_cases(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            suite = root / "suite.json"
            manifest = root / "runs" / "real-case" / "manifest.json"
            manifest.parent.mkdir(parents=True)
            manifest.write_text(
                json.dumps({"schema_version": 1, "promotion": {}, "anchors": []}),
                encoding="utf-8",
            )
            templates = {
                decision: str(root / f"{decision}.json")
                for decision in ("accepted", "corrected", "rejected", "deferred")
            }
            for path in templates.values():
                Path(path).write_text("{}", encoding="utf-8")
            review_packet = root / "review-packet.json"
            review_packet.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "suite": str(suite),
                        "cases": [
                            {
                                "case_id": "real-case",
                                "suggested_review_decision": "deferred",
                                "review_decision_state": "pending",
                                "artifacts": {
                                    "manifest": str(manifest),
                                    "review_templates": templates,
                                },
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            output = root / "review-harvest.json"
            markdown = root / "review-harvest.md"

            with redirect_stdout(StringIO()) as stdout:
                main(
                    [
                        "promotion-review-harvest",
                        str(review_packet),
                        "-o",
                        str(output),
                        "--markdown",
                        str(markdown),
                    ]
                )

            self.assertIn("pending=1", stdout.getvalue())
            result = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(result["newly_applied_decision_count"], 0)
            self.assertEqual(result["applied_case_count"], 0)
            self.assertEqual(result["harvestable_case_count"], 0)
            self.assertEqual(result["pending_case_count"], 1)
            self.assertEqual(result["pending_cases"][0]["case_id"], "real-case")
            self.assertEqual(
                result["pending_cases"][0]["decision_templates"],
                templates,
            )
            self.assertEqual(
                result["pending_cases"][0]["decision_template_readiness"][
                    "accepted"
                ]["missing_fields"],
                ["decision", "reviewer", "reason"],
            )
            self.assertEqual(result["decision_templates"]["real-case"], templates)
            self.assertEqual(result["decision_choice_commands"], {})
            rendered = markdown.read_text(encoding="utf-8")
            self.assertIn("Decision templates", rendered)
            self.assertIn(templates["accepted"], rendered)
            self.assertNotIn("Decision Choice Commands", rendered)

    def test_status_cli_writes_json_and_markdown(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "status.json"
            markdown = Path(temp_dir) / "status.md"

            with (
                patch("morphea.segmenters.is_mlx_runtime_available", return_value=False),
                redirect_stdout(StringIO()) as stdout,
            ):
                main(["status", "-o", str(output), "--markdown", str(markdown)])

            status = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(status["schema_version"], 1)
            self.assertIn("flat_color", status["segmenters"])
            self.assertIn("mlx", status["classifiers"])
            self.assertIn("capability blockers", stdout.getvalue())
            self.assertTrue(markdown.exists())

    def test_status_cli_accepts_config_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output = root / "status.json"
            markdown = root / "status.md"
            model_path = root / "sam.npz"
            config = root / "status-config.json"
            config.write_text(
                json.dumps(
                    {
                        "output": str(output),
                        "markdown": str(markdown),
                        "mlx_sam_model_path": str(model_path),
                    }
                ),
                encoding="utf-8",
            )

            with (
                patch("morphea.segmenters.is_mlx_runtime_available", return_value=False),
                redirect_stdout(StringIO()),
            ):
                main(["status", "--config", str(config)])

            status = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(
                status["segmenters"]["mlx_sam"]["model_path"],
                str(model_path),
            )
            self.assertTrue(markdown.exists())

    def test_status_cli_args_override_config_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output = root / "status.json"
            config_model = root / "config-sam.npz"
            cli_model = root / "cli-sam.npz"
            config = root / "status-config.json"
            config.write_text(
                json.dumps(
                    {
                        "output": str(output),
                        "mlx_sam_model_path": str(config_model),
                    }
                ),
                encoding="utf-8",
            )

            with (
                patch("morphea.segmenters.is_mlx_runtime_available", return_value=False),
                redirect_stdout(StringIO()),
            ):
                main(
                    [
                        "status",
                        "--config",
                        str(config),
                        "--mlx-sam-model-path",
                        str(cli_model),
                    ]
                )

            status = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(
                status["segmenters"]["mlx_sam"]["model_path"],
                str(cli_model),
            )

    def test_vectorize_accepts_color_tolerance(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "input.png"
            output_path = Path(temp_dir) / "output.svg"
            image = Image.new("RGB", (16, 16), "white")
            draw = ImageDraw.Draw(image)
            draw.ellipse((3, 3, 12, 12), fill="#dd2222")
            draw.point(((7, 3), (8, 12)), fill="#e02a2a")
            image.save(input_path)

            with redirect_stdout(StringIO()):
                main(
                    [
                        "vectorize",
                        str(input_path),
                        "-o",
                        str(output_path),
                        "--color-tolerance",
                        "18",
                    ]
                )

            manifest = json.loads(output_path.with_suffix(".json").read_text())
            self.assertEqual(manifest["anchor_count"], 1)
            self.assertEqual(manifest["anchors"][0]["kind"], "circle")

    def test_vectorize_reads_runtime_config_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "input.png"
            output_path = Path(temp_dir) / "output.svg"
            config_path = Path(temp_dir) / "vectorize.json"
            image = Image.new("RGB", (16, 16), "white")
            draw = ImageDraw.Draw(image)
            draw.ellipse((3, 3, 12, 12), fill="#dd2222")
            draw.point(((7, 3), (8, 12)), fill="#e02a2a")
            image.save(input_path)
            config_path.write_text(
                json.dumps({"color_tolerance": 18, "min_area": 8}),
                encoding="utf-8",
            )

            with redirect_stdout(StringIO()):
                main(
                    [
                        "vectorize",
                        str(input_path),
                        "-o",
                        str(output_path),
                        "--config",
                        str(config_path),
                    ]
                )

            manifest = json.loads(output_path.with_suffix(".json").read_text())
            self.assertEqual(manifest["anchor_count"], 1)

    def test_vectorize_config_accepts_artifact_paths(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_path = root / "input.png"
            output_path = root / "configured.svg"
            manifest_path = root / "configured-manifest.json"
            debug_svg = root / "configured-debug.svg"
            config_path = root / "vectorize.json"
            image = Image.new("RGB", (16, 16), "white")
            draw = ImageDraw.Draw(image)
            draw.ellipse((3, 3, 12, 12), fill="#dd2222")
            image.save(input_path)
            config_path.write_text(
                json.dumps(
                    {
                        "input": str(input_path),
                        "output": str(output_path),
                        "manifest": str(manifest_path),
                        "debug_svg": str(debug_svg),
                        "min_area": 8,
                    }
                ),
                encoding="utf-8",
            )

            with redirect_stdout(StringIO()):
                main(["vectorize", "--config", str(config_path)])

            self.assertTrue(output_path.exists())
            self.assertTrue(debug_svg.exists())
            manifest = json.loads(manifest_path.read_text())
            self.assertEqual(manifest["anchor_count"], 1)

    def test_vectorize_cli_args_override_config_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "input.png"
            output_path = Path(temp_dir) / "output.svg"
            config_path = Path(temp_dir) / "vectorize.json"
            image = Image.new("RGB", (16, 16), "white")
            draw = ImageDraw.Draw(image)
            draw.ellipse((3, 3, 12, 12), fill="#dd2222")
            image.save(input_path)
            config_path.write_text(json.dumps({"min_area": 999}), encoding="utf-8")

            with redirect_stdout(StringIO()):
                main(
                    [
                        "vectorize",
                        str(input_path),
                        "-o",
                        str(output_path),
                        "--config",
                        str(config_path),
                        "--min-area",
                        "8",
                    ]
                )

            manifest = json.loads(output_path.with_suffix(".json").read_text())
            self.assertEqual(manifest["anchor_count"], 1)

    def test_vectorize_cli_args_override_config_artifact_paths(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_input = root / "config-input.png"
            override_input = root / "override-input.png"
            config_output = root / "config-output.svg"
            output_path = root / "override-output.svg"
            config_path = root / "vectorize.json"
            Image.new("RGB", (16, 16), "white").save(config_input)
            image = Image.new("RGB", (16, 16), "white")
            draw = ImageDraw.Draw(image)
            draw.ellipse((3, 3, 12, 12), fill="#dd2222")
            image.save(override_input)
            config_path.write_text(
                json.dumps(
                    {
                        "input": str(config_input),
                        "output": str(config_output),
                        "min_area": 999,
                    }
                ),
                encoding="utf-8",
            )

            with redirect_stdout(StringIO()):
                main(
                    [
                        "vectorize",
                        str(override_input),
                        "-o",
                        str(output_path),
                        "--config",
                        str(config_path),
                        "--min-area",
                        "8",
                    ]
                )

            manifest = json.loads(output_path.with_suffix(".json").read_text())
            self.assertEqual(manifest["anchor_count"], 1)
            self.assertFalse(config_output.exists())

    def test_vectorize_config_accepts_explicit_background(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "input.png"
            output_path = Path(temp_dir) / "output.svg"
            config_path = Path(temp_dir) / "vectorize.json"
            image = Image.new("RGB", (18, 14), "#f6f6f6")
            draw = ImageDraw.Draw(image)
            draw.rectangle((0, 0, 8, 5), fill="#003366")
            image.save(input_path)
            config_path.write_text(
                json.dumps({"background": "#f6f6f6", "min_area": 4}),
                encoding="utf-8",
            )

            with redirect_stdout(StringIO()):
                main(
                    [
                        "vectorize",
                        str(input_path),
                        "-o",
                        str(output_path),
                        "--config",
                        str(config_path),
                    ]
                )

            manifest = json.loads(output_path.with_suffix(".json").read_text())
            self.assertEqual(manifest["anchor_count"], 1)
            self.assertEqual(manifest["anchors"][0]["color"], "#003366")

    def test_vectorize_config_rejects_unknown_keys(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "input.png"
            output_path = Path(temp_dir) / "output.svg"
            config_path = Path(temp_dir) / "vectorize.json"
            Image.new("RGB", (8, 8), "white").save(input_path)
            config_path.write_text(json.dumps({"unknown": 1}), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "unsupported vectorize config keys"):
                main(
                    [
                        "vectorize",
                        str(input_path),
                        "-o",
                        str(output_path),
                        "--config",
                        str(config_path),
                    ]
                )

    def test_vectorize_reads_cutout_export_from_config_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "input.png"
            output_path = Path(temp_dir) / "output.svg"
            config_path = Path(temp_dir) / "vectorize.json"
            image = Image.new("RGB", (18, 9), "white")
            draw = ImageDraw.Draw(image)
            draw.rectangle((2, 2, 15, 6), fill="#003366")
            draw.rectangle((6, 4, 11, 4), fill="white")
            image.save(input_path)
            config_path.write_text(
                json.dumps({"min_area": 8, "cutout_export": "negative_mask"}),
                encoding="utf-8",
            )

            with redirect_stdout(StringIO()):
                main(
                    [
                        "vectorize",
                        str(input_path),
                        "-o",
                        str(output_path),
                        "--config",
                        str(config_path),
                    ]
                )

            svg = output_path.read_text(encoding="utf-8")
            self.assertIn('<mask id="morphea-cutout-mask"', svg)

    def test_vectorize_cutout_export_flag_overrides_config_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "input.png"
            output_path = Path(temp_dir) / "output.svg"
            config_path = Path(temp_dir) / "vectorize.json"
            image = Image.new("RGB", (18, 9), "white")
            draw = ImageDraw.Draw(image)
            draw.rectangle((2, 2, 15, 6), fill="#003366")
            draw.rectangle((6, 4, 11, 4), fill="white")
            image.save(input_path)
            config_path.write_text(
                json.dumps({"min_area": 8, "cutout_export": "negative_mask"}),
                encoding="utf-8",
            )

            with redirect_stdout(StringIO()):
                main(
                    [
                        "vectorize",
                        str(input_path),
                        "-o",
                        str(output_path),
                        "--config",
                        str(config_path),
                        "--cutout-export",
                        "overlay_stroke",
                    ]
                )

            svg = output_path.read_text(encoding="utf-8")
            self.assertNotIn('<mask id="morphea-cutout-mask"', svg)
            self.assertIn('stroke="#ffffff"', svg)

    def test_vectorize_manifest_includes_cutout_strokes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "input.png"
            output_path = Path(temp_dir) / "output.svg"
            image = Image.new("RGB", (18, 9), "white")
            draw = ImageDraw.Draw(image)
            draw.rectangle((2, 2, 15, 6), fill="#003366")
            draw.rectangle((6, 4, 11, 4), fill="white")
            image.save(input_path)

            with redirect_stdout(StringIO()):
                main(["vectorize", str(input_path), "-o", str(output_path)])

            manifest = json.loads(output_path.with_suffix(".json").read_text())
            cutouts = [
                anchor
                for anchor in manifest["anchors"]
                if anchor.get("stroke", {}).get("is_cutout")
            ]
            self.assertEqual(len(cutouts), 1)
            self.assertEqual(cutouts[0]["color"], "#ffffff")

    def test_vectorize_can_export_cutouts_as_negative_mask(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "input.png"
            output_path = Path(temp_dir) / "output.svg"
            image = Image.new("RGB", (18, 9), "white")
            draw = ImageDraw.Draw(image)
            draw.rectangle((2, 2, 15, 6), fill="#003366")
            draw.rectangle((6, 4, 11, 4), fill="white")
            image.save(input_path)

            with redirect_stdout(StringIO()):
                main(
                    [
                        "vectorize",
                        str(input_path),
                        "-o",
                        str(output_path),
                        "--cutout-export",
                        "negative_mask",
                    ]
                )

            svg = output_path.read_text(encoding="utf-8")
            manifest = json.loads(output_path.with_suffix(".json").read_text())
            self.assertIn('<mask id="morphea-cutout-mask"', svg)
            self.assertIn('mask="url(#morphea-cutout-mask)"', svg)
            self.assertIn('stroke="black"', svg)
            self.assertNotIn('stroke="#ffffff"', svg)
            self.assertEqual(
                manifest["metrics"]["negative_mask_candidate_count"],
                1,
            )

    def test_vectorize_writes_runtime_diagnostics(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "input.png"
            output_path = Path(temp_dir) / "output.svg"
            image = Image.new("RGB", (40, 40), "white")
            draw = ImageDraw.Draw(image)
            draw.ellipse((8, 8, 31, 31), fill="#dd2222")
            image.save(input_path)

            with redirect_stdout(StringIO()):
                main(
                    [
                        "vectorize",
                        str(input_path),
                        "-o",
                        str(output_path),
                        "--max-size",
                        "20",
                        "--max-component-area",
                        "20",
                        "--timeout-seconds",
                        "5",
                    ]
                )

            manifest = json.loads(output_path.with_suffix(".json").read_text())
            codes = [diagnostic["code"] for diagnostic in manifest["diagnostics"]]
            self.assertIn("image_resized_for_analysis", codes)
            self.assertIn("color_mask_split_for_components", codes)
            self.assertIn("component_deferred", codes)

    def test_vectorize_can_write_run_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "input.png"
            output_path = Path(temp_dir) / "ignored.svg"
            run_root = Path(temp_dir) / "runs"
            image = Image.new("RGB", (24, 16), "white")
            draw = ImageDraw.Draw(image)
            draw.ellipse((2, 2, 10, 10), fill="#dd2222")
            image.save(input_path)

            with redirect_stdout(StringIO()):
                main(
                    [
                        "vectorize",
                        str(input_path),
                        "-o",
                        str(output_path),
                        "--run-dir",
                        str(run_root),
                    ]
                )

            run_dirs = list(run_root.iterdir())
            self.assertEqual(len(run_dirs), 1)
            self.assertTrue((run_dirs[0] / "input" / "input.png").exists())
            self.assertTrue((run_dirs[0] / "output.svg").exists())
            self.assertTrue((run_dirs[0] / "manifest.json").exists())
            self.assertTrue((run_dirs[0] / "config.json").exists())
            self.assertTrue((run_dirs[0] / "report.md").exists())
            self.assertTrue((run_dirs[0] / "debug.svg").exists())

    def test_vectorize_config_accepts_scoring_weights(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_path = root / "input.png"
            output_path = root / "ignored.svg"
            run_root = root / "runs"
            config_path = root / "vectorize-config.json"
            image = Image.new("RGB", (24, 16), "white")
            draw = ImageDraw.Draw(image)
            draw.ellipse((2, 2, 10, 10), fill="#dd2222")
            image.save(input_path)
            config_path.write_text(
                json.dumps(
                    {
                        "min_area": 4,
                        "simple_shape_bonus_weight": 2.0,
                        "node_complexity_weight": 0.02,
                    }
                ),
                encoding="utf-8",
            )

            with redirect_stdout(StringIO()):
                main(
                    [
                        "vectorize",
                        str(input_path),
                        "-o",
                        str(output_path),
                        "--run-dir",
                        str(run_root),
                        "--config",
                        str(config_path),
                    ]
                )

            run_dir = next(run_root.iterdir())
            config = json.loads((run_dir / "config.json").read_text(encoding="utf-8"))
            self.assertEqual(config["simple_shape_bonus_weight"], 2.0)
            self.assertEqual(config["node_complexity_weight"], 0.02)

    def test_vectorize_config_accepts_anchor_thresholds(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_path = root / "input.png"
            output_path = root / "ignored.svg"
            run_root = root / "runs"
            config_path = root / "vectorize-config.json"
            image = Image.new("RGB", (24, 16), "white")
            draw = ImageDraw.Draw(image)
            draw.rectangle((4, 4, 14, 8), fill="#003366")
            image.save(input_path)
            config_path.write_text(
                json.dumps(
                    {
                        "min_area": 4,
                        "rect_max_fill_error": 0.05,
                        "stroke_min_length_width_ratio": 4.0,
                    }
                ),
                encoding="utf-8",
            )

            with redirect_stdout(StringIO()):
                main(
                    [
                        "vectorize",
                        str(input_path),
                        "-o",
                        str(output_path),
                        "--run-dir",
                        str(run_root),
                        "--config",
                        str(config_path),
                    ]
                )

            run_dir = next(run_root.iterdir())
            config = json.loads((run_dir / "config.json").read_text(encoding="utf-8"))
            self.assertEqual(config["rect_max_fill_error"], 0.05)
            self.assertEqual(config["stroke_min_length_width_ratio"], 4.0)

    def test_vectorize_can_write_debug_svg(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "input.png"
            output_path = Path(temp_dir) / "output.svg"
            debug_path = Path(temp_dir) / "debug.svg"
            image = Image.new("RGB", (24, 16), "white")
            draw = ImageDraw.Draw(image)
            draw.ellipse((2, 2, 10, 10), fill="#dd2222")
            image.save(input_path)

            with redirect_stdout(StringIO()):
                main(
                    [
                        "vectorize",
                        str(input_path),
                        "-o",
                        str(output_path),
                        "--debug-svg",
                        str(debug_path),
                    ]
                )

            debug_svg = debug_path.read_text(encoding="utf-8")
            self.assertIn('id="anchor-0000"', debug_svg)
            self.assertIn("anchor-0000:circle", debug_svg)

    def test_vectorize_accepts_classifier_model_prior(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            generate_synthetic_dataset(
                output_dir=Path(temp_dir) / "dataset",
                count=4,
                seed=40,
                width=64,
                height=64,
                val_count=1,
                test_count=1,
            )
            model_path = Path(temp_dir) / "model.json"
            train_centroid_classifier(Path(temp_dir) / "dataset" / "dataset.json", output=model_path)
            input_path = Path(temp_dir) / "input.png"
            output_path = Path(temp_dir) / "output.svg"
            image = Image.new("RGB", (24, 16), "white")
            draw = ImageDraw.Draw(image)
            draw.ellipse((2, 2, 10, 10), fill="#dd2222")
            image.save(input_path)

            with redirect_stdout(StringIO()):
                main(
                    [
                        "vectorize",
                        str(input_path),
                        "-o",
                        str(output_path),
                        "--classifier-model",
                        str(model_path),
                    ]
                )

            manifest = json.loads(output_path.with_suffix(".json").read_text())
            self.assertIn(
                "classifier_prior_error",
                manifest["anchors"][0]["metrics"],
            )

    def test_vectorize_accepts_mlx_feature_head_classifier_model(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            model_path = Path(temp_dir) / "mlx-model.json"
            model_path.write_text(
                json.dumps(
                    {
                        "model_type": "mlx_transformer_primitive_classifier",
                        "classes": ["circle", "cubic_path"],
                        "fallback_centroids": {},
                        "mlx_training": {
                            "weight_format": "mlx_feature_head_v1",
                            "labels": ["circle", "cubic_path"],
                            "weights": [
                                [
                                    0.0, 0.0, 8.0, 0.0, 0.0, 0.0,
                                    0.0, 0.0, 0.0, 0.0, 0.0,
                                ],
                                [
                                    0.0, 0.0, -8.0, 0.0, 0.0, 0.0,
                                    0.0, 0.0, 0.0, 0.0, 0.0,
                                ],
                            ],
                            "bias": [0.0, 0.0],
                            "normalization": {
                                "mean": [0.0] * 11,
                                "scale": [1.0] * 11,
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )
            input_path = Path(temp_dir) / "input.png"
            output_path = Path(temp_dir) / "output.svg"
            image = Image.new("RGB", (24, 16), "white")
            draw = ImageDraw.Draw(image)
            draw.ellipse((2, 2, 10, 10), fill="#dd2222")
            image.save(input_path)

            with redirect_stdout(StringIO()):
                main(
                    [
                        "vectorize",
                        str(input_path),
                        "-o",
                        str(output_path),
                        "--classifier-model",
                        str(model_path),
                    ]
                )

            manifest = json.loads(output_path.with_suffix(".json").read_text())
            self.assertEqual(
                manifest["anchors"][0]["metrics"]["classifier_prior_error"],
                0.0,
            )

    def test_vectorize_uses_mlx_raster_mixer_prior(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            model_path = Path(temp_dir) / "mlx-model.json"
            model_path.write_text(
                json.dumps(
                    {
                        "model_type": "mlx_transformer_primitive_classifier",
                        "classes": ["circle", "cubic_path"],
                        "fallback_centroids": {},
                        "mlx_training": {
                            "weight_format": "mlx_feature_head_v1",
                            "labels": ["circle", "cubic_path"],
                            "weights": [
                                [
                                    0.0, 0.0, -8.0, 0.0, 0.0, 0.0,
                                    0.0, 0.0, 0.0, 0.0, 0.0,
                                ],
                                [
                                    0.0, 0.0, 8.0, 0.0, 0.0, 0.0,
                                    0.0, 0.0, 0.0, 0.0, 0.0,
                                ],
                            ],
                            "bias": [0.0, 0.0],
                            "normalization": {
                                "mean": [0.0] * 11,
                                "scale": [1.0] * 11,
                            },
                            "crop_token_spec": {"crop_size": 4},
                            "raster_token_mixer": {
                                "weight_format": "raster_token_mixer_v1",
                                "labels": ["circle", "cubic_path"],
                                "attention": {
                                    "heads": 1,
                                    "embedding_names": [
                                        "head_0_red",
                                        "head_0_green",
                                        "head_0_blue",
                                        "head_0_alpha",
                                        "head_0_x",
                                        "head_0_y",
                                        "head_0_foreground",
                                    ],
                                },
                                "weights": [
                                    [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 40.0],
                                    [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, -40.0],
                                ],
                                "bias": [0.0, 0.0],
                                "normalization": {
                                    "mean": [0.0] * 7,
                                    "scale": [1.0] * 7,
                                },
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )
            input_path = Path(temp_dir) / "input.png"
            output_path = Path(temp_dir) / "output.svg"
            image = Image.new("RGB", (24, 16), "white")
            draw = ImageDraw.Draw(image)
            draw.ellipse((2, 2, 10, 10), fill="#dd2222")
            image.save(input_path)

            with redirect_stdout(StringIO()):
                main(
                    [
                        "vectorize",
                        str(input_path),
                        "-o",
                        str(output_path),
                        "--classifier-model",
                        str(model_path),
                    ]
                )

            manifest = json.loads(output_path.with_suffix(".json").read_text())
            self.assertEqual(manifest["anchors"][0]["kind"], "circle")
            self.assertEqual(
                manifest["anchors"][0]["metrics"]["classifier_prior_error"],
                0.0,
            )

    def test_report_cli_writes_markdown_report(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manifest = Path(temp_dir) / "manifest.json"
            output = Path(temp_dir) / "report.md"
            manifest.write_text(
                json.dumps(
                    {
                        "width": 12,
                        "height": 12,
                        "anchor_count": 1,
                        "anchors": [{"kind": "quad"}],
                        "groups": [],
                        "diagnostics": [],
                    }
                ),
                encoding="utf-8",
            )

            with redirect_stdout(StringIO()):
                main(["report", str(manifest), "-o", str(output)])

            self.assertIn(
                "`quad`: 1",
                output.read_text(encoding="utf-8"),
            )

    def test_report_cli_writes_html_report(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manifest = Path(temp_dir) / "manifest.json"
            output = Path(temp_dir) / "report.html"
            manifest.write_text(
                json.dumps(
                    {
                        "width": 12,
                        "height": 12,
                        "anchor_count": 1,
                        "anchors": [{"kind": "quad"}],
                        "layers": [],
                        "groups": [],
                        "diagnostics": [],
                        "metrics": {"editability_score": 0.5},
                    }
                ),
                encoding="utf-8",
            )

            with redirect_stdout(StringIO()):
                main(["report", str(manifest), "-o", str(output)])

            html = output.read_text(encoding="utf-8")
            self.assertIn("<h1>Morphēa Vectorize Report</h1>", html)
            self.assertIn("<code>quad</code>", html)

    def test_report_cli_accepts_command_config_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest = root / "manifest.json"
            run_config = root / "run-config.json"
            output = root / "report.md"
            command_config = root / "report-config.json"
            manifest.write_text(
                json.dumps(
                    {
                        "width": 12,
                        "height": 12,
                        "anchor_count": 1,
                        "anchors": [{"kind": "quad"}],
                        "groups": [],
                        "diagnostics": [],
                    }
                ),
                encoding="utf-8",
            )
            run_config.write_text(
                json.dumps({"command": "vectorize", "min_area": 8}),
                encoding="utf-8",
            )
            command_config.write_text(
                json.dumps(
                    {
                        "manifest": str(manifest),
                        "output": str(output),
                        "config": str(run_config),
                        "format": "markdown",
                    }
                ),
                encoding="utf-8",
            )

            with redirect_stdout(StringIO()):
                main(["report", "--command-config", str(command_config)])

            report = output.read_text(encoding="utf-8")
            self.assertIn("`quad`: 1", report)
            self.assertIn('"min_area": 8', report)

    def test_report_cli_args_override_command_config_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest = root / "manifest.json"
            config_output = root / "config-report.md"
            cli_output = root / "cli-report.html"
            command_config = root / "report-config.json"
            manifest.write_text(
                json.dumps(
                    {
                        "width": 12,
                        "height": 12,
                        "anchor_count": 1,
                        "anchors": [{"kind": "circle"}],
                        "layers": [],
                        "groups": [],
                        "diagnostics": [],
                    }
                ),
                encoding="utf-8",
            )
            command_config.write_text(
                json.dumps(
                    {
                        "manifest": str(manifest),
                        "output": str(config_output),
                        "format": "markdown",
                    }
                ),
                encoding="utf-8",
            )

            with redirect_stdout(StringIO()):
                main(
                    [
                        "report",
                        "--command-config",
                        str(command_config),
                        "-o",
                        str(cli_output),
                        "--format",
                        "html",
                    ]
                )

            self.assertFalse(config_output.exists())
            html = cli_output.read_text(encoding="utf-8")
            self.assertIn("<h1>Morphēa Vectorize Report</h1>", html)
            self.assertIn("<code>circle</code>", html)


if __name__ == "__main__":
    unittest.main()
