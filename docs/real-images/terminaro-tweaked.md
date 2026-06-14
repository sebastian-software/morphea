# Real Image Assessment: terminaro-tweaked.png

Source path:

`/Users/sebastian/Desktop/terminaro-tweaked.png`

## Image Facts

- PNG, 1254 x 1254.
- Indexed/palette-style source, loaded as RGBA.
- 255 unique RGBA colors.
- Large transparent blue outside/background-like region.
- Major colors include near-white fills, dark navy figure shapes, gold rings
  and dots, beige table tiles, and several near-white/beige variants.

Observed via local inspection:

- top color by count is transparent `(38, 69, 201, 0)`.
- major opaque colors include:
  - near-white `(254, 253, 253, 255)`
  - navy `(0, 37, 84, 255)`
  - gold `(182, 127, 19, 255)`
  - beige variants around `(246, 240, 235, 255)` and `(231, 216, 202, 255)`

## Current Prototype Behavior

Updated M1 bounded run:

```sh
PYTHONPATH=src python3 -m morphea.cli vectorize \
  /Users/sebastian/Desktop/terminaro-tweaked.png \
  -o /tmp/morphea-terminaro-m1/terminaro.svg \
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
- Diagnostics included:
  - `image_resized_for_analysis` from 1254 x 1254 to 256 x 256
  - `palette_quantized` with max 10 colors and preserved navy, gold, and
    beige table anchors
  - `transparent_pixels_ignored`

Curated suite entry:

- Defined in `docs/real-images/suite.json`.
- Uses the same bounded config as the M1 run.
- Checks minimum semantic expectations for:
  - circle anchors
  - table quad anchors
  - one perspective grid group
  - smooth stroke anchors

Suite command:

```sh
PYTHONPATH=src python3 -m morphea.cli curated-check docs/real-images/suite.json \
  -o runs/curated-report.json \
  --output-dir runs/curated \
  --snapshot runs/curated-snapshot.json \
  --run
```

The snapshot file is deterministic and meant for commit/config regression
diffs. It records expectation results, anchor/group kind counts, and metrics
without timestamps.

Earlier unbounded behavior:

Temporary command attempted outside the repo:

```sh
PYTHONPATH=src python3 -m morphea.cli vectorize \
  /Users/sebastian/Desktop/terminaro-tweaked.png \
  -o /tmp/morphea-terminaro/terminaro.svg \
  --color-tolerance 18 \
  --min-area 16
```

Result:

- The run did not complete promptly and was stopped after more than a minute.
- This is expected for the current pure-Python component and cut-out scans on a
  full-size 1254px real image.
- The failure mode is useful: runtime control and preprocessing must come
  before deeper ML or self-learning work.

## Expected Semantic Anchors

High-priority anchors:

- Outer gold circular border as `stroke_circle` or arc stroke.
- Three gold center dots as true `circle` anchors.
- Gold shoulder brooches as true circles.
- Gold headband element as stroke/arc or simple filled band.
- Dark navy hair/clothing cut-out lines as white overlay strokes.
- Table grid lines as clean strokes.
- Table cells as perspective quads grouped into a grid.

Secondary anchors:

- Large white circular interior as background/negative region, not a vector
  fragment explosion.
- Navy face/hair/clothing masses as larger filled paths after anchors reserve
  the simple structures.
- Beige tile fills as quads or grouped regions.

## Current Gaps Exposed

- Performance:
  - current exact/near-flat mask scans are too slow for this image size.
  - cut-out scan needs component-size limits or ROI processing.
- Preprocessing:
  - transparent background must be ignored deliberately.
  - near-white and beige colors need palette grouping. Current behavior
    preserves the large beige table palette instead of snapping it to
    background.
  - antialiasing and indexed palette edges need quantization before component
    extraction.
- Shape semantics:
  - outer ring should be found before general color components fragment it.
  - table semantic expectations now pass with 14 editable quads and one grid
    group, but v10 promotion still fails on region-circle matching,
    fragmentation/layer depth, and raster L1 fidelity.
  - white line gaps in hair/clothing need curved cut-out detection, not only
    horizontal/vertical gaps.
- Reporting:
  - long-running components should be reported as skipped/deferred instead of
    stalling the CLI.

## Milestone Mapping

- M1 should make this image run to completion with runtime limits and useful
  skipped/deferred diagnostics.
- M2 should improve ring, stroke, and quad recognition on this image.
- M3 should prevent navy/white/beige regions from becoming layer fragments.
- M4 should produce visual reports for inspecting failures.
- M6 and M7 should add MLX segment proposals and primitive classification.
- M8 should allow high-confidence anchors from this image class to enter a
  reviewed self-learning loop.
