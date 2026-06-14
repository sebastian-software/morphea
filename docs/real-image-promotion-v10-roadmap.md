# Real-Image Promotion v10+ Roadmap

## Summary

Real images are Morphēa's primary proving ground. Synthetic primitives and
icon benchmarks are necessary calibration tools, but the system only matters if
it can turn messy raster inputs into SVG structure that feels intentionally
built by a human.

This roadmap defines the high bar for that work. A region is not successful
because it passes a numeric raster threshold. It is successful only when the
promoted SVG is visually credible, semantically honest, and useful to edit.

The main track is **Real-Image Promotion**. MLX/SAM is an enabling segmentation
track. Editability scoring is the promotion gate and ranking discipline.

The execution design for the next v10+ planning layer lives in
[`docs/superpowers/specs/2026-06-14-real-image-promotion-v10-plus-design.md`](superpowers/specs/2026-06-14-real-image-promotion-v10-plus-design.md).

## Roadmap Operating Model

This roadmap separates four concerns that must not collapse into one score:

- **Mainline**: real-image promotion. This decides whether source regions
  become trusted semantic SVG, honest fallback, deferred work, or rejected
  attempts.
- **Segmentation enablers**: classical masks, color grouping, MLX/SAM, and
  future learned region proposal systems. These propose regions; they do not
  certify output quality.
- **Quality gates**: deterministic checks that can block promotion regardless
  of aggregate score.
- **Learning loop**: reviewed pseudo-label collection and model improvement.
  This loop consumes accepted evidence; it does not decide what is true.

Every major change should answer the same question: did it increase trusted
green promotion on real images without hiding red failures?

## Current Honest State

Morphēa already has the foundation for real-image work:

- semantic-first editability is accepted in ADR 0001;
- local MLX-first segmentation is accepted in ADR 0002;
- reviewed pseudo-label self-learning is accepted in ADR 0008;
- the curated real-image suite lives in `docs/real-images/suite.json`;
- bounded preprocessing, runtime controls, snapshots, primitive anchors, scene
  groups, and run artifacts exist;
- the Lucide benchmark exposes icon-scale semantic failures with deterministic
  source assets.

The Lucide audit is the warning sign that shapes this roadmap. A prior green
aggregate pass still allowed `badge-check` to be visually wrong: a scalloped
badge was promoted as a round ring. That is a false positive, not a tolerable
approximation. The current honest Lucide posture is now 24/24 after preserving
`badge-check` as a closed irregular `stroke_path`, plus several yellow cases
that are semantically plausible but visibly loose. `lucide-check` reports now
preserve optional `quality_label` and `review_notes` metadata and write a
Quality Ledger that names the five yellow calibration cases directly.
The suite also carries negative contracts for the original false-positive
class: `badge-check` requires zero full-icon `stroke_circle` matches, and
`circle` requires zero full-icon irregular `stroke_path` matches. When those
guards fail, Lucide reports label the issue as `forbidden_matches`.

Future gates must catch this class of error. A benchmark may be useful while
red. It is harmful when it calls red output green.

## Non-Negotiable Invariants

These invariants override milestone convenience, aggregate scores, and demo
pressure:

- **No semantic lies**: a shape with the wrong class, topology, or grouping is
  red, even if it looks superficially close.
- **No silent degradation**: every failed, deferred, or rejected semantic
  attempt must remain visible in reports.
- **No unreviewed learning**: pseudo-labels become training data only after
  review.
- **No cloud dependency**: cloud tools and external vectorizers may be
  comparison references, never required runtime dependencies or label sources.
- **No dashboard laundering**: thresholds may not be loosened merely to turn a
  suite green.
- **No single-metric promotion**: L1, edge error, node count, or classifier
  confidence can support a decision but cannot certify promotion alone.
- **No hidden fallback**: fallback output must be explicitly labeled and must
  not masquerade as promoted structure.

## Quality Doctrine

Morphēa must optimize for editable semantic structure before pixel-perfect
tracing, but it must not use "editability" as an excuse for wrong geometry.

Quality labels:

- **Green**: visually convincing, semantically correct, editable, compact, and
  explainable.
- **Yellow**: useful evidence, close enough to study, but not promotable as a
  trusted output.
- **Red**: blocked. The output loses shape identity, topology, grouping, or
  visible intent even if raster metrics pass.

Promotion rules:

- A primitive substitution that erases meaning is red.
- Reusing one detected anchor to satisfy two semantic expectations is red.
- Low node count is good only when the shape remains true.
- Higher raster fidelity is not enough if the output fragments into
  uneditable noise.
- Slight raster deviation is acceptable only when the semantic structure is
  visibly right and easier to edit.
- Every promoted region must carry provenance: source region, detector path,
  score evidence, and rejection alternatives where available.

## Promotion Contract

Every candidate region in a real image must end in one explicit state:

- `promoted`: trusted editable SVG structure;
- `fallback`: rendered or traced conservatively because no semantic structure
  is trusted;
- `deferred`: intentionally skipped because the system lacks a reliable
  detector, segmenter, or runtime budget;
- `rejected`: attempted semantic promotion failed quality gates.

Promotion requires all of the following:

- visual fidelity within a family-specific envelope;
- stable shape identity, such as circle, stroke, grid, text-like fragment,
  logo mark, or organic fallback;
- topology consistency, including holes, cut-outs, closed paths, joins, and
  repeated structures;
- distinct anchors for distinct semantic parts;
- bounded fragmentation and layer depth;
- editable parameters that match the intended object;
- grouping when repeated parts form one semantic object;
- deterministic artifacts for human review.

The system should prefer an honest fallback over a confident lie.

## Artifact Model

The v10+ pipeline should make these artifacts explicit. Names are conceptual
contracts; implementation may choose concrete JSON field names later, but must
preserve the same boundaries.

- **Corpus case**: source image reference, licensing/provenance, intended
  stress family, recommended bounded config, current red/yellow/green status,
  and review notes.
- **Region proposal**: source crop, region bounds, mask source, segmentation
  method, parent case id, and reason the region is being evaluated.
- **Semantic candidate**: proposed SVG structure, anchor ids, primitive kinds,
  grouping, detector provenance, score components, and rejected alternatives.
- **Promotion decision**: one of `promoted`, `fallback`, `deferred`, or
  `rejected`, with gate outcomes and human-readable rationale.
- **Review record**: reviewer decision, issue tags, correction notes, accepted
  label payload when applicable, and provenance of the reviewed artifact.
- **Snapshot**: stable machine-readable summary of case status, promotion
  counts, metrics, gates, failures, and visual artifact paths.

The report hierarchy should flow from case to region to candidate to decision.
Aggregate suite summaries are useful only after the individual decisions remain
inspectable.

## Green/Yellow/Red Rubric

Promotion color is a decision label, not a visualization preference.

| Label | Meaning | Allowed in promoted SVG? | Typical Action |
| --- | --- | ---: | --- |
| Green | Correct shape identity, topology, grouping, fidelity, and editability. | yes | Promote and track for regression. |
| Yellow | Useful evidence, but visibly loose, under-specified, or missing a gate. | no | Keep in reports, improve detector or contract. |
| Red | Wrong semantic structure, hidden failure, severe visual mismatch, or unsafe learning signal. | no | Block promotion and tag failure cause. |

Green requires passing all hard gates. Yellow may have acceptable raster
metrics. Red may have acceptable raster metrics. The label is assigned by the
promotion contract, not by a single metric.

## Gate Registry

Hard gates block promotion. Score components can rank candidates after these
gates pass, but they cannot override a hard failure.

| Gate | Blocks When | Required Evidence |
| --- | --- | --- |
| Shape class | Candidate primitive family does not match the intended source structure. | detector family, expected family, visual overlay |
| Topology | Holes, cut-outs, open/closed state, joins, or disconnected parts are wrong. | source mask, candidate topology summary, diff |
| Distinct anchors | One detected anchor satisfies multiple semantic parts that should be independent. | contract expectation ids, anchor ids |
| Fragmentation | One editable object becomes many ungrouped or noisy pieces. | shape count, group ids, source region |
| Grouping | Repeated or related objects lose their relationship or form a misleading group. | group metrics, member ids, overlay |
| Visual fidelity | Candidate is visibly misplaced, distorted, or incomplete beyond family tolerance. | rendered SVG, reference crop, diff metrics |
| Provenance | Candidate lacks source region, detector path, or decision rationale. | manifest fields, run artifact paths |
| Review safety | Candidate would become training data without accepted review. | review record, label provenance |

Any hard-gate failure makes the candidate red unless the region is explicitly
marked `deferred` before semantic promotion is attempted.

## Report Contract

Promotion reports must lead with decision quality rather than raw metric
tables.

Required report order:

1. red failures by severity;
2. false-positive promotion risks;
3. yellow cases requiring review;
4. green promoted regions;
5. fallback and deferred regions;
6. aggregate metrics;
7. artifact index.

Every report should include:

- case-level red/yellow/green status;
- stress family, expected promotion families, issue tags, and licensing status;
- region-level promotion decisions;
- region-level expected-vs-actual truth for configured source-region gates;
- region-level layer-depth and fragmentation evidence;
- failed hard gates;
- score component breakdowns;
- reference/render/diff contact sheet links;
- region-overlay contact sheet links that outline source-region gate outcomes;
- snapshot comparison when a baseline exists;
- snapshot comparison rows that identify changed source-region ids;
- missing-source or capability warnings.

Reports that show only aggregate pass/fail counts are incomplete for v10+
promotion work.

## Milestone Ladder

### RIP0: Roadmap Cleanup and Audit Baseline

Purpose: make the current state legible before adding new capability.

Exit criteria:

- `docs/milestones.md` links to this roadmap as the forward-looking real-image
  track.
- Lucide status is documented as 24/24, with the prior `badge-check` false
  positive resolved and named yellow cases still visible in generated
  `lucide-check --markdown` reports.
- Real-image suite status is summarized with green/yellow/red labels.
- Existing snapshot and run artifact commands remain documented.
- No document claims that aggregate pass/fail equals visual quality.

### RIP1: Real-Image Corpus v10

Purpose: replace tiny ad hoc real-image evidence with a curated, representative
corpus.

Required families:

- generated illustrations with antialiasing and palette drift;
- UI screenshots with text, controls, icons, and thin strokes;
- logos and marks with strong shape identity;
- icons embedded in screenshots rather than isolated fixtures;
- diagrams, tables, grids, and repeated structures;
- mixed text/image compositions;
- transparent-background and near-white-background cases.

Exit criteria:

- every case has source provenance, licensing status, recommended bounded
  config, and human-readable intent;
- every case has red/yellow/green labels for current output;
- every case can generate reference/render/diff contact sheets;
- source images that cannot be checked in are represented by stable local-path
  metadata and snapshot artifacts.

### RIP2: Quality Gate v2

Purpose: make false positives harder than honest failures.

Required gates:

- distinct-anchor contract evaluation;
- topology mismatch detection for holes, rings, cut-outs, closed paths, and
  disconnected components;
- shape-class mismatch detection for cases such as scalloped badge vs circle;
- fragmentation and layer-depth penalties;
- group consistency checks for grids, repeated icons, and parallel strokes;
- visual diff summaries with red/yellow/green thresholds, region-level
  source-vs-SVG crop deltas, and named region visual failures;
- per-family thresholds rather than one global raster score.

Exit criteria:

- `badge-check` cannot pass as a circle-like substitute.
- A real-image region with wrong topology is red even with acceptable L1.
- Markdown reports show failed gates before aggregate metrics.
- Contact sheets are first-class review artifacts, not optional debugging.

### RIP3: Promotion Pipeline

Purpose: make promotion an explicit pipeline stage instead of an implicit side
effect of candidate ranking.

The pipeline should:

1. segment candidate regions;
2. generate semantic candidates;
3. compare candidate families and fallbacks;
4. assign promotion state;
5. write provenance and review artifacts;
6. export only trusted promoted shapes as semantic SVG.

Exit criteria:

- manifests expose region-level promotion state;
- fallback and rejected regions are visible in reports;
- promoted SVG output can be filtered from debug/fallback output;
- no failed semantic candidate disappears silently.

### RIP4: Editability Score

Purpose: turn semantic-first intent into a measurable, reviewable score.

The score must combine:

- shape identity confidence;
- parameter economy;
- node economy;
- stroke width stability;
- line and curve smoothness;
- topology consistency;
- grouping quality;
- fragmentation penalty;
- raster fidelity;
- provenance confidence;
- classifier prior disagreement.

Exit criteria:

- score components are visible independently;
- a high score cannot hide a red topology or shape-class gate;
- score regressions can be compared across snapshots;
- accepted outputs produce better human-editable SVG, not just lower error.

### RIP5: MLX/SAM Segmentation Track

Purpose: use local model segmentation only where it improves promotion
decisions.

MLX/SAM is not a replacement for quality gates. It is a candidate-region
generator and comparison baseline.

Exit criteria:

- the pipeline can run classical and MLX/SAM segmentation side by side;
- segment provenance records which source produced each candidate;
- `compare-segments` reports per-source proposal/downstream status deltas so
  classical and MLX/SAM outputs can be judged before defaulting either source;
- source comparisons include an assessment verdict for improved, mixed, noise,
  unchanged, or needs-review outcomes based on promotion-proxy deltas;
- MLX/SAM is judged by green promotion increase and red false-positive
  decrease, not by mask aesthetics alone;
- the system remains usable without cloud APIs.

### RIP6: Human Review Artifacts

Purpose: make review fast enough to support a self-learning loop.

Review artifacts should show:

- source crop;
- promoted SVG render;
- diff;
- anchor overlay;
- promotion state;
- failed gates;
- editable structure summary;
- issue tags.

Current implementation evidence: checked promotion runs write
`promotion-review.md` for anchor state, region state, and candidate rejection
reasons, `contact-sheet.png` for visual comparison, and `editability-review.md`
for accepted-output decision, threshold status, gate-blocked components, issue
tags, and regression deltas.
They also write `review-decision.json`, a pending machine-readable decision
record with suggested accepted/corrected/rejected/deferred outcome and the
gate/component evidence needed for review, plus terminal
accepted/corrected/rejected/deferred review templates that preserve the same
evidence.
Curated output roots also write `review-gallery.html`, so those artifacts can
be scanned visually from one local page before a terminal decision is applied.
`morphea promotion-apply-review` consumes edited terminal decision records,
rejects pending records, writes applied JSON/Markdown summaries, and can
persist `review_decision_applied` into run manifests. Pending, terminal, and
applied review records carry `quality_label_policy.mode: sidecar_only`, so
accepted/corrected reviews become auditable evidence without implicitly
rewriting suite `current_quality_label`.
`morphea harvest --require-applied-review` can then gate pseudo-label
harvesting so only accepted/corrected applied decisions become candidates.
`morphea harvest-curated --require-applied-review` preserves existing applied
decisions across fresh curated reruns and restores them into regenerated
manifests and curated JSON reports before harvesting.
`morphea review --accept-applied-reviews` maps harvested applied promotion
reviews into the existing review/apply-review loop while preserving issue tags.
`morphea merge-labels` preserves review and applied-review provenance in
accepted pseudo-label manifests, and dataset samples carry review item id,
review reason, issue tags, applied decision, applied case id, and source
review-decision path while excluding rejected/deferred review items from
trainable datasets.
`morphea self-learn` separates retraining from acceptance: acceptance requires
the training comparison gate plus passing curated validation when configured,
and cycle summaries expose reviewed-label issue and applied-decision counts.
Cycle Markdown reports also show reviewed-label issue counts and provenance
field coverage, so a training run can be scanned for missing review lineage.
Training comparisons now include per-label validation accuracy deltas, and
those deltas feed best/worst gate summaries so primitive-family regressions can
block acceptance.
Self-learning cycle reports now expose normalized `suite_family_validation`
across primitive label families, curated real-image family summaries, and
optional Lucide family summaries. `morphea self-learn --lucide-suite` validates
accepted models with the same `classifier_model` override and blocks acceptance
on Lucide failures.
`morphea self-learn --suite-family-baseline` compares the current normalized
family view against a fixed baseline and blocks acceptance only for newly
introduced bad family outcomes, separating known suite debt from fresh
regressions.
When baseline comparison is clean, known curated/Lucide validation failures
remain visible but are not blocking acceptance reasons.
Known baseline debt is also listed as `known_debt` / `known_debt_count` in
cycle reports, so accepted runs show carried red families separately from new
or resolved regressions.
`morphea self-learn --suite-family-baseline-output` writes accepted
`suite_family_validation` snapshots as reusable baseline artifacts and skips
writes for rejected cycles.
Baseline snapshot writes now require reviewer, reason, and changelog evidence;
successful writes embed the review record and append a JSONL changelog entry.
Cycle Markdown keeps the portable baseline artifact clean while surfacing the
run-local source cycle, base dataset, reviewed-label file, and validation
dataset next to the snapshot status, so baseline promotions can be audited back
to the exact accepted retraining cycle.
Existing baseline output files are protected unless the configured
`suite_family_baseline` path matches the output path, so checked-in baselines
cannot be overwritten by an accidental ad hoc output path.
`docs/real-images/baselines/current-suite-family-baseline.json` is checked in
as a reviewed accepted-cycle baseline and is exercised through the real
`morphea self-learn --suite-family-baseline` CLI path. Current known baseline
debt is empty: the Lucide `circle_compound_strokes` debt was resolved by
preserving the irregular `badge-check` outline as a closed `stroke_path`, the
checked `generated_illustration_table_grid` family passes after preserving the
large beige table palette, and the
`generated_illustration_opaque_table_grid` family moved from `failed_missing`
to `passed` through the checked-in opaque fixture.

Canonical issue tags:

- `shape_class_mismatch`;
- `topology_mismatch`;
- `fragmentation`;
- `bad_grouping`;
- `stroke_instability`;
- `false_positive_promotion`;
- `weak_visual_fidelity`;
- `overfit_trace`;
- `missing_semantic_detector`.

Exit criteria:

- a reviewer can mark each candidate accepted, corrected, rejected, or
  deferred;
- review decisions are machine-readable;
- issue tags survive into training and regression reports.

### RIP7: Reviewed Pseudo-Label Loop

Purpose: learn from Morphēa's own accepted outputs without copying the wrong
target from external vectorizers.

The loop must follow ADR 0008:

- collect high-confidence outputs;
- expose them for human review;
- train only from accepted or corrected labels;
- preserve provenance, gates, group context, and issue tags;
- compare retrained models against curated real-image and synthetic suites.

Exit criteria:

- unreviewed pseudo-labels never become training labels;
- external vectorizers may be comparison material but never label sources;
- model acceptance requires improved promotion quality, not just classifier
  accuracy.

### RIP8: Multi-Family Regression Discipline

Purpose: prevent progress in one family from hiding regressions in another.

Required report views:

- real-image corpus summary;
- Lucide icon summary;
- primitive fixture summary;
- family-specific green/yellow/red counts;
- top red failures by severity;
- yellow drift list;
- node and fragmentation deltas;
- contact-sheet index.

Exit criteria:

- every detector change can be audited by family;
- snapshots distinguish intentional semantic changes from accidental drift;
- failures are sorted by user-visible severity, not by test order.

### RIP9: Promotion-Centric SVG Export

Purpose: make exported SVG reflect trust boundaries.

Export policy:

- promoted regions export as editable semantic SVG;
- fallback regions export only when explicitly requested;
- rejected semantic candidates stay in debug artifacts;
- deferred regions are visible in manifests and reports;
- groups preserve semantic names and provenance ids.
- exported promotion SVG nodes carry stable anchor, promotion-region, and
  applied-review metadata so trusted output can be inspected without guessing
  which manifest record produced each node.
- curated `promoted.svg` and `fallback.svg` sidecars carry the same stable
  metadata wrappers as explicit `promotion-export` runs.
- `promotion-export --markdown` writes a scan-friendly export report that shows
  promoted/fallback/rejected/deferred counts and region reasons for items
  missing from the promoted SVG.

Exit criteria:

- users can inspect only trusted structure;
- debug exports can explain what was attempted and rejected;
- promoted SVGs avoid hidden semantic lies.

### RIP10+: Local Self-Improving Real-Image System

Purpose: converge on a local research system that improves through evidence,
review, and regression discipline.

The target system:

- runs locally on Apple Silicon;
- combines classical geometry, MLX/SAM segmentation, learned priors, and
  deterministic gates;
- promotes only trustworthy structure;
- learns only from reviewed labels;
- keeps every decision inspectable;
- treats false-positive promotion as the highest-severity quality failure.

The v10+ bar is not "vectorize more images." It is "earn trust on real images."

## Recommended Execution Order

Work should proceed in this order unless a later audit proves a different
dependency:

1. **Lock the audit language**: keep Lucide, primitive, and real-image reports
   honest about red/yellow/green status before changing detectors.
2. **Curate the corpus**: add enough real-image cases to expose different
   failure families, but keep every case reviewed and explainable.
3. **Generate visual review artifacts**: make contact sheets and overlays cheap
   enough that every suite run can be inspected.
4. **Implement hard gates**: distinct anchors, topology mismatch, shape-class
   mismatch, fragmentation, and grouping consistency must block promotion.
5. **Add promotion state**: manifests and exports must distinguish promoted,
   fallback, deferred, and rejected regions.
6. **Introduce editability score**: score components should explain ranking
   after hard gates, not replace them.
7. **Capture review decisions**: make accepted/corrected/rejected/deferred
   decisions machine-readable before pseudo-label harvesting.
8. **Apply review decisions**: consume edited decision records and write an
   applied summary back to manifests and reports.
9. **Gate harvesting on applied decisions**: accepted/corrected applied
   decisions can become training candidates; rejected/deferred decisions stay
   as review evidence.
10. **Preserve applied decisions in curated harvests**: make rerunnable
   curated self-learning consume reviewed run roots or reapply edited decision
   records before harvesting.
11. **Collect reviewed pseudo-labels**: export only accepted/corrected applied
   promotion reviews into the reviewed-label self-learning path while retaining
   rejected/deferred evidence.
12. **Prove reviewed-label merge gates**: merge only accepted/corrected applied
   promotion reviews into trainable datasets and keep rejected/deferred
   evidence out.
13. **Run MLX/SAM side by side**: compare segmentation sources only after the
   promotion evaluator can tell whether a region proposal helped.
14. **Run reviewed pseudo-label training gates**: train only from green or
   corrected review artifacts, then accept models only when curated validation
   quality improves without family regressions.
15. **Add family regression evidence**: acceptance must show which real-image,
   Lucide, and primitive families improved, held steady, or regressed.
16. **Promote suite-family validation**: compare real-image, Lucide, and
   primitive validation views side by side before accepting self-learning
   models.
17. **Baseline suite-family validation**: compare those family views against
   fixed real-image, Lucide, and primitive baselines so newly introduced
   regressions are separated from known suite debt.
18. **Persist accepted suite-family baselines**: write accepted
   `suite_family_validation` snapshots as reviewed baseline artifacts for the
   next self-learning cycle.
19. **Review baseline updates**: require metadata and changelog evidence before
   replacing a fixed suite-family baseline.
20. **Constrain baseline replacement paths**: require an explicit expected
   baseline target before overwriting an existing checked-in suite-family
   baseline.
21. **Check in a suite-family baseline smoke**: add a small baseline fixture and
   documented CLI smoke path that exercises the baseline-gated self-learning
   flow end to end.
22. **Promote a reviewed suite-family baseline**: replace the empty smoke
   baseline with an accepted cycle artifact once the real-image, Lucide, and
   primitive family evidence has been reviewed.

Do not broaden icon suites, train models, or chase benchmark aggregates before
steps 1-5 are credible. More data amplifies bad gates.

## First Implementation Packet: RIP0 + RIP1

The next concrete implementation packet should combine current-state cleanup
with corpus design.

Current human-readable status lives in
`docs/real-images/promotion-status.md`. Machine-readable per-case labels live
in `docs/real-images/suite.json`.

Required deliverables:

- update milestone and plan docs to point to this roadmap;
- record the Lucide status as 24/24 with the prior `badge-check` false
  positive resolved and named yellow cases still visible;
- add a real-image status ledger that labels each curated case green, yellow,
  or red under the current pipeline;
- define a minimal corpus schema extension for source provenance, licensing
  status, stress family, expected promotion families, and current quality
  label;
- generate or specify contact-sheet artifacts for every curated real-image
  case;
- keep missing local source images visible as unavailable cases rather than
  silently dropping them;
- avoid detector tuning until the corpus and labels make failure modes visible.

Exit criteria:

- a reviewer can open one report and see which real-image families are green,
  yellow, and red;
- every current real-image case has an explicit intended stress family;
- every current red/yellow case has issue tags;
- the next implementation plan can target Quality Gate v2 without guessing the
  corpus contract.

## Promotion Severity

Failures should be sorted by user-visible severity:

1. **False-positive promotion**: wrong semantic SVG is marked green.
2. **Topology loss**: holes, cut-outs, joins, or closed/open state are wrong.
3. **Shape-class mismatch**: the output substitutes the wrong primitive family.
4. **Grouping failure**: repeated parts lose their relationship or become a
   misleading group.
5. **Fragmentation**: editable objects explode into many small pieces.
6. **Visual drift**: structure is plausible but visibly misplaced or distorted.
7. **Runtime deferral**: the region is skipped because the current pipeline
   cannot process it safely.

False-positive promotion is always more severe than honest fallback. A red
fallback can be improved later; a green lie pollutes review, training, and user
trust.

## Implementation Principles

- Build gates before broadening the corpus.
- Prefer small, labeled, high-signal suites over large unreviewed collections.
- Keep benchmark failures visible until they are genuinely solved.
- Do not tune thresholds to make dashboards green.
- Make visual audit artifacts cheap to generate and hard to ignore.
- Treat source provenance and licensing as part of corpus quality.
- Separate segmentation quality from promotion quality.
- Keep fallback honest and reversible.

## Acceptance Definition

This roadmap is satisfied only when a later implementation can demonstrate:

- real-image cases are evaluated with red/yellow/green labels;
- promoted regions have explicit state and provenance;
- visual contact sheets exist for every promoted or rejected candidate;
- false-positive semantic promotion is caught by gates;
- editability score explains decisions in components;
- MLX/SAM improves promotion outcomes before it becomes default;
- reviewed pseudo-labels are the only training source for self-learning;
- exported SVGs are useful to edit, not just plausible to view.
