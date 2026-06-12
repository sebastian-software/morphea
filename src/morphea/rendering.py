"""Deterministic raster rendering for Morphēa manifests."""

from __future__ import annotations

from math import ceil, cos, pi, sin
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
    if kind == "ellipse" and "ellipse" in anchor:
        ellipse = anchor["ellipse"]
        cx = float(ellipse["cx"])
        cy = float(ellipse["cy"])
        rx = float(ellipse["rx"])
        ry = float(ellipse["ry"])
        draw.ellipse((cx - rx, cy - ry, cx + rx, cy + ry), fill=color)
        return
    if kind == "stroke_ellipse" and "ellipse" in anchor:
        ellipse = anchor["ellipse"]
        cx = float(ellipse["cx"])
        cy = float(ellipse["cy"])
        rx = float(ellipse["rx"])
        ry = float(ellipse["ry"])
        width = _stroke_width(anchor)
        half = width / 2
        # Match the SVG model: the stroke centers on the ellipse outline.
        draw.ellipse(
            (cx - rx - half, cy - ry - half, cx + rx + half, cy + ry + half),
            outline=color,
            width=width,
        )
        return
    if kind == "stroke_circle" and "circle" in anchor:
        circle = anchor["circle"]
        cx = float(circle["cx"])
        cy = float(circle["cy"])
        radius = float(circle["r"])
        width = _stroke_width(anchor)
        half = width / 2
        # Match the SVG model: the stroke centers on the circle outline.
        draw.ellipse(
            (cx - radius - half, cy - radius - half, cx + radius + half, cy + radius + half),
            outline=color,
            width=width,
        )
        return
    if kind == "arc" and "arc" in anchor and "stroke" in anchor:
        points = _sampled_arc_points(anchor["arc"])
        width = _stroke_width(anchor)
        if len(points) >= 2:
            draw.line(points, fill=color, width=width, joint="curve")
            if str(anchor["stroke"].get("cap_style", "round")) == "round":
                _draw_round_caps(draw, (points[0], points[-1]), width, color)
        return
    if kind in {"stroke_path", "stroke_polyline", "arc"} and "stroke" in anchor:
        points = [
            (float(point["x"]), float(point["y"]))
            for point in anchor["stroke"].get("centerline", [])
        ]
        if len(points) < 2:
            return
        width = _stroke_width(anchor)
        if kind == "stroke_path" and len(points) >= 3:
            points = _sampled_catmull_rom_points(points)
        draw.line(points, fill=color, width=width, joint="curve")
        if (
            kind == "stroke_path"
            and str(anchor["stroke"].get("cap_style", "round")) == "round"
        ):
            _draw_round_caps(draw, (points[0], points[-1]), width, color)
        return
    if kind == "cubic_path" and "path" in anchor:
        points = [
            (float(point["x"]), float(point["y"]))
            for point in anchor["path"].get("points", [])
        ]
        if len(points) >= 3:
            draw.polygon(_sampled_closed_catmull_rom(points), fill=color)
        return
    if kind in {"rect", "rounded_rect", "quad"} and "quad" in anchor:
        points = [
            (float(point["x"]), float(point["y"]))
            for point in anchor["quad"].get("corners", [])
        ]
        if len(points) >= 3:
            draw.polygon(points, fill=color)


def _sampled_closed_catmull_rom(
    points: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    from morphea.scene import Point, catmull_rom_segments_closed

    control = tuple(Point(x, y) for x, y in points)
    sampled: list[tuple[float, float]] = []
    current = control[0]
    for control1, control2, end in catmull_rom_segments_closed(control):
        steps = max(
            4,
            ceil(
                current.distance_to(control1)
                + control1.distance_to(control2)
                + control2.distance_to(end)
            ),
        )
        for step in range(1, steps + 1):
            t = step / steps
            u = 1 - t
            x = (
                u * u * u * current.x
                + 3 * u * u * t * control1.x
                + 3 * u * t * t * control2.x
                + t * t * t * end.x
            )
            y = (
                u * u * u * current.y
                + 3 * u * u * t * control1.y
                + 3 * u * t * t * control2.y
                + t * t * t * end.y
            )
            sampled.append((x, y))
        current = end
    return sampled


def _sampled_catmull_rom_points(
    points: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    """Sample the same Catmull-Rom curve the SVG export emits."""

    from morphea.scene import Point, catmull_rom_segments

    control = tuple(Point(x, y) for x, y in points)
    sampled = [points[0]]
    current = control[0]
    for control1, control2, end in catmull_rom_segments(control):
        length = (
            current.distance_to(control1)
            + control1.distance_to(control2)
            + control2.distance_to(end)
        )
        steps = max(8, ceil(length))
        for step in range(1, steps + 1):
            t = step / steps
            u = 1 - t
            x = (
                u * u * u * current.x
                + 3 * u * u * t * control1.x
                + 3 * u * t * t * control2.x
                + t * t * t * end.x
            )
            y = (
                u * u * u * current.y
                + 3 * u * u * t * control1.y
                + 3 * u * t * t * control2.y
                + t * t * t * end.y
            )
            sampled.append((x, y))
        current = end
    return sampled


def _sampled_arc_points(arc: dict[str, Any]) -> list[tuple[float, float]]:
    cx = float(arc.get("cx", 0.0))
    cy = float(arc.get("cy", 0.0))
    radius = float(arc.get("r", 0.0))
    theta_start = float(arc.get("theta_start", 0.0))
    theta_end = float(arc.get("theta_end", 0.0))
    span = theta_end - theta_start
    steps = max(16, ceil(abs(span) * radius / 2 * pi))
    return [
        (
            cx + radius * cos(theta_start + span * index / steps),
            cy + radius * sin(theta_start + span * index / steps),
        )
        for index in range(steps + 1)
    ]


def _draw_round_caps(
    draw: ImageDraw.ImageDraw,
    endpoints: tuple[tuple[float, float], tuple[float, float]],
    width: int,
    color: tuple[int, int, int, int],
) -> None:
    half = width / 2
    for x, y in endpoints:
        draw.ellipse((x - half, y - half, x + half - 1, y + half - 1), fill=color)


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
