#!/usr/bin/env python3
"""
Compute spread statistics by hour for all instruments.

Uses data/global_<bar>/*.parquet and outputs:
- data/analysis/spread_by_hour_<bar>.csv (long format)
- data/analysis/spread_by_hour_<bar>_mean_pivot.csv (hours x instruments, mean bps)
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl


def _extract_symbol(path: Path) -> str:
    name = path.stem
    # e.g., AUDUSD_1m -> AUDUSD
    if "_" in name:
        return name.split("_")[0]
    return name


def _process_file(path: Path) -> pd.DataFrame:
    sym = _extract_symbol(path)
    close_col = f"close_{sym}"
    spread_col = f"spread_{sym}"
    ts_col = "timestamp"

    df = pl.read_parquet(path, columns=[ts_col, close_col, spread_col])
    df = df.with_columns(
        [
            (pl.col(spread_col) / pl.col(close_col) * 10000.0).alias("spread_bps"),
            pl.col(ts_col).dt.hour().alias("hour"),
        ]
    )
    agg = (
        df.group_by("hour")
        .agg(
            [
                pl.count().alias("count"),
                pl.col("spread_bps").mean().alias("spread_bps_mean"),
                pl.col("spread_bps").median().alias("spread_bps_median"),
                pl.col("spread_bps").quantile(0.10).alias("spread_bps_p10"),
                pl.col("spread_bps").quantile(0.90).alias("spread_bps_p90"),
            ]
        )
        .sort("hour")
        .with_columns(pl.lit(sym).alias("instrument"))
    )
    return agg.to_pandas()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bar", default="1m", help="bar size directory suffix (e.g., 1m, 5m, 15m)")
    args = parser.parse_args()

    data_dir = Path(f"data/global_{args.bar}")
    out_dir = Path("data/analysis")
    out_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(data_dir.glob(f"*_{args.bar}.parquet"))
    if not files:
        raise SystemExit(f"No parquet files found in {data_dir}")

    frames = []
    for f in files:
        frames.append(_process_file(f))

    out = pd.concat(frames, ignore_index=True)
    out_path = out_dir / f"spread_by_hour_{args.bar}.csv"
    out.to_csv(out_path, index=False)

    pivot = out.pivot(index="hour", columns="instrument", values="spread_bps_mean").sort_index()
    pivot_path = out_dir / f"spread_by_hour_{args.bar}_mean_pivot.csv"
    pivot.to_csv(pivot_path, index=True)

    print(f"Saved:\n- {out_path}\n- {pivot_path}")


if __name__ == "__main__":
    main()
