#!/usr/bin/env python3
"""
Exit-variant analysis for MOM trades.

Variants:
1) baseline: Z-cross or Z-stop (|Z|>=3.5) or timeout
2) cond_z: Z-cross only if active-leg PnL <= 0, Z-stop unconditional
3) trail_giveback_X: active-leg MFE giveback X bps + Z-cross + Z-stop
4) stop_bps_X: active-leg stop at -X bps + Z-cross + Z-stop

Outputs:
- data/analysis/m5_exit_variant_summary.csv
- data/analysis/m15_exit_variant_summary.csv
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

import numpy as np
import pandas as pd

sys.path.append(os.path.join(os.getcwd(), "scripts"))
from metrics import sharpe_daily, sharpe_daily_active, sharpe_trade
import build_meta_dataset_v3_m5 as m5
import build_meta_dataset_v3 as m15


@dataclass
class TFConfig:
    label: str
    events_path: str
    module: object
    max_hold: int


CONFIGS = [
    TFConfig("m5", "data/meta_model/events_m5_8yr_v3_mom.csv", m5, 500),
    TFConfig("m15", "data/meta_model/events_m15_8yr_v3_mom.csv", m15, 500),
]

OUT_DIR = "data/analysis"
STOP_Z = 3.5
TRAIL_GIVEBACKS = [5.0, 10.0, 15.0]
STOP_BPS = [5.0, 10.0, 15.0]


def _max_dd(pnls: np.ndarray) -> float:
    if len(pnls) == 0:
        return 0.0
    curve = np.cumsum(pnls)
    peak = np.maximum.accumulate(curve)
    return float((curve - peak).min())


def _metrics(pnls: list[float], exit_ts: list[int], durations: list[int]) -> dict:
    if not pnls:
        return dict(
            trades=0,
            win_rate=0.0,
            mean_pnl=0.0,
            total_pnl=0.0,
            max_dd=0.0,
            sharpe=0.0,
            sharpe_active=0.0,
            sharpe_trade=0.0,
            mean_duration=0.0,
        )
    arr = np.asarray(pnls, dtype=float)
    ts = np.asarray(exit_ts, dtype="int64")
    return dict(
        trades=int(len(arr)),
        win_rate=float((arr > 0).mean() * 100.0),
        mean_pnl=float(arr.mean()),
        total_pnl=float(arr.sum()),
        max_dd=_max_dd(arr),
        sharpe=sharpe_daily(arr, ts),
        sharpe_active=sharpe_daily_active(arr, ts),
        sharpe_trade=sharpe_trade(arr, ts),
        mean_duration=float(np.mean(durations)) if durations else 0.0,
    )


def _load_prices(module, fx, fy, cx, cy):
    df = module.load_pair_data(fx, fy, cx, cy)
    if df is None:
        return None
    x = np.log(df["X"].to_numpy())
    y = np.log(df["Y"].to_numpy())
    ts = df["timestamp"].to_numpy()
    if np.issubdtype(ts.dtype, np.datetime64):
        ts = ts.astype("datetime64[ns]").astype("int64")
    else:
        ts = ts.astype("int64")
    return ts, x, y


def _pair_map(module):
    return {name: (fx, fy, cx, cy) for name, fx, fy, cx, cy, *_ in module.PAIRS}


def _compute_z_scores(module, y, x):
    betas, errors, _ = module.compute_kalman_states(y, x)
    return module.compute_z_scores(errors)


def _simulate_variants(entry_idx: int, direction: int, active: np.ndarray, z_scores: np.ndarray, max_hold: int):
    last_idx = min(entry_idx + max_hold, len(z_scores) - 1)
    entry_price = active[entry_idx]

    # State for variants
    cond_done = False
    cond_exit_idx = None
    cond_exit_pnl = None

    trail_done = [False] * len(TRAIL_GIVEBACKS)
    trail_exit_idx = [None] * len(TRAIL_GIVEBACKS)
    trail_exit_pnl = [None] * len(TRAIL_GIVEBACKS)
    trail_max = [0.0] * len(TRAIL_GIVEBACKS)

    stop_done = [False] * len(STOP_BPS)
    stop_exit_idx = [None] * len(STOP_BPS)
    stop_exit_pnl = [None] * len(STOP_BPS)

    for i in range(entry_idx + 1, last_idx + 1):
        z = z_scores[i]
        pnl = direction * (active[i] - entry_price) * 10000.0

        if direction == 1:
            z_cross = z < 0
            z_stop = z > STOP_Z
        else:
            z_cross = z > 0
            z_stop = z < -STOP_Z

        # Conditional Z-cross exit
        if not cond_done:
            if z_stop:
                cond_done = True
                cond_exit_idx = i
                cond_exit_pnl = pnl
            elif z_cross and pnl <= 0.0:
                cond_done = True
                cond_exit_idx = i
                cond_exit_pnl = pnl

        # Trailing giveback exits
        for j, giveback in enumerate(TRAIL_GIVEBACKS):
            if trail_done[j]:
                continue
            if z_stop or z_cross:
                trail_done[j] = True
                trail_exit_idx[j] = i
                trail_exit_pnl[j] = pnl
                continue
            if pnl > trail_max[j]:
                trail_max[j] = pnl
            if trail_max[j] > 0 and (trail_max[j] - pnl) >= giveback:
                trail_done[j] = True
                trail_exit_idx[j] = i
                trail_exit_pnl[j] = pnl

        # Active-leg stop exits
        for j, stop_bps in enumerate(STOP_BPS):
            if stop_done[j]:
                continue
            if pnl <= -stop_bps:
                stop_done[j] = True
                stop_exit_idx[j] = i
                stop_exit_pnl[j] = pnl
                continue
            if z_stop or z_cross:
                stop_done[j] = True
                stop_exit_idx[j] = i
                stop_exit_pnl[j] = pnl

        if cond_done and all(trail_done) and all(stop_done):
            break

    # Timeout for any remaining
    if not cond_done:
        cond_exit_idx = last_idx
        cond_exit_pnl = direction * (active[last_idx] - entry_price) * 10000.0
    for j in range(len(TRAIL_GIVEBACKS)):
        if not trail_done[j]:
            trail_exit_idx[j] = last_idx
            trail_exit_pnl[j] = direction * (active[last_idx] - entry_price) * 10000.0
    for j in range(len(STOP_BPS)):
        if not stop_done[j]:
            stop_exit_idx[j] = last_idx
            stop_exit_pnl[j] = direction * (active[last_idx] - entry_price) * 10000.0

    return {
        "cond": (cond_exit_idx, cond_exit_pnl),
        "trail": list(zip(trail_exit_idx, trail_exit_pnl)),
        "stop": list(zip(stop_exit_idx, stop_exit_pnl)),
    }


def _analyze(cfg: TFConfig) -> pd.DataFrame:
    df = pd.read_csv(
        cfg.events_path,
        usecols=["pair", "timestamp", "active_leg", "side", "duration_bars", "pnl_bps"],
    )
    df["timestamp"] = df["timestamp"].astype("int64")

    pair_info = _pair_map(cfg.module)
    results = {
        "baseline": {"pnls": [], "exit_ts": [], "durations": []},
        "cond_z": {"pnls": [], "exit_ts": [], "durations": []},
    }
    for giveback in TRAIL_GIVEBACKS:
        results[f"trail_{int(giveback)}"] = {"pnls": [], "exit_ts": [], "durations": []}
    for stop_bps in STOP_BPS:
        results[f"stop_{int(stop_bps)}"] = {"pnls": [], "exit_ts": [], "durations": []}

    skipped = 0

    for pair, sub in df.groupby("pair"):
        if pair not in pair_info:
            continue
        fx, fy, cx, cy = pair_info[pair]
        loaded = _load_prices(cfg.module, fx, fy, cx, cy)
        if loaded is None:
            continue
        ts, x, y = loaded
        z_scores = _compute_z_scores(cfg.module, y, x)

        idx_map = {int(t): i for i, t in enumerate(ts)}

        for _, row in sub.iterrows():
            entry_ts = int(row["timestamp"])
            entry_idx = idx_map.get(entry_ts)
            if entry_idx is None:
                skipped += 1
                continue
            base_exit_idx = entry_idx + int(row["duration_bars"])
            if base_exit_idx >= len(ts):
                skipped += 1
                continue

            direction = 1 if row["side"] == "LONG" else -1
            active_leg = row["active_leg"]
            active = y if active_leg == "Y" else x

            # Baseline metrics use stored pnl and exit_ts
            results["baseline"]["pnls"].append(float(row["pnl_bps"]))
            results["baseline"]["exit_ts"].append(int(ts[base_exit_idx]))
            results["baseline"]["durations"].append(int(base_exit_idx - entry_idx))

            variants = _simulate_variants(entry_idx, direction, active, z_scores, cfg.max_hold)

            cond_idx, cond_pnl = variants["cond"]
            results["cond_z"]["pnls"].append(float(cond_pnl))
            results["cond_z"]["exit_ts"].append(int(ts[cond_idx]))
            results["cond_z"]["durations"].append(int(cond_idx - entry_idx))

            for giveback, (exit_idx, exit_pnl) in zip(TRAIL_GIVEBACKS, variants["trail"]):
                key = f"trail_{int(giveback)}"
                results[key]["pnls"].append(float(exit_pnl))
                results[key]["exit_ts"].append(int(ts[exit_idx]))
                results[key]["durations"].append(int(exit_idx - entry_idx))

            for stop_bps, (exit_idx, exit_pnl) in zip(STOP_BPS, variants["stop"]):
                key = f"stop_{int(stop_bps)}"
                results[key]["pnls"].append(float(exit_pnl))
                results[key]["exit_ts"].append(int(ts[exit_idx]))
                results[key]["durations"].append(int(exit_idx - entry_idx))

    rows = []
    baseline_mean = np.mean(results["baseline"]["pnls"]) if results["baseline"]["pnls"] else 0.0

    for variant, data in results.items():
        metrics = _metrics(data["pnls"], data["exit_ts"], data["durations"])
        metrics["variant"] = variant
        metrics["delta_mean_vs_baseline"] = metrics["mean_pnl"] - baseline_mean
        metrics["skipped_trades"] = skipped
        rows.append(metrics)

    return pd.DataFrame(rows)


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    for cfg in CONFIGS:
        summary = _analyze(cfg)
        out_path = os.path.join(OUT_DIR, f"{cfg.label}_exit_variant_summary.csv")
        summary.to_csv(out_path, index=False)
        print(f"Saved: {out_path}")


if __name__ == "__main__":
    main()
