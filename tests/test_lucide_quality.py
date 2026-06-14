import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageDraw

from morphea.cli import main
from morphea.lucide_quality import (
    _check_expectations,
    build_lucide_training_corpus,
    check_lucide_suite,
    load_lucide_suite,
    lucide_source_renderer_status,
    render_lucide_markdown,
)


class LucideQualityTests(unittest.TestCase):
    def test_load_checked_in_lucide_suite(self):
        suite = load_lucide_suite("assets/lucide/suite.json")

        self.assertEqual(suite["source_package"], "lucide-static")
        self.assertEqual(suite["source_version"], "1.18.0")
        self.assertEqual(len(suite["cases"]), 24)
        self.assertEqual(suite["cases"][0]["id"], "plus")

    def test_lucide_renderer_status_has_explicit_shape(self):
        status = lucide_source_renderer_status()

        self.assertIn("available", status)
        self.assertIn("backend", status)
        if not status["available"]:
            self.assertIn("reason", status)

    def test_check_lucide_suite_runs_with_mocked_source_renderer(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "minus.svg"
            suite = root / "suite.json"
            output = root / "report.json"
            markdown = root / "report.md"
            output_dir = root / "cases"
            source.write_text("<svg></svg>", encoding="utf-8")
            suite.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "source_package": "lucide-static",
                        "source_version": "test",
                        "render": {
                            "size": 64,
                            "background": "#ffffff",
                            "color": "#000000",
                        },
                        "recommended_config": {
                            "background": "#ffffff",
                            "min_area": 2,
                            "max_size": 64,
                            "max_colors": 3,
                            "color_tolerance": 48,
                            "timeout_seconds": 5,
                        },
                        "cases": [
                            {
                                "id": "minus",
                                "family": "simple_stroke_glyphs",
                                "source": "minus.svg",
                                "expectations": [
                                    {
                                        "id": "one-stroke",
                                        "kind": "stroke_polyline",
                                        "min_count": 1,
                                        "max_count": 1,
                                    },
                                    {
                                        "id": "no-fallback-path",
                                        "metric": "generic_path_count",
                                        "max_value": 0,
                                    },
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with patch(
                "morphea.lucide_quality.lucide_source_renderer_status",
                return_value={"backend": "mock", "available": True},
            ), patch(
                "morphea.lucide_quality._render_source_svg",
                side_effect=_write_minus_png,
            ):
                result = check_lucide_suite(
                    suite,
                    output=output,
                    output_dir=output_dir,
                    markdown=markdown,
                )

            self.assertTrue(result["ok"])
            self.assertEqual(result["case_count"], 1)
            self.assertEqual(result["family_summary"]["simple_stroke_glyphs"]["passed_count"], 1)
            self.assertEqual(result["quality_summary"]["green"], 1)
            self.assertEqual(result["cases"][0]["quality_label"], "green")
            self.assertEqual(
                result["cases"][0]["anchor_kind_counts"]["stroke_polyline"],
                1,
            )
            self.assertTrue((output_dir / "minus" / "source.svg").exists())
            self.assertTrue((output_dir / "minus" / "svg-render.png").exists())
            manifest = json.loads(
                (output_dir / "minus" / "manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertIn("svg_raster_l1_error", manifest["metrics"])
            self.assertIn("# Morphea Lucide Check", markdown.read_text())
            self.assertEqual(json.loads(output.read_text())["passed_count"], 1)

    def test_lucide_quality_labels_require_review_notes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            suite = root / "suite.json"
            suite.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "render": {"size": 64},
                        "cases": [
                            {
                                "id": "loose-icon",
                                "family": "simple_stroke_glyphs",
                                "source": "loose.svg",
                                "quality_label": "yellow",
                                "expectations": [
                                    {
                                        "id": "one-stroke",
                                        "kind": "stroke_polyline",
                                    }
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                ValueError,
                "quality_label yellow requires review_notes",
            ):
                load_lucide_suite(suite)

    def test_build_lucide_training_corpus_writes_png_svg_and_labels(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "minus.svg"
            suite = root / "suite.json"
            output = root / "corpus.json"
            output_dir = root / "corpus"
            markdown = root / "corpus.md"
            source.write_text(
                """
<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"
  viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
  <path d="M5 12h14" />
</svg>
""".strip(),
                encoding="utf-8",
            )
            suite.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "source_package": "lucide-static",
                        "source_version": "test",
                        "render": {
                            "size": 64,
                            "background": "#ffffff",
                            "color": "#000000",
                        },
                        "cases": [
                            {
                                "id": "minus",
                                "family": "simple_stroke_glyphs",
                                "source": "minus.svg",
                                "expectations": [
                                    {
                                        "id": "one-stroke",
                                        "kind": "stroke_polyline",
                                        "min_count": 1,
                                        "max_count": 1,
                                    },
                                    {
                                        "id": "no-circle",
                                        "kind": "stroke_circle",
                                        "min_count": 0,
                                        "max_count": 0,
                                    },
                                    {
                                        "id": "svg-close",
                                        "metric": "svg_raster_l1_error",
                                        "max_value": 0.04,
                                    },
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with patch(
                "morphea.lucide_quality.lucide_source_renderer_status",
                return_value={"backend": "mock", "available": True},
            ), patch(
                "morphea.lucide_quality._render_source_svg",
                side_effect=_write_minus_png,
            ):
                result = build_lucide_training_corpus(
                    suite,
                    output=output,
                    output_dir=output_dir,
                    markdown=markdown,
                )

            self.assertTrue(result["ok"])
            self.assertEqual(result["example_count"], 1)
            self.assertTrue((output_dir / "minus" / "input.png").exists())
            self.assertTrue((output_dir / "minus" / "source.svg").exists())
            example = result["examples"][0]
            self.assertEqual(example["status"], "rendered")
            self.assertEqual(example["split"], "train")
            self.assertEqual(
                example["labels"]["anchor_kind_targets"],
                {"stroke_polyline": 1},
            )
            self.assertEqual(
                example["labels"]["forbidden_anchor_kinds"],
                {"stroke_circle": 1},
            )
            self.assertEqual(
                example["labels"]["metric_targets"][0]["metric"],
                "svg_raster_l1_error",
            )
            self.assertEqual(
                example["labels"]["source_svg"]["path_command_counts"],
                {"H": 1, "M": 1},
            )
            saved = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(
                saved["target_summary"]["anchor_kind_targets"],
                {"stroke_polyline": 1},
            )
            self.assertIn("# Morphea Lucide Training Corpus", markdown.read_text())

    def test_lucide_corpus_cli_writes_manifest(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "minus.svg"
            suite = root / "suite.json"
            output = root / "corpus.json"
            output_dir = root / "corpus"
            source.write_text(
                "<svg xmlns='http://www.w3.org/2000/svg'><path d='M5 12h14' /></svg>",
                encoding="utf-8",
            )
            suite.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "render": {"size": 64},
                        "cases": [
                            {
                                "id": "minus",
                                "family": "simple_stroke_glyphs",
                                "source": "minus.svg",
                                "expectations": [
                                    {
                                        "id": "one-stroke",
                                        "kind": "stroke_polyline",
                                    }
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with patch(
                "morphea.lucide_quality.lucide_source_renderer_status",
                return_value={"backend": "mock", "available": True},
            ), patch(
                "morphea.lucide_quality._render_source_svg",
                side_effect=_write_minus_png,
            ):
                with redirect_stdout(StringIO()):
                    main(
                        [
                            "lucide-corpus",
                            str(suite),
                            "-o",
                            str(output),
                            "--output-dir",
                            str(output_dir),
                        ]
                    )

            self.assertEqual(
                json.loads(output.read_text(encoding="utf-8"))["example_count"],
                1,
            )

    def test_lucide_cli_exits_nonzero_when_contract_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "minus.svg"
            suite = root / "suite.json"
            output = root / "report.json"
            source.write_text("<svg></svg>", encoding="utf-8")
            suite.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "source_package": "lucide-static",
                        "source_version": "test",
                        "render": {"size": 64},
                        "recommended_config": {
                            "background": "#ffffff",
                            "min_area": 2,
                            "max_size": 64,
                            "timeout_seconds": 5,
                        },
                        "cases": [
                            {
                                "id": "minus",
                                "family": "simple_stroke_glyphs",
                                "source": "minus.svg",
                                "expectations": [
                                    {
                                        "id": "impossible",
                                        "kind": "stroke_circle",
                                        "min_count": 1,
                                    }
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with patch(
                "morphea.lucide_quality.lucide_source_renderer_status",
                return_value={"backend": "mock", "available": True},
            ), patch(
                "morphea.lucide_quality._render_source_svg",
                side_effect=_write_minus_png,
            ):
                with self.assertRaises(SystemExit):
                    with redirect_stdout(StringIO()):
                        main(["lucide-check", str(suite), "-o", str(output)])

            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertFalse(report["ok"])
            self.assertEqual(report["failed_count"], 1)

    def test_duplicate_kind_expectations_require_distinct_anchors(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "minus.svg"
            suite = root / "suite.json"
            source.write_text("<svg></svg>", encoding="utf-8")
            suite.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "source_package": "lucide-static",
                        "source_version": "test",
                        "render": {"size": 64},
                        "recommended_config": {
                            "background": "#ffffff",
                            "min_area": 2,
                            "max_size": 64,
                            "timeout_seconds": 5,
                        },
                        "cases": [
                            {
                                "id": "minus",
                                "family": "simple_stroke_glyphs",
                                "source": "minus.svg",
                                "expectations": [
                                    {
                                        "id": "first-stroke",
                                        "kind": "stroke_polyline",
                                        "min_count": 1,
                                    },
                                    {
                                        "id": "second-stroke",
                                        "kind": "stroke_polyline",
                                        "min_count": 1,
                                    },
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with patch(
                "morphea.lucide_quality.lucide_source_renderer_status",
                return_value={"backend": "mock", "available": True},
            ), patch(
                "morphea.lucide_quality._render_source_svg",
                side_effect=_write_minus_png,
            ):
                result = check_lucide_suite(suite)

            case = result["cases"][0]
            self.assertFalse(case["ok"])
            self.assertTrue(case["expectations"][0]["ok"])
            self.assertFalse(case["expectations"][1]["ok"])
            self.assertEqual(case["expectations"][1]["actual_count"], 1)
            self.assertEqual(case["expectations"][1]["cumulative_min_count"], 2)
            self.assertEqual(case["failed_expectation_count"], 1)
            self.assertEqual(case["failed_expectation_ids"], ["second-stroke"])
            self.assertEqual(
                case["expectations"][1]["failure_reason"],
                "insufficient_distinct_anchors",
            )
            self.assertEqual(case["expectations"][1]["required_count"], 2)
            self.assertEqual(case["expectations"][1]["missing_count"], 1)

    def test_bounded_kind_expectations_match_distinct_regions(self):
        manifest = {
            "anchors": [
                {
                    "kind": "stroke_path",
                    "source_mask": {"bounds": [0, 0, 64, 64]},
                },
                {
                    "kind": "stroke_path",
                    "source_mask": {"bounds": [20, 20, 40, 40]},
                },
            ]
        }

        results = _check_expectations(
            [
                {
                    "id": "outer-path",
                    "kind": "stroke_path",
                    "bounds": [0, 0, 64, 64],
                    "min_iou": 0.5,
                },
                {
                    "id": "inner-path",
                    "kind": "stroke_path",
                    "bounds": [20, 20, 40, 40],
                    "min_iou": 0.5,
                },
                {
                    "id": "missing-path",
                    "kind": "stroke_path",
                    "bounds": [50, 50, 60, 60],
                    "min_iou": 0.5,
                },
            ],
            manifest,
        )

        self.assertTrue(results[0]["ok"])
        self.assertEqual(results[0]["actual_count"], 1)
        self.assertTrue(results[1]["ok"])
        self.assertEqual(results[1]["actual_count"], 1)
        self.assertFalse(results[2]["ok"])
        self.assertEqual(results[2]["actual_count"], 0)
        self.assertEqual(results[2]["failure_reason"], "insufficient_anchors")
        self.assertEqual(results[2]["missing_count"], 1)

    def test_forbidden_kind_expectations_report_forbidden_matches(self):
        results = _check_expectations(
            [
                {
                    "id": "not-circle-substitute",
                    "kind": "stroke_circle",
                    "min_count": 0,
                    "max_count": 0,
                }
            ],
            {"anchors": [{"kind": "stroke_circle"}]},
        )

        self.assertFalse(results[0]["ok"])
        self.assertEqual(results[0]["actual_count"], 1)
        self.assertEqual(results[0]["failure_reason"], "forbidden_matches")
        self.assertEqual(results[0]["excess_count"], 1)

    def test_checked_in_lucide_suite_pins_badge_and_circle_false_positives(self):
        suite = load_lucide_suite("assets/lucide/suite.json")
        cases = {case["id"]: case for case in suite["cases"]}

        circle_expectations = {
            expectation["id"]: expectation
            for expectation in cases["circle"]["expectations"]
        }
        badge_expectations = {
            expectation["id"]: expectation
            for expectation in cases["badge-check"]["expectations"]
        }

        self.assertEqual(
            circle_expectations["not-irregular-badge-outline"]["kind"],
            "stroke_path",
        )
        self.assertEqual(
            circle_expectations["not-irregular-badge-outline"]["max_count"],
            0,
        )
        self.assertEqual(
            badge_expectations["not-circle-substitute"]["kind"],
            "stroke_circle",
        )
        self.assertEqual(
            badge_expectations["not-circle-substitute"]["max_count"],
            0,
        )

    def test_bounds_require_kind_expectation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "minus.svg"
            suite = root / "suite.json"
            source.write_text("<svg></svg>", encoding="utf-8")
            suite.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "render": {"size": 64},
                        "cases": [
                            {
                                "id": "minus",
                                "family": "simple_stroke_glyphs",
                                "source": "minus.svg",
                                "expectations": [
                                    {
                                        "id": "bad-bounds",
                                        "metric": "generic_path_count",
                                        "max_value": 0,
                                        "bounds": [0, 0, 64, 64],
                                    }
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(ValueError) as error:
                load_lucide_suite(suite)

            self.assertIn("bounds are only supported", str(error.exception))

    def test_render_lucide_markdown_summarizes_failures(self):
        markdown = render_lucide_markdown(
            {
                "suite": "suite.json",
                "source_package": "lucide-static",
                "source_version": "test",
                "renderer": {"backend": "mock", "available": True},
                "case_count": 1,
                "passed_count": 0,
                "failed_count": 1,
                "ok": False,
                "family_summary": {
                    "simple_stroke_glyphs": {
                        "case_count": 1,
                        "passed_count": 0,
                        "failed_count": 1,
                    }
                },
                "cases": [
                    {
                        "id": "plus",
                        "family": "simple_stroke_glyphs",
                        "status": "checked",
                        "ok": False,
                        "quality_label": "red",
                        "review_notes": ["generic fallback path remains"],
                        "anchor_kind_counts": {"cubic_path": 1},
                        "metrics": {
                            "generic_path_count": 1,
                            "node_count": 12,
                            "svg_raster_l1_error": 0.02,
                            "svg_raster_edge_error": 0.03,
                        },
                        "expectations": [
                            {
                                "id": "no-fallback-path",
                                "metric": "generic_path_count",
                                "actual_value": 1,
                                "max_value": 0,
                                "ok": False,
                                "failure_reason": "metric_above_max",
                                "excess_value": 1,
                            }
                        ],
                    }
                ],
            }
        )

        self.assertIn("# Morphea Lucide Check", markdown)
        self.assertIn("## Quality Ledger", markdown)
        self.assertIn("- Red cases: `plus`", markdown)
        self.assertIn(
            "| `plus` | `simple_stroke_glyphs` | `red` | `false` | "
            "`generic fallback path remains` |",
            markdown,
        )
        self.assertIn("| `plus` | `simple_stroke_glyphs` | `false` |", markdown)
        self.assertIn("`no-fallback-path`", markdown)
        self.assertIn(
            "| `no-fallback-path` | `metric:generic_path_count` | 1 | <= 0 | `false` | `metric_above_max`, excess_value=1 |",
            markdown,
        )

        forbidden_markdown = render_lucide_markdown(
            {
                "suite": "suite.json",
                "source_package": "lucide-static",
                "source_version": "test",
                "renderer": {"backend": "mock", "available": True},
                "case_count": 1,
                "passed_count": 0,
                "failed_count": 1,
                "ok": False,
                "family_summary": {},
                "cases": [
                    {
                        "id": "badge-check",
                        "family": "circle_compound_strokes",
                        "status": "checked",
                        "ok": False,
                        "quality_label": "red",
                        "review_notes": ["badge became a circle"],
                        "anchor_kind_counts": {"stroke_circle": 1},
                        "metrics": {},
                        "expectations": [
                            {
                                "id": "not-circle-substitute",
                                "kind": "stroke_circle",
                                "actual_count": 1,
                                "min_count": 0,
                                "max_count": 0,
                                "ok": False,
                                "failure_reason": "forbidden_matches",
                                "excess_count": 1,
                            }
                        ],
                    }
                ],
            }
        )
        self.assertIn(
            "| `not-circle-substitute` | `kind:stroke_circle` | 1 | = 0 | `false` | `forbidden_matches`, excess_count=1 |",
            forbidden_markdown,
        )


def _write_minus_png(source, output, *, renderer, render_config):
    image = Image.new("RGB", (64, 64), "white")
    draw = ImageDraw.Draw(image)
    draw.line((16, 32, 48, 32), fill="black", width=5)
    image.save(output)
