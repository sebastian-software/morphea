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
  --mlx-sam-model-path checkpoints/sam2.1_hiera_tiny_image_segmenter_q8_trunk_mask_q4_memory.safetensors
```

Without `--mlx-sam-model-path`, `mlx_sam` should remain `not_configured`. With
a valid local `.safetensors` checkpoint in the Python 3.14 environment, it
should report `mlx_sam_package_available`. For quantized checkpoints, also
check that `model_sidecar_exists` is `true`; that means the adjacent
`.safetensors.json` quantization sidecar is present. The default Markdown
status output includes these values in the Backend Diagnostics table.

## Checkpoint Handling

`morphea segment --segmenter mlx_sam` intentionally takes a local
`.safetensors` path. It does not implicitly download model weights during a
segmentation run. Use an explicit setup step to download or convert a SAM2.1
checkpoint into `checkpoints/`, then pass that path to Morphēa.

For a first smoke test, prefer a small or quantized SAM2.1 MLX checkpoint from
the `mlx-sam` model family. The smallest local proof path used so far is the
4-bit tiny checkpoint. Download both the `.safetensors` file and its adjacent
`.safetensors.json` sidecar:

```sh
.venv-mlx-sam/bin/python - <<'PY'
from huggingface_hub import hf_hub_download

repo = "avbiswas/sam2.1-hiera-tiny-mlx-4bit"
for filename in (
    "sam2.1_hiera_tiny_image_segmenter_q8_trunk_mask_q4_memory.safetensors",
    "sam2.1_hiera_tiny_image_segmenter_q8_trunk_mask_q4_memory.safetensors.json",
):
    print(hf_hub_download(repo_id=repo, filename=filename, local_dir="checkpoints"))
PY
```

Then run the checked-in smoke configs. They write reports under `/tmp` so the
repo stays clean:

```sh
mkdir -p /tmp/morphea-mlx-sam-smoke

.venv-mlx-sam/bin/python -m morphea.cli status \
  --config docs/real-images/mlx-sam-smoke/status.json

.venv/bin/python -m morphea.cli segment \
  --config docs/real-images/mlx-sam-smoke/flat-color-segment.json

.venv-mlx-sam/bin/python -m morphea.cli segment \
  --config docs/real-images/mlx-sam-smoke/mlx-sam-segment.json

.venv/bin/python -m morphea.cli compare-segments \
  --config docs/real-images/mlx-sam-smoke/compare-segments.json
```

To test the Flat-Color-guided prompt strategy, run the optional guided config:

```sh
.venv-mlx-sam/bin/python -m morphea.cli segment \
  --config docs/real-images/mlx-sam-smoke/mlx-sam-flat-color-centers-segment.json

.venv/bin/python -m morphea.cli compare-segments \
  --config docs/real-images/mlx-sam-smoke/compare-flat-color-centers.json
```

The current guided smoke produces 16 MLX/SAM proposals and 16 spatial matches
against the Flat-Color baseline, but still reports `verdict=noise` with
`green_delta=-20.0`. Treat it as better prompt-placement evidence, not as a
promotion-quality pass.

The equivalent expanded commands are:

```sh
.venv/bin/python -m morphea.cli segment assets/curated/terminaro-opaque-table-grid.png \
  --segmenter flat_color \
  --max-size 256 \
  --max-colors 10 \
  --min-area 12 \
  --color-tolerance 18 \
  --max-component-area 12000 \
  --geometry-gate \
  --require-reserved-anchor \
  -o /tmp/morphea-mlx-sam-smoke/flat-color-segments.json \
  --markdown /tmp/morphea-mlx-sam-smoke/flat-color-segments.md
```

```sh
.venv-mlx-sam/bin/python -m morphea.cli segment assets/curated/terminaro-opaque-table-grid.png \
  --segmenter mlx_sam \
  --mlx-model-path checkpoints/sam2.1_hiera_tiny_image_segmenter_q8_trunk_mask_q4_memory.safetensors \
  --mlx-score-threshold 0.01 \
  --mlx-max-masks 4 \
  --mlx-timeout-seconds 45 \
  --max-component-area 12000 \
  --geometry-gate \
  --require-reserved-anchor \
  -o /tmp/morphea-mlx-sam-smoke/mlx-sam-segments.json \
  --markdown /tmp/morphea-mlx-sam-smoke/mlx-sam-segments.md
```

Compare the manifests:

```sh
.venv/bin/python -m morphea.cli compare-segments \
  /tmp/morphea-mlx-sam-smoke/flat-color-segments.json \
  /tmp/morphea-mlx-sam-smoke/mlx-sam-segments.json \
  -o /tmp/morphea-mlx-sam-smoke/segment-comparison.json \
  --markdown /tmp/morphea-mlx-sam-smoke/segment-comparison.md
```

That run is only a real milestone signal if it produces inspectable proposals
and can be compared against the flat-color baseline with `compare-segments`.
Package availability alone is not enough evidence that SAM improves real-image
promotion quality.

The first checked local smoke on `assets/curated/terminaro-opaque-table-grid.png`
proved live SAM execution, not promotion improvement: Flat-Color produced 41
proposals with 29 geometry-gate accepted proposals, while the 4-prompt tiny
MLX/SAM run produced 4 proposals and all 4 passed the geometry gate. The
comparison verdict was `noise` because green promotion proxy count dropped from
29 to 4, even though red rejected candidates dropped from 12 to 0. Treat this
as runtime evidence and a prompt/config baseline, not as quality evidence.
With source-coordinate proposal bounds, the comparison currently reports
`spatial_matches=3`: two accepted Flat-Color regions match accepted MLX/SAM
regions, while one rejected Flat-Color region overlaps an accepted MLX/SAM
region and remains review evidence rather than a promotion claim.
The MLX/SAM config carries `max_component_area: 12000`, so larger prompt
sweeps cannot turn huge image-spanning masks into accepted primitive anchors
just because they fit a coarse circle or rounded rectangle.
