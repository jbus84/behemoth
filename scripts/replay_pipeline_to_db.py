#!/usr/bin/env python3
from __future__ import annotations

import argparse
import heapq
import itertools
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import numpy as np
import redis
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.api.db import Base
from services.api.guardrail import is_trade_allowed, update_guardrail_on_close
from services.api.models import ActiveLeg, AccountState, GuardrailState, Position, PositionStatus, Side
from services.api.risk import (
    check_risk_on_create,
    compute_target_notional,
    get_or_create_account_state,
    update_account_on_close,
)
from services.api.settings import settings
from services.api.validation import PIPELINE_PATHS, _metrics


def _get_progress_redis() -> redis.Redis | None:
    url = os.getenv("REPLAY_REDIS_URL") or os.getenv("REDIS_URL")
    if not url:
        return None
    try:
        client = redis.Redis.from_url(url, decode_responses=True)
        client.ping()
        return client
    except redis.RedisError:
        return None


def _update_progress(client: redis.Redis | None, key: str, **payload: object) -> None:
    if client is None:
        return None
    data = {"updated_at": int(time.time()), **payload}
    try:
        client.hset(key, mapping={k: str(v) for k, v in data.items()})
        client.expire(key, 60 * 60)
    except redis.RedisError:
        return None


def _compute_exit_ts(df: pd.DataFrame, bar_minutes: int) -> pd.Series:
    bar_ns = int(pd.Timedelta(minutes=bar_minutes).value)
    durations = df["duration_bars"].astype(int)
    timeout_adjust = (durations >= 500).astype(int)
    return df["timestamp"].astype("int64") + ((durations - timeout_adjust) * bar_ns)


def _to_dt(ts_ns: int) -> datetime:
    return datetime.fromtimestamp(ts_ns / 1_000_000_000, tz=timezone.utc)


def _reset_state(session, strategy_id: str) -> None:
    session.query(Position).filter(Position.strategy_id == strategy_id).delete()
    session.query(GuardrailState).filter(GuardrailState.strategy_id == strategy_id).delete()
    session.query(AccountState).filter(AccountState.strategy_id == strategy_id).delete()
    session.commit()


def _close_position(session, pos: Position, exit_ts: datetime, pnl_bps: float, guardrail: bool) -> None:
    pos.status = PositionStatus.CLOSED
    pos.exit_ts = exit_ts
    pos.pnl_bps = pnl_bps
    pos.version += 1

    notional = pos.notional_usd if pos.notional_usd is not None else pos.size
    update_account_on_close(
        session,
        strategy_id=str(pos.strategy_id),
        pnl_bps=float(pnl_bps),
        notional=float(notional),
        exit_ts=exit_ts,
    )
    if guardrail and settings.guardrail_enabled:
        update_guardrail_on_close(
            session,
            strategy_id=str(pos.strategy_id),
            pair=str(pos.pair),
            exit_ts=exit_ts,
            pnl_bps=float(pnl_bps),
        )


def _load_positions(session, strategy_id: str) -> pd.DataFrame:
    df = pd.read_sql(
        "SELECT pnl_bps, exit_ts, notional_usd, size FROM positions "
        "WHERE strategy_id = ? AND pnl_bps IS NOT NULL AND exit_ts IS NOT NULL",
        session.connection(),
        params=[strategy_id],
    )
    if df.empty:
        return df
    df["exit_ts"] = pd.to_datetime(df["exit_ts"], utc=True)
    df["notional_usd"] = df["notional_usd"].fillna(df["size"]).astype(float)
    df["pnl_usd"] = df["notional_usd"] * df["pnl_bps"] / 10000.0
    return df.sort_values("exit_ts")


def _equity_stats(df: pd.DataFrame) -> dict:
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


def _monthly_metrics(df: pd.DataFrame) -> list[dict]:
    if df.empty:
        return []
    df = df.copy()
    df["month"] = df["exit_ts"].dt.to_period("M").astype(str)
    rows: list[dict] = []
    for month, sub in df.groupby("month"):
        metrics = _metrics(
            sub["pnl_bps"].to_numpy(),
            sub["exit_ts"].astype("int64").to_numpy(),
        )
        rows.append(
            {
                "month": month,
                **metrics,
                "total_pnl_usd": float(sub["pnl_usd"].sum()),
            }
        )
    return rows


def replay_bar(
    session,
    bar: str,
    strategy_id: str,
    guardrail: bool,
    enforce_risk: bool,
    commit_every: int,
    sleep_s: float,
    limit: int | None,
) -> dict:
    bar_minutes = 5 if bar == "m5" else 15
    path = Path(PIPELINE_PATHS[bar])
    if not path.exists():
        raise SystemExit(f"Missing pipeline file for {bar}: {path}")

    cols = ["pair", "timestamp", "duration_bars", "pnl_bps", "side", "active_leg"]
    open_heap: list[tuple[int, int, Position, float]] = []
    tie_breaker = itertools.count()
    processed = 0
    skipped_guardrail = 0
    skipped_risk = 0
    opened = 0
    closed = 0
    started_at = time.time()
    progress_key = f"replay:progress:{bar}"
    progress_client = _get_progress_redis()

    for chunk in pd.read_csv(path, usecols=cols, chunksize=50000):
        chunk = chunk.copy()
        chunk["exit_ts"] = _compute_exit_ts(chunk, bar_minutes)

        for row in chunk.itertuples(index=False):
            if limit and processed >= limit:
                break
            processed += 1

            entry_ts_ns = int(row.timestamp)
            exit_ts_ns = int(row.exit_ts)

            while open_heap and open_heap[0][0] <= entry_ts_ns:
                _, _, pos, pnl_bps = heapq.heappop(open_heap)
                exit_dt = pos.exit_ts if pos.exit_ts is not None else _to_dt(entry_ts_ns)
                _close_position(session, pos, exit_dt, pnl_bps, guardrail)
                closed += 1

            entry_dt = _to_dt(entry_ts_ns)
            if guardrail and settings.guardrail_enabled:
                allowed, _, _ = is_trade_allowed(session, strategy_id, row.pair, entry_dt)
                if not allowed:
                    skipped_guardrail += 1
                    continue

            state = get_or_create_account_state(session, strategy_id)
            equity = float(state.equity)
            notional = compute_target_notional(strategy_id, row.pair, equity)
            alloc_frac = notional / equity if equity else 0.0

            if enforce_risk:
                risk_ok, _ = check_risk_on_create(session, strategy_id, row.pair, float(notional))
                if not risk_ok:
                    skipped_risk += 1
                    continue

            pos = Position(
                strategy_id=strategy_id,
                pair=row.pair,
                side=Side(row.side),
                active_leg=ActiveLeg(row.active_leg),
                status=PositionStatus.OPEN,
                size=float(notional),
                notional_usd=float(notional),
                alloc_frac=float(alloc_frac),
                entry_equity=float(equity),
                entry_ts=entry_dt,
            )
            session.add(pos)
            session.flush()
            opened += 1

            pos.exit_ts = _to_dt(exit_ts_ns)
            heapq.heappush(open_heap, (exit_ts_ns, next(tie_breaker), pos, float(row.pnl_bps)))

            if commit_every and processed % commit_every == 0:
                session.commit()
                if sleep_s:
                    time.sleep(sleep_s)
                elapsed = max(time.time() - started_at, 1e-6)
                rate = processed / elapsed
                print(
                    f"[{bar}] processed={processed} opened={opened} closed={closed} "
                    f"skipped_guardrail={skipped_guardrail} skipped_risk={skipped_risk} "
                    f"rate={rate:.1f}/s"
                )
                _update_progress(
                    progress_client,
                    progress_key,
                    processed=processed,
                    opened=opened,
                    closed=closed,
                    skipped_guardrail=skipped_guardrail,
                    skipped_risk=skipped_risk,
                    done=False,
                )

        if limit and processed >= limit:
            break

    while open_heap:
        _, _, pos, pnl_bps = heapq.heappop(open_heap)
        _close_position(session, pos, pos.exit_ts, pnl_bps, guardrail)
        closed += 1

    session.commit()
    _update_progress(
        progress_client,
        progress_key,
        processed=processed,
        opened=opened,
        closed=closed,
        skipped_guardrail=skipped_guardrail,
        skipped_risk=skipped_risk,
        done=True,
    )

    metrics = {"trades": 0, "mean_pnl": 0.0, "total_pnl": 0.0, "max_dd": 0.0}
    equity_stats = {
        "start_equity": float(settings.account_equity_start),
        "end_equity": float(settings.account_equity_start),
        "total_pnl_usd": 0.0,
        "max_dd_usd": 0.0,
        "max_dd_pct": 0.0,
        "max_daily_dd_pct": 0.0,
        "cagr": 0.0,
    }
    monthly = []
    try:
        pnl_df = _load_positions(session, strategy_id)
        if not pnl_df.empty:
            metrics = _metrics(
                pnl_df["pnl_bps"].to_numpy(),
                pnl_df["exit_ts"].astype("int64").to_numpy(),
            )
            equity_stats = _equity_stats(pnl_df)
            monthly = _monthly_metrics(pnl_df)
    except Exception:
        pass

    return {
        "bar": bar,
        "strategy_id": strategy_id,
        "processed": processed,
        "opened": opened,
        "closed": closed,
        "skipped_guardrail": skipped_guardrail,
        "skipped_risk": skipped_risk,
        "summary": metrics,
        "equity_stats": equity_stats,
        "monthly": monthly,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bars", default="m5,m15", help="comma separated: m5,m15")
    parser.add_argument("--strategy-prefix", default="mom", help="strategy id prefix")
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"))
    parser.add_argument("--guardrail", action="store_true", default=True)
    parser.add_argument("--no-guardrail", dest="guardrail", action="store_false")
    parser.add_argument("--enforce-risk", action="store_true", default=True)
    parser.add_argument("--no-enforce-risk", dest="enforce_risk", action="store_false")
    parser.add_argument("--reset", action="store_true", help="clear positions/guardrail/account for strategy")
    parser.add_argument("--commit-every", type=int, default=5000)
    parser.add_argument("--sleep", type=float, default=0.0, help="sleep seconds between commits")
    parser.add_argument("--limit", type=int, default=None, help="limit trades for quick run")
    parser.add_argument("--report", default="data/analysis/replay_report.json", help="write report JSON")
    args = parser.parse_args()

    if not args.database_url:
        raise SystemExit("DATABASE_URL is required")

    engine = create_engine(args.database_url)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)

    bars = [b.strip() for b in args.bars.split(",") if b.strip()]
    report = []
    with Session() as session:
        for bar in bars:
            strategy_id = f"{args.strategy_prefix}_{bar}"
            if args.reset:
                _reset_state(session, strategy_id)
            result = replay_bar(
                session,
                bar,
                strategy_id,
                guardrail=args.guardrail,
                enforce_risk=args.enforce_risk,
                commit_every=args.commit_every,
                sleep_s=args.sleep,
                limit=args.limit,
            )
            report.append(result)
            print(result)

    out_path = Path(args.report)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2))
    print(f"Saved report: {out_path}")


if __name__ == "__main__":
    main()
