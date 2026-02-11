#!/usr/bin/env python3
"""
Gap/illiquidity sensitivity using tick gaps.
Removes trades that overlap large tick gaps in either leg.
Outputs:
- data/analysis/m5_tick_gap_sensitivity.csv
- data/analysis/m15_tick_gap_sensitivity.csv
"""

from __future__ import annotations

import os
import sys
import numpy as np
import pandas as pd

sys.path.append(os.path.join(os.getcwd(), "scripts"))
from metrics import sharpe_daily, sharpe_daily_active, sharpe_trade
from pipelines import build_events_m5 as m5
from pipelines import build_events_m15 as m15

TICK_ROOT = "/Users/danielfisher/Desktop/tick"
OUT_DIR = "data/analysis"

GAP_SECONDS = [60, 120, 300]
LOSS_STREAK = 3
COOLDOWN_DAYS = 14

CONFIGS = [
    ("m5", "data/events/events_m5_8yr_v3_mom.csv", m5),
    ("m15", "data/events/events_m15_8yr_v3_mom.csv", m15),
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


def _symbol_from_barfile(fname: str) -> str:
    return fname.split("_")[0]


def _compute_gaps_for_symbol(symbol: str, gaps: list[int]) -> dict[int, tuple[np.ndarray, np.ndarray]]:
    path = os.path.join(TICK_ROOT, symbol)
    if not os.path.isdir(path):
        return {g: (np.array([], dtype="int64"), np.array([], dtype="int64")) for g in gaps}
    files = sorted([f for f in os.listdir(path) if f.endswith("_ticks.parquet")])
    if not files:
        return {g: (np.array([], dtype="int64"), np.array([], dtype="int64")) for g in gaps}

    gap_lists = {g: [] for g in gaps}
    prev_last = None

    for fname in files:
        f = os.path.join(path, fname)
        try:
            df = pd.read_parquet(f, columns=["timestamp"])
        except Exception:
            continue
        if df.empty:
            continue
        ts = pd.to_datetime(df["timestamp"], utc=True).astype("int64").to_numpy()
        if len(ts) < 2:
            continue
        # cross-file gap
        if prev_last is not None:
            delta = (ts[0] - prev_last) / 1e9
            for g in gaps:
                if delta > g:
                    gap_lists[g].append((int(prev_last), int(ts[0])))
        prev_last = int(ts[-1])

        delta = np.diff(ts) / 1e9
        for g in gaps:
            idx = np.where(delta > g)[0]
            if len(idx):
                for i in idx:
                    gap_lists[g].append((int(ts[i]), int(ts[i + 1])))

    out = {}
    for g, pairs in gap_lists.items():
        if not pairs:
            out[g] = (np.array([], dtype="int64"), np.array([], dtype="int64"))
            continue
        start = np.array([p[0] for p in pairs], dtype="int64")
        end = np.array([p[1] for p in pairs], dtype="int64")
        order = np.argsort(start)
        out[g] = (start[order], end[order])
    return out


def _overlaps_gap(entry_ts: int, exit_ts: int, gap_start: np.ndarray, gap_end: np.ndarray) -> bool:
    if len(gap_start) == 0:
        return False
    i = np.searchsorted(gap_start, exit_ts, side="right") - 1
    if i < 0:
        return False
    return gap_end[i] >= entry_ts


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)

    for label, path, module in CONFIGS:
        df = pd.read_csv(path, usecols=["pair", "timestamp", "duration_bars", "pnl_bps"])
        df["timestamp"] = df["timestamp"].astype("int64")

        pair_map = _pair_map(module)
        symbols = set()
        for _, (fx, fy, _cx, _cy) in pair_map.items():
            symbols.add(_symbol_from_barfile(fx))
            symbols.add(_symbol_from_barfile(fy))

        symbol_gaps = {gap: {} for gap in GAP_SECONDS}
        for sym in symbols:
            gap_map = _compute_gaps_for_symbol(sym, GAP_SECONDS)
            for g in GAP_SECONDS:
                symbol_gaps[g][sym] = gap_map[g]

        # load bar timestamps per pair for accurate exit_ts
        pair_ts = {}
        pair_idx = {}
        for pair, (fx, fy, cx, cy) in pair_map.items():
            loaded = module.load_pair_data(fx, fy, cx, cy)
            if loaded is None:
                continue
            ts = loaded["timestamp"].to_numpy()
            if np.issubdtype(ts.dtype, np.datetime64):
                ts = ts.astype("datetime64[ns]").astype("int64")
            else:
                ts = ts.astype("int64")
            pair_ts[pair] = ts
            pair_idx[pair] = {int(t): i for i, t in enumerate(ts)}

        baseline_rows = []
        for row in df.itertuples(index=False):
            if row.pair not in pair_ts:
                continue
            idx_map = pair_idx[row.pair]
            ts = pair_ts[row.pair]
            entry_idx = idx_map.get(int(row.timestamp))
            if entry_idx is None:
                continue
            duration = int(row.duration_bars)
            exit_idx = entry_idx + (duration - 1 if duration >= 500 else duration)
            if exit_idx >= len(ts):
                continue
            baseline_rows.append({"pair": row.pair, "timestamp": int(row.timestamp), "exit_ts": int(ts[exit_idx]), "pnl_bps": float(row.pnl_bps)})

        base_df = pd.DataFrame(baseline_rows)
        rows = []
        rows.append({"variant": "baseline", "guardrail": False, **_metrics(base_df), "gap_s": 0})
        rows.append({"variant": "baseline", "guardrail": True, **_metrics(_apply_guardrail(base_df)), "gap_s": 0})

        for gap in GAP_SECONDS:
            keep = []
            for row in base_df.itertuples(index=False):
                fx, fy, _cx, _cy = pair_map.get(row.pair, (None, None, None, None))
                if fx is None:
                    continue
                sym_x = _symbol_from_barfile(fx)
                sym_y = _symbol_from_barfile(fy)
                start_x, end_x = symbol_gaps[gap].get(sym_x, (np.array([], dtype="int64"), np.array([], dtype="int64")))
                start_y, end_y = symbol_gaps[gap].get(sym_y, (np.array([], dtype="int64"), np.array([], dtype="int64")))

                if _overlaps_gap(int(row.timestamp), int(row.exit_ts), start_x, end_x) or _overlaps_gap(int(row.timestamp), int(row.exit_ts), start_y, end_y):
                    continue
                keep.append(row._asdict())

            filtered = pd.DataFrame(keep)
            rows.append({"variant": f"gap_{gap}s", "guardrail": False, **_metrics(filtered), "gap_s": gap})
            rows.append({"variant": f"gap_{gap}s", "guardrail": True, **_metrics(_apply_guardrail(filtered)), "gap_s": gap})

        out = pd.DataFrame(rows)
        out.to_csv(os.path.join(OUT_DIR, f"{label}_tick_gap_sensitivity.csv"), index=False)
        print(f"Saved: {OUT_DIR}/{label}_tick_gap_sensitivity.csv")


if __name__ == "__main__":
    main()
