# Curve

Curve is a local research prototype for semantic-first raster-to-SVG
vectorization.

Most vectorizers optimize for visual similarity first. Curve optimizes for
editable structure first: true circles should stay circles, strokes should stay
strokes, perspective tiles should stay quads, and repeated structures should
become coherent scene groups instead of noisy path fragments.

The project is intentionally hybrid. Deterministic geometry establishes a
trustworthy baseline; local ML, reviewed pseudo-labels, and refinement loops
then help choose and improve semantic primitives without turning every image
into dense, hard-to-edit paths.

## Why Curve Exists

AI-generated illustrations, logos, and UI screenshots often look flat enough
to vectorize, but common tracing output is difficult to edit:

- simple circles become lumpy Bezier paths;
- clean strokes become filled blobs;
- white cut-outs become unstructured holes;
- perspective grids become many unrelated polygons;
- antialiasing and palette drift create too many layers.

Curve treats these as structure-recognition problems. Pixel fidelity still
matters, but it is balanced against editability, primitive quality, layer
fragmentation, and scene semantics.

## Current Baseline

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

Curve is a Python package with a CLI entrypoint. The project currently targets
Python 3.12 or newer.

```sh
python -m pip install -e .
```

Run the test suite:

```sh
python -m unittest discover -s tests
```

Vectorize an image into editable SVG primitives:

```sh
curve vectorize input.png -o output.svg
```

For near-flat or antialiased images, group close colors before component
detection:

```sh
curve vectorize input.png -o output.svg --color-tolerance 18
```

Write a full run directory with input copy, SVG, preview, manifest, config, and
reports:

```sh
curve vectorize input.png -o output.svg --run-dir runs
```

Run the curated real-image suite metadata and bounded local cases:

```sh
curve curated-check docs/real-images/suite.json \
  -o runs/curated-report.json \
  --output-dir runs/curated \
  --run
```

Profile the curated suite:

```sh
curve profile-curated docs/real-images/suite.json \
  -o runs/curated-profile.json \
  --markdown runs/curated-profile.md \
  --repeats 3
```

## Common Workflows

Generate labeled synthetic samples:

```sh
curve generate -o runs/synthetic --count 10 --seed 1
```

Train the primitive-classifier baseline:

```sh
curve train runs/synthetic/dataset.json -o runs/model.json
```

Use a trained classifier as an optional vectorize ranking prior:

```sh
curve vectorize input.png -o output.svg --classifier-model runs/model.json
```

Harvest high-confidence pseudo-labels from run manifests:

```sh
curve harvest runs -o runs/pseudo-labels.json \
  --min-editability-score 0.8 \
  --max-fragmentation-penalty 0.2
```

Create and apply a human review queue:

```sh
curve review runs/pseudo-labels.json -o runs/review.json
curve apply-review runs/review.json -o runs/accepted-labels.json
```

Run a reviewed-label self-learning cycle:

```sh
curve self-learn runs/synthetic/dataset.json \
  --reviewed-labels runs/accepted-labels.json \
  -o runs/self-learn
```

Run structure-preserving refinement:

```sh
curve refine runs/manifest.json -o runs/refined-manifest.json
```

Run a config-driven vectorize sweep:

```sh
curve sweep sweep.json -o runs/sweep --markdown runs/sweep.md
```

## Documentation

- [Plan](docs/plan.md): semantic-first vectorization direction.
- [Milestones](docs/milestones.md): implemented baselines and roadmap.
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

## Development Notes

- Keep tests bounded. When running long checks locally, wrap subprocesses with
  an explicit timeout.
- Do not use local real-image files as checked-in assets. Curated suite entries
  may point at local paths, but the files themselves stay outside git.
- Curve prefers simple parametric shapes over generic paths unless fidelity
  would break materially.
