# Real Image Assessment: ChatGPT Image 2026-06-11

Source path:

`assets/curated/terminaro-opaque-table-grid.png`

## Image Facts

- PNG, 1254 x 1254.
- Checked-in opaque RGB fixture derived from the local transparent Terminaro
  image.
- 254 unique RGBA values after loading, mostly antialiasing and subtle fill
  variations over an opaque white background.
- Major colors include near-white background/fills, navy figure regions, gold
  circles/ring elements, and beige table tiles.

Observed via local inspection:

- top colors by count include:
  - white `(255, 255, 255, 255)`
  - near-white `(254, 253, 253, 255)`
  - navy `(0, 37, 84, 255)`
  - near-white `(253, 253, 253, 255)`
  - gold `(182, 127, 19, 255)`

## Current Prototype Behavior

Bounded run:

```sh
PYTHONPATH=src python3 -m morphea.cli vectorize \
  assets/curated/terminaro-opaque-table-grid.png \
  -o /private/tmp/morphea-chatgpt-example.svg \
  --color-tolerance 18 \
  --max-size 256 \
  --max-colors 10 \
  --max-component-area 12000 \
  --timeout-seconds 8 \
  --min-area 12
```

Result:

- Completed successfully as part of the curated suite.
- Wrote SVG, JSON manifest, promotion sidecars, and contact sheet.
- Produced 62 anchors:
  - 14 `quad`
  - 13 `cubic_path`
  - 12 `stroke_path`
  - 9 `stroke_polyline`
  - 6 `arc`
  - 5 `circle`
  - 2 `rect`
  - 1 `stroke_circle`
- Reported one `perspective_grid` group for the table quads.
- Reported `simple_shape_ratio=0.790323`, `fragmentation_penalty=0.467742`,
  `parameter_economy=0.268145`, `raster_l1_error=0.057522`, and
  `raster_edge_error=0.014766`.
- Diagnostics included:
  - `image_resized_for_analysis` from 1254 x 1254 to 256 x 256
  - `palette_quantized` with max 10 colors
- Semantic expectations pass.
- The structure gate now treats `cutout_overlays` as review-visible
  non-structural layers: raw `layer_count` remains 4, while
  `structural_layer_count=3` satisfies the threshold.
- v10 fragmentation now scores unstructured fallback fragments instead of all
  same-color primitives, so expected table cells, circles, and cutout strokes
  no longer block review.
- Organic fallback node-budget capping reduces generated-illustration
  parameter debt above the 0.25 review threshold.
- The opt-in quality-label review policy now treats the remaining red quality
  label as `manual_review_pending`, so promotion is deferred and editability
  review has no failed components for this case.

## Expected Semantic Anchors

High-priority anchors:

- Outer gold circular border as `stroke_circle` or arc stroke.
- Three gold center dots as true `circle` anchors.
- Gold shoulder brooches as true circles.
- Table cells as perspective quads grouped into a grid.
- Hair, clothing, and table lines as editable strokes when line-like.

Secondary anchors:

- Large navy figure regions as larger filled paths after primitive anchors are
  reserved.
- Beige tile fills as quads or grouped regions.
- White cut-outs as editable overlay strokes where they are visually important.

## Curated Suite Entry

- Defined in `docs/real-images/suite.json`.
- Uses the same bounded config as the probe run.
- Checks minimum semantic expectations for:
  - circle anchors
  - table quad anchors
  - one perspective grid group
  - editable stroke anchors counted across stroke polylines, stroke paths, and
    arcs

## Milestone Mapping

- M1 keeps the case bounded with resizing, palette quantization, and timeout
  controls.
- M2 should improve outer-ring and cut-out stroke recognition.
- M3 should keep the table and repeated line structures grouped.
- M10 uses this case to broaden the curated suite beyond the transparent
  `terminaro-tweaked.png` variant.
