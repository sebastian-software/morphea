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
from curve.scene import Scene, SvgStyle, anchor_to_svg_element, anchors_to_svg, scene_from_mask

__all__ = [
    "AnchorCandidate",
    "AnchorKind",
    "BinaryMask",
    "CircleAnchor",
    "MaskComponent",
    "Point",
    "QuadAnchor",
    "Scene",
    "StrokeAnchor",
    "SvgStyle",
    "anchor_to_svg_element",
    "anchors_to_svg",
    "choose_best_anchor",
    "connected_components",
    "detect_primitive_anchors",
    "primitive_candidates_for_component",
    "scene_from_mask",
]
