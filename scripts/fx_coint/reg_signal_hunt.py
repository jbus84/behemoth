"""Regression signal hunt at 1/2/3/4h on FX majors, scored vs real-cost break-even IC.

Usage:
    uv run python scripts/fx_coint/reg_signal_hunt.py --freq all --symbol all
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
from scipy.stats import spearmanr
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

PAIRS = ["EURUSD", "GBPUSD", "AUDUSD", "USDJPY", "USDCHF", "USDCAD"]
COST_BPS = {"EURUSD": 0.64, "GBPUSD": 0.63, "USDJPY": 0.80,
            "USDCAD": 0.97, "USDCHF": 1.05, "AUDUSD": 1.06}
FREQS = ["1h", "2h", "3h", "4h"]
FREQ_MINUTES = {"1h": 60, "2h": 120, "3h": 180, "4h": 240}
FEATURE_COLS = ["r_1", "mom_short", "mom_long", "rvol_24", "hour"]


def build_freq_bars(
    df_1m: pl.DataFrame, freq: str, session: tuple[int, int] = (7, 21)
) -> pd.DataFrame:
    t = df_1m.sort("bucket").with_columns(
        pl.col("mid").log().diff().alias("lr1"),
        pl.col("bucket").dt.truncate(freq).alias("bf"),
    )
    bars = (
        t.group_by("bf")
        .agg(
            pl.col("mid").last(),
            pl.col("n_ticks").sum(),
            (pl.col("lr1").std() * 1e4).alias("rvol_bps"),
        )
        .rename({"bf": "bucket"})
        .sort("bucket")
        .to_pandas()
    )
    bars["bucket"] = pd.to_datetime(bars["bucket"])
    # Apply session filter BEFORE computing contig so that contig reflects
    # true adjacency in the returned frame
    hour = bars["bucket"].dt.hour
    keep = (hour >= session[0]) & (hour < session[1]) & (bars["bucket"].dt.dayofweek < 5)
    bars = bars[keep].reset_index(drop=True)
    # Now compute contig on the filtered frame
    step = np.timedelta64(FREQ_MINUTES[freq], "m")
    prev = bars["bucket"].shift(1).to_numpy()
    bars["contig"] = (bars["bucket"].to_numpy() - prev) == step
    bars.loc[0, "contig"] = False
    return bars
