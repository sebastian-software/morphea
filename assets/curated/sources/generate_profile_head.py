"""Deterministic stand-in for the classical-profile real-image case.

Hand-made curated bitmaps live in assets/curated/. This generator exists so
the synthetic stand-in is reproducible; real artwork (screenshots, logos)
is simply dropped next to it as PNG and referenced from suite.json.

Run: PYTHONPATH=src python3 assets/curated/sources/generate_profile_head.py
"""

from __future__ import annotations

from math import ceil, cos, pi, radians, sin
from pathlib import Path

from PIL import Image, ImageDraw

INK = "#0f2a52"
SIZE = (128, 160)
OUTPUT = Path(__file__).resolve().parent.parent / "profile_head_synthetic.png"


def _bezier(points, steps=160):
    from math import comb

    degree = len(points) - 1
    samples = []
    for index in range(steps + 1):
        t = index / steps
        x = sum(
            comb(degree, k) * (1 - t) ** (degree - k) * t**k * points[k][0]
            for k in range(degree + 1)
        )
        y = sum(
            comb(degree, k) * (1 - t) ** (degree - k) * t**k * points[k][1]
            for k in range(degree + 1)
        )
        samples.append((x, y))
    return samples


def _arc_line(draw, cx, cy, r, a0, a1, width, color):
    steps = max(24, ceil(r * abs(a1 - a0) / 360 * 2 * pi))
    points = [
        (
            cx + r * cos(radians(a0 + (a1 - a0) * i / steps)),
            cy + r * sin(radians(a0 + (a1 - a0) * i / steps)),
        )
        for i in range(steps + 1)
    ]
    draw.line(points, fill=color, width=width, joint="curve")


def main() -> None:
    image = Image.new("RGB", SIZE, "#ffffff")
    draw = ImageDraw.Draw(image)

    # Head silhouette: skull dome, brow, nose, lips, chin, neck.
    outline = []
    outline += _bezier([(36, 132), (28, 96), (22, 72), (30, 38)])  # back/neck up
    outline += _bezier([(30, 38), (44, 12), (78, 8), (96, 26)])  # skull dome
    outline += _bezier([(96, 26), (104, 38), (102, 48), (96, 54)])  # forehead
    outline += _bezier([(96, 54), (108, 66), (110, 72), (100, 74)])  # nose
    outline += _bezier([(100, 74), (96, 78), (100, 82), (96, 86)])  # lips
    outline += _bezier([(96, 86), (100, 92), (94, 100), (86, 102)])  # chin
    outline += _bezier([(86, 102), (76, 110), (72, 124), (74, 144)])  # jaw/neck
    outline += [(74, 160), (36, 160)]
    draw.polygon(outline, fill=INK)

    # Curls: white arc slits inside the hair mass, kept apart so each one
    # stays its own enclosed gap.
    _arc_line(draw, 54, 46, 20, -158, -32, 4, "#ffffff")
    _arc_line(draw, 50, 64, 15, -148, -12, 3, "#ffffff")
    _arc_line(draw, 78, 28, 9, -150, -20, 3, "#ffffff")
    _arc_line(draw, 84, 50, 10, -130, 10, 3, "#ffffff")
    _arc_line(draw, 44, 86, 12, -120, 20, 3, "#ffffff")

    # Eye: short white slit below the brow.
    _arc_line(draw, 86, 64, 7, -30, 50, 3, "#ffffff")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    image.save(OUTPUT)
    print(f"wrote {OUTPUT}")


if __name__ == "__main__":
    main()
