# Morphēa

Reveal the shape within.

Morphēa reconstructs clean, editable SVG geometry from bitmap artwork. It is
built for icons, logos, illustrations, UI captures, and technical graphics
where the output should be something a person can inspect and edit.

Most vectorizers trace pixels. Morphēa reconstructs form: circles stay circles,
strokes stay strokes, perspective tiles stay quads, and repeated structures
become coherent scene groups instead of noisy path fragments.

## Why Morphēa exists

AI-generated artwork and screenshots often look simple enough to vectorize, but
common tracing output is hard to work with:

- simple circles become lumpy Bezier paths;
- clean strokes become filled blobs;
- white cut-outs become unstructured holes;
- perspective grids become many unrelated polygons;
- antialiasing and palette drift create too many layers.

Morphēa treats those cases as shape-reconstruction problems. Pixel fidelity
still matters, but it is balanced against editability, primitive quality, layer
fragmentation, and scene semantics.

## Current baseline

The current baseline implements:

- primitive anchor detection for circles, dots, rings, strokes, arcs,
  rectangles, rounded rectangles, perspective quads, and grid-like tile groups;
- editable white cut-out strokes, with an optional negative-mask SVG export
  strategy;
- real-image runtime controls for alpha handling, palette quantization,
  analysis resizing, component deferral, and timeouts;
- timestamped run directories with SVG, manifest, preview, config, palette,
  mask summaries, and Markdown/HTML reports;
- synthetic dataset generation and primitive classifier training, including an
  optional MLX path when the local environment supports it;
- curated real-image checks, snapshots, and profile reports;
- reviewed pseudo-label harvesting, review/apply-review, retraining gates, and
  self-learning cycles;
- structure-preserving local and soft-raster refinement.

See [docs/milestones.md](docs/milestones.md) for the implemented baseline and
the longer roadmap.

## Quickstart

Morphēa is a Python package with a CLI entrypoint. The project currently targets
Python 3.12 or newer.

```sh
python -m pip install -e .
```

Run the test suite:

```sh
python -m unittest discover -s tests
```

Run the primitive round-trip quality gate:

```sh
morphea primitive-check -o runs/primitive-quality.json \
  --output-dir runs/primitive-quality \
  --markdown runs/primitive-quality.md
```

Vectorize an image into editable SVG primitives:

```sh
morphea vectorize input.png -o output.svg
```

For near-flat or antialiased images, group close colors before component
detection:

```sh
morphea vectorize input.png -o output.svg --color-tolerance 18
```

Write a full run directory with input copy, SVG, preview, manifest, config, and
reports:

```sh
morphea vectorize input.png -o output.svg --run-dir runs
```

Run the curated real-image suite metadata and bounded local cases:

```sh
morphea curated-check docs/real-images/suite.json \
  -o runs/curated-report.json \
  --output-dir runs/curated \
  --run
```

Profile the curated suite:

```sh
morphea profile-curated docs/real-images/suite.json \
  -o runs/curated-profile.json \
  --markdown runs/curated-profile.md \
  --repeats 3
```

The old `curve` command remains available as a compatibility alias during the
rename. New docs and scripts should use `morphea`.

## Common workflows

Generate labeled synthetic samples:

```sh
morphea generate -o runs/synthetic --count 10 --seed 1
```

Train the primitive-classifier baseline:

```sh
morphea train runs/synthetic/dataset.json -o runs/model.json
```

Use a trained classifier as an optional vectorize ranking prior:

```sh
morphea vectorize input.png -o output.svg --classifier-model runs/model.json
```

Harvest high-confidence pseudo-labels from run manifests:

```sh
morphea harvest runs -o runs/pseudo-labels.json \
  --min-editability-score 0.8 \
  --max-fragmentation-penalty 0.2
```

Create and apply a human review queue:

```sh
morphea review runs/pseudo-labels.json -o runs/review.json
morphea apply-review runs/review.json -o runs/accepted-labels.json
```

Run a reviewed-label self-learning cycle:

```sh
morphea self-learn runs/synthetic/dataset.json \
  --reviewed-labels runs/accepted-labels.json \
  -o runs/self-learn
```

Run structure-preserving refinement:

```sh
morphea refine runs/manifest.json -o runs/refined-manifest.json
```

Run a config-driven vectorize sweep:

```sh
morphea sweep sweep.json -o runs/sweep --markdown runs/sweep.md
```

## Documentation

- [Brand strategy](docs/brand-strategy.md): naming, positioning, voice, and
  launch motions.
- [Plan](docs/plan.md): semantic-first vectorization direction.
- [Milestones](docs/milestones.md): implemented baselines and roadmap.
- [Primitive quality roadmap](docs/primitive-quality-roadmap.md): step-by-step
  gates for primary forms and primitive compositions.
- [Schema](docs/schema.md): manifests, reports, status files, and command
  schemas.
- [Sweeps](docs/sweeps.md): config-driven experiment comparisons.
- [ADRs](docs/adr): accepted architecture decisions.
- [Real-image notes](docs/real-images): curated local image metadata and
  observations. The source images stay outside git.

## GitHub Pages

The static project homepage lives in [site/](site/). It is dependency-free HTML
and CSS. The Pages workflow uploads that site plus a temporary copy of the repo
docs so the published documentation links resolve without duplicating docs in
the repository.

To enable deployment, set the repository Pages source to **GitHub Actions** in
GitHub repository settings.

## Development notes

- Keep tests bounded. When running long checks locally, wrap subprocesses with
  an explicit timeout.
- Do not use local real-image files as checked-in assets. Curated suite entries
  may point at local paths, but the files themselves stay outside git.
- Morphēa prefers simple parametric shapes over generic paths unless fidelity
  would break materially.
