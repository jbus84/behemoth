#!/usr/bin/env python3
"""
Compare timeout convention: duration==500 exits at entry+499 vs entry+500.
Reports mean PnL difference and flip rate.
Outputs:
- data/analysis/m5_timeout_convention.csv
- data/analysis/m15_timeout_convention.csv
"""

from __future__ import annotations

import os
import sys
import numpy as np
import pandas as pd

sys.path.append(os.path.join(os.getcwd(), "scripts"))
import build_meta_dataset_v3_m5 as m5
import build_meta_dataset_v3 as m15

OUT_DIR = "data/analysis"

CONFIGS = [
    ("m5", "data/meta_model/events_m5_8yr_v3_mom.csv", m5),
    ("m15", "data/meta_model/events_m15_8yr_v3_mom.csv", m15),
]


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

    for label, path, module in CONFIGS:
        df = pd.read_csv(path, usecols=["pair", "timestamp", "active_leg", "side", "duration_bars", "pnl_bps"])
        df["timestamp"] = df["timestamp"].astype("int64")

        pair_info = _pair_map(module)
        rows = []

        for pair, sub in df.groupby("pair"):
            if pair not in pair_info:
                continue
            fx, fy, cx, cy = pair_info[pair]
            loaded = _load_prices(module, fx, fy, cx, cy)
            if loaded is None:
                continue
            ts, x, y = loaded
            idx_map = {int(t): i for i, t in enumerate(ts)}

            for row in sub.itertuples(index=False):
                entry_ts = int(row.timestamp)
                entry_idx = idx_map.get(entry_ts)
                if entry_idx is None:
                    continue
                duration = int(row.duration_bars)
                if duration < 500:
                    continue
                # Two conventions
                exit_a = entry_idx + 499
                exit_b = entry_idx + 500
                if exit_b >= len(ts):
                    continue

                direction = 1 if row.side == "LONG" else -1
                active = y if row.active_leg == "Y" else x

                pnl_a = direction * (active[exit_a] - active[entry_idx]) * 10000.0
                pnl_b = direction * (active[exit_b] - active[entry_idx]) * 10000.0
                rows.append((pnl_a, pnl_b))

        if not rows:
            out = pd.DataFrame([{"timeframe": label, "timeouts": 0}])
        else:
            arr = np.asarray(rows)
            pnl_a = arr[:, 0]
            pnl_b = arr[:, 1]
            delta = pnl_b - pnl_a
            flips = ((pnl_a > 0) != (pnl_b > 0)).mean()
            out = pd.DataFrame(
                [
                    {
                        "timeframe": label,
                        "timeouts": len(rows),
                        "delta_mean": float(delta.mean()),
                        "delta_p95": float(np.quantile(delta, 0.95)),
                        "flip_rate": float(flips),
                    }
                ]
            )

        out.to_csv(os.path.join(OUT_DIR, f"{label}_timeout_convention.csv"), index=False)
        print(f"Saved: {OUT_DIR}/{label}_timeout_convention.csv")


if __name__ == "__main__":
    main()
