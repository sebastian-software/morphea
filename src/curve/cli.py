"""Minimal CLI placeholder for the Curve research prototype."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from curve.classifier import train_centroid_classifier
from curve.dataset import generate_synthetic_dataset
from curve.eval import write_eval_summary
from curve.images import scene_from_flat_color_image
from curve.runs import create_run_dir, write_vectorize_run
from curve.self_learning import apply_review_file, create_review_file, harvest_pseudo_labels


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
        default=8,
        help="Minimum exact-color component area to consider.",
    )
    vectorize.add_argument(
        "--color-tolerance",
        type=float,
        default=0.0,
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
        "--run-dir",
        type=Path,
        help="Write a timestamped experiment run directory under this root.",
    )
    vectorize.add_argument(
        "--classifier-model",
        type=Path,
        help="Optional primitive classifier model JSON used as a ranking prior.",
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

    train = subcommands.add_parser(
        "train",
        help="Train a primitive classifier from a generated dataset.json.",
    )
    train.add_argument("dataset", type=Path)
    train.add_argument("-o", "--output", type=Path, required=True)

    harvest = subcommands.add_parser(
        "harvest",
        help="Collect high-confidence pseudo-labels from vectorize runs.",
    )
    harvest.add_argument("run_root", type=Path)
    harvest.add_argument("-o", "--output", type=Path, required=True)
    harvest.add_argument("--max-run-diagnostics", type=int, default=0)
    harvest.add_argument("--max-classifier-prior-error", type=float, default=0.0)

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

    args = parser.parse_args(argv)
    if args.command == "vectorize":
        config = {
            "command": "vectorize",
            "input": str(args.input),
            "output": str(args.output),
            "min_area": args.min_area,
            "color_tolerance": args.color_tolerance,
            "max_size": args.max_size,
            "max_colors": args.max_colors,
            "max_component_area": args.max_component_area,
            "timeout_seconds": args.timeout_seconds,
            "classifier_model": str(args.classifier_model) if args.classifier_model else None,
        }
        scene = scene_from_flat_color_image(
            args.input,
            min_area=args.min_area,
            color_tolerance=args.color_tolerance,
            max_size=args.max_size,
            max_colors=args.max_colors,
            max_component_area=args.max_component_area,
            timeout_seconds=args.timeout_seconds,
            classifier_model=args.classifier_model,
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

    if args.command == "train":
        model = train_centroid_classifier(args.dataset, output=args.output)
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

    print(f"curve {args.command}: pipeline implementation pending")


if __name__ == "__main__":
    main()
