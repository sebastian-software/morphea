import unittest

from morphea.primitive_baseline import (
    DEFAULT_BASELINE_PATH,
    baseline_snapshot,
    compare_to_baseline,
    load_baseline,
    render_baseline_diff_markdown,
)
from morphea.primitive_quality import check_primitive_quality


def _report_with_case(**overrides) -> dict:
    case = {
        "id": "sample",
        "ok": True,
        "actual_kind": "rect",
        "anchor_count": 1,
        "anchor_kind_counts": {"rect": 1},
        "metrics": {"raster_l1_error": 0.01, "raster_edge_error": 0.02},
        "svg_metrics": {
            "svg_raster_l1_error": 0.015,
            "svg_raster_edge_error": 0.025,
        },
        "geometry": {"bbox_iou": 0.95},
    }
    case.update(overrides)
    return {"cases": [case]}


class PrimitiveBaselineUnitTests(unittest.TestCase):
    def test_identical_reports_show_no_drift(self):
        report = _report_with_case()
        baseline = baseline_snapshot(report)

        diff = compare_to_baseline(report, baseline)

        self.assertTrue(diff["ok"])
        self.assertEqual(diff["regressions"], [])
        self.assertEqual(diff["improvements"], [])

    def test_metric_regression_and_improvement_are_separated(self):
        baseline = baseline_snapshot(_report_with_case())
        drifted = _report_with_case(
            metrics={"raster_l1_error": 0.02, "raster_edge_error": 0.012},
            svg_metrics={
                "svg_raster_l1_error": 0.015,
                "svg_raster_edge_error": 0.025,
            },
        )

        diff = compare_to_baseline(drifted, baseline)

        self.assertFalse(diff["ok"])
        self.assertEqual(
            [(finding["field"]) for finding in diff["regressions"]],
            ["l1"],
        )
        self.assertEqual(
            [(finding["field"]) for finding in diff["improvements"]],
            ["edge"],
        )

    def test_lower_bbox_iou_counts_as_regression(self):
        baseline = baseline_snapshot(_report_with_case())
        drifted = _report_with_case(geometry={"bbox_iou": 0.90})

        diff = compare_to_baseline(drifted, baseline)

        self.assertFalse(diff["ok"])
        self.assertEqual(diff["regressions"][0]["field"], "bbox_iou")

    def test_kind_flip_and_case_set_changes_are_findings(self):
        baseline = baseline_snapshot(_report_with_case())
        flipped = _report_with_case(
            actual_kind="quad",
            anchor_kind_counts={"quad": 1},
        )

        diff = compare_to_baseline(flipped, baseline)
        self.assertFalse(diff["ok"])
        self.assertEqual(
            sorted(finding["field"] for finding in diff["regressions"]),
            ["anchor_kind_counts", "kind"],
        )

        extra = {"cases": _report_with_case()["cases"] + [
            dict(_report_with_case()["cases"][0], id="brand_new"),
        ]}
        diff = compare_to_baseline(extra, baseline)
        self.assertEqual(diff["added_cases"], ["brand_new"])
        self.assertFalse(diff["ok"])

    def test_small_drift_within_tolerance_is_noise(self):
        baseline = baseline_snapshot(_report_with_case())
        nudged = _report_with_case(
            metrics={"raster_l1_error": 0.0115, "raster_edge_error": 0.02},
            svg_metrics={
                "svg_raster_l1_error": 0.015,
                "svg_raster_edge_error": 0.025,
            },
        )

        diff = compare_to_baseline(nudged, baseline)

        self.assertTrue(diff["ok"])

    def test_markdown_names_every_finding(self):
        baseline = baseline_snapshot(_report_with_case())
        drifted = _report_with_case(actual_kind="quad")

        markdown = render_baseline_diff_markdown(
            compare_to_baseline(drifted, baseline)
        )

        self.assertIn("regression sample.kind", markdown)
        self.assertIn("--update-baseline", markdown)


class PrimitiveBaselineSuiteTests(unittest.TestCase):
    def test_full_suite_matches_checked_in_baseline(self):
        """The regression guard: any drift against the pinned baseline fails.

        After an intentional change, regenerate via
        `morphea primitive-check --update-baseline` and commit the diff.
        """

        report = check_primitive_quality()
        baseline = load_baseline(DEFAULT_BASELINE_PATH)

        diff = compare_to_baseline(report, baseline)

        self.assertTrue(
            diff["ok"],
            render_baseline_diff_markdown(diff),
        )


if __name__ == "__main__":
    unittest.main()
