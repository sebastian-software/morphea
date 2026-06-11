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
- `groups`: semantic groups such as `perspective_grid` and
  `parallel_stroke_group`
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
- `cutout_overlay_count`
- `negative_mask_candidate_count`
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

Cut-out export policy fields:

- `cutout_strategy`: currently `overlay_stroke` for editable white/near-background
  cut-out strokes
- `mask_eligible`: whether the anchor can be migrated to a future negative-mask
  export path without losing the semantic cut-out intent

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

`curve sweep --markdown summary.md` writes a Markdown comparison view ranked by
editability score and raster error. It is derived from `sweep-summary.json` and
does not change the JSON schema.

## Profile Report v1

Written by `curve profile`.

Top-level fields:

- `schema_version`: currently `1`
- `input`
- `repeat_count`
- `config`: effective vectorize runtime config
- `runs`
- `summary`

Each run records `index`, `elapsed_seconds`, `anchor_count`,
`diagnostic_count`, and `diagnostic_codes`. The summary records min/mean/max
elapsed seconds across all repeats.

## Curated Snapshot v1

Written by `curve curated-check --snapshot snapshot.json`.

Top-level fields:

- `schema_version`: currently `1`
- `suite`: source curated suite path
- `case_count`
- `ok`
- `cases`: deterministic per-case summaries sorted by case id

Case snapshot fields:

- `id`
- `status`
- `ok`
- `source_exists`
- `expectations`: sorted expectation outcomes with actual/minimum counts
- `config`: bounded vectorize config when the case was run
- `anchor_count`
- `anchor_kind_counts`
- `group_kind_counts`
- `diagnostic_count`
- `metrics`: run metrics such as editability and raster-fidelity values

Snapshots avoid timestamps and run-directory paths so they can be diffed across
commits and configurations.

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
- `raster_error_weight`
- `quality_error_weight`
- `node_complexity_weight`
- `parameter_complexity_weight`
- `simple_shape_bonus_weight`
- `stroke_circle_min_diameter`
- `stroke_circle_max_aspect_error`
- `stroke_circle_min_inner_ratio`
- `stroke_circle_max_area_error`
- `circle_min_diameter`
- `circle_max_aspect_error`
- `circle_max_area_error`
- `stroke_min_length`
- `stroke_min_length_width_ratio`
- `quad_min_fill_ratio`
- `quad_max_fill_error`
- `rect_max_fill_error`
- `rounded_rect_max_fill_error`

CLI arguments override values loaded from the config file.

## Segment Proposal Manifest v1

Written by `curve segment`.

Top-level fields:

- `schema_version`: currently `1`
- `input`
- `config`
- `proposal_count`
- `proposals`

Proposal fields:

- `id`
- `source`: for example `flat_color` or `mlx_sam`
- `confidence`
- `color`
- `bounds`
- `area`
- `status`

MLX SAM currently has an explicit not-configured error path. It will write the
same proposal schema once the local model runtime is installed.

## Segment Config v1

Read by `curve segment --config`.

Supported fields:

- `segmenter`: currently `flat_color` or `mlx_sam`
- `min_area`
- `color_tolerance`
- `max_size`
- `max_colors`
- `max_component_area`
- `split_components`: default `true`, emits connected-component proposals
  instead of one proposal per color mask
- `mlx_model_path`
- `mlx_score_threshold`
- `mlx_max_masks`
- `mlx_timeout_seconds`

CLI arguments override values loaded from the config file.

## Training Config v1

Read by `curve train --config`.

Supported fields:

- `dataset`
- `output`

CLI arguments override values loaded from the config file.

## MLX Training Config v1

Read by `curve train-mlx --config`.

Supported fields:

- `dataset`
- `output`
- `epochs`
- `hidden_dim`
- `num_heads`
- `num_layers`
- `learning_rate`
- `allow_unavailable`: when true, writes a fallback artifact if MLX is not
  installed locally

CLI arguments override values loaded from the config file.

## Training Comparison Config v1

Read by `curve compare-training --config`.

Supported fields:

- `base_dataset`
- `pseudo_dataset`
- `validation_dataset`
- `output`

CLI arguments override values loaded from the config file.

## Retrain Config v1

Read by `curve retrain --config`.

Supported fields:

- `base_dataset`
- `pseudo_dataset`
- `validation_dataset`
- `output`
- `comparison_output`

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

Written by `curve train`, `curve retrain`, and `curve train-mlx`.

Top-level fields:

- `model_type`: currently `centroid_primitive_classifier` or
  `mlx_transformer_primitive_classifier`
- `feature_names`
- `classes`
- `centroids`
- `train_examples`
- `source_datasets`: present for `curve retrain`, recording base,
  pseudo-label, and validation dataset paths
- `augmentation`: present for `curve retrain`, recording base and reviewed
  pseudo-label train example counts
- `evaluation`: direct classifier accuracy/confusion for validation/test splits
- `ranking_evaluation`: heuristic-only versus classifier-prior candidate
  ranking comparison for validation/test splits

`curve train-mlx` writes `backend`, `backend_available`, `status`,
`training_config`, `fallback_model_type`, and `fallback_centroids`. The fallback
centroids keep the artifact usable as a deterministic `--classifier-model`
prior when MLX is not installed or while Transformer weight training is still
being expanded.

`curve retrain` persists the augmented model so it can be used as a
`--classifier-model` prior in later vectorize/profile runs. Its centroid
backend is intentionally explicit; a future MLX-backed classifier can keep the
same high-level source/evaluation fields while changing `model_type`.

## Training Comparison v1

Written by `curve compare-training`.

Top-level fields:

- `schema_version`: currently `1`
- `base_dataset`
- `pseudo_dataset`
- `validation_dataset`
- `baseline`: centroid classifier summary trained only on base train examples
- `augmented`: centroid classifier summary trained on base plus reviewed
  pseudo-label train examples
- `delta`: training-count and accuracy changes from baseline to augmented

Both `baseline` and `augmented` include validation/test `evaluation` and
`ranking_evaluation` sections using the same validation dataset. The report is
intended to show whether reviewed pseudo-labels improve, degrade, or leave
candidate ranking unchanged before a heavier retraining backend is introduced.

## Snapshot Comparison v1

Written by `curve compare-snapshots` and `curve compare-git-snapshots`.

Top-level fields:

- `schema_version`: currently `1`
- `before`
- `after`
- `item_kind`: `cases`, `runs`, or `root`
- `item_count`
- `added_ids`
- `removed_ids`
- `items`
- `git`: present for `compare-git-snapshots`

Each item records the shared `id`, `changed_metric_count`, and numeric
`metric_deltas`. Deltas use flattened metric paths, for example
`metrics.editability_score` or `anchor_kind_counts.quad`. Boolean fields are
not treated as numeric metrics.

`curve compare-snapshots --markdown comparison.md` writes a scan-friendly table
for reviewing differences between saved reports from different commits or
configurations.

`curve compare-git-snapshots before_ref after_ref --path snapshot.json` reads
the same checked-in snapshot file from two git refs with `git show` and does
not modify the current working tree.

`curve snapshot-git-ref REF --suite suite.json -o snapshot.json` creates a
temporary detached git worktree for `REF`, runs `curve curated-check` inside
that worktree, and writes a normal Curated Snapshot v1 file to the requested
output path. The snapshot file intentionally stays compatible with
`curve compare-snapshots`; git metadata is returned by the command result but
is not embedded into the deterministic snapshot.

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

## Refinement Metadata v1

Written by `curve refine`.

Recognized backends:

- `local_metric`: active structure-preserving local optimizer
- `differentiable` and `diffvg`: optional differentiable-renderer backend names
  that currently fail with an explicit not-installed/not-configured error

Top-level `refinement` fields:

- `backend`
- `max_iterations`
- `timeout_seconds`
- `source_image`
- `raster_l1_weight`
- `raster_edge_weight`
- `structure_preserving`
- `optimizer`

The local metric optimizer uses a weighted objective of raster L1 and raster
edge error. Optimizer metadata stores initial/final L1, edge, and combined
objective values so geometry changes can be judged against visual edge quality,
not only average pixel color.

`optimizer.optimized_parameter_kinds` lists primitive kinds whose parameters
changed during the local pass. The current local backend can adjust circle
radii and quad-like corner parameters while preserving the original primitive
kind.
