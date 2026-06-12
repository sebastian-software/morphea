# Curve Milestone Plan

This document expands the implementation plan beyond the first base-form
prototype. The long-term goal is a local, self-improving, semantic-first
raster-to-SVG research system.

## North Star

Curve should produce SVGs that feel intentionally constructed by a human:
simple shapes stay simple, strokes stay editable, cut-out lines stay clean,
and repeated structures become coherent groups. Visual similarity matters, but
editable semantic structure is the primary quality target.

The system should evolve from deterministic geometry first, then add local AI,
then add training and self-learning loops.

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
- CLI path: `curve vectorize input.png -o output.svg`.

Acceptance evidence:

- `PYTHONPATH=src python3 -m unittest discover -s tests`
- Current suite covers masks, PNG fixtures, SVG export, CLI, manifests,
  cut-outs, rings, strokes, quads, and grid grouping.

## M1: Real-Image Preprocessing and Runtime Control

Status: in progress.

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
- `curve profile input.png -o profile.json` records bounded vectorize timings,
  anchor counts, diagnostics, diagnostic stage counts, and min/mean/max elapsed
  summaries for repeated runs.
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

Remaining:

- continue profile-guided hot-loop work as larger curated image families expose
  new bottlenecks.

## M2: Primitive Anchor Detection V2

Status: started.

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

Status: started.

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
- `curve vectorize --cutout-export negative_mask` writes editable cut-out
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
- `curve vectorize --debug-svg` writes an inspectable SVG with anchor ids,
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

Status: started.

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
- `curve eval` JSON/Markdown summaries over run directories
- scene-level `metrics` in manifests
- `editability_score`
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
- metrics surfaced in reports, eval summaries, and sweep summaries
- diagnostic stage counts surfaced in reports, eval summaries, and sweep
  summaries for cross-run failure attribution.
- deterministic manifest preview renderer for current primitive types
- `curve report` can render Markdown or HTML from an existing manifest
- sweep summaries include `semantic_rank` and a top-level `ranking` list using
  semantic-first score ordering before raster error.
- sweep run configs can pass `cutout_export` through to run-directory SVG
  export, so overlay and negative-mask exports can be compared in experiments.
- optional Markdown comparison reports for config sweeps

## M5: Synthetic Dataset Generator

Status: started.

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

- deterministic `curve generate`
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

Status: started.

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
- `curve segment input.png -o proposals.json` writes segment proposal manifests
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
- `curve segment --markdown proposals.md` renders a scan-friendly proposal
  report with backend status, aggregate counts, anchor kinds, and reservation
  reasons.
- optional segment geometry gating can turn pending proposals into
  `accepted` or `rejected` downstream decisions using primitive anchor quality
  error and reservation requirements.
- segment proposal manifests record `anchor_quality_error` and
  `downstream_decision_reason` so later review/training stages can explain why
  a proposal passed or failed the geometry gate.
- `curve compare-segments before.json after.json -o comparison.json` compares
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
- `curve segment --segmenter mlx_sam` exposes the explicit not-configured path
  until the local MLX/SAM runtime is installed

## M7: Primitive Classifier Training

Status: started.

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
- `curve train dataset.json -o model.json`
- `curve train-mlx dataset.json -o model.json` for the optional MLX
  Transformer classifier path
- train/val/test evaluation sections in model artifact
- confusion matrix output
- `curve eval-classifier model.json dataset.json -o report.json` for
  standalone evaluation of an existing primitive classifier artifact
- `curve eval-classifier --markdown report.md` for scan-friendly classifier
  evaluation summaries
- classifier artifacts and evaluation reports include centroid-spread
  `feature_importance`, making it visible when simple geometry and
  scene-group context signals separate primitive classes.
- optional `--classifier-model` prior during `curve vectorize`
- `classifier_prior_error` metric in candidate manifests
- `curve train` writes `ranking_evaluation` comparing heuristic-only candidate
  ranking with classifier-prior-assisted ranking on validation/test splits
- `curve train-mlx --allow-unavailable` writes a deterministic artifact with
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
- `curve train-mlx --crop-size N` records the raster token size, token shape,
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
- runtime classifier loading prefers valid `mlx_token_transformer_v1` logits
  when crop tokens are available, then falls back through feature/raster fusion,
  raster-token mixer, feature head, and centroid fallback.
- `curve eval-classifier` uses RGBA crop-token examples for direct
  accuracy/confusion when evaluating a valid MLX raster-token mixer artifact.
- `--classifier-model` can load `mlx_feature_head_v1` artifacts and use their
  serialized weights as the candidate-ranking prior, while malformed or
  unavailable MLX artifacts degrade to centroid fallback weights.
- vectorize candidate ranking now generates component-derived RGBA crop tokens
  for valid `raster_token_mixer_v1` artifacts, allowing runtime priors to fuse
  raster attention and geometric feature logits.

Remaining:

- replace the current learned projection calibration with full end-to-end MLX
  attention/projection backpropagation once local MLX execution is available in
  the target environment.

## M8: Self-Learning Loop

Status: started.

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

- `curve harvest` pseudo-label collection from run manifests
- run-level warning-diagnostic filter
- anchor-level `classifier_prior_error` filter
- run-level `editability_score` minimum filter
- run-level `fragmentation_penalty` maximum filter
- run-level `raster_l1_error` and `raster_edge_error` maximum filters
- anchor-level aggregate quality filter for unstable simple-shape metrics
- output pseudo-label index with source manifest provenance
- harvested pseudo-labels preserve scene `group_context` for groups that
  contain the accepted anchor, and `curve merge-labels` carries that context
  into generated pseudo-sample manifests with source group provenance.
- `curve harvest --markdown harvest.md` writes a scan-friendly pseudo-label
  quality-gate report with accepted labels, filters, and rejected runs
- `curve harvest-curated suite.json --run-root runs/curated -o pseudo.json`
  runs bounded curated real-image cases and harvests pseudo-labels from the
  generated per-case manifests
- human-editable review queue via `curve review`
- `curve review --markdown review.md` writes a scan-friendly queue summary
  while keeping accept/reject decisions in JSON; review and apply-review
  Markdown reports surface harvested group context so reviewers can see when an
  anchor belongs to a grid, parallel stroke group, merge candidate, or
  reservation group.
- accepted/rejected/pending split via `curve apply-review`
- `curve apply-review --markdown accepted.md` writes a scan-friendly decision
  summary for accepted, rejected, and pending labels
- review items support `corrected_kind` and structured issue tags for wrong
  primitive type, cut-out, and stroke-behavior feedback
- review queue and apply-review artifacts aggregate `issue_counts` so repeated
  primitive-type, cut-out, and stroke-behavior problems are visible in JSON and
  Markdown summaries.
- accepted reviewed pseudo-labels can be merged into a classifier-compatible
  train split via `curve merge-labels`
- `curve compare-training` compares baseline classifier training against
  reviewed pseudo-label augmentation on a fixed validation/test dataset
- comparison reports include a scan-friendly augmentation verdict with
  best/worst accuracy deltas and train-example delta, so regressions are easier
  to spot before retraining is accepted.
- comparison reports include feature-importance spread deltas so reviewed
  pseudo-labels can be audited for which geometry or group-context signals they
  strengthen.
- `curve compare-training --markdown comparison.md` writes a scan-friendly
  retraining comparison table derived from the JSON report.
- `curve training-gate comparison.json -o gate.json` turns a retraining
  comparison into an accept/manual-review/reject decision using explicit
  regression tolerances
- `curve self-learn base/dataset.json --reviewed-labels reviewed.json -o cycle`
  runs merge-labels, compare-training, training-gate, and accepted-gate
  retraining as one repeatable reviewed-label cycle
- `curve self-learn --curated-suite suite.json` validates an accepted
  retrained model against the fixed curated real-image suite by passing the
  model as `classifier_model`; skipped gates do not pretend validation ran
- `curve retrain` writes an augmented primitive classifier model from base plus
  reviewed pseudo-label train examples, including source-dataset provenance and
  validation/test evaluation metrics
- `curve retrain --config retrain.json` supports repeatable self-learning
  retraining runs and can optionally write the comparison report next to the
  model
- `curve retrain --backend mlx` writes an augmented MLX classifier artifact
  from base plus reviewed pseudo-label train examples, using the MLX
  train/fallback path and recording the generated augmented dataset index.
- MLX retraining can consume reviewed pseudo-label manifests that do not carry
  source images: feature training includes those pseudo labels, while
  raster-token crops are trained from image-backed samples.

Remaining:

- add true end-to-end MLX fine-tuning of attention/projection weights once the
  local MLX runtime path moves beyond serialized encoder-head training and
  projection calibration.

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
- `curve refine manifest.json -o refined.json`
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
  behind the same `curve refine --backend ...` interface, with an explicit
  not-installed/not-configured failure path until a renderer is wired
- `curve refine --backend differentiable` now runs a built-in soft-raster
  gradient backend for structure-preserving circle-radius refinement and
  quad-like (`rect`, `rounded_rect`, `quad`) plus stroke-like
  (`stroke_polyline`, `stroke_path`, `arc`) transform refinement, including
  renderer metadata and objective deltas.
- `curve refine --backend diffvg` remains the optional external adapter path
  with explicit not-installed/adapter-pending status until DiffVG is wired.
- refinement backend status reports distinguish active local metric refinement,
  missing optional renderer packages, and adapter-pending optional renderer
  states without allowing structure-changing refinement to run implicitly.
- refinement config validates iteration, timeout, and raster-weight limits, and
  optimizer metadata records elapsed seconds, timeout state, and stopped reason
- `curve refinement-gate refined.json -o gate.json` turns structure audit and
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
- `curve curated-check suite.json -o report.json` for suite validation.
- `curve curated-check --config curated-check.json` for repeatable real-image
  suite validation inputs.
- optional `--run` mode using each case's bounded `recommended_config`.
- per-case `output.svg`, `debug.svg`, `manifest.json`, `config.json`,
  `report.md`, `report.html`, and `preview.png` artifacts via `--output-dir`.
- curated artifacts are written through the same run writer as vectorize runs,
  including input copies and raster-fidelity metrics.
- expectation checks for anchor kinds and scene group kinds.
- metric expectation checks for curated cases, including editability,
  simple-shape ratio, and fragmentation envelopes.
- deterministic `curve curated-check --snapshot snapshot.json` regression
  summaries for important commits/configurations.
- `curve curated-check --markdown report.md` writes scan-friendly real-image
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
  - `curve generate`
  - `curve train`
  - `curve vectorize`
  - `curve eval`
  - `curve report`
  - `curve sweep`
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

- `curve generate`
- `curve train`
- `curve train-mlx`
- `curve eval-classifier`
- `curve vectorize`
- `curve profile`
- `curve eval`
- `curve report`
- `curve segment`
- `curve sweep`
- `curve merge-labels`
- `curve harvest-curated`
- `curve compare-training`
- `curve training-gate`
- `curve self-learn`
- `curve retrain`
- `curve refinement-gate`
- `curve status`
- `curve vectorize --config config.json` for repeatable runtime knob files
- `curve generate --config generate.json` for repeatable synthetic corpus
  generation
- `curve train --config train.json` for repeatable classifier training inputs
- `curve eval-classifier --config eval-classifier.json` for repeatable
  classifier evaluation reports
- `curve eval --config eval.json` for repeatable run-directory summaries
- `curve profile --config profile.json` for repeatable bounded runtime probes
- `curve report --command-config report.json` for repeatable standalone report
  rendering from existing manifests
- `curve harvest --config harvest.json` for repeatable pseudo-label quality
  gates
- `curve harvest --markdown harvest.md` for scan-friendly pseudo-label quality
  reports
- `curve harvest-curated --config harvest-curated.json` for repeatable
  curated real-image pseudo-label collection
- `curve review --config review.json` and `curve apply-review --config
  apply-review.json` for repeatable human-review queue processing
- `curve review --markdown review.md` for scan-friendly review queue summaries
- `curve apply-review --markdown accepted.md` for scan-friendly review decision
  summaries
- `curve merge-labels --config merge-labels.json` for repeatable reviewed-label
  dataset export
- `curve compare-training --config compare.json` for repeatable retraining
  comparisons
- `curve compare-training --markdown compare.md` for scan-friendly retraining
  comparisons
- `curve training-gate --config training-gate.json` for repeatable retraining
  acceptance decisions
- `curve self-learn --config self-learn.json` for repeatable reviewed-label
  self-learning cycles, including optional curated-suite validation
- `curve retrain --config retrain.json` for repeatable augmented model output
- `curve refine --config refine.json` for repeatable bounded refinement runs
- `curve refinement-gate --config refinement-gate.json` for repeatable
  structure-preserving refinement acceptance decisions
- `curve status -o status.json --markdown status.md` for a single
  machine-readable report of segmenter, classifier, and refinement backend
  availability/blockers
- `curve status --config status.json` for repeatable runtime/backend
  availability checks
- `curve curated-check --config curated-check.json` for repeatable curated
  real-image suite validation
- `curve segment --config segment.json` for repeatable segment proposal runs
- `curve segment --markdown proposals.md` for scan-friendly segment proposal
  reports
- `curve compare-segments before.json after.json -o comparison.json` for
  comparing segment proposal outputs across configs or backends
- segment configs include component splitting and `max_component_area`
- segment configs include future MLX model/runtime knobs without requiring the
  MLX backend to be installed
- vectorize scoring weights for raster error, quality error, complexity, and
  simple-shape bonus
- vectorize anchor threshold config for circle/ring, stroke, quad, rect, and
  rounded-rect candidate gates
- `curve compare-snapshots before.json after.json` for comparing saved
  summaries from different commits/configurations
- `curve compare-git-snapshots before_ref after_ref --path snapshot.json` for
  comparing the same checked-in snapshot file across git refs without changing
  the working tree
- `curve snapshot-git-ref ref --suite suite.json -o snapshot.json` for
  generating curated snapshots from a detached temporary worktree without
  checking out the current working tree
- `curve sweep --markdown summary.md` for scan-friendly config comparisons
- schema-v1 sweep configs
- schema-v1 scene manifests
- `sweep-summary.json` experiment metadata

Remaining:

- add new schema entries when future milestones introduce new commands or real
  MLX model execution.

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
