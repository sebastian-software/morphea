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
- `layers`: anchor indexes grouped by semantic layer
- `groups`: semantic groups such as `perspective_grid`
- `diagnostics`: non-fatal preprocessing/runtime diagnostics
- `metrics`: scene-level editability and quality metrics

Anchor fields:

- `id`
- `kind`: primitive kind, for example `circle`, `stroke_circle`,
  `stroke_polyline`, `stroke_path`, `arc`, `rect`, `rounded_rect`, or `quad`
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
- `raster_l1_error`: average normalized RGB error for run-directory previews
- `raster_alpha_error`: average normalized alpha error for run-directory previews
- `raster_edge_error`: normalized luminance-edge mismatch for run-directory previews
- `raster_size_match`: whether the source image and rendered preview sizes matched
- `color_fragment_counts`

Layer fields:

- `name`
- `anchor_indexes`
- `anchor_count`

## Sweep Summary v1

Written by `curve sweep` as `sweep-summary.json`.

Top-level fields:

- `schema_version`: currently `1`
- `sweep`: source sweep config path
- `input`: source input image
- `run_count`
- `runs`: per-run summaries with anchor/group/diagnostic counts

Each run summary also carries `editability_score`, `fragmentation_penalty`,
`raster_l1_error`, and `raster_edge_error` when the manifest contains those
metrics.

## Vectorize Config v1

Read by `curve vectorize --config`.

Supported fields match current runtime knobs:

- `min_area`
- `color_tolerance`
- `max_size`
- `max_colors`
- `max_component_area`
- `timeout_seconds`
- `classifier_model`

CLI arguments override values loaded from the config file.

## Synthetic Dataset v1

Written by `curve generate`.

`dataset.json` records:

- `count`, `seed`, `width`, `height`
- `difficulty`: currently `basic` or `dense`
- `splits`
- `samples`

Each generated sample manifest also includes `seed` and `difficulty` so a
single PNG/JSON pair is reproducible outside the dataset index.

## Primitive Classifier Model v1

Written by `curve train`.

Top-level fields:

- `model_type`: currently `centroid_primitive_classifier`
- `feature_names`
- `classes`
- `centroids`
- `train_examples`
- `evaluation`: direct classifier accuracy/confusion for validation/test splits
- `ranking_evaluation`: heuristic-only versus classifier-prior candidate
  ranking comparison for validation/test splits

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

`preview.png` is rendered deterministically from `manifest.json`; run-directory
manifests compare it with the copied input and store bounded raster-fidelity
metrics.
`debug.svg` keeps the editable geometry but wraps each anchor with ids, bounds,
and confidence labels for inspection.
