"""Checked-in metric baseline for the primitive fixture suite.

The fixture contracts gate hard failures, but their budgets are upper
bounds: a case can drift from excellent to barely-passing without tripping
anything, and a semantic flip inside an allowed kind set (``rect`` to
``quad``) stays silent. The baseline pins the exact current outcome of every
case so any movement, better or worse, shows up as a reviewable diff.

Workflow: ``primitive-check --baseline`` compares and fails on any drift;
after an intentional change run ``primitive-check --update-baseline`` and
commit the regenerated file, so the movement is visible in the pull request.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DEFAULT_BASELINE_PATH = Path("tests/data/primitive-baseline.json")
BASELINE_SCHEMA_VERSION = 1

# Absolute drift below this is treated as environment noise (for example a
# Pillow upgrade nudging anti-aliased rasterization), not as a change.
DEFAULT_METRIC_TOLERANCE = 0.002

_METRIC_KEYS = (
    ("l1", ("metrics", "raster_l1_error")),
    ("edge", ("metrics", "raster_edge_error")),
    ("svg_l1", ("svg_metrics", "svg_raster_l1_error")),
    ("svg_edge", ("svg_metrics", "svg_raster_edge_error")),
    ("bbox_iou", ("geometry", "bbox_iou")),
)


def baseline_snapshot(report: dict[str, Any]) -> dict[str, Any]:
    """Extract the per-case outcome worth pinning from a full report."""

    cases: dict[str, Any] = {}
    for case in report.get("cases", []):
        entry: dict[str, Any] = {
            "ok": bool(case.get("ok")),
            "kind": case.get("actual_kind"),
            "anchor_count": int(case.get("anchor_count", 0)),
            "anchor_kind_counts": dict(case.get("anchor_kind_counts", {})),
        }
        for name, (section, key) in _METRIC_KEYS:
            value = (case.get(section) or {}).get(key)
            if isinstance(value, (int, float)):
                entry[name] = round(float(value), 6)
        cases[str(case.get("id"))] = entry
    return {
        "schema_version": BASELINE_SCHEMA_VERSION,
        "case_count": len(cases),
        "cases": dict(sorted(cases.items())),
    }


def write_baseline(
    report: dict[str, Any],
    *,
    path: str | Path = DEFAULT_BASELINE_PATH,
) -> Path:
    baseline_path = Path(path)
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    baseline_path.write_text(
        json.dumps(baseline_snapshot(report), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return baseline_path


def load_baseline(path: str | Path = DEFAULT_BASELINE_PATH) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def compare_to_baseline(
    report: dict[str, Any],
    baseline: dict[str, Any],
    *,
    metric_tolerance: float = DEFAULT_METRIC_TOLERANCE,
) -> dict[str, Any]:
    """Diff a fresh report against the pinned baseline.

    Any drift beyond tolerance is a finding: regressions and improvements
    both require a deliberate baseline update, otherwise the baseline decays
    into a stale upper bound and quiet back-sliding becomes invisible again.
    """

    current = baseline_snapshot(report)["cases"]
    pinned = baseline.get("cases", {})

    added = sorted(set(current) - set(pinned))
    removed = sorted(set(pinned) - set(current))
    regressions: list[dict[str, Any]] = []
    improvements: list[dict[str, Any]] = []

    for case_id in sorted(set(current) & set(pinned)):
        now = current[case_id]
        was = pinned[case_id]
        if now["ok"] != was["ok"]:
            regressions.append(
                {
                    "id": case_id,
                    "field": "ok",
                    "was": was["ok"],
                    "now": now["ok"],
                }
            )
        for field in ("kind", "anchor_count", "anchor_kind_counts"):
            if now.get(field) != was.get(field):
                regressions.append(
                    {
                        "id": case_id,
                        "field": field,
                        "was": was.get(field),
                        "now": now.get(field),
                    }
                )
        for name, _ in _METRIC_KEYS:
            if name not in now or name not in was:
                continue
            delta = float(now[name]) - float(was[name])
            if abs(delta) <= metric_tolerance:
                continue
            worse = delta > 0 if name != "bbox_iou" else delta < 0
            finding = {
                "id": case_id,
                "field": name,
                "was": was[name],
                "now": now[name],
                "delta": round(delta, 6),
            }
            (regressions if worse else improvements).append(finding)

    return {
        "ok": not (added or removed or regressions or improvements),
        "metric_tolerance": metric_tolerance,
        "added_cases": added,
        "removed_cases": removed,
        "regressions": regressions,
        "improvements": improvements,
    }


def render_baseline_diff_markdown(diff: dict[str, Any]) -> str:
    if diff.get("ok"):
        return "primitive baseline: no drift\n"
    lines = ["primitive baseline drift detected:"]
    for case_id in diff.get("added_cases", []):
        lines.append(f"  added case {case_id} (update the baseline)")
    for case_id in diff.get("removed_cases", []):
        lines.append(f"  removed case {case_id} (update the baseline)")
    for finding in diff.get("regressions", []):
        lines.append(
            f"  regression {finding['id']}.{finding['field']}: "
            f"{finding['was']} -> {finding['now']}"
        )
    for finding in diff.get("improvements", []):
        lines.append(
            f"  improvement {finding['id']}.{finding['field']}: "
            f"{finding['was']} -> {finding['now']} (update the baseline)"
        )
    lines.append(
        "run `morphea primitive-check --update-baseline` after reviewing and "
        "commit the regenerated baseline"
    )
    return "\n".join(lines) + "\n"
