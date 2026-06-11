# ADR 0002: Local MLX-First Pipeline

## Status

Accepted

## Context

The prototype should make local research iteration possible without relying on
cloud vectorization services or external teachers. Apple Silicon is the target
environment.

## Decision

Curve will use a local MLX-first approach. MLX SAM is the intended primary
segmenter, while classical segmentation and heuristics remain available as
fallbacks and baselines.

## Consequences

- Setup may download packages and model weights.
- Runtime inference and evaluation happen locally.
- No cloud APIs or external vectorizer outputs are used as labels.

## Alternatives Considered

- Cloud model pipeline: rejected because it weakens reproducibility and local
  iteration.
- Classical CV only: rejected because the research direction explicitly needs a
  local AI layer.

