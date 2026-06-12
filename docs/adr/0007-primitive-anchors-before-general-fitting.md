# ADR 0007: Primitive Anchors Before General Fitting

## Status

Accepted

## Context

Simple forms are highly visible in vectorized illustrations. An egg-shaped
circle, jittery straight line, uneven ring, or warped perspective tile is
immediately noticeable. Generic contour fitting can overfit pixels and destroy
these forms before the pipeline has a chance to regularize them.

## Decision

Morphēa will run primitive anchor detection before general segment fitting. It
will detect, regularize, score, and reserve simple forms such as circles, rings,
dots, lines, arcs, strokes, rectangles, rounded rectangles, perspective quads,
trapezoids, parallelograms, and grid/tile structures.

## Consequences

- The scene model must be able to reserve anchor regions before organic detail
  fitting.
- Candidate ranking must reward simple parametric forms and penalize noisy
  substitutes.
- Geometry-first regularization is part of semantic-first vectorization.

## Alternatives Considered

- Generic fitting first, simplification later: rejected because bad early
  fragmentation makes anchors harder to recover.
- Pixel-closest path approximation: rejected for anchors because humans notice
  primitive instability more than tiny contour deviations.

