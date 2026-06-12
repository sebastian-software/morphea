# Freeform Arc Quality Status

This document records what the implementation can and cannot do for curved
forms. It mirrors the code, not ambitions, and is updated per milestone. See
`freeform-arc-quality-roadmap.md` for the plan.

## Detector

- Arcs are fitted as circular stroke bands: a whole-pixel Kåsa fit, a refit
  through per-angle-bin centerline midpoints, dual width estimation, round
  cap angle trimming, and rejections for closed rings, low angular coverage,
  non-circular centerlines (midpoint residual), and tapered fills (radial
  band uniformity).
- `stroke_path` is fitted from a functional per-column centerline bounded to
  7 control points with cap classification by end taper and near-constant
  width enforcement; honest straight strokes stay two-point
  `stroke_polyline` anchors.
- `ellipse` and `stroke_ellipse` are fitted from bounds plus a pixel-unit
  boundary-ray residual; near-round shapes stay circles, sub-9 px minors and
  stadium shapes stay rounded rects.
- Cut-outs run entirely on enclosed gap components with their own functional
  centerline, so straight, diagonal, and curved gaps share one path; bowed
  gaps become smooth `stroke_path` overlays.
- The `cubic_path` fallback carries a Moore-traced outline bounded to 16
  nodes with `fallback_reason` and ranks behind every semantic candidate via
  a flat penalty.

## Scene Model and SVG Export

- Arcs carry `ArcAnchor` parameters (center, radius, angle range, sweep,
  large-arc) and export as a single SVG `A` path with round caps.
- `stroke_path` anchors with three or more control points export Catmull-Rom
  derived cubic `C` segments; organic `cubic_path` outlines export closed
  Catmull-Rom `C` loops ending in `Z`.
- Ellipses export as `<ellipse>` elements, filled or stroked.
- The manifest serializes arc parameters, ellipse radii, organic path points
  with node counts and `fallback_reason`, and stroke caps/joins.

## Renderer and Quality Gates

- The manifest preview renderer samples the same fitted circle, Catmull-Rom
  spline, or closed outline that the SVG export emits, including round caps,
  so preview and SVG stay within tight `svg_vs_preview_l1_error` budgets.
- Every fixture rasterizes the actual exported SVG through the builtin
  supersampling backend in `svg_raster.py` and gates `svg_raster_l1_error`,
  `svg_raster_edge_error`, `svg_alpha_error`, and `svg_vs_preview_l1_error`
  per family. The backend covers the exported subset including `A`/`Q`/`C`
  path commands and the negative cut-out mask, and is cross-checked against
  `rsvg-convert` when that binary is installed.
- Known systematic offset the derived SVG thresholds account for: SVG
  polygons cover the mathematical area while PIL sources fill inclusive
  pixels (quads measure up to 0.03 L1).

## Milestone Status

All roadmap milestones through FQ12 are implemented and green:

- FQ0 baseline inventory: this document plus `anchor_kind_counts` /
  `curve_anchor_kind_counts` in every `primitive-check` report.
- FQ1 SVG raster gate: builtin supersampling backend in `svg_raster.py`,
  gated per family, cross-checked against `rsvg-convert` when installed.
- FQ2 simple arcs: 24 cases, 8 families, circular band fit with endpoint,
  bow, width, and cap contracts.
- FQ3 smooth arc export: `ArcAnchor` parameters export as one SVG `A` path;
  preview samples the same circle.
- FQ4 smooth stroke paths: 21 cases, 7 families, bounded control points,
  Catmull-Rom `C` export, cap classification.
- FQ5 ellipses: 21 cases, 7 families, `ellipse`/`stroke_ellipse` primitives
  with circle/rounded-rect/capsule rejections.
- FQ6 curved cut-outs: 15 cases, 5 families, unified gap-component cut-out
  detection, smooth overlay export, negative-mask comparison.
- FQ7 anti-aliased and palette-drift curves: 15 cases, 5 families.
- FQ8 curve compositions: 21 cases, 7 families including parallel arc groups
  and curve-cut rect promotion.
- FQ9 organic fallback: 15 cases, 5 families; `cubic_path` carries a traced
  16-node outline, closed `C` export, `fallback_reason`, and ranks behind
  every semantic candidate.
- FQ10 refinement gate: per-anchor parameter deltas; control-point budget and
  cap/join are enforced.
- FQ12 gallery: kind and contract filters for arcs, smooth curves, ellipses,
  curved cut-outs, and organic fallbacks; every card shows bitmap, exported
  SVG, and the rasterized SVG; the homepage teaser stays small.

The fixture suite stands at 291 deterministic cases (159 baseline + 132
freeform/curve cases), all passing both the manifest preview and the exported
SVG raster gates.

## Regression Snapshot Baseline

The contract budgets are upper bounds, so quality can drift inside them
without failing anything. `tests/data/primitive-baseline.json` therefore
pins the exact outcome of every fixture case: detected kind, anchor and
node composition, preview and SVG raster metrics, and bounding-box IoU.

- `morphea primitive-check --baseline` (and the always-on
  `tests/test_primitive_baseline.py` suite guard) fail on any drift beyond
  a 0.002 noise tolerance, in both directions; improvements also require a
  deliberate baseline refresh so the pin never decays into a stale bound.
- After an intentional change run
  `morphea primitive-check -o <report> --update-baseline` and commit the
  regenerated file; the per-case movement is then reviewable in the diff.

## Hand-Made Real-Image Cases

Curated complex artwork lives in `assets/curated/`:

- Drop the PNG into `assets/curated/` (generators for synthetic stand-ins go
  into `assets/curated/sources/`).
- Add a case to `assets/curated/suite.json` with a `source`, a
  `recommended_config`, and honest `expectations` (anchor kinds with counts
  and manifest metrics such as `cutout_anchor_count`, `generic_path_count`,
  `editability_score`).
- `morphea curated-check assets/curated/suite.json --run` executes the suite;
  `tests/test_curated.py` runs it as part of the normal test suite.

The first case, `profile_head_synthetic`, is a deterministic stand-in for a
classical profile head: one organic silhouette (adaptive node budget,
~23 nodes), five curl slits and one eye slit detected as editable cut-out
arcs and strokes.

## FQ11: Real-Image Promotion Process

No real-image curve tuning ships without a synthetic contract first:

1. Map the failing real image to the closest FQ family (arc, smooth curve,
   ellipse, curved cut-out, composition, or organic fallback).
2. Reproduce the failure as a deterministic fixture in that family (or a new
   variant) and watch it fail for the same reason.
3. Only then adjust detector thresholds or fitting, keeping the full
   `primitive-check` suite green.
4. Run the curated real-image smoke (`morphea curated-check`) after detector
   changes when a curated suite file is available; curated metrics stay
   secondary to fixture-level correctness.

Known real-image gaps that still need this treatment:

- Curved letterforms in logos combine arcs, smooth curves, and organic
  fills inside a single connected component; the current pipeline handles
  them only when color separates the parts.
- Rotated (non-axis-aligned) ellipses are still detected as organic
  fallbacks; the roadmap defers them until the axis-aligned families have
  soaked.
