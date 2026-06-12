"""Deterministic rasterization for the SVG subset Morphēa exports.

The primitive harness must validate the actual exported SVG, not only the
manifest-rendered preview. This module implements a small supersampling
rasterizer for exactly the elements ``scene.anchors_to_svg`` can emit:
``rect``, ``circle``, ``ellipse``, ``polygon``, stroked and filled ``path``
with ``M``/``L``/``Q``/``C``/``A``/``Z`` commands, and the negative cut-out
``mask`` structure. It exists so the SVG raster gate is always available and
fully deterministic; external renderers stay optional cross-checks.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from math import atan2, ceil, cos, hypot, pi, radians, sin, sqrt
from typing import Iterable

from PIL import Image, ImageChops, ImageDraw

from morphea.rendering import raster_fidelity_metrics


SUPERSAMPLE_SCALE = 4
_SVG_NS = "{http://www.w3.org/2000/svg}"
_PATH_TOKEN = re.compile(r"[MmLlQqCcAaZz]|-?\d+(?:\.\d+)?(?:e-?\d+)?")
_MASK_URL = re.compile(r"url\(#([^)]+)\)")


def svg_raster_capability() -> dict[str, object]:
    """Report which SVG raster backend this environment provides."""

    return {
        "backend": "builtin",
        "available": True,
        "supersample": SUPERSAMPLE_SCALE,
    }


def rasterize_svg(
    svg_text: str,
    *,
    background: str = "#ffffff",
    scale: int = SUPERSAMPLE_SCALE,
) -> Image.Image:
    """Rasterize exported SVG text into an RGBA image at its declared size."""

    root = ET.fromstring(svg_text)
    width = int(float(root.attrib.get("width", 1)))
    height = int(float(root.attrib.get("height", 1)))
    masks = _collect_masks(root)
    canvas = Image.new(
        "RGBA",
        (width * scale, height * scale),
        _rgba(background),
    )
    _render_children(canvas, root, masks, scale)
    return canvas.resize((width, height), Image.Resampling.BOX)


def svg_raster_metrics(
    *,
    source: Image.Image,
    svg_text: str,
    preview: Image.Image | None = None,
    background: str = "#ffffff",
) -> dict[str, object]:
    """Compare the rasterized exported SVG with source and optional preview."""

    rendered = rasterize_svg(svg_text, background=background)
    source_metrics = raster_fidelity_metrics(source=source, rendered=rendered)
    metrics: dict[str, object] = {
        "svg_raster_backend": "builtin",
        "svg_render_size_match": source_metrics["raster_size_match"],
        "svg_raster_l1_error": source_metrics["raster_l1_error"],
        "svg_raster_edge_error": source_metrics["raster_edge_error"],
        "svg_alpha_error": source_metrics["raster_alpha_error"],
    }
    if preview is not None:
        preview_metrics = raster_fidelity_metrics(
            source=preview.convert("RGBA"),
            rendered=rendered,
        )
        metrics["svg_vs_preview_l1_error"] = preview_metrics["raster_l1_error"]
        metrics["svg_vs_preview_edge_error"] = preview_metrics["raster_edge_error"]
    return metrics


def rasterized_svg_image(
    svg_text: str,
    *,
    background: str = "#ffffff",
) -> Image.Image:
    return rasterize_svg(svg_text, background=background)


def _collect_masks(root: ET.Element) -> dict[str, ET.Element]:
    masks: dict[str, ET.Element] = {}
    for defs in _iter_local(root, "defs"):
        for mask in _iter_local(defs, "mask"):
            mask_id = mask.attrib.get("id")
            if mask_id:
                masks[mask_id] = mask
    return masks


def _iter_local(element: ET.Element, local_name: str) -> Iterable[ET.Element]:
    for child in element:
        if _local_tag(child) == local_name:
            yield child


def _local_tag(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def _render_children(
    canvas: Image.Image,
    parent: ET.Element,
    masks: dict[str, ET.Element],
    scale: int,
) -> None:
    for child in parent:
        tag = _local_tag(child)
        if tag == "defs":
            continue
        if tag == "g":
            _render_group(canvas, child, masks, scale)
            continue
        _render_shape(ImageDraw.Draw(canvas), child, scale, canvas)


def _render_group(
    canvas: Image.Image,
    group: ET.Element,
    masks: dict[str, ET.Element],
    scale: int,
) -> None:
    mask_reference = _MASK_URL.search(group.attrib.get("mask", ""))
    if mask_reference is None:
        _render_children(canvas, group, masks, scale)
        return

    mask_element = masks.get(mask_reference.group(1))
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    _render_children(layer, group, masks, scale)
    if mask_element is not None:
        mask_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 255))
        _render_children(mask_layer, mask_element, masks, scale)
        mask_alpha = mask_layer.convert("L")
        layer.putalpha(ImageChops.multiply(layer.getchannel("A"), mask_alpha))
    canvas.alpha_composite(layer)


def _render_shape(
    draw: ImageDraw.ImageDraw,
    element: ET.Element,
    scale: int,
    canvas: Image.Image,
) -> None:
    tag = _local_tag(element)
    if tag == "rect":
        _render_rect(draw, element, scale)
    elif tag == "circle":
        _render_circle(draw, element, scale)
    elif tag == "ellipse":
        _render_ellipse(draw, element, scale)
    elif tag == "polygon":
        _render_polygon(draw, element, scale)
    elif tag == "path":
        _render_path(draw, element, scale)


def _render_rect(
    draw: ImageDraw.ImageDraw,
    element: ET.Element,
    scale: int,
) -> None:
    fill = _paint(element.attrib.get("fill"))
    if fill is None:
        return
    x = _number(element, "x")
    y = _number(element, "y")
    width = _number(element, "width")
    height = _number(element, "height")
    radius = max(_number(element, "rx"), _number(element, "ry"))
    box = (
        round(x * scale),
        round(y * scale),
        round((x + width) * scale) - 1,
        round((y + height) * scale) - 1,
    )
    if box[2] < box[0] or box[3] < box[1]:
        return
    if radius > 0:
        draw.rounded_rectangle(box, radius=round(radius * scale), fill=fill)
    else:
        draw.rectangle(box, fill=fill)


def _render_circle(
    draw: ImageDraw.ImageDraw,
    element: ET.Element,
    scale: int,
) -> None:
    cx = _number(element, "cx")
    cy = _number(element, "cy")
    radius = _number(element, "r")
    _render_ellipse_geometry(draw, element, scale, cx, cy, radius, radius)


def _render_ellipse(
    draw: ImageDraw.ImageDraw,
    element: ET.Element,
    scale: int,
) -> None:
    cx = _number(element, "cx")
    cy = _number(element, "cy")
    rx = _number(element, "rx")
    ry = _number(element, "ry")
    _render_ellipse_geometry(draw, element, scale, cx, cy, rx, ry)


def _render_ellipse_geometry(
    draw: ImageDraw.ImageDraw,
    element: ET.Element,
    scale: int,
    cx: float,
    cy: float,
    rx: float,
    ry: float,
) -> None:
    fill = _paint(element.attrib.get("fill", "#000000"))
    stroke = _paint(element.attrib.get("stroke"))
    stroke_width = _number(element, "stroke-width", default=1.0)
    if fill is not None:
        draw.ellipse(_ellipse_box(cx, cy, rx, ry, scale), fill=fill)
    if stroke is not None and stroke_width > 0:
        # SVG centers the stroke on the geometry edge; PIL draws the outline
        # width inward from the bounding box, so widen the box by half a width.
        half = stroke_width / 2
        draw.ellipse(
            _ellipse_box(cx, cy, rx + half, ry + half, scale),
            outline=stroke,
            width=max(1, round(stroke_width * scale)),
        )


def _ellipse_box(
    cx: float,
    cy: float,
    rx: float,
    ry: float,
    scale: int,
) -> tuple[int, int, int, int]:
    return (
        round((cx - rx) * scale),
        round((cy - ry) * scale),
        round((cx + rx) * scale) - 1,
        round((cy + ry) * scale) - 1,
    )


def _render_polygon(
    draw: ImageDraw.ImageDraw,
    element: ET.Element,
    scale: int,
) -> None:
    fill = _paint(element.attrib.get("fill"))
    if fill is None:
        return
    points = [
        (float(x) * scale, float(y) * scale)
        for x, y in (
            pair.split(",")
            for pair in element.attrib.get("points", "").split()
        )
    ]
    if len(points) >= 3:
        draw.polygon(points, fill=fill)


def _render_path(
    draw: ImageDraw.ImageDraw,
    element: ET.Element,
    scale: int,
) -> None:
    subpaths = _flattened_path(element.attrib.get("d", ""), scale)
    if not subpaths:
        return
    fill = _paint(element.attrib.get("fill"))
    stroke = _paint(element.attrib.get("stroke"))
    stroke_width = _number(element, "stroke-width", default=1.0)
    cap = element.attrib.get("stroke-linecap", "butt")
    if fill is not None:
        closed_fills = [points for points, _ in subpaths if len(points) >= 3]
        if element.attrib.get("fill-rule") == "evenodd" and len(closed_fills) > 1:
            _fill_evenodd(draw, closed_fills, fill)
        else:
            for points in closed_fills:
                draw.polygon(points, fill=fill)
    if stroke is None or stroke_width <= 0:
        return
    pixel_width = max(1, round(stroke_width * scale))
    for points, closed in subpaths:
        if len(points) < 2:
            continue
        line_points = points + points[:1] if closed else points
        draw.line(line_points, fill=stroke, width=pixel_width, joint="curve")
        if closed:
            continue
        if cap == "round":
            for end in (points[0], points[-1]):
                _draw_cap_circle(draw, end, pixel_width, stroke)
        elif cap == "square":
            _draw_square_cap(draw, points[0], points[1], pixel_width, stroke)
            _draw_square_cap(draw, points[-1], points[-2], pixel_width, stroke)


def _fill_evenodd(
    draw: ImageDraw.ImageDraw,
    subpaths: list[list[tuple[float, float]]],
    fill: tuple[int, int, int, int],
) -> None:
    """Even-odd fill via an XOR coverage mask, composited in place."""

    image = draw._image
    mask = Image.new("1", image.size, 0)
    for points in subpaths:
        contour = Image.new("1", image.size, 0)
        ImageDraw.Draw(contour).polygon(points, fill=1)
        mask = ImageChops.logical_xor(mask, contour)
    overlay = Image.new("RGBA", image.size, fill)
    image.paste(overlay, (0, 0), mask.convert("L").point(lambda v: 255 if v else 0))


def _draw_cap_circle(
    draw: ImageDraw.ImageDraw,
    center: tuple[float, float],
    pixel_width: int,
    color: tuple[int, int, int, int],
) -> None:
    radius = pixel_width / 2
    draw.ellipse(
        (
            center[0] - radius,
            center[1] - radius,
            center[0] + radius - 1,
            center[1] + radius - 1,
        ),
        fill=color,
    )


def _draw_square_cap(
    draw: ImageDraw.ImageDraw,
    end: tuple[float, float],
    inner: tuple[float, float],
    pixel_width: int,
    color: tuple[int, int, int, int],
) -> None:
    dx = end[0] - inner[0]
    dy = end[1] - inner[1]
    length = hypot(dx, dy)
    if length <= 0:
        return
    dx /= length
    dy /= length
    half = pixel_width / 2
    tip = (end[0] + dx * half, end[1] + dy * half)
    normal = (-dy * half, dx * half)
    draw.polygon(
        [
            (end[0] + normal[0], end[1] + normal[1]),
            (tip[0] + normal[0], tip[1] + normal[1]),
            (tip[0] - normal[0], tip[1] - normal[1]),
            (end[0] - normal[0], end[1] - normal[1]),
        ],
        fill=color,
    )


def _flattened_path(
    d: str,
    scale: int,
) -> list[tuple[list[tuple[float, float]], bool]]:
    tokens = _PATH_TOKEN.findall(d)
    subpaths: list[tuple[list[tuple[float, float]], bool]] = []
    points: list[tuple[float, float]] = []
    index = 0
    current = (0.0, 0.0)
    start = (0.0, 0.0)

    def read() -> float:
        nonlocal index
        value = float(tokens[index])
        index += 1
        return value

    while index < len(tokens):
        command = tokens[index]
        index += 1
        if command in {"M", "m"}:
            if points:
                subpaths.append((points, False))
            x, y = read(), read()
            if command == "m":
                x += current[0]
                y += current[1]
            current = (x, y)
            start = current
            points = [(x * scale, y * scale)]
        elif command in {"L", "l"}:
            x, y = read(), read()
            if command == "l":
                x += current[0]
                y += current[1]
            current = (x, y)
            points.append((x * scale, y * scale))
        elif command in {"Q", "q"}:
            x1, y1, x, y = read(), read(), read(), read()
            if command == "q":
                x1 += current[0]
                y1 += current[1]
                x += current[0]
                y += current[1]
            points.extend(
                _sample_quadratic(current, (x1, y1), (x, y), scale)
            )
            current = (x, y)
        elif command in {"C", "c"}:
            x1, y1, x2, y2, x, y = (
                read(), read(), read(), read(), read(), read(),
            )
            if command == "c":
                x1 += current[0]
                y1 += current[1]
                x2 += current[0]
                y2 += current[1]
                x += current[0]
                y += current[1]
            points.extend(
                _sample_cubic(current, (x1, y1), (x2, y2), (x, y), scale)
            )
            current = (x, y)
        elif command in {"A", "a"}:
            rx, ry, rotation, large_arc, sweep, x, y = (
                read(), read(), read(), read(), read(), read(), read(),
            )
            if command == "a":
                x += current[0]
                y += current[1]
            points.extend(
                _sample_arc(
                    current,
                    (x, y),
                    rx=rx,
                    ry=ry,
                    rotation=rotation,
                    large_arc=large_arc != 0,
                    sweep=sweep != 0,
                    scale=scale,
                )
            )
            current = (x, y)
        elif command in {"Z", "z"}:
            if points:
                subpaths.append((points, True))
            points = []
            current = start
        else:  # bare number without command: malformed path, stop parsing
            break
    if points:
        subpaths.append((points, False))
    return subpaths


def _sample_quadratic(
    start: tuple[float, float],
    control: tuple[float, float],
    end: tuple[float, float],
    scale: int,
) -> list[tuple[float, float]]:
    steps = _curve_steps((start, control, end), scale)
    samples = []
    for step in range(1, steps + 1):
        t = step / steps
        u = 1 - t
        x = u * u * start[0] + 2 * u * t * control[0] + t * t * end[0]
        y = u * u * start[1] + 2 * u * t * control[1] + t * t * end[1]
        samples.append((x * scale, y * scale))
    return samples


def _sample_cubic(
    start: tuple[float, float],
    control1: tuple[float, float],
    control2: tuple[float, float],
    end: tuple[float, float],
    scale: int,
) -> list[tuple[float, float]]:
    steps = _curve_steps((start, control1, control2, end), scale)
    samples = []
    for step in range(1, steps + 1):
        t = step / steps
        u = 1 - t
        x = (
            u * u * u * start[0]
            + 3 * u * u * t * control1[0]
            + 3 * u * t * t * control2[0]
            + t * t * t * end[0]
        )
        y = (
            u * u * u * start[1]
            + 3 * u * u * t * control1[1]
            + 3 * u * t * t * control2[1]
            + t * t * t * end[1]
        )
        samples.append((x * scale, y * scale))
    return samples


def _sample_arc(
    start: tuple[float, float],
    end: tuple[float, float],
    *,
    rx: float,
    ry: float,
    rotation: float,
    large_arc: bool,
    sweep: bool,
    scale: int,
) -> list[tuple[float, float]]:
    # W3C endpoint-to-center arc parameterization (SVG 2, B.2.4).
    if rx <= 0 or ry <= 0 or start == end:
        return [(end[0] * scale, end[1] * scale)]
    rx = abs(rx)
    ry = abs(ry)
    phi = radians(rotation % 360)
    cos_phi = cos(phi)
    sin_phi = sin(phi)
    dx = (start[0] - end[0]) / 2
    dy = (start[1] - end[1]) / 2
    x1p = cos_phi * dx + sin_phi * dy
    y1p = -sin_phi * dx + cos_phi * dy
    lam = (x1p / rx) ** 2 + (y1p / ry) ** 2
    if lam > 1:
        factor = sqrt(lam)
        rx *= factor
        ry *= factor
    numerator = (rx * ry) ** 2 - (rx * y1p) ** 2 - (ry * x1p) ** 2
    denominator = (rx * y1p) ** 2 + (ry * x1p) ** 2
    radicand = max(numerator / denominator, 0.0) if denominator else 0.0
    coefficient = sqrt(radicand)
    if large_arc == sweep:
        coefficient = -coefficient
    cxp = coefficient * rx * y1p / ry
    cyp = -coefficient * ry * x1p / rx
    cx = cos_phi * cxp - sin_phi * cyp + (start[0] + end[0]) / 2
    cy = sin_phi * cxp + cos_phi * cyp + (start[1] + end[1]) / 2
    theta1 = atan2((y1p - cyp) / ry, (x1p - cxp) / rx)
    theta2 = atan2((-y1p - cyp) / ry, (-x1p - cxp) / rx)
    delta = theta2 - theta1
    if sweep and delta < 0:
        delta += 2 * pi
    elif not sweep and delta > 0:
        delta -= 2 * pi

    arc_length = abs(delta) * max(rx, ry)
    steps = max(8, ceil(arc_length * scale / 2))
    samples = []
    for step in range(1, steps + 1):
        theta = theta1 + delta * step / steps
        x = cx + rx * cos(theta) * cos_phi - ry * sin(theta) * sin_phi
        y = cy + rx * cos(theta) * sin_phi + ry * sin(theta) * cos_phi
        samples.append((x * scale, y * scale))
    return samples


def _curve_steps(
    control_points: tuple[tuple[float, float], ...],
    scale: int,
) -> int:
    length = sum(
        hypot(b[0] - a[0], b[1] - a[1])
        for a, b in zip(control_points, control_points[1:])
    )
    return max(8, ceil(length * scale / 2))


def _number(element: ET.Element, name: str, *, default: float = 0.0) -> float:
    raw = element.attrib.get(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _paint(value: str | None) -> tuple[int, int, int, int] | None:
    if value is None:
        return None
    value = value.strip()
    if value == "none" or not value:
        return None
    named = {"white": "#ffffff", "black": "#000000"}
    value = named.get(value.lower(), value)
    return _rgba(value)


def _rgba(color: str) -> tuple[int, int, int, int]:
    color = color.strip()
    if not color.startswith("#") or len(color) not in {7, 9}:
        return (11, 45, 95, 255)
    red = int(color[1:3], 16)
    green = int(color[3:5], 16)
    blue = int(color[5:7], 16)
    alpha = int(color[7:9], 16) if len(color) == 9 else 255
    return (red, green, blue, alpha)
