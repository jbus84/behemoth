#!/usr/bin/env python3
"""
Execution realism with resimulated exits after delayed entry.
Delays: 1-3 bars. Exits recomputed via Z-cross/stop from delayed entry.
Outputs:
- data/analysis/m5_execution_latency_resim.csv
- data/analysis/m15_execution_latency_resim.csv
"""

from __future__ import annotations

import os
import sys
import numpy as np
import pandas as pd

sys.path.append(os.path.join(os.getcwd(), "scripts"))
from metrics import sharpe_daily, sharpe_daily_active, sharpe_trade
import build_meta_dataset_v3_m5 as m5
import build_meta_dataset_v3 as m15

OUT_DIR = "data/analysis"
DELAYS = [1, 2, 3]
LOSS_STREAK = 3
COOLDOWN_DAYS = 14
THRESH_MOM = 1.5
STOP_Z = 3.5

CONFIGS = [
    ("m5", "data/meta_model/events_m5_8yr_v3_mom.csv", m5, 5),
    ("m15", "data/meta_model/events_m15_8yr_v3_mom.csv", m15, 15),
]


def _max_dd(pnls: np.ndarray) -> float:
    if len(pnls) == 0:
        return 0.0
    curve = np.cumsum(pnls)
    peak = np.maximum.accumulate(curve)
    return float((curve - peak).min())


def _metrics(df: pd.DataFrame) -> dict:
    if df.empty:
        return dict(trades=0, mean_pnl=0.0, total_pnl=0.0, max_dd=0.0, sharpe=0.0)
    pnl = df["pnl_bps"].to_numpy()
    ts = df["exit_ts"].to_numpy()
    return dict(
        trades=int(len(pnl)),
        mean_pnl=float(np.mean(pnl)),
        total_pnl=float(np.sum(pnl)),
        max_dd=_max_dd(pnl),
        sharpe=sharpe_daily(pnl, ts),
        sharpe_active=sharpe_daily_active(pnl, ts),
        sharpe_trade=sharpe_trade(pnl, ts),
    )


def _apply_guardrail(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values("exit_ts").copy()
    keep = []
    state = {}
    cooldown_ns = int(pd.Timedelta(days=COOLDOWN_DAYS).value)

    for row in df.itertuples(index=False):
        pair = row.pair
        ts = int(row.exit_ts)
        pnl = float(row.pnl_bps)

        if pair not in state:
            state[pair] = {"loss_streak": 0, "pause_until": None}

        st = state[pair]
        if st["pause_until"] is not None and ts < st["pause_until"]:
            continue

        keep.append(row)

        if pnl > 0:
            st["loss_streak"] = 0
        else:
            st["loss_streak"] += 1
            if st["loss_streak"] >= LOSS_STREAK:
                st["pause_until"] = ts + cooldown_ns
                st["loss_streak"] = 0

    if not keep:
        return df.iloc[:0]
    return pd.DataFrame(keep)


def _pair_map(module):
    return {name: (fx, fy, cx, cy) for name, fx, fy, cx, cy, *_ in module.PAIRS}


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


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)

    for label, path, module, bar_minutes in CONFIGS:
        events = pd.read_csv(path, usecols=["pair", "timestamp", "duration_bars", "pnl_bps", "active_leg", "side"])
        events["timestamp"] = events["timestamp"].astype("int64")
        bar_ns = int(pd.Timedelta(minutes=bar_minutes).value)
        durations = events["duration_bars"].astype(int)
        timeout_adjust = (durations >= 500).astype(int)
        events["exit_ts"] = events["timestamp"] + ((durations - timeout_adjust) * bar_ns)

        results = []
        results.append({"variant": "baseline", "guardrail": False, **_metrics(events), "skip_rate": 0.0})
        results.append({"variant": "baseline", "guardrail": True, **_metrics(_apply_guardrail(events)), "skip_rate": 0.0})

        pair_info = _pair_map(module)
        pair_cache = {}
        idx_cache = {}
        z_cache = {}

        for pair, (fx, fy, cx, cy) in pair_info.items():
            loaded = _load_prices(module, fx, fy, cx, cy)
            if loaded is None:
                continue
            ts, x, y = loaded
            pair_cache[pair] = (ts, x, y)
            idx_cache[pair] = {int(t): i for i, t in enumerate(ts)}
            betas, errors, _ = module.compute_kalman_states(y, x)
            z_cache[pair] = module.compute_z_scores(errors)

        for delay in DELAYS:
            rows = []
            skipped = 0
            for row in events.itertuples(index=False):
                pair = row.pair
                if pair not in pair_cache:
                    skipped += 1
                    continue
                ts, x, y = pair_cache[pair]
                z_scores = z_cache[pair]
                idx_map = idx_cache[pair]

                entry_ts = int(row.timestamp)
                entry_idx = idx_map.get(entry_ts)
                if entry_idx is None:
                    skipped += 1
                    continue
                entry_idx_d = entry_idx + delay
                if entry_idx_d >= len(z_scores):
                    skipped += 1
                    continue

                direction = 1 if row.side == "LONG" else -1
                active_leg = row.active_leg

                pnl, duration, _ = module.simulate_trade(
                    entry_idx_d, direction, "MOM", y, x, z_scores, active_leg, THRESH_MOM, STOP_Z
                )

                exit_idx = entry_idx_d + (duration - 1 if duration >= 500 else duration)
                if exit_idx >= len(ts):
                    skipped += 1
                    continue

                rows.append({"pair": pair, "pnl_bps": pnl, "exit_ts": int(ts[exit_idx])})

            data = pd.DataFrame(rows)
            skip_rate = skipped / max(len(events), 1)
            results.append({"variant": f"resim_delay_{delay}", "guardrail": False, **_metrics(data), "skip_rate": skip_rate})
            results.append({"variant": f"resim_delay_{delay}", "guardrail": True, **_metrics(_apply_guardrail(data)), "skip_rate": skip_rate})

        out = pd.DataFrame(results)
        out.to_csv(os.path.join(OUT_DIR, f"{label}_execution_latency_resim.csv"), index=False)
        print(f"Saved: {OUT_DIR}/{label}_execution_latency_resim.csv")


if __name__ == "__main__":
    main()
