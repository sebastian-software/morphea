"""Review-packet helpers for the local promotion workflow."""

from __future__ import annotations

import json
import shlex
from pathlib import Path
from typing import Any

from morphea.promotion_export import apply_promotion_review_decision
from morphea.self_learning import HARVEST_FILTER_DEFAULTS


HARVESTABLE_PROMOTION_DECISIONS = {"accepted", "corrected"}
TERMINAL_PROMOTION_REVIEW_DECISIONS = (
    "accepted",
    "corrected",
    "rejected",
    "deferred",
)


def prepare_promotion_review_harvest(
    *,
    review_packet: str | Path,
    output: str | Path,
    markdown: str | Path | None = None,
    harvest_config: str | Path | None = None,
    review_config: str | Path | None = None,
    decisions: dict[str, str | Path] | None = None,
    decision_templates: dict[str, dict[str, str | Path]] | None = None,
    suite: str | Path | None = None,
    run_root: str | Path | None = None,
    harvest_output: str | Path | None = None,
    curated_report: str | Path | None = None,
    snapshot: str | Path | None = None,
    harvest_markdown: str | Path | None = None,
) -> dict[str, object]:
    """Apply selected terminal decisions and prepare a harvest-curated config."""

    packet_path = Path(review_packet)
    packet = _load_review_packet(packet_path)
    base_dir = packet_path.parent
    cases = _packet_cases(packet)
    cases_by_id = _cases_by_id(cases)
    decision_map = decisions or {}
    template_map = _decision_template_map(cases, decision_templates)
    template_readiness = _decision_template_readiness(template_map, base_dir)
    choice_command_map = _decision_choice_commands(review_config, template_map)
    unknown_cases = sorted(set(decision_map) - set(cases_by_id))
    if unknown_cases:
        raise ValueError(
            "review decisions reference unknown packet cases: "
            + ", ".join(unknown_cases)
        )

    run_root_path = Path(run_root) if run_root is not None else base_dir
    newly_applied = []
    for case_id, decision_path in sorted(decision_map.items()):
        case = cases_by_id[case_id]
        manifest_path = _case_manifest_path(case, base_dir, run_root_path)
        if manifest_path is None:
            raise ValueError(f"review packet case {case_id} has no manifest artifact")
        applied_output = manifest_path.with_name("applied-review.json")
        applied_markdown = manifest_path.with_name("applied-review.md")
        applied = apply_promotion_review_decision(
            review_decision=_resolve_path(decision_path, base_dir),
            output=applied_output,
            markdown=applied_markdown,
            manifest=manifest_path,
        )
        newly_applied.append(
            {
                "case_id": case_id,
                "decision": applied.get("decision"),
                "accepted_for_promotion": bool(
                    applied.get("accepted_for_promotion", False)
                ),
                "source_review_decision": applied.get("source_review_decision"),
                "manifest": str(manifest_path),
                "output": str(applied_output),
                "markdown": str(applied_markdown),
            }
        )

    applied_cases, pending_cases = _packet_review_status(
        cases,
        base_dir=base_dir,
        run_root=run_root_path,
        decision_templates=template_map,
        decision_template_readiness=template_readiness,
        decision_choice_commands=choice_command_map,
    )
    harvest_cfg = _harvest_curated_config(
        packet=packet,
        base_dir=base_dir,
        suite=suite,
        run_root=run_root_path,
        harvest_output=harvest_output,
        curated_report=curated_report,
        snapshot=snapshot,
        harvest_markdown=harvest_markdown,
    )
    if harvest_config is not None:
        _write_json(Path(harvest_config), harvest_cfg)

    result = {
        "schema_version": 1,
        "review_packet": str(packet_path),
        "review_config": str(review_config) if review_config else None,
        "suite": harvest_cfg.get("suite"),
        "run_root": harvest_cfg.get("run_root"),
        "case_count": len(cases),
        "newly_applied_decision_count": len(newly_applied),
        "newly_applied_decisions": newly_applied,
        "applied_case_count": len(applied_cases),
        "applied_cases": applied_cases,
        "harvestable_case_count": sum(
            1
            for case in applied_cases
            if case.get("decision") in HARVESTABLE_PROMOTION_DECISIONS
        ),
        "pending_case_count": len(pending_cases),
        "pending_cases": pending_cases,
        "decision_templates": template_map,
        "decision_template_readiness": template_readiness,
        "decision_choice_commands": choice_command_map,
        "harvest_config": harvest_cfg,
        "harvest_config_path": str(harvest_config) if harvest_config else None,
        "next_commands": _next_commands(harvest_config),
    }
    _write_json(Path(output), result)
    if markdown is not None:
        markdown_path = Path(markdown)
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(
            render_promotion_review_harvest_markdown(result),
            encoding="utf-8",
        )
    return result


def render_promotion_review_harvest_markdown(result: dict[str, object]) -> str:
    lines = [
        "# Morphēa Promotion Review Harvest Prep",
        "",
        f"- Review packet: `{result.get('review_packet', 'n/a')}`",
        f"- Suite: `{result.get('suite', 'n/a')}`",
        f"- Run root: `{result.get('run_root', 'n/a')}`",
        f"- Cases: {_fmt_value(result.get('case_count'))}",
        f"- Newly applied decisions: {_fmt_value(result.get('newly_applied_decision_count'))}",
        f"- Applied cases: {_fmt_value(result.get('applied_case_count'))}",
        f"- Harvestable cases: {_fmt_value(result.get('harvestable_case_count'))}",
        f"- Pending cases: {_fmt_value(result.get('pending_case_count'))}",
        "",
        "## Newly Applied",
        "",
        "| Case | Decision | Accepted | Manifest | Output |",
        "| --- | --- | --- | --- | --- |",
    ]
    applied = result.get("newly_applied_decisions", [])
    if isinstance(applied, list) and applied:
        for item in applied:
            if not isinstance(item, dict):
                continue
            lines.append(
                "| "
                f"`{item.get('case_id', 'n/a')}` | "
                f"`{item.get('decision', 'n/a')}` | "
                f"`{str(item.get('accepted_for_promotion', False)).lower()}` | "
                f"`{item.get('manifest', 'n/a')}` | "
                f"`{item.get('output', 'n/a')}` |"
            )
    else:
        lines.append("| n/a | n/a | n/a | n/a | n/a |")

    lines.extend(
        [
            "",
            "## Applied Case Status",
            "",
            "| Case | Decision | Harvestable | Manifest |",
            "| --- | --- | --- | --- |",
        ]
    )
    applied_cases = result.get("applied_cases", [])
    if isinstance(applied_cases, list) and applied_cases:
        for item in applied_cases:
            if not isinstance(item, dict):
                continue
            lines.append(
                "| "
                f"`{item.get('case_id', 'n/a')}` | "
                f"`{item.get('decision', 'n/a')}` | "
                f"`{str(item.get('harvestable', False)).lower()}` | "
                f"`{item.get('manifest', 'n/a')}` |"
            )
    else:
        lines.append("| n/a | n/a | n/a | n/a |")

    lines.extend(
        [
            "",
            "## Pending Cases",
            "",
            "| Case | Suggested | Review decision | Decision templates | Manifest |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    pending = result.get("pending_cases", [])
    if isinstance(pending, list) and pending:
        for item in pending:
            if not isinstance(item, dict):
                continue
            lines.append(
                "| "
                f"`{item.get('case_id', 'n/a')}` | "
                f"`{item.get('suggested_review_decision', 'n/a')}` | "
                f"`{item.get('review_decision', 'n/a')}` | "
                f"{_fmt_decision_templates(item.get('decision_templates'))} | "
                f"`{item.get('manifest', 'n/a')}` |"
            )
    else:
        lines.append("| n/a | n/a | n/a | n/a | n/a |")

    _append_decision_choice_commands(
        lines,
        result.get("decision_choice_commands"),
        result.get("decision_template_readiness"),
    )

    config_path = result.get("harvest_config_path")
    commands = result.get("next_commands", [])
    if isinstance(config_path, str) and config_path:
        lines.extend(
            [
                "",
                "## Next Commands",
                "",
            ]
        )
        if isinstance(commands, list) and commands:
            for command in commands:
                if isinstance(command, str) and command:
                    lines.extend(["```sh", command, "```"])
        else:
            lines.append("n/a")
    return "\n".join(lines).rstrip() + "\n"


def _load_review_packet(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("promotion review packet must be a JSON object")
    return data


def _packet_cases(packet: dict[str, object]) -> list[dict[str, object]]:
    cases = packet.get("cases", [])
    if not isinstance(cases, list):
        return []
    return [case for case in cases if isinstance(case, dict)]


def _cases_by_id(cases: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    by_id: dict[str, dict[str, object]] = {}
    for case in cases:
        case_id = case.get("case_id")
        if isinstance(case_id, str) and case_id:
            by_id[case_id] = case
    return by_id


def _packet_review_status(
    cases: list[dict[str, object]],
    *,
    base_dir: Path,
    run_root: Path,
    decision_templates: dict[str, dict[str, str]],
    decision_template_readiness: dict[str, dict[str, dict[str, object]]],
    decision_choice_commands: dict[str, dict[str, str]],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    applied_cases: list[dict[str, object]] = []
    pending_cases: list[dict[str, object]] = []
    for case in cases:
        case_id = str(case.get("case_id", "n/a"))
        manifest_path = _case_manifest_path(case, base_dir, run_root)
        applied = _manifest_applied_review(manifest_path)
        if applied:
            decision = str(applied.get("decision", "n/a"))
            applied_cases.append(
                {
                    "case_id": case_id,
                    "decision": decision,
                    "harvestable": decision in HARVESTABLE_PROMOTION_DECISIONS,
                    "accepted_for_promotion": bool(
                        applied.get("accepted_for_promotion", False)
                    ),
                    "source_review_decision": applied.get(
                        "source_review_decision",
                    ),
                    "manifest": str(manifest_path) if manifest_path else None,
                }
            )
        else:
            pending_cases.append(
                {
                    "case_id": case_id,
                    "suggested_review_decision": case.get(
                        "suggested_review_decision",
                        "n/a",
                    ),
                    "review_decision": case.get("review_decision_state", "n/a"),
                    "decision_templates": decision_templates.get(case_id, {}),
                    "decision_template_readiness": decision_template_readiness.get(
                        case_id,
                        {},
                    ),
                    "decision_choice_commands": decision_choice_commands.get(
                        case_id,
                        {},
                    ),
                    "manifest": str(manifest_path) if manifest_path else None,
                }
            )
    return applied_cases, pending_cases


def _decision_template_readiness(
    decision_templates: dict[str, dict[str, str]],
    base_dir: Path,
) -> dict[str, dict[str, dict[str, object]]]:
    readiness: dict[str, dict[str, dict[str, object]]] = {}
    for case_id, templates in sorted(decision_templates.items()):
        case_readiness: dict[str, dict[str, object]] = {}
        for decision in TERMINAL_PROMOTION_REVIEW_DECISIONS:
            template = templates.get(decision)
            if not template:
                continue
            case_readiness[decision] = _terminal_template_readiness(
                decision=decision,
                template_path=_resolve_path(template, base_dir),
            )
        if case_readiness:
            readiness[case_id] = case_readiness
    return readiness


def _terminal_template_readiness(
    *,
    decision: str,
    template_path: Path,
) -> dict[str, object]:
    try:
        data = json.loads(template_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {
            "path": str(template_path),
            "ready": False,
            "missing_fields": ["template_file"],
        }
    except json.JSONDecodeError:
        return {
            "path": str(template_path),
            "ready": False,
            "missing_fields": ["template_json"],
        }
    if not isinstance(data, dict):
        return {
            "path": str(template_path),
            "ready": False,
            "missing_fields": ["template_object"],
        }
    missing = _terminal_template_missing_fields(decision, data)
    return {
        "path": str(template_path),
        "ready": not missing,
        "missing_fields": missing,
    }


def _terminal_template_missing_fields(
    decision: str,
    data: dict[str, object],
) -> list[str]:
    missing: list[str] = []
    if data.get("decision") != decision:
        missing.append("decision")
    if not _non_empty_string(data.get("reviewer")):
        missing.append("reviewer")
    if not _non_empty_string(data.get("reason")):
        missing.append("reason")
    if decision == "corrected":
        if not _non_empty_string(data.get("correction_notes")):
            missing.append("correction_notes")
        if not _non_empty_string_list(data.get("corrected_artifacts")):
            missing.append("corrected_artifacts")
    return missing


def _non_empty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _non_empty_string_list(value: object) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(item, str) and bool(item.strip()) for item in value)
    )


def _decision_choice_commands(
    review_config: str | Path | None,
    decision_templates: dict[str, dict[str, str]],
) -> dict[str, dict[str, str]]:
    if review_config is None:
        return {}
    config_arg = shlex.quote(str(review_config))
    commands: dict[str, dict[str, str]] = {}
    for case_id, templates in sorted(decision_templates.items()):
        case_commands = {
            decision: (
                "PYTHONPATH=src python3 -m morphea.cli "
                f"promotion-review-harvest --config {config_arg} "
                f"--decision-choice {shlex.quote(f'{case_id}={decision}')}"
            )
            for decision in TERMINAL_PROMOTION_REVIEW_DECISIONS
            if isinstance(templates.get(decision), str) and templates[decision]
        }
        if case_commands:
            commands[case_id] = case_commands
    return commands


def _decision_template_map(
    cases: list[dict[str, object]],
    configured: dict[str, dict[str, str | Path]] | None,
) -> dict[str, dict[str, str]]:
    template_map: dict[str, dict[str, str]] = {}
    for case in cases:
        case_id = case.get("case_id")
        if not isinstance(case_id, str) or not case_id:
            continue
        templates = _case_packet_decision_templates(case)
        if templates:
            template_map[case_id] = templates
    if configured:
        for case_id, templates in configured.items():
            if not isinstance(case_id, str) or not case_id:
                continue
            normalized = _normalized_terminal_templates(templates)
            if normalized:
                template_map[case_id] = normalized
    return template_map


def _case_packet_decision_templates(case: dict[str, object]) -> dict[str, str]:
    artifacts = case.get("artifacts", {})
    if not isinstance(artifacts, dict):
        return {}
    templates = artifacts.get("review_templates", {})
    if not isinstance(templates, dict):
        return {}
    return _normalized_terminal_templates(templates)


def _normalized_terminal_templates(
    templates: dict[str, object],
) -> dict[str, str]:
    return {
        decision: str(path)
        for decision in TERMINAL_PROMOTION_REVIEW_DECISIONS
        if isinstance((path := templates.get(decision)), (str, Path)) and str(path)
    }


def _case_manifest_path(
    case: dict[str, object],
    base_dir: Path,
    run_root: Path,
) -> Path | None:
    artifacts = case.get("artifacts", {})
    if isinstance(artifacts, dict):
        manifest = artifacts.get("manifest")
        if isinstance(manifest, str) and manifest:
            return _resolve_path(manifest, base_dir)
    case_id = case.get("case_id")
    if isinstance(case_id, str) and case_id:
        fallback = run_root / case_id / "manifest.json"
        if fallback.exists():
            return fallback
    return None


def _manifest_applied_review(path: Path | None) -> dict[str, object]:
    if path is None or not path.exists():
        return {}
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        return {}
    applied = manifest.get("review_decision_applied")
    if isinstance(applied, dict):
        return applied
    promotion = manifest.get("promotion")
    if isinstance(promotion, dict):
        applied = promotion.get("review_decision_applied")
        if isinstance(applied, dict):
            return applied
    return {}


def _harvest_curated_config(
    *,
    packet: dict[str, object],
    base_dir: Path,
    suite: str | Path | None,
    run_root: Path,
    harvest_output: str | Path | None,
    curated_report: str | Path | None,
    snapshot: str | Path | None,
    harvest_markdown: str | Path | None,
) -> dict[str, object]:
    suite_value = str(suite) if suite is not None else _string_value(packet.get("suite"))
    if not suite_value:
        raise ValueError(
            "review packet has no suite; pass --suite to write a harvest config"
        )
    output_path = Path(harvest_output) if harvest_output is not None else (
        base_dir / "harvested-pseudo-labels.json"
    )
    report_path = Path(curated_report) if curated_report is not None else (
        base_dir / "curated-report.json"
    )
    snapshot_path = Path(snapshot) if snapshot is not None else (
        base_dir / "curated-snapshot.json"
    )
    markdown_path = Path(harvest_markdown) if harvest_markdown is not None else (
        base_dir / "harvested-pseudo-labels.md"
    )
    config = {
        "suite": suite_value,
        "run_root": str(run_root),
        "output": str(output_path),
        "curated_report": str(report_path),
        "snapshot": str(snapshot_path),
        "markdown": str(markdown_path),
        **HARVEST_FILTER_DEFAULTS,
        "require_applied_review": True,
    }
    return config


def _next_commands(harvest_config: str | Path | None) -> list[str]:
    if harvest_config is None:
        return []
    return [
        "PYTHONPATH=src python3 -m morphea.cli harvest-curated "
        f"--config {shlex.quote(str(harvest_config))}"
    ]


def _resolve_path(value: str | Path, base_dir: Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else base_dir / path


def _string_value(value: object) -> str:
    return value if isinstance(value, str) else ""


def _fmt_value(value: object) -> str:
    if isinstance(value, bool):
        return "n/a"
    if isinstance(value, int):
        return str(value)
    return "n/a"


def _fmt_decision_templates(value: object) -> str:
    if not isinstance(value, dict):
        return "n/a"
    parts = [
        f"`{decision}`=`{value[decision]}`"
        for decision in TERMINAL_PROMOTION_REVIEW_DECISIONS
        if isinstance(value.get(decision), str) and value[decision]
    ]
    return ", ".join(parts) if parts else "n/a"


def _append_decision_choice_commands(
    lines: list[str],
    value: object,
    readiness: object,
) -> None:
    if not isinstance(value, dict) or not value:
        return
    readiness = readiness if isinstance(readiness, dict) else {}
    block = ["", "## Decision Choice Commands", ""]
    for case_id in sorted(value):
        commands = value.get(case_id)
        if not isinstance(case_id, str) or not isinstance(commands, dict):
            continue
        command_items = [
            (decision, commands.get(decision))
            for decision in TERMINAL_PROMOTION_REVIEW_DECISIONS
            if isinstance(commands.get(decision), str) and commands.get(decision)
        ]
        if not command_items:
            continue
        block.extend([f"### {case_id}", ""])
        for decision, command in command_items:
            readiness_label = _fmt_template_readiness(
                readiness.get(case_id) if isinstance(readiness, dict) else None,
                decision,
            )
            block.extend(
                [
                    f"- `{decision}`: {readiness_label}",
                    "```sh",
                    str(command),
                    "```",
                    "",
                ]
            )
    if len(block) > 3:
        lines.extend(block)


def _fmt_template_readiness(value: object, decision: str) -> str:
    if not isinstance(value, dict):
        return "`unknown`"
    item = value.get(decision)
    if not isinstance(item, dict):
        return "`unknown`"
    if item.get("ready") is True:
        return "`ready`"
    missing = item.get("missing_fields")
    if isinstance(missing, list) and missing:
        return "needs edit: " + ", ".join(f"`{field}`" for field in missing)
    return "`not_ready`"


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
