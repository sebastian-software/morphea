# Real-Image Promotion Status Ledger

This ledger is the human-readable RIP0/RIP1 status view. The machine-readable
case metadata lives in `docs/real-images/suite.json` under each case's
`promotion` block.

## Last Audit Commands

Curated real images:

```sh
PYTHONPATH=src python3 -m morphea.cli curated-check docs/real-images/suite.json \
  -o /tmp/morphea-rip3-exit-report.json \
  --output-dir /tmp/morphea-rip3-exit-runs \
  --snapshot /tmp/morphea-rip3-exit-snapshot.json \
  --markdown /tmp/morphea-rip3-exit-report.md \
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
| `ui-radio-acceptance-screenshot` | available local file | checked, expectations passed | red | `fragmentation`, `topology_mismatch`, `duplicate_radio_control_anchor` | visual L1 0.033861 < 0.08, but radio topology gate rejects 2 components for 1 intended control |

Current curated semantic result: 3 cases, 1 checked expectation pass, 1 checked
expectation failure, 1 missing source. No real-image case is green under the
v10+ definition because green requires all promotion gates passing and an
available reviewed source.

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
contact-sheet PNG, promoted/fallback SVGs, promotion-export JSON, palette
summary, mask summary, promotion-region review files, and report files.

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

Curated reports now derive `promotion_regions` from source-region gates. Each
region records `promoted`, `deferred`, or `rejected` state with bounds, gate id,
and reason. This is the first RIP3 promotion-pipeline state artifact.
Checked promotion cases with an output directory also write `promoted.svg`,
`fallback.svg`, `promotion-export.json`, `promotion-regions.json`, and
`promotion-review.md`, so trusted region anchors can be separated from
debug/fallback output and rejected candidates remain reviewable.
The run `manifest.json` also carries a top-level `promotion` object and
per-anchor `promotion_state` / `promotion_regions` annotations.
`promotion-export.json` records promoted, fallback-only, rejected, and deferred
anchor-index partitions plus anchor-state counts, so failed semantic candidates
remain explicit even when `fallback.svg` contains all non-promoted anchors.
The `morphea promotion-export` command can regenerate promoted/fallback SVGs
from any promotion-annotated manifest, outside curated sidecar generation.

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

## RIP2 Exit Audit

| Criterion | Status | Evidence |
| --- | --- | --- |
| `badge-check` cannot pass as a circle-like substitute. | met | Lucide calibration remains 23/24 with `badge-check` red. |
| Wrong topology is red even with acceptable L1. | met | `ui-radio-acceptance-screenshot` has visual L1 0.033861 under its 0.08 family threshold, but `radio-control-region-topology` is red because one intended control selects 2 components. |
| Markdown reports show failed gates before aggregate metrics. | met | `render_curated_markdown` begins with the Promotion Gates table before the case metrics table. |
| Contact sheets are first-class review artifacts. | met | Curated runs emit source, preview, anchor overlay, SVG render, diff, promotion summary, and failed-gate panels. |

## RIP3 Exit Audit

| Criterion | Status | Evidence |
| --- | --- | --- |
| Manifests expose region-level promotion state. | met | Checked run manifests include `promotion.regions`; `terminaro-tweaked` records `gold-circle-region-shape-class` as `rejected`, and `ui-radio-acceptance-screenshot` records `radio-control-region-topology` as `rejected`. |
| Fallback and rejected regions are visible in reports. | met | `/tmp/morphea-rip3-exit-report.md` lists `Promotion regions: rejected=1` for both checked real-image cases and shows the failed gate ids before aggregate metrics. |
| Promoted SVG output can be filtered from debug/fallback output. | met | Checked run directories write `promoted.svg`, `fallback.svg`, and `promotion-export.json`; `morphea promotion-export` can regenerate the same partition from a promotion-annotated manifest. |
| No failed semantic candidate disappears silently. | met | `promotion-export.json` records `rejected_anchor_indexes` and `anchor_state_counts`; current checked real-image manifests count 5 rejected anchors for `terminaro-tweaked` and 2 rejected anchors for `ui-radio-acceptance-screenshot`. |

## RIP4 Progress

The first RIP4 slice exposes formula-level `editability_components` in
manifests, run reports, curated reports, snapshots, and sweep summaries. The
current components explain the existing aggregate score without changing gate
decisions: `simple_shape_ratio`, `fragmentation_penalty`, `diagnostic_penalty`,
`generic_path_penalty`, `unclipped_score`, and `clipped_score`.

## Next Gate

The next mainline block should expand RIP4 from formula transparency to v10
component scoring: shape identity confidence, parameter/node economy, stroke
stability, smoothness, topology, grouping, raster fidelity, provenance, and
classifier-prior disagreement. These components must remain subordinate to red
topology and shape-class gates.
