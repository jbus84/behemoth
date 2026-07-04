"""
Quantile level sweep: PR #376 only tested quantile=0.85 for the sigma-predicting
regressor itself. Does a different quantile level raise the whole baseline
before optimizing the window further?

Tests a small set of quantile levels at a couple of representative windows
(not a full grid -- keeps compute bounded).

Usage::

    uv run python scripts/boostlss_xs/quantile_level_sweep.py \\
        --data-dir /path/to/tick_bars \\
        --tick-dir /path/to/raw_ticks \\
        [--pairs EURUSD GBPJPY AUDUSD USDJPY] \\
        [--quantiles 0.70 0.75 0.80 0.85 0.90 0.95] \\
        [--windows 4.0:5.0 4.5:5.5] \\
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


def _parse_window(s: str) -> tuple[float, float]:
    lo_str, hi_str = s.split(":")
    return float(lo_str), float(hi_str)


def run_window(
    lo: float,
    hi: float,
    sigma_by_pair: dict[str, np.ndarray],
    pairs: list[str],
    data_dir: str,
    tick_dir: str,
    threshold: float,
) -> tuple[int, float, float] | None:
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
        return None
    all_raw = pd.concat(tick_dfs, ignore_index=True)
    oos_dfs: list[pd.DataFrame] = []
    for _sym, g in all_raw.groupby("sym"):
        try:
            oos_dfs.append(fit_meta_label_wfo(g.copy(), feat_cols=_FEAT_COLS))
        except Exception as e:
            print(f"  {_sym}: meta-label failed — {e}")
    if not oos_dfs:
        return None
    result = pd.concat(oos_dfs, ignore_index=True)
    ob_net = _option_b_net_per_fill(result, threshold)
    return (len(result), result.mean_auc.mean(), ob_net)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Quantile level sweep for the sigma regressor")
    p.add_argument("--data-dir",  default="/Users/danielfisher/repositories/behemoth/data/tick_bars")
    p.add_argument("--tick-dir",  default="/Users/danielfisher/Desktop/tick")
    p.add_argument("--pairs",     nargs="+", default=_DEFAULT_PAIRS)
    p.add_argument("--quantiles", type=float, nargs="+",
                    default=[0.70, 0.75, 0.80, 0.85, 0.90, 0.95])
    p.add_argument("--windows",   type=str, nargs="+", default=["4.0:5.0", "4.5:5.5"],
                    help="lo:hi pairs, e.g. 4.0:5.0")
    p.add_argument("--threshold", type=float, default=0.55)
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    windows = [_parse_window(w) for w in args.windows]

    d_by_pair: dict[str, dict] = {}
    for sym in args.pairs:
        d_by_pair[sym] = build_1h_features(sym, args.data_dir)

    print(f"{'Quantile':>9}  {'Window':>12}  {'n_trades':>8}  {'AUC':>6}  "
          f"{'Option B bps/fill':>18}")
    for q in args.quantiles:
        sigma_by_pair: dict[str, np.ndarray] = {}
        for sym in args.pairs:
            d = d_by_pair[sym]
            X, vs = d["X"], d["vs"]
            n = len(vs)
            y = np.full(n, np.nan)
            y[:-1] = vs[1:]
            sigma_by_pair[sym] = fit_wfo_quantile_robust(X, y, quantile=q)

        for lo, hi in windows:
            r = run_window(lo, hi, sigma_by_pair, args.pairs, args.data_dir,
                            args.tick_dir, args.threshold)
            window_str = f"{lo}:{hi}"
            if r is None:
                print(f"{q:>9.2f}  {window_str:>12}  {'0':>8}  {'--':>6}  {'--':>18}")
                continue
            n_trades, auc, ob = r
            print(f"{q:>9.2f}  {window_str:>12}  {n_trades:>8}  {auc:>6.3f}  {ob:>+18.3f}")
