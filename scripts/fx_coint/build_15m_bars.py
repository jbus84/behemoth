"""Build 15m flow bars by resampling the 1m TIME bars (time->time aggregation is
safe; the 'never resample tick-count bars' lesson applies only to tick->time).

Validates the aggregation by reproducing the existing 30m_flow bars from 1m,
then writes *_15m_flow.parquet matching the 1h/30m schema:
  bucket, mid, bid, ask, n_ticks, flow_tick, flow_ofi, rvol_bps

Usage: uv run python scripts/fx_coint/build_15m_bars.py
"""
from __future__ import annotations

import glob
import os

import numpy as np
import pandas as pd

SRC = sorted(glob.glob("data/tick_bars/*_1m_flow.parquet"))


def resample(df1m: pd.DataFrame, rule: str) -> pd.DataFrame:
    df = df1m.copy()
    df["bucket"] = pd.to_datetime(df["bucket"])
    df = df.set_index("bucket").sort_index()
    logr = np.log(df["mid"]).diff()
    g = df.resample(rule, label="right", closed="right")
    out = pd.DataFrame({
        "mid": g["mid"].last(),
        "bid": g["bid"].last(),
        "ask": g["ask"].last(),
        "n_ticks": g["n_ticks"].sum(),
        "flow_tick": g["flow_tick"].sum(),
        "flow_ofi": g["flow_ofi"].sum(),
        # realized vol within the bar, in bps, from 1m squared log-returns
        "rvol_bps": np.sqrt((logr**2).resample(rule, label="right", closed="right").sum()) * 1e4,
    })
    out = out.dropna(subset=["mid"])
    out = out[out["n_ticks"] > 0]
    return out.reset_index()


def validate_against_30m(df1m: pd.DataFrame, sym: str) -> None:
    ref_path = f"data/tick_bars/{sym}_30m_flow.parquet"
    if not os.path.exists(ref_path):
        return
    ref = pd.read_parquet(ref_path)
    ref["bucket"] = pd.to_datetime(ref["bucket"])
    mine = resample(df1m, "30min")
    m = mine.merge(ref, on="bucket", suffixes=("_mine", "_ref"), how="inner")
    if len(m) < 100:
        print(f"  [{sym}] WARN only {len(m)} overlapping 30m bars")
        return
    # correlation of key columns
    for col in ("mid", "n_ticks", "flow_ofi"):
        c = np.corrcoef(m[f"{col}_mine"], m[f"{col}_ref"])[0, 1]
        print(f"  [{sym}] 30m {col}: corr(mine,ref)={c:.4f}  "
              f"mean|rel diff|={np.nanmean(np.abs((m[f'{col}_mine']-m[f'{col}_ref'])/(m[f'{col}_ref'].abs()+1e-9))):.4f}")


def main() -> None:
    for f in SRC:
        sym = os.path.basename(f).split("_")[0]
        df1m = pd.read_parquet(f)
        if sym == "EURUSD":
            print("VALIDATION (reproduce 30m from 1m):")
            validate_against_30m(df1m, sym)
        bars15 = resample(df1m, "15min")
        out = f"data/tick_bars/{sym}_15m_flow.parquet"
        bars15.to_parquet(out)
        print(f"  wrote {out}: {len(bars15)} bars, "
              f"{bars15['bucket'].min()} -> {bars15['bucket'].max()}")


if __name__ == "__main__":
    main()
