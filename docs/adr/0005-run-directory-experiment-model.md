# ADR 0005: Run Directory Experiment Model

## Status

Accepted

## Context

The prototype needs reproducible experiments and rich intermediate artifacts,
but a database or experiment tracking system would add infrastructure before
the pipeline is stable.

## Decision

Each CLI run will write a timestamped run directory containing the effective
config, input copy, intermediates, candidates, final SVG, scene JSON, metrics,
and report.

## Consequences

- Runs are easy to inspect, copy, diff, and archive.
- A later index or SQLite catalog can be added without changing the artifact
  model.
- Reports should be self-contained enough to debug one run without external
  state.

## Alternatives Considered

- SQLite-first tracking: deferred until query needs are clearer.
- MLflow/W&B-style tracking: rejected for v1 because custom SVG artifacts are
  more important than generic experiment dashboards.

