"""Static HTML gallery generation for primitive quality artifacts."""

from __future__ import annotations

import html
import json
import os
import shutil
from pathlib import Path
from statistics import mean
from typing import Any, Iterable

from morphea.primitive_quality import write_primitive_quality_report


DEFAULT_REPORT_PATH = Path("site/assets/primitive-quality/report.json")
DEFAULT_CASES_DIR = Path("site/assets/primitive-quality/cases")
DEFAULT_MARKDOWN_PATH = Path("site/assets/primitive-quality/report.md")
DEFAULT_HTML_PATH = Path("site/primitive-quality/index.html")
DEFAULT_HOMEPAGE_PATH = Path("site/index.html")
HERO_START = "<!-- primitive-gallery-hero:start -->"
HERO_END = "<!-- primitive-gallery-hero:end -->"
TEASER_START = "<!-- primitive-gallery-teaser:start -->"
TEASER_END = "<!-- primitive-gallery-teaser:end -->"
DEFAULT_HERO_CASE_IDS = (
    "touching_circle_stroke_right",
    "stroke_crossing_rectangle_horizontal",
)
DEFAULT_TEASER_CASE_IDS = (
    "filled_square",
    "filled_circle",
    "horizontal_stroke",
    "outlined_ring",
    "antialiased_circle",
    "composition_square_plus_circle_a",
    "touching_circle_stroke_right",
    "stroke_crossing_rectangle_horizontal",
    "overlapping_rectangles_bottom_right",
    "cutout_horizontal_gap_center",
    "group_parallel_strokes_horizontal",
    "arc_up",
    "curve_s",
    "ellipse_horizontal",
    "cutout_curve_rect",
    "organic_blob",
)


def write_primitive_gallery_site(
    *,
    output: str | Path = DEFAULT_REPORT_PATH,
    output_dir: str | Path = DEFAULT_CASES_DIR,
    markdown: str | Path = DEFAULT_MARKDOWN_PATH,
    html_output: str | Path = DEFAULT_HTML_PATH,
    homepage: str | Path | None = DEFAULT_HOMEPAGE_PATH,
    cases: Iterable[str] = (),
    filter_pattern: str | None = None,
    hero_cases: Iterable[str] = DEFAULT_HERO_CASE_IDS,
    teaser_cases: Iterable[str] = DEFAULT_TEASER_CASE_IDS,
    clean: bool = True,
) -> dict[str, Any]:
    """Write primitive-check artifacts plus the static QA gallery pages."""

    output_path = Path(output)
    output_dir_path = Path(output_dir)
    markdown_path = Path(markdown)
    html_path = Path(html_output)
    if clean and output_dir_path.exists():
        shutil.rmtree(output_dir_path)

    report = write_primitive_quality_report(
        output=output_path,
        output_dir=output_dir_path,
        markdown=markdown_path,
        cases=cases,
        filter_pattern=filter_pattern,
    )
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(
        render_full_gallery_html(report, html_path=html_path),
        encoding="utf-8",
    )
    if homepage is not None:
        homepage_path = Path(homepage)
        if homepage_path.exists():
            if _has_homepage_block(homepage_path, HERO_START, HERO_END):
                _update_homepage_block(
                    homepage_path,
                    HERO_START,
                    HERO_END,
                    render_homepage_hero_html(
                        report,
                        homepage_path=homepage_path,
                        hero_cases=tuple(hero_cases),
                    ),
                )
            _update_homepage_teaser(
                homepage_path,
                render_homepage_teaser_html(
                    report,
                    homepage_path=homepage_path,
                    full_gallery_path=html_path,
                    teaser_cases=tuple(teaser_cases),
                ),
            )
    return report


def render_full_gallery_html(
    report: dict[str, Any],
    *,
    html_path: str | Path,
) -> str:
    html_path = Path(html_path)
    cases = list(report.get("cases", []))
    families = list(report.get("family_summaries", []))
    l1_values = [_metric(case, "raster_l1_error") for case in cases]
    edge_values = [_metric(case, "raster_edge_error") for case in cases]
    family_options = "\n".join(
        f'            <option value="{_esc(str(family.get("family")))}">'
        f'{_esc(str(family.get("family")))} ({family.get("case_count", 0)})</option>'
        for family in families
    )
    cards = "\n".join(_render_full_case_card(case, html_path) for case in cases)
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Morphēa primitive quality gallery</title>
    <meta name="description" content="Deterministic primitive quality fixtures rendered as bitmap and SVG pairs.">
    <style>
{_FULL_GALLERY_CSS}
    </style>
  </head>
  <body>
    <header class="gallery-header">
      <a class="home-link" href="../">Morphēa</a>
      <div>
        <p class="eyebrow">Primitive quality gallery</p>
        <h1>{report.get("case_count", 0)} deterministic round-trip cases</h1>
        <p class="lede">Every card is a <code>primitive-check</code> artifact: source bitmap and exported SVG in the same 64&thinsp;px viewport, so geometry drift is visible at a glance. {_curve_coverage_text(report)}</p>
      </div>
    </header>

    <aside class="gallery-controls" aria-label="Primitive gallery filters">
      <div class="stat-strip">
        <span><strong>{report.get("passed_count", 0)}</strong> passed</span>
        <span><strong>{report.get("failed_count", 0)}</strong> failed</span>
        <span><strong>{len(families)}</strong> families</span>
        <span><strong>{_range_text(l1_values)}</strong> L1</span>
        <span><strong>{_range_text(edge_values)}</strong> edge</span>
        <button type="button" id="details-toggle" aria-pressed="false">Show QA details</button>
        <details class="metric-legend">
          <summary>What the numbers mean</summary>
          <dl>
            <div><dt>Preview L1 / edge</dt><dd>Mean per-pixel color and edge-structure difference between the manifest-rendered preview and the source bitmap. 0 is identical; family budgets sit between 0.001 and 0.08.</dd></div>
            <div><dt>SVG L1 / edge</dt><dd>The same two measures against the rasterized <em>exported SVG</em>, the file you would actually use.</dd></div>
            <div><dt>BBox IoU</dt><dd>Bounding-box overlap between detected and expected geometry; 1.0 is a perfect match.</dd></div>
            <div><dt>Anchors / nodes</dt><dd>How many primitives the scene uses and how many control points they carry. Fewer means easier to edit.</dd></div>
          </dl>
        </details>
      </div>
      <div class="filter-row">
        <label>
          <span>Search</span>
          <input id="case-search" type="search" placeholder="case, family, kind, contract">
        </label>
        <label>
          <span>Family</span>
          <select id="family-filter">
            <option value="all">All families</option>
{family_options}
          </select>
        </label>
        <label>
          <span>Kind</span>
          <select id="kind-filter">
            <option value="all">All kinds</option>
            <option value="rect">rect</option>
            <option value="quad">quad</option>
            <option value="circle">circle</option>
            <option value="stroke_polyline">stroke_polyline</option>
            <option value="stroke_circle">stroke_circle</option>
            <option value="rounded_rect">rounded_rect</option>
            <option value="arc">arc</option>
            <option value="stroke_path">stroke_path</option>
            <option value="ellipse">ellipse</option>
            <option value="stroke_ellipse">stroke_ellipse</option>
            <option value="cubic_path">cubic_path</option>
          </select>
        </label>
        <label>
          <span>Contracts</span>
          <select id="contract-filter">
            <option value="all">All contracts</option>
            <option value="group">Groups</option>
            <option value="cutout">Cut-outs</option>
            <option value="export">Export comparison</option>
            <option value="arc_contract">Arcs</option>
            <option value="smooth_curve_contract">Smooth curves</option>
            <option value="ellipse_contract">Ellipses</option>
            <option value="curved_cutout_contract">Curved cut-outs</option>
            <option value="organic_fallback">Organic fallback</option>
            <option value="failed">Failed only</option>
          </select>
        </label>
      </div>
      <p id="visible-count" class="visible-count">{len(cases)} cases visible</p>
    </aside>

    <main class="case-grid" aria-label="Primitive cases">
{cards}
    </main>

    <script>
{_FULL_GALLERY_JS}
    </script>
  </body>
</html>
"""


def render_homepage_teaser_html(
    report: dict[str, Any],
    *,
    homepage_path: str | Path,
    full_gallery_path: str | Path,
    teaser_cases: tuple[str, ...] = DEFAULT_TEASER_CASE_IDS,
) -> str:
    homepage_path = Path(homepage_path)
    full_gallery_path = Path(full_gallery_path)
    cases_by_id = {str(case.get("id")): case for case in report.get("cases", [])}
    teaser = [
        cases_by_id[case_id]
        for case_id in teaser_cases
        if case_id in cases_by_id and cases_by_id[case_id].get("ok")
    ]
    cards = "\n".join(_render_teaser_card(case, homepage_path) for case in teaser)
    gallery_href = _relative_uri(full_gallery_path, homepage_path.parent)
    return f"""        <div class="primitive-copy">
          <p class="eyebrow">Primitive quality gate</p>
          <h2>Generated bitmap-to-SVG proof cases.</h2>
          <p>
            These panels are generated from passing <code>primitive-check</code>
            artifacts. Each bitmap and SVG pair uses the same fixed canvas.
          </p>
          <a class="text-link" href="{_esc(gallery_href)}">Primitive quality gallery: {report.get("case_count", 0)} passing cases</a>
        </div>
        <div class="primitive-gallery">
{cards}
        </div>"""


def render_homepage_hero_html(
    report: dict[str, Any],
    *,
    homepage_path: str | Path,
    hero_cases: tuple[str, ...] = DEFAULT_HERO_CASE_IDS,
) -> str:
    homepage_path = Path(homepage_path)
    selected = _select_passing_cases(report, hero_cases, limit=2)
    cards = "\n".join(_render_hero_case(case, homepage_path) for case in selected)
    return f"""          <div class="hero-proof-panel" aria-label="Generated primitive round-trip examples">
            <div class="hero-proof-header">
              <div>
                <p class="eyebrow">Live quality artifacts</p>
                <h2>Bitmap and exported SVG, same canvas.</h2>
              </div>
              <span class="hero-proof-status">PASS</span>
            </div>
            <div class="hero-proof-cases">
{cards}
            </div>
          </div>"""


def _render_hero_case(case: dict[str, Any], homepage_path: Path) -> str:
    case_id = str(case.get("id"))
    title = _short_title(case_id)
    kind = _summary_kind(case)
    metrics = case.get("metrics", {})
    return f"""              <article class="hero-proof-case">
                <header>
                  <h3>{_esc(title)}</h3>
                  <span>{_esc(kind)}</span>
                </header>
                <div class="hero-proof-pair">
                  {_render_media_figure("Bitmap", _artifact_uri(case, "input", homepage_path), case_id + " bitmap", frame_class="demo-frame hero-proof-frame")}
                  {_render_media_figure("SVG", _artifact_uri(case, "output_svg", homepage_path), case_id + " SVG", frame_class="demo-frame hero-proof-frame")}
                </div>
                <p class="hero-proof-meta">
                  <span>{_anchor_count_text(case)}</span>
                  <span>L1 {_metric_text(metrics, "raster_l1_error")}</span>
                  <span>edge {_metric_text(metrics, "raster_edge_error")}</span>
                </p>
              </article>"""


def _curve_coverage_text(report: dict[str, Any]) -> str:
    curve_counts = report.get("curve_anchor_kind_counts", {})
    curve_counts = curve_counts if isinstance(curve_counts, dict) else {}
    present = {
        str(kind): int(count)
        for kind, count in curve_counts.items()
        if int(count) > 0
    }
    if not present:
        return (
            "No freeform curve coverage yet: arcs, smooth stroke paths, "
            "ellipses, and organic paths are tracked by the freeform arc "
            "quality roadmap."
        )
    summary = ", ".join(
        f"{count} {kind}" for kind, count in sorted(present.items())
    )
    return f"Passing cases include {summary} anchors."


def _render_full_case_card(case: dict[str, Any], html_path: Path) -> str:
    case_id = str(case.get("id"))
    family = str(case.get("family"))
    variant = str(case.get("variant"))
    kind = str(case.get("actual_kind") or "n/a")
    metrics = case.get("metrics", {})
    svg_metrics = case.get("svg_metrics") or {}
    geometry = case.get("geometry", {})
    group_matches = case.get("group_matches", [])
    contract_tokens = _contract_tokens(case)
    search_text = " ".join(
        [
            case_id,
            family,
            variant,
            kind,
            " ".join(contract_tokens),
            " ".join(str(match.get("expected_kind")) for match in group_matches),
        ]
    )
    anchor_count = int(case.get("anchor_count", 0))
    anchor_noun = "anchor" if anchor_count == 1 else "anchors"
    return f"""      <article class="case-card" data-family="{_esc(family)}" data-kind="{_esc(kind)}" data-contracts="{_esc(' '.join(contract_tokens))}" data-ok="{str(bool(case.get("ok"))).lower()}" data-search="{_esc(search_text.lower())}">
        <header>
          <div>
            <p class="case-family">{_esc(family)}</p>
            <h2>{_esc(_title_from_id(case_id))}</h2>
          </div>
          <span class="status {'pass' if case.get('ok') else 'fail'}">{'PASS' if case.get('ok') else 'FAIL'}</span>
        </header>
        <div class="media-pair">
          {_render_media_figure("Bitmap", _artifact_uri(case, "input", html_path), case_id + " bitmap")}
          {_render_media_figure("SVG", _artifact_uri(case, "output_svg", html_path), case_id + " exported SVG")}
        </div>
        <p class="case-facts"><code>{_esc(kind)}</code><span>{anchor_count} {anchor_noun} · {_node_count(case)} nodes</span></p>
        <details class="case-details">
          <summary>QA details</summary>
          <div class="details-body">
            <table class="metric-table">
              <tr><th scope="row" title="Mean per-pixel color difference, manifest preview vs source">Preview L1 / edge</th><td>{_metric_text(metrics, "raster_l1_error")} / {_metric_text(metrics, "raster_edge_error")}</td></tr>
              <tr><th scope="row" title="Same comparison against the rasterized exported SVG">SVG L1 / edge</th><td>{_metric_text(svg_metrics, "svg_raster_l1_error")} / {_metric_text(svg_metrics, "svg_raster_edge_error")}</td></tr>
              <tr><th scope="row" title="Bounding-box overlap, detected vs expected geometry">BBox IoU</th><td>{_metric_text(geometry, "bbox_iou")}</td></tr>
              <tr><th scope="row" title="Fixture variant within the family">Variant</th><td>{_esc(variant)}</td></tr>
            </table>
            {_render_svg_raster_figure(case, html_path)}
            <div class="badges">{_badge_html(case)}</div>
          </div>
        </details>
      </article>"""


def _render_teaser_card(case: dict[str, Any], homepage_path: Path) -> str:
    case_id = str(case.get("id"))
    title = _short_title(case_id)
    kind = _summary_kind(case)
    metrics = case.get("metrics", {})
    return f"""          <article class="demo-item">
            <header>
              <h3>{_esc(title)}</h3>
              <span>PASS</span>
            </header>
            <div class="demo-pair">
              {_render_media_figure("Bitmap", _artifact_uri(case, "input", homepage_path), case_id + " bitmap")}
              {_render_media_figure("SVG", _artifact_uri(case, "output_svg", homepage_path), case_id + " SVG")}
            </div>
            <p><code>{_esc(kind)}</code> · {_anchor_count_text(case)} · L1 {_metric_text(metrics, "raster_l1_error")} · edge {_metric_text(metrics, "raster_edge_error")}</p>
          </article>"""


def _render_svg_raster_figure(case: dict[str, Any], html_path: Path) -> str:
    artifacts = case.get("artifacts", {})
    if not isinstance(artifacts, dict) or "svg_render" not in artifacts:
        return ""
    return f"""<figure class="raster-proof">
              <figcaption title="The exact bitmap the SVG metrics are computed from">Rasterized SVG</figcaption>
              <div class="demo-frame">
                <img src="{_esc(_artifact_uri(case, "svg_render", html_path))}" alt="{_esc(str(case.get("id")) + " rasterized SVG")}" loading="lazy" decoding="async">
              </div>
            </figure>"""


def _render_media_figure(
    label: str,
    src: str,
    alt: str,
    *,
    frame_class: str = "demo-frame",
) -> str:
    return f"""<figure>
                <figcaption>{_esc(label)}</figcaption>
                <span class="{_esc(frame_class)}"><img src="{_esc(src)}" width="64" height="64" alt="{_esc(alt)}" loading="lazy" decoding="async"></span>
              </figure>"""


def _update_homepage_teaser(homepage: Path, replacement: str) -> None:
    _update_homepage_block(homepage, TEASER_START, TEASER_END, replacement)


def _has_homepage_block(homepage: Path, start_marker: str, end_marker: str) -> bool:
    source = homepage.read_text(encoding="utf-8")
    start = source.find(start_marker)
    end = source.find(end_marker)
    return start >= 0 and end > start


def _update_homepage_block(
    homepage: Path,
    start_marker: str,
    end_marker: str,
    replacement: str,
) -> None:
    source = homepage.read_text(encoding="utf-8")
    start = source.find(start_marker)
    end = source.find(end_marker)
    if start < 0 or end < 0 or end <= start:
        raise ValueError(f"{homepage} is missing primitive gallery markers")
    updated = (
        source[: start + len(start_marker)]
        + "\n"
        + replacement
        + "\n"
        + source[end:]
    )
    homepage.write_text(updated, encoding="utf-8")


def _select_passing_cases(
    report: dict[str, Any],
    preferred_ids: tuple[str, ...],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    cases = [case for case in report.get("cases", []) if case.get("ok")]
    cases_by_id = {str(case.get("id")): case for case in cases}
    selected: list[dict[str, Any]] = [
        cases_by_id[case_id] for case_id in preferred_ids if case_id in cases_by_id
    ]
    selected_ids = {str(case.get("id")) for case in selected}
    for case in cases:
        if len(selected) >= limit:
            break
        if str(case.get("id")) not in selected_ids:
            selected.append(case)
            selected_ids.add(str(case.get("id")))
    return selected[:limit]


def _artifact_uri(case: dict[str, Any], key: str, html_path: Path) -> str:
    artifacts = case.get("artifacts", {})
    target = Path(str(artifacts.get(key, "")))
    if not target.is_absolute():
        target = Path.cwd() / target
    return _relative_uri(target, html_path.parent)


def _relative_uri(target: Path, base_dir: Path) -> str:
    if not base_dir.is_absolute():
        base_dir = Path.cwd() / base_dir
    relative = os.path.relpath(target, base_dir)
    return Path(relative).as_posix()


def _contract_tokens(case: dict[str, Any]) -> list[str]:
    tokens: list[str] = []
    if case.get("group_matches"):
        tokens.append("group")
        tokens.extend(
            str(match.get("expected_kind"))
            for match in case.get("group_matches", [])
            if match.get("expected_kind")
        )
    if case.get("export_comparison"):
        tokens.append("export")
    for match in case.get("matches", []):
        actual = match.get("geometry_diff", {}).get("actual", {})
        stroke = actual.get("geometry", {}).get("stroke", {})
        if isinstance(stroke, dict) and stroke.get("is_cutout"):
            tokens.append("cutout")
    if "cutout" in str(case.get("family", "")):
        tokens.append("cutout")
    tokens.extend(_curve_contract_tokens(case))
    if not case.get("ok"):
        tokens.append("failed")
    return sorted(set(tokens))


def _curve_contract_tokens(case: dict[str, Any]) -> list[str]:
    kinds = set()
    counts = case.get("anchor_kind_counts", {})
    if isinstance(counts, dict):
        kinds.update(str(kind) for kind, count in counts.items() if count)
    kinds.add(str(case.get("actual_kind")))
    tokens = []
    if "arc" in kinds:
        tokens.append("arc_contract")
    if "stroke_path" in kinds:
        if "cutout" in str(case.get("family", "")):
            tokens.append("curved_cutout_contract")
        else:
            tokens.append("smooth_curve_contract")
    if kinds & {"ellipse", "stroke_ellipse"}:
        tokens.append("ellipse_contract")
    if "cubic_path" in kinds:
        tokens.append("organic_fallback")
    return tokens


def _badge_html(case: dict[str, Any]) -> str:
    labels = []
    labels.extend(
        str(match.get("expected_kind"))
        for match in case.get("group_matches", [])
        if match.get("expected_kind")
    )
    if case.get("export_comparison"):
        labels.append("export_comparison")
    if "cutout" in _contract_tokens(case):
        labels.append("cutout")
    labels.extend(_curve_contract_tokens(case))
    if not labels:
        labels.append("semantic contract")
    return "".join(f"<span>{_esc(label)}</span>" for label in sorted(set(labels)))


def _node_count(case: dict[str, Any]) -> int | str:
    artifacts = case.get("artifacts", {})
    manifest_path = artifacts.get("manifest") if isinstance(artifacts, dict) else None
    if manifest_path:
        try:
            manifest = json.loads(Path(str(manifest_path)).read_text(encoding="utf-8"))
            return sum(int(anchor.get("node_count", 0)) for anchor in manifest.get("anchors", []))
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return "n/a"
    return "n/a"


def _anchor_count_text(case: dict[str, Any]) -> str:
    count = int(case.get("anchor_count", 0))
    noun = "anchor" if count == 1 else "anchors"
    return f"{count} {noun}"


def _summary_kind(case: dict[str, Any]) -> str:
    group_matches = case.get("group_matches", [])
    if group_matches:
        return str(group_matches[0].get("expected_kind") or case.get("actual_kind"))
    if case.get("export_comparison"):
        return "cutout export"
    kinds = [
        str(match.get("actual_kind"))
        for match in case.get("matches", [])
        if match.get("actual_kind")
    ]
    return " + ".join(kinds[:2]) if len(kinds) > 1 else str(case.get("actual_kind"))


def _title_from_id(case_id: str) -> str:
    return case_id.replace("_", " ")


def _short_title(case_id: str) -> str:
    custom = {
        "composition_square_plus_circle_a": "Square plus circle",
        "touching_circle_stroke_right": "Touching circle and stroke",
        "stroke_crossing_rectangle_horizontal": "Stroke crossing rectangle",
        "overlapping_rectangles_bottom_right": "Ordered overlap",
        "cutout_horizontal_gap_center": "Cut-out stroke",
        "group_parallel_strokes_horizontal": "Parallel strokes",
    }
    return custom.get(case_id, _title_from_id(case_id).title())


def _metric(case: dict[str, Any], key: str) -> float:
    metrics = case.get("metrics", {})
    try:
        return float(metrics.get(key, 0.0))
    except (TypeError, ValueError):
        return 0.0


def _metric_text(metrics: dict[str, Any], key: str) -> str:
    try:
        return f"{float(metrics.get(key, 0.0)):.4f}"
    except (TypeError, ValueError):
        return "n/a"


def _range_text(values: list[float]) -> str:
    if not values:
        return "n/a"
    return f"{min(values):.3f}-{max(values):.3f}"


def _esc(value: str) -> str:
    return html.escape(value, quote=True)


_FULL_GALLERY_CSS = r"""
:root {
  --paper: #f5efe3;
  --panel: #fffaf2;
  --ink: #101719;
  --muted: #57615e;
  --line: #cdbc9f;
  --line-soft: #ddd0b8;
  --teal: #17656b;
  --gold: #ad7b1e;
  --red: #b83b33;
  --green: #2f746d;
  --serif: "Iowan Old Style", "Palatino Linotype", Palatino, Georgia, serif;
  --mono: "SFMono-Regular", Consolas, monospace;
}

* { box-sizing: border-box; }

body {
  background: var(--paper);
  color: var(--ink);
  font-family: Optima, Avenir, "Avenir Next", sans-serif;
  margin: 0;
}

code {
  font-family: var(--mono);
  font-size: 0.92em;
}

.gallery-header {
  align-items: end;
  border-bottom: 1px solid var(--line);
  display: grid;
  gap: 32px;
  grid-template-columns: 170px minmax(0, 1fr);
  padding: 34px 40px 28px;
}

.home-link {
  border: 1px solid var(--ink);
  color: var(--ink);
  display: inline-block;
  font-weight: 800;
  padding: 8px 10px;
  text-decoration: none;
  width: max-content;
}

.home-link:hover,
.home-link:focus-visible {
  background: var(--ink);
  color: var(--panel);
}

.eyebrow {
  color: var(--teal);
  font-size: 12px;
  font-weight: 850;
  letter-spacing: .08em;
  margin: 0 0 8px;
  text-transform: uppercase;
}

h1 {
  font-family: var(--serif);
  font-size: clamp(34px, 5vw, 64px);
  letter-spacing: 0;
  line-height: .96;
  margin: 0;
  text-wrap: balance;
}

.lede {
  color: var(--muted);
  font-size: 16px;
  line-height: 1.5;
  margin: 14px 0 0;
  max-width: 72ch;
}

.gallery-controls {
  background: color-mix(in srgb, var(--paper) 86%, var(--panel));
  border-bottom: 1px solid var(--line);
  padding: 14px 40px 16px;
  position: sticky;
  top: 0;
  z-index: 4;
}

.stat-strip {
  align-items: center;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}

.stat-strip span,
.badges span {
  border: 1px solid var(--line);
  background: var(--panel);
  color: var(--muted);
  font-size: 12px;
  font-weight: 700;
  padding: 5px 8px;
}

.stat-strip strong {
  color: var(--ink);
}

#details-toggle {
  background: var(--panel);
  border: 1px solid var(--teal);
  color: var(--teal);
  cursor: pointer;
  font: inherit;
  font-size: 12px;
  font-weight: 800;
  margin-left: auto;
  padding: 5px 10px;
}

#details-toggle[aria-pressed="true"] {
  background: var(--teal);
  color: var(--panel);
}

.metric-legend {
  flex-basis: 100%;
}

.metric-legend summary {
  color: var(--muted);
  cursor: pointer;
  font-size: 12px;
  font-weight: 700;
  width: max-content;
}

.metric-legend summary:hover { color: var(--ink); }

.metric-legend dl {
  display: grid;
  gap: 6px 18px;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  margin: 10px 0 2px;
  max-width: 1200px;
}

.metric-legend dt {
  font-size: 12px;
  font-weight: 800;
}

.metric-legend dd {
  color: var(--muted);
  font-size: 13px;
  line-height: 1.45;
  margin: 2px 0 0;
}

.filter-row {
  display: grid;
  gap: 10px;
  grid-template-columns: minmax(220px, 1.35fr) repeat(3, minmax(150px, .55fr));
}

label {
  display: grid;
  gap: 5px;
}

label span {
  color: var(--muted);
  font-size: 11px;
  font-weight: 800;
  text-transform: uppercase;
}

input,
select {
  appearance: none;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 0;
  color: var(--ink);
  font: inherit;
  min-height: 38px;
  padding: 7px 10px;
}

input:focus-visible,
select:focus-visible,
button:focus-visible,
summary:focus-visible,
.home-link:focus-visible {
  outline: 2px solid var(--gold);
  outline-offset: 2px;
}

.visible-count {
  color: var(--muted);
  font-size: 13px;
  margin: 10px 0 0;
}

.case-grid {
  display: grid;
  gap: 16px;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  padding: 24px 40px 48px;
}

.case-card {
  align-content: start;
  background: var(--panel);
  border: 1px solid var(--line);
  display: grid;
  gap: 12px;
  padding: 14px;
}

.case-card[hidden] {
  display: none;
}

.case-card header {
  align-items: start;
  display: flex;
  gap: 12px;
  justify-content: space-between;
}

.case-family {
  color: var(--teal);
  font-size: 11px;
  font-weight: 850;
  letter-spacing: .04em;
  margin: 0 0 4px;
  text-transform: uppercase;
}

.case-card h2 {
  font-family: var(--serif);
  font-size: 21px;
  line-height: 1.05;
  margin: 0;
}

.status {
  border: 1px solid currentColor;
  font-size: 11px;
  font-weight: 850;
  padding: 4px 6px;
}

.status.pass { color: var(--green); }
.status.fail { background: var(--red); border-color: var(--red); color: var(--panel); }

.media-pair,
.demo-pair {
  display: grid;
  gap: 10px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

figure {
  margin: 0;
}

figcaption {
  color: var(--muted);
  font-size: 11px;
  font-weight: 850;
  margin-bottom: 6px;
  text-transform: uppercase;
}

.demo-frame {
  align-items: center;
  aspect-ratio: 1;
  background:
    linear-gradient(45deg, color-mix(in srgb, var(--line) 36%, transparent) 25%, transparent 25%) 0 0 / 12px 12px,
    linear-gradient(45deg, transparent 75%, color-mix(in srgb, var(--line) 36%, transparent) 75%) 0 0 / 12px 12px,
    linear-gradient(45deg, transparent 75%, color-mix(in srgb, var(--line) 36%, transparent) 75%) 6px 6px / 12px 12px,
    linear-gradient(45deg, color-mix(in srgb, var(--line) 36%, transparent) 25%, #fff 25%) 6px 6px / 12px 12px;
  border: 1px solid var(--line);
  display: grid;
  justify-items: center;
  max-width: 128px;
  width: 100%;
}

.demo-frame img {
  display: block;
  height: 100%;
  image-rendering: pixelated;
  object-fit: contain;
  width: 100%;
}

.case-facts {
  align-items: baseline;
  border-top: 1px solid var(--line-soft);
  display: flex;
  flex-wrap: wrap;
  gap: 4px 10px;
  justify-content: space-between;
  margin: 0;
  padding-top: 10px;
}

.case-facts code {
  font-size: 13px;
  font-weight: 700;
}

.case-facts span {
  color: var(--muted);
  font-size: 12.5px;
}

.case-details summary {
  color: var(--teal);
  cursor: pointer;
  font-size: 12px;
  font-weight: 800;
  list-style: none;
  text-transform: uppercase;
  width: max-content;
}

.case-details summary::-webkit-details-marker { display: none; }

.case-details summary::before {
  content: "+";
  display: inline-block;
  margin-right: 6px;
  transition: transform .18s cubic-bezier(.22, 1, .36, 1);
}

.case-details[open] summary::before {
  transform: rotate(45deg);
}

.case-details summary:hover { color: var(--ink); }

.details-body {
  display: grid;
  gap: 12px;
  padding-top: 12px;
}

.metric-table {
  border-collapse: collapse;
  width: 100%;
}

.metric-table th,
.metric-table td {
  border-top: 1px solid var(--line-soft);
  font-size: 12.5px;
  padding: 5px 0;
  text-align: left;
}

.metric-table th {
  color: var(--muted);
  cursor: help;
  font-weight: 700;
  text-decoration: underline dotted color-mix(in srgb, var(--muted) 55%, transparent);
  text-underline-offset: 3px;
  width: 46%;
}

.metric-table td {
  font-family: var(--mono);
  font-size: 12px;
}

.raster-proof .demo-frame {
  max-width: 96px;
}

.badges {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

@media (prefers-reduced-motion: reduce) {
  .case-details summary::before {
    transition: none;
  }
}

@media (max-width: 820px) {
  .gallery-header,
  .filter-row {
    grid-template-columns: 1fr;
  }

  .gallery-header,
  .gallery-controls,
  .case-grid {
    padding-left: 18px;
    padding-right: 18px;
  }

  .case-grid {
    grid-template-columns: 1fr;
  }

  #details-toggle {
    margin-left: 0;
  }

  /* The stacked filter block would pin half the viewport if it stayed sticky. */
  .gallery-controls {
    position: static;
  }
}
"""


_FULL_GALLERY_JS = r"""
const cards = [...document.querySelectorAll('.case-card')];
const search = document.querySelector('#case-search');
const family = document.querySelector('#family-filter');
const kind = document.querySelector('#kind-filter');
const contract = document.querySelector('#contract-filter');
const count = document.querySelector('#visible-count');
const detailsToggle = document.querySelector('#details-toggle');

function applyFilters() {
  const query = search.value.trim().toLowerCase();
  let visible = 0;
  for (const card of cards) {
    const contracts = card.dataset.contracts || '';
    const ok =
      (!query || card.dataset.search.includes(query)) &&
      (family.value === 'all' || card.dataset.family === family.value) &&
      (kind.value === 'all' || card.dataset.kind === kind.value) &&
      (contract.value === 'all' ||
        (contract.value === 'failed' && card.dataset.ok === 'false') ||
        (contract.value !== 'failed' && contracts.includes(contract.value)));
    card.hidden = !ok;
    if (ok) visible += 1;
  }
  count.textContent = `${visible} cases visible`;
}

for (const control of [search, family, kind, contract]) {
  control.addEventListener('input', applyFilters);
}
applyFilters();

detailsToggle.addEventListener('click', () => {
  const open = detailsToggle.getAttribute('aria-pressed') !== 'true';
  detailsToggle.setAttribute('aria-pressed', String(open));
  detailsToggle.textContent = open ? 'Hide QA details' : 'Show QA details';
  for (const details of document.querySelectorAll('.case-details')) {
    details.open = open;
  }
});
"""
