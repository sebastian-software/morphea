# Curve

Curve is a local research prototype for semantic-first raster-to-SVG
vectorization.

The primary goal is not pixel-perfect tracing. The primary goal is editable
SVG structure: simple, stable primitives first, then more complex organic
detail.

## Current Focus

- Detect simple visual anchors before generic fitting.
- Prefer true circles, strokes, arcs, rectangles, and perspective quads over
  noisy path approximations.
- Penalize fragmented layers when a simpler editable shape explains the image.
- Treat cut-out-looking lines as editable strokes in v1.

See [docs/plan.md](docs/plan.md) and [docs/adr](docs/adr) for the current
implementation direction and accepted architecture decisions.

## Development

```sh
python3 -m unittest discover -s tests
```

## First Usable Path

The current CLI can vectorize exact flat-color images into editable SVG
primitives:

```sh
PYTHONPATH=src python3 -m curve.cli vectorize input.png -o output.svg
```

This path currently targets non-antialiased flat-color fixtures. It detects and
exports the first base forms: circles/dots, straight stroke components, and
perspective quad tiles.

For simple anti-aliased or near-flat images, group close colors before
component detection:

```sh
PYTHONPATH=src python3 -m curve.cli vectorize input.png -o output.svg --color-tolerance 18
```

Write a timestamped run directory with input copy, SVG, manifest, config, and
Markdown report:

```sh
PYTHONPATH=src python3 -m curve.cli vectorize input.png -o output.svg --run-dir runs
```

Summarize run directories:

```sh
PYTHONPATH=src python3 -m curve.cli eval runs -o runs/summary.json --markdown runs/summary.md
```

Generate labeled synthetic flat-color samples:

```sh
PYTHONPATH=src python3 -m curve.cli generate -o runs/synthetic --count 10 --seed 1
```

Generation writes `dataset.json` plus split folders (`train`, `val`, `test`).

Train the current primitive-classifier baseline:

```sh
PYTHONPATH=src python3 -m curve.cli train runs/synthetic/dataset.json -o runs/model.json
```

Use a trained classifier as an optional vectorize ranking prior:

```sh
PYTHONPATH=src python3 -m curve.cli vectorize input.png -o output.svg --classifier-model runs/model.json
```

Harvest high-confidence pseudo-labels from run manifests:

```sh
PYTHONPATH=src python3 -m curve.cli harvest runs -o runs/pseudo-labels.json
```
