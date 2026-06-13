# Morphēa Milestone Plan

This document expands the implementation plan beyond the first base-form
prototype. The long-term goal is a local, self-improving, semantic-first
raster-to-SVG research system.

## North Star

Morphēa should produce SVGs that feel intentionally constructed by a human:
simple shapes stay simple, strokes stay editable, cut-out lines stay clean,
and repeated structures become coherent groups. Visual similarity matters, but
editable semantic structure is the primary quality target.

The system should evolve from deterministic geometry first, then add local AI,
then add training and self-learning loops.

The active step-by-step quality track for primary forms and primitive
compositions lives in [primitive-quality-roadmap.md](primitive-quality-roadmap.md).
The forward-looking high-bar track for real images lives in
[real-image-promotion-v10-roadmap.md](real-image-promotion-v10-roadmap.md).

## M0: Primitive Anchor Prototype

Status: implemented.

Purpose: prove that the repo can detect and process the first simple forms
end-to-end.

Implemented capabilities:

- Binary-mask connected components.
- Circle and dot anchors.
- Circle rings as `stroke_circle`.
- Smooth line strokes using principal-axis fitting.
- Perspective quads as editable polygons.
- Simple white cut-out gaps as overlay strokes.
- Near-flat RGB grouping via `--color-tolerance`.
- Plain SVG export and JSON recognition manifest.
- CLI path: `morphea vectorize input.png -o output.svg`.

Acceptance evidence:

- `PYTHONPATH=src python3 -m unittest discover -s tests`
- Current suite covers masks, PNG fixtures, SVG export, CLI, manifests,
  cut-outs, rings, strokes, quads, and grid grouping.

## M1: Real-Image Preprocessing and Runtime Control

Status: implemented for the current real-image runtime baseline.

Purpose: make real generated images tractable before adding heavier ML.

Why this matters: real images contain antialiasing, palette drift, transparent
backgrounds, soft texture, and large components. The current pure-Python mask
pipeline can stall on full-size 1254px images.

Deliverables:

- Image normalization stage:
  - alpha flattening or transparent-region ignore policy
  - palette quantization with configurable max colors
  - near-white and near-background grouping
  - optional downsample-for-analysis with final-coordinate scaling
- Region-of-interest splitting:
  - process large color masks as bounded components
  - skip or defer components above a configured complexity threshold
  - emit warnings instead of hanging
- Runtime limits:
  - `--max-size`, `--max-component-area`, `--timeout-seconds`
  - manifest entries for skipped/deferred components
- Faster component implementation:
  - replace hot loops with array-backed operations where useful
  - preserve the current `BinaryMask` API as a testable interface

Acceptance criteria:

- `terminaro-tweaked.png` completes a CLI run without hanging.
- Manifest reports major palette groups and skipped/deferred regions clearly.
- Large background/transparent areas do not become vector candidates.
- Tests include at least one antialiased and one transparent-background fixture.
- `morphea curated-check docs/real-images/suite.json --run` completes the
  current curated real-image suite with no failed expectations under an
  external timeout.

Implemented so far:

- `--max-size` analysis resize with anchor coordinate scaling.
- `--max-colors` palette quantization.
- `--max-component-area` color-mask/component deferral diagnostics.
- `--timeout-seconds` internal partial-run cutoff.
- manifest `diagnostics` entries.
- bounded `terminaro-tweaked.png` run completes under an external timeout.
- transparent-background regression fixture.
- transparent pixels are ignored with diagnostics, and partial-alpha pixels are
  flattened onto the inferred or configured background before color grouping.
- explicit `background` preprocessing is available through vectorize/profile
  configs, sweep run configs, curated recommended configs, and flat-color
  segment configs.
- large color masks emit `color_mask_split_for_components` and are split into
  connected components before oversized components are deferred.
- image component scanning checks `timeout_seconds` during traversal and avoids
  retaining pixel sets for oversized deferred components.
- `connected_components` and the bounded image component scanner use a
  bytearray-backed occupancy grid during BFS while preserving the public
  `BinaryMask` / `MaskComponent` API.
- component BFS scans neighbors inline instead of allocating per-pixel
  neighbor tuples in the hot loop.
- flat-color mask extraction scans image buffers sequentially via Pillow pixel
  data instead of calling `getpixel` for every pixel.
- flat-color mask extraction stores linear pixel indexes during palette
  grouping and materializes `(x, y)` coordinates only for retained masks.
- exact-color mask extraction bypasses palette membership scans, while
  tolerant grouping caches repeated source colors to avoid repeated nearest
  palette searches.
- mask components can carry bounds hints from component scanning, and
  `row_spans` computes per-row extents in one pass instead of rescanning the
  component once per row.
- `morphea profile input.png -o profile.json` records bounded vectorize timings,
  anchor counts, diagnostics, diagnostic stage counts, and min/mean/max elapsed
  summaries for repeated runs.
- `morphea profile-curated suite.json -o profile.json` profiles every available
  curated real-image case with its recommended config, keeps missing sources
  visible, and reports the slowest case plus per-case min/mean/max timings.
- component BFS in both generic masks and bounded image scanning uses direct
  8-neighbor index checks instead of nested per-pixel neighbor range loops.
- boundary-pixel detection and centroid calculation avoid repeated generator
  passes and per-pixel neighbor tuple allocation.
- raster edge metrics use compact integer luma buffers instead of float lists
  during preview/refinement comparisons.
- mask components cache derived centroid, boundary-pixel, and row-span
  geometry so primitive candidate generation does not rescan the same pixels
  for each simple-shape hypothesis.
- connected-component BFS now fills bounds, centroid, and row-span hints during
  the scan, including bounded image scans, so downstream primitive detection
  avoids repeated component passes.
- connected-component BFS now also fills boundary-pixel hints, including
  bounded image scans, so circle/ring/stroke candidate generation can reuse
  scanner-derived boundaries instead of rescanning retained components.
- freeform cut-out gap detection uses a local interior-gap component scanner
  for temporary background gaps, avoiding the heavier generic
  `connected_components` hint path during real-image profiling.
- principal-axis fitting computes projection bounds in one streaming pass
  instead of allocating per-component projection lists.
- temporary interior-gap scans avoid redundant seed-list allocation, and
  enclosed-gap bound checks use component bounds instead of rescanning every
  gap pixel.
- generic and bounded component scanners update bounds and row spans with
  direct comparisons instead of per-pixel `min()`/`max()` calls.
- the temporary interior-gap scanner inlines 8-neighbor enqueueing so
  freeform cut-out detection avoids tens of thousands of per-pixel helper
  calls on curated real images.

Remaining:

- none for the current real-image runtime baseline; continue profile-guided
  hot-loop work from `profile-curated` reports as larger curated image
  families expose new bottlenecks.

## M2: Primitive Anchor Detection V2

Status: implemented for the current primitive-anchor baseline.

Purpose: make simple forms robust enough to be trusted before generic fitting.

Deliverables:

- Circle/ring detection:
  - robust center/radius estimation from boundary samples
  - roundness regularization
  - stroke-width stability metric
- Stroke detection:
  - polyline centerline extraction for curved strokes
  - width estimation along the path
  - cap/join classification
  - cut-out stroke detection for white/near-background gaps
- Quad and grid detection:
  - perspective tile grouping
  - row/column grouping
  - grid consistency metrics
  - vanishing-line diagnostics
- Candidate reservation:
  - anchors reserve pixels/regions before generic fitting
  - later fitting must not fragment reserved simple shapes

Acceptance criteria:

- Outer rings become `stroke_circle` or arc strokes.
- Dots become true circles.
- Straight and gently curved strokes export as stroked paths.
- Perspective table tiles export as quads and are grouped as a grid.
- Simple shape candidates beat noisier path candidates unless fidelity breaks
  materially.

Implemented so far:

- circle/ring metrics for roundness and stroke width.
- filled circle and ring candidates regularize center/radius from boundary
  samples with a deterministic algebraic fit and record
  `circle_fit_residual_error`.
- stroke width, smoothness, cut-out error metrics.
- quad edge/corner metrics and perspective grid consistency metric.
- quad detection adds numeric subtype markers for trapezoids and
  parallelograms while preserving `quad` as the editable primitive kind.
- stroke payloads preserve `cap_style` and `join_style`.
- straight high-coverage stroke components classify as `butt` caps.
- stroke-polyline candidates keep straight strokes as two-point editable
  centerlines, but add a conservative control point when the component visibly
  deviates from the principal-axis line.
- curved stroke and arc candidates record local `width_samples` at centerline
  support points instead of collapsing every editable stroke to one global
  width.
- sparse curved stroke components can classify as editable `arc` anchors with a
  three-point centerline when their bow is large enough to beat a straight
  stroke interpretation.
- diagonal and freeform thin interior gaps can be detected as editable cut-out
  overlay strokes when they are enclosed by the host shape.
- anti-aliased neutral UI rings can be recovered from a composite grayscale
  mask as `circle`/`stroke_circle` anchors when individual gray palette
  fragments are too small to pass per-color component thresholds.
- compact filled axis-aligned rectangles classify as `rect` and stay in the
  `filled_primitives` scene layer.
- simple rounded-rectangle silhouettes classify as `rounded_rect`; descriptive
  metrics such as `corner_radius` are excluded from candidate error scoring.
- anchors with a shared `parallel_group_id` are exposed as
  `parallel_stroke_group` scene groups with `parallel_spacing_error`.
- perspective-grid scene groups expose row/column counts and
  `vanishing_line_diagnostics` derived from quad edge pairs.
- reserved simple-shape anchors are exposed as a
  `primitive_anchor_reservation` scene group with reserved bounds area.
- segment proposals mark simple parametric anchors as reserved with a
  `simple_shape_anchor` reason and reserved bounds before later fitting stages
  can fragment them.

## M3: Scene Graph and Layer Semantics

Status: implemented for the current scene-graph baseline.

Purpose: move from a list of anchors to a coherent editable vector scene.

Deliverables:

- Canonical scene graph:
  - layers
  - groups
  - reserved anchors
  - source masks
  - confidence and provenance
- Stacking and cut-out semantics:
  - v1 white overlay strokes remain supported
  - add mask/negative-stroke option for cases where overlay strokes are wrong
- Shape merging:
  - merge same-color fragments when they form one semantic object
  - avoid Vectorizer.ai-style layer explosion when a simpler object is better
- Export policy:
  - plain editable SVG by default
  - optional debug SVG with source ids and confidence labels

Acceptance criteria:

- Manifest can explain why each output element exists.
- Same-color fragmentation is penalized and visible in reports.
- Cut-outs remain editable and do not silently become unstructured holes.

Implemented so far:

- anchor manifests include stable ids, layer names, confidence, reservation
  bounds, provenance, and export policy metadata.
- anchor manifests include stable `source_mask` proxies derived from reserved
  bounds so run artifacts and review workflows can refer back to mask sources.
- scene manifests include a top-level `layers` section with anchor indexes and
  counts per semantic layer.
- simple anchors are marked as reserved by `simple_shape_anchor`.
- cut-out strokes are assigned to a `cutout_overlays` layer.
- cut-out export policy records the default `overlay_stroke` strategy and
  whether the anchor is eligible for negative-mask SVG export.
- `morphea vectorize --cutout-export negative_mask` writes editable cut-out
  strokes into an SVG mask instead of painting visible white overlay strokes;
  run directories apply the same export option to `output.svg`.
- vectorize config files can set `cutout_export`, with an explicit CLI flag
  taking precedence.
- scene metrics expose reserved simple-shape count, reserved bounds area, and
  reserved area ratio so later fitting can be audited against primitive
  reservations.
- scene metrics include `cutout_overlay_count` and
  `negative_mask_candidate_count` so reports can distinguish overlay exports
  from mask-capable cut-out semantics.
- `morphea vectorize --debug-svg` writes an inspectable SVG with anchor ids,
  bounds, and confidence labels.
- vectorize run directories include `debug.svg`.
- reports, eval summaries, and sweep summaries include layer counts.
- scene manifests include `parallel_stroke_group` entries for grouped strokes.
- scene manifests include `same_color_fragment_group` entries that identify
  same-color merge candidates instead of leaving fragmentation as only a scalar
  penalty.
- same-color fragment groups include a structured `merge_plan` with combined
  bounds, per-fragment bounds, bounds fill ratio, and a conservative merge or
  review action.
- same-color merge plans include `auto_merge_allowed` and `decision_reason` so
  automatic merges stay auditable instead of becoming opaque cleanup behavior.
- compact, same-color, axis-aligned `rect` fragments can be conservatively
  merged into one editable `rect` when their combined bounds contain no gap;
  gapped same-color fragments stay separate to preserve cut-out semantics.

## M4: Reports, Metrics, and Experiment Runs

Status: implemented for the current experiment-report baseline.

Purpose: make every iteration measurable.

Deliverables:

- Timestamped run directories:
  - input copy
  - effective config
  - palette and masks
  - anchors
  - final scene JSON
  - SVG
  - rasterized preview
  - metrics
  - HTML/Markdown report
- Metrics:
  - editability score
  - node/shape/parameter counts
  - simple-shape priority bonus
  - fragmentation penalty
  - circle roundness
  - line smoothness
  - stroke width variance
  - parallel spacing
  - quad/grid consistency
  - raster fidelity diagnostics
- Config sweeps:
  - compare preprocessing thresholds
  - compare anchor candidate thresholds
  - rank outputs by semantic-first score

Acceptance criteria:

- A run can be inspected without rerunning the pipeline.
- Reports show where failures originate: palette, segmentation, fitting,
  cleanup, scoring, or export.

Implemented so far:

- timestamped vectorize run directories via `--run-dir`
- input copy
- `output.svg`
- `preview.png`
- `manifest.json`
- `config.json`
- `anchors.json`
- `palette.json`
- `mask-summary.json`
- `report.md`
- `report.html`
- report summaries for anchor types and diagnostics
- report summaries group diagnostics by pipeline stage so failures can be
  attributed to preprocessing, palette, segmentation, fitting, cleanup,
  scoring, export, runtime, or unknown sources.
- report summaries for scene groups, including same-color fragment groups
- report summaries include same-color merge actions and decision reasons when
  present.
- `morphea eval` JSON/Markdown summaries over run directories
- scene-level `metrics` in manifests
- `editability_score`
- `editability_components`, with formula-level score components exposed for
  reports, snapshots, and sweep summaries
- `editability_v10_components`, with review-level scores for shape identity,
  parameter/node economy, stroke stability, smoothness, topology, grouping,
  fragmentation, raster fidelity, provenance, and classifier-prior agreement
- `editability_review`, with accepted/manual-review/rejected decisions derived
  from promotion state, v10 component thresholds, gate-blocked components, and
  explicit regression-delta status
- `curated-check --baseline-snapshot`, which compares editability-review
  component scores against a previous curated snapshot
- `fragmentation_penalty`
- run-directory raster fidelity metrics: `raster_l1_error`,
  `raster_alpha_error`, `raster_edge_error`, and `raster_size_match`
- node, parameter, simple-shape, generic-path, cut-out, and color-fragment
  counts
- aggregate anchor-quality summaries expose mean/max quality error and
  per-metric counts/means/maxima for primitive fit metrics such as circle
  roundness, line smoothness, stroke-width variance, and quad/grid errors.
- anchor manifests include `simple_shape_priority_bonus` and
  `semantic_anchor_score`, making simple-form preference visible in reports,
  reviews, and pseudo-label harvesting.
- scene metrics aggregate anchor scoring into `anchor_scoring_summary`, so
  runs expose total/mean simple-shape priority and semantic score envelopes.
- scene metrics expose `editability_components`, so score changes can be
  inspected as component deltas instead of opaque aggregate movement.
- scene metrics expose `editability_v10_components`, so RIP4 can grow toward
  the v10 contract without turning any single score into a promotion bypass.
- curated promotion gates cap matching v10 components with `gate_blocked`,
  `failed_gates`, and `uncapped_score`, so red topology, shape-class, grouping,
  visual-fidelity, provenance, or fragmentation gates cannot be averaged away.
- curated reports derive `editability_review`, so accepted-output status is
  tied to component thresholds instead of raster fidelity alone.
- editability review can record `regression_deltas` and
  `regressed_components`, so accepted outputs can be downgraded when component
  quality regresses against a supplied baseline snapshot.
- checked promotion runs write `editability-review.md`, so accepted-output
  decisions, threshold failures, gate-blocked components, issue tags, and
  regression deltas are reviewable beside the promotion export artifacts.
- checked promotion runs write `review-decision.json`, so reviewers get a
  pending machine-readable decision record with suggested
  accepted/corrected/rejected/deferred outcome, issue tags, failed gates,
  component failures, and regression evidence.
- `morphea promotion-apply-review` validates edited promotion review decisions,
  rejects pending records, writes applied JSON/Markdown summaries, and can
  persist `review_decision_applied` into a run manifest.
- `morphea harvest --require-applied-review` gates pseudo-label harvesting on
  applied promotion review decisions, so only `accepted` and `corrected`
  applied decisions become candidates while missing, invalid, rejected, and
  deferred decisions remain visible in `rejected_runs`.
- `morphea harvest-curated --require-applied-review` preserves existing applied
  review decisions across fresh curated reruns, restores them into regenerated
  manifests and curated JSON reports, and harvests only accepted/corrected
  applied decisions.
- `morphea review --accept-applied-reviews` maps harvested applied promotion
  reviews into the existing review/apply-review flow, accepting
  accepted/corrected decisions, rejecting rejected/deferred decisions, and
  preserving issue tags for reviewed-label artifacts.
- `morphea merge-labels` preserves `review` and `review_decision_applied`
  provenance in accepted pseudo-label manifests and dataset samples while
  keeping rejected/deferred review items out of trainable datasets.
- `morphea self-learn` separates retraining from acceptance: model acceptance
  now requires an accepted training comparison gate and, when configured,
  passing curated validation, with reviewed-label issue counts and
  applied-review decision counts in the cycle summary.
- training comparisons expose per-label validation accuracy deltas, and those
  label-level deltas feed the best/worst gate summary so primitive-family
  regressions can block acceptance.
- self-learning cycle summaries expose normalized suite-family validation
  across primitive label deltas, curated real-image family summaries, and
  optional Lucide family summaries; configured Lucide validation blocks
  acceptance on failure.
- `morphea self-learn --suite-family-baseline baseline.json` compares current
  suite-family validation with a fixed baseline and blocks acceptance only for
  newly introduced bad family outcomes.
- `morphea self-learn --suite-family-baseline-output next-baseline.json` writes
  accepted suite-family validation as a reusable baseline artifact and skips
  writes for rejected cycles.
- suite-family baseline snapshots require reviewer, reason, and changelog
  evidence before writing, so accepted baseline refreshes produce a review
  record and JSONL changelog entry.
- existing suite-family baseline output files are protected unless
  `--suite-family-baseline` points to the same path, preventing accidental
  overwrites of checked-in baseline artifacts.
- metrics surfaced in reports, eval summaries, and sweep summaries
- diagnostic stage counts surfaced in reports, eval summaries, and sweep
  summaries for cross-run failure attribution.
- deterministic manifest preview renderer for current primitive types
- `morphea report` can render Markdown or HTML from an existing manifest
- sweep summaries include `semantic_rank` and a top-level `ranking` list using
  semantic-first score ordering before raster error.
- sweep run configs can pass `cutout_export` through to run-directory SVG
  export, so overlay and negative-mask exports can be compared in experiments.
- optional Markdown comparison reports for config sweeps

## M5: Synthetic Dataset Generator

Status: implemented for the current synthetic-data baseline.

Purpose: create reliable labels for training and evaluation.

Scope:

- Flat-color only at first.
- No noise, blur, gradients, or photoreal texture in the first generator.
- Include overlaid shapes and cut-out-like white strokes.

Deliverables:

- Synthetic scene generator for:
  - circles, rings, dots
  - lines, arcs, curved strokes
  - rects, rounded rects
  - quads, trapezoids, parallelograms
  - grid/tile structures
  - simple logo-like compositions
- Ground-truth scene JSON.
- Rasterized PNG fixtures.
- Train/validation/test splits.
- Difficulty tiers.

Acceptance criteria:

- Generator can create thousands of labeled flat-color examples.
- The deterministic pipeline can be benchmarked against known ground truth.
- Failures are reproducible from seed/config.

Implemented so far:

- deterministic `morphea generate`
- labeled PNG + JSON manifest pairs
- `dataset.json` index
- `dataset.json` records aggregate and per-sample anchor-kind counts so
  generated training corpora can be audited without reopening every manifest
- deterministic `train` / `val` / `test` split folders
- core primitive ground truth for circles, point dots, circle strokes, line
  strokes, curved strokes, arc strokes, rects, rounded rects, quads, and
  perspective tile grids
- synthetic quad ground truth includes numeric subtype markers for trapezoids
  and parallelograms while preserving `quad` as the editable primitive kind
- cut-out-like white overlay strokes with editable stroke metadata
- preview/SVG coverage for generated `arc`, `rect`, and `rounded_rect`
  manifests
- `basic` and `dense` difficulty tiers; `dense` adds labeled parallel stroke
  groups while preserving deterministic seed behavior
- `logo` difficulty tier adds simple logo-like compositions with a ring mark,
  accent dot, diagonal stroke, and rounded wordmark bar
- `grid` difficulty tier adds a larger labeled perspective tile family with
  row/column metadata for table-like quad-grid training cases

## M6: Local MLX Segmentation Layer

Status: implemented for the current local-segmentation baseline.

Purpose: add local AI as a proposal layer, not as the final source of truth.

Deliverables:

- MLX environment setup via `uv`.
- MLX SAM integration behind a segmenter interface.
- Classical segmenter remains available as a baseline.
- Segment proposal manifest:
  - mask id
  - confidence
  - source model
  - bounding box
  - downstream accepted/rejected status

Acceptance criteria:

- MLX SAM can propose regions locally for selected test images.
- Pipeline can run with or without MLX and compare outcomes.
- AI proposals never bypass geometry scoring and editability metrics.

Implemented so far:

- `Segmenter` protocol
- `SegmentProposal` metadata schema
- `FlatColorSegmenter` baseline
- `MlxSamSegmenter` adapter placeholder with explicit not-configured error
- manifest-ready proposal serialization
- `morphea segment input.png -o proposals.json` writes segment proposal manifests
  from the flat-color baseline
- segment proposal manifests include backend availability/status metadata so
  flat-color and future MLX runs can be compared explicitly.
- flat-color segment proposals split connected components by default and can
  mark oversized components as `deferred` via `max_component_area`
- segment proposals include `downstream_status` and `rejection_reason` so
  geometry/review stages can distinguish pending proposals from rejected ones.
- pending flat-color segment proposals include primitive `anchor_kind`,
  `anchor_metrics`, and `anchor_parameter_count` summaries from the geometry
  scorer, while deferred oversized proposals remain rejected without pretending
  to be accepted anchors.
- segment proposal manifests include aggregate proposal status, downstream
  status, anchor-kind, and reserved-anchor counts for quick scan/review.
- segment proposal manifests include `proposal_tile_grid` groups for regular
  2D arrangements of reserved `rect`/`quad` proposals, including row/column
  counts, occupancy, spacing errors, and proposal ids in grid order.
- `morphea segment --markdown proposals.md` renders a scan-friendly proposal
  report with backend status, aggregate counts, anchor kinds, and reservation
  reasons.
- optional segment geometry gating can turn pending proposals into
  `accepted` or `rejected` downstream decisions using primitive anchor quality
  error and reservation requirements.
- segment proposal manifests record `anchor_quality_error` and
  `downstream_decision_reason` so later review/training stages can explain why
  a proposal passed or failed the geometry gate.
- `morphea compare-segments before.json after.json -o comparison.json` compares
  segment proposal manifests from different configs or segmenter backends,
  including summary-count deltas, config differences, added/removed proposals,
  changed downstream/anchor decisions, and added/removed/changed proposal
  groups such as `proposal_tile_grid`.
- segment configs accept future MLX runtime knobs for model path, score
  threshold, mask count, and runtime timeout while preserving the explicit
  not-configured failure path
- MLX SAM status reporting distinguishes missing MLX package, missing model
  configuration, missing model file, and adapter-pending states without
  allowing AI proposals to bypass the geometry pipeline.
- MLX SAM status includes per-capability diagnostics for the JSON proposal
  adapter and the optional live SAM model adapter.
- `MlxSamSegmenter` can consume local JSON proposal payloads through the same
  segment proposal schema, score threshold, mask limit, and downstream
  geometry gate; this gives M6 an operational adapter contract before live SAM
  weights are wired.
- JSON proposal payloads can carry either rectangular bounds/bboxes or
  mask-row payloads, so local adapter tests can exercise non-rectangular
  region proposals before the live SAM runtime is connected.
- when the optional `mlx-sam` package is available in a compatible Python
  environment and `mlx_model_path` points at a `.safetensors` checkpoint,
  `MlxSamSegmenter` can run bounded grid-point prompts and convert positive
  live SAM masks into the same proposal schema and geometry gate.
- `morphea segment --segmenter mlx_sam` exposes the explicit not-configured path
  until the local MLX/SAM runtime is installed

## M7: Primitive Classifier Training

Status: implemented for the current classifier-training baseline.

Purpose: train the first local model that helps choose semantic primitive type.

Model target:

- Small from-scratch MLX Transformer.
- Input: mask/RGBA crop plus geometric features.
- Output: primitive/stroke class plus confidence.
- No direct geometry-parameter prediction in the first version.

Classes:

- `circle`
- `stroke_circle`
- `ellipse`
- `rect`
- `rounded_rect`
- `stroke_path`
- `stroke_polyline`
- `polygon`
- `quad`
- `arc`
- `star`
- `cubic_path`
- `unknown`

Deliverables:

- Training dataset from M5.
- Training command.
- Evaluation command.
- Confusion matrix.
- Integration into candidate ranking as a confidence prior.

Acceptance criteria:

- Classifier improves candidate selection on synthetic validation data compared
  with heuristic-only ranking.
- Low-confidence predictions degrade safely to deterministic geometry.

Implemented so far:

- feature extraction from generated ground-truth manifests
- trainable centroid primitive-classifier baseline
- `morphea train dataset.json -o model.json`
- `morphea train-mlx dataset.json -o model.json` for the optional MLX
  Transformer classifier path
- train/val/test evaluation sections in model artifact
- confusion matrix output
- `morphea eval-classifier model.json dataset.json -o report.json` for
  standalone evaluation of an existing primitive classifier artifact
- `morphea eval-classifier --markdown report.md` for scan-friendly classifier
  evaluation summaries
- classifier artifacts and evaluation reports include centroid-spread
  `feature_importance`, making it visible when simple geometry and
  scene-group context signals separate primitive classes.
- optional `--classifier-model` prior during `morphea vectorize`
- `classifier_prior_error` metric in candidate manifests
- `morphea train` writes `ranking_evaluation` comparing heuristic-only candidate
  ranking with classifier-prior-assisted ranking on validation/test splits
- `morphea train-mlx --allow-unavailable` writes a deterministic artifact with
  MLX backend status plus centroid fallback weights, so the training pipeline
  remains runnable when MLX is not installed locally
- MLX classifier runtime status distinguishes missing MLX package from an
  available package that trains a serialized normalized feature-head weight
  artifact, while keeping centroid fallback weights usable as the safe ranking
  prior.
- the available MLX training path no longer emits metadata-only hooks; it
  writes optimized feature-head weights, bias, normalization, and loss history
  while marking the full raster-crop Transformer encoder as pending.
- classifier feature extraction includes detected/generated
  `quad_subtype_code` values so trapezoid and parallelogram structure can
  influence candidate ranking without adding new top-level primitive classes
- classifier feature extraction includes anchor `group_context` signals for
  perspective grids, parallel stroke groups, same-color fragment groups, and
  primitive reservations, so reviewed pseudo-labels can carry scene structure
  into centroid and MLX training examples.
- classifier training can extract fixed-size RGBA anchor-crop token sequences
  from synthetic dataset images and manifests.
- `morphea train-mlx --crop-size N` records the raster token size, token shape,
  channel order, and crop-token summary in the MLX training artifact.
- available MLX training artifacts include `raster_token_mixer_v1`, a
  trainable attention-style pooling block over RGBA crop tokens with its own
  normalized weights, bias, and loss history.
- available MLX training artifacts also include `mlx_feature_raster_fusion_v1`,
  a trainable fusion head over geometric primitive features plus raster-token
  attention embeddings. Runtime prediction prefers this learned fusion when
  crop tokens are available and falls back to the older feature/mixer logits
  when it is missing or malformed.
- available MLX training artifacts now include `mlx_token_transformer_v1`, a
  serialized small token encoder that pools RGBA crops into raster tokens,
  combines them with geometric feature tokens, runs scaled dot-product
  self-attention layers, and trains a classifier head on the pooled encoder
  embedding.
- `mlx_token_transformer_v1` now records a learned projection calibration over
  encoder dimensions, so token embeddings are no longer purely deterministic
  before classifier-head training.
- when real MLX autograd is available, `mlx_token_transformer_v1` now trains
  `mlx_token_projection_v1` token-to-hidden projection weights and the token
  classifier head together, records `training_status`, and uses those
  projection weights at runtime.
- runtime classifier loading prefers valid `mlx_token_transformer_v1` logits
  when crop tokens are available, then falls back through feature/raster fusion,
  raster-token mixer, feature head, and centroid fallback.
- `morphea eval-classifier` uses RGBA crop-token examples for direct
  accuracy/confusion when evaluating a valid MLX raster-token mixer artifact.
- `morphea eval-classifier` also uses RGBA crop-token examples for
  candidate-ranking evaluation when a valid MLX raster mixer, fusion head, or
  token-transformer block is present.
- `--classifier-model` can load `mlx_feature_head_v1` artifacts and use their
  serialized weights as the candidate-ranking prior, while malformed or
  unavailable MLX artifacts degrade to centroid fallback weights.
- vectorize candidate ranking now generates component-derived RGBA crop tokens
  for valid `raster_token_mixer_v1` artifacts, allowing runtime priors to fuse
  raster attention and geometric feature logits.
- MLX classifier runtime status reports trainable feature/raster/token
  capabilities and end-to-end token-projection training separately from the
  end-to-end attention-weight training capability.
- available MLX token-transformer artifacts now train
  `mlx_attention_diagonal_v1` per-layer query/key/value/output scales and
  output bias with MLX autograd, serialize them in `attention_parameters`, and
  use them during runtime prediction.

Remaining:

- none for the current primitive-classifier milestone baseline; future quality
  work can replace diagonal attention parameters with richer projection
  matrices if real-image results justify the extra complexity.

## M8: Self-Learning Loop

Status: implemented for the current self-learning baseline.

Purpose: turn the pipeline into an iteration engine.

Deliverables:

- Batch runner over curated real images.
- Quality filters for pseudo-label candidates:
  - high editability score
  - acceptable raster diagnostics
  - stable anchor metrics
  - low fragmentation
- Pseudo-label export.
- Human review hooks:
  - accept/reject anchors
  - mark wrong primitive type
  - mark bad cut-out/stroke behavior
- Retraining loop:
  - synthetic pretraining
  - real pseudo-label fine-tuning
  - validation against fixed real-image suite

Acceptance criteria:

- The system can collect its own high-confidence examples from real images.
- Retraining produces measurable improvement without using external vectorizer
  outputs as labels.

Implemented so far:

- `morphea harvest` pseudo-label collection from run manifests
- run-level warning-diagnostic filter
- anchor-level `classifier_prior_error` filter
- run-level `editability_score` minimum filter
- run-level `fragmentation_penalty` maximum filter
- run-level `raster_l1_error` and `raster_edge_error` maximum filters
- anchor-level aggregate quality filter for unstable simple-shape metrics
- output pseudo-label index with source manifest provenance
- harvested pseudo-labels preserve scene `group_context` for groups that
  contain the accepted anchor, and `morphea merge-labels` carries that context
  into generated pseudo-sample manifests with source group provenance.
- `morphea harvest --markdown harvest.md` writes a scan-friendly pseudo-label
  quality-gate report with accepted labels, filters, and rejected runs
- `morphea harvest-curated suite.json --run-root runs/curated -o pseudo.json`
  runs bounded curated real-image cases and harvests pseudo-labels from the
  generated per-case manifests
- human-editable review queue via `morphea review`
- `morphea review --markdown review.md` writes a scan-friendly queue summary
  while keeping accept/reject decisions in JSON; review and apply-review
  Markdown reports surface harvested group context so reviewers can see when an
  anchor belongs to a grid, parallel stroke group, merge candidate, or
  reservation group.
- accepted/rejected/pending split via `morphea apply-review`
- `morphea apply-review --markdown accepted.md` writes a scan-friendly decision
  summary for accepted, rejected, and pending labels
- review items support `corrected_kind` and structured issue tags for wrong
  primitive type, cut-out, and stroke-behavior feedback
- review queue and apply-review artifacts aggregate `issue_counts` so repeated
  primitive-type, cut-out, and stroke-behavior problems are visible in JSON and
  Markdown summaries.
- accepted reviewed pseudo-labels can be merged into a classifier-compatible
  train split via `morphea merge-labels`
- `morphea compare-training` compares baseline classifier training against
  reviewed pseudo-label augmentation on a fixed validation/test dataset
- comparison reports include a scan-friendly augmentation verdict with
  best/worst accuracy deltas and train-example delta, so regressions are easier
  to spot before retraining is accepted.
- comparison reports include feature-importance spread deltas so reviewed
  pseudo-labels can be audited for which geometry or group-context signals they
  strengthen.
- `morphea compare-training --markdown comparison.md` writes a scan-friendly
  retraining comparison table derived from the JSON report.
- `morphea training-gate comparison.json -o gate.json` turns a retraining
  comparison into an accept/manual-review/reject decision using explicit
  regression tolerances
- `morphea self-learn base/dataset.json --reviewed-labels reviewed.json -o cycle`
  runs merge-labels, compare-training, training-gate, and accepted-gate
  retraining as one repeatable reviewed-label cycle
- `morphea self-learn --curated-suite suite.json` validates an accepted
  retrained model against the fixed curated real-image suite by passing the
  model as `classifier_model`; skipped gates do not pretend validation ran
- `morphea self-learn --lucide-suite suite.json` validates an accepted
  retrained model against the curated Lucide benchmark with the same
  `classifier_model` override and reports the result beside primitive and
  real-image families
- `morphea self-learn --suite-family-baseline baseline.json` distinguishes
  newly introduced family regressions from known baseline debt before accepting
  the cycle
- `morphea self-learn --suite-family-baseline-output next-baseline.json`
  persists accepted `suite_family_validation` snapshots for the next baseline
  comparison
- `--suite-family-baseline-reviewer`, `--suite-family-baseline-reason`, and
  `--suite-family-baseline-changelog` make baseline refreshes auditable and
  prevent silent baseline replacement
- existing `--suite-family-baseline-output` paths require a matching
  `--suite-family-baseline` path before they can be overwritten
- `morphea retrain` writes an augmented primitive classifier model from base plus
  reviewed pseudo-label train examples, including source-dataset provenance and
  validation/test evaluation metrics
- `morphea retrain --config retrain.json` supports repeatable self-learning
  retraining runs and can optionally write the comparison report next to the
  model
- `morphea retrain --backend mlx` writes an augmented MLX classifier artifact
  from base plus reviewed pseudo-label train examples, using the MLX
  train/fallback path and recording the generated augmented dataset index.
- MLX retraining can consume reviewed pseudo-label manifests that do not carry
  source images: feature training includes those pseudo labels, while
  raster-token crops are trained from image-backed samples.
- reviewed-label MLX retraining now uses the same end-to-end token projection
  and attention-parameter training path as `morphea train-mlx` for image-backed
  examples.

Remaining:

- none for the current reviewed-label self-learning baseline; additional real
  pseudo-label data should drive future quality thresholds.

## M9: Differentiable and Local Refinement

Status: implemented for the built-in local and soft-raster backends.

Purpose: improve geometry after a good semantic initialization exists.

Deliverables:

- Refinement interface with strict time/iteration limits.
- Robust renderer for deterministic metrics.
- Optional differentiable backend:
  - DiffVG if practical
  - alternative renderer if DiffVG is too brittle on Apple Silicon
- Refinement only changes parameters of accepted semantic shapes unless a
  config explicitly allows structure changes.

Acceptance criteria:

- Refinement improves raster diagnostics without destroying editability.
- A true circle does not become a noisy path just to gain tiny pixel fidelity.

Implemented so far:

- `RefinementConfig`
- `morphea refine manifest.json -o refined.json`
- `local_metric` backend
- structure-preserving manifest output
- refinement metadata and per-anchor metrics
- top-level refinement `structure_audit` records source/refined anchor counts,
  preserved primitive kinds, geometry-change count, and editability preservation.
- optional `--source-image` refinement input
- first structure-preserving local optimizer for circle radius adjustment using
  rendered raster L1 error
- weighted refinement objective using both raster L1 and edge-error diagnostics
  via `--raster-l1-weight` and `--raster-edge-weight`
- structure-preserving local optimizer for quad-like primitives (`rect`,
  `rounded_rect`, `quad`) using bounded translation and scale parameter steps
- structure-preserving local optimizer for stroke-like primitives
  (`stroke_polyline`, `stroke_path`, `arc`) using bounded centerline
  translation and stroke-width steps
- recognized optional differentiable backend names (`differentiable`, `diffvg`)
  behind the same `morphea refine --backend ...` interface, with an explicit
  not-installed/not-configured failure path until a renderer is wired
- `morphea refine --backend differentiable` now runs a built-in soft-raster
  gradient backend for structure-preserving circle-radius refinement and
  quad-like (`rect`, `rounded_rect`, `quad`) plus stroke-like
  (`stroke_polyline`, `stroke_path`, `arc`) transform refinement, including
  renderer metadata and objective deltas.
- `morphea refine --backend diffvg` remains the optional external adapter path
  with explicit not-installed/adapter-pending status until DiffVG is wired.
- refinement backend status reports distinguish active local metric refinement,
  missing optional renderer packages, and adapter-pending optional renderer
  states without allowing structure-changing refinement to run implicitly.
- refinement config validates iteration, timeout, and raster-weight limits, and
  optimizer metadata records elapsed seconds, timeout state, and stopped reason
- `morphea refinement-gate refined.json -o gate.json` turns structure audit and
  optimizer objective metrics into an accept/manual-review/reject decision so
  tiny pixel gains cannot silently break editability

Remaining:

- optionally wire DiffVG when it is practical in the target local environment.

## M10: Curated Real-Image Suite

Status: implemented for the current curated baseline.

Purpose: keep the system honest against actual target images.

Deliverables:

- Local fixture directory policy for real images.
- Per-image notes:
  - observed structures
  - expected anchors
  - known current failures
  - milestone that should address each failure
- Fixed regression runs.

Initial candidate:

- `/Users/sebastian/Desktop/terminaro-tweaked.png`

Acceptance criteria:

- Each curated image has a documented expected-shape checklist.
- CLI can produce SVG, manifest, and report for each image within runtime
  limits.

Implemented so far:

- `docs/real-images/suite.json` for local real-image metadata without checking
  large binaries into git.
- `morphea curated-check suite.json -o report.json` for suite validation.
- `morphea curated-check --config curated-check.json` for repeatable real-image
  suite validation inputs.
- optional `--run` mode using each case's bounded `recommended_config`.
- per-case `output.svg`, `debug.svg`, `manifest.json`, `config.json`,
  `report.md`, `report.html`, and `preview.png` artifacts via `--output-dir`.
- curated artifacts are written through the same run writer as vectorize runs,
  including input copies and raster-fidelity metrics.
- expectation checks for anchor kinds and scene group kinds.
- metric expectation checks for curated cases, including editability,
  simple-shape ratio, and fragmentation envelopes.
- deterministic `morphea curated-check --snapshot snapshot.json` regression
  summaries for important commits/configurations.
- `morphea curated-check --markdown report.md` writes scan-friendly real-image
  suite reports with case status, failed expectations, key metrics, and
  artifact directories.
- second documented curated case:
  `chatgpt-image-2026-06-11`, covering the opaque white-background version of
  the Greek-figures/table illustration.
- third documented curated case:
  `ui-radio-acceptance-screenshot`, adding a text-heavy UI screenshot family
  with a small radio-circle control and bounded text-fragment expectations.
- checked-in deterministic baseline snapshot at
  `docs/real-images/baselines/current-curated-snapshot.json`.
- the UI radio-control case now exercises neutral composite ring recovery so
  thin anti-aliased controls remain represented by simple circle primitives.

Remaining:

- add more families as new representative local images become available.

## M11: Productized Research CLI

Status: implemented for the current research baseline.

Purpose: make the research loop pleasant enough to use repeatedly.

Deliverables:

- Commands:
  - `morphea generate`
  - `morphea train`
  - `morphea vectorize`
  - `morphea eval`
  - `morphea report`
  - `morphea sweep`
- Config files:
  - preprocessing
  - segmenters
  - anchor thresholds
  - scoring weights
  - training
- Stable output schema.
- Versioned experiment metadata.

Acceptance criteria:

- A user can run a full experiment without editing Python code.
- Results from different commits/configs can be compared.

Implemented so far:

- `morphea generate`
- `morphea train`
- `morphea train-mlx`
- `morphea eval-classifier`
- `morphea vectorize`
- `morphea profile`
- `morphea eval`
- `morphea report`
- `morphea segment`
- `morphea sweep`
- `morphea merge-labels`
- `morphea harvest-curated`
- `morphea compare-training`
- `morphea training-gate`
- `morphea self-learn`
- `morphea retrain`
- `morphea refinement-gate`
- `morphea status`
- `morphea vectorize --config config.json` for repeatable input/output,
  artifact, and runtime knob files
- `morphea generate --config generate.json` for repeatable synthetic corpus
  generation
- `morphea train --config train.json` for repeatable classifier training inputs
- `morphea eval-classifier --config eval-classifier.json` for repeatable
  classifier evaluation reports
- `morphea eval --config eval.json` for repeatable run-directory summaries
- `morphea profile --config profile.json` for repeatable bounded runtime probes
- `morphea profile-curated --config profile-curated.json` for repeatable
  curated-family runtime profiling and Markdown summaries
- `morphea report --command-config report.json` for repeatable standalone report
  rendering from existing manifests
- `morphea harvest --config harvest.json` for repeatable pseudo-label quality
  gates
- `morphea harvest --markdown harvest.md` for scan-friendly pseudo-label quality
  reports
- `morphea harvest-curated --config harvest-curated.json` for repeatable
  curated real-image pseudo-label collection
- `morphea review --config review.json` and `morphea apply-review --config
  apply-review.json` for repeatable human-review queue processing
- `morphea review --markdown review.md` for scan-friendly review queue summaries
- `morphea apply-review --markdown accepted.md` for scan-friendly review decision
  summaries
- `morphea merge-labels --config merge-labels.json` for repeatable reviewed-label
  dataset export
- `morphea compare-training --config compare.json` for repeatable retraining
  comparisons
- `morphea compare-training --markdown compare.md` for scan-friendly retraining
  comparisons
- `morphea training-gate --config training-gate.json` for repeatable retraining
  acceptance decisions
- `morphea self-learn --config self-learn.json` for repeatable reviewed-label
  self-learning cycles, including optional curated-suite validation
- `morphea retrain --config retrain.json` for repeatable augmented model output
- `morphea refine --config refine.json` for repeatable bounded refinement runs
- `morphea refinement-gate --config refinement-gate.json` for repeatable
  structure-preserving refinement acceptance decisions
- `morphea status -o status.json --markdown status.md` for a single
  machine-readable report of segmenter, classifier, and refinement backend
  availability/blockers
- `morphea status --config status.json` for repeatable runtime/backend
  availability checks
- `morphea status` reports blocked backend capabilities such as the live MLX SAM
  adapter and end-to-end MLX attention training separately from installed
  package status
- `morphea curated-check --config curated-check.json` for repeatable curated
  real-image suite validation
- `morphea segment --config segment.json` for repeatable input/output,
  report, and segment proposal runs
- `morphea segment --markdown proposals.md` for scan-friendly segment proposal
  reports
- `morphea compare-segments before.json after.json -o comparison.json` for
  comparing segment proposal outputs across configs or backends
- `morphea compare-segments --config compare-segments.json` for repeatable
  segment proposal comparisons
- segment configs include component splitting and `max_component_area`
- segment configs include future MLX model/runtime knobs without requiring the
  MLX backend to be installed
- vectorize scoring weights for raster error, quality error, complexity, and
  simple-shape bonus
- vectorize anchor threshold config for circle/ring, stroke, quad, rect, and
  rounded-rect candidate gates
- `morphea compare-snapshots before.json after.json` for comparing saved
  summaries from different commits/configurations
- `morphea compare-snapshots --config compare-snapshots.json` for repeatable
  saved-summary comparisons
- `morphea compare-git-snapshots before_ref after_ref --path snapshot.json` for
  comparing the same checked-in snapshot file across git refs without changing
  the working tree
- `morphea compare-git-snapshots --config compare-git-snapshots.json` for
  repeatable git-ref snapshot comparisons
- `morphea snapshot-git-ref ref --suite suite.json -o snapshot.json` for
  generating curated snapshots from a detached temporary worktree without
  checking out the current working tree
- `morphea snapshot-git-ref --config snapshot-git-ref.json` for repeatable
  isolated git snapshot generation
- `morphea sweep` configs can carry output roots and Markdown report paths for
  repeatable config comparisons
- schema-v1 sweep configs
- schema-v1 scene manifests
- `sweep-summary.json` experiment metadata

Remaining:

- add new schema entries when future milestones introduce new commands or real
  MLX model execution.

## M12: Primitive Fidelity Harness

Status: implemented for the current fixed-fixture baseline.

Purpose: make the simplest shapes the primary quality gate before homepage or
curated-image polish.

Implemented so far:

- `morphea primitive-check` generates deterministic primitive raster fixtures,
  vectorizes them, renders the recognized scene back to pixels, and writes a
  machine-readable report.
- Optional per-case artifacts include `input.png`, `output.svg`, `debug.svg`,
  `manifest.json`, and `preview.png`.
- The fixed fixture set covers filled square, filled rectangle, filled circle,
  horizontal/vertical/diagonal strokes, outlined ring, rounded rectangle, and a
  simple quad.
- The report records pass/fail status, selected primitive kind, raster L1/edge
  errors, bounding-box IoU, geometry bounds, and concrete failure reasons.

Acceptance evidence:

- `PYTHONPATH=src python3 -m morphea.cli primitive-check -o /tmp/primitive.json`
- `PYTHONPATH=src python3 -m unittest tests.test_primitive_quality`

Remaining:

- add randomized variants only after the fixed basic cases remain stable.

## M13: Ground-Truth Primitive Specs

Status: implemented for the current hand-authored fixture baseline.

Purpose: keep primitive expectations explicit and separate from broad synthetic
training data.

Implemented so far:

- each built-in primitive fixture records canvas size, background, expected
  primitive kind, expected color, expected geometry, coordinate tolerance, raster
  thresholds, and minimum bounding-box IoU.
- fixtures are generated from hand-authored specs at runtime rather than
  checked in as binary assets.
- square/rectangle/quad contracts assert four-corner geometry; circle/ring
  contracts assert center/radius; stroke contracts assert two-point centerlines
  and width.

Remaining:

- move specs to external JSON only if users need to edit the fixture set without
  touching Python.

## M14: Geometry Contract Tests

Status: implemented for the current primitive contract baseline.

Purpose: fail on wrong semantic geometry even when aggregate scene metrics look
acceptable.

Implemented so far:

- primitive quality checks fail wrong primitive kinds, unexpected `cubic_path`
  fallbacks, loose coordinates, poor bounding-box IoU, out-of-canvas bounds, and
  visual round-trip regressions.
- regression tests cover square, circle, stroke, ring, and CLI report behavior.
- the ring/stroke regressions that produced oversized arc or curved-stroke
  candidates are now covered by focused detector tests.

Remaining:

- add contract cases for nested/cut-out primitives after the single-primitive
  set stays stable.

## M15: Visual Round-Trip Gates

Status: implemented for the current manifest-rendered preview baseline.

Purpose: compare source raster fixtures against rendered recognized scenes, not
just primitive counts.

Implemented so far:

- primitive-check records `raster_l1_error`, `raster_edge_error`,
  `raster_alpha_error`, `raster_size_match`, and bounding-box IoU per case.
- strict thresholds are used for filled square, rectangle, and quad; slightly
  looser thresholds are used for circles, rings, rounded rectangles, and
  diagonal strokes where rasterization differs by edge pixels.
- per-case artifacts make input/output inspection possible without rerunning
  the harness.

Remaining:

- add an SVG-raster backend only if manifest-rendered previews diverge from the
  browser/editor SVG rendering path.

## M16: Detector Tightening Loop

Status: started and implemented for the first primitive failures.

Purpose: use failing primitive cases to tighten recognition before broader real
image tuning.

Implemented so far:

- straight thick strokes no longer receive artificial control points from edge
  pixels; horizontal and vertical Pillow-style strokes remain two-point
  `stroke_polyline` anchors.
- arc candidates with width samples or visual stroke bounds far outside their
  source component are rejected, preventing outlined rings from becoming giant
  arc strokes.
- arc scoring avoids treating the intended bend of a three-point arc as line
  jitter while still preserving width-variance pressure.

Remaining:

- add rejection diagnostics if future failures need inspectable candidate-level
  reject reasons.
- keep each detector change paired with a primitive contract or focused
  detector regression test.

## M17: Honest Basic Gallery

Status: pending.

Purpose: publish only examples that are backed by passing primitive contracts.

Planned behavior:

- generate a small static gallery from `primitive-check` artifacts after the
  basic gate is stable.
- show bitmap input, rendered SVG preview, primitive contract summary, selected
  kind, coordinates, node count, and raster errors.
- keep complex illustrations out of the homepage until their own semantic and
  visual contracts are strong enough.

## Commit Discipline

Continue using small Conventional Commits:

- `docs: ...` for plans, ADRs, and research notes
- `feat: ...` for new pipeline capability
- `test: ...` for test-only additions
- `fix: ...` for behavior corrections
- `perf: ...` for runtime improvements
- `chore: ...` for tooling or cleanup

Each milestone should land in multiple small commits when it naturally splits
into docs, core logic, CLI, tests, and reporting.
