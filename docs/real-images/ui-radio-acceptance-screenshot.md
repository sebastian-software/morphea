# UI Radio Acceptance Screenshot

Source image:

- `/Users/sebastian/Desktop/Bildschirmfoto 2026-05-29 um 23.19.25.png`

## Why This Case Exists

This is a real UI screenshot, not a generated illustration. It adds a second
real-image family to the curated suite:

- mostly white UI background
- black anti-aliased text
- a small unselected radio control
- many glyph fragments that should stay bounded and measurable

The case is intentionally different from the Greek-figures/table family. It
keeps the pipeline honest about tiny simple controls and text-heavy screenshots.

## Expected Structures

- `radio-circle-anchor`: at least one true `circle` anchor for the unselected
  radio control at the recommended analysis scale.
- `text-stroke-fragments`: at least ten `stroke_polyline` anchors from text/UI
  strokes, proving the run stays bounded and produces editable primitives.

## Recommended Config

```json
{
  "min_area": 8,
  "color_tolerance": 10,
  "max_size": 768,
  "max_colors": 8,
  "max_component_area": 12000,
  "timeout_seconds": 5
}
```

## Known Current Behavior

Text remains fragmented and carries a high fragmentation penalty. That is
acceptable for this milestone; the case exists to keep runtime bounded and to
make the simple circular control visible in regression snapshots.
