# ADR 0004: White Cut-Outs as Overlay Strokes in V1

## Status

Accepted

## Context

Many flat illustrations use white lines as cut-outs through darker shapes. They
can be modeled as masks, holes, white shapes, or white strokes.

## Decision

In v1, Morphēa will model cut-out-looking white lines as editable white overlay
strokes.

## Consequences

- Designers can directly edit the line path, width, cap, join, and color.
- The representation is background-dependent and not topologically perfect.
- True masks or negative strokes remain a later option.

## Alternatives Considered

- Negative masks: deferred because they add topology complexity early.
- Filled holes: rejected for v1 because they are less intuitive to edit than
  strokes.

