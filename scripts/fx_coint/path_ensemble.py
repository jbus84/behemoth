"""Conditional and matched-unconditional 1-minute path ensembles for an edge."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.fx_coint.path_geometry_paths import build_minute_index, hold_path  # noqa: E402
from scripts.fx_coint.path_metrics import path_excursions  # noqa: E402
from scripts.fx_coint.reg_signal_hunt import (  # noqa: E402
    build_freq_bars,
    build_panel,
)
from scripts.fx_coint.tail_wfo import walk_forward  # noqa: E402


def _panel_and_closes(sym, freq):
    bars = build_freq_bars(pl.read_parquet(_REPO_ROOT / f"data/tick_bars/{sym}_1m_flow.parquet"), freq)
    panel = build_panel(bars)
    close = dict(zip(bars["bucket"].to_numpy(), bars["mid"].to_numpy(), strict=False))
    sig = dict(zip(panel["bucket"].to_numpy(), panel["sigma_h"].to_numpy(), strict=False))
    return panel, close, sig


def tail_long_entries(sym, freq="2h", q=0.95, n_folds=5):
    panel, _close, sig = _panel_and_closes(sym, freq)
    folds = walk_forward(panel, n_folds=n_folds)
    out = []
    for f in folds:
        thr = np.quantile(f["train_pred"], q)
        sel = f["test_pred"] >= thr
        for bk in f["test_bucket"][sel]:
            s = float(sig.get(bk, np.nan))
            if np.isfinite(s) and s > 0:
                out.append((bk, "long", s))
    return out


_NS_PER_DAY = 86_400_000_000_000


def offset_placebo_entries(sym, freq, signal_entries, min_off_days=3, max_off_days=60, seed=0):
    """Null = real entries shifted by a random whole-day offset (same time-of-day).

    Decouples the signal moment from the path while holding pair/hour/regime fixed.
    Whole-day shift preserves time-of-day exactly; |offset| >= min_off_days guarantees
    the shifted hold window cannot overlap the original (hold << 1 day for intraday edges,
    and >= a few days for the daily reversion edge — set min_off_days accordingly).
    """
    rng = np.random.default_rng(seed)
    panel, _close, sig = _panel_and_closes(sym, freq)
    valid = {int(np.datetime64(b, "ns").astype("int64")): b for b in panel["bucket"].to_numpy()
             if np.isfinite(sig.get(b, np.nan)) and sig.get(b, 0) > 0}
    signal_ns = {int(np.datetime64(b, "ns").astype("int64")) for b, _, _ in signal_entries}
    out = []
    for b, side, _s in signal_entries:
        b_ns = int(np.datetime64(b, "ns").astype("int64"))
        placed = False
        for _ in range(20):  # retry until a valid, non-signal, in-panel slot is found
            k = int(rng.integers(min_off_days, max_off_days + 1)) * (1 if rng.random() < 0.5 else -1)
            cand = b_ns + k * _NS_PER_DAY
            if cand in valid and cand not in signal_ns:
                out.append((valid[cand], side, float(sig.get(valid[cand]))))
                placed = True
                break
        # if no slot found in 20 tries, drop this entry (keeps the null clean)
        _ = placed
    return out


def jittered_entries(signal_entries, bars, freq, k_bars, sig):
    """Small-offset robustness: shift each entry by k_bars (can be +/-) within the panel.

    bars = panel bucket array (sorted); returns entries at bucket index +k_bars where valid.
    """
    idx_of = {int(np.datetime64(b, "ns").astype("int64")): i for i, b in enumerate(bars)}
    out = []
    for b, side, _s in signal_entries:
        i = idx_of.get(int(np.datetime64(b, "ns").astype("int64")))
        if i is None:
            continue
        j = i + k_bars
        if 0 <= j < len(bars):
            bj = bars[j]
            s = float(sig.get(bj, np.nan))
            if np.isfinite(s) and s > 0:
                out.append((bj, side, s))
    return out


def build_ensemble(sym, entries, freq, n_bars=1):
    _panel, close, _sig = _panel_and_closes(sym, freq)
    bn, mids = build_minute_index(sym)
    rows = []
    for bk, side, sigma_bps in entries:
        entry_mid = close.get(bk)
        if entry_mid is None or not np.isfinite(entry_mid):
            continue
        minutes = hold_path(bk, freq, bn, mids, n_bars=n_bars)
        ex = path_excursions(float(entry_mid), minutes, side, sigma_bps)
        if ex["n_steps"] == 0:
            continue
        rows.append({"bucket": bk, "sigma_bps": sigma_bps, **ex})
    return pd.DataFrame(rows)
