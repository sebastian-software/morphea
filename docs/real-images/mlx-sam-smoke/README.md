# MLX/SAM Smoke Configs

These configs make the current live MLX/SAM runtime proof repeatable without
committing model weights or generated smoke output.

Prerequisites:

- `.venv` installed with `.[mlx]`
- `.venv-mlx-sam` installed with `.[mlx,sam]`
- the tiny SAM2.1 MLX checkpoint and adjacent `.safetensors.json` sidecar in
  `checkpoints/`

Run the smoke:

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

Run the optional Flat-Color-guided prompt smoke:

```sh
.venv-mlx-sam/bin/python -m morphea.cli segment \
  --config docs/real-images/mlx-sam-smoke/mlx-sam-flat-color-centers-segment.json

.venv/bin/python -m morphea.cli compare-segments \
  --config docs/real-images/mlx-sam-smoke/compare-flat-color-centers.json

.venv/bin/python -m morphea.cli compare-segments \
  --config docs/real-images/mlx-sam-smoke/compare-prompt-strategies.json
```

Current expected signal on `assets/curated/terminaro-opaque-table-grid.png`:
Flat-Color produces 41 proposals with 29 geometry-gate accepted proposals; the
tiny 4-prompt MLX/SAM run produces 4 proposals, all accepted. The comparison
verdict is `noise`, not `improved`, because the green promotion proxy drops
from 29 to 4. The comparison currently reports `spatial_matches=3`, which is
useful overlap evidence but not enough to call the source improved; the current
mean spatial IoU for those matches is `0.953309`. Treat this as runtime
evidence and a prompt/config baseline. The MLX/SAM config includes
`max_component_area: 12000` so oversized AI masks are deferred before geometry
gating rather than being promoted as coarse primitive anchors.

The optional `flat_color_centers` smoke is a prompt-strategy experiment. It is
expected to improve overlap evidence relative to blind grid prompting. The
current local run produces 16 proposals, `spatial_matches=16`, and mean
spatial IoU `0.902292`, but the comparison verdict remains `noise` with
`green_delta=-20.0` and 7 accepted-to-rejected spatial transitions; this is
better evidence for prompt placement, not yet a promotable quality improvement.

The direct `grid_points` -> `flat_color_centers` prompt comparison currently
reports `verdict=mixed`: accepted proposals rise by 5, but rejected candidates
also rise by 7. Use that comparison to guide prompt work; do not use the guided
strategy as a default quality claim.

Each comparison report also writes `segment_comparison_audit`. The two
Flat-Color -> MLX/SAM comparisons and the direct prompt-strategy comparison are
expected to report `ok=true`, 9/9 covered checks, and no missing checks. A
`noise` or `mixed` verdict is still acceptable here because the audit measures
whether the comparison evidence is complete, not whether MLX/SAM should be
promoted as the default segmenter.
