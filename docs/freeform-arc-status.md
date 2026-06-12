# Freeform Arc Baseline Status (FQ0)

This document records what the implementation can and cannot do for curved
forms at the start of the freeform arc quality track. It mirrors the code, not
ambitions. See `freeform-arc-quality-roadmap.md` for the plan.

## Detector

- `arc` is detected by `_arc_candidate` in `detection.py` for thin curved
  components only: component density must stay at or below 0.45, the bow must
  reach at least a quarter of the short side, and `arc_bow_ratio` must reach
  0.12.
- The arc centerline is three points: the two component edge midpoints and the
  single pixel farthest from the chord. There is no circle or ellipse fit for
  arcs yet.
- Oversized arc and stroke false positives are rejected by
  `_stroke_bounds_exceed_component`, which compares the stroke bounds with the
  component bounds.
- Straight strokes (`stroke_polyline`) can gain one middle control point in
  `_stroke_polyline_centerline` when the component bows away from the
  principal axis.
- `stroke_path` exists as an anchor kind, but no detector path emits it. All
  detected strokes are `stroke_polyline` or `arc`.
- There is no `ellipse` or `stroke_ellipse` anchor kind. Oval components fail
  the circle aspect checks and fall through to quad or the generic fallback.
- The `cubic_path` fallback candidate carries no geometry: only node and
  parameter counts sized from the component area. It cannot be rendered or
  exported.

## Scene Model and SVG Export

- Since FQ3 detected arcs carry an `ArcAnchor` (center, radius, angle range,
  sweep, large-arc) and export as a single SVG `A` path with round caps. The
  manifest serializes those parameters under `anchors[].arc` and the preview
  renderer samples the same fitted circle, so preview, exported SVG, and
  source agree within `svg_vs_preview_l1_error <= 0.02` on the arc fixtures.
- `stroke_path` and `stroke_polyline` still export through `_polyline_path`
  as `M`/`L` paths; smooth `Q`/`C` export is FQ4 territory.
- `cubic_path` anchors export as an unsupported-anchor SVG comment.

## Renderer and Quality Gates

- `render_manifest_image` draws arcs and stroke paths as straight polylines
  between centerline points. A detected arc therefore renders as two chords.
- Since FQ1 every fixture also rasterizes the actual exported SVG through the
  builtin supersampling backend in `svg_raster.py` and gates
  `svg_raster_l1_error`, `svg_raster_edge_error`, `svg_alpha_error`, and
  `svg_vs_preview_l1_error` per family. The backend handles the exported
  subset including `A`/`Q`/`C` path commands and the negative cut-out mask,
  and is cross-checked against `rsvg-convert` when that binary is installed.
- Known systematic offsets the derived SVG thresholds account for: SVG
  polygons cover the mathematical area while PIL sources fill inclusive
  pixels (quads measure up to 0.03 L1), and SVG centers ring strokes on the
  radius while the manifest preview paints them inward (ring
  `svg_vs_preview_l1_error` up to 0.16 with the SVG closer to the source).

## Fixtures and Gallery

- The primitive fixture suite covers 159 cases across rects, squares, circles,
  rings, strokes, rounded rects, quads, anti-aliased and palette-drift
  variants, transparency, compositions, cut-outs, and groups.
- There is no fixture family for arcs, smooth curves, ellipses, curved
  cut-outs, or organic fallbacks.
- The public primitive gallery has no freeform curve coverage. The gallery
  header now states this explicitly until curve families pass.
- The `primitive-check` report records `anchor_kind_counts` and
  `curve_anchor_kind_counts` so curve coverage is measurable instead of
  anecdotal. At baseline every curve kind counts zero.

## Known Real-Image Gaps That Need Curves

- Curved letterforms and round badge outlines in curated real images currently
  fragment into quads or are dropped to the generic fallback.
- Smile-like arcs and curved underlines become either a bowed
  `stroke_polyline` rendered as two chords or an `arc` that still exports as a
  polyline path.

Both gaps must be reproduced as synthetic FQ families before any detector
tuning (FQ11 rule).
