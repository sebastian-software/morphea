"""Minimal CLI placeholder for the Curve research prototype."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from curve.images import scene_from_flat_color_image


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
        "--manifest",
        type=Path,
        help="Output JSON manifest path. Defaults to output path with .json suffix.",
    )
    vectorize.add_argument(
        "--no-manifest",
        action="store_true",
        help="Do not write a JSON recognition manifest.",
    )

    for name in ("generate", "train", "eval"):
        subcommands.add_parser(name, help=f"{name} command placeholder.")

    args = parser.parse_args(argv)
    if args.command == "vectorize":
        scene = scene_from_flat_color_image(args.input, min_area=args.min_area)
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

    print(f"curve {args.command}: pipeline implementation pending")


if __name__ == "__main__":
    main()
