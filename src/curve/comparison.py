"""Comparison helpers for saved experiment snapshots."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def compare_snapshots(
    before: str | Path,
    after: str | Path,
    *,
    output: str | Path,
    markdown: str | Path | None = None,
) -> dict[str, Any]:
    before_path = Path(before)
    after_path = Path(after)
    before_data = json.loads(before_path.read_text(encoding="utf-8"))
    after_data = json.loads(after_path.read_text(encoding="utf-8"))
    comparison = render_snapshot_comparison(
        before_data,
        after_data,
        before=str(before_path),
        after=str(after_path),
    )
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(comparison, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    if markdown is not None:
        markdown_path = Path(markdown)
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(
            render_snapshot_comparison_markdown(comparison),
            encoding="utf-8",
        )
    return comparison


def render_snapshot_comparison(
    before_data: dict[str, Any],
    after_data: dict[str, Any],
    *,
    before: str,
    after: str,
) -> dict[str, Any]:
    before_items, item_kind = _indexed_items(before_data)
    after_items, _ = _indexed_items(after_data)
    shared_ids = sorted(set(before_items) & set(after_items))
    added_ids = sorted(set(after_items) - set(before_items))
    removed_ids = sorted(set(before_items) - set(after_items))
    items = []
    for item_id in shared_ids:
        deltas = _numeric_deltas(before_items[item_id], after_items[item_id])
        changed = [delta for delta in deltas if delta["delta"] != 0.0]
        items.append(
            {
                "id": item_id,
                "changed_metric_count": len(changed),
                "metric_deltas": changed,
            }
        )

    return {
        "schema_version": 1,
        "before": before,
        "after": after,
        "item_kind": item_kind,
        "item_count": len(shared_ids),
        "added_ids": added_ids,
        "removed_ids": removed_ids,
        "items": items,
    }


def render_snapshot_comparison_markdown(comparison: dict[str, Any]) -> str:
    lines = [
        "# Curve Snapshot Comparison",
        "",
        f"- Before: `{comparison.get('before')}`",
        f"- After: `{comparison.get('after')}`",
        f"- Compared {comparison.get('item_count', 0)} `{comparison.get('item_kind')}` items",
        "",
        "## Changed Metrics",
        "",
        "| Item | Metric | Before | After | Delta |",
        "| --- | --- | ---: | ---: | ---: |",
    ]
    change_count = 0
    for item in comparison.get("items", []):
        for delta in item.get("metric_deltas", []):
            change_count += 1
            lines.append(
                "| "
                f"`{item.get('id')}` | `{delta.get('path')}` | "
                f"{_fmt(delta.get('before'))} | "
                f"{_fmt(delta.get('after'))} | "
                f"{_fmt(delta.get('delta'))} |"
            )
    if change_count == 0:
        lines.append("| n/a | n/a | n/a | n/a | n/a |")

    lines.extend(["", "## Added / Removed", ""])
    lines.append(f"- Added: {_id_list(comparison.get('added_ids', []))}")
    lines.append(f"- Removed: {_id_list(comparison.get('removed_ids', []))}")
    return "\n".join(lines) + "\n"


def _indexed_items(data: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], str]:
    if isinstance(data.get("cases"), list):
        return _index_by_id(data["cases"]), "cases"
    if isinstance(data.get("runs"), list):
        return _index_by_id(data["runs"]), "runs"
    return {"root": data}, "root"


def _index_by_id(items: list[Any]) -> dict[str, dict[str, Any]]:
    indexed = {}
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        item_id = item.get("id", f"item-{index:05d}")
        indexed[str(item_id)] = item
    return indexed


def _numeric_deltas(
    before: dict[str, Any],
    after: dict[str, Any],
) -> list[dict[str, Any]]:
    before_values = _flatten_numbers(before)
    after_values = _flatten_numbers(after)
    deltas = []
    for path in sorted(set(before_values) & set(after_values)):
        before_value = before_values[path]
        after_value = after_values[path]
        deltas.append(
            {
                "path": path,
                "before": before_value,
                "after": after_value,
                "delta": after_value - before_value,
            }
        )
    return deltas


def _flatten_numbers(data: Any, prefix: str = "") -> dict[str, float]:
    if isinstance(data, bool):
        return {}
    if isinstance(data, (int, float)):
        return {prefix: float(data)}
    if isinstance(data, dict):
        values: dict[str, float] = {}
        for key, value in data.items():
            next_prefix = f"{prefix}.{key}" if prefix else str(key)
            values.update(_flatten_numbers(value, next_prefix))
        return values
    return {}


def _fmt(value: Any) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{value:.6g}"
    return "n/a"


def _id_list(values: Any) -> str:
    if not values:
        return "none"
    return ", ".join(f"`{value}`" for value in values)
