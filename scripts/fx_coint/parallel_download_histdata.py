#!/usr/bin/env python3
"""Parallel HistData tick downloader — launches one process per symbol.

Each process gets its own cookie jar and scrapes HistData independently.
HistData may throttle or block if too many concurrent; default max=3.
"""

import argparse
import subprocess
import sys
from pathlib import Path

DEFAULT_SYMBOLS = [
    "EURUSD", "GBPUSD", "AUDUSD", "USDCAD", "USDJPY", "USDCHF",
    "EURGBP", "EURJPY", "GBPJPY", "AUDJPY", "EURCHF",
    "AUDCAD", "GBPAUD", "EURAUD", "GBPCHF", "CADJPY",
    "CHFJPY", "NZDUSD", "EURNZD", "GBPNZD", "AUDNZD",
]


def _build_months(start_year: int = 2018, end_year: int = 2025) -> str:
    months = []
    for y in range(start_year, end_year + 1):
        for m in range(1, 13):
            months.append(f"{y}{m:02d}")
    return ",".join(months)


def run_symbol(symbol: str, months: str, tick_root: str) -> subprocess.Popen:
    cmd = [
        sys.executable,
        "scripts/download_histdata_ticks.py",
        "--symbols", symbol,
        "--months", months,
        "--tick-root", tick_root,
        "--skip-existing", "true",
    ]
    log = Path(f"/tmp/download_{symbol.lower()}.log")
    return subprocess.Popen(cmd, stdout=open(log, "w"), stderr=subprocess.STDOUT)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
    p.add_argument("--months", default=_build_months())
    p.add_argument("--tick-root", default="/Users/danielfisher/Desktop/tick")
    p.add_argument("--max-concurrent", type=int, default=3)
    args = p.parse_args()

    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    print(f"Symbols: {len(symbols)} | Max concurrent: {args.max_concurrent}")

    active = []
    completed = []
    failed = []

    for sym in symbols:
        # Wait for a slot
        while len(active) >= args.max_concurrent:
            for proc_info in active[:]:
                sym_i, proc = proc_info
                ret = proc.poll()
                if ret is not None:
                    active.remove(proc_info)
                    if ret == 0:
                        completed.append(sym_i)
                        print(f"  ✅ {sym_i} done ({len(completed)}/{len(symbols)})")
                    else:
                        failed.append(sym_i)
                        print(f"  ❌ {sym_i} failed (exit {ret})")
            # Brief pause before next poll
            import time
            time.sleep(2)

        # Start new symbol
        print(f"Starting {sym}...")
        proc = run_symbol(sym, args.months, args.tick_root)
        active.append((sym, proc))

    # Wait for remaining
    for sym, proc in active:
        proc.wait()
        if proc.returncode == 0:
            completed.append(sym)
            print(f"  ✅ {sym} done")
        else:
            failed.append(sym)
            print(f"  ❌ {sym} failed (exit {proc.returncode})")

    print(f"\nDone: {len(completed)} | Failed: {len(failed)}")
    if failed:
        print(f"Failed symbols: {', '.join(failed)}")


if __name__ == "__main__":
    main()
