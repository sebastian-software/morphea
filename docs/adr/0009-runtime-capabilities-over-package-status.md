# ADR 0009: Runtime Capabilities Over Package Status

## Status

Accepted

## Context

Curve has optional local backends for MLX SAM segmentation, MLX primitive
classification, and differentiable refinement. Some milestones depend on
external runtimes, model files, or adapter work that may not be present in every
developer environment.

A package-level check is too coarse. For example, `mlx` being importable does
not mean live SAM proposals are wired, and it does not mean end-to-end
attention/projection training is implemented. Conversely, the JSON SAM proposal
adapter can be useful even when the live MLX runtime is missing.

## Decision

Runtime reports will distinguish backend status from capability status.

Backends continue to report `status`, `backend_available`, and `reason`.
Optional backends may also report a `capabilities` object whose entries record
`available`, `status`, and `reason`.

`curve status` aggregates unavailable or pending capabilities into
`blocked_capabilities` separately from `blocked_backends`.

## Consequences

- Milestone blockers can be represented in JSON and Markdown without pretending
  that package installation completes the feature.
- JSON SAM proposal replay can remain available while live SAM model execution
  is still pending.
- MLX feature/raster/token classifier work can be marked available separately
  from true end-to-end attention/projection backpropagation.
- Future live adapters can flip a capability to `available` without changing
  the broader report schema.

## Alternatives Considered

- Treat package availability as feature availability: rejected because it hides
  adapter and training gaps.
- Encode all pending work only in milestone prose: rejected because CLI users
  and automated checks need machine-readable blockers.
- Mark a whole backend unavailable while a sub-capability works: rejected
  because the JSON proposal adapter and fallback classifier artifacts are useful
  parts of the research loop.
