#!/usr/bin/env python3
"""
Build per-symbol spread cost tables (p50/p90) and apply a simple cost model
to guardrailed M5/M15 MOM trades.

Outputs:
 - data/analysis/m5_cost_table.csv
 - data/analysis/m15_cost_table.csv
 - data/analysis/m5_cost_impact.csv
 - data/analysis/m15_cost_impact.csv
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Dict, Tuple

import numpy as np
import pandas as pd

ROOT = Path(".").resolve()
sys.path.append(str(ROOT / "src"))
sys.path.append(str(ROOT))

from behemoth.core.guardrail import apply_loss_streak_guardrail
from behemoth.core.metrics import sharpe_daily
from services.api.settings import settings


ROOT = Path(".")
DATA_DIR = {
    "m5": ROOT / "data" / "global_5m",
    "m15": ROOT / "data" / "global_15m",
}
EVENTS_PATH = {
    "m5": ROOT / "data" / "meta_model" / "events_m5_8yr_v3_mom.csv",
    "m15": ROOT / "data" / "meta_model" / "events_m15_8yr_v3_mom.csv",
}
OUT_DIR = ROOT / "data" / "analysis"


def _bar_suffix(bar: str) -> str:
    return "5m" if bar == "m5" else "15m"


def _symbol_from_file(path: Path, bar: str) -> str:
    stem = path.stem
    suffix = f"_{_bar_suffix(bar)}"
    return stem[: -len(suffix)] if stem.endswith(suffix) else stem


def build_cost_table(bar: str) -> pd.DataFrame:
    data_dir = DATA_DIR[bar]
    rows = []
    for file in sorted(data_dir.glob(f"*_{_bar_suffix(bar)}.parquet")):
        symbol = _symbol_from_file(file, bar)
        close_col = f"close_{symbol}"
        ask_col = f"ask_{symbol}"
        spread_col = f"spread_{symbol}"
        df = pd.read_parquet(file, columns=[close_col, ask_col, spread_col], engine="pyarrow")
        if df.empty:
            continue
        ask = df[ask_col].to_numpy(dtype=float)
        spread = df[spread_col].to_numpy(dtype=float)
        mid = ask - (spread / 2.0)
        valid = (mid > 0) & (spread >= 0)
        if not np.any(valid):
            continue
        half_spread_bps = (spread[valid] / 2.0) / mid[valid] * 10000.0
        rows.append(
            {
                "symbol": symbol,
                "half_spread_p50_bps": float(np.nanpercentile(half_spread_bps, 50)),
                "half_spread_p90_bps": float(np.nanpercentile(half_spread_bps, 90)),
                "half_spread_p95_bps": float(np.nanpercentile(half_spread_bps, 95)),
                "half_spread_p99_bps": float(np.nanpercentile(half_spread_bps, 99)),
            }
        )
    return pd.DataFrame(rows).sort_values("symbol")


def _pair_map() -> Dict[str, Tuple[str, str]]:
    import sys

    sys.path.append(os.getcwd())
    from pipelines.build_events_m5 import PAIRS as PAIRS_M5

    mapping = {}
    for name, fx, fy, cx, cy, *_ in PAIRS_M5:
        x_symbol = cx.replace("close_", "")
        y_symbol = cy.replace("close_", "")
        mapping[name] = (x_symbol, y_symbol)
    return mapping


def _max_dd(pnls: np.ndarray) -> float:
    if len(pnls) == 0:
        return 0.0
    curve = np.cumsum(pnls)
    peak = np.maximum.accumulate(curve)
    return float((curve - peak).min())


def _metrics(df: pd.DataFrame) -> dict:
    if df.empty:
        return {
            "trades": 0,
            "win_rate": 0.0,
            "mean_pnl": 0.0,
            "total_pnl": 0.0,
            "max_dd": 0.0,
            "sharpe": 0.0,
        }
    pnls = df["pnl_bps"].to_numpy(dtype=float)
    ts = df["exit_ts"].to_numpy(dtype="int64")
    return {
        "trades": int(len(pnls)),
        "win_rate": float((pnls > 0).mean() * 100.0),
        "mean_pnl": float(np.mean(pnls)),
        "total_pnl": float(np.sum(pnls)),
        "max_dd": _max_dd(pnls),
        "sharpe": float(sharpe_daily(pnls, ts)),
    }


def apply_costs_and_guardrail(bar: str, cost_table: pd.DataFrame, mode: str, floor_bps: float, fee_bps: float, slip_bps: float) -> dict:
    df = pd.read_csv(EVENTS_PATH[bar])
    if "strategy_type" in df.columns:
        df = df[df["strategy_type"] == "MOM"]
    bar_minutes = 5 if bar == "m5" else 15
    bar_ns = int(pd.Timedelta(minutes=bar_minutes).value)
    durations = df["duration_bars"].astype(int)
    timeout_adjust = (durations >= 500).astype(int)
    df["exit_ts"] = df["timestamp"].astype("int64") + ((durations - timeout_adjust) * bar_ns)

    pair_map = _pair_map()
    cost_lookup = {
        row["symbol"]: row[f"half_spread_{mode}_bps"]
        for _, row in cost_table.iterrows()
    }

    cost_bps = []
    for row in df.itertuples(index=False):
        x_sym, y_sym = pair_map.get(row.pair, (None, None))
        sym = y_sym if row.active_leg == "Y" else x_sym
        half_spread = cost_lookup.get(sym, 0.0)
        per_side = max(half_spread, floor_bps) + fee_bps + slip_bps
        cost_bps.append(2.0 * per_side)

    df = df.assign(cost_bps=np.array(cost_bps, dtype=float))
    df["pnl_bps"] = df["pnl_bps"] - df["cost_bps"]
    df = df[["pair", "exit_ts", "pnl_bps"]]

    df = apply_loss_streak_guardrail(
        df,
        loss_threshold=settings.guardrail_loss_threshold,
        loss_streak=settings.guardrail_loss_streak,
        cooldown_days=settings.guardrail_cooldown_days,
    )

    metrics = _metrics(df)
    metrics["mode"] = mode
    metrics["floor_bps"] = floor_bps
    metrics["fee_bps"] = fee_bps
    metrics["slip_bps"] = slip_bps
    return metrics


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--floor-bps", type=float, default=2.0, help="minimum half-spread bps per side")
    parser.add_argument("--fee-bps", type=float, default=0.0, help="fee bps per side")
    parser.add_argument("--slip-bps", type=float, default=1.0, help="slippage bps per side")
    parser.add_argument("--modes", nargs="+", default=["p50", "p90"], help="spread quantiles to use: p50/p90/p95/p99")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    for bar in ["m5", "m15"]:
        table = build_cost_table(bar)
        table.to_csv(OUT_DIR / f"{bar}_cost_table.csv", index=False)

        rows = []
        for mode in args.modes:
            rows.append(
                apply_costs_and_guardrail(
                    bar,
                    table,
                    mode=mode,
                    floor_bps=args.floor_bps,
                    fee_bps=args.fee_bps,
                    slip_bps=args.slip_bps,
                )
            )
        pd.DataFrame(rows).to_csv(OUT_DIR / f"{bar}_cost_impact.csv", index=False)
        print(f"Saved: data/analysis/{bar}_cost_table.csv")
        print(f"Saved: data/analysis/{bar}_cost_impact.csv")


if __name__ == "__main__":
    main()
