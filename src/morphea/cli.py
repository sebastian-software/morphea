"""CLI for the Morphēa reconstruction prototype."""

from __future__ import annotations

import argparse
import json
import shlex
from pathlib import Path

from morphea.classifier import evaluate_classifier_model, train_centroid_classifier
from morphea.comparison import (
    compare_git_snapshots,
    compare_segment_manifests,
    compare_snapshots,
    generate_git_curated_snapshot,
)
from morphea.curated import (
    check_curated_suite,
    render_curated_markdown,
    write_review_packet_followup_artifacts,
)
from morphea.dataset import generate_synthetic_dataset
from morphea.eval import write_eval_summary
from morphea.images import scene_from_flat_color_image
from morphea.lucide_quality import check_lucide_suite
from morphea.mlx_classifier import (
    MlxClassifierTrainingConfig,
    train_mlx_transformer_classifier,
)
from morphea.profiling import profile_curated_suite, profile_vectorize
from morphea.promotion_export import (
    apply_promotion_review_decision,
    write_promotion_svg_exports,
)
from morphea.promotion_review_workflow import prepare_promotion_review_harvest
from morphea.primitive_baseline import (
    compare_to_baseline,
    load_baseline,
    render_baseline_diff_markdown,
    write_baseline,
)
from morphea.primitive_gallery import write_primitive_gallery_site
from morphea.primitive_quality import write_primitive_quality_report
from morphea.runs import (
    create_run_dir,
    write_html_report,
    write_markdown_report,
    write_vectorize_run,
)
from morphea.segmenters import (
    FlatColorSegmenter,
    MlxSamSegmenter,
    gate_segment_proposals,
    proposals_to_manifest,
    render_segment_proposal_markdown,
    segment_proposal_groups,
    segment_proposal_summary,
    segmenter_backend_status,
)
from morphea.scene import SvgStyle
from morphea.self_learning import (
    HARVEST_FILTER_DEFAULTS,
    apply_review_file,
    compare_retraining,
    create_review_file,
    gate_training_comparison,
    harvest_curated_pseudo_labels,
    harvest_pseudo_labels,
    merge_reviewed_pseudo_label_dataset,
    retrain_centroid_classifier,
    retrain_mlx_classifier,
    run_self_learning_cycle,
)
from morphea.refinement import (
    RefinementConfig,
    gate_refinement_result,
    refine_manifest,
)
from morphea.status import collect_runtime_status, render_runtime_status_markdown
from morphea.sweeps import run_sweep


VECTORIZE_DEFAULT_CONFIG = {
    "background": None,
    "min_area": 8,
    "color_tolerance": 0.0,
    "max_size": None,
    "max_colors": None,
    "max_component_area": None,
    "timeout_seconds": None,
    "classifier_model": None,
    "raster_error_weight": 1.0,
    "quality_error_weight": 1.0,
    "node_complexity_weight": 0.015,
    "parameter_complexity_weight": 0.01,
    "simple_shape_bonus_weight": 1.0,
    "stroke_circle_min_diameter": 6,
    "stroke_circle_max_aspect_error": 0.18,
    "stroke_circle_min_inner_ratio": 0.25,
    "stroke_circle_max_area_error": 0.45,
    "circle_min_diameter": 3,
    "circle_max_aspect_error": 0.22,
    "circle_max_area_error": 0.35,
    "stroke_min_length": 4.0,
    "stroke_min_length_width_ratio": 3.0,
    "quad_min_fill_ratio": 0.35,
    "quad_max_fill_error": 0.28,
    "rect_max_fill_error": 0.08,
    "rounded_rect_max_fill_error": 0.30,
}
CUTOUT_EXPORT_VALUES = {"overlay_stroke", "negative_mask"}
VECTORIZE_ARTIFACT_CONFIG_KEYS = {
    "input",
    "output",
    "manifest",
    "debug_svg",
    "run_dir",
    "no_manifest",
    "cutout_export",
}
GENERATE_DEFAULT_CONFIG = {
    "output_dir": None,
    "count": 1,
    "seed": 1,
    "width": 96,
    "height": 96,
    "difficulty": "basic",
    "val_count": 1,
    "test_count": 1,
}
GENERATE_CONFIG_KEYS = set(GENERATE_DEFAULT_CONFIG)
TRAIN_CONFIG_KEYS = {"dataset", "output"}
EVAL_CONFIG_KEYS = {"run_root", "output", "markdown"}
PROFILE_CONFIG_KEYS = set(VECTORIZE_DEFAULT_CONFIG) | {"input", "output", "repeats"}
PROFILE_CURATED_CONFIG_KEYS = {"suite", "output", "markdown", "repeats"}
EVAL_CLASSIFIER_CONFIG_KEYS = {"model", "dataset", "output", "markdown", "splits"}
TRAIN_MLX_CONFIG_KEYS = {
    "dataset",
    "output",
    "epochs",
    "hidden_dim",
    "num_heads",
    "num_layers",
    "learning_rate",
    "crop_size",
    "allow_unavailable",
}
SEGMENT_CONFIG_DEFAULTS = {
    "segmenter": "flat_color",
    "background": None,
    "min_area": 8,
    "color_tolerance": 0.0,
    "max_size": None,
    "max_colors": None,
    "max_component_area": None,
    "split_components": True,
    "mlx_model_path": None,
    "mlx_score_threshold": 0.0,
    "mlx_max_masks": None,
    "mlx_timeout_seconds": None,
    "mlx_prompt_strategy": "grid_points",
    "geometry_gate": False,
    "max_anchor_quality_error": 1.0,
    "require_reserved_anchor": False,
}
MLX_PROMPT_STRATEGIES = ("grid_points", "flat_color_centers")
SEGMENT_ARTIFACT_CONFIG_KEYS = {"input", "output", "markdown"}
COMPARE_SNAPSHOTS_CONFIG_KEYS = {"before", "after", "output", "markdown"}
COMPARE_SEGMENTS_CONFIG_KEYS = {"before", "after", "output", "markdown"}
COMPARE_GIT_SNAPSHOTS_CONFIG_KEYS = {
    "before_ref",
    "after_ref",
    "path",
    "output",
    "markdown",
    "repo",
}
SNAPSHOT_GIT_REF_CONFIG_KEYS = {
    "ref",
    "suite",
    "output",
    "report",
    "output_dir",
    "repo",
    "timeout_seconds",
    "run",
}
COMPARE_TRAINING_CONFIG_KEYS = {
    "base_dataset",
    "pseudo_dataset",
    "validation_dataset",
    "output",
    "markdown",
}
TRAINING_GATE_CONFIG_KEYS = {
    "comparison",
    "output",
    "markdown",
    "min_train_examples_delta",
    "min_best_accuracy_delta",
    "max_worst_accuracy_drop",
    "allow_unchanged",
}
SELF_LEARN_CONFIG_KEYS = {
    "base_dataset",
    "reviewed_labels",
    "validation_dataset",
    "curated_suite",
    "curated_output_dir",
    "curated_report",
    "curated_snapshot",
    "lucide_suite",
    "lucide_output_dir",
    "lucide_report",
    "suite_family_baseline",
    "suite_family_baseline_output",
    "suite_family_baseline_reviewer",
    "suite_family_baseline_reason",
    "suite_family_baseline_changelog",
    "output_dir",
    "markdown",
    "min_train_examples_delta",
    "min_best_accuracy_delta",
    "max_worst_accuracy_drop",
    "allow_unchanged",
    "backend",
    "epochs",
    "hidden_dim",
    "num_heads",
    "num_layers",
    "learning_rate",
    "crop_size",
    "allow_unavailable",
}
RETRAIN_CONFIG_KEYS = {
    "base_dataset",
    "pseudo_dataset",
    "validation_dataset",
    "output",
    "comparison_output",
    "backend",
    "epochs",
    "hidden_dim",
    "num_heads",
    "num_layers",
    "learning_rate",
    "crop_size",
    "allow_unavailable",
}
REFINE_CONFIG_KEYS = {
    "manifest",
    "output",
    "backend",
    "max_iterations",
    "timeout_seconds",
    "source_image",
    "raster_l1_weight",
    "raster_edge_weight",
}
REFINEMENT_GATE_CONFIG_KEYS = {
    "refined_manifest",
    "output",
    "markdown",
    "max_objective_regression",
    "require_improvement",
}
STATUS_CONFIG_KEYS = {"output", "markdown", "mlx_sam_model_path"}
REPORT_CONFIG_KEYS = {"manifest", "output", "config", "format"}
PRIMITIVE_CHECK_CONFIG_KEYS = {
    "output",
    "output_dir",
    "markdown",
    "case",
    "filter",
    "refine",
    "refinement_iterations",
}
HARVEST_DEFAULT_CONFIG = {
    "run_root": None,
    "output": None,
    "markdown": None,
    **HARVEST_FILTER_DEFAULTS,
}
HARVEST_CURATED_DEFAULT_CONFIG = {
    "suite": None,
    "run_root": None,
    "output": None,
    "curated_report": None,
    "snapshot": None,
    **{
        key: value
        for key, value in HARVEST_DEFAULT_CONFIG.items()
        if key not in {"run_root", "output"}
    },
}
REVIEW_CONFIG_KEYS = {
    "pseudo_labels",
    "output",
    "markdown",
    "accept_applied_reviews",
}
APPLY_REVIEW_CONFIG_KEYS = {"review", "output", "markdown"}
MERGE_LABELS_CONFIG_KEYS = {"reviewed_labels", "output_dir"}
PROMOTION_REVIEW_HARVEST_CONFIG_KEYS = {
    "review_packet",
    "output",
    "markdown",
    "harvest_config",
    "decision_plan",
    "decisions",
    "decision_choices",
    "decision_templates",
    "decision_overrides",
    "suite",
    "run_root",
    "harvest_output",
    "curated_report",
    "snapshot",
    "harvest_markdown",
}
CURATED_CHECK_CONFIG_KEYS = {
    "suite",
    "output",
    "output_dir",
    "run",
    "snapshot",
    "baseline_snapshot",
    "markdown",
}
PROMOTION_REVIEW_TERMINAL_DECISIONS = (
    "accepted",
    "corrected",
    "rejected",
    "deferred",
)
LUCIDE_CHECK_CONFIG_KEYS = {
    "suite",
    "output",
    "output_dir",
    "markdown",
} | set(VECTORIZE_DEFAULT_CONFIG)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="morphea",
        description="Bitmap-to-vector reconstruction focused on editable SVG form",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    vectorize = subcommands.add_parser(
        "vectorize",
        help="Vectorize a flat-color raster image into editable SVG primitives.",
    )
    vectorize.add_argument(
        "input",
        type=Path,
        nargs="?",
        help="Input PNG/JPEG/WebP image.",
    )
    vectorize.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output SVG path.",
    )
    vectorize.add_argument(
        "--background",
        help="Explicit background color as #rrggbb for flattening/grouping.",
    )
    vectorize.add_argument(
        "--min-area",
        type=int,
        default=None,
        help="Minimum exact-color component area to consider.",
    )
    vectorize.add_argument(
        "--color-tolerance",
        type=float,
        default=None,
        help="RGB distance for grouping near-flat colors into one mask.",
    )
    vectorize.add_argument(
        "--max-size",
        type=int,
        help="Resize the longest image side for analysis, then scale anchors back.",
    )
    vectorize.add_argument(
        "--max-colors",
        type=int,
        help="Quantize the analysis image to this many colors before grouping.",
    )
    vectorize.add_argument(
        "--max-component-area",
        type=int,
        help="Defer components larger than this analysis-pixel area.",
    )
    vectorize.add_argument(
        "--timeout-seconds",
        type=float,
        help="Stop processing after this many seconds and write partial diagnostics.",
    )
    vectorize.add_argument(
        "--manifest",
        type=Path,
        help="Output JSON manifest path. Defaults to output path with .json suffix.",
    )
    vectorize.add_argument(
        "--no-manifest",
        action="store_true",
        default=None,
        help="Do not write a JSON recognition manifest.",
    )
    vectorize.add_argument(
        "--debug-svg",
        type=Path,
        help="Optional debug SVG path with source ids, bounds, and labels.",
    )
    vectorize.add_argument(
        "--run-dir",
        type=Path,
        help="Write a timestamped experiment run directory under this root.",
    )
    vectorize.add_argument(
        "--classifier-model",
        type=Path,
        help="Optional primitive classifier model JSON used as a ranking prior.",
    )
    vectorize.add_argument(
        "--cutout-export",
        choices=("overlay_stroke", "negative_mask"),
        default=None,
        help="Export cut-outs as visible overlay strokes or as an editable SVG mask.",
    )
    vectorize.add_argument("--raster-error-weight", type=float)
    vectorize.add_argument("--quality-error-weight", type=float)
    vectorize.add_argument("--node-complexity-weight", type=float)
    vectorize.add_argument("--parameter-complexity-weight", type=float)
    vectorize.add_argument("--simple-shape-bonus-weight", type=float)
    vectorize.add_argument("--circle-max-aspect-error", type=float)
    vectorize.add_argument("--circle-max-area-error", type=float)
    vectorize.add_argument("--stroke-min-length-width-ratio", type=float)
    vectorize.add_argument("--quad-max-fill-error", type=float)
    vectorize.add_argument("--rect-max-fill-error", type=float)
    vectorize.add_argument(
        "--config",
        type=Path,
        help="Optional JSON config for vectorize runtime knobs.",
    )

    profile = subcommands.add_parser(
        "profile",
        help="Measure bounded vectorize runtime for an input image.",
    )
    profile.add_argument("input", type=Path, nargs="?")
    profile.add_argument("-o", "--output", type=Path)
    profile.add_argument("--repeats", type=int, default=None)
    profile.add_argument("--background")
    profile.add_argument("--min-area", type=int, default=None)
    profile.add_argument("--color-tolerance", type=float, default=None)
    profile.add_argument("--max-size", type=int)
    profile.add_argument("--max-colors", type=int)
    profile.add_argument("--max-component-area", type=int)
    profile.add_argument("--timeout-seconds", type=float)
    profile.add_argument("--classifier-model", type=Path)
    profile.add_argument("--raster-error-weight", type=float)
    profile.add_argument("--quality-error-weight", type=float)
    profile.add_argument("--node-complexity-weight", type=float)
    profile.add_argument("--parameter-complexity-weight", type=float)
    profile.add_argument("--simple-shape-bonus-weight", type=float)
    profile.add_argument("--circle-max-aspect-error", type=float)
    profile.add_argument("--circle-max-area-error", type=float)
    profile.add_argument("--stroke-min-length-width-ratio", type=float)
    profile.add_argument("--quad-max-fill-error", type=float)
    profile.add_argument("--rect-max-fill-error", type=float)
    profile.add_argument(
        "--config",
        type=Path,
        help="Optional JSON config for vectorize runtime knobs.",
    )

    profile_curated = subcommands.add_parser(
        "profile-curated",
        help="Profile every available case in a curated real-image suite.",
    )
    profile_curated.add_argument("suite", type=Path, nargs="?")
    profile_curated.add_argument("-o", "--output", type=Path)
    profile_curated.add_argument("--markdown", type=Path)
    profile_curated.add_argument("--repeats", type=int, default=None)
    profile_curated.add_argument("--config", type=Path)

    generate = subcommands.add_parser(
        "generate",
        help="Generate synthetic flat-color primitive training samples.",
    )
    generate.add_argument("-o", "--output-dir", type=Path)
    generate.add_argument("--count", type=int, default=None)
    generate.add_argument("--seed", type=int, default=None)
    generate.add_argument("--width", type=int, default=None)
    generate.add_argument("--height", type=int, default=None)
    generate.add_argument("--difficulty", default=None)
    generate.add_argument("--val-count", type=int, default=None)
    generate.add_argument("--test-count", type=int, default=None)
    generate.add_argument("--config", type=Path)

    eval_parser = subcommands.add_parser(
        "eval",
        help="Summarize vectorize run directories.",
    )
    eval_parser.add_argument("run_root", type=Path, nargs="?")
    eval_parser.add_argument("-o", "--output", type=Path)
    eval_parser.add_argument("--markdown", type=Path)
    eval_parser.add_argument("--config", type=Path)

    segment = subcommands.add_parser(
        "segment",
        help="Write segment proposals for an input image.",
    )
    segment.add_argument("input", type=Path, nargs="?")
    segment.add_argument("-o", "--output", type=Path)
    segment.add_argument("--markdown", type=Path)
    segment.add_argument("--segmenter", choices=("flat_color", "mlx_sam"))
    segment.add_argument("--background")
    segment.add_argument("--min-area", type=int)
    segment.add_argument("--color-tolerance", type=float)
    segment.add_argument("--max-size", type=int)
    segment.add_argument("--max-colors", type=int)
    segment.add_argument("--max-component-area", type=int)
    segment.add_argument("--mlx-model-path", type=Path)
    segment.add_argument("--mlx-score-threshold", type=float)
    segment.add_argument("--mlx-max-masks", type=int)
    segment.add_argument("--mlx-timeout-seconds", type=float)
    segment.add_argument(
        "--mlx-prompt-strategy",
        choices=MLX_PROMPT_STRATEGIES,
    )
    segment.add_argument(
        "--geometry-gate",
        dest="geometry_gate",
        action="store_true",
        default=None,
    )
    segment.add_argument(
        "--no-geometry-gate",
        dest="geometry_gate",
        action="store_false",
    )
    segment.add_argument("--max-anchor-quality-error", type=float)
    segment.add_argument(
        "--require-reserved-anchor",
        dest="require_reserved_anchor",
        action="store_true",
        default=None,
    )
    segment.add_argument(
        "--allow-unreserved-anchor",
        dest="require_reserved_anchor",
        action="store_false",
    )
    segment.add_argument(
        "--split-components",
        dest="split_components",
        action="store_true",
        default=None,
    )
    segment.add_argument(
        "--no-split-components",
        dest="split_components",
        action="store_false",
    )
    segment.add_argument("--config", type=Path)

    report = subcommands.add_parser(
        "report",
        help="Render a report from an existing vectorize manifest.",
    )
    report.add_argument("manifest", type=Path, nargs="?")
    report.add_argument("-o", "--output", type=Path)
    report.add_argument("--config", type=Path)
    report.add_argument("--command-config", type=Path)
    report.add_argument(
        "--format",
        choices=("markdown", "html"),
        default=None,
        help="Report format. Defaults to html for .html output, otherwise markdown.",
    )

    train = subcommands.add_parser(
        "train",
        help="Train a primitive classifier from a generated dataset.json.",
    )
    train.add_argument("dataset", type=Path, nargs="?")
    train.add_argument("-o", "--output", type=Path)
    train.add_argument("--config", type=Path)

    train_mlx = subcommands.add_parser(
        "train-mlx",
        help="Train the optional MLX Transformer primitive classifier.",
    )
    train_mlx.add_argument("dataset", type=Path, nargs="?")
    train_mlx.add_argument("-o", "--output", type=Path)
    train_mlx.add_argument("--epochs", type=int)
    train_mlx.add_argument("--hidden-dim", type=int)
    train_mlx.add_argument("--num-heads", type=int)
    train_mlx.add_argument("--num-layers", type=int)
    train_mlx.add_argument("--learning-rate", type=float)
    train_mlx.add_argument("--crop-size", type=int)
    train_mlx.add_argument(
        "--allow-unavailable",
        action="store_true",
        help="Write a fallback artifact when MLX is not installed.",
    )
    train_mlx.add_argument("--config", type=Path)

    eval_classifier = subcommands.add_parser(
        "eval-classifier",
        help="Evaluate a primitive classifier model against a generated dataset.",
    )
    eval_classifier.add_argument("model", type=Path, nargs="?")
    eval_classifier.add_argument("dataset", type=Path, nargs="?")
    eval_classifier.add_argument("-o", "--output", type=Path)
    eval_classifier.add_argument("--markdown", type=Path)
    eval_classifier.add_argument(
        "--splits",
        nargs="+",
        default=None,
        help="Dataset splits to evaluate. Defaults to val test.",
    )
    eval_classifier.add_argument("--config", type=Path)

    harvest = subcommands.add_parser(
        "harvest",
        help="Collect high-confidence pseudo-labels from vectorize runs.",
    )
    harvest.add_argument("run_root", type=Path, nargs="?")
    harvest.add_argument("-o", "--output", type=Path)
    harvest.add_argument("--markdown", type=Path)
    harvest.add_argument("--max-run-diagnostics", type=int)
    harvest.add_argument("--max-classifier-prior-error", type=float)
    harvest.add_argument("--min-editability-score", type=float)
    harvest.add_argument("--max-fragmentation-penalty", type=float)
    harvest.add_argument("--max-raster-l1-error", type=float)
    harvest.add_argument("--max-raster-edge-error", type=float)
    harvest.add_argument("--max-anchor-quality-error", type=float)
    harvest.add_argument(
        "--require-applied-review",
        action="store_true",
        default=None,
        help="Harvest only runs with accepted/corrected applied review decisions.",
    )
    harvest.add_argument("--config", type=Path)

    harvest_curated = subcommands.add_parser(
        "harvest-curated",
        help="Run a curated real-image suite and harvest high-confidence labels.",
    )
    harvest_curated.add_argument("suite", type=Path, nargs="?")
    harvest_curated.add_argument("--run-root", type=Path)
    harvest_curated.add_argument("-o", "--output", type=Path)
    harvest_curated.add_argument("--curated-report", type=Path)
    harvest_curated.add_argument("--snapshot", type=Path)
    harvest_curated.add_argument("--markdown", type=Path)
    harvest_curated.add_argument("--max-run-diagnostics", type=int)
    harvest_curated.add_argument("--max-classifier-prior-error", type=float)
    harvest_curated.add_argument("--min-editability-score", type=float)
    harvest_curated.add_argument("--max-fragmentation-penalty", type=float)
    harvest_curated.add_argument("--max-raster-l1-error", type=float)
    harvest_curated.add_argument("--max-raster-edge-error", type=float)
    harvest_curated.add_argument("--max-anchor-quality-error", type=float)
    harvest_curated.add_argument(
        "--require-applied-review",
        action="store_true",
        default=None,
        help="Harvest only accepted/corrected applied promotion reviews.",
    )
    harvest_curated.add_argument("--config", type=Path)

    review = subcommands.add_parser(
        "review",
        help="Create a human-editable review queue from harvested pseudo-labels.",
    )
    review.add_argument("pseudo_labels", type=Path, nargs="?")
    review.add_argument("-o", "--output", type=Path)
    review.add_argument("--markdown", type=Path)
    review.add_argument(
        "--accept-applied-reviews",
        action="store_true",
        default=None,
        help="Pre-accept accepted/corrected applied review decisions.",
    )
    review.add_argument("--config", type=Path)

    apply_review = subcommands.add_parser(
        "apply-review",
        help="Apply accept/reject decisions from a review file.",
    )
    apply_review.add_argument("review", type=Path, nargs="?")
    apply_review.add_argument("-o", "--output", type=Path)
    apply_review.add_argument("--markdown", type=Path)
    apply_review.add_argument("--config", type=Path)

    merge_labels = subcommands.add_parser(
        "merge-labels",
        help="Convert accepted reviewed pseudo-labels into a trainable dataset.",
    )
    merge_labels.add_argument("reviewed_labels", type=Path, nargs="?")
    merge_labels.add_argument("-o", "--output-dir", type=Path)
    merge_labels.add_argument("--config", type=Path)

    compare_training = subcommands.add_parser(
        "compare-training",
        help="Compare baseline classifier training against pseudo-label augmentation.",
    )
    compare_training.add_argument("base_dataset", type=Path, nargs="?")
    compare_training.add_argument("--pseudo-dataset", type=Path)
    compare_training.add_argument("--validation-dataset", type=Path)
    compare_training.add_argument("-o", "--output", type=Path)
    compare_training.add_argument("--markdown", type=Path)
    compare_training.add_argument("--config", type=Path)

    training_gate = subcommands.add_parser(
        "training-gate",
        help="Decide whether a training comparison is safe to accept.",
    )
    training_gate.add_argument("comparison", type=Path, nargs="?")
    training_gate.add_argument("-o", "--output", type=Path)
    training_gate.add_argument("--markdown", type=Path)
    training_gate.add_argument("--min-train-examples-delta", type=int)
    training_gate.add_argument("--min-best-accuracy-delta", type=float)
    training_gate.add_argument("--max-worst-accuracy-drop", type=float)
    training_gate.add_argument("--allow-unchanged", action="store_true")
    training_gate.add_argument("--config", type=Path)

    self_learn = subcommands.add_parser(
        "self-learn",
        help="Run the reviewed-label self-learning retraining decision cycle.",
    )
    self_learn.add_argument("base_dataset", type=Path, nargs="?")
    self_learn.add_argument("--reviewed-labels", type=Path)
    self_learn.add_argument("--validation-dataset", type=Path)
    self_learn.add_argument("--curated-suite", type=Path)
    self_learn.add_argument("--curated-output-dir", type=Path)
    self_learn.add_argument("--curated-report", type=Path)
    self_learn.add_argument("--curated-snapshot", type=Path)
    self_learn.add_argument("--lucide-suite", type=Path)
    self_learn.add_argument("--lucide-output-dir", type=Path)
    self_learn.add_argument("--lucide-report", type=Path)
    self_learn.add_argument("--suite-family-baseline", type=Path)
    self_learn.add_argument("--suite-family-baseline-output", type=Path)
    self_learn.add_argument("--suite-family-baseline-reviewer")
    self_learn.add_argument("--suite-family-baseline-reason")
    self_learn.add_argument("--suite-family-baseline-changelog", type=Path)
    self_learn.add_argument("-o", "--output-dir", type=Path)
    self_learn.add_argument("--markdown", type=Path)
    self_learn.add_argument("--min-train-examples-delta", type=int)
    self_learn.add_argument("--min-best-accuracy-delta", type=float)
    self_learn.add_argument("--max-worst-accuracy-drop", type=float)
    self_learn.add_argument("--allow-unchanged", action="store_true")
    self_learn.add_argument("--backend", choices=("centroid", "mlx"))
    self_learn.add_argument("--epochs", type=int)
    self_learn.add_argument("--hidden-dim", type=int)
    self_learn.add_argument("--num-heads", type=int)
    self_learn.add_argument("--num-layers", type=int)
    self_learn.add_argument("--learning-rate", type=float)
    self_learn.add_argument("--crop-size", type=int)
    self_learn.add_argument("--allow-unavailable", action="store_true")
    self_learn.add_argument("--config", type=Path)

    retrain = subcommands.add_parser(
        "retrain",
        help="Train an augmented classifier from base and reviewed pseudo-label datasets.",
    )
    retrain.add_argument("base_dataset", type=Path, nargs="?")
    retrain.add_argument("--pseudo-dataset", type=Path)
    retrain.add_argument("--validation-dataset", type=Path)
    retrain.add_argument("-o", "--output", type=Path)
    retrain.add_argument("--comparison-output", type=Path)
    retrain.add_argument("--backend", choices=("centroid", "mlx"))
    retrain.add_argument("--epochs", type=int)
    retrain.add_argument("--hidden-dim", type=int)
    retrain.add_argument("--num-heads", type=int)
    retrain.add_argument("--num-layers", type=int)
    retrain.add_argument("--learning-rate", type=float)
    retrain.add_argument("--crop-size", type=int)
    retrain.add_argument("--allow-unavailable", action="store_true")
    retrain.add_argument("--config", type=Path)

    compare_snapshots_parser = subcommands.add_parser(
        "compare-snapshots",
        help="Compare two saved experiment JSON snapshots.",
    )
    compare_snapshots_parser.add_argument("before", type=Path, nargs="?")
    compare_snapshots_parser.add_argument("after", type=Path, nargs="?")
    compare_snapshots_parser.add_argument("-o", "--output", type=Path)
    compare_snapshots_parser.add_argument("--markdown", type=Path)
    compare_snapshots_parser.add_argument("--config", type=Path)

    compare_segments_parser = subcommands.add_parser(
        "compare-segments",
        help="Compare two segment proposal manifests.",
    )
    compare_segments_parser.add_argument("before", type=Path, nargs="?")
    compare_segments_parser.add_argument("after", type=Path, nargs="?")
    compare_segments_parser.add_argument("-o", "--output", type=Path)
    compare_segments_parser.add_argument("--markdown", type=Path)
    compare_segments_parser.add_argument("--config", type=Path)

    compare_git_snapshots_parser = subcommands.add_parser(
        "compare-git-snapshots",
        help="Compare the same saved snapshot file across two git refs.",
    )
    compare_git_snapshots_parser.add_argument("before_ref", nargs="?")
    compare_git_snapshots_parser.add_argument("after_ref", nargs="?")
    compare_git_snapshots_parser.add_argument("--path", type=Path)
    compare_git_snapshots_parser.add_argument(
        "-o",
        "--output",
        type=Path,
    )
    compare_git_snapshots_parser.add_argument("--markdown", type=Path)
    compare_git_snapshots_parser.add_argument("--repo", type=Path)
    compare_git_snapshots_parser.add_argument("--config", type=Path)

    snapshot_git_ref = subcommands.add_parser(
        "snapshot-git-ref",
        help="Generate a curated snapshot for a git ref in an isolated worktree.",
    )
    snapshot_git_ref.add_argument("ref", nargs="?")
    snapshot_git_ref.add_argument("--suite", type=Path)
    snapshot_git_ref.add_argument("-o", "--output", type=Path)
    snapshot_git_ref.add_argument("--report", type=Path)
    snapshot_git_ref.add_argument("--output-dir", type=Path)
    snapshot_git_ref.add_argument("--repo", type=Path)
    snapshot_git_ref.add_argument("--timeout-seconds", type=float)
    snapshot_git_ref.add_argument("--run", dest="run", action="store_true", default=None)
    snapshot_git_ref.add_argument(
        "--no-run",
        dest="run",
        action="store_false",
    )
    snapshot_git_ref.add_argument("--config", type=Path)

    refine = subcommands.add_parser(
        "refine",
        help="Apply a structure-preserving refinement backend to a manifest.",
    )
    refine.add_argument("manifest", type=Path, nargs="?")
    refine.add_argument("-o", "--output", type=Path)
    refine.add_argument("--backend")
    refine.add_argument("--max-iterations", type=int)
    refine.add_argument("--timeout-seconds", type=float)
    refine.add_argument("--raster-l1-weight", type=float)
    refine.add_argument("--raster-edge-weight", type=float)
    refine.add_argument(
        "--source-image",
        type=Path,
        help="Optional source image used for structure-preserving local metrics.",
    )
    refine.add_argument("--config", type=Path)

    refinement_gate = subcommands.add_parser(
        "refinement-gate",
        help="Decide whether a refinement result is safe to accept.",
    )
    refinement_gate.add_argument("refined_manifest", type=Path, nargs="?")
    refinement_gate.add_argument("-o", "--output", type=Path)
    refinement_gate.add_argument("--markdown", type=Path)
    refinement_gate.add_argument("--max-objective-regression", type=float)
    refinement_gate.add_argument(
        "--allow-unchanged",
        dest="require_improvement",
        action="store_false",
        default=None,
    )
    refinement_gate.add_argument("--config", type=Path)

    status = subcommands.add_parser(
        "status",
        help="Write runtime/backend availability status.",
    )
    status.add_argument("-o", "--output", type=Path)
    status.add_argument("--markdown", type=Path)
    status.add_argument("--mlx-sam-model-path", type=Path)
    status.add_argument("--config", type=Path)

    primitive_check = subcommands.add_parser(
        "primitive-check",
        help="Run deterministic primitive round-trip quality checks.",
    )
    primitive_check.add_argument("-o", "--output", type=Path)
    primitive_check.add_argument(
        "--output-dir",
        type=Path,
        help="Optional directory for per-case input, SVG, manifest, and preview artifacts.",
    )
    primitive_check.add_argument("--markdown", type=Path)
    primitive_check.add_argument(
        "--case",
        action="append",
        default=None,
        help="Run only a specific primitive case or family. May be repeated.",
    )
    primitive_check.add_argument(
        "--filter",
        help="Run cases whose id or family matches a shell-style pattern.",
    )
    primitive_check.add_argument(
        "--refine",
        action="store_true",
        default=None,
        help="Run the local structure-preserving refinement gate for selected cases.",
    )
    primitive_check.add_argument("--refinement-iterations", type=int, default=None)
    primitive_check.add_argument(
        "--baseline",
        nargs="?",
        type=Path,
        const=Path("tests/data/primitive-baseline.json"),
        default=None,
        help=(
            "Compare the full run against a pinned metric baseline and fail "
            "on any drift. Without a value the checked-in default path is "
            "used. Requires running without --case/--filter."
        ),
    )
    primitive_check.add_argument(
        "--update-baseline",
        nargs="?",
        type=Path,
        const=Path("tests/data/primitive-baseline.json"),
        default=None,
        help="Regenerate the pinned metric baseline from this full run.",
    )
    primitive_check.add_argument("--config", type=Path)

    primitive_gallery = subcommands.add_parser(
        "primitive-gallery",
        help="Generate the static primitive quality gallery site.",
    )
    primitive_gallery.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("site/assets/primitive-quality/report.json"),
    )
    primitive_gallery.add_argument(
        "--output-dir",
        type=Path,
        default=Path("site/assets/primitive-quality/cases"),
        help="Directory for per-case gallery artifacts.",
    )
    primitive_gallery.add_argument(
        "--markdown",
        type=Path,
        default=Path("site/assets/primitive-quality/report.md"),
    )
    primitive_gallery.add_argument(
        "--html",
        type=Path,
        default=Path("site/primitive-quality/index.html"),
        help="Output path for the full static gallery page.",
    )
    primitive_gallery.add_argument(
        "--homepage",
        type=Path,
        default=Path("site/index.html"),
        help="Homepage path whose primitive teaser block should be refreshed.",
    )
    primitive_gallery.add_argument(
        "--no-homepage",
        action="store_true",
        help="Skip updating the homepage teaser block.",
    )
    primitive_gallery.add_argument(
        "--case",
        action="append",
        default=None,
        help="Generate only a specific primitive case. May be repeated.",
    )
    primitive_gallery.add_argument(
        "--filter",
        help="Generate cases whose id or family matches a shell-style pattern.",
    )
    primitive_gallery.add_argument(
        "--no-clean",
        action="store_true",
        help="Keep existing files in the artifact output directory.",
    )

    curated_check = subcommands.add_parser(
        "curated-check",
        help="Validate a curated real-image suite and optionally run it.",
    )
    curated_check.add_argument("suite", type=Path, nargs="?")
    curated_check.add_argument("-o", "--output", type=Path)
    curated_check.add_argument(
        "--output-dir",
        type=Path,
        help="Directory for per-case SVG, manifest, and config artifacts.",
    )
    curated_check.add_argument(
        "--run",
        action="store_true",
        help="Run each existing source image with its recommended config.",
    )
    curated_check.add_argument(
        "--snapshot",
        type=Path,
        help="Write a deterministic regression snapshot JSON.",
    )
    curated_check.add_argument(
        "--baseline-snapshot",
        type=Path,
        help="Compare editability review components against a previous snapshot.",
    )
    curated_check.add_argument("--markdown", type=Path)
    curated_check.add_argument("--config", type=Path)

    promotion_review_run = subcommands.add_parser(
        "promotion-review-run",
        help=(
            "Run a curated promotion suite and write review artifacts under "
            "one output root."
        ),
    )
    promotion_review_run.add_argument("suite", type=Path, nargs="?")
    promotion_review_run.add_argument("-o", "--output", type=Path)
    promotion_review_run.add_argument(
        "--output-dir",
        type=Path,
        help="Directory for per-case artifacts and suite-level review files.",
    )
    promotion_review_run.add_argument(
        "--snapshot",
        type=Path,
        help="Write a deterministic regression snapshot JSON.",
    )
    promotion_review_run.add_argument(
        "--baseline-snapshot",
        type=Path,
        help="Compare editability review components against a previous snapshot.",
    )
    promotion_review_run.add_argument("--markdown", type=Path)
    promotion_review_run.add_argument("--config", type=Path)

    lucide_check = subcommands.add_parser(
        "lucide-check",
        help="Validate the curated Lucide icon benchmark suite.",
    )
    lucide_check.add_argument("suite", type=Path, nargs="?")
    lucide_check.add_argument("-o", "--output", type=Path)
    lucide_check.add_argument(
        "--output-dir",
        type=Path,
        help="Directory for per-case Lucide artifacts.",
    )
    lucide_check.add_argument("--markdown", type=Path)
    lucide_check.add_argument("--config", type=Path)

    promotion_export = subcommands.add_parser(
        "promotion-export",
        help="Export promoted and fallback SVGs from a promotion-annotated manifest.",
    )
    promotion_export.add_argument("manifest", type=Path)
    promotion_export.add_argument("--promoted-svg", type=Path)
    promotion_export.add_argument("--fallback-svg", type=Path)
    promotion_export.add_argument("-o", "--output", type=Path)
    promotion_export.add_argument("--markdown", type=Path)

    promotion_apply_review = subcommands.add_parser(
        "promotion-apply-review",
        help="Apply an edited promotion review decision record.",
    )
    promotion_apply_review.add_argument("review_decision", type=Path)
    promotion_apply_review.add_argument("-o", "--output", type=Path)
    promotion_apply_review.add_argument("--markdown", type=Path)
    promotion_apply_review.add_argument("--manifest", type=Path)
    promotion_apply_review.add_argument("--reviewer")
    promotion_apply_review.add_argument("--reason")
    promotion_apply_review.add_argument("--correction-notes")
    promotion_apply_review.add_argument(
        "--corrected-artifact",
        action="append",
        default=None,
    )
    promotion_apply_review.add_argument(
        "--reviewed-region",
        action="append",
        default=None,
        help="Promotion region id explicitly reviewed by this terminal decision.",
    )

    promotion_review_harvest = subcommands.add_parser(
        "promotion-review-harvest",
        help=(
            "Apply selected promotion review decisions and write a "
            "harvest-curated config."
        ),
    )
    promotion_review_harvest.add_argument("review_packet", type=Path, nargs="?")
    promotion_review_harvest.add_argument("-o", "--output", type=Path)
    promotion_review_harvest.add_argument("--markdown", type=Path)
    promotion_review_harvest.add_argument("--harvest-config", type=Path)
    promotion_review_harvest.add_argument(
        "--decision",
        action="append",
        default=[],
        help="Terminal review decision as CASE_ID=path/to/decision.json.",
    )
    promotion_review_harvest.add_argument(
        "--decision-choice",
        action="append",
        default=[],
        help=(
            "Terminal review choice as CASE_ID=accepted|corrected|rejected|deferred; "
            "resolved through review decision templates."
        ),
    )
    promotion_review_harvest.add_argument(
        "--reviewer",
        action="append",
        default=[],
        help="Reviewer evidence as CASE_ID=name for the selected terminal decision.",
    )
    promotion_review_harvest.add_argument(
        "--reason",
        action="append",
        default=[],
        help="Review reason evidence as CASE_ID=reason.",
    )
    promotion_review_harvest.add_argument(
        "--correction-notes",
        action="append",
        default=[],
        help="Corrected-decision notes as CASE_ID=notes.",
    )
    promotion_review_harvest.add_argument(
        "--corrected-artifact",
        action="append",
        default=[],
        help="Corrected-decision artifact path as CASE_ID=path; repeatable.",
    )
    promotion_review_harvest.add_argument(
        "--reviewed-region",
        action="append",
        default=[],
        help="Reviewed promotion region as CASE_ID=region-id; repeatable.",
    )
    promotion_review_harvest.add_argument("--suite", type=Path)
    promotion_review_harvest.add_argument("--run-root", type=Path)
    promotion_review_harvest.add_argument("--harvest-output", type=Path)
    promotion_review_harvest.add_argument("--curated-report", type=Path)
    promotion_review_harvest.add_argument("--snapshot", type=Path)
    promotion_review_harvest.add_argument("--harvest-markdown", type=Path)
    promotion_review_harvest.add_argument("--config", type=Path)
    promotion_review_harvest.add_argument(
        "--decision-plan",
        type=Path,
        help=(
            "Portable reviewer decision overlay with decision_choices and "
            "decision_overrides."
        ),
    )

    sweep = subcommands.add_parser(
        "sweep",
        help="Run a config-driven vectorize sweep.",
    )
    sweep.add_argument("config", type=Path)
    sweep.add_argument("-o", "--output-dir", type=Path)
    sweep.add_argument("--markdown", type=Path)

    args = parser.parse_args(argv)
    if args.command == "vectorize":
        vectorize_artifacts = _resolved_vectorize_artifact_config(args)
        vectorize_config = _resolved_vectorize_config(args)
        cutout_export = _resolved_cutout_export(args)
        config = {
            "command": "vectorize",
            "input": str(vectorize_artifacts["input"]),
            "output": str(vectorize_artifacts["output"]),
            "manifest": (
                str(vectorize_artifacts["manifest"])
                if vectorize_artifacts.get("manifest")
                else None
            ),
            "debug_svg": (
                str(vectorize_artifacts["debug_svg"])
                if vectorize_artifacts.get("debug_svg")
                else None
            ),
            "run_dir": (
                str(vectorize_artifacts["run_dir"])
                if vectorize_artifacts.get("run_dir")
                else None
            ),
            "no_manifest": vectorize_artifacts["no_manifest"],
            "config": str(args.config) if args.config else None,
            "cutout_export": cutout_export,
            **vectorize_config,
        }
        scene = scene_from_flat_color_image(
            vectorize_artifacts["input"],
            **vectorize_config,
        )
        if vectorize_artifacts["run_dir"] is not None:
            run_dir = create_run_dir(vectorize_artifacts["run_dir"])
            run = write_vectorize_run(
                run_dir=run_dir,
                input_path=vectorize_artifacts["input"],
                scene=scene,
                config=config,
            )
            print(f"wrote run {run.run_dir} with {len(scene.anchors)} anchors")
            return

        output_path = vectorize_artifacts["output"]
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            scene.to_svg(SvgStyle(cutout_strategy=cutout_export)),
            encoding="utf-8",
        )
        if vectorize_artifacts["debug_svg"] is not None:
            debug_svg = vectorize_artifacts["debug_svg"]
            debug_svg.parent.mkdir(parents=True, exist_ok=True)
            debug_svg.write_text(scene.to_debug_svg(), encoding="utf-8")
        if not vectorize_artifacts["no_manifest"]:
            manifest_path = (
                vectorize_artifacts["manifest"] or output_path.with_suffix(".json")
            )
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            manifest_path.write_text(
                json.dumps(scene.to_manifest(), indent=2, sort_keys=True),
                encoding="utf-8",
            )
        print(f"wrote {output_path} with {len(scene.anchors)} anchors")
        return

    if args.command == "profile":
        profile_config = _resolved_profile_config(args)
        report = profile_vectorize(
            profile_config["input"],
            output=profile_config["output"],
            repeats=int(profile_config["repeats"]),
            config=profile_config["config"],
        )
        print(
            "profiled "
            f"{report['repeat_count']} runs; "
            f"mean={report['summary']['mean_elapsed_seconds']:.6f}s"
        )
        return

    if args.command == "promotion-export":
        result = write_promotion_svg_exports(
            manifest=args.manifest,
            promoted_svg=args.promoted_svg,
            fallback_svg=args.fallback_svg,
            output=args.output,
            markdown=args.markdown,
        )
        print(
            "exported promotion SVGs "
            f"(promoted={len(result['promoted_anchor_indexes'])}, "
            f"fallback={len(result['fallback_anchor_indexes'])})"
        )
        return

    if args.command == "profile-curated":
        profile_config = _resolved_profile_curated_config(args)
        report = profile_curated_suite(
            profile_config["suite"],
            output=profile_config["output"],
            repeats=int(profile_config["repeats"]),
            markdown=profile_config.get("markdown"),
        )
        print(
            "profiled curated suite "
            f"{report['checked_count']}/{report['case_count']} cases; "
            f"slowest={report['summary']['slowest_case_id'] or 'n/a'}"
        )
        return

    if args.command == "generate":
        generate_config = _resolved_generate_config(args)
        generate_synthetic_dataset(
            output_dir=generate_config["output_dir"],
            count=generate_config["count"],
            seed=generate_config["seed"],
            width=generate_config["width"],
            height=generate_config["height"],
            difficulty=generate_config["difficulty"],
            val_count=generate_config["val_count"],
            test_count=generate_config["test_count"],
        )
        print(
            "wrote "
            f"{generate_config['count']} synthetic samples to "
            f"{generate_config['output_dir']}"
        )
        return

    if args.command == "eval":
        eval_config = _resolved_eval_config(args)
        summary = write_eval_summary(
            run_root=eval_config["run_root"],
            output=eval_config["output"],
            markdown=eval_config.get("markdown"),
        )
        print(f"evaluated {summary['run_count']} runs")
        return

    if args.command == "segment":
        segment_artifacts = _resolved_segment_artifact_config(args)
        segment_config = _resolved_segment_config(args)
        segmenter = _segmenter_from_config(segment_config)
        proposals = segmenter.propose(segment_artifacts["input"])
        if bool(segment_config["geometry_gate"]):
            proposals = gate_segment_proposals(
                proposals,
                max_anchor_quality_error=(
                    float(segment_config["max_anchor_quality_error"])
                    if segment_config.get("max_anchor_quality_error") is not None
                    else None
                ),
                require_reserved_anchor=bool(
                    segment_config["require_reserved_anchor"]
                ),
            )
        proposal_groups = segment_proposal_groups(proposals)
        manifest = {
            "schema_version": 1,
            "input": str(segment_artifacts["input"]),
            "config": segment_config,
            "backend": segmenter_backend_status(segmenter),
            "proposal_count": len(proposals),
            "summary": segment_proposal_summary(proposals, proposal_groups),
            "proposal_groups": proposal_groups,
            "proposals": proposals_to_manifest(proposals),
        }
        output_path = segment_artifacts["output"]
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        if segment_artifacts.get("markdown") is not None:
            markdown_path = segment_artifacts["markdown"]
            markdown_path.parent.mkdir(parents=True, exist_ok=True)
            markdown_path.write_text(
                render_segment_proposal_markdown(manifest),
                encoding="utf-8",
            )
        print(f"wrote {len(proposals)} segment proposals")
        return

    if args.command == "report":
        report_config = _resolved_report_config(args)
        report_format = report_config["format"] or (
            "html"
            if Path(report_config["output"]).suffix.lower() == ".html"
            else "markdown"
        )
        if report_format == "html":
            write_html_report(
                manifest=report_config["manifest"],
                output=report_config["output"],
                config=report_config.get("config"),
            )
        else:
            write_markdown_report(
                manifest=report_config["manifest"],
                output=report_config["output"],
                config=report_config.get("config"),
            )
        print(f"wrote report {report_config['output']}")
        return

    if args.command == "train":
        train_config = _resolved_train_config(args)
        model = train_centroid_classifier(
            train_config["dataset"],
            output=train_config["output"],
        )
        print(
            f"trained {model['model_type']} with {model['train_examples']} examples"
        )
        return

    if args.command == "train-mlx":
        train_config, mlx_config = _resolved_train_mlx_config(args)
        model = train_mlx_transformer_classifier(
            train_config["dataset"],
            output=train_config["output"],
            config=mlx_config,
        )
        print(
            f"trained {model['model_type']} with {model['train_examples']} examples "
            f"(status={model['status']})"
        )
        return

    if args.command == "promotion-apply-review":
        result = apply_promotion_review_decision(
            review_decision=args.review_decision,
            output=args.output,
            markdown=args.markdown,
            manifest=args.manifest,
            reviewer=args.reviewer,
            reason=args.reason,
            correction_notes=args.correction_notes,
            corrected_artifacts=args.corrected_artifact,
            reviewed_region_ids=args.reviewed_region,
        )
        print(
            "applied promotion review "
            f"(case={result.get('case_id')}, decision={result['decision']})"
        )
        return

    if args.command == "promotion-review-harvest":
        review_harvest_config = _resolved_promotion_review_harvest_config(args)
        result = prepare_promotion_review_harvest(
            review_packet=review_harvest_config["review_packet"],
            output=review_harvest_config["output"],
            markdown=review_harvest_config.get("markdown"),
            harvest_config=review_harvest_config.get("harvest_config"),
            review_config=review_harvest_config.get("review_config"),
            decisions=review_harvest_config.get("decisions"),
            decision_templates=review_harvest_config.get("decision_templates"),
            decision_overrides=review_harvest_config.get("decision_overrides"),
            suite=review_harvest_config.get("suite"),
            run_root=review_harvest_config.get("run_root"),
            harvest_output=review_harvest_config.get("harvest_output"),
            curated_report=review_harvest_config.get("curated_report"),
            snapshot=review_harvest_config.get("snapshot"),
            harvest_markdown=review_harvest_config.get("harvest_markdown"),
        )
        print(
            "prepared promotion review harvest "
            f"(applied={result['newly_applied_decision_count']}, "
            f"pending={result['pending_case_count']}, "
            f"harvestable={result['harvestable_case_count']})"
        )
        return

    if args.command == "eval-classifier":
        eval_config = _resolved_eval_classifier_config(args)
        report = evaluate_classifier_model(
            eval_config["model"],
            eval_config["dataset"],
            output=eval_config["output"],
            markdown=eval_config.get("markdown"),
            splits=tuple(eval_config["splits"]),
        )
        print(
            f"evaluated {report['model_type']} on "
            f"{len(report['splits'])} dataset splits"
        )
        return

    if args.command == "harvest":
        harvest_config = _resolved_harvest_config(args)
        result = harvest_pseudo_labels(
            run_root=harvest_config["run_root"],
            output=harvest_config["output"],
            markdown=harvest_config.get("markdown"),
            max_run_diagnostics=int(harvest_config["max_run_diagnostics"]),
            max_classifier_prior_error=float(
                harvest_config["max_classifier_prior_error"]
            ),
            min_editability_score=float(harvest_config["min_editability_score"]),
            max_fragmentation_penalty=float(
                harvest_config["max_fragmentation_penalty"]
            ),
            max_raster_l1_error=float(harvest_config["max_raster_l1_error"]),
            max_raster_edge_error=float(harvest_config["max_raster_edge_error"]),
            max_anchor_quality_error=float(
                harvest_config["max_anchor_quality_error"]
            ),
            require_applied_review=bool(harvest_config["require_applied_review"]),
        )
        print(f"harvested {result['pseudo_label_count']} pseudo-labels")
        return

    if args.command == "harvest-curated":
        harvest_config = _resolved_harvest_curated_config(args)
        result = harvest_curated_pseudo_labels(
            suite=harvest_config["suite"],
            run_root=harvest_config["run_root"],
            output=harvest_config["output"],
            curated_report=harvest_config.get("curated_report"),
            snapshot=harvest_config.get("snapshot"),
            markdown=harvest_config.get("markdown"),
            max_run_diagnostics=int(harvest_config["max_run_diagnostics"]),
            max_classifier_prior_error=float(
                harvest_config["max_classifier_prior_error"]
            ),
            min_editability_score=float(harvest_config["min_editability_score"]),
            max_fragmentation_penalty=float(
                harvest_config["max_fragmentation_penalty"]
            ),
            max_raster_l1_error=float(harvest_config["max_raster_l1_error"]),
            max_raster_edge_error=float(harvest_config["max_raster_edge_error"]),
            max_anchor_quality_error=float(
                harvest_config["max_anchor_quality_error"]
            ),
            require_applied_review=bool(harvest_config["require_applied_review"]),
        )
        print(
            f"harvested {result['pseudo_label_count']} pseudo-labels "
            f"from {result['curated_checked_count']} curated cases"
        )
        return

    if args.command == "review":
        review_config = _resolved_review_config(args)
        review_result = create_review_file(
            pseudo_labels=review_config["pseudo_labels"],
            output=review_config["output"],
            markdown=review_config.get("markdown"),
            accept_applied_reviews=bool(
                review_config.get("accept_applied_reviews", False)
            ),
        )
        print(f"created review queue with {review_result['review_count']} items")
        return

    if args.command == "apply-review":
        review_config = _resolved_apply_review_config(args)
        reviewed = apply_review_file(
            review=review_config["review"],
            output=review_config["output"],
            markdown=review_config.get("markdown"),
        )
        print(f"accepted {reviewed['accepted_count']} reviewed pseudo-labels")
        return

    if args.command == "merge-labels":
        merge_config = _resolved_merge_labels_config(args)
        dataset = merge_reviewed_pseudo_label_dataset(
            reviewed_labels=merge_config["reviewed_labels"],
            output_dir=merge_config["output_dir"],
        )
        print(f"merged {dataset['count']} reviewed labels")
        return

    if args.command == "compare-training":
        compare_config = _resolved_compare_training_config(args)
        result = compare_retraining(
            base_dataset=compare_config["base_dataset"],
            pseudo_dataset=compare_config["pseudo_dataset"],
            validation_dataset=compare_config.get("validation_dataset"),
            output=compare_config["output"],
            markdown=compare_config.get("markdown"),
        )
        print(
            "compared "
            f"{result['baseline']['train_examples']} baseline examples with "
            f"{result['augmented']['train_examples']} augmented examples"
        )
        return

    if args.command == "training-gate":
        gate_config = _resolved_training_gate_config(args)
        result = gate_training_comparison(
            comparison=gate_config["comparison"],
            output=gate_config["output"],
            markdown=gate_config.get("markdown"),
            min_train_examples_delta=int(gate_config["min_train_examples_delta"]),
            min_best_accuracy_delta=float(gate_config["min_best_accuracy_delta"]),
            max_worst_accuracy_drop=float(gate_config["max_worst_accuracy_drop"]),
            allow_unchanged=bool(gate_config["allow_unchanged"]),
        )
        print(f"training gate decision: {result['decision']}")
        return

    if args.command == "self-learn":
        cycle_config = _resolved_self_learn_config(args)
        result = run_self_learning_cycle(
            base_dataset=cycle_config["base_dataset"],
            reviewed_labels=cycle_config["reviewed_labels"],
            validation_dataset=cycle_config.get("validation_dataset"),
            curated_suite=cycle_config.get("curated_suite"),
            curated_output_dir=cycle_config.get("curated_output_dir"),
            curated_report=cycle_config.get("curated_report"),
            curated_snapshot=cycle_config.get("curated_snapshot"),
            lucide_suite=cycle_config.get("lucide_suite"),
            lucide_output_dir=cycle_config.get("lucide_output_dir"),
            lucide_report=cycle_config.get("lucide_report"),
            suite_family_baseline=cycle_config.get("suite_family_baseline"),
            suite_family_baseline_output=cycle_config.get(
                "suite_family_baseline_output"
            ),
            suite_family_baseline_reviewer=str(
                cycle_config.get("suite_family_baseline_reviewer", "")
            ),
            suite_family_baseline_reason=str(
                cycle_config.get("suite_family_baseline_reason", "")
            ),
            suite_family_baseline_changelog=cycle_config.get(
                "suite_family_baseline_changelog"
            ),
            output_dir=cycle_config["output_dir"],
            markdown=cycle_config.get("markdown"),
            min_train_examples_delta=int(cycle_config["min_train_examples_delta"]),
            min_best_accuracy_delta=float(cycle_config["min_best_accuracy_delta"]),
            max_worst_accuracy_drop=float(cycle_config["max_worst_accuracy_drop"]),
            allow_unchanged=bool(cycle_config["allow_unchanged"]),
            backend=str(cycle_config.get("backend", "centroid")),
            mlx_config=(
                _retrain_mlx_config(cycle_config)
                if cycle_config.get("backend") == "mlx"
                else None
            ),
        )
        print(
            f"self-learning cycle {result['status']} "
            f"(gate={result['gate']['decision']})"
        )
        return

    if args.command == "retrain":
        retrain_config = _resolved_retrain_config(args)
        if retrain_config.get("backend", "centroid") == "mlx":
            model = retrain_mlx_classifier(
                base_dataset=retrain_config["base_dataset"],
                pseudo_dataset=retrain_config["pseudo_dataset"],
                validation_dataset=retrain_config.get("validation_dataset"),
                output=retrain_config["output"],
                comparison_output=retrain_config.get("comparison_output"),
                config=_retrain_mlx_config(retrain_config),
            )
        else:
            model = retrain_centroid_classifier(
                base_dataset=retrain_config["base_dataset"],
                pseudo_dataset=retrain_config["pseudo_dataset"],
                validation_dataset=retrain_config.get("validation_dataset"),
                output=retrain_config["output"],
                comparison_output=retrain_config.get("comparison_output"),
            )
        print(
            f"retrained {model['model_type']} with {model['train_examples']} examples"
        )
        return

    if args.command == "compare-snapshots":
        compare_config = _resolved_compare_snapshots_config(args)
        result = compare_snapshots(
            compare_config["before"],
            compare_config["after"],
            output=compare_config["output"],
            markdown=compare_config.get("markdown"),
        )
        print(f"compared {result['item_count']} snapshot items")
        return

    if args.command == "compare-segments":
        compare_config = _resolved_compare_segments_config(args)
        result = compare_segment_manifests(
            compare_config["before"],
            compare_config["after"],
            output=compare_config["output"],
            markdown=compare_config.get("markdown"),
        )
        print(_compare_segments_stdout_summary(result))
        return

    if args.command == "compare-git-snapshots":
        compare_config = _resolved_compare_git_snapshots_config(args)
        result = compare_git_snapshots(
            compare_config["before_ref"],
            compare_config["after_ref"],
            snapshot_path=compare_config["path"],
            output=compare_config["output"],
            markdown=compare_config.get("markdown"),
            repo=compare_config["repo"],
        )
        print(f"compared {result['item_count']} git snapshot items")
        return

    if args.command == "snapshot-git-ref":
        snapshot_config = _resolved_snapshot_git_ref_config(args)
        result = generate_git_curated_snapshot(
            snapshot_config["ref"],
            suite=snapshot_config["suite"],
            output=snapshot_config["output"],
            report=snapshot_config.get("report"),
            output_dir=snapshot_config.get("output_dir"),
            repo=snapshot_config["repo"],
            run=bool(snapshot_config["run"]),
            timeout_seconds=float(snapshot_config["timeout_seconds"]),
        )
        print(
            f"generated git snapshot for {result['git']['ref']} with "
            f"{result['case_count']} cases"
        )
        return

    if args.command == "refine":
        refine_config = _resolved_refine_config(args)
        result = refine_manifest(
            manifest=refine_config["manifest"],
            output=refine_config["output"],
            config=RefinementConfig(
                backend=str(refine_config["backend"]),
                max_iterations=int(refine_config["max_iterations"]),
                timeout_seconds=(
                    float(refine_config["timeout_seconds"])
                    if refine_config.get("timeout_seconds") is not None
                    else None
                ),
                source_image=refine_config.get("source_image"),
                raster_l1_weight=float(refine_config["raster_l1_weight"]),
                raster_edge_weight=float(refine_config["raster_edge_weight"]),
            ),
        )
        print(f"refined {len(result.get('anchors', []))} anchors")
        return

    if args.command == "refinement-gate":
        gate_config = _resolved_refinement_gate_config(args)
        result = gate_refinement_result(
            refined_manifest=gate_config["refined_manifest"],
            output=gate_config["output"],
            markdown=gate_config.get("markdown"),
            max_objective_regression=float(
                gate_config["max_objective_regression"]
            ),
            require_improvement=bool(gate_config["require_improvement"]),
        )
        print(f"refinement gate decision: {result['decision']}")
        return

    if args.command == "status":
        status_config = _resolved_status_config(args)
        result = collect_runtime_status(
            output=status_config.get("output"),
            markdown=status_config.get("markdown"),
            mlx_sam_model_path=status_config.get("mlx_sam_model_path"),
        )
        if (
            status_config.get("output") is None
            and status_config.get("markdown") is None
        ):
            print(render_runtime_status_markdown(result), end="")
            return
        print(
            "wrote runtime status with "
            f"{len(result['blocked_backends'])} backend blockers and "
            f"{len(result.get('blocked_capabilities', []))} capability blockers"
        )
        return

    if args.command == "primitive-check":
        primitive_config = _resolved_primitive_check_config(args)
        result = write_primitive_quality_report(
            output=primitive_config["output"],
            output_dir=primitive_config.get("output_dir"),
            markdown=primitive_config.get("markdown"),
            cases=primitive_config.get("case", ()),
            filter_pattern=primitive_config.get("filter"),
            refine=bool(primitive_config.get("refine", False)),
            refinement_iterations=int(
                primitive_config.get("refinement_iterations", 1)
            ),
        )
        print(
            "checked "
            f"{result['case_count']} primitive cases "
            f"({result['failed_count']} failed)"
        )
        if not result["ok"]:
            raise SystemExit(1)
        selection_active = bool(
            primitive_config.get("case") or primitive_config.get("filter")
        )
        if args.update_baseline is not None:
            if selection_active:
                print("baseline updates require a full run without --case/--filter")
                raise SystemExit(1)
            baseline_path = write_baseline(result, path=args.update_baseline)
            print(f"primitive baseline updated: {baseline_path}")
        elif args.baseline is not None:
            if selection_active:
                print("baseline comparison requires a full run without --case/--filter")
                raise SystemExit(1)
            diff = compare_to_baseline(result, load_baseline(args.baseline))
            print(render_baseline_diff_markdown(diff), end="")
            if not diff["ok"]:
                raise SystemExit(1)
        return

    if args.command == "primitive-gallery":
        result = write_primitive_gallery_site(
            output=args.output,
            output_dir=args.output_dir,
            markdown=args.markdown,
            html_output=args.html,
            homepage=None if args.no_homepage else args.homepage,
            cases=args.case or (),
            filter_pattern=args.filter,
            clean=not args.no_clean,
        )
        print(
            "wrote primitive gallery with "
            f"{result['case_count']} cases "
            f"({result['failed_count']} failed)"
        )
        if not result["ok"]:
            raise SystemExit(1)
        return

    if args.command == "curated-check":
        curated_config = _resolved_curated_check_config(args)
        result = check_curated_suite(
            curated_config["suite"],
            output=curated_config["output"],
            output_dir=curated_config.get("output_dir"),
            run=bool(curated_config.get("run", False)),
            snapshot=curated_config.get("snapshot"),
            baseline_snapshot=curated_config.get("baseline_snapshot"),
            markdown=curated_config.get("markdown"),
        )
        print(f"checked {result['case_count']} curated cases")
        return

    if args.command == "promotion-review-run":
        review_run_config = _resolved_promotion_review_run_config(args)
        result = check_curated_suite(
            review_run_config["suite"],
            output=review_run_config["output"],
            output_dir=review_run_config["output_dir"],
            run=True,
            snapshot=review_run_config["snapshot"],
            baseline_snapshot=review_run_config.get("baseline_snapshot"),
            markdown=review_run_config["markdown"],
        )
        review_harvest_config = _promotion_review_run_harvest_config(
            review_run_config,
        )
        review_harvest_config["decision_templates"] = (
            _promotion_review_run_decision_templates(
                review_harvest_config["review_packet"]
            )
        )
        review_harvest_config_path = (
            review_run_config["output_dir"] / "promotion-review-harvest.json"
        )
        _write_json_file(review_harvest_config_path, review_harvest_config)
        result.setdefault("artifacts", {})[
            "promotion_review_harvest_config"
        ] = str(review_harvest_config_path)
        result["next_commands"] = _promotion_review_run_next_commands(
            review_harvest_config_path
        )
        write_review_packet_followup_artifacts(
            review_run_config["output_dir"],
            result,
            review_harvest_config=review_harvest_config_path,
        )
        _write_json_file(review_run_config["output"], result)
        review_run_config["markdown"].parent.mkdir(parents=True, exist_ok=True)
        review_run_config["markdown"].write_text(
            render_curated_markdown(result),
            encoding="utf-8",
        )
        print(
            "prepared promotion review run "
            f"({result['case_count']} curated cases, "
            f"output_dir={review_run_config['output_dir']})"
        )
        return

    if args.command == "lucide-check":
        lucide_config = _resolved_lucide_check_config(args)
        overrides = {
            key: value
            for key, value in lucide_config.items()
            if key in VECTORIZE_DEFAULT_CONFIG
        }
        result = check_lucide_suite(
            lucide_config["suite"],
            output=lucide_config["output"],
            output_dir=lucide_config.get("output_dir"),
            markdown=lucide_config.get("markdown"),
            config_overrides=overrides,
        )
        print(
            "checked "
            f"{result['case_count']} Lucide cases "
            f"({result['failed_count']} failed)"
        )
        if not result["ok"]:
            raise SystemExit(1)
        return

    if args.command == "sweep":
        sweep_config = _resolved_sweep_command_config(args)
        result = run_sweep(
            sweep_config["config"],
            output_dir=sweep_config["output_dir"],
            markdown=sweep_config.get("markdown"),
        )
        print(f"ran {result['run_count']} sweep runs")
        return


def _resolved_vectorize_config(args: argparse.Namespace) -> dict[str, object]:
    config = dict(VECTORIZE_DEFAULT_CONFIG)
    if args.config is not None:
        loaded = _load_vectorize_config(args.config)
        config.update(
            {
                key: value
                for key, value in loaded.items()
                if key in VECTORIZE_DEFAULT_CONFIG
            }
        )

    for key in VECTORIZE_DEFAULT_CONFIG:
        value = getattr(args, key, None)
        if value is not None:
            config[key] = str(value) if key == "classifier_model" else value
    return config


def _promotion_review_decision_args(values: list[str]) -> dict[str, Path]:
    decisions: dict[str, Path] = {}
    for value in values:
        if "=" not in value:
            raise ValueError("promotion review decision args must be CASE_ID=path")
        case_id, path = value.split("=", 1)
        if not case_id or not path:
            raise ValueError("promotion review decision args must be CASE_ID=path")
        decisions[case_id] = Path(path)
    return decisions


def _promotion_review_decision_choice_args(values: list[str]) -> dict[str, str]:
    choices: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(
                "promotion review decision choices must be CASE_ID=decision"
            )
        case_id, decision = value.split("=", 1)
        if not case_id or not decision:
            raise ValueError(
                "promotion review decision choices must be CASE_ID=decision"
            )
        if decision not in PROMOTION_REVIEW_TERMINAL_DECISIONS:
            allowed = ", ".join(PROMOTION_REVIEW_TERMINAL_DECISIONS)
            raise ValueError(
                "promotion review decision choices must use one of: "
                f"{allowed}"
            )
        choices[case_id] = decision
    return choices


def _promotion_review_override_args(
    *,
    reviewers: list[str],
    reasons: list[str],
    correction_notes: list[str],
    corrected_artifacts: list[str],
    reviewed_regions: list[str],
) -> dict[str, dict[str, object]]:
    overrides: dict[str, dict[str, object]] = {}
    for field, values in (
        ("reviewer", reviewers),
        ("reason", reasons),
        ("correction_notes", correction_notes),
    ):
        for case_id, value in _promotion_review_string_assignments(
            values,
            field,
        ).items():
            overrides.setdefault(case_id, {})[field] = value
    for case_id, value in _promotion_review_string_assignment_items(
        corrected_artifacts,
        "corrected_artifacts",
    ):
        artifacts = overrides.setdefault(case_id, {}).setdefault(
            "corrected_artifacts",
            [],
        )
        if not isinstance(artifacts, list):
            artifacts = []
            overrides[case_id]["corrected_artifacts"] = artifacts
        artifacts.append(value)
    for case_id, value in _promotion_review_string_assignment_items(
        reviewed_regions,
        "reviewed_region_ids",
    ):
        regions = overrides.setdefault(case_id, {}).setdefault(
            "reviewed_region_ids",
            [],
        )
        if not isinstance(regions, list):
            regions = []
            overrides[case_id]["reviewed_region_ids"] = regions
        regions.append(value)
    return overrides


def _promotion_review_string_assignments(
    values: list[str],
    field: str,
) -> dict[str, str]:
    assignments: dict[str, str] = {}
    for case_id, value in _promotion_review_string_assignment_items(values, field):
        assignments[case_id] = value
    return assignments


def _promotion_review_string_assignment_items(
    values: list[str],
    field: str,
) -> list[tuple[str, str]]:
    assignments: list[tuple[str, str]] = []
    for value in values:
        if "=" not in value:
            raise ValueError(
                f"promotion review {field} overrides must be CASE_ID=value"
            )
        case_id, assignment = value.split("=", 1)
        if not case_id or not assignment.strip():
            raise ValueError(
                f"promotion review {field} overrides must be CASE_ID=value"
            )
        assignments.append((case_id, assignment))
    return assignments


def _merge_promotion_review_overrides(
    base: object,
    cli: dict[str, dict[str, object]],
) -> dict[str, dict[str, object]]:
    merged: dict[str, dict[str, object]] = {}
    if isinstance(base, dict):
        for case_id, overrides in base.items():
            if isinstance(case_id, str) and isinstance(overrides, dict):
                merged[case_id] = dict(overrides)
    for case_id, overrides in cli.items():
        case_overrides = merged.setdefault(case_id, {})
        for field, value in overrides.items():
            if field in {"corrected_artifacts", "reviewed_region_ids"}:
                case_overrides[field] = list(value) if isinstance(value, list) else []
            else:
                case_overrides[field] = value
    return merged


def _resolved_promotion_review_harvest_config(
    args: argparse.Namespace,
) -> dict[str, object]:
    config = _load_promotion_review_harvest_config(args.config)
    if args.config is not None:
        config["review_config"] = args.config
    for key in (
        "review_packet",
        "output",
        "markdown",
        "harvest_config",
        "suite",
        "run_root",
        "harvest_output",
        "curated_report",
        "snapshot",
        "harvest_markdown",
        "decision_plan",
    ):
        value = getattr(args, key, None)
        if value is not None:
            config[key] = value
    _require_config_paths(
        config,
        ("review_packet", "output"),
        "promotion-review-harvest",
    )
    decision_plan = _load_promotion_review_decision_plan(
        config.get("decision_plan")
    )
    plan_choices = dict(decision_plan.get("decision_choices", {}))
    config_choices = dict(config.get("decision_choices", {}))
    cli_choices = _promotion_review_decision_choice_args(args.decision_choice)
    decisions: dict[str, Path] = {}
    decisions.update(
        _promotion_review_decisions_from_choices(config, config_choices)
    )
    decisions.update(dict(config.get("decisions", {})))
    decisions.update(_promotion_review_decisions_from_choices(config, plan_choices))
    decisions.update(_promotion_review_decisions_from_choices(config, cli_choices))
    decisions.update(_promotion_review_decision_args(args.decision))
    if decisions:
        config["decisions"] = decisions
    else:
        config["decisions"] = {}
    cli_overrides = _promotion_review_override_args(
        reviewers=args.reviewer,
        reasons=args.reason,
        correction_notes=args.correction_notes,
        corrected_artifacts=args.corrected_artifact,
        reviewed_regions=args.reviewed_region,
    )
    config["decision_overrides"] = _merge_promotion_review_overrides(
        _merge_promotion_review_overrides(
            config.get("decision_overrides", {}),
            dict(decision_plan.get("decision_overrides", {})),
        ),
        cli_overrides,
    )
    return config


def _resolved_vectorize_artifact_config(
    args: argparse.Namespace,
) -> dict[str, object]:
    config: dict[str, object] = {
        "input": None,
        "output": None,
        "manifest": None,
        "debug_svg": None,
        "run_dir": None,
        "no_manifest": False,
    }
    if args.config is not None:
        loaded = _load_vectorize_config(args.config)
        config.update(
            {
                key: value
                for key, value in loaded.items()
                if key in VECTORIZE_ARTIFACT_CONFIG_KEYS
            }
        )

    for key in ("input", "output", "manifest", "debug_svg", "run_dir"):
        value = getattr(args, key, None)
        if value is not None:
            config[key] = value
    if args.no_manifest is not None:
        config["no_manifest"] = args.no_manifest

    _require_config_paths(config, ("input", "output"), "vectorize")
    for key in ("input", "output", "manifest", "debug_svg", "run_dir"):
        if config.get(key) is not None:
            config[key] = Path(str(config[key]))
    config["no_manifest"] = bool(config.get("no_manifest", False))
    return config


def _resolved_cutout_export(args: argparse.Namespace) -> str:
    if args.cutout_export is not None:
        return str(args.cutout_export)
    if args.config is None:
        return "overlay_stroke"
    loaded = _load_vectorize_config(args.config)
    return str(loaded.get("cutout_export", "overlay_stroke"))


def _resolved_train_config(args: argparse.Namespace) -> dict[str, Path]:
    config = _load_path_config(args.config, TRAIN_CONFIG_KEYS, "train")
    if args.dataset is not None:
        config["dataset"] = args.dataset
    if args.output is not None:
        config["output"] = args.output
    _require_config_paths(config, ("dataset", "output"), "train")
    return config


def _resolved_eval_config(args: argparse.Namespace) -> dict[str, Path]:
    config = _load_path_config(args.config, EVAL_CONFIG_KEYS, "eval")
    if args.run_root is not None:
        config["run_root"] = args.run_root
    if args.output is not None:
        config["output"] = args.output
    if args.markdown is not None:
        config["markdown"] = args.markdown
    _require_config_paths(config, ("run_root", "output"), "eval")
    return config


def _resolved_report_config(args: argparse.Namespace) -> dict[str, object]:
    config = _load_report_config(args.command_config)
    config.setdefault("format", None)
    if args.manifest is not None:
        config["manifest"] = args.manifest
    if args.output is not None:
        config["output"] = args.output
    if args.config is not None:
        config["config"] = args.config
    if args.format is not None:
        config["format"] = args.format
    _require_config_paths(config, ("manifest", "output"), "report")
    for key in ("manifest", "output", "config"):
        if config.get(key) is not None:
            config[key] = Path(str(config[key]))
    report_format = config.get("format")
    if report_format is not None and report_format not in {"markdown", "html"}:
        raise ValueError("report format must be markdown or html")
    return config


def _resolved_profile_config(args: argparse.Namespace) -> dict[str, object]:
    loaded = _load_profile_config(args.config)
    vectorize_config = dict(VECTORIZE_DEFAULT_CONFIG)
    vectorize_config.update(
        {
            key: value
            for key, value in loaded.items()
            if key in VECTORIZE_DEFAULT_CONFIG
        }
    )
    for key in VECTORIZE_DEFAULT_CONFIG:
        value = getattr(args, key, None)
        if value is not None:
            vectorize_config[key] = str(value) if key == "classifier_model" else value
    if vectorize_config.get("classifier_model") is not None:
        vectorize_config["classifier_model"] = str(vectorize_config["classifier_model"])

    config: dict[str, object] = {
        "input": loaded.get("input"),
        "output": loaded.get("output"),
        "repeats": loaded.get("repeats", 1),
        "config": vectorize_config,
    }
    if args.input is not None:
        config["input"] = args.input
    if args.output is not None:
        config["output"] = args.output
    if args.repeats is not None:
        config["repeats"] = args.repeats
    _require_config_paths(config, ("input", "output"), "profile")
    config["input"] = Path(str(config["input"]))
    config["output"] = Path(str(config["output"]))
    config["repeats"] = int(config["repeats"])
    return config


def _resolved_profile_curated_config(
    args: argparse.Namespace,
) -> dict[str, object]:
    config = _load_profile_curated_config(args.config)
    if args.suite is not None:
        config["suite"] = args.suite
    if args.output is not None:
        config["output"] = args.output
    if args.markdown is not None:
        config["markdown"] = args.markdown
    if args.repeats is not None:
        config["repeats"] = args.repeats
    config.setdefault("repeats", 1)
    _require_config_paths(config, ("suite", "output"), "profile-curated")
    for key in ("suite", "output", "markdown"):
        if config.get(key) is not None:
            config[key] = Path(str(config[key]))
    config["repeats"] = int(config["repeats"])
    return config


def _resolved_generate_config(args: argparse.Namespace) -> dict[str, object]:
    config = dict(GENERATE_DEFAULT_CONFIG)
    config.update(_load_generate_config(args.config))
    for key in GENERATE_DEFAULT_CONFIG:
        value = getattr(args, key, None)
        if value is not None:
            config[key] = value

    _require_config_paths(config, ("output_dir",), "generate")
    config["output_dir"] = Path(str(config["output_dir"]))
    for key in ("count", "seed", "width", "height", "val_count", "test_count"):
        config[key] = int(config[key])
    config["difficulty"] = str(config["difficulty"])
    return config


def _resolved_sweep_command_config(args: argparse.Namespace) -> dict[str, object]:
    loaded = json.loads(args.config.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("sweep config must be a JSON object")
    config: dict[str, object] = {
        "config": args.config,
        "output_dir": loaded.get("output_dir"),
        "markdown": loaded.get("markdown"),
    }
    if args.output_dir is not None:
        config["output_dir"] = args.output_dir
    if args.markdown is not None:
        config["markdown"] = args.markdown

    _require_config_paths(config, ("output_dir",), "sweep")
    config["output_dir"] = Path(str(config["output_dir"]))
    if config.get("markdown") is not None:
        config["markdown"] = Path(str(config["markdown"]))
    return config


def _resolved_eval_classifier_config(args: argparse.Namespace) -> dict[str, object]:
    config = _load_eval_classifier_config(args.config)
    if args.model is not None:
        config["model"] = args.model
    if args.dataset is not None:
        config["dataset"] = args.dataset
    if args.output is not None:
        config["output"] = args.output
    if args.markdown is not None:
        config["markdown"] = args.markdown
    if args.splits is not None:
        config["splits"] = list(args.splits)
    _require_config_paths(config, ("model", "dataset", "output"), "eval-classifier")
    return {
        "model": Path(config["model"]),
        "dataset": Path(config["dataset"]),
        "output": Path(config["output"]),
        "markdown": (
            Path(config["markdown"]) if config.get("markdown") is not None else None
        ),
        "splits": _normalized_splits(config.get("splits", ["val", "test"])),
    }


def _resolved_train_mlx_config(
    args: argparse.Namespace,
) -> tuple[dict[str, Path], MlxClassifierTrainingConfig]:
    config = _load_train_mlx_config(args.config)
    if args.dataset is not None:
        config["dataset"] = args.dataset
    if args.output is not None:
        config["output"] = args.output
    for key in (
        "epochs",
        "hidden_dim",
        "num_heads",
        "num_layers",
        "learning_rate",
        "crop_size",
    ):
        value = getattr(args, key, None)
        if value is not None:
            config[key] = value
    if args.allow_unavailable:
        config["allow_unavailable"] = True
    _require_config_paths(config, ("dataset", "output"), "train-mlx")
    return (
        {
            "dataset": Path(config["dataset"]),
            "output": Path(config["output"]),
        },
        MlxClassifierTrainingConfig(
            epochs=int(config.get("epochs", 25)),
            hidden_dim=int(config.get("hidden_dim", 32)),
            num_heads=int(config.get("num_heads", 4)),
            num_layers=int(config.get("num_layers", 1)),
            learning_rate=float(config.get("learning_rate", 0.001)),
            crop_size=int(config.get("crop_size", 16)),
            allow_unavailable=bool(config.get("allow_unavailable", False)),
        ),
    )


def _resolved_segment_config(args: argparse.Namespace) -> dict[str, object]:
    config = dict(SEGMENT_CONFIG_DEFAULTS)
    if args.config is not None:
        loaded = _load_segment_config(args.config)
        config.update(
            {
                key: value
                for key, value in loaded.items()
                if key in SEGMENT_CONFIG_DEFAULTS
            }
        )

    for key in SEGMENT_CONFIG_DEFAULTS:
        value = getattr(args, key, None)
        if value is not None:
            config[key] = value
    if config.get("mlx_model_path") is not None:
        config["mlx_model_path"] = str(config["mlx_model_path"])
    if str(config["mlx_prompt_strategy"]) not in MLX_PROMPT_STRATEGIES:
        supported = ", ".join(MLX_PROMPT_STRATEGIES)
        msg = (
            "unsupported mlx_prompt_strategy: "
            f"{config['mlx_prompt_strategy']} (expected one of: {supported})"
        )
        raise ValueError(msg)
    return config


def _resolved_segment_artifact_config(args: argparse.Namespace) -> dict[str, object]:
    config: dict[str, object] = {"input": None, "output": None, "markdown": None}
    if args.config is not None:
        loaded = _load_segment_config(args.config)
        config.update(
            {
                key: value
                for key, value in loaded.items()
                if key in SEGMENT_ARTIFACT_CONFIG_KEYS
            }
        )

    for key in SEGMENT_ARTIFACT_CONFIG_KEYS:
        value = getattr(args, key, None)
        if value is not None:
            config[key] = value

    _require_config_paths(config, ("input", "output"), "segment")
    for key in SEGMENT_ARTIFACT_CONFIG_KEYS:
        if config.get(key) is not None:
            config[key] = Path(str(config[key]))
    return config


def _resolved_compare_training_config(args: argparse.Namespace) -> dict[str, Path]:
    config = _load_path_config(
        args.config,
        COMPARE_TRAINING_CONFIG_KEYS,
        "compare-training",
    )
    if args.base_dataset is not None:
        config["base_dataset"] = args.base_dataset
    if args.pseudo_dataset is not None:
        config["pseudo_dataset"] = args.pseudo_dataset
    if args.validation_dataset is not None:
        config["validation_dataset"] = args.validation_dataset
    if args.output is not None:
        config["output"] = args.output
    if args.markdown is not None:
        config["markdown"] = args.markdown
    _require_config_paths(
        config,
        ("base_dataset", "pseudo_dataset", "output"),
        "compare-training",
    )
    return config


def _resolved_training_gate_config(args: argparse.Namespace) -> dict[str, object]:
    config: dict[str, object] = {
        "min_train_examples_delta": 1,
        "min_best_accuracy_delta": 0.0,
        "max_worst_accuracy_drop": 0.0,
        "allow_unchanged": False,
        "backend": "centroid",
    }
    config.update(
        _load_training_gate_config(args.config)
        if args.config is not None
        else {}
    )
    if args.comparison is not None:
        config["comparison"] = args.comparison
    if args.output is not None:
        config["output"] = args.output
    if args.markdown is not None:
        config["markdown"] = args.markdown
    for key in (
        "min_train_examples_delta",
        "min_best_accuracy_delta",
        "max_worst_accuracy_drop",
    ):
        value = getattr(args, key, None)
        if value is not None:
            config[key] = value
    if args.allow_unchanged:
        config["allow_unchanged"] = True
    _require_config_paths(config, ("comparison", "output"), "training-gate")
    for key in ("comparison", "output", "markdown"):
        if config.get(key) is not None:
            config[key] = Path(str(config[key]))
    return config


def _resolved_self_learn_config(args: argparse.Namespace) -> dict[str, object]:
    config: dict[str, object] = {
        "min_train_examples_delta": 1,
        "min_best_accuracy_delta": 0.0,
        "max_worst_accuracy_drop": 0.0,
        "allow_unchanged": False,
    }
    config.update(
        _load_self_learn_config(args.config)
        if args.config is not None
        else {}
    )
    if args.base_dataset is not None:
        config["base_dataset"] = args.base_dataset
    if args.reviewed_labels is not None:
        config["reviewed_labels"] = args.reviewed_labels
    if args.validation_dataset is not None:
        config["validation_dataset"] = args.validation_dataset
    if args.curated_suite is not None:
        config["curated_suite"] = args.curated_suite
    if args.curated_output_dir is not None:
        config["curated_output_dir"] = args.curated_output_dir
    if args.curated_report is not None:
        config["curated_report"] = args.curated_report
    if args.curated_snapshot is not None:
        config["curated_snapshot"] = args.curated_snapshot
    if args.lucide_suite is not None:
        config["lucide_suite"] = args.lucide_suite
    if args.lucide_output_dir is not None:
        config["lucide_output_dir"] = args.lucide_output_dir
    if args.lucide_report is not None:
        config["lucide_report"] = args.lucide_report
    if args.suite_family_baseline is not None:
        config["suite_family_baseline"] = args.suite_family_baseline
    if args.suite_family_baseline_output is not None:
        config["suite_family_baseline_output"] = args.suite_family_baseline_output
    if args.suite_family_baseline_reviewer is not None:
        config["suite_family_baseline_reviewer"] = args.suite_family_baseline_reviewer
    if args.suite_family_baseline_reason is not None:
        config["suite_family_baseline_reason"] = args.suite_family_baseline_reason
    if args.suite_family_baseline_changelog is not None:
        config["suite_family_baseline_changelog"] = args.suite_family_baseline_changelog
    if args.output_dir is not None:
        config["output_dir"] = args.output_dir
    if args.markdown is not None:
        config["markdown"] = args.markdown
    if args.backend is not None:
        config["backend"] = args.backend
    for key in (
        "min_train_examples_delta",
        "min_best_accuracy_delta",
        "max_worst_accuracy_drop",
        "epochs",
        "hidden_dim",
        "num_heads",
        "num_layers",
        "learning_rate",
        "crop_size",
    ):
        value = getattr(args, key, None)
        if value is not None:
            config[key] = value
    if args.allow_unchanged:
        config["allow_unchanged"] = True
    if args.allow_unavailable:
        config["allow_unavailable"] = True
    _require_config_paths(
        config,
        ("base_dataset", "reviewed_labels", "output_dir"),
        "self-learn",
    )
    for key in (
        "base_dataset",
        "reviewed_labels",
        "validation_dataset",
        "curated_suite",
        "curated_output_dir",
        "curated_report",
        "curated_snapshot",
        "lucide_suite",
        "lucide_output_dir",
        "lucide_report",
        "suite_family_baseline",
        "suite_family_baseline_output",
        "suite_family_baseline_changelog",
        "output_dir",
        "markdown",
    ):
        if config.get(key) is not None:
            config[key] = Path(str(config[key]))
    return config


def _resolved_retrain_config(args: argparse.Namespace) -> dict[str, object]:
    config = _load_retrain_config(args.config)
    if args.base_dataset is not None:
        config["base_dataset"] = args.base_dataset
    if args.pseudo_dataset is not None:
        config["pseudo_dataset"] = args.pseudo_dataset
    if args.validation_dataset is not None:
        config["validation_dataset"] = args.validation_dataset
    if args.output is not None:
        config["output"] = args.output
    if args.comparison_output is not None:
        config["comparison_output"] = args.comparison_output
    if args.backend is not None:
        config["backend"] = args.backend
    for key in (
        "epochs",
        "hidden_dim",
        "num_heads",
        "num_layers",
        "learning_rate",
        "crop_size",
    ):
        value = getattr(args, key, None)
        if value is not None:
            config[key] = value
    if args.allow_unavailable:
        config["allow_unavailable"] = True
    _require_config_paths(
        config,
        ("base_dataset", "pseudo_dataset", "output"),
        "retrain",
    )
    return config


def _resolved_compare_snapshots_config(args: argparse.Namespace) -> dict[str, Path]:
    config = _load_path_config(
        args.config,
        COMPARE_SNAPSHOTS_CONFIG_KEYS,
        "compare-snapshots",
    )
    if args.before is not None:
        config["before"] = args.before
    if args.after is not None:
        config["after"] = args.after
    if args.output is not None:
        config["output"] = args.output
    if args.markdown is not None:
        config["markdown"] = args.markdown
    _require_config_paths(config, ("before", "after", "output"), "compare-snapshots")
    return config


def _resolved_compare_segments_config(args: argparse.Namespace) -> dict[str, Path]:
    config = _load_path_config(
        args.config,
        COMPARE_SEGMENTS_CONFIG_KEYS,
        "compare-segments",
    )
    if args.before is not None:
        config["before"] = args.before
    if args.after is not None:
        config["after"] = args.after
    if args.output is not None:
        config["output"] = args.output
    if args.markdown is not None:
        config["markdown"] = args.markdown
    _require_config_paths(config, ("before", "after", "output"), "compare-segments")
    return config


def _compare_segments_stdout_summary(result: dict[str, object]) -> str:
    assessment = result.get("source_delta_assessment")
    assessment = assessment if isinstance(assessment, dict) else {}
    spatial_summary = result.get("spatial_match_summary")
    spatial_summary = spatial_summary if isinstance(spatial_summary, dict) else {}
    return (
        "compared segment sources "
        f"{result.get('before_source', 'n/a')} -> {result.get('after_source', 'n/a')}: "
        f"proposals {result.get('before_proposal_count', 0)} -> "
        f"{result.get('after_proposal_count', 0)} "
        f"(delta {result.get('proposal_count_delta', 0)}), "
        f"shared={result.get('shared_proposal_count', 0)}, "
        f"spatial_matches={result.get('spatial_match_count', 0)}, "
        f"spatial_mean_iou={spatial_summary.get('mean_bbox_iou', 'n/a')}, "
        f"verdict={assessment.get('verdict', 'n/a')}, "
        f"green_delta={assessment.get('green_promotion_delta', 'n/a')}, "
        f"red_delta={assessment.get('red_candidate_delta', 'n/a')}, "
        f"manual_delta={assessment.get('manual_review_delta', 'n/a')}"
    )


def _resolved_compare_git_snapshots_config(
    args: argparse.Namespace,
) -> dict[str, object]:
    config = _load_compare_git_snapshots_config(args.config)
    config.setdefault("repo", Path("."))
    if args.before_ref is not None:
        config["before_ref"] = args.before_ref
    if args.after_ref is not None:
        config["after_ref"] = args.after_ref
    if args.path is not None:
        config["path"] = args.path
    if args.output is not None:
        config["output"] = args.output
    if args.markdown is not None:
        config["markdown"] = args.markdown
    if args.repo is not None:
        config["repo"] = args.repo
    _require_config_paths(
        config,
        ("before_ref", "after_ref", "path", "output", "repo"),
        "compare-git-snapshots",
    )
    for key in ("path", "output", "markdown", "repo"):
        if config.get(key) is not None:
            config[key] = Path(str(config[key]))
    config["before_ref"] = str(config["before_ref"])
    config["after_ref"] = str(config["after_ref"])
    return config


def _resolved_snapshot_git_ref_config(args: argparse.Namespace) -> dict[str, object]:
    config = _load_snapshot_git_ref_config(args.config)
    config.setdefault("repo", Path("."))
    config.setdefault("timeout_seconds", 120.0)
    config.setdefault("run", True)
    if args.ref is not None:
        config["ref"] = args.ref
    if args.suite is not None:
        config["suite"] = args.suite
    if args.output is not None:
        config["output"] = args.output
    if args.report is not None:
        config["report"] = args.report
    if args.output_dir is not None:
        config["output_dir"] = args.output_dir
    if args.repo is not None:
        config["repo"] = args.repo
    if args.timeout_seconds is not None:
        config["timeout_seconds"] = args.timeout_seconds
    if args.run is not None:
        config["run"] = args.run
    _require_config_paths(
        config,
        ("ref", "suite", "output", "repo"),
        "snapshot-git-ref",
    )
    for key in ("suite", "output", "report", "output_dir", "repo"):
        if config.get(key) is not None:
            config[key] = Path(str(config[key]))
    config["ref"] = str(config["ref"])
    config["timeout_seconds"] = float(config["timeout_seconds"])
    config["run"] = bool(config["run"])
    return config


def _load_compare_git_snapshots_config(path: Path | None) -> dict[str, object]:
    if path is None:
        return {}
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("compare-git-snapshots config must be a JSON object")
    unknown = sorted(set(loaded) - COMPARE_GIT_SNAPSHOTS_CONFIG_KEYS)
    if unknown:
        msg = f"unsupported compare-git-snapshots config keys: {', '.join(unknown)}"
        raise ValueError(msg)
    config = dict(loaded)
    for key in ("path", "output", "markdown", "repo"):
        if config.get(key) is not None:
            config[key] = Path(str(config[key]))
    return config


def _load_snapshot_git_ref_config(path: Path | None) -> dict[str, object]:
    if path is None:
        return {}
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("snapshot-git-ref config must be a JSON object")
    unknown = sorted(set(loaded) - SNAPSHOT_GIT_REF_CONFIG_KEYS)
    if unknown:
        msg = f"unsupported snapshot-git-ref config keys: {', '.join(unknown)}"
        raise ValueError(msg)
    config = dict(loaded)
    for key in ("suite", "output", "report", "output_dir", "repo"):
        if config.get(key) is not None:
            config[key] = Path(str(config[key]))
    return config


def _load_retrain_config(path: Path | None) -> dict[str, object]:
    if path is None:
        return {}
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("retrain config must be a JSON object")
    unknown = sorted(set(loaded) - RETRAIN_CONFIG_KEYS)
    if unknown:
        msg = f"unsupported retrain config keys: {', '.join(unknown)}"
        raise ValueError(msg)
    config = dict(loaded)
    for key in (
        "base_dataset",
        "pseudo_dataset",
        "validation_dataset",
        "output",
        "comparison_output",
    ):
        if config.get(key) is not None:
            config[key] = Path(str(config[key]))
    return config


def _retrain_mlx_config(config: dict[str, object]) -> MlxClassifierTrainingConfig:
    return MlxClassifierTrainingConfig(
        epochs=int(config.get("epochs", 25)),
        hidden_dim=int(config.get("hidden_dim", 32)),
        num_heads=int(config.get("num_heads", 4)),
        num_layers=int(config.get("num_layers", 1)),
        learning_rate=float(config.get("learning_rate", 0.001)),
        crop_size=int(config.get("crop_size", 16)),
        allow_unavailable=bool(config.get("allow_unavailable", False)),
    )


def _resolved_refine_config(args: argparse.Namespace) -> dict[str, object]:
    config = _load_refine_config(args.config)
    if args.manifest is not None:
        config["manifest"] = args.manifest
    if args.output is not None:
        config["output"] = args.output
    for key in (
        "backend",
        "max_iterations",
        "timeout_seconds",
        "source_image",
        "raster_l1_weight",
        "raster_edge_weight",
    ):
        value = getattr(args, key, None)
        if value is not None:
            config[key] = value
    _require_config_paths(config, ("manifest", "output"), "refine")
    return {
        "manifest": Path(config["manifest"]),
        "output": Path(config["output"]),
        "backend": str(config.get("backend", "local_metric")),
        "max_iterations": int(config.get("max_iterations", 0)),
        "timeout_seconds": config.get("timeout_seconds"),
        "source_image": (
            Path(config["source_image"])
            if config.get("source_image") is not None
            else None
        ),
        "raster_l1_weight": float(config.get("raster_l1_weight", 1.0)),
        "raster_edge_weight": float(config.get("raster_edge_weight", 0.25)),
    }


def _resolved_refinement_gate_config(args: argparse.Namespace) -> dict[str, object]:
    config: dict[str, object] = {
        "max_objective_regression": 0.0,
        "require_improvement": True,
    }
    config.update(
        _load_refinement_gate_config(args.config)
        if args.config is not None
        else {}
    )
    if args.refined_manifest is not None:
        config["refined_manifest"] = args.refined_manifest
    if args.output is not None:
        config["output"] = args.output
    if args.markdown is not None:
        config["markdown"] = args.markdown
    if args.max_objective_regression is not None:
        config["max_objective_regression"] = args.max_objective_regression
    if args.require_improvement is not None:
        config["require_improvement"] = args.require_improvement
    _require_config_paths(
        config,
        ("refined_manifest", "output"),
        "refinement-gate",
    )
    for key in ("refined_manifest", "output", "markdown"):
        if config.get(key) is not None:
            config[key] = Path(str(config[key]))
    return config


def _resolved_status_config(args: argparse.Namespace) -> dict[str, object]:
    config = _load_status_config(args.config)
    if args.output is not None:
        config["output"] = args.output
    if args.markdown is not None:
        config["markdown"] = args.markdown
    if args.mlx_sam_model_path is not None:
        config["mlx_sam_model_path"] = args.mlx_sam_model_path
    for key in ("output", "markdown", "mlx_sam_model_path"):
        if config.get(key) is not None:
            config[key] = Path(str(config[key]))
    return config


def _resolved_primitive_check_config(args: argparse.Namespace) -> dict[str, object]:
    config = _load_primitive_check_config(args.config)
    if args.output is not None:
        config["output"] = args.output
    if args.output_dir is not None:
        config["output_dir"] = args.output_dir
    if args.markdown is not None:
        config["markdown"] = args.markdown
    if args.case is not None:
        config["case"] = args.case
    if args.filter is not None:
        config["filter"] = args.filter
    if args.refine is not None:
        config["refine"] = args.refine
    if args.refinement_iterations is not None:
        config["refinement_iterations"] = args.refinement_iterations
    _require_config_paths(config, ("output",), "primitive-check")
    for key in ("output", "output_dir", "markdown"):
        if config.get(key) is not None:
            config[key] = Path(str(config[key]))
    if isinstance(config.get("case"), str):
        config["case"] = [config["case"]]
    elif config.get("case") is None:
        config["case"] = []
    if config.get("refinement_iterations") is None:
        config["refinement_iterations"] = 1
    return config


def _resolved_harvest_config(args: argparse.Namespace) -> dict[str, object]:
    config = dict(HARVEST_DEFAULT_CONFIG)
    if args.config is not None:
        config.update(_load_harvest_config(args.config))
    if args.run_root is not None:
        config["run_root"] = args.run_root
    if args.output is not None:
        config["output"] = args.output
    if args.markdown is not None:
        config["markdown"] = args.markdown
    for key in (
        "max_run_diagnostics",
        "max_classifier_prior_error",
        "min_editability_score",
        "max_fragmentation_penalty",
        "max_raster_l1_error",
        "max_raster_edge_error",
        "max_anchor_quality_error",
        "require_applied_review",
    ):
        value = getattr(args, key, None)
        if value is not None:
            config[key] = value
    _require_config_paths(config, ("run_root", "output"), "harvest")
    config["run_root"] = Path(config["run_root"])
    config["output"] = Path(config["output"])
    if config.get("markdown") is not None:
        config["markdown"] = Path(str(config["markdown"]))
    return config


def _resolved_harvest_curated_config(args: argparse.Namespace) -> dict[str, object]:
    config = dict(HARVEST_CURATED_DEFAULT_CONFIG)
    if args.config is not None:
        config.update(_load_harvest_curated_config(args.config))
    if args.suite is not None:
        config["suite"] = args.suite
    if args.run_root is not None:
        config["run_root"] = args.run_root
    if args.output is not None:
        config["output"] = args.output
    if args.curated_report is not None:
        config["curated_report"] = args.curated_report
    if args.snapshot is not None:
        config["snapshot"] = args.snapshot
    if args.markdown is not None:
        config["markdown"] = args.markdown
    for key in (
        "max_run_diagnostics",
        "max_classifier_prior_error",
        "min_editability_score",
        "max_fragmentation_penalty",
        "max_raster_l1_error",
        "max_raster_edge_error",
        "max_anchor_quality_error",
        "require_applied_review",
    ):
        value = getattr(args, key, None)
        if value is not None:
            config[key] = value
    _require_config_paths(config, ("suite", "run_root", "output"), "harvest-curated")
    for key in ("suite", "run_root", "output", "curated_report", "snapshot", "markdown"):
        if config.get(key) is not None:
            config[key] = Path(str(config[key]))
    return config


def _resolved_review_config(args: argparse.Namespace) -> dict[str, Path]:
    config = _load_path_config(args.config, REVIEW_CONFIG_KEYS, "review")
    if args.pseudo_labels is not None:
        config["pseudo_labels"] = args.pseudo_labels
    if args.output is not None:
        config["output"] = args.output
    if args.markdown is not None:
        config["markdown"] = args.markdown
    if args.accept_applied_reviews is not None:
        config["accept_applied_reviews"] = args.accept_applied_reviews
    _require_config_paths(config, ("pseudo_labels", "output"), "review")
    return config


def _resolved_apply_review_config(args: argparse.Namespace) -> dict[str, Path]:
    config = _load_path_config(args.config, APPLY_REVIEW_CONFIG_KEYS, "apply-review")
    if args.review is not None:
        config["review"] = args.review
    if args.output is not None:
        config["output"] = args.output
    if args.markdown is not None:
        config["markdown"] = args.markdown
    _require_config_paths(config, ("review", "output"), "apply-review")
    return config


def _resolved_merge_labels_config(args: argparse.Namespace) -> dict[str, Path]:
    config = _load_path_config(args.config, MERGE_LABELS_CONFIG_KEYS, "merge-labels")
    if args.reviewed_labels is not None:
        config["reviewed_labels"] = args.reviewed_labels
    if args.output_dir is not None:
        config["output_dir"] = args.output_dir
    _require_config_paths(config, ("reviewed_labels", "output_dir"), "merge-labels")
    return config


def _resolved_curated_check_config(args: argparse.Namespace) -> dict[str, object]:
    config = _load_curated_check_config(args.config)
    if args.suite is not None:
        config["suite"] = args.suite
    if args.output is not None:
        config["output"] = args.output
    if args.output_dir is not None:
        config["output_dir"] = args.output_dir
    if args.run:
        config["run"] = True
    if args.snapshot is not None:
        config["snapshot"] = args.snapshot
    if args.baseline_snapshot is not None:
        config["baseline_snapshot"] = args.baseline_snapshot
    if args.markdown is not None:
        config["markdown"] = args.markdown
    _require_config_paths(config, ("suite", "output"), "curated-check")
    for key in (
        "suite",
        "output",
        "output_dir",
        "snapshot",
        "baseline_snapshot",
        "markdown",
    ):
        if config.get(key) is not None:
            config[key] = Path(str(config[key]))
    config["run"] = bool(config.get("run", False))
    return config


def _resolved_promotion_review_run_config(
    args: argparse.Namespace,
) -> dict[str, object]:
    config = _load_curated_check_config(args.config)
    if args.suite is not None:
        config["suite"] = args.suite
    if args.output is not None:
        config["output"] = args.output
    if args.output_dir is not None:
        config["output_dir"] = args.output_dir
    if args.snapshot is not None:
        config["snapshot"] = args.snapshot
    if args.baseline_snapshot is not None:
        config["baseline_snapshot"] = args.baseline_snapshot
    if args.markdown is not None:
        config["markdown"] = args.markdown
    _require_config_paths(config, ("suite", "output_dir"), "promotion-review-run")
    output_dir = Path(str(config["output_dir"]))
    config["suite"] = Path(str(config["suite"]))
    config["output_dir"] = output_dir
    config["output"] = Path(
        str(config.get("output") or output_dir / "curated-report.json")
    )
    config["markdown"] = Path(
        str(config.get("markdown") or output_dir / "curated-report.md")
    )
    config["snapshot"] = Path(
        str(config.get("snapshot") or output_dir / "curated-snapshot.json")
    )
    if config.get("baseline_snapshot") is not None:
        config["baseline_snapshot"] = Path(str(config["baseline_snapshot"]))
    config["run"] = True
    return config


def _promotion_review_run_harvest_config(
    config: dict[str, object],
) -> dict[str, object]:
    output_dir = Path(str(config["output_dir"]))
    return {
        "review_packet": str(output_dir / "review-packet.json"),
        "output": str(output_dir / "review-harvest.json"),
        "markdown": str(output_dir / "review-harvest.md"),
        "harvest_config": str(output_dir / "harvest-curated.json"),
        "decisions": {},
        "decision_overrides": {},
        "suite": str(config["suite"]),
        "run_root": str(output_dir),
        "harvest_output": str(output_dir / "harvested-pseudo-labels.json"),
        "curated_report": str(config["output"]),
        "snapshot": str(config["snapshot"]),
        "harvest_markdown": str(output_dir / "harvested-pseudo-labels.md"),
    }


def _promotion_review_run_decision_templates(
    review_packet: str | Path,
) -> dict[str, dict[str, str]]:
    packet = json.loads(Path(review_packet).read_text(encoding="utf-8"))
    if not isinstance(packet, dict):
        raise ValueError("promotion review packet must be a JSON object")
    templates_by_case: dict[str, dict[str, str]] = {}
    cases = packet.get("cases", [])
    if not isinstance(cases, list):
        return templates_by_case
    for case in cases:
        if not isinstance(case, dict):
            continue
        case_id = case.get("case_id")
        artifacts = case.get("artifacts", {})
        artifacts = artifacts if isinstance(artifacts, dict) else {}
        templates = artifacts.get("review_templates", {})
        templates = templates if isinstance(templates, dict) else {}
        if not isinstance(case_id, str) or not case_id:
            continue
        decision_templates = {
            decision: path
            for decision in PROMOTION_REVIEW_TERMINAL_DECISIONS
            if isinstance((path := templates.get(decision)), str) and path
        }
        if decision_templates:
            templates_by_case[case_id] = decision_templates
    return templates_by_case


def _promotion_review_run_next_commands(config_path: str | Path) -> list[str]:
    return [
        "PYTHONPATH=src python3 -m morphea.cli promotion-review-harvest "
        f"--config {shlex.quote(str(config_path))}"
    ]


def _write_json_file(path: str | Path, data: object) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(data, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _resolved_lucide_check_config(args: argparse.Namespace) -> dict[str, object]:
    config = _load_lucide_check_config(args.config)
    if args.suite is not None:
        config["suite"] = args.suite
    if args.output is not None:
        config["output"] = args.output
    if args.output_dir is not None:
        config["output_dir"] = args.output_dir
    if args.markdown is not None:
        config["markdown"] = args.markdown
    _require_config_paths(config, ("suite", "output"), "lucide-check")
    for key in ("suite", "output", "output_dir", "markdown", "classifier_model"):
        if config.get(key) is not None:
            config[key] = Path(str(config[key]))
    return config


def _load_vectorize_config(path: Path) -> dict[str, object]:
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("vectorize config must be a JSON object")
    supported = set(VECTORIZE_DEFAULT_CONFIG) | VECTORIZE_ARTIFACT_CONFIG_KEYS
    unknown = sorted(set(loaded) - supported)
    if unknown:
        msg = f"unsupported vectorize config keys: {', '.join(unknown)}"
        raise ValueError(msg)
    cutout_export = loaded.get("cutout_export")
    if cutout_export is not None and cutout_export not in CUTOUT_EXPORT_VALUES:
        raise ValueError("cutout_export must be overlay_stroke or negative_mask")
    config = dict(loaded)
    for key in ("input", "output", "manifest", "debug_svg", "run_dir"):
        if config.get(key) is not None:
            config[key] = Path(str(config[key]))
    return config


def _load_segment_config(path: Path) -> dict[str, object]:
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("segment config must be a JSON object")
    supported = set(SEGMENT_CONFIG_DEFAULTS) | SEGMENT_ARTIFACT_CONFIG_KEYS
    unknown = sorted(set(loaded) - supported)
    if unknown:
        msg = f"unsupported segment config keys: {', '.join(unknown)}"
        raise ValueError(msg)
    config = dict(loaded)
    for key in SEGMENT_ARTIFACT_CONFIG_KEYS:
        if config.get(key) is not None:
            config[key] = Path(str(config[key]))
    return config


def _load_profile_config(path: Path | None) -> dict[str, object]:
    if path is None:
        return {}
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("profile config must be a JSON object")
    unknown = sorted(set(loaded) - PROFILE_CONFIG_KEYS)
    if unknown:
        msg = f"unsupported profile config keys: {', '.join(unknown)}"
        raise ValueError(msg)
    config = dict(loaded)
    for key in ("input", "output", "classifier_model"):
        if key in config and config[key] is not None:
            config[key] = Path(str(config[key]))
    return config


def _load_profile_curated_config(path: Path | None) -> dict[str, object]:
    if path is None:
        return {}
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("profile-curated config must be a JSON object")
    unknown = sorted(set(loaded) - PROFILE_CURATED_CONFIG_KEYS)
    if unknown:
        msg = f"unsupported profile-curated config keys: {', '.join(unknown)}"
        raise ValueError(msg)
    config = dict(loaded)
    for key in ("suite", "output", "markdown"):
        if key in config and config[key] is not None:
            config[key] = Path(str(config[key]))
    return config


def _load_report_config(path: Path | None) -> dict[str, object]:
    if path is None:
        return {}
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("report config must be a JSON object")
    unknown = sorted(set(loaded) - REPORT_CONFIG_KEYS)
    if unknown:
        msg = f"unsupported report config keys: {', '.join(unknown)}"
        raise ValueError(msg)
    config = dict(loaded)
    for key in ("manifest", "output", "config"):
        if key in config and config[key] is not None:
            config[key] = Path(str(config[key]))
    return config


def _load_generate_config(path: Path | None) -> dict[str, object]:
    if path is None:
        return {}
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("generate config must be a JSON object")
    unknown = sorted(set(loaded) - GENERATE_CONFIG_KEYS)
    if unknown:
        msg = f"unsupported generate config keys: {', '.join(unknown)}"
        raise ValueError(msg)
    config = dict(loaded)
    if config.get("output_dir") is not None:
        config["output_dir"] = Path(str(config["output_dir"]))
    return config


def _load_train_mlx_config(path: Path | None) -> dict[str, object]:
    if path is None:
        return {}
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("train-mlx config must be a JSON object")
    unknown = sorted(set(loaded) - TRAIN_MLX_CONFIG_KEYS)
    if unknown:
        msg = f"unsupported train-mlx config keys: {', '.join(unknown)}"
        raise ValueError(msg)
    config = dict(loaded)
    for key in ("dataset", "output"):
        if key in config and config[key] is not None:
            config[key] = Path(str(config[key]))
    return config


def _load_curated_check_config(path: Path | None) -> dict[str, object]:
    if path is None:
        return {}
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("curated-check config must be a JSON object")
    unknown = sorted(set(loaded) - CURATED_CHECK_CONFIG_KEYS)
    if unknown:
        msg = f"unsupported curated-check config keys: {', '.join(unknown)}"
        raise ValueError(msg)
    config = dict(loaded)
    for key in (
        "suite",
        "output",
        "output_dir",
        "snapshot",
        "baseline_snapshot",
        "markdown",
    ):
        if key in config and config[key] is not None:
            config[key] = Path(str(config[key]))
    if "run" in config and not isinstance(config["run"], bool):
        raise ValueError("curated-check run must be a boolean")
    return config


def _load_lucide_check_config(path: Path | None) -> dict[str, object]:
    if path is None:
        return {}
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("lucide-check config must be a JSON object")
    unknown = sorted(set(loaded) - LUCIDE_CHECK_CONFIG_KEYS)
    if unknown:
        msg = f"unsupported lucide-check config keys: {', '.join(unknown)}"
        raise ValueError(msg)
    config = dict(loaded)
    for key in ("suite", "output", "output_dir", "markdown", "classifier_model"):
        if key in config and config[key] is not None:
            config[key] = Path(str(config[key]))
    return config


def _load_eval_classifier_config(path: Path | None) -> dict[str, object]:
    if path is None:
        return {}
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("eval-classifier config must be a JSON object")
    unknown = sorted(set(loaded) - EVAL_CLASSIFIER_CONFIG_KEYS)
    if unknown:
        msg = f"unsupported eval-classifier config keys: {', '.join(unknown)}"
        raise ValueError(msg)
    config = dict(loaded)
    for key in ("model", "dataset", "output", "markdown"):
        if key in config and config[key] is not None:
            config[key] = Path(str(config[key]))
    if "splits" in config:
        config["splits"] = _normalized_splits(config["splits"])
    return config


def _normalized_splits(value: object) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError("eval-classifier splits must be a non-empty array")
    splits = []
    for split in value:
        if not isinstance(split, str) or not split:
            raise ValueError("eval-classifier splits must contain strings")
        splits.append(split)
    return splits


def _load_refine_config(path: Path | None) -> dict[str, object]:
    if path is None:
        return {}
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("refine config must be a JSON object")
    unknown = sorted(set(loaded) - REFINE_CONFIG_KEYS)
    if unknown:
        msg = f"unsupported refine config keys: {', '.join(unknown)}"
        raise ValueError(msg)
    config = dict(loaded)
    for key in ("manifest", "output", "source_image"):
        if key in config and config[key] is not None:
            config[key] = Path(str(config[key]))
    return config


def _load_refinement_gate_config(path: Path) -> dict[str, object]:
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("refinement-gate config must be a JSON object")
    unknown = sorted(set(loaded) - REFINEMENT_GATE_CONFIG_KEYS)
    if unknown:
        msg = f"unsupported refinement-gate config keys: {', '.join(unknown)}"
        raise ValueError(msg)
    config = dict(loaded)
    for key in ("refined_manifest", "output", "markdown"):
        if key in config and config[key] is not None:
            config[key] = Path(str(config[key]))
    return config


def _load_status_config(path: Path | None) -> dict[str, object]:
    if path is None:
        return {}
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("status config must be a JSON object")
    unknown = sorted(set(loaded) - STATUS_CONFIG_KEYS)
    if unknown:
        msg = f"unsupported status config keys: {', '.join(unknown)}"
        raise ValueError(msg)
    config = dict(loaded)
    for key in ("output", "markdown", "mlx_sam_model_path"):
        if key in config and config[key] is not None:
            config[key] = Path(str(config[key]))
    return config


def _load_primitive_check_config(path: Path | None) -> dict[str, object]:
    if path is None:
        return {}
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("primitive-check config must be a JSON object")
    unknown = sorted(set(loaded) - PRIMITIVE_CHECK_CONFIG_KEYS)
    if unknown:
        msg = f"unsupported primitive-check config keys: {', '.join(unknown)}"
        raise ValueError(msg)
    config = dict(loaded)
    for key in ("output", "output_dir", "markdown"):
        if key in config and config[key] is not None:
            config[key] = Path(str(config[key]))
    if "case" in config and isinstance(config["case"], str):
        config["case"] = [config["case"]]
    return config


def _load_harvest_config(path: Path) -> dict[str, object]:
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("harvest config must be a JSON object")
    unknown = sorted(set(loaded) - set(HARVEST_DEFAULT_CONFIG))
    if unknown:
        msg = f"unsupported harvest config keys: {', '.join(unknown)}"
        raise ValueError(msg)
    config = dict(loaded)
    for key in ("run_root", "output", "markdown"):
        if key in config and config[key] is not None:
            config[key] = Path(str(config[key]))
    return config


def _load_harvest_curated_config(path: Path) -> dict[str, object]:
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("harvest-curated config must be a JSON object")
    unknown = sorted(set(loaded) - set(HARVEST_CURATED_DEFAULT_CONFIG))
    if unknown:
        msg = f"unsupported harvest-curated config keys: {', '.join(unknown)}"
        raise ValueError(msg)
    config = dict(loaded)
    for key in ("suite", "run_root", "output", "curated_report", "snapshot", "markdown"):
        if key in config and config[key] is not None:
            config[key] = Path(str(config[key]))
    return config


def _load_promotion_review_harvest_config(
    path: Path | None,
) -> dict[str, object]:
    if path is None:
        return {}
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("promotion-review-harvest config must be a JSON object")
    unknown = sorted(set(loaded) - PROMOTION_REVIEW_HARVEST_CONFIG_KEYS)
    if unknown:
        msg = (
            "unsupported promotion-review-harvest config keys: "
            + ", ".join(unknown)
        )
        raise ValueError(msg)
    config = dict(loaded)
    for key in (
        "review_packet",
        "output",
        "markdown",
        "harvest_config",
        "suite",
        "run_root",
        "harvest_output",
        "curated_report",
        "snapshot",
        "harvest_markdown",
        "decision_plan",
    ):
        if config.get(key) is not None:
            config[key] = Path(str(config[key]))
    if "decisions" in config:
        config["decisions"] = _promotion_review_decisions_from_config(
            config["decisions"],
        )
    if "decision_choices" in config:
        config["decision_choices"] = _promotion_review_decision_choices_from_config(
            config["decision_choices"],
        )
    if "decision_templates" in config:
        config["decision_templates"] = (
            _promotion_review_decision_templates_from_config(
                config["decision_templates"],
            )
        )
    if "decision_overrides" in config:
        config["decision_overrides"] = (
            _promotion_review_decision_overrides_from_config(
                config["decision_overrides"],
            )
        )
    return config


def _load_promotion_review_decision_plan(
    path: object,
) -> dict[str, object]:
    if path is None:
        return {}
    plan_path = Path(str(path))
    loaded = json.loads(plan_path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("promotion-review-harvest decision_plan must be a JSON object")
    allowed = {"schema_version", "decision_choices", "decision_overrides"}
    unknown = sorted(set(loaded) - allowed)
    if unknown:
        raise ValueError(
            "promotion-review-harvest decision_plan unsupported fields: "
            + ", ".join(unknown)
        )
    plan: dict[str, object] = {}
    if "decision_choices" in loaded:
        plan["decision_choices"] = _promotion_review_decision_choices_from_config(
            loaded["decision_choices"],
        )
    if "decision_overrides" in loaded:
        plan["decision_overrides"] = _promotion_review_decision_overrides_from_config(
            loaded["decision_overrides"],
        )
    return plan


def _promotion_review_decisions_from_config(value: object) -> dict[str, Path]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("promotion-review-harvest decisions must be an object")
    decisions: dict[str, Path] = {}
    for case_id, path in value.items():
        if not isinstance(case_id, str) or not case_id:
            raise ValueError(
                "promotion-review-harvest decisions must use non-empty case ids"
            )
        if not isinstance(path, str) or not path:
            raise ValueError(
                "promotion-review-harvest decisions must map case ids to paths"
            )
        decisions[case_id] = Path(path)
    return decisions


def _promotion_review_decision_choices_from_config(value: object) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("promotion-review-harvest decision_choices must be an object")
    choices: dict[str, str] = {}
    for case_id, decision in value.items():
        if not isinstance(case_id, str) or not case_id:
            raise ValueError(
                "promotion-review-harvest decision_choices must use non-empty case ids"
            )
        if (
            not isinstance(decision, str)
            or decision not in PROMOTION_REVIEW_TERMINAL_DECISIONS
        ):
            allowed = ", ".join(PROMOTION_REVIEW_TERMINAL_DECISIONS)
            raise ValueError(
                "promotion-review-harvest decision_choices must use one of: "
                f"{allowed}"
            )
        choices[case_id] = decision
    return choices


def _promotion_review_decision_templates_from_config(
    value: object,
) -> dict[str, dict[str, str]]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("promotion-review-harvest decision_templates must be an object")
    templates_by_case: dict[str, dict[str, str]] = {}
    for case_id, templates in value.items():
        if not isinstance(case_id, str) or not case_id:
            raise ValueError(
                "promotion-review-harvest decision_templates must use non-empty case ids"
            )
        if not isinstance(templates, dict):
            raise ValueError(
                "promotion-review-harvest decision_templates must map case ids to objects"
            )
        terminal_templates: dict[str, str] = {}
        for decision in PROMOTION_REVIEW_TERMINAL_DECISIONS:
            path = templates.get(decision)
            if path is None:
                continue
            if not isinstance(path, str) or not path:
                raise ValueError(
                    "promotion-review-harvest decision_templates must map decisions to paths"
                )
            terminal_templates[decision] = path
        if terminal_templates:
            templates_by_case[case_id] = terminal_templates
    return templates_by_case


def _promotion_review_decision_overrides_from_config(
    value: object,
) -> dict[str, dict[str, object]]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("promotion-review-harvest decision_overrides must be an object")
    overrides_by_case: dict[str, dict[str, object]] = {}
    allowed = {
        "reviewer",
        "reason",
        "correction_notes",
        "corrected_artifacts",
        "reviewed_region_ids",
    }
    for case_id, overrides in value.items():
        if not isinstance(case_id, str) or not case_id:
            raise ValueError(
                "promotion-review-harvest decision_overrides must use non-empty case ids"
            )
        if not isinstance(overrides, dict):
            raise ValueError(
                "promotion-review-harvest decision_overrides must map case ids to objects"
            )
        unknown = sorted(set(overrides) - allowed)
        if unknown:
            raise ValueError(
                "promotion-review-harvest decision_overrides unsupported fields: "
                + ", ".join(unknown)
            )
        normalized: dict[str, object] = {}
        for key in ("reviewer", "reason", "correction_notes"):
            value_for_key = overrides.get(key)
            if value_for_key is None:
                continue
            if not isinstance(value_for_key, str) or not value_for_key.strip():
                raise ValueError(
                    "promotion-review-harvest decision_overrides "
                    f"{key} must be a non-empty string"
                )
            normalized[key] = value_for_key
        corrected = overrides.get("corrected_artifacts")
        if corrected is not None:
            if (
                not isinstance(corrected, list)
                or not corrected
                or not all(
                    isinstance(item, str) and bool(item.strip())
                    for item in corrected
                )
            ):
                raise ValueError(
                    "promotion-review-harvest decision_overrides "
                    "corrected_artifacts must be a non-empty string array"
                )
            normalized["corrected_artifacts"] = list(corrected)
        reviewed_regions = overrides.get("reviewed_region_ids")
        if reviewed_regions is not None:
            if (
                not isinstance(reviewed_regions, list)
                or not reviewed_regions
                or not all(
                    isinstance(item, str) and bool(item.strip())
                    for item in reviewed_regions
                )
            ):
                raise ValueError(
                    "promotion-review-harvest decision_overrides "
                    "reviewed_region_ids must be a non-empty string array"
                )
            normalized["reviewed_region_ids"] = list(reviewed_regions)
        if normalized:
            overrides_by_case[case_id] = normalized
    return overrides_by_case


def _promotion_review_decisions_from_choices(
    config: dict[str, object],
    choices: dict[str, str],
) -> dict[str, Path]:
    if not choices:
        return {}
    templates = _promotion_review_harvest_template_map(config)
    decisions: dict[str, Path] = {}
    for case_id, decision in choices.items():
        case_templates = templates.get(case_id)
        if not case_templates:
            raise ValueError(
                "promotion review decision choice has no templates for case: "
                f"{case_id}"
            )
        template_path = case_templates.get(decision)
        if not template_path:
            raise ValueError(
                "promotion review decision choice has no "
                f"{decision} template for case: {case_id}"
            )
        decisions[case_id] = Path(template_path)
    return decisions


def _promotion_review_harvest_template_map(
    config: dict[str, object],
) -> dict[str, dict[str, str]]:
    templates: dict[str, dict[str, str]] = {}
    packet_path = config.get("review_packet")
    if packet_path is not None:
        templates.update(_promotion_review_run_decision_templates(packet_path))
    configured = config.get("decision_templates")
    if isinstance(configured, dict):
        for case_id, case_templates in configured.items():
            if not isinstance(case_id, str) or not isinstance(case_templates, dict):
                continue
            terminal_templates = {
                decision: path
                for decision in PROMOTION_REVIEW_TERMINAL_DECISIONS
                if isinstance((path := case_templates.get(decision)), str) and path
            }
            if terminal_templates:
                templates[case_id] = terminal_templates
    return templates


def _load_training_gate_config(path: Path) -> dict[str, object]:
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("training-gate config must be a JSON object")
    unknown = sorted(set(loaded) - TRAINING_GATE_CONFIG_KEYS)
    if unknown:
        msg = f"unsupported training-gate config keys: {', '.join(unknown)}"
        raise ValueError(msg)
    config = dict(loaded)
    for key in ("comparison", "output", "markdown"):
        if key in config and config[key] is not None:
            config[key] = Path(str(config[key]))
    return config


def _load_self_learn_config(path: Path) -> dict[str, object]:
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("self-learn config must be a JSON object")
    unknown = sorted(set(loaded) - SELF_LEARN_CONFIG_KEYS)
    if unknown:
        msg = f"unsupported self-learn config keys: {', '.join(unknown)}"
        raise ValueError(msg)
    config = dict(loaded)
    for key in (
        "base_dataset",
        "reviewed_labels",
        "validation_dataset",
        "curated_suite",
        "curated_output_dir",
        "curated_report",
        "curated_snapshot",
        "lucide_suite",
        "lucide_output_dir",
        "lucide_report",
        "suite_family_baseline",
        "suite_family_baseline_output",
        "suite_family_baseline_changelog",
        "output_dir",
        "markdown",
    ):
        if key in config and config[key] is not None:
            config[key] = Path(str(config[key]))
    return config


def _segmenter_from_config(
    config: dict[str, object],
) -> FlatColorSegmenter | MlxSamSegmenter:
    segmenter = config.get("segmenter")
    if segmenter == "flat_color":
        return FlatColorSegmenter(
            background=(
                config.get("background")
                if config.get("background") is not None
                else None
            ),
            min_area=int(config["min_area"]),
            color_tolerance=float(config["color_tolerance"]),
            max_size=(
                int(config["max_size"])
                if config.get("max_size") is not None
                else None
            ),
            max_colors=(
                int(config["max_colors"])
                if config.get("max_colors") is not None
                else None
            ),
            max_component_area=(
                int(config["max_component_area"])
                if config.get("max_component_area") is not None
                else None
            ),
            split_components=bool(config["split_components"]),
        )
    if segmenter == "mlx_sam":
        return MlxSamSegmenter(
            model_path=(
                str(config["mlx_model_path"])
                if config.get("mlx_model_path") is not None
                else None
            ),
            score_threshold=float(config["mlx_score_threshold"]),
            max_masks=(
                int(config["mlx_max_masks"])
                if config.get("mlx_max_masks") is not None
                else None
            ),
            timeout_seconds=(
                float(config["mlx_timeout_seconds"])
                if config.get("mlx_timeout_seconds") is not None
                else None
            ),
            max_component_area=(
                int(config["max_component_area"])
                if config.get("max_component_area") is not None
                else None
            ),
            prompt_strategy=str(config["mlx_prompt_strategy"]),
            prompt_min_area=int(config["min_area"]),
            prompt_color_tolerance=float(config["color_tolerance"]),
            prompt_max_size=(
                int(config["max_size"])
                if config.get("max_size") is not None
                else None
            ),
            prompt_max_colors=(
                int(config["max_colors"])
                if config.get("max_colors") is not None
                else None
            ),
        )
    raise ValueError(f"unsupported segmenter: {segmenter}")


def _load_path_config(
    path: Path | None,
    allowed_keys: set[str],
    name: str,
) -> dict[str, object]:
    if path is None:
        return {}
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"{name} config must be a JSON object")
    unknown = sorted(set(loaded) - allowed_keys)
    if unknown:
        msg = f"unsupported {name} config keys: {', '.join(unknown)}"
        raise ValueError(msg)
    return {
        key: value if isinstance(value, bool) else Path(str(value))
        for key, value in loaded.items()
        if value is not None
    }


def _require_config_paths(
    config: dict[str, object],
    required: tuple[str, ...],
    name: str,
) -> None:
    missing = [key for key in required if config.get(key) is None]
    if missing:
        msg = f"{name} requires: {', '.join(missing)}"
        raise ValueError(msg)


if __name__ == "__main__":
    main()
