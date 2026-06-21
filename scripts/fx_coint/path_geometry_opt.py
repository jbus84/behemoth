"""Causal geometry optimizer for the tail-long edge: fold-aware trades, grid search, gates."""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import polars as pl
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.fx_coint.path_geometry_paths import build_minute_index, hold_path  # noqa: E402
from scripts.fx_coint.reg_signal_hunt import (  # noqa: E402
    COST_BPS,
    FEATURE_COLS,
    build_freq_bars,
    build_panel,
)


@dataclass
class Trade:
    entry_mid: float
    minutes: np.ndarray
    side: str
    sigma_bps: float
    bucket: np.datetime64
    cost_bps: float


def _bars_panel(sym, freq):
    bars = build_freq_bars(pl.read_parquet(_REPO_ROOT / f"data/tick_bars/{sym}_1m_flow.parquet"), freq)
    panel = build_panel(bars)
    close = dict(zip(bars["bucket"].to_numpy(), bars["mid"].to_numpy(), strict=False))
    return panel, close


def _mk_trade(bk, sigma, close, bn, mids, freq, n_bars, cost_bps):
    em = close.get(bk)
    if em is None or not np.isfinite(em) or not (sigma > 0):
        return None
    mins = hold_path(bk, freq, bn, mids, n_bars=n_bars)
    if len(mins) < 1:
        return None
    return Trade(float(em), mins, "long", float(sigma), bk, float(cost_bps))


def fold_trades(sym, freq="2h", q=0.95, n_folds=5, n_bars=1, min_train_frac=0.5, purge=1):
    panel, close = _bars_panel(sym, freq)
    bn, mids = build_minute_index(sym)
    X = panel[FEATURE_COLS].to_numpy()
    yz = panel["target_z"].to_numpy()
    bucket = panel["bucket"].to_numpy()
    sig = panel["sigma_h"].to_numpy()
    n = len(panel)
    cost = COST_BPS[sym]
    edges = np.linspace(int(n * min_train_frac), n, n_folds + 1).astype(int)
    out = []
    for k in range(n_folds):
        split = edges[k]
        test_lo, test_hi = edges[k] + purge, edges[k + 1]
        if test_hi - test_lo < 1 or split < 10:
            continue
        scaler = StandardScaler().fit(X[:split])
        model = Ridge(alpha=1.0).fit(scaler.transform(X[:split]), yz[:split])
        train_pred = model.predict(scaler.transform(X[:split]))
        test_pred = model.predict(scaler.transform(X[test_lo:test_hi]))
        thr = np.quantile(train_pred, q)
        tr = [_mk_trade(bucket[i], sig[i], close, bn, mids, freq, n_bars, cost)
              for i in np.where(train_pred >= thr)[0]]
        te = [_mk_trade(bucket[test_lo + j], sig[test_lo + j], close, bn, mids, freq, n_bars, cost)
              for j in np.where(test_pred >= thr)[0]]
        out.append({"train": [t for t in tr if t], "test": [t for t in te if t]})
    return out
