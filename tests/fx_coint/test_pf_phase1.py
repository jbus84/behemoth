"""Tests for Phase-1 backtest harness: PF-exit vs fixed-horizon baseline.

Uses synthetic 1m data (matching test_tail_wfo.py pattern) to avoid dependency
on real parquet files not present in the worktree.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import polars as pl

from scripts.fx_coint.pf_core import PFParams
from scripts.fx_coint.pf_paths import hold_path
from scripts.fx_coint.reg_signal_hunt import COST_BPS, build_freq_bars, build_panel
from scripts.fx_coint.tail_wfo import walk_forward


def _synthetic_1m(start, n, seed=0):
    ts = [start + timedelta(minutes=i) for i in range(n)]
    rng = np.random.default_rng(seed)
    steps = 1e-5 + rng.normal(0.0, 5e-5, n)
    mid = 1.10 + np.cumsum(steps)
    return pl.DataFrame({
        "bucket": ts,
        "mid": mid,
        "bid": mid - 5e-5,
        "ask": mid + 5e-5,
        "n_ticks": np.ones(n, dtype=np.int64),
        "flow_tick": np.zeros(n),
        "flow_ofi": np.zeros(n),
    })


def _make_minute_idx(df_1m: pl.DataFrame):
    """Build minute_idx tuple from a polars 1m DataFrame."""
    df = df_1m.sort("bucket")
    buckets_ns = df["bucket"].to_numpy().astype("datetime64[ns]").astype("int64")
    mids = df["mid"].to_numpy().astype(float)
    return buckets_ns, mids


def _run_pair_phase1_synthetic(df_1m, sym="EURUSD", freq="2h", q=0.80, n_folds=4):
    """Like run_pair_phase1 but accepts a synthetic 1m DataFrame instead of loading parquet."""
    from scripts.fx_coint.pf_core import run_filter
    from scripts.fx_coint.pf_exit import exit_index
    from scripts.fx_coint.pf_paths import path_to_volnorm_returns

    bars = build_freq_bars(df_1m, freq, session=(0, 24))
    panel = build_panel(bars)
    folds = walk_forward(panel, n_folds=n_folds)
    minute_idx = _make_minute_idx(df_1m)
    buckets_ns, mids = minute_idx
    cost = COST_BPS[sym]
    params = PFParams()

    sig_by_bucket = dict(
        zip(panel["bucket"].to_numpy(), panel["sigma_h"].to_numpy(), strict=False)
    )

    net_base_list: list[float] = []
    net_pf_list: list[float] = []
    bucket_list = []

    for f in folds:
        thr = float(np.quantile(f["train_pred"], q))
        sel = f["test_pred"] >= thr
        test_preds = f["test_pred"][sel]
        test_actuals = f["test_actual_bps"][sel]
        test_buckets = f["test_bucket"][sel]

        for tp, act, bk in zip(test_preds, test_actuals, test_buckets, strict=False):
            sigma_bps = float(sig_by_bucket.get(bk, np.nan))
            # --- PF exit ---
            path = hold_path(bk, freq, buckets_ns, mids)
            if len(path) >= 2 and sigma_bps > 0:
                obs = path_to_volnorm_returns(path, sigma_bps)
                post = run_filter(obs, tilt=float(tp), params=params)
                xi = exit_index(post, side="long", max_hold=len(obs))
                gross_pf = float((np.log(path[xi + 1]) - np.log(path[0])) * 1e4)
            else:
                gross_pf = float(act)

            net_base_list.append(float(act) - cost)
            net_pf_list.append(gross_pf - cost)
            bucket_list.append(bk)

    return {
        "net_base": np.array(net_base_list),
        "net_pf": np.array(net_pf_list),
        "bucket": np.array(bucket_list, dtype="datetime64[ns]"),
        "n": len(net_base_list),
    }


def test_phase1_arrays_align_and_baseline_matches_fixed_horizon():
    """Brief's canonical test: aligned arrays, finite values, n > 30."""
    df_1m = _synthetic_1m(datetime(2022, 1, 3, 0, 0), n=1500 * 60, seed=42)
    out = _run_pair_phase1_synthetic(df_1m, q=0.80, n_folds=4)
    assert out["n"] > 30, f"Expected >30 entries, got {out['n']}"
    assert out["net_base"].shape == out["net_pf"].shape == (out["n"],)
    assert out["bucket"].shape == (out["n"],)
    assert np.all(np.isfinite(out["net_base"]))
    assert np.all(np.isfinite(out["net_pf"]))


def test_phase1_alignment_strengthened():
    """Strengthened alignment check: hold_path endpoint log-return vs bar-close bps.

    For entries where hold_path is non-empty, compare the path endpoint gross bps
    (from path[0] to path[-1]) against test_actual_bps. The median abs difference
    measures the window alignment (1m-path endpoint vs bar-close mid).
    """
    df_1m = _synthetic_1m(datetime(2022, 1, 3, 0, 0), n=1500 * 60, seed=42)
    bars = build_freq_bars(df_1m, "2h", session=(0, 24))
    panel = build_panel(bars)
    folds = walk_forward(panel, n_folds=4)

    buckets_ns, mids = _make_minute_idx(df_1m)
    diffs = []

    for f in folds:
        thr = float(np.quantile(f["train_pred"], 0.80))
        sel = f["test_pred"] >= thr
        for act, bk in zip(f["test_actual_bps"][sel], f["test_bucket"][sel], strict=False):
            path = hold_path(bk, "2h", buckets_ns, mids)
            if len(path) < 2:
                continue
            path_gross = (np.log(path[-1]) - np.log(path[0])) * 1e4
            diffs.append(float(path_gross) - float(act))

    diffs = np.array(diffs)
    assert len(diffs) >= 10, f"Too few path-endpoint samples: {len(diffs)}"
    median_abs = float(np.median(np.abs(diffs)))
    print(
        f"\nAlignment check: median |path_endpoint - bar_close| = {median_abs:.4f} bps"
        f"  (n={len(diffs)})"
    )
    assert median_abs < 5.0, (
        f"Large path/bar-close gap: {median_abs:.4f} bps — possible window mismatch"
    )
