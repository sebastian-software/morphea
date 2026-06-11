# ADR 0006: First Training Target Is a Primitive Classifier

## Status

Accepted

## Context

The research prototype needs training, but direct raster-to-scene prediction
would be difficult to debug and would entangle segmentation, geometry, and
export too early.

## Decision

The first trainable model will be a small from-scratch MLX Transformer that
predicts primitive or stroke class plus confidence from a mask/RGBA crop and
geometric features.

## Consequences

- Geometry parameters remain deterministically fitted.
- ML predictions support candidate ranking instead of replacing geometry.
- Synthetic flat-color data can provide reliable labels.

## Alternatives Considered

- Raster-to-scene model: rejected for v1 because it is too broad and opaque.
- Feature-only MLP: rejected because the user prefers a small Transformer.

