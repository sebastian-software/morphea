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
                proposal_groups=[
                    {
                        "id": "proposal-group-0000",
                        "kind": "proposal_tile_grid",
                        "proposal_ids": ["flat_color-0000", "flat_color-0001"],
                        "metrics": {
                            "row_count": 1.0,
                            "column_count": 2.0,
                            "grid_occupancy_ratio": 1.0,
                        },
                    },
                    {
                        "id": "proposal-group-removed",
                        "kind": "proposal_tile_grid",
                        "proposal_ids": ["flat_color-0001"],
                        "metrics": {"tile_count": 1.0},
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
                proposal_groups=[
                    {
                        "id": "proposal-group-0000",
                        "kind": "proposal_tile_grid",
                        "proposal_ids": ["flat_color-0000", "flat_color-0002"],
                        "metrics": {
                            "row_count": 1.0,
                            "column_count": 2.0,
                            "grid_occupancy_ratio": 0.5,
                        },
                    },
                    {
                        "id": "proposal-group-added",
                        "kind": "proposal_tile_grid",
                        "proposal_ids": ["flat_color-0002"],
                        "metrics": {"tile_count": 1.0},
                    },
                ],
            ),
            before="pending.json",
            after="gated.json",
        )

        self.assertEqual(comparison["shared_proposal_count"], 1)
        self.assertEqual(comparison["added_ids"], ["flat_color-0002"])
        self.assertEqual(comparison["removed_ids"], ["flat_color-0001"])
        self.assertEqual(comparison["shared_group_count"], 1)
        self.assertEqual(comparison["added_group_ids"], ["proposal-group-added"])
        self.assertEqual(comparison["removed_group_ids"], ["proposal-group-removed"])
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
        group_changes = comparison["proposal_group_changes"][0]["changes"]
        self.assertIn(
            {
                "field": "metrics.grid_occupancy_ratio",
                "before": 1.0,
                "after": 0.5,
            },
            group_changes,
        )
        self.assertIn(
            {
                "field": "proposal_ids",
                "before": ["flat_color-0000", "flat_color-0001"],
                "after": ["flat_color-0000", "flat_color-0002"],
            },
            group_changes,
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
                        proposal_groups=[
                            {
                                "id": "proposal-group-0000",
                                "kind": "proposal_tile_grid",
                                "proposal_ids": ["flat_color-0000"],
                                "metrics": {"tile_count": 1.0},
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
            self.assertEqual(result["added_group_ids"], ["proposal-group-0000"])
            self.assertTrue(output.exists())
            self.assertIn(
                "Curve Segment Manifest Comparison",
                markdown.read_text(encoding="utf-8"),
            )
            self.assertIn(
                "Added groups: `proposal-group-0000`",
                markdown.read_text(encoding="utf-8"),
            )
            cli_result = json.loads(
                (root / "cli-segment-comparison.json").read_text(encoding="utf-8")
            )
            self.assertEqual(cli_result["proposal_changes"][0]["id"], "flat_color-0000")

    def test_compare_segment_manifests_cli_accepts_config_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            before = root / "before-segments.json"
            after = root / "after-segments.json"
            output = root / "segment-comparison.json"
            markdown = root / "segment-comparison.md"
            config = root / "compare-segments.json"
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
                        summary={"downstream_status_counts": {"accepted": 1}},
                        proposals=[
                            {
                                "id": "flat_color-0000",
                                "source": "flat_color",
                                "status": "proposed",
                                "downstream_status": "accepted",
                            }
                        ],
                    )
                ),
                encoding="utf-8",
            )
            config.write_text(
                json.dumps(
                    {
                        "before": str(before),
                        "after": str(after),
                        "output": str(output),
                        "markdown": str(markdown),
                    }
                ),
                encoding="utf-8",
            )

            with redirect_stdout(StringIO()):
                main(["compare-segments", "--config", str(config)])

            result = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(result["shared_proposal_count"], 1)
            self.assertTrue(markdown.exists())

    def test_compare_segment_manifests_cli_args_override_config_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_before = root / "config-before-segments.json"
            config_after = root / "config-after-segments.json"
            before = root / "before-segments.json"
            after = root / "after-segments.json"
            config_output = root / "config-comparison.json"
            output = root / "segment-comparison.json"
            config = root / "compare-segments.json"
            config_before.write_text(json.dumps(_segment_manifest()))
            config_after.write_text(json.dumps(_segment_manifest()))
            before.write_text(
                json.dumps(
                    _segment_manifest(
                        proposals=[
                            {
                                "id": "flat_color-0000",
                                "source": "flat_color",
                                "status": "proposed",
                                "downstream_status": "pending",
                            }
                        ],
                    )
                )
            )
            after.write_text(
                json.dumps(
                    _segment_manifest(
                        proposals=[
                            {
                                "id": "flat_color-0000",
                                "source": "flat_color",
                                "status": "proposed",
                                "downstream_status": "accepted",
                            }
                        ],
                    )
                )
            )
            config.write_text(
                json.dumps(
                    {
                        "before": str(config_before),
                        "after": str(config_after),
                        "output": str(config_output),
                    }
                ),
                encoding="utf-8",
            )

            with redirect_stdout(StringIO()):
                main(
                    [
                        "compare-segments",
                        str(before),
                        str(after),
                        "-o",
                        str(output),
                        "--config",
                        str(config),
                    ]
                )

            result = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(len(result["proposal_changes"]), 1)
            self.assertFalse(config_output.exists())

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

    def test_compare_snapshots_cli_accepts_config_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            before = root / "before.json"
            after = root / "after.json"
            output = root / "comparison.json"
            markdown = root / "comparison.md"
            config = root / "compare-snapshots.json"
            before.write_text(json.dumps({"cases": [{"id": "a", "anchor_count": 1}]}))
            after.write_text(json.dumps({"cases": [{"id": "a", "anchor_count": 2}]}))
            config.write_text(
                json.dumps(
                    {
                        "before": str(before),
                        "after": str(after),
                        "output": str(output),
                        "markdown": str(markdown),
                    }
                ),
                encoding="utf-8",
            )

            with redirect_stdout(StringIO()):
                main(["compare-snapshots", "--config", str(config)])

            comparison = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(comparison["items"][0]["metric_deltas"][0]["delta"], 1.0)
            self.assertTrue(markdown.exists())

    def test_compare_snapshots_cli_args_override_config_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_before = root / "config-before.json"
            config_after = root / "config-after.json"
            before = root / "before.json"
            after = root / "after.json"
            config_output = root / "config-comparison.json"
            output = root / "comparison.json"
            config = root / "compare-snapshots.json"
            config_before.write_text(json.dumps({"cases": [{"id": "a", "anchor_count": 1}]}))
            config_after.write_text(json.dumps({"cases": [{"id": "a", "anchor_count": 1}]}))
            before.write_text(json.dumps({"cases": [{"id": "a", "anchor_count": 2}]}))
            after.write_text(json.dumps({"cases": [{"id": "a", "anchor_count": 5}]}))
            config.write_text(
                json.dumps(
                    {
                        "before": str(config_before),
                        "after": str(config_after),
                        "output": str(config_output),
                    }
                ),
                encoding="utf-8",
            )

            with redirect_stdout(StringIO()):
                main(
                    [
                        "compare-snapshots",
                        str(before),
                        str(after),
                        "-o",
                        str(output),
                        "--config",
                        str(config),
                    ]
                )

            comparison = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(comparison["items"][0]["metric_deltas"][0]["delta"], 3.0)
            self.assertFalse(config_output.exists())

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

    def test_compare_git_snapshots_cli_accepts_config_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config = root / "compare-git-snapshots.json"
            output = root / "git-comparison.json"
            markdown = root / "git-comparison.md"
            config.write_text(
                json.dumps(
                    {
                        "before_ref": "HEAD",
                        "after_ref": "HEAD",
                        "path": "docs/real-images/baselines/current-curated-snapshot.json",
                        "output": str(output),
                        "markdown": str(markdown),
                    }
                ),
                encoding="utf-8",
            )

            with redirect_stdout(StringIO()):
                main(["compare-git-snapshots", "--config", str(config)])

            result = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(result["git"]["before_ref"], "HEAD")
            self.assertEqual(
                result["git"]["snapshot_path"],
                "docs/real-images/baselines/current-curated-snapshot.json",
            )
            self.assertTrue(markdown.exists())

    def test_compare_git_snapshots_cli_args_override_config_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config = root / "compare-git-snapshots.json"
            config_output = root / "config-output.json"
            output = root / "cli-output.json"
            config.write_text(
                json.dumps(
                    {
                        "before_ref": "HEAD",
                        "after_ref": "HEAD",
                        "path": "docs/real-images/baselines/current-curated-snapshot.json",
                        "output": str(config_output),
                    }
                ),
                encoding="utf-8",
            )

            with redirect_stdout(StringIO()):
                main(
                    [
                        "compare-git-snapshots",
                        "--config",
                        str(config),
                        "-o",
                        str(output),
                    ]
                )

            self.assertTrue(output.exists())
            self.assertFalse(config_output.exists())

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

    def test_snapshot_git_ref_cli_accepts_config_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config = root / "snapshot-git-ref.json"
            suite = root / "suite.json"
            output = root / "snapshot.json"
            report = root / "report.json"
            output_dir = root / "runs"
            config.write_text(
                json.dumps(
                    {
                        "ref": "HEAD",
                        "suite": str(suite),
                        "output": str(output),
                        "report": str(report),
                        "output_dir": str(output_dir),
                        "repo": ".",
                        "timeout_seconds": 9,
                        "run": False,
                    }
                ),
                encoding="utf-8",
            )

            with patch("curve.cli.generate_git_curated_snapshot") as generate:
                generate.return_value = {
                    "git": {"ref": "HEAD"},
                    "case_count": 2,
                    "snapshot": str(output),
                }
                with redirect_stdout(StringIO()):
                    main(["snapshot-git-ref", "--config", str(config)])

            generate.assert_called_once()
            args, kwargs = generate.call_args
            self.assertEqual(args, ("HEAD",))
            self.assertEqual(kwargs["suite"], suite)
            self.assertEqual(kwargs["output"], output)
            self.assertEqual(kwargs["report"], report)
            self.assertEqual(kwargs["output_dir"], output_dir)
            self.assertEqual(kwargs["repo"], Path("."))
            self.assertEqual(kwargs["timeout_seconds"], 9)
            self.assertFalse(kwargs["run"])

    def test_snapshot_git_ref_cli_args_override_config_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config = root / "snapshot-git-ref.json"
            config_suite = root / "config-suite.json"
            suite = root / "cli-suite.json"
            config_output = root / "config-snapshot.json"
            output = root / "cli-snapshot.json"
            config.write_text(
                json.dumps(
                    {
                        "ref": "CONFIG",
                        "suite": str(config_suite),
                        "output": str(config_output),
                        "timeout_seconds": 30,
                        "run": True,
                    }
                ),
                encoding="utf-8",
            )

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
                            "--config",
                            str(config),
                            "--suite",
                            str(suite),
                            "-o",
                            str(output),
                            "--timeout-seconds",
                            "7",
                            "--no-run",
                        ]
                    )

            generate.assert_called_once()
            args, kwargs = generate.call_args
            self.assertEqual(args, ("HEAD",))
            self.assertEqual(kwargs["suite"], suite)
            self.assertEqual(kwargs["output"], output)
            self.assertEqual(kwargs["timeout_seconds"], 7)
            self.assertFalse(kwargs["run"])


def _segment_manifest(
    *,
    config=None,
    summary=None,
    proposals=None,
    proposal_groups=None,
):
    config = config or {}
    summary = summary or {}
    proposals = proposals or []
    proposal_groups = proposal_groups or []
    return {
        "schema_version": 1,
        "input": "input.png",
        "config": {"segmenter": "flat_color", "geometry_gate": False, **config},
        "backend": {"source": "flat_color", "status": "available"},
        "proposal_count": len(proposals),
        "summary": summary,
        "proposal_groups": proposal_groups,
        "proposals": proposals,
    }


if __name__ == "__main__":
    unittest.main()
