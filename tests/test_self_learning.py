import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from curve.cli import main
from curve.self_learning import apply_review_file, create_review_file, harvest_pseudo_labels


class SelfLearningTests(unittest.TestCase):
    def test_harvest_pseudo_labels_accepts_clean_run_anchors(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "runs"
            _write_manifest(root, "clean", diagnostics=[], classifier_error=0.0)
            output = Path(temp_dir) / "pseudo.json"

            result = harvest_pseudo_labels(run_root=root, output=output)

            self.assertEqual(result["pseudo_label_count"], 1)
            self.assertEqual(result["pseudo_labels"][0]["kind"], "circle")
            self.assertEqual(result["pseudo_labels"][0]["run_metrics"]["editability_score"], 1.0)
            self.assertTrue(output.exists())

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

    def test_harvest_cli_writes_output(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "runs"
            _write_manifest(root, "clean", diagnostics=[], classifier_error=0.0)
            output = Path(temp_dir) / "pseudo.json"

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
                    ]
                )

            result = json.loads(output.read_text())
            self.assertEqual(result["pseudo_label_count"], 1)
            self.assertEqual(result["filters"]["min_editability_score"], 0.8)

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
            self.assertTrue(output.exists())

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

    def test_review_cli_roundtrip(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pseudo = Path(temp_dir) / "pseudo.json"
            pseudo.write_text(
                json.dumps({"pseudo_labels": [{"kind": "circle"}]}),
                encoding="utf-8",
            )
            review = Path(temp_dir) / "review.json"
            accepted = Path(temp_dir) / "accepted.json"

            with redirect_stdout(StringIO()):
                main(["review", str(pseudo), "-o", str(review)])
            data = json.loads(review.read_text())
            data["items"][0]["decision"] = "accept"
            review.write_text(json.dumps(data), encoding="utf-8")
            with redirect_stdout(StringIO()):
                main(["apply-review", str(review), "-o", str(accepted)])

            result = json.loads(accepted.read_text())
            self.assertEqual(result["accepted_count"], 1)


def _write_manifest(
    root: Path,
    run_name: str,
    *,
    diagnostics: list[dict[str, object]],
    classifier_error: float,
    editability_score: float = 1.0,
    fragmentation_penalty: float = 0.0,
) -> None:
    run_dir = root / run_name
    run_dir.mkdir(parents=True)
    (run_dir / "manifest.json").write_text(
        json.dumps(
            {
                "anchors": [
                    {
                        "kind": "circle",
                        "color": "#dd2222",
                        "metrics": {"classifier_prior_error": classifier_error},
                    }
                ],
                "diagnostics": diagnostics,
                "metrics": {
                    "editability_score": editability_score,
                    "fragmentation_penalty": fragmentation_penalty,
                },
            }
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    unittest.main()
