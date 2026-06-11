import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from curve.cli import main
from curve.eval import evaluate_runs, render_eval_markdown, write_eval_summary


class EvalTests(unittest.TestCase):
    def test_evaluate_runs_summarizes_manifests(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = _write_run_manifest(Path(temp_dir), "run-a")

            summary = evaluate_runs(run_dir.parent)

            self.assertEqual(summary["run_count"], 1)
            self.assertEqual(summary["runs"][0]["anchor_count"], 2)
            self.assertEqual(summary["runs"][0]["anchor_types"]["circle"], 1)
            self.assertEqual(
                summary["runs"][0]["diagnostic_codes"]["component_deferred"],
                1,
            )

    def test_write_eval_summary_outputs_json_and_markdown(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "runs"
            _write_run_manifest(root, "run-a")
            output = Path(temp_dir) / "summary.json"
            markdown = Path(temp_dir) / "summary.md"

            write_eval_summary(run_root=root, output=output, markdown=markdown)

            self.assertTrue(output.exists())
            self.assertTrue(markdown.exists())
            self.assertIn("# Curve Eval Summary", markdown.read_text())

    def test_render_eval_markdown_lists_runs(self):
        markdown = render_eval_markdown(
            {
                "run_count": 1,
                "runs": [
                    {
                        "run": "run-a",
                        "anchor_count": 2,
                        "group_count": 1,
                        "diagnostic_count": 0,
                    }
                ],
            }
        )

        self.assertIn("### run-a", markdown)
        self.assertIn("- Anchors: 2", markdown)

    def test_eval_cli_writes_summary(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "runs"
            _write_run_manifest(root, "run-a")
            output = Path(temp_dir) / "summary.json"

            with redirect_stdout(StringIO()):
                main(["eval", str(root), "-o", str(output)])

            summary = json.loads(output.read_text())
            self.assertEqual(summary["run_count"], 1)


def _write_run_manifest(root: Path, name: str) -> Path:
    run_dir = root / name
    run_dir.mkdir(parents=True)
    (run_dir / "manifest.json").write_text(
        json.dumps(
            {
                "anchor_count": 2,
                "anchors": [
                    {"kind": "circle"},
                    {"kind": "stroke_polyline"},
                ],
                "groups": [{"kind": "perspective_grid"}],
                "diagnostics": [{"code": "component_deferred"}],
            }
        ),
        encoding="utf-8",
    )
    return run_dir


if __name__ == "__main__":
    unittest.main()

