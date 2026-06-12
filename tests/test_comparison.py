import json
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from curve.cli import main
from curve.comparison import (
    compare_git_snapshots,
    compare_segment_manifests,
    compare_snapshots,
    generate_git_curated_snapshot,
    render_segment_manifest_comparison,
    render_snapshot_comparison,
    render_snapshot_comparison_markdown,
)


class SnapshotComparisonTests(unittest.TestCase):
    def test_render_segment_manifest_comparison_reports_gate_changes(self):
        comparison = render_segment_manifest_comparison(
            _segment_manifest(
                summary={
                    "downstream_status_counts": {"pending": 2},
                    "anchor_kind_counts": {"rect": 2},
                    "reserved_anchor_count": 2,
                },
                proposals=[
                    {
                        "id": "flat_color-0000",
                        "source": "flat_color",
                        "confidence": 1.0,
                        "bounds": [2, 2, 6, 6],
                        "status": "proposed",
                        "downstream_status": "pending",
                        "anchor_kind": "rect",
                        "anchor_reserved": True,
                    },
                    {
                        "id": "flat_color-0001",
                        "source": "flat_color",
                        "confidence": 1.0,
                        "bounds": [12, 2, 16, 6],
                        "status": "proposed",
                        "downstream_status": "pending",
                        "anchor_kind": "rect",
                        "anchor_reserved": True,
                    },
                ],
            ),
            _segment_manifest(
                config={"geometry_gate": True},
                summary={
                    "downstream_status_counts": {"accepted": 2},
                    "anchor_kind_counts": {"rect": 2},
                    "reserved_anchor_count": 1,
                    "downstream_decision_reason_counts": {
                        "geometry_gate_passed": 2
                    },
                },
                proposals=[
                    {
                        "id": "flat_color-0000",
                        "source": "flat_color",
                        "confidence": 1.0,
                        "bounds": [2, 2, 6, 6],
                        "status": "proposed",
                        "downstream_status": "accepted",
                        "anchor_kind": "rect",
                        "anchor_reserved": True,
                        "anchor_quality_error": 0.0,
                        "downstream_decision_reason": "geometry_gate_passed",
                    },
                    {
                        "id": "flat_color-0002",
                        "source": "flat_color",
                        "confidence": 1.0,
                        "bounds": [18, 2, 22, 6],
                        "status": "proposed",
                        "downstream_status": "accepted",
                        "anchor_kind": "rect",
                        "anchor_reserved": True,
                    },
                ],
            ),
            before="pending.json",
            after="gated.json",
        )

        self.assertEqual(comparison["shared_proposal_count"], 1)
        self.assertEqual(comparison["added_ids"], ["flat_color-0002"])
        self.assertEqual(comparison["removed_ids"], ["flat_color-0001"])
        self.assertIn(
            {
                "group": "downstream_status_counts",
                "key": "accepted",
                "before": 0.0,
                "after": 2.0,
                "delta": 2.0,
            },
            comparison["summary_deltas"],
        )
        self.assertIn(
            {
                "group": "reserved_anchor_count",
                "key": "value",
                "before": 2.0,
                "after": 1.0,
                "delta": -1.0,
            },
            comparison["summary_deltas"],
        )
        changes = comparison["proposal_changes"][0]["changes"]
        self.assertIn(
            {
                "field": "downstream_status",
                "before": "pending",
                "after": "accepted",
            },
            changes,
        )
        self.assertIn(
            {"key": "geometry_gate", "before": False, "after": True},
            comparison["config_deltas"],
        )

    def test_compare_segment_manifests_cli_writes_json_and_markdown(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            before = root / "before-segments.json"
            after = root / "after-segments.json"
            output = root / "segment-comparison.json"
            markdown = root / "segment-comparison.md"
            before.write_text(
                json.dumps(
                    _segment_manifest(
                        summary={"downstream_status_counts": {"pending": 1}},
                        proposals=[
                            {
                                "id": "flat_color-0000",
                                "source": "flat_color",
                                "status": "proposed",
                                "downstream_status": "pending",
                            }
                        ],
                    )
                ),
                encoding="utf-8",
            )
            after.write_text(
                json.dumps(
                    _segment_manifest(
                        config={"geometry_gate": True},
                        summary={"downstream_status_counts": {"accepted": 1}},
                        proposals=[
                            {
                                "id": "flat_color-0000",
                                "source": "flat_color",
                                "status": "proposed",
                                "downstream_status": "accepted",
                                "downstream_decision_reason": "geometry_gate_passed",
                            }
                        ],
                    )
                ),
                encoding="utf-8",
            )

            result = compare_segment_manifests(
                before,
                after,
                output=output,
                markdown=markdown,
            )
            with redirect_stdout(StringIO()):
                main(
                    [
                        "compare-segments",
                        str(before),
                        str(after),
                        "-o",
                        str(root / "cli-segment-comparison.json"),
                        "--markdown",
                        str(root / "cli-segment-comparison.md"),
                    ]
                )

            self.assertEqual(result["shared_proposal_count"], 1)
            self.assertTrue(output.exists())
            self.assertIn(
                "Curve Segment Manifest Comparison",
                markdown.read_text(encoding="utf-8"),
            )
            cli_result = json.loads(
                (root / "cli-segment-comparison.json").read_text(encoding="utf-8")
            )
            self.assertEqual(cli_result["proposal_changes"][0]["id"], "flat_color-0000")

    def test_render_snapshot_comparison_reports_case_metric_deltas(self):
        comparison = render_snapshot_comparison(
            {
                "cases": [
                    {
                        "id": "terminaro",
                        "metrics": {"editability_score": 0.8},
                        "anchor_kind_counts": {"quad": 4},
                        "expectations": [
                            {
                                "id": "simple-shape-ratio",
                                "metric": "simple_shape_ratio",
                                "actual_value": 0.82,
                                "min_value": 0.8,
                                "ok": True,
                            }
                        ],
                    }
                ]
            },
            {
                "cases": [
                    {
                        "id": "terminaro",
                        "metrics": {"editability_score": 0.9},
                        "anchor_kind_counts": {"quad": 6},
                        "expectations": [
                            {
                                "id": "simple-shape-ratio",
                                "metric": "simple_shape_ratio",
                                "actual_value": 0.9,
                                "min_value": 0.8,
                                "ok": True,
                            }
                        ],
                    },
                    {"id": "new-case", "metrics": {"editability_score": 0.5}},
                ]
            },
            before="before.json",
            after="after.json",
        )

        self.assertEqual(comparison["item_kind"], "cases")
        self.assertEqual(comparison["added_ids"], ["new-case"])
        deltas = comparison["items"][0]["metric_deltas"]
        self.assertIn(
            {
                "path": "anchor_kind_counts.quad",
                "before": 4.0,
                "after": 6.0,
                "delta": 2.0,
            },
            deltas,
        )
        self.assertIn(
            {
                "path": "expectations.simple-shape-ratio.actual_value",
                "before": 0.82,
                "after": 0.9,
                "delta": 0.08000000000000007,
            },
            deltas,
        )

    def test_compare_snapshots_writes_json_and_markdown(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            before = root / "before.json"
            after = root / "after.json"
            output = root / "comparison.json"
            markdown = root / "comparison.md"
            before.write_text(
                json.dumps(
                    {
                        "runs": [
                            {
                                "id": "strict",
                                "editability_score": 0.7,
                                "raster_l1_error": 0.2,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            after.write_text(
                json.dumps(
                    {
                        "runs": [
                            {
                                "id": "strict",
                                "editability_score": 0.8,
                                "raster_l1_error": 0.15,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            result = compare_snapshots(
                before,
                after,
                output=output,
                markdown=markdown,
            )

            self.assertEqual(result["item_kind"], "runs")
            self.assertTrue(output.exists())
            self.assertTrue(markdown.exists())
            self.assertIn("Curve Snapshot Comparison", markdown.read_text())

    def test_compare_snapshots_cli_writes_outputs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            before = root / "before.json"
            after = root / "after.json"
            output = root / "comparison.json"
            markdown = root / "comparison.md"
            before.write_text(json.dumps({"cases": [{"id": "a", "anchor_count": 1}]}))
            after.write_text(json.dumps({"cases": [{"id": "a", "anchor_count": 2}]}))

            with redirect_stdout(StringIO()):
                main(
                    [
                        "compare-snapshots",
                        str(before),
                        str(after),
                        "-o",
                        str(output),
                        "--markdown",
                        str(markdown),
                    ]
                )

            comparison = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(comparison["items"][0]["metric_deltas"][0]["delta"], 1.0)
            self.assertIn(
                "`anchor_count`",
                markdown.read_text(encoding="utf-8"),
            )

    def test_render_snapshot_comparison_markdown_handles_no_changes(self):
        markdown = render_snapshot_comparison_markdown(
            {
                "before": "before.json",
                "after": "after.json",
                "item_kind": "cases",
                "item_count": 1,
                "items": [{"id": "same", "metric_deltas": []}],
                "added_ids": [],
                "removed_ids": [],
            }
        )

        self.assertIn("| n/a | n/a | n/a | n/a | n/a |", markdown)

    def test_compare_git_snapshots_reads_snapshot_from_refs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output = root / "git-comparison.json"
            markdown = root / "git-comparison.md"

            result = compare_git_snapshots(
                "HEAD",
                "HEAD",
                snapshot_path="docs/real-images/baselines/current-curated-snapshot.json",
                output=output,
                markdown=markdown,
            )

            self.assertEqual(result["item_kind"], "cases")
            self.assertEqual(result["git"]["before_ref"], "HEAD")
            self.assertTrue(output.exists())
            self.assertTrue(markdown.exists())
            self.assertGreaterEqual(result["item_count"], 1)
            self.assertTrue(
                all(item["changed_metric_count"] == 0 for item in result["items"])
            )

    def test_compare_git_snapshots_cli_writes_outputs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output = root / "git-comparison.json"

            with redirect_stdout(StringIO()):
                main(
                    [
                        "compare-git-snapshots",
                        "HEAD",
                        "HEAD",
                        "--path",
                        "docs/real-images/baselines/current-curated-snapshot.json",
                        "-o",
                        str(output),
                    ]
                )

            result = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(
                result["git"]["snapshot_path"],
                "docs/real-images/baselines/current-curated-snapshot.json",
            )

    def test_generate_git_curated_snapshot_uses_isolated_worktree(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            suite = root / "suite.json"
            output = root / "snapshot.json"
            report = root / "report.json"
            calls: list[dict[str, object]] = []

            def fake_run(
                command,
                *,
                cwd,
                check,
                capture_output,
                text,
                timeout,
                env=None,
            ):
                calls.append(
                    {
                        "command": command,
                        "cwd": cwd,
                        "check": check,
                        "timeout": timeout,
                        "env": env,
                    }
                )
                if command[:3] == ["git", "rev-parse", "--show-toplevel"]:
                    return subprocess.CompletedProcess(
                        command,
                        0,
                        stdout=str(Path("/repo")) + "\n",
                        stderr="",
                    )
                if "curated-check" in command:
                    output.write_text(
                        json.dumps(
                            {
                                "schema_version": 1,
                                "case_count": 1,
                                "ok": True,
                                "cases": [{"id": "case-a"}],
                            }
                        ),
                        encoding="utf-8",
                    )
                    report.write_text(json.dumps({"case_count": 1}), encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

            with patch("curve.comparison.subprocess.run", side_effect=fake_run):
                result = generate_git_curated_snapshot(
                    "HEAD",
                    suite=suite,
                    output=output,
                    report=report,
                    repo="/repo",
                    timeout_seconds=42,
                )

            commands = [call["command"] for call in calls]
            curated_command = next(command for command in commands if "curated-check" in command)
            self.assertEqual(result["git"]["ref"], "HEAD")
            self.assertEqual(result["case_count"], 1)
            self.assertEqual(result["snapshot"], str(output))
            self.assertIn("--run", curated_command)
            self.assertIn(str(output), curated_command)
            self.assertEqual(
                [call["timeout"] for call in calls if "curated-check" in call["command"]],
                [42],
            )
            curated_env = next(call["env"] for call in calls if "curated-check" in call["command"])
            self.assertIsNotNone(curated_env)
            self.assertIn("worktree/src", curated_env["PYTHONPATH"])
            self.assertTrue(
                any(command[:3] == ["git", "worktree", "add"] for command in commands)
            )
            self.assertTrue(
                any(command[:3] == ["git", "worktree", "remove"] for command in commands)
            )

    def test_snapshot_git_ref_cli_delegates_to_generator(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output = root / "snapshot.json"

            with patch("curve.cli.generate_git_curated_snapshot") as generate:
                generate.return_value = {
                    "git": {"ref": "HEAD"},
                    "case_count": 2,
                    "snapshot": str(output),
                }
                with redirect_stdout(StringIO()):
                    main(
                        [
                            "snapshot-git-ref",
                            "HEAD",
                            "--suite",
                            "docs/real-images/suite.json",
                            "-o",
                            str(output),
                            "--timeout-seconds",
                            "7",
                            "--no-run",
                        ]
                    )

            generate.assert_called_once()
            _, kwargs = generate.call_args
            self.assertEqual(kwargs["suite"], Path("docs/real-images/suite.json"))
            self.assertEqual(kwargs["output"], output)
            self.assertEqual(kwargs["timeout_seconds"], 7)
            self.assertFalse(kwargs["run"])


def _segment_manifest(
    *,
    config=None,
    summary=None,
    proposals=None,
):
    config = config or {}
    summary = summary or {}
    proposals = proposals or []
    return {
        "schema_version": 1,
        "input": "input.png",
        "config": {"segmenter": "flat_color", "geometry_gate": False, **config},
        "backend": {"source": "flat_color", "status": "available"},
        "proposal_count": len(proposals),
        "summary": summary,
        "proposals": proposals,
    }


if __name__ == "__main__":
    unittest.main()
