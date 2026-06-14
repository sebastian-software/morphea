"""Static HTML review gallery rendering for curated promotion artifacts."""

from __future__ import annotations

from html import escape
import os
from pathlib import Path
from typing import Any


PROMOTION_REVIEW_DECISIONS = ("accepted", "corrected", "rejected", "deferred")

_REVIEW_GALLERY_CSS = """
:root {
  color-scheme: light;
  --bg: #f7f8fb;
  --panel: #ffffff;
  --ink: #17202f;
  --muted: #667085;
  --line: #d9dee7;
  --green: #0f7a4f;
  --yellow: #9a6700;
  --red: #b42318;
  --blue: #175cd3;
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  background: var(--bg);
  color: var(--ink);
  font: 14px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}

a {
  color: var(--blue);
  text-decoration: none;
}

a:hover {
  text-decoration: underline;
}

.page-header {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 24px;
  align-items: end;
  padding: 28px clamp(18px, 4vw, 48px) 18px;
  border-bottom: 1px solid var(--line);
  background: var(--panel);
}

.eyebrow {
  margin: 0 0 6px;
  color: var(--muted);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0;
  text-transform: uppercase;
}

h1,
h2,
p {
  margin-top: 0;
}

h1 {
  margin-bottom: 8px;
  font-size: 30px;
  line-height: 1.1;
}

h2 {
  margin-bottom: 0;
  font-size: 18px;
  line-height: 1.25;
}

.lede {
  margin-bottom: 0;
  color: var(--muted);
  overflow-wrap: anywhere;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(74px, 1fr));
  gap: 8px;
  margin: 0;
}

.summary-grid div {
  min-width: 74px;
  padding: 10px 12px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: #fbfcff;
}

dt {
  color: var(--muted);
  font-size: 12px;
}

dd {
  margin: 0;
  font-weight: 700;
}

.status-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
  padding: 14px clamp(18px, 4vw, 48px);
  border-bottom: 1px solid var(--line);
  background: #eef3f8;
}

.chip,
.queue-badge {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 3px 8px;
  border-radius: 999px;
  border: 1px solid var(--line);
  background: #fff;
  color: var(--muted);
  font-size: 12px;
  font-weight: 700;
}

.chip.green {
  border-color: #abefc6;
  color: var(--green);
}

.chip.yellow {
  border-color: #fedf89;
  color: var(--yellow);
}

.chip.red {
  border-color: #fecdca;
  color: var(--red);
}

.queue-badge {
  background: #eff8ff;
  border-color: #b2ddff;
  color: var(--blue);
}

.text-link {
  font-weight: 700;
}

.gallery-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 16px;
  padding: 20px clamp(18px, 4vw, 48px) 44px;
}

.case-card {
  overflow: hidden;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--panel);
  box-shadow: 0 1px 2px rgba(16, 24, 40, 0.06);
}

.case-card.red {
  border-top: 4px solid var(--red);
}

.case-card.yellow {
  border-top: 4px solid var(--yellow);
}

.case-card.green {
  border-top: 4px solid var(--green);
}

.case-visual {
  min-height: 210px;
  border-bottom: 1px solid var(--line);
  background: #f2f4f7;
}

.case-visual img {
  display: block;
  width: 100%;
  height: auto;
}

.missing-visual,
.empty-state {
  padding: 24px;
  color: var(--muted);
}

.case-body {
  padding: 14px;
}

.case-title-row,
.link-row,
.template-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.case-title-row {
  margin-bottom: 12px;
}

.case-facts {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  margin: 0 0 12px;
}

.case-facts div {
  min-width: 0;
  padding: 8px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: #fbfcff;
}

.case-facts dd {
  overflow-wrap: anywhere;
}

.tag-line {
  margin-bottom: 8px;
  color: var(--muted);
}

code {
  display: inline-block;
  margin: 2px 3px 2px 0;
  padding: 2px 5px;
  border-radius: 5px;
  background: #eef2f6;
  color: #344054;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12px;
}

.link-row,
.template-row {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid var(--line);
}

.link-row a,
.template-row a {
  padding: 5px 8px;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: #fff;
  font-weight: 700;
}

.muted {
  color: var(--muted);
}

.command-panel {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid var(--line);
}

.command-panel summary {
  cursor: pointer;
  color: var(--blue);
  font-weight: 700;
}

.command-panel dl {
  margin: 10px 0 0;
}

.command-panel div {
  margin-top: 8px;
}

.command-panel code {
  display: block;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}

@media (max-width: 760px) {
  .page-header {
    grid-template-columns: 1fr;
  }

  .summary-grid,
  .case-facts {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
"""


def render_review_gallery_html(
    report: dict[str, Any],
    packet: dict[str, object],
    *,
    html_path: Path,
) -> str:
    raw_cases = report.get("cases", [])
    cases = [
        case
        for case in _promotion_sorted_cases(
            raw_cases if isinstance(raw_cases, list) else []
        )
        if isinstance(case, dict) and isinstance(case.get("promotion"), dict)
    ]
    packet_cases = packet.get("cases", [])
    queued_case_ids = {
        str(case.get("case_id"))
        for case in packet_cases
        if isinstance(case, dict) and isinstance(case.get("case_id"), str)
    }
    packet_cases_by_id = {
        str(case.get("case_id")): case
        for case in packet_cases
        if isinstance(case, dict) and isinstance(case.get("case_id"), str)
    }
    label_counts = _review_gallery_label_counts(cases)
    decision_counts = _review_gallery_decision_counts(cases)
    cards = "\n".join(
        _render_review_gallery_case_card(
            case,
            html_path=html_path,
            queued=case.get("id") in queued_case_ids,
            packet_case=packet_cases_by_id.get(str(case.get("id"))),
        )
        for case in cases
    )
    if not cards:
        cards = '<p class="empty-state">No promotion cases in this suite run.</p>'
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Morphēa review gallery</title>
    <style>
{_REVIEW_GALLERY_CSS}
    </style>
  </head>
  <body>
    <header class="page-header">
      <div>
        <p class="eyebrow">Curated promotion review</p>
        <h1>Morphēa review gallery</h1>
        <p class="lede">{_html(str(report.get("suite", "n/a")))}</p>
      </div>
      <dl class="summary-grid">
        <div><dt>Cases</dt><dd>{len(cases)}</dd></div>
        <div><dt>Queued</dt><dd>{_html(str(packet.get("case_count", 0)))}</dd></div>
        <div><dt>Deferred</dt><dd>{_html(str(decision_counts.get("deferred", 0)))}</dd></div>
        <div><dt>Rejected</dt><dd>{_html(str(decision_counts.get("rejected", 0)))}</dd></div>
      </dl>
    </header>

    <section class="status-strip" aria-label="Quality labels">
      <span class="chip green">green {_html(str(label_counts.get("green", 0)))}</span>
      <span class="chip yellow">yellow {_html(str(label_counts.get("yellow", 0)))}</span>
      <span class="chip red">red {_html(str(label_counts.get("red", 0)))}</span>
      <a class="text-link" href="review-packet.md">review packet</a>
      <a class="text-link" href="review-packet.json">review packet JSON</a>
    </section>

    <main class="gallery-grid">
{cards}
    </main>
  </body>
</html>
"""


def _render_review_gallery_case_card(
    case: dict[str, Any],
    *,
    html_path: Path,
    queued: bool,
    packet_case: dict[str, object] | None = None,
) -> str:
    case_id = str(case.get("id", "n/a"))
    promotion = case.get("promotion", {})
    promotion = promotion if isinstance(promotion, dict) else {}
    summary = case.get("promotion_summary", {})
    summary = summary if isinstance(summary, dict) else {}
    review = case.get("editability_review", {})
    review = review if isinstance(review, dict) else {}
    artifacts = case.get("artifacts", {})
    artifacts = artifacts if isinstance(artifacts, dict) else {}
    quality = str(promotion.get("current_quality_label", "n/a"))
    quality_class = _review_gallery_quality_class(quality)
    failed_gates = _failed_gate_ids(case.get("promotion_gates"))
    failed_components = _failed_component_ids(review.get("failed_components"))
    contact_sheet = _review_gallery_image(
        artifacts.get("contact_sheet"),
        html_path=html_path,
        alt=f"Contact sheet for {case_id}",
    )
    links = _review_gallery_artifact_links(
        artifacts,
        html_path=html_path,
        keys=(
            ("promotion_review", "Promotion review"),
            ("editability_review", "Editability review"),
            ("review_decision", "Pending decision"),
            ("promotion_export", "Promotion export"),
            ("manifest", "Manifest"),
        ),
    )
    template_links = _review_gallery_template_links(
        artifacts.get("review_templates"),
        html_path=html_path,
    )
    review_commands = _review_gallery_review_commands(packet_case)
    queue_badge = '<span class="queue-badge">review queue</span>' if queued else ""
    return f"""      <article class="case-card {quality_class}">
        <div class="case-visual">{contact_sheet}</div>
        <div class="case-body">
          <div class="case-title-row">
            <h2>{_html(case_id)}</h2>
            <span class="chip {quality_class}">{_html(quality)}</span>
            {queue_badge}
          </div>
          <dl class="case-facts">
            <div><dt>Promotion</dt><dd>{_html(str(summary.get("decision", "n/a")))}</dd></div>
            <div><dt>Editability</dt><dd>{_html(str(review.get("decision", "n/a")))}</dd></div>
            <div><dt>Suggested</dt><dd>{_html(str(_case_suggested_review_decision(case)))}</dd></div>
            <div><dt>Status</dt><dd>{_html(str(case.get("status", "n/a")))}</dd></div>
          </dl>
          <p class="tag-line"><strong>Issues</strong> {_html_list(_promotion_issue_tags(promotion))}</p>
          <p class="tag-line"><strong>Failed gates</strong> {_html_list(failed_gates)}</p>
          <p class="tag-line"><strong>Failed components</strong> {_html_list(failed_components)}</p>
          <div class="link-row">{links}</div>
          <div class="template-row">{template_links}</div>
          {review_commands}
        </div>
      </article>"""


def _promotion_sorted_cases(cases: object) -> list[dict[str, Any]]:
    if not isinstance(cases, list):
        return []
    sortable = [case for case in cases if isinstance(case, dict)]
    return sorted(sortable, key=_promotion_case_sort_key)


def _promotion_case_sort_key(case: dict[str, Any]) -> tuple[int, str]:
    summary = case.get("promotion_summary", {})
    if not isinstance(summary, dict):
        return (3, str(case.get("id", "")))
    if int(summary.get("red_gate_count", 0)) > 0:
        return (0, str(case.get("id", "")))
    if int(summary.get("yellow_gate_count", 0)) > 0:
        return (1, str(case.get("id", "")))
    return (2, str(case.get("id", "")))


def _case_suggested_review_decision(case: dict[str, Any]) -> str:
    decision = case.get("review_decision")
    if isinstance(decision, dict):
        return str(decision.get("suggested_decision", "n/a"))
    return "n/a"


def _review_gallery_label_counts(cases: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"green": 0, "yellow": 0, "red": 0}
    for case in cases:
        promotion = case.get("promotion", {})
        if isinstance(promotion, dict):
            label = str(promotion.get("current_quality_label", "n/a"))
            counts[label] = counts.get(label, 0) + 1
    return dict(sorted(counts.items()))


def _review_gallery_quality_class(value: str) -> str:
    return value if value in {"green", "yellow", "red"} else "unknown"


def _review_gallery_decision_counts(cases: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for case in cases:
        summary = case.get("promotion_summary", {})
        if isinstance(summary, dict):
            decision = str(summary.get("decision", "n/a"))
            counts[decision] = counts.get(decision, 0) + 1
    return dict(sorted(counts.items()))


def _failed_gate_ids(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [
        str(gate.get("id", "n/a"))
        for gate in value
        if isinstance(gate, dict) and not gate.get("ok", False)
    ]


def _failed_component_ids(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [
        str(component.get("id", "n/a"))
        for component in value
        if isinstance(component, dict)
    ]


def _promotion_issue_tags(promotion: dict[str, object]) -> list[str]:
    issues = promotion.get("current_issues", [])
    if not isinstance(issues, list):
        return []
    return sorted({str(issue) for issue in issues if isinstance(issue, str) and issue})


def _review_gallery_image(value: object, *, html_path: Path, alt: str) -> str:
    if not isinstance(value, str) or not value:
        return '<div class="missing-visual">No contact sheet</div>'
    uri = _review_gallery_uri(value, html_path=html_path)
    return f'<img src="{_html(uri)}" alt="{_html(alt)}" loading="lazy">'


def _review_gallery_artifact_links(
    artifacts: dict[str, object],
    *,
    html_path: Path,
    keys: tuple[tuple[str, str], ...],
) -> str:
    links: list[str] = []
    for key, label in keys:
        value = artifacts.get(key)
        if not isinstance(value, str) or not value:
            continue
        uri = _review_gallery_uri(value, html_path=html_path)
        links.append(f'<a href="{_html(uri)}">{_html(label)}</a>')
    if not links:
        return '<span class="muted">No links</span>'
    return "\n            ".join(links)


def _review_gallery_template_links(value: object, *, html_path: Path) -> str:
    if not isinstance(value, dict) or not value:
        return '<span class="muted">No decision templates</span>'
    links: list[str] = []
    for decision in PROMOTION_REVIEW_DECISIONS:
        path = value.get(decision)
        if not isinstance(path, str) or not path:
            continue
        uri = _review_gallery_uri(path, html_path=html_path)
        links.append(f'<a href="{_html(uri)}">{_html(decision)}</a>')
    if not links:
        return '<span class="muted">No decision templates</span>'
    return "\n            ".join(links)


def _review_gallery_review_commands(packet_case: object) -> str:
    if not isinstance(packet_case, dict):
        return ""
    commands = packet_case.get("review_commands")
    if not isinstance(commands, dict) or not commands:
        return ""
    rows: list[str] = []
    for decision in PROMOTION_REVIEW_DECISIONS:
        command = commands.get(decision)
        if not isinstance(command, str) or not command:
            continue
        rows.append(
            "              "
            f"<div><dt>{_html(decision)}</dt>"
            f"<dd><code>{_html(command)}</code></dd></div>"
        )
    if not rows:
        return ""
    return (
        '<details class="command-panel">'
        "<summary>Apply commands</summary>"
        "<dl>\n"
        + "\n".join(rows)
        + "\n            </dl></details>"
    )


def _review_gallery_uri(value: str, *, html_path: Path) -> str:
    target = Path(value)
    if not target.is_absolute():
        target = Path.cwd() / target
    base_dir = html_path.parent
    if not base_dir.is_absolute():
        base_dir = Path.cwd() / base_dir
    return Path(os.path.relpath(target, base_dir)).as_posix()


def _html(value: object) -> str:
    return escape(str(value), quote=True)


def _html_list(values: object) -> str:
    if not isinstance(values, list) or not values:
        return '<span class="muted">none</span>'
    return " ".join(
        f"<code>{_html(value)}</code>"
        for value in values
        if isinstance(value, str) and value
    ) or '<span class="muted">none</span>'
