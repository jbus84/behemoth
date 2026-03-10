#!/usr/bin/env python3
"""Reconcile FTMO risk reservations against allocator events and trade ledger."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd


def _table(df: pd.DataFrame) -> str:
    if df.empty:
        return "_empty_"
    try:
        return df.to_markdown(index=False)
    except Exception:
        return "```\n" + df.to_string(index=False) + "\n```"


def _parse_symbols(raw: str) -> list[str]:
    out = [x.strip().upper() for x in str(raw).split(",") if x.strip()]
    return sorted(list(dict.fromkeys(out)))


def _to_num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def _dt_utc(s: pd.Series) -> pd.Series:
    try:
        return pd.to_datetime(s, utc=True, errors="coerce", format="mixed")
    except TypeError:
        return pd.to_datetime(s, utc=True, errors="coerce")


def _safe_query(con: duckdb.DuckDBPyConnection | None, sql: str, params: list[Any]) -> pd.DataFrame:
    if con is None:
        return pd.DataFrame()
    try:
        return con.execute(sql, params).fetchdf()
    except Exception:
        return pd.DataFrame()


def _table_exists(con: duckdb.DuckDBPyConnection | None, table_name: str) -> bool:
    if con is None:
        return False
    try:
        row = con.execute(
            """
            SELECT 1
            FROM information_schema.tables
            WHERE lower(table_name) = lower(?)
            LIMIT 1
            """,
            [table_name],
        ).fetchone()
        return bool(row)
    except Exception:
        return False


def run(
    *,
    symbols: list[str],
    runtime_db_path: Path,
    event_lookback_days: int,
    stale_pending_hours: float,
    stale_open_hours: float,
    out_csv: Path,
    report_out: Path,
) -> pd.DataFrame:
    now_utc = datetime.now(timezone.utc)
    evaluated_at_utc = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    cutoff_utc = now_utc - timedelta(days=max(1, int(event_lookback_days)))

    con: duckdb.DuckDBPyConnection | None = None
    if runtime_db_path.exists():
        try:
            con = duckdb.connect(str(runtime_db_path), read_only=True)
        except Exception:
            con = None

    try:
        reservations = (
            _safe_query(
                con,
                """
                SELECT reservation_id, created_ts, updated_ts, symbol, candidate_uid, broker_pos_id,
                       status, reserved_loss_ccy
                FROM ftmo_risk_reservations
                """,
                [],
            )
            if _table_exists(con, "ftmo_risk_reservations")
            else pd.DataFrame()
        )
        events = (
            _safe_query(
                con,
                """
                SELECT event_ts, symbol, status, block_reason, reservation_id
                FROM ftmo_allocator_events
                WHERE event_ts >= ?
                """,
                [cutoff_utc],
            )
            if _table_exists(con, "ftmo_allocator_events")
            else pd.DataFrame()
        )
        trades = (
            _safe_query(
                con,
                """
                SELECT broker_pos_id, symbol, status
                FROM trades
                """,
                [],
            )
            if _table_exists(con, "trades")
            else pd.DataFrame()
        )
    finally:
        if con is not None:
            con.close()

    if not reservations.empty:
        reservations["symbol"] = reservations.get("symbol", pd.Series(dtype=str)).astype(str).str.upper()
        reservations["reservation_id"] = reservations.get("reservation_id", pd.Series(dtype=str)).astype(str)
        reservations["status"] = reservations.get("status", pd.Series(dtype=str)).astype(str).str.upper()
        reservations["broker_pos_id"] = reservations.get("broker_pos_id", pd.Series(dtype=str)).astype(str)
        reservations["created_ts"] = _dt_utc(reservations.get("created_ts", pd.Series(dtype=object)))
        reservations["updated_ts"] = _dt_utc(reservations.get("updated_ts", pd.Series(dtype=object)))
        reservations["reserved_loss_ccy"] = _to_num(
            reservations.get("reserved_loss_ccy", pd.Series(dtype=float))
        ).fillna(0.0)

    if not events.empty:
        events["symbol"] = events.get("symbol", pd.Series(dtype=str)).astype(str).str.upper()
        events["status"] = events.get("status", pd.Series(dtype=str)).astype(str).str.upper()
        events["block_reason"] = events.get("block_reason", pd.Series(dtype=str)).astype(str)
        events["reservation_id"] = events.get("reservation_id", pd.Series(dtype=str)).astype(str)
        events["event_ts"] = _dt_utc(events.get("event_ts", pd.Series(dtype=object)))

    if not trades.empty:
        trades["symbol"] = trades.get("symbol", pd.Series(dtype=str)).astype(str).str.upper()
        trades["broker_pos_id"] = trades.get("broker_pos_id", pd.Series(dtype=str)).astype(str)
        trades["status"] = trades.get("status", pd.Series(dtype=str)).astype(str).str.upper()

    rows: list[dict[str, Any]] = []
    for sym in symbols:
        rr = (
            reservations[reservations.get("symbol", pd.Series(dtype=str)).astype(str) == sym].copy()
            if not reservations.empty
            else pd.DataFrame()
        )
        ev = (
            events[events.get("symbol", pd.Series(dtype=str)).astype(str) == sym].copy()
            if not events.empty
            else pd.DataFrame()
        )
        tr = (
            trades[trades.get("symbol", pd.Series(dtype=str)).astype(str) == sym].copy()
            if not trades.empty
            else pd.DataFrame()
        )

        reservations_total = int(len(rr))
        pending_count = int((rr.get("status", pd.Series(dtype=str)).astype(str) == "PENDING").sum()) if not rr.empty else 0
        open_count = int((rr.get("status", pd.Series(dtype=str)).astype(str) == "OPEN").sum()) if not rr.empty else 0
        released_count = int((rr.get("status", pd.Series(dtype=str)).astype(str) == "RELEASED").sum()) if not rr.empty else 0
        expired_count = int((rr.get("status", pd.Series(dtype=str)).astype(str) == "EXPIRED").sum()) if not rr.empty else 0
        active_reserved = float(
            rr[rr.get("status", pd.Series(dtype=str)).astype(str).isin(["PENDING", "OPEN"])]
            .get("reserved_loss_ccy", pd.Series(dtype=float))
            .sum()
        ) if not rr.empty else 0.0

        admitted_events = int((ev.get("status", pd.Series(dtype=str)).astype(str) == "ADMITTED").sum()) if not ev.empty else 0
        blocked_events = int((ev.get("status", pd.Series(dtype=str)).astype(str) == "BLOCKED").sum()) if not ev.empty else 0

        admitted_missing_reservation_id_count = int(
            (
                (ev.get("status", pd.Series(dtype=str)).astype(str) == "ADMITTED")
                & ev.get("reservation_id", pd.Series(dtype=str)).astype(str).str.strip().isin(
                    {"", "None", "nan"}
                )
            ).sum()
        ) if not ev.empty else 0

        known_reservation_ids = (
            set(rr.get("reservation_id", pd.Series(dtype=str)).astype(str).tolist())
            if not rr.empty
            else set()
        )
        admitted_unknown_reservation_id_count = int(
            (
                (ev.get("status", pd.Series(dtype=str)).astype(str) == "ADMITTED")
                & (~ev.get("reservation_id", pd.Series(dtype=str)).astype(str).str.strip().isin({"", "None", "nan"}))
                & (~ev.get("reservation_id", pd.Series(dtype=str)).astype(str).isin(known_reservation_ids))
            ).sum()
        ) if not ev.empty else 0

        stale_pending_count = 0
        if not rr.empty:
            pend = rr[rr.get("status", pd.Series(dtype=str)).astype(str) == "PENDING"].copy()
            if not pend.empty:
                age_h = (
                    (now_utc - _dt_utc(pend.get("created_ts", pd.Series(dtype=object))))
                    .dt.total_seconds()
                    / 3600.0
                )
                stale_pending_count = int((age_h.isna() | (age_h > float(stale_pending_hours))).sum())

        stale_open_count = 0
        if not rr.empty:
            opn = rr[rr.get("status", pd.Series(dtype=str)).astype(str) == "OPEN"].copy()
            if not opn.empty:
                age_h_open = (
                    (now_utc - _dt_utc(opn.get("updated_ts", pd.Series(dtype=object))))
                    .dt.total_seconds()
                    / 3600.0
                )
                stale_open_count = int((age_h_open.isna() | (age_h_open > float(stale_open_hours))).sum())

        open_without_broker_pos_count = int(
            (
                (rr.get("status", pd.Series(dtype=str)).astype(str) == "OPEN")
                & (rr.get("broker_pos_id", pd.Series(dtype=str)).astype(str).str.strip() == "")
            ).sum()
        ) if not rr.empty else 0

        trade_ids = set(
            tr.get("broker_pos_id", pd.Series(dtype=str)).astype(str).str.strip().tolist()
        ) if not tr.empty else set()
        open_with_broker = rr[
            (rr.get("status", pd.Series(dtype=str)).astype(str) == "OPEN")
            & (rr.get("broker_pos_id", pd.Series(dtype=str)).astype(str).str.strip() != "")
        ].copy() if not rr.empty else pd.DataFrame()
        open_missing_trade_count = int(
            (~open_with_broker.get("broker_pos_id", pd.Series(dtype=str)).astype(str).isin(trade_ids)).sum()
        ) if not open_with_broker.empty else 0

        reconciliation_pass = bool(
            admitted_missing_reservation_id_count == 0
            and admitted_unknown_reservation_id_count == 0
            and open_without_broker_pos_count == 0
            and open_missing_trade_count == 0
            and stale_pending_count == 0
        )

        rows.append(
            {
                "symbol": sym,
                "reservations_total": reservations_total,
                "pending_count": pending_count,
                "open_count": open_count,
                "released_count": released_count,
                "expired_count": expired_count,
                "active_reserved_loss_ccy": active_reserved,
                "admitted_events": admitted_events,
                "blocked_events": blocked_events,
                "admitted_missing_reservation_id_count": admitted_missing_reservation_id_count,
                "admitted_unknown_reservation_id_count": admitted_unknown_reservation_id_count,
                "stale_pending_count": stale_pending_count,
                "stale_open_count": stale_open_count,
                "open_without_broker_pos_count": open_without_broker_pos_count,
                "open_missing_trade_count": open_missing_trade_count,
                "reconciliation_pass": reconciliation_pass,
                "source_db_path": str(runtime_db_path),
                "evaluated_at_utc": evaluated_at_utc,
            }
        )

    out = pd.DataFrame(rows)
    if out.empty:
        out = pd.DataFrame(
            columns=[
                "symbol",
                "reservations_total",
                "pending_count",
                "open_count",
                "released_count",
                "expired_count",
                "active_reserved_loss_ccy",
                "admitted_events",
                "blocked_events",
                "admitted_missing_reservation_id_count",
                "admitted_unknown_reservation_id_count",
                "stale_pending_count",
                "stale_open_count",
                "open_without_broker_pos_count",
                "open_missing_trade_count",
                "reconciliation_pass",
                "source_db_path",
                "evaluated_at_utc",
            ]
        )

    if not out.empty:
        all_row = {
            "symbol": "ALL",
            "reservations_total": int(_to_num(out["reservations_total"]).sum()),
            "pending_count": int(_to_num(out["pending_count"]).sum()),
            "open_count": int(_to_num(out["open_count"]).sum()),
            "released_count": int(_to_num(out["released_count"]).sum()),
            "expired_count": int(_to_num(out["expired_count"]).sum()),
            "active_reserved_loss_ccy": float(_to_num(out["active_reserved_loss_ccy"]).sum()),
            "admitted_events": int(_to_num(out["admitted_events"]).sum()),
            "blocked_events": int(_to_num(out["blocked_events"]).sum()),
            "admitted_missing_reservation_id_count": int(
                _to_num(out["admitted_missing_reservation_id_count"]).sum()
            ),
            "admitted_unknown_reservation_id_count": int(
                _to_num(out["admitted_unknown_reservation_id_count"]).sum()
            ),
            "stale_pending_count": int(_to_num(out["stale_pending_count"]).sum()),
            "stale_open_count": int(_to_num(out["stale_open_count"]).sum()),
            "open_without_broker_pos_count": int(_to_num(out["open_without_broker_pos_count"]).sum()),
            "open_missing_trade_count": int(_to_num(out["open_missing_trade_count"]).sum()),
            "reconciliation_pass": bool(out["reconciliation_pass"].astype(bool).all()),
            "source_db_path": str(runtime_db_path),
            "evaluated_at_utc": evaluated_at_utc,
        }
        out = pd.concat([out, pd.DataFrame([all_row])], ignore_index=True)

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    report_out.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(out_csv, index=False)

    failed = out[
        (out.get("symbol", pd.Series(dtype=str)).astype(str) != "ALL")
        & (~out.get("reconciliation_pass", pd.Series(dtype=bool)).astype(bool))
    ].copy()
    core_cols = [
        "symbol",
        "pending_count",
        "open_count",
        "admitted_events",
        "blocked_events",
        "stale_pending_count",
        "open_without_broker_pos_count",
        "open_missing_trade_count",
        "admitted_missing_reservation_id_count",
        "admitted_unknown_reservation_id_count",
        "reconciliation_pass",
    ]
    lines: list[str] = []
    lines.append("# FTMO Risk Reservation Reconciliation Report")
    lines.append("")
    lines.append(f"- generated_at_utc: `{evaluated_at_utc}`")
    lines.append(f"- runtime_db_path: `{runtime_db_path}`")
    lines.append(f"- event_lookback_days: `{int(max(1, event_lookback_days))}`")
    lines.append(f"- stale_pending_hours: `{float(stale_pending_hours)}`")
    lines.append(f"- stale_open_hours: `{float(stale_open_hours)}`")
    lines.append(f"- reconciliation_csv: `{out_csv}`")
    lines.append("")
    lines.append("## Failed Symbols")
    lines.append(_table(failed[core_cols] if not failed.empty else failed))
    lines.append("")
    lines.append("## Full Reconciliation")
    lines.append(_table(out[core_cols + ["active_reserved_loss_ccy"]]))
    report_out.write_text("\n".join(lines), encoding="utf-8")
    return out


def main() -> None:
    p = argparse.ArgumentParser(description="Reconcile FTMO reservations against runtime state")
    p.add_argument("--symbols", default="EURUSD,GBPUSD,USDJPY,USDCHF,AUDUSD,USDCAD")
    p.add_argument("--runtime-db-path", default="data/db/behemoth_runtime.db")
    p.add_argument("--event-lookback-days", type=int, default=30)
    p.add_argument("--stale-pending-hours", type=float, default=6.0)
    p.add_argument("--stale-open-hours", type=float, default=72.0)
    p.add_argument(
        "--out-csv",
        default="data/analysis/tick_opportunity_mining/ftmo_reservation_reconciliation.csv",
    )
    p.add_argument("--report-out", default="docs/analysis/oco_ftmo_risk_reconciliation_report.md")
    args = p.parse_args()

    out = run(
        symbols=_parse_symbols(args.symbols),
        runtime_db_path=Path(str(args.runtime_db_path)),
        event_lookback_days=int(max(1, args.event_lookback_days)),
        stale_pending_hours=float(args.stale_pending_hours),
        stale_open_hours=float(args.stale_open_hours),
        out_csv=Path(str(args.out_csv)),
        report_out=Path(str(args.report_out)),
    )
    print(f"wrote reconciliation: {args.out_csv} rows={len(out)}")


if __name__ == "__main__":
    main()
