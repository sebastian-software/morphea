# Output Schemas

Curve schemas are intentionally small while the project is still a research
prototype. New fields may be added, but existing schema-v1 field names should
stay stable unless an ADR changes the contract.

## Scene Manifest v1

Written by:

- `curve vectorize`
- `curve sweep`
- synthetic sample generation

Top-level fields:

- `schema_version`: currently `1`
- `width`: source image width
- `height`: source image height
- `anchor_count`: number of recognized anchors
- `anchors`: editable primitive candidates
- `groups`: semantic groups such as `perspective_grid`
- `diagnostics`: non-fatal preprocessing/runtime diagnostics

Anchor fields:

- `kind`: primitive kind, for example `circle`, `stroke_polyline`, `quad`
- `color`: source color as hex when available
- `raster_error`
- `node_count`
- `parameter_count`
- `metrics`
- geometry payload, one of `circle`, `stroke`, or `quad`

## Sweep Summary v1

Written by `curve sweep` as `sweep-summary.json`.

Top-level fields:

- `schema_version`: currently `1`
- `sweep`: source sweep config path
- `input`: source input image
- `run_count`
- `runs`: per-run summaries with anchor/group/diagnostic counts
