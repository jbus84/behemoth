#!/usr/bin/env python3
"""
Build FX/commodities strategy report for M5, M15, and M60 (H1 source data).

Variants per timeframe:
- baseline
- baseline_guardrail
- baseline_guardrail_acceleration

Outputs:
- data/analysis/strategy_fx_comm_overall.csv
- data/analysis/strategy_fx_comm_pair.csv
- data/analysis/strategy_fx_comm_yearly.csv
- data/analysis/strategy_fx_comm_pair_yearly.csv
- data/analysis/strategy_fx_comm_accel_thresholds.csv
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from behemoth.config import COOLDOWN_DAYS, LOSS_STREAK
from behemoth.core.metrics import sharpe_daily


START_EQUITY = 100_000.0
RISK_PER_TRADE_PCT = 0.01
MIN_ACCEL_TRADE_FRAC = 0.20
ACCEL_QUANTILES = [0.50, 0.60, 0.70, 0.80, 0.85, 0.90, 0.92, 0.94, 0.96, 0.98]

PAIR_WHITELIST_BASE = [
    "EUR/GBP",
    "AUD/NZD",
    "EUR/CHF",
    "EUR/JPY",
    "GBP/JPY",
    "CHF/JPY",
    "EUR/AUD",
    "GBP/AUD",
    "AUD/CAD",
    "GBP/CAD",
    "NZD/CAD",
    "Gold/Oil",
    "Oil/Silver",
    "Gold/Silver",
]
OIL_LINKED_PAIRS = {"Gold/Oil", "Oil/Silver"}


@dataclass(frozen=True)
class TfConfig:
    report_bar: str
    source_bar: str
    path: str
    bar_minutes: int


TIMEFRAMES = [
    TfConfig("m5", "m5", "data/events/events_m5_8yr_v3_mom.csv", 5),
    TfConfig("m15", "m15", "data/events/events_m15_8yr_v3_mom.csv", 15),
    TfConfig("m60", "h1", "data/events/events_h1_8yr_v3_mom.csv", 60),
]


def _normalize_ts_ns(series: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(series):
        vals = series.astype("int64")
        if len(vals) == 0:
            return vals
        max_v = int(vals.max())
        # us epoch -> ns epoch
        if 10**14 < max_v < 10**17:
            return vals * 1000
        # s epoch -> ns epoch
        if 10**9 < max_v < 10**11:
            return vals * 1_000_000_000
        return vals
    return pd.to_datetime(series, utc=True, errors="coerce").astype("int64")


def _compute_exit_ts(df: pd.DataFrame, bar_minutes: int) -> pd.Series:
    if "exit_ts" in df.columns:
        return _normalize_ts_ns(df["exit_ts"])
    duration_col = None
    if "duration_bars" in df.columns:
        duration_col = "duration_bars"
    elif "duration" in df.columns:
        duration_col = "duration"
    if duration_col is None:
        return _normalize_ts_ns(df["timestamp"])
    bar_ns = int(pd.Timedelta(minutes=bar_minutes).value)
    durations = pd.to_numeric(df[duration_col], errors="coerce").fillna(0).astype(int).clip(lower=0)
    if "max_hold_bars" in df.columns:
        max_hold = pd.to_numeric(df["max_hold_bars"], errors="coerce").fillna(500).astype(int).clip(lower=1)
    else:
        max_hold = pd.Series(500, index=df.index, dtype="int64")
    timeout_adjust = (durations >= max_hold).astype(int)
    return _normalize_ts_ns(df["timestamp"]) + ((durations - timeout_adjust) * bar_ns)


def _load_tf_frame(cfg: TfConfig, pair_whitelist: list[str]) -> pd.DataFrame:
    path = ROOT / cfg.path
    if not path.exists():
        raise FileNotFoundError(f"Missing dataset: {cfg.path}")

    df = pd.read_csv(path)
    if df.empty:
        return df

    if "pair" not in df.columns and "symbol" in df.columns:
        df = df.rename(columns={"symbol": "pair"})
    if "pair" not in df.columns:
        raise ValueError(f"Expected `pair` column in {cfg.path}")
    if "pnl_bps" not in df.columns:
        raise ValueError(f"Expected `pnl_bps` column in {cfg.path}")

    if "strategy_type" in df.columns:
        df = df[df["strategy_type"].astype(str).str.upper() == "MOM"].copy()
    else:
        df = df.copy()

    df = df[df["pair"].isin(pair_whitelist)].copy()
    if df.empty:
        return df

    df["timestamp"] = _normalize_ts_ns(df["timestamp"])
    df["exit_ts"] = _compute_exit_ts(df, cfg.bar_minutes)
    df["pnl_bps"] = pd.to_numeric(df["pnl_bps"], errors="coerce")
    df = df.dropna(subset=["pnl_bps", "timestamp", "exit_ts", "pair"]).copy()
    df["pnl_bps"] = df["pnl_bps"].astype(float)
    if "z_accel" in df.columns:
        df["z_accel"] = pd.to_numeric(df["z_accel"], errors="coerce")
    else:
        df["z_accel"] = 0.0
    if "entry_exit_variant" not in df.columns:
        df["entry_exit_variant"] = "baseline"
    if "exit_policy" not in df.columns:
        if "max_hold_bars" in df.columns:
            max_hold = pd.to_numeric(df["max_hold_bars"], errors="coerce")
            is_adaptive = bool((max_hold.fillna(500) < 500).any())
            df["exit_policy"] = "adaptive_entry_z" if is_adaptive else "fixed"
        else:
            df["exit_policy"] = "fixed"

    return df.sort_values(["timestamp", "pair", "entry_exit_variant"]).reset_index(drop=True)


def _apply_guardrail(df: pd.DataFrame) -> pd.DataFrame:
    """
    Causal guardrail simulation:
    - Check guardrail only at entry timestamp.
    - Update streak/pause only on exit of accepted trades.
    - Never retroactively cancel already-open accepted trades.
    """
    if df.empty:
        return df.copy()

    work = df.copy().reset_index(drop=True)
    n = len(work)
    work["row_id"] = np.arange(n, dtype=np.int64)

    entries = work[["row_id", "timestamp"]].rename(columns={"timestamp": "ts"})
    entries["event_type"] = 1  # entry after exit when ts ties

    exits = work[["row_id", "exit_ts"]].rename(columns={"exit_ts": "ts"})
    exits["event_type"] = 0  # process exits first on equal timestamp

    events = pd.concat([entries, exits], ignore_index=True).sort_values(
        ["ts", "event_type", "row_id"], kind="mergesort"
    )

    cooldown_ns = int(pd.Timedelta(days=COOLDOWN_DAYS).value)
    accepted = np.zeros(n, dtype=bool)
    pairs = work["pair"].to_numpy()
    pnls = work["pnl_bps"].to_numpy(dtype=float)

    state: dict[str, dict[str, int]] = {}
    # state[pair] = {"loss_streak": int, "pause_until": int}

    for evt in events.itertuples(index=False):
        rid = int(evt.row_id)
        ts = int(evt.ts)
        pair = str(pairs[rid])

        st = state.get(pair)
        if st is None:
            st = {"loss_streak": 0, "pause_until": -1}
            state[pair] = st

        if int(evt.event_type) == 1:
            # Entry check only. If paused, block this entry.
            if st["pause_until"] != -1 and ts < st["pause_until"]:
                continue
            accepted[rid] = True
            continue

        # Exit event only updates state for trades that were accepted at entry.
        if not accepted[rid]:
            continue

        pnl = float(pnls[rid])
        if pnl > 0.0:
            st["loss_streak"] = 0
            st["pause_until"] = -1
        else:
            st["loss_streak"] += 1
            if st["loss_streak"] >= LOSS_STREAK:
                st["pause_until"] = ts + cooldown_ns
                st["loss_streak"] = 0

    out = work.loc[accepted].copy()
    return out.drop(columns=["row_id"]).reset_index(drop=True)


def _derive_risk_bps(df: pd.DataFrame, fallback: float = 100.0) -> float:
    losses = df.loc[df["pnl_bps"] < 0.0, "pnl_bps"].abs()
    if losses.empty:
        return float(fallback)
    # Conservative proxy for stop distance: historical worst realized loss.
    # This keeps "1% risk per trade" bounded to <=1% on the observed sample.
    v = float(losses.max())
    return max(v, 1.0)


def _equity_stats(df: pd.DataFrame, risk_bps: float) -> dict[str, float]:
    """
    Account-equity risk stats under risk-per-trade sizing.
    """
    if df.empty:
        return {
            "cagr": 0.0,
            "max_dd_usd": 0.0,
            "max_dd_pct": 0.0,
            "max_below_start_usd": 0.0,
            "max_below_start_pct": 0.0,
            "max_daily_dd_pct": 0.0,
        }

    ordered = df.sort_values("exit_ts").copy()
    start_date = pd.to_datetime(int(ordered["exit_ts"].iloc[0]), unit="ns", utc=True).date()
    end_date = pd.to_datetime(int(ordered["exit_ts"].iloc[-1]), unit="ns", utc=True).date()
    days = (end_date - start_date).days

    equity = float(START_EQUITY)
    equity_curve: list[float] = []
    pnl_usd: list[float] = []
    exit_dates: list[pd.Timestamp] = []
    bankrupt = False

    for row in ordered.itertuples(index=False):
        # Risk model: each trade risks 1% of current equity at `risk_bps` adverse move.
        # account_return = risk_pct * (pnl_bps / risk_bps)
        trade_ret = RISK_PER_TRADE_PCT * (float(row.pnl_bps) / float(risk_bps))
        trade_pnl_usd = equity * trade_ret
        equity += trade_pnl_usd
        if equity <= 0.0:
            equity = 0.0
            bankrupt = True
        equity_curve.append(equity)
        pnl_usd.append(trade_pnl_usd)
        exit_dates.append(pd.to_datetime(int(row.exit_ts), unit="ns", utc=True))
        if bankrupt:
            break

    eq = np.asarray([START_EQUITY, *equity_curve], dtype=float)
    peak = np.maximum.accumulate(eq)
    dd_usd = eq - peak
    dd_pct = np.divide(dd_usd, peak, out=np.zeros_like(dd_usd), where=peak > 0.0)

    below_start_usd = eq - START_EQUITY
    below_start_pct = below_start_usd / START_EQUITY

    cagr = 0.0
    if bankrupt:
        cagr = -1.0
    elif days > 0:
        try:
            cagr = float((eq[-1] / START_EQUITY) ** (365.25 / days) - 1.0)
        except (ZeroDivisionError, OverflowError, ValueError):
            cagr = 0.0

    ddf = pd.DataFrame({"exit_dt": exit_dates, "pnl_usd": pnl_usd})
    ddf["date"] = ddf["exit_dt"].dt.normalize()
    daily_pnl = ddf.groupby("date")["pnl_usd"].sum().sort_index()
    daily_equity = START_EQUITY + daily_pnl.cumsum()
    daily_peak = daily_equity.cummax()
    daily_dd_pct = ((daily_equity - daily_peak) / daily_peak).min() if not daily_equity.empty else 0.0

    return {
        "cagr": float(cagr),
        "max_dd_usd": float(dd_usd.min()) if len(dd_usd) else 0.0,
        "max_dd_pct": float(dd_pct.min()) if len(dd_pct) else 0.0,
        "max_below_start_usd": float(below_start_usd.min()) if len(below_start_usd) else 0.0,
        "max_below_start_pct": float(below_start_pct.min()) if len(below_start_pct) else 0.0,
        "max_daily_dd_pct": float(daily_dd_pct),
    }


def _notional_cagr(df: pd.DataFrame) -> float:
    """
    CAGR from aggregated trade bps as if returns were on full notional.
    This does not apply account position sizing.
    """
    if df.empty:
        return 0.0
    ordered = df.sort_values("exit_ts")
    start_date = pd.to_datetime(int(ordered["exit_ts"].iloc[0]), unit="ns", utc=True).date()
    end_date = pd.to_datetime(int(ordered["exit_ts"].iloc[-1]), unit="ns", utc=True).date()
    days = (end_date - start_date).days
    if days <= 0:
        return 0.0

    total_return = float(ordered["pnl_bps"].sum()) / 10000.0
    if 1.0 + total_return <= 0.0:
        return -1.0
    try:
        return float((1.0 + total_return) ** (365.25 / days) - 1.0)
    except (ZeroDivisionError, OverflowError, ValueError):
        return 0.0


def _daily_stats_bps(df: pd.DataFrame) -> dict[str, float]:
    """
    Daily PnL and daily-curve drawdown statistics in bps.
    """
    if df.empty:
        return {
            "days_calendar": 0.0,
            "days_active": 0.0,
            "mean_daily_pnl_bps": 0.0,
            "median_daily_pnl_bps": 0.0,
            "mean_daily_pnl_bps_active": 0.0,
            "worst_single_day_bps": 0.0,
            "best_single_day_bps": 0.0,
            "max_daily_dd_bps": 0.0,
            "mean_daily_dd_bps_underwater": 0.0,
            "annualized_bps_calendar": 0.0,
        }

    exit_dt = pd.to_datetime(df["exit_ts"], unit="ns", utc=True)
    by_day = pd.DataFrame({"day": exit_dt.dt.normalize(), "pnl_bps": df["pnl_bps"].to_numpy(dtype=float)})
    daily_active = by_day.groupby("day")["pnl_bps"].sum().sort_index()
    full_idx = pd.date_range(daily_active.index.min(), daily_active.index.max(), freq="D", tz="UTC")
    daily = daily_active.reindex(full_idx, fill_value=0.0)
    vals = daily.to_numpy(dtype=float)

    curve = np.cumsum(vals)
    peak = np.maximum.accumulate(curve)
    dd = curve - peak
    uw = dd[dd < 0.0]

    mean_daily = float(np.mean(vals)) if len(vals) else 0.0
    return {
        "days_calendar": float(len(daily)),
        "days_active": float(len(daily_active)),
        "mean_daily_pnl_bps": mean_daily,
        "median_daily_pnl_bps": float(np.median(vals)) if len(vals) else 0.0,
        "mean_daily_pnl_bps_active": float(np.mean(daily_active.to_numpy(dtype=float))) if len(daily_active) else 0.0,
        "worst_single_day_bps": float(np.min(vals)) if len(vals) else 0.0,
        "best_single_day_bps": float(np.max(vals)) if len(vals) else 0.0,
        "max_daily_dd_bps": float(np.min(dd)) if len(dd) else 0.0,
        "mean_daily_dd_bps_underwater": float(np.mean(uw)) if len(uw) else 0.0,
        "annualized_bps_calendar": float(mean_daily * 365.25),
    }


def _exposure_stats(df: pd.DataFrame) -> dict[str, float]:
    """
    Exposure statistics from trade entry/exit timestamps.
    """
    if df.empty:
        return {
            "time_in_market_pct": 0.0,
            "avg_concurrent_trades": 0.0,
            "trade_density_per_day": 0.0,
            "avg_trade_duration_bars": 0.0,
            "avg_trade_duration_hours": 0.0,
        }

    if "timestamp" not in df.columns or "exit_ts" not in df.columns:
        return {
            "time_in_market_pct": 0.0,
            "avg_concurrent_trades": 0.0,
            "trade_density_per_day": 0.0,
            "avg_trade_duration_bars": 0.0,
            "avg_trade_duration_hours": 0.0,
        }

    start_ns = pd.to_numeric(df["timestamp"], errors="coerce")
    end_ns = pd.to_numeric(df["exit_ts"], errors="coerce")
    valid = start_ns.notna() & end_ns.notna()
    if not bool(valid.any()):
        return {
            "time_in_market_pct": 0.0,
            "avg_concurrent_trades": 0.0,
            "trade_density_per_day": 0.0,
            "avg_trade_duration_bars": 0.0,
            "avg_trade_duration_hours": 0.0,
        }

    start_vals = start_ns.loc[valid].astype("int64")
    end_vals = end_ns.loc[valid].astype("int64")
    keep = end_vals >= start_vals
    if not bool(keep.any()):
        return {
            "time_in_market_pct": 0.0,
            "avg_concurrent_trades": 0.0,
            "trade_density_per_day": 0.0,
            "avg_trade_duration_bars": 0.0,
            "avg_trade_duration_hours": 0.0,
        }

    start_vals = start_vals.loc[keep]
    end_vals = end_vals.loc[keep]

    t0 = int(start_vals.min())
    t1 = int(end_vals.max())
    total_ns = max(0, t1 - t0)

    entries = pd.DataFrame({"ts": start_vals.to_numpy(dtype="int64"), "delta": np.ones(len(start_vals), dtype="int8"), "event_type": np.ones(len(start_vals), dtype="int8")})
    exits = pd.DataFrame({"ts": end_vals.to_numpy(dtype="int64"), "delta": -np.ones(len(end_vals), dtype="int8"), "event_type": np.zeros(len(end_vals), dtype="int8")})
    events = pd.concat([entries, exits], ignore_index=True).sort_values(
        ["ts", "event_type"], kind="mergesort"
    )

    active_ns = 0
    weighted_concurrency_ns = 0
    current_open = 0
    prev_ts = int(events["ts"].iloc[0])
    for evt in events.itertuples(index=False):
        ts = int(evt.ts)
        dt = ts - prev_ts
        if dt > 0:
            if current_open > 0:
                active_ns += dt
            weighted_concurrency_ns += current_open * dt
        current_open += int(evt.delta)
        prev_ts = ts

    time_in_market_pct = (100.0 * active_ns / total_ns) if total_ns > 0 else 0.0
    avg_concurrency = (weighted_concurrency_ns / total_ns) if total_ns > 0 else 0.0
    total_days = total_ns / float(pd.Timedelta(days=1).value) if total_ns > 0 else 0.0
    trade_density_per_day = (len(start_vals) / total_days) if total_days > 0 else 0.0

    duration_hours = (end_vals.to_numpy(dtype=float) - start_vals.to_numpy(dtype=float)) / float(pd.Timedelta(hours=1).value)
    duration_hours = duration_hours[np.isfinite(duration_hours) & (duration_hours >= 0.0)]
    avg_duration_hours = float(np.mean(duration_hours)) if len(duration_hours) else 0.0

    if "duration_bars" in df.columns:
        dur_bars = pd.to_numeric(df.loc[valid].loc[keep].get("duration_bars"), errors="coerce").to_numpy(dtype=float)
        dur_bars = dur_bars[np.isfinite(dur_bars) & (dur_bars >= 0.0)]
        avg_duration_bars = float(np.mean(dur_bars)) if len(dur_bars) else 0.0
    else:
        avg_duration_bars = 0.0

    return {
        "time_in_market_pct": float(time_in_market_pct),
        "avg_concurrent_trades": float(avg_concurrency),
        "trade_density_per_day": float(trade_density_per_day),
        "avg_trade_duration_bars": float(avg_duration_bars),
        "avg_trade_duration_hours": float(avg_duration_hours),
    }


def _metrics_with_risk(df: pd.DataFrame, risk_bps: float) -> dict[str, float]:
    if df.empty:
        return {
            "trades": 0,
            "mean_pnl_per_trade_bps": 0.0,
            "total_pnl_bps": 0.0,
            "sharpe": 0.0,
            "cagr": 0.0,
            "cagr_notional_bps": 0.0,
            "risk_bps": float(risk_bps),
            "risk_per_trade_pct": RISK_PER_TRADE_PCT,
            "max_dd_usd": 0.0,
            "max_dd_pct": 0.0,
            "max_below_start_usd": 0.0,
            "max_below_start_pct": 0.0,
            "max_daily_dd_pct": 0.0,
            "days_calendar": 0.0,
            "days_active": 0.0,
            "mean_daily_pnl_bps": 0.0,
            "median_daily_pnl_bps": 0.0,
            "mean_daily_pnl_bps_active": 0.0,
            "worst_single_day_bps": 0.0,
            "best_single_day_bps": 0.0,
            "max_daily_dd_bps": 0.0,
            "mean_daily_dd_bps_underwater": 0.0,
            "annualized_bps_calendar": 0.0,
            "time_in_market_pct": 0.0,
            "avg_concurrent_trades": 0.0,
            "trade_density_per_day": 0.0,
            "avg_trade_duration_bars": 0.0,
            "avg_trade_duration_hours": 0.0,
        }
    pnls = df["pnl_bps"].to_numpy(dtype=float)
    ts = df["exit_ts"].to_numpy(dtype="int64")
    eq_stats = _equity_stats(df, risk_bps=risk_bps)
    daily_stats = _daily_stats_bps(df)
    exposure_stats = _exposure_stats(df)
    return {
        "trades": int(len(df)),
        "mean_pnl_per_trade_bps": float(np.mean(pnls)),
        "total_pnl_bps": float(np.sum(pnls)),
        "sharpe": float(sharpe_daily(pnls, ts)),
        "cagr": float(eq_stats["cagr"]),
        "cagr_notional_bps": float(_notional_cagr(df)),
        "risk_bps": float(risk_bps),
        "risk_per_trade_pct": RISK_PER_TRADE_PCT,
        "max_dd_usd": float(eq_stats["max_dd_usd"]),
        "max_dd_pct": float(eq_stats["max_dd_pct"]),
        "max_below_start_usd": float(eq_stats["max_below_start_usd"]),
        "max_below_start_pct": float(eq_stats["max_below_start_pct"]),
        "max_daily_dd_pct": float(eq_stats["max_daily_dd_pct"]),
        "days_calendar": float(daily_stats["days_calendar"]),
        "days_active": float(daily_stats["days_active"]),
        "mean_daily_pnl_bps": float(daily_stats["mean_daily_pnl_bps"]),
        "median_daily_pnl_bps": float(daily_stats["median_daily_pnl_bps"]),
        "mean_daily_pnl_bps_active": float(daily_stats["mean_daily_pnl_bps_active"]),
        "worst_single_day_bps": float(daily_stats["worst_single_day_bps"]),
        "best_single_day_bps": float(daily_stats["best_single_day_bps"]),
        "max_daily_dd_bps": float(daily_stats["max_daily_dd_bps"]),
        "mean_daily_dd_bps_underwater": float(daily_stats["mean_daily_dd_bps_underwater"]),
        "annualized_bps_calendar": float(daily_stats["annualized_bps_calendar"]),
        "time_in_market_pct": float(exposure_stats["time_in_market_pct"]),
        "avg_concurrent_trades": float(exposure_stats["avg_concurrent_trades"]),
        "trade_density_per_day": float(exposure_stats["trade_density_per_day"]),
        "avg_trade_duration_bars": float(exposure_stats["avg_trade_duration_bars"]),
        "avg_trade_duration_hours": float(exposure_stats["avg_trade_duration_hours"]),
    }


def _build_threshold_grid(abs_accel: pd.Series) -> list[float]:
    vals = [0.0]
    clean = abs_accel.replace([np.inf, -np.inf], np.nan).dropna()
    if clean.empty:
        return vals
    arr = clean.to_numpy(dtype=float)
    for q in ACCEL_QUANTILES:
        vals.append(float(np.quantile(arr, q)))
    unique = sorted({round(v, 10) for v in vals})
    return [float(v) for v in unique]


def _select_accel_threshold(
    baseline_df: pd.DataFrame,
    baseline_guard_df: pd.DataFrame,
    timeframe: str,
    exit_policy: str,
    entry_exit_variant: str,
    risk_bps: float,
) -> tuple[float, pd.DataFrame]:
    base_trades = int(len(baseline_guard_df))
    if base_trades == 0:
        out = pd.DataFrame(
            [
                {
                    "timeframe": timeframe,
                    "exit_policy": exit_policy,
                    "entry_exit_variant": entry_exit_variant,
                    "threshold": 0.0,
                    "eligible": False,
                    "selected": True,
                    "trade_frac": 0.0,
                    **_metrics_with_risk(baseline_guard_df, risk_bps),
                }
            ]
        )
        return 0.0, out

    thresholds = _build_threshold_grid(baseline_df["z_accel"].abs())
    rows = []
    for thr in thresholds:
        pre_guard = baseline_df if thr <= 0.0 else baseline_df[baseline_df["z_accel"].abs() > thr]
        sample = _apply_guardrail(pre_guard)
        m = _metrics_with_risk(sample, risk_bps)
        frac = (m["trades"] / base_trades) if base_trades else 0.0
        rows.append(
            {
                "timeframe": timeframe,
                "exit_policy": exit_policy,
                "entry_exit_variant": entry_exit_variant,
                "threshold": float(thr),
                "eligible": bool(frac >= MIN_ACCEL_TRADE_FRAC),
                "selected": False,
                "trade_frac": float(frac),
                **m,
            }
        )

    cand = pd.DataFrame(rows)
    selectable = cand[cand["eligible"]].copy()
    if selectable.empty:
        selectable = cand.copy()

    best_idx = selectable.sort_values(
        by=[
            "sharpe",
            "mean_pnl_per_trade_bps",
            "total_pnl_bps",
            "threshold",
        ],
        ascending=[False, False, False, True],
    ).index[0]
    cand.loc[best_idx, "selected"] = True
    best_threshold = float(cand.loc[best_idx, "threshold"])
    return best_threshold, cand


def _filter_pairs_by_sharpe(df: pd.DataFrame, cutoff: float) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    keep: list[str] = []
    for pair, sub in df.groupby("pair", sort=True):
        s = float(sharpe_daily(sub["pnl_bps"].to_numpy(dtype=float), sub["exit_ts"].to_numpy(dtype="int64")))
        if s >= cutoff:
            keep.append(pair)
    if not keep:
        return df.iloc[:0].copy()
    return df[df["pair"].isin(keep)].copy().reset_index(drop=True)


def _append_rollups(
    timeframe: str,
    source_bar: str,
    exit_policy: str,
    entry_exit_variant: str,
    variant: str,
    df: pd.DataFrame,
    overall_rows: list[dict],
    pair_rows: list[dict],
    yearly_rows: list[dict],
    pair_yearly_rows: list[dict],
    risk_bps: float,
    pair_universe_label: str,
) -> None:
    metrics_all = _metrics_with_risk(df, risk_bps)
    overall_rows.append(
        {
            "timeframe": timeframe,
            "source_bar": source_bar,
            "exit_policy": exit_policy,
            "entry_exit_variant": entry_exit_variant,
            "variant": variant,
            "pair_universe": pair_universe_label,
            **metrics_all,
        }
    )

    if df.empty:
        yearly_rows.append(
            {
                "timeframe": timeframe,
                "source_bar": source_bar,
                "exit_policy": exit_policy,
                "entry_exit_variant": entry_exit_variant,
                "variant": variant,
                "year": "overall",
                **metrics_all,
            }
        )
        return

    work = df.copy()
    work["year"] = pd.to_datetime(work["exit_ts"], unit="ns", utc=True).dt.year

    yearly_rows.append(
        {
            "timeframe": timeframe,
            "source_bar": source_bar,
            "exit_policy": exit_policy,
            "entry_exit_variant": entry_exit_variant,
            "variant": variant,
            "year": "overall",
            **metrics_all,
        }
    )
    for year, sub in work.groupby("year", sort=True):
        yearly_rows.append(
                {
                    "timeframe": timeframe,
                    "source_bar": source_bar,
                    "exit_policy": exit_policy,
                    "entry_exit_variant": entry_exit_variant,
                    "variant": variant,
                    "year": int(year),
                    **_metrics_with_risk(sub, risk_bps),
            }
        )

    for pair, sub_pair in work.groupby("pair", sort=True):
        pair_metrics = _metrics_with_risk(sub_pair, risk_bps)
        pair_rows.append(
            {
                "timeframe": timeframe,
                "source_bar": source_bar,
                "exit_policy": exit_policy,
                "entry_exit_variant": entry_exit_variant,
                "variant": variant,
                "pair": pair,
                **pair_metrics,
            }
        )
        pair_yearly_rows.append(
            {
                "timeframe": timeframe,
                "source_bar": source_bar,
                "exit_policy": exit_policy,
                "entry_exit_variant": entry_exit_variant,
                "variant": variant,
                "pair": pair,
                "year": "overall",
                **pair_metrics,
            }
        )
        for year, sub_pair_year in sub_pair.groupby("year", sort=True):
            pair_yearly_rows.append(
                {
                    "timeframe": timeframe,
                    "source_bar": source_bar,
                    "exit_policy": exit_policy,
                    "entry_exit_variant": entry_exit_variant,
                    "variant": variant,
                    "pair": pair,
                    "year": int(year),
                    **_metrics_with_risk(sub_pair_year, risk_bps),
                }
            )


def _build_universe(exclude_oil: bool) -> tuple[list[str], str, str]:
    if exclude_oil:
        wl = [p for p in PAIR_WHITELIST_BASE if p not in OIL_LINKED_PAIRS]
        return wl, "fx_commodities_no_oil_12", "strategy_fx_comm_no_oil"
    return list(PAIR_WHITELIST_BASE), "fx_commodities_14", "strategy_fx_comm"


def _load_meta_mixed_trades(path: Path, pair_whitelist: list[str]) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Missing meta trades file: {path}")
    df = pd.read_csv(path)
    if df.empty:
        return df
    need = {"variant", "pair", "timestamp", "exit_ts", "pnl_bps"}
    miss = sorted(need.difference(df.columns))
    if miss:
        raise ValueError(f"Meta trades missing required columns: {miss}")
    work = df.copy()
    if "mix_id" not in work.columns:
        work["mix_id"] = "default_mix"
    else:
        work["mix_id"] = work["mix_id"].astype(str)
    work["pair"] = work["pair"].astype(str)
    work = work[work["pair"].isin(pair_whitelist)].copy()
    work["timestamp"] = _normalize_ts_ns(work["timestamp"])
    work["exit_ts"] = _normalize_ts_ns(work["exit_ts"])
    work["pnl_bps"] = pd.to_numeric(work["pnl_bps"], errors="coerce")
    work = work.dropna(subset=["pair", "timestamp", "exit_ts", "pnl_bps", "variant", "mix_id"]).copy()
    return work.sort_values(["mix_id", "variant", "timestamp", "pair"]).reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build multi-timeframe strategy report for FX/commodities.")
    parser.add_argument(
        "--exclude-oil",
        action="store_true",
        help="exclude oil-linked pairs (Gold/Oil, Oil/Silver) and write *_no_oil outputs",
    )
    parser.add_argument(
        "--include-meta-mixed",
        action="store_true",
        help="append mixed meta variants from a precomputed OOS trades file",
    )
    parser.add_argument(
        "--meta-mixed-path",
        default="data/analysis/meta_tb_mixed_no_oil_oos_trades.csv",
        help="path to mixed meta OOS trades CSV (requires variant,pair,timestamp,exit_ts,pnl_bps)",
    )
    args = parser.parse_args()

    pair_whitelist, pair_universe_label, out_prefix = _build_universe(args.exclude_oil)

    out_dir = ROOT / "data" / "analysis"
    out_dir.mkdir(parents=True, exist_ok=True)

    overall_rows: list[dict] = []
    pair_rows: list[dict] = []
    yearly_rows: list[dict] = []
    pair_yearly_rows: list[dict] = []
    threshold_tables: list[pd.DataFrame] = []

    for cfg in TIMEFRAMES:
        frame = _load_tf_frame(cfg, pair_whitelist=pair_whitelist)
        grouped_frames = []
        if frame.empty:
            grouped_frames.append(("fixed", "baseline", frame.copy()))
        else:
            for (exit_policy, entry_exit_variant), sub_frame in frame.groupby(
                ["exit_policy", "entry_exit_variant"], sort=True
            ):
                grouped_frames.append((str(exit_policy), str(entry_exit_variant), sub_frame.copy()))

        for exit_policy, entry_exit_variant, sub_frame in grouped_frames:
            baseline = sub_frame.copy()
            guardrail = _apply_guardrail(baseline)
            risk_bps = _derive_risk_bps(baseline, fallback=100.0)
            best_thr, thr_table = _select_accel_threshold(
                baseline,
                guardrail,
                cfg.report_bar,
                exit_policy,
                entry_exit_variant,
                risk_bps,
            )
            threshold_tables.append(thr_table)

            pre_guard_accel = baseline if best_thr <= 0.0 else baseline[baseline["z_accel"].abs() > best_thr].copy()
            accel = _apply_guardrail(pre_guard_accel)
            guard_025 = _filter_pairs_by_sharpe(guardrail, cutoff=0.25)
            guard_030 = _filter_pairs_by_sharpe(guardrail, cutoff=0.30)
            accel_025 = _filter_pairs_by_sharpe(accel, cutoff=0.25)
            accel_030 = _filter_pairs_by_sharpe(accel, cutoff=0.30)

            variants = {
                "baseline": baseline,
                "baseline_guardrail": guardrail,
                "baseline_guardrail_acceleration": accel,
                "baseline_guardrail_sharpe025": guard_025,
                "baseline_guardrail_sharpe030": guard_030,
                "baseline_guardrail_acceleration_sharpe025": accel_025,
                "baseline_guardrail_acceleration_sharpe030": accel_030,
            }
            for variant, sub in variants.items():
                _append_rollups(
                    timeframe=cfg.report_bar,
                    source_bar=cfg.source_bar,
                    exit_policy=exit_policy,
                    entry_exit_variant=entry_exit_variant,
                    variant=variant,
                    df=sub,
                    overall_rows=overall_rows,
                    pair_rows=pair_rows,
                    yearly_rows=yearly_rows,
                    pair_yearly_rows=pair_yearly_rows,
                    risk_bps=risk_bps,
                    pair_universe_label=pair_universe_label,
                )

    if args.include_meta_mixed:
        meta_path = ROOT / args.meta_mixed_path
        meta = _load_meta_mixed_trades(meta_path, pair_whitelist=pair_whitelist)
        if meta.empty:
            print(f"Meta mixed file has no usable rows: {meta_path}")
        else:
            risk_bps_meta = _derive_risk_bps(meta, fallback=100.0)
            for (mix_id, variant), sub in meta.groupby(["mix_id", "variant"], sort=True):
                _append_rollups(
                    timeframe="mixed",
                    source_bar="mixed",
                    exit_policy="adaptive_entry_z",
                    entry_exit_variant="baseline",
                    variant=f"mixed_{mix_id}__{variant}",
                    df=sub.copy(),
                    overall_rows=overall_rows,
                    pair_rows=pair_rows,
                    yearly_rows=yearly_rows,
                    pair_yearly_rows=pair_yearly_rows,
                    risk_bps=risk_bps_meta,
                    pair_universe_label=pair_universe_label,
                )

    overall_df = pd.DataFrame(overall_rows).sort_values(
        ["timeframe", "exit_policy", "entry_exit_variant", "variant"]
    ).reset_index(drop=True)
    pair_df = pd.DataFrame(pair_rows).sort_values(
        ["timeframe", "exit_policy", "entry_exit_variant", "variant", "pair"]
    ).reset_index(drop=True)

    yearly_df = pd.DataFrame(yearly_rows)
    yearly_df["year_sort"] = yearly_df["year"].apply(lambda x: 9999 if x == "overall" else int(x))
    yearly_df = (
        yearly_df.sort_values(
            ["timeframe", "exit_policy", "entry_exit_variant", "variant", "year_sort"]
        )
        .drop(columns=["year_sort"])
        .reset_index(drop=True)
    )

    pair_yearly_df = pd.DataFrame(pair_yearly_rows)
    pair_yearly_df["year_sort"] = pair_yearly_df["year"].apply(lambda x: 9999 if x == "overall" else int(x))
    pair_yearly_df = (
        pair_yearly_df.sort_values(
            ["timeframe", "exit_policy", "entry_exit_variant", "variant", "pair", "year_sort"]
        )
        .drop(columns=["year_sort"])
        .reset_index(drop=True)
    )

    threshold_df = pd.concat(threshold_tables, ignore_index=True)
    threshold_df = threshold_df.sort_values(
        ["timeframe", "exit_policy", "entry_exit_variant", "threshold"]
    ).reset_index(drop=True)

    overall_name = f"{out_prefix}_overall.csv"
    pair_name = f"{out_prefix}_pair.csv"
    yearly_name = f"{out_prefix}_yearly.csv"
    pair_yearly_name = f"{out_prefix}_pair_yearly.csv"
    thresh_name = f"{out_prefix}_accel_thresholds.csv"

    overall_df.to_csv(out_dir / overall_name, index=False)
    pair_df.to_csv(out_dir / pair_name, index=False)
    yearly_df.to_csv(out_dir / yearly_name, index=False)
    pair_yearly_df.to_csv(out_dir / pair_yearly_name, index=False)
    threshold_df.to_csv(out_dir / thresh_name, index=False)

    print("Saved report outputs:")
    print(f"- data/analysis/{overall_name}")
    print(f"- data/analysis/{pair_name}")
    print(f"- data/analysis/{yearly_name}")
    print(f"- data/analysis/{pair_yearly_name}")
    print(f"- data/analysis/{thresh_name}")


if __name__ == "__main__":
    main()
