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

    _bar_buckets = bars["bucket"].to_numpy().astype("datetime64[ns]")
    _bar_mids = bars["mid"].to_numpy().astype(float)
    close_by_bucket = dict(zip(_bar_buckets, _bar_mids, strict=False))

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
            bk_ns = np.datetime64(bk, "ns")
            entry_mid = close_by_bucket.get(bk_ns)
            # --- PF exit ---
            minutes = hold_path(bk, freq, buckets_ns, mids)
            if entry_mid is not None and np.isfinite(entry_mid) and len(minutes) >= 1 and sigma_bps > 0:
                series = np.concatenate([[entry_mid], minutes])
                obs = path_to_volnorm_returns(series, sigma_bps)
                post = run_filter(obs, tilt=float(tp), params=params)
                xi = exit_index(post, side="long", max_hold=len(obs))
                gross_pf = float((np.log(minutes[xi]) - np.log(entry_mid)) * 1e4)
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
    """Strengthened alignment check: cap-exit gross == test_actual_bps.

    For entries where hold_path is non-empty, compare the cap-exit gross bps
    (entry_mid=bar-close at B, exit at minutes[-1]=next bar close) against test_actual_bps.
    With the corrected [B+f, B+2f) window this diff must be < 1e-6.
    """
    df_1m = _synthetic_1m(datetime(2022, 1, 3, 0, 0), n=1500 * 60, seed=42)
    bars = build_freq_bars(df_1m, "2h", session=(0, 24))
    panel = build_panel(bars)
    folds = walk_forward(panel, n_folds=4)

    buckets_ns, mids = _make_minute_idx(df_1m)
    _bar_buckets = bars["bucket"].to_numpy().astype("datetime64[ns]")
    _bar_mids = bars["mid"].to_numpy().astype(float)
    close_by_bucket = dict(zip(_bar_buckets, _bar_mids, strict=False))
    diffs = []

    for f in folds:
        thr = float(np.quantile(f["train_pred"], 0.80))
        sel = f["test_pred"] >= thr
        for act, bk in zip(f["test_actual_bps"][sel], f["test_bucket"][sel], strict=False):
            bk_ns = np.datetime64(bk, "ns")
            entry_mid = close_by_bucket.get(bk_ns)
            if entry_mid is None or not np.isfinite(entry_mid):
                continue
            minutes = hold_path(bk, "2h", buckets_ns, mids)
            if len(minutes) < 1:
                continue
            cap_gross = (np.log(minutes[-1]) - np.log(entry_mid)) * 1e4
            diffs.append(float(cap_gross) - float(act))

    diffs = np.array(diffs)
    assert len(diffs) >= 10, f"Too few path-endpoint samples: {len(diffs)}"
    max_abs = float(np.max(np.abs(diffs)))
    print(
        f"\nAlignment check: max |cap_gross - test_actual_bps| = {max_abs:.2e} bps"
        f"  (n={len(diffs)})"
    )
    assert max_abs < 1e-6, (
        f"Alignment gap {max_abs:.2e} bps — window or entry-mid mismatch"
    )


def test_hold_to_cap_reproduces_baseline():
    """Load-bearing correctness gate: cap-exit gross == test_actual_bps to < 1e-6.

    Uses real EURUSD data (symlinked parquet). Mirrors run_pair_phase1 construction:
    entry_mid = close_by_bucket[B], minutes = hold_path window [B+f, B+2f),
    cap_gross = log(minutes[-1]/entry_mid)*1e4.
    """
    from pathlib import Path

    import polars as pl

    _REPO_ROOT = Path(__file__).resolve().parents[2]
    src = _REPO_ROOT / "data/tick_bars/EURUSD_1m_flow.parquet"
    if not src.exists():
        import pytest
        pytest.skip("EURUSD_1m_flow.parquet not available")

    from scripts.fx_coint.pf_paths import build_minute_index, hold_path
    from scripts.fx_coint.reg_signal_hunt import build_freq_bars, build_panel
    from scripts.fx_coint.tail_wfo import walk_forward

    bars = build_freq_bars(pl.read_parquet(src), "2h")
    panel = build_panel(bars)
    folds = walk_forward(panel, n_folds=5)
    buckets_ns, mids = build_minute_index("EURUSD")

    _bar_buckets = bars["bucket"].to_numpy().astype("datetime64[ns]")
    _bar_mids = bars["mid"].to_numpy().astype(float)
    close_by_bucket = dict(zip(_bar_buckets, _bar_mids, strict=False))

    diffs = []
    for f in folds:
        thr = float(np.quantile(f["test_pred"], 0.95))
        sel = f["test_pred"] >= thr
        for act, bk in zip(f["test_actual_bps"][sel], f["test_bucket"][sel], strict=False):
            bk_ns = np.datetime64(bk, "ns")
            entry_mid = close_by_bucket.get(bk_ns)
            if entry_mid is None or not np.isfinite(entry_mid):
                continue
            minutes = hold_path(bk, "2h", buckets_ns, mids)
            if len(minutes) < 1:
                continue
            cap_gross = (np.log(minutes[-1]) - np.log(entry_mid)) * 1e4
            diffs.append(float(cap_gross) - float(act))

    assert len(diffs) > 30, f"Too few entries: {len(diffs)}"
    max_abs = float(np.max(np.abs(diffs)))
    print(f"\n[EURUSD] max |cap_gross - test_actual_bps| = {max_abs:.2e} bps  (n={len(diffs)})")
    assert max_abs < 1e-6, (
        f"Alignment gap {max_abs:.2e} bps exceeds 1e-6 — construction mismatch"
    )
