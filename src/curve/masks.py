"""Small binary-mask utilities for early primitive detection."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Iterable

from curve.anchors import Point


Pixel = tuple[int, int]


@dataclass(frozen=True)
class BinaryMask:
    width: int
    height: int
    pixels: frozenset[Pixel]

    @classmethod
    def from_rows(cls, rows: Iterable[str], filled: str = "#") -> BinaryMask:
        rows = tuple(rows)
        if not rows:
            return cls(width=0, height=0, pixels=frozenset())
        width = len(rows[0])
        pixels: set[Pixel] = set()
        for y, row in enumerate(rows):
            if len(row) != width:
                msg = "all mask rows must have the same width"
                raise ValueError(msg)
            for x, value in enumerate(row):
                if value == filled:
                    pixels.add((x, y))
        return cls(width=width, height=len(rows), pixels=frozenset(pixels))

    def contains(self, pixel: Pixel) -> bool:
        return pixel in self.pixels


@dataclass(frozen=True)
class MaskComponent:
    pixels: frozenset[Pixel]
    bounds_hint: tuple[int, int, int, int] | None = field(
        default=None,
        compare=False,
        repr=False,
    )

    @property
    def area(self) -> int:
        return len(self.pixels)

    @property
    def bounds(self) -> tuple[int, int, int, int]:
        if self.bounds_hint is not None:
            return self.bounds_hint
        min_x = min_y = 0
        max_x = max_y = -1
        for index, (x, y) in enumerate(self.pixels):
            if index == 0:
                min_x = max_x = x
                min_y = max_y = y
                continue
            min_x = min(min_x, x)
            max_x = max(max_x, x)
            min_y = min(min_y, y)
            max_y = max(max_y, y)
        return min_x, min_y, max_x, max_y

    @property
    def width(self) -> int:
        min_x, _, max_x, _ = self.bounds
        return max_x - min_x + 1

    @property
    def height(self) -> int:
        _, min_y, _, max_y = self.bounds
        return max_y - min_y + 1

    @property
    def centroid(self) -> Point:
        return Point(
            sum(x for x, _ in self.pixels) / self.area,
            sum(y for _, y in self.pixels) / self.area,
        )

    @property
    def boundary_pixels(self) -> frozenset[Pixel]:
        boundary: set[Pixel] = set()
        for pixel in self.pixels:
            x, y = pixel
            if any(neighbor not in self.pixels for neighbor in _neighbors4(x, y)):
                boundary.add(pixel)
        return frozenset(boundary)

    def row_spans(self) -> tuple[tuple[int, int, int], ...]:
        rows: dict[int, tuple[int, int]] = {}
        for x, y in self.pixels:
            if y not in rows:
                rows[y] = (x, x)
                continue
            min_x, max_x = rows[y]
            rows[y] = (min(min_x, x), max(max_x, x))
        return tuple((y, *rows[y]) for y in sorted(rows))


def connected_components(mask: BinaryMask, *, min_area: int = 1) -> tuple[MaskComponent, ...]:
    grid, seeds = _indexed_mask(mask)
    components: list[MaskComponent] = []

    for seed in seeds:
        if not grid[seed]:
            continue

        grid[seed] = 0
        pixels: list[Pixel] = []
        start_x = seed % mask.width
        start_y = seed // mask.width
        min_x = max_x = start_x
        min_y = max_y = start_y
        queue: deque[int] = deque([seed])
        while queue:
            index = queue.popleft()
            x = index % mask.width
            y = index // mask.width
            pixels.append((x, y))
            min_x = min(min_x, x)
            max_x = max(max_x, x)
            min_y = min(min_y, y)
            max_y = max(max_y, y)
            _enqueue_neighbors8(
                grid,
                queue,
                x=x,
                y=y,
                width=mask.width,
                height=mask.height,
            )
        if len(pixels) >= min_area:
            components.append(
                MaskComponent(
                    frozenset(pixels),
                    bounds_hint=(min_x, min_y, max_x, max_y),
                )
            )

    return tuple(sorted(components, key=lambda component: component.area, reverse=True))


def _indexed_mask(mask: BinaryMask) -> tuple[bytearray, tuple[int, ...]]:
    grid = bytearray(mask.width * mask.height)
    indexes: list[int] = []
    for x, y in mask.pixels:
        index = y * mask.width + x
        grid[index] = 1
        indexes.append(index)
    return grid, tuple(indexes)


def _enqueue_neighbors8(
    grid: bytearray,
    queue: deque[int],
    *,
    x: int,
    y: int,
    width: int,
    height: int,
) -> None:
    can_left = x > 0
    can_right = x < width - 1
    can_up = y > 0
    can_down = y < height - 1
    index = y * width + x

    if can_up:
        top = index - width
        if grid[top]:
            grid[top] = 0
            queue.append(top)
        if can_left and grid[top - 1]:
            grid[top - 1] = 0
            queue.append(top - 1)
        if can_right and grid[top + 1]:
            grid[top + 1] = 0
            queue.append(top + 1)
    if can_left and grid[index - 1]:
        grid[index - 1] = 0
        queue.append(index - 1)
    if can_right and grid[index + 1]:
        grid[index + 1] = 0
        queue.append(index + 1)
    if can_down:
        bottom = index + width
        if grid[bottom]:
            grid[bottom] = 0
            queue.append(bottom)
        if can_left and grid[bottom - 1]:
            grid[bottom - 1] = 0
            queue.append(bottom - 1)
        if can_right and grid[bottom + 1]:
            grid[bottom + 1] = 0
            queue.append(bottom + 1)


def _neighbors4(x: int, y: int) -> tuple[Pixel, Pixel, Pixel, Pixel]:
    return ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1))
