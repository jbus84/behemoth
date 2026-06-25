"""One-bar-ahead 3-class label via rolling causal terciles.

Goal: balanced (~33/33/33) AND stationary class proportions through time,
and drift-immune (thresholds track local regime so a static long/short bias
cannot score).

At bar t:
  * target  = next-bar return r_{t+1} = mid_{t+1}/mid_t - 1   (bps)
  * thresholds = lower/upper terciles of REALIZED returns over the trailing
    causal window [t-W+1, t]  (uses only returns known by t)
  * label: r_{t+1} < q33 -> -1,  > q67 -> +1,  else 0

Usage:
    uv run python scripts/fx_coint/hourly_nextbar_label.py --year 2024 --window 500
"""
# ruff: noqa: E402  (imports follow sys.path bootstrap, by design)
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.fx_coint.hourly_multirocket_wfo import load_hourly


def label_next_bar_tercile(df: pd.DataFrame, window: int = 500) -> pd.DataFrame:
    """Add `tb_label` in {-1,0,1} from rolling causal terciles of next-bar return.

    Causal: thresholds at t use realized returns up to and including t; the
    labelled quantity r_{t+1} is compared against them. Last bar is unlabelable.
    """
    mid = df["mid"].to_numpy()
    realized = np.empty(len(mid))
    realized[0] = np.nan
    realized[1:] = mid[1:] / mid[:-1] - 1.0          # r_t (known at t)
    fwd = np.empty(len(mid))
    fwd[:-1] = mid[1:] / mid[:-1] - 1.0              # r_{t+1} (target at t)
    fwd[-1] = np.nan

    r = pd.Series(realized, index=df.index)
    q33 = r.rolling(window, min_periods=window // 2).quantile(1 / 3)
    q67 = r.rolling(window, min_periods=window // 2).quantile(2 / 3)

    label = np.zeros(len(mid), dtype=np.int8)
    f = pd.Series(fwd, index=df.index)
    label[(f < q33).to_numpy(na_value=False)] = -1
    label[(f > q67).to_numpy(na_value=False)] = 1
    # unlabelable rows (warmup + last bar) -> 0 and flag
    valid = (~q33.isna()).to_numpy() & (~np.isnan(fwd))
    label[~valid] = 0

    out = df.copy()
    out["tb_label"] = label
    out["fwd_ret_bps"] = fwd * 10_000.0
    out["_label_valid"] = valid
    return out


def label_horizon_tercile(df: pd.DataFrame, horizon: int, window: int = 500) -> pd.DataFrame:
    """Drift-immune h-bar-ahead 3-class label via rolling causal terciles.

    Thresholds at t use realized h-bar returns known by t (the last `horizon` bars);
    the h-bar forward return r_{t->t+h} is labelled against them. Last `horizon`
    rows unlabelable. Uses h-bar scale for terciles to maintain balance and
    drift-immunity across horizons.
    """
    mid = df["mid"].to_numpy()
    n = len(mid)

    # h-bar realized returns (what happened h bars ago)
    realized = np.empty(n)
    realized[:horizon] = np.nan
    realized[horizon:] = mid[horizon:] / mid[:-horizon] - 1.0

    # h-bar forward returns (what will happen)
    fwd = np.full(n, np.nan)
    fwd[: n - horizon] = mid[horizon:] / mid[: n - horizon] - 1.0

    r = pd.Series(realized, index=df.index)
    q33 = r.rolling(window, min_periods=window // 2).quantile(1 / 3)
    q67 = r.rolling(window, min_periods=window // 2).quantile(2 / 3)

    label = np.zeros(n, dtype=np.int8)
    f = pd.Series(fwd, index=df.index)
    label[(f < q33).to_numpy(na_value=False)] = -1
    label[(f > q67).to_numpy(na_value=False)] = 1
    valid = (~q33.isna()).to_numpy() & (~np.isnan(fwd))
    label[~valid] = 0

    out = df.copy()
    out["tb_label"] = label
    out["fwd_ret_bps"] = fwd * 10_000.0
    out["_label_valid"] = valid
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="EURUSD")
    ap.add_argument("--year", type=int, default=2024)
    ap.add_argument("--window", type=int, default=500)
    args = ap.parse_args()

    df = load_hourly(args.symbol)
    start, end = pd.Timestamp(f"{args.year}-01-01"), pd.Timestamp(f"{args.year+1}-01-01")
    df = df[(df["bucket"] >= start) & (df["bucket"] < end)].reset_index(drop=True)
    df = label_next_bar_tercile(df, window=args.window)

    v = df[df["_label_valid"]]
    lab = v["tb_label"].to_numpy()
    n = len(lab)
    print(f"=== next-bar tercile label  {args.symbol} {args.year}  W={args.window} ===")
    print(f"valid labelled bars: {n} / {len(df)}")
    print(f"OVERALL   -1={np.mean(lab==-1)*100:4.1f}%  "
          f"0={np.mean(lab==0)*100:4.1f}%  +1={np.mean(lab==1)*100:4.1f}%")

    # stationarity: class fractions per month
    v = v.assign(month=v["bucket"].dt.to_period("M"))
    print("\nper-month class balance (proves stationarity):")
    print(f"{'month':<9s} {'n':>5s} {'-1%':>6s} {'0%':>6s} {'+1%':>6s} "
          f"{'fwd|-1':>8s} {'fwd|0':>8s} {'fwd|+1':>8s}")
    for m, g in v.groupby("month"):
        l = g["tb_label"].to_numpy()
        fb = g["fwd_ret_bps"].to_numpy()
        print(f"{str(m):<9s} {len(g):>5d} "
              f"{np.mean(l==-1)*100:>5.1f}% {np.mean(l==0)*100:>5.1f}% {np.mean(l==1)*100:>5.1f}% "
              f"{fb[l==-1].mean():>+8.2f} {fb[l==0].mean():>+8.2f} {fb[l==1].mean():>+8.2f}")

    # sanity: class means must separate in forward return (label is well-formed)
    fb = v["fwd_ret_bps"].to_numpy()
    print(f"\nforward-return by class (bps):  "
          f"-1={fb[lab==-1].mean():+.2f}  0={fb[lab==0].mean():+.2f}  +1={fb[lab==1].mean():+.2f}")


if __name__ == "__main__":
    main()
