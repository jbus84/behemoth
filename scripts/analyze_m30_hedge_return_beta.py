#!/usr/bin/env python3
"""
Analyze return-beta hedging on 30m data (rebalance every bar).
Compares unhedged vs hedged PnL and residual exposure for MOM/REV trades.

Outputs:
- data/analysis/m30_hedge_compare_summary.csv
- data/analysis/m30_hedge_compare_monthly.csv
- data/analysis/m30_hedge_exposure_monthly.csv
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict

import numpy as np
import pandas as pd

sys.path.append(os.path.join(os.getcwd(), "scripts"))
import build_meta_dataset_v3_m30 as m30

OUT_DIR = "data/analysis"

THRESH_MOM = 1.5
THRESH_REV = 2.5
STOP_LEVEL = 3.5
MIN_GAP = 20
MAX_HOLD = 500
HEDGE_CLIP = 10.0


def _max_dd(pnl: np.ndarray) -> float:
    if len(pnl) == 0:
        return 0.0
    curve = np.cumsum(pnl)
    peak = np.maximum.accumulate(curve)
    return float((curve - peak).min())


def _trade_metrics(trades: pd.DataFrame, pnl_col: str) -> dict:
    if trades.empty:
        return dict(trades=0, win_rate=0.0, mean_pnl=0.0, total_pnl=0.0, max_dd=0.0)
    pnl = trades[pnl_col].to_numpy()
    order = np.argsort(trades["entry_ts"].to_numpy())
    pnl = pnl[order]
    return dict(
        trades=int(len(pnl)),
        win_rate=float((pnl > 0).mean() * 100.0),
        mean_pnl=float(pnl.mean()),
        total_pnl=float(pnl.sum()),
        max_dd=_max_dd(pnl),
    )


def _exit_hit(strategy_type: str, direction: int, z: float) -> bool:
    if strategy_type == "MOM":
        if direction == 1:
            return z < 0 or z > STOP_LEVEL
        return z > 0 or z < -STOP_LEVEL
    # REV
    if direction == 1:
        return z > 0 or z < -STOP_LEVEL
    return z < 0 or z > STOP_LEVEL


def _hedge_ratio(active_leg: str, ret_beta: float) -> float:
    if active_leg == "Y":
        ratio = ret_beta
    else:
        ratio = 0.0 if abs(ret_beta) < 1e-6 else 1.0 / ret_beta
    return float(np.clip(ratio, -HEDGE_CLIP, HEDGE_CLIP))


def simulate_trade(
    entry_idx: int,
    direction: int,
    strategy_type: str,
    y: np.ndarray,
    x: np.ndarray,
    z_scores: np.ndarray,
    ret_betas: np.ndarray,
    active_leg: str,
    ts: np.ndarray,
    month_arr: np.ndarray,
    exposure_store: dict,
) -> dict:
    if active_leg == "Y":
        active = y
        other = x
    else:
        active = x
        other = y

    unhedged = []
    hedged = []
    months = []

    end = min(entry_idx + MAX_HOLD, len(z_scores) - 1)
    exit_idx = end

    for i in range(entry_idx + 1, end + 1):
        delta_active = active[i] - active[i - 1]
        delta_other = other[i] - other[i - 1]
        hedge_beta = _hedge_ratio(active_leg, ret_betas[i])

        un_pnl = direction * delta_active * 10000.0
        hed_pnl = direction * (delta_active - hedge_beta * delta_other) * 10000.0
        unhedged.append(un_pnl)
        hedged.append(hed_pnl)
        months.append(month_arr[i])

        if _exit_hit(strategy_type, direction, z_scores[i]):
            exit_idx = i
            break

    if unhedged:
        for m, un_pnl, hed_pnl in zip(months, unhedged, hedged):
            exposure_store[(strategy_type, m)]["unhedged"].append(abs(un_pnl))
            exposure_store[(strategy_type, m)]["hedged"].append(abs(hed_pnl))

    return {
        "entry_ts": ts[entry_idx],
        "entry_month": month_arr[entry_idx],
        "exit_ts": ts[exit_idx],
        "duration_bars": exit_idx - entry_idx,
        "unhedged_pnl": float(np.sum(unhedged)),
        "hedged_pnl": float(np.sum(hedged)),
    }


def _load_good_mom_pairs(path: str) -> set[str]:
    df = pd.read_csv(path)
    base = df[(df["strategy_type"] == "MOM") & (df["variant"] == "unhedged")].set_index("pair")
    hedg = df[(df["strategy_type"] == "MOM") & (df["variant"] == "ret_beta")].set_index("pair")
    common = base.index.intersection(hedg.index)
    dd_improve = hedg.loc[common, "max_dd"] - base.loc[common, "max_dd"]
    pnl_delta = hedg.loc[common, "total_pnl"] - base.loc[common, "total_pnl"]
    good = common[(dd_improve > 0) & (pnl_delta > 0)]
    return set(good)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", choices=["MOM", "REV", "BOTH"], default="BOTH")
    parser.add_argument("--pairs", default="", help="Comma-separated pair names to include")
    parser.add_argument("--pairs-good-mom", action="store_true", help="Use MOM pairs where hedging improves PnL and DD")
    args = parser.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)
    pair_filter = None
    if args.pairs:
        pair_filter = {p.strip() for p in args.pairs.split(",") if p.strip()}
    if args.pairs_good_mom:
        pair_filter = _load_good_mom_pairs(os.path.join(OUT_DIR, "m30_hedge_pair_summary.csv"))

    trade_rows = []
    exposure_store = defaultdict(lambda: {"unhedged": [], "hedged": []})

    for name, fx, fy, cx, cy, _, _ in m30.PAIRS:
        if pair_filter is not None and name not in pair_filter:
            continue
        df = m30.load_pair_data(fx, fy, cx, cy)
        if df is None:
            continue

        y = np.log(df["Y"].to_numpy())
        x = np.log(df["X"].to_numpy())
        ts = df["timestamp"].to_numpy()
        ts_dt = pd.to_datetime(ts, unit="ns", utc=True, errors="coerce")
        month_arr = ts_dt.strftime("%Y-%m").to_numpy()

        betas, errors, ret_betas = m30.compute_kalman_states(y, x)
        z_scores = m30.compute_z_scores(errors)

        last_entry_mom = 0
        last_entry_rev = 0

        for i in range(500, len(y) - 2):
            z = z_scores[i]
            beta = betas[i]

            if beta < 0.98:
                active_leg = "Y"
            elif beta > 1.02:
                active_leg = "X"
            else:
                continue

            if args.strategy in ("MOM", "BOTH"):
                if abs(z) >= THRESH_MOM and i - last_entry_mom >= MIN_GAP:
                    direction = 1 if z > 0 else -1
                    res = simulate_trade(
                        i,
                        direction,
                        "MOM",
                        y,
                        x,
                        z_scores,
                        ret_betas,
                        active_leg,
                        ts,
                        month_arr,
                        exposure_store,
                    )
                    trade_rows.append({"pair": name, "strategy_type": "MOM", "side": "LONG" if direction == 1 else "SHORT", "active_leg": active_leg, **res})
                    last_entry_mom = i

            if args.strategy in ("REV", "BOTH"):
                if abs(z) >= THRESH_REV and i - last_entry_rev >= MIN_GAP:
                    direction = -1 if z > 0 else 1
                    res = simulate_trade(
                        i,
                        direction,
                        "REV",
                        y,
                        x,
                        z_scores,
                        ret_betas,
                        active_leg,
                        ts,
                        month_arr,
                        exposure_store,
                    )
                    trade_rows.append({"pair": name, "strategy_type": "REV", "side": "LONG" if direction == 1 else "SHORT", "active_leg": active_leg, **res})
                    last_entry_rev = i

    trades = pd.DataFrame(trade_rows)
    trades["entry_ts"] = trades["entry_ts"].astype("int64")

    summary_rows = []
    monthly_rows = []
    exposure_rows = []

    for strat in ["MOM", "REV"]:
        if args.strategy != "BOTH" and strat != args.strategy:
            continue
        sub = trades[trades["strategy_type"] == strat].copy()
        for mode, col in [("unhedged", "unhedged_pnl"), ("hedged", "hedged_pnl")]:
            stats = _trade_metrics(sub, col)
            # exposure aggregates (all months)
            all_exp = []
            for (s, _m), vals in exposure_store.items():
                if s != strat:
                    continue
                all_exp.extend(vals[mode])
            all_exp = np.array(all_exp, dtype=float)
            summary_rows.append(
                {
                    "strategy_type": strat,
                    "hedge_mode": mode,
                    **stats,
                    "mean_abs_exposure": float(np.mean(np.abs(all_exp))) if len(all_exp) else 0.0,
                    "p50_abs_exposure": float(np.percentile(np.abs(all_exp), 50)) if len(all_exp) else 0.0,
                    "p90_abs_exposure": float(np.percentile(np.abs(all_exp), 90)) if len(all_exp) else 0.0,
                    "p99_abs_exposure": float(np.percentile(np.abs(all_exp), 99)) if len(all_exp) else 0.0,
                }
            )

            for month, grp in sub.groupby("entry_month"):
                mstats = _trade_metrics(grp, col)
                monthly_rows.append(
                    {
                        "strategy_type": strat,
                        "month": month,
                        "hedge_mode": mode,
                        **mstats,
                    }
                )

        # exposure by month
        months = sorted({m for (s, m) in exposure_store.keys() if s == strat})
        for month in months:
            vals = exposure_store[(strat, month)]
            for mode in ["unhedged", "hedged"]:
                arr = np.array(vals[mode], dtype=float)
                exposure_rows.append(
                    {
                        "strategy_type": strat,
                        "month": month,
                        "hedge_mode": mode,
                        "mean_abs_exposure": float(np.mean(arr)) if len(arr) else 0.0,
                        "p90_abs_exposure": float(np.percentile(arr, 90)) if len(arr) else 0.0,
                        "p99_abs_exposure": float(np.percentile(arr, 99)) if len(arr) else 0.0,
                        "n_obs": int(len(arr)),
                    }
                )

    summary = pd.DataFrame(summary_rows)
    monthly = pd.DataFrame(monthly_rows)
    exposure = pd.DataFrame(exposure_rows)

    suffix = "all"
    if args.pairs_good_mom:
        suffix = "good_mom"
    elif pair_filter is not None:
        suffix = "filtered"

    summary.to_csv(os.path.join(OUT_DIR, f"m30_hedge_compare_summary_{suffix}.csv"), index=False)
    monthly.to_csv(os.path.join(OUT_DIR, f"m30_hedge_compare_monthly_{suffix}.csv"), index=False)
    exposure.to_csv(os.path.join(OUT_DIR, f"m30_hedge_exposure_monthly_{suffix}.csv"), index=False)

    print("Saved:")
    print(f"- data/analysis/m30_hedge_compare_summary_{suffix}.csv")
    print(f"- data/analysis/m30_hedge_compare_monthly_{suffix}.csv")
    print(f"- data/analysis/m30_hedge_exposure_monthly_{suffix}.csv")


if __name__ == "__main__":
    main()
