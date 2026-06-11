# Real Image Assessment: ChatGPT Image 2026-06-11

Source path:

`/Users/sebastian/Downloads/ChatGPT Image 11. Juni 2026, 20_46_25.png`

## Image Facts

- PNG, 1254 x 1254.
- Opaque white background.
- 36,241 unique RGBA colors after loading, mostly antialiasing and subtle
  fill variations.
- Major colors include near-white background/fills, navy figure regions, gold
  circles/ring elements, and beige table tiles.

Observed via local inspection:

- top colors by count include:
  - near-white `(254, 254, 254, 255)`
  - white `(255, 255, 255, 255)`
  - near-white `(253, 253, 253, 255)`
  - beige `(228, 213, 197, 255)`
  - navy `(0, 36, 83, 255)`

## Current Prototype Behavior

Bounded run:

```sh
PYTHONPATH=src python3 -m curve.cli vectorize \
  "/Users/sebastian/Downloads/ChatGPT Image 11. Juni 2026, 20_46_25.png" \
  -o /private/tmp/curve-chatgpt-example.svg \
  --color-tolerance 18 \
  --max-size 256 \
  --max-colors 10 \
  --max-component-area 12000 \
  --timeout-seconds 8 \
  --min-area 12
```

Result:

- Completed successfully under an external 15 second timeout.
- Wrote SVG and JSON manifest.
- Produced 54 anchors:
  - 19 `quad`
  - 19 `stroke_polyline`
  - 11 `cubic_path`
  - 5 `circle`
- Reported one `perspective_grid` group for the table quads.
- Diagnostics included:
  - `image_resized_for_analysis` from 1254 x 1254 to 256 x 256
  - `palette_quantized` with max 10 colors

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
  - smooth stroke anchors

## Milestone Mapping

- M1 keeps the case bounded with resizing, palette quantization, and timeout
  controls.
- M2 should improve outer-ring and cut-out stroke recognition.
- M3 should keep the table and repeated line structures grouped.
- M10 uses this case to broaden the curated suite beyond the transparent
  `terminaro-tweaked.png` variant.
