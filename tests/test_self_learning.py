import json
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageDraw

from morphea.cli import main
from morphea.classifier import examples_from_dataset
from morphea.dataset import generate_synthetic_dataset
from morphea.self_learning import (
    apply_review_file,
    compare_retraining,
    create_review_file,
    gate_training_comparison,
    harvest_curated_pseudo_labels,
    harvest_pseudo_labels,
    merge_reviewed_pseudo_label_dataset,
    render_apply_review_markdown,
    render_harvest_markdown,
    render_review_markdown,
    render_self_learning_cycle_markdown,
    render_training_gate_markdown,
    render_training_comparison_markdown,
    run_self_learning_cycle,
    retrain_centroid_classifier,
    retrain_mlx_classifier,
)
from morphea.mlx_classifier import MlxClassifierTrainingConfig


class SelfLearningTests(unittest.TestCase):
    def test_harvest_pseudo_labels_accepts_clean_run_anchors(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "runs"
            _write_manifest(
                root,
                "clean",
                diagnostics=[],
                classifier_error=0.0,
                groups=[
                    {
                        "id": "grid-a",
                        "kind": "perspective_grid",
                        "anchor_indexes": [0, 1],
                        "metrics": {"row_count": 1.0, "column_count": 2.0},
                    }
                ],
            )
            output = Path(temp_dir) / "pseudo.json"

            result = harvest_pseudo_labels(run_root=root, output=output)

            self.assertEqual(result["pseudo_label_count"], 1)
            self.assertEqual(result["pseudo_labels"][0]["kind"], "circle")
            self.assertEqual(result["pseudo_labels"][0]["anchor"]["kind"], "circle")
            self.assertEqual(
                result["pseudo_labels"][0]["run_metrics"]["editability_score"],
                1.0,
            )
            self.assertEqual(
                result["pseudo_labels"][0]["group_context"][0]["kind"],
                "perspective_grid",
            )
            self.assertEqual(
                result["pseudo_labels"][0]["group_context"][0]["anchor_position"],
                0,
            )
            self.assertTrue(output.exists())

    def test_render_harvest_markdown_summarizes_quality_gates(self):
        markdown = render_harvest_markdown(
            {
                "pseudo_label_count": 1,
                "pseudo_labels": [
                    {
                        "run": "clean",
                        "anchor_index": 0,
                        "kind": "circle",
                        "anchor_quality_error": 0.02,
                        "group_context": [
                            {"kind": "perspective_grid", "anchor_indexes": [0, 1]}
                        ],
                        "source_manifest": "runs/clean/manifest.json",
                    }
                ],
                "rejected_runs": [
                    {
                        "run": "noisy",
                        "reason": "too_many_run_diagnostics",
                        "diagnostic_count": 2,
                    }
                ],
                "filters": {
                    "max_run_diagnostics": 0,
                    "min_editability_score": 0.8,
                },
            }
        )

        self.assertIn("# Morphēa Pseudo-Label Harvest", markdown)
        self.assertIn("| `min_editability_score` | 0.8 |", markdown)
        self.assertIn("| `clean` | 0 | `circle` (perspective_grid) | 0.02 |", markdown)
        self.assertIn("| `noisy` | `too_many_run_diagnostics` | 2 |", markdown)

    def test_harvest_pseudo_labels_writes_markdown_report(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "runs"
            _write_manifest(root, "clean", diagnostics=[], classifier_error=0.0)
            output = Path(temp_dir) / "pseudo.json"
            markdown = Path(temp_dir) / "pseudo.md"

            harvest_pseudo_labels(run_root=root, output=output, markdown=markdown)

            self.assertTrue(output.exists())
            self.assertIn(
                "# Morphēa Pseudo-Label Harvest",
                markdown.read_text(encoding="utf-8"),
            )

    def test_harvest_curated_runs_suite_and_collects_labels(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            suite = _write_curated_circle_suite(root)
            run_root = root / "runs"
            output = root / "pseudo.json"
            curated_report = root / "curated.json"
            snapshot = root / "snapshot.json"
            markdown = root / "pseudo.md"

            result = harvest_curated_pseudo_labels(
                suite=suite,
                run_root=run_root,
                output=output,
                curated_report=curated_report,
                snapshot=snapshot,
                markdown=markdown,
            )

            self.assertEqual(result["source"], "curated_suite")
            self.assertEqual(result["curated_case_count"], 1)
            self.assertEqual(result["curated_checked_count"], 1)
            self.assertEqual(result["curated_missing_source_count"], 0)
            self.assertGreaterEqual(result["pseudo_label_count"], 1)
            self.assertTrue((run_root / "circle-case" / "manifest.json").exists())
            self.assertTrue(curated_report.exists())
            self.assertTrue(snapshot.exists())
            saved = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(saved["source"], "curated_suite")
            self.assertIn(
                "- Suite:",
                markdown.read_text(encoding="utf-8"),
            )

    def test_harvest_curated_preserves_applied_reviews_across_rerun(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            suite = _write_curated_circle_suite(root)
            run_root = root / "runs"
            output = root / "pseudo.json"
            curated_report = root / "curated.json"
            markdown = root / "pseudo.md"
            applied_review = {
                "decision": "accepted",
                "case_id": "circle-case",
                "issue_tags": [],
            }
            _write_manifest(
                run_root,
                "circle-case",
                diagnostics=[],
                classifier_error=0.0,
                applied_review=applied_review,
            )

            result = harvest_curated_pseudo_labels(
                suite=suite,
                run_root=run_root,
                output=output,
                curated_report=curated_report,
                markdown=markdown,
                require_applied_review=True,
            )

            self.assertEqual(result["pseudo_label_count"], 1)
            self.assertEqual(result["applied_review_restored_count"], 1)
            self.assertEqual(result["applied_review_restored_cases"], ["circle-case"])
            self.assertEqual(
                result["pseudo_labels"][0]["review_decision_applied"]["decision"],
                "accepted",
            )
            manifest = json.loads(
                (run_root / "circle-case" / "manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(
                manifest["review_decision_applied"]["decision"],
                "accepted",
            )
            curated = json.loads(curated_report.read_text(encoding="utf-8"))
            self.assertEqual(
                curated["cases"][0]["review_decision_applied"]["decision"],
                "accepted",
            )
            self.assertIn(
                "- Restored applied reviews: 1",
                markdown.read_text(encoding="utf-8"),
            )

    def test_harvest_rejects_runs_with_warning_diagnostics(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "runs"
            _write_manifest(
                root,
                "warning",
                diagnostics=[{"level": "warning", "code": "component_deferred"}],
                classifier_error=0.0,
            )
            output = Path(temp_dir) / "pseudo.json"

            result = harvest_pseudo_labels(run_root=root, output=output)

            self.assertEqual(result["pseudo_label_count"], 0)
            self.assertEqual(result["rejected_runs"][0]["reason"], "too_many_run_diagnostics")

    def test_harvest_filters_high_classifier_prior_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "runs"
            _write_manifest(root, "mismatch", diagnostics=[], classifier_error=0.35)
            output = Path(temp_dir) / "pseudo.json"

            result = harvest_pseudo_labels(run_root=root, output=output)

            self.assertEqual(result["pseudo_label_count"], 0)

    def test_harvest_rejects_low_editability_runs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "runs"
            _write_manifest(
                root,
                "low-editability",
                diagnostics=[],
                classifier_error=0.0,
                editability_score=0.4,
            )
            output = Path(temp_dir) / "pseudo.json"

            result = harvest_pseudo_labels(
                run_root=root,
                output=output,
                min_editability_score=0.75,
            )

            self.assertEqual(result["pseudo_label_count"], 0)
            self.assertEqual(
                result["rejected_runs"][0]["reason"],
                "editability_score_too_low",
            )

    def test_harvest_rejects_high_fragmentation_runs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "runs"
            _write_manifest(
                root,
                "fragmented",
                diagnostics=[],
                classifier_error=0.0,
                fragmentation_penalty=0.35,
            )
            output = Path(temp_dir) / "pseudo.json"

            result = harvest_pseudo_labels(
                run_root=root,
                output=output,
                max_fragmentation_penalty=0.2,
            )

            self.assertEqual(result["pseudo_label_count"], 0)
            self.assertEqual(
                result["rejected_runs"][0]["reason"],
                "fragmentation_penalty_too_high",
            )

    def test_harvest_rejects_high_raster_error_runs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "runs"
            _write_manifest(
                root,
                "bad-raster",
                diagnostics=[],
                classifier_error=0.0,
                raster_l1_error=0.42,
            )
            output = Path(temp_dir) / "pseudo.json"

            result = harvest_pseudo_labels(
                run_root=root,
                output=output,
                max_raster_l1_error=0.1,
            )

            self.assertEqual(result["pseudo_label_count"], 0)
            self.assertEqual(
                result["rejected_runs"][0]["reason"],
                "raster_l1_error_too_high",
            )

    def test_harvest_filters_unstable_anchor_metrics(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "runs"
            _write_manifest(
                root,
                "jittery-anchor",
                diagnostics=[],
                classifier_error=0.0,
                anchor_metrics={"line_smoothness_error": 0.4},
            )
            output = Path(temp_dir) / "pseudo.json"

            result = harvest_pseudo_labels(
                run_root=root,
                output=output,
                max_anchor_quality_error=0.1,
            )

            self.assertEqual(result["pseudo_label_count"], 0)
            self.assertEqual(result["filters"]["max_anchor_quality_error"], 0.1)

    def test_harvest_can_require_accepted_applied_review(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "runs"
            _write_manifest(
                root,
                "missing-review",
                diagnostics=[],
                classifier_error=0.0,
            )
            _write_manifest(
                root,
                "corrected-review",
                diagnostics=[],
                classifier_error=0.0,
                applied_review={
                    "decision": "corrected",
                    "issue_tags": ["topology_mismatch"],
                },
            )
            _write_manifest(
                root,
                "rejected-review",
                diagnostics=[],
                classifier_error=0.0,
                applied_review={
                    "decision": "rejected",
                    "issue_tags": ["weak_visual_fidelity"],
                },
            )
            output = Path(temp_dir) / "pseudo.json"

            result = harvest_pseudo_labels(
                run_root=root,
                output=output,
                require_applied_review=True,
            )

            self.assertEqual(result["pseudo_label_count"], 1)
            self.assertEqual(
                result["pseudo_labels"][0]["run"],
                "corrected-review",
            )
            self.assertEqual(
                result["pseudo_labels"][0]["review_decision_applied"]["decision"],
                "corrected",
            )
            self.assertEqual(result["filters"]["require_applied_review"], True)
            rejected = {
                item["run"]: item
                for item in result["rejected_runs"]
            }
            self.assertEqual(
                rejected["missing-review"]["reason"],
                "missing_applied_review",
            )
            self.assertEqual(
                rejected["rejected-review"]["reason"],
                "applied_review_not_accepted",
            )

    def test_harvest_cli_can_require_applied_review(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "runs"
            _write_manifest(
                root,
                "accepted-review",
                diagnostics=[],
                classifier_error=0.0,
                applied_review={"decision": "accepted"},
            )
            output = Path(temp_dir) / "pseudo.json"
            markdown = Path(temp_dir) / "pseudo.md"

            with redirect_stdout(StringIO()):
                main(
                    [
                        "harvest",
                        str(root),
                        "-o",
                        str(output),
                        "--markdown",
                        str(markdown),
                        "--require-applied-review",
                    ]
                )

            result = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(result["pseudo_label_count"], 1)
            self.assertTrue(result["filters"]["require_applied_review"])
            self.assertIn(
                "| `require_applied_review` | true |",
                markdown.read_text(encoding="utf-8"),
            )

    def test_harvest_cli_writes_output(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "runs"
            _write_manifest(root, "clean", diagnostics=[], classifier_error=0.0)
            output = Path(temp_dir) / "pseudo.json"
            markdown = Path(temp_dir) / "pseudo.md"

            with redirect_stdout(StringIO()):
                main(
                    [
                        "harvest",
                        str(root),
                        "-o",
                        str(output),
                        "--min-editability-score",
                        "0.8",
                        "--max-fragmentation-penalty",
                        "0.25",
                        "--max-raster-edge-error",
                        "0.5",
                        "--max-anchor-quality-error",
                        "0.25",
                        "--markdown",
                        str(markdown),
                    ]
                )

            result = json.loads(output.read_text())
            self.assertEqual(result["pseudo_label_count"], 1)
            self.assertEqual(result["filters"]["min_editability_score"], 0.8)
            self.assertEqual(result["filters"]["max_raster_edge_error"], 0.5)
            self.assertIn(
                "# Morphēa Pseudo-Label Harvest",
                markdown.read_text(encoding="utf-8"),
            )

    def test_harvest_cli_accepts_config_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "runs"
            _write_manifest(root, "clean", diagnostics=[], classifier_error=0.0)
            output = Path(temp_dir) / "pseudo.json"
            markdown = Path(temp_dir) / "pseudo.md"
            config = Path(temp_dir) / "harvest.json"
            config.write_text(
                json.dumps(
                    {
                        "run_root": str(root),
                        "output": str(output),
                        "markdown": str(markdown),
                        "min_editability_score": 0.8,
                        "max_fragmentation_penalty": 0.25,
                        "max_raster_edge_error": 0.5,
                        "max_anchor_quality_error": 0.25,
                    }
                ),
                encoding="utf-8",
            )

            with redirect_stdout(StringIO()):
                main(["harvest", "--config", str(config)])

            result = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(result["pseudo_label_count"], 1)
            self.assertEqual(result["filters"]["min_editability_score"], 0.8)
            self.assertEqual(result["filters"]["max_fragmentation_penalty"], 0.25)
            self.assertIn(
                "# Morphēa Pseudo-Label Harvest",
                markdown.read_text(encoding="utf-8"),
            )

    def test_harvest_curated_cli_writes_outputs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            suite = _write_curated_circle_suite(root)
            run_root = root / "runs"
            output = root / "pseudo.json"
            curated_report = root / "curated.json"
            markdown = root / "pseudo.md"

            with redirect_stdout(StringIO()):
                main(
                    [
                        "harvest-curated",
                        str(suite),
                        "--run-root",
                        str(run_root),
                        "-o",
                        str(output),
                        "--curated-report",
                        str(curated_report),
                        "--markdown",
                        str(markdown),
                        "--min-editability-score",
                        "0.0",
                    ]
                )

            result = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(result["source"], "curated_suite")
            self.assertEqual(result["curated_checked_count"], 1)
            self.assertTrue(curated_report.exists())
            self.assertIn(
                "Morphēa Pseudo-Label Harvest",
                markdown.read_text(encoding="utf-8"),
            )

    def test_harvest_curated_cli_accepts_config_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            suite = _write_curated_circle_suite(root)
            run_root = root / "runs"
            output = root / "pseudo.json"
            markdown = root / "pseudo.md"
            config = root / "harvest-curated.json"
            config.write_text(
                json.dumps(
                    {
                        "suite": str(suite),
                        "run_root": str(run_root),
                        "output": str(output),
                        "markdown": str(markdown),
                        "max_fragmentation_penalty": 1.0,
                    }
                ),
                encoding="utf-8",
            )

            with redirect_stdout(StringIO()):
                main(["harvest-curated", "--config", str(config)])

            result = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(result["curated_case_count"], 1)
            self.assertEqual(result["filters"]["max_fragmentation_penalty"], 1.0)
            self.assertTrue(markdown.exists())

    def test_create_review_file_marks_labels_pending(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pseudo = Path(temp_dir) / "pseudo.json"
            pseudo.write_text(
                json.dumps({"pseudo_labels": [{"kind": "circle"}]}),
                encoding="utf-8",
            )
            output = Path(temp_dir) / "review.json"

            review = create_review_file(pseudo_labels=pseudo, output=output)

            self.assertEqual(review["review_count"], 1)
            self.assertEqual(review["issue_counts"], {})
            self.assertEqual(review["items"][0]["decision"], "pending")
            self.assertEqual(review["items"][0]["corrected_kind"], "")
            self.assertEqual(review["items"][0]["issues"], [])
            self.assertTrue(output.exists())

    def test_create_review_file_can_accept_applied_reviews(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pseudo = Path(temp_dir) / "pseudo.json"
            pseudo.write_text(
                json.dumps(
                    {
                        "pseudo_labels": [
                            {
                                "kind": "circle",
                                "review_decision_applied": {
                                    "case_id": "circle-case",
                                    "decision": "corrected",
                                    "issue_tags": ["topology_mismatch"],
                                },
                            },
                            {
                                "kind": "quad",
                                "review_decision_applied": {
                                    "case_id": "quad-case",
                                    "decision": "rejected",
                                    "issue_tags": ["weak_visual_fidelity"],
                                },
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )
            review_path = Path(temp_dir) / "review.json"
            reviewed_path = Path(temp_dir) / "reviewed.json"

            review = create_review_file(
                pseudo_labels=pseudo,
                output=review_path,
                accept_applied_reviews=True,
            )
            reviewed = apply_review_file(
                review=review_path,
                output=reviewed_path,
            )

            self.assertEqual(review["auto_accepted_applied_review_count"], 1)
            self.assertEqual(review["auto_rejected_applied_review_count"], 1)
            self.assertEqual(review["items"][0]["decision"], "accept")
            self.assertEqual(review["items"][1]["decision"], "reject")
            self.assertEqual(
                review["issue_counts"],
                {
                    "topology_mismatch": 1,
                    "weak_visual_fidelity": 1,
                },
            )
            self.assertEqual(reviewed["accepted_count"], 1)
            self.assertEqual(reviewed["rejected_count"], 1)
            self.assertEqual(
                reviewed["accepted"][0]["review"]["issues"],
                ["topology_mismatch"],
            )

    def test_render_review_markdown_summarizes_pending_items(self):
        markdown = render_review_markdown(
            {
                "source": "pseudo.json",
                "review_count": 1,
                "items": [
                    {
                        "id": "review-00000",
                        "decision": "pending",
                        "issues": ["bad_cutout"],
                        "label": {
                            "kind": "circle",
                            "anchor_quality_error": 0.03,
                            "group_context": [
                                {
                                    "kind": "perspective_grid",
                                    "anchor_position": 2,
                                }
                            ],
                        },
                    }
                ],
            }
        )

        self.assertIn("# Morphēa Review Queue", markdown)
        self.assertIn("- Source: `pseudo.json`", markdown)
        self.assertIn("- Issue counts: `bad_cutout: 1`", markdown)
        self.assertIn(
            "| `review-00000` | `pending` | `circle` | `perspective_grid#2` | 0.03 | bad_cutout |",
            markdown,
        )

    def test_create_review_file_writes_markdown_report(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pseudo = Path(temp_dir) / "pseudo.json"
            pseudo.write_text(
                json.dumps({"pseudo_labels": [{"kind": "circle"}]}),
                encoding="utf-8",
            )
            output = Path(temp_dir) / "review.json"
            markdown = Path(temp_dir) / "review.md"

            create_review_file(
                pseudo_labels=pseudo,
                output=output,
                markdown=markdown,
            )

            self.assertTrue(output.exists())
            self.assertIn(
                "# Morphēa Review Queue",
                markdown.read_text(encoding="utf-8"),
            )

    def test_review_cli_can_accept_applied_reviews(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pseudo = Path(temp_dir) / "pseudo.json"
            pseudo.write_text(
                json.dumps(
                    {
                        "pseudo_labels": [
                            {
                                "kind": "circle",
                                "review_decision_applied": {
                                    "decision": "accepted",
                                    "issue_tags": ["fragmentation"],
                                },
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            review = Path(temp_dir) / "review.json"
            markdown = Path(temp_dir) / "review.md"
            reviewed = Path(temp_dir) / "reviewed.json"

            with redirect_stdout(StringIO()):
                main(
                    [
                        "review",
                        str(pseudo),
                        "-o",
                        str(review),
                        "--markdown",
                        str(markdown),
                        "--accept-applied-reviews",
                    ]
                )
                main(["apply-review", str(review), "-o", str(reviewed)])

            review_data = json.loads(review.read_text(encoding="utf-8"))
            self.assertEqual(review_data["items"][0]["decision"], "accept")
            self.assertEqual(
                review_data["items"][0]["issues"],
                ["fragmentation"],
            )
            reviewed_data = json.loads(reviewed.read_text(encoding="utf-8"))
            self.assertEqual(reviewed_data["accepted_count"], 1)
            self.assertIn(
                "- Auto-accepted applied reviews: 1",
                markdown.read_text(encoding="utf-8"),
            )

    def test_apply_review_file_splits_accept_reject_pending(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            review = Path(temp_dir) / "review.json"
            review.write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "id": "review-00000",
                                "decision": "accept",
                                "issues": ["bad_stroke"],
                                "label": {"kind": "circle"},
                            },
                            {
                                "id": "review-00001",
                                "decision": "reject",
                                "reason": "wrong type",
                                "issues": ["wrong_primitive_type"],
                                "label": {"kind": "quad"},
                            },
                            {
                                "id": "review-00002",
                                "decision": "pending",
                                "issues": ["bad_cutout"],
                                "label": {"kind": "stroke_polyline"},
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )
            output = Path(temp_dir) / "accepted.json"

            result = apply_review_file(review=review, output=output)

            self.assertEqual(result["accepted_count"], 1)
            self.assertEqual(result["rejected_count"], 1)
            self.assertEqual(result["pending_count"], 1)
            self.assertEqual(
                result["issue_counts"],
                {
                    "bad_cutout": 1,
                    "bad_stroke": 1,
                    "wrong_primitive_type": 1,
                },
            )

    def test_render_apply_review_markdown_summarizes_decisions(self):
        markdown = render_apply_review_markdown(
            {
                "source_review": "review.json",
                "accepted_count": 1,
                "rejected_count": 1,
                "pending_count": 1,
                "issue_counts": {
                    "bad_cutout": 1,
                    "wrong_primitive_type": 1,
                },
                "accepted": [
                    {
                        "kind": "stroke_polyline",
                        "group_context": [
                            {
                                "kind": "parallel_stroke_group",
                                "anchor_position": 1,
                            }
                        ],
                        "review": {
                            "corrected_kind": "stroke_polyline",
                            "issues": ["wrong_primitive_type"],
                        },
                    }
                ],
                "rejected": [
                    {
                        "id": "review-00001",
                        "reason": "bad cutout",
                        "issues": ["bad_cutout"],
                        "label": {
                            "group_context": [
                                {
                                    "kind": "primitive_anchor_reservation",
                                    "anchor_position": 0,
                                }
                            ]
                        },
                    }
                ],
                "pending": ["review-00002"],
            }
        )

        self.assertIn("# Morphēa Apply Review", markdown)
        self.assertIn("- Accepted: 1", markdown)
        self.assertIn(
            "- Issue counts: `bad_cutout: 1, wrong_primitive_type: 1`",
            markdown,
        )
        self.assertIn(
            "| `stroke_polyline` | `stroke_polyline` | "
            "`parallel_stroke_group#1` | wrong_primitive_type |",
            markdown,
        )
        self.assertIn(
            "| `review-00001` | bad cutout | `primitive_anchor_reservation#0` | bad_cutout |",
            markdown,
        )
        self.assertIn("`review-00002`", markdown)

    def test_apply_review_file_writes_markdown_report(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            review = Path(temp_dir) / "review.json"
            review.write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "id": "review-00000",
                                "decision": "accept",
                                "label": {"kind": "circle"},
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            output = Path(temp_dir) / "accepted.json"
            markdown = Path(temp_dir) / "accepted.md"

            apply_review_file(review=review, output=output, markdown=markdown)

            self.assertTrue(output.exists())
            self.assertIn(
                "# Morphēa Apply Review",
                markdown.read_text(encoding="utf-8"),
            )

    def test_apply_review_file_can_correct_kind_and_record_issues(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            review = Path(temp_dir) / "review.json"
            review.write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "id": "review-00000",
                                "decision": "accept",
                                "corrected_kind": "stroke_polyline",
                                "issues": ["wrong_primitive_type", "bad_cutout"],
                                "label": {
                                    "kind": "circle",
                                    "anchor": {
                                        "kind": "circle",
                                        "metrics": {},
                                    },
                                },
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            output = Path(temp_dir) / "accepted.json"

            result = apply_review_file(review=review, output=output)

            accepted = result["accepted"][0]
            self.assertEqual(accepted["kind"], "stroke_polyline")
            self.assertEqual(accepted["anchor"]["kind"], "stroke_polyline")
            self.assertEqual(
                accepted["review"]["issues"],
                ["wrong_primitive_type", "bad_cutout"],
            )

    def test_review_cli_roundtrip(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pseudo = Path(temp_dir) / "pseudo.json"
            pseudo.write_text(
                json.dumps({"pseudo_labels": [{"kind": "circle"}]}),
                encoding="utf-8",
            )
            review = Path(temp_dir) / "review.json"
            markdown = Path(temp_dir) / "review.md"
            accepted = Path(temp_dir) / "accepted.json"
            accepted_markdown = Path(temp_dir) / "accepted.md"

            with redirect_stdout(StringIO()):
                main(
                    [
                        "review",
                        str(pseudo),
                        "-o",
                        str(review),
                        "--markdown",
                        str(markdown),
                    ]
                )
            data = json.loads(review.read_text())
            data["items"][0]["decision"] = "accept"
            review.write_text(json.dumps(data), encoding="utf-8")
            with redirect_stdout(StringIO()):
                main(
                    [
                        "apply-review",
                        str(review),
                        "-o",
                        str(accepted),
                        "--markdown",
                        str(accepted_markdown),
                    ]
                )

            result = json.loads(accepted.read_text())
            self.assertEqual(result["accepted_count"], 1)
            self.assertIn(
                "# Morphēa Review Queue",
                markdown.read_text(encoding="utf-8"),
            )
            self.assertIn(
                "# Morphēa Apply Review",
                accepted_markdown.read_text(encoding="utf-8"),
            )

    def test_review_cli_accepts_config_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pseudo = Path(temp_dir) / "pseudo.json"
            pseudo.write_text(
                json.dumps({"pseudo_labels": [{"kind": "circle"}]}),
                encoding="utf-8",
            )
            review = Path(temp_dir) / "review.json"
            markdown = Path(temp_dir) / "review.md"
            config = Path(temp_dir) / "review-config.json"
            config.write_text(
                json.dumps(
                    {
                        "pseudo_labels": str(pseudo),
                        "output": str(review),
                        "markdown": str(markdown),
                    }
                ),
                encoding="utf-8",
            )

            with redirect_stdout(StringIO()):
                main(["review", "--config", str(config)])

            data = json.loads(review.read_text(encoding="utf-8"))
            self.assertEqual(data["review_count"], 1)
            self.assertIn(
                "# Morphēa Review Queue",
                markdown.read_text(encoding="utf-8"),
            )

    def test_apply_review_cli_accepts_config_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            review = Path(temp_dir) / "review.json"
            accepted = Path(temp_dir) / "accepted.json"
            markdown = Path(temp_dir) / "accepted.md"
            config = Path(temp_dir) / "apply-review-config.json"
            review.write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "id": "review-00000",
                                "decision": "accept",
                                "label": {"kind": "circle"},
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            config.write_text(
                json.dumps(
                    {
                        "review": str(review),
                        "output": str(accepted),
                        "markdown": str(markdown),
                    }
                ),
                encoding="utf-8",
            )

            with redirect_stdout(StringIO()):
                main(["apply-review", "--config", str(config)])

            result = json.loads(accepted.read_text(encoding="utf-8"))
            self.assertEqual(result["accepted_count"], 1)
            self.assertIn(
                "# Morphēa Apply Review",
                markdown.read_text(encoding="utf-8"),
            )

    def test_merge_reviewed_pseudo_labels_writes_trainable_dataset(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            runs = root / "runs"
            _write_manifest(
                runs,
                "clean",
                diagnostics=[],
                classifier_error=0.0,
                groups=[
                    {
                        "id": "grid-a",
                        "kind": "perspective_grid",
                        "anchor_indexes": [0, 1],
                        "metrics": {"row_count": 1.0, "column_count": 2.0},
                    }
                ],
            )
            pseudo = root / "pseudo.json"
            reviewed = root / "reviewed.json"
            output_dir = root / "dataset"

            harvest_pseudo_labels(run_root=runs, output=pseudo)
            review = create_review_file(pseudo_labels=pseudo, output=root / "review.json")
            review["items"][0]["decision"] = "accept"
            (root / "review.json").write_text(json.dumps(review), encoding="utf-8")
            apply_review_file(review=root / "review.json", output=reviewed)

            dataset = merge_reviewed_pseudo_label_dataset(
                reviewed_labels=reviewed,
                output_dir=output_dir,
            )
            examples = examples_from_dataset(output_dir / "dataset.json")

            self.assertEqual(dataset["count"], 1)
            self.assertTrue((output_dir / "train" / "pseudo-00000.json").exists())
            self.assertEqual(len(examples), 1)
            self.assertEqual(examples[0].label, "circle")
            pseudo_manifest = json.loads(
                (output_dir / "train" / "pseudo-00000.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(pseudo_manifest["groups"][0]["kind"], "perspective_grid")
            self.assertEqual(pseudo_manifest["groups"][0]["anchor_indexes"], [0])
            self.assertEqual(pseudo_manifest["groups"][0]["source_group_id"], "grid-a")
            self.assertEqual(
                pseudo_manifest["groups"][0]["source_anchor_indexes"],
                [0, 1],
            )

    def test_merge_reviewed_labels_preserves_applied_review_provenance(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            pseudo = root / "pseudo.json"
            review = root / "review.json"
            reviewed = root / "reviewed.json"
            output_dir = root / "dataset"
            pseudo.write_text(
                json.dumps(
                    {
                        "pseudo_labels": [
                            {
                                "kind": "circle",
                                "anchor": {"kind": "circle"},
                                "review_decision_applied": {
                                    "case_id": "circle-case",
                                    "decision": "accepted",
                                    "issue_tags": ["fragmentation"],
                                    "source_review_decision": "circle-review.json",
                                },
                            },
                            {
                                "kind": "quad",
                                "anchor": {"kind": "quad"},
                                "review_decision_applied": {
                                    "case_id": "quad-case",
                                    "decision": "deferred",
                                    "issue_tags": ["weak_visual_fidelity"],
                                },
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            create_review_file(
                pseudo_labels=pseudo,
                output=review,
                accept_applied_reviews=True,
            )
            apply_review_file(review=review, output=reviewed)
            dataset = merge_reviewed_pseudo_label_dataset(
                reviewed_labels=reviewed,
                output_dir=output_dir,
            )

            self.assertEqual(dataset["count"], 1)
            self.assertEqual(
                dataset["samples"][0]["applied_review_decision"],
                "accepted",
            )
            self.assertEqual(
                dataset["samples"][0]["applied_review_case_id"],
                "circle-case",
            )
            self.assertEqual(
                dataset["samples"][0]["applied_review_source_review_decision"],
                "circle-review.json",
            )
            self.assertEqual(
                dataset["samples"][0]["review_item_id"],
                "review-00000",
            )
            self.assertEqual(
                dataset["samples"][0]["review_reason"],
                "applied_review_accepted",
            )
            self.assertEqual(
                dataset["samples"][0]["review_issues"],
                ["fragmentation"],
            )
            self.assertEqual(
                dataset["reviewed_label_summary"]["applied_review_decision_counts"],
                {"accepted": 1},
            )
            self.assertEqual(
                dataset["reviewed_label_summary"]["issue_counts"],
                {"fragmentation": 1},
            )
            pseudo_manifest = json.loads(
                (output_dir / "train" / "pseudo-00000.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(
                pseudo_manifest["review_decision_applied"]["case_id"],
                "circle-case",
            )
            self.assertEqual(
                pseudo_manifest["review"]["issues"],
                ["fragmentation"],
            )
            self.assertEqual(
                pseudo_manifest["review"]["review_item_id"],
                "review-00000",
            )

    def test_merge_labels_cli_writes_dataset(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            reviewed = root / "reviewed.json"
            reviewed.write_text(
                json.dumps(
                    {
                        "accepted": [
                            {
                                "kind": "circle",
                                "anchor": {
                                    "kind": "circle",
                                    "node_count": 1,
                                    "parameter_count": 3,
                                    "circle": {"cx": 5, "cy": 5, "r": 3},
                                },
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            output_dir = root / "dataset"

            with redirect_stdout(StringIO()):
                main(["merge-labels", str(reviewed), "-o", str(output_dir)])

            self.assertTrue((output_dir / "dataset.json").exists())

    def test_merge_labels_cli_accepts_config_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            reviewed = root / "reviewed.json"
            output_dir = root / "dataset"
            config = root / "merge-labels.json"
            _write_reviewed_circle(reviewed)
            config.write_text(
                json.dumps(
                    {
                        "reviewed_labels": str(reviewed),
                        "output_dir": str(output_dir),
                    }
                ),
                encoding="utf-8",
            )

            with redirect_stdout(StringIO()):
                main(["merge-labels", "--config", str(config)])

            self.assertTrue((output_dir / "dataset.json").exists())

    def test_compare_retraining_reports_augmented_delta(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            base_dir = root / "base"
            pseudo_dir = root / "pseudo"
            reviewed = root / "reviewed.json"
            output = root / "compare.json"
            generate_synthetic_dataset(
                output_dir=base_dir,
                count=4,
                seed=90,
                width=64,
                height=64,
                val_count=1,
                test_count=1,
            )
            _write_reviewed_circle(reviewed)
            merge_reviewed_pseudo_label_dataset(
                reviewed_labels=reviewed,
                output_dir=pseudo_dir,
            )

            result = compare_retraining(
                base_dataset=base_dir / "dataset.json",
                pseudo_dataset=pseudo_dir / "dataset.json",
                output=output,
            )

            self.assertTrue(output.exists())
            self.assertEqual(result["schema_version"], 1)
            self.assertEqual(result["delta"]["train_examples"], 1)
            self.assertGreater(
                result["augmented"]["train_examples"],
                result["baseline"]["train_examples"],
            )
            self.assertIn("feature_importance", result["baseline"])
            self.assertIn("feature_importance", result["augmented"])
            self.assertIn(
                "label_accuracy",
                result["baseline"]["evaluation"]["val"],
            )
            self.assertIn("ranking_evaluation", result["delta"])
            self.assertIn("label_accuracy", result["delta"])
            self.assertIn("feature_importance", result["delta"])
            self.assertTrue(
                any(
                    item["feature"] == "node_count"
                    for item in result["delta"]["feature_importance"]
                )
            )
            self.assertIn(
                result["summary"]["status"],
                {"improved", "regressed", "mixed", "unchanged"},
            )
            self.assertEqual(result["summary"]["train_examples_delta"], 1)
            self.assertGreater(result["summary"]["metric_count"], 0)

    def test_render_training_comparison_markdown_summarizes_verdict(self):
        markdown = render_training_comparison_markdown(
            {
                "base_dataset": "base/dataset.json",
                "pseudo_dataset": "pseudo/dataset.json",
                "validation_dataset": "base/dataset.json",
                "summary": {
                    "status": "improved",
                    "train_examples_delta": 2,
                    "best_accuracy_delta": 0.1,
                    "worst_accuracy_delta": 0.0,
                },
                "baseline": {"evaluation": {"val": {"accuracy": 0.5}}},
                "augmented": {"evaluation": {"val": {"accuracy": 0.6}}},
                "delta": {
                    "evaluation": {"val": 0.1},
                    "label_accuracy": {
                        "val": {
                            "circle": {
                                "baseline_accuracy": 0.5,
                                "augmented_accuracy": 1.0,
                                "accuracy_delta": 0.5,
                            }
                        }
                    },
                    "feature_importance": [
                        {
                            "feature": "group_count",
                            "baseline_spread": 0.0,
                            "augmented_spread": 1.0,
                            "spread_delta": 1.0,
                        }
                    ],
                },
            }
        )

        self.assertIn("# Morphēa Training Comparison", markdown)
        self.assertIn("- Status: `improved`", markdown)
        self.assertIn("| `val` | 0.5 | 0.6 | 0.1 |", markdown)
        self.assertIn("## Label Accuracy Delta", markdown)
        self.assertIn("| `val` | `circle` | 0.5 | 1 | 0.5 |", markdown)
        self.assertIn("## Feature Importance Delta", markdown)
        self.assertIn("| `group_count` | 0 | 1 | 1 |", markdown)

    def test_compare_training_cli_writes_report(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            base_dir = root / "base"
            pseudo_dir = root / "pseudo"
            reviewed = root / "reviewed.json"
            output = root / "compare.json"
            generate_synthetic_dataset(
                output_dir=base_dir,
                count=4,
                seed=91,
                width=64,
                height=64,
                val_count=1,
                test_count=1,
            )
            _write_reviewed_circle(reviewed)
            merge_reviewed_pseudo_label_dataset(
                reviewed_labels=reviewed,
                output_dir=pseudo_dir,
            )

            with redirect_stdout(StringIO()):
                main(
                    [
                        "compare-training",
                        str(base_dir / "dataset.json"),
                        "--pseudo-dataset",
                        str(pseudo_dir / "dataset.json"),
                        "-o",
                        str(output),
                    ]
                )

            result = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(result["delta"]["train_examples"], 1)
            self.assertEqual(result["summary"]["train_examples_delta"], 1)
            self.assertIn("best_accuracy_delta", result["summary"])

    def test_compare_training_cli_writes_markdown_report(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            base_dir = root / "base"
            pseudo_dir = root / "pseudo"
            reviewed = root / "reviewed.json"
            output = root / "compare.json"
            markdown = root / "compare.md"
            generate_synthetic_dataset(
                output_dir=base_dir,
                count=4,
                seed=95,
                width=64,
                height=64,
                val_count=1,
                test_count=1,
            )
            _write_reviewed_circle(reviewed)
            merge_reviewed_pseudo_label_dataset(
                reviewed_labels=reviewed,
                output_dir=pseudo_dir,
            )

            with redirect_stdout(StringIO()):
                main(
                    [
                        "compare-training",
                        str(base_dir / "dataset.json"),
                        "--pseudo-dataset",
                        str(pseudo_dir / "dataset.json"),
                        "-o",
                        str(output),
                        "--markdown",
                        str(markdown),
                    ]
                )

            self.assertTrue(output.exists())
            self.assertIn(
                "# Morphēa Training Comparison",
                markdown.read_text(encoding="utf-8"),
            )

    def test_compare_training_cli_accepts_config_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            base_dir = root / "base"
            pseudo_dir = root / "pseudo"
            reviewed = root / "reviewed.json"
            output = root / "compare.json"
            markdown = root / "compare.md"
            config = root / "compare-training.json"
            generate_synthetic_dataset(
                output_dir=base_dir,
                count=4,
                seed=92,
                width=64,
                height=64,
                val_count=1,
                test_count=1,
            )
            _write_reviewed_circle(reviewed)
            merge_reviewed_pseudo_label_dataset(
                reviewed_labels=reviewed,
                output_dir=pseudo_dir,
            )
            config.write_text(
                json.dumps(
                    {
                        "base_dataset": str(base_dir / "dataset.json"),
                        "pseudo_dataset": str(pseudo_dir / "dataset.json"),
                        "output": str(output),
                        "markdown": str(markdown),
                    }
                ),
                encoding="utf-8",
            )

            with redirect_stdout(StringIO()):
                main(["compare-training", "--config", str(config)])

            result = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(result["delta"]["train_examples"], 1)
            self.assertTrue(markdown.exists())

    def test_training_gate_accepts_improved_comparison(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            comparison = Path(temp_dir) / "compare.json"
            output = Path(temp_dir) / "gate.json"
            _write_training_comparison(
                comparison,
                status="improved",
                train_delta=2,
                best_delta=0.2,
                worst_delta=0.0,
            )

            result = gate_training_comparison(
                comparison=comparison,
                output=output,
            )

            self.assertEqual(result["decision"], "accept")
            self.assertTrue(result["accepted"])
            self.assertEqual(result["reasons"], [])
            self.assertTrue(output.exists())

    def test_training_gate_rejects_regression(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            comparison = Path(temp_dir) / "compare.json"
            output = Path(temp_dir) / "gate.json"
            _write_training_comparison(
                comparison,
                status="regressed",
                train_delta=1,
                best_delta=-0.1,
                worst_delta=-0.2,
            )

            result = gate_training_comparison(
                comparison=comparison,
                output=output,
            )

            self.assertEqual(result["decision"], "reject")
            self.assertFalse(result["accepted"])
            self.assertIn("comparison_status_regressed", result["reasons"])
            self.assertIn("worst_accuracy_delta_below_tolerance", result["reasons"])

    def test_training_gate_marks_mixed_comparison_for_review(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            comparison = Path(temp_dir) / "compare.json"
            output = Path(temp_dir) / "gate.json"
            _write_training_comparison(
                comparison,
                status="mixed",
                train_delta=1,
                best_delta=0.2,
                worst_delta=0.0,
            )

            result = gate_training_comparison(
                comparison=comparison,
                output=output,
            )

            self.assertEqual(result["decision"], "manual_review")
            self.assertFalse(result["accepted"])
            self.assertIn("comparison_status_mixed", result["reasons"])

    def test_render_training_gate_markdown_summarizes_decision(self):
        markdown = render_training_gate_markdown(
            {
                "comparison": "compare.json",
                "decision": "reject",
                "accepted": False,
                "reasons": ["worst_accuracy_delta_below_tolerance"],
                "gates": {"max_worst_accuracy_drop": 0.0},
                "summary": {
                    "status": "regressed",
                    "train_examples_delta": 1,
                    "best_accuracy_delta": -0.1,
                    "worst_accuracy_delta": -0.2,
                },
            }
        )

        self.assertIn("# Morphēa Training Gate", markdown)
        self.assertIn("- Decision: `reject`", markdown)
        self.assertIn("`worst_accuracy_delta_below_tolerance`", markdown)

    def test_training_gate_cli_writes_json_and_markdown(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            comparison = Path(temp_dir) / "compare.json"
            output = Path(temp_dir) / "gate.json"
            markdown = Path(temp_dir) / "gate.md"
            _write_training_comparison(
                comparison,
                status="improved",
                train_delta=1,
                best_delta=0.05,
                worst_delta=0.0,
            )

            with redirect_stdout(StringIO()):
                main(
                    [
                        "training-gate",
                        str(comparison),
                        "-o",
                        str(output),
                        "--markdown",
                        str(markdown),
                    ]
                )

            result = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(result["decision"], "accept")
            self.assertIn(
                "# Morphēa Training Gate",
                markdown.read_text(encoding="utf-8"),
            )

    def test_training_gate_cli_accepts_config_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            comparison = Path(temp_dir) / "compare.json"
            output = Path(temp_dir) / "gate.json"
            config = Path(temp_dir) / "training-gate.json"
            _write_training_comparison(
                comparison,
                status="unchanged",
                train_delta=1,
                best_delta=0.0,
                worst_delta=0.0,
            )
            config.write_text(
                json.dumps(
                    {
                        "comparison": str(comparison),
                        "output": str(output),
                        "allow_unchanged": True,
                    }
                ),
                encoding="utf-8",
            )

            with redirect_stdout(StringIO()):
                main(["training-gate", "--config", str(config)])

            result = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(result["decision"], "accept")
            self.assertTrue(result["gates"]["allow_unchanged"])

    def test_self_learning_cycle_writes_decision_artifacts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            base_dir = root / "base"
            reviewed = root / "reviewed.json"
            output_dir = root / "cycle"
            generate_synthetic_dataset(
                output_dir=base_dir,
                count=4,
                seed=96,
                width=64,
                height=64,
                val_count=1,
                test_count=1,
            )
            _write_reviewed_circle(reviewed)

            result = run_self_learning_cycle(
                base_dataset=base_dir / "dataset.json",
                reviewed_labels=reviewed,
                output_dir=output_dir,
                max_worst_accuracy_drop=1.0,
                allow_unchanged=True,
            )

            self.assertIn(result["status"], {"retrained", "skipped_retrain"})
            self.assertTrue((output_dir / "pseudo-dataset" / "dataset.json").exists())
            self.assertTrue((output_dir / "comparison.json").exists())
            self.assertTrue((output_dir / "comparison.md").exists())
            self.assertTrue((output_dir / "gate.json").exists())
            self.assertTrue((output_dir / "gate.md").exists())
            self.assertTrue((output_dir / "self-learning-cycle.json").exists())
            self.assertTrue((output_dir / "self-learning-cycle.md").exists())
            if result["gate"]["accepted"]:
                self.assertEqual(result["status"], "retrained")
                self.assertTrue((output_dir / "model.json").exists())
            else:
                self.assertEqual(result["status"], "skipped_retrain")
                self.assertFalse((output_dir / "model.json").exists())

    def test_self_learning_cycle_validates_accepted_model_on_curated_suite(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            base_dir = root / "base"
            reviewed = root / "reviewed.json"
            output_dir = root / "cycle"
            curated_suite = _write_curated_circle_suite(root)
            generate_synthetic_dataset(
                output_dir=base_dir,
                count=4,
                seed=98,
                width=64,
                height=64,
                val_count=1,
                test_count=1,
            )
            _write_reviewed_circle(reviewed)

            def accepted_gate(**kwargs):
                Path(kwargs["output"]).write_text(
                    json.dumps(
                        {
                            "decision": "accept",
                            "accepted": True,
                            "reasons": [],
                        }
                    ),
                    encoding="utf-8",
                )
                Path(kwargs["markdown"]).write_text("# gate\n", encoding="utf-8")
                return {"decision": "accept", "accepted": True, "reasons": []}

            with patch("morphea.self_learning.gate_training_comparison", accepted_gate):
                result = run_self_learning_cycle(
                    base_dataset=base_dir / "dataset.json",
                    reviewed_labels=reviewed,
                    output_dir=output_dir,
                    curated_suite=curated_suite,
                )

            self.assertEqual(result["status"], "retrained")
            self.assertTrue(result["accepted"])
            self.assertEqual(result["acceptance_gate"]["reasons"], [])
            self.assertEqual(result["curated_validation"]["status"], "checked")
            self.assertEqual(result["curated_validation"]["checked_count"], 1)
            self.assertEqual(
                result["suite_family_validation"]["real_image"]["status"],
                "checked",
            )
            self.assertIn(
                "primitive",
                result["suite_family_validation"],
            )
            self.assertTrue(
                result["suite_family_validation"]["real_image"]["families"]
            )
            self.assertTrue((output_dir / "model.json").exists())
            self.assertTrue((output_dir / "curated-validation.json").exists())
            self.assertTrue(
                (output_dir / "curated-validation-snapshot.json").exists()
            )
            curated_report = json.loads(
                (output_dir / "curated-validation.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(
                curated_report["config_overrides"]["classifier_model"],
                str(output_dir / "model.json"),
            )

    def test_self_learning_cycle_validates_accepted_model_on_lucide_suite(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            base_dir = root / "base"
            reviewed = root / "reviewed.json"
            output_dir = root / "cycle"
            lucide_suite = root / "lucide-suite.json"
            generate_synthetic_dataset(
                output_dir=base_dir,
                count=4,
                seed=102,
                width=64,
                height=64,
                val_count=1,
                test_count=1,
            )
            _write_reviewed_circle(reviewed)

            def accepted_gate(**kwargs):
                Path(kwargs["output"]).write_text(
                    json.dumps(
                        {
                            "decision": "accept",
                            "accepted": True,
                            "reasons": [],
                        }
                    ),
                    encoding="utf-8",
                )
                Path(kwargs["markdown"]).write_text("# gate\n", encoding="utf-8")
                return {"decision": "accept", "accepted": True, "reasons": []}

            def passing_lucide(*args, **kwargs):
                self.assertEqual(args[0], lucide_suite)
                self.assertEqual(
                    kwargs["config_overrides"]["classifier_model"],
                    output_dir / "model.json",
                )
                report = {
                    "ok": True,
                    "case_count": 2,
                    "failed_count": 0,
                    "family_summary": {
                        "outline_circle": {
                            "case_count": 2,
                            "passed_count": 2,
                            "failed_count": 0,
                        }
                    },
                    "cases": [
                        {"id": "circle-a", "status": "checked", "ok": True},
                        {"id": "circle-b", "status": "checked", "ok": True},
                    ],
                }
                Path(kwargs["output"]).write_text(
                    json.dumps(report),
                    encoding="utf-8",
                )
                return report

            with (
                patch("morphea.self_learning.gate_training_comparison", accepted_gate),
                patch("morphea.self_learning.check_lucide_suite", passing_lucide),
            ):
                result = run_self_learning_cycle(
                    base_dataset=base_dir / "dataset.json",
                    reviewed_labels=reviewed,
                    output_dir=output_dir,
                    lucide_suite=lucide_suite,
                )

            self.assertTrue(result["accepted"])
            self.assertEqual(result["lucide_validation"]["status"], "checked")
            self.assertEqual(result["lucide_validation"]["checked_count"], 2)
            self.assertEqual(
                result["suite_family_validation"]["lucide"]["families"][0]["family"],
                "outline_circle",
            )
            self.assertTrue((output_dir / "lucide-validation.json").exists())

    def test_self_learning_cycle_requires_curated_validation_for_acceptance(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            base_dir = root / "base"
            reviewed = root / "reviewed.json"
            output_dir = root / "cycle"
            curated_suite = _write_curated_circle_suite(root)
            generate_synthetic_dataset(
                output_dir=base_dir,
                count=4,
                seed=101,
                width=64,
                height=64,
                val_count=1,
                test_count=1,
            )
            _write_reviewed_circle(reviewed)

            def accepted_gate(**kwargs):
                Path(kwargs["output"]).write_text(
                    json.dumps(
                        {
                            "decision": "accept",
                            "accepted": True,
                            "reasons": [],
                        }
                    ),
                    encoding="utf-8",
                )
                Path(kwargs["markdown"]).write_text("# gate\n", encoding="utf-8")
                return {"decision": "accept", "accepted": True, "reasons": []}

            def failing_curated(*args, **kwargs):
                output = kwargs.get("output")
                if output is not None:
                    Path(output).write_text(
                        json.dumps(
                            {
                                "ok": False,
                                "case_count": 1,
                                "cases": [
                                    {
                                        "id": "circle-case",
                                        "status": "checked",
                                        "ok": False,
                                    }
                                ],
                            }
                        ),
                        encoding="utf-8",
                    )
                return {
                    "ok": False,
                    "case_count": 1,
                    "cases": [
                        {
                            "id": "circle-case",
                            "status": "checked",
                            "ok": False,
                        }
                    ],
                }

            with (
                patch("morphea.self_learning.gate_training_comparison", accepted_gate),
                patch("morphea.self_learning.check_curated_suite", failing_curated),
            ):
                result = run_self_learning_cycle(
                    base_dataset=base_dir / "dataset.json",
                    reviewed_labels=reviewed,
                    output_dir=output_dir,
                    curated_suite=curated_suite,
                )

            self.assertEqual(result["status"], "retrained")
            self.assertFalse(result["accepted"])
            self.assertIn(
                "curated_validation_failed",
                result["acceptance_gate"]["reasons"],
            )
            self.assertTrue((output_dir / "model.json").exists())

    def test_self_learning_cycle_requires_lucide_validation_for_acceptance(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            base_dir = root / "base"
            reviewed = root / "reviewed.json"
            output_dir = root / "cycle"
            lucide_suite = root / "lucide-suite.json"
            generate_synthetic_dataset(
                output_dir=base_dir,
                count=4,
                seed=103,
                width=64,
                height=64,
                val_count=1,
                test_count=1,
            )
            _write_reviewed_circle(reviewed)

            def accepted_gate(**kwargs):
                Path(kwargs["output"]).write_text(
                    json.dumps(
                        {
                            "decision": "accept",
                            "accepted": True,
                            "reasons": [],
                        }
                    ),
                    encoding="utf-8",
                )
                Path(kwargs["markdown"]).write_text("# gate\n", encoding="utf-8")
                return {"decision": "accept", "accepted": True, "reasons": []}

            def failing_lucide(*args, **kwargs):
                report = {
                    "ok": False,
                    "case_count": 1,
                    "failed_count": 1,
                    "family_summary": {
                        "outline_circle": {
                            "case_count": 1,
                            "passed_count": 0,
                            "failed_count": 1,
                        }
                    },
                    "cases": [
                        {"id": "circle-a", "status": "checked", "ok": False},
                    ],
                }
                Path(kwargs["output"]).write_text(
                    json.dumps(report),
                    encoding="utf-8",
                )
                return report

            with (
                patch("morphea.self_learning.gate_training_comparison", accepted_gate),
                patch("morphea.self_learning.check_lucide_suite", failing_lucide),
            ):
                result = run_self_learning_cycle(
                    base_dataset=base_dir / "dataset.json",
                    reviewed_labels=reviewed,
                    output_dir=output_dir,
                    lucide_suite=lucide_suite,
                )

            self.assertFalse(result["accepted"])
            self.assertIn(
                "lucide_validation_failed",
                result["acceptance_gate"]["reasons"],
            )
            self.assertEqual(
                result["suite_family_validation"]["lucide"]["families"][0]["outcome"],
                "failed",
            )

    def test_self_learning_cycle_allows_known_suite_baseline_debt(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            base_dir = root / "base"
            reviewed = root / "reviewed.json"
            output_dir = root / "cycle"
            lucide_suite = root / "lucide-suite.json"
            baseline = root / "suite-family-baseline.json"
            generate_synthetic_dataset(
                output_dir=base_dir,
                count=4,
                seed=109,
                width=64,
                height=64,
                val_count=1,
                test_count=1,
            )
            _write_reviewed_circle(reviewed)
            baseline.write_text(
                json.dumps(
                    {
                        "suite_family_validation": {
                            "primitive": {"families": []},
                            "real_image": {"families": []},
                            "lucide": {
                                "status": "checked",
                                "ok": False,
                                "families": [
                                    {
                                        "family": "outline_circle",
                                        "outcome": "failed",
                                    }
                                ],
                            },
                        }
                    }
                ),
                encoding="utf-8",
            )

            def accepted_gate(**kwargs):
                Path(kwargs["output"]).write_text(
                    json.dumps(
                        {
                            "decision": "accept",
                            "accepted": True,
                            "reasons": [],
                        }
                    ),
                    encoding="utf-8",
                )
                Path(kwargs["markdown"]).write_text("# gate\n", encoding="utf-8")
                return {"decision": "accept", "accepted": True, "reasons": []}

            def failing_lucide(*args, **kwargs):
                report = {
                    "ok": False,
                    "case_count": 1,
                    "failed_count": 1,
                    "family_summary": {
                        "outline_circle": {
                            "case_count": 1,
                            "passed_count": 0,
                            "failed_count": 1,
                        }
                    },
                    "cases": [
                        {"id": "circle-a", "status": "checked", "ok": False},
                    ],
                }
                Path(kwargs["output"]).write_text(
                    json.dumps(report),
                    encoding="utf-8",
                )
                return report

            with (
                patch("morphea.self_learning.gate_training_comparison", accepted_gate),
                patch("morphea.self_learning.check_lucide_suite", failing_lucide),
            ):
                result = run_self_learning_cycle(
                    base_dataset=base_dir / "dataset.json",
                    reviewed_labels=reviewed,
                    output_dir=output_dir,
                    lucide_suite=lucide_suite,
                    suite_family_baseline=baseline,
                )

            self.assertTrue(result["accepted"])
            self.assertEqual(
                result["suite_family_baseline_comparison"]["ok"],
                True,
            )
            comparison = result["suite_family_baseline_comparison"]
            self.assertEqual(comparison["new_regression_count"], 0)
            self.assertEqual(comparison["known_debt_count"], 1)
            self.assertEqual(comparison["resolved_regression_count"], 0)
            self.assertEqual(comparison["known_debt"][0]["suite"], "lucide")
            self.assertEqual(
                comparison["known_debt"][0]["family"],
                "outline_circle",
            )
            self.assertEqual(
                comparison["known_debt"][0]["baseline_outcome"],
                "failed",
            )
            self.assertEqual(
                comparison["known_debt"][0]["current_outcome"],
                "failed",
            )
            self.assertIn(
                "lucide_validation_known_baseline_debt",
                result["acceptance_gate"]["reasons"],
            )
            self.assertEqual(result["acceptance_gate"]["blocking_reasons"], [])

    def test_self_learning_cycle_blocks_new_suite_family_baseline_regression(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            base_dir = root / "base"
            reviewed = root / "reviewed.json"
            output_dir = root / "cycle"
            baseline = root / "suite-family-baseline.json"
            generate_synthetic_dataset(
                output_dir=base_dir,
                count=4,
                seed=104,
                width=64,
                height=64,
                val_count=1,
                test_count=1,
            )
            _write_reviewed_circle(reviewed)
            baseline.write_text(
                json.dumps(
                    {
                        "suite_family_validation": {
                            "primitive": {
                                "status": "held",
                                "ok": True,
                                "families": [
                                    {
                                        "split": "val",
                                        "family": "circle",
                                        "outcome": "held",
                                    }
                                ],
                            },
                            "real_image": {
                                "status": "checked",
                                "families": [
                                    {
                                        "family": "known_debt",
                                        "outcome": "failed",
                                    }
                                ],
                            },
                            "lucide": {"status": "not_configured", "families": []},
                        }
                    }
                ),
                encoding="utf-8",
            )

            def regressed_comparison(**kwargs):
                report = {
                    "schema_version": 1,
                    "summary": {
                        "status": "mixed",
                        "train_examples_delta": 1,
                        "best_accuracy_delta": 0.1,
                        "worst_accuracy_delta": -1.0,
                    },
                    "delta": {
                        "label_accuracy": {
                            "val": {
                                "circle": {
                                    "baseline_accuracy": 1.0,
                                    "augmented_accuracy": 0.0,
                                    "accuracy_delta": -1.0,
                                }
                            }
                        }
                    },
                }
                Path(kwargs["output"]).write_text(
                    json.dumps(report),
                    encoding="utf-8",
                )
                Path(kwargs["markdown"]).write_text("# comparison\n", encoding="utf-8")
                return report

            def accepted_gate(**kwargs):
                Path(kwargs["output"]).write_text(
                    json.dumps(
                        {
                            "decision": "accept",
                            "accepted": True,
                            "reasons": [],
                        }
                    ),
                    encoding="utf-8",
                )
                Path(kwargs["markdown"]).write_text("# gate\n", encoding="utf-8")
                return {"decision": "accept", "accepted": True, "reasons": []}

            with (
                patch("morphea.self_learning.compare_retraining", regressed_comparison),
                patch("morphea.self_learning.gate_training_comparison", accepted_gate),
            ):
                result = run_self_learning_cycle(
                    base_dataset=base_dir / "dataset.json",
                    reviewed_labels=reviewed,
                    output_dir=output_dir,
                    suite_family_baseline=baseline,
                )

            self.assertFalse(result["accepted"])
            self.assertIn(
                "suite_family_baseline_regressed",
                result["acceptance_gate"]["reasons"],
            )
            comparison = result["suite_family_baseline_comparison"]
            self.assertEqual(comparison["new_regression_count"], 1)
            self.assertEqual(comparison["resolved_regression_count"], 1)
            self.assertEqual(comparison["known_debt_count"], 0)
            self.assertEqual(
                comparison["new_regressions"][0]["current_outcome"],
                "regressed",
            )
            self.assertIsNone(
                comparison["resolved_regressions"][0]["current_outcome"],
            )

    def test_self_learning_cycle_writes_accepted_suite_family_baseline_snapshot(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            base_dir = root / "base"
            reviewed = root / "reviewed.json"
            output_dir = root / "cycle"
            baseline_output = root / "accepted-suite-family-baseline.json"
            changelog = root / "suite-family-baseline-changelog.jsonl"
            generate_synthetic_dataset(
                output_dir=base_dir,
                count=4,
                seed=105,
                width=64,
                height=64,
                val_count=1,
                test_count=1,
            )
            _write_reviewed_circle(reviewed)

            def accepted_gate(**kwargs):
                Path(kwargs["output"]).write_text(
                    json.dumps(
                        {
                            "decision": "accept",
                            "accepted": True,
                            "reasons": [],
                        }
                    ),
                    encoding="utf-8",
                )
                Path(kwargs["markdown"]).write_text("# gate\n", encoding="utf-8")
                return {"decision": "accept", "accepted": True, "reasons": []}

            with patch("morphea.self_learning.gate_training_comparison", accepted_gate):
                result = run_self_learning_cycle(
                    base_dataset=base_dir / "dataset.json",
                    reviewed_labels=reviewed,
                    output_dir=output_dir,
                    suite_family_baseline_output=baseline_output,
                    suite_family_baseline_reviewer="qa",
                    suite_family_baseline_reason="accepted family validation",
                    suite_family_baseline_changelog=changelog,
                )

            self.assertTrue(result["accepted"])
            self.assertEqual(
                result["suite_family_baseline_snapshot"]["status"],
                "written",
            )
            self.assertEqual(
                result["artifacts"]["suite_family_baseline_snapshot"],
                str(baseline_output),
            )
            snapshot = json.loads(baseline_output.read_text(encoding="utf-8"))
            self.assertEqual(snapshot["source"], "self_learning_cycle")
            self.assertTrue(snapshot["accepted"])
            self.assertEqual(snapshot["review"]["reviewer"], "qa")
            self.assertEqual(
                snapshot["review"]["reason"],
                "accepted family validation",
            )
            self.assertIn("suite_family_validation", snapshot)
            volatile_snapshot_fields = {
                "base_dataset",
                "reviewed_labels",
                "source_cycle",
                "validation_dataset",
            }
            self.assertTrue(
                volatile_snapshot_fields.isdisjoint(snapshot),
            )
            self.assertTrue(
                baseline_output.read_text(encoding="utf-8").endswith("\n"),
            )
            changelog_entries = [
                json.loads(line)
                for line in changelog.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(len(changelog_entries), 1)
            self.assertEqual(
                changelog_entries[0]["action"],
                "suite_family_baseline_updated",
            )
            self.assertEqual(
                changelog_entries[0]["baseline_snapshot"],
                str(baseline_output),
            )
            self.assertEqual(changelog_entries[0]["review"]["reviewer"], "qa")
            self.assertTrue(
                volatile_snapshot_fields.isdisjoint(changelog_entries[0]),
            )

    def test_self_learning_cycle_requires_review_evidence_for_baseline_snapshot(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            base_dir = root / "base"
            reviewed = root / "reviewed.json"
            output_dir = root / "cycle"
            baseline_output = root / "accepted-suite-family-baseline.json"
            generate_synthetic_dataset(
                output_dir=base_dir,
                count=4,
                seed=106,
                width=64,
                height=64,
                val_count=1,
                test_count=1,
            )
            _write_reviewed_circle(reviewed)

            def accepted_gate(**kwargs):
                Path(kwargs["output"]).write_text(
                    json.dumps(
                        {
                            "decision": "accept",
                            "accepted": True,
                            "reasons": [],
                        }
                    ),
                    encoding="utf-8",
                )
                Path(kwargs["markdown"]).write_text("# gate\n", encoding="utf-8")
                return {"decision": "accept", "accepted": True, "reasons": []}

            with patch("morphea.self_learning.gate_training_comparison", accepted_gate):
                result = run_self_learning_cycle(
                    base_dataset=base_dir / "dataset.json",
                    reviewed_labels=reviewed,
                    output_dir=output_dir,
                    suite_family_baseline_output=baseline_output,
                )

            self.assertTrue(result["accepted"])
            snapshot = result["suite_family_baseline_snapshot"]
            self.assertEqual(snapshot["status"], "skipped_missing_review_evidence")
            self.assertEqual(
                snapshot["missing_review_fields"],
                ["reviewer", "reason", "changelog"],
            )
            self.assertFalse(baseline_output.exists())

    def test_self_learning_cycle_refuses_accidental_baseline_overwrite(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            base_dir = root / "base"
            reviewed = root / "reviewed.json"
            output_dir = root / "cycle"
            baseline_output = root / "checked-in-baseline.json"
            changelog = root / "suite-family-baseline-changelog.jsonl"
            baseline_output.write_text(
                json.dumps({"sentinel": "do-not-overwrite"}),
                encoding="utf-8",
            )
            generate_synthetic_dataset(
                output_dir=base_dir,
                count=4,
                seed=107,
                width=64,
                height=64,
                val_count=1,
                test_count=1,
            )
            _write_reviewed_circle(reviewed)

            def accepted_gate(**kwargs):
                Path(kwargs["output"]).write_text(
                    json.dumps(
                        {
                            "decision": "accept",
                            "accepted": True,
                            "reasons": [],
                        }
                    ),
                    encoding="utf-8",
                )
                Path(kwargs["markdown"]).write_text("# gate\n", encoding="utf-8")
                return {"decision": "accept", "accepted": True, "reasons": []}

            with patch("morphea.self_learning.gate_training_comparison", accepted_gate):
                result = run_self_learning_cycle(
                    base_dataset=base_dir / "dataset.json",
                    reviewed_labels=reviewed,
                    output_dir=output_dir,
                    suite_family_baseline_output=baseline_output,
                    suite_family_baseline_reviewer="qa",
                    suite_family_baseline_reason="accidental overwrite guard",
                    suite_family_baseline_changelog=changelog,
                )

            self.assertTrue(result["accepted"])
            snapshot = result["suite_family_baseline_snapshot"]
            self.assertEqual(
                snapshot["status"],
                "skipped_existing_output_requires_matching_baseline",
            )
            self.assertEqual(
                json.loads(baseline_output.read_text(encoding="utf-8")),
                {"sentinel": "do-not-overwrite"},
            )
            self.assertFalse(changelog.exists())

    def test_self_learning_cycle_skips_curated_validation_without_model(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            base_dir = root / "base"
            reviewed = root / "reviewed.json"
            output_dir = root / "cycle"
            curated_suite = _write_curated_circle_suite(root)
            generate_synthetic_dataset(
                output_dir=base_dir,
                count=4,
                seed=99,
                width=64,
                height=64,
                val_count=1,
                test_count=1,
            )
            _write_reviewed_circle(reviewed)

            result = run_self_learning_cycle(
                base_dataset=base_dir / "dataset.json",
                reviewed_labels=reviewed,
                output_dir=output_dir,
                curated_suite=curated_suite,
                min_train_examples_delta=10,
            )

            self.assertEqual(result["status"], "skipped_retrain")
            self.assertFalse(result["accepted"])
            self.assertIn(
                "training_gate_not_accepted",
                result["acceptance_gate"]["reasons"],
            )
            self.assertEqual(
                result["curated_validation"]["status"],
                "skipped_gate_not_accepted",
            )
            self.assertFalse((output_dir / "curated-validation.json").exists())

    def test_render_self_learning_cycle_markdown_summarizes_artifacts(self):
        markdown = render_self_learning_cycle_markdown(
            {
                "status": "skipped_retrain",
                "accepted": False,
                "pseudo_dataset": {
                    "count": 2,
                    "reviewed_label_summary": {
                        "applied_review_decision_counts": {"accepted": 1},
                    },
                },
                "comparison_summary": {
                    "status": "mixed",
                    "best_accuracy_delta": 0.1,
                    "worst_accuracy_delta": -0.1,
                },
                "gate": {
                    "decision": "manual_review",
                    "accepted": False,
                    "reasons": ["comparison_status_mixed"],
                },
                "acceptance_gate": {
                    "accepted": False,
                    "reasons": ["training_gate_not_accepted"],
                    "blocking_reasons": ["training_gate_not_accepted"],
                },
                "artifacts": {
                    "comparison": "comparison.json",
                    "gate": "gate.json",
                },
                "suite_family_validation": {
                    "primitive": {
                        "status": "improved",
                        "ok": True,
                        "families": [
                            {
                                "split": "val",
                                "family": "circle",
                                "baseline_accuracy": 0.5,
                                "augmented_accuracy": 1.0,
                                "accuracy_delta": 0.5,
                                "outcome": "improved",
                            }
                        ],
                    },
                    "real_image": {
                        "status": "checked",
                        "ok": True,
                        "families": [
                            {
                                "family": "generated_table",
                                "case_count": 2,
                                "checked_count": 2,
                                "passed_count": 2,
                                "failed_count": 0,
                                "missing_source_count": 0,
                                "outcome": "passed",
                            }
                        ],
                    },
                    "lucide": {
                        "status": "not_configured",
                        "ok": None,
                        "families": [],
                    },
                },
                "suite_family_baseline_comparison": {
                    "status": "checked",
                    "baseline": "baseline.json",
                    "ok": False,
                    "new_regression_count": 1,
                    "known_debt_count": 1,
                    "resolved_regression_count": 0,
                    "new_regressions": [
                        {
                            "suite": "primitive",
                            "split": "val",
                            "family": "circle",
                            "baseline_outcome": "held",
                            "current_outcome": "regressed",
                            "accuracy_delta": -0.25,
                        }
                    ],
                    "known_debt": [
                        {
                            "suite": "lucide",
                            "split": "",
                            "family": "circle_compound_strokes",
                            "baseline_outcome": "failed",
                            "current_outcome": "failed",
                            "case_count": 8,
                            "failed_count": 1,
                            "missing_source_count": 0,
                        }
                    ],
                    "resolved_regressions": [],
                },
                "suite_family_baseline_snapshot": {
                    "status": "skipped_not_accepted",
                    "output": "next-baseline.json",
                },
            }
        )

        self.assertIn("# Morphēa Self-Learning Cycle", markdown)
        self.assertIn("- Status: `skipped_retrain`", markdown)
        self.assertIn("- Accepted: `False`", markdown)
        self.assertIn("`training_gate_not_accepted`", markdown)
        self.assertIn("- Blocking acceptance reasons: `training_gate_not_accepted`", markdown)
        self.assertIn("- Applied review decisions: `accepted: 1`", markdown)
        self.assertIn("## Suite Family Validation", markdown)
        self.assertIn(
            "| `primitive` | `improved` | `True` | `circle` |",
            markdown,
        )
        self.assertIn(
            "| `real_image` | `checked` | `True` | `generated_table` |",
            markdown,
        )
        self.assertIn(
            "| `lucide` | `not_configured` | `None` | n/a | n/a | n/a |",
            markdown,
        )
        self.assertIn("## Suite Family Baseline", markdown)
        self.assertIn("- New regressions: 1", markdown)
        self.assertIn("- Known debt: 1", markdown)
        self.assertIn(
            "| `new_regression` | `primitive` | `val` | `circle` | `held` | `regressed` | delta=-0.25 |",
            markdown,
        )
        self.assertIn(
            "| `known_debt` | `lucide` | `n/a` | `circle_compound_strokes` | `failed` | `failed` | cases=8, failed=1, missing=0 |",
            markdown,
        )
        self.assertIn("## Suite Family Baseline Snapshot", markdown)
        self.assertIn("- Status: `skipped_not_accepted`", markdown)
        self.assertIn("| `gate` | `gate.json` |", markdown)
        self.assertIn("`comparison_status_mixed`", markdown)

    def test_self_learn_cli_accepts_config_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            base_dir = root / "base"
            reviewed = root / "reviewed.json"
            output_dir = root / "cycle"
            config = root / "self-learn.json"
            markdown = root / "cycle.md"
            suite_family_baseline = root / "suite-family-baseline.json"
            suite_family_baseline_output = root / "next-suite-family-baseline.json"
            suite_family_baseline_changelog = root / "suite-family-changelog.jsonl"
            curated_suite = _write_curated_circle_suite(root)
            generate_synthetic_dataset(
                output_dir=base_dir,
                count=4,
                seed=97,
                width=64,
                height=64,
                val_count=1,
                test_count=1,
            )
            _write_reviewed_circle(reviewed)
            suite_family_baseline.write_text(
                json.dumps(
                    {
                        "suite_family_validation": {
                            "primitive": {"families": []},
                            "real_image": {"families": []},
                            "lucide": {"families": []},
                        }
                    }
                ),
                encoding="utf-8",
            )
            config.write_text(
                json.dumps(
                    {
                        "base_dataset": str(base_dir / "dataset.json"),
                        "reviewed_labels": str(reviewed),
                        "output_dir": str(output_dir),
                        "markdown": str(markdown),
                        "curated_suite": str(curated_suite),
                        "lucide_suite": str(root / "lucide-suite.json"),
                        "lucide_output_dir": str(root / "lucide-runs"),
                        "lucide_report": str(root / "lucide-report.json"),
                        "suite_family_baseline": str(suite_family_baseline),
                        "suite_family_baseline_output": str(
                            suite_family_baseline_output
                        ),
                        "suite_family_baseline_reviewer": "qa",
                        "suite_family_baseline_reason": "config smoke review",
                        "suite_family_baseline_changelog": str(
                            suite_family_baseline_changelog
                        ),
                        "min_train_examples_delta": 10,
                        "max_worst_accuracy_drop": 1.0,
                        "allow_unchanged": True,
                    }
                ),
                encoding="utf-8",
            )

            with redirect_stdout(StringIO()):
                main(["self-learn", "--config", str(config)])

            result = json.loads(
                (output_dir / "self-learning-cycle.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertIn(result["status"], {"retrained", "skipped_retrain"})
            self.assertTrue(markdown.exists())
            self.assertEqual(
                result["artifacts"]["summary_markdown"],
                str(markdown),
            )
            self.assertEqual(
                result["curated_validation"]["status"],
                "skipped_gate_not_accepted",
            )
            self.assertEqual(
                result["lucide_validation"]["status"],
                "skipped_gate_not_accepted",
            )
            self.assertEqual(
                result["suite_family_baseline_comparison"]["status"],
                "checked",
            )
            self.assertEqual(
                result["suite_family_baseline_snapshot"]["status"],
                "skipped_not_accepted",
            )
            self.assertFalse(suite_family_baseline_output.exists())
            self.assertFalse(suite_family_baseline_changelog.exists())

    def test_self_learn_cli_smokes_checked_in_suite_family_baseline(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            base_dir = root / "base"
            reviewed = root / "reviewed.json"
            output_dir = root / "cycle"
            baseline = Path(
                "docs/real-images/baselines/current-suite-family-baseline.json"
            )
            generate_synthetic_dataset(
                output_dir=base_dir,
                count=4,
                seed=108,
                width=64,
                height=64,
                val_count=1,
                test_count=1,
            )
            _write_reviewed_circle(reviewed)

            with redirect_stdout(StringIO()):
                main(
                    [
                        "self-learn",
                        str(base_dir / "dataset.json"),
                        "--reviewed-labels",
                        str(reviewed),
                        "-o",
                        str(output_dir),
                        "--suite-family-baseline",
                        str(baseline),
                        "--min-train-examples-delta",
                        "10",
                    ]
                )

            result = json.loads(
                (output_dir / "self-learning-cycle.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(
                result["suite_family_baseline_comparison"]["status"],
                "checked",
            )
            self.assertEqual(
                result["suite_family_baseline_comparison"]["baseline"],
                str(baseline),
            )

    def test_retrain_centroid_classifier_writes_augmented_model(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            base_dir = root / "base"
            pseudo_dir = root / "pseudo"
            reviewed = root / "reviewed.json"
            model_path = root / "model.json"
            compare_path = root / "compare.json"
            generate_synthetic_dataset(
                output_dir=base_dir,
                count=4,
                seed=93,
                width=64,
                height=64,
                val_count=1,
                test_count=1,
            )
            _write_reviewed_circle(reviewed)
            merge_reviewed_pseudo_label_dataset(
                reviewed_labels=reviewed,
                output_dir=pseudo_dir,
            )

            model = retrain_centroid_classifier(
                base_dataset=base_dir / "dataset.json",
                pseudo_dataset=pseudo_dir / "dataset.json",
                output=model_path,
                comparison_output=compare_path,
            )

            self.assertTrue(model_path.exists())
            self.assertTrue(compare_path.exists())
            self.assertEqual(model["augmentation"]["pseudo_train_examples"], 1)
            self.assertEqual(
                model["train_examples"],
                model["augmentation"]["base_train_examples"] + 1,
            )
            self.assertIn("evaluation", model)
            self.assertIn("ranking_evaluation", model)
            self.assertIn("feature_importance", model)
            self.assertEqual(
                model["source_datasets"]["pseudo_dataset"],
                str(pseudo_dir / "dataset.json"),
            )

    def test_retrain_mlx_classifier_writes_augmented_model(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            base_dir = root / "base"
            pseudo_dir = root / "pseudo"
            reviewed = root / "reviewed.json"
            model_path = root / "mlx-model.json"
            compare_path = root / "compare.json"
            generate_synthetic_dataset(
                output_dir=base_dir,
                count=4,
                seed=94,
                width=64,
                height=64,
                val_count=1,
                test_count=1,
            )
            _write_reviewed_circle(reviewed)
            merge_reviewed_pseudo_label_dataset(
                reviewed_labels=reviewed,
                output_dir=pseudo_dir,
            )
            mlx_module = types.ModuleType("mlx")
            mlx_core = types.ModuleType("mlx.core")
            mlx_core.__version__ = "test-mlx"
            mlx_module.core = mlx_core

            with (
                patch("morphea.mlx_classifier.is_mlx_available", return_value=True),
                patch.dict(sys.modules, {"mlx": mlx_module, "mlx.core": mlx_core}),
            ):
                model = retrain_mlx_classifier(
                    base_dataset=base_dir / "dataset.json",
                    pseudo_dataset=pseudo_dir / "dataset.json",
                    output=model_path,
                    comparison_output=compare_path,
                    config=MlxClassifierTrainingConfig(epochs=1, crop_size=6),
                )

            augmented_dataset = Path(model["source_datasets"]["augmented_dataset"])
            self.assertTrue(model_path.exists())
            self.assertTrue(compare_path.exists())
            self.assertTrue(augmented_dataset.exists())
            self.assertEqual(model["model_type"], "mlx_transformer_primitive_classifier")
            self.assertEqual(model["retraining_backend"], "mlx")
            self.assertEqual(model["augmentation"]["pseudo_train_examples"], 1)
            self.assertIn("feature_importance", model)
            self.assertEqual(
                model["train_examples"],
                model["augmentation"]["base_train_examples"] + 1,
            )
            self.assertEqual(
                model["source_datasets"]["pseudo_dataset"],
                str(pseudo_dir / "dataset.json"),
            )
            self.assertIn("token_transformer", model["mlx_training"])

    def test_retrain_cli_accepts_config_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            base_dir = root / "base"
            pseudo_dir = root / "pseudo"
            reviewed = root / "reviewed.json"
            model_path = root / "model.json"
            compare_path = root / "compare.json"
            config = root / "retrain.json"
            generate_synthetic_dataset(
                output_dir=base_dir,
                count=4,
                seed=94,
                width=64,
                height=64,
                val_count=1,
                test_count=1,
            )
            _write_reviewed_circle(reviewed)
            merge_reviewed_pseudo_label_dataset(
                reviewed_labels=reviewed,
                output_dir=pseudo_dir,
            )
            config.write_text(
                json.dumps(
                    {
                        "base_dataset": str(base_dir / "dataset.json"),
                        "pseudo_dataset": str(pseudo_dir / "dataset.json"),
                        "output": str(model_path),
                        "comparison_output": str(compare_path),
                    }
                ),
                encoding="utf-8",
            )

            with redirect_stdout(StringIO()):
                main(["retrain", "--config", str(config)])

            model = json.loads(model_path.read_text(encoding="utf-8"))
            comparison = json.loads(compare_path.read_text(encoding="utf-8"))
            self.assertEqual(model["augmentation"]["pseudo_train_examples"], 1)
            self.assertEqual(comparison["delta"]["train_examples"], 1)

    def test_retrain_cli_accepts_mlx_backend_config(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            base_dir = root / "base"
            pseudo_dir = root / "pseudo"
            reviewed = root / "reviewed.json"
            model_path = root / "mlx-model.json"
            config = root / "retrain-mlx.json"
            generate_synthetic_dataset(
                output_dir=base_dir,
                count=4,
                seed=95,
                width=64,
                height=64,
                val_count=1,
                test_count=1,
            )
            _write_reviewed_circle(reviewed)
            merge_reviewed_pseudo_label_dataset(
                reviewed_labels=reviewed,
                output_dir=pseudo_dir,
            )
            config.write_text(
                json.dumps(
                    {
                        "backend": "mlx",
                        "base_dataset": str(base_dir / "dataset.json"),
                        "pseudo_dataset": str(pseudo_dir / "dataset.json"),
                        "output": str(model_path),
                        "epochs": 1,
                        "crop_size": 6,
                        "allow_unavailable": True,
                    }
                ),
                encoding="utf-8",
            )

            with redirect_stdout(StringIO()):
                main(["retrain", "--config", str(config)])

            model = json.loads(model_path.read_text(encoding="utf-8"))
            self.assertEqual(model["model_type"], "mlx_transformer_primitive_classifier")
            self.assertEqual(model["retraining_backend"], "mlx")
            self.assertEqual(model["augmentation"]["pseudo_train_examples"], 1)
            self.assertIn("augmented_dataset", model["source_datasets"])


def _write_manifest(
    root: Path,
    run_name: str,
    *,
    diagnostics: list[dict[str, object]],
    classifier_error: float,
    editability_score: float = 1.0,
    fragmentation_penalty: float = 0.0,
    raster_l1_error: float = 0.0,
    raster_edge_error: float = 0.0,
    anchor_metrics: dict[str, float] | None = None,
    groups: list[dict[str, object]] | None = None,
    applied_review: dict[str, object] | None = None,
) -> None:
    run_dir = root / run_name
    run_dir.mkdir(parents=True)
    metrics = {"classifier_prior_error": classifier_error}
    if anchor_metrics is not None:
        metrics.update(anchor_metrics)
    manifest = {
        "anchors": [
            {
                "kind": "circle",
                "color": "#dd2222",
                "metrics": metrics,
            }
        ],
        "diagnostics": diagnostics,
        "groups": groups or [],
        "metrics": {
            "editability_score": editability_score,
            "fragmentation_penalty": fragmentation_penalty,
            "raster_l1_error": raster_l1_error,
            "raster_edge_error": raster_edge_error,
        },
    }
    if applied_review is not None:
        manifest["review_decision_applied"] = applied_review
    (run_dir / "manifest.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )


def _write_reviewed_circle(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "accepted": [
                    {
                        "kind": "circle",
                        "anchor": {
                            "kind": "circle",
                            "node_count": 1,
                            "parameter_count": 3,
                            "circle": {"cx": 5, "cy": 5, "r": 3},
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )


def _write_training_comparison(
    path: Path,
    *,
    status: str,
    train_delta: int,
    best_delta: float | None,
    worst_delta: float | None,
) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "summary": {
                    "status": status,
                    "train_examples_delta": train_delta,
                    "best_accuracy_delta": best_delta,
                    "worst_accuracy_delta": worst_delta,
                },
            }
        ),
        encoding="utf-8",
    )


def _write_curated_circle_suite(root: Path) -> Path:
    source = root / "circle.png"
    image = Image.new("RGB", (32, 32), "white")
    draw = ImageDraw.Draw(image)
    draw.ellipse((8, 8, 23, 23), fill="#c08011")
    image.save(source)
    suite = root / "suite.json"
    suite.write_text(
        json.dumps(
            {
                "version": 1,
                "cases": [
                    {
                        "id": "circle-case",
                        "source": str(source),
                        "recommended_config": {
                            "min_area": 4,
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
    return suite


if __name__ == "__main__":
    unittest.main()
