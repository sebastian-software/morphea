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
