# Product

## Register

product

## Users

Engineers and technically fluent designers evaluating whether Morphēa's
bitmap-to-SVG reconstruction is trustworthy. Primary user: the project author
running QA loops. Secondary: visitors who land on the site and want to verify
the quality claims against real artifacts. Both read code, understand
geometry, and distrust marketing.

## Product Purpose

Morphēa reconstructs editable SVG geometry (circles stay circles, strokes
stay strokes) from flat-color bitmaps. The QA gallery is the evidence surface:
every card is generated from a passing `primitive-check` fixture and shows
the source bitmap next to the exported SVG. Success means a skeptical visitor
can inspect any case and confirm the claim themselves.

## Brand Personality

Honest, precise, calm. The tone of a well-kept lab notebook: confident
because the data is right there, never louder than the evidence.

## Anti-references

- Marketing pages that present hand-drawn illustrations as tool output.
- Vectorizer landing pages with cherry-picked before/after sliders.
- Dashboard templates that drown one number in chrome.
- Anything that hides failures or rounds metrics into vague claims.

## Design Principles

- Evidence first: generated artifacts lead, prose follows.
- Show the failure path: PASS is only meaningful because FAIL is possible.
- Progressive disclosure: the visual proof up front, the numbers one step
  behind it.
- Density with calm: hundreds of cases must scan fast without shouting.

## Accessibility & Inclusion

Static site, no auth. Keyboard-reachable controls, visible focus, WCAG AA
contrast, `prefers-reduced-motion` respected, alt text on all artifact
images.
