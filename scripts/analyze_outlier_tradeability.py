#!/usr/bin/env python3
"""
Assess tradeability of outlier bars (8σ) by checking continuation vs reversal
and systemic vs isolated occurrence.

Outputs:
- data/analysis/m5_outlier_tradeability.csv
- data/analysis/m15_outlier_tradeability.csv
- data/analysis/outlier_tradeability_summary.csv
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
WINDOW = 500
THRESH = 8.0
NEXT_HORIZONS = [1, 3, 6]

CONFIGS = [
    ("m5", m5),
    ("m15", m15),
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


def _rolling_std(arr: np.ndarray, window: int) -> np.ndarray:
    return pd.Series(arr).rolling(window).std().to_numpy()


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    summary_rows = []

    for label, module in CONFIGS:
        pair_info = _pair_map(module)
        rows = []
        ts_outlier_counts = {}

        for pair, (fx, fy, cx, cy) in pair_info.items():
            loaded = _load_prices(module, fx, fy, cx, cy)
            if loaded is None:
                continue
            ts, x, y = loaded

            for leg_name, series in [("X", x), ("Y", y)]:
                ret = np.diff(series)
                std = _rolling_std(ret, WINDOW)
                mask = (np.abs(ret) > THRESH * std) & ~np.isnan(std)
                idx = np.where(mask)[0]
                if len(idx) == 0:
                    continue

                for i in idx:
                    if i + max(NEXT_HORIZONS) >= len(ret):
                        continue
                    out_ret = ret[i]
                    out_bps = out_ret * 10000.0
                    sign = 1 if out_ret > 0 else -1

                    next1 = ret[i + 1] * 10000.0
                    next3 = ret[i + 1 : i + 1 + 3].sum() * 10000.0
                    next6 = ret[i + 1 : i + 1 + 6].sum() * 10000.0

                    continuation = 1 if next1 * sign > 0 else 0
                    reversal = 1 if next1 * sign < 0 else 0
                    retrace50 = 1 if (next1 * sign < 0) and (abs(next1) >= 0.5 * abs(out_bps)) else 0

                    t = int(ts[i + 1])
                    ts_outlier_counts[t] = ts_outlier_counts.get(t, 0) + 1

                    rows.append(
                        {
                            "pair": pair,
                            "leg": leg_name,
                            "timestamp": t,
                            "outlier_bps": out_bps,
                            "next1_bps": next1,
                            "next3_bps": next3,
                            "next6_bps": next6,
                            "continuation": continuation,
                            "reversal": reversal,
                            "retrace50": retrace50,
                        }
                    )

        df = pd.DataFrame(rows)
        if df.empty:
            continue

        # classify systemic vs isolated
        counts = pd.Series(ts_outlier_counts)
        df["outlier_count_same_ts"] = df["timestamp"].map(counts).fillna(1).astype(int)
        df["systemic"] = (df["outlier_count_same_ts"] >= 4).astype(int)
        df["isolated"] = (df["outlier_count_same_ts"] == 1).astype(int)

        # session distribution
        dt = pd.to_datetime(df["timestamp"], unit="ns", utc=True, errors="coerce")
        df["hour"] = dt.dt.hour

        out_path = os.path.join(OUT_DIR, f"{label}_outlier_tradeability.csv")
        df.to_csv(out_path, index=False)

        summary_rows.append(
            {
                "timeframe": label,
                "outliers": int(len(df)),
                "mean_outlier_bps": float(df["outlier_bps"].mean()),
                "p95_outlier_bps": float(df["outlier_bps"].abs().quantile(0.95)),
                "continuation_rate": float(df["continuation"].mean()),
                "reversal_rate": float(df["reversal"].mean()),
                "retrace50_rate": float(df["retrace50"].mean()),
                "systemic_rate": float(df["systemic"].mean()),
                "isolated_rate": float(df["isolated"].mean()),
                "next1_mean_bps": float(df["next1_bps"].mean()),
                "next3_mean_bps": float(df["next3_bps"].mean()),
                "next6_mean_bps": float(df["next6_bps"].mean()),
            }
        )

        print(f"Saved: {out_path}")

    summary = pd.DataFrame(summary_rows)
    summary.to_csv(os.path.join(OUT_DIR, "outlier_tradeability_summary.csv"), index=False)
    print(f"Saved: {OUT_DIR}/outlier_tradeability_summary.csv")


if __name__ == "__main__":
    main()
