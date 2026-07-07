#!/usr/bin/env python3
"""Download real historical tick data (bid/ask) from a running MetaTrader 5 terminal
via the official MetaTrader5 Python API, and convert to the same canonical parquet
schema used by download_histdata_ticks.py -- so it drops into the existing pipeline
(scripts/fx_coint/*) with zero changes elsewhere.

REQUIRES (all outside what this script can set up for you):
  - MT5 terminal installed and RUNNING, logged into an account on the broker whose
    data you want (e.g. IC Markets demo account) -- the API talks to this local
    terminal instance, not directly to the broker over the network.
  - `pip install MetaTrader5` in the SAME Python environment this script runs in.
    The MetaTrader5 package is Windows-native; on Mac this means running inside
    whatever Windows/Wine environment hosts the MT5 terminal (a Windows VM, or
    IC Markets' Mac-wrapper install), not the mac-native project venv used
    elsewhere in this repo.

Output schema (matches download_histdata_ticks.py exactly):
  timestamp (UTC), bid, ask, mid, spread, log_return
  written to {tick_root}/{symbol}/{symbol}_{YYYYMM}_ticks.parquet

Usage:
  python download_mt5_ticks.py --symbols EURUSD,GBPUSD --months 202401,202402 \
      --tick-root ~/Desktop/tick_icmarkets
"""

from __future__ import annotations

import argparse
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None  # allows --help / argument parsing to work even without the package


def _parse_months(raw: str) -> list[str]:
    months = [m.strip() for m in str(raw).split(",") if m.strip()]
    for m in months:
        if not re.fullmatch(r"\d{6}", m):
            raise ValueError(f"bad month (expected YYYYMM): {m}")
    return months


def _parse_symbols(raw: str) -> list[str]:
    return [s.strip().upper() for s in str(raw).split(",") if s.strip()]


def _month_bounds_utc(yyyymm: str) -> tuple[datetime, datetime]:
    year, month = int(yyyymm[:4]), int(yyyymm[4:6])
    start = datetime(year, month, 1, tzinfo=timezone.utc)
    end = datetime(year + 1, 1, 1, tzinfo=timezone.utc) if month == 12 else datetime(year, month + 1, 1, tzinfo=timezone.utc)
    return start, end


def fetch_month_ticks(symbol: str, yyyymm: str) -> pd.DataFrame:
    """Pull one month of tick data via copy_ticks_range, chunked by day to stay
    well under any per-call size limit the terminal/broker might impose."""
    start, end = _month_bounds_utc(yyyymm)
    all_chunks = []
    day = start
    while day < end:
        next_day = min(day + timedelta(days=1), end)
        ticks = mt5.copy_ticks_range(symbol, day, next_day, mt5.COPY_TICKS_ALL)
        if ticks is not None and len(ticks) > 0:
            df = pd.DataFrame(ticks)
            all_chunks.append(df)
        day = next_day
    if not all_chunks:
        return pd.DataFrame()
    raw = pd.concat(all_chunks, ignore_index=True)
    # time_msc is milliseconds since epoch, UTC -- more precise than the integer `time` field
    raw["timestamp"] = pd.to_datetime(raw["time_msc"], unit="ms", utc=True)
    raw = raw[(raw["bid"] > 0) & (raw["ask"] > 0)].copy()
    raw["mid"] = (raw["bid"] + raw["ask"]) / 2.0
    raw["spread"] = raw["ask"] - raw["bid"]
    raw = raw.sort_values("timestamp").drop_duplicates(subset="timestamp")
    raw["log_return"] = np.log(raw["mid"]).diff().fillna(0.0)
    return raw[["timestamp", "bid", "ask", "mid", "spread", "log_return"]].reset_index(drop=True)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", required=True, help="comma-separated symbols, e.g. EURUSD,GBPUSD")
    p.add_argument("--months", required=True, help="comma-separated YYYYMM, e.g. 202401,202402")
    p.add_argument("--tick-root", default="~/Desktop/tick_icmarkets")
    p.add_argument("--skip-existing", default="true")
    args = p.parse_args()

    if mt5 is None:
        raise SystemExit(
            "MetaTrader5 package not installed in this Python environment. "
            "Install with `pip install MetaTrader5` inside the environment that has "
            "access to a running MT5 terminal (Windows/Wine), then re-run this script."
        )

    if not mt5.initialize():
        raise SystemExit(f"mt5.initialize() failed: {mt5.last_error()}. "
                          "Is the MT5 terminal running and logged in?")

    account_info = mt5.account_info()
    if account_info is not None:
        print(f"Connected to MT5: server={account_info.server}  login={account_info.login}")
    else:
        print("Warning: connected but could not read account_info -- check terminal login state.")

    symbols = _parse_symbols(args.symbols)
    months = _parse_months(args.months)
    tick_root = Path(args.tick_root).expanduser()
    skip_existing = str(args.skip_existing).lower() == "true"

    written = skipped = failed = 0
    for symbol in symbols:
        if not mt5.symbol_select(symbol, True):
            print(f"SKIP {symbol}: symbol not available on this broker/server")
            continue
        out_dir = tick_root / symbol
        out_dir.mkdir(parents=True, exist_ok=True)
        for yyyymm in months:
            out_path = out_dir / f"{symbol}_{yyyymm}_ticks.parquet"
            if skip_existing and out_path.exists():
                skipped += 1
                continue
            try:
                df = fetch_month_ticks(symbol, yyyymm)
                if df.empty:
                    print(f"  {symbol} {yyyymm}: no ticks returned (outside retention window?)")
                    failed += 1
                    continue
                df.to_parquet(out_path, index=False)
                print(f"  wrote {out_path} rows={len(df)}")
                written += 1
            except Exception as e:  # noqa: BLE001
                print(f"  FAILED {symbol} {yyyymm}: {e}")
                failed += 1

    mt5.shutdown()
    print(f"\nDone. written={written} skipped={skipped} failed={failed}")


if __name__ == "__main__":
    main()
