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
- `metrics`: scene-level editability and quality metrics

Anchor fields:

- `id`
- `kind`: primitive kind, for example `circle`, `stroke_polyline`, `quad`
- `color`: source color as hex when available
- `layer`
- `confidence`
- `reserved`: reserved bounds and reason
- `provenance`: source stage and fitting stage
- `export_policy`: editability and debug label metadata
- `raster_error`
- `node_count`
- `parameter_count`
- `metrics`
- geometry payload, one of `circle`, `stroke`, or `quad`

Stroke payload fields:

- `centerline`
- `width_samples`
- `is_cutout`
- `cap_style`
- `join_style`

Scene metrics:

- `shape_count`
- `node_count`
- `parameter_count`
- `simple_shape_count`
- `generic_path_count`
- `cutout_anchor_count`
- `group_count`
- `simple_shape_ratio`
- `fragmentation_penalty`
- `diagnostic_penalty`
- `editability_score`
- `color_fragment_counts`

## Sweep Summary v1

Written by `curve sweep` as `sweep-summary.json`.

Top-level fields:

- `schema_version`: currently `1`
- `sweep`: source sweep config path
- `input`: source input image
- `run_count`
- `runs`: per-run summaries with anchor/group/diagnostic counts

Each run summary also carries `editability_score` and
`fragmentation_penalty` when the manifest contains scene metrics.

## Run Directory v1

Written by `curve vectorize --run-dir` and by each `curve sweep` run.

Files:

- `input/<source-name>` when the source image exists
- `output.svg`
- `manifest.json`
- `config.json`
- `report.md`
- `preview.png`
- `debug.svg`

`preview.png` is rendered deterministically from `manifest.json`; it is a
debug artifact for inspection and future raster-fidelity metrics.
`debug.svg` keeps the editable geometry but wraps each anchor with ids, bounds,
and confidence labels for inspection.
