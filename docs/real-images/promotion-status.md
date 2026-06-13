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
| `terminaro-tweaked` | available local file | checked, expectations failed | red | `missing_semantic_detector`, `shape_class_mismatch`, `weak_visual_fidelity` | `gold-circle-anchors` 4/5, region gate 2/5 with `hole_count=1`, table group 2/8, layer count 4 > 3, visual L1 0.235448 > 0.18 |
| `chatgpt-image-2026-06-11` | missing local file | missing_source | red | `runtime_deferral`, `missing_local_source` | source path unavailable during audit |
| `ui-radio-acceptance-screenshot` | available local file | checked, expectations passed | red | `fragmentation`, `topology_mismatch`, `duplicate_radio_control_anchor` | visual L1 0.033861 < 0.08, but radio topology gate rejects 2 components for 1 intended control |

Current curated semantic result: 3 cases, 1 checked expectation pass, 1 checked
expectation failure, 1 missing source. No real-image case is green under the
v10+ definition because green requires all promotion gates passing and an
available reviewed source.

## Lucide Calibration

Lucide is not the real-image target, but it is the current definitive-shape
calibration suite for false-positive promotion risk.

| Status | Cases | Notes |
| --- | ---: | --- |
| passed current semantic contracts | 23 | Useful regression evidence, not proof of visual perfection. |
| red | 1 | `badge-check` still fails because the scalloped badge outline is not represented as a distinct editable path. |
| yellow | 5 | `move`, `image`, `alarm-clock`, `arrow-left-right`, and `share-2` pass current contracts but remain visibly loose enough to require review before promotion-style claims. |

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

## RIP2 Exit Audit

| Criterion | Status | Evidence |
| --- | --- | --- |
| `badge-check` cannot pass as a circle-like substitute. | met | Lucide calibration remains 23/24 with `badge-check` red. |
| Wrong topology is red even with acceptable L1. | met | `ui-radio-acceptance-screenshot` has visual L1 0.033861 under its 0.08 family threshold, but `radio-control-region-topology` is red because one intended control selects 2 components. |
| Markdown reports show failed gates before aggregate metrics. | met | `render_curated_markdown` begins with the Promotion Gates table before the case metrics table. |
| Contact sheets are first-class review artifacts. | met | Curated runs emit source, preview, anchor overlay, SVG render, diff, promotion summary, and failed-gate panels. |

## RIP3 Exit Audit

| Criterion | Status | Evidence |
| --- | --- | --- |
| Manifests expose region-level promotion state. | met | Checked run manifests include `promotion.regions`; `terminaro-tweaked` records `gold-circle-region-shape-class` as `rejected`, and `ui-radio-acceptance-screenshot` records `radio-control-region-topology` as `rejected`. |
| Fallback and rejected regions are visible in reports. | met | `/tmp/morphea-rip3-exit-report.md` lists `Promotion regions: rejected=1` for both checked real-image cases and shows the failed gate ids before aggregate metrics. |
| Promoted SVG output can be filtered from debug/fallback output. | met | Checked run directories write `promoted.svg`, `fallback.svg`, and `promotion-export.json`; `morphea promotion-export` can regenerate the same partition from a promotion-annotated manifest. |
| No failed semantic candidate disappears silently. | met | `promotion-export.json` records `rejected_anchor_indexes` and `anchor_state_counts`; current checked real-image manifests count 5 rejected anchors for `terminaro-tweaked` and 2 rejected anchors for `ui-radio-acceptance-screenshot`. |

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
For example, the current UI screenshot keeps `raster_fidelity=0.944073` but
sets `topology_consistency=0` because `radio-control-region-topology` is red.
The current Terminaro run sets shape identity, topology, grouping, and raster
fidelity components to `0` because the corresponding red gates fail.

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

## Next Gate

The next mainline block should add a checked-in suite-family baseline fixture
and a smoke command in docs, so the baseline-gated self-learning path is
exercised with the real CLI rather than only unit fixtures.
