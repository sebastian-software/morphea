"""Small binary-mask utilities for early primitive detection."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
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

    @property
    def area(self) -> int:
        return len(self.pixels)

    @property
    def bounds(self) -> tuple[int, int, int, int]:
        xs = [x for x, _ in self.pixels]
        ys = [y for _, y in self.pixels]
        return min(xs), min(ys), max(xs), max(ys)

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
        spans: list[tuple[int, int, int]] = []
        _, min_y, _, max_y = self.bounds
        for y in range(min_y, max_y + 1):
            xs = [x for x, pixel_y in self.pixels if pixel_y == y]
            if xs:
                spans.append((y, min(xs), max(xs)))
        return tuple(spans)


def connected_components(mask: BinaryMask, *, min_area: int = 1) -> tuple[MaskComponent, ...]:
    grid, seeds = _indexed_mask(mask)
    components: list[MaskComponent] = []

    for seed in seeds:
        if not grid[seed]:
            continue

        grid[seed] = 0
        pixels: list[Pixel] = []
        queue: deque[int] = deque([seed])
        while queue:
            index = queue.popleft()
            x = index % mask.width
            y = index // mask.width
            pixels.append((x, y))
            for neighbor in _neighbor_indexes8(index, mask.width, mask.height):
                if grid[neighbor]:
                    grid[neighbor] = 0
                    queue.append(neighbor)
        if len(pixels) >= min_area:
            components.append(MaskComponent(frozenset(pixels)))

    return tuple(sorted(components, key=lambda component: component.area, reverse=True))


def _indexed_mask(mask: BinaryMask) -> tuple[bytearray, tuple[int, ...]]:
    grid = bytearray(mask.width * mask.height)
    indexes: list[int] = []
    for x, y in mask.pixels:
        index = y * mask.width + x
        grid[index] = 1
        indexes.append(index)
    return grid, tuple(indexes)


def _neighbor_indexes8(index: int, width: int, height: int) -> tuple[int, ...]:
    x = index % width
    y = index // width
    neighbors: list[int] = []
    for neighbor_y in range(max(0, y - 1), min(height, y + 2)):
        row_offset = neighbor_y * width
        for neighbor_x in range(max(0, x - 1), min(width, x + 2)):
            if neighbor_x == x and neighbor_y == y:
                continue
            neighbors.append(row_offset + neighbor_x)
    return tuple(neighbors)


def _neighbors4(x: int, y: int) -> tuple[Pixel, Pixel, Pixel, Pixel]:
    return ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1))
