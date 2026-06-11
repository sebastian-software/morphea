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
from curve.detection import detect_primitive_anchors, primitive_candidates_for_component
from curve.masks import BinaryMask, MaskComponent, connected_components

__all__ = [
    "AnchorCandidate",
    "AnchorKind",
    "BinaryMask",
    "CircleAnchor",
    "MaskComponent",
    "Point",
    "QuadAnchor",
    "StrokeAnchor",
    "choose_best_anchor",
    "connected_components",
    "detect_primitive_anchors",
    "primitive_candidates_for_component",
]
