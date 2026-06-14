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
- `editability_review`: present in curated promotion manifests; accepted-output
  review decision derived from promotion state and v10 editability component
  thresholds

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
- `promotion_state`: present in curated promotion manifests; one of
  `promoted`, `deferred`, `rejected`, or `fallback`
- `promotion_regions`: present in curated promotion manifests; region refs that
  selected this anchor, with region id, state, gate id, and reason
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
- `structured_text_fallback_count`
- `unstructured_generic_path_count`
- `cutout_anchor_count`
- `cutout_overlay_count`
- `negative_mask_candidate_count`
- `group_count`
- `simple_shape_ratio`
- `fragmentation_penalty`
- `unstructured_fragmentation_penalty`
- `unstructured_fragment_counts`
- `editability_components`: formula-level component breakdown for
  `editability_score`, currently including `simple_shape_ratio`,
  `fragmentation_penalty`, `diagnostic_penalty`, `generic_path_penalty`,
  `unclipped_score`, and `clipped_score`
- `editability_v10_components`: review-level component scores for the RIP4
  contract, including shape identity, parameter economy, node economy, stroke
  width stability, line/curve smoothness, topology consistency, grouping,
  fragmentation, raster fidelity, provenance, and classifier-prior agreement.
  The parameter economy component includes `budget`, `max_parameter_count`,
  `over_budget_anchor_count`, and `top_contributors` evidence so reviewers can
  identify the shapes that dominate the score before changing detectors or
  thresholds.
  The v10 fragmentation component scores `unstructured_fragmentation_penalty`
  so expected repeated primitives such as table cells, circles, and cutout
  strokes do not count as review-blocking fragmentation, while the raw
  `fragmentation_penalty` remains available for aggregate diagnostics.
  Text-like grouping only marks small glyph-sized cubic paths as structured;
  larger same-color organic fallback paths remain in
  `unstructured_generic_path_count` and `unstructured_fragmentation_penalty`.
  Components may include `observed`, source metrics, and gate-capping fields:
  `gate_blocked`, `failed_gates`, and `uncapped_score`.
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
  `same_color_fragment_group`, `text_like_fragment_group`, or
  `primitive_anchor_reservation`
- `anchor_indexes`
- `metrics`
- `color`: present for `same_color_fragment_group` and
  `text_like_fragment_group`
- `merge_plan`: present for `same_color_fragment_group`; records the
  recommended action, `auto_merge_allowed`, decision reason, target kind,
  combined bounds, per-fragment bounds, and bounds fill ratio for later
  merge/review steps
- `fallback_anchor_indexes`: present for `text_like_fragment_group`; identifies
  bounded glyph-like `cubic_path` fallbacks that remain review-visible but are
  not counted as unstructured v10 fallback debt
- `candidate_fallback_path_count` and `excluded_fallback_path_count`: present
  in `text_like_fragment_group.metrics`; show how many same-color cubic paths
  were considered and how many were left as non-text fallback debt
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

Each run summary also carries `editability_score`, `editability_components`,
`editability_v10_components`, `fragmentation_penalty`, `raster_l1_error`,
`raster_edge_error`, `semantic_rank`, and `diagnostic_stage_counts` when the
manifest contains those metrics and diagnostics.

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
The generated HTML is deterministic and contains no timestamps. Homepage hero
and teaser blocks select only passing primitive-check cases and count passing
cases in their gallery link text; failed cases may remain visible in the full
QA gallery but are not published as proof examples.

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
`output_dir`, `run`, `snapshot`, `baseline_snapshot`, and `markdown`. CLI
arguments override matching config values, and `run` must be a boolean when
provided in JSON.

`morphea promotion-review-run suite.json --output-dir review-run` is a
review-oriented wrapper around `curated-check`: it runs the suite, writes
`curated-report.json`, `curated-report.md`, and `curated-snapshot.json` under
the output root by default, and emits the same per-case artifacts,
`review-packet.json`, `review-packet.md`, and `review-gallery.html`. It also
writes `promotion-review-harvest.json`, a starter config with empty
`decisions`, empty `decision_overrides`, per-case `decision_templates` for
reviewer selection, and stable paths for `promotion-review-harvest --config`.
After the starter config exists, `promotion-review-run` rewrites the review
packet and gallery with per-case `decision_choice_commands`, so the first
review packet shows the explicit `promotion-review-harvest --decision-choice`
path as well as the template-edit apply path.
The final `curated-report.json`
and `curated-report.md` also include `next_commands`, starting with the exact
harvest command for the generated starter config.

Curated suite expectations support four mutually exclusive check types:
`kind` with `min_count` and optional `max_count`, `kinds` with a non-empty array
of accepted anchor kinds plus `min_count` and optional `max_count`, `group_kind`
with `min_count` and optional `max_count`, or `metric` with `min_value` and/or
`max_value`. Metric expectations read top-level manifest `metrics` values such
as `editability_score`, `simple_shape_ratio`, and `fragmentation_penalty`.

Repeated `kind`, `kinds`, or `group_kind` expectations are cumulative per
selector. For example, two separate `kind: circle`, `min_count: 1` expectations
require two distinct circle anchors; the second result records
`cumulative_min_count: 2`. A `kinds` expectation counts anchors whose `kind`
matches any listed value, which is useful when one semantic role may be
represented by several editable primitive classes such as `stroke_polyline`,
`stroke_path`, or `arc`.

Lucide suite `kind` expectations may also include `bounds` as
`[left, top, right, bottom]` plus optional `min_iou` to restrict matching to a
source region. This keeps compound icons from satisfying unrelated expectations
with the same global anchor kind; failed expectation rows report
`failure_reason` plus shortfall/excess fields such as `missing_count`.
Lucide suite cases may also carry optional visual-review metadata:
`quality_label` (`green`, `yellow`, or `red`) and `review_notes`. Yellow or red
labels require at least one review note. `morphea lucide-check` copies those
fields into case reports, derives `quality_summary`, and the Markdown report
writes a Quality Ledger that names yellow/red cases separately from semantic
pass/fail status.

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
- `quality_label_review_policy`: optional; when set to
  `manual_review_pending` on a red `current_quality_label`, the quality-label
  gate remains failed but is treated as yellow/deferred review evidence instead
  of a detector rejection
- `current_status`: current pipeline status such as
  `checked_failed_expectations`, `checked_expectations_pass_but_not_promotable`,
  or `missing_source`
- `current_issues`: string array of issue tags, for example
  `fragmentation`, `missing_promotion_state`, or `missing_local_source`
- `visual_audit_status`: current visual artifact posture, for example
  `contact_sheet_available` or `unavailable_missing_source`
- `visual_thresholds`: optional per-family visual fidelity thresholds. The
  object includes optional `family`, `max_raster_l1_error` and/or
  `max_raster_edge_error`, optional `severity`, and optional `description`.
  Thresholds are evaluated as a derived `visual_fidelity_thresholds` promotion
  gate after the checked run has written raster metrics into the report.
- `structure_thresholds`: optional fragmentation/layer-depth thresholds. The
  object includes `max_fragmentation_penalty`, `max_layer_count`, and/or
  `max_structural_layer_count`, optional `non_structural_layer_roles`, optional
  `severity`, and optional `description`. `max_layer_count` checks raw manifest
  layer count. `max_structural_layer_count` checks an effective layer count
  after excluding explicitly configured non-structural roles such as
  `cutout_overlays`. Thresholds are evaluated as a derived
  `fragmentation_layer_thresholds` promotion gate.
- `hard_gates`: optional array of explicit promotion gates. Each gate includes
  `id`, `gate_type`, `expectation_ids`, optional `severity`, and optional
  `description`. Supported `gate_type` values are `shape_class`, `topology`,
  `grouping`, `fragmentation`, `visual_fidelity`, `provenance`, and
  `review_safety`. `expectation_ids` must reference expectations in the same
  case.
- `region_gates`: optional array of source-region promotion gates. Each gate
  includes `id`, `gate_type`, `bounds`, `expected_kinds` and/or
  `forbidden_kinds`, optional `min_count`, optional `max_count`, optional
  `min_iou`, optional topology limits, optional region visual thresholds
  (`max_raster_l1_error` and/or `max_raster_edge_error`), optional `severity`,
  and optional `description`. `bounds` are `[left, top, right, bottom]` in
  manifest/source coordinates. Region gates select anchors whose manifest
  `source_mask.bounds` overlap the region by at least `min_iou`, then check the
  selected anchor kinds.

Region gate topology limits are optional non-negative integer fields:
`min_closed_anchors`, `max_closed_anchors`, `min_open_anchors`,
`max_open_anchors`, `max_hole_count`, `max_cutout_count`,
`min_nested_contours`, `max_nested_contours`, and
`max_disconnected_components`. Region gates may also set
`required_topology_descriptors` or `forbidden_topology_descriptors`.
`nested_contour_count` is a conservative per-region proxy derived from hole
counts plus cutout anchors. Region-gate evidence includes
`topology_summary` with selected-anchor, closed/open, hole, cutout, disconnected
component, nested-contour, descriptor, and kind-count summaries.
`topology_descriptors` is a compact label list such as `empty`, `closed`,
`open`, `mixed_open_closed`, `single_component`, `multi_component`, `holes`,
`cutouts`, or `nested_contours`. Required and forbidden descriptor lists are
copied into gate evidence and shown in Region Truth expected values. Evidence
also includes
`candidate_rejections` for selected anchors that were rejected by the gate,
with anchor id, kind, bounds, overlap metrics, reject reasons such as
`kind_mismatch`, `forbidden_kind`, or `topology_failure`, and topology failures
when applicable.
For checked cases, region-gate evidence also includes `visual_delta`: a
source-vs-exported-SVG crop comparison for the region bounds, with crop
`bounds`, `width`, `height`, `raster_l1_error`, `raster_edge_error`,
`raster_alpha_error`, and `raster_size_match`. If the region gate sets visual
thresholds, evidence also includes `visual_thresholds` and `visual_failures`.
`curated-check --markdown` includes a Region Truth table for these gates,
showing the stable region/gate id, promotion state, bounds, expected and
forbidden kinds, matching/selected/forbidden/rejected counts, and topology
summary plus the compact region visual delta, thresholds, and failures when
available.
- `group_gates`: optional array of manifest-group promotion gates. Each gate
  includes `id`, `gate_type` (`grouping` or `fragmentation`),
  `expected_group_kinds`, optional `min_count`, optional `max_count`, optional
  `min_member_count`, optional `max_member_count`, optional `severity`, and
  optional `description`. Group-gate evidence includes selected group ids,
  kinds, member counts, and group metrics.
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
- `layer_count`
- `layer_anchor_counts`
- `diagnostic_count`
- `metrics`: run metrics such as editability and raster-fidelity values
- `promotion`: optional copied promotion metadata from the source suite case

Snapshots avoid timestamps and run-directory paths so they can be diffed across
commits and configurations. Promotion-gate snapshot evidence for source
availability and contact sheets is reduced to stable booleans instead of local
source or artifact paths.

When `curated-check --output-dir` is used for checked cases, each per-case run
directory includes the standard vectorize artifacts plus:

- `svg-render.png`: deterministic rasterization of the exported SVG
- `diff.png`: red/blue source-vs-SVG visual difference image
- `anchor-overlay.png`: source image with manifest anchor bounds overlaid
- `promoted.svg`: semantic SVG containing only anchors selected by promoted
  promotion regions
- `fallback.svg`: SVG containing anchors not selected for promoted export,
  including rejected or deferred anchors that must remain outside trusted
  semantic output
- `promotion-export.json`: promoted/fallback anchor-index partition,
  fallback-only/rejected/deferred anchor-index partitions, anchor-state counts,
  region-state counts, region state records, promotion-gate records, and
  promoted/fallback SVG paths
- `promotion-regions.json`: region-state review data with selected anchor ids,
  selected anchor indexes, gate status, state, and rejection/defer reason
- `promotion-review.md`: scan-friendly Markdown review of anchor state counts,
  promoted/deferred/rejected regions, and candidate rejections from region-gate
  evidence
- `editability-review.md`: scan-friendly Markdown review of accepted-output
  decision, component thresholds, gate-blocked components, issue tags, and
  regression deltas
- `review-decision.json`: machine-editable review decision record with
  `decision: pending`, allowed terminal decisions (`accepted`, `corrected`,
  `rejected`, `deferred`), suggested decision, issue tags, failed gates,
  failed/gate-blocked components, regression evidence, and
  `quality_label_policy`. Checked output records also carry `review_artifacts`
  that link back to the manifest, promotion-region JSON, promotion review, and
  editability review.
- `review-templates/{accepted,corrected,rejected,deferred}.json`: terminal
  reviewer decision templates derived from the pending decision record. Each
  template preserves the same gate/component evidence, sets one terminal
  decision, and marks whether the template accepts promotion, matches the
  suggested decision, requires reviewer/reason evidence, or requires correction
  notes/artifacts. Templates also preserve `quality_label_policy`.
- `region-overlay.png`: source image with configured source-region gates
  highlighted by gate outcome; failed red gates use red outlines, failed yellow
  gates use yellow outlines, and passing regions use green outlines
- `contact-sheet.png`: source, manifest preview, anchor overlay, region
  overlay, SVG render, diff, promotion decision, and failed-gate panels for
  cases with promotion metadata

The curated output root also includes suite-level review packet artifacts:

- `review-packet.json`: machine-readable queue of deferred/rejected cases that
  need a reviewer decision, with issue tags, failed gate/component ids, failed
  gate details (`id`, `gate_type`, `severity`, and `reason`), suggested
  decision, paths to per-case review artifacts, and paths to terminal reviewer
  decision templates. Each queued case also carries
  `quality_label_policy` and `review_requirements`, which names fields required
  for all terminal decisions (`reviewer`, `reason`) and the extra fields
  required for corrected decisions (`correction_notes`, `corrected_artifacts`).
  Cases with a manifest and terminal templates also carry `review_commands`,
  copy/paste `promotion-apply-review` commands for each terminal decision.
  Review packets produced by `promotion-review-run` also carry
  `review_harvest_config`, `review_harvest_command`, and per-case
  `decision_choice_commands` plus `decision_choice_evidence_flags`, exposing
  the no-JSON-edit reviewer path directly from the initial packet.
- `review-packet.md`: scan-friendly Markdown summary of the same queue, with
  links/paths to contact sheets, promotion reviews, editability reviews,
  failed-gate detail tables, and `review-decision.json` files plus
  accepted/corrected/rejected/deferred template paths, the same
  terminal/corrected review requirements, and per-decision apply and
  harvest-choice commands
- `review-gallery.html`: local static gallery for promotion cases in the suite
  run. It shows quality label, promotion/editability decisions, issue tags,
  failed gate/component ids, failed-gate reason summaries, the contact sheet
  image, review artifact links, terminal decision-template links, review-packet
  apply commands, and harvest-choice commands without requiring raw JSON
  inspection.

When `curated-check --markdown` is used, the suite Markdown report includes a
Corpus Ledger table before the promotion-gate details. The ledger surfaces each
promotion case's red/yellow/green quality label, current status, stress family,
expected promotion families, issue tags, and licensing status, with per-case
detail sections repeating source provenance and expected promotion families so
reviewers do not need to inspect raw suite JSON for the corpus contract. The
same Markdown report includes a Promotion Gate Details table for failed gates,
including case id, gate id, gate type, severity, and reason.

When a suite case includes `promotion` metadata, checked and missing-source
case reports also include:

- `promotion_gates`: derived hard-gate results for `source_available`,
  `semantic_expectations`, `visual_contact_sheet`, `current_quality_label`, and
  any case-specific `promotion.hard_gates`, `promotion.region_gates`,
  `promotion.group_gates`, `promotion.structure_thresholds`, or
  `promotion.visual_thresholds`
- `promotion_summary`: compact decision summary with `decision`, failed gate
  count, red/yellow gate counts, and optional `deferred_reason`
- `promotion_regions`: region-level promotion state derived from
  `promotion.region_gates`, including region id, state (`promoted`, `deferred`,
  or `rejected`), bounds, gate id, selected anchor ids/indexes, gate status, and
  reason. Checked cases also include per-region layer evidence derived from the
  selected anchors: `layer_roles`, `layer_role_counts`, `region_layer_count`,
  `structural_layer_roles`, `structural_layer_count`, and
  `non_structural_layer_roles`. They also include a selected-anchor profile with
  `selected_anchor_kind_counts`, `selected_simple_anchor_count`,
  `selected_stroke_anchor_count`, and `selected_generic_path_anchor_count` so
  region-level fragmentation and fallback shape mix can be reviewed without
  scanning every anchor. When available, `visual_delta`, `visual_thresholds`,
  and `visual_failures` are copied from the corresponding region-gate evidence
  so promotion exports and review Markdown can show the same region-level
  raster delta and threshold result.
- `editability_review`: accepted-output review decision with `decision`
  (`accepted`, `manual_review`, or `rejected`), `accepted`, component
  `thresholds`, `component_scores`, `failed_components`,
  `gate_blocked_components`, `regression_delta_status`, `regression_deltas`,
  `regressed_components`, and `reasons`
- `review_decision`: machine-editable reviewer decision record with a pending
  `decision`, suggested accepted/corrected/rejected/deferred outcome, issue
  tags, failed gates, component failures, gate-blocked components, and
  regression evidence. Checked output records include `review_artifacts` links
  to the run manifest, promotion-region JSON, promotion review, and editability
  review. Its `quality_label_policy.mode` is `sidecar_only`: applied reviews do
  not update `current_quality_label` automatically.

For checked cases with `--output-dir`, the run `manifest.json` also includes a
top-level `promotion` object with summary, gates, regions, and promotion export
editability-review, and review-decision artifact paths. Anchors selected by
promotion regions are annotated with `promotion_state` and
`promotion_regions`; unselected anchors are marked `fallback`. The manifest
also preserves the same per-region layer evidence under `promotion.regions`,
plus review-template paths and top-level `editability_review` and
`review_decision`, so the accepted-output decision and the editable
human-review decision record are preserved with the run artifact.

Curated `promoted.svg` and `fallback.svg` use the same stable promotion-node
metadata as `morphea promotion-export`: emitted SVG shapes are wrapped with
anchor id, anchor index, promotion state, source promotion region ids, and
review-decision metadata.

`morphea promotion-export manifest.json --promoted-svg promoted.svg
--fallback-svg fallback.svg -o promotion-export.json --markdown
promotion-export.md` can regenerate the promoted/fallback SVG partition from
any promotion-annotated manifest. The JSON output includes the same promoted,
fallback-only, rejected, and deferred anchor state partition as curated run
sidecars, a zero-filled `export_summary`, and copied promotion `regions` with
gate/reason evidence. Exported SVG shapes are wrapped in stable `<g>` nodes
with `data-morphea-anchor-id`, `data-anchor-index`, `data-promotion-state`,
optional `data-promotion-regions`, and applied-review decision metadata when
the manifest contains `review_decision_applied`. The optional Markdown report
summarizes promoted/fallback/rejected/deferred anchor and region counts and
lists fallback, rejected, and deferred items missing from the promoted SVG.

`morphea promotion-apply-review review-decision.json -o applied-review.json
--markdown applied-review.md --manifest manifest.json` consumes an edited
terminal review decision, rejects still-pending decisions, requires non-empty
`reviewer` and `reason` evidence, writes an applied review summary, and can
persist `review_decision_applied` back into the run manifest and its top-level
`promotion` object. `corrected` decisions additionally require
`correction_notes` and at least one `corrected_artifacts` entry, so corrected
records cannot be harvested without correction evidence. Terminal records may
also carry `reviewed_region_ids`: when such a record is applied against a
manifest, accepted/corrected decisions validate those ids against
`promotion.regions`, require each listed region to be gate-ok or already
promoted, and mark only those reviewed regions plus their selected anchors as
review-promoted. Unknown or gate-failed reviewed regions are rejected rather
than turned into training evidence. Generated terminal templates may be applied
without manually editing JSON by passing
`--reviewer`, `--reason`, and for corrected reviews `--correction-notes` plus
one or more `--corrected-artifact` values, plus repeatable
`--reviewed-region region-id` values for explicit region-scoped evidence;
these CLI values are recorded as review overrides in the applied summary. The
applied summary includes
`quality_label_policy` with `mode: sidecar_only` and
`updates_current_quality_label: false`, preserves `review_artifacts`, and
renders those links plus reviewer/reason evidence in Markdown before the
gate/component evidence, so accepted/corrected reviews remain promotion
evidence until suite metadata is deliberately edited.

`morphea promotion-review-harvest review-packet.json -o review-harvest.json
--harvest-config harvest-curated.json --decision case-id=terminal-decision.json`
is the suite-level bridge from review packets to harvest preparation. It
applies only explicitly supplied terminal decision files, writes
`applied-review.json` / `applied-review.md` beside the case manifest via the
same `promotion-apply-review` rules, summarizes applied, harvestable, and
pending cases, and writes a `harvest-curated --config` file with
`require_applied_review: true`. Applied case rows include reviewer, reason,
source decision path, promoted-anchor count, harvest block reason, and applied
review-artifact links, so harvestable and blocked applied cases remain
auditable from the prep report. Cases without an applied review remain
pending in the prep report rather than becoming implicit training candidates.
Pending cases carry available terminal `decision_templates` in JSON and
Markdown when the review packet or config exposes them, so reviewers can see the
accepted/corrected/rejected/deferred choices without applying them
automatically. Pending cases also preserve packet `review_artifacts` links for
contact sheets, promotion reviews, editability reviews, pending decision
records, and promotion exports, so the harvest-prep report can be used without
opening raw packet JSON. Pending cases also carry packet `failed_gate_ids` and
structured `failed_gate_details`; Markdown renders a compact failed-gate list
in the Pending Cases table plus a Pending Gate Details table with case, gate,
type, severity, and reason. The same inputs can be loaded from
`morphea promotion-review-harvest --config promotion-review-harvest.json`;
CLI arguments override config values, and individual `--decision case=path`
arguments override same-case entries in the config `decisions` object. The
shortcut `--decision-choice case=accepted` resolves an explicit terminal choice
through the available `decision_templates`; config `decision_choices` use the
same mechanism and remain overrideable by CLI choices or direct `--decision`
paths. The same command accepts case-scoped CLI evidence flags:
`--reviewer case=name`, `--reason case=reason`,
`--correction-notes case=notes`, and repeatable
`--corrected-artifact case=path` and `--reviewed-region case=region-id`;
these flags override same-case `decision_overrides` from config and are passed
through to
`promotion-apply-review`. When the prep run itself is driven by `--config`,
pending cases also carry `decision_choice_commands` in JSON and Markdown:
one copy/paste command per available terminal template, shaped like
`promotion-review-harvest --config ... --decision-choice case=decision`. The
prep report also carries `decision_template_readiness`, marking whether each
terminal template already has required reviewer evidence; generated templates
normally report missing `reviewer` and `reason` until edited or until
case-scoped `decision_overrides` supply the same evidence. The
`decision_template_readiness_summary` block aggregates ready templates, ready
cases, and missing-field counts so reviewers can see remaining evidence debt
without scanning every row. It also carries
`decision_choice_evidence_flags`, a non-executing hint map of reviewer-evidence
flags to add to a selected decision-choice command. Markdown renders those
flags beside each command with a reminder to replace placeholders before
running.

`morphea harvest --require-applied-review` filters run manifests through
`review_decision_applied`: only `accepted` and `corrected` applied decisions
can become pseudo-label candidates. When a manifest carries promotion-state
annotations, accepted/corrected reviews also require at least one
`promotion_state: promoted` anchor, and only promoted anchors from that run are
harvested. Accepted reviews over fallback-only or deferred-only promotion
exports are rejected as
`applied_review_without_promoted_anchors`. Missing, invalid, `rejected`, and
`deferred` applied decisions remain visible in `rejected_runs`.

`morphea harvest-curated --require-applied-review` preserves existing
`review_decision_applied` records from the run root across the fresh curated
rerun, writes restored decisions back into the new per-case manifest and
curated JSON report, then harvests only accepted/corrected applied decisions.

`morphea review --accept-applied-reviews` converts harvested
`review_decision_applied` evidence into the existing review/apply-review path:
`accepted` and `corrected` applied decisions become `accept` review items,
`rejected` and `deferred` applied decisions become `reject` items, and issue
tags are preserved for reviewed-label reports and training datasets.

`morphea merge-labels` writes accepted reviewed pseudo-label manifests with
`review` and `review_decision_applied` provenance when available. Dataset
samples also carry `review_item_id`, `review_reason`, `review_issues`,
`applied_review_decision`, `applied_review_case_id`, and
`applied_review_source_review_decision`, so accepted/corrected applied
promotion reviews remain auditable after conversion to trainable data while
rejected/deferred review items are excluded.

`morphea self-learn` now separates retraining from acceptance: the cycle can
write a model after the training comparison gate passes, but `accepted` is only
true when the training gate accepts and, when a curated suite is configured,
the classifier-backed curated validation also passes. The cycle summary also
records reviewed-label issue counts and applied-review decision counts from the
pseudo-label dataset; the Markdown report additionally summarizes reviewed-label
issue counts and which review/apply-review provenance fields are present on
dataset samples.

Training comparison reports include per-label `label_accuracy` for validation
splits and `delta.label_accuracy` rows. These label-level deltas are included
in the best/worst accuracy summary, so a regression in one primitive family can
block the training gate even if aggregate accuracy improves.

Curated real-image reports include `family_summary` keyed by stress family,
with case, checked, passed, failed, and missing-source counts. Self-learning
cycle reports normalize primitive label deltas, curated real-image families,
and optional Lucide families into `suite_family_validation`, so acceptance can
be reviewed side by side instead of by aggregate suite status alone.
When `suite_family_baseline` is configured, the cycle compares the normalized
family view against a fixed baseline and reports `suite_family_baseline_comparison`.
New bad outcomes block acceptance, already-known baseline debt is reported in
`known_debt` / `known_debt_count` without being classified as newly introduced,
and formerly bad families that are now passing are reported in
`resolved_regressions` / `resolved_regression_count`.

`promotion_summary.decision` is `promoted` only when all derived gates pass,
`rejected` when any failed gate has red severity, and `deferred` when only
yellow gates fail. A red `current_quality_label` normally remains a red
review-safety gate, but `quality_label_review_policy:
manual_review_pending` intentionally downgrades that single quality-label gate
to yellow so mechanically green cases can enter explicit manual review without
being marked promoted. Missing-source promotion cases are also `deferred` with
`deferred_reason: missing_source`; their red gates remain visible so they still
count as unavailable suite evidence.

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

`backend` records `source`, `backend_available`, `status`, an optional
`reason`, and an optional `next_action`. MLX SAM status distinguishes
`json_adapter_available`, `mlx_sam_package_available`, `not_installed`,
`not_configured`, `model_missing`, `mlx_sam_package_missing`, and
`adapter_pending`; it also records `package_available`,
`sam_package_available`, `model_configured`, `model_exists`,
`model_sidecar_path`, `model_sidecar_exists`, adapter name, runtime knobs, and
per-capability status for `json_proposal_adapter` and
`live_sam_model_adapter`. The sidecar fields are diagnostic only: quantized
MLX/SAM checkpoints normally need the adjacent `.safetensors.json` file, while
unquantized checkpoints may not. The JSON adapter is a local bridge for
checked-in or generated proposal payloads shaped as:

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
`mlx_sam_model_path`. CLI arguments override matching config values. `output`
and `markdown` are optional; when neither is provided, the CLI renders the
Markdown status report to stdout.

Top-level fields:

- `schema_version`: currently `1`
- `segmenters`: status for `flat_color` and `mlx_sam`
- `classifiers`: status for `centroid` and `mlx`
- `refinement`: output of `available_refinement_backends()`
- `blocked_backends`: normalized rows for unavailable or non-available
  backends
- `blocked_capabilities`: normalized rows for backend capabilities that are
  unavailable or still pending implementation

Each status entry records `status`, `backend_available`, optional `reason`, and
optional `next_action` where the underlying backend exposes those fields. The
report is intentionally diagnostic: missing MLX/SAM/DiffVG integrations are
reported explicitly instead of being treated as partial success.
Markdown status reports include a Backend Diagnostics table when status entries
carry runtime detail fields such as `adapter`, `model_path`, `model_exists`,
`model_sidecar_path`, `model_sidecar_exists`, `package_available`, or
`sam_package_available`.

Optional status entries may expose a `capabilities` object. Each capability
records `available`, `status`, optional `reason`, and optional `next_action`.
The current MLX/SAM capability statuses make `live_sam_model_adapter` explicit
as a remaining blocker and point missing runtimes at the corresponding `uv`
setup command. The classifier status also reports available
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
- `max_component_area`: defers oversized Flat-Color components and oversized
  MLX/SAM adapter masks before geometry gating
- `split_components`: default `true`, emits connected-component proposals
  instead of one proposal per color mask
- `mlx_model_path`: local JSON proposal payload or `.safetensors` checkpoint
  path. Segment manifests serialize this as a string whether it came from a
  config file or the `--mlx-model-path` CLI flag.
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

The checked-in configs under `docs/real-images/mlx-sam-smoke/` are the current
repeatability fixture for the live MLX/SAM smoke. They use repo-relative input
and checkpoint paths, write generated artifacts to `/tmp/morphea-mlx-sam-smoke`,
and should remain runtime evidence until comparison reports show an improved
promotion signal.

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

## Promotion Review Harvest Config v1

Read by `morphea promotion-review-harvest --config`.

Supported fields:

- `review_packet`: suite-level `review-packet.json` path
- `output`: harvest-prep JSON report path
- `markdown`: optional harvest-prep Markdown report path
- `harvest_config`: optional generated `harvest-curated` config path
- `decision_plan`: optional portable reviewer decision overlay path. The plan
  can carry `decision_choices` and `decision_overrides` without embedding
  run-local template paths; those choices are resolved through the generated
  config's `decision_templates` or the review packet.
- `decisions`: object mapping case ids to terminal
  `review-decision.json` paths
- `decision_choices`: optional object mapping case ids to terminal decision
  names (`accepted`, `corrected`, `rejected`, or `deferred`). Choices are
  resolved through `decision_templates` or the review packet's template paths;
  they are explicit reviewer selections, not automatic defaults.
- `decision_templates`: optional review-run metadata mapping case ids to
  available terminal decision template paths. This field is accepted in config
  files for reviewer convenience but is not applied automatically; reviewers
  still select terminal decisions by populating `decisions`, using
  `decision_choices`, or passing `--decision` / `--decision-choice`.
- `decision_overrides`: optional object mapping case ids to explicit review
  evidence fields passed to `promotion-apply-review` when that case's terminal
  decision is applied. Supported fields are `reviewer`, `reason`,
  `correction_notes`, `corrected_artifacts`, and `reviewed_region_ids`. These
  values let generated terminal templates stay unedited while the config still
  supplies the required reviewer evidence; applied summaries record the fields
  as review overrides.
- `suite`: optional suite override for the generated harvest config
- `run_root`: optional run-root override for manifest lookup and generated
  harvest config
- `harvest_output`: optional pseudo-label output path for the generated
  harvest config
- `curated_report`: optional curated report path for the generated harvest
  config
- `snapshot`: optional curated snapshot path for the generated harvest config
- `harvest_markdown`: optional pseudo-label Markdown report path for the
  generated harvest config

CLI arguments override values loaded from the config file. `decision_plan`
values are merged after the base config and before explicit CLI flags, so a
checked-in portable review plan can be replayed against a fresh generated
review run while still allowing one-off command-line overrides. `--decision`
arguments are merged into the config `decisions` object and override the same
case id. `decision_overrides` are case-scoped and are applied to whichever
terminal decision path or decision choice is selected for that case. The
case-scoped CLI flags `--reviewer`, `--reason`, `--correction-notes`, and
`--corrected-artifact` plus repeatable `--reviewed-region` override same-field
config or plan evidence for the selected case.

## Promotion Review Decision Plan v1

Read by `morphea promotion-review-harvest --decision-plan` or by the
`decision_plan` field in a promotion-review-harvest config.

Supported fields:

- `schema_version`: optional schema version marker
- `decision_choices`: object mapping case ids to terminal decision names
  (`accepted`, `corrected`, `rejected`, or `deferred`)
- `decision_overrides`: object mapping case ids to the same explicit reviewer
  evidence fields supported by harvest configs: `reviewer`, `reason`,
  `correction_notes`, `corrected_artifacts`, and `reviewed_region_ids`

Decision plans intentionally do not contain run-local template paths. They are
portable review evidence overlays that become actionable only when combined
with a generated review packet or harvest config that exposes terminal
decision templates.

Harvest-prep Markdown reports keep region-scoped accepted/corrected evidence
visible in the Applied Case Status table. Applied rows include the selected
`reviewed_region_ids`, the gate-ok `review_promoted_region_ids`, and the
`review_promoted_anchor_indexes` that became promoted through the review,
alongside reviewer, reason, source decision path, review artifacts, harvest
state, and harvest block reason.

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
- `lucide_validation`: optional Lucide benchmark validation summary when
  `lucide_suite` is configured
- `suite_family_validation`: normalized primitive, real-image, and Lucide
  family evidence used to inspect regressions before model acceptance
- `suite_family_baseline_comparison`: optional comparison against a fixed
  `suite_family_validation` baseline with new regression, known-debt, and
  resolved regression counts
- `suite_family_baseline_snapshot`: optional snapshot-write status when
  `suite_family_baseline_output` is configured

`morphea self-learn` always writes comparison and gate artifacts. It writes
`model.json` only when the training gate accepts the reviewed-label
augmentation. When `curated_suite` is configured and retraining is accepted,
the cycle runs `morphea curated-check` with the accepted model as
`classifier_model` and writes curated validation artifacts. When `lucide_suite`
is configured and retraining is accepted, the cycle runs `morphea lucide-check`
with the same model override; failed Lucide validation blocks acceptance. When
`suite_family_baseline` is configured, newly introduced primitive, real-image,
or Lucide family regressions also block acceptance. When
`suite_family_baseline_output` is configured, accepted cycles write the current
`suite_family_validation` as the next baseline artifact only when reviewer,
reason, and changelog evidence are supplied; rejected cycles report
`skipped_not_accepted`, and missing review evidence reports
`skipped_missing_review_evidence` without overwriting the requested output.
Persisted suite-family baseline snapshots and changelog entries are portable
review artifacts and intentionally omit run-local paths such as `base_dataset`,
`reviewed_labels`, `validation_dataset`, and `source_cycle`; those paths remain
in the cycle report itself. Cycle Markdown repeats that run-local provenance in
the baseline snapshot section, including the source cycle report path, base
dataset, reviewed labels, and validation dataset, so reviewers can audit why a
portable baseline was written without making the baseline artifact
machine-specific.
When `suite_family_baseline_comparison.ok` is true, configured curated or
Lucide suite failures are treated as known baseline debt: they remain in
`acceptance_gate.reasons` but are omitted from
`acceptance_gate.blocking_reasons`. New family regressions remain blocking.
If the requested baseline output already exists, the cycle writes it only when
`suite_family_baseline` points to that same path; otherwise it reports
`skipped_existing_output_requires_matching_baseline` and leaves the existing
file untouched.
The checked-in reviewed accepted-cycle baseline lives at
`docs/real-images/baselines/current-suite-family-baseline.json`.

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
- `lucide_suite`
- `lucide_output_dir`
- `lucide_report`
- `suite_family_baseline`
- `suite_family_baseline_output`
- `suite_family_baseline_reviewer`
- `suite_family_baseline_reason`
- `suite_family_baseline_changelog`
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
`parallel_stroke_group`, `same_color_fragment_group`,
`text_like_fragment_group`, and `primitive_anchor_reservation`. This lets
synthetic and reviewed pseudo-label training preserve simple-shape, text-like
fragment, and grid context without changing primitive labels.

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
- `promotion_region_delta_count`
- `promotion_region_deltas`
- `git`: present for `compare-git-snapshots`

Each item records the shared `id`, `changed_metric_count`, and numeric
`metric_deltas`. Deltas use flattened metric paths, for example
`metrics.editability_score`, `anchor_kind_counts.quad`, or
`expectations.simple-shape-ratio.actual_value`. List items with `id` fields use
that id as the flattened path segment. Boolean fields are not treated as
numeric metrics.

When compared items include `promotion_regions`, the comparison also records
explicit `promotion_region_deltas` for shared cases. Each delta includes
`case_id`, `region_id`, `status` (`changed`, `added`, or `removed`), before/after
state, before/after gate status, before/after selected anchor counts/indexes,
before/after reasons, region layer-depth fields such as `region_layer_count`
and `structural_layer_count`, selected-anchor profile fields such as
`selected_anchor_kind_counts`, and a field-level `changes` list. This avoids
relying on aggregate metric paths to identify which source-region contract
changed.

`morphea compare-snapshots --markdown comparison.md` writes a scan-friendly table
for reviewing differences between saved reports from different commits or
configurations. The Markdown report includes a `Promotion Region Deltas` table
when region-level promotion state is present.

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
- `source_summaries`: before/after source summaries with backend status,
  optional backend adapter, proposal count, status counts, downstream status
  counts, optional promotion-region state counts, anchor-kind counts,
  reserved-anchor count, and proposal-group counts
- `source_deltas`: count deltas derived from `source_summaries`, useful for
  flat-color vs MLX/SAM side-by-side review
- `downstream_status_deltas`: filtered source deltas for
  `downstream_status_counts`; these are proposal-level promotion proxies, not
  ground-truth labels
- `promotion_proxy_deltas`: explicit proxy view that maps downstream
  `accepted`, `rejected`, and `pending` counts to green-promotion,
  red-candidate, and manual-review deltas until segment manifests carry
  region-level promotion labels
- `source_delta_assessment`: heuristic side-by-side assessment with
  `green_promotion_delta`, `red_candidate_delta`, `manual_review_delta`,
  `proposal_count_delta`, `promotion_delta_basis`,
  `uses_region_promotion_labels`, `positive_signals`, `risk_signals`, and a
  `verdict` of `improved`, `mixed`, `noise`, `unchanged`, or `needs_review`.
  When compared manifests expose promotion-region states, the assessment uses
  `promotion_region_state_counts`; otherwise it falls back to downstream-status
  proxy counts.
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
Markdown summary with Source Assessment, Source Summaries, Promotion Proxy
Deltas, and Source Deltas tables for comparing flat-color and MLX/SAM proposal
outputs or for comparing gated and ungated segment configs. The CLI stdout
summarizes the same source-level evidence with before/after sources, proposal
counts, shared proposal count, verdict, and green/red/manual-review deltas, so
side-by-side runs with no shared proposal ids do not look like empty
comparisons.

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
