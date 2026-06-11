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
