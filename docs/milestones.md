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
- large color masks emit `color_mask_split_for_components` and are split into
  connected components before oversized components are deferred.
- image component scanning checks `timeout_seconds` during traversal and avoids
  retaining pixel sets for oversized deferred components.
- `connected_components` and the bounded image component scanner use a
  bytearray-backed occupancy grid during BFS while preserving the public
  `BinaryMask` / `MaskComponent` API.

Remaining:

- broader raster hot-loop profiling and optimization beyond component BFS.

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
- stroke width, smoothness, cut-out error metrics.
- quad edge/corner metrics and perspective grid consistency metric.
- stroke payloads preserve `cap_style` and `join_style`.
- straight high-coverage stroke components classify as `butt` caps.
- compact filled axis-aligned rectangles classify as `rect` and stay in the
  `filled_primitives` scene layer.
- simple rounded-rectangle silhouettes classify as `rounded_rect`; descriptive
  metrics such as `corner_radius` are excluded from candidate error scoring.

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
- scene manifests include a top-level `layers` section with anchor indexes and
  counts per semantic layer.
- simple anchors are marked as reserved by `simple_shape_anchor`.
- cut-out strokes are assigned to a `cutout_overlays` layer.
- `curve vectorize --debug-svg` writes an inspectable SVG with anchor ids,
  bounds, and confidence labels.
- vectorize run directories include `debug.svg`.
- reports, eval summaries, and sweep summaries include layer counts.

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
- `report.md`
- report summaries for anchor types and diagnostics
- `curve eval` JSON/Markdown summaries over run directories
- scene-level `metrics` in manifests
- `editability_score`
- `fragmentation_penalty`
- run-directory raster fidelity metrics: `raster_l1_error`,
  `raster_alpha_error`, `raster_edge_error`, and `raster_size_match`
- node, parameter, simple-shape, generic-path, cut-out, and color-fragment
  counts
- metrics surfaced in reports, eval summaries, and sweep summaries
- deterministic manifest preview renderer for current primitive types

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
- deterministic `train` / `val` / `test` split folders
- core primitive ground truth for circles, point dots, circle strokes, line
  strokes, curved strokes, arc strokes, rects, rounded rects, quads, and
  perspective tile grids
- cut-out-like white overlay strokes with editable stroke metadata
- preview/SVG coverage for generated `arc`, `rect`, and `rounded_rect`
  manifests

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
- train/val/test evaluation sections in model artifact
- confusion matrix output
- optional `--classifier-model` prior during `curve vectorize`
- `classifier_prior_error` metric in candidate manifests
- `curve train` writes `ranking_evaluation` comparing heuristic-only candidate
  ranking with classifier-prior-assisted ranking on validation/test splits

Remaining:

- replace or augment centroid baseline with small MLX Transformer

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
- output pseudo-label index with source manifest provenance
- human-editable review queue via `curve review`
- accepted/rejected/pending split via `curve apply-review`
- accepted reviewed pseudo-labels can be merged into a classifier-compatible
  train split via `curve merge-labels`

Remaining:

- retraining comparison against fixed validation suite

## M9: Differentiable and Local Refinement

Status: started.

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
- optional `--source-image` refinement input
- first structure-preserving local optimizer for circle radius adjustment using
  rendered raster L1 error

Remaining:

- refinement-specific use of the full raster diagnostics beyond L1 selection
- broader parameter-adjusting local optimizer beyond circle radius
- optional differentiable backend behind the same interface

## M10: Curated Real-Image Suite

Status: started.

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
- optional `--run` mode using each case's bounded `recommended_config`.
- per-case `output.svg`, `debug.svg`, `manifest.json`, `config.json`,
  `report.md`, and `preview.png` artifacts via `--output-dir`.
- expectation checks for anchor kinds and scene group kinds.

Remaining:

- broaden the suite beyond `terminaro-tweaked.png`.
- fixed regression run snapshots for important commits/configurations.
- visual preview/report rendering for curated cases.

## M11: Productized Research CLI

Status: started.

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
- `curve vectorize`
- `curve eval`
- `curve report`
- `curve sweep`
- `curve merge-labels`
- schema-v1 sweep configs
- schema-v1 scene manifests
- `sweep-summary.json` experiment metadata

Remaining:

- richer config files for preprocessing, segmenters, thresholds, scoring,
  and training.
- comparison views across commits/configs beyond the first JSON summary.

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
