#!/usr/bin/env python3
"""Diagnose live Rolling Threshold behavior from local Runtime State."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.behemoth.diagnostics.live_threshold import (  # noqa: E402
    LiveThresholdConfig,
    run_live_threshold_diagnostic,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Diagnose live Rolling Threshold behavior")
    parser.add_argument("--db", required=True, help="Path to live_state.db")
    parser.add_argument("--symbol", required=True, help="Symbol to diagnose, such as EURUSD")
    parser.add_argument("--run-id", required=True, help="Diagnostic run id used for output filenames")
    parser.add_argument("--live-run-id", default="jforex_live", help="Runtime run_id used for live audit rows")
    parser.add_argument("--start-ts", required=True, help="Inclusive diagnostic start timestamp")
    parser.add_argument("--end-ts", required=True, help="Inclusive diagnostic end timestamp")
    parser.add_argument("--lookback-days", type=int, default=20)
    parser.add_argument("--execution-quantile", type=float, default=0.9)
    parser.add_argument("--min-history", type=int, default=300)
    parser.add_argument("--out-dir", default="data/analysis/live_threshold_diagnostics")
    parser.add_argument("--api", default="", help="Optional API base URL to checkpoint before reading")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    if args.api:
        requests.get(f"{args.api.rstrip('/')}/state/checkpoint", timeout=5).raise_for_status()
    config = LiveThresholdConfig(
        symbol=str(args.symbol).upper(),
        run_id=str(args.run_id),
        live_run_id=str(args.live_run_id),
        lookback_days=int(args.lookback_days),
        execution_quantile=float(args.execution_quantile),
        min_history=int(args.min_history),
        start_ts=pd.Timestamp(args.start_ts),
        end_ts=pd.Timestamp(args.end_ts),
        out_dir=Path(args.out_dir),
    )
    con = duckdb.connect(str(args.db), read_only=True)
    try:
        summary = run_live_threshold_diagnostic(con, config)
    finally:
        con.close()
    print(f"classification={summary['classification']}")
    print(f"summary={config.out_dir / (config.run_id + '_summary.json')}")
    print(f"report={config.out_dir / (config.run_id + '_report.md')}")


if __name__ == "__main__":
    main()
