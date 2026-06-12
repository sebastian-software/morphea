"""Comparison helpers for saved experiment snapshots."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
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


def compare_segment_manifests(
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
    comparison = render_segment_manifest_comparison(
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
            render_segment_manifest_comparison_markdown(comparison),
            encoding="utf-8",
        )
    return comparison


def compare_git_snapshots(
    before_ref: str,
    after_ref: str,
    *,
    snapshot_path: str | Path,
    output: str | Path,
    markdown: str | Path | None = None,
    repo: str | Path = ".",
) -> dict[str, Any]:
    snapshot = str(snapshot_path)
    before_data = _git_show_json(repo, before_ref, snapshot)
    after_data = _git_show_json(repo, after_ref, snapshot)
    comparison = render_snapshot_comparison(
        before_data,
        after_data,
        before=f"{before_ref}:{snapshot}",
        after=f"{after_ref}:{snapshot}",
    )
    comparison["git"] = {
        "repo": str(repo),
        "before_ref": before_ref,
        "after_ref": after_ref,
        "snapshot_path": snapshot,
    }
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


def render_segment_manifest_comparison(
    before_data: dict[str, Any],
    after_data: dict[str, Any],
    *,
    before: str,
    after: str,
) -> dict[str, Any]:
    before_proposals = _index_by_id(_list_value(before_data.get("proposals")))
    after_proposals = _index_by_id(_list_value(after_data.get("proposals")))
    before_groups = _index_by_id(_list_value(before_data.get("proposal_groups")))
    after_groups = _index_by_id(_list_value(after_data.get("proposal_groups")))
    shared_ids = sorted(set(before_proposals) & set(after_proposals))
    proposal_changes = []
    for proposal_id in shared_ids:
        changes = _proposal_field_changes(
            before_proposals[proposal_id],
            after_proposals[proposal_id],
        )
        if changes:
            proposal_changes.append({"id": proposal_id, "changes": changes})
    shared_group_ids = sorted(set(before_groups) & set(after_groups))
    group_changes = []
    for group_id in shared_group_ids:
        changes = _proposal_group_changes(
            before_groups[group_id],
            after_groups[group_id],
        )
        if changes:
            group_changes.append({"id": group_id, "changes": changes})

    return {
        "schema_version": 1,
        "before": before,
        "after": after,
        "before_source": _backend_source(before_data),
        "after_source": _backend_source(after_data),
        "before_proposal_count": int(before_data.get("proposal_count", 0)),
        "after_proposal_count": int(after_data.get("proposal_count", 0)),
        "proposal_count_delta": int(after_data.get("proposal_count", 0))
        - int(before_data.get("proposal_count", 0)),
        "shared_proposal_count": len(shared_ids),
        "added_ids": sorted(set(after_proposals) - set(before_proposals)),
        "removed_ids": sorted(set(before_proposals) - set(after_proposals)),
        "shared_group_count": len(shared_group_ids),
        "added_group_ids": sorted(set(after_groups) - set(before_groups)),
        "removed_group_ids": sorted(set(before_groups) - set(after_groups)),
        "summary_deltas": _summary_count_deltas(
            _dict_value(before_data.get("summary")),
            _dict_value(after_data.get("summary")),
        ),
        "config_deltas": _config_deltas(
            _dict_value(before_data.get("config")),
            _dict_value(after_data.get("config")),
        ),
        "proposal_changes": proposal_changes,
        "proposal_group_changes": group_changes,
    }


def render_segment_manifest_comparison_markdown(
    comparison: dict[str, Any],
) -> str:
    lines = [
        "# Curve Segment Manifest Comparison",
        "",
        f"- Before: `{comparison.get('before')}`",
        f"- After: `{comparison.get('after')}`",
        "- Sources: "
        f"`{comparison.get('before_source')}` -> "
        f"`{comparison.get('after_source')}`",
        f"- Proposal count delta: `{comparison.get('proposal_count_delta', 0)}`",
        f"- Shared proposals: `{comparison.get('shared_proposal_count', 0)}`",
        f"- Added: {_id_list(comparison.get('added_ids', []))}",
        f"- Removed: {_id_list(comparison.get('removed_ids', []))}",
        f"- Shared groups: `{comparison.get('shared_group_count', 0)}`",
        f"- Added groups: {_id_list(comparison.get('added_group_ids', []))}",
        f"- Removed groups: {_id_list(comparison.get('removed_group_ids', []))}",
        "",
        "## Summary Deltas",
        "",
        "| Group | Key | Before | After | Delta |",
        "| --- | --- | ---: | ---: | ---: |",
    ]
    summary_deltas = _list_value(comparison.get("summary_deltas"))
    if summary_deltas:
        for delta in summary_deltas:
            lines.append(
                "| "
                f"`{delta.get('group')}` | `{delta.get('key')}` | "
                f"{_fmt(delta.get('before'))} | "
                f"{_fmt(delta.get('after'))} | "
                f"{_fmt(delta.get('delta'))} |"
            )
    else:
        lines.append("| n/a | n/a | n/a | n/a | n/a |")

    lines.extend(["", "## Proposal Changes", ""])
    lines.extend(
        [
            "| Proposal | Field | Before | After |",
            "| --- | --- | --- | --- |",
        ]
    )
    change_count = 0
    for proposal in _list_value(comparison.get("proposal_changes")):
        for change in _list_value(proposal.get("changes")):
            change_count += 1
            lines.append(
                "| "
                f"`{proposal.get('id')}` | `{change.get('field')}` | "
                f"`{change.get('before')}` | `{change.get('after')}` |"
            )
    if change_count == 0:
        lines.append("| n/a | n/a | n/a | n/a |")

    lines.extend(["", "## Proposal Group Changes", ""])
    lines.extend(
        [
            "| Group | Field | Before | After |",
            "| --- | --- | --- | --- |",
        ]
    )
    group_change_count = 0
    for group in _list_value(comparison.get("proposal_group_changes")):
        for change in _list_value(group.get("changes")):
            group_change_count += 1
            lines.append(
                "| "
                f"`{group.get('id')}` | `{change.get('field')}` | "
                f"`{change.get('before')}` | `{change.get('after')}` |"
            )
    if group_change_count == 0:
        lines.append("| n/a | n/a | n/a | n/a |")

    return "\n".join(lines) + "\n"


def generate_git_curated_snapshot(
    ref: str,
    *,
    suite: str | Path,
    output: str | Path,
    report: str | Path | None = None,
    output_dir: str | Path | None = None,
    repo: str | Path = ".",
    run: bool = True,
    timeout_seconds: float = 120.0,
) -> dict[str, Any]:
    """Generate a curated snapshot for a git ref in an isolated worktree."""

    repo_path = Path(repo)
    repo_root = _git_repo_root(repo_path)
    suite_arg = _suite_arg_for_worktree(suite, repo_root)
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report_path = Path(report) if report is not None else None
    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
    if output_dir is not None:
        Path(output_dir).mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="curve-git-snapshot-") as temp_dir:
        worktree = Path(temp_dir) / "worktree"
        _run_subprocess(
            ["git", "worktree", "add", "--detach", str(worktree), ref],
            cwd=repo_root,
            timeout=30,
        )
        try:
            generated_report = report_path or Path(temp_dir) / "report.json"
            command = [
                sys.executable,
                "-m",
                "curve.cli",
                "curated-check",
                str(suite_arg),
                "-o",
                str(generated_report),
                "--snapshot",
                str(output_path),
            ]
            if output_dir is not None:
                command.extend(["--output-dir", str(output_dir)])
            if run:
                command.append("--run")
            _run_subprocess(
                command,
                cwd=worktree,
                timeout=timeout_seconds,
                env=_worktree_python_env(worktree),
            )
        finally:
            _run_subprocess(
                ["git", "worktree", "remove", "--force", str(worktree)],
                cwd=repo_root,
                timeout=30,
                check=False,
            )
            if worktree.exists():
                shutil.rmtree(worktree, ignore_errors=True)

    snapshot = json.loads(output_path.read_text(encoding="utf-8"))
    if not isinstance(snapshot, dict):
        raise ValueError(f"generated snapshot at {output_path} must be a JSON object")
    result = {
        "schema_version": 1,
        "git": {
            "repo": str(repo_root),
            "ref": ref,
            "suite": str(suite),
        },
        "snapshot": str(output_path),
        "run": run,
        "case_count": snapshot.get("case_count", 0),
        "ok": snapshot.get("ok", False),
    }
    if report_path is not None:
        result["report"] = str(report_path)
    if output_dir is not None:
        result["output_dir"] = str(output_dir)
    return result


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


def _backend_source(data: dict[str, Any]) -> str:
    backend = data.get("backend")
    if isinstance(backend, dict):
        return str(backend.get("source", "unknown"))
    return "unknown"


def _summary_count_deltas(
    before: dict[str, Any],
    after: dict[str, Any],
) -> list[dict[str, Any]]:
    deltas = []
    groups = sorted(set(before) | set(after))
    for group in groups:
        before_raw = before.get(group)
        after_raw = after.get(group)
        if _is_number(before_raw) or _is_number(after_raw):
            before_value = _number_or_zero(before_raw)
            after_value = _number_or_zero(after_raw)
            if before_value != after_value:
                deltas.append(
                    {
                        "group": group,
                        "key": "value",
                        "before": before_value,
                        "after": after_value,
                        "delta": after_value - before_value,
                    }
                )
            continue
        before_counts = _dict_value(before.get(group))
        after_counts = _dict_value(after.get(group))
        for key in sorted(set(before_counts) | set(after_counts)):
            before_value = _number_or_zero(before_counts.get(key))
            after_value = _number_or_zero(after_counts.get(key))
            if before_value == after_value:
                continue
            deltas.append(
                {
                    "group": group,
                    "key": key,
                    "before": before_value,
                    "after": after_value,
                    "delta": after_value - before_value,
                }
            )
    return deltas


def _config_deltas(
    before: dict[str, Any],
    after: dict[str, Any],
) -> list[dict[str, Any]]:
    deltas = []
    for key in sorted(set(before) | set(after)):
        before_value = before.get(key)
        after_value = after.get(key)
        if before_value == after_value:
            continue
        deltas.append(
            {
                "key": key,
                "before": before_value,
                "after": after_value,
            }
        )
    return deltas


def _proposal_field_changes(
    before: dict[str, Any],
    after: dict[str, Any],
) -> list[dict[str, Any]]:
    fields = (
        "source",
        "confidence",
        "status",
        "downstream_status",
        "rejection_reason",
        "anchor_kind",
        "anchor_parameter_count",
        "anchor_reserved",
        "reservation_reason",
        "anchor_quality_error",
        "downstream_decision_reason",
    )
    changes = []
    for field in fields:
        before_value = before.get(field)
        after_value = after.get(field)
        if before_value == after_value:
            continue
        changes.append(
            {
                "field": field,
                "before": before_value,
                "after": after_value,
            }
        )
    if before.get("bounds") != after.get("bounds"):
        changes.append(
            {
                "field": "bounds",
                "before": before.get("bounds"),
                "after": after.get("bounds"),
            }
        )
    return changes


def _proposal_group_changes(
    before: dict[str, Any],
    after: dict[str, Any],
) -> list[dict[str, Any]]:
    changes = []
    for field in ("kind", "proposal_ids"):
        before_value = before.get(field)
        after_value = after.get(field)
        if before_value == after_value:
            continue
        changes.append(
            {
                "field": field,
                "before": before_value,
                "after": after_value,
            }
        )

    before_metrics = _flatten_numbers(_dict_value(before.get("metrics")))
    after_metrics = _flatten_numbers(_dict_value(after.get("metrics")))
    for path in sorted(set(before_metrics) | set(after_metrics)):
        before_value = before_metrics.get(path)
        after_value = after_metrics.get(path)
        if before_value == after_value:
            continue
        changes.append(
            {
                "field": f"metrics.{path}",
                "before": before_value,
                "after": after_value,
            }
        )
    return changes


def _index_by_id(items: list[Any]) -> dict[str, dict[str, Any]]:
    indexed = {}
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        item_id = item.get("id", f"item-{index:05d}")
        indexed[str(item_id)] = item
    return indexed


def _list_value(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _dict_value(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _number_or_zero(value: Any) -> float:
    if _is_number(value):
        return float(value)
    return 0.0


def _is_number(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    return isinstance(value, (int, float))


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
    if isinstance(data, list):
        values = {}
        for index, value in enumerate(data):
            item_id = value.get("id") if isinstance(value, dict) else None
            key = str(item_id) if isinstance(item_id, str) else str(index)
            next_prefix = f"{prefix}.{key}" if prefix else key
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


def _git_show_json(repo: str | Path, ref: str, snapshot_path: str) -> dict[str, Any]:
    result = _run_subprocess(
        ["git", "show", f"{ref}:{snapshot_path}"],
        cwd=repo,
        timeout=5,
    )
    data = json.loads(result.stdout)
    if not isinstance(data, dict):
        raise ValueError(f"snapshot at {ref}:{snapshot_path} must be a JSON object")
    return data


def _git_repo_root(repo: str | Path) -> Path:
    result = _run_subprocess(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=repo,
        timeout=5,
    )
    return Path(result.stdout.strip())


def _suite_arg_for_worktree(suite: str | Path, repo_root: Path) -> Path:
    suite_path = Path(suite)
    if not suite_path.is_absolute():
        return suite_path
    try:
        return suite_path.relative_to(repo_root)
    except ValueError:
        return suite_path


def _worktree_python_env(worktree: Path) -> dict[str, str]:
    env = dict(os.environ)
    src_path = str(worktree / "src")
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = f"{src_path}{os.pathsep}{existing}" if existing else src_path
    return env


def _run_subprocess(
    command: list[str],
    *,
    cwd: str | Path,
    timeout: float,
    check: bool = True,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        check=check,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )
