# ADR 0008: Reviewed Pseudo-Labels Drive Self-Learning

## Status

Accepted

## Context

Morphēa needs to improve on real generated images, not only synthetic fixtures.
Using external vectorizers as labels would make the system chase the wrong
target: visually plausible but often fragmented, hard-to-edit SVG structure.
At the same time, fully manual labels are too slow for iterative research.

## Decision

Morphēa will collect high-confidence outputs from its own pipeline as
pseudo-labels, expose them for human review, and retrain only from accepted or
corrected reviewed labels. External vectorizer outputs may be used for visual
comparison, but not as training labels.

The self-learning loop must keep provenance, quality gates, review decisions,
group context, and retraining comparisons in machine-readable artifacts before
an augmented model is accepted.

## Consequences

- Pseudo-label collection needs explicit quality gates for editability,
  fragmentation, raster diagnostics, primitive stability, and classifier prior
  disagreement.
- Review artifacts must preserve group context and issue tags so repeated
  failures in grids, strokes, and cut-outs can feed back into training.
- Retraining must be gated by validation/test comparisons and curated real
  image checks before a model is trusted.
- Learning speed is lower than copying external labels, but the target remains
  editable semantic structure.

## Alternatives Considered

- Train from external vectorizer SVGs: rejected because they often encode many
  visually correct but hard-to-edit layers.
- Accept all high-confidence pseudo-labels automatically: rejected because
  systematic primitive, cut-out, or grouping mistakes would reinforce
  themselves.
- Fully manual real-image labels only: rejected because iteration would be too
  slow for the research loop.
