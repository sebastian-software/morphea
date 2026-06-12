"""Compatibility aliases for the former ``curve`` package name."""

from __future__ import annotations

import importlib
import sys

import morphea as _morphea
from morphea import *  # noqa: F401,F403


_SUBMODULES = (
    "anchors",
    "classifier",
    "comparison",
    "curated",
    "dataset",
    "detection",
    "diagnostics",
    "eval",
    "images",
    "masks",
    "mlx_classifier",
    "profiling",
    "refinement",
    "rendering",
    "runs",
    "scene",
    "segmenters",
    "self_learning",
    "status",
    "sweeps",
    "synthetic",
    "token_transformer",
)


__all__ = getattr(_morphea, "__all__", [])

for _name in _SUBMODULES:
    _module = importlib.import_module(f"morphea.{_name}")
    sys.modules[f"curve.{_name}"] = _module
    globals()[_name] = _module

