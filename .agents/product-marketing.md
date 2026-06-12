# Morphēa product marketing context

Morphēa is a bitmap-to-vector reconstruction tool focused on editable SVG
geometry. It is a local Python research prototype with a CLI, reports, manifests,
curated checks, and optional local ML/refinement paths.

Primary audience:

- developers building graphics, design-tool, asset, or documentation workflows;
- design engineers who need SVGs they can inspect and modify;
- designers who want cleaner editable output from bitmap artwork.

Core positioning:

> Most vectorizers trace pixels. Morphēa reconstructs form.

Primary claim:

> Reveal the shape within.

Main benefit:

Morphēa turns bitmap artwork into SVG output that is easier to edit: circles,
strokes, quads, cut-outs, and repeated structures are treated as semantic
shapes, not just dense paths.

Proof points available today:

- primitive anchors for circles, rings, strokes, arcs, rectangles, rounded
  rectangles, quads, and perspective grids;
- editable white cut-out strokes and optional negative-mask SVG export;
- bounded real-image runtime controls;
- run directories with SVG, manifest, preview, config, palette, and reports;
- synthetic training, curated checks, pseudo-label review, retraining gates, and
  local refinement.

Voice:

Calm, precise, and useful. Avoid "magic", "supercharge", "revolutionary",
"next-gen", "one-click perfect SVGs", and broad AI claims. Prefer concrete
phrases like "clean paths", "editable SVG geometry", "shape reconstruction",
and "structured vector output".

Compatibility note:

`morphea` is the canonical package and CLI name. `curve` remains a temporary
compatibility alias for older scripts.
