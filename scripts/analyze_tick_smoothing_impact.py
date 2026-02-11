#!/usr/bin/env python3
"""
Quantify impact of tick smoothing on OHLC and MOM signal counts.

Defaults:
- Years: 2024-2025 (to keep runtime reasonable)
- Timeframes: M5 + M15

Outputs:
- data/analysis/<bar>_smoothing_ohlc_summary.csv
- data/analysis/<bar>_smoothing_signal_summary.csv
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd

TICK_ROOT = "/Users/danielfisher/Desktop/tick"
OUT_DIR = "data/analysis"


def _parse_years(spec: str | None) -> set[int] | None:
    if spec is None or not spec.strip():
        return {2024, 2025}
    spec = spec.strip().lower()
    if spec in {"all", "full", "*"}:
        return None
    years: set[int] = set()
    for chunk in spec.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "-" in chunk:
            start_s, end_s = chunk.split("-", 1)
            start = int(start_s)
            end = int(end_s)
            if end < start:
                start, end = end, start
            years.update(range(start, end + 1))
        else:
            years.add(int(chunk))
    return years


YEARS = _parse_years(os.getenv("SMOOTHING_YEARS"))
TIMEFRAMES = {
    "m5": 300,
    "m15": 900,
}

# Smoothing configs (can be reduced via SMOOTHING_PRESET=fast)
TIME_BUCKETS_S = [1, 5, 10]
PRICE_EPS_BPS = [0.1, 0.5, 1.0]

ONLY_BAR = os.getenv("ONLY_BAR")
PRESET = os.getenv("SMOOTHING_PRESET", "full")
SKIP_OHLC = os.getenv("SMOOTHING_SKIP_OHLC", "0").strip().lower() in {"1", "true", "yes"}
if ONLY_BAR in TIMEFRAMES:
    TIMEFRAMES = {ONLY_BAR: TIMEFRAMES[ONLY_BAR]}
if PRESET == "fast":
    TIME_BUCKETS_S = [1, 5]
    PRICE_EPS_BPS = [0.5, 1.0]

Z_ENTRY = 1.5
Z_STOP = 4.0
Z_LOOKBACK = 750
MIN_GAP = 20
MAX_HOLD = 500

LOSS_STREAK = int(os.getenv("SMOOTHING_LOSS_STREAK", "3"))
COOLDOWN_DAYS = int(os.getenv("SMOOTHING_COOLDOWN_DAYS", "7"))
GUARDRAIL_MODE = os.getenv("SMOOTHING_GUARDRAIL", "0").strip().lower()


def _guardrail_modes() -> list[tuple[str, bool]]:
    if GUARDRAIL_MODE in {"1", "true", "yes"}:
        return [("guard", True)]
    if GUARDRAIL_MODE in {"both", "all"}:
        return [("noguard", False), ("guard", True)]
    return [("noguard", False)]


@dataclass
class PairSpec:
    name: str
    fx: str
    fy: str
    cx: str
    cy: str


def _pair_specs(bar: str) -> list[PairSpec]:
    if bar == "m5":
        from pipelines import build_events_m5 as mod
    else:
        from pipelines import build_events_m15 as mod
    return [PairSpec(name, fx, fy, cx, cy) for name, fx, fy, cx, cy, *_ in mod.PAIRS]


def _symbols_from_pairs(pairs: list[PairSpec]) -> list[str]:
    syms = set()
    for p in pairs:
        syms.add(p.fx.split("_")[0])
        syms.add(p.fy.split("_")[0])
    return sorted(syms)


def _year_from_fname(fname: str) -> int | None:
    m = re.search(r"_(\d{6})_ticks\.parquet$", fname)
    if not m:
        return None
    yyyymm = m.group(1)
    return int(yyyymm[:4])


def _load_ticks(symbol: str) -> Iterable[tuple[np.ndarray, np.ndarray]]:
    path = os.path.join(TICK_ROOT, symbol)
    if not os.path.isdir(path):
        return
    files = sorted([f for f in os.listdir(path) if f.endswith("_ticks.parquet")])
    for fname in files:
        year = _year_from_fname(fname)
        if year is None or (YEARS is not None and year not in YEARS):
            continue
        fpath = os.path.join(path, fname)
        df = pd.read_parquet(fpath, columns=["timestamp", "mid"])
        if df.empty:
            continue
        ts = pd.to_datetime(df["timestamp"], utc=True).astype("int64").to_numpy()
        price = df["mid"].to_numpy()
        yield ts, price


def _build_bars(ts: np.ndarray, price: np.ndarray, bar_s: int) -> pd.DataFrame:
    bar_ns = bar_s * 1_000_000_000
    bar_id = (ts // bar_ns).astype("int64")
    # group by bar_id
    df = pd.DataFrame({"bar_id": bar_id, "price": price})
    grouped = df.groupby("bar_id")
    out = pd.DataFrame({
        "bar_id": grouped["bar_id"].first(),
        "open": grouped["price"].first(),
        "high": grouped["price"].max(),
        "low": grouped["price"].min(),
        "close": grouped["price"].last(),
    }).reset_index(drop=True)
    return out


def _throttle_ticks(ts: np.ndarray, price: np.ndarray, bucket_s: float) -> tuple[np.ndarray, np.ndarray]:
    bucket_ns = int(bucket_s * 1_000_000_000)
    bucket = ts // bucket_ns
    # keep last tick per bucket
    keep = np.r_[bucket[1:] != bucket[:-1], True]
    return ts[keep], price[keep]


def _price_filter_ticks(ts: np.ndarray, price: np.ndarray, eps_bps: float) -> tuple[np.ndarray, np.ndarray]:
    if len(price) == 0:
        return ts, price
    keep_idx = [0]
    last_price = price[0]
    for i in range(1, len(price)):
        bps = abs(price[i] - last_price) / last_price * 10000.0
        if bps >= eps_bps:
            keep_idx.append(i)
            last_price = price[i]
    idx = np.array(keep_idx, dtype=int)
    return ts[idx], price[idx]


def _ohlc_diff(baseline: pd.DataFrame, smoothed: pd.DataFrame) -> dict:
    merged = baseline.merge(smoothed, on="bar_id", suffixes=("_base", "_smooth"))
    if merged.empty:
        return {"bars": 0}
    diffs = {}
    for col in ["open", "high", "low", "close"]:
        d = (merged[f"{col}_smooth"] - merged[f"{col}_base"]).abs()
        d_bps = (d / merged[f"{col}_base"]).replace([np.inf, -np.inf], np.nan) * 10000.0
        d_bps = d_bps.fillna(0.0)
        diffs[f"{col}_abs_mean"] = float(d.mean())
        diffs[f"{col}_abs_p50"] = float(d.median())
        diffs[f"{col}_abs_p95"] = float(d.quantile(0.95))
        diffs[f"{col}_abs_p99"] = float(d.quantile(0.99))
        diffs[f"{col}_bps_mean"] = float(d_bps.mean())
        diffs[f"{col}_bps_p50"] = float(d_bps.median())
        diffs[f"{col}_bps_p95"] = float(d_bps.quantile(0.95))
        diffs[f"{col}_bps_p99"] = float(d_bps.quantile(0.99))
        diffs[f"{col}_abs_gt_1bp"] = float((d_bps >= 1.0).mean())
    diffs["bars"] = int(len(merged))
    return diffs


def _compute_signals(close_x: np.ndarray, close_y: np.ndarray, ts: np.ndarray, bar: str) -> set[int]:
    if bar == "m5":
        from pipelines import build_events_m5 as mod
    else:
        from pipelines import build_events_m15 as mod

    y = np.log(close_y)
    x = np.log(close_x)
    betas, errors, _ = mod.compute_kalman_states(y, x)
    z = mod.compute_z_scores(errors, window=Z_LOOKBACK)

    last_entry = 0
    entries = set()
    for i in range(Z_LOOKBACK, len(y) - 2):
        beta = betas[i]
        if beta < 0.98:
            pass
        elif beta > 1.02:
            pass
        else:
            continue
        if abs(z[i]) < Z_ENTRY:
            continue
        if i - last_entry < MIN_GAP:
            continue
        entries.add(int(ts[i]))
        last_entry = i
    return entries


def _compute_trades(close_x: np.ndarray, close_y: np.ndarray, ts: np.ndarray, bar: str) -> list[dict]:
    if bar == "m5":
        from pipelines import build_events_m5 as mod
    else:
        from pipelines import build_events_m15 as mod

    y = np.log(close_y)
    x = np.log(close_x)
    betas, errors, _ = mod.compute_kalman_states(y, x)
    z = mod.compute_z_scores(errors, window=Z_LOOKBACK)

    last_entry = 0
    trades: list[dict] = []
    for i in range(Z_LOOKBACK, len(y) - 2):
        beta = betas[i]
        if beta < 0.98:
            active = y
        elif beta > 1.02:
            active = x
        else:
            continue
        if abs(z[i]) < Z_ENTRY:
            continue
        if i - last_entry < MIN_GAP:
            continue
        direction = 1 if z[i] > 0 else -1
        entry_price = active[i]
        exit_idx = min(i + MAX_HOLD, len(z) - 1)
        for j in range(i + 1, exit_idx + 1):
            z_j = z[j]
            if direction == 1:
                if z_j < 0 or z_j > Z_STOP:
                    exit_idx = j
                    break
            else:
                if z_j > 0 or z_j < -Z_STOP:
                    exit_idx = j
                    break
        pnl = float(direction * (active[exit_idx] - entry_price) * 10000.0)
        trades.append({
            "entry_ts": int(ts[i]),
            "exit_ts": int(ts[exit_idx]),
            "pnl": pnl,
        })
        last_entry = i
    return trades


def _apply_guardrail(trades: list[dict]) -> list[dict]:
    if not trades:
        return trades
    cooldown_ns = int(pd.Timedelta(days=COOLDOWN_DAYS).value)
    loss_streak = 0
    pause_until = None
    kept: list[dict] = []
    for t in trades:
        if pause_until is not None and t["entry_ts"] < pause_until:
            continue
        kept.append(t)
        if t["pnl"] <= 0:
            loss_streak += 1
        else:
            loss_streak = 0
        if loss_streak >= LOSS_STREAK:
            pause_until = t["exit_ts"] + cooldown_ns
            loss_streak = 0
    return kept


def _pnl_stats(trades: list[dict]) -> tuple[int, float, float]:
    if not trades:
        return 0, 0.0, 0.0
    pnls = np.array([t["pnl"] for t in trades], dtype=float)
    return int(len(pnls)), float(np.mean(pnls)), float(np.sum(pnls))


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    for bar, bar_s in TIMEFRAMES.items():
        pairs = _pair_specs(bar)
        symbols = _symbols_from_pairs(pairs)

        # Build baseline bars per symbol
        baseline_bars = {}
        for sym in symbols:
            frames = []
            for ts, price in _load_ticks(sym):
                frames.append(_build_bars(ts, price, bar_s))
            if not frames:
                continue
            df = pd.concat(frames, ignore_index=True)
            # consolidate duplicate bar_ids
            grouped = df.groupby("bar_id")
            baseline_bars[sym] = pd.DataFrame({
                "bar_id": grouped["bar_id"].first(),
                "open": grouped["open"].first(),
                "high": grouped["high"].max(),
                "low": grouped["low"].min(),
                "close": grouped["close"].last(),
            }).reset_index(drop=True)

        # Smoothing configs
        ohlc_rows = []
        signal_rows = []
        impact_rows = []
        impact_year_rows = []

        configs = []
        for b in TIME_BUCKETS_S:
            configs.append((f"time_bucket_{b}s", ("time", b)))
        for eps in PRICE_EPS_BPS:
            configs.append((f"price_eps_{eps}bps", ("price", eps)))

        for label, cfg in configs:
            smoothed_bars = {}
            for sym in symbols:
                frames = []
                for ts, price in _load_ticks(sym):
                    if cfg[0] == "time":
                        ts2, px2 = _throttle_ticks(ts, price, cfg[1])
                    else:
                        ts2, px2 = _price_filter_ticks(ts, price, cfg[1])
                    frames.append(_build_bars(ts2, px2, bar_s))
                if not frames:
                    continue
                df = pd.concat(frames, ignore_index=True)
                grouped = df.groupby("bar_id")
                smoothed_bars[sym] = pd.DataFrame({
                    "bar_id": grouped["bar_id"].first(),
                    "open": grouped["open"].first(),
                    "high": grouped["high"].max(),
                    "low": grouped["low"].min(),
                    "close": grouped["close"].last(),
                }).reset_index(drop=True)

                # OHLC diffs
                if not SKIP_OHLC and sym in baseline_bars:
                    diffs = _ohlc_diff(baseline_bars[sym], smoothed_bars[sym])
                    ohlc_rows.append({"bar": bar, "symbol": sym, "config": label, **diffs})

            # Signal drift + strategy impact
            for pair in pairs:
                sx = pair.fx.split("_")[0]
                sy = pair.fy.split("_")[0]
                if sx not in baseline_bars or sy not in baseline_bars:
                    continue
                if sx not in smoothed_bars or sy not in smoothed_bars:
                    continue

                bx = baseline_bars[sx]
                by = baseline_bars[sy]
                mx = smoothed_bars[sx]
                my = smoothed_bars[sy]

                base = bx.merge(by, on="bar_id", suffixes=("_x", "_y"))
                smooth = mx.merge(my, on="bar_id", suffixes=("_x", "_y"))

                if base.empty or smooth.empty:
                    continue

                # align on bar_id
                merged = base.merge(smooth, on="bar_id", suffixes=("_base", "_smooth"))
                if merged.empty:
                    continue

                ts_bar = merged["bar_id"].to_numpy() * bar_s * 1_000_000_000

                base_entries = _compute_signals(
                    merged["close_x_base"].to_numpy(),
                    merged["close_y_base"].to_numpy(),
                    ts_bar,
                    bar,
                )
                smooth_entries = _compute_signals(
                    merged["close_x_smooth"].to_numpy(),
                    merged["close_y_smooth"].to_numpy(),
                    ts_bar,
                    bar,
                )

                inter = base_entries.intersection(smooth_entries)
                signal_rows.append({
                    "bar": bar,
                    "pair": pair.name,
                    "config": label,
                    "base_entries": len(base_entries),
                    "smooth_entries": len(smooth_entries),
                    "overlap": len(inter),
                    "overlap_rate": (len(inter) / len(base_entries)) if base_entries else 0.0,
                })

                # Strategy impact (PnL on active leg)
                base_trades = _compute_trades(
                    merged["close_x_base"].to_numpy(),
                    merged["close_y_base"].to_numpy(),
                    ts_bar,
                    bar,
                )
                smooth_trades = _compute_trades(
                    merged["close_x_smooth"].to_numpy(),
                    merged["close_y_smooth"].to_numpy(),
                    ts_bar,
                    bar,
                )
                for guard_label, use_guard in _guardrail_modes():
                    if use_guard:
                        base_kept = _apply_guardrail(base_trades)
                        smooth_kept = _apply_guardrail(smooth_trades)
                    else:
                        base_kept = base_trades
                        smooth_kept = smooth_trades

                    base_n, base_mean, base_total = _pnl_stats(base_kept)
                    smooth_n, smooth_mean, smooth_total = _pnl_stats(smooth_kept)
                    mean_delta_pct = ((smooth_mean - base_mean) / abs(base_mean) * 100.0) if base_mean != 0 else 0.0
                    total_delta_pct = ((smooth_total - base_total) / abs(base_total) * 100.0) if base_total != 0 else 0.0

                    impact_rows.append({
                        "bar": bar,
                        "pair": pair.name,
                        "config": label,
                        "guardrail": guard_label,
                        "base_trades": base_n,
                        "smooth_trades": smooth_n,
                        "base_mean_pnl": base_mean,
                        "smooth_mean_pnl": smooth_mean,
                        "mean_delta_pct": mean_delta_pct,
                        "base_total_pnl": base_total,
                        "smooth_total_pnl": smooth_total,
                        "total_delta_pct": total_delta_pct,
                    })

                    if base_kept or smooth_kept:
                        base_years = pd.to_datetime([t["entry_ts"] for t in base_kept], utc=True).year if base_kept else []
                        smooth_years = pd.to_datetime([t["entry_ts"] for t in smooth_kept], utc=True).year if smooth_kept else []

                        for year in sorted(set(base_years) | set(smooth_years)):
                            base_year_trades = [t for t, y in zip(base_kept, base_years) if y == year]
                            smooth_year_trades = [t for t, y in zip(smooth_kept, smooth_years) if y == year]
                            b_n, b_mean, b_total = _pnl_stats(base_year_trades)
                            s_n, s_mean, s_total = _pnl_stats(smooth_year_trades)
                            impact_year_rows.append({
                                "bar": bar,
                                "pair": pair.name,
                                "config": label,
                                "guardrail": guard_label,
                                "year": int(year),
                                "base_trades": b_n,
                                "smooth_trades": s_n,
                                "base_mean_pnl": b_mean,
                                "smooth_mean_pnl": s_mean,
                                "base_total_pnl": b_total,
                                "smooth_total_pnl": s_total,
                            })

        if not SKIP_OHLC:
            pd.DataFrame(ohlc_rows).to_csv(os.path.join(OUT_DIR, f"{bar}_smoothing_ohlc_summary.csv"), index=False)
        pd.DataFrame(signal_rows).to_csv(os.path.join(OUT_DIR, f"{bar}_smoothing_signal_summary.csv"), index=False)
        pd.DataFrame(impact_rows).to_csv(os.path.join(OUT_DIR, f"{bar}_smoothing_strategy_impact.csv"), index=False)
        pd.DataFrame(impact_year_rows).to_csv(os.path.join(OUT_DIR, f"{bar}_smoothing_strategy_impact_year.csv"), index=False)
        print(f"Saved smoothing impact for {bar}")


if __name__ == "__main__":
    main()
