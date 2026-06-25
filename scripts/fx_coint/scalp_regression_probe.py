"""Regression-target scalp probe @ 15m, H1 (15-min hold) — the larger-move-prediction thesis.

Instead of RidgeClassifier-on-sign (Family D), fit a walk-forward Ridge REGRESSION on the
continuous H1 forward return, and only trade when the model forecasts a LARGE move — the
top/bottom tail of the prediction. Sweep P90 / P95 / P99. The question: do the bars where
the regression predicts the biggest moves realize enough to clear taker cost?

Per pair and pooled across tight majors; net of Pepperstone-Razor taker cost; honest
non-overlap inference (every-Kth) + day-block bootstrap on the pooled tail.

Usage:
    uv run python scripts/fx_coint/scalp_regression_probe.py --year 2024
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_ROOT = _Path(__file__).resolve().parents[2]
if str(_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_ROOT))

import argparse  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.linear_model import Ridge  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402

from scripts.fx_coint.phase0_family_d import FEATURE_COLS  # noqa: E402
from scripts.fx_coint.phase0_scalp_common import (  # noqa: E402
    DEFAULT_COST_BPS,
    add_rolling_features,
    compute_forward_returns,
    load_raw_ticks,
)
from scripts.fx_coint.scalp_tf_probe import build_enriched  # noqa: E402

TIGHT = ["EURUSD", "GBPUSD", "USDJPY"]
RNG = np.random.default_rng(0)


def ridge_regression_signal(df: pd.DataFrame, target_col: str, n_blocks: int = 6) -> np.ndarray:
    """Expanding-block walk-forward Ridge predicting the continuous target (OOS)."""
    cols = [c for c in FEATURE_COLS if c in df.columns]
    n = len(df)
    pred = np.full(n, np.nan)
    X = np.nan_to_num(df[cols].to_numpy(dtype=float), nan=0.0)
    y = df[target_col].to_numpy(dtype=float)
    bs = n // n_blocks
    for b in range(1, n_blocks):
        tr = slice(0, b * bs)
        te = slice(b * bs, (b + 1) * bs if b < n_blocks - 1 else n)
        ytr = y[tr]
        m = np.isfinite(ytr)
        if m.sum() < 100:
            continue
        sc = StandardScaler().fit(X[tr][m])
        model = Ridge(alpha=1.0).fit(sc.transform(X[tr][m]), ytr[m])
        pred[te] = model.predict(sc.transform(X[te]))
    return pred


def tail_trades(pred: np.ndarray, fwd: np.ndarray, bucket: np.ndarray, q: float):
    """Select the |pred| tail at quantile q. Return WITH-signal gross (sign(pred)*fwd),
    per-trade, plus bucket. Fade gross = -with gross."""
    valid = np.isfinite(pred) & np.isfinite(fwd)
    p, f, b = pred[valid], fwd[valid], bucket[valid]
    if len(p) < 50:
        return np.array([]), np.array([])
    sel = np.abs(p) >= np.quantile(np.abs(p), q)
    return np.sign(p[sel]) * f[sel], b[sel]  # with-signal gross (fade = negate)


def boot_ci(net, bucket, n_boot=3000):
    if len(net) < 5:
        return np.nan, np.nan
    s = pd.Series(net, index=pd.to_datetime(bucket).date)
    arrs = [g.to_numpy() for _, g in s.groupby(level=0)]
    means = np.empty(n_boot)
    for i in range(n_boot):
        pick = RNG.integers(0, len(arrs), len(arrs))
        means[i] = np.concatenate([arrs[j] for j in pick]).mean()
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=2024)
    ap.add_argument("--freq", default="15m")
    ap.add_argument("--target", default="fwd_ret_1", help="fwd_ret_1 (H1, 15-min)")
    ap.add_argument("--quantiles", nargs="+", type=float, default=[0.90, 0.95, 0.99])
    args = ap.parse_args()

    print(f"REGRESSION-TARGET scalp @ {args.freq} H1 (predict {args.target}, trade |pred| tail), "
          f"taker cost, {args.year}")
    print("  grossBps = WITH-signal mean (fade gross = negate); net = gross - cost both ways\n")
    pooled = {q: ([], [], 0.0) for q in args.quantiles}
    print(f"{'pair':>7} {'q':>5} {'n':>5} {'predIC':>7} {'grossBps':>9} "
          f"{'netWith':>8} {'netFade':>8} {'hitWith':>7}")
    for sym in TIGHT:
        cf = DEFAULT_COST_BPS[sym] / 10_000
        df = add_rolling_features(build_enriched(load_raw_ticks(sym, args.year), sym, args.freq), sym)
        df = compute_forward_returns(df, [1])
        pred = ridge_regression_signal(df, args.target)
        fwd = df["fwd_ret_1"].to_numpy()
        bk = df["bucket"].to_numpy()
        v = np.isfinite(pred) & np.isfinite(fwd)
        ic = float(np.corrcoef(pred[v][::5], fwd[v][::5])[0, 1]) if v.sum() > 50 else float("nan")
        for q in args.quantiles:
            gross, b = tail_trades(pred, fwd, bk, q)
            if len(gross) < 5:
                continue
            g = gross.mean() * 1e4
            print(f"{sym:>7} {q:>5} {len(gross):>5} {ic:>7.4f} {g:>9.3f} "
                  f"{g - cf*1e4:>8.3f} {-g - cf*1e4:>8.3f} {(gross > 0).mean()*100:>6.0f}%")
            pooled[q] = (pooled[q][0] + [gross], pooled[q][1] + [b], cf)
    print("\n  POOLED (tight majors) — WITH vs FADE:")
    print(f"  {'q':>5} {'n':>5} {'grossBps':>9} {'netWith':>8} {'netFade':>8} "
          f"{'fadeBootCI95_bps':>24} {'hitFade':>8}")
    for q in args.quantiles:
        if not pooled[q][0]:
            continue
        gross = np.concatenate(pooled[q][0])
        bk = np.concatenate(pooled[q][1])
        cf = pooled[q][2]
        g = gross.mean() * 1e4
        fade_net = -gross - cf
        clo, chi = boot_ci(fade_net, bk)
        flag = "  <<< FADE POSITIVE" if clo > 0 else ""
        print(f"  {q:>5} {len(gross):>5} {g:>9.3f} {g - cf*1e4:>8.3f} {-g - cf*1e4:>8.3f} "
              f"[{clo*1e4:>+9.3f},{chi*1e4:>+9.3f}] {(gross < 0).mean()*100:>6.0f}%{flag}")


if __name__ == "__main__":
    main()
