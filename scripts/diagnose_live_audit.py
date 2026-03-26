#!/usr/bin/env python3
"""Diagnose live audit activity from the runtime DuckDB."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd
import requests


def _table(df: pd.DataFrame) -> str:
    if df.empty:
        return "_empty_"
    try:
        return df.to_markdown(index=False)
    except Exception:
        return "```\n" + df.to_string(index=False) + "\n```"


def _safe_query(con: duckdb.DuckDBPyConnection, sql: str, params: list[Any]) -> pd.DataFrame:
    try:
        return con.execute(sql, params).fetchdf()
    except Exception as exc:
        raise RuntimeError(f"diagnostic query failed: {exc}") from exc


def _table_exists(con: duckdb.DuckDBPyConnection, table_name: str) -> bool:
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
        return row is not None
    except Exception:
        return False


def _column_exists(con: duckdb.DuckDBPyConnection, table_name: str, column_name: str) -> bool:
    try:
        row = con.execute(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE lower(table_name) = lower(?)
              AND lower(column_name) = lower(?)
            LIMIT 1
            """,
            [table_name, column_name],
        ).fetchone()
        return row is not None
    except Exception:
        return False


def _percentile_or_nan(series: pd.Series, q: float) -> float:
    if series.empty:
        return float("nan")
    return float(series.quantile(q))


def _fmt_float(value: Any, digits: int = 3) -> str:
    if value is None or pd.isna(value):
        return "nan"
    return f"{float(value):.{digits}f}"


def checkpoint_and_connect(api_base: str, db_path: str) -> duckdb.DuckDBPyConnection:
    try:
        requests.get(f"{api_base}/state/checkpoint", timeout=5).raise_for_status()
    except requests.RequestException as exc:
        print(f"Warning: checkpoint failed ({exc}). Reading DB as-is (WAL may be incomplete).")
    return duckdb.connect(db_path, read_only=True)


def _has_predict_evaluations(con: duckdb.DuckDBPyConnection, run_id: str) -> bool:
    if not _table_exists(con, "predict_evaluations"):
        return False
    try:
        row = con.execute(
            """
            SELECT 1
            FROM predict_evaluations
            WHERE lower(coalesce(run_id, '')) = lower(?)
            LIMIT 1
            """,
            [run_id],
        ).fetchone()
        return row is not None
    except Exception:
        return False


def _section_funnel(con: duckdb.DuckDBPyConnection, run_id: str, use_eval: bool) -> list[str]:
    lines = ["## Prediction Funnel"]
    if use_eval and _table_exists(con, "predict_evaluations"):
        df = _safe_query(
            con,
            """
            SELECT
                upper(e.symbol) AS symbol,
                COUNT(*) AS total_evaluations,
                SUM(CASE WHEN e.preselected_exec = 1 THEN 1 ELSE 0 END) AS preselected_exec_1,
                SUM(CASE WHEN e.selected_exec = 1 THEN 1 ELSE 0 END) AS selected_exec_1,
                COUNT(DISTINCT t.internal_trade_id) AS trades
            FROM predict_evaluations e
            LEFT JOIN trades t
                ON lower(coalesce(t.run_id, '')) = lower(coalesce(e.run_id, ''))
               AND upper(coalesce(t.symbol, '')) = upper(coalesce(e.symbol, ''))
               AND coalesce(t.candidate_uid, '') = coalesce(e.candidate_uid, '')
            WHERE lower(coalesce(e.run_id, '')) = lower(?)
            GROUP BY 1
            ORDER BY 1
            """,
            [run_id],
        )
        lines.append("Source: `predict_evaluations`.")
        if df.empty:
            lines.append("_No rows found for this run._")
            return lines
        df["threshold_miss_rate"] = 1.0 - (df["preselected_exec_1"] / df["total_evaluations"])
        df = df[
            [
                "symbol",
                "total_evaluations",
                "preselected_exec_1",
                "selected_exec_1",
                "trades",
                "threshold_miss_rate",
            ]
        ].copy()
        lines.append(_table(df))
        return lines

    lines.append("Fallback source: `account_risk_allocator_events`.")
    lines.append("`predict_evaluations` not populated for this session - sub-threshold misses are not visible.")
    lines.append("`account_risk_allocator_events` has no `run_id`; fallback spans all sessions in the DB.")
    df = _safe_query(
        con,
        """
        SELECT
            upper(symbol) AS symbol,
            COUNT(*) AS total_events,
            SUM(CASE WHEN upper(status) = 'ADMITTED' THEN 1 ELSE 0 END) AS admitted,
            SUM(CASE WHEN upper(status) = 'BLOCKED' THEN 1 ELSE 0 END) AS blocked
        FROM account_risk_allocator_events
        GROUP BY 1
        ORDER BY 1
        """,
        [],
    )
    lines.append(_table(df))
    trade_run_ids = _safe_query(
        con,
        """
        SELECT COUNT(DISTINCT coalesce(run_id, '')) AS distinct_run_ids
        FROM trades
        """,
        [],
    )
    if not trade_run_ids.empty and int(trade_run_ids.iloc[0, 0] or 0) > 1:
        lines.append("Warning: multiple trade `run_id` values are present, so the fallback is broader than a single session.")
    return lines


def _section_score_distribution(con: duckdb.DuckDBPyConnection, run_id: str, use_eval: bool) -> list[str]:
    lines = ["## Score Distribution"]
    if use_eval and _table_exists(con, "predict_evaluations"):
        df = _safe_query(
            con,
            """
            SELECT upper(symbol) AS symbol, pred_prob, threshold
            FROM predict_evaluations
            WHERE lower(coalesce(run_id, '')) = lower(?)
              AND pred_prob IS NOT NULL
            """,
            [run_id],
        )
        lines.append("Source: `predict_evaluations`.")
        if df.empty:
            lines.append("_No score rows found for this run._")
            return lines
    else:
        df = _safe_query(
            con,
            """
            SELECT upper(symbol) AS symbol, pred_prob, threshold
            FROM audit_logs
            WHERE lower(coalesce(run_id, '')) = lower(?)
              AND pred_prob IS NOT NULL
            """,
            [run_id],
        )
        lines.append("Fallback source: `audit_logs` (admitted rows only).")
        lines.append("`predict_evaluations` not populated for this session - score visibility is admission-only.")
        if df.empty:
            lines.append("_No score rows found for this run._")
            return lines

    rows: list[dict[str, Any]] = []
    for symbol, group in df.groupby("symbol", dropna=False):
        probs = pd.to_numeric(group["pred_prob"], errors="coerce").dropna()
        thresh = pd.to_numeric(group["threshold"], errors="coerce").dropna()
        rows.append(
            {
                "symbol": symbol,
                "n": int(len(group)),
                "threshold": _fmt_float(thresh.median() if not thresh.empty else float("nan")),
                "p25": _fmt_float(_percentile_or_nan(probs, 0.25)),
                "p50": _fmt_float(_percentile_or_nan(probs, 0.50)),
                "p75": _fmt_float(_percentile_or_nan(probs, 0.75)),
                "p90": _fmt_float(_percentile_or_nan(probs, 0.90)),
                "p95": _fmt_float(_percentile_or_nan(probs, 0.95)),
                "p99": _fmt_float(_percentile_or_nan(probs, 0.99)),
            }
        )
    lines.append(_table(pd.DataFrame(rows).sort_values("symbol")))
    return lines


def _section_block_reasons(con: duckdb.DuckDBPyConnection, run_id: str, use_eval: bool) -> list[str]:
    lines = ["## Block Reason Breakdown"]
    if use_eval and _table_exists(con, "predict_evaluations"):
        df = _safe_query(
            con,
            """
            SELECT
                upper(symbol) AS symbol,
                threshold_block_reason,
                risk_block_reason
            FROM predict_evaluations
            WHERE lower(coalesce(run_id, '')) = lower(?)
            """,
            [run_id],
        )
        lines.append("Source: `predict_evaluations`.")
        if df.empty:
            lines.append("_No block reasons found for this run._")
            return lines
        rows: list[dict[str, Any]] = []
        for _, row in df.iterrows():
            symbol = row.get("symbol")
            threshold_reason = row.get("threshold_block_reason")
            risk_reason = row.get("risk_block_reason")
            if pd.notna(threshold_reason) and str(threshold_reason).strip():
                rows.append({"symbol": symbol, "gate": "threshold", "block_reason": threshold_reason})
            if pd.notna(risk_reason) and str(risk_reason).strip():
                rows.append({"symbol": symbol, "gate": "risk", "block_reason": risk_reason})
        if not rows:
            lines.append("_No block reasons found for this run._")
            return lines
        out = (
            pd.DataFrame(rows)
            .groupby(["symbol", "gate", "block_reason"], dropna=False)
            .size()
            .reset_index(name="count")
            .sort_values(["symbol", "gate", "count", "block_reason"], ascending=[True, True, False, True])
        )
        lines.append(_table(out))
        return lines

    lines.append("Fallback source: `account_risk_allocator_events`.")
    lines.append("`predict_evaluations` not populated for this session - threshold-only blocking is not visible.")
    df = _safe_query(
        con,
        """
        SELECT
            upper(symbol) AS symbol,
            coalesce(block_reason, '') AS block_reason
        FROM account_risk_allocator_events
        WHERE upper(coalesce(status, '')) = 'BLOCKED'
        """,
        [],
    )
    if df.empty:
        lines.append("_No block reasons found for this run._")
        return lines
    out = (
        df.groupby(["symbol", "block_reason"], dropna=False)
        .size()
        .reset_index(name="count")
        .sort_values(["symbol", "count", "block_reason"], ascending=[True, False, True])
    )
    lines.append(_table(out))
    return lines


def _section_trade_outcomes(con: duckdb.DuckDBPyConnection, run_id: str) -> list[str]:
    lines = ["## Trade Outcomes"]
    close_reason_expr = (
        "coalesce(close_reason, '')"
        if _column_exists(con, "trades", "close_reason")
        else "''"
    )
    df = _safe_query(
        con,
        f"""
        SELECT
            upper(symbol) AS symbol,
            status,
            pnl_pips,
            {close_reason_expr} AS close_reason_value
        FROM trades
        WHERE lower(coalesce(run_id, '')) = lower(?)
        """,
        [run_id],
    )
    if df.empty:
        lines.append("_No trades found for this run._")
        return lines
    df["status"] = df["status"].astype(str).str.upper()
    df["pnl_pips"] = pd.to_numeric(df["pnl_pips"], errors="coerce")
    rows: list[dict[str, Any]] = []
    for symbol, group in df.groupby("symbol", dropna=False):
        closed = group[group["status"] == "CLOSED"].copy()
        wins = closed[closed["pnl_pips"] > 0]
        losses = closed[closed["pnl_pips"] < 0]
        reason_counts = (
            closed.loc[
                closed["close_reason_value"].astype(str).str.strip() != "",
                "close_reason_value",
            ]
            .astype(str)
            .value_counts()
        )
        reason_text = ", ".join(f"{reason}={count}" for reason, count in reason_counts.items())
        rows.append(
            {
                "symbol": symbol,
                "closed_trades": int(len(closed)),
                "wins": int(len(wins)),
                "win_rate": _fmt_float((len(wins) / len(closed) * 100.0) if len(closed) else 0.0, 1) + "%",
                "avg_winner_pips": _fmt_float(wins["pnl_pips"].mean() if not wins.empty else float("nan")),
                "avg_loser_pips": _fmt_float(losses["pnl_pips"].mean() if not losses.empty else float("nan")),
                "total_pnl_pips": _fmt_float(closed["pnl_pips"].sum() if not closed.empty else float("nan")),
                "close_reasons": reason_text,
            }
        )
    lines.append(_table(pd.DataFrame(rows).sort_values("symbol")))
    return lines


def _build_report(con: duckdb.DuckDBPyConnection, run_id: str) -> str:
    use_eval = _has_predict_evaluations(con, run_id)
    lines = [
        "# Live Audit Diagnostic Report",
        "",
        f"- run_id: `{run_id}`",
        f"- prediction evaluations: {'yes' if use_eval else 'no'}",
        "",
    ]
    for section in (
        _section_funnel(con, run_id, use_eval),
        _section_score_distribution(con, run_id, use_eval),
        _section_block_reasons(con, run_id, use_eval),
        _section_trade_outcomes(con, run_id),
    ):
        lines.extend(section)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Diagnose live audit activity from the runtime DB")
    parser.add_argument("--db", required=True, help="Path to the live_state.db DuckDB file")
    parser.add_argument("--api", default="http://localhost:8000", help="API base URL")
    parser.add_argument("--run-id", default="jforex_live", help="Runtime run identifier")
    parser.add_argument("--out", required=True, help="Output markdown report path")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    con = checkpoint_and_connect(args.api, args.db)
    try:
        report = _build_report(con, args.run_id)
    finally:
        con.close()
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")


if __name__ == "__main__":
    main()
