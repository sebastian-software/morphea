# Freeform Arc Quality Roadmap

This roadmap defines the next quality track after the current primitive
fixture baseline. Its goal is to make Morphēa reliable on curved, flowing
forms while preserving the same discipline that made the simple primitive
track useful: deterministic fixtures, semantic contracts, SVG round trips, and
small detector changes driven by failing cases.

## Goal

Morphēa should recognize curved visual intent as editable SVG primitives when
the input supports that interpretation:

1. open circular or elliptical arcs should become editable stroked arc paths;
2. smooth non-circular curves should become editable smooth stroke paths;
3. ovals and ellipses should become editable ellipse primitives;
4. curved cut-outs should remain editable overlay strokes or masks;
5. filled organic shapes should use a controlled path fallback with quality
   contracts instead of noisy accidental primitive anchors.

This track is not a license to accept visually close but semantically useless
paths. A curved shape only passes when the exported SVG is both editable and
visually faithful after rendering.

## Current Baseline

Implemented today:

- `arc` exists as an anchor kind.
- thin curved components can be detected as `arc` in focused detector tests.
- curved stroke centerlines can contain a middle control point.
- `arc`, `stroke_path`, and `stroke_polyline` export as SVG stroked paths.
- oversized arc false positives are rejected for ring-like and broad filled
  regions.
- the public primitive gallery has no arc or freeform curve cases yet.

Important limitations:

- the current `arc` SVG export is a polyline-style path, not a true smooth
  `Q`, `C`, or `A` command;
- there is no primitive-quality fixture family for arcs;
- visual gates currently rely mostly on manifest-rendered previews, while the
  recent adjacent-rect gap bug showed that real exported SVG rasterization must
  become a first-class gate;
- filled organic shapes still belong mostly to fallback territory and should
  not be mixed with arc work too early.

## Shape Classes

This track separates visually similar things that need different contracts.

### Open Stroke Arcs

Examples: smile arcs, curved underlines, partial ring borders, crescent-like
stroked marks.

Expected representation:

- `stroke_arc` or `arc` with endpoint, radius/center or equivalent smooth path
  parameters;
- SVG export as `path` using `A` for circular or elliptical arcs where possible;
- stable `stroke-width`, `stroke-linecap`, and `stroke-linejoin`.

### Smooth Stroke Paths

Examples: S-curves, loose hair-like strokes, flowing decorative lines.

Expected representation:

- `stroke_path` with a smooth centerline;
- SVG export as `Q` or `C` commands when the curve is not a single geometric
  arc;
- bounded number of control points;
- stable width samples.

### Ellipses and Ovals

Examples: non-circular dots, oval badges, distorted circular elements.

Expected representation:

- `ellipse` anchor for filled ovals;
- `stroke_ellipse` anchor for oval rings when needed;
- fallback to `quad` or `cubic_path` is not acceptable for clean oval fixtures.

### Curved Cut-Outs

Examples: white curved gaps through a colored area, clothing folds, hair
strands.

Expected representation:

- editable overlay `stroke_path` or `arc` in v1;
- optional negative-mask export comparison when the shape is truly a cut-out;
- base filled primitive must remain intact when the cut-out crosses it.

### Filled Organic Shapes

Examples: blobs, leaves, soft silhouettes, filled asymmetric curves.

Expected representation:

- controlled `cubic_path` fallback with low node count and smoothness
  constraints;
- no accidental giant arc, stroke, circle, ellipse, or rectangle candidates;
- later promotion to semantic shapes only when a clear class exists.

## Gate Levels

### Gate A: Semantic Curve Contract

Each freeform case must assert:

- expected anchor kind or narrow allowed set;
- expected anchor count;
- no unexpected `cubic_path` for clean stroked arcs, curves, ellipses, or
  cut-out strokes;
- endpoints within tolerance;
- centerline or arc control geometry within tolerance;
- stroke width within tolerance;
- cap and join style where visible;
- curvature direction and bow magnitude;
- no bounds outside the source component by more than tolerance;
- no unrelated giant stroke or arc component.

### Gate B: SVG Round Trip

Each case must render the actual exported SVG and compare it with the source:

- rendered SVG size matches source;
- `svg_raster_l1_error` below the family threshold;
- `svg_raster_edge_error` below the family threshold;
- alpha coverage is checked for transparent or cut-out fixtures;
- contact or crossing regions have no unintended gaps;
- anti-aliased fixtures use thresholds based on real exported SVG behavior.

Manifest-rendered previews may remain useful, but they are not enough for this
track.

### Gate C: Editability

Each case must assert that the output stays editable:

- clean arcs use one arc path or one smooth path, not many tiny segments;
- smooth curves have a bounded control-point count;
- ellipses use ellipse primitives;
- cut-out strokes remain selectable stroke primitives;
- filled organic fallbacks record path node count, smoothness, and fallback
  reason.

### Gate D: False-Positive Envelope

Every detector relaxation must add at least one rejection case:

- rings must not become oversized arcs;
- broad filled regions must not become strokes;
- rounded rectangles must not become arcs;
- diagonal strokes must not gain fake curve controls;
- partial occlusion must not create transparent gaps in the SVG output;
- noisy organic blobs must not be mislabeled as clean ellipses or arcs.

## Milestones

### FQ0: Baseline Inventory

Purpose: document exactly what the current implementation can and cannot do.

Work:

- list existing `arc`, `stroke_path`, and `cubic_path` behavior from detector,
  scene model, renderer, and gallery;
- add a small report section that shows kind counts for curve-like anchors;
- mark the current primitive gallery as "no freeform curve coverage yet";
- capture one or two known real-image failures that need curved forms.

Exit criteria:

- roadmap and current status agree with the code;
- no detector changes are made in this milestone;
- existing tests and `primitive-check` stay green.

### FQ1: SVG Raster Gate for Curves

Purpose: make the exported SVG itself testable before adding many curve cases.

Work:

- add an optional SVG rasterization path to the primitive harness;
- record `svg_raster_l1_error`, `svg_raster_edge_error`, and
  `svg_alpha_error`;
- compare manifest-rendered preview and exported-SVG render when both exist;
- fail when exported SVG diverges from the manifest preview beyond tolerance;
- keep the dependency isolated so environments without the SVG backend can
  report a clear skipped capability instead of silently passing.

Exit criteria:

- at least one existing rect/contact regression is checked through the SVG
  raster gate;
- reports distinguish manifest preview metrics from actual SVG metrics;
- `primitive-gallery` can display both metrics without hand-edited values.

### FQ2: Simple Arc Fixtures

Purpose: prove one clean open arc before tackling freeform curves.

Fixture families, at least 3 variants each:

- upward arc;
- downward arc;
- left-facing arc;
- right-facing arc;
- shallow arc;
- steep arc;
- thick arc;
- small-radius arc.

Contracts:

- one `arc` or `stroke_arc` anchor;
- endpoint coordinates within 1-2 px;
- bow direction correct;
- stroke width within tolerance;
- no fallback `cubic_path`;
- SVG render within family threshold.

Exit criteria:

- all simple arc families pass deterministic fixtures;
- failure output shows endpoint, bow, width, and SVG metric diffs.

### FQ3: True Smooth Arc Export

Purpose: stop treating arcs as broken polylines.

Work:

- add a scene-level representation for circular or elliptical arc parameters;
- fit center/radius or ellipse radii from the component where possible;
- export clean circular/elliptical arcs with SVG `A` commands;
- retain a smooth fallback path only when the geometry is not arc-like;
- add tests that assert the exported path contains the intended command class.

Exit criteria:

- simple arc fixtures export one editable smooth arc path;
- straight strokes still export as straight two-point strokes;
- rings still prefer `stroke_circle` or `stroke_ellipse` over arcs when closed.

### FQ4: Smooth Stroke Path Fixtures

Purpose: cover curved strokes that are not single arcs.

Fixture families, at least 3 variants each:

- simple quadratic curve;
- S-curve;
- loose wave;
- asymmetric curve;
- diagonal curve;
- curve with square caps;
- curve with round caps.

Contracts:

- expected kind is `stroke_path`;
- centerline has a bounded number of control points;
- line smoothness error below threshold;
- width variance below threshold;
- SVG export uses `Q` or `C` where appropriate;
- raster errors stay within threshold.

Exit criteria:

- non-arc curves no longer need to masquerade as `arc`;
- clean curves are not exported as long stair-step polylines.

### FQ5: Ellipse and Oval Primitives

Purpose: support distorted circular elements without forcing them into circles
or generic paths.

Fixture families, at least 3 variants each:

- filled horizontal ellipse;
- filled vertical ellipse;
- small ellipse;
- large ellipse;
- stroked ellipse;
- anti-aliased ellipse;
- rotated ellipse as a separate later family if the axis-aligned version is
  stable.

Contracts:

- expected kind is `ellipse` or `stroke_ellipse`;
- center, radii, and stroke width within tolerance;
- circle fixtures still prefer `circle`;
- rounded rectangles and capsules do not become ellipses.

Exit criteria:

- clean oval fixtures use editable ellipse primitives;
- ellipse false positives are covered by rect, rounded-rect, capsule, and blob
  rejection cases.

### FQ6: Curved Cut-Outs and Overlay Strokes

Purpose: handle white or background-colored curved gaps without punching
unintended visual holes.

Fixture families, at least 3 variants each:

- curved cut-out through a rectangle;
- curved cut-out through a circle;
- curved cut-out through a ring;
- crossing curved cut-out plus separate foreground primitive;
- near-background but not exact-white cut-out.

Contracts:

- base shape remains intact in manifest order;
- cut-out is editable as overlay stroke or negative mask;
- SVG render has no unintended gaps at crossings or contacts;
- `negative_mask_svg` and overlay export comparison remain available for
  inspection.

Exit criteria:

- curved cut-outs pass both overlay and optional negative-mask comparison;
- crossing cases do not create the gap failure seen in adjacent rects.

### FQ7: Anti-Aliased and Palette-Drift Curves

Purpose: make curve recognition work on realistic raster edges.

Fixture families, at least 3 variants each:

- high-res downsampled arcs;
- high-res downsampled S-curves;
- anti-aliased ellipses;
- near-flat color drift along a stroke;
- transparent-background curve fixtures.

Contracts:

- source preprocessing is explicit;
- representative color remains stable;
- fragmented edge colors do not create extra anchors;
- SVG raster metrics use slightly looser but documented thresholds.

Exit criteria:

- anti-aliased curves do not fragment into many tiny paths;
- exact-color failure modes are documented where color tolerance is required.

### FQ8: Curve Compositions

Purpose: prove curved forms interact with existing primitives.

Fixture families, at least 3 variants each:

- arc plus circle;
- arc plus rectangle;
- curve crossing rectangle;
- curve touching circle;
- ellipse plus stroke;
- multiple parallel arcs;
- curve group with shared color.

Contracts:

- expected anchor count and order-independent matching;
- crossings preserve the intended visual stacking;
- touching curves do not create gaps or merged accidental shapes;
- parallel arc groups record spacing consistency where applicable.

Exit criteria:

- curve compositions pass without weakening single-primitive thresholds;
- gallery cards expose kind, node count, SVG metrics, and contract badges.

### FQ9: Filled Organic Path Baseline

Purpose: define what "good fallback" means for filled freeform shapes.

Fixture families, at least 3 variants each:

- simple blob;
- leaf-like shape;
- asymmetric filled curve;
- crescent-like filled shape;
- smooth compound silhouette.

Contracts:

- expected kind is controlled `cubic_path` unless a semantic primitive exists;
- path node count below family threshold;
- no giant arc, ellipse, circle, rect, or stroke false positive;
- path smoothness and bounds are recorded;
- SVG raster error passes a broader but explicit fallback threshold.

Exit criteria:

- organic fallback is honest and inspectable;
- real-image organic failures can be mapped to synthetic families before
  detector tuning.

### FQ10: Curve Refinement Gate

Purpose: allow refinement to improve visual fidelity without destroying
semantic structure.

Work:

- add optional before/after refinement metrics for curve families;
- preserve anchor kind, cap/join, and control-point budget;
- reject refinements that lower raster error by adding noisy points;
- report parameter deltas for endpoints, controls, radii, and width samples.

Exit criteria:

- refinement improves or preserves SVG raster metrics;
- semantic contracts remain green after refinement.

### FQ11: Real-Image Promotion

Purpose: use real images only after synthetic curve families explain the
failure.

Work:

- map real-image curve failures to FQ fixture families;
- add synthetic reproduction before detector changes;
- run curated smoke only after relevant FQ families pass;
- document remaining real-image gaps honestly.

Exit criteria:

- no real-image curve improvement ships without a synthetic contract;
- curated metrics remain secondary to fixture-level correctness.

### FQ12: Honest Curve Gallery

Purpose: publish only curve demos that are backed by real passing artifacts.

Work:

- extend `primitive-gallery` filters for arcs, stroke paths, ellipses, and
  organic fallbacks;
- show input bitmap, exported SVG, and optional SVG-raster preview;
- add badges for `arc_contract`, `smooth_curve_contract`,
  `ellipse_contract`, `curved_cutout_contract`, and `organic_fallback`;
- keep homepage teaser small and link to the long QA page.

Exit criteria:

- every visible curve demo is generated from a passing fixture;
- failed or experimental families are absent or clearly marked as failing QA;
- no hand-drawn marketing illustration is presented as quality evidence.

## Fixture Growth Targets

Initial target:

- FQ2 simple arcs: 8 families x 3 variants = 24 cases.
- FQ4 smooth stroke paths: 7 families x 3 variants = 21 cases.
- FQ5 ellipses/ovals: 7 families x 3 variants = 21 cases.
- FQ6 curved cut-outs: 5 families x 3 variants = 15 cases.
- FQ7 anti-aliased/palette curves: 5 families x 3 variants = 15 cases.
- FQ8 curve compositions: 7 families x 3 variants = 21 cases.
- FQ9 filled organic fallback: 5 families x 3 variants = 15 cases.

That yields roughly 132 deterministic curve/freeform cases before seeded
random expansion.

Later target:

- 10 variants for stable core families;
- 100+ curve cases in the generated gallery;
- seeded random variants only after fixed deterministic cases are green.

## Data Model Additions

Likely scene-model additions:

- `ellipse`: center, rx, ry, rotation;
- `stroke_ellipse`: center, rx, ry, rotation, width;
- `stroke_arc`: start, end, center or radii, sweep/large-arc flags, width;
- `stroke_path`: smooth control points, width samples, cap, join;
- `cubic_path`: path commands, node count, smoothness metrics, fallback reason.

Manifest additions:

- `curve`: command class, endpoints, controls, curvature direction, bow ratio;
- `ellipse`: center, radii, rotation;
- `svg_metrics`: exported-SVG raster metrics;
- `fallback_reason`: explicit reason for controlled organic path output;
- `editability`: command count, control-point count, node budget status.

## Detector Strategy

The detector should follow this order:

1. closed circles and rings;
2. axis-aligned rects, rounded rects, and quads;
3. straight strokes;
4. closed ellipses and stroked ellipses;
5. single geometric arcs;
6. smooth non-arc stroke paths;
7. curved cut-out overlay strokes;
8. controlled organic paths;
9. generic fallback only when no semantic candidate passes.

Ranking rules:

- a simple semantic curve beats a generic path when visual error is within the
  family threshold;
- a generic path beats a bad arc when the arc bounds, width, or curvature are
  implausible;
- broad filled regions are never promoted to strokes only because their
  outline is curved;
- closed shapes must not be represented as open arcs unless the fixture
  explicitly asks for partial arcs.

## Test Plan

Run on every curve iteration:

- `PYTHONPATH=src python3 -m unittest discover -s tests`
- focused `primitive-check --case` or `--filter` for the family under work
- full `primitive-check`
- SVG raster gate for all curve families once FQ1 exists
- curated smoke after detector changes
- `git diff --check`

Focused tests to add:

- simple arc endpoint/bow/width contract;
- true SVG arc command export;
- smooth curve command export;
- ellipse center/radius contract;
- anti-aliased curve segmentation stability;
- curved cut-out overlay and negative-mask comparison;
- false-positive rejection for ring, rounded rectangle, capsule, blob, and
  diagonal stroke.

## Commit Strategy

Suggested modular commit order:

1. `docs: add freeform arc quality roadmap`
2. `feat: add svg raster metrics to primitive harness`
3. `feat: add simple arc primitive fixtures`
4. `feat: export smooth arc paths`
5. `feat: add smooth stroke path fixtures`
6. `feat: add ellipse primitive contracts`
7. `feat: add curved cutout contracts`
8. `feat: add antialias curve fixtures`
9. `feat: add curve composition gates`
10. `feat: add controlled organic fallback gates`
11. `feat: gate curve refinement`
12. `feat: publish curve quality gallery`

Each commit should be created only after the relevant focused tests, the full
primitive harness, and `git diff --check` pass.

## Non-Goals

- Do not solve arbitrary logo tracing in the first curve milestone.
- Do not accept noisy high-node paths as a success for clean arcs.
- Do not add random curve generation before fixed cases pass.
- Do not make homepage demos lead the work; generated QA artifacts lead.
- Do not tune real-image outputs without a synthetic fixture that reproduces
  the failure.

## Open Questions

- Should `arc` remain as the public kind name, or should the manifest introduce
  explicit `stroke_arc` while preserving `arc` as a compatibility alias?
- Should SVG rasterization be a required dependency in CI or an optional
  capability with a clear skip status?
- What is the first real-image failure we want to promote once FQ2-FQ4 are
  stable?
