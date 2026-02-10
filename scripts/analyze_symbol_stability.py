#!/usr/bin/env python3
"""
Symbol stability test: remove top-N contributors and recompute metrics.

Outputs:
- data/analysis/m5_symbol_topn_sensitivity.csv
- data/analysis/m15_symbol_topn_sensitivity.csv
"""
from __future__ import annotations

import os
import sys
import numpy as np
import pandas as pd

sys.path.append(os.path.join(os.getcwd(), "scripts"))
from metrics import sharpe_daily, sharpe_daily_active, sharpe_trade

OUT_DIR = "data/analysis"
LOSS_STREAK = 3
COOLDOWN_DAYS = 7
TOP_N_LIST = [0, 1, 2, 3]

CONFIGS = [
    ("m5", "data/meta_model/events_m5_8yr_v3_mom.csv", 5),
    ("m15", "data/meta_model/events_m15_8yr_v3_mom.csv", 15),
]


def _max_dd(pnls: np.ndarray) -> float:
    if len(pnls) == 0:
        return 0.0
    curve = np.cumsum(pnls)
    peak = np.maximum.accumulate(curve)
    return float((curve - peak).min())


def _metrics(df: pd.DataFrame) -> dict:
    if df.empty:
        return dict(trades=0, mean_pnl=0.0, total_pnl=0.0, max_dd=0.0, sharpe=0.0, sharpe_active=0.0, sharpe_trade=0.0)
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


def main() -> None:  # pragma: no cover
    os.makedirs(OUT_DIR, exist_ok=True)

    for label, path, bar_minutes in CONFIGS:
        df = pd.read_csv(path)
        df["timestamp"] = df["timestamp"].astype("int64")
        bar_ns = int(pd.Timedelta(minutes=bar_minutes).value)
        durations = df["duration_bars"].astype(int)
        timeout_adjust = (durations >= 500).astype(int)
        df["exit_ts"] = df["timestamp"] + ((durations - timeout_adjust) * bar_ns)

        # Rank pairs by total PnL on baseline (no guardrail)
        pair_rank = (
            df.groupby("pair")["pnl_bps"].sum().sort_values(ascending=False)
        )

        rows = []
        for n in TOP_N_LIST:
            remove_pairs = list(pair_rank.head(n).index) if n > 0 else []
            kept = df[~df["pair"].isin(remove_pairs)].copy()

            rows.append({
                "removed_top_n": n,
                "removed_pairs": ",".join(remove_pairs) if remove_pairs else "",
                "guardrail": False,
                **_metrics(kept),
            })
            rows.append({
                "removed_top_n": n,
                "removed_pairs": ",".join(remove_pairs) if remove_pairs else "",
                "guardrail": True,
                **_metrics(_apply_guardrail(kept)),
            })

        out = pd.DataFrame(rows)
        out.to_csv(os.path.join(OUT_DIR, f"{label}_symbol_topn_sensitivity.csv"), index=False)
        print(f"Saved: {OUT_DIR}/{label}_symbol_topn_sensitivity.csv")


if __name__ == "__main__":
    main()
