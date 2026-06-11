import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from curve.cli import main
from curve.comparison import (
    compare_snapshots,
    render_snapshot_comparison,
    render_snapshot_comparison_markdown,
)


class SnapshotComparisonTests(unittest.TestCase):
    def test_render_snapshot_comparison_reports_case_metric_deltas(self):
        comparison = render_snapshot_comparison(
            {
                "cases": [
                    {
                        "id": "terminaro",
                        "metrics": {"editability_score": 0.8},
                        "anchor_kind_counts": {"quad": 4},
                    }
                ]
            },
            {
                "cases": [
                    {
                        "id": "terminaro",
                        "metrics": {"editability_score": 0.9},
                        "anchor_kind_counts": {"quad": 6},
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


if __name__ == "__main__":
    unittest.main()
