#!/usr/bin/env python3
"""Summarize a runtime DB slice for one symbol and time window."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd


def _table(df: pd.DataFrame) -> str:
    if df.empty:
        return "_empty_"
    try:
        return df.to_markdown(index=False)
    except Exception:
        return "```\n" + df.to_string(index=False) + "\n```"


def _to_utc_series(s: pd.Series) -> pd.Series:
    try:
        return pd.to_datetime(s, utc=True, errors="coerce", format="mixed")
    except TypeError:
        return pd.to_datetime(s, utc=True, errors="coerce")


def _parse_ts(raw: str | None) -> pd.Timestamp | None:
    txt = str(raw or "").strip()
    if not txt:
        return None
    ts = pd.to_datetime(txt, utc=True, errors="coerce")
    if pd.isna(ts):
        raise ValueError(f"invalid timestamp: {raw!r}")
    return ts


def _load_df(con: duckdb.DuckDBPyConnection, sql: str, params: list[object]) -> pd.DataFrame:
    try:
        return con.execute(sql, params).fetchdf()
    except Exception:
        return pd.DataFrame()


def _load_audit_df(con: duckdb.DuckDBPyConnection, symbol: str) -> pd.DataFrame:
    # Prefer close_ts (signal bar time). Fallback keeps compatibility with older DBs.
    with_close = _load_df(
        con,
        """
        SELECT symbol, event_ts, close_ts, candidate_uid, pred_prob, threshold, model_month
        FROM audit_logs
        WHERE upper(symbol) = ?
        """,
        [symbol],
    )
    if len(with_close.columns) > 0:
        if "close_ts" not in with_close.columns:
            with_close["close_ts"] = pd.NaT
        return with_close

    legacy = _load_df(
        con,
        """
        SELECT symbol, event_ts, candidate_uid, pred_prob, threshold, model_month
        FROM audit_logs
        WHERE upper(symbol) = ?
        """,
        [symbol],
    )
    if len(legacy.columns) == 0:
        return pd.DataFrame(
            columns=[
                "symbol",
                "event_ts",
                "close_ts",
                "candidate_uid",
                "pred_prob",
                "threshold",
                "model_month",
            ]
        )
    legacy["close_ts"] = pd.NaT
    return legacy


def run(
    *,
    runtime_db_path: Path,
    symbol: str,
    start_ts: str | None,
    end_ts: str | None,
    out_csv: Path,
    report_out: Path,
) -> pd.DataFrame:
    sym = str(symbol).upper().strip()
    start = _parse_ts(start_ts)
    end = _parse_ts(end_ts)
    if start is not None and end is not None and not (start < end):
        raise ValueError("start_ts must be earlier than end_ts")

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if not runtime_db_path.exists():
        out = pd.DataFrame(
            [
                {
                    "symbol": sym,
                    "runtime_db_path": str(runtime_db_path),
                    "runtime_db_exists": False,
                    "start_ts": start.isoformat() if start is not None else "",
                    "end_ts": end.isoformat() if end is not None else "",
                    "trades_symbol_rows": 0,
                    "trades_window_rows": 0,
                    "trades_window_closed_rows": 0,
                    "trades_window_net_pnl_pips": 0.0,
                    "trades_rows_outside_window": 0,
                    "audit_symbol_rows": 0,
                    "audit_window_rows": 0,
                    "audit_window_source": "event_ts",
                    "audit_event_window_rows": 0,
                    "audit_close_window_rows": 0,
                    "audit_event_window_ratio": 0.0,
                    "audit_rows_outside_window": 0,
                    "trade_entry_min_utc": "",
                    "trade_entry_max_utc": "",
                    "trade_exit_min_utc": "",
                    "trade_exit_max_utc": "",
                    "audit_event_min_utc": "",
                    "audit_event_max_utc": "",
                    "audit_close_min_utc": "",
                    "audit_close_max_utc": "",
                    "evaluated_at_utc": now,
                }
            ]
        )
        out_csv.parent.mkdir(parents=True, exist_ok=True)
        report_out.parent.mkdir(parents=True, exist_ok=True)
        out.to_csv(out_csv, index=False)
        report_out.write_text(
            f"# Runtime DB Run Summary\n\nDB not found: `{runtime_db_path}`\n",
            encoding="utf-8",
        )
        return out

    con = duckdb.connect(str(runtime_db_path), read_only=True)
    try:
        trades = _load_df(
            con,
            """
            SELECT symbol, broker_pos_id, candidate_uid, status, entry_ts, exit_ts, pnl_pips
            FROM trades
            WHERE upper(symbol) = ?
            """,
            [sym],
        )
        audit = _load_audit_df(con, sym)
    finally:
        con.close()

    if not trades.empty:
        trades["entry_ts"] = _to_utc_series(trades.get("entry_ts", pd.Series(dtype=object)))
        trades["exit_ts"] = _to_utc_series(trades.get("exit_ts", pd.Series(dtype=object)))
        trades["status"] = trades.get("status", pd.Series(dtype=str)).astype(str).str.upper()
        trades["pnl_pips"] = pd.to_numeric(trades.get("pnl_pips", pd.Series(dtype=float)), errors="coerce")

    if not audit.empty:
        audit["event_ts"] = _to_utc_series(audit.get("event_ts", pd.Series(dtype=object)))
        audit["close_ts"] = _to_utc_series(audit.get("close_ts", pd.Series(dtype=object)))
        audit["model_month"] = audit.get("model_month", pd.Series(dtype=str)).astype(str)

    def _in_window(ts: pd.Series) -> pd.Series:
        mask = ts.notna()
        if start is not None:
            mask = mask & (ts >= start)
        if end is not None:
            mask = mask & (ts < end)
        return mask

    trades_window = trades[_in_window(trades["entry_ts"])] if not trades.empty else pd.DataFrame()
    audit_event_window = audit[_in_window(audit["event_ts"])] if not audit.empty else pd.DataFrame()
    audit_close_window = audit[_in_window(audit["close_ts"])] if not audit.empty else pd.DataFrame()
    audit_window = audit_close_window if len(audit_close_window) > 0 else audit_event_window
    audit_window_source = "close_ts" if len(audit_close_window) > 0 else "event_ts"
    audit_ts_col = "close_ts" if audit_window_source == "close_ts" else "event_ts"

    trades_outside = (
        int((~_in_window(trades["entry_ts"]) & trades["entry_ts"].notna()).sum())
        if not trades.empty
        else 0
    )
    audit_outside = (
        int((~_in_window(audit[audit_ts_col]) & audit[audit_ts_col].notna()).sum())
        if not audit.empty
        else 0
    )

    audit_ratio = (
        float(len(audit_window)) / float(len(audit))
        if len(audit) > 0
        else 0.0
    )

    summary = pd.DataFrame(
        [
            {
                "symbol": sym,
                "runtime_db_path": str(runtime_db_path),
                "runtime_db_exists": True,
                "start_ts": start.isoformat() if start is not None else "",
                "end_ts": end.isoformat() if end is not None else "",
                "trades_symbol_rows": int(len(trades)),
                "trades_window_rows": int(len(trades_window)),
                "trades_window_closed_rows": int(
                    (trades_window.get("status", pd.Series(dtype=str)) == "CLOSED").sum()
                )
                if not trades_window.empty
                else 0,
                "trades_window_net_pnl_pips": float(
                    trades_window.loc[
                        trades_window.get("status", pd.Series(dtype=str)) == "CLOSED", "pnl_pips"
                    ].fillna(0.0).sum()
                )
                if not trades_window.empty
                else 0.0,
                "trades_rows_outside_window": trades_outside,
                "audit_symbol_rows": int(len(audit)),
                "audit_window_rows": int(len(audit_window)),
                "audit_window_source": audit_window_source,
                "audit_event_window_rows": int(len(audit_event_window)),
                "audit_close_window_rows": int(len(audit_close_window)),
                "audit_event_window_ratio": float(audit_ratio),
                "audit_rows_outside_window": audit_outside,
                "trade_entry_min_utc": (
                    trades["entry_ts"].min().isoformat() if not trades.empty and trades["entry_ts"].notna().any() else ""
                ),
                "trade_entry_max_utc": (
                    trades["entry_ts"].max().isoformat() if not trades.empty and trades["entry_ts"].notna().any() else ""
                ),
                "trade_exit_min_utc": (
                    trades["exit_ts"].min().isoformat() if not trades.empty and trades["exit_ts"].notna().any() else ""
                ),
                "trade_exit_max_utc": (
                    trades["exit_ts"].max().isoformat() if not trades.empty and trades["exit_ts"].notna().any() else ""
                ),
                "audit_event_min_utc": (
                    audit["event_ts"].min().isoformat() if not audit.empty and audit["event_ts"].notna().any() else ""
                ),
                "audit_event_max_utc": (
                    audit["event_ts"].max().isoformat() if not audit.empty and audit["event_ts"].notna().any() else ""
                ),
                "audit_close_min_utc": (
                    audit["close_ts"].min().isoformat() if not audit.empty and audit["close_ts"].notna().any() else ""
                ),
                "audit_close_max_utc": (
                    audit["close_ts"].max().isoformat() if not audit.empty and audit["close_ts"].notna().any() else ""
                ),
                "evaluated_at_utc": now,
            }
        ]
    )

    trades_daily = pd.DataFrame()
    if not trades.empty:
        trades_daily = trades.copy()
        trades_daily["day_utc"] = trades_daily["entry_ts"].dt.strftime("%Y-%m-%d")
        trades_daily = (
            trades_daily.groupby("day_utc", as_index=False)
            .agg(
                trades=("broker_pos_id", "size"),
                closed=("status", lambda s: int((s == "CLOSED").sum())),
                net_pnl_pips=("pnl_pips", lambda s: float(s.fillna(0.0).sum())),
            )
            .sort_values("day_utc")
        )

    audit_daily = pd.DataFrame()
    if not audit.empty:
        audit_daily = audit.copy()
        audit_daily["day_utc"] = audit_daily[audit_ts_col].dt.strftime("%Y-%m-%d")
        audit_daily = (
            audit_daily.groupby("day_utc", as_index=False)
            .agg(
                selected_events=("candidate_uid", "size"),
                unique_candidates=("candidate_uid", "nunique"),
            )
            .sort_values("day_utc")
        )

    model_months = pd.DataFrame()
    if not audit.empty and "model_month" in audit.columns:
        model_months = (
            audit.groupby("model_month", dropna=False, as_index=False)
            .size()
            .rename(columns={"size": "rows"})
            .sort_values("model_month")
        )

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    report_out.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(out_csv, index=False)

    report = [
        "# Runtime DB Run Summary",
        "",
        f"- symbol: `{sym}`",
        f"- db: `{runtime_db_path}`",
        f"- start_ts: `{start.isoformat() if start is not None else ''}`",
        f"- end_ts: `{end.isoformat() if end is not None else ''}`",
        "",
        "## Summary",
        _table(summary),
        "",
        "## Trades By Day",
        _table(trades_daily),
        "",
        "## Audit Events By Day",
        _table(audit_daily),
        "",
        "## Audit Model Months",
        _table(model_months),
        "",
    ]
    report_out.write_text("\n".join(report), encoding="utf-8")
    return summary


def main() -> None:
    p = argparse.ArgumentParser(description="Summarize one runtime DB run window")
    p.add_argument("--runtime-db", default="data/db/behemoth_runtime.db")
    p.add_argument("--symbol", required=True)
    p.add_argument("--start-ts", default="")
    p.add_argument("--end-ts", default="")
    p.add_argument(
        "--out-csv",
        default="data/analysis/backtest_reconcile/runtime_db_run_summary.csv",
    )
    p.add_argument(
        "--report-out",
        default="docs/analysis/runtime_db_run_summary.md",
    )
    args = p.parse_args()

    out = run(
        runtime_db_path=Path(str(args.runtime_db)),
        symbol=str(args.symbol).upper().strip(),
        start_ts=str(args.start_ts).strip() or None,
        end_ts=str(args.end_ts).strip() or None,
        out_csv=Path(str(args.out_csv)),
        report_out=Path(str(args.report_out)),
    )
    print(f"wrote summary: {args.out_csv} rows={len(out)}")
    print(f"wrote report: {args.report_out}")


if __name__ == "__main__":
    main()
