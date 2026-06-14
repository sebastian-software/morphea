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
    primitive_variant_specs,
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
                    "variant_count": 0,
                    "variant_seed": 1,
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
                self.assertIn("variant_source", case)
                self.assertIn("topology", case)
                self.assertIn("geometry_diff", case)
                self.assertIn("failure_categories", case)
                self.assertIn("failure_details", case)
                self.assertTrue((case_dir / "input.png").exists())
                self.assertTrue((case_dir / "output.svg").exists())
                self.assertTrue((case_dir / "manifest.json").exists())
                self.assertTrue((case_dir / "preview.png").exists())

    def test_primitive_quality_harness_adds_seeded_variants(self):
        report = check_primitive_quality(
            variant_count=6,
            variant_seed=11,
            filter_pattern="variant_*",
        )

        self.assertTrue(report["ok"])
        self.assertEqual(report["case_count"], 6)
        self.assertEqual(report["failed_count"], 0)
        self.assertEqual(
            report["selected_case_ids"],
            [
                "variant_filled_square_11_0000",
                "variant_filled_rectangle_11_0001",
                "variant_filled_circle_11_0002",
                "variant_horizontal_stroke_11_0003",
                "variant_vertical_stroke_11_0004",
                "variant_simple_quad_11_0005",
            ],
        )
        self.assertEqual(report["variant_summary"], {"seeded": 6})
        self.assertEqual(report["selection"]["variant_count"], 6)
        self.assertEqual(report["selection"]["variant_seed"], 11)
        self.assertEqual(
            {case["variant_source"] for case in report["cases"]},
            {"seeded"},
        )

    def test_primitive_quality_harness_adds_extended_seeded_variants(self):
        report = check_primitive_quality(
            variant_count=9,
            variant_seed=11,
            filter_pattern="variant_*",
        )

        self.assertTrue(report["ok"])
        self.assertEqual(report["case_count"], 9)
        actual_kinds = {
            case["id"]: case["actual_kind"]
            for case in report["cases"]
        }
        self.assertEqual(
            actual_kinds,
            {
                "variant_filled_square_11_0000": "rect",
                "variant_filled_rectangle_11_0001": "rect",
                "variant_filled_circle_11_0002": "circle",
                "variant_horizontal_stroke_11_0003": "stroke_polyline",
                "variant_vertical_stroke_11_0004": "stroke_polyline",
                "variant_simple_quad_11_0005": "quad",
                "variant_diagonal_stroke_11_0006": "stroke_polyline",
                "variant_outlined_ring_11_0007": "stroke_circle",
                "variant_rounded_rectangle_11_0008": "rounded_rect",
            },
        )
        self.assertEqual(report["variant_summary"], {"seeded": 9})

    def test_primitive_variant_specs_are_seed_stable(self):
        first = primitive_variant_specs(count=4, seed=7)
        second = primitive_variant_specs(count=4, seed=7)
        different = primitive_variant_specs(count=4, seed=8)

        self.assertEqual([spec.id for spec in first], [spec.id for spec in second])
        self.assertEqual(
            [spec.geometry for spec in first],
            [spec.geometry for spec in second],
        )
        self.assertNotEqual(
            [spec.geometry for spec in first],
            [spec.geometry for spec in different],
        )
        self.assertEqual({spec.variant_source for spec in first}, {"seeded"})

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

    def test_simple_arc_exports_single_svg_arc_command(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            report = check_primitive_quality(
                output_dir=temp_dir,
                cases=("arc_up", "arc_down", "arc_left", "arc_right"),
            )

            self.assertTrue(report["ok"])
            for case in report["cases"]:
                svg = (Path(temp_dir) / case["id"] / "output.svg").read_text(
                    encoding="utf-8"
                )
                paths = [
                    line for line in svg.splitlines() if "<path" in line
                ]
                self.assertEqual(len(paths), 1)
                self.assertIn(" A ", paths[0])
                self.assertNotIn(" L ", paths[0])
                self.assertIn('stroke-linecap="round"', paths[0])
                manifest = json.loads(
                    (Path(temp_dir) / case["id"] / "manifest.json").read_text(
                        encoding="utf-8"
                    )
                )
                arc = manifest["anchors"][0]["arc"]
                self.assertGreater(arc["r"], 2.0)
                self.assertIn("sweep", arc)
                self.assertIn("large_arc", arc)

    def test_straight_strokes_still_export_two_point_lines(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            report = check_primitive_quality(
                output_dir=temp_dir,
                cases=("horizontal_stroke", "outlined_ring"),
            )

            self.assertTrue(report["ok"])
            stroke_svg = (
                Path(temp_dir) / "horizontal_stroke" / "output.svg"
            ).read_text(encoding="utf-8")
            self.assertIn(" L ", stroke_svg)
            self.assertNotIn(" A ", stroke_svg)
            ring_svg = (
                Path(temp_dir) / "outlined_ring" / "output.svg"
            ).read_text(encoding="utf-8")
            self.assertIn("<circle", ring_svg)
            self.assertNotIn("<path", ring_svg)

    def test_smooth_curves_export_cubic_segments_with_bounded_controls(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            report = check_primitive_quality(
                output_dir=temp_dir,
                cases=("curve_s", "curve_wave", "curve_square_caps"),
            )

            self.assertTrue(report["ok"])
            for case in report["cases"]:
                self.assertEqual(case["actual_kind"], "stroke_path")
                svg = (Path(temp_dir) / case["id"] / "output.svg").read_text(
                    encoding="utf-8"
                )
                self.assertIn(" C ", svg)
                self.assertNotIn(" A ", svg)
                manifest = json.loads(
                    (Path(temp_dir) / case["id"] / "manifest.json").read_text(
                        encoding="utf-8"
                    )
                )
                centerline = manifest["anchors"][0]["stroke"]["centerline"]
                self.assertLessEqual(len(centerline), 9)
                self.assertGreaterEqual(len(centerline), 3)
            caps = {
                case["id"]: json.loads(
                    (Path(temp_dir) / case["id"] / "manifest.json").read_text(
                        encoding="utf-8"
                    )
                )["anchors"][0]["stroke"]["cap_style"]
                for case in report["cases"]
            }
            self.assertEqual(caps["curve_s"], "round")
            self.assertEqual(caps["curve_square_caps"], "butt")

    def test_curved_cutouts_stay_editable_and_compare_exports(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            report = check_primitive_quality(
                output_dir=temp_dir,
                cases=("cutout_curve_rect", "cutout_curve_ring"),
            )

            self.assertTrue(report["ok"])
            for case in report["cases"]:
                self.assertEqual(case["topology"]["expected_cutout_count"], 1)
                self.assertEqual(case["topology"]["actual_cutout_count"], 1)
                self.assertEqual(case["topology"]["expected_hole_count"], 0)
                self.assertEqual(case["topology"]["actual_hole_count"], 0)
                comparison = case["export_comparison"]
                self.assertTrue(comparison["ok"])
                self.assertEqual(comparison["cutout_anchor_count"], 1)
                manifest = json.loads(
                    (Path(temp_dir) / case["id"] / "manifest.json").read_text(
                        encoding="utf-8"
                    )
                )
                cutouts = [
                    anchor
                    for anchor in manifest["anchors"]
                    if anchor.get("stroke", {}).get("is_cutout")
                ]
                self.assertEqual(len(cutouts), 1)
                # Circular slits fit a true arc and export an A command.
                self.assertEqual(cutouts[0]["kind"], "arc")
                self.assertEqual(len(cutouts[0]["stroke"]["centerline"]), 3)
                self.assertIn("arc", cutouts[0])
                svg = (Path(temp_dir) / case["id"] / "output.svg").read_text(
                    encoding="utf-8"
                )
                self.assertIn('stroke="#ffffff"', svg)
                self.assertIn(" A ", svg)

    def test_organic_fallback_is_controlled_and_inspectable(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            report = check_primitive_quality(
                output_dir=temp_dir,
                cases=("organic_blob", "organic_crescent"),
            )

            self.assertTrue(report["ok"])
            for case in report["cases"]:
                self.assertEqual(case["actual_kind"], "cubic_path")
                manifest = json.loads(
                    (Path(temp_dir) / case["id"] / "manifest.json").read_text(
                        encoding="utf-8"
                    )
                )
                anchor = manifest["anchors"][0]
                self.assertLessEqual(anchor["path"]["node_count"], 16)
                self.assertEqual(
                    anchor["path"]["fallback_reason"],
                    "organic_boundary_fit",
                )
                self.assertIn("path_smoothness", anchor["metrics"])
                svg = (Path(temp_dir) / case["id"] / "output.svg").read_text(
                    encoding="utf-8"
                )
                self.assertIn(" C ", svg)
                self.assertIn("Z", svg)
            self.assertEqual(report["curve_anchor_kind_counts"]["cubic_path"], 2)

    def test_organic_holes_report_nested_path_topology(self):
        report = check_primitive_quality(
            cases=("organic_donut", "organic_double_hole"),
        )

        self.assertTrue(report["ok"])
        topology_by_case = {
            case["id"]: case["topology"]
            for case in report["cases"]
        }
        self.assertEqual(
            topology_by_case["organic_donut"],
            {
                "expected_hole_count": 1,
                "actual_hole_count": 1,
                "expected_cutout_count": 0,
                "actual_cutout_count": 0,
                "path_anchor_count": 1,
                "cutout_anchor_indexes": [],
                "hole_anchor_indexes": [0],
            },
        )
        self.assertEqual(
            topology_by_case["organic_double_hole"],
            {
                "expected_hole_count": 2,
                "actual_hole_count": 2,
                "expected_cutout_count": 0,
                "actual_cutout_count": 0,
                "path_anchor_count": 1,
                "cutout_anchor_indexes": [],
                "hole_anchor_indexes": [0],
            },
        )

    def test_curve_compositions_keep_groups_and_kinds(self):
        report = check_primitive_quality(
            cases=(
                "composition_parallel_arcs",
                "composition_curve_group",
                "composition_curve_crossing_rect",
            ),
        )

        self.assertTrue(report["ok"])
        by_id = {case["id"]: case for case in report["cases"]}
        self.assertEqual(
            by_id["composition_parallel_arcs"]["anchor_kind_counts"],
            {"arc": 2},
        )
        self.assertEqual(
            [
                match["expected_kind"]
                for match in by_id["composition_parallel_arcs"]["group_matches"]
            ],
            ["parallel_stroke_group"],
        )
        self.assertEqual(
            by_id["composition_curve_group"]["anchor_kind_counts"],
            {"stroke_path": 2},
        )
        crossing = by_id["composition_curve_crossing_rect"]
        self.assertEqual(crossing["anchor_kind_counts"]["rect"], 1)
        self.assertEqual(crossing["anchor_kind_counts"]["stroke_path"], 1)

    def test_antialiased_curves_do_not_fragment(self):
        report = check_primitive_quality(
            cases=(
                "antialiased_arc",
                "antialiased_curve_s",
                "transparent_curve_s",
                "drift_curve_s",
            ),
        )

        self.assertTrue(report["ok"])
        for case in report["cases"]:
            self.assertEqual(case["anchor_count"], 1)
        kinds = {case["id"]: case["actual_kind"] for case in report["cases"]}
        self.assertEqual(kinds["antialiased_arc"], "arc")
        self.assertEqual(kinds["antialiased_curve_s"], "stroke_path")
        self.assertEqual(kinds["transparent_curve_s"], "stroke_path")
        self.assertEqual(kinds["drift_curve_s"], "stroke_path")

    def test_ellipse_fixtures_export_editable_ellipse_primitives(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            report = check_primitive_quality(
                output_dir=temp_dir,
                cases=(
                    "ellipse_horizontal",
                    "stroked_ellipse",
                    "filled_circle",
                    "rounded_rectangle",
                ),
            )

            self.assertTrue(report["ok"])
            kinds = {case["id"]: case["actual_kind"] for case in report["cases"]}
            self.assertEqual(kinds["ellipse_horizontal"], "ellipse")
            self.assertEqual(kinds["stroked_ellipse"], "stroke_ellipse")
            # Gate D: circles stay circles and rounded rects stay rects.
            self.assertEqual(kinds["filled_circle"], "circle")
            self.assertEqual(kinds["rounded_rectangle"], "rounded_rect")
            filled_svg = (
                Path(temp_dir) / "ellipse_horizontal" / "output.svg"
            ).read_text(encoding="utf-8")
            self.assertIn("<ellipse", filled_svg)
            self.assertNotIn("<path", filled_svg)
            stroked_svg = (
                Path(temp_dir) / "stroked_ellipse" / "output.svg"
            ).read_text(encoding="utf-8")
            self.assertIn('fill="none"', stroked_svg)
            self.assertIn("<ellipse", stroked_svg)
            manifest = json.loads(
                (Path(temp_dir) / "ellipse_horizontal" / "manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            ellipse = manifest["anchors"][0]["ellipse"]
            self.assertGreater(ellipse["rx"], ellipse["ry"])

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
                "variant_count": 0,
                "variant_seed": 1,
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

    def test_refinement_gate_reports_curve_parameter_deltas(self):
        report = check_primitive_quality(
            cases=("arc_up", "curve_s", "organic_blob"),
            refine=True,
        )

        self.assertTrue(report["ok"])
        for case in report["cases"]:
            refinement = case["refinement"]
            self.assertTrue(refinement["ok"])
            self.assertTrue(refinement["structure_audit"]["structure_preserved"])
            deltas = refinement["parameter_deltas"]
            self.assertEqual(len(deltas), 1)
            self.assertFalse(deltas[0]["node_count_changed"])
            self.assertFalse(deltas[0]["cap_or_join_changed"])
        arc_delta = next(
            case["refinement"]["parameter_deltas"][0]
            for case in report["cases"]
            if case["id"] == "arc_up"
        )
        self.assertIn("arc_delta", arc_delta)

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
                "arc_up": 10,
                "arc_down": 3,
                "arc_left": 3,
                "arc_right": 3,
                "arc_shallow": 3,
                "arc_steep": 3,
                "arc_thick": 3,
                "arc_small_radius": 3,
                "curve_quadratic": 3,
                "curve_s": 10,
                "curve_wave": 3,
                "curve_asymmetric": 3,
                "curve_diagonal": 3,
                "curve_square_caps": 3,
                "curve_round_caps": 3,
                "ellipse_horizontal": 3,
                "ellipse_vertical": 3,
                "ellipse_small": 3,
                "ellipse_large": 3,
                "ellipse_wide": 3,
                "stroked_ellipse": 3,
                "antialiased_ellipse": 3,
                "cutout_curve_rect": 3,
                "cutout_curve_circle": 3,
                "cutout_curve_ring": 3,
                "cutout_curve_crossing": 3,
                "cutout_near_background": 3,
                "antialiased_arc": 3,
                "antialiased_curve": 3,
                "drift_curve": 3,
                "transparent_arc": 3,
                "transparent_curve": 3,
                "composition_arc_circle": 3,
                "composition_arc_rect": 3,
                "composition_curve_crossing_rect": 3,
                "composition_curve_touching_circle": 3,
                "composition_ellipse_stroke": 3,
                "composition_parallel_arcs": 3,
                "composition_curve_group": 3,
                "organic_blob": 3,
                "organic_leaf": 3,
                "organic_asymmetric": 3,
                "organic_crescent": 3,
                "organic_compound": 3,
                "organic_donut": 3,
                "organic_frame": 3,
                "organic_double_hole": 3,
                "concave_c": 3,
                "concave_u": 3,
                "concave_embrace": 3,
                "corner_star": 3,
                "corner_arrow": 3,
                "corner_notch": 3,
                "cutout_curve_s": 3,
                "cutout_curve_wave": 3,
                "tiny_dot": 3,
                "tiny_ring": 3,
                "tiny_rect": 3,
                "rotated_ellipse": 3,
                "dominant_palette": 3,
                "palette_seam": 3,
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
                        "topology": {
                            "expected_hole_count": 1,
                            "actual_hole_count": 0,
                            "expected_cutout_count": 0,
                            "actual_cutout_count": 0,
                        },
                        "failures": ["unexpected cubic_path fallback"],
                    }
                ],
            }
        )

        self.assertIn("filled_square", markdown)
        self.assertIn(
            "| Case | OK | Actual | L1 | Edge | SVG L1 | SVG Edge | "
            "IoU | Holes | Cutouts | Failures |",
            markdown,
        )
        self.assertIn(
            "| `filled_square` | `false` | `cubic_path` | 0.2 | 0.1 | "
            "n/a | n/a | 0.4 | 0/1 | 0/0 |",
            markdown,
        )
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

    def test_primitive_check_cli_accepts_seeded_variants(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "primitive-report.json"

            with redirect_stdout(StringIO()):
                main(
                    [
                        "primitive-check",
                        "-o",
                        str(output),
                        "--variant-count",
                        "3",
                        "--variant-seed",
                        "13",
                        "--filter",
                        "variant_*",
                    ]
                )

            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertTrue(report["ok"])
            self.assertEqual(report["case_count"], 3)
            self.assertEqual(report["variant_summary"], {"seeded": 3})
            self.assertEqual(report["selection"]["variant_count"], 3)
            self.assertEqual(report["selection"]["variant_seed"], 13)

    def test_primitive_check_config_accepts_seeded_variants(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output = root / "primitive-report.json"
            config = root / "primitive-check.json"
            config.write_text(
                json.dumps(
                    {
                        "output": str(output),
                        "filter": "variant_*",
                        "variant_count": 2,
                        "variant_seed": 5,
                    }
                ),
                encoding="utf-8",
            )

            with redirect_stdout(StringIO()):
                main(["primitive-check", "--config", str(config)])

            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(
                report["selected_case_ids"],
                [
                    "variant_filled_square_5_0000",
                    "variant_filled_rectangle_5_0001",
                ],
            )
            self.assertEqual(report["selection"]["variant_count"], 2)


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
