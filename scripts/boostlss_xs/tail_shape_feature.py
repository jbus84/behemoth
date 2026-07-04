"""
Tail-shape meta-labeler feature: does exposing a "how fat is this bar's tail"
signal to the meta-labeler help, even though baking similar information into
first-stage sigma sizing (Merton's jump-intensity, SHASH's skew/kurtosis) never
did (see BACKLOG.md's distribution comparison)?

Fits a second, lower quantile regression (default q=0.5, median |return|)
alongside the existing high quantile (default q=0.90, the sigma-sizing signal
per Task 2's quantile sweep -- q=0.90 beat q=0.85 at both tested windows),
computes their ratio (tail_ratio = high/median) at every OOS bar, and merges it
onto the trades dataframe by matching timestamps -- purely additive, no change
to run_tick_backtest's signature or sigma sizing.

Note: a trade's tail_ratio can be missing (NaN) if the low-quantile regression's
OOS prediction wasn't yet defined at that bar (WFO fold warmup) even though the
high-quantile prediction was -- fit_meta_label_wfo's dropna(subset=feat_cols)
will then drop that row only when tail_ratio is in feat_cols, so the "with
tail_ratio" variant can have a slightly smaller n_trades than the baseline.
This is expected, not a bug -- note it when interpreting results, don't try to
force matching counts.

Usage::

    uv run python scripts/boostlss_xs/tail_shape_feature.py \\
        --data-dir /path/to/tick_bars \\
        --tick-dir /path/to/raw_ticks \\
        [--pairs EURUSD GBPJPY AUDUSD USDJPY] \\
        [--high-quantile 0.90] \\
        [--low-quantile 0.5] \\
        [--sig-thresh 4.5] \\
        [--sig-thresh-hi 5.5] \\
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

_RATIO_FLOOR = 1e-6


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Tail-shape meta-labeler feature experiment")
    p.add_argument("--data-dir",      default="/Users/danielfisher/repositories/behemoth/data/tick_bars")
    p.add_argument("--tick-dir",      default="/Users/danielfisher/Desktop/tick")
    p.add_argument("--pairs",         nargs="+", default=_DEFAULT_PAIRS)
    p.add_argument("--high-quantile", type=float, default=0.90)
    p.add_argument("--low-quantile",  type=float, default=0.5)
    p.add_argument("--sig-thresh",    type=float, default=4.5)
    p.add_argument("--sig-thresh-hi", type=float, default=5.5)
    p.add_argument("--threshold",     type=float, default=0.55)
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()

    tick_dfs: list[pd.DataFrame] = []
    for sym in args.pairs:
        d = build_1h_features(sym, args.data_dir)
        X, vs, ts = d["X"], d["vs"], d["ts"]
        n = len(vs)
        y = np.full(n, np.nan)
        y[:-1] = vs[1:]

        print(f"  {sym}: fitting high (q={args.high_quantile}) + "
              f"low (q={args.low_quantile}) quantile WFO...", flush=True)
        sg_high = fit_wfo_quantile_robust(X, y, quantile=args.high_quantile)
        sg_low = fit_wfo_quantile_robust(X, y, quantile=args.low_quantile)
        tail_ratio = sg_high / np.maximum(sg_low, _RATIO_FLOOR)

        ratio_by_ts = {
            str(ts[i]): tail_ratio[i] for i in range(n) if not np.isnan(tail_ratio[i])
        }

        df_sym, _ = run_tick_backtest(
            sym=sym, data_dir=args.data_dir, tick_dir=args.tick_dir,
            family="gaussian", sigma_override=sg_high,
            sig_thresh=args.sig_thresh, sig_thresh_hi=args.sig_thresh_hi,
        )
        if len(df_sym) == 0:
            continue
        df_sym["tail_ratio"] = df_sym["ts"].map(ratio_by_ts)
        tick_dfs.append(df_sym)

    if not tick_dfs:
        print("No trades produced.")
        raise SystemExit(1)

    all_raw = pd.concat(tick_dfs, ignore_index=True)

    for label, feat_cols in [
        ("baseline (no tail_ratio)", _FEAT_COLS),
        ("with tail_ratio", [*_FEAT_COLS, "tail_ratio"]),
    ]:
        oos_dfs: list[pd.DataFrame] = []
        for sym, g in all_raw.groupby("sym"):
            try:
                oos_dfs.append(fit_meta_label_wfo(g.copy(), feat_cols=feat_cols))
            except Exception as e:
                print(f"  {sym}: meta-label failed ({label}) — {e}")
        if not oos_dfs:
            print(f"{label}: meta-labeling produced no results")
            continue
        result = pd.concat(oos_dfs, ignore_index=True)
        ob_net = _option_b_net_per_fill(result, args.threshold)
        print(f"{label:<28}  n={len(result):>5}  AUC={result.mean_auc.mean():.3f}  "
              f"TP%={result.label.mean():.1%}  Option B={ob_net:+.3f} bps/fill")
