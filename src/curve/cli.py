"""Minimal CLI placeholder for the Curve research prototype."""

from __future__ import annotations

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="curve",
        description="Semantic-first raster-to-SVG research prototype",
    )
    parser.add_argument(
        "command",
        choices=["generate", "train", "vectorize", "eval"],
        help="Prototype command to run.",
    )
    args = parser.parse_args()
    print(f"curve {args.command}: pipeline implementation pending")


if __name__ == "__main__":
    main()

