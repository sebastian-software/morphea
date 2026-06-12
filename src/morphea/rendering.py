"""Deterministic raster rendering for Morphēa manifests."""

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


def raster_fidelity_metrics(
    *,
    source: Image.Image,
    rendered: Image.Image,
) -> dict[str, object]:
    """Compare a rendered preview with its source image using bounded metrics."""

    source_rgba = source.convert("RGBA")
    rendered_rgba = rendered.convert("RGBA")
    size_matches = source_rgba.size == rendered_rgba.size
    if not size_matches:
        rendered_rgba = rendered_rgba.resize(source_rgba.size, Image.Resampling.NEAREST)

    source_pixels = source_rgba.tobytes()
    rendered_pixels = rendered_rgba.tobytes()
    pixel_count = max(len(source_pixels) // 4, 1)

    rgb_error = 0.0
    alpha_error = 0.0
    for index in range(0, len(source_pixels), 4):
        if source_pixels[index + 3] == 0 and rendered_pixels[index + 3] == 0:
            continue
        rgb_error += (
            abs(source_pixels[index] - rendered_pixels[index])
            + abs(source_pixels[index + 1] - rendered_pixels[index + 1])
            + abs(source_pixels[index + 2] - rendered_pixels[index + 2])
        )
        alpha_error += abs(source_pixels[index + 3] - rendered_pixels[index + 3])

    return {
        "raster_size_match": size_matches,
        "raster_l1_error": round(rgb_error / (pixel_count * 3 * 255), 6),
        "raster_alpha_error": round(alpha_error / (pixel_count * 255), 6),
        "raster_edge_error": round(
            _edge_l1_error(source_rgba, rendered_rgba),
            6,
        ),
    }


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


def _edge_l1_error(source: Image.Image, rendered: Image.Image) -> float:
    width, height = source.size
    if width < 2 or height < 2:
        return 0.0

    source_luma = _luma_values(source)
    rendered_luma = _luma_values(rendered)
    error = 0.0
    count = 0
    for y in range(height - 1):
        row = y * width
        next_row = (y + 1) * width
        for x in range(width - 1):
            index = row + x
            source_edge = (
                abs(source_luma[index] - source_luma[index + 1])
                + abs(source_luma[index] - source_luma[next_row + x])
            )
            rendered_edge = (
                abs(rendered_luma[index] - rendered_luma[index + 1])
                + abs(rendered_luma[index] - rendered_luma[next_row + x])
            )
            error += abs(source_edge - rendered_edge)
            count += 1
    return error / (count * 510)


def _luma_values(image: Image.Image) -> bytearray:
    pixels = image.tobytes()
    luma = bytearray(len(pixels) // 4)
    output_index = 0
    for index in range(0, len(pixels), 4):
        luma[output_index] = (
            (pixels[index] * 299)
            + (pixels[index + 1] * 587)
            + (pixels[index + 2] * 114)
        ) // 1000
        output_index += 1
    return luma


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
