#!/usr/bin/env python3
"""Build FTMO allocator monitoring metrics, alerts, and markdown report."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd

METRIC_SPECS: list[dict[str, Any]] = [
    {"metric_id": "FTMO_ALLOC_BLOCK_RATE", "warn": 0.35, "fail": 0.55, "mode": "ge"},
    {"metric_id": "FTMO_ALLOC_BUDGET_EXCEEDED_RATE", "warn": 0.15, "fail": 0.30, "mode": "ge"},
    {"metric_id": "FTMO_ALLOC_PIP_VALUE_UNAVAILABLE_RATE", "warn": 0.005, "fail": 0.02, "mode": "ge"},
    {"metric_id": "FTMO_ALLOC_STALE_PENDING_COUNT", "warn": 1.0, "fail": 3.0, "mode": "ge"},
    {"metric_id": "FTMO_ALLOC_OPEN_WITHOUT_BROKER_POS_COUNT", "warn": 1.0, "fail": 2.0, "mode": "ge"},
    {
        "metric_id": "FTMO_ALLOC_ADMITTED_MISSING_RESERVATION_ID_COUNT",
        "warn": 1.0,
        "fail": 2.0,
        "mode": "ge",
    },
]


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


def _band(value: float, *, warn: float, fail: float, mode: str) -> tuple[str, str]:
    if not np.isfinite(value):
        return "gray", "high"
    v = float(value)
    if mode == "ge":
        if v >= float(fail):
            return "red", "high"
        if v >= float(warn):
            return "amber", "medium"
        return "green", "info"
    if mode == "gt":
        if v > float(fail):
            return "red", "high"
        if v > float(warn):
            return "amber", "medium"
        return "green", "info"
    if mode == "le":
        if v <= float(fail):
            return "red", "high"
        if v <= float(warn):
            return "amber", "medium"
        return "green", "info"
    if mode == "lt":
        if v < float(fail):
            return "red", "high"
        if v < float(warn):
            return "amber", "medium"
        return "green", "info"
    return "gray", "high"


def run(
    *,
    symbols: list[str],
    runtime_db_path: Path,
    lookback_days: int,
    stale_pending_hours: float,
    stale_open_hours: float,
    out_metrics_csv: Path,
    out_alerts_csv: Path,
    report_out: Path,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    now_utc = datetime.now(timezone.utc)
    cutoff_utc = now_utc - timedelta(days=max(1, int(lookback_days)))
    evaluated_at_utc = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    test_month = now_utc.strftime("%Y-%m")

    con: duckdb.DuckDBPyConnection | None = None
    if runtime_db_path.exists():
        try:
            con = duckdb.connect(str(runtime_db_path), read_only=True)
        except Exception:
            con = None

    try:
        events = (
            _safe_query(
                con,
                """
                SELECT event_ts, symbol, status, block_reason, reserved_loss_ccy, reservation_id
                FROM ftmo_allocator_events
                WHERE event_ts >= ?
                """,
                [cutoff_utc],
            )
            if _table_exists(con, "ftmo_allocator_events")
            else pd.DataFrame()
        )
        reservations = (
            _safe_query(
                con,
                """
                SELECT reservation_id, created_ts, updated_ts, symbol, broker_pos_id, status, reserved_loss_ccy
                FROM ftmo_risk_reservations
                """,
                [],
            )
            if _table_exists(con, "ftmo_risk_reservations")
            else pd.DataFrame()
        )
    finally:
        if con is not None:
            con.close()

    if not events.empty:
        events["symbol"] = events.get("symbol", pd.Series(dtype=str)).astype(str).str.upper()
        events["status"] = events.get("status", pd.Series(dtype=str)).astype(str).str.upper()
        events["block_reason"] = events.get("block_reason", pd.Series(dtype=str)).astype(str)
        events["reservation_id"] = events.get("reservation_id", pd.Series(dtype=str)).astype(str)
        events["event_ts"] = _dt_utc(events.get("event_ts", pd.Series(dtype=object)))
        events["reserved_loss_ccy"] = _to_num(events.get("reserved_loss_ccy", pd.Series(dtype=float)))
        events = events[events["symbol"].astype(str).str.strip() != ""].copy()

    if not reservations.empty:
        reservations["symbol"] = reservations.get("symbol", pd.Series(dtype=str)).astype(str).str.upper()
        reservations["status"] = reservations.get("status", pd.Series(dtype=str)).astype(str).str.upper()
        reservations["reservation_id"] = reservations.get("reservation_id", pd.Series(dtype=str)).astype(str)
        reservations["broker_pos_id"] = reservations.get("broker_pos_id", pd.Series(dtype=str)).astype(str)
        reservations["created_ts"] = _dt_utc(reservations.get("created_ts", pd.Series(dtype=object)))
        reservations["updated_ts"] = _dt_utc(reservations.get("updated_ts", pd.Series(dtype=object)))
        reservations["reserved_loss_ccy"] = _to_num(
            reservations.get("reserved_loss_ccy", pd.Series(dtype=float))
        )
        reservations = reservations[reservations["symbol"].astype(str).str.strip() != ""].copy()

    metric_rows: list[dict[str, Any]] = []
    alert_rows: list[dict[str, Any]] = []

    for sym in symbols:
        ev = (
            events[events.get("symbol", pd.Series(dtype=str)).astype(str) == sym].copy()
            if not events.empty
            else pd.DataFrame()
        )
        rr = (
            reservations[reservations.get("symbol", pd.Series(dtype=str)).astype(str) == sym].copy()
            if not reservations.empty
            else pd.DataFrame()
        )
        preselected_total = int(len(ev))
        admitted = int((ev.get("status", pd.Series(dtype=str)).astype(str) == "ADMITTED").sum()) if not ev.empty else 0
        blocked = int((ev.get("status", pd.Series(dtype=str)).astype(str) == "BLOCKED").sum()) if not ev.empty else 0
        block_budget = int(
            (
                (ev.get("status", pd.Series(dtype=str)).astype(str) == "BLOCKED")
                & (ev.get("block_reason", pd.Series(dtype=str)).astype(str) == "FTMO_RESERVED_BUDGET_EXCEEDED")
            ).sum()
        ) if not ev.empty else 0
        block_pip_unavailable = int(
            (
                (ev.get("status", pd.Series(dtype=str)).astype(str) == "BLOCKED")
                & (ev.get("block_reason", pd.Series(dtype=str)).astype(str) == "FTMO_PIP_VALUE_UNAVAILABLE")
            ).sum()
        ) if not ev.empty else 0
        admitted_missing_reservation_id = int(
            (
                (ev.get("status", pd.Series(dtype=str)).astype(str) == "ADMITTED")
                & (
                    ev.get("reservation_id", pd.Series(dtype=str)).astype(str).str.strip().isin({"", "None", "nan"})
                )
            ).sum()
        ) if not ev.empty else 0

        open_without_broker = int(
            (
                (rr.get("status", pd.Series(dtype=str)).astype(str) == "OPEN")
                & (rr.get("broker_pos_id", pd.Series(dtype=str)).astype(str).str.strip() == "")
            ).sum()
        ) if not rr.empty else 0

        stale_pending = 0
        if not rr.empty:
            pend = rr[rr.get("status", pd.Series(dtype=str)).astype(str) == "PENDING"].copy()
            if not pend.empty:
                age_h = (
                    (now_utc - _dt_utc(pend.get("created_ts", pd.Series(dtype=object))))
                    .dt.total_seconds()
                    / 3600.0
                )
                stale_pending = int((age_h.isna() | (age_h > float(stale_pending_hours))).sum())

        stale_open = 0
        if not rr.empty:
            opn = rr[rr.get("status", pd.Series(dtype=str)).astype(str) == "OPEN"].copy()
            if not opn.empty:
                age_h_open = (
                    (now_utc - _dt_utc(opn.get("updated_ts", pd.Series(dtype=object))))
                    .dt.total_seconds()
                    / 3600.0
                )
                stale_open = int((age_h_open.isna() | (age_h_open > float(stale_open_hours))).sum())

        known_reservation_ids = set(rr.get("reservation_id", pd.Series(dtype=str)).astype(str).tolist()) if not rr.empty else set()
        admitted_unknown_reservation_id = int(
            (
                (ev.get("status", pd.Series(dtype=str)).astype(str) == "ADMITTED")
                & (~ev.get("reservation_id", pd.Series(dtype=str)).astype(str).str.strip().isin({"", "None", "nan"}))
                & (~ev.get("reservation_id", pd.Series(dtype=str)).astype(str).isin(known_reservation_ids))
            ).sum()
        ) if not ev.empty else 0

        denom = float(max(1, preselected_total))
        metric_values = {
            "FTMO_ALLOC_BLOCK_RATE": float(blocked) / denom,
            "FTMO_ALLOC_BUDGET_EXCEEDED_RATE": float(block_budget) / denom,
            "FTMO_ALLOC_PIP_VALUE_UNAVAILABLE_RATE": float(block_pip_unavailable) / denom,
            "FTMO_ALLOC_STALE_PENDING_COUNT": float(stale_pending),
            "FTMO_ALLOC_OPEN_WITHOUT_BROKER_POS_COUNT": float(open_without_broker),
            "FTMO_ALLOC_ADMITTED_MISSING_RESERVATION_ID_COUNT": float(
                admitted_missing_reservation_id + admitted_unknown_reservation_id
            ),
            "FTMO_ALLOC_EVENT_ROWS_LOOKBACK": float(preselected_total),
            "FTMO_ALLOC_ADMITTED_ROWS_LOOKBACK": float(admitted),
            "FTMO_ALLOC_BLOCKED_ROWS_LOOKBACK": float(blocked),
            "FTMO_ALLOC_STALE_OPEN_COUNT": float(stale_open),
        }

        for metric_id, metric_value in metric_values.items():
            metric_rows.append(
                {
                    "stage_id": 10,
                    "symbol": sym,
                    "metric_id": metric_id,
                    "metric_value": float(metric_value),
                    "source_path": str(runtime_db_path),
                    "evaluated_at_utc": evaluated_at_utc,
                }
            )

        for spec in METRIC_SPECS:
            metric_id = str(spec["metric_id"])
            metric_value = float(metric_values.get(metric_id, np.nan))
            warn = float(spec["warn"])
            fail = float(spec["fail"])
            band, sev = _band(metric_value, warn=warn, fail=fail, mode=str(spec["mode"]))
            alert_rows.append(
                {
                    "source_alert": "ftmo_allocator",
                    "symbol": sym,
                    "test_month": test_month,
                    "metric_id": metric_id,
                    "metric_value": metric_value,
                    "warn_threshold": warn,
                    "fail_threshold": fail,
                    "band": band,
                    "severity": sev,
                    "source_path": str(runtime_db_path),
                    "details_json": json.dumps(
                        {
                            "lookback_days": int(max(1, lookback_days)),
                            "stale_pending_hours": float(stale_pending_hours),
                            "stale_open_hours": float(stale_open_hours),
                            "preselected_total": int(preselected_total),
                            "admitted": int(admitted),
                            "blocked": int(blocked),
                        },
                        sort_keys=True,
                    ),
                    "evaluated_at_utc": evaluated_at_utc,
                }
            )

    metrics_df = pd.DataFrame(metric_rows)
    alerts_df = pd.DataFrame(alert_rows)

    out_metrics_csv.parent.mkdir(parents=True, exist_ok=True)
    out_alerts_csv.parent.mkdir(parents=True, exist_ok=True)
    report_out.parent.mkdir(parents=True, exist_ok=True)
    metrics_df.to_csv(out_metrics_csv, index=False)
    alerts_df.to_csv(out_alerts_csv, index=False)

    alert_summary = (
        alerts_df.groupby(["symbol", "band"], as_index=False)
        .agg(rows=("metric_id", "count"))
        .sort_values(["symbol", "band"])
        if not alerts_df.empty
        else pd.DataFrame(columns=["symbol", "band", "rows"])
    )

    latest_snapshot = (
        metrics_df[metrics_df["metric_id"].isin([x["metric_id"] for x in METRIC_SPECS])]
        .pivot_table(index="symbol", columns="metric_id", values="metric_value", aggfunc="first")
        .reset_index()
        .sort_values("symbol")
        if not metrics_df.empty
        else pd.DataFrame()
    )

    lines: list[str] = []
    lines.append("# FTMO Allocator Monitoring Report")
    lines.append("")
    lines.append(f"- generated_at_utc: `{evaluated_at_utc}`")
    lines.append(f"- runtime_db_path: `{runtime_db_path}`")
    lines.append(f"- lookback_days: `{int(max(1, lookback_days))}`")
    lines.append(f"- metrics_csv: `{out_metrics_csv}`")
    lines.append(f"- alerts_csv: `{out_alerts_csv}`")
    lines.append("")
    lines.append("## Alert Bands")
    lines.append(_table(alert_summary))
    lines.append("")
    lines.append("## Snapshot By Symbol")
    lines.append(_table(latest_snapshot))
    lines.append("")
    lines.append("## Full Alerts")
    lines.append(_table(alerts_df))
    lines.append("")
    lines.append("## Full Metrics")
    lines.append(_table(metrics_df))
    report_out.write_text("\n".join(lines), encoding="utf-8")
    return metrics_df, alerts_df


def main() -> None:
    p = argparse.ArgumentParser(description="Build FTMO allocator monitoring report")
    p.add_argument("--symbols", default="EURUSD,GBPUSD,USDJPY,USDCHF,AUDUSD,USDCAD")
    p.add_argument("--runtime-db-path", default="data/db/behemoth_runtime.db")
    p.add_argument("--lookback-days", type=int, default=7)
    p.add_argument("--stale-pending-hours", type=float, default=6.0)
    p.add_argument("--stale-open-hours", type=float, default=72.0)
    p.add_argument(
        "--out-metrics-csv",
        default="data/analysis/tick_opportunity_mining/ftmo_allocator_monitoring_metrics.csv",
    )
    p.add_argument(
        "--out-alerts-csv",
        default="data/analysis/tick_opportunity_mining/ftmo_allocator_monitoring_alerts.csv",
    )
    p.add_argument(
        "--report-out",
        default="docs/analysis/oco_ftmo_allocator_risk_monitoring_report.md",
    )
    args = p.parse_args()

    metrics, alerts = run(
        symbols=_parse_symbols(args.symbols),
        runtime_db_path=Path(str(args.runtime_db_path)),
        lookback_days=int(max(1, args.lookback_days)),
        stale_pending_hours=float(args.stale_pending_hours),
        stale_open_hours=float(args.stale_open_hours),
        out_metrics_csv=Path(str(args.out_metrics_csv)),
        out_alerts_csv=Path(str(args.out_alerts_csv)),
        report_out=Path(str(args.report_out)),
    )
    print(f"wrote metrics: {args.out_metrics_csv} rows={len(metrics)}")
    print(f"wrote alerts: {args.out_alerts_csv} rows={len(alerts)}")


if __name__ == "__main__":
    main()
