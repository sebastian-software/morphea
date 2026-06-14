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


PROMOTION_REGION_DELTA_FIELDS = (
    "state",
    "gate_ok",
    "selected_anchor_count",
    "selected_anchor_indexes",
    "selected_anchor_ids",
    "reason",
    "bounds",
    "expected_kinds",
    "forbidden_kinds",
    "gate_id",
    "gate_type",
    "region_layer_count",
    "layer_roles",
    "layer_role_counts",
    "structural_layer_count",
    "structural_layer_roles",
    "selected_anchor_kind_counts",
    "selected_simple_anchor_count",
    "selected_stroke_anchor_count",
    "selected_generic_path_anchor_count",
)


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
    before_source_summary = _segment_source_summary(before_data, side="before")
    after_source_summary = _segment_source_summary(after_data, side="after")
    source_deltas = _segment_source_deltas(
        before_source_summary,
        after_source_summary,
    )
    promotion_proxy_deltas = _segment_promotion_proxy_deltas(source_deltas)
    downstream_status_deltas = [
        delta
        for delta in source_deltas
        if delta.get("group") == "downstream_status_counts"
    ]
    source_delta_assessment = _segment_source_delta_assessment(source_deltas)
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
        "source_summaries": [before_source_summary, after_source_summary],
        "source_deltas": source_deltas,
        "promotion_proxy_deltas": promotion_proxy_deltas,
        "downstream_status_deltas": downstream_status_deltas,
        "source_delta_assessment": source_delta_assessment,
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
        "# Morphēa Segment Manifest Comparison",
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
        "## Source Assessment",
        "",
    ]
    assessment = _dict_value(comparison.get("source_delta_assessment"))
    if assessment:
        lines.extend(
            [
                f"- Verdict: {_code_cell(assessment.get('verdict'))}",
                (
                    "- Green promotion delta: "
                    f"`{_fmt(assessment.get('green_promotion_delta'))}`"
                ),
                (
                    "- Red candidate delta: "
                    f"`{_fmt(assessment.get('red_candidate_delta'))}`"
                ),
                (
                    "- Manual review delta: "
                    f"`{_fmt(assessment.get('manual_review_delta'))}`"
                ),
                (
                    "- Proposal count delta: "
                    f"`{_fmt(assessment.get('proposal_count_delta'))}`"
                ),
                "- Promotion delta basis: "
                f"{_code_cell(assessment.get('promotion_delta_basis'))}",
                "- Uses region promotion labels: "
                f"`{str(assessment.get('uses_region_promotion_labels', False)).lower()}`",
                f"- Positive signals: {_signal_cell(assessment.get('positive_signals'))}",
                f"- Risk signals: {_signal_cell(assessment.get('risk_signals'))}",
            ]
        )
    else:
        lines.append("- Verdict: `n/a`")

    lines.extend(
        [
            "",
            "## Source Summaries",
            "",
            (
                "| Side | Source | Backend | Adapter | Proposals | "
                "Downstream Status | Anchor Kinds | Reserved Anchors | Groups |"
            ),
            "| --- | --- | --- | --- | ---: | --- | --- | ---: | --- |",
        ]
    )
    source_summaries = _list_value(comparison.get("source_summaries"))
    if source_summaries:
        for summary in source_summaries:
            lines.append(
                "| "
                f"{_code_cell(summary.get('side'))} | "
                f"{_code_cell(summary.get('source'))} | "
                f"{_code_cell(summary.get('backend_status'))} | "
                f"{_code_cell(summary.get('backend_adapter'))} | "
                f"{_fmt(summary.get('proposal_count'))} | "
                f"{_count_cell(summary.get('downstream_status_counts'))} | "
                f"{_count_cell(summary.get('anchor_kind_counts'))} | "
                f"{_fmt(summary.get('reserved_anchor_count'))} | "
                f"{_count_cell(summary.get('proposal_group_counts'))} |"
            )
    else:
        lines.append("| n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |")

    lines.extend(
        [
            "",
            "## Promotion Proxy Deltas",
            "",
            "| Proxy | Downstream status | Before | After | Delta |",
            "| --- | --- | ---: | ---: | ---: |",
        ]
    )
    proxy_deltas = _list_value(comparison.get("promotion_proxy_deltas"))
    if proxy_deltas:
        for delta in proxy_deltas:
            lines.append(
                "| "
                f"`{delta.get('key')}` | "
                f"`{delta.get('source_key')}` | "
                f"{_fmt(delta.get('before'))} | "
                f"{_fmt(delta.get('after'))} | "
                f"{_fmt(delta.get('delta'))} |"
            )
    else:
        lines.append("| n/a | n/a | n/a | n/a | n/a |")

    lines.extend(
        [
            "",
            "## Source Deltas",
            "",
            "| Group | Key | Before | After | Delta |",
            "| --- | --- | ---: | ---: | ---: |",
        ]
    )
    source_deltas = _list_value(comparison.get("source_deltas"))
    if source_deltas:
        for delta in source_deltas:
            lines.append(
                "| "
                f"`{delta.get('group')}` | `{delta.get('key')}` | "
                f"{_fmt(delta.get('before'))} | "
                f"{_fmt(delta.get('after'))} | "
                f"{_fmt(delta.get('delta'))} |"
            )
    else:
        lines.append("| n/a | n/a | n/a | n/a | n/a |")

    lines.extend(
        [
            "",
            "## Summary Deltas",
            "",
            "| Group | Key | Before | After | Delta |",
            "| --- | --- | ---: | ---: | ---: |",
        ]
    )
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

    with tempfile.TemporaryDirectory(prefix="morphea-git-snapshot-") as temp_dir:
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
                "morphea.cli",
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
    promotion_region_deltas = _promotion_region_deltas(before_items, after_items)

    return {
        "schema_version": 1,
        "before": before,
        "after": after,
        "item_kind": item_kind,
        "item_count": len(shared_ids),
        "added_ids": added_ids,
        "removed_ids": removed_ids,
        "items": items,
        "promotion_region_delta_count": len(promotion_region_deltas),
        "promotion_region_deltas": promotion_region_deltas,
    }


def render_snapshot_comparison_markdown(comparison: dict[str, Any]) -> str:
    lines = [
        "# Morphēa Snapshot Comparison",
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

    region_deltas = _list_value(comparison.get("promotion_region_deltas"))
    lines.extend(
        [
            "",
            "## Promotion Region Deltas",
            "",
            "| Case | Region | Status | State | Gate OK | Selected | Reason |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    if region_deltas:
        for delta in region_deltas:
            delta_item = _dict_value(delta)
            state_cell = _transition_cell(
                delta_item.get("before_state"),
                delta_item.get("after_state"),
            )
            gate_cell = _transition_cell(
                delta_item.get("before_gate_ok"),
                delta_item.get("after_gate_ok"),
            )
            before_selected = _selected_summary(delta_item, "before")
            after_selected = _selected_summary(delta_item, "after")
            selected_cell = _transition_cell(before_selected, after_selected)
            reason_cell = _transition_cell(
                delta_item.get("before_reason"),
                delta_item.get("after_reason"),
            )
            lines.append(
                "| "
                f"{_code_cell(delta_item.get('case_id'))} | "
                f"{_code_cell(delta_item.get('region_id'))} | "
                f"{_code_cell(delta_item.get('status'))} | "
                f"{state_cell} | "
                f"{gate_cell} | "
                f"{selected_cell} | "
                f"{reason_cell} |"
            )
    else:
        lines.append("| n/a | n/a | n/a | n/a | n/a | n/a | n/a |")

    lines.extend(["", "## Added / Removed", ""])
    lines.append(f"- Added: {_id_list(comparison.get('added_ids', []))}")
    lines.append(f"- Removed: {_id_list(comparison.get('removed_ids', []))}")
    return "\n".join(lines) + "\n"


def _promotion_region_deltas(
    before_items: dict[str, dict[str, Any]],
    after_items: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    deltas: list[dict[str, Any]] = []
    for item_id in sorted(set(before_items) & set(after_items)):
        before_regions = _promotion_regions_by_id(before_items[item_id])
        after_regions = _promotion_regions_by_id(after_items[item_id])
        shared_region_ids = sorted(set(before_regions) & set(after_regions))
        for region_id in shared_region_ids:
            delta = _promotion_region_delta(
                item_id,
                region_id,
                "changed",
                before_regions[region_id],
                after_regions[region_id],
            )
            if delta["changes"]:
                deltas.append(delta)
        for region_id in sorted(set(after_regions) - set(before_regions)):
            deltas.append(
                _promotion_region_delta(
                    item_id,
                    region_id,
                    "added",
                    None,
                    after_regions[region_id],
                )
            )
        for region_id in sorted(set(before_regions) - set(after_regions)):
            deltas.append(
                _promotion_region_delta(
                    item_id,
                    region_id,
                    "removed",
                    before_regions[region_id],
                    None,
                )
            )
    return deltas


def _promotion_regions_by_id(item: dict[str, Any]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for index, region in enumerate(_list_value(item.get("promotion_regions"))):
        if not isinstance(region, dict):
            continue
        region_id = (
            region.get("id")
            or region.get("region_id")
            or region.get("gate_id")
            or f"region-{index:05d}"
        )
        indexed[str(region_id)] = region
    return indexed


def _promotion_region_delta(
    case_id: str,
    region_id: str,
    status: str,
    before_region: dict[str, Any] | None,
    after_region: dict[str, Any] | None,
) -> dict[str, Any]:
    changes = []
    for field in PROMOTION_REGION_DELTA_FIELDS:
        before_value = _region_field(before_region, field)
        after_value = _region_field(after_region, field)
        if before_value != after_value:
            changes.append(
                {
                    "field": field,
                    "before": before_value,
                    "after": after_value,
                }
            )
    return {
        "case_id": case_id,
        "region_id": region_id,
        "status": status,
        "before_state": _region_field(before_region, "state"),
        "after_state": _region_field(after_region, "state"),
        "before_gate_ok": _region_field(before_region, "gate_ok"),
        "after_gate_ok": _region_field(after_region, "gate_ok"),
        "before_selected_anchor_count": _region_field(
            before_region,
            "selected_anchor_count",
        ),
        "after_selected_anchor_count": _region_field(
            after_region,
            "selected_anchor_count",
        ),
        "before_selected_anchor_indexes": _region_field(
            before_region,
            "selected_anchor_indexes",
        ),
        "after_selected_anchor_indexes": _region_field(
            after_region,
            "selected_anchor_indexes",
        ),
        "before_reason": _region_field(before_region, "reason"),
        "after_reason": _region_field(after_region, "reason"),
        "changes": changes,
    }


def _region_field(region: dict[str, Any] | None, field: str) -> Any:
    if not isinstance(region, dict):
        return None
    return region.get(field)


def _selected_summary(delta: dict[str, Any], side: str) -> str | None:
    count = delta.get(f"{side}_selected_anchor_count")
    indexes = delta.get(f"{side}_selected_anchor_indexes")
    if isinstance(indexes, list) and indexes:
        index_text = ",".join(str(index) for index in indexes)
        if count is None:
            return f"[{index_text}]"
        return f"{count} [{index_text}]"
    if count is not None:
        return str(count)
    return None


def _transition_cell(before: Any, after: Any) -> str:
    if before == after:
        return _code_cell(before)
    return f"{_code_cell(before)} -> {_code_cell(after)}"


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


def _segment_source_summary(
    data: dict[str, Any],
    *,
    side: str,
) -> dict[str, Any]:
    summary = _dict_value(data.get("summary"))
    proposals = _list_value(data.get("proposals"))
    backend = _dict_value(data.get("backend"))
    return {
        "side": side,
        "source": _backend_source(data),
        "backend_status": backend.get("status", "unknown"),
        "backend_adapter": backend.get("adapter"),
        "proposal_count": int(data.get("proposal_count", len(proposals))),
        "status_counts": _segment_count_group(
            summary,
            proposals,
            group="status_counts",
            field="status",
        ),
        "downstream_status_counts": _segment_count_group(
            summary,
            proposals,
            group="downstream_status_counts",
            field="downstream_status",
        ),
        "downstream_decision_reason_counts": _segment_count_group(
            summary,
            proposals,
            group="downstream_decision_reason_counts",
            field="downstream_decision_reason",
            include_missing=False,
        ),
        "anchor_kind_counts": _segment_count_group(
            summary,
            proposals,
            group="anchor_kind_counts",
            field="anchor_kind",
            include_missing=False,
        ),
        "reserved_anchor_count": int(
            _number_or_zero(
                summary.get(
                    "reserved_anchor_count",
                    sum(1 for proposal in proposals if proposal.get("anchor_reserved")),
                )
            )
        ),
        "proposal_group_counts": _dict_value(summary.get("proposal_group_counts")),
    }


def _segment_source_deltas(
    before: dict[str, Any],
    after: dict[str, Any],
) -> list[dict[str, Any]]:
    before_counts = _segment_delta_groups(before)
    after_counts = _segment_delta_groups(after)
    return _summary_count_deltas(before_counts, after_counts)


def _segment_promotion_proxy_deltas(
    source_deltas: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        _segment_promotion_proxy_delta(
            source_deltas,
            key="green_promotion",
            downstream_status="accepted",
        ),
        _segment_promotion_proxy_delta(
            source_deltas,
            key="red_candidate",
            downstream_status="rejected",
        ),
        _segment_promotion_proxy_delta(
            source_deltas,
            key="manual_review",
            downstream_status="pending",
        ),
    ]


def _segment_promotion_proxy_delta(
    source_deltas: list[dict[str, Any]],
    *,
    key: str,
    downstream_status: str,
) -> dict[str, Any]:
    source = _segment_delta_record(
        source_deltas,
        group="downstream_status_counts",
        key=downstream_status,
    )
    return {
        "group": "promotion_proxy_counts",
        "key": key,
        "source_group": "downstream_status_counts",
        "source_key": downstream_status,
        "before": source.get("before", 0.0),
        "after": source.get("after", 0.0),
        "delta": source.get("delta", 0.0),
    }


def _segment_source_delta_assessment(
    source_deltas: list[dict[str, Any]],
) -> dict[str, Any]:
    green_delta = _segment_delta_value(
        source_deltas,
        group="downstream_status_counts",
        key="accepted",
    )
    red_delta = _segment_delta_value(
        source_deltas,
        group="downstream_status_counts",
        key="rejected",
    )
    manual_delta = _segment_delta_value(
        source_deltas,
        group="downstream_status_counts",
        key="pending",
    )
    proposal_delta = _segment_delta_value(
        source_deltas,
        group="proposal_count",
        key="value",
    )
    positive_signals = []
    risk_signals = []
    if green_delta > 0:
        positive_signals.append("green_promotion_increase")
    if red_delta < 0:
        positive_signals.append("red_candidate_decrease")
    if manual_delta < 0:
        positive_signals.append("manual_review_decrease")
    if green_delta < 0:
        risk_signals.append("green_promotion_decrease")
    if red_delta > 0:
        risk_signals.append("red_candidate_increase")
    if manual_delta > 0:
        risk_signals.append("manual_review_increase")
    if proposal_delta > 0 and green_delta <= 0:
        risk_signals.append("proposal_count_increase_without_green_gain")

    if (
        green_delta == 0
        and red_delta == 0
        and manual_delta == 0
        and proposal_delta == 0
    ):
        verdict = "unchanged"
    elif green_delta > 0 and red_delta <= 0 and manual_delta <= 0:
        verdict = "improved"
    elif green_delta <= 0 and risk_signals:
        verdict = "noise"
    elif green_delta > 0 and risk_signals:
        verdict = "mixed"
    else:
        verdict = "needs_review"

    return {
        "verdict": verdict,
        "green_promotion_delta": green_delta,
        "red_candidate_delta": red_delta,
        "manual_review_delta": manual_delta,
        "proposal_count_delta": proposal_delta,
        "promotion_delta_basis": "downstream_status_counts_proxy",
        "uses_region_promotion_labels": False,
        "positive_signals": positive_signals,
        "risk_signals": risk_signals,
    }


def _segment_delta_value(
    deltas: list[dict[str, Any]],
    *,
    group: str,
    key: str,
) -> float:
    return _number_or_zero(
        _segment_delta_record(deltas, group=group, key=key).get("delta")
    )


def _segment_delta_record(
    deltas: list[dict[str, Any]],
    *,
    group: str,
    key: str,
) -> dict[str, Any]:
    for delta in deltas:
        if delta.get("group") == group and delta.get("key") == key:
            return delta
    return {}


def _segment_delta_groups(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "proposal_count": summary.get("proposal_count", 0),
        "status_counts": _dict_value(summary.get("status_counts")),
        "downstream_status_counts": _dict_value(
            summary.get("downstream_status_counts")
        ),
        "downstream_decision_reason_counts": _dict_value(
            summary.get("downstream_decision_reason_counts")
        ),
        "anchor_kind_counts": _dict_value(summary.get("anchor_kind_counts")),
        "reserved_anchor_count": summary.get("reserved_anchor_count", 0),
        "proposal_group_counts": _dict_value(summary.get("proposal_group_counts")),
    }


def _segment_count_group(
    summary: dict[str, Any],
    proposals: list[Any],
    *,
    group: str,
    field: str,
    include_missing: bool = True,
) -> dict[str, int]:
    summary_counts = summary.get(group)
    if isinstance(summary_counts, dict):
        return {
            str(key): int(value)
            for key, value in sorted(summary_counts.items())
            if _is_number(value)
        }

    counts: dict[str, int] = {}
    for proposal in proposals:
        if not isinstance(proposal, dict):
            continue
        value = proposal.get(field)
        if value is None and not include_missing:
            continue
        key = str(value if value is not None else "unknown")
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


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


def _code_cell(value: Any) -> str:
    if value is None or value == "":
        return "`n/a`"
    return f"`{value}`"


def _count_cell(value: Any) -> str:
    counts = _dict_value(value)
    if not counts:
        return "`none`"
    parts = [f"{key}: {counts[key]}" for key in sorted(counts)]
    return "`" + ", ".join(parts) + "`"


def _signal_cell(value: Any) -> str:
    signals = _list_value(value)
    if not signals:
        return "`none`"
    return "`" + ", ".join(str(signal) for signal in signals) + "`"


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
