# Semantic-First Vectorization Plan

## Summary

Morphēa is a local research prototype for raster-to-SVG vectorization. Its
primary target is not to clone visually dense tracing tools. It should produce
fewer, more meaningful, directly editable SVG shapes.

For the expanded milestone roadmap, see [milestones.md](milestones.md).
Key architecture decisions live in [adr](adr/), including primitive-first
fitting and the reviewed pseudo-label self-learning loop.

The first implementation priority is simple geometry. Circles, smooth lines,
strokes, arcs, rectangles, perspective quads, trapezoids, parallelograms, and
regular grid or tile structures must be detected and stabilized before generic
segment fitting. These forms are visual anchors: if they are egg-shaped,
jittery, or uneven, the whole result feels wrong.

## Pipeline Direction

1. Preprocess the image conservatively: alpha normalization, palette
   quantization, and analysis/final scaling.
2. Run `primitive_anchor_detection` before generic fitting.
3. Reserve detected anchors in the scene model so later organic fitting cannot
   fragment or overwrite them.
4. Run general segment fitting for remaining regions.
5. Score candidates with semantic/editability metrics first and raster fidelity
   second.
6. Export plain SVG primitives and a canonical scene JSON.
7. Write every run to a timestamped run directory with config, intermediates,
   metrics, and a visual report.
8. Use reviewed pseudo-labels from Morphēa's own high-confidence outputs for
   self-learning; external vectorizer SVGs are comparison material, not labels.

## Primitive Anchor Detection

The anchor stage must prioritize:

- Circles, circle rings, and point dots.
- Straight lines, smooth curves, arcs, and stroke groups.
- Parallel stroke groups.
- Rectangles and rounded rectangles.
- Perspective rectangles, trapezoids, parallelograms, and quadrilateral tiles.
- Regular grid/tile structures such as perspective table grids.

Simple parametric candidates win over complex path candidates unless they
break raster fidelity badly. This intentionally favors editability over
microscopic contour matching.

## Scene Model Requirements

The scene model must support fill and stroke primitives:

- Fill primitives: `circle`, `ellipse`, `rect`, `rounded_rect`, `polygon`,
  `arc`, `star`, `cubic_path`.
- Stroke primitives: `stroke_path`, `stroke_arc`, `stroke_circle`,
  `stroke_polyline`.
- Stroke attributes: `width`, `cap`, `join`, `color`, `confidence`,
  `source_segment`.

White cut-out-looking lines are represented as editable white overlay strokes
in v1. This is less topologically pure than masks, but it makes hair, clothing,
grid, and border lines easier for a human to select and edit.

## Metrics

Anchor metrics:

- `circle_roundness_error`: penalizes egg-shaped circles and rings.
- `line_smoothness_error`: penalizes jittery or uneven centerlines.
- `stroke_width_variance`: penalizes unstable stroke width.
- `parallel_spacing_error`: penalizes uneven spacing in line groups.
- `cutout_anchor_error`: applies anchor quality rules to white overlay strokes.
- `quad_edge_straightness_error`: penalizes unstable quadrilateral edges.
- `quad_corner_consistency_error`: penalizes implausible or unstable corners.
- `perspective_grid_consistency_error`: penalizes inconsistent perspective
  rows, columns, and vanishing behavior.
- `simple_shape_priority_bonus`: rewards simple editable shapes over generic
  paths.

General metrics still matter: nodes, shape count, parameter count, layer depth,
L1, SSIM, alpha error, and edge error. They are secondary to semantic quality
for v1 candidate ranking.

## Test Strategy

Golden cases for the first implementation:

- An outside ring is modeled as a clean `stroke_circle` or arc stroke.
- Dots are modeled as true circles.
- Table tiles are modeled as perspective quads or a grid structure, not noisy
  polygons.
- Straight grid lines stay straight and harmonically spaced.
- White hair and clothing cut-outs are modeled as smooth overlay strokes.
- A simple shape candidate beats a more pixel-close but jittery path when
  fidelity remains acceptable.
