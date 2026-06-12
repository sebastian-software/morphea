import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageDraw

from curve.cli import main
from curve.refinement import (
    RefinementConfig,
    available_refinement_backends,
    gate_refinement_result,
    refinement_backend_status,
    refine_manifest,
    render_refinement_gate_markdown,
)


class RefinementTests(unittest.TestCase):
    def test_refine_manifest_preserves_anchor_kind_and_adds_metadata(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manifest = _write_manifest(Path(temp_dir))
            output = Path(temp_dir) / "refined.json"

            result = refine_manifest(
                manifest=manifest,
                output=output,
                config=RefinementConfig(max_iterations=3, timeout_seconds=1.0),
            )

            self.assertEqual(result["anchors"][0]["kind"], "circle")
            self.assertTrue(result["refinement"]["structure_preserving"])
            self.assertTrue(
                result["refinement"]["structure_audit"]["structure_preserved"]
            )
            self.assertTrue(
                result["refinement"]["structure_audit"]["editability_preserved"]
            )
            self.assertEqual(
                result["refinement"]["structure_audit"]["changed_geometry_count"],
                0,
            )
            self.assertEqual(
                result["anchors"][0]["metrics"]["refinement_iterations"],
                3.0,
            )
            self.assertEqual(
                result["refinement"]["optimizer"]["stopped_reason"],
                "not_attempted",
            )
            self.assertIn("elapsed_seconds", result["refinement"]["optimizer"])
            self.assertTrue(output.exists())

    def test_refine_cli_writes_output(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manifest = _write_manifest(Path(temp_dir))
            output = Path(temp_dir) / "refined.json"

            with redirect_stdout(StringIO()):
                main(["refine", str(manifest), "-o", str(output)])

            result = json.loads(output.read_text())
            self.assertEqual(result["refinement"]["backend"], "local_metric")

    def test_local_metric_refinement_adjusts_circle_radius_from_source(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest = _write_circle_manifest(root, radius=3)
            source = _write_circle_source(root, radius=4)
            output = root / "refined.json"

            result = refine_manifest(
                manifest=manifest,
                output=output,
                config=RefinementConfig(
                    max_iterations=3,
                    timeout_seconds=1.0,
                    source_image=source,
                ),
            )

            self.assertEqual(result["anchors"][0]["kind"], "circle")
            self.assertEqual(result["anchors"][0]["circle"]["r"], 4.0)
            self.assertLess(
                result["refinement"]["optimizer"]["final_raster_l1_error"],
                result["refinement"]["optimizer"]["initial_raster_l1_error"],
            )
            self.assertIn(
                "final_raster_edge_error",
                result["refinement"]["optimizer"],
            )
            self.assertLess(
                result["refinement"]["optimizer"]["final_objective"],
                result["refinement"]["optimizer"]["initial_objective"],
            )
            self.assertIn("refinement_objective", result["metrics"])
            self.assertIn(
                result["refinement"]["optimizer"]["stopped_reason"],
                {"converged", "max_iterations"},
            )
            self.assertTrue(
                result["refinement"]["structure_audit"]["editability_preserved"]
            )
            self.assertEqual(
                result["refinement"]["structure_audit"]["changed_geometry_count"],
                1,
            )
            self.assertEqual(
                result["anchors"][0]["metrics"]["refinement_radius_delta"],
                1.0,
            )

    def test_differentiable_refinement_adjusts_circle_radius_from_source(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest = _write_circle_manifest(root, radius=3)
            source = _write_circle_source(root, radius=4)
            output = root / "refined.json"

            result = refine_manifest(
                manifest=manifest,
                output=output,
                config=RefinementConfig(
                    backend="differentiable",
                    max_iterations=5,
                    timeout_seconds=1.0,
                    source_image=source,
                ),
            )

            self.assertEqual(result["refinement"]["backend"], "differentiable")
            self.assertEqual(
                result["refinement"]["optimizer"]["renderer"],
                "soft_raster_primitives",
            )
            self.assertIn(
                "circle",
                result["refinement"]["optimizer"]["renderer_primitive_kinds"],
            )
            self.assertGreater(result["anchors"][0]["circle"]["r"], 3.0)
            self.assertLess(
                result["refinement"]["optimizer"]["final_objective"],
                result["refinement"]["optimizer"]["initial_objective"],
            )
            self.assertIn(
                "differentiable_radius_gradient",
                result["anchors"][0]["metrics"],
            )

    def test_differentiable_refinement_adjusts_quad_geometry_from_source(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest = _write_rect_manifest(root, inset=7)
            source = _write_rect_source(root, inset=6)
            output = root / "refined.json"

            result = refine_manifest(
                manifest=manifest,
                output=output,
                config=RefinementConfig(
                    backend="differentiable",
                    max_iterations=3,
                    timeout_seconds=1.0,
                    source_image=source,
                ),
            )

            corners = result["anchors"][0]["quad"]["corners"]
            self.assertEqual(result["anchors"][0]["kind"], "rect")
            self.assertLess(corners[0]["x"], 7.0)
            self.assertLess(corners[0]["y"], 7.0)
            self.assertGreater(corners[2]["x"], 13.0)
            self.assertGreater(corners[2]["y"], 13.0)
            self.assertIn(
                "rect",
                result["refinement"]["optimizer"]["optimized_parameter_kinds"],
            )
            self.assertIn(
                "rect",
                result["refinement"]["optimizer"]["renderer_primitive_kinds"],
            )
            self.assertLess(
                result["refinement"]["optimizer"]["final_objective"],
                result["refinement"]["optimizer"]["initial_objective"],
            )
            self.assertGreater(
                result["anchors"][0]["metrics"]["refinement_quad_corner_delta"],
                0.0,
            )
            self.assertIn(
                "differentiable_quad_scale_gradient",
                result["anchors"][0]["metrics"],
            )

    def test_refine_cli_accepts_source_image(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest = _write_circle_manifest(root, radius=3)
            source = _write_circle_source(root, radius=4)
            output = root / "refined.json"

            with redirect_stdout(StringIO()):
                main(
                    [
                        "refine",
                        str(manifest),
                        "-o",
                        str(output),
                        "--max-iterations",
                        "2",
                        "--source-image",
                        str(source),
                        "--raster-edge-weight",
                        "0.5",
                    ]
                )

            result = json.loads(output.read_text())
            self.assertTrue(result["refinement"]["optimizer"]["attempted"])
            self.assertEqual(result["refinement"]["raster_edge_weight"], 0.5)

    def test_refine_cli_accepts_config_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest = _write_circle_manifest(root, radius=3)
            source = _write_circle_source(root, radius=4)
            output = root / "refined.json"
            config = root / "refine.json"
            config.write_text(
                json.dumps(
                    {
                        "manifest": str(manifest),
                        "output": str(output),
                        "max_iterations": 2,
                        "timeout_seconds": 1.0,
                        "source_image": str(source),
                        "raster_l1_weight": 0.75,
                        "raster_edge_weight": 0.5,
                    }
                ),
                encoding="utf-8",
            )

            with redirect_stdout(StringIO()):
                main(["refine", "--config", str(config)])

            result = json.loads(output.read_text(encoding="utf-8"))
            self.assertTrue(result["refinement"]["optimizer"]["attempted"])
            self.assertEqual(result["refinement"]["max_iterations"], 2)
            self.assertEqual(result["refinement"]["raster_l1_weight"], 0.75)
            self.assertEqual(result["refinement"]["raster_edge_weight"], 0.5)

    def test_refinement_gate_accepts_improved_structure_preserving_result(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            refined = _write_refined_manifest(
                root,
                structure_preserved=True,
                editability_preserved=True,
                initial_objective=0.4,
                final_objective=0.2,
                attempted=True,
            )
            output = root / "gate.json"

            result = gate_refinement_result(
                refined_manifest=refined,
                output=output,
            )

            self.assertEqual(result["decision"], "accept")
            self.assertTrue(result["accepted"])
            self.assertEqual(result["optimizer"]["objective_delta"], -0.2)
            self.assertTrue(output.exists())

    def test_refinement_gate_rejects_structure_break_or_regression(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            refined = _write_refined_manifest(
                root,
                structure_preserved=False,
                editability_preserved=True,
                initial_objective=0.2,
                final_objective=0.4,
                attempted=True,
            )
            output = root / "gate.json"

            result = gate_refinement_result(
                refined_manifest=refined,
                output=output,
            )

            self.assertEqual(result["decision"], "reject")
            self.assertFalse(result["accepted"])
            self.assertIn("structure_not_preserved", result["reasons"])
            self.assertIn("objective_regressed", result["reasons"])

    def test_refinement_gate_marks_missing_metrics_for_review(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            refined = _write_refined_manifest(
                root,
                structure_preserved=True,
                editability_preserved=True,
                initial_objective=None,
                final_objective=None,
                attempted=False,
            )
            output = root / "gate.json"

            result = gate_refinement_result(
                refined_manifest=refined,
                output=output,
            )

            self.assertEqual(result["decision"], "manual_review")
            self.assertIn("missing_objective_metrics", result["reasons"])
            self.assertIn("optimizer_not_attempted", result["reasons"])

    def test_render_refinement_gate_markdown_summarizes_decision(self):
        markdown = render_refinement_gate_markdown(
            {
                "decision": "reject",
                "accepted": False,
                "refined_manifest": "refined.json",
                "reasons": ["objective_regressed"],
                "gates": {"max_objective_regression": 0.0},
                "structure_audit": {
                    "structure_preserved": True,
                    "editability_preserved": True,
                },
                "optimizer": {
                    "initial_objective": 0.2,
                    "final_objective": 0.4,
                    "objective_delta": 0.2,
                },
            }
        )

        self.assertIn("# Curve Refinement Gate", markdown)
        self.assertIn("- Decision: `reject`", markdown)
        self.assertIn("`objective_regressed`", markdown)

    def test_refinement_gate_cli_writes_json_and_markdown(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            refined = _write_refined_manifest(
                root,
                structure_preserved=True,
                editability_preserved=True,
                initial_objective=0.4,
                final_objective=0.4,
                attempted=True,
            )
            output = root / "gate.json"
            markdown = root / "gate.md"

            with redirect_stdout(StringIO()):
                main(
                    [
                        "refinement-gate",
                        str(refined),
                        "-o",
                        str(output),
                        "--markdown",
                        str(markdown),
                        "--allow-unchanged",
                    ]
                )

            result = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(result["decision"], "accept")
            self.assertTrue(markdown.exists())

    def test_refinement_gate_cli_accepts_config_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            refined = _write_refined_manifest(
                root,
                structure_preserved=True,
                editability_preserved=True,
                initial_objective=0.4,
                final_objective=0.4,
                attempted=True,
            )
            output = root / "gate.json"
            config = root / "refinement-gate.json"
            config.write_text(
                json.dumps(
                    {
                        "refined_manifest": str(refined),
                        "output": str(output),
                        "require_improvement": False,
                    }
                ),
                encoding="utf-8",
            )

            with redirect_stdout(StringIO()):
                main(["refinement-gate", "--config", str(config)])

            result = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(result["decision"], "accept")
            self.assertFalse(result["gates"]["require_improvement"])

    def test_local_metric_refinement_adjusts_quad_geometry_from_source(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest = _write_rect_manifest(root, inset=7)
            source = _write_rect_source(root, inset=6)
            output = root / "refined.json"

            result = refine_manifest(
                manifest=manifest,
                output=output,
                config=RefinementConfig(
                    max_iterations=1,
                    timeout_seconds=1.0,
                    source_image=source,
                ),
            )

            corners = result["anchors"][0]["quad"]["corners"]
            self.assertEqual(result["anchors"][0]["kind"], "rect")
            self.assertEqual(corners[0], {"x": 6.0, "y": 6.0})
            self.assertEqual(corners[2], {"x": 14.0, "y": 14.0})
            self.assertIn(
                "rect",
                result["refinement"]["optimizer"]["optimized_parameter_kinds"],
            )
            self.assertGreater(
                result["anchors"][0]["metrics"]["refinement_quad_corner_delta"],
                0.0,
            )

    def test_local_metric_refinement_adjusts_stroke_centerline_from_source(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest = _write_stroke_manifest(root, y=8)
            source = _write_stroke_source(root, y=9)
            output = root / "refined.json"

            result = refine_manifest(
                manifest=manifest,
                output=output,
                config=RefinementConfig(
                    max_iterations=2,
                    timeout_seconds=1.0,
                    source_image=source,
                ),
            )

            centerline = result["anchors"][0]["stroke"]["centerline"]
            self.assertEqual(result["anchors"][0]["kind"], "stroke_polyline")
            self.assertEqual(centerline[0], {"x": 4.0, "y": 9.0})
            self.assertEqual(centerline[1], {"x": 15.0, "y": 9.0})
            self.assertIn(
                "stroke_polyline",
                result["refinement"]["optimizer"]["optimized_parameter_kinds"],
            )
            self.assertGreater(
                result["anchors"][0]["metrics"]["refinement_stroke_centerline_delta"],
                0.0,
            )

    def test_unknown_refinement_backend_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manifest = _write_manifest(Path(temp_dir))

            with self.assertRaisesRegex(ValueError, "unsupported refinement backend"):
                refine_manifest(
                    manifest=manifest,
                    output=Path(temp_dir) / "refined.json",
                    config=RefinementConfig(backend="unknown"),
                )

    def test_refinement_rejects_unbounded_or_invalid_limits(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manifest = _write_manifest(Path(temp_dir))
            invalid_configs = [
                RefinementConfig(max_iterations=-1),
                RefinementConfig(timeout_seconds=0),
                RefinementConfig(raster_l1_weight=-0.1),
                RefinementConfig(raster_l1_weight=0.0, raster_edge_weight=0.0),
            ]

            for config in invalid_configs:
                with self.subTest(config=config):
                    with self.assertRaises(ValueError):
                        refine_manifest(
                            manifest=manifest,
                            output=Path(temp_dir) / "refined.json",
                            config=config,
                        )

    def test_optional_diffvg_backend_reports_not_configured(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manifest = _write_manifest(Path(temp_dir))

            with patch(
                "curve.refinement.is_optional_refinement_package_available",
                return_value=False,
            ):
                with self.assertRaisesRegex(RuntimeError, "status=not_installed"):
                    refine_manifest(
                        manifest=manifest,
                        output=Path(temp_dir) / "refined.json",
                        config=RefinementConfig(backend="diffvg"),
                    )

    def test_optional_differentiable_backend_stays_pending_when_package_exists(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manifest = _write_manifest(Path(temp_dir))

            with patch(
                "curve.refinement.is_optional_refinement_package_available",
                return_value=True,
            ):
                with self.assertRaisesRegex(RuntimeError, "status=adapter_pending"):
                    refine_manifest(
                        manifest=manifest,
                        output=Path(temp_dir) / "refined.json",
                        config=RefinementConfig(backend="diffvg"),
                    )

    def test_refinement_backend_status_reports_local_and_optional_state(self):
        local = refinement_backend_status("local_metric")
        with patch(
            "curve.refinement.is_optional_refinement_package_available",
            return_value=False,
        ):
            optional = refinement_backend_status("diffvg")

        self.assertTrue(local["backend_available"])
        self.assertEqual(local["status"], "available")
        self.assertFalse(optional["backend_available"])
        self.assertEqual(optional["status"], "not_installed")
        self.assertIn("pydiffvg", optional["package_candidates"])
        self.assertTrue(refinement_backend_status("differentiable")["backend_available"])

    def test_available_refinement_backends_lists_optional_diffvg(self):
        backends = available_refinement_backends()

        self.assertIn("local_metric", backends["local"])
        self.assertIn("differentiable", backends["local"])
        self.assertIn("diffvg", backends["optional"])
        self.assertIn("details", backends)
        self.assertEqual(backends["details"]["local_metric"]["status"], "available")
        self.assertEqual(backends["details"]["differentiable"]["status"], "available")


def _write_manifest(root: Path) -> Path:
    manifest = root / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "anchors": [
                    {
                        "kind": "circle",
                        "metrics": {},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return manifest


def _write_refined_manifest(
    root: Path,
    *,
    structure_preserved: bool,
    editability_preserved: bool,
    initial_objective: float | None,
    final_objective: float | None,
    attempted: bool,
) -> Path:
    manifest = root / "refined.json"
    manifest.write_text(
        json.dumps(
            {
                "anchors": [{"kind": "circle", "metrics": {}}],
                "refinement": {
                    "structure_audit": {
                        "structure_preserved": structure_preserved,
                        "editability_preserved": editability_preserved,
                    },
                    "optimizer": {
                        "attempted": attempted,
                        "timeout_reached": False,
                        "stopped_reason": "converged",
                        "initial_objective": initial_objective,
                        "final_objective": final_objective,
                        "initial_raster_l1_error": initial_objective,
                        "final_raster_l1_error": final_objective,
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    return manifest


def _write_circle_manifest(root: Path, *, radius: float) -> Path:
    manifest = root / "circle-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "width": 16,
                "height": 16,
                "anchor_count": 1,
                "anchors": [
                    {
                        "kind": "circle",
                        "circle": {"cx": 8, "cy": 8, "r": radius},
                        "color": "#dd2222",
                        "metrics": {},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return manifest


def _write_circle_source(root: Path, *, radius: int) -> Path:
    source = root / "source.png"
    image = Image.new("RGB", (16, 16), "white")
    draw = ImageDraw.Draw(image)
    draw.ellipse((8 - radius, 8 - radius, 8 + radius, 8 + radius), fill="#dd2222")
    image.save(source)
    return source


def _write_rect_manifest(root: Path, *, inset: float) -> Path:
    manifest = root / "rect-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "width": 20,
                "height": 20,
                "anchor_count": 1,
                "anchors": [
                    {
                        "kind": "rect",
                        "quad": {
                            "corners": [
                                {"x": inset, "y": inset},
                                {"x": 20 - inset, "y": inset},
                                {"x": 20 - inset, "y": 20 - inset},
                                {"x": inset, "y": 20 - inset},
                            ]
                        },
                        "color": "#dd2222",
                        "metrics": {},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return manifest


def _write_rect_source(root: Path, *, inset: int) -> Path:
    source = root / "rect-source.png"
    image = Image.new("RGB", (20, 20), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((inset, inset, 20 - inset, 20 - inset), fill="#dd2222")
    image.save(source)
    return source


def _write_stroke_manifest(root: Path, *, y: float) -> Path:
    manifest = root / "stroke-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "width": 20,
                "height": 20,
                "anchor_count": 1,
                "anchors": [
                    {
                        "kind": "stroke_polyline",
                        "stroke": {
                            "centerline": [
                                {"x": 4, "y": y},
                                {"x": 15, "y": y},
                            ],
                            "width_samples": [3.0],
                        },
                        "color": "#dd2222",
                        "metrics": {},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return manifest


def _write_stroke_source(root: Path, *, y: int) -> Path:
    source = root / "stroke-source.png"
    image = Image.new("RGB", (20, 20), "white")
    draw = ImageDraw.Draw(image)
    draw.line((4, y, 15, y), fill="#dd2222", width=3)
    image.save(source)
    return source


if __name__ == "__main__":
    unittest.main()
