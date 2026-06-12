# Primitive Quality Roadmap

This roadmap is the active plan for making Morphēa reliable on primary forms
and then on combinations of primary forms. It deliberately starts with boring,
deterministic cases before returning to homepage examples or complex curated
illustrations.

## Goal

Morphēa should recognize simple visual intent as editable SVG primitives and
prove that recognition with a round-trip check:

1. generate or load a known raster input;
2. vectorize it;
3. inspect the semantic manifest/SVG;
4. render the recognized output back to pixels;
5. compare source and rendered output with a small tolerance;
6. fail loudly when geometry, primitive kind, bounds, or visual fidelity drift.

Visual similarity is necessary but not enough. A square that renders correctly
as a noisy path is still wrong. A circle that is visually close but represented
as many polygon/path fragments is also wrong. Every milestone below has both
semantic contracts and pixel round-trip contracts.

## Current Baseline

Implemented now:

- `morphea primitive-check`
- fixed single-primitive fixtures for square, rectangle, circle, three strokes,
  ring, rounded rectangle, and quad
- per-case JSON/Markdown results
- optional per-case artifacts: input PNG, output SVG, debug SVG, manifest JSON,
  rendered preview PNG
- geometry checks for kind, coordinates, bounds, stroke width, and bounding-box
  IoU
- raster checks for L1, edge error, alpha error, and size match
- first detector tightening for straight strokes and oversized arc candidates

This is the first step, not the finish line. The next work is to expand the
fixture space without weakening the contracts.

## Working Rules

- Add the smallest failing fixture before changing detection logic.
- Keep generated fixtures deterministic unless a milestone explicitly adds
  seeded variants.
- A case is not passing unless both semantic geometry and rendered pixels pass.
- Do not promote real-image or homepage examples until their underlying fixture
  family is green.
- Keep every detector relaxation paired with a stricter rejection test for a
  known false positive.
- Store enough artifacts that failures can be inspected without rerunning the
  command.

## Gate Levels

### Gate A: Semantic Contract

Each case must assert:

- expected primitive kind or narrow allowed-kind set;
- expected anchor count;
- no unexpected `cubic_path` fallback;
- no giant bounds or out-of-canvas geometry;
- expected color;
- expected geometry within tolerance:
  - quad/rect: four corners;
  - circle/ring: center, radius, stroke width where relevant;
  - stroke: centerline points, width, caps/joins when relevant.

### Gate B: Visual Round Trip

Each case must assert:

- rendered size matches source;
- `raster_l1_error` is below the case threshold;
- `raster_edge_error` is below the case threshold;
- `bbox_iou` is above the case threshold;
- alpha error is checked for transparent fixtures once those are added.

### Gate C: Regression Envelope

Each milestone should produce:

- a stable report artifact;
- an updated test covering every new fixture family;
- documented thresholds and why they are acceptable;
- a curated smoke run only after primitive gates pass.

## Milestones

### PQ0: Fixed Single Primitives

Status: implemented.

Purpose: prove that the core primitive loop works on one isolated shape.

Fixture families:

- filled square
- filled rectangle
- filled circle
- horizontal stroke
- vertical stroke
- diagonal stroke
- outlined ring
- rounded rectangle
- simple quad

Exit criteria:

- `morphea primitive-check` passes all fixed cases.
- The unit suite passes.
- A curated smoke run is checked after the primitive gate.

### PQ1: Harness Hardening

Purpose: make the primitive harness convenient enough to use for months.

Implementation work:

- Add `--case` or `--filter` so one fixture can be rerun quickly.
- Add stable failure categories: `wrong_kind`, `wrong_count`,
  `geometry_drift`, `visual_drift`, `fallback_path`, `bounds_escape`.
- Add a compact per-case diff block showing expected vs actual geometry.
- Add a JSON config/spec loader only when the in-code fixture list becomes hard
  to review.
- Add a command suitable for CI that exits non-zero when any case fails.

Exit criteria:

- A developer can run one failing case in isolation.
- Reports make it obvious whether the failure is segmentation, candidate
  ranking, geometry fitting, rendering, or threshold selection.

### PQ2: Primitive Variant Matrix

Status: implemented for deterministic single-primitive variants.

Purpose: prove single primitives across position, size, and style variation.

Fixture families:

- squares at multiple sizes and positions;
- rectangles with aspect ratios from near-square to long bars;
- circles at small, medium, and large radii;
- rings with several stroke widths;
- strokes with width 1-8 px;
- diagonal strokes at common angles;
- rounded rectangles with several corner radii;
- quads including trapezoid and parallelogram subtypes.

Implementation work:

- Generate seeded deterministic variants from each fixed spec.
- Keep each variant's expected geometry explicit after generation.
- Record aggregate pass/fail by primitive family.
- Add thresholds per family, not one global loose threshold.

Exit criteria:

- Each primitive family has at least 10 deterministic variants.
- No family relies on `cubic_path` for simple expected shapes.
- Visual thresholds are tight enough that a visibly shifted shape fails.

Current evidence:

- 90 deterministic primitive cases run through `morphea primitive-check`.
- square, rectangle, circle, horizontal/vertical/diagonal stroke, ring, rounded
  rectangle, and quad families each have 10 variants.
- regressions cover 1 px strokes, wide filled rectangles, and skewed quads so
  variants drive detector behavior instead of only looser thresholds.

### PQ3: Anti-Aliased and Palette-Drift Primitives

Status: implemented for deterministic RGB anti-aliasing, near-flat palette
drift, and transparent-circle fixtures.

Purpose: handle the exact kind of raster edges produced by design tools and AI
image outputs without fragmenting simple shapes.

Fixture families:

- anti-aliased filled circles;
- anti-aliased rings;
- anti-aliased strokes;
- near-flat color drift on one primitive;
- transparent background fixtures;
- partial-alpha edge fixtures.

Implementation work:

- Add source images rendered at higher resolution and downsampled.
- Add explicit background/alpha expectations.
- Compare exact-color vs color-tolerance runs.
- Add diagnostics expectations for alpha flattening and palette quantization.

Exit criteria:

- Anti-aliased primitives still collapse to one intended primitive.
- The same fixture fails without the needed preprocessing when that failure is
  expected and documented.
- Transparent background handling does not create phantom shapes.

Current evidence:

- anti-aliased circle, ring, and stroke families each have 3 deterministic
  variants using high-resolution source rendering and downsampling.
- palette-drift fixtures use explicit color tolerance while preserving the
  intended representative primitive color.
- transparent circle fixtures validate alpha-aware raster comparison and do not
  create background phantom anchors.

### PQ4: Non-Touching Primitive Compositions

Status: implemented for deterministic separated composition fixtures.

Purpose: prove that multiple independent primary forms are detected together
without merging, dropping, or inventing shapes.

Fixture families:

- two separated shapes with the same color;
- two separated shapes with different colors;
- circle plus stroke;
- square plus circle;
- ring plus dot;
- several dots aligned in a row;
- multiple strokes in one canvas.

Implementation work:

- Extend contracts to assert multiple anchors by id or by geometry matching.
- Match expected primitives to actual anchors by kind/color/bounds, not by
  output order alone.
- Add per-anchor visual bounds and per-scene aggregate raster checks.

Exit criteria:

- Anchor count matches the expected primitive count.
- Same-color separated shapes stay separate unless a later grouping rule says
  otherwise.
- Geometry matching is stable when output order changes.

Current evidence:

- the primitive harness now performs order-independent expected-to-actual
  matching by kind, color, bounds, and geometry.
- each non-touching composition family has 3 deterministic variants:
  same-color separated shapes, different-color separated shapes, circle plus
  stroke, square plus circle, ring plus dot, aligned dot rows, and multiple
  strokes.
- reports include `matches`, `unmatched_expected`, and `unexpected_actual` so
  multi-anchor failures identify dropped or invented primitives directly.

### PQ5: Touching and Adjacent Primitive Compositions

Status: implemented for adjacent rectangle merge/separate policy fixtures.

Purpose: handle cases where primitive boundaries meet or nearly meet.

Fixture families:

- adjacent rectangles sharing an edge;
- same-color adjacent rectangles that should merge;
- different-color adjacent rectangles that should not merge;
- circle touching a stroke;
- stroke crossing a rectangle;
- small gaps between primitives;
- overlapping primitives with clear draw order.

Implementation work:

- Add layer/order expectations to contracts.
- Add merge-policy expectations: separate, merge, or manual-review.
- Add gap tolerance checks so tiny raster gaps do not become bogus shapes.
- Add visual round-trip checks for occlusion and overlap.

Exit criteria:

- The pipeline can explain whether touching shapes were kept separate or
  intentionally merged.
- Overlap does not create giant fallback regions or false arcs.

Current evidence:

- adjacent different-color rectangles stay as separate anchors.
- adjacent same-color rectangles with a shared edge are accepted as a merged
  filled rectangle.
- same-color rectangles with a small visible gap stay separate.

Remaining:

- add stricter crossing/overlap fixtures for stroke-over-rectangle and
  circle-touching-stroke cases once their merge policy is explicit enough to
  avoid ambiguous contracts.

### PQ6: Cut-Outs, Holes, and Negative Space

Status: implemented for editable thin horizontal and diagonal cut-out stroke
fixtures.

Purpose: make white/near-background interior marks editable without treating
every hole as a destructive topology problem.

Fixture families:

- rectangle with a white straight cut-out stroke;
- circle with a white cut-out stroke;
- thick stroke with an inner highlight;
- ring as `stroke_circle`;
- donut-like filled shape where a hole should not become a white overlay;
- negative-mask export comparisons.

Implementation work:

- Add expected cut-out anchor contracts.
- Compare `overlay_stroke` and `negative_mask` exports.
- Add false-positive tests for large holes that are not thin cut-outs.
- Add rendered-output checks for cut-out placement and width.

Exit criteria:

- Thin cut-outs become editable strokes.
- Large holes do not masquerade as thin cut-out strokes.
- Export strategy does not change the semantic manifest unexpectedly.

Current evidence:

- horizontal and diagonal white interior gaps are checked as `stroke_polyline`
  anchors with `stroke.is_cutout=true`.
- each cut-out fixture family has 3 deterministic variants.
- focused detector tests already cover the negative case where a large hole must
  not become a thin cut-out stroke.

Remaining:

- add fixture-level `negative_mask` vs `overlay_stroke` export comparisons after
  the homepage gallery can expose both SVG outputs cleanly.

### PQ7: Repeated Structures and Groups

Status: implemented for repeated primitive group contracts.

Purpose: validate groups made from primitives, not just individual shapes.

Fixture families:

- parallel stroke groups;
- row of dots;
- simple grid of axis-aligned rectangles;
- perspective tile row;
- perspective tile grid;
- repeated same-color fragments that should be reviewed or merged.

Implementation work:

- Add group-level contracts:
  - `parallel_stroke_group`;
  - `perspective_grid`;
  - `same_color_fragment_group`;
  - `primitive_anchor_reservation`.
- Assert row/column counts and group membership.
- Add spacing and vanishing diagnostics thresholds.

Exit criteria:

- Repeated structures are visible in `groups`, not only as unrelated anchors.
- Grouping errors fail even when individual anchors look acceptable.

Current evidence:

- primitive-check can assert expected manifest groups.
- parallel stroke groups, dot rows/columns as same-color fragment groups, and
  quad rows/grids as `perspective_grid` groups each have 3 deterministic
  variants.
- reports include `group_matches`, and group failures use the stable
  `group_drift` category.

### PQ8: Structure-Preserving Refinement Gates

Status: implemented as an optional primitive-check refinement gate.

Purpose: improve coordinates and raster fidelity without breaking editability.

Fixture families:

- shifted circle/ring fits;
- slightly noisy rectangle/quad boundaries;
- strokes with small endpoint drift;
- anti-aliased shapes where local refinement should help.

Implementation work:

- Run `morphea refine` on selected primitive-check cases.
- Add before/after objective reports per case.
- Require structure audit preservation.
- Reject refinement when primitive kind, anchor count, layer, or group
  semantics change.

Exit criteria:

- Refinement improves or preserves visual metrics.
- No accepted refinement turns simple primitives into generic paths.

Current evidence:

- `primitive-check --refine --refinement-iterations N` runs the local
  structure-preserving refinement path for selected cases.
- the gate fails if structure/editability are not preserved or if L1/edge
  metrics regress beyond the allowed epsilon.
- focused tests cover a refined filled-circle primitive case.

### PQ9: Real-Image Promotion

Status: implemented as an explicit curated-to-primitive family map.

Purpose: move from synthetic confidence to representative real examples only
when the supporting primitive families are green.

Implementation work:

- Map each real-image expectation to a primitive fixture family.
- Add a real image only when its core primitive family passes PQ2-PQ7.
- Keep the curated suite focused on known semantics:
  circles, rings, strokes, quads, grids, cut-outs, and groups.
- Do not use broad aggregate metrics as proof if they are inflated by false
  primitives.

Exit criteria:

- Curated expectations are explainable by fixture-backed behavior.
- Real-image failures create new primitive/composition fixtures before detector
  changes.

Current evidence:

- [real-images/primitive-family-map.md](real-images/primitive-family-map.md)
  maps each curated real-image expectation to the primitive fixture families
  that must stay green first.
- curated smoke remains secondary to `primitive-check`; broad metric regressions
  should produce a primitive fixture before detector scoring changes.

### PQ10: Honest Basic Gallery

Purpose: publish examples only after they are backed by passing contracts.

Implementation work:

- Generate gallery assets from `primitive-check` artifacts.
- Show input bitmap, rendered preview, primitive kind, coordinates, node count,
  and raster errors.
- Exclude complex illustrations until their primitive families and composition
  contracts pass.

Exit criteria:

- Every gallery panel points to a passing report case.
- The homepage no longer uses hand-drawn diagrams as proof of vectorization
  quality.

## Suggested Work Order

1. Finish PQ1 so failing cases are fast to isolate.
2. Build PQ2 for deterministic single-primitive variants.
3. Add PQ3 for anti-aliasing and alpha handling.
4. Add PQ4 for non-touching multi-shape scenes.
5. Add PQ5 for touching/overlap behavior.
6. Add PQ6 for cut-outs and holes.
7. Add PQ7 for grids and repeated groups.
8. Run PQ8 refinement only after initialization is semantically correct.
9. Promote real images through PQ9.
10. Build the homepage/gallery through PQ10.

## Default Commands

Run the primitive gate:

```sh
PYTHONPATH=src python3 -m morphea.cli primitive-check \
  -o runs/primitive-quality/report.json \
  --output-dir runs/primitive-quality/cases \
  --markdown runs/primitive-quality/report.md
```

Run the full unit suite:

```sh
PYTHONPATH=src python3 -m unittest discover -s tests
```

Run the curated smoke after primitive gates pass:

```sh
PYTHONPATH=src python3 -m morphea.cli curated-check \
  docs/real-images/suite.json \
  -o runs/curated-smoke/report.json \
  --output-dir runs/curated-smoke/cases \
  --markdown runs/curated-smoke/report.md \
  --run
```

## Done Means

A milestone is done only when:

- fixtures exist;
- tests cover the fixture family;
- `primitive-check` reports all relevant cases green;
- visual thresholds are tight enough to catch visible drift;
- semantic contracts catch wrong primitive kinds and fallback paths;
- docs explain what the milestone proves and what it still does not prove.

This roadmap should be updated whenever a new failure class appears. The update
should happen before broad detector changes, so the work keeps moving forward
through explicit gates instead of subjective visual inspection alone.
