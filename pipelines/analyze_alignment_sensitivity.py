#!/usr/bin/env python3
"""
Time alignment stress test: shift one leg by +/-1 bar and measure impact.

Outputs:
- data/analysis/m5_alignment_sensitivity.csv
- data/analysis/m15_alignment_sensitivity.csv
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
import numpy as np
import pandas as pd

sys.path.append(os.path.join(os.getcwd(), "src"))
from behemoth.config import Z_ENTRY_MOM, Z_STOP, MIN_GAP_BARS, ACTIVE_LEG_LOW, ACTIVE_LEG_HIGH
from behemoth.core.active_leg import select_active_leg
from behemoth.core.events import simulate_trade
from behemoth.core.kalman import compute_kalman_states
from behemoth.core.zscore import compute_z_scores
from behemoth.io.loaders import load_pair_data

OUT_DIR = "data/analysis"
Z_WINDOW = 500
STRIDE = int(os.getenv("ALIGN_STRIDE", "1"))
MAX_BARS = int(os.getenv("ALIGN_MAX_BARS", "0"))
MAX_PAIRS = int(os.getenv("ALIGN_MAX_PAIRS", "0"))


@dataclass
class PairSpec:
    name: str
    fx: str
    fy: str
    cx: str
    cy: str


M5_PAIRS = [
    ("EUR/GBP", "EURUSD_5m.parquet", "GBPUSD_5m.parquet", "close_EURUSD", "close_GBPUSD"),
    ("Gold/Oil", "BCOUSD_5m.parquet", "XAUUSD_5m.parquet", "close_BCOUSD", "close_XAUUSD"),
    ("Oil/Silver", "BCOUSD_5m.parquet", "XAGUSD_5m.parquet", "close_BCOUSD", "close_XAGUSD"),
    ("AUD/NZD", "NZDUSD_5m.parquet", "AUDUSD_5m.parquet", "close_NZDUSD", "close_AUDUSD"),
    ("CAC/NZD", "NZDUSD_5m.parquet", "FRXEUR_5m.parquet", "close_NZDUSD", "close_FRXEUR"),
    ("Gold/Silver", "XAUUSD_5m.parquet", "XAGUSD_5m.parquet", "close_XAUUSD", "close_XAGUSD"),
    ("SPX/DAX", "SPXUSD_5m.parquet", "GRXEUR_5m.parquet", "close_SPXUSD", "close_GRXEUR"),
    ("SPX/CAC", "SPXUSD_5m.parquet", "FRXEUR_5m.parquet", "close_SPXUSD", "close_FRXEUR"),
    ("SPX/FTSE", "SPXUSD_5m.parquet", "UKXGBP_5m.parquet", "close_SPXUSD", "close_UKXGBP"),
    ("SPX/Nikkei", "SPXUSD_5m.parquet", "JPXJPY_5m.parquet", "close_SPXUSD", "close_JPXJPY"),
    ("SPX/HK", "SPXUSD_5m.parquet", "HKXHKD_5m.parquet", "close_SPXUSD", "close_HKXHKD"),
    ("SPX/Dow", "SPXUSD_5m.parquet", "UDXUSD_5m.parquet", "close_SPXUSD", "close_UDXUSD"),
    ("SPX/Nas", "SPXUSD_5m.parquet", "NSXUSD_5m.parquet", "close_SPXUSD", "close_NSXUSD"),
    ("AUD/CAD", "AUDUSD_5m.parquet", "USDCAD_5m.parquet", "close_AUDUSD", "close_USDCAD"),
    ("EUR/CHF", "EURUSD_5m.parquet", "USDCHF_5m.parquet", "close_EURUSD", "close_USDCHF"),
    ("EUR/JPY", "EURUSD_5m.parquet", "USDJPY_5m.parquet", "close_EURUSD", "close_USDJPY"),
    ("GBP/JPY", "GBPUSD_5m.parquet", "USDJPY_5m.parquet", "close_GBPUSD", "close_USDJPY"),
    ("CHF/JPY", "USDCHF_5m.parquet", "USDJPY_5m.parquet", "close_USDCHF", "close_USDJPY"),
    ("EUR/AUD", "EURUSD_5m.parquet", "AUDUSD_5m.parquet", "close_EURUSD", "close_AUDUSD"),
    ("GBP/AUD", "GBPUSD_5m.parquet", "AUDUSD_5m.parquet", "close_GBPUSD", "close_AUDUSD"),
    ("GBP/CAD", "GBPUSD_5m.parquet", "USDCAD_5m.parquet", "close_GBPUSD", "close_USDCAD"),
    ("NZD/CAD", "NZDUSD_5m.parquet", "USDCAD_5m.parquet", "close_NZDUSD", "close_USDCAD"),
]

M15_PAIRS = [
    ("EUR/GBP", "EURUSD_15m.parquet", "GBPUSD_15m.parquet", "close_EURUSD", "close_GBPUSD"),
    ("Gold/Oil", "BCOUSD_15m.parquet", "XAUUSD_15m.parquet", "close_BCOUSD", "close_XAUUSD"),
    ("Oil/Silver", "BCOUSD_15m.parquet", "XAGUSD_15m.parquet", "close_BCOUSD", "close_XAGUSD"),
    ("AUD/NZD", "NZDUSD_15m.parquet", "AUDUSD_15m.parquet", "close_NZDUSD", "close_AUDUSD"),
    ("CAC/NZD", "NZDUSD_15m.parquet", "FRXEUR_15m.parquet", "close_NZDUSD", "close_FRXEUR"),
    ("Gold/Silver", "XAUUSD_15m.parquet", "XAGUSD_15m.parquet", "close_XAUUSD", "close_XAGUSD"),
    ("SPX/DAX", "SPXUSD_15m.parquet", "GRXEUR_15m.parquet", "close_SPXUSD", "close_GRXEUR"),
    ("SPX/CAC", "SPXUSD_15m.parquet", "FRXEUR_15m.parquet", "close_SPXUSD", "close_FRXEUR"),
    ("SPX/FTSE", "SPXUSD_15m.parquet", "UKXGBP_15m.parquet", "close_SPXUSD", "close_UKXGBP"),
    ("SPX/Nikkei", "SPXUSD_15m.parquet", "JPXJPY_15m.parquet", "close_SPXUSD", "close_JPXJPY"),
    ("SPX/HK", "SPXUSD_15m.parquet", "HKXHKD_15m.parquet", "close_SPXUSD", "close_HKXHKD"),
    ("SPX/Dow", "SPXUSD_15m.parquet", "UDXUSD_15m.parquet", "close_SPXUSD", "close_UDXUSD"),
    ("SPX/Nas", "SPXUSD_15m.parquet", "NSXUSD_15m.parquet", "close_SPXUSD", "close_NSXUSD"),
    ("AUD/CAD", "AUDUSD_15m.parquet", "USDCAD_15m.parquet", "close_AUDUSD", "close_USDCAD"),
    ("EUR/CHF", "EURUSD_15m.parquet", "USDCHF_15m.parquet", "close_EURUSD", "close_USDCHF"),
    ("EUR/JPY", "EURUSD_15m.parquet", "USDJPY_15m.parquet", "close_EURUSD", "close_USDJPY"),
    ("GBP/JPY", "GBPUSD_15m.parquet", "USDJPY_15m.parquet", "close_GBPUSD", "close_USDJPY"),
    ("CHF/JPY", "USDCHF_15m.parquet", "USDJPY_15m.parquet", "close_USDCHF", "close_USDJPY"),
    ("EUR/AUD", "EURUSD_15m.parquet", "AUDUSD_15m.parquet", "close_EURUSD", "close_AUDUSD"),
    ("GBP/AUD", "GBPUSD_15m.parquet", "AUDUSD_15m.parquet", "close_GBPUSD", "close_AUDUSD"),
    ("GBP/CAD", "GBPUSD_15m.parquet", "USDCAD_15m.parquet", "close_GBPUSD", "close_USDCAD"),
    ("NZD/CAD", "NZDUSD_15m.parquet", "USDCAD_15m.parquet", "close_NZDUSD", "close_USDCAD"),
]


CONFIGS = [
    ("m5", "data/global_5m", M5_PAIRS),
    ("m15", "data/global_15m", M15_PAIRS),
]


def _load_pair(data_dir: str, spec: PairSpec):
    df = load_pair_data(data_dir, spec.fx, spec.fy, spec.cx, spec.cy)
    if df is None or df.height == 0:
        return None
    if MAX_BARS > 0:
        keep = MAX_BARS + Z_WINDOW + 50
        if df.height > keep:
            df = df.tail(keep)
    y = np.log(df["Y"].to_numpy())
    x = np.log(df["X"].to_numpy())
    ts = df["timestamp"].to_numpy()
    return ts, y, x


def _align_series(ts, y, x, shift: int):
    if shift == 0:
        return ts, y, x
    if shift > 0:
        return ts[:-shift], y[:-shift], x[shift:]
    # shift < 0
    s = abs(shift)
    return ts[s:], y[s:], x[:-s]


def _max_dd(pnls: np.ndarray) -> float:
    if len(pnls) == 0:
        return 0.0
    curve = np.cumsum(pnls)
    peak = np.maximum.accumulate(curve)
    return float((curve - peak).min())


def _metrics(pnls: list[float]) -> dict:
    arr = np.asarray(pnls, dtype=float)
    if arr.size == 0:
        return {"trades": 0, "mean_pnl": 0.0, "total_pnl": 0.0, "max_dd": 0.0}
    return {
        "trades": int(arr.size),
        "mean_pnl": float(arr.mean()),
        "total_pnl": float(arr.sum()),
        "max_dd": _max_dd(arr),
    }


def _build_mom_trades(ts, y, x):
    betas, errors, _ = compute_kalman_states(y, x)
    z_scores = compute_z_scores(errors, window=Z_WINDOW)

    last_entry = -10_000
    pnls = []
    end = len(z_scores)
    if MAX_BARS > 0:
        end = min(end, MAX_BARS)
    for i in range(0, end, max(1, STRIDE)):
        z = z_scores[i]
        if abs(z) < Z_ENTRY_MOM:
            continue
        if i - last_entry < MIN_GAP_BARS:
            continue
        active = select_active_leg(betas[i], ACTIVE_LEG_LOW, ACTIVE_LEG_HIGH)
        if active is None:
            continue
        direction = 1 if z > 0 else -1
        pnl, _, _ = simulate_trade(i, direction, "MOM", y, x, z_scores, active, Z_ENTRY_MOM, Z_STOP)
        pnls.append(pnl)
        last_entry = i
    return pnls


def main() -> None:  # pragma: no cover
    os.makedirs(OUT_DIR, exist_ok=True)

    for label, data_dir, pairs in CONFIGS:
        rows = []
        for idx, (name, fx, fy, cx, cy) in enumerate(pairs):
            if MAX_PAIRS > 0 and idx >= MAX_PAIRS:
                break
            spec = PairSpec(name, fx, fy, cx, cy)
            loaded = _load_pair(data_dir, spec)
            if loaded is None:
                continue
            ts, y, x = loaded

            for shift in (-1, 0, 1):
                ts_s, y_s, x_s = _align_series(ts, y, x, shift)
                if len(ts_s) < 100:
                    continue
                pnls = _build_mom_trades(ts_s, y_s, x_s)
                m = _metrics(pnls)
                rows.append({"pair": name, "shift": shift, "stride": STRIDE, "max_bars": MAX_BARS, **m})

        out = pd.DataFrame(rows)
        out.to_csv(os.path.join(OUT_DIR, f"{label}_alignment_sensitivity.csv"), index=False)
        print(f"Saved: {OUT_DIR}/{label}_alignment_sensitivity.csv")


if __name__ == "__main__":
    main()
