#!/usr/bin/env python3
"""
Deep fill-price sensitivity study.
Entry modes: close, next_close, mean
Slippage models:
- proportional: factors in [0.0, 0.02, 0.05, 0.1, 0.2]
- fixed bps: [0, 1, 2, 5, 10]
Outputs:
- data/analysis/m5_fill_price_deep.csv
- data/analysis/m15_fill_price_deep.csv
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
PROP_SLIP = [0.0, 0.02, 0.05, 0.1, 0.2]
FIXED_SLIP = [0, 1, 2, 5, 10]
ENTRY_MODES = ["close", "next_close", "mean"]
LOSS_STREAK = 3
COOLDOWN_DAYS = 14

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
        events = pd.read_csv(path, usecols=["pair", "timestamp", "duration_bars", "active_leg", "side"])
        events["timestamp"] = events["timestamp"].astype("int64")

        pair_info = _pair_map(module)
        pair_cache = {}
        idx_cache = {}
        for pair, (fx, fy, cx, cy) in pair_info.items():
            loaded = _load_prices(module, fx, fy, cx, cy)
            if loaded is None:
                continue
            ts, x, y = loaded
            pair_cache[pair] = (ts, x, y)
            idx_cache[pair] = {int(t): i for i, t in enumerate(ts)}

        rows = []
        for mode in ENTRY_MODES:
            for slip in PROP_SLIP:
                data = []
                skipped = 0
                for row in events.itertuples(index=False):
                    pair = row.pair
                    if pair not in pair_cache:
                        skipped += 1
                        continue
                    ts, x, y = pair_cache[pair]
                    idx_map = idx_cache[pair]

                    entry_ts = int(row.timestamp)
                    entry_idx = idx_map.get(entry_ts)
                    if entry_idx is None:
                        skipped += 1
                        continue
                    duration = int(row.duration_bars)
                    exit_idx = entry_idx + (duration - 1 if duration >= 500 else duration)
                    if exit_idx >= len(ts):
                        skipped += 1
                        continue
                    exit_ts = int(ts[exit_idx])

                    series = y if row.active_leg == "Y" else x
                    if mode == "close":
                        entry_price = series[entry_idx]
                    elif mode == "next_close":
                        if entry_idx + 1 >= len(series):
                            skipped += 1
                            continue
                        entry_price = series[entry_idx + 1]
                    else:  # mean
                        if entry_idx + 1 >= len(series):
                            skipped += 1
                            continue
                        entry_price = 0.5 * (series[entry_idx] + series[entry_idx + 1])

                    exit_price = series[exit_idx]
                    direction = 1 if row.side == "LONG" else -1
                    pnl = direction * (exit_price - entry_price) * 10000.0
                    pnl_adj = pnl - slip * abs(pnl)

                    data.append({"pair": pair, "pnl_bps": pnl_adj, "exit_ts": exit_ts})

                df = pd.DataFrame(data)
                metrics = _metrics(df)
                metrics_g = _metrics(_apply_guardrail(df))
                rows.append({"variant": f"{mode}_prop_{slip}", "guardrail": False, **metrics, "skip_rate": skipped / max(len(events), 1)})
                rows.append({"variant": f"{mode}_prop_{slip}", "guardrail": True, **metrics_g, "skip_rate": skipped / max(len(events), 1)})

            for slip_bps in FIXED_SLIP:
                data = []
                skipped = 0
                for row in events.itertuples(index=False):
                    pair = row.pair
                    if pair not in pair_cache:
                        skipped += 1
                        continue
                    ts, x, y = pair_cache[pair]
                    idx_map = idx_cache[pair]

                    entry_ts = int(row.timestamp)
                    entry_idx = idx_map.get(entry_ts)
                    if entry_idx is None:
                        skipped += 1
                        continue
                    duration = int(row.duration_bars)
                    exit_idx = entry_idx + (duration - 1 if duration >= 500 else duration)
                    if exit_idx >= len(ts):
                        skipped += 1
                        continue
                    exit_ts = int(ts[exit_idx])

                    series = y if row.active_leg == "Y" else x
                    if mode == "close":
                        entry_price = series[entry_idx]
                    elif mode == "next_close":
                        if entry_idx + 1 >= len(series):
                            skipped += 1
                            continue
                        entry_price = series[entry_idx + 1]
                    else:
                        if entry_idx + 1 >= len(series):
                            skipped += 1
                            continue
                        entry_price = 0.5 * (series[entry_idx] + series[entry_idx + 1])

                    exit_price = series[exit_idx]
                    direction = 1 if row.side == "LONG" else -1
                    pnl = direction * (exit_price - entry_price) * 10000.0
                    pnl_adj = pnl - slip_bps

                    data.append({"pair": pair, "pnl_bps": pnl_adj, "exit_ts": exit_ts})

                df = pd.DataFrame(data)
                metrics = _metrics(df)
                metrics_g = _metrics(_apply_guardrail(df))
                rows.append({"variant": f"{mode}_fixed_{slip_bps}", "guardrail": False, **metrics, "skip_rate": skipped / max(len(events), 1)})
                rows.append({"variant": f"{mode}_fixed_{slip_bps}", "guardrail": True, **metrics_g, "skip_rate": skipped / max(len(events), 1)})

        out = pd.DataFrame(rows)
        out.to_csv(os.path.join(OUT_DIR, f"{label}_fill_price_deep.csv"), index=False)
        print(f"Saved: {OUT_DIR}/{label}_fill_price_deep.csv")


if __name__ == "__main__":
    main()
