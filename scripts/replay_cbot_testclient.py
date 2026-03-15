#!/usr/bin/env python3
"""Source-neutral Stage 12 TestClient replay entrypoint."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.replay_histdata_cbot_testclient import *  # noqa: F401,F403
from scripts.replay_histdata_cbot_testclient import main


if __name__ == "__main__":
    main()
