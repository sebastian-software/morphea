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

## M2: Primitive Anchor Detection V2

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

## M3: Scene Graph and Layer Semantics

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

## M4: Reports, Metrics, and Experiment Runs

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

## M5: Synthetic Dataset Generator

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

## M6: Local MLX Segmentation Layer

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

## M7: Primitive Classifier Training

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

## M8: Self-Learning Loop

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

## M9: Differentiable and Local Refinement

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

## M10: Curated Real-Image Suite

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

## M11: Productized Research CLI

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

