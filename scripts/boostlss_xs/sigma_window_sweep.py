"""
Windowed-sigma sweep: does capping the UPPER end of predicted sigma (excluding
anomalously large predictions) improve on just raising the lower sig_thresh
alone? Fixes a lower bound where trade count/AUC are known good (from
regression_threshold_sweep.py), then sweeps sig_thresh_hi.

Motivation: the strategy's own thesis is "momentum/jump bars fail, indecision
bars revert." FX hourly returns here have a small (~4.6%) but genuine jump-
driven tail (see BACKLOG.md's kurtosis analysis). A bar at the very top of the
predicted-sigma distribution is more likely to *be* one of those jump bars --
exactly the kind that historically fails to revert. Windowing to "moderately
high but not extreme" volatility directly targets that, rather than being an
arbitrary numeric knob.

Usage::

    uv run python scripts/boostlss_xs/sigma_window_sweep.py \\
        --data-dir /path/to/tick_bars \\
        --tick-dir /path/to/raw_ticks \\
        [--pairs EURUSD GBPJPY AUDUSD USDJPY] \\
        [--quantile 0.85] \\
        [--lo 3.0 4.0 4.5] \\
        [--hi 20 15 10 8 6 5] \\
        [--threshold 0.55]
"""
from __future__ import annotations

import argparse
import contextlib

import numpy as np
import pandas as pd
from meta_label_straddle import (
    _FEAT_COLS,
    _option_b_net_per_fill,
    build_1h_features,
    fit_meta_label_wfo,
    run_tick_backtest,
)
from plain_regression_baseline import _DEFAULT_PAIRS, fit_wfo_quantile_robust


def run_window(
    lo: float, hi: float | None, sigma_by_pair: dict[str, np.ndarray],
    pairs: list[str], data_dir: str, tick_dir: str, threshold: float,
) -> tuple[float, int, float] | None:
    tick_dfs: list[pd.DataFrame] = []
    for sym in pairs:
        df_sym, _ = run_tick_backtest(
            sym=sym, data_dir=data_dir, tick_dir=tick_dir,
            family="gaussian", sigma_override=sigma_by_pair[sym],
            sig_thresh=lo, sig_thresh_hi=hi, verbose=False,
        )
        if len(df_sym) > 0:
            tick_dfs.append(df_sym)
    if not tick_dfs:
        print(f"  lo={lo} hi={hi}: 0 trades")
        return None
    all_raw = pd.concat(tick_dfs, ignore_index=True)
    oos_dfs: list[pd.DataFrame] = []
    for _sym, g in all_raw.groupby("sym"):
        with contextlib.suppress(Exception):
            oos_dfs.append(fit_meta_label_wfo(g.copy(), feat_cols=_FEAT_COLS))
    if not oos_dfs:
        print(f"  lo={lo} hi={hi}: meta-labeling produced no results")
        return None
    result = pd.concat(oos_dfs, ignore_index=True)
    ob_net = _option_b_net_per_fill(result, threshold)
    hi_str = f"{hi:.1f}" if hi is not None else "None"
    print(f"  lo={lo:.2f}  hi={hi_str:>5}  n_trades={len(result):>5}  "
          f"AUC={result.mean_auc.mean():.3f}  TP%={result.label.mean():.1%}  "
          f"Option B={ob_net:+.3f} bps/fill")
    return (lo, len(result), ob_net)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Windowed-sigma sweep for quantile-robust regression")
    p.add_argument("--data-dir",   default="/Users/danielfisher/repositories/behemoth/data/tick_bars")
    p.add_argument("--tick-dir",   default="/Users/danielfisher/Desktop/tick")
    p.add_argument("--pairs",      nargs="+", default=_DEFAULT_PAIRS)
    p.add_argument("--quantile",   type=float, default=0.85)
    p.add_argument("--lo",         type=float, nargs="+", default=[3.5, 4.0, 4.5])
    p.add_argument("--hi",         type=float, nargs="+", default=[4.5, 5.0, 5.5, 6.0])
    p.add_argument("--threshold",  type=float, default=0.55)
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()

    sigma_by_pair: dict[str, np.ndarray] = {}
    for sym in args.pairs:
        d = build_1h_features(sym, args.data_dir)
        X, vs = d["X"], d["vs"]
        n = len(vs)
        y = np.full(n, np.nan)
        y[:-1] = vs[1:]
        print(f"  {sym}: fitting quantile-robust WFO...", flush=True)
        sigma_by_pair[sym] = fit_wfo_quantile_robust(X, y, quantile=args.quantile)

    results: list[tuple[float, float, int, float]] = []
    for lo in args.lo:
        print(f"\n=== lo={lo} ===")
        for hi in args.hi:
            if hi <= lo:
                continue
            r = run_window(lo, hi, sigma_by_pair, args.pairs, args.data_dir, args.tick_dir, args.threshold)
            if r is not None:
                results.append((lo, hi, r[1], r[2]))

    if results:
        best = max(results, key=lambda r: r[3])
        print(f"\nBest window: lo={best[0]}, hi={best[1]} -> Option B={best[3]:+.3f} bps/fill "
              f"(n_trades={best[2]})")
