#!/usr/bin/env python3
"""Build the frozen month-scoped candidate bundle for monthly recertification."""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import date
from pathlib import Path

DEFAULT_SYMBOLS = "EURUSD,GBPUSD,USDJPY,USDCHF,AUDUSD,USDCAD"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _validate_model_month(value: str) -> str:
    try:
        date.fromisoformat(f"{value}-01")
    except ValueError as exc:
        raise SystemExit(f"[monthly-build] invalid --model-month: {value}") from exc
    return value


def _derive_model_month(override: str | None = None) -> str:
    if override:
        return _validate_model_month(override)
    today = date.today()
    if today.month == 1:
        return _validate_model_month(f"{today.year - 1:04d}-12")
    return _validate_model_month(f"{today.year:04d}-{today.month - 1:02d}")


def _run_step(cmd: list[str], label: str) -> None:
    print(f"[monthly-build] {label}", flush=True)
    result = subprocess.run(cmd, cwd=_repo_root())
    if result.returncode != 0:
        raise SystemExit(f"[monthly-build] {label} failed (rc={result.returncode})")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-month", help="Override model month YYYY-MM (default: last complete month)")
    args = parser.parse_args()

    model_month = _derive_model_month(args.model_month)
    print(f"[monthly-build] building bundle for {model_month}", flush=True)

    _run_step(
        [
            "uv",
            "run",
            "python",
            "scripts/sync_candidate_model_artifacts.py",
            "--lock-dir",
            "configs/research/governance/oco",
            "--source-models-dir",
            "models/oco",
            "--target-models-dir",
            "models/oco_dukascopy_candidate",
            "--symbols",
            DEFAULT_SYMBOLS,
        ],
        "step 1/2: sync_candidate_model_artifacts",
    )
    _run_step(
        [
            "uv",
            "run",
            "python",
            "scripts/freeze_oco_historical_governance.py",
            "--allow-dirty",
            "--symbols",
            DEFAULT_SYMBOLS,
            "--out-dir",
            "configs/research/governance/oco_candidate_builds",
            "--months",
            model_month,
            "--config-dir",
            "configs/research/experiments_dukascopy_candidate",
            "--analysis-dir",
            "data/analysis/tick_opportunity_mining_dukascopy_candidate",
            "--models-dir",
            "models/oco_dukascopy_candidate",
        ],
        "step 2/2: freeze_oco_historical_governance",
    )


if __name__ == "__main__":
    main()
