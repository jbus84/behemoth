"""
sig_thresh sweep for plain-regression sigma sources (see plain_regression_baseline.py
for the two variants and the motivating findings).

Every strategy hyperparameter (sig_thresh, entry_k, sl_k) was originally tuned
around GaussianLSS's specific sigma scale across years of prior work (PR #367
onward). A non-BoostLSS sigma source has a different natural scale, so reusing
Gaussian's sig_thresh=1.5 unmodified understates what that source can do.
Sigma is fit ONCE per (pair, variant) and cached; only the cheap candidate-
generation + tick-exact backtest step reruns per threshold value.

Usage::

    uv run python scripts/boostlss_xs/regression_threshold_sweep.py \\
        --data-dir /path/to/tick_bars \\
        --tick-dir /path/to/raw_ticks \\
        [--pairs EURUSD GBPJPY AUDUSD USDJPY] \\
        [--variant squared_error|quantile] \\
        [--quantile 0.85] \\
        [--sig-thresh-sweep 0.5 1.0 1.5 2.0 2.5 3.0] \\
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
from plain_regression_baseline import (
    _DEFAULT_PAIRS,
    fit_wfo_quantile_robust,
    fit_wfo_squared_error,
)


def run_threshold_sweep(
    variant_name: str,
    sigma_by_pair: dict[str, np.ndarray],
    pairs: list[str],
    data_dir: str,
    tick_dir: str,
    sig_thresh_sweep: list[float],
    meta_threshold: float,
) -> None:
    print(f"\n{'='*76}\nVariant: {variant_name}\n{'='*76}")
    results: list[tuple[float, int, float]] = []
    for thresh in sig_thresh_sweep:
        tick_dfs: list[pd.DataFrame] = []
        for sym in pairs:
            df_sym, _ = run_tick_backtest(
                sym=sym, data_dir=data_dir, tick_dir=tick_dir,
                family="gaussian", sigma_override=sigma_by_pair[sym],
                sig_thresh=thresh, verbose=False,
            )
            if len(df_sym) > 0:
                tick_dfs.append(df_sym)
        if not tick_dfs:
            print(f"  sig_thresh={thresh}: 0 trades")
            continue
        all_raw = pd.concat(tick_dfs, ignore_index=True)
        oos_dfs: list[pd.DataFrame] = []
        for _sym, g in all_raw.groupby("sym"):
            with contextlib.suppress(Exception):
                oos_dfs.append(fit_meta_label_wfo(g.copy(), feat_cols=_FEAT_COLS))
        if not oos_dfs:
            print(f"  sig_thresh={thresh}: meta-labeling produced no results")
            continue
        result = pd.concat(oos_dfs, ignore_index=True)
        ob_net = _option_b_net_per_fill(result, meta_threshold)
        print(f"  sig_thresh={thresh:.2f}  n_trades={len(result):>5}  "
              f"AUC={result.mean_auc.mean():.3f}  TP%={result.label.mean():.1%}  "
              f"Option B={ob_net:+.3f} bps/fill")
        results.append((thresh, len(result), ob_net))

    if results:
        best = max(results, key=lambda r: r[2])
        print(f"\n  Best for {variant_name}: sig_thresh={best[0]:.2f} -> "
              f"Option B={best[2]:+.3f} bps/fill (n_trades={best[1]})")
        print("  Caution: if Option B is still climbing at the sweep's highest "
              "threshold, the true peak is untested and trade count is falling "
              "-- extend the sweep before trusting the top of the curve.")


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="sig_thresh sweep for plain-regression sigma sources")
    p.add_argument("--data-dir",   default="/Users/danielfisher/repositories/behemoth/data/tick_bars")
    p.add_argument("--tick-dir",   default="/Users/danielfisher/Desktop/tick")
    p.add_argument("--pairs",      nargs="+", default=_DEFAULT_PAIRS)
    p.add_argument("--variant",    choices=["squared_error", "quantile", "both"], default="both")
    p.add_argument("--quantile",   type=float, default=0.85)
    p.add_argument("--sig-thresh-sweep", type=float, nargs="+",
                    default=[0.5, 1.0, 1.5, 2.0, 2.5, 3.0])
    p.add_argument("--threshold",  type=float, default=0.55)
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()

    sigma_by_variant: dict[str, dict[str, np.ndarray]] = {}
    variants = ["squared_error", "quantile"] if args.variant == "both" else [args.variant]
    for v in variants:
        sigma_by_variant[v] = {}

    for sym in args.pairs:
        d = build_1h_features(sym, args.data_dir)
        X, vs = d["X"], d["vs"]
        n = len(vs)
        y = np.full(n, np.nan)
        y[:-1] = vs[1:]

        print(f"  {sym}: fitting {'+'.join(variants)} WFO...", flush=True)
        if "squared_error" in variants:
            sigma_by_variant["squared_error"][sym] = fit_wfo_squared_error(X, y)
        if "quantile" in variants:
            sigma_by_variant["quantile"][sym] = fit_wfo_quantile_robust(X, y, quantile=args.quantile)

    for v in variants:
        run_threshold_sweep(
            f"{v} (sig_thresh sweep)", sigma_by_variant[v], args.pairs,
            args.data_dir, args.tick_dir, args.sig_thresh_sweep, args.threshold,
        )
