"""Semantic-first vectorization research primitives."""

from curve.anchors import (
    AnchorCandidate,
    AnchorKind,
    CircleAnchor,
    Point,
    QuadAnchor,
    StrokeAnchor,
    choose_best_anchor,
)
from curve.detection import (
    detect_cutout_strokes,
    detect_primitive_anchors,
    primitive_candidates_for_component,
)
from curve.images import ColorMask, flat_color_masks_from_image, scene_from_flat_color_image
from curve.masks import BinaryMask, MaskComponent, connected_components
from curve.scene import (
    Scene,
    SvgStyle,
    anchor_to_manifest,
    anchor_to_svg_element,
    anchors_to_svg,
    scene_from_mask,
    scene_groups_to_manifest,
)
from curve.synthetic import SyntheticSample, generate_synthetic_sample
from curve.runs import VectorizeRun, create_run_dir, render_markdown_report, write_vectorize_run
from curve.eval import evaluate_runs, render_eval_markdown, write_eval_summary

__all__ = [
    "AnchorCandidate",
    "AnchorKind",
    "BinaryMask",
    "CircleAnchor",
    "ColorMask",
    "MaskComponent",
    "Point",
    "QuadAnchor",
    "Scene",
    "StrokeAnchor",
    "SvgStyle",
    "SyntheticSample",
    "VectorizeRun",
    "anchor_to_manifest",
    "anchor_to_svg_element",
    "anchors_to_svg",
    "choose_best_anchor",
    "connected_components",
    "create_run_dir",
    "detect_cutout_strokes",
    "detect_primitive_anchors",
    "evaluate_runs",
    "flat_color_masks_from_image",
    "generate_synthetic_sample",
    "primitive_candidates_for_component",
    "scene_from_flat_color_image",
    "scene_groups_to_manifest",
    "scene_from_mask",
    "render_markdown_report",
    "render_eval_markdown",
    "write_vectorize_run",
    "write_eval_summary",
]
