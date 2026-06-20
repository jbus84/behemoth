"""CLI to pre-build enriched 1-min bars for majors.

Usage:
    uv run python scripts/fx_coint/build_enriched_1m_bars.py --year 2024
"""

from __future__ import annotations

import argparse
import sys as _sys
from pathlib import Path as _Path

_ROOT = _Path(__file__).resolve().parents[2]
if str(_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_ROOT))

from scripts.fx_coint.phase0_scalp_common import (  # noqa: E402
    build_enriched_1m_bars,
    load_raw_ticks,
    save_enriched_bars,
)

PAIRS = ["EURUSD", "GBPUSD", "AUDUSD", "USDJPY", "USDCHF", "USDCAD"]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--year", type=int, required=True)
    p.add_argument("--pairs", nargs="+", default=PAIRS)
    args = p.parse_args()

    for sym in args.pairs:
        try:
            ticks = load_raw_ticks(sym, args.year)
            bars = build_enriched_1m_bars(ticks, sym)
            path = save_enriched_bars(bars, sym, "1m")
            print(f"{sym}: {len(bars)} bars  {bars['bucket'].min()} -> {bars['bucket'].max()}  -> {path}")
        except FileNotFoundError as e:
            print(f"SKIP {sym}: {e}")


if __name__ == "__main__":
    main()
