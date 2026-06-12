# ADR 0001: Semantic-First Editability

## Status

Accepted

## Context

Raster-to-SVG systems can produce visually plausible output by layering many
small path fragments. That is useful for resemblance, but it makes the SVG hard
to inspect and edit. Morphēa is intended to explore a different quality target:
editable structure first.

## Decision

Morphēa will optimize for semantic editability before pixel-perfect tracing.
Simple, meaningful primitives should beat fragmented path approximations when
visual fidelity remains acceptable.

## Consequences

- Candidate ranking must include editability metrics, not only raster error.
- Shape fragmentation and unnecessary layer depth are treated as quality
  problems.
- Slight visual deviation is acceptable when the result is much more editable.

## Alternatives Considered

- Pixel-first tracing: rejected because it tends to overfit contours and layer
  fragments.
- Balanced scoring as the primary goal: deferred until semantic-first behavior
  has a measurable baseline.

