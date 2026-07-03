"""
Stability check: does the windowed quantile-robust regression plateau found in
PR #376 (sig_thresh~4.0-4.5, sig_thresh_hi~4.8-5.5, Option B +4.8 to +5.3 bps/fill)
hold up consistently across pairs and years, or is it concentrated in one
pair/period?

Usage::

    uv run python scripts/boostlss_xs/stability_check.py \\
        --data-dir /path/to/tick_bars \\
        --tick-dir /path/to/raw_ticks \\
        [--pairs EURUSD GBPJPY AUDUSD USDJPY] \\
        [--quantile 0.85] \\
        [--sig-thresh 4.0] \\
        [--sig-thresh-hi 5.0] \\
        [--threshold 0.55]
"""
from __future__ import annotations

import argparse

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


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Stability check for windowed quantile-robust regression")
    p.add_argument("--data-dir",      default="/Users/danielfisher/repositories/behemoth/data/tick_bars")
    p.add_argument("--tick-dir",      default="/Users/danielfisher/Desktop/tick")
    p.add_argument("--pairs",         nargs="+", default=_DEFAULT_PAIRS)
    p.add_argument("--quantile",      type=float, default=0.85)
    p.add_argument("--sig-thresh",    type=float, default=4.0)
    p.add_argument("--sig-thresh-hi", type=float, default=5.0)
    p.add_argument("--threshold",     type=float, default=0.55)
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()

    per_pair_trades: dict[str, pd.DataFrame] = {}
    for sym in args.pairs:
        d = build_1h_features(sym, args.data_dir)
        X, vs = d["X"], d["vs"]
        n = len(vs)
        y = np.full(n, np.nan)
        y[:-1] = vs[1:]

        print(f"  {sym}: fitting quantile-robust WFO (q={args.quantile})...", flush=True)
        sg = fit_wfo_quantile_robust(X, y, quantile=args.quantile)

        df_sym, _ = run_tick_backtest(
            sym=sym, data_dir=args.data_dir, tick_dir=args.tick_dir,
            family="gaussian", sigma_override=sg,
            sig_thresh=args.sig_thresh, sig_thresh_hi=args.sig_thresh_hi,
        )
        if len(df_sym) > 0:
            per_pair_trades[sym] = df_sym

    if not per_pair_trades:
        print("No trades produced.")
        raise SystemExit(1)

    all_raw = pd.concat(per_pair_trades.values(), ignore_index=True)

    oos_dfs: list[pd.DataFrame] = []
    for sym, g in all_raw.groupby("sym"):
        try:
            oos_dfs.append(fit_meta_label_wfo(g.copy(), feat_cols=_FEAT_COLS))
        except Exception as e:
            print(f"  {sym}: meta-label failed — {e}")

    if not oos_dfs:
        print("Meta-labeling produced no results.")
        raise SystemExit(1)

    result = pd.concat(oos_dfs, ignore_index=True)
    pooled_ob = _option_b_net_per_fill(result, args.threshold)

    print()
    print("=" * 70)
    print(f"POOLED RESULT  sig_thresh={args.sig_thresh}  "
          f"sig_thresh_hi={args.sig_thresh_hi}  q={args.quantile}")
    print("=" * 70)
    print(f"  n_trades: {len(result)}  AUC: {result.mean_auc.mean():.3f}  "
          f"TP%: {result.label.mean():.1%}  Option B: {pooled_ob:+.3f} bps/fill")

    print()
    print("=" * 70)
    print("BY PAIR")
    print("=" * 70)
    for sym, g in result.groupby("sym"):
        ob = _option_b_net_per_fill(g, args.threshold)
        print(f"  {sym:<8}  n={len(g):>5}  AUC={g.mean_auc.mean():.3f}  "
              f"TP%={g.label.mean():.1%}  Option B={ob:+.3f} bps/fill")

    print()
    print("=" * 70)
    print("BY YEAR (pooled)")
    print("=" * 70)
    result = result.copy()
    result["year"] = result.ts.str[:4]
    for yr, g in result.groupby("year"):
        ob = _option_b_net_per_fill(g, args.threshold)
        print(f"  {yr}  n={len(g):>5}  AUC={g.mean_auc.mean():.3f}  "
              f"TP%={g.label.mean():.1%}  Option B={ob:+.3f} bps/fill")
