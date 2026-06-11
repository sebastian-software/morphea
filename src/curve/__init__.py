"""Semantic-first vectorization research primitives."""

from curve.anchors import (
    AnchorCandidate,
    AnchorKind,
    CircleAnchor,
    Point,
    QuadAnchor,
    StrokeAnchor,
    choose_best_anchor,
)

__all__ = [
    "AnchorCandidate",
    "AnchorKind",
    "CircleAnchor",
    "Point",
    "QuadAnchor",
    "StrokeAnchor",
    "choose_best_anchor",
]

