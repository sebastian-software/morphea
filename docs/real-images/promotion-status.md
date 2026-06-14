# Real-Image Promotion Status Ledger

This ledger is the human-readable RIP0/RIP1 status view. The machine-readable
case metadata lives in `docs/real-images/suite.json` under each case's
`promotion` block.

## Last Audit Commands

Curated real images:

```sh
PYTHONPATH=src python3 -m morphea.cli curated-check docs/real-images/suite.json \
  -o /tmp/morphea-rip3-exit-report.json \
  --output-dir /tmp/morphea-rip3-exit-runs \
  --snapshot /tmp/morphea-rip3-exit-snapshot.json \
  --markdown /tmp/morphea-rip3-exit-report.md \
  --run
```

Lucide calibration:

```sh
PYTHONPATH=src python3 -m morphea.cli lucide-check assets/lucide/suite.json \
  -o /tmp/morphea-real-image-promotion-lucide-report.json \
  --output-dir /tmp/morphea-real-image-promotion-lucide-runs \
  --markdown /tmp/morphea-real-image-promotion-lucide-report.md
```

## Real-Image Cases

| Case | Source | Pipeline Status | v10 Label | Primary Issues | Evidence |
| --- | --- | --- | --- | --- | --- |
| `terminaro-tweaked` | available local file | checked, expectations passed; promotion gates failed | red | `shape_class_mismatch`, `fragmentation`, `weak_visual_fidelity` | `gold-circle-anchors` 5/5, `table-perspective-quads` 14/8, grid group 1/1; structure gate now passes with `structural_layer_count` 3/3 while raw layer count remains 4 due cutout overlays; v10 remains red because region gate matches 2/5 circles with `hole_count=1`, visual L1 0.230301 > 0.18 |
| `chatgpt-image-2026-06-11` | checked-in opaque fixture | checked, expectations passed; promotion gates failed | red | `fragmentation` | source restored via `assets/curated/terminaro-opaque-table-grid.png`; circles 5/5, table quads 14/12, editable strokes 27/12, visual L1 0.056356 < 0.18, `structural_layer_count` 3/3; v10 remains red because `current_quality_label` is red and editability review rejects parameter economy and fragmentation |
| `ui-radio-acceptance-screenshot` | available local file | checked, expectations passed; promotion gates failed | red | `fragmentation` | visual L1 0.033861 < 0.08; radio topology gate now passes with 1 selected `stroke_circle` and `disconnected_component_count=1`; v10 remains red because `current_quality_label` is red and editability review rejects shape identity, fragmentation, and provenance |

Current curated semantic result: 3 cases, 3 checked expectation passes, 0
checked expectation failures, 0 missing sources. No real-image case is green
under the v10+ definition because green requires all promotion gates passing
and an available reviewed source.

## Lucide Calibration

Lucide is not the real-image target, but it is the current definitive-shape
calibration suite for false-positive promotion risk.

| Status | Cases | Notes |
| --- | ---: | --- |
| passed current semantic contracts | 24 | Useful regression evidence, not proof of visual perfection. |
| red | 0 | `badge-check` now represents the scalloped badge outline as a closed editable `stroke_path`, not as a circle substitute. |
| yellow | 5 | `move`, `image`, `alarm-clock`, `arrow-left-right`, and `share-2` pass current contracts but remain visibly loose enough to require review before promotion-style claims. |

Lucide case reports now include `failed_expectation_count`,
`failed_expectation_ids`, and per-expectation `failure_reason` fields with
shortfall/excess details. `badge-check` now uses bounded expectations to
separate the outer badge outline from the inner check mark. The inner
`check-stroke` region passes, and the outer `editable-badge-outline`
expectation now matches the closed irregular `stroke_path` outline.

## Visual Artifact Posture

Current curated runs emit per-case run directories with input copy, SVG output,
debug SVG, manifest JSON, preview PNG, SVG render PNG, red/blue diff PNG,
contact-sheet PNG, promoted/fallback SVGs, promotion-export JSON, palette
summary, mask summary, promotion-region review files, editability-review
Markdown, review-decision JSON, and report files.

Curated reports also include derived promotion gates:

- `source_available`;
- `semantic_expectations`;
- `visual_contact_sheet`;
- `current_quality_label`.

Cases may also define explicit hard gates that reference concrete expectations,
for example `circle-anchor-shape-class`, `table-grid-topology`, or
`radio-control-topology`. These make shape-class and topology failures visible
as named gates instead of relying only on a broad semantic expectation failure.
Cases may also define source-region gates, such as
`gold-circle-region-shape-class` or `radio-control-region-topology`, that check
expected anchor kinds inside concrete image bounds. Region gates now also emit
`topology_summary` evidence for closed/open anchors, holes, cutouts, and
disconnected component counts.

Cases may define per-family `visual_thresholds`, which produce a
`visual_fidelity_thresholds` gate from run raster metrics after structural hard
gates are available.

Cases may define `group_gates`, such as `table-grid-group-consistency` and
`text-parallel-stroke-grouping`, to require group kind and member-count evidence
for grids, repeated structures, and parallel strokes.

Cases may define `structure_thresholds`, which produce
`fragmentation_layer_thresholds` evidence for aggregate fragmentation and layer
depth.

Curated reports now derive `promotion_regions` from source-region gates. Each
region records `promoted`, `deferred`, or `rejected` state with bounds, gate id,
and reason. This is the first RIP3 promotion-pipeline state artifact.
Checked promotion cases with an output directory also write `promoted.svg`,
`fallback.svg`, `promotion-export.json`, `promotion-regions.json`, and
`promotion-review.md`, so trusted region anchors can be separated from
debug/fallback output and rejected candidates remain reviewable. They also
write `editability-review.md`, which exposes accepted-output decisions,
component threshold failures, gate-blocked components, issue tags, and
regression deltas in a dedicated review artifact. They also write
`review-decision.json`, a machine-editable pending decision record with
allowed accepted/corrected/rejected/deferred outcomes, suggested decision,
issue tags, failed gates, component failures, and regression evidence.
The run `manifest.json` also carries a top-level `promotion` object and
per-anchor `promotion_state` / `promotion_regions` annotations, plus a
top-level `review_decision` record.
`promotion-export.json` records promoted, fallback-only, rejected, and deferred
anchor-index partitions plus anchor-state counts, so failed semantic candidates
remain explicit even when `fallback.svg` contains all non-promoted anchors.
The `morphea promotion-export` command can regenerate promoted/fallback SVGs
from any promotion-annotated manifest, outside curated sidecar generation.

Red gate failures produce `promotion_summary.decision: rejected`; yellow-only
failures produce `deferred`; all gates passing produces `promoted`.

The current contact sheet includes:

- source/reference image;
- manifest preview;
- anchor overlay;
- exported SVG render;
- red/blue visual diff;
- promotion decision summary;
- failed-gate summary.

The complementary `editability-review.md` sidecar includes:

- accepted-output decision and reasons;
- required and observed component threshold status;
- gate-blocked components with failed gate ids;
- regression delta status and per-component deltas;
- current issue tags.

The complementary `review-decision.json` sidecar starts with
`decision: pending` and carries the allowed terminal decisions
`accepted`, `corrected`, `rejected`, and `deferred`, plus the suggested
decision and the gate/component evidence a reviewer needs to edit it.

Checked real-image cases can become green only when the hard gates pass, the
source is available, review artifacts exist, and the case's current quality
label is green.
When present, missing-source promotion cases remain red suite evidence and can
be carried as known baseline debt, but their promotion decision is `deferred`
with `deferred_reason: missing_source` rather than a rejected semantic
candidate.

## RIP2 Exit Audit

| Criterion | Status | Evidence |
| --- | --- | --- |
| `badge-check` cannot pass as a circle-like substitute. | met | Lucide calibration is 24/24; `badge-check` passes only because the badge outline is preserved as a closed irregular `stroke_path`, not as a circle substitute. |
| Wrong topology is red even with acceptable L1. | met | `radio-control-region-topology` remains a red topology gate; the prior duplicate-anchor failure selected 2 components and was rejected, while the current deduped run selects 1 component and passes. |
| Markdown reports show failed gates before aggregate metrics. | met | `render_curated_markdown` begins with the Promotion Gates table before the case metrics table. |
| Contact sheets are first-class review artifacts. | met | Curated runs emit source, preview, anchor overlay, SVG render, diff, promotion summary, and failed-gate panels. |

## RIP3 Exit Audit

| Criterion | Status | Evidence |
| --- | --- | --- |
| Manifests expose region-level promotion state. | met | Checked run manifests include `promotion.regions`; `terminaro-tweaked` records `gold-circle-region-shape-class` as `rejected`, and `ui-radio-acceptance-screenshot` records `radio-control-region-topology` as `deferred` after its gate passes but the case remains red. |
| Fallback and rejected regions are visible in reports. | met | `/tmp/morphea-rip3-exit-report.md` lists `Promotion regions: rejected=1` for both checked real-image cases and shows the failed gate ids before aggregate metrics. |
| Promoted SVG output can be filtered from debug/fallback output. | met | Checked run directories write `promoted.svg`, `fallback.svg`, and `promotion-export.json`; `morphea promotion-export` can regenerate the same partition from a promotion-annotated manifest. |
| No failed semantic candidate disappears silently. | met | `promotion-export.json` records rejected/deferred anchor indexes and `anchor_state_counts`; current checked real-image manifests keep `terminaro-tweaked` rejected anchors explicit and keep the UI radio anchor deferred until the case quality decision changes. |

## RIP4 Progress

The first RIP4 slice exposes formula-level `editability_components` in
manifests, run reports, curated reports, snapshots, and sweep summaries. The
current components explain the existing aggregate score without changing gate
decisions: `simple_shape_ratio`, `fragmentation_penalty`, `diagnostic_penalty`,
`generic_path_penalty`, `unclipped_score`, and `clipped_score`.

The second RIP4 slice adds `editability_v10_components`, a review-level block
with independent scores for shape identity, parameter economy, node economy,
stroke width stability, line/curve smoothness, topology consistency, grouping,
fragmentation, raster fidelity, provenance, and classifier-prior agreement.
Run-level raster metrics refresh the raster-fidelity component after preview
rendering; missing classifier-prior or stroke/smoothness metrics remain explicit
as unobserved component evidence rather than hidden zeros.

Promotion gates now cap matching v10 components instead of being averaged away.
For example, the current UI screenshot keeps `raster_fidelity=0.944073` and now
keeps `topology_consistency=1.0` after duplicate radio anchors are deduplicated,
but it still fails shape identity, fragmentation, and provenance component
thresholds. The current Terminaro run still caps shape identity and raster
fidelity because the corresponding red gates fail.

Curated promotion reports now also include `editability_review`, which turns
promotion state plus v10 component thresholds into an accepted-output decision:
`accepted`, `manual_review`, or `rejected`. Accepted requires a promoted
promotion decision, no gate-blocked components, and passing required component
thresholds for shape identity, parameter/node economy, topology, grouping,
fragmentation, raster fidelity, and provenance. Optional observed stroke,
smoothness, and classifier-prior components can also block acceptance when
their observed score is below threshold.

`morphea curated-check --baseline-snapshot previous.json` compares current
review component scores against a prior curated snapshot. `editability_review`
then records `regression_delta_status`, `regression_deltas`, and
`regressed_components`; accepted outputs are downgraded to `manual_review` when
any comparable component regresses by more than `0.05`.

Checked promotion runs with `--output-dir` now also write
`editability-review.md` beside `promotion-review.md`. The sidecar exposes the
same accepted-output decision as Markdown, including threshold pass/fail rows,
gate-blocked component evidence, current issue tags, and regression deltas when
a baseline snapshot is configured.

Checked promotion runs also write `review-decision.json` and include the same
record in reports, snapshots, and run manifests. This is the first RIP6
machine-readable decision artifact: it is pending by default, carries the
suggested accepted/corrected/rejected/deferred outcome, and preserves issue
tags plus failed gate/component evidence for later application.

`morphea promotion-apply-review` consumes an edited terminal
`review-decision.json`, rejects still-pending decisions, writes an applied
review summary JSON/Markdown, and can persist `review_decision_applied` back
into the run manifest and its `promotion` object.

`morphea harvest --require-applied-review` now gates pseudo-label harvesting on
`review_decision_applied`: only `accepted` and `corrected` applied decisions
can become candidates; missing, invalid, `rejected`, or `deferred` applied
decisions remain visible in `rejected_runs`.

`morphea harvest-curated --require-applied-review` preserves existing applied
review decisions from the run root across the fresh curated rerun, restores
them into the regenerated per-case manifests and curated JSON report, and then
harvests only accepted/corrected applied decisions.

`morphea review --accept-applied-reviews` bridges those harvested candidates
into the existing review/apply-review loop: accepted/corrected applied
promotion reviews become accepted review items, rejected/deferred decisions
become rejected items, and issue tags survive into reviewed-label artifacts.

`morphea merge-labels` now preserves `review` and `review_decision_applied`
provenance in accepted pseudo-label training manifests and records
`review_issues` plus `applied_review_decision` in dataset samples. Rejected and
deferred review items remain outside the trainable dataset.

`morphea self-learn` now separates retraining from model acceptance. A model can
be written after the training comparison gate accepts, but the cycle's
`accepted` flag is true only when that gate accepts and any configured curated
validation suite also passes. Cycle summaries include reviewed-label issue
counts and applied-review decision counts from the pseudo-label dataset.

Training comparison reports now include per-label validation accuracy and
`delta.label_accuracy`; those label-level deltas feed the best/worst training
gate summary, so a primitive-family regression can block model acceptance even
when an aggregate split metric improves.

Self-learning cycle reports now expose `suite_family_validation`: primitive
label-family deltas, curated real-image family summaries, and optional Lucide
family summaries are rendered side by side. `--lucide-suite` is accepted by
`morphea self-learn`; when configured, failed Lucide validation blocks model
acceptance just like failed curated validation.

`morphea self-learn --suite-family-baseline baseline.json` compares the current
normalized family view against a fixed baseline. Newly introduced primitive,
real-image, or Lucide bad outcomes block acceptance, while known baseline debt
is reported separately from new regressions.
When the baseline comparison is clean, configured curated or Lucide validation
failures remain visible as known baseline debt but no longer block acceptance;
new family regressions still block.
Cycle reports now include `known_debt` / `known_debt_count`, making carried
red families visible beside `new_regressions` and `resolved_regressions`.

`morphea self-learn --suite-family-baseline-output next-baseline.json` writes
the accepted cycle's current `suite_family_validation` as a reusable baseline
artifact only when `--suite-family-baseline-reviewer`,
`--suite-family-baseline-reason`, and `--suite-family-baseline-changelog` are
provided. Successful updates include a review record in the snapshot and append
a JSONL changelog entry; rejected cycles and missing review evidence do not
write the requested baseline output.

Existing baseline output files are protected: the cycle writes an existing
`--suite-family-baseline-output` path only when `--suite-family-baseline`
points to that same path. Otherwise it reports
`skipped_existing_output_requires_matching_baseline` and leaves the file
untouched.

`docs/real-images/baselines/current-suite-family-baseline.json` is now a
checked-in reviewed accepted-cycle baseline for
`morphea self-learn --suite-family-baseline`. It records 22 suite-family rows:
16 held primitive split/family rows, three Lucide family rows, and three
real-image family rows. Current known baseline debt is empty: the opaque
generated-illustration family moved from `failed_missing` to `passed` after the
checked-in fixture refresh, and the baseline comparison reported
`known_debt_count=0`, `new_regression_count=0`, and `resolved_regression_count=1`.

`tests.test_self_learning` runs the real CLI against this fixture so the
baseline comparison path is covered outside helper-only unit tests.

## Next Gate

The next promotion-quality block should keep all real-image semantic
expectations green while addressing the remaining v10 red gates:
`terminaro-tweaked` region-circle matching plus raster L1 fidelity. The opaque
generated-illustration and UI screenshot cases no longer fail their mechanical
structure/topology gates, but both still need review/quality-label decisions
and editability component improvements before they can move out of red.
