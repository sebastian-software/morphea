# ADR 0003: Strokes as First-Class Primitives

## Status

Accepted

## Context

Illustrations often contain rings, hair lines, clothing folds, grid lines, and
parallel decorative strokes. Modeling these as filled double-contour paths
produces SVGs that are harder to edit and often visually less clean.

## Decision

Morphēa will represent strokes as first-class scene primitives with centerline,
width, cap, join, color, confidence, and source segment metadata.

## Consequences

- Stroke candidates can beat filled path candidates even when the path follows
  pixels more closely.
- Stroke-specific metrics are needed for smoothness, width stability, and
  parallel spacing.
- SVG export should emit true stroked paths or stroked circles where possible.

## Alternatives Considered

- Always export filled geometry: rejected because it is less editable.
- Convert strokes only at export time: rejected because scoring must understand
  strokes before export.

