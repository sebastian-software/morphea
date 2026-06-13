# Real-Image Promotion Status Ledger

This ledger is the human-readable RIP0/RIP1 status view. The machine-readable
case metadata lives in `docs/real-images/suite.json` under each case's
`promotion` block.

## Last Audit Commands

Curated real images:

```sh
PYTHONPATH=src python3 -m morphea.cli curated-check docs/real-images/suite.json \
  -o /tmp/morphea-real-image-promotion-curated-report-metadata.json \
  --output-dir /tmp/morphea-real-image-promotion-curated-runs-metadata \
  --snapshot /tmp/morphea-real-image-promotion-curated-snapshot-metadata.json \
  --markdown /tmp/morphea-real-image-promotion-curated-report-metadata.md \
  --run
```

Lucide calibration:

```sh
PYTHONPATH=src python3 -m morphea.cli lucide-check assets/lucide/suite.json \
  -o /tmp/morphea-real-image-promotion-lucide-report.json \
  --output-dir /tmp/morphea-real-image-promotion-lucide-runs \
  --markdown /tmp/morphea-real-image-promotion-lucide-report.md
```

## Real-Image Cases

| Case | Source | Pipeline Status | v10 Label | Primary Issues | Evidence |
| --- | --- | --- | --- | --- | --- |
| `terminaro-tweaked` | available local file | checked, expectations failed | red | `missing_semantic_detector`, `shape_class_mismatch`, `weak_visual_fidelity` | `gold-circle-anchors` 4/5, region gate 2/5 with `hole_count=1`, table group 2/8, layer count 4 > 3, visual L1 0.235448 > 0.18 |
| `chatgpt-image-2026-06-11` | missing local file | missing_source | red | `runtime_deferral`, `missing_local_source` | source path unavailable during audit |
| `ui-radio-acceptance-screenshot` | available local file | checked, expectations passed | yellow | `fragmentation`, `missing_promotion_state` | configured topology and shape-class gates pass; current label still keeps promotion deferred |

Current curated result: 3 cases, 1 checked pass, 1 checked failure, 1 missing
source. No real-image case is green under the v10+ definition because green
requires explicit promotion state and visual review artifacts.

## Lucide Calibration

Lucide is not the real-image target, but it is the current definitive-shape
calibration suite for false-positive promotion risk.

| Status | Cases | Notes |
| --- | ---: | --- |
| passed current semantic contracts | 23 | Useful regression evidence, not proof of visual perfection. |
| red | 1 | `badge-check` still fails because the scalloped badge outline is not represented as a distinct editable path. |
| yellow | 5 | `move`, `image`, `alarm-clock`, `arrow-left-right`, and `share-2` pass current contracts but remain visibly loose enough to require review before promotion-style claims. |

## Visual Artifact Posture

Current curated runs emit per-case run directories with input copy, SVG output,
debug SVG, manifest JSON, preview PNG, SVG render PNG, red/blue diff PNG,
contact-sheet PNG, palette summary, mask summary, and report files.

Curated reports also include derived promotion gates:

- `source_available`;
- `semantic_expectations`;
- `visual_contact_sheet`;
- `current_quality_label`.

Cases may also define explicit hard gates that reference concrete expectations,
for example `circle-anchor-shape-class`, `table-grid-topology`, or
`radio-control-topology`. These make shape-class and topology failures visible
as named gates instead of relying only on a broad semantic expectation failure.
Cases may also define source-region gates, such as
`gold-circle-region-shape-class` or `radio-control-region-topology`, that check
expected anchor kinds inside concrete image bounds. Region gates now also emit
`topology_summary` evidence for closed/open anchors, holes, cutouts, and
disconnected component counts.

Cases may define per-family `visual_thresholds`, which produce a
`visual_fidelity_thresholds` gate from run raster metrics after structural hard
gates are available.

Cases may define `group_gates`, such as `table-grid-group-consistency` and
`text-parallel-stroke-grouping`, to require group kind and member-count evidence
for grids, repeated structures, and parallel strokes.

Cases may define `structure_thresholds`, which produce
`fragmentation_layer_thresholds` evidence for aggregate fragmentation and layer
depth.

Red gate failures produce `promotion_summary.decision: rejected`; yellow-only
failures produce `deferred`; all gates passing produces `promoted`.

The current contact sheet includes:

- source/reference image;
- manifest preview;
- anchor overlay;
- exported SVG render;
- red/blue visual diff;
- promotion decision summary;
- failed-gate summary.

Checked real-image cases can become green only when the hard gates pass, the
source is available, review artifacts exist, and the case's current quality
label is green.

## Next Gate

The next implementation block should audit RIP2 exit criteria against generated
reports and decide whether the remaining work should move to RIP3 promotion
pipeline state.
