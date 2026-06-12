"""Compatibility wrapper for ``python -m curve.cli``."""

from __future__ import annotations

from morphea.cli import *  # noqa: F401,F403
from morphea.cli import main


if __name__ == "__main__":
    main()
