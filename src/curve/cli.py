"""Minimal CLI placeholder for the Curve research prototype."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from curve.classifier import evaluate_classifier_model, train_centroid_classifier
from curve.comparison import (
    compare_git_snapshots,
    compare_segment_manifests,
    compare_snapshots,
    generate_git_curated_snapshot,
)
from curve.curated import check_curated_suite
from curve.dataset import generate_synthetic_dataset
from curve.eval import write_eval_summary
from curve.images import scene_from_flat_color_image
from curve.mlx_classifier import (
    MlxClassifierTrainingConfig,
    train_mlx_transformer_classifier,
)
from curve.profiling import profile_vectorize
from curve.runs import (
    create_run_dir,
    write_html_report,
    write_markdown_report,
    write_vectorize_run,
)
from curve.segmenters import (
    FlatColorSegmenter,
    MlxSamSegmenter,
    gate_segment_proposals,
    proposals_to_manifest,
    render_segment_proposal_markdown,
    segment_proposal_groups,
    segment_proposal_summary,
    segmenter_backend_status,
)
from curve.scene import SvgStyle
from curve.self_learning import (
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
from curve.refinement import (
    RefinementConfig,
    gate_refinement_result,
    refine_manifest,
)
from curve.status import collect_runtime_status
from curve.sweeps import run_sweep


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
    "stroke_circle_min_inner_ratio": 0.45,
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
TRAIN_CONFIG_KEYS = {"dataset", "output"}
EVAL_CONFIG_KEYS = {"run_root", "output", "markdown"}
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
    "geometry_gate": False,
    "max_anchor_quality_error": 1.0,
    "require_reserved_anchor": False,
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
    "output_dir",
    "markdown",
    "min_train_examples_delta",
    "min_best_accuracy_delta",
    "max_worst_accuracy_drop",
    "allow_unchanged",
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
REVIEW_CONFIG_KEYS = {"pseudo_labels", "output", "markdown"}
APPLY_REVIEW_CONFIG_KEYS = {"review", "output", "markdown"}
MERGE_LABELS_CONFIG_KEYS = {"reviewed_labels", "output_dir"}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="curve",
        description="Semantic-first raster-to-SVG research prototype",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    vectorize = subcommands.add_parser(
        "vectorize",
        help="Vectorize a flat-color raster image into editable SVG primitives.",
    )
    vectorize.add_argument("input", type=Path, help="Input PNG/JPEG/WebP image.")
    vectorize.add_argument(
        "-o",
        "--output",
        type=Path,
        required=True,
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
    profile.add_argument("input", type=Path)
    profile.add_argument("-o", "--output", type=Path, required=True)
    profile.add_argument("--repeats", type=int, default=1)
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

    generate = subcommands.add_parser(
        "generate",
        help="Generate synthetic flat-color primitive training samples.",
    )
    generate.add_argument("-o", "--output-dir", type=Path, required=True)
    generate.add_argument("--count", type=int, default=1)
    generate.add_argument("--seed", type=int, default=1)
    generate.add_argument("--width", type=int, default=96)
    generate.add_argument("--height", type=int, default=96)
    generate.add_argument("--difficulty", default="basic")
    generate.add_argument("--val-count", type=int, default=1)
    generate.add_argument("--test-count", type=int, default=1)

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
    segment.add_argument("input", type=Path)
    segment.add_argument("-o", "--output", type=Path, required=True)
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
    report.add_argument("manifest", type=Path)
    report.add_argument("-o", "--output", type=Path, required=True)
    report.add_argument("--config", type=Path)
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
    harvest_curated.add_argument("--config", type=Path)

    review = subcommands.add_parser(
        "review",
        help="Create a human-editable review queue from harvested pseudo-labels.",
    )
    review.add_argument("pseudo_labels", type=Path, nargs="?")
    review.add_argument("-o", "--output", type=Path)
    review.add_argument("--markdown", type=Path)
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
    self_learn.add_argument("-o", "--output-dir", type=Path)
    self_learn.add_argument("--markdown", type=Path)
    self_learn.add_argument("--min-train-examples-delta", type=int)
    self_learn.add_argument("--min-best-accuracy-delta", type=float)
    self_learn.add_argument("--max-worst-accuracy-drop", type=float)
    self_learn.add_argument("--allow-unchanged", action="store_true")
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
    compare_snapshots_parser.add_argument("before", type=Path)
    compare_snapshots_parser.add_argument("after", type=Path)
    compare_snapshots_parser.add_argument("-o", "--output", type=Path, required=True)
    compare_snapshots_parser.add_argument("--markdown", type=Path)

    compare_segments_parser = subcommands.add_parser(
        "compare-segments",
        help="Compare two segment proposal manifests.",
    )
    compare_segments_parser.add_argument("before", type=Path)
    compare_segments_parser.add_argument("after", type=Path)
    compare_segments_parser.add_argument("-o", "--output", type=Path, required=True)
    compare_segments_parser.add_argument("--markdown", type=Path)

    compare_git_snapshots_parser = subcommands.add_parser(
        "compare-git-snapshots",
        help="Compare the same saved snapshot file across two git refs.",
    )
    compare_git_snapshots_parser.add_argument("before_ref")
    compare_git_snapshots_parser.add_argument("after_ref")
    compare_git_snapshots_parser.add_argument("--path", type=Path, required=True)
    compare_git_snapshots_parser.add_argument(
        "-o",
        "--output",
        type=Path,
        required=True,
    )
    compare_git_snapshots_parser.add_argument("--markdown", type=Path)
    compare_git_snapshots_parser.add_argument("--repo", type=Path, default=Path("."))

    snapshot_git_ref = subcommands.add_parser(
        "snapshot-git-ref",
        help="Generate a curated snapshot for a git ref in an isolated worktree.",
    )
    snapshot_git_ref.add_argument("ref")
    snapshot_git_ref.add_argument("--suite", type=Path, required=True)
    snapshot_git_ref.add_argument("-o", "--output", type=Path, required=True)
    snapshot_git_ref.add_argument("--report", type=Path)
    snapshot_git_ref.add_argument("--output-dir", type=Path)
    snapshot_git_ref.add_argument("--repo", type=Path, default=Path("."))
    snapshot_git_ref.add_argument("--timeout-seconds", type=float, default=120.0)
    snapshot_git_ref.add_argument(
        "--no-run",
        dest="run",
        action="store_false",
        default=True,
    )

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
    status.add_argument("-o", "--output", type=Path, required=True)
    status.add_argument("--markdown", type=Path)
    status.add_argument("--mlx-sam-model-path", type=Path)

    curated_check = subcommands.add_parser(
        "curated-check",
        help="Validate a curated real-image suite and optionally run it.",
    )
    curated_check.add_argument("suite", type=Path)
    curated_check.add_argument("-o", "--output", type=Path, required=True)
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
    curated_check.add_argument("--markdown", type=Path)

    sweep = subcommands.add_parser(
        "sweep",
        help="Run a config-driven vectorize sweep.",
    )
    sweep.add_argument("config", type=Path)
    sweep.add_argument("-o", "--output-dir", type=Path, required=True)
    sweep.add_argument("--markdown", type=Path)

    args = parser.parse_args(argv)
    if args.command == "vectorize":
        vectorize_config = _resolved_vectorize_config(args)
        cutout_export = _resolved_cutout_export(args)
        config = {
            "command": "vectorize",
            "input": str(args.input),
            "output": str(args.output),
            "debug_svg": str(args.debug_svg) if args.debug_svg else None,
            "config": str(args.config) if args.config else None,
            "cutout_export": cutout_export,
            **vectorize_config,
        }
        scene = scene_from_flat_color_image(
            args.input,
            **vectorize_config,
        )
        if args.run_dir is not None:
            run_dir = create_run_dir(args.run_dir)
            run = write_vectorize_run(
                run_dir=run_dir,
                input_path=args.input,
                scene=scene,
                config=config,
            )
            print(f"wrote run {run.run_dir} with {len(scene.anchors)} anchors")
            return

        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            scene.to_svg(SvgStyle(cutout_strategy=cutout_export)),
            encoding="utf-8",
        )
        if args.debug_svg is not None:
            args.debug_svg.parent.mkdir(parents=True, exist_ok=True)
            args.debug_svg.write_text(scene.to_debug_svg(), encoding="utf-8")
        if not args.no_manifest:
            manifest_path = args.manifest or args.output.with_suffix(".json")
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            manifest_path.write_text(
                json.dumps(scene.to_manifest(), indent=2, sort_keys=True),
                encoding="utf-8",
            )
        print(f"wrote {args.output} with {len(scene.anchors)} anchors")
        return

    if args.command == "profile":
        profile_config = _resolved_vectorize_config(args)
        report = profile_vectorize(
            args.input,
            output=args.output,
            repeats=args.repeats,
            config=profile_config,
        )
        print(
            "profiled "
            f"{report['repeat_count']} runs; "
            f"mean={report['summary']['mean_elapsed_seconds']:.6f}s"
        )
        return

    if args.command == "generate":
        generate_synthetic_dataset(
            output_dir=args.output_dir,
            count=args.count,
            seed=args.seed,
            width=args.width,
            height=args.height,
            difficulty=args.difficulty,
            val_count=args.val_count,
            test_count=args.test_count,
        )
        print(f"wrote {args.count} synthetic samples to {args.output_dir}")
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
        segment_config = _resolved_segment_config(args)
        segmenter = _segmenter_from_config(segment_config)
        proposals = segmenter.propose(args.input)
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
            "input": str(args.input),
            "config": segment_config,
            "backend": segmenter_backend_status(segmenter),
            "proposal_count": len(proposals),
            "summary": segment_proposal_summary(proposals, proposal_groups),
            "proposal_groups": proposal_groups,
            "proposals": proposals_to_manifest(proposals),
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(manifest, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        if args.markdown is not None:
            args.markdown.parent.mkdir(parents=True, exist_ok=True)
            args.markdown.write_text(
                render_segment_proposal_markdown(manifest),
                encoding="utf-8",
            )
        print(f"wrote {len(proposals)} segment proposals")
        return

    if args.command == "report":
        report_format = args.format or (
            "html" if args.output.suffix.lower() == ".html" else "markdown"
        )
        if report_format == "html":
            write_html_report(
                manifest=args.manifest,
                output=args.output,
                config=args.config,
            )
        else:
            write_markdown_report(
                manifest=args.manifest,
                output=args.output,
                config=args.config,
            )
        print(f"wrote report {args.output}")
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
            output_dir=cycle_config["output_dir"],
            markdown=cycle_config.get("markdown"),
            min_train_examples_delta=int(cycle_config["min_train_examples_delta"]),
            min_best_accuracy_delta=float(cycle_config["min_best_accuracy_delta"]),
            max_worst_accuracy_drop=float(cycle_config["max_worst_accuracy_drop"]),
            allow_unchanged=bool(cycle_config["allow_unchanged"]),
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
        result = compare_snapshots(
            args.before,
            args.after,
            output=args.output,
            markdown=args.markdown,
        )
        print(f"compared {result['item_count']} snapshot items")
        return

    if args.command == "compare-segments":
        result = compare_segment_manifests(
            args.before,
            args.after,
            output=args.output,
            markdown=args.markdown,
        )
        print(f"compared {result['shared_proposal_count']} segment proposals")
        return

    if args.command == "compare-git-snapshots":
        result = compare_git_snapshots(
            args.before_ref,
            args.after_ref,
            snapshot_path=args.path,
            output=args.output,
            markdown=args.markdown,
            repo=args.repo,
        )
        print(f"compared {result['item_count']} git snapshot items")
        return

    if args.command == "snapshot-git-ref":
        result = generate_git_curated_snapshot(
            args.ref,
            suite=args.suite,
            output=args.output,
            report=args.report,
            output_dir=args.output_dir,
            repo=args.repo,
            run=args.run,
            timeout_seconds=args.timeout_seconds,
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
        result = collect_runtime_status(
            output=args.output,
            markdown=args.markdown,
            mlx_sam_model_path=args.mlx_sam_model_path,
        )
        print(f"wrote runtime status with {len(result['blocked_backends'])} blockers")
        return

    if args.command == "curated-check":
        result = check_curated_suite(
            args.suite,
            output=args.output,
            output_dir=args.output_dir,
            run=args.run,
            snapshot=args.snapshot,
            markdown=args.markdown,
        )
        print(f"checked {result['case_count']} curated cases")
        return

    if args.command == "sweep":
        result = run_sweep(
            args.config,
            output_dir=args.output_dir,
            markdown=args.markdown,
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
        config.update(loaded)

    for key in SEGMENT_CONFIG_DEFAULTS:
        value = getattr(args, key, None)
        if value is not None:
            config[key] = value
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
    if args.output_dir is not None:
        config["output_dir"] = args.output_dir
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


def _load_vectorize_config(path: Path) -> dict[str, object]:
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("vectorize config must be a JSON object")
    supported = set(VECTORIZE_DEFAULT_CONFIG) | {"cutout_export"}
    unknown = sorted(set(loaded) - supported)
    if unknown:
        msg = f"unsupported vectorize config keys: {', '.join(unknown)}"
        raise ValueError(msg)
    cutout_export = loaded.get("cutout_export")
    if cutout_export is not None and cutout_export not in CUTOUT_EXPORT_VALUES:
        raise ValueError("cutout_export must be overlay_stroke or negative_mask")
    return loaded


def _load_segment_config(path: Path) -> dict[str, object]:
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("segment config must be a JSON object")
    unknown = sorted(set(loaded) - set(SEGMENT_CONFIG_DEFAULTS))
    if unknown:
        msg = f"unsupported segment config keys: {', '.join(unknown)}"
        raise ValueError(msg)
    return loaded


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
        )
    raise ValueError(f"unsupported segmenter: {segmenter}")


def _load_path_config(
    path: Path | None,
    allowed_keys: set[str],
    name: str,
) -> dict[str, Path]:
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
        key: Path(str(value))
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
