"""Structure-preserving refinement interface and local baseline backend."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RefinementConfig:
    backend: str = "local_metric"
    max_iterations: int = 0
    timeout_seconds: float | None = None


def refine_manifest(
    *,
    manifest: str | Path,
    output: str | Path,
    config: RefinementConfig | None = None,
) -> dict[str, object]:
    config = config or RefinementConfig()
    if config.backend != "local_metric":
        msg = f"unsupported refinement backend: {config.backend}"
        raise ValueError(msg)

    data = json.loads(Path(manifest).read_text(encoding="utf-8"))
    refined_anchors = []
    for anchor in data.get("anchors", []):
        refined = dict(anchor)
        metrics = dict(refined.get("metrics", {}))
        metrics["refinement_structure_preserved"] = 1.0
        metrics["refinement_iterations"] = float(config.max_iterations)
        refined["metrics"] = metrics
        refined_anchors.append(refined)

    result = dict(data)
    result["anchors"] = refined_anchors
    result["refinement"] = {
        "backend": config.backend,
        "max_iterations": config.max_iterations,
        "timeout_seconds": config.timeout_seconds,
        "structure_preserving": True,
    }
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    return result

