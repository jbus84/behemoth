"""
Plain-regression baseline for the reversion-OCO sigma signal.

Question: does the BoostLSS distributional-regression framework (joint
location-scale-shape likelihood optimization) earn its keep over a plain
gradient-boosted regressor with no distributional framework at all?

Two variants, both run through the *exact* same candidate-generation +
tick-exact backtest + meta-labeler pipeline as every BoostLSS family
(via run_tick_backtest's sigma_override), for a fully fair comparison:

  squared_error — HistGradientBoostingRegressor fit to y**2 (squared next-bar
                  return), sigma = sqrt(predicted variance). The direct
                  "plain regression" analog of what GaussianLSS's sigma
                  estimates.
  quantile      — HistGradientBoostingRegressor with loss="quantile" fit to
                  |y| directly. Far less sensitive to the rare large-jump
                  tail than squared-error (squaring amplifies outliers),
                  since FX hourly returns here have extreme excess kurtosis
                  (+15 to +45 full-sample) driven by ~4.6% of bars that are
                  genuine jump events -- trimming just the top/bottom 0.5%
                  drops excess kurtosis to a much more modest +2.4/+2.6.

Key findings (2026-07, see BACKLOG.md for the full writeup):
  - GaussianLSS's own sigma is a *worse* pure volatility forecast than plain
    squared-error regression (2-7x lower correlation with realized y**2 on
    held-out data), yet still narrowly wins on Option B economics at
    Gaussian's own tuned sig_thresh=1.5 -- strong evidence that much of
    Gaussian's edge is inherited from every other strategy hyperparameter
    having been implicitly tuned around its specific sigma scale, not a
    fundamental statistical advantage.
  - Confirmed directly: re-tuning sig_thresh for squared-error regression
    (untested at Gaussian's default 1.5) takes it from worse than Gaussian
    (+0.774) to beating it (+1.409 bps/fill at sig_thresh=3.0).
  - The quantile-robust variant is a much stronger signal outright: up to
    +3.715 bps/fill at sig_thresh=3.0 (4x Gaussian's tuned baseline), with
    high TP% (79%) and decent AUC (0.78) -- not just a threshold artifact.
  - Neither sweep had peaked as of sig_thresh=3.0 (still climbing) --
    extend the sweep and watch trade count (falls to ~3.7k/6.7k at the top
    of the tested range) before trusting the very top of the curve; fewer
    trades means more sampling noise in the reported average.

Usage::

    uv run python scripts/boostlss_xs/plain_regression_baseline.py \\
        --data-dir /path/to/tick_bars \\
        --tick-dir /path/to/raw_ticks \\
        --output-dir /tmp/plain_regression \\
        [--pairs EURUSD GBPJPY AUDUSD USDJPY] \\
        [--variant squared_error|quantile] \\
        [--quantile 0.85] \\
        [--sig-thresh 1.5] \\
        [--threshold 0.55]
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

import numpy as np
import pandas as pd
from meta_label_straddle import (
    _FEAT_COLS,
    _MAX_TRAIN,
    _N_FOLDS,
    _option_b_net_per_fill,
    build_1h_features,
    fit_meta_label_wfo,
    run_tick_backtest,
)
from sklearn.ensemble import HistGradientBoostingRegressor

_DEFAULT_PAIRS: list[str] = ["EURUSD", "GBPJPY", "AUDUSD", "USDJPY"]


def fit_wfo_squared_error(X: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Squared-error regression on y**2; sigma = sqrt(predicted variance).
    Same 5-fold expanding WFO + embargo=8 + 20K train cap as fit_wfo_dist."""
    n = len(y)
    sg_oos = np.full(n, np.nan)
    y2 = y ** 2
    fold_size = n // (_N_FOLDS + 1)
    for fi in range(_N_FOLDS):
        tr_end = fold_size * (fi + 1)
        te_start = tr_end + 8
        te_end = min(te_start + fold_size, n)
        if te_end <= te_start:
            break
        ok = ~(np.isnan(X[:tr_end]).any(axis=1) | np.isnan(y2[:tr_end]))
        idx = np.where(ok)[0]
        if len(idx) > _MAX_TRAIN:
            idx = np.random.default_rng(42 + fi).choice(idx, _MAX_TRAIN, replace=False)
            idx.sort()
        if len(idx) < 200:
            continue
        model = HistGradientBoostingRegressor(
            max_iter=200, max_depth=3, learning_rate=0.1, loss="squared_error", random_state=42
        )
        model.fit(X[idx], y2[idx])
        pred_var = model.predict(X[te_start:te_end])
        sg_oos[te_start:te_end] = np.sqrt(np.maximum(pred_var, 0.0))
    return sg_oos


def fit_wfo_quantile_robust(X: np.ndarray, y: np.ndarray, quantile: float = 0.85) -> np.ndarray:
    """Quantile regression on |y| directly -- robust to the jump tail that
    squared-error regression (and GaussianLSS's own MLE) get distorted by."""
    n = len(y)
    sg_oos = np.full(n, np.nan)
    abs_y = np.abs(y)
    fold_size = n // (_N_FOLDS + 1)
    for fi in range(_N_FOLDS):
        tr_end = fold_size * (fi + 1)
        te_start = tr_end + 8
        te_end = min(te_start + fold_size, n)
        if te_end <= te_start:
            break
        ok = ~(np.isnan(X[:tr_end]).any(axis=1) | np.isnan(abs_y[:tr_end]))
        idx = np.where(ok)[0]
        if len(idx) > _MAX_TRAIN:
            idx = np.random.default_rng(42 + fi).choice(idx, _MAX_TRAIN, replace=False)
            idx.sort()
        if len(idx) < 200:
            continue
        model = HistGradientBoostingRegressor(
            max_iter=200, max_depth=3, learning_rate=0.1,
            loss="quantile", quantile=quantile, random_state=42,
        )
        model.fit(X[idx], abs_y[idx])
        pred = model.predict(X[te_start:te_end])
        sg_oos[te_start:te_end] = np.maximum(pred, 0.0)
    return sg_oos


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Plain-regression baseline vs BoostLSS sigma")
    p.add_argument("--data-dir",   default="/Users/danielfisher/repositories/behemoth/data/tick_bars")
    p.add_argument("--tick-dir",   default="/Users/danielfisher/Desktop/tick")
    p.add_argument("--output-dir", default="/tmp/plain_regression")
    p.add_argument("--pairs",      nargs="+", default=_DEFAULT_PAIRS)
    p.add_argument("--variant",    choices=["squared_error", "quantile"], default="squared_error")
    p.add_argument("--quantile",   type=float, default=0.85)
    p.add_argument("--sig-thresh", type=float, default=1.5)
    p.add_argument("--threshold",  type=float, default=0.55)
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    Path(args.output_dir).mkdir(parents=True, exist_ok=True)

    tick_dfs: list[pd.DataFrame] = []
    for sym in args.pairs:
        d = build_1h_features(sym, args.data_dir)
        X, vs = d["X"], d["vs"]
        n = len(vs)
        y = np.full(n, np.nan)
        y[:-1] = vs[1:]

        print(f"  {sym}: fitting {args.variant} WFO...", flush=True)
        if args.variant == "squared_error":
            sg = fit_wfo_squared_error(X, y)
        else:
            sg = fit_wfo_quantile_robust(X, y, quantile=args.quantile)

        df_sym, _ = run_tick_backtest(
            sym=sym, data_dir=args.data_dir, tick_dir=args.tick_dir,
            family="gaussian", sigma_override=sg, sig_thresh=args.sig_thresh,
        )
        if len(df_sym) > 0:
            tick_dfs.append(df_sym)

    if not tick_dfs:
        print("No trades produced.")
        raise SystemExit(1)

    all_raw = pd.concat(tick_dfs, ignore_index=True)
    raw_path = os.path.join(args.output_dir, "plain_regression_trades.csv")
    all_raw.to_csv(raw_path, index=False)

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
    ob_net = _option_b_net_per_fill(result, args.threshold)

    print()
    print("=" * 70)
    print(f"PLAIN REGRESSION ({args.variant}) — full pipeline result")
    print("=" * 70)
    print(f"  sig_thresh: {args.sig_thresh}")
    print(f"  n_trades:   {len(result)}")
    print(f"  Meta AUC:   {result.mean_auc.mean():.3f}")
    print(f"  TP%:        {result.label.mean():.1%}")
    print(f"  Option B all-in bps/fill: {ob_net:+.3f}")
