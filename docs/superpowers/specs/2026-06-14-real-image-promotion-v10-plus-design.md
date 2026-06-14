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
- A contact sheet shows source, preview, overlay, rendered SVG, diff, decision,
  and failed-gate context.
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
  `review-decision.json`;
- reviewer decision templates for accepted, corrected, rejected, and deferred.
  Current slice: checked promotion runs write terminal JSON templates under
  `review-templates/`, and suite-level review packets link those paths per
  case;
- applied-review summaries that link back to region truth and promotion gates;
- a small local gallery for current green/yellow/red examples. Current slice:
  curated runs with `--output-dir` write `review-gallery.html`, a static local
  page with contact sheets, quality labels, promotion/editability decisions,
  failed gates/components, review links, and terminal decision-template links.

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
  and Source Deltas tables so selected classical and MLX/SAM runs can be
  reviewed side by side. It also emits a source delta assessment that labels
  the comparison as improved, mixed, noise, unchanged, or needing review from
  green promotion, red candidate, manual-review, and proposal-count deltas. The
  downstream status rows are treated as promotion proxies until region-level
  promotion labels exist.

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
  missing-from-promoted rows that surface region reasons.
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
  reruns and harvests only accepted/corrected applied reviews. `merge-labels`
  keeps review and applied-review provenance in pseudo-label manifests, and
  dataset samples carry review item id, review reason, issue tags, applied
  decision, applied case id, and source review-decision path. `self-learn`
  Markdown reports summarize reviewed-label issue counts and provenance-field
  coverage.

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

Exit criteria:

- a new real-image case can be added, audited, reviewed, and carried through
  baseline-gated learning without changing code;
- the project can show honest examples without overclaiming quality;
- false-positive semantic promotion remains the highest-severity failure.

## First Concrete Implementation Packet

The next packet should be **RP10.1 Red Gate Kill List**, because the baseline is
now clean and the suite is semantically green. More corpus or MLX work before
this would amplify unresolved promotion failures.

Scope:

- keep Lucide and primitive checks green;
- keep all three current real-image cases semantically green;
- choose one current red gate as the first fix target;
- update the fixture, report, snapshot, and suite-family baseline only after the
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
   applying a decision.
2. Decide whether applied `accepted`/`corrected` reviews should update
   `current_quality_label` in suite metadata, or remain sidecar-only applied
   review evidence. Current policy is sidecar-only: pending decisions,
   terminal templates, and applied summaries carry `quality_label_policy` with
   `updates_current_quality_label: false`; suite labels remain manual metadata
   until the suite file is explicitly edited.
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

Baseline refresh should happen only after the acceptance commands pass and the
suite-family comparison reports no new regressions.

## Review Questions for Us

These are the planning questions to answer before starting RP10.1:

- Should `current_quality_label` remain manually red until explicit applied
  review, or should applied `accepted`/`corrected` reviews update the suite
  label in a follow-up commit? Answer: applied reviews remain sidecar-only
  evidence and do not update suite metadata automatically.
- What minimum reviewer packet is enough for the three deferred cases: current
  contact sheets plus `review-decision.json`, or a curated gallery that puts all
  deferred cases in one scan?
- Do we want region truth annotations inside `docs/real-images/suite.json`, or
  in per-case sidecar files to keep the suite compact?
- What is the minimum visible artifact that convinces us a region is truly
  editable: SVG node count, side-by-side render, editability component scores,
  or reviewer-applied correction?

## Commit Discipline

Use modular Conventional Commits:

- `docs:` for roadmap/spec/status updates;
- `feat:` for new promotion, gate, region, export, or review capability;
- `fix:` for detector or gate behavior corrections;
- `test:` for fixtures, snapshots, baselines, and regression cases.

Every promotion-quality commit should name the protected failure family in its
message or body when possible.
