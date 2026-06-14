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

PYTHONPATH=src python3 -m morphea.cli generate \
  -o /tmp/morphea-real-image-review-base \
  --count 4 \
  --seed 109 \
  --width 64 \
  --height 64 \
  --val-count 1 \
  --test-count 1

PYTHONPATH=src python3 -m morphea.cli self-learn \
  /tmp/morphea-real-image-review-base/dataset.json \
  --reviewed-labels /tmp/morphea-real-image-review-run/reviewed.json \
  -o /tmp/morphea-real-image-review-run/self-learn \
  --allow-unchanged \
  --max-worst-accuracy-drop 1.0
```

The region-scoped plan accepts the transparent Terminaro and checked-in opaque
generated-illustration gold-circle shape-class and visual-fidelity regions via
`reviewed_region_ids`. The UI radio screenshot remains explicitly deferred.
This plan produces trusted pseudo-label candidates only for the reviewed
gold-circle anchors, currently 10 anchors across the two accepted generated
illustration cases, converts those candidates into accepted reviewed labels,
feeds those labels into a self-learning training gate, and writes a
reviewed-label dataset without updating suite `current_quality_label` metadata.
The self-learning cycle summary preserves applied-review decision counts and
provenance-field coverage so the accepted training evidence remains auditable;
the current checked-in replay may still reject model acceptance when the
training comparison regresses.
