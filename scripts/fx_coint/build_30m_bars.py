"""Build cached 30-min flow bars from the 1-min flow bars.
Output: data/tick_bars/{sym}_30m_flow.parquet.

Usage: python scripts/fx_coint/build_30m_bars.py [--data-dir PATH]
"""

from __future__ import annotations

import argparse
import os

import polars as pl

from scripts.fx_coint.feature_bars_30m import aggregate_30m

PAIRS = ["EURUSD", "GBPUSD", "AUDUSD", "USDJPY", "USDCHF", "USDCAD"]


def build(sym: str, src_dir: str) -> pl.DataFrame:
    df = pl.read_parquet(f"{src_dir}/{sym}_1m_flow.parquet")
    return aggregate_30m(df)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build 30m flow bars from 1m flow bars.")
    parser.add_argument("--data-dir", default="data/tick_bars", help="Directory containing 1m and output 30m parquet files.")
    args = parser.parse_args()

    src_dir = args.data_dir
    out_dir = args.data_dir
    os.makedirs(out_dir, exist_ok=True)
    for sym in PAIRS:
        df = build(sym, src_dir)
        path = f"{out_dir}/{sym}_30m_flow.parquet"
        df.write_parquet(path)
        print(
            f"{sym}: {df.height} bars  {df['bucket'].min()} -> {df['bucket'].max()}  -> {path}"
        )


if __name__ == "__main__":
    main()
