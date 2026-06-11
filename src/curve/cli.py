"""Minimal CLI placeholder for the Curve research prototype."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from curve.classifier import train_centroid_classifier
from curve.comparison import compare_snapshots
from curve.curated import check_curated_suite
from curve.dataset import generate_synthetic_dataset
from curve.eval import write_eval_summary
from curve.images import scene_from_flat_color_image
from curve.runs import create_run_dir, write_markdown_report, write_vectorize_run
from curve.self_learning import (
    apply_review_file,
    compare_retraining,
    create_review_file,
    harvest_pseudo_labels,
    merge_reviewed_pseudo_label_dataset,
)
from curve.refinement import RefinementConfig, refine_manifest
from curve.sweeps import run_sweep


VECTORIZE_DEFAULT_CONFIG = {
    "min_area": 8,
    "color_tolerance": 0.0,
    "max_size": None,
    "max_colors": None,
    "max_component_area": None,
    "timeout_seconds": None,
    "classifier_model": None,
}
TRAIN_CONFIG_KEYS = {"dataset", "output"}
COMPARE_TRAINING_CONFIG_KEYS = {
    "base_dataset",
    "pseudo_dataset",
    "validation_dataset",
    "output",
}


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
    eval_parser.add_argument("run_root", type=Path)
    eval_parser.add_argument("-o", "--output", type=Path, required=True)
    eval_parser.add_argument("--markdown", type=Path)

    report = subcommands.add_parser(
        "report",
        help="Render a Markdown report from an existing vectorize manifest.",
    )
    report.add_argument("manifest", type=Path)
    report.add_argument("-o", "--output", type=Path, required=True)
    report.add_argument("--config", type=Path)

    train = subcommands.add_parser(
        "train",
        help="Train a primitive classifier from a generated dataset.json.",
    )
    train.add_argument("dataset", type=Path, nargs="?")
    train.add_argument("-o", "--output", type=Path)
    train.add_argument("--config", type=Path)

    harvest = subcommands.add_parser(
        "harvest",
        help="Collect high-confidence pseudo-labels from vectorize runs.",
    )
    harvest.add_argument("run_root", type=Path)
    harvest.add_argument("-o", "--output", type=Path, required=True)
    harvest.add_argument("--max-run-diagnostics", type=int, default=0)
    harvest.add_argument("--max-classifier-prior-error", type=float, default=0.0)
    harvest.add_argument("--min-editability-score", type=float, default=0.0)
    harvest.add_argument("--max-fragmentation-penalty", type=float, default=1.0)

    review = subcommands.add_parser(
        "review",
        help="Create a human-editable review queue from harvested pseudo-labels.",
    )
    review.add_argument("pseudo_labels", type=Path)
    review.add_argument("-o", "--output", type=Path, required=True)

    apply_review = subcommands.add_parser(
        "apply-review",
        help="Apply accept/reject decisions from a review file.",
    )
    apply_review.add_argument("review", type=Path)
    apply_review.add_argument("-o", "--output", type=Path, required=True)

    merge_labels = subcommands.add_parser(
        "merge-labels",
        help="Convert accepted reviewed pseudo-labels into a trainable dataset.",
    )
    merge_labels.add_argument("reviewed_labels", type=Path)
    merge_labels.add_argument("-o", "--output-dir", type=Path, required=True)

    compare_training = subcommands.add_parser(
        "compare-training",
        help="Compare baseline classifier training against pseudo-label augmentation.",
    )
    compare_training.add_argument("base_dataset", type=Path, nargs="?")
    compare_training.add_argument("--pseudo-dataset", type=Path)
    compare_training.add_argument("--validation-dataset", type=Path)
    compare_training.add_argument("-o", "--output", type=Path)
    compare_training.add_argument("--config", type=Path)

    compare_snapshots_parser = subcommands.add_parser(
        "compare-snapshots",
        help="Compare two saved experiment JSON snapshots.",
    )
    compare_snapshots_parser.add_argument("before", type=Path)
    compare_snapshots_parser.add_argument("after", type=Path)
    compare_snapshots_parser.add_argument("-o", "--output", type=Path, required=True)
    compare_snapshots_parser.add_argument("--markdown", type=Path)

    refine = subcommands.add_parser(
        "refine",
        help="Apply a structure-preserving refinement backend to a manifest.",
    )
    refine.add_argument("manifest", type=Path)
    refine.add_argument("-o", "--output", type=Path, required=True)
    refine.add_argument("--backend", default="local_metric")
    refine.add_argument("--max-iterations", type=int, default=0)
    refine.add_argument("--timeout-seconds", type=float)
    refine.add_argument("--raster-l1-weight", type=float, default=1.0)
    refine.add_argument("--raster-edge-weight", type=float, default=0.25)
    refine.add_argument(
        "--source-image",
        type=Path,
        help="Optional source image used for structure-preserving local metrics.",
    )

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
        config = {
            "command": "vectorize",
            "input": str(args.input),
            "output": str(args.output),
            "debug_svg": str(args.debug_svg) if args.debug_svg else None,
            "config": str(args.config) if args.config else None,
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
        args.output.write_text(scene.to_svg(), encoding="utf-8")
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
        summary = write_eval_summary(
            run_root=args.run_root,
            output=args.output,
            markdown=args.markdown,
        )
        print(f"evaluated {summary['run_count']} runs")
        return

    if args.command == "report":
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

    if args.command == "harvest":
        result = harvest_pseudo_labels(
            run_root=args.run_root,
            output=args.output,
            max_run_diagnostics=args.max_run_diagnostics,
            max_classifier_prior_error=args.max_classifier_prior_error,
            min_editability_score=args.min_editability_score,
            max_fragmentation_penalty=args.max_fragmentation_penalty,
        )
        print(f"harvested {result['pseudo_label_count']} pseudo-labels")
        return

    if args.command == "review":
        review_result = create_review_file(
            pseudo_labels=args.pseudo_labels,
            output=args.output,
        )
        print(f"created review queue with {review_result['review_count']} items")
        return

    if args.command == "apply-review":
        reviewed = apply_review_file(
            review=args.review,
            output=args.output,
        )
        print(f"accepted {reviewed['accepted_count']} reviewed pseudo-labels")
        return

    if args.command == "merge-labels":
        dataset = merge_reviewed_pseudo_label_dataset(
            reviewed_labels=args.reviewed_labels,
            output_dir=args.output_dir,
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
        )
        print(
            "compared "
            f"{result['baseline']['train_examples']} baseline examples with "
            f"{result['augmented']['train_examples']} augmented examples"
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

    if args.command == "refine":
        result = refine_manifest(
            manifest=args.manifest,
            output=args.output,
            config=RefinementConfig(
                backend=args.backend,
                max_iterations=args.max_iterations,
                timeout_seconds=args.timeout_seconds,
                source_image=args.source_image,
                raster_l1_weight=args.raster_l1_weight,
                raster_edge_weight=args.raster_edge_weight,
            ),
        )
        print(f"refined {len(result.get('anchors', []))} anchors")
        return

    if args.command == "curated-check":
        result = check_curated_suite(
            args.suite,
            output=args.output,
            output_dir=args.output_dir,
            run=args.run,
            snapshot=args.snapshot,
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
        config.update(loaded)

    for key in VECTORIZE_DEFAULT_CONFIG:
        value = getattr(args, key, None)
        if value is not None:
            config[key] = str(value) if key == "classifier_model" else value
    return config


def _resolved_train_config(args: argparse.Namespace) -> dict[str, Path]:
    config = _load_path_config(args.config, TRAIN_CONFIG_KEYS, "train")
    if args.dataset is not None:
        config["dataset"] = args.dataset
    if args.output is not None:
        config["output"] = args.output
    _require_config_paths(config, ("dataset", "output"), "train")
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
    _require_config_paths(
        config,
        ("base_dataset", "pseudo_dataset", "output"),
        "compare-training",
    )
    return config


def _load_vectorize_config(path: Path) -> dict[str, object]:
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("vectorize config must be a JSON object")
    unknown = sorted(set(loaded) - set(VECTORIZE_DEFAULT_CONFIG))
    if unknown:
        msg = f"unsupported vectorize config keys: {', '.join(unknown)}"
        raise ValueError(msg)
    return loaded


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
    config: dict[str, Path],
    required: tuple[str, ...],
    name: str,
) -> None:
    missing = [key for key in required if key not in config]
    if missing:
        msg = f"{name} requires: {', '.join(missing)}"
        raise ValueError(msg)


if __name__ == "__main__":
    main()
