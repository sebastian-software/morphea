import unittest

from curve.diagnostics import diagnostic_stage, diagnostic_stage_counts


class DiagnosticStageTests(unittest.TestCase):
    def test_diagnostic_stage_counts_respect_explicit_stage_metadata(self):
        counts = diagnostic_stage_counts(
            (
                {"code": "custom-warning", "stage": "fitting"},
                {"code": "other-warning", "stage": "export"},
                {"code": "bad-stage", "stage": "not-a-stage"},
            )
        )

        self.assertEqual(counts["fitting"], 1)
        self.assertEqual(counts["export"], 1)
        self.assertEqual(counts["unknown"], 1)

    def test_diagnostic_stage_classifies_late_pipeline_code_conventions(self):
        self.assertEqual(diagnostic_stage("fit_circle_failed"), "fitting")
        self.assertEqual(diagnostic_stage("cleanup_merge_candidates"), "cleanup")
        self.assertEqual(diagnostic_stage("score_candidate_rejected"), "scoring")
        self.assertEqual(diagnostic_stage("svg_export_failed"), "export")


if __name__ == "__main__":
    unittest.main()
