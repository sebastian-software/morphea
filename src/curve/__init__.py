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
    SCENE_MANIFEST_SCHEMA_VERSION,
    Scene,
    SvgStyle,
    anchor_to_manifest,
    anchor_to_svg_element,
    anchors_to_svg,
    scene_from_mask,
    scene_groups_to_manifest,
)
from curve.synthetic import SyntheticSample, generate_synthetic_sample
from curve.runs import (
    VectorizeRun,
    create_run_dir,
    render_markdown_report,
    write_markdown_report,
    write_vectorize_run,
)
from curve.eval import evaluate_runs, render_eval_markdown, write_eval_summary
from curve.dataset import DatasetSplit, generate_synthetic_dataset, split_counts
from curve.classifier import (
    FEATURE_NAMES,
    TrainingExample,
    classifier_prior_error,
    evaluate_classifier,
    examples_from_dataset,
    features_from_anchor,
    features_from_candidate,
    load_centroid_model,
    predict_label,
    train_centroid_classifier,
)
from curve.segmenters import (
    FlatColorSegmenter,
    MlxSamSegmenter,
    SegmentProposal,
    Segmenter,
    proposals_to_manifest,
)
from curve.self_learning import apply_review_file, create_review_file, harvest_pseudo_labels
from curve.refinement import RefinementConfig, refine_manifest
from curve.curated import check_curated_suite, load_curated_suite
from curve.sweeps import load_sweep_config, run_sweep

__all__ = [
    "AnchorCandidate",
    "AnchorKind",
    "BinaryMask",
    "CircleAnchor",
    "ColorMask",
    "DatasetSplit",
    "FEATURE_NAMES",
    "FlatColorSegmenter",
    "MaskComponent",
    "MlxSamSegmenter",
    "Point",
    "QuadAnchor",
    "RefinementConfig",
    "SCENE_MANIFEST_SCHEMA_VERSION",
    "Scene",
    "SegmentProposal",
    "Segmenter",
    "StrokeAnchor",
    "SvgStyle",
    "SyntheticSample",
    "TrainingExample",
    "VectorizeRun",
    "anchor_to_manifest",
    "anchor_to_svg_element",
    "apply_review_file",
    "anchors_to_svg",
    "choose_best_anchor",
    "connected_components",
    "create_run_dir",
    "create_review_file",
    "classifier_prior_error",
    "check_curated_suite",
    "detect_cutout_strokes",
    "detect_primitive_anchors",
    "evaluate_runs",
    "evaluate_classifier",
    "examples_from_dataset",
    "features_from_anchor",
    "features_from_candidate",
    "flat_color_masks_from_image",
    "generate_synthetic_sample",
    "generate_synthetic_dataset",
    "harvest_pseudo_labels",
    "primitive_candidates_for_component",
    "load_centroid_model",
    "load_curated_suite",
    "load_sweep_config",
    "proposals_to_manifest",
    "predict_label",
    "scene_from_flat_color_image",
    "scene_groups_to_manifest",
    "scene_from_mask",
    "split_counts",
    "render_markdown_report",
    "write_markdown_report",
    "render_eval_markdown",
    "refine_manifest",
    "run_sweep",
    "write_vectorize_run",
    "write_eval_summary",
    "train_centroid_classifier",
]
