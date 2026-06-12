# Morphēa brand strategy

## Core idea

Morphēa is a bitmap-to-vector reconstruction tool. It takes imperfect raster
artwork and recovers clean, editable vector form.

The brand should feel like a precise studio tool, not a loud AI product. The
central idea is simple: reveal the shape inside the bitmap.

## Naming

Use `Morphēa` in brand, website, docs prose, logos, and screenshots.

Use `morphea` for CLI commands, package names, import paths, URLs, and file
names.

The former `curve` name remains as a temporary technical alias. New copy,
examples, and scripts should teach `morphea`.

## Positioning

Short description:

> Morphēa reconstructs clean, editable SVG geometry from bitmap artwork.

Practical description:

> Morphēa turns icons, logos, illustrations, UI captures, and technical
> graphics into structured SVGs with editable shapes and clean paths.

Contrast line:

> Most vectorizers trace pixels. Morphēa reconstructs form.

Primary claim:

> Reveal the shape within.

## Audience

Primary audience:

- developers building graphics, design-tool, documentation, or asset pipelines;
- design engineers who need inspectable SVG output;
- designers who care about editing the result, not just seeing a close preview.

They are trying to avoid noisy tracing output: lumpy circles, filled stroke
blobs, too many layers, broken grids, and uneditable cut-outs.

## Message pillars

Editable form over pixel tracing:
Morphēa favors semantic SVG primitives when fidelity still holds.

Local and inspectable:
The project runs locally, writes manifests and reports, and keeps optional
backends explicit.

Built for control:
The output should be readable, selectable, and fixable by a person.

Research with a product spine:
The system can use curated checks, pseudo-label review, and refinement loops,
but the story stays focused on better SVG output.

## Voice

Write with calm precision. Use concrete nouns and visible outcomes.

Use:

- reconstructs form
- editable SVG geometry
- clean paths
- structured shapes
- bitmap artwork
- shape reconstruction
- vector reconstruction

Avoid:

- magic
- supercharge
- revolutionary
- next-gen
- one-click perfect SVGs
- AI-powered vectorizer
- vague promises about creativity or productivity

The tone can be slightly editorial, but it should not become ornate. A good
sentence should still work in a README.

## Visual direction

The visual system should show the transition from bitmap evidence to vector
form:

- pixel to curve;
- noise to structure;
- raster grid to editable SVG;
- fragment to recognizable shape.

Palette:

- deep ink for primary text and dark bands;
- warm stone for page backgrounds;
- Aegean or oxidized turquoise for vector strokes and interaction accents;
- restrained gold for numbering and small emphasis.

The mark should be a simple raster-to-curve symbol: a few square pixels resolving
into a single Bezier-like curve. Avoid generic M marks and shiny AI gradients.

## Homepage copy

Hero:

```txt
Morphēa
Reveal the shape within.

Most vectorizers trace pixels. Morphēa reconstructs form, turning bitmap
artwork into clean, editable SVG geometry.
```

Primary CTA:

```txt
Read the plan
```

Secondary CTA:

```txt
Run the CLI
```

Section lines:

```txt
Designed for artwork that should stay editable.
```

```txt
Circles stay circles. Strokes stay strokes. Grids stay coherent.
```

```txt
Reports show what Morphēa recognized, skipped, and refined.
```

## Marketing motions

GitHub/README launch polish:
Ship the new name, strong README, and homepage first. The goal is to make the
repo understandable in under a minute.

Example gallery:
Publish a small gallery with three panels per case: bitmap input, recognized
scene, editable SVG. This will explain the product faster than a long feature
list.

Search content:
Create focused pages or docs around terms people already use: "editable SVG
from PNG", "clean vector logos", "raster to SVG for icons", and "SVG tracing
with editable shapes".

Comparison content:
Compare shape reconstruction against tracing workflows. Keep it factual: show
where Morphēa is better today, where it is still experimental, and when a normal
tracer is enough.

Design-engineering community posts:
Share short technical posts with real before/after artifacts, not hype. The
best channels are likely GitHub, Hacker News-style communities, design
engineering circles, and graphics/devtool forums.
