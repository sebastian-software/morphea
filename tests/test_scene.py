import unittest

from morphea.masks import BinaryMask
from morphea.anchors import (
    AnchorCandidate,
    AnchorKind,
    CircleAnchor,
    Point,
    QuadAnchor,
    StrokeAnchor,
)
from morphea.scene import (
    SCENE_MANIFEST_SCHEMA_VERSION,
    Scene,
    SvgStyle,
    merge_auto_mergeable_same_color_fragments,
    promote_occluded_rect_fragment_groups,
    promote_occluded_rect_primitives,
    scene_from_mask,
    scene_layers_to_manifest,
    scene_groups_to_manifest,
    scene_metrics_to_manifest,
)


class SceneExportTests(unittest.TestCase):
    def test_circle_mask_exports_editable_svg_circle(self):
        mask = BinaryMask.from_rows(
            (
                "...###...",
                "..#####..",
                ".#######.",
                "#########",
                "#########",
                "#########",
                ".#######.",
                "..#####..",
                "...###...",
            )
        )

        svg = scene_from_mask(mask).to_svg(SvgStyle(fill="#123456"))

        self.assertIn("<circle ", svg)
        self.assertIn('fill="#123456"', svg)
        self.assertNotIn("<polygon", svg)

    def test_stroke_mask_exports_editable_svg_stroke_path(self):
        mask = BinaryMask.from_rows(
            (
                "............",
                ".##########.",
                ".##########.",
                "............",
            )
        )

        svg = scene_from_mask(mask).to_svg(SvgStyle(stroke="#ffffff"))

        self.assertIn("<path ", svg)
        self.assertIn('fill="none"', svg)
        self.assertIn('stroke="#ffffff"', svg)
        self.assertIn('stroke-linecap="butt"', svg)

    def test_stroke_manifest_and_svg_preserve_cap_and_join_styles(self):
        anchor = AnchorCandidate(
            kind=AnchorKind.STROKE_POLYLINE,
            raster_error=0.0,
            node_count=2,
            parameter_count=5,
            stroke=StrokeAnchor(
                centerline=(Point(1, 2), Point(8, 2), Point(10, 4)),
                width_samples=(2.0,),
                cap_style="square",
                join_style="miter",
            ),
        )
        scene = Scene(width=12, height=8, anchors=(anchor,))

        svg = scene.to_svg()
        manifest = scene.to_manifest()

        self.assertIn('stroke-linecap="square"', svg)
        self.assertIn('stroke-linejoin="miter"', svg)
        self.assertEqual(manifest["anchors"][0]["stroke"]["cap_style"], "square")
        self.assertEqual(manifest["anchors"][0]["stroke"]["join_style"], "miter")

    def test_closed_stroke_path_exports_closed_svg_path(self):
        anchor = AnchorCandidate(
            kind=AnchorKind.STROKE_PATH,
            raster_error=0.0,
            node_count=4,
            parameter_count=9,
            stroke=StrokeAnchor(
                centerline=(
                    Point(2, 2),
                    Point(5, 10),
                    Point(7, 6),
                    Point(10, 5),
                ),
                width_samples=(2.0,),
                closed=True,
            ),
        )
        scene = Scene(width=12, height=12, anchors=(anchor,))

        svg = scene.to_svg()
        manifest = scene.to_manifest()

        self.assertIn(" Z", svg)
        self.assertIn('fill="none"', svg)
        self.assertTrue(manifest["anchors"][0]["stroke"]["closed"])

    def test_butt_stroke_manifest_bounds_do_not_extend_along_centerline(self):
        anchor = AnchorCandidate(
            kind=AnchorKind.STROKE_POLYLINE,
            raster_error=0.0,
            node_count=2,
            parameter_count=5,
            stroke=StrokeAnchor(
                centerline=(Point(10, 5), Point(20, 5)),
                width_samples=(4.0,),
                cap_style="butt",
            ),
        )

        manifest = Scene(width=32, height=16, anchors=(anchor,)).to_manifest()

        self.assertEqual(
            manifest["anchors"][0]["reserved"]["bounds"],
            [10.0, 3.0, 20.0, 7.0],
        )

    def test_square_stroke_manifest_bounds_extend_along_centerline(self):
        anchor = AnchorCandidate(
            kind=AnchorKind.STROKE_POLYLINE,
            raster_error=0.0,
            node_count=2,
            parameter_count=5,
            stroke=StrokeAnchor(
                centerline=(Point(10, 5), Point(20, 5)),
                width_samples=(4.0,),
                cap_style="square",
            ),
        )

        manifest = Scene(width=32, height=16, anchors=(anchor,)).to_manifest()

        self.assertEqual(
            manifest["anchors"][0]["reserved"]["bounds"],
            [8.0, 3.0, 22.0, 7.0],
        )

    def test_arc_exports_as_editable_svg_stroke(self):
        anchor = AnchorCandidate(
            kind=AnchorKind.ARC,
            raster_error=0.0,
            node_count=3,
            parameter_count=6,
            stroke=StrokeAnchor(
                centerline=(Point(2, 8), Point(6, 4), Point(10, 8)),
                width_samples=(2.0,),
            ),
        )
        scene = Scene(width=12, height=12, anchors=(anchor,))

        svg = scene.to_svg()

        self.assertIn("<path ", svg)
        self.assertIn('stroke-linecap="round"', svg)
        self.assertIn('stroke-linejoin="round"', svg)

    def test_rect_and_rounded_rect_export_as_svg_rects(self):
        rect = AnchorCandidate(
            kind=AnchorKind.RECT,
            raster_error=0.0,
            node_count=4,
            parameter_count=4,
            quad=QuadAnchor(
                corners=(Point(2, 3), Point(8, 3), Point(8, 7), Point(2, 7)),
            ),
        )
        rounded = AnchorCandidate(
            kind=AnchorKind.ROUNDED_RECT,
            raster_error=0.0,
            node_count=4,
            parameter_count=5,
            quad=QuadAnchor(
                corners=(Point(3, 9), Point(10, 9), Point(10, 13), Point(3, 13)),
            ),
            metrics={"corner_radius": 2.0},
        )
        scene = Scene(width=14, height=16, anchors=(rect, rounded))

        svg = scene.to_svg()

        self.assertIn(
            '<rect x="2" y="3" width="7" height="5" rx="0" ry="0"',
            svg,
        )
        self.assertIn('shape-rendering="crispEdges"', svg)
        self.assertIn('<rect x="3" y="9" width="8" height="5" rx="2" ry="2"', svg)

    def test_circle_ring_exports_editable_svg_stroke_circle(self):
        mask = BinaryMask.from_rows(
            (
                "...#######...",
                "..#########..",
                ".####...####.",
                "###.......###",
                "##.........##",
                "##.........##",
                "##.........##",
                "###.......###",
                ".####...####.",
                "..#########..",
                "...#######...",
            )
        )

        svg = scene_from_mask(mask).to_svg(SvgStyle(stroke="#c99700"))

        self.assertIn("<circle ", svg)
        self.assertIn('fill="none"', svg)
        self.assertIn('stroke="#c99700"', svg)
        self.assertIn("stroke-width=", svg)

    def test_perspective_quad_exports_editable_svg_polygon(self):
        mask = BinaryMask.from_rows(
            (
                "....####....",
                "...######...",
                "..########..",
                ".##########.",
                "############",
            )
        )

        svg = scene_from_mask(mask).to_svg(SvgStyle(fill="#d0a21a"))

        self.assertIn("<polygon ", svg)
        self.assertIn('fill="#d0a21a"', svg)
        self.assertNotIn("unsupported anchor", svg)

    def test_multiple_quads_are_reported_as_grid_group(self):
        tile = BinaryMask.from_rows(
            (
                "....####....",
                "...######...",
                "..########..",
                ".##########.",
                "############",
            )
        )
        shifted_pixels = {(x + 16, y) for x, y in tile.pixels}
        mask = BinaryMask(
            width=28,
            height=5,
            pixels=tile.pixels | frozenset(shifted_pixels),
        )

        manifest = scene_from_mask(mask).to_manifest()

        self.assertEqual(manifest["schema_version"], SCENE_MANIFEST_SCHEMA_VERSION)
        self.assertEqual(manifest["groups"][0]["kind"], "perspective_grid")
        self.assertEqual(manifest["groups"][0]["anchor_indexes"], [0, 1])
        self.assertEqual(manifest["groups"][0]["row_count"], 1)
        self.assertEqual(manifest["groups"][0]["column_count"], 2)
        self.assertIn(
            "perspective_grid_consistency_error",
            manifest["groups"][0]["metrics"],
        )
        self.assertEqual(
            manifest["groups"][0]["metrics"]["vanishing_line_diagnostics"][
                "horizontal_edge_pairs"
            ],
            2,
        )
        self.assertIn("editability_score", manifest["metrics"])

    def test_parallel_strokes_are_reported_as_group(self):
        anchors = (
            AnchorCandidate(
                kind=AnchorKind.STROKE_POLYLINE,
                raster_error=0.0,
                node_count=2,
                parameter_count=5,
                stroke=StrokeAnchor(
                    centerline=(Point(0, 0), Point(10, 0)),
                    width_samples=(2.0,),
                    parallel_group_id="parallel-a",
                ),
            ),
            AnchorCandidate(
                kind=AnchorKind.STROKE_POLYLINE,
                raster_error=0.0,
                node_count=2,
                parameter_count=5,
                stroke=StrokeAnchor(
                    centerline=(Point(0, 4), Point(10, 4)),
                    width_samples=(2.0,),
                    parallel_group_id="parallel-a",
                ),
            ),
        )

        manifest = Scene(width=12, height=8, anchors=anchors).to_manifest()

        self.assertEqual(manifest["groups"][0]["kind"], "parallel_stroke_group")
        self.assertEqual(manifest["groups"][0]["id"], "parallel-a")
        self.assertEqual(manifest["groups"][0]["anchor_indexes"], [0, 1])
        self.assertIn("parallel_spacing_error", manifest["groups"][0]["metrics"])

    def test_manifest_explains_anchor_layer_reservation_and_provenance(self):
        mask = BinaryMask.from_rows(
            (
                "...###...",
                "..#####..",
                ".#######.",
                "#########",
                "#########",
                "#########",
                ".#######.",
                "..#####..",
                "...###...",
            )
        )

        manifest = scene_from_mask(mask).to_manifest()
        anchor = manifest["anchors"][0]

        self.assertEqual(anchor["id"], "anchor-0000")
        self.assertEqual(anchor["layer"], "filled_primitives")
        self.assertEqual(anchor["reserved"]["reason"], "simple_shape_anchor")
        self.assertEqual(anchor["source_mask"]["id"], "mask-0000")
        self.assertEqual(anchor["source_mask"]["source"], "reserved_bounds")
        self.assertEqual(anchor["source_mask"]["bounds"], anchor["reserved"]["bounds"])
        self.assertGreater(anchor["source_mask"]["bounds_area"], 0.0)
        self.assertEqual(anchor["provenance"]["source"], "primitive_anchor_detection")
        self.assertTrue(anchor["export_policy"]["editable"])
        self.assertGreater(anchor["metrics"]["simple_shape_priority_bonus"], 0.0)
        self.assertIn("semantic_anchor_score", anchor["metrics"])
        self.assertGreater(anchor["confidence"], 0.0)
        self.assertEqual(manifest["layers"][0]["name"], "filled_primitives")
        self.assertEqual(manifest["layers"][0]["anchor_indexes"], [0])

    def test_scene_reservation_metrics_expose_simple_shape_area(self):
        circle = AnchorCandidate(
            kind=AnchorKind.CIRCLE,
            raster_error=0.0,
            node_count=1,
            parameter_count=3,
            circle=CircleAnchor(center=Point(5, 5), radius=2),
        )
        rect = AnchorCandidate(
            kind=AnchorKind.RECT,
            raster_error=0.0,
            node_count=4,
            parameter_count=4,
            quad=QuadAnchor(
                corners=(Point(10, 10), Point(14, 10), Point(14, 13), Point(10, 13)),
            ),
        )
        fallback = AnchorCandidate(
            kind=AnchorKind.CUBIC_PATH,
            raster_error=0.0,
            node_count=8,
            parameter_count=12,
        )

        manifest = Scene(width=20, height=20, anchors=(circle, rect, fallback)).to_manifest()
        reservation_group = [
            group
            for group in manifest["groups"]
            if group["kind"] == "primitive_anchor_reservation"
        ][0]

        self.assertEqual(reservation_group["anchor_indexes"], [0, 1])
        self.assertEqual(reservation_group["metrics"]["reserved_anchor_count"], 2)
        self.assertEqual(reservation_group["metrics"]["reserved_bounds_area"], 28.0)
        self.assertEqual(manifest["metrics"]["reserved_simple_shape_count"], 2)
        self.assertEqual(manifest["metrics"]["reserved_simple_shape_area"], 28.0)
        self.assertEqual(manifest["metrics"]["reserved_simple_shape_area_ratio"], 0.07)

    def test_scene_reservation_area_ratio_is_capped(self):
        anchors = (
            AnchorCandidate(
                kind=AnchorKind.CIRCLE,
                raster_error=0.0,
                node_count=1,
                parameter_count=3,
                circle=CircleAnchor(center=Point(4, 4), radius=4),
            ),
            AnchorCandidate(
                kind=AnchorKind.CIRCLE,
                raster_error=0.0,
                node_count=1,
                parameter_count=3,
                circle=CircleAnchor(center=Point(5, 5), radius=4),
            ),
        )

        manifest = Scene(width=8, height=8, anchors=anchors).to_manifest()

        self.assertEqual(manifest["metrics"]["reserved_simple_shape_area_ratio"], 1.0)

    def test_scene_layers_group_anchor_indexes_by_layer(self):
        anchors = (
            AnchorCandidate(
                kind=AnchorKind.CIRCLE,
                raster_error=0.0,
                node_count=1,
                parameter_count=3,
            ),
            AnchorCandidate(
                kind=AnchorKind.STROKE_POLYLINE,
                raster_error=0.0,
                node_count=2,
                parameter_count=5,
                stroke=StrokeAnchor(
                    centerline=(Point(0, 0), Point(4, 0)),
                    width_samples=(1.0,),
                    is_cutout=True,
                ),
            ),
        )

        layers = scene_layers_to_manifest(anchors)

        self.assertEqual(
            {layer["name"]: layer["anchor_indexes"] for layer in layers},
            {"cutout_overlays": [1], "filled_primitives": [0]},
        )

    def test_cutout_manifest_records_overlay_and_mask_candidate_policy(self):
        anchor = AnchorCandidate(
            kind=AnchorKind.STROKE_POLYLINE,
            raster_error=0.0,
            node_count=2,
            parameter_count=5,
            stroke=StrokeAnchor(
                centerline=(Point(1, 1), Point(8, 1)),
                width_samples=(2.0,),
                is_cutout=True,
            ),
        )

        manifest = Scene(width=10, height=4, anchors=(anchor,)).to_manifest()
        export_policy = manifest["anchors"][0]["export_policy"]

        self.assertEqual(export_policy["cutout_strategy"], "overlay_stroke")
        self.assertTrue(export_policy["mask_eligible"])
        self.assertEqual(manifest["metrics"]["cutout_overlay_count"], 1)
        self.assertEqual(manifest["metrics"]["negative_mask_candidate_count"], 1)

    def test_negative_mask_cutout_export_uses_editable_mask_strokes(self):
        fill = AnchorCandidate(
            kind=AnchorKind.RECT,
            raster_error=0.0,
            node_count=4,
            parameter_count=4,
            color="#003366",
            quad=QuadAnchor(
                corners=(Point(1, 1), Point(9, 1), Point(9, 5), Point(1, 5)),
            ),
        )
        cutout = AnchorCandidate(
            kind=AnchorKind.STROKE_POLYLINE,
            raster_error=0.0,
            node_count=2,
            parameter_count=5,
            color="#ffffff",
            stroke=StrokeAnchor(
                centerline=(Point(2, 3), Point(8, 3)),
                width_samples=(1.0,),
                is_cutout=True,
            ),
        )

        svg = Scene(width=10, height=6, anchors=(fill, cutout)).to_svg(
            SvgStyle(cutout_strategy="negative_mask")
        )

        self.assertIn('<mask id="morphea-cutout-mask"', svg)
        self.assertIn('mask="url(#morphea-cutout-mask)"', svg)
        self.assertIn('stroke="black"', svg)
        self.assertIn('fill="#003366"', svg)
        self.assertNotIn('stroke="#ffffff"', svg)

    def test_debug_svg_includes_anchor_ids_bounds_and_labels(self):
        mask = BinaryMask.from_rows(
            (
                "...###...",
                "..#####..",
                ".#######.",
                "#########",
                "#########",
                "#########",
                ".#######.",
                "..#####..",
                "...###...",
            )
        )

        svg = scene_from_mask(mask).to_debug_svg()

        self.assertIn('id="anchor-0000"', svg)
        self.assertIn('data-kind="circle"', svg)
        self.assertIn('stroke-dasharray="2 2"', svg)
        self.assertIn("anchor-0000:circle", svg)

    def test_scene_metrics_penalize_same_color_fragmentation(self):
        clean = (
            AnchorCandidate(
                kind=AnchorKind.CIRCLE,
                raster_error=0.0,
                node_count=1,
                parameter_count=3,
                color="#dd2222",
            ),
        )
        fragmented = (
            AnchorCandidate(
                kind=AnchorKind.CUBIC_PATH,
                raster_error=0.0,
                node_count=8,
                parameter_count=12,
                color="#dd2222",
            ),
            AnchorCandidate(
                kind=AnchorKind.CUBIC_PATH,
                raster_error=0.0,
                node_count=8,
                parameter_count=12,
                color="#dd2222",
            ),
        )

        clean_metrics = scene_metrics_to_manifest(clean)
        fragmented_metrics = scene_metrics_to_manifest(fragmented)
        fragment_groups = scene_groups_to_manifest(fragmented)

        self.assertEqual(clean_metrics["fragmentation_penalty"], 0.0)
        self.assertGreater(fragmented_metrics["fragmentation_penalty"], 0.0)
        self.assertGreater(
            clean_metrics["editability_score"],
            fragmented_metrics["editability_score"],
        )
        self.assertEqual(fragment_groups[0]["kind"], "same_color_fragment_group")
        self.assertEqual(fragment_groups[0]["color"], "#dd2222")
        self.assertEqual(fragment_groups[0]["anchor_indexes"], [0, 1])
        self.assertTrue(fragment_groups[0]["metrics"]["merge_candidate"])
        self.assertEqual(
            fragment_groups[0]["merge_plan"]["action"],
            "review_as_separate_fragments",
        )
        self.assertFalse(fragment_groups[0]["merge_plan"]["auto_merge_allowed"])
        self.assertEqual(
            fragment_groups[0]["merge_plan"]["decision_reason"],
            "sparse_same_color_bounds",
        )
        self.assertEqual(
            fragment_groups[0]["merge_plan"]["target_kind"],
            "compound_shape",
        )
        self.assertIn("bounds_fill_ratio", fragment_groups[0]["metrics"])

    def test_same_color_adjacent_fragments_get_merge_plan(self):
        fragments = (
            AnchorCandidate(
                kind=AnchorKind.RECT,
                raster_error=0.0,
                node_count=4,
                parameter_count=4,
                color="#003366",
                quad=QuadAnchor(
                    corners=(Point(0, 0), Point(4, 0), Point(4, 4), Point(0, 4)),
                ),
            ),
            AnchorCandidate(
                kind=AnchorKind.RECT,
                raster_error=0.0,
                node_count=4,
                parameter_count=4,
                color="#003366",
                quad=QuadAnchor(
                    corners=(Point(4, 0), Point(8, 0), Point(8, 4), Point(4, 4)),
                ),
            ),
        )

        fragment_groups = scene_groups_to_manifest(fragments)
        group = [
            group
            for group in fragment_groups
            if group["kind"] == "same_color_fragment_group"
        ][0]

        self.assertEqual(group["merge_plan"]["action"], "merge_adjacent_fragments")
        self.assertTrue(group["merge_plan"]["auto_merge_allowed"])
        self.assertEqual(
            group["merge_plan"]["decision_reason"],
            "compact_same_color_bounds",
        )
        self.assertEqual(group["merge_plan"]["bounds"], [0, 0, 8, 4])
        self.assertEqual(group["metrics"]["bounds_fill_ratio"], 1.0)

    def test_contacting_different_color_primitives_get_contact_group(self):
        anchors = (
            AnchorCandidate(
                kind=AnchorKind.CIRCLE,
                raster_error=0.0,
                node_count=1,
                parameter_count=3,
                color="#003366",
                circle=CircleAnchor(center=Point(5, 5), radius=4),
            ),
            AnchorCandidate(
                kind=AnchorKind.STROKE_POLYLINE,
                raster_error=0.0,
                node_count=2,
                parameter_count=5,
                color="#dd2222",
                stroke=StrokeAnchor(
                    centerline=(Point(9, 5), Point(14, 5)),
                    width_samples=(2.0,),
                ),
            ),
        )

        groups = scene_groups_to_manifest(anchors)
        contact_group = [
            group
            for group in groups
            if group["kind"] == "primitive_contact_pair"
        ][0]

        self.assertEqual(contact_group["anchor_indexes"], [0, 1])
        self.assertEqual(contact_group["relation"], "overlapping")
        self.assertEqual(contact_group["separation_policy"], "separate_by_color")
        self.assertEqual(contact_group["colors"], ["#003366", "#dd2222"])

    def test_occluded_rect_fragments_record_ordered_occluder_group(self):
        anchors = (
            AnchorCandidate(
                kind=AnchorKind.RECT,
                raster_error=0.0,
                node_count=4,
                parameter_count=4,
                color="#003366",
                quad=QuadAnchor(
                    corners=(Point(0, 0), Point(10, 0), Point(10, 4), Point(0, 4)),
                ),
            ),
            AnchorCandidate(
                kind=AnchorKind.RECT,
                raster_error=0.0,
                node_count=4,
                parameter_count=4,
                color="#003366",
                quad=QuadAnchor(
                    corners=(Point(0, 7), Point(10, 7), Point(10, 10), Point(0, 10)),
                ),
            ),
            AnchorCandidate(
                kind=AnchorKind.STROKE_POLYLINE,
                raster_error=0.0,
                node_count=2,
                parameter_count=5,
                color="#dd2222",
                stroke=StrokeAnchor(
                    centerline=(Point(-1, 5.5), Point(11, 5.5)),
                    width_samples=(2.0,),
                ),
            ),
        )

        groups = scene_groups_to_manifest(anchors)
        occlusion_group = [
            group
            for group in groups
            if group["kind"] == "occluded_primitive_group"
        ][0]

        self.assertEqual(occlusion_group["fragment_anchor_indexes"], [0, 1])
        self.assertEqual(occlusion_group["occluder_anchor_indexes"], [2])
        self.assertEqual(occlusion_group["base_color"], "#003366")
        self.assertEqual(occlusion_group["target_kind"], "rect")
        self.assertEqual(occlusion_group["draw_order"], "base_then_occluder")
        self.assertEqual(
            occlusion_group["occlusion_policy"],
            "visible_fragments_with_ordered_occluder",
        )

    def test_occluded_rect_fragments_promote_to_full_base_rect(self):
        top = AnchorCandidate(
            kind=AnchorKind.RECT,
            raster_error=0.0,
            node_count=4,
            parameter_count=4,
            color="#003366",
            quad=QuadAnchor(
                corners=(Point(12, 20), Point(52, 20), Point(52, 30), Point(12, 30)),
            ),
        )
        bottom = AnchorCandidate(
            kind=AnchorKind.RECT,
            raster_error=0.0,
            node_count=4,
            parameter_count=4,
            color="#003366",
            quad=QuadAnchor(
                corners=(Point(12, 35), Point(52, 35), Point(52, 44), Point(12, 44)),
            ),
        )
        occluder = AnchorCandidate(
            kind=AnchorKind.STROKE_POLYLINE,
            raster_error=0.0,
            node_count=2,
            parameter_count=5,
            color="#dd2222",
            stroke=StrokeAnchor(
                centerline=(Point(8, 32.5), Point(56, 32.5)),
                width_samples=(4.0,),
                cap_style="butt",
            ),
        )

        promoted = promote_occluded_rect_fragment_groups((top, bottom, occluder))

        self.assertEqual(len(promoted), 2)
        self.assertEqual(promoted[0].kind, AnchorKind.RECT)
        self.assertEqual(
            promoted[0].quad.corners,
            (Point(12, 20), Point(52, 20), Point(52, 44), Point(12, 44)),
        )
        self.assertEqual(promoted[0].metrics["occluded_rect_fragment_promotion"], 1.0)
        self.assertEqual(promoted[1], occluder)

    def test_occluded_rect_like_quad_promotes_to_full_rect(self):
        base = AnchorCandidate(
            kind=AnchorKind.QUAD,
            raster_error=0.12,
            node_count=4,
            parameter_count=8,
            color="#003366",
            quad=QuadAnchor(
                corners=(Point(10, 16), Point(42, 16), Point(27, 48), Point(10, 48)),
            ),
            metrics={"quad_corner_consistency_error": 0.2},
        )
        occluder = AnchorCandidate(
            kind=AnchorKind.RECT,
            raster_error=0.0,
            node_count=4,
            parameter_count=4,
            color="#c99700",
            quad=QuadAnchor(
                corners=(Point(28, 26), Point(56, 26), Point(56, 54), Point(28, 54)),
            ),
        )

        promoted = promote_occluded_rect_primitives((base, occluder))

        self.assertEqual(promoted[0].kind, AnchorKind.RECT)
        self.assertEqual(
            promoted[0].quad.corners,
            (Point(10, 16), Point(42, 16), Point(42, 48), Point(10, 48)),
        )
        self.assertEqual(promoted[0].metrics["occluded_rect_promotion"], 1.0)

    def test_scene_metrics_summarize_anchor_quality_errors(self):
        anchors = (
            AnchorCandidate(
                kind=AnchorKind.CIRCLE,
                raster_error=0.0,
                node_count=1,
                parameter_count=3,
                metrics={"circle_roundness_error": 0.1},
            ),
            AnchorCandidate(
                kind=AnchorKind.STROKE_POLYLINE,
                raster_error=0.0,
                node_count=2,
                parameter_count=5,
                metrics={
                    "line_smoothness_error": 0.2,
                    "stroke_width_variance": 0.4,
                },
            ),
        )

        metrics = scene_metrics_to_manifest(anchors)

        self.assertEqual(metrics["anchor_quality_error_mean"], 0.35)
        self.assertEqual(metrics["anchor_quality_error_max"], 0.6)
        self.assertEqual(
            metrics["anchor_quality_metric_summary"]["stroke_width_variance"],
            {"count": 1, "mean": 0.4, "max": 0.4},
        )
        self.assertEqual(
            metrics["anchor_scoring_summary"]["simple_shape_priority_bonus_total"],
            0.6,
        )
        self.assertEqual(
            metrics["anchor_scoring_summary"]["semantic_anchor_score_min"],
            -0.205,
        )

    def test_auto_merge_compact_same_color_rect_fragments(self):
        fragments = (
            _rect_anchor(0, 0, 4, 4, color="#003366"),
            _rect_anchor(4, 0, 8, 4, color="#003366"),
            _rect_anchor(0, 6, 4, 10, color="#c99700"),
        )

        merged = merge_auto_mergeable_same_color_fragments(fragments)

        self.assertEqual(len(merged), 2)
        self.assertEqual(merged[0].kind, AnchorKind.RECT)
        self.assertEqual(merged[0].color, "#003366")
        self.assertEqual(merged[0].metrics["merged_fragment_count"], 2.0)
        self.assertEqual(
            [(point.x, point.y) for point in merged[0].quad.corners],
            [(0, 0), (8, 0), (8, 4), (0, 4)],
        )

    def test_auto_merge_keeps_gapped_same_color_rects_separate(self):
        fragments = (
            _rect_anchor(0, 0, 4, 4, color="#003366"),
            _rect_anchor(5, 0, 9, 4, color="#003366"),
        )

        merged = merge_auto_mergeable_same_color_fragments(fragments)

        self.assertEqual(merged, fragments)


def _rect_anchor(
    min_x: float,
    min_y: float,
    max_x: float,
    max_y: float,
    *,
    color: str,
) -> AnchorCandidate:
    return AnchorCandidate(
        kind=AnchorKind.RECT,
        raster_error=0.0,
        node_count=4,
        parameter_count=4,
        color=color,
        quad=QuadAnchor(
            corners=(
                Point(min_x, min_y),
                Point(max_x, min_y),
                Point(max_x, max_y),
                Point(min_x, max_y),
            ),
        ),
    )


if __name__ == "__main__":
    unittest.main()
