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

`current-suite-family-baseline.json` is the checked-in reviewed baseline for
`morphea self-learn --suite-family-baseline`. It is produced by an accepted
self-learning cycle and records primitive, real-image, and Lucide family
outcomes side by side. Current known debt is intentionally carried in the
baseline rather than hidden:

- Real-image `generated_illustration_table_grid` is checked and failing.
- Real-image `generated_illustration_opaque_table_grid` is failing because the
  local source image is missing.

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

Refresh the checked-in suite-family baseline only from an accepted cycle and
only with review evidence:

```sh
PYTHONPATH=src python3 -m morphea.cli self-learn /private/tmp/morphea-base/dataset.json \
  --reviewed-labels /private/tmp/morphea-reviewed-labels.json \
  --curated-suite docs/real-images/suite.json \
  --lucide-suite assets/lucide/suite.json \
  --suite-family-baseline docs/real-images/baselines/current-suite-family-baseline.json \
  --suite-family-baseline-output docs/real-images/baselines/current-suite-family-baseline.json \
  --suite-family-baseline-reviewer morphea \
  --suite-family-baseline-reason "Reviewed suite-family baseline refresh." \
  --suite-family-baseline-changelog docs/real-images/baselines/suite-family-baseline-changelog.jsonl \
  -o /private/tmp/morphea-self-learning-baseline-refresh
```

Accepted refreshes append to `suite-family-baseline-changelog.jsonl`. The
persisted baseline snapshot and changelog stay portable: run-local paths remain
in the cycle report, not in checked-in baseline artifacts.
