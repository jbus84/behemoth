#!/usr/bin/env python3
from __future__ import annotations

import argparse
import heapq
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.api.settings import settings
from services.api.validation import PIPELINE_PATHS, _metrics
from services.api.weights import load_weights
from behemoth.core.guardrail import apply_loss_streak_guardrail


@dataclass
class GuardrailState:
    loss_streak: int = 0
    pause_until: datetime | None = None


@dataclass
class AccountState:
    equity: float
    peak_equity: float
    day_start_date: datetime.date
    day_start_equity: float
    halted: bool = False
    halt_reason: str | None = None


def _to_utc(ts: pd.Series) -> pd.Series:
    dt = pd.to_datetime(ts, utc=True)
    return dt


def _compute_exit_ts(df: pd.DataFrame, bar_minutes: int) -> pd.Series:
    bar_ns = int(pd.Timedelta(minutes=bar_minutes).value)
    durations = df["duration_bars"].astype(int)
    timeout_adjust = (durations >= 500).astype(int)
    exit_ts = df["timestamp"].astype("int64") + ((durations - timeout_adjust) * bar_ns)
    return pd.to_datetime(exit_ts, utc=True)


def _init_account() -> AccountState:
    start_equity = float(settings.account_equity_start)
    today = datetime.now(timezone.utc).date()
    return AccountState(
        equity=start_equity,
        peak_equity=start_equity,
        day_start_date=today,
        day_start_equity=start_equity,
    )


def _apply_guardrail_on_close(
    state: GuardrailState,
    exit_ts: datetime,
    pnl_bps: float,
) -> GuardrailState:
    loss_threshold = float(settings.guardrail_loss_threshold)
    loss_streak_target = int(settings.guardrail_loss_streak)
    cooldown_days = int(settings.guardrail_cooldown_days)
    if pnl_bps > loss_threshold:
        state.loss_streak = 0
        state.pause_until = None
        return state
    state.loss_streak += 1
    if state.loss_streak >= loss_streak_target:
        state.pause_until = exit_ts + timedelta(days=cooldown_days)
        state.loss_streak = 0
    return state


def _risk_check(
    account: AccountState,
) -> tuple[bool, str | None]:
    if account.halted:
        return False, account.halt_reason or "risk_halted"
    return True, None


def _update_account_on_close(
    account: AccountState,
    pnl_bps: float,
    notional: float,
    exit_ts: datetime,
) -> AccountState:
    equity_before = account.equity
    exit_date = exit_ts.date()
    if account.day_start_date != exit_date:
        account.day_start_date = exit_date
        account.day_start_equity = equity_before
    pnl_usd = float(notional) * float(pnl_bps) / 10000.0
    account.equity = equity_before + pnl_usd
    account.peak_equity = max(account.peak_equity, account.equity)
    daily_loss_pct = (account.equity - account.day_start_equity) / account.day_start_equity
    dd_pct = (account.equity - account.peak_equity) / account.peak_equity
    if settings.max_daily_loss_pct:
        buffer = float(settings.max_daily_loss_buffer_pct or 0.0)
        limit = float(settings.max_daily_loss_pct)
        if daily_loss_pct <= -limit:
            account.halted = True
            account.halt_reason = f"max_daily_loss {daily_loss_pct:.4f}"
        elif buffer > 0 and daily_loss_pct <= -(limit - buffer):
            account.halted = True
            account.halt_reason = f"max_daily_loss_buffer {daily_loss_pct:.4f}"
    if settings.max_dd_pct:
        buffer = float(settings.max_dd_buffer_pct or 0.0)
        limit = float(settings.max_dd_pct)
        if dd_pct <= -limit:
            account.halted = True
            account.halt_reason = f"max_drawdown {dd_pct:.4f}"
        elif buffer > 0 and dd_pct <= -(limit - buffer):
            account.halted = True
            account.halt_reason = f"max_drawdown_buffer {dd_pct:.4f}"
    return account


def _simulate(
    path: Path,
    bar_minutes: int,
    strategy_id: str,
    enforce_risk: bool,
    guardrail: bool,
) -> dict[str, Any]:
    df = pd.read_csv(path)
    if df.empty:
        return {"bar": strategy_id, "trades": 0}
    df["timestamp"] = _to_utc(df["timestamp"])
    df["exit_ts"] = _compute_exit_ts(df, bar_minutes)
    df = df.sort_values("timestamp").copy()
    df["exit_ts_ns"] = df["exit_ts"].astype("int64")
    df["row_id"] = np.arange(len(df), dtype="int64")

    weights = load_weights(strategy_id)
    if not weights:
        weights = {}

    account = _init_account()
    open_heap: list[tuple[datetime, int, float, float, str]] = []
    counter = 0

    closed: list[dict[str, Any]] = []
    skipped_guardrail = 0
    skipped_risk = 0

    def close_ready(until: datetime) -> None:
        nonlocal account
        while open_heap and open_heap[0][0] <= until:
            exit_ts, _, notional, pnl_bps, pair = heapq.heappop(open_heap)
            account = _update_account_on_close(account, pnl_bps, notional, exit_ts)
            closed.append(
                {
                    "exit_ts": exit_ts,
                    "pnl_bps": pnl_bps,
                    "notional_usd": notional,
                }
            )

    # Apply guardrail by exit time to match baseline statistics.
    if guardrail:
        before = len(df)
        guard_df = df[["pair", "exit_ts_ns", "pnl_bps", "row_id"]].copy()
        guard_df = guard_df.rename(columns={"exit_ts_ns": "exit_ts"})
        kept = apply_loss_streak_guardrail(
            guard_df,
            loss_threshold=float(settings.guardrail_loss_threshold),
            loss_streak=int(settings.guardrail_loss_streak),
            cooldown_days=int(settings.guardrail_cooldown_days),
        )
        kept_ids = set(kept["row_id"].tolist()) if not kept.empty else set()
        df = df[df["row_id"].isin(kept_ids)]
        skipped_guardrail = before - len(df)

    for row in df.itertuples(index=False):
        entry_ts = row.timestamp.to_pydatetime()
        close_ready(entry_ts)
        pair = str(row.pair)
        equity = float(account.equity)
        weight_sum = float(sum(max(v, 0.0) for v in weights.values())) or 1.0
        weight = float(weights.get(pair, 1.0))
        target_notional = equity * (weight / weight_sum)
        if enforce_risk:
            ok, _reason = _risk_check(account)
            if not ok:
                skipped_risk += 1
                continue

        counter += 1
        heapq.heappush(
            open_heap,
            (row.exit_ts.to_pydatetime(), counter, float(target_notional), float(row.pnl_bps), pair),
        )
        open_exposure += float(target_notional)

    # Close any remaining open positions
    if open_heap:
        close_ready(open_heap[-1][0])

    if closed:
        pnl_df = pd.DataFrame(closed).sort_values("exit_ts")
        pnl_df["exit_ts"] = pd.to_datetime(pnl_df["exit_ts"], utc=True)
        pnl_df["pnl_usd"] = pnl_df["notional_usd"] * pnl_df["pnl_bps"] / 10000.0
        metrics = _metrics(pnl_df["pnl_bps"].to_numpy(), pnl_df["exit_ts"].astype("int64").to_numpy())
        equity_stats = _equity_stats(pnl_df)
    else:
        metrics = _metrics(np.array([]), np.array([]))
        equity_stats = {
            "start_equity": float(settings.account_equity_start),
            "end_equity": float(settings.account_equity_start),
            "total_pnl_usd": 0.0,
            "max_dd_usd": 0.0,
            "max_dd_pct": 0.0,
            "max_daily_dd_pct": 0.0,
            "cagr": 0.0,
        }

    return {
        "bar": strategy_id,
        "enforce_risk": enforce_risk,
        "guardrail": guardrail,
        "skipped_guardrail": skipped_guardrail,
        "skipped_risk": skipped_risk,
        "summary": metrics,
        "equity_stats": equity_stats,
    }


def _equity_stats(df: pd.DataFrame) -> dict[str, float]:
    if df.empty:
        return {
            "start_equity": float(settings.account_equity_start),
            "end_equity": float(settings.account_equity_start),
            "total_pnl_usd": 0.0,
            "max_dd_usd": 0.0,
            "max_dd_pct": 0.0,
            "max_daily_dd_pct": 0.0,
            "cagr": 0.0,
        }
    start_equity = float(settings.account_equity_start)
    equity = start_equity + df["pnl_usd"].cumsum()
    peak = equity.cummax()
    dd = equity - peak
    max_dd_usd = float(dd.min())
    max_dd_pct = float((dd / peak).min())
    daily = df.groupby(df["exit_ts"].dt.date)["pnl_usd"].sum()
    daily_equity = start_equity + daily.cumsum()
    daily_peak = daily_equity.cummax()
    daily_dd = daily_equity - daily_peak
    max_daily_dd_pct = float((daily_dd / daily_peak).min()) if not daily_dd.empty else 0.0
    start_date = df["exit_ts"].iloc[0].date()
    end_date = df["exit_ts"].iloc[-1].date()
    days = max((end_date - start_date).days, 0)
    cagr = (equity.iloc[-1] / start_equity) ** (365.25 / days) - 1.0 if days > 0 else 0.0
    return {
        "start_equity": start_equity,
        "end_equity": float(equity.iloc[-1]),
        "total_pnl_usd": float(df["pnl_usd"].sum()),
        "max_dd_usd": max_dd_usd,
        "max_dd_pct": max_dd_pct,
        "max_daily_dd_pct": max_daily_dd_pct,
        "cagr": float(cagr),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bars", default="m5,m15")
    parser.add_argument("--guardrail", action="store_true", default=True)
    parser.add_argument("--no-guardrail", dest="guardrail", action="store_false")
    parser.add_argument("--out", default="data/analysis/replay_risk_compare.csv")
    parser.add_argument("--json-out", default="data/analysis/replay_risk_compare.json")
    args = parser.parse_args()

    bars = [b.strip() for b in args.bars.split(",") if b.strip()]
    rows = []
    for bar in bars:
        path = Path(PIPELINE_PATHS[bar])
        bar_minutes = 5 if bar == "m5" else 15 if bar == "m15" else None
        if bar_minutes is None:
            raise SystemExit(f"Unknown bar: {bar}")
        for risk in (False, True):
            strategy_id = f"mom_{bar}"
            result = _simulate(path, bar_minutes, strategy_id, risk, args.guardrail)
            rows.append(
                {
                    "bar": bar,
                    "risk_enabled": risk,
                    "guardrail": args.guardrail,
                    "skipped_guardrail": result["skipped_guardrail"],
                    "skipped_risk": result["skipped_risk"],
                    **result["summary"],
                    **{f"equity_{k}": v for k, v in result["equity_stats"].items()},
                }
            )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(out_path, index=False)
    json_path = Path(args.json_out)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(rows, indent=2))
    print(f"Saved: {out_path}")
    print(f"Saved: {json_path}")


if __name__ == "__main__":
    main()
