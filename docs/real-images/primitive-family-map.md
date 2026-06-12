# Real-Image Primitive Family Map

This file maps curated real-image expectations back to primitive fixture
families. Real-image results are smoke evidence only; detector changes should
first reproduce failures in the primitive harness.

## `terminaro-tweaked`

- `gold-circle-anchors` -> `filled_circle`, `antialiased_circle`,
  `palette_drift_primitive`
- `table-perspective-quads` -> `simple_quad`, `group_quad_grid`
- `table-grid-group` -> `group_quad_grid`
- `smooth-stroke-anchors` -> `horizontal_stroke`, `vertical_stroke`,
  `diagonal_stroke`, `antialiased_stroke`, `group_parallel_strokes`
- `simple-shape-ratio` -> aggregate smoke over the families above
- `fragmentation-bounded` -> `composition_same_color_separated`,
  `group_dot_row`, `adjacent_small_gap_rects`

## `chatgpt-image-2026-06-11`

- `gold-circle-anchors` -> `filled_circle`, `antialiased_circle`,
  `palette_drift_primitive`
- `table-perspective-quads` -> `simple_quad`, `group_quad_grid`
- `table-grid-group` -> `group_quad_grid`
- `smooth-stroke-anchors` -> `horizontal_stroke`, `vertical_stroke`,
  `diagonal_stroke`, `antialiased_stroke`, `group_parallel_strokes`
- `simple-shape-ratio` -> aggregate smoke over the families above
- `fragmentation-bounded` -> `composition_same_color_separated`,
  `group_dot_row`, `adjacent_small_gap_rects`

## `ui-radio-acceptance-screenshot`

- `radio-circle-anchor` -> `outlined_ring`, `antialiased_ring`,
  `transparent_circle`
- `text-stroke-fragments` -> `horizontal_stroke`, `vertical_stroke`,
  `diagonal_stroke`, `antialiased_stroke`
- `simple-shape-ratio` -> aggregate smoke over the families above

## Promotion Rule

A curated expectation can be tightened only after its mapped fixture family is
green in `morphea primitive-check`. If a curated case fails in a way not covered
by the mapped families, add or update a primitive fixture before changing broad
detector scoring.
