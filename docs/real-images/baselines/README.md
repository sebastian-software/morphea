# Curated Real-Image Baselines

This directory stores deterministic baseline snapshots for the curated
real-image suite. Source PNGs stay outside git; snapshots keep only semantic
counts, expectation outcomes, bounded configs, and metrics.

Regenerate the current baseline:

```sh
PYTHONPATH=src python3 -m morphea.cli curated-check docs/real-images/suite.json \
  -o /private/tmp/morphea-curated-report.json \
  --output-dir /private/tmp/morphea-curated-runs \
  --snapshot docs/real-images/baselines/current-curated-snapshot.json \
  --run
```

Compare a new snapshot against the checked-in baseline:

```sh
PYTHONPATH=src python3 -m morphea.cli compare-snapshots \
  docs/real-images/baselines/current-curated-snapshot.json \
  /private/tmp/morphea-curated-snapshot.json \
  -o /private/tmp/morphea-curated-comparison.json \
  --markdown /private/tmp/morphea-curated-comparison.md
```

Generate a snapshot from a git ref without checking out the current working
tree:

```sh
PYTHONPATH=src python3 -m morphea.cli snapshot-git-ref HEAD \
  --suite docs/real-images/suite.json \
  -o /private/tmp/morphea-head-curated-snapshot.json \
  --report /private/tmp/morphea-head-curated-report.json \
  --output-dir /private/tmp/morphea-head-curated-runs
```

Update the checked-in snapshot only when a detector behavior change is
intentional and the semantic expectations still pass.

## Suite-Family Self-Learning Baseline

`current-suite-family-baseline.json` is the checked-in smoke baseline for
`morphea self-learn --suite-family-baseline`. It intentionally starts with
empty primitive, real-image, and Lucide family views so the CLI path can be
validated before a production baseline is promoted.

Smoke the baseline-gated self-learning path after generating a temporary base
dataset and reviewed-label file:

```sh
PYTHONPATH=src python3 -m morphea.cli self-learn /tmp/morphea-base/dataset.json \
  --reviewed-labels /tmp/morphea-reviewed-labels.json \
  --suite-family-baseline docs/real-images/baselines/current-suite-family-baseline.json \
  -o /tmp/morphea-self-learning-baseline-smoke \
  --min-train-examples-delta 10
```

That command intentionally exercises the baseline comparison path even when
the training gate skips retraining.
