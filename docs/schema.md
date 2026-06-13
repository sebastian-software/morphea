# Output Schemas

Morphēa schemas are intentionally small while the project is still a research
prototype. New fields may be added, but existing schema-v1 field names should
stay stable unless an ADR changes the contract.

## Scene Manifest v1

Written by:

- `morphea vectorize`
- `morphea sweep`
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

Anchor metrics always include `simple_shape_priority_bonus` and
`semantic_anchor_score` so reviews and self-learning reports can audit why a
simple editable primitive beat or lost to another candidate. Additional
primitive-quality metrics are included when relevant.

Anti-aliased neutral UI rings may be recovered from a composite grayscale mask
when individual palette fragments are below per-color component thresholds. The
resulting anchor is still emitted as a normal `circle` or `stroke_circle` with
an editable `circle` payload.

Stroke payload fields:

- `centerline`
- `width_samples`: one global width for straight two-point strokes, or local
  support-point widths for curved stroke/arc centerlines
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
- `anchor_quality_error_mean`
- `anchor_quality_error_max`
- `anchor_quality_metric_summary`: per-metric aggregate counts, means, and
  maxima for primitive quality metrics such as `circle_roundness_error`,
  `line_smoothness_error`, `stroke_width_variance`, and quad/grid errors
- `anchor_scoring_summary`: aggregate `simple_shape_priority_bonus` and
  `semantic_anchor_score` values so run reports can audit semantic-first
  ranking pressure
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
  recommended action, `auto_merge_allowed`, decision reason, target kind,
  combined bounds, per-fragment bounds, and bounds fill ratio for later
  merge/review steps
- `row_count`: present for `perspective_grid`
- `column_count`: present for `perspective_grid`

When compact same-color axis-aligned `rect` fragments are automatically merged,
the resulting anchor remains a `rect` and records descriptive metrics such as
`merged_fragment_count`, `merge_bounds_fill_ratio`,
`source_fragment_node_count`, and `source_fragment_parameter_count`.

`perspective_grid.metrics.vanishing_line_diagnostics` records how many
horizontal and vertical edge pairs were inspected and how many finite
intersections were found. This keeps perspective-grid regularity visible even
before a full vanishing-point solver is introduced.

## Sweep Summary v1

Written by `morphea sweep` as `sweep-summary.json`.

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

`morphea sweep --markdown summary.md` writes a Markdown comparison view ranked by
editability score and raster error. It is derived from `sweep-summary.json` and
does not change the JSON schema.

Sweep run configs may include `cutout_export` with `overlay_stroke` or
`negative_mask`; this affects the run directory `output.svg` but is not passed
to primitive detection.

## Sweep Config v1

Read by `morphea sweep`.

Top-level fields:

- `version`: currently `1`
- `input`: source image path
- `runs`: non-empty list of run objects with `id` and optional `config`
- `output_dir`: optional run output root for CLI execution
- `markdown`: optional Markdown summary path for CLI execution

CLI `--output-dir` and `--markdown` arguments override `output_dir` and
`markdown` loaded from the sweep config.

## Eval Summary v1

Written by `morphea eval`.

Top-level fields:

- `run_count`
- `runs`: per-run summaries for discovered run directories

Each run summary records anchor, layer, group, diagnostic, metric, and
anchor-type counts. Diagnostic data includes both raw `diagnostic_codes` and
stage-oriented `diagnostic_stage_counts` using the same stage buckets as
Markdown/HTML run reports.

## Eval Config v1

Read by `morphea eval --config`.

Supported fields:

- `run_root`
- `output`
- `markdown`: optional Markdown summary path

CLI arguments override values loaded from the config file.

## Primitive Quality Report v1

Written by `morphea primitive-check`.

Top-level fields:

- `schema_version`: currently `1`
- `case_count`
- `passed_count`
- `failed_count`
- `ok`
- `selected_case_ids`: ids selected by `--case`/`--filter`
- `family_summaries`: pass/fail counts grouped by fixture family
- `selection`: requested case ids and filter pattern
- `cases`: fixed primitive fixture results

Each case records:

- `id`
- `family`
- `variant`
- `expected_kinds`
- `actual_kind`
- `anchor_count`
- `metrics`: includes `raster_l1_error`, `raster_edge_error`,
  `raster_alpha_error`, and `raster_size_match`
- `geometry`: expected bounds, actual bounds, and `bbox_iou`
- `geometry_diff`: compact expected-vs-actual semantic geometry
- `matches`: order-independent expected-to-actual primitive matches
- `unmatched_expected`: expected primitives that could not be matched
- `unexpected_actual`: extra actual primitives left after matching
- `group_matches`: expected manifest group contracts that matched
- `export_comparison`: present for cut-out export gate cases; compares
  `overlay_stroke` and `negative_mask` SVG output from the same scene
- `refinement`: present when `primitive-check --refine` is used; records
  structure audit and before/after raster metrics
- `failures`: contract failures such as wrong kind, fallback path, loose
  coordinates, out-of-canvas bounds, or visual round-trip regression
- `failure_categories`: stable categories such as `wrong_kind`, `wrong_count`,
  `geometry_drift`, `visual_drift`, `fallback_path`, `bounds_escape`, and
  `group_drift`
- `failure_details`: category/message pairs for machine-readable diagnostics
- `artifacts`: present when `--output-dir` is used; includes input PNG,
  output SVG, debug SVG, manifest JSON, rendered preview PNG, and
  `negative_mask_svg` for cut-out export gate cases

The built-in fixture set covers filled square, filled rectangle, filled circle,
horizontal/vertical/diagonal strokes, outlined ring, rounded rectangle, and a
simple quad. These cases are intentionally boring and should stay stricter than
the curated real-image suite.

## Primitive Gallery Site v1

Written by `morphea primitive-gallery`.

Default outputs:

- `site/assets/primitive-quality/report.json`
- `site/assets/primitive-quality/report.md`
- `site/assets/primitive-quality/cases/<case-id>/...`
- `site/primitive-quality/index.html`

The command reuses `primitive-check`, supports the same `--case` and `--filter`
selection options, and refreshes the marked homepage teaser block by default.
The generated HTML is deterministic and contains no timestamps.

## Primitive Check Config v1

Read by `morphea primitive-check --config`.

Supported fields:

- `output`
- `output_dir`: optional per-case artifact root
- `markdown`: optional Markdown summary path
- `case`: optional case or family id, or a list of ids
- `filter`: optional shell-style pattern matched against case id or family
- `refine`: optional boolean; run structure-preserving refinement on selected
  primitive cases
- `refinement_iterations`: optional local refinement iteration count; defaults
  to `1`

CLI arguments override values loaded from the config file.

## Profile Report v1

Written by `morphea profile`.
`morphea profile --config profile.json` accepts `input`, `output`, `repeats`,
and the same bounded vectorize runtime knobs used by `morphea vectorize --config`.
CLI arguments override matching config values.

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

## Curated Profile Report v1

Written by `morphea profile-curated`.
`morphea profile-curated --config profile-curated.json` accepts `suite`,
`output`, `markdown`, and `repeats`. CLI arguments override matching config
values.

Top-level fields:

- `schema_version`: currently `1`
- `suite`
- `repeat_count`
- `case_count`
- `checked_count`
- `missing_source_count`
- `cases`
- `summary`

Each case records `id`, `source`, `status`, `config`, `runs`, and `summary`.
Available source images use the case `recommended_config` and the same run
fields as Profile Report v1. Missing source images are retained in the report
with `status: "missing_source"` and empty runs so curated-family reports stay
auditable even when local image assets are incomplete.

The summary records `slowest_case_id`, `max_elapsed_seconds`, and
`mean_case_elapsed_seconds` across checked cases. `--markdown` writes a
scan-friendly companion table for profile-guided hot-loop work.

## Curated Snapshot v1

Written by `morphea curated-check --snapshot snapshot.json`.
`morphea curated-check --markdown report.md` writes a scan-friendly companion
report from the same suite check result, including case status, failed
expectations, key anchor/group counts, key metrics, and per-case artifact
directories when `--output-dir` is used.

`morphea curated-check --config curated-check.json` accepts `suite`, `output`,
`output_dir`, `run`, `snapshot`, and `markdown`. CLI arguments override matching
config values, and `run` must be a boolean when provided in JSON.

Curated suite expectations support three mutually exclusive check types:
`kind` with `min_count` and optional `max_count`, `group_kind` with `min_count`
and optional `max_count`, or `metric` with `min_value` and/or `max_value`.
Metric expectations read top-level manifest `metrics` values such as
`editability_score`, `simple_shape_ratio`, and `fragmentation_penalty`.

Repeated `kind` or `group_kind` expectations are cumulative. For example, two
separate `kind: circle`, `min_count: 1` expectations require two distinct circle
anchors; the second result records `cumulative_min_count: 2`.

Curated suite cases may include optional `promotion` metadata for the
real-image promotion roadmap. When present, `morphea curated-check` validates
the metadata and copies it into JSON reports, Markdown reports, and deterministic
snapshots.

Promotion metadata fields:

- `stress_family`: short family id such as `ui_screenshot_text_and_controls`
- `source_provenance`: human-readable source/provenance note
- `licensing_status`: source licensing or local-use status
- `expected_promotion_families`: non-empty string array of intended semantic
  promotion families
- `current_quality_label`: one of `green`, `yellow`, or `red`
- `current_status`: current pipeline status such as
  `checked_failed_expectations`, `checked_expectations_pass_but_not_promotable`,
  or `missing_source`
- `current_issues`: string array of issue tags, for example
  `fragmentation`, `missing_promotion_state`, or `missing_local_source`
- `visual_audit_status`: current visual artifact posture, for example
  `contact_sheet_available` or `unavailable_missing_source`
- `hard_gates`: optional array of explicit promotion gates. Each gate includes
  `id`, `gate_type`, `expectation_ids`, optional `severity`, and optional
  `description`. Supported `gate_type` values are `shape_class`, `topology`,
  `grouping`, `fragmentation`, `visual_fidelity`, `provenance`, and
  `review_safety`. `expectation_ids` must reference expectations in the same
  case.
- `region_gates`: optional array of source-region promotion gates. Each gate
  includes `id`, `gate_type`, `bounds`, `expected_kinds` and/or
  `forbidden_kinds`, optional `min_count`, optional `max_count`, optional
  `min_iou`, optional topology limits, optional `severity`, and optional
  `description`. `bounds` are `[left, top, right, bottom]` in manifest/source
  coordinates. Region gates select anchors whose manifest `source_mask.bounds`
  overlap the region by at least `min_iou`, then check the selected anchor
  kinds.

Region gate topology limits are optional non-negative integer fields:
`min_closed_anchors`, `max_closed_anchors`, `min_open_anchors`,
`max_open_anchors`, `max_hole_count`, `max_cutout_count`, and
`max_disconnected_components`. Region-gate evidence includes
`topology_summary` with selected-anchor, closed/open, hole, cutout, disconnected
component, and kind-count summaries.
- `review_notes`: optional string array for dated human review notes

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
- `promotion`: optional copied promotion metadata from the source suite case

Snapshots avoid timestamps and run-directory paths so they can be diffed across
commits and configurations.

When `curated-check --output-dir` is used for checked cases, each per-case run
directory includes the standard vectorize artifacts plus:

- `svg-render.png`: deterministic rasterization of the exported SVG
- `diff.png`: red/blue source-vs-SVG visual difference image
- `anchor-overlay.png`: source image with manifest anchor bounds overlaid
- `contact-sheet.png`: source, manifest preview, anchor overlay, SVG render,
  diff, promotion decision, and failed-gate panels for cases with promotion
  metadata

When a suite case includes `promotion` metadata, checked and missing-source
case reports also include:

- `promotion_gates`: derived hard-gate results for `source_available`,
  `semantic_expectations`, `visual_contact_sheet`, `current_quality_label`, and
  any case-specific `promotion.hard_gates` or `promotion.region_gates`
- `promotion_summary`: compact decision summary with `decision`, failed gate
  count, and red/yellow gate counts

`promotion_summary.decision` is `promoted` only when all derived gates pass,
`rejected` when any failed gate has red severity, and `deferred` when only
yellow gates fail.

## Vectorize Config v1

Read by `morphea vectorize --config`.

Supported fields include artifact paths and current runtime knobs:

- `input`: input PNG/JPEG/WebP image
- `output`: output SVG path
- `manifest`: optional output JSON manifest path
- `debug_svg`: optional debug SVG path with source ids, bounds, and labels
- `run_dir`: optional root for timestamped experiment run directories
- `no_manifest`: skip writing the JSON manifest for direct SVG outputs
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

## Report Config v1

Read by `morphea report --command-config`.

Supported fields:

- `manifest`
- `output`
- `config`: optional vectorize/run config JSON rendered in the report
- `format`: optional `markdown` or `html`; when omitted, the output suffix
  selects HTML for `.html` and Markdown otherwise

`morphea report --config` remains the optional vectorize/run config file that is
rendered inside the report. CLI arguments override values loaded from
`--command-config`.

## Segment Proposal Manifest v1

Written by `morphea segment`. `morphea segment --markdown proposals.md` writes a
scan-friendly Markdown report derived from the same manifest, including summary
counts and a proposal table with anchor reservation state.

Top-level fields:

- `schema_version`: currently `1`
- `input`
- `config`
- `backend`: segmenter availability/status metadata
- `proposal_count`
- `summary`: aggregate `status_counts`, `downstream_status_counts`,
  `anchor_kind_counts`, `reserved_anchor_count`, and
  `downstream_decision_reason_counts`; when proposal groups are emitted it
  also includes `proposal_group_counts`
- `proposal_groups`: higher-level groupings inferred from simple proposal
  anchors, currently `proposal_tile_grid`
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
- `anchor_kind`: nullable primitive kind summary from the geometry scorer for
  pending flat-color proposals
- `anchor_metrics`: nullable primitive metric summary for the proposed anchor
- `anchor_parameter_count`: nullable parameter count for the proposed anchor
- `anchor_reserved`: true when a simple parametric anchor is reserved before
  later fitting stages can fragment it
- `reservation_reason`: nullable reservation reason, currently
  `simple_shape_anchor`
- `reservation_bounds`: nullable reserved bounds for the proposal
- `anchor_quality_error`: nullable geometry quality error used by optional
  segment geometry gating
- `downstream_decision_reason`: nullable machine-readable reason for the
  downstream geometry gate decision, for example `geometry_gate_passed`,
  `missing_anchor_summary`, `anchor_quality_error_too_high`, or
  `anchor_not_reserved`

Proposal group fields:

- `id`
- `kind`: currently `proposal_tile_grid` for regular 2D arrangements of
  reserved `rect`/`quad` proposals
- `proposal_ids`: proposal ids in row/column order
- `metrics`: includes `row_count`, `column_count`, `tile_count`,
  `grid_occupancy_ratio`, row/column spacing errors, and mean tile dimensions

`backend` records `source`, `backend_available`, `status`, and an optional
`reason`. MLX SAM status distinguishes `json_adapter_available`,
`mlx_sam_package_available`, `not_installed`, `not_configured`,
`model_missing`, and `adapter_pending`; it also records `package_available`,
`sam_package_available`, `model_configured`, `model_exists`, adapter name,
runtime knobs, and per-capability status for `json_proposal_adapter` and
`live_sam_model_adapter`. The JSON adapter is a local bridge for checked-in or
generated proposal payloads shaped as:

- `proposals`: list of proposal objects
- each proposal may contain `bounds` as `[left, top, right, bottom]` or `bbox`
  as `[left, top, width, height]`
- alternatively each proposal may contain `mask` rows, either as strings where
  `.`, `0`, space, and `_` are empty or as nested numeric/boolean rows; `x`/`y`
  or `left`/`top` offset the local mask into image coordinates
- optional `confidence`/`score`
- optional `color`

JSON adapter proposals use the same proposal schema and downstream geometry
gate as live SAM proposals. When `mlx-sam` is installed in a compatible Python
environment and `mlx_model_path` points at a `.safetensors` checkpoint, the
`mlx_sam_grid_points` adapter prompts the model with bounded grid points,
converts positive masks to proposal components, and then uses the same geometry
gate. Other non-JSON SAM model paths remain `adapter_pending`.

## Runtime Status Report v1

Written by `morphea status`.
`morphea status --config status.json` accepts `output`, `markdown`, and
`mlx_sam_model_path`. CLI arguments override matching config values.

Top-level fields:

- `schema_version`: currently `1`
- `segmenters`: status for `flat_color` and `mlx_sam`
- `classifiers`: status for `centroid` and `mlx`
- `refinement`: output of `available_refinement_backends()`
- `blocked_backends`: normalized rows for unavailable or non-available
  backends
- `blocked_capabilities`: normalized rows for backend capabilities that are
  unavailable or still pending implementation

Each status entry records `status`, `backend_available`, and optional `reason`
where the underlying backend exposes those fields. The report is intentionally
diagnostic: missing MLX/SAM/DiffVG integrations are reported explicitly instead
of being treated as partial success.

Optional status entries may expose a `capabilities` object. Each capability
records `available`, `status`, and optional `reason`. The current MLX/SAM
capability statuses make `live_sam_model_adapter` explicit as a remaining
blocker. The classifier status also reports available
`end_to_end_token_projection_training` and `end_to_end_attention_training`
capabilities when MLX autograd is usable.

## Segment Config v1

Read by `morphea segment --config`.

Supported fields:

- `input`: input image path
- `output`: output segment proposal manifest path
- `markdown`: optional Markdown proposal report path
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
- `geometry_gate`: default `false`; when true, pending proposals are accepted
  or rejected before serialization using primitive anchor geometry metrics
- `max_anchor_quality_error`: nullable upper bound for gate acceptance,
  default `1.0`
- `require_reserved_anchor`: default `false`; when true, only proposals with a
  reserved simple anchor can pass the geometry gate

CLI arguments override values loaded from the config file.

## Pseudo-Label Harvest v1

Written by `morphea harvest`. `morphea harvest --markdown harvest.md` writes a
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
metrics, run metrics, `source_manifest` provenance, and `group_context` for
scene groups that contained the harvested anchor.

`morphea harvest-curated` first runs a curated real-image suite with each case's
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

Read by `morphea harvest --config`.

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

Read by `morphea harvest-curated --config`.

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

Written by `morphea review` and `morphea apply-review`.
`morphea review --markdown review.md` writes a scan-friendly queue summary while
the editable decisions stay in the JSON review file.

Review queue items contain `decision`, `reason`, `corrected_kind`, `issues`,
and the original `label`. `corrected_kind` lets a reviewer mark a wrong
primitive type without manually editing nested anchor payloads. `issues` is a
free-form string list for structured human notes such as `wrong_primitive_type`,
`bad_cutout`, or `bad_stroke`. Review queue and apply-review artifacts include
`issue_counts` so repeated cut-out, stroke, or primitive-type problems are
visible without scanning every item. Markdown review reports surface label
`group_context` so humans can judge anchors in their grid, stroke-group,
merge, or reservation context.

`morphea apply-review` writes accepted, rejected, and pending splits.
`morphea apply-review --markdown accepted.md` writes a scan-friendly decision
summary next to the JSON artifact. Accepted labels include a `review`
provenance object and apply `corrected_kind` to both the top-level label kind
and embedded anchor kind when present.

When harvested labels carry `group_context`, `morphea merge-labels` preserves it
in each generated pseudo-sample manifest as single-anchor groups with
`source_group_id`, `source_anchor_indexes`, and `source_anchor_position`
provenance.

## Review Config v1

Read by `morphea review --config`.

Supported fields:

- `pseudo_labels`
- `output`
- `markdown`: optional Markdown queue summary path

CLI arguments override values loaded from the config file.

## Apply Review Config v1

Read by `morphea apply-review --config`.

Supported fields:

- `review`
- `output`
- `markdown`: optional Markdown decision summary path

CLI arguments override values loaded from the config file.

## Merge Labels Config v1

Read by `morphea merge-labels --config`.

Supported fields:

- `reviewed_labels`
- `output_dir`

CLI arguments override values loaded from the config file.

## Training Config v1

Read by `morphea train --config`.

Supported fields:

- `dataset`
- `output`

CLI arguments override values loaded from the config file.

## Classifier Evaluation Config v1

Read by `morphea eval-classifier --config`.

Supported fields:

- `model`
- `dataset`
- `output`
- `markdown`: optional Markdown report path
- `splits`: optional non-empty array of dataset split names, defaulting to
  `["val", "test"]`

CLI arguments override values loaded from the config file.

## MLX Training Config v1

Read by `morphea train-mlx --config`.

Supported fields:

- `dataset`
- `output`
- `epochs`
- `hidden_dim`
- `num_heads`
- `num_layers`
- `learning_rate`
- `crop_size`: square RGBA anchor-crop size used by the MLX raster token loader
- `allow_unavailable`: when true, writes a fallback artifact if MLX is not
  installed locally

CLI arguments override values loaded from the config file.

## Training Comparison Config v1

Read by `morphea compare-training --config`.

Supported fields:

- `base_dataset`
- `pseudo_dataset`
- `validation_dataset`
- `output`
- `markdown`: optional Markdown report path

CLI arguments override values loaded from the config file.

## Training Gate v1

Written by `morphea training-gate`.

Top-level fields:

- `schema_version`: currently `1`
- `comparison`: source training comparison JSON path
- `decision`: `accept`, `manual_review`, or `reject`
- `accepted`: boolean shortcut for `decision == "accept"`
- `reasons`: machine-readable gate reasons
- `gates`: active threshold values
- `summary`: copied comparison summary

`morphea training-gate --markdown gate.md` writes a scan-friendly decision
summary next to the JSON artifact.

## Training Gate Config v1

Read by `morphea training-gate --config`.

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

Written by `morphea self-learn` as `self-learning-cycle.json` inside the output
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

`morphea self-learn` always writes comparison and gate artifacts. It writes
`model.json` only when the training gate accepts the reviewed-label
augmentation. When `curated_suite` is configured and retraining is accepted,
the cycle runs `morphea curated-check` with the accepted model as
`classifier_model` and writes curated validation artifacts.

## Self-Learning Config v1

Read by `morphea self-learn --config`.

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

Read by `morphea retrain --config`.

Supported fields:

- `base_dataset`
- `pseudo_dataset`
- `validation_dataset`
- `output`
- `comparison_output`
- `backend`: `centroid` or `mlx`; defaults to `centroid`
- `epochs`: MLX backend only
- `hidden_dim`: MLX backend only
- `num_heads`: MLX backend only
- `num_layers`: MLX backend only
- `learning_rate`: MLX backend only
- `crop_size`: MLX backend only
- `allow_unavailable`: MLX backend only; writes an MLX fallback artifact when
  the optional runtime is not installed

CLI arguments override values loaded from the config file.

## Refine Config v1

Read by `morphea refine --config`.

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

Written by `morphea refinement-gate`.

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

Read by `morphea refinement-gate --config`.

Supported fields:

- `refined_manifest`
- `output`
- `markdown`: optional Markdown report path
- `max_objective_regression`
- `require_improvement`

CLI arguments override values loaded from the config file.

## Generate Config v1

Read by `morphea generate --config`.

Supported fields:

- `output_dir`
- `count`
- `seed`
- `width`
- `height`
- `difficulty`: currently `basic`, `dense`, `grid`, or `logo`
- `val_count`
- `test_count`

CLI arguments override values loaded from the config file. Omitted fields use
the same defaults as the direct CLI: one 96x96 `basic` sample with one
validation and one test slot where possible.

## Synthetic Dataset v1

Written by `morphea generate`.

`dataset.json` records:

- `count`, `seed`, `width`, `height`
- `difficulty`: currently `basic`, `dense`, `grid`, or `logo`
- `splits`
- `anchor_kind_counts`: aggregate ground-truth primitive counts
- `split_anchor_kind_counts`: aggregate ground-truth counts per train/val/test
  split
- `samples`

Each generated sample manifest also includes `seed` and `difficulty` so a
single PNG/JSON pair is reproducible outside the dataset index.
Each dataset sample entry records `anchor_count` and `anchor_kind_counts` so a
training corpus can be audited without reopening every manifest.

Quad anchors may include numeric `metrics.quad_subtype_code` values: `1.0` for
trapezoid and `2.0` for parallelogram. They remain `quad` anchors so the
primitive vocabulary stays small while training data and detected anchors can
still target visually important quad families.

Primitive classifier feature extraction includes `quad_subtype_code` as a
numeric feature. This lets the first classifier learn trapezoid and
parallelogram-sensitive ranking behavior without expanding the top-level class
set or forcing downstream exporters to understand new primitive kinds.

Primitive classifier feature extraction also includes lightweight scene-group
context when a manifest anchor belongs to `groups`. The numeric features record
the group count plus membership flags for `perspective_grid`,
`parallel_stroke_group`, `same_color_fragment_group`, and
`primitive_anchor_reservation`. This lets synthetic and reviewed pseudo-label
training preserve simple-shape and grid context without changing primitive
labels.

## Primitive Classifier Model v1

Written by `morphea train`, `morphea retrain`, and `morphea train-mlx`.

Top-level fields:

- `model_type`: currently `centroid_primitive_classifier` or
  `mlx_transformer_primitive_classifier`
- `feature_names`
- `classes`
- `centroids`
- `feature_importance`: centroid-spread summary sorted by strongest
  class-separating feature; each row records `feature`, `spread`, `min`, and
  `max`
- `train_examples`
- `source_datasets`: present for `morphea retrain`, recording base,
  pseudo-label, and validation dataset paths
- `augmentation`: present for `morphea retrain`, recording base and reviewed
  pseudo-label train example counts
- `evaluation`: direct classifier accuracy/confusion for validation/test splits
- `ranking_evaluation`: heuristic-only versus classifier-prior candidate
  ranking comparison for validation/test splits

`morphea train-mlx` writes `backend`, `backend_available`, `status`, `runtime`,
`reason`, `training_implementation`, `training_config`, `fallback_model_type`,
and `fallback_centroids`. Runtime status distinguishes `not_installed` from an
available MLX package. When MLX is available, status is `trained` and
`mlx_training` stores an optimized normalized feature-head artifact with
`weight_format`, `architecture`, `transformer_status`, `normalization`,
`weights`, `bias`, `loss_history`, `crop_token_spec`, and
`crop_token_summary`. `crop_token_spec` records the square RGBA token shape and
normalization range derived from anchor crops in the source dataset.
`raster_token_mixer` stores a first trainable attention-style block over those
tokens, including head count, embedding names, weights, bias, normalization,
and loss history. `feature_raster_fusion` stores a trainable
`mlx_feature_raster_fusion_v1` head over the concatenated geometric feature row
and raster-token attention embedding. It records feature names, raster
embedding names, fusion strategy, head count, weights, bias, normalization, and
loss history. `token_transformer` stores a serialized `mlx_token_transformer_v1`
encoder path. Its `tokenization` section records feature tokens, crop size,
raster grid size, raster token count, and channel order. Its `encoder` section
records hidden dimension, head count, layer count, projection policy, attention
type, and pooling policy. When MLX autograd is available, `token_projection`
stores `mlx_token_projection_v1` weights, bias, input names, optimizer, and
training example count for the learned token-to-hidden projection.
`attention_parameters` stores `mlx_attention_diagonal_v1` per-layer
query/key/value/output scales and output bias trained with the same MLX
autograd loop. Its classifier head stores weights, bias, normalization, and
loss history over the pooled encoder embedding. `projection_calibration`
records either identity parameters after learned token projection or
training-derived per-dimension scale and bias values for fallback
token-transformer projection paths, plus strategy and training example count.
The fallback centroids keep the artifact usable as a deterministic
`--classifier-model` prior when MLX is not installed.
When `mlx_training.weight_format` is `mlx_feature_head_v1`, classifier loading
uses the serialized MLX feature-head weights for prediction; malformed or
unavailable MLX artifacts degrade to `fallback_centroids`.
During vectorization, valid `raster_token_mixer_v1` artifacts receive
component-derived RGBA crop tokens so candidate-ranking priors can fuse raster
attention logits with feature-head logits. If a valid
`mlx_feature_raster_fusion_v1` block is present, runtime prediction prefers its
learned feature/raster logits when crop tokens are available and falls back to
the separate feature-head plus raster-token mixer otherwise.
If a valid `mlx_token_transformer_v1` block is present, runtime prediction uses
that token-encoder head first, including projection calibration when present,
then falls back through feature/raster fusion, raster-token mixer, feature head,
and finally centroid fallback.

`morphea retrain` persists the augmented model so it can be used as a
`--classifier-model` prior in later vectorize/profile runs. The default
`centroid` backend keeps the original model schema. The `mlx` backend writes an
`mlx_transformer_primitive_classifier` artifact via the train-MLX path, then
adds `source_datasets`, `augmentation`, `retraining_backend`, and the generated
`augmented_dataset` index path. Reviewed pseudo-label samples may omit source
images; they still contribute feature examples, while raster-token training
uses image-backed samples only.

## Classifier Evaluation Report v1

Written by `morphea eval-classifier`. `--markdown report.md` writes a
scan-friendly table view derived from the JSON report, including whether direct
and ranking evaluation used raster-token inputs.

Top-level fields:

- `schema_version`: currently `1`
- `model`
- `dataset`
- `model_type`
- `classifier_backend`: `centroid`, `mlx_feature_head`, or `centroid_fallback`
- `uses_raster_tokens`: true when direct evaluation uses stored RGBA crop-token
  inputs for an MLX raster-token mixer
- `ranking_uses_raster_tokens`: true when candidate-ranking evaluation also
  passes stored RGBA crop tokens through the MLX prior
- `feature_names`
- `classes`
- `splits`
- `evaluation`: direct classifier accuracy/confusion by requested split
- `ranking_evaluation`: heuristic-only versus classifier-prior ranking by
  requested split

The command can evaluate centroid models, MLX fallback artifacts, and
`mlx_feature_head_v1` artifacts. When a valid `raster_token_mixer_v1`,
`mlx_feature_raster_fusion_v1`, or `mlx_token_transformer_v1` block is present,
direct accuracy/confusion use RGBA crop tokens from the dataset;
candidate-ranking evaluation also uses dataset crop tokens and records
`uses_raster_tokens` on each ranking split.

## Training Comparison v1

Written by `morphea compare-training`.

Top-level fields:

- `schema_version`: currently `1`
- `base_dataset`
- `pseudo_dataset`
- `validation_dataset`
- `baseline`: centroid classifier summary trained only on base train examples
- `augmented`: centroid classifier summary trained on base plus reviewed
  pseudo-label train examples
- `delta`: training-count, accuracy, ranking, and feature-importance spread
  changes from baseline to augmented
- `summary`: scan-friendly augmentation verdict with status, metric count,
  best/worst accuracy deltas, and train-example delta

Both `baseline` and `augmented` include validation/test `evaluation` and
`ranking_evaluation` sections plus `feature_importance` using the same
validation dataset. The report is
intended to show whether reviewed pseudo-labels improve, degrade, or leave
candidate ranking unchanged before a heavier retraining backend is introduced.
`morphea compare-training --markdown comparison.md` writes a scan-friendly
Markdown table derived from the same JSON report.

## Snapshot Comparison v1

Written by `morphea compare-snapshots` and `morphea compare-git-snapshots`.

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

`morphea compare-snapshots --markdown comparison.md` writes a scan-friendly table
for reviewing differences between saved reports from different commits or
configurations.

## Snapshot Comparison Config v1

Read by `morphea compare-snapshots --config`.

Supported fields:

- `before`
- `after`
- `output`
- `markdown`: optional Markdown comparison path

CLI arguments override values loaded from the config file.

## Git Snapshot Comparison Config v1

Read by `morphea compare-git-snapshots --config`.

Supported fields:

- `before_ref`
- `after_ref`
- `path`: checked-in snapshot path to read from both refs
- `output`
- `markdown`: optional Markdown comparison path
- `repo`: optional repository root, defaults to `.`

CLI arguments override values loaded from the config file.

`morphea compare-git-snapshots before_ref after_ref --path snapshot.json` reads
the same checked-in snapshot file from two git refs with `git show` and does
not modify the current working tree.

## Snapshot Git Ref Config v1

Read by `morphea snapshot-git-ref --config`.

Supported fields:

- `ref`
- `suite`
- `output`
- `report`: optional curated-check report path
- `output_dir`: optional curated-check output directory
- `repo`: optional repository root, defaults to `.`
- `timeout_seconds`: optional curated-check timeout, defaults to `120`
- `run`: optional boolean, defaults to `true`

CLI arguments override values loaded from the config file.

`morphea snapshot-git-ref REF --suite suite.json -o snapshot.json` creates a
temporary detached git worktree for `REF`, runs `morphea curated-check` inside
that worktree, and writes a normal Curated Snapshot v1 file to the requested
output path. The snapshot file intentionally stays compatible with
`morphea compare-snapshots`; git metadata is returned by the command result but
is not embedded into the deterministic snapshot.

## Segment Manifest Comparison v1

Written by `morphea compare-segments`.

Top-level fields:

- `schema_version`: currently `1`
- `before`
- `after`
- `before_source`
- `after_source`
- `before_proposal_count`
- `after_proposal_count`
- `proposal_count_delta`
- `shared_proposal_count`
- `added_ids`
- `removed_ids`
- `shared_group_count`
- `added_group_ids`
- `removed_group_ids`
- `summary_deltas`: count deltas across segment summary groups such as
  `downstream_status_counts`, `anchor_kind_counts`, and
  `downstream_decision_reason_counts`
- `config_deltas`: changed segment config keys between the two manifests
- `proposal_changes`: changed fields for shared proposal ids, including
  downstream status, rejection reason, anchor kind, reservation state,
  anchor-quality error, decision reason, and bounds
- `proposal_group_changes`: changed group kind, proposal membership, and
  numeric group metrics for shared proposal group ids

`morphea compare-segments --markdown comparison.md` writes a scan-friendly
Markdown summary for comparing flat-color and future MLX proposal outputs or
for comparing gated and ungated segment configs.

## Segment Comparison Config v1

Read by `morphea compare-segments --config`.

Supported fields:

- `before`
- `after`
- `output`
- `markdown`: optional Markdown comparison path

CLI arguments override values loaded from the config file.

## Run Directory v1

Written by `morphea vectorize --run-dir` and by each `morphea sweep` run.

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
from manifest diagnostic codes or an explicit diagnostic `stage` field. Current
stage buckets are `preprocessing`, `palette`, `segmentation`, `fitting`,
`cleanup`, `scoring`, `export`, `runtime`, and `unknown`.

## Refinement Metadata v1

Written by `morphea refine`.

Recognized backends:

- `local_metric`: active structure-preserving local optimizer
- `differentiable`: active built-in soft-raster gradient backend, currently
  scoped to structure-preserving circle-radius, quad-like transform, and
  stroke-like transform refinement
- `diffvg`: optional external differentiable-renderer backend name that fails
  with an explicit not-installed/not-configured error until the adapter is
  wired

`available_refinement_backends()` also exposes per-backend `details`. Optional
backend status for `diffvg` distinguishes `not_installed` from
`adapter_pending`, records `package_available`, and lists package candidates
such as `pydiffvg`/`diffvg`. Even when a package is present, `diffvg` remains
unavailable until a renderer adapter is wired.

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
The differentiable backend uses a soft primitive rasterizer with an analytic
radius-gradient step for editable circle anchors and bounded soft-objective
translation/scale gradients for quad-like anchors plus translation/width
gradients for stroke-like anchors. Its optimizer metadata records
`renderer: soft_raster_primitives`, `renderer_primitive_kinds`, soft objective
deltas, optimized parameter kinds, timeout state, and the same hard raster
L1/edge metrics used by gates and reports.

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
