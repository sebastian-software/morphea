# Real-Image Review Decisions

This directory stores portable promotion review decision plans for the curated
real-image suite. Plans use case ids, terminal decision names, and reviewer
evidence only; they intentionally avoid run-local terminal-template paths.

Replay the current deferred decision plan against a fresh review run:

```sh
PYTHONPATH=src python3 -m morphea.cli promotion-review-run docs/real-images/suite.json \
  --output-dir /tmp/morphea-real-image-review-run

PYTHONPATH=src python3 -m morphea.cli promotion-review-harvest \
  --config /tmp/morphea-real-image-review-run/promotion-review-harvest.json \
  --decision-plan docs/real-images/reviews/current-deferred-decision-plan.json
```

The current plan keeps all three real-image cases explicitly deferred. These
records are reviewer-applied evidence, not accepted training labels.

Replay the current region-scoped decision plan:

```sh
PYTHONPATH=src python3 -m morphea.cli promotion-review-run docs/real-images/suite.json \
  --output-dir /tmp/morphea-real-image-review-run

PYTHONPATH=src python3 -m morphea.cli promotion-review-harvest \
  --config /tmp/morphea-real-image-review-run/promotion-review-harvest.json \
  --decision-plan docs/real-images/reviews/current-region-decision-plan.json

PYTHONPATH=src python3 -m morphea.cli harvest-curated \
  --config /tmp/morphea-real-image-review-run/harvest-curated.json

PYTHONPATH=src python3 -m morphea.cli review \
  /tmp/morphea-real-image-review-run/harvested-pseudo-labels.json \
  -o /tmp/morphea-real-image-review-run/review.json \
  --accept-applied-reviews

PYTHONPATH=src python3 -m morphea.cli apply-review \
  /tmp/morphea-real-image-review-run/review.json \
  -o /tmp/morphea-real-image-review-run/reviewed.json

PYTHONPATH=src python3 -m morphea.cli merge-labels \
  /tmp/morphea-real-image-review-run/reviewed.json \
  -o /tmp/morphea-real-image-review-run/reviewed-dataset
```

The region-scoped plan accepts only the Terminaro
`gold-circle-region-shape-class` region via `reviewed_region_ids`. The opaque
generated illustration and UI radio screenshot remain explicitly deferred. This
plan produces trusted pseudo-label candidates only for the reviewed Terminaro
gold-circle anchors, converts those candidates into accepted reviewed labels,
and writes a reviewed-label dataset without updating suite
`current_quality_label` metadata.
