#!/usr/bin/env python3
"""Broker-neutral compatibility wrapper for the legacy FTMO monitoring report builder."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

# Load the sibling module dynamically — scripts/ is not a package so a
# bare ``from scripts.X import …`` fails when invoked via ``uv run python
# scripts/build_account_risk_monitoring_report.py``.
_sibling = Path(__file__).resolve().parent / "build_ftmo_allocator_monitoring_report.py"
_spec = importlib.util.spec_from_file_location(
    "build_ftmo_allocator_monitoring_report", _sibling
)
_mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _mod
_spec.loader.exec_module(_mod)

from build_ftmo_allocator_monitoring_report import *  # noqa: F401,F403
from build_ftmo_allocator_monitoring_report import main


if __name__ == "__main__":
    main()
