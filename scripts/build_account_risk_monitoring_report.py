#!/usr/bin/env python3
"""Broker-neutral compatibility wrapper for the legacy FTMO monitoring report builder."""

from __future__ import annotations

from scripts.build_ftmo_allocator_monitoring_report import *  # noqa: F401,F403
from scripts.build_ftmo_allocator_monitoring_report import main


if __name__ == "__main__":
    main()
