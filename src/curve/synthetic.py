"""Synthetic flat-color scene generation for training and evaluation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from random import Random

from PIL import Image, ImageDraw

from curve.anchors import (
    AnchorCandidate,
    AnchorKind,
    CircleAnchor,
    Point,
    QuadAnchor,
    StrokeAnchor,
)
from curve.scene import Scene


PALETTE = ("#003366", "#c99700", "#dd2222", "#e7d8ca")


@dataclass(frozen=True)
class SyntheticSample:
    scene: Scene
    image: Image.Image
    seed: int

    def write(self, output_dir: str | Path, name: str) -> tuple[Path, Path]:
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        image_path = output / f"{name}.png"
        manifest_path = output / f"{name}.json"
        self.image.save(image_path)
        manifest = self.scene.to_manifest()
        manifest["seed"] = self.seed
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return image_path, manifest_path


def generate_synthetic_sample(
    *,
    seed: int,
    width: int = 96,
    height: int = 96,
) -> SyntheticSample:
    rng = Random(seed)
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    anchors: list[AnchorCandidate] = []

    anchors.append(_draw_circle(draw, rng, width, height))
    anchors.append(_draw_stroke_circle(draw, rng, width, height))
    anchors.append(_draw_stroke(draw, rng, width, height))
    anchors.append(_draw_quad(draw, rng, width, height))

    return SyntheticSample(
        scene=Scene(width=width, height=height, anchors=tuple(anchors)),
        image=image,
        seed=seed,
    )


def _draw_circle(
    draw: ImageDraw.ImageDraw,
    rng: Random,
    width: int,
    height: int,
) -> AnchorCandidate:
    radius = rng.randint(5, 10)
    center = Point(rng.randint(radius + 2, width // 2), rng.randint(radius + 2, height // 2))
    color = rng.choice(PALETTE)
    draw.ellipse(
        (
            center.x - radius,
            center.y - radius,
            center.x + radius,
            center.y + radius,
        ),
        fill=color,
    )
    return AnchorCandidate(
        kind=AnchorKind.CIRCLE,
        raster_error=0.0,
        node_count=1,
        parameter_count=3,
        color=color,
        circle=CircleAnchor(center=center, radius=radius),
    )


def _draw_stroke_circle(
    draw: ImageDraw.ImageDraw,
    rng: Random,
    width: int,
    height: int,
) -> AnchorCandidate:
    radius = rng.randint(10, 16)
    stroke_width = rng.randint(2, 4)
    center = Point(
        rng.randint(width // 2, width - radius - 3),
        rng.randint(radius + 3, height // 2),
    )
    color = rng.choice(PALETTE)
    draw.ellipse(
        (
            center.x - radius,
            center.y - radius,
            center.x + radius,
            center.y + radius,
        ),
        outline=color,
        width=stroke_width,
    )
    return AnchorCandidate(
        kind=AnchorKind.STROKE_CIRCLE,
        raster_error=0.0,
        node_count=1,
        parameter_count=4,
        color=color,
        circle=CircleAnchor(center=center, radius=radius),
        stroke=StrokeAnchor(centerline=(), width_samples=(float(stroke_width),)),
    )


def _draw_stroke(
    draw: ImageDraw.ImageDraw,
    rng: Random,
    width: int,
    height: int,
) -> AnchorCandidate:
    start = Point(rng.randint(8, width // 3), rng.randint(height // 2, height - 10))
    end = Point(rng.randint(width // 2, width - 8), rng.randint(height // 2, height - 10))
    stroke_width = rng.randint(2, 4)
    color = rng.choice(PALETTE)
    draw.line((start.x, start.y, end.x, end.y), fill=color, width=stroke_width)
    return AnchorCandidate(
        kind=AnchorKind.STROKE_POLYLINE,
        raster_error=0.0,
        node_count=2,
        parameter_count=5,
        color=color,
        stroke=StrokeAnchor(
            centerline=(start, end),
            width_samples=(float(stroke_width),),
        ),
    )


def _draw_quad(
    draw: ImageDraw.ImageDraw,
    rng: Random,
    width: int,
    height: int,
) -> AnchorCandidate:
    top_y = rng.randint(height // 2, height - 28)
    bottom_y = top_y + rng.randint(12, 22)
    left = rng.randint(6, width // 3)
    top_width = rng.randint(12, 22)
    bottom_width = top_width + rng.randint(4, 12)
    skew = rng.randint(-5, 5)
    corners = (
        Point(left, top_y),
        Point(left + top_width, top_y),
        Point(left + top_width + skew + bottom_width - top_width, bottom_y),
        Point(left + skew - (bottom_width - top_width) // 2, bottom_y),
    )
    color = rng.choice(PALETTE)
    draw.polygon([(point.x, point.y) for point in corners], fill=color)
    return AnchorCandidate(
        kind=AnchorKind.QUAD,
        raster_error=0.0,
        node_count=4,
        parameter_count=8,
        color=color,
        quad=QuadAnchor(corners=corners),
    )

