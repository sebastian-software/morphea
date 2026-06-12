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
- `source_mask`: stable source-mask proxy used by run artifacts and reviews
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
- `reserved_simple_shape_count`
- `reserved_simple_shape_area`
- `reserved_simple_shape_area_ratio`
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

- `cutout_strategy`: `overlay_stroke` by default for editable
  white/near-background cut-out strokes; SVG export can also use
  `negative_mask` to keep cut-out strokes editable inside an SVG mask.
- `mask_eligible`: whether the anchor can be exported through the
  negative-mask path without losing the semantic cut-out intent.

Source mask fields:

- `id`: stable source-mask id aligned with the anchor index, for example
  `mask-0000`
- `source`: currently `reserved_bounds`, meaning the mask proxy is derived
  from the reserved anchor bounds
- `bounds`: the source-mask proxy bounds used by run artifacts
- `bounds_area`: area of those bounds, used for inspection and later
  reservation audits

Group fields:

- `kind`: for example `perspective_grid`, `parallel_stroke_group`,
  `same_color_fragment_group`, or `primitive_anchor_reservation`
- `anchor_indexes`
- `metrics`
- `color`: present for `same_color_fragment_group`
- `merge_plan`: present for `same_color_fragment_group`; records the
  recommended action, target kind, combined bounds, per-fragment bounds, and
  bounds fill ratio for later merge/review steps
- `row_count`: present for `perspective_grid`
- `column_count`: present for `perspective_grid`

`perspective_grid.metrics.vanishing_line_diagnostics` records how many
horizontal and vertical edge pairs were inspected and how many finite
intersections were found. This keeps perspective-grid regularity visible even
before a full vanishing-point solver is introduced.

## Sweep Summary v1

Written by `curve sweep` as `sweep-summary.json`.

Top-level fields:

- `schema_version`: currently `1`
- `sweep`: source sweep config path
- `input`: source input image
- `run_count`
- `ranking`: semantic-first ranking with run id, rank, editability score, and
  raster L1 error
- `runs`: per-run summaries with anchor/group/diagnostic counts

Each run summary also carries `editability_score`, `fragmentation_penalty`,
`raster_l1_error`, `raster_edge_error`, `semantic_rank`, and
`diagnostic_stage_counts` when the manifest contains those metrics and
diagnostics.

`curve sweep --markdown summary.md` writes a Markdown comparison view ranked by
editability score and raster error. It is derived from `sweep-summary.json` and
does not change the JSON schema.

Sweep run configs may include `cutout_export` with `overlay_stroke` or
`negative_mask`; this affects the run directory `output.svg` but is not passed
to primitive detection.

## Eval Summary v1

Written by `curve eval`.

Top-level fields:

- `run_count`
- `runs`: per-run summaries for discovered run directories

Each run summary records anchor, layer, group, diagnostic, metric, and
anchor-type counts. Diagnostic data includes both raw `diagnostic_codes` and
stage-oriented `diagnostic_stage_counts` using the same stage buckets as
Markdown/HTML run reports.

## Eval Config v1

Read by `curve eval --config`.

Supported fields:

- `run_root`
- `output`
- `markdown`: optional Markdown summary path

CLI arguments override values loaded from the config file.

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
`diagnostic_count`, `diagnostic_codes`, and `diagnostic_stage_counts`. The
summary records min/mean/max elapsed seconds across all repeats.

## Curated Snapshot v1

Written by `curve curated-check --snapshot snapshot.json`.

Curated suite expectations support three mutually exclusive check types:
`kind` with `min_count`, `group_kind` with `min_count`, or `metric` with
`min_value` and/or `max_value`. Metric expectations read top-level manifest
`metrics` values such as `editability_score`, `simple_shape_ratio`, and
`fragmentation_penalty`.

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
- `expectations`: sorted expectation outcomes with actual/minimum counts or
  metric actual/bound values
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

- `background`: optional explicit background color as `#rrggbb` or RGB triplet
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
- `cutout_export`: export-only option, either `overlay_stroke` or
  `negative_mask`

CLI arguments override values loaded from the config file.

## Segment Proposal Manifest v1

Written by `curve segment`.

Top-level fields:

- `schema_version`: currently `1`
- `input`
- `config`
- `backend`: segmenter availability/status metadata
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
- `downstream_status`: `pending`, `accepted`, or `rejected`; initial flat-color
  proposals are `pending`, while deferred oversized proposals are `rejected`
- `rejection_reason`: nullable machine-readable reason for rejected proposals

`backend` records `source`, `backend_available`, `status`, and an optional
`reason`. MLX SAM status distinguishes `not_installed`, `not_configured`,
`model_missing`, and `adapter_pending`; it also records `package_available`,
`model_configured`, `model_exists`, and the runtime knobs. It will write the
same proposal schema once the local model runtime is installed and wired.

## Runtime Status Report v1

Written by `curve status`.

Top-level fields:

- `schema_version`: currently `1`
- `segmenters`: status for `flat_color` and `mlx_sam`
- `classifiers`: status for `centroid` and `mlx`
- `refinement`: output of `available_refinement_backends()`
- `blocked_backends`: normalized rows for unavailable or non-available
  backends

Each status entry records `status`, `backend_available`, and optional `reason`
where the underlying backend exposes those fields. The report is intentionally
diagnostic: missing MLX/SAM/DiffVG integrations are reported explicitly instead
of being treated as partial success.

## Segment Config v1

Read by `curve segment --config`.

Supported fields:

- `segmenter`: currently `flat_color` or `mlx_sam`
- `background`: optional explicit background color as `#rrggbb` or RGB triplet
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

## Pseudo-Label Harvest v1

Written by `curve harvest`. `curve harvest --markdown harvest.md` writes a
scan-friendly quality-gate report next to the JSON artifact.

Top-level fields:

- `pseudo_label_count`
- `pseudo_labels`
- `rejected_runs`
- `filters`

`filters` records the active quality gates:

- `max_run_diagnostics`
- `max_classifier_prior_error`
- `min_editability_score`
- `max_fragmentation_penalty`
- `max_raster_l1_error`
- `max_raster_edge_error`
- `max_anchor_quality_error`

Each accepted pseudo-label includes `anchor_quality_error`, copied anchor
metrics, run metrics, and `source_manifest` provenance.

`curve harvest-curated` first runs a curated real-image suite with each case's
bounded `recommended_config`, then harvests the generated run directories with
the same quality gates. Its output keeps the normal harvest fields and adds:

- `schema_version`: currently `1`
- `source`: `curated_suite`
- `suite`: source curated suite path
- `run_root`: directory containing per-case run artifacts
- `curated_ok`
- `curated_case_count`
- `curated_checked_count`
- `curated_missing_source_count`

## Harvest Config v1

Read by `curve harvest --config`.

Supported fields:

- `run_root`
- `output`
- `markdown`: optional Markdown report path
- `max_run_diagnostics`
- `max_classifier_prior_error`
- `min_editability_score`
- `max_fragmentation_penalty`
- `max_raster_l1_error`
- `max_raster_edge_error`
- `max_anchor_quality_error`

CLI arguments override values loaded from the config file.

## Harvest Curated Config v1

Read by `curve harvest-curated --config`.

Supported fields:

- `suite`
- `run_root`: directory for per-case curated run artifacts
- `output`
- `curated_report`: optional raw curated-check report path
- `snapshot`: optional deterministic curated snapshot path
- `markdown`: optional Markdown report path
- `max_run_diagnostics`
- `max_classifier_prior_error`
- `min_editability_score`
- `max_fragmentation_penalty`
- `max_raster_l1_error`
- `max_raster_edge_error`
- `max_anchor_quality_error`

CLI arguments override values loaded from the config file.

## Review Queue and Reviewed Labels v1

Written by `curve review` and `curve apply-review`.
`curve review --markdown review.md` writes a scan-friendly queue summary while
the editable decisions stay in the JSON review file.

Review queue items contain `decision`, `reason`, `corrected_kind`, `issues`,
and the original `label`. `corrected_kind` lets a reviewer mark a wrong
primitive type without manually editing nested anchor payloads. `issues` is a
free-form string list for structured human notes such as `wrong_primitive_type`,
`bad_cutout`, or `bad_stroke`.

`curve apply-review` writes accepted, rejected, and pending splits.
`curve apply-review --markdown accepted.md` writes a scan-friendly decision
summary next to the JSON artifact. Accepted labels include a `review`
provenance object and apply `corrected_kind` to both the top-level label kind
and embedded anchor kind when present.

## Review Config v1

Read by `curve review --config`.

Supported fields:

- `pseudo_labels`
- `output`
- `markdown`: optional Markdown queue summary path

CLI arguments override values loaded from the config file.

## Apply Review Config v1

Read by `curve apply-review --config`.

Supported fields:

- `review`
- `output`
- `markdown`: optional Markdown decision summary path

CLI arguments override values loaded from the config file.

## Merge Labels Config v1

Read by `curve merge-labels --config`.

Supported fields:

- `reviewed_labels`
- `output_dir`

CLI arguments override values loaded from the config file.

## Training Config v1

Read by `curve train --config`.

Supported fields:

- `dataset`
- `output`

CLI arguments override values loaded from the config file.

## Classifier Evaluation Config v1

Read by `curve eval-classifier --config`.

Supported fields:

- `model`
- `dataset`
- `output`
- `markdown`: optional Markdown report path
- `splits`: optional non-empty array of dataset split names, defaulting to
  `["val", "test"]`

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
- `markdown`: optional Markdown report path

CLI arguments override values loaded from the config file.

## Training Gate v1

Written by `curve training-gate`.

Top-level fields:

- `schema_version`: currently `1`
- `comparison`: source training comparison JSON path
- `decision`: `accept`, `manual_review`, or `reject`
- `accepted`: boolean shortcut for `decision == "accept"`
- `reasons`: machine-readable gate reasons
- `gates`: active threshold values
- `summary`: copied comparison summary

`curve training-gate --markdown gate.md` writes a scan-friendly decision
summary next to the JSON artifact.

## Training Gate Config v1

Read by `curve training-gate --config`.

Supported fields:

- `comparison`
- `output`
- `markdown`: optional Markdown report path
- `min_train_examples_delta`
- `min_best_accuracy_delta`
- `max_worst_accuracy_drop`
- `allow_unchanged`

CLI arguments override values loaded from the config file.

## Self-Learning Cycle v1

Written by `curve self-learn` as `self-learning-cycle.json` inside the output
directory.

Top-level fields:

- `schema_version`: currently `1`
- `status`: `retrained` or `skipped_retrain`
- `base_dataset`
- `reviewed_labels`
- `validation_dataset`
- `output_dir`
- `artifacts`: pseudo dataset, comparison, gate, optional model, and summaries
- `pseudo_dataset`: pseudo-label train example count and split counts
- `comparison_summary`: copied training comparison summary
- `gate`: copied gate decision, accepted flag, and reasons
- `model`: compact model summary when retraining was accepted
- `curated_validation`: optional fixed-suite validation summary when
  `curated_suite` is configured

`curve self-learn` always writes comparison and gate artifacts. It writes
`model.json` only when the training gate accepts the reviewed-label
augmentation. When `curated_suite` is configured and retraining is accepted,
the cycle runs `curve curated-check` with the accepted model as
`classifier_model` and writes curated validation artifacts.

## Self-Learning Config v1

Read by `curve self-learn --config`.

Supported fields:

- `base_dataset`
- `reviewed_labels`
- `validation_dataset`
- `curated_suite`
- `curated_output_dir`
- `curated_report`
- `curated_snapshot`
- `output_dir`
- `markdown`: optional cycle Markdown summary path
- `min_train_examples_delta`
- `min_best_accuracy_delta`
- `max_worst_accuracy_drop`
- `allow_unchanged`

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

## Refine Config v1

Read by `curve refine --config`.

Supported fields:

- `manifest`
- `output`
- `backend`
- `max_iterations`
- `timeout_seconds`
- `source_image`
- `raster_l1_weight`
- `raster_edge_weight`

CLI arguments override values loaded from the config file.

## Refinement Gate v1

Written by `curve refinement-gate`.

Top-level fields:

- `schema_version`: currently `1`
- `refined_manifest`: source refined manifest path
- `decision`: `accept`, `manual_review`, or `reject`
- `accepted`: boolean shortcut for `decision == "accept"`
- `reasons`: machine-readable gate reasons
- `gates`: active threshold values
- `structure_audit`: copied refinement structure audit
- `optimizer`: copied optimizer metrics plus objective delta

The gate rejects structure/editability breaks and objective regressions. Missing
optimizer metrics, timeouts, or unchanged non-improving results go to manual
review unless explicitly allowed.

## Refinement Gate Config v1

Read by `curve refinement-gate --config`.

Supported fields:

- `refined_manifest`
- `output`
- `markdown`: optional Markdown report path
- `max_objective_regression`
- `require_improvement`

CLI arguments override values loaded from the config file.

## Synthetic Dataset v1

Written by `curve generate`.

`dataset.json` records:

- `count`, `seed`, `width`, `height`
- `difficulty`: currently `basic`, `dense`, or `logo`
- `splits`
- `samples`

Each generated sample manifest also includes `seed` and `difficulty` so a
single PNG/JSON pair is reproducible outside the dataset index.

Quad anchors may include numeric `metrics.quad_subtype_code` values: `1.0` for
trapezoid and `2.0` for parallelogram. They remain `quad` anchors so the
primitive vocabulary stays small while training data and detected anchors can
still target visually important quad families.

Primitive classifier feature extraction includes `quad_subtype_code` as a
numeric feature. This lets the first classifier learn trapezoid and
parallelogram-sensitive ranking behavior without expanding the top-level class
set or forcing downstream exporters to understand new primitive kinds.

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

`curve train-mlx` writes `backend`, `backend_available`, `status`, `runtime`,
`reason`, `training_implementation`, `training_config`, `fallback_model_type`,
and `fallback_centroids`. Runtime status distinguishes `not_installed` from an
available MLX package. When MLX is available, status is `trained` and
`mlx_training` stores an optimized normalized feature-head artifact with
`weight_format`, `architecture`, `transformer_status`, `normalization`,
`weights`, `bias`, and `loss_history`. The fallback centroids keep the artifact
usable as a deterministic `--classifier-model` prior when MLX is not installed
or while the full raster-crop Transformer encoder is still being expanded.

`curve retrain` persists the augmented model so it can be used as a
`--classifier-model` prior in later vectorize/profile runs. Its centroid
backend is intentionally explicit; a future MLX-backed classifier can keep the
same high-level source/evaluation fields while changing `model_type`.

## Classifier Evaluation Report v1

Written by `curve eval-classifier`. `--markdown report.md` writes a
scan-friendly table view derived from the JSON report.

Top-level fields:

- `schema_version`: currently `1`
- `model`
- `dataset`
- `model_type`
- `feature_names`
- `classes`
- `splits`
- `evaluation`: direct classifier accuracy/confusion by requested split
- `ranking_evaluation`: heuristic-only versus classifier-prior ranking by
  requested split

The command can evaluate centroid models and MLX fallback artifacts because it
loads models through the same deterministic `--classifier-model` path used by
vectorization.

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
- `summary`: scan-friendly augmentation verdict with status, metric count,
  best/worst accuracy deltas, and train-example delta

Both `baseline` and `augmented` include validation/test `evaluation` and
`ranking_evaluation` sections using the same validation dataset. The report is
intended to show whether reviewed pseudo-labels improve, degrade, or leave
candidate ranking unchanged before a heavier retraining backend is introduced.
`curve compare-training --markdown comparison.md` writes a scan-friendly
Markdown table derived from the same JSON report.

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
`metrics.editability_score`, `anchor_kind_counts.quad`, or
`expectations.simple-shape-ratio.actual_value`. List items with `id` fields use
that id as the flattened path segment. Boolean fields are not treated as
numeric metrics.

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
- `anchors.json`
- `palette.json`
- `mask-summary.json`
- `report.md`
- `report.html`
- `preview.png`
- `debug.svg`

`preview.png` is rendered deterministically from `manifest.json`; run-directory
manifests compare it with the copied input and store bounded raster-fidelity
metrics.

`anchors.json` stores the manifest anchor list as a standalone inspection file.
`palette.json` groups anchors by source color with kind and layer counts.
`mask-summary.json` records one source-mask proxy per anchor using the reserved
bounds that later stages should not fragment.
`debug.svg` keeps the editable geometry but wraps each anchor with ids, bounds,
and confidence labels for inspection.

Markdown and HTML reports include a pipeline-stage diagnostic summary derived
from manifest diagnostic codes. Current stage buckets are `preprocessing`,
`palette`, `segmentation`, `runtime`, and `unknown`.

## Refinement Metadata v1

Written by `curve refine`.

Recognized backends:

- `local_metric`: active structure-preserving local optimizer
- `differentiable` and `diffvg`: optional differentiable-renderer backend names
  that currently fail with an explicit not-installed/not-configured error

`available_refinement_backends()` also exposes per-backend `details`. Optional
backend status distinguishes `not_installed` from `adapter_pending`, records
`package_available`, and lists package candidates such as `pydiffvg`/`diffvg`.
Even when a package is present, optional backends remain unavailable until a
renderer adapter is wired.

Top-level `refinement` fields:

- `backend`
- `max_iterations`
- `timeout_seconds`
- `source_image`
- `raster_l1_weight`
- `raster_edge_weight`
- `structure_preserving`
- `structure_audit`
- `optimizer`

The local metric optimizer uses a weighted objective of raster L1 and raster
edge error. Optimizer metadata stores initial/final L1, edge, and combined
objective values so geometry changes can be judged against visual edge quality,
not only average pixel color.

`max_iterations` must be non-negative, `timeout_seconds` must be positive when
set, and raster objective weights must be non-negative with at least one
positive weight. `optimizer.elapsed_seconds`, `optimizer.timeout_reached`, and
`optimizer.stopped_reason` make bounded refinement runs auditable.

`optimizer.optimized_parameter_kinds` lists primitive kinds whose parameters
changed during the local pass. The current local backend can adjust circle
radii, quad-like corner parameters, and stroke/arc centerline or width samples
while preserving the original primitive kind.

`structure_audit` records source/refined anchor counts, preserved-kind count,
changed-geometry count, `structure_preserved`, and `editability_preserved`.
