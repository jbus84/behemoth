"""Path-aware directional model (Stage 1): does the W-bar path into an entry carry
directional information that point-in-time features miss, at N=30/50?

Flattens a window of per-bar path channels and feeds it as X to the existing
walk-forward harness (pnl_walkforward.model_oos_pnl). Benchmarks against the
point-in-time 30-feature design matrix on identical events. Per-symbol primary,
pooled reference. Verdict gates Stage 2 (torch GRU/TCN).

Usage: uv run python scripts/fx_coint/path_window_model.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from feature_ic_definitive import build_all  # noqa: E402, F401
from model_search import COST_BPS, _histgbm, build_design  # noqa: E402, F401
from sample_weights import event_weights  # noqa: E402
from sklearn.neural_network import MLPRegressor  # noqa: E402
from sklearn.pipeline import Pipeline  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402
from triple_barrier import triple_barrier_core  # noqa: E402


def path_channels(logp, f, vol) -> list[np.ndarray]:
    """Per-bar path channels in fixed order: [log_return, vol, intra_bar_mom, hl_pos_frac]."""
    log_return = np.diff(np.asarray(logp, dtype=float), prepend=float(logp[0]))
    return [log_return,
            np.asarray(vol, dtype=float),
            np.asarray(f["intra_bar_mom"], dtype=float),
            np.asarray(f["hl_pos_frac"], dtype=float)]


def build_window_matrix(channels, entry, W: int) -> np.ndarray:
    """Flatten the W-bar window ending at each entry into a (len(entry), W*C) matrix.

    Row i = concatenate over channels of ch[entry[i]-W+1 : entry[i]+1] (channel-major).
    Raises ValueError if any entry[i] < W-1 (window would underflow).
    """
    entry = np.asarray(entry)
    if entry.min() < W - 1:
        raise ValueError(f"entry index {int(entry.min())} < W-1={W - 1}; window underflows")
    rows = np.empty((len(entry), W * len(channels)), dtype=float)
    for i, e in enumerate(entry):
        rows[i] = np.concatenate([ch[e - W + 1:e + 1] for ch in channels])
    return rows


POOL = ["AUDUSD", "EURUSD", "GBPUSD", "USDCAD", "USDCHF"]
N_GRID = [30, 50]
W_GRID = [16, 32, 64]
N_EVENTS = 10000


def sample_events(cache, n_tb, W_max, rng):
    """Per-symbol sorted event indices, shared across builders for fair comparison."""
    out = {}
    for s, (logp, _f, vol, bph) in cache.items():
        n = len(logp)
        warm = max(int(96 * bph) + 60, W_max - 1)
        idx = np.arange(warm, n - n_tb - 3)
        idx = idx[np.isfinite(vol[idx + 1]) & (vol[idx + 1] > 0)]
        out[s] = np.sort(rng.choice(idx, min(N_EVENTS, len(idx)), replace=False))
    return out


def _tb_and_weights(logp, vol, ev, n_tb):
    entry = ev + 1
    n = len(logp)
    t1, ret, _, _ = triple_barrier_core(
        logp, entry, np.minimum(entry + n_tb, n - 1),
        1.0 * vol[entry] * np.sqrt(n_tb))
    bar_log_ret = np.diff(logp, prepend=logp[0])
    sw = event_weights(bar_log_ret, entry, t1)
    return entry, t1, ret, sw


def build_sym_window(cache, ev_by_sym, n_tb, W):
    """Per-symbol dicts with X = flattened W-bar path window."""
    sym_data = {}
    for s, (logp, f, vol, _bph) in cache.items():
        ev = ev_by_sym[s]
        entry, t1, ret, sw = _tb_and_weights(logp, vol, ev, n_tb)
        channels = path_channels(logp, f, vol)
        X = build_window_matrix(channels, entry, W)
        fin = np.isfinite(X).all(axis=1) & np.isfinite(ret)
        sym_data[s] = dict(X=X[fin], y=ret[fin], entry=entry[fin],
                           t1=t1[fin], ret=ret[fin], sw=sw[fin])
    return sym_data


def build_sym_pointwise(cache, ev_by_sym, n_tb):
    """Per-symbol dicts with X = existing 30-feature point-in-time design matrix."""
    sym_data = {}
    for s, (logp, f, vol, _bph) in cache.items():
        ev = ev_by_sym[s]
        entry, t1, ret, sw = _tb_and_weights(logp, vol, ev, n_tb)
        feature_names = [k for k in f if k != "ent_sign"]
        interactions = [("ffd_0.1", "ffd_zvol20")]
        X, _ = build_design(f, entry, feature_names, interactions)
        fin = np.isfinite(X).all(axis=1) & np.isfinite(ret)
        sym_data[s] = dict(X=X[fin], y=ret[fin], entry=entry[fin],
                           t1=t1[fin], ret=ret[fin], sw=sw[fin])
    return sym_data


def make_window_models(seed=0):
    """Stage-1 path models: scaled MLP + regularized HistGBM."""
    mlp = Pipeline([
        ("scale", StandardScaler()),
        ("mlp", MLPRegressor(hidden_layer_sizes=(64, 32), alpha=1e-3,
                             max_iter=300, early_stopping=True,
                             validation_fraction=0.15, random_state=seed)),
    ])
    return {"mlp": mlp, "histgbm": _histgbm(seed)}


def fit_predict_for(model):
    """fit_predict closure for model_oos_pnl. HistGBM gets sample_weight; MLP pipeline
    is fit unweighted (keeps step-prefixed sample_weight plumbing out of scope)."""
    def _fn(train_dict, test_dict):
        if isinstance(model, Pipeline):
            model.fit(train_dict["X"], train_dict["y"])
        else:
            model.fit(train_dict["X"], train_dict["y"],
                      sample_weight=train_dict.get("sw"))
        return model.predict(test_dict["X"])
    return _fn
