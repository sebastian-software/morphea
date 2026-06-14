# MLX and MLX/SAM Runtime Notes

This project keeps the MLX classifier path and the live MLX/SAM segmentation
path separate. The classifier can run in the normal Python 3.12+ project
environment. The optional `mlx-sam` package currently requires Python 3.14+,
so live SAM should run from a separate uv environment.

## Local Environments

Install the project and MLX classifier runtime into the normal development
environment:

```sh
uv pip install --python .venv/bin/python -e '.[mlx]'
```

Create a separate live SAM environment:

```sh
uv venv .venv-mlx-sam --python 3.14
uv pip install --python .venv-mlx-sam/bin/python -e '.[mlx,sam]'
```

The `.venv-*`, `checkpoints/`, and `models/` paths are ignored by git so local
runtime assets do not become accidental source changes.

## Status Checks

Check the classifier/runtime baseline:

```sh
.venv/bin/python -m morphea.cli status
```

Check the live SAM package runtime after configuring a local checkpoint:

```sh
.venv-mlx-sam/bin/python -m morphea.cli status \
  --mlx-sam-model-path checkpoints/sam2.1_hiera_tiny_image_segmenter.safetensors
```

Without `--mlx-sam-model-path`, `mlx_sam` should remain `not_configured`. With
a valid local `.safetensors` checkpoint in the Python 3.14 environment, it
should report `mlx_sam_package_available`.

## Checkpoint Handling

`morphea segment --segmenter mlx_sam` intentionally takes a local
`.safetensors` path. It does not implicitly download model weights during a
segmentation run. Use an explicit setup step to download or convert a SAM2.1
checkpoint into `checkpoints/`, then pass that path to Morphēa.

For a first smoke test, prefer a small or quantized SAM2.1 MLX checkpoint from
the `mlx-sam` model family, then run:

```sh
.venv-mlx-sam/bin/python -m morphea.cli segment assets/curated/terminaro-opaque-table-grid.png \
  --segmenter mlx_sam \
  --mlx-model-path checkpoints/sam2.1_hiera_tiny_image_segmenter.safetensors \
  --mlx-max-masks 9 \
  --mlx-timeout-seconds 30 \
  --geometry-gate \
  --require-reserved-anchor \
  -o runs/mlx-sam-smoke/segments.json \
  --markdown runs/mlx-sam-smoke/segments.md
```

That run is only a real milestone signal if it produces inspectable proposals
and can be compared against the flat-color baseline with `compare-segments`.
Package availability alone is not enough evidence that SAM improves real-image
promotion quality.
