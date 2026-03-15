#!/usr/bin/env python3
"""Source-neutral cTrader execution parity entrypoint."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.validate_histdata_ctrader_execution_parity import *  # noqa: F401,F403
from scripts.validate_histdata_ctrader_execution_parity import main


if __name__ == "__main__":
    main()
