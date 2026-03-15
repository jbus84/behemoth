#!/usr/bin/env python3
"""Broker-neutral compatibility wrapper for the legacy FTMO reservation reconciler."""

from __future__ import annotations

from scripts.reconcile_ftmo_reservations import *  # noqa: F401,F403
from scripts.reconcile_ftmo_reservations import main


if __name__ == "__main__":
    main()
