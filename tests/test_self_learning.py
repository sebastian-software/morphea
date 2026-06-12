import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from PIL import Image, ImageDraw

from curve.cli import main
from curve.classifier import examples_from_dataset
from curve.dataset import generate_synthetic_dataset
from curve.self_learning import (
    apply_review_file,
    compare_retraining,
    create_review_file,
    harvest_curated_pseudo_labels,
    harvest_pseudo_labels,
    merge_reviewed_pseudo_label_dataset,
    render_apply_review_markdown,
    render_harvest_markdown,
    render_review_markdown,
    render_training_comparison_markdown,
    retrain_centroid_classifier,
)


class SelfLearningTests(unittest.TestCase):
    def test_harvest_pseudo_labels_accepts_clean_run_anchors(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "runs"
            _write_manifest(root, "clean", diagnostics=[], classifier_error=0.0)
            output = Path(temp_dir) / "pseudo.json"

            result = harvest_pseudo_labels(run_root=root, output=output)

            self.assertEqual(result["pseudo_label_count"], 1)
            self.assertEqual(result["pseudo_labels"][0]["kind"], "circle")
            self.assertEqual(result["pseudo_labels"][0]["anchor"]["kind"], "circle")
            self.assertEqual(result["pseudo_labels"][0]["run_metrics"]["editability_score"], 1.0)
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

        self.assertIn("# Curve Pseudo-Label Harvest", markdown)
        self.assertIn("| `min_editability_score` | 0.8 |", markdown)
        self.assertIn("| `clean` | 0 | `circle` | 0.02 |", markdown)
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
                "# Curve Pseudo-Label Harvest",
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
                "# Curve Pseudo-Label Harvest",
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
                "# Curve Pseudo-Label Harvest",
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
                "Curve Pseudo-Label Harvest",
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
            self.assertEqual(review["items"][0]["decision"], "pending")
            self.assertEqual(review["items"][0]["corrected_kind"], "")
            self.assertEqual(review["items"][0]["issues"], [])
            self.assertTrue(output.exists())

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
                        },
                    }
                ],
            }
        )

        self.assertIn("# Curve Review Queue", markdown)
        self.assertIn("- Source: `pseudo.json`", markdown)
        self.assertIn(
            "| `review-00000` | `pending` | `circle` | 0.03 | bad_cutout |",
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
                "# Curve Review Queue",
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
                                "label": {"kind": "circle"},
                            },
                            {
                                "id": "review-00001",
                                "decision": "reject",
                                "reason": "wrong type",
                                "label": {"kind": "quad"},
                            },
                            {
                                "id": "review-00002",
                                "decision": "pending",
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

    def test_render_apply_review_markdown_summarizes_decisions(self):
        markdown = render_apply_review_markdown(
            {
                "source_review": "review.json",
                "accepted_count": 1,
                "rejected_count": 1,
                "pending_count": 1,
                "accepted": [
                    {
                        "kind": "stroke_polyline",
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
                    }
                ],
                "pending": ["review-00002"],
            }
        )

        self.assertIn("# Curve Apply Review", markdown)
        self.assertIn("- Accepted: 1", markdown)
        self.assertIn(
            "| `stroke_polyline` | `stroke_polyline` | wrong_primitive_type |",
            markdown,
        )
        self.assertIn("| `review-00001` | bad cutout | bad_cutout |", markdown)
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
                "# Curve Apply Review",
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
                "# Curve Review Queue",
                markdown.read_text(encoding="utf-8"),
            )
            self.assertIn(
                "# Curve Apply Review",
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
                "# Curve Review Queue",
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
                "# Curve Apply Review",
                markdown.read_text(encoding="utf-8"),
            )

    def test_merge_reviewed_pseudo_labels_writes_trainable_dataset(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            runs = root / "runs"
            _write_manifest(runs, "clean", diagnostics=[], classifier_error=0.0)
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
            self.assertIn("ranking_evaluation", result["delta"])
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
                "delta": {"evaluation": {"val": 0.1}},
            }
        )

        self.assertIn("# Curve Training Comparison", markdown)
        self.assertIn("- Status: `improved`", markdown)
        self.assertIn("| `val` | 0.5 | 0.6 | 0.1 |", markdown)

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
                "# Curve Training Comparison",
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
            self.assertEqual(
                model["source_datasets"]["pseudo_dataset"],
                str(pseudo_dir / "dataset.json"),
            )

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
) -> None:
    run_dir = root / run_name
    run_dir.mkdir(parents=True)
    metrics = {"classifier_prior_error": classifier_error}
    if anchor_metrics is not None:
        metrics.update(anchor_metrics)
    (run_dir / "manifest.json").write_text(
        json.dumps(
            {
                "anchors": [
                    {
                        "kind": "circle",
                        "color": "#dd2222",
                        "metrics": metrics,
                    }
                ],
                "diagnostics": diagnostics,
                "metrics": {
                    "editability_score": editability_score,
                    "fragmentation_penalty": fragmentation_penalty,
                    "raster_l1_error": raster_l1_error,
                    "raster_edge_error": raster_edge_error,
                },
            }
        ),
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
