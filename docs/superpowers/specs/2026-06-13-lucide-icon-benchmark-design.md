# Lucide Icon Benchmark Design

## Summary

Add a focused Lucide-backed benchmark track for definitive stroke icon shapes.
The goal is to render a curated subset of Lucide SVG icons to 64x64 PNG inputs,
run them through Morphea, and verify both raster fidelity and editable semantic
structure.

This benchmark exposes cases the current primitive and curated logo suites
do not stress enough: connected stroke glyphs, stroked rounded rectangles,
circle-plus-line compounds, corner brackets, arrows, crosses, and icon-sized
multi-stroke compositions.

## Current Evidence

A temporary proof of concept used `lucide-static@1.18.0`, which is ISC licensed
and ships individual SVG files. Rendering selected icons to 64x64 PNGs with
`rsvg-convert`, then running `morphea vectorize`, produced useful failures:

- `chevron-right`, `mouse-pointer`, `badge-check`, and `eye` are broadly
  tractable.
- `plus`, `x`, and `square` look visually close but become `cubic_path`
  fallbacks instead of editable strokes or stroked rectangles.
- `search`, `zoom-in`, and `alarm-clock` lose important compound structure,
  showing that connected or touching stroke components need decomposition into
  circle, line, and path anchors.
- `scan-line`, `image`, and `move` stress corner joins, stroke rectangles,
  arrows, and separated/near-touching stroke components.

The proof of concept changed no repository files.

## Goals

- Pin a small, reviewable Lucide subset rather than benchmark the entire icon
  library.
- Render deterministic 64x64 PNG fixtures from the selected source SVGs.
- Compare Morphea output against explicit semantic contracts and exported-SVG
  raster metrics.
- Create failing cases before detector changes.
- Keep the benchmark useful as a milestone gate and gallery evidence source.

## Non-Goals

- Do not ingest all Lucide icons.
- Do not train on Lucide SVG source data.
- Do not treat visual similarity alone as success.
- Do not tune detector behavior directly against a broad aggregate score.
- Do not require network access during normal tests.

## Source and Licensing

Use Lucide static SVG files from `lucide-static@1.18.0` as the initial source.
Lucide is ISC licensed, so the benchmark will vendor a small selected subset of
source SVG files and a local copy of the license notice.

The implementation stores only selected source icons, not the full npm package:

- `assets/lucide/LICENSE`
- `assets/lucide/suite.json`
- `assets/lucide/icons/*.svg`

Each selected SVG remains close to upstream source form, preserving the
license comment where present.

## Initial Icon Set

Start with 24 icons split by contract family:

- LIC1 simple stroke glyphs:
  `plus`, `x`, `minus`, `equal`, `chevron-right`, `chevron-left`,
  `arrow-left-right`, `mouse-pointer`
- LIC2 circle and compound strokes:
  `circle`, `search`, `zoom-in`, `crosshair`, `alarm-clock`, `badge-check`,
  `eye`, `share-2`
- LIC3 stroked rectangles and UI glyphs:
  `square`, `image`, `credit-card`, `sheet`, `laptop-minimal`, `scan-line`,
  `move`, `frame`

This set is intentionally cherry-picked. It covers high-signal geometric
families without pretending to represent the whole Lucide library.

## Harness Design

Add a Lucide-specific benchmark command that follows the existing
`primitive-check` and `curated-check` pattern:

```sh
morphea lucide-check assets/lucide/suite.json \
  -o runs/lucide/report.json \
  --output-dir runs/lucide/cases \
  --markdown runs/lucide/report.md
```

The harness will:

1. Load each selected SVG and its expected contract from `suite.json`.
2. Render the source SVG to a 64x64 PNG input using an available renderer.
3. Run Morphea with pinned default settings for this benchmark.
4. Write per-case artifacts:
   - source SVG copy;
   - rendered input PNG;
   - Morphea output SVG;
   - debug SVG;
   - manifest JSON;
   - rasterized output PNG;
   - contact-sheet preview when the report requests visual comparison.
5. Evaluate semantic contracts and raster metrics.
6. Write aggregate JSON and Markdown reports.

## Rendering Policy

Use `rsvg-convert` when available for source SVG to PNG rendering. If it is not
available, fall back to CairoSVG when installed. If neither renderer is
available, the command must fail with an explicit capability error for the
Lucide source render step rather than silently skipping the benchmark.

The benchmark renders black strokes on a white background at 64x64. This
matches common icon usage and avoids transparent-background ambiguity during the
first milestone.

## Semantic Contracts

Each case asserts a narrow expected structure:

- expected allowed anchor kinds;
- expected minimum and maximum anchor count;
- maximum `cubic_path` count, often zero for definitive stroke glyphs;
- expected simple-shape ratio floor;
- required group kinds for repeated or related strokes when the case contract
  needs them;
- per-family raster thresholds for exported SVG output;
- no unexpected oversized bounds or out-of-canvas geometry.

Example contract intent:

- `plus`: two `stroke_polyline` anchors, no `cubic_path`.
- `x`: two diagonal `stroke_polyline` anchors, no `cubic_path`.
- `search`: one `stroke_circle` and one handle stroke.
- `zoom-in`: one `stroke_circle`, one handle stroke, and two internal strokes.
- `square`: one stroked rounded-rectangle representation or an accepted
  stroke-rectangle group, no filled organic fallback.
- `scan-line`: four corner-bracket strokes plus one center stroke.

If the current scene model lacks a perfect primitive kind, the contract will
prefer an explicit transitional allowed structure over broad fallback success.

## Milestones

### LIC0: Lucide Harness

Purpose: make the benchmark reproducible and inspectable before detector work.

Exit criteria:

- selected SVG subset and license notice are checked in;
- `morphea lucide-check` can render and vectorize the selected icons;
- reports show per-case semantic results and exported-SVG raster metrics;
- failing cases are visible in `lucide-check`; the normal unit suite gates only
  the harness mechanics until each LIC family is promoted.

### LIC1: Simple Stroke Glyphs

Purpose: recover definitive connected and crossing line icons as editable
strokes.

Initial cases:

- `plus`
- `x`
- `minus`
- `equal`
- `chevron-right`
- `chevron-left`
- `arrow-left-right`
- `mouse-pointer`

Exit criteria:

- crossing and touching line glyphs do not collapse to `cubic_path`;
- straight and diagonal strokes keep stable endpoints, width, and caps;
- exported SVG raster metrics stay within family thresholds.

### LIC2: Circle and Compound Strokes

Purpose: decompose circle-plus-stroke icons into editable semantic parts.

Initial cases:

- `circle`
- `search`
- `zoom-in`
- `crosshair`
- `alarm-clock`
- `badge-check`
- `eye`
- `share-2`

Exit criteria:

- circles and rings remain circle primitives;
- handles, ticks, hands, and inner marks remain selectable strokes;
- touching compounds do not erase or absorb adjacent primitives.

### LIC3: Stroked Rectangles and UI Glyphs

Purpose: represent outline UI shapes as editable stroke geometry rather than
filled fallback outlines.

Initial cases:

- `square`
- `image`
- `credit-card`
- `sheet`
- `laptop-minimal`
- `scan-line`
- `move`
- `frame`

Exit criteria:

- stroked rectangles and rounded rectangles receive explicit editable
  structure;
- corner brackets and arrowheads remain bounded stroke paths;
- multi-stroke icons preserve anchor count and visual stacking.

## Architecture Notes

Keep the Lucide harness separate from `primitive_quality.py` initially. That
file is already large and focused on generated fixtures. A small
`lucide_quality.py` module can reuse shared functions for vectorization,
manifest loading, SVG raster metrics, and report rendering.

Shared helpers can be extracted later only if repetition becomes
material between primitive, curated, and Lucide checks.

## Testing Strategy

- Unit tests for suite loading, renderer capability selection, and contract
  evaluation.
- A focused smoke test with one or two vendored icons that does not require
  network access.
- Full `lucide-check` run as a developer command; CI promotion is a later
  explicit decision after LIC1 is green.
- Existing gates must remain green:

```sh
PYTHONPATH=src python3 -m unittest discover -s tests
PYTHONPATH=src python3 -m morphea.cli primitive-check -o /tmp/primitive.json --baseline
```

## Reporting

The Markdown report will lead with a family summary:

- case count;
- pass/fail count;
- anchor kind counts;
- generic fallback count;
- SVG raster L1 and edge error ranges;
- failure categories such as `wrong_kind`, `wrong_count`, `fallback_path`,
  `visual_drift`, and `bounds_escape`.

Per-case rows include source icon name, actual anchor kinds, expected
contract summary, raster metrics, and artifact directory.

## Risks

- Lucide source paths are stroke-first SVGs, while Morphea sees only rasterized
  pixels. The benchmark must judge recovered editable intent, not exact SVG
  command identity.
- Some icons use intentional compound paths that are visually one continuous
  mark. Contracts avoid overfitting to upstream path boundaries when a
  different editable decomposition is equally useful.
- Renderer differences can affect thresholds. Pin 64x64 rendering and keep
  thresholds family-specific.
- The first implementation will likely produce many red cases. That is useful
  as long as the report is explicit and the normal baseline remains stable.

## Recommendation

Implement LIC0 first, then use the initial failed cases to drive LIC1. The
highest-value detector gap is connected stroke decomposition: `plus`, `x`,
`square`, `search`, and `zoom-in` already show clear failures that are easy to
inspect and explain.
