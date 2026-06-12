import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from PIL import Image

from morphea.cli import main
from morphea.primitive_quality import (
    check_primitive_quality,
    primitive_specs,
    render_primitive_quality_markdown,
)


class PrimitiveQualityTests(unittest.TestCase):
    def test_primitive_quality_harness_passes_basic_cases(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            report = check_primitive_quality(output_dir=temp_dir)

            self.assertTrue(report["ok"])
            self.assertEqual(report["case_count"], len(primitive_specs()))
            self.assertEqual(report["failed_count"], 0)
            self.assertEqual(
                report["selection"],
                {
                    "cases": [],
                    "filter": None,
                    "refine": False,
                    "refinement_iterations": 1,
                },
            )
            actual_kinds = {
                case["id"]: case["actual_kind"]
                for case in report["cases"]
            }
            self.assertEqual(actual_kinds["filled_square"], "rect")
            self.assertEqual(actual_kinds["filled_circle"], "circle")
            self.assertEqual(actual_kinds["horizontal_stroke"], "stroke_polyline")
            self.assertEqual(actual_kinds["outlined_ring"], "stroke_circle")

            root = Path(temp_dir)
            for case in report["cases"]:
                case_dir = root / case["id"]
                self.assertIn("family", case)
                self.assertIn("variant", case)
                self.assertIn("geometry_diff", case)
                self.assertIn("failure_categories", case)
                self.assertIn("failure_details", case)
                self.assertTrue((case_dir / "input.png").exists())
                self.assertTrue((case_dir / "output.svg").exists())
                self.assertTrue((case_dir / "manifest.json").exists())
                self.assertTrue((case_dir / "preview.png").exists())

    def test_primitive_quality_report_counts_anchor_kinds(self):
        report = check_primitive_quality(
            cases=("filled_square", "composition_square_plus_circle_a"),
        )

        self.assertTrue(report["ok"])
        self.assertEqual(report["anchor_kind_counts"]["rect"], 2)
        self.assertEqual(report["anchor_kind_counts"]["circle"], 1)
        self.assertEqual(
            report["curve_anchor_kind_counts"],
            {
                "arc": 0,
                "stroke_path": 0,
                "ellipse": 0,
                "stroke_ellipse": 0,
                "cubic_path": 0,
            },
        )
        case_counts = {
            case["id"]: case["anchor_kind_counts"]
            for case in report["cases"]
        }
        self.assertEqual(case_counts["filled_square"], {"rect": 1})
        self.assertEqual(
            case_counts["composition_square_plus_circle_a"],
            {"circle": 1, "rect": 1},
        )

    def test_primitive_quality_report_includes_svg_raster_gate(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            report = check_primitive_quality(
                output_dir=temp_dir,
                cases=(
                    "adjacent_different_color_rects_horizontal",
                    "filled_square",
                ),
            )

            self.assertTrue(report["ok"])
            self.assertEqual(
                report["svg_raster_capability"]["backend"],
                "builtin",
            )
            for case in report["cases"]:
                svg_metrics = case["svg_metrics"]
                self.assertEqual(svg_metrics["svg_raster_backend"], "builtin")
                self.assertTrue(svg_metrics["svg_render_size_match"])
                thresholds = case["svg_thresholds"]
                self.assertLessEqual(
                    svg_metrics["svg_raster_l1_error"],
                    thresholds["svg_raster_l1_error"],
                )
                self.assertLessEqual(
                    svg_metrics["svg_raster_edge_error"],
                    thresholds["svg_raster_edge_error"],
                )
                self.assertLessEqual(
                    svg_metrics["svg_vs_preview_l1_error"],
                    thresholds["svg_vs_preview_l1_error"],
                )
                case_dir = Path(temp_dir) / case["id"]
                self.assertTrue((case_dir / "svg-render.png").exists())
            # The adjacent rect contact case renders the actual exported SVG
            # with zero divergence; a regression that reopens the gap fails.
            adjacent = next(
                case
                for case in report["cases"]
                if case["id"] == "adjacent_different_color_rects_horizontal"
            )
            self.assertEqual(adjacent["svg_metrics"]["svg_raster_l1_error"], 0.0)

    def test_simple_arc_fixture_meets_arc_contract(self):
        report = check_primitive_quality(cases=("arc_up", "arc_thick", "arc_shallow"))

        self.assertTrue(report["ok"])
        for case in report["cases"]:
            self.assertEqual(case["actual_kind"], "arc")
            self.assertEqual(case["anchor_count"], 1)
            self.assertEqual(case["anchor_kind_counts"], {"arc": 1})
        self.assertEqual(report["curve_anchor_kind_counts"]["arc"], 3)

    def test_arc_contract_failures_report_endpoint_bow_and_width(self):
        from morphea.primitive_quality import _arc_failures, primitive_specs

        spec = next(spec for spec in primitive_specs() if spec.id == "arc_up")
        drifted_anchor = {
            "kind": "arc",
            "stroke": {
                "centerline": [
                    {"x": 5.0, "y": 50.0},
                    {"x": 32.0, "y": 44.0},
                    {"x": 60.0, "y": 50.0},
                ],
                "width_samples": [9.0],
                "cap_style": "butt",
            },
        }

        failures = [failure["message"] for failure in _arc_failures(spec, drifted_anchor)]

        self.assertTrue(any("endpoint distance" in message for message in failures))
        self.assertTrue(any("bow" in message for message in failures))
        self.assertTrue(any("width" in message for message in failures))
        self.assertTrue(any("cap_style" in message for message in failures))

    def test_primitive_quality_harness_filters_cases(self):
        report = check_primitive_quality(cases=("filled_square",))

        self.assertTrue(report["ok"])
        self.assertEqual(report["case_count"], 1)
        self.assertEqual(report["selected_case_ids"], ["filled_square"])
        self.assertEqual(
            report["selection"],
            {
                "cases": ["filled_square"],
                "filter": None,
                "refine": False,
                "refinement_iterations": 1,
            },
        )

    def test_primitive_quality_harness_filters_by_pattern(self):
        report = check_primitive_quality(filter_pattern="*_stroke_width_1")

        self.assertTrue(report["ok"])
        self.assertEqual(
            report["selected_case_ids"],
            ["horizontal_stroke_width_1", "vertical_stroke_width_1"],
        )

    def test_diagonal_stroke_contract_requires_flat_svg_caps(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            report = check_primitive_quality(
                output_dir=temp_dir,
                cases=("diagonal_stroke_width_7",),
            )

            self.assertTrue(report["ok"])
            manifest = json.loads(
                (Path(temp_dir) / "diagonal_stroke_width_7" / "manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            stroke = manifest["anchors"][0]["stroke"]
            self.assertEqual(stroke["cap_style"], "butt")
            svg = (
                Path(temp_dir) / "diagonal_stroke_width_7" / "output.svg"
            ).read_text(encoding="utf-8")
            self.assertIn('stroke-linecap="butt"', svg)

    def test_rounded_rectangle_wide_source_is_visibly_rounded(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            report = check_primitive_quality(
                output_dir=temp_dir,
                cases=("rounded_rectangle_wide",),
            )

            self.assertTrue(report["ok"])
            case_root = Path(temp_dir) / "rounded_rectangle_wide"
            image = Image.open(case_root / "input.png").convert("RGB")
            colors = image.getcolors(maxcolors=4096)
            self.assertIsNotNone(colors)
            self.assertGreater(len(colors), 2)
            manifest = json.loads(
                (case_root / "manifest.json").read_text(encoding="utf-8")
            )
            anchor = manifest["anchors"][0]
            self.assertEqual(anchor["kind"], "rounded_rect")
            self.assertGreater(anchor["metrics"]["corner_radius"], 3.0)

    def test_adjacent_different_color_rect_svgs_export_without_contact_gaps(self):
        cases = (
            "adjacent_different_color_rects_horizontal",
            "adjacent_different_color_rects_vertical",
            "adjacent_different_color_rects_offset",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            report = check_primitive_quality(output_dir=temp_dir, cases=cases)

            self.assertTrue(report["ok"])
            for case_id in cases:
                rects = _svg_rects(Path(temp_dir) / case_id / "output.svg")
                self.assertEqual(len(rects), 2)
                self.assertTrue(
                    _has_touching_rect_pair(rects),
                    f"{case_id} exported rects do not touch without a gap",
                )

    def test_primitive_quality_harness_matches_multiple_anchors(self):
        report = check_primitive_quality(cases=("composition_square_plus_circle_a",))

        self.assertTrue(report["ok"])
        case = report["cases"][0]
        self.assertEqual(case["anchor_count"], 2)
        self.assertEqual(case["unmatched_expected"], [])
        self.assertEqual(case["unexpected_actual"], [])
        self.assertEqual(
            {match["expected_id"]: match["actual_kind"] for match in case["matches"]},
            {"square": "rect", "circle": "circle"},
        )

    def test_primitive_quality_harness_matches_expected_groups(self):
        report = check_primitive_quality(cases=("group_parallel_strokes_horizontal",))

        self.assertTrue(report["ok"])
        case = report["cases"][0]
        self.assertEqual(
            case["group_matches"],
            [
                {
                    "expected_kind": "parallel_stroke_group",
                    "group_index": 0,
                    "anchor_count": 2,
                }
            ],
        )

    def test_primitive_quality_harness_can_gate_refinement(self):
        report = check_primitive_quality(cases=("filled_circle",), refine=True)

        self.assertTrue(report["ok"])
        refinement = report["cases"][0]["refinement"]
        self.assertTrue(refinement["ok"])
        self.assertTrue(refinement["structure_audit"]["structure_preserved"])

    def test_primitive_quality_harness_compares_cutout_exports(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            report = check_primitive_quality(
                cases=("cutout_horizontal_gap_center",),
                output_dir=temp_dir,
            )

            self.assertTrue(report["ok"])
            case = report["cases"][0]
            comparison = case["export_comparison"]
            self.assertTrue(comparison["ok"])
            self.assertEqual(comparison["cutout_anchor_count"], 1)
            self.assertTrue(
                comparison["overlay_stroke"]["has_visible_cutout_stroke"]
            )
            self.assertFalse(comparison["overlay_stroke"]["has_mask"])
            self.assertTrue(comparison["negative_mask"]["has_mask"])
            self.assertTrue(comparison["negative_mask"]["uses_mask_group"])
            self.assertTrue(
                comparison["negative_mask"]["has_editable_mask_stroke"]
            )
            self.assertFalse(
                comparison["negative_mask"]["has_visible_cutout_stroke"]
            )
            negative_svg = Path(
                case["artifacts"]["negative_mask_svg"]
            ).read_text(encoding="utf-8")
            overlay_svg = Path(case["artifacts"]["output_svg"]).read_text(
                encoding="utf-8"
            )
            self.assertIn('<mask id="morphea-cutout-mask"', negative_svg)
            self.assertNotIn('<mask id="morphea-cutout-mask"', overlay_svg)

    def test_primitive_specs_have_ten_variants_per_family(self):
        counts: dict[str, int] = {}
        for spec in primitive_specs():
            counts[spec.family or spec.id] = counts.get(spec.family or spec.id, 0) + 1

        self.assertEqual(
            counts,
            {
                "diagonal_stroke": 10,
                "filled_circle": 10,
                "filled_rectangle": 10,
                "filled_square": 10,
                "horizontal_stroke": 10,
                "outlined_ring": 10,
                "rounded_rectangle": 10,
                "simple_quad": 10,
                "vertical_stroke": 10,
                "arc_up": 3,
                "arc_down": 3,
                "arc_left": 3,
                "arc_right": 3,
                "arc_shallow": 3,
                "arc_steep": 3,
                "arc_thick": 3,
                "arc_small_radius": 3,
                "antialiased_circle": 3,
                "antialiased_ring": 3,
                "antialiased_stroke": 3,
                "palette_drift_primitive": 3,
                "transparent_circle": 3,
                "composition_circle_plus_stroke": 3,
                "composition_different_color_separated": 3,
                "composition_dot_row": 3,
                "composition_multiple_strokes": 3,
                "composition_ring_plus_dot": 3,
                "composition_same_color_separated": 3,
                "composition_square_plus_circle": 3,
                "adjacent_different_color_rects": 3,
                "adjacent_same_color_rects_merge": 3,
                "adjacent_small_gap_rects": 3,
                "overlapping_rectangles_ordered": 3,
                "stroke_crossing_rectangle": 3,
                "touching_circle_stroke": 3,
                "cutout_diagonal_gap": 3,
                "cutout_horizontal_gap": 3,
                "group_dot_row": 3,
                "group_parallel_strokes": 3,
                "group_quad_grid": 3,
            },
        )

    def test_primitive_quality_markdown_summarizes_failures(self):
        markdown = render_primitive_quality_markdown(
            {
                "case_count": 1,
                "passed_count": 0,
                "failed_count": 1,
                "ok": False,
                "cases": [
                    {
                        "id": "filled_square",
                        "ok": False,
                        "actual_kind": "cubic_path",
                        "failure_categories": ["fallback_path"],
                        "metrics": {
                            "raster_l1_error": 0.2,
                            "raster_edge_error": 0.1,
                        },
                        "geometry": {"bbox_iou": 0.4},
                        "failures": ["unexpected cubic_path fallback"],
                    }
                ],
            }
        )

        self.assertIn("filled_square", markdown)
        self.assertIn("unexpected cubic_path fallback", markdown)

    def test_primitive_check_cli_writes_report_markdown_and_artifacts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output = root / "primitive-report.json"
            markdown = root / "primitive-report.md"
            artifact_dir = root / "artifacts"

            with redirect_stdout(StringIO()) as stdout:
                main(
                    [
                        "primitive-check",
                        "-o",
                        str(output),
                        "--output-dir",
                        str(artifact_dir),
                        "--markdown",
                        str(markdown),
                    ]
                )

            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertTrue(report["ok"])
            self.assertTrue(markdown.exists())
            self.assertTrue((artifact_dir / "filled_square" / "output.svg").exists())
            self.assertIn("primitive cases", stdout.getvalue())

    def test_primitive_check_cli_filters_cases(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output = root / "primitive-report.json"

            with redirect_stdout(StringIO()):
                main(
                    [
                        "primitive-check",
                        "-o",
                        str(output),
                        "--case",
                        "filled_square",
                    ]
                )

            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertTrue(report["ok"])
            self.assertEqual(report["selected_case_ids"], ["filled_square"])

    def test_primitive_check_cli_exits_nonzero_for_empty_selection(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "primitive-report.json"

            with self.assertRaises(SystemExit) as raised:
                with redirect_stdout(StringIO()):
                    main(
                        [
                            "primitive-check",
                            "-o",
                            str(output),
                            "--filter",
                            "does-not-match",
                        ]
                    )

            self.assertEqual(raised.exception.code, 1)
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertFalse(report["ok"])
            self.assertEqual(report["case_count"], 0)

    def test_primitive_check_cli_accepts_config_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output = root / "primitive-report.json"
            markdown = root / "primitive-report.md"
            artifact_dir = root / "artifacts"
            config = root / "primitive-check.json"
            config.write_text(
                json.dumps(
                    {
                        "output": str(output),
                        "output_dir": str(artifact_dir),
                        "markdown": str(markdown),
                        "case": "filled_square",
                    }
                ),
                encoding="utf-8",
            )

            with redirect_stdout(StringIO()):
                main(["primitive-check", "--config", str(config)])

            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(report["case_count"], 1)
            self.assertEqual(report["selection"]["cases"], ["filled_square"])
            self.assertTrue(markdown.exists())


def _svg_rects(path: Path) -> list[dict[str, float]]:
    root = ET.fromstring(path.read_text(encoding="utf-8"))
    rects: list[dict[str, float]] = []
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1] != "rect":
            continue
        rects.append(
            {
                "x0": float(element.attrib["x"]),
                "y0": float(element.attrib["y"]),
                "x1": float(element.attrib["x"]) + float(element.attrib["width"]),
                "y1": float(element.attrib["y"]) + float(element.attrib["height"]),
            }
        )
    return rects


def _has_touching_rect_pair(rects: list[dict[str, float]]) -> bool:
    for index, first in enumerate(rects):
        for second in rects[index + 1 :]:
            if _rects_touch_vertically(first, second) or _rects_touch_horizontally(
                first,
                second,
            ):
                return True
    return False


def _rects_touch_vertically(first: dict[str, float], second: dict[str, float]) -> bool:
    touches_x = abs(first["x1"] - second["x0"]) < 1e-9 or abs(
        second["x1"] - first["x0"]
    ) < 1e-9
    overlaps_y = min(first["y1"], second["y1"]) - max(first["y0"], second["y0"]) > 0
    return touches_x and overlaps_y


def _rects_touch_horizontally(first: dict[str, float], second: dict[str, float]) -> bool:
    touches_y = abs(first["y1"] - second["y0"]) < 1e-9 or abs(
        second["y1"] - first["y0"]
    ) < 1e-9
    overlaps_x = min(first["x1"], second["x1"]) - max(first["x0"], second["x0"]) > 0
    return touches_y and overlaps_x


if __name__ == "__main__":
    unittest.main()
