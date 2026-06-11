# Curated Real-Image Baselines

This directory stores deterministic baseline snapshots for the curated
real-image suite. Source PNGs stay outside git; snapshots keep only semantic
counts, expectation outcomes, bounded configs, and metrics.

Regenerate the current baseline:

```sh
PYTHONPATH=src python3 -m curve.cli curated-check docs/real-images/suite.json \
  -o /private/tmp/curve-curated-report.json \
  --output-dir /private/tmp/curve-curated-runs \
  --snapshot docs/real-images/baselines/current-curated-snapshot.json \
  --run
```

Compare a new snapshot against the checked-in baseline:

```sh
PYTHONPATH=src python3 -m curve.cli compare-snapshots \
  docs/real-images/baselines/current-curated-snapshot.json \
  /private/tmp/curve-curated-snapshot.json \
  -o /private/tmp/curve-curated-comparison.json \
  --markdown /private/tmp/curve-curated-comparison.md
```

Update the checked-in snapshot only when a detector behavior change is
intentional and the semantic expectations still pass.
