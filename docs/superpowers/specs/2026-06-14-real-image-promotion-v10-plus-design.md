# Real-Image Promotion v10+ Design

Date: 2026-06-14

## Planning Assumption

This spec chooses a combined direction: the primary roadmap is **Real-Image
Promotion v10+**, with MLX/SAM treated as an enabling candidate-region source
and editability scoring treated as the review and gate discipline. The immediate
implementation packet should attack the current red v10 promotion gates, but
the design bar is the v10+ target system rather than a narrow v1 cleanup.

## Current Baseline

The current repository state is a good foundation, not a finished promotion
system.

Known evidence:

- `docs/real-images/suite.json` has three curated real-image cases.
- The curated semantic suite is green: three checked cases, three expectation
  passes, zero missing sources.
- The Lucide benchmark is green under current semantic contracts: 24 checked
  cases, zero failed cases.
- The Lucide report still carries visual-review labels: `lucide-check
  --markdown` names five yellow calibration cases even while the semantic suite
  remains 24/24.
- Suite-family baseline debt is empty after the opaque generated-illustration
  fixture refresh.
- All three current real-image cases are still v10 red because promotion gates,
  not semantic expectations, block trusted output.

Current promotion states after the structural-layer, UI-topology, Terminaro
region-coverage, transparent-raster flattening, organic fallback node-budget,
and quality-label review-policy refinements:

- `terminaro-tweaked`: deferred for manual review via
  `quality_label_review_policy: manual_review_pending`; editability review has
  no failed components after parameter economy rose to 0.268145.
- `chatgpt-image-2026-06-11`: deferred for manual review via
  `quality_label_review_policy: manual_review_pending`; editability review has
  no failed components after parameter economy rose to 0.268145.
- `ui-radio-acceptance-screenshot`: deferred for manual review via
  `quality_label_review_policy: manual_review_pending`; text-like fallback
  grouping removes the prior shape identity, fragmentation, and provenance
  component failures.

The next roadmap must preserve the current semantic-green baseline while moving
from "the detector found plausible anchors" to "the promoted SVG is trustworthy
and useful to edit."

## North Star

Morphea should become a local real-image SVG promotion system that can explain
every region-level decision.

For every source region, the system should answer:

- What visual object is this region intended to represent?
- Which candidate sources proposed it?
- Which semantic candidates competed for it?
- Why was one candidate promoted, rejected, deferred, or left as fallback?
- What evidence proves the promoted SVG is visually credible, semantically
  honest, compact enough, and useful to edit?
- What review decision, if any, made it eligible for future learning?

The v10+ target is not "more vectorization." It is a disciplined promotion
system that avoids false-positive semantic SVG even when a looser trace would
look acceptable at thumbnail size.

## Non-Goals

- Do not make MLX/SAM the default path before promotion gates can judge whether
  it helped.
- Do not loosen thresholds merely to turn the current red cases green.
- Do not train from pending, rejected, deferred, or gate-blocked promotion
  output.
- Do not treat raster similarity as proof of editability.
- Do not hide fallback output inside promoted SVG.

## v10 Green Contract

A real-image region is green only when all of these are true:

- Source is available or represented by a checked-in fixture with provenance.
- Semantic expectations pass without anchor reuse tricks.
- Hard gates pass for shape identity, topology, grouping, fragmentation, and
  visual fidelity.
- `promotion_summary.decision` is `promoted`.
- `editability_review.decision` is `accepted` or a human-applied `corrected`
  decision with preserved review evidence.
- The promoted SVG can be exported independently from fallback/debug output.
- A contact sheet shows source, preview, anchor overlay, region overlay,
  rendered SVG, diff, decision, and failed-gate context.
- Suite-family validation has no new primitive, Lucide, or real-image
  regressions.

Yellow remains useful research evidence. Red remains useful failure evidence.
Only green is trusted promoted output.

## System Tracks

### Track A: Real-Image Promotion Mainline

This is the main product surface. It owns region state, hard gates, promotion
exports, review artifacts, and suite-family acceptance.

Responsibilities:

- normalize all candidate regions into one region ledger;
- produce semantic candidates and fallback candidates;
- run deterministic gate evaluation;
- assign `promoted`, `fallback`, `deferred`, or `rejected`;
- write promotion-aware manifests and SVG exports;
- keep rejected and deferred attempts inspectable.

Success measure: more real-image regions become green without increasing false
positive promotion or hiding red evidence.

### Track B: Editability Evidence

Editability scoring is not a replacement for gates. It explains and ranks
candidates after hard failures are visible.

Responsibilities:

- expose independent v10 component scores;
- cap components when matching red gates fail;
- compare component regressions across snapshots;
- explain why accepted output is actually easier to edit;
- keep parameter economy, node economy, smoothness, topology, grouping,
  fragmentation, raster fidelity, provenance, and classifier-prior evidence
  separate.

Success measure: reviewers can identify why a candidate is better or worse
without reading detector internals.

### Track C: MLX/SAM Candidate Regions

MLX/SAM is an optional local candidate-region source, not an oracle.

Responsibilities:

- produce candidate masks in the same proposal schema as classical segmenters;
- record source provenance and runtime capability status;
- run side by side with classical masks;
- compete under the same promotion gates;
- remain optional when local MLX/SAM is unavailable.

Success measure: MLX/SAM increases accepted green regions or reduces manual
review burden without increasing red false positives.

### Track D: Reviewed Learning Loop

The learning loop consumes only reviewed evidence.

Responsibilities:

- preserve pending review records;
- apply human decisions to run manifests;
- harvest only accepted/corrected decisions;
- merge labels without losing issue tags;
- retrain under primitive, Lucide, and real-image family gates;
- persist accepted suite-family baselines with review evidence.

Success measure: model updates improve or hold every family view and never
launder known failures into training data.

## v10+ Milestone Ladder

### RP10.1: Red Gate Kill List

Purpose: turn the current suite from "semantic green, promotion red" into a
case-by-case promotion-quality improvement plan.

Deliverables:

- per-failed-gate issue records in `docs/real-images/promotion-status.md`;
- targeted detector or gate changes for the three current red gates;
- updated curated snapshot and suite-family baseline after each accepted fix;
- no Lucide or primitive regression.

Current report slice: `curated-check --markdown` now writes a Corpus Ledger that
lists each promotion case's quality label, current status, stress family,
expected promotion families, issue tags, and licensing status before the
promotion-gate details.

Exit criteria:

- `chatgpt-image-2026-06-11` no longer fails fallback layer depth, or the gate
  explains why the extra layer is semantically required. This is currently met
  by `max_structural_layer_count` with `cutout_overlays` excluded from core
  layer depth while still visible in gate evidence.
- `terminaro-tweaked` has a corrected gold-circle region gate or a documented
  detector change that matches all five intended circles without accepting
  ring/cutout false positives. This is currently met by `min_anchor_coverage`
  over the shoulder-brooch and center-dot ROI; the gate matches five `circle`
  anchors and excludes the large ring/cutout false positives.
- `ui-radio-acceptance-screenshot` represents one intended radio control as one
  topology-compatible region, not duplicate semantic components. This is
  currently met mechanically by neutral composite anchor deduplication; the
  region remains deferred until the case quality decision changes.
- Generated-illustration parameter economy passes the review threshold after
  organic fallback node-budget capping: both Terminaro variants now score
  `parameter_economy=0.268145` against a required 0.25, with no failed
  editability-review components.
- Generated-illustration review-label policy is now explicit: both Terminaro
  variants opt into `quality_label_review_policy: manual_review_pending`, which
  keeps their red quality label visible but moves the promotion decision to
  `deferred` instead of `rejected`.
- UI screenshot text fallback handling is now explicit: the sparse black glyph
  fragments form a `text_like_fragment_group`, so their bounded cubic fallbacks
  remain visible for review without counting as unstructured v10 fallback debt.
  This moves the UI screenshot to manual-review pending rather than detector
  rejection.

### RP10.2: Region Truth Schema

Purpose: stop relying on broad case-level expectations when failures are
region-specific.

Deliverables:

- source-region annotations for intended objects, expected kinds, allowed
  alternates, and topology constraints;
- stable region ids that survive report, snapshot, review, and harvest flows;
- region-level expected/actual tables in Markdown reports;
- compact JSON schema docs for region truth.

Current report slice: `curated-check --markdown` now writes a Region Truth table
for configured source-region gates, listing stable region/gate ids, promotion
state, bounds, expected kinds, actual matching/selected/forbidden counts, and
topology summaries.

Current comparison slice: `compare-snapshots` and `compare-git-snapshots` now
write explicit `promotion_region_deltas` for shared cases, so a baseline diff
can identify the changed, added, or removed region id plus before/after state,
gate status, selected anchors, and reason.

Exit criteria:

- every real-image red gate references a stable region id;
- snapshot diffs can show which region changed;
- reviewers can tell whether a fix improved the intended object or only moved
  aggregate metrics.

### RP10.3: Layer and Fragmentation Model

Purpose: make layer depth and fragmentation meaningful instead of blunt
aggregate penalties.

Deliverables:

- layer-role classification for filled primitives, strokes, cutout overlays,
  generic paths, text-like fragments, and fallback regions;
- per-region layer depth instead of only whole-manifest layer depth;
- merge rules for harmless cutout overlays and same-object fragments;
- hard limits for accidental layer explosion.

Current region slice: promotion-region records now carry `layer_roles`,
`layer_role_counts`, `region_layer_count`, `structural_layer_roles`, and
`structural_layer_count` derived from selected anchors. They reuse
`promotion.structure_thresholds.non_structural_layer_roles`, so harmless
overlay roles can be visible without inflating structural layer depth.
They also carry `selected_anchor_kind_counts` and simple/stroke/generic-path
anchor counts, making local fragmentation and shape mix visible per region.
`curated-check --markdown` shows the same evidence in the Region Truth table.

Exit criteria:

- generated illustration cases can distinguish useful overlay layers from
  uneditable fragmentation;
- v10 gates can reject noisy layer depth without punishing necessary semantic
  overlays;
- layer fixes reduce editability-review failures, not just one aggregate count.

### RP10.4: Shape and Topology Strictness

Purpose: make false-positive promotion rarer than honest fallback.

Deliverables:

- explicit topology descriptors for closed/open state, holes, cutouts,
  disconnected components, and nested contours;
- stricter circle/ring/badge/control distinction;
- candidate-level reject reasons for shape and topology mismatches;
- focused fixtures for every corrected failure.

Current evidence slice: region-gate evidence now writes `candidate_rejections`
for selected anchors that failed the region contract. Rejections preserve anchor
id, kind, geometry overlap, reasons (`kind_mismatch`, `forbidden_kind`,
`topology_failure`), and topology failures, while the Region Truth table exposes
the rejected candidate count next to matching/selected/forbidden counts.
Promotion export manifests preserve the gate records, and `promotion-review.md`
renders a Candidate Rejections table so reviewers do not have to inspect raw
JSON for rejected shape/topology candidates.
Nested-contour evidence is now explicit as `nested_contour_count`, derived from
hole counts plus cutout anchors, with optional `min_nested_contours` and
`max_nested_contours` region-gate limits.
Topology summaries also emit `topology_descriptors`, a compact label list for
closed/open state, component count, holes, cutouts, and nested contours.
Region gates can require or forbid these labels with
`required_topology_descriptors` and `forbidden_topology_descriptors`, allowing
single-control regions to reject multi-component or nested candidates directly.
The real UI radio-control region now requires `closed` and `single_component`
and forbids multi-component, hole, cutout, and nested-contour descriptors.
The real Terminaro gold-circle region now requires `closed` and
`multi_component` and forbids single-component, hole, cutout, and nested-contour
descriptors, preserving the five-circle contract rather than accepting a ring
or merged badge-like substitute.
The Lucide calibration suite now pins the same shape-class boundary with
explicit zero-match contracts: `circle` forbids a full-icon irregular
`stroke_path` via `not-irregular-badge-outline`, and `badge-check` forbids a
full-icon `stroke_circle` via `not-circle-substitute`. Lucide Markdown reports
render these as `= 0` expectations, and violations are labeled
`forbidden_matches`.

Exit criteria:

- badge-like, ring-like, and radio-control-like objects cannot satisfy each
  other's contracts by accident;
- rejected candidates include enough evidence to explain the rejection in a
  review artifact;
- Lucide remains 24/24 while real-image gates become stricter.

### RP10.5: Visual Fidelity That Serves Semantics

Purpose: make raster thresholds useful without letting them certify wrong SVG.

Deliverables:

- per-family visual thresholds tied to region intent;
- region-level raster deltas in addition to case-level deltas;
- contact sheets that highlight failed regions, not only whole-image diffs;
- visual regression comparison against the checked-in curated snapshot.

Current evidence slice: checked curated runs now attach `visual_delta` to each
source-region gate. The delta is computed from the source-vs-exported-SVG crop
for the configured region bounds and records crop bounds, size, L1 error, edge
error, alpha error, and size-match status. Region gates can also set
`max_raster_l1_error` and `max_raster_edge_error`; failures are stored as
`visual_failures` and participate in the gate result. `promotion_regions`,
manifest promotion state, `promotion-export.json`, `promotion-review.md`, and
the suite Region Truth and Promotion Gate Details tables all carry the same
region-level visual delta, thresholds, failures, and failed-gate reason, so
reviewers can inspect visual drift at the region that the semantic gate is
already discussing. The real gold-circle region now passes a red region visual
gate, while the real radio-control crop records a yellow region visual-fidelity
failure after its topology gate passes.
Contact sheets now include a region overlay panel, and checked run artifacts
write `region-overlay.png`; failed red/yellow source-region gates are outlined
directly on the source image while passing regions remain green.

Exit criteria:

- a case can fail visual fidelity only where the user can inspect the offending
  region;
- visual improvements that worsen topology remain red;
- visual drift improvements are accepted only when semantic gates hold.

### RP10.6: Review Workflow as a First-Class Artifact

Purpose: make human review fast, consistent, and reusable for learning.

Deliverables:

- review packets grouped by failed gate and issue tag. First slice: curated
  runs with `--output-dir` write suite-level `review-packet.json` and
  `review-packet.md` that collect deferred/rejected cases and link their
  contact sheet, promotion review, editability review, and pending
  `review-decision.json`. Packet cases also surface `review_requirements` so
  reviewer/reason and corrected-decision evidence requirements are visible
  before a terminal template is opened, plus per-decision `review_commands` so
  edited terminal templates can be applied without manual path reconstruction.
  Review packets now also carry and render failed-gate details (`id`, type,
  severity, reason), so yellow visual-fidelity or review-safety debt is visible
  from the packet without opening raw JSON;
- reviewer decision templates for accepted, corrected, rejected, and deferred.
  Current slice: checked promotion runs write terminal JSON templates under
  `review-templates/`, and suite-level review packets link those paths per
  case. Applying a terminal decision now requires reviewer and reason evidence;
  applying `corrected` also requires correction notes and corrected-artifact
  evidence. Pending and terminal decision records preserve `review_artifacts`
  links back to the manifest, promotion-region JSON, promotion review, and
  editability review;
- applied-review summaries that link back to region truth and promotion gates;
- a small local gallery for current green/yellow/red examples. Current slice:
  curated runs with `--output-dir` write `review-gallery.html`, a static local
  page with contact sheets, quality labels, promotion/editability decisions,
  failed gates/components, failed-gate reasons, review links, terminal
  decision-template links, and per-decision apply commands for queued cases.

Exit criteria:

- a reviewer can process a suite run without opening raw JSON;
- corrected decisions preserve both original failure evidence and corrected
  output evidence;
- accepted/corrected records can be harvested without manual path surgery.

### RP10.7: MLX/SAM Side-by-Side Evaluation

Purpose: evaluate MLX/SAM only after the promotion evaluator can judge it.

Deliverables:

- segmenter interface output parity between classical and MLX/SAM sources;
- capability reporting for missing MLX package, missing model, and unavailable
  live SAM adapter;
- side-by-side region proposal reports;
- per-source promotion deltas.

Current implementation:

- `compare-segments` now reports source summaries and source deltas for
  proposal count, downstream status, decision reasons, anchor kinds, reserved
  anchors, and proposal groups. Its Markdown report renders Source Summaries
  and Source Deltas tables plus explicit Promotion Proxy Deltas, so selected
  classical and MLX/SAM runs can be reviewed side by side. It also emits a
  source delta assessment that labels the comparison as improved, mixed, noise,
  unchanged, or needing review from green promotion, red candidate,
  manual-review, and proposal-count deltas. When segment manifests carry
  `promotion_regions`, the assessment uses true promotion-region state counts;
  otherwise it records downstream-status proxy counts as the basis. CLI stdout
  now prints the same source-level counts and verdict rather than only the
  shared proposal-id count, which is usually zero across classical and MLX/SAM
  sources. Flat-Color segment manifests now scale proposal bounds back to
  source-image coordinates after `max_size` analysis resizing, and
  `compare-segments` adds greedy spatial proposal matches plus mean/min/max IoU
  and downstream/anchor transition counts, so classical and MLX/SAM runs can be
  compared even when their proposal ids differ. Runtime status now also records
  whether the adjacent `.safetensors.json` sidecar exists for configured
  MLX/SAM checkpoints, so quantized-checkpoint setup is inspectable before a
  run; the same fields are visible in the default status Markdown Backend
  Diagnostics table. The first local tiny 4-bit SAM2.1 MLX smoke on
  `assets/curated/terminaro-opaque-table-grid.png` proves live
  `mlx_sam_grid_points` execution and comparison artifact generation: 4 MLX/SAM
  proposals passed the geometry gate, but the source assessment was `noise`
  because the green promotion proxy count dropped from 29 to 4 versus the
  Flat-Color baseline. A repeatable `flat_color_centers` prompt-strategy smoke
  now produces 16 MLX/SAM proposals and 16 spatial matches against the
  Flat-Color baseline, but remains `noise`; the direct
  `grid_points -> flat_color_centers` comparison is `mixed`, with accepted
  proposals increasing while rejected candidates also increase.

Exit criteria:

- MLX/SAM can be run on selected cases without becoming a hard dependency;
- reports show whether MLX/SAM improved green promotion, reduced red candidates,
  or only added noise;
- no training or promotion path assumes MLX/SAM output is ground truth.

### RP10.8: Promotion-Centric Export

Purpose: make the exported SVG reflect trust state, not detector internals.

Deliverables:

- promoted-only SVG export for trusted semantic output;
- fallback/debug SVG export for complete inspection;
- stable ids linking SVG nodes to source regions and review decisions;
- export summaries with promoted, fallback, rejected, and deferred counts.

Current implementation:

- `promotion-export` can regenerate promoted and fallback SVG partitions plus a
  JSON export summary. Exported shapes are wrapped in stable metadata nodes
  carrying anchor id, anchor index, promotion state, source promotion region
  ids, and applied review-decision metadata when present. It can also write a
  Markdown export report with promoted/fallback/rejected/deferred counts and
  missing-from-promoted rows that surface region reasons. The JSON summary now
  carries the same `missing_from_promoted` records with state, anchor indexes,
  region ids, and reasons, and curated sidecars write the same field.
- curated promotion run sidecars now apply the same stable metadata wrappers to
  `promoted.svg` and `fallback.svg` while preserving the configured cut-out
  export strategy.

Exit criteria:

- green regions can be consumed independently of rejected candidates;
- a user can inspect why an object is missing from promoted SVG;
- exported SVG structure is stable enough for editability review.

### RP10.9: Reviewed Real-Image Learning

Purpose: close the loop from accepted promotion evidence to safer local models.

Deliverables:

- curated harvests that preserve applied decisions across reruns;
- reviewed-label merges that keep issue tags and decision provenance;
- retraining gates across primitive, Lucide, and real-image families;
- accepted suite-family baseline updates after reviewed improvements.

Current implementation:

- `harvest-curated --require-applied-review` preserves applied decisions across
  reruns and harvests only accepted/corrected applied reviews.
  Promotion-annotated manifests must also expose at least one trusted promoted
  anchor, and only promoted anchors from that run become pseudo-labels. `merge-labels`
  keeps review and applied-review provenance in pseudo-label manifests, and
  dataset samples carry review item id, review reason, issue tags, applied
  decision, applied case id, and source review-decision path. `self-learn`
  JSON and Markdown reports summarize reviewed-label issue counts,
  applied-review decision counts, and provenance-field coverage. The current
  region-scoped plan has a CLI regression through review, apply-review,
  merge-labels, and self-learn, proving accepted reviewed region anchors can
  become train examples, reach a retraining gate, and remain auditable while
  deferred evidence stays excluded. The current checked-in replay keeps model
  acceptance conservative: five accepted Terminaro region labels are carried
  into the cycle, but the training gate rejects the update when the comparison
  status regresses. `self-learn` can now train the accepted cycle model with
  either the default centroid backend or the local
  `mlx_transformer_primitive_classifier` backend (`backend: mlx`). The MLX path
  still depends on reviewed pseudo-labels and the same acceptance gates; it is
  an own primitive-classifier model path, not SAM fine-tuning. Training gate
  artifacts now include worst/best metric
  contributors, so rejected self-learning cycles can identify the metric,
  split, and label behind the gate decision. Training comparison artifacts now
  also include ranking-decision deltas, so a reviewer can inspect which
  classifier choices changed between the baseline and augmented model.
  Suite-family baseline comparisons now emit full per-family comparison rows
  and outcome counts, including held, improved, known-debt, resolved-regression,
  new-regression, and missing-current-family states. Missing current coverage
  for a previously good baseline family blocks model acceptance instead of
  silently accepting an under-validated cycle.

Exit criteria:

- a model update cannot be accepted if it introduces new real-image, Lucide, or
  primitive family debt;
- accepted/corrected real-image evidence can improve classifier priors;
- rejected/deferred evidence stays available for analysis but out of training.

### RP10.10+: Local Research Product

Purpose: make the system usable as a local research loop, not only a CLI pile.

Deliverables:

- one command for suite run, report generation, and review packet output;
- one command for applying reviews and preparing harvest candidates;
- stable local artifact conventions;
- documentation that separates green demos from red/yellow research evidence.

Current implementation:

- `promotion-review-run suite.json --output-dir review-run` is the
  review-oriented suite-run entry point. It implies `run=True`, derives default
  `curated-report.json`, `curated-report.md`, and `curated-snapshot.json`
  paths under the output root, and writes per-case artifacts plus suite-level
  `review-packet.json`, `review-packet.md`, and `review-gallery.html`. It also
  writes a starter `promotion-review-harvest.json` config with empty
  `decisions`, empty `decision_overrides`, per-case terminal decision template
  paths, and stable follow-up paths, then surfaces the generated
  `promotion-review-harvest --config` command in report JSON and Markdown.
- After the starter config exists, `promotion-review-run` rewrites
  `review-packet.json`, `review-packet.md`, and `review-gallery.html` with
  per-case `decision_choice_commands` and reviewer evidence-flag hints, so the
  initial reviewer surface contains the no-JSON-edit harvest path directly.
  The gallery status strip also mirrors the packet-level reviewable region
  summary, so visual review starts with the same prepared-region counts as the
  JSON and Markdown packet.
  The packet also derives gate-ok `reviewable_regions` from promotion-region
  state and renders stable region ids, gate types, states, selected-anchor
  counts, and reasons, plus a packet-level summary of reviewable region cases,
  total regions, selected anchors, states, and gate types. Accepted/corrected
  choice hints include matching `--reviewed-region case=region-id` flags, so
  reviewers can choose a region-scoped path from the first packet instead of
  opening raw `promotion-regions.json`.
- `curated-check --run --output-dir --markdown --snapshot` remains the lower
  level suite-run entry point for explicit artifact paths.
- `promotion-review-harvest` is the review-to-harvest bridge: it applies only
  explicit terminal decision files from a review packet, persists
  `review_decision_applied` through the existing apply-review rules, reports
  applied/harvestable/pending packet cases with promoted-anchor counts and
  harvest block reasons, and writes a `harvest-curated` config with
  `require_applied_review: true`. The CLI regression path proves
  the generated config carries accepted applied reviews forward while keeping
  deferred applied reviews visible but out of pseudo-label harvesting.
  `promotion-review-harvest --config` makes the same bridge repeatable with a
  case-id decision map and explicit per-case CLI overrides. Pending cases in
  its JSON/Markdown report now include terminal decision-template paths when
  available, but those templates remain guidance until a reviewer adds a
  `decisions` entry, passes `--decision`, or uses an explicit template-backed
  `decision_choices` / `--decision-choice` selection. When run from config, the
  prep report also renders copy/paste `decision_choice_commands` for pending
  cases with template-readiness labels for missing reviewer evidence. Pending
  harvest-prep rows preserve packet `reviewable_regions` and render a
  dedicated reviewable-region table, and accepted/corrected choice hints repeat
  `--reviewed-region case=region-id` flags next to reviewer/reason hints. The
  same prep report now writes a `reviewable_region_summary` covering applied
  reviewed-region ids, review-promoted region ids, harvestable reviewed-region
  ids, pending region ids, and applied region decision counts. The CLI stdout
  summary prints those applied/promoted/harvestable/pending region counts next
  to the case counts.
- `promotion-apply-review` can apply a terminal template with explicit CLI
  reviewer evidence overrides (`--reviewer`, `--reason`, and corrected-evidence
  flags, plus `--reviewed-region` for explicit region evidence), so reviewers
  can avoid hand-editing JSON while still supplying required evidence.
- `promotion-review-harvest --config` can carry case-scoped
  `decision_overrides` for the same reviewer evidence fields, allowing
  template-backed `decision_choices` to apply generated terminal templates
  without mutating those template files.
- `promotion-review-harvest --config` can also load a portable
  `decision_plan` overlay with `decision_choices` and `decision_overrides`, so
  explicit reviewer decisions can be checked in without run-local template
  paths and replayed against a fresh review run.
- `promotion-review-harvest --config` also accepts the same evidence directly
  as case-scoped CLI flags, so a reviewer can choose a terminal template and
  supply reviewer/reason evidence from one command line.
- Accepted/corrected applied reviews can now carry explicit
  `reviewed_region_ids`. Applying such a decision validates the listed regions
  against the run manifest, promotes only gate-ok reviewed regions plus their
  selected anchors, and keeps suite `current_quality_label` updates manual.
- Harvest prep reports render evidence-flag hints beside decision-choice
  commands when templates are missing reviewer fields, making the no-JSON-edit
  path visible without turning placeholder values into executable defaults.
- Harvest prep reports summarize terminal-template readiness as aggregate
  ready-template, ready-case, and missing-field counts before the per-case
  tables.
- Harvest prep pending rows preserve review-artifact links from the packet, so
  reviewers can reach contact sheets, promotion reviews, editability reviews,
  pending decisions, and promotion exports from the same report that contains
  the decision-choice commands.
- Harvest prep applied rows include reviewer, reason, source decision path, and
  applied review-artifact links, plus reviewed-region ids, review-promoted
  region ids, and review-promoted anchor indexes, keeping harvestable decisions
  auditable after they move out of the pending queue.

Exit criteria:

- a new real-image case can be added, audited, reviewed, and carried through
  baseline-gated learning without changing code;
- the project can show honest examples without overclaiming quality;
- false-positive semantic promotion remains the highest-severity failure.

## Implemented First Packet

The first packet was **RP10.1 Red Gate Kill List**. The baseline is now clean,
the suite is semantically green, and the current implementation has moved the
three real-image cases from mechanical red gates to explicit manual-review
evidence with portable decision plans. Further corpus and MLX/SAM work should
preserve these review and gate contracts instead of bypassing them.

Scope:

- keep Lucide and primitive checks green;
- keep all three current real-image cases semantically green;
- make every current red gate explainable at region, editability, or review
  policy level;
- update fixtures, reports, snapshots, and suite-family baselines only after the
  fix is backed by command output.

Recommended target order after the structural-layer, UI-topology, Terminaro
region-coverage, transparent-raster flattening, organic fallback node-budget,
and quality-label review-policy refinements:

1. Build a reviewer-facing packet for all three deferred real-image cases so a
   human can apply `accepted`, `corrected`, `rejected`, or `deferred` decisions
   without reading raw JSON. The packet now links contact sheets, promotion
   reviews, editability reviews, pending review decisions, and terminal
   decision templates for all four outcomes. The same output root now includes
   `review-gallery.html` for scanning those cases visually before editing or
   applying a decision, and `promotion-review-run` adds per-case
   `decision_choice_commands` so reviewers can apply a selected terminal
   outcome through `promotion-review-harvest --decision-choice` plus explicit
   evidence flags. The current checked-in portable review plan at
   `docs/real-images/reviews/current-deferred-decision-plan.json` applies
   explicit `deferred` decisions for all three cases. The current checked-in
   region-scoped plan at
   `docs/real-images/reviews/current-region-decision-plan.json` accepts only
   the Terminaro `gold-circle-region-shape-class` region via
   `reviewed_region_ids`; the opaque generated illustration and UI radio case
   remain deferred.
2. Decide whether applied `accepted`/`corrected` reviews should update
   `current_quality_label` in suite metadata, or remain sidecar-only applied
   review evidence. Current policy is sidecar-only: pending decisions,
   terminal templates, and applied summaries carry `quality_label_policy` with
   `updates_current_quality_label: false`; suite labels remain manual metadata
   until the suite file is explicitly edited. Accepted/corrected region
   evidence is now carried through `reviewed_region_ids`, so reviewed gate-ok
   regions can become harvestable without making whole-case label updates
   implicit.
3. Add a follow-up guard that keeps text-like fallback grouping from masking
   non-text organic fallback debt in future UI screenshots. Current guard:
   `text_like_fragment_group` only marks small glyph-sized cubic paths as
   structured; larger same-color organic fallback paths stay in
   `unstructured_generic_path_count` and
   `unstructured_fragmentation_penalty`.

Reasoning:

- The transparent Terminaro case no longer fails region-circle matching, raster
  fidelity, v10 fragmentation, or parameter economy. It is now deferred for
  explicit manual review instead of being silently promoted.
- The opaque generated illustration no longer has a mechanical red gate besides
  the intentionally red quality label, and editability review has no failed
  components. It follows the same manual-review-pending policy as the
  transparent source.
- The UI radio case now has a topology-compatible radio region, and text-heavy
  fallback debt is identified as structured text-like fragments rather than
  unstructured fallback debt. It now follows the same manual-review-pending
  policy as the generated-illustration cases.

Acceptance commands for the packet:

```sh
PYTHONPATH=src python3 -m morphea.cli curated-check docs/real-images/suite.json \
  -o /tmp/morphea-rp10-report.json \
  --output-dir /tmp/morphea-rp10-runs \
  --snapshot /tmp/morphea-rp10-snapshot.json \
  --markdown /tmp/morphea-rp10-report.md \
  --run

PYTHONPATH=src python3 -m morphea.cli lucide-check assets/lucide/suite.json \
  -o /tmp/morphea-rp10-lucide-report.json \
  --output-dir /tmp/morphea-rp10-lucide-runs \
  --markdown /tmp/morphea-rp10-lucide-report.md

PYTHONPATH=src python3 -m unittest discover -s tests
```

Baseline refreshes should continue to happen only after the acceptance commands
pass and suite-family comparison reports no new regressions.

## Review Questions for Us

These RP10 planning questions are now answered by the current review workflow:

- Should `current_quality_label` remain manually red until explicit applied
  review, or should applied `accepted`/`corrected` reviews update the suite
  label in a follow-up commit? Answer: applied reviews remain sidecar-only
  evidence and do not update suite metadata automatically.
- What minimum reviewer packet is enough for the three deferred cases: current
  contact sheets plus `review-decision.json`, or a curated gallery that puts all
  deferred cases in one scan? Answer: the minimum packet is the curated gallery
  plus `review-packet.md/json`, terminal templates, and per-case
  `decision_choice_commands` with reviewer evidence-flag hints. Contact sheets
  and individual review sidecars remain linked, but raw JSON inspection is not
  required for the first pass.
- Do we want region truth annotations inside `docs/real-images/suite.json`, or
  in per-case sidecar files to keep the suite compact? Answer: current curated
  region truth remains in `docs/real-images/suite.json` so gates, snapshots,
  promotion exports, review packets, and harvest plans share one authoritative
  case contract. Portable review decisions live in sidecar plan files because
  they are reviewer evidence overlays, not source-region truth. If the corpus
  grows enough to make the suite hard to review, split region truth into
  per-case sidecars only after the loader preserves the same stable ids and
  snapshot diff semantics.
- What is the minimum visible artifact that convinces us a region is truly
  editable: SVG node count, side-by-side render, editability component scores,
  or reviewer-applied correction? Answer: no single artifact is enough. A
  trusted region needs the contact sheet or gallery for visual inspection,
  region truth with gate-ok state for semantic contract evidence, editability
  v10 component scores for structure evidence, promotion export metadata for
  SVG traceability, and an applied accepted/corrected review when manual
  policy is involved. Harvest-prep Markdown now keeps reviewed region ids,
  review-promoted region ids, and review-promoted anchor indexes visible after
  pending cases move into applied status. Pending harvest cases now also carry
  failed gate ids and structured failed-gate reasons forward from the review
  packet, so reviewers can see why a case remains blocked without opening raw
  packet JSON.

## Commit Discipline

Use modular Conventional Commits:

- `docs:` for roadmap/spec/status updates;
- `feat:` for new promotion, gate, region, export, or review capability;
- `fix:` for detector or gate behavior corrections;
- `test:` for fixtures, snapshots, baselines, and regression cases.

Every promotion-quality commit should name the protected failure family in its
message or body when possible.
