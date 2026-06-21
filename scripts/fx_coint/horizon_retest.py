"""Uniform 1h-grid multi-horizon tail-long net-edge re-test."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.fx_coint.reg_signal_hunt import (  # noqa: E402
    COST_BPS,
    FEATURE_COLS,
    build_freq_bars,
    build_panel,
)


def build_horizon_panel(bars: pd.DataFrame, H: int, vol_lookback: int = 24) -> pd.DataFrame:
    panel = build_panel(bars, vol_lookback=vol_lookback).reset_index(drop=True)
    b = bars.reset_index(drop=True)
    mid = b["mid"].to_numpy()
    contig = b["contig"].to_numpy()
    n = len(b)
    fwd = np.full(n, np.nan)
    # forward-H window [i, i+H] valid only if bars i+1..i+H are all contiguous
    for i in range(n - H):
        if contig[i + 1:i + 1 + H].all():
            fwd[i] = (np.log(mid[i + H]) - np.log(mid[i])) * 1e4
    fwd_by_bucket = dict(zip(b["bucket"].to_numpy(), fwd, strict=False))
    rf = panel["bucket"].map(lambda x: fwd_by_bucket.get(x, np.nan)).to_numpy()
    out = panel.copy()
    out["ret_fwd_bps"] = rf
    out["target_z"] = rf / (out["sigma_h"].to_numpy() * np.sqrt(H))
    keep = np.isfinite(out["ret_fwd_bps"].to_numpy()) & np.isfinite(out["target_z"].to_numpy())
    return out[keep].reset_index(drop=True)[FEATURE_COLS + ["bucket", "sigma_h", "ret_fwd_bps", "target_z"]]


def horizon_net_track(
    sym: str,
    H: int,
    q: float = 0.95,
    n_folds: int = 5,
    min_train_frac: float = 0.5,
    purge: int = 1,
) -> dict:
    """Expanding-window WFO tail-long net track on 1h grid (overlapping entries)."""
    bars = build_freq_bars(
        pl.read_parquet(_REPO_ROOT / f"data/tick_bars/{sym}_1m_flow.parquet"), "1h"
    )
    panel = build_horizon_panel(bars, H)
    X = panel[FEATURE_COLS].to_numpy()
    yz = panel["target_z"].to_numpy()
    fwd = panel["ret_fwd_bps"].to_numpy()
    bucket = panel["bucket"].to_numpy()
    cost = COST_BPS[sym]
    n = len(panel)
    edges = np.linspace(int(n * min_train_frac), n, n_folds + 1).astype(int)
    nets, bks = [], []
    for k in range(n_folds):
        split = edges[k]
        lo, hi = edges[k] + purge, edges[k + 1]
        if hi - lo < 1 or split < 10:
            continue
        sc = StandardScaler().fit(X[:split])
        model = Ridge(alpha=1.0).fit(sc.transform(X[:split]), yz[:split])
        thr = np.quantile(model.predict(sc.transform(X[:split])), q)
        tp = model.predict(sc.transform(X[lo:hi]))
        sel = tp >= thr
        nets.append(fwd[lo:hi][sel] - cost)
        bks.append(bucket[lo:hi][sel])
    net = np.concatenate(nets) if nets else np.array([])
    bk = np.concatenate(bks) if bks else np.array([], dtype="datetime64[ns]")
    return {"net": net, "bucket": bk, "n": len(net)}
