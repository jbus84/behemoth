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

import pandas as pd  # noqa: E402

from scripts.fx_coint.path_bracket import evaluate_bracket  # noqa: E402
from scripts.fx_coint.path_geometry_paths import build_minute_index, hold_path  # noqa: E402
from scripts.fx_coint.reg_signal_hunt import (  # noqa: E402
    COST_BPS,
    FEATURE_COLS,
    build_freq_bars,
    build_panel,
)
from scripts.fx_coint.tail_wfo import day_clustered_tstat  # noqa: E402


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


_STOPS = [None, 1.0, 1.5, 2.0, 3.0]
_TPS = [None, 2.0, 3.0, 4.0]
GRID = [(s, t) for s in _STOPS for t in _TPS]
BASELINE_CELL = (None, None)


def cell_net(trades, cell):
    s, t = cell
    return np.array([evaluate_bracket(tr.entry_mid, tr.minutes, tr.side, tr.sigma_bps,
                                      s, t, tr.cost_bps) for tr in trades], dtype=float)


def optimize_geometry(folds):
    net_oos, bk_oos, base_oos, cells = [], [], [], []
    for f in folds:
        if not f["train"] or not f["test"]:
            continue
        best, best_mean = BASELINE_CELL, -np.inf
        for cell in GRID:
            m = np.nanmean(cell_net(f["train"], cell))
            if m > best_mean:
                best_mean, best = m, cell
        te_net = cell_net(f["test"], best)
        te_base = cell_net(f["test"], BASELINE_CELL)
        net_oos.append(te_net)
        base_oos.append(te_base)
        bk_oos.append(np.array([tr.bucket for tr in f["test"]], dtype="datetime64[ns]"))
        cells.append(best)
    return {"net_oos": np.concatenate(net_oos), "baseline_oos": np.concatenate(base_oos),
            "bucket_oos": np.concatenate(bk_oos), "selected_cells": cells}


def year_block_bootstrap_ci(net, bucket, n_boot=3000, seed=0):
    rng = np.random.default_rng(seed)
    s = pd.Series(np.asarray(net, float), index=pd.to_datetime(pd.Series(bucket)).dt.year)
    blocks = [g.to_numpy() for _, g in s.groupby(level=0)]
    if len(blocks) < 2:
        return float("nan"), float("nan")
    means = np.empty(n_boot)
    for b in range(n_boot):
        pick = rng.integers(0, len(blocks), len(blocks))
        means[b] = np.concatenate([blocks[i] for i in pick]).mean()
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def positive_years(net, bucket):
    yr = pd.Series(np.asarray(net, float), index=pd.to_datetime(pd.Series(bucket)).dt.year)
    m = yr.groupby(level=0).mean()
    return int((m > 0).sum()), int(len(m))


def paired_day_clustered_p(net, baseline, bucket):
    diff = np.asarray(net, float) - np.asarray(baseline, float)
    dc = day_clustered_tstat(diff, bucket)
    return {"n_days": dc["n_days"], "mean_diff": dc["daily_mean"],
            "t_stat": dc["t_stat"], "p_value": dc["p_value"]}


def gate2(opt):
    net, base, bk = opt["net_oos"], opt["baseline_oos"], opt["bucket_oos"]
    pdc = paired_day_clustered_p(net, base, bk)
    lo, hi = year_block_bootstrap_ci(net - base, bk)
    pos, ny = positive_years(net - base, bk)
    return {"mean_base": float(np.nanmean(base)), "mean_geom": float(np.nanmean(net)),
            "mean_diff": pdc["mean_diff"], "day_t": pdc["t_stat"], "day_p": pdc["p_value"],
            "ci_lo": lo, "ci_hi": hi, "pos_y": pos, "n_y": ny}


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
