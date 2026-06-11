"""Deterministic raster rendering for Curve manifests."""

from __future__ import annotations

from pathlib import Path
from statistics import mean
from typing import Any

from PIL import Image, ImageDraw


def render_manifest_image(
    manifest: dict[str, Any],
    *,
    background: str = "#ffffff",
) -> Image.Image:
    width = int(manifest.get("width", 1))
    height = int(manifest.get("height", 1))
    image = Image.new("RGBA", (width, height), _rgba(background))
    draw = ImageDraw.Draw(image)
    for anchor in manifest.get("anchors", []):
        _draw_anchor(draw, anchor)
    return image


def write_manifest_preview(
    *,
    manifest: dict[str, Any],
    output: str | Path,
    background: str = "#ffffff",
) -> Path:
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    render_manifest_image(manifest, background=background).save(output_path)
    return output_path


def _draw_anchor(draw: ImageDraw.ImageDraw, anchor: dict[str, Any]) -> None:
    color = _rgba(str(anchor.get("color") or "#0b2d5f"))
    kind = anchor.get("kind")
    if kind == "circle" and "circle" in anchor:
        circle = anchor["circle"]
        cx = float(circle["cx"])
        cy = float(circle["cy"])
        radius = float(circle["r"])
        draw.ellipse(
            (cx - radius, cy - radius, cx + radius, cy + radius),
            fill=color,
        )
        return
    if kind == "stroke_circle" and "circle" in anchor:
        circle = anchor["circle"]
        cx = float(circle["cx"])
        cy = float(circle["cy"])
        radius = float(circle["r"])
        draw.ellipse(
            (cx - radius, cy - radius, cx + radius, cy + radius),
            outline=color,
            width=_stroke_width(anchor),
        )
        return
    if kind in {"stroke_path", "stroke_polyline", "arc"} and "stroke" in anchor:
        points = [
            (float(point["x"]), float(point["y"]))
            for point in anchor["stroke"].get("centerline", [])
        ]
        if len(points) >= 2:
            draw.line(points, fill=color, width=_stroke_width(anchor), joint="curve")
        return
    if kind in {"rect", "rounded_rect", "quad"} and "quad" in anchor:
        points = [
            (float(point["x"]), float(point["y"]))
            for point in anchor["quad"].get("corners", [])
        ]
        if len(points) >= 3:
            draw.polygon(points, fill=color)


def _stroke_width(anchor: dict[str, Any]) -> int:
    stroke = anchor.get("stroke") or {}
    samples = [float(sample) for sample in stroke.get("width_samples", [])]
    if not samples and anchor.get("kind") == "stroke_circle":
        samples = [float(anchor.get("metrics", {}).get("stroke_width", 1.0))]
    width = mean(samples) if samples else 1.0
    return max(1, round(width))


def _rgba(color: str) -> tuple[int, int, int, int]:
    color = color.strip()
    if not color.startswith("#") or len(color) not in {7, 9}:
        return (11, 45, 95, 255)
    red = int(color[1:3], 16)
    green = int(color[3:5], 16)
    blue = int(color[5:7], 16)
    alpha = int(color[7:9], 16) if len(color) == 9 else 255
    return (red, green, blue, alpha)
