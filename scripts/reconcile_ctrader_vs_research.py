#!/usr/bin/env python3
"""Reconcile cTrader runtime DB signals against research predictions."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd


@dataclass
class Check:
    check_id: str
    status: str
    severity: str
    metric: str
    value: Any
    expected: Any
    operator: str
    detail: str


def _table(df: pd.DataFrame) -> str:
    if df.empty:
        return "_empty_"
    try:
        return df.to_markdown(index=False)
    except Exception:
        return "```\n" + df.to_string(index=False) + "\n```"


def _to_utc(s: pd.Series) -> pd.Series:
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


def _uid_symbol(uid: str) -> str:
    parts = str(uid).split("|")
    if len(parts) >= 3:
        return str(parts[1]).upper().strip()
    return ""


def _safe_query(con: duckdb.DuckDBPyConnection | None, sql: str, params: list[Any]) -> pd.DataFrame:
    if con is None:
        return pd.DataFrame()
    try:
        return con.execute(sql, params).fetchdf()
    except Exception:
        return pd.DataFrame()


def _window_mask(s: pd.Series, start: pd.Timestamp | None, end: pd.Timestamp | None) -> pd.Series:
    mask = s.notna()
    if start is not None:
        mask = mask & (s >= start)
    if end is not None:
        mask = mask & (s < end)
    return mask


def _add_check(
    checks: list[Check],
    *,
    check_id: str,
    ok: bool,
    severity: str,
    metric: str,
    value: Any,
    expected: Any,
    operator: str,
    detail: str,
) -> None:
    checks.append(
        Check(
            check_id=check_id,
            status="pass" if bool(ok) else "fail",
            severity=str(severity),
            metric=str(metric),
            value=value,
            expected=expected,
            operator=str(operator),
            detail=str(detail),
        )
    )


def _derive_model_month_from_ts(ts: pd.Series) -> pd.Series:
    return ts.dt.strftime("%Y-%m")


def _load_locked_uids_by_month(
    history_dir: Path,
    symbol: str,
    months: list[str],
) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    sym = str(symbol).upper().strip()
    for month in months:
        m = str(month).strip()
        if not m:
            continue
        p = history_dir / m / f"{sym.lower()}_oco_live_lock.json"
        if not p.exists():
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            rows = data.get("state_universe", {}).get("rows", [])
            if not isinstance(rows, list):
                continue
            uids: set[str] = set()
            for row in rows:
                if not isinstance(row, dict):
                    continue
                row_sym = str(row.get("symbol", sym)).upper().strip()
                if row_sym and row_sym != sym:
                    continue
                state_id = str(row.get("state_id", "")).strip()
                if not state_id:
                    continue
                bar_ticks = int(row.get("bar_ticks"))
                horizon = int(row.get("horizon"))
                uids.add(f"oco|{sym}|{bar_ticks}|h{horizon}|{state_id}")
            if uids:
                out[m] = uids
        except Exception:
            continue
    return out


def _asof_ts_ns(s: pd.Series) -> pd.Series:
    """Normalize timezone-aware datetime series to UTC nanosecond resolution."""
    out = _to_utc(s)
    try:
        return out.astype("datetime64[ns, UTC]")
    except Exception:
        # Last-resort normalization path if dtype casting fails in older pandas builds.
        return pd.to_datetime(out.astype(str), utc=True, errors="coerce").astype("datetime64[ns, UTC]")


def _timestamp_alignment_diagnostics(
    *,
    left: pd.DataFrame,
    right: pd.DataFrame,
    left_ts_col: str,
    right_ts_col: str,
    key_cols: list[str],
    tolerance_sec: float,
) -> dict[str, float]:
    out = {
        "lag_sample_count": 0.0,
        "best_lag_minutes": float("nan"),
        "median_abs_gap_sec": float("nan"),
        "p95_abs_gap_sec": float("nan"),
        "match_ratio_lag0": 0.0,
        "match_ratio_best_lag": 0.0,
    }
    if left.empty or right.empty:
        return out

    ldf = left.copy()
    rdf = right.copy()
    ldf[left_ts_col] = _asof_ts_ns(ldf[left_ts_col])
    rdf[right_ts_col] = _asof_ts_ns(rdf[right_ts_col])
    for c in key_cols:
        ldf[c] = ldf[c].astype(str)
        rdf[c] = rdf[c].astype(str)
    ldf = ldf[ldf[left_ts_col].notna()].sort_values(left_ts_col)
    rdf = rdf[rdf[right_ts_col].notna()].sort_values(right_ts_col)
    if ldf.empty or rdf.empty:
        return out

    keys = ldf[key_cols].drop_duplicates()
    rdf = rdf.merge(keys, on=key_cols, how="inner")
    if rdf.empty:
        return out

    matched_any = pd.merge_asof(
        ldf,
        rdf,
        left_on=left_ts_col,
        right_on=right_ts_col,
        by=key_cols,
        direction="nearest",
    )
    matched_any = matched_any[matched_any[right_ts_col].notna()].copy()
    if matched_any.empty:
        return out

    delta_sec = (matched_any[right_ts_col] - matched_any[left_ts_col]).dt.total_seconds()
    abs_delta_sec = delta_sec.abs()
    sample_count = int(len(abs_delta_sec))
    out["lag_sample_count"] = float(sample_count)
    out["best_lag_minutes"] = float(delta_sec.median() / 60.0)
    out["median_abs_gap_sec"] = float(abs_delta_sec.median())
    out["p95_abs_gap_sec"] = float(abs_delta_sec.quantile(0.95))

    tol = pd.Timedelta(seconds=max(0.0, float(tolerance_sec)))
    lag0 = pd.merge_asof(
        ldf,
        rdf,
        left_on=left_ts_col,
        right_on=right_ts_col,
        by=key_cols,
        tolerance=tol,
        direction="nearest",
    )
    out["match_ratio_lag0"] = float(lag0[right_ts_col].notna().sum()) / float(len(ldf))

    shift = pd.to_timedelta(float(delta_sec.median()), unit="s")
    shifted = ldf.copy()
    shifted[left_ts_col] = shifted[left_ts_col] + shift
    lag_best = pd.merge_asof(
        shifted,
        rdf,
        left_on=left_ts_col,
        right_on=right_ts_col,
        by=key_cols,
        tolerance=tol,
        direction="nearest",
    )
    out["match_ratio_best_lag"] = float(lag_best[right_ts_col].notna().sum()) / float(len(shifted))
    return out


def _load_research_predictions_window(
    predictions_parquet: Path,
    *,
    symbol: str,
    start: pd.Timestamp | None,
    end: pd.Timestamp | None,
) -> pd.DataFrame:
    """Load only the symbol/window slice from predictions parquet using DuckDB pushdown."""
    con = duckdb.connect()
    try:
        filters = ["upper(split_part(candidate_uid, '|', 2)) = ?"]
        close_ts_expr = "try_cast(close_ts AS TIMESTAMP WITH TIME ZONE)"
        params: list[Any] = [str(predictions_parquet), str(symbol).upper().strip()]
        if start is not None:
            filters.append(f"{close_ts_expr} >= ?")
            params.append(start.to_pydatetime())
        if end is not None:
            filters.append(f"{close_ts_expr} < ?")
            params.append(end.to_pydatetime())
        sql = (
            "SELECT * FROM read_parquet(?) "
            "WHERE " + " AND ".join(filters)
        )
        return con.execute(sql, params).fetchdf()
    finally:
        con.close()


def _month_tags_between(start: pd.Timestamp | None, end: pd.Timestamp | None) -> list[str]:
    if start is None or end is None or not (start < end):
        return []
    end_inclusive = end - pd.Timedelta(microseconds=1)
    if end_inclusive < start:
        return []
    s0 = start.tz_convert("UTC").tz_localize(None) if start.tzinfo is not None else start
    e0 = (
        end_inclusive.tz_convert("UTC").tz_localize(None)
        if end_inclusive.tzinfo is not None
        else end_inclusive
    )
    pr = pd.period_range(start=s0.to_period("M"), end=e0.to_period("M"), freq="M")
    return [str(p).replace("-", "") for p in pr]


def _quote_sql_path(path: Path) -> str:
    return "'" + str(path).replace("'", "''") + "'"


def _load_hist_tick_timestamps(
    *,
    symbol: str,
    start: pd.Timestamp | None,
    end: pd.Timestamp | None,
    tick_root: Path | None,
) -> pd.Series:
    if tick_root is None or start is None or end is None or not (start < end):
        return pd.Series(dtype="datetime64[ns, UTC]")
    sym = str(symbol).upper().strip()
    months = _month_tags_between(start, end)
    files = [
        tick_root / sym / f"{sym}_{m}_ticks.parquet"
        for m in months
        if (tick_root / sym / f"{sym}_{m}_ticks.parquet").exists()
    ]
    if not files:
        return pd.Series(dtype="datetime64[ns, UTC]")

    files_sql = "[" + ",".join(_quote_sql_path(p) for p in files) + "]"
    con = duckdb.connect()
    try:
        sql = (
            f"SELECT timestamp AS ts FROM read_parquet({files_sql}) "
            "WHERE timestamp >= ? AND timestamp < ? ORDER BY timestamp"
        )
        df = con.execute(sql, [start.to_pydatetime(), end.to_pydatetime()]).fetchdf()
    finally:
        con.close()
    if "ts" not in df.columns:
        return pd.Series(dtype="datetime64[ns, UTC]")
    return _to_utc(df["ts"])


def _median_intertick_ms(ts: pd.Series) -> float:
    if ts.empty:
        return float("nan")
    x = _to_utc(ts).dropna().sort_values()
    if len(x) < 2:
        return float("nan")
    dt_ms = x.diff().dt.total_seconds().dropna() * 1000.0
    if dt_ms.empty:
        return float("nan")
    return float(dt_ms.median())


def run(
    *,
    symbol: str,
    runtime_db_path: Path,
    predictions_parquet: Path,
    history_dir: Path | None = None,
    tick_root: Path | None = None,
    start_ts: str | None = None,
    end_ts: str | None = None,
    strict_window: bool = True,
    timestamp_tolerance_sec: float = 2.0,
    out_checks_csv: Path = Path("data/analysis/backtest_reconcile/ctrader_vs_research_checks.csv"),
    out_mismatches_csv: Path = Path("data/analysis/backtest_reconcile/ctrader_vs_research_mismatches.csv"),
    report_out: Path = Path("docs/analysis/ctrader_vs_research_reconciliation.md"),
) -> tuple[pd.DataFrame, pd.DataFrame]:
    sym = str(symbol).upper().strip()
    start = _parse_ts(start_ts)
    end = _parse_ts(end_ts)
    if start is not None and end is not None and not (start < end):
        raise ValueError("start_ts must be earlier than end_ts")

    checks: list[Check] = []
    mismatches: list[dict[str, Any]] = []
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    _add_check(
        checks,
        check_id="RUNTIME_DB_EXISTS",
        ok=runtime_db_path.exists(),
        severity="critical",
        metric="runtime_db_exists",
        value=bool(runtime_db_path.exists()),
        expected=True,
        operator="==",
        detail=f"path={runtime_db_path}",
    )
    _add_check(
        checks,
        check_id="PREDICTIONS_PARQUET_EXISTS",
        ok=predictions_parquet.exists(),
        severity="critical",
        metric="predictions_parquet_exists",
        value=bool(predictions_parquet.exists()),
        expected=True,
        operator="==",
        detail=f"path={predictions_parquet}",
    )

    if (not runtime_db_path.exists()) or (not predictions_parquet.exists()):
        checks_df = pd.DataFrame([c.__dict__ for c in checks])
        mismatches_df = pd.DataFrame(mismatches)
        out_checks_csv.parent.mkdir(parents=True, exist_ok=True)
        out_mismatches_csv.parent.mkdir(parents=True, exist_ok=True)
        report_out.parent.mkdir(parents=True, exist_ok=True)
        checks_df.to_csv(out_checks_csv, index=False)
        mismatches_df.to_csv(out_mismatches_csv, index=False)
        report_out.write_text(
            "# cTrader vs Research Reconciliation\n\nMissing required input files.\n",
            encoding="utf-8",
        )
        return checks_df, mismatches_df

    con = duckdb.connect(str(runtime_db_path), read_only=True)
    try:
        trades = _safe_query(
            con,
            """
            SELECT symbol, broker_pos_id, candidate_uid, status, entry_ts, exit_ts, pnl_pips
            FROM trades
            WHERE upper(symbol) = ?
            """,
            [sym],
        )
        audit = _safe_query(
            con,
            """
            SELECT symbol, event_ts, close_ts, candidate_uid, pred_prob, threshold, model_month
            FROM audit_logs
            WHERE upper(symbol) = ?
            """,
            [sym],
        )
        raw_ticks = _safe_query(
            con,
            """
            SELECT symbol, tick_ts
            FROM raw_ticks
            WHERE upper(symbol) = ?
            """,
            [sym],
        )
    finally:
        con.close()

    research = _load_research_predictions_window(
        predictions_parquet,
        symbol=sym,
        start=start,
        end=end,
    )
    if "candidate_uid" not in research.columns or "close_ts" not in research.columns:
        raise ValueError("predictions parquet must contain candidate_uid and close_ts")

    research = research.copy()
    research["candidate_uid"] = research["candidate_uid"].astype(str)
    research["close_ts"] = _to_utc(research.get("close_ts", pd.Series(dtype=object)))

    if "selected_exec" not in research.columns:
        if {"pred_prob", "threshold_exec"}.issubset(research.columns):
            research["selected_exec"] = (
                pd.to_numeric(research["pred_prob"], errors="coerce")
                >= pd.to_numeric(research["threshold_exec"], errors="coerce")
            ).astype(int)
        else:
            raise ValueError("predictions parquet missing selected_exec and cannot derive from threshold_exec")

    research["model_month"] = _derive_model_month_from_ts(research["close_ts"])
    research_window = research[_window_mask(research["close_ts"], start, end)].copy()
    research_sel = research_window[research_window["selected_exec"] == 1].copy()

    history_filter_applied = False
    history_filter_month_coverage_ratio = 0.0
    history_filter_selected_rows_before = int(len(research_sel))
    history_filter_selected_rows_after = int(len(research_sel))
    if history_dir is not None and str(history_dir).strip() != "":
        history_filter_applied = True
        months = sorted(
            {
                str(m).strip()
                for m in research_window.get("model_month", pd.Series(dtype=str)).dropna().astype(str)
                if str(m).strip() != ""
            }
        )
        locked_uids_by_month = _load_locked_uids_by_month(Path(history_dir), sym, months)
        if months:
            history_filter_month_coverage_ratio = float(len(locked_uids_by_month)) / float(len(months))
        _add_check(
            checks,
            check_id="HIST_LOCK_MONTH_COVERAGE_EQ_1_00",
            ok=(history_filter_month_coverage_ratio >= 1.0),
            severity="high",
            metric="hist_lock_month_coverage_ratio",
            value=float(history_filter_month_coverage_ratio),
            expected=1.0,
            operator="==",
            detail=f"history_dir={history_dir}",
        )

        if len(research_window) > 0:
            mask = pd.Series(
                [
                    str(uid) in locked_uids_by_month.get(str(mm), set())
                    for uid, mm in zip(
                        research_window.get("candidate_uid", pd.Series(dtype=str)).astype(str),
                        research_window.get("model_month", pd.Series(dtype=str)).astype(str),
                    )
                ],
                index=research_window.index,
                dtype=bool,
            )
            research_window = research_window[mask].copy()
            research_sel = research_window[research_window["selected_exec"] == 1].copy()
        else:
            research_sel = research_window.copy()

        history_filter_selected_rows_after = int(len(research_sel))
        _add_check(
            checks,
            check_id="HIST_LOCK_FILTER_SELECTED_ROWS_GT_0",
            ok=(history_filter_selected_rows_after > 0),
            severity="critical",
            metric="hist_lock_filter_selected_rows",
            value=int(history_filter_selected_rows_after),
            expected=">0",
            operator=">",
            detail=f"before={history_filter_selected_rows_before}",
        )

    if not trades.empty:
        trades["entry_ts"] = _to_utc(trades.get("entry_ts", pd.Series(dtype=object)))
        trades["exit_ts"] = _to_utc(trades.get("exit_ts", pd.Series(dtype=object)))
        trades["status"] = trades.get("status", pd.Series(dtype=str)).astype(str).str.upper()
        trades["candidate_uid"] = trades.get("candidate_uid", pd.Series(dtype=str)).astype(str)

    if not audit.empty:
        audit["event_ts"] = _to_utc(audit.get("event_ts", pd.Series(dtype=object)))
        if "close_ts" in audit.columns:
            audit["close_ts"] = _to_utc(audit.get("close_ts", pd.Series(dtype=object)))
        else:
            audit["close_ts"] = pd.NaT
        audit["model_month"] = audit.get("model_month", pd.Series(dtype=str)).astype(str)
        audit["candidate_uid"] = audit.get("candidate_uid", pd.Series(dtype=str)).astype(str)

    if not raw_ticks.empty:
        raw_ticks["tick_ts"] = _to_utc(raw_ticks.get("tick_ts", pd.Series(dtype=object)))

    trades_window = trades[_window_mask(trades["entry_ts"], start, end)] if not trades.empty else pd.DataFrame()
    audit_event_window = audit[_window_mask(audit["event_ts"], start, end)] if not audit.empty else pd.DataFrame()
    audit_close_window = audit[_window_mask(audit["close_ts"], start, end)] if not audit.empty else pd.DataFrame()
    raw_ticks_window = (
        raw_ticks[_window_mask(raw_ticks["tick_ts"], start, end)] if not raw_ticks.empty else pd.DataFrame()
    )

    audit_window = audit_close_window if len(audit_close_window) > 0 else audit_event_window
    audit_window_source = "close_ts" if len(audit_close_window) > 0 else "event_ts"

    if not trades.empty:
        entry_ts = trades["entry_ts"]
        before_start_mask = entry_ts.notna() & ((entry_ts < start) if start is not None else False)
        after_end_mask = entry_ts.notna() & ((entry_ts >= end) if end is not None else False)
        trades_outside_before_start = int(before_start_mask.sum())
        trades_outside_after_end = int(after_end_mask.sum())
    else:
        before_start_mask = pd.Series(dtype=bool)
        after_end_mask = pd.Series(dtype=bool)
        trades_outside_before_start = 0
        trades_outside_after_end = 0

    _add_check(
        checks,
        check_id="TRADES_SYMBOL_ROWS_PRESENT",
        ok=len(trades) > 0,
        severity="high",
        metric="trades_symbol_rows",
        value=int(len(trades)),
        expected=">0",
        operator=">",
        detail="rows for symbol in runtime trades table",
    )
    _add_check(
        checks,
        check_id="TRADES_WINDOW_ROWS_PRESENT",
        ok=len(trades_window) > 0,
        severity="high",
        metric="trades_window_rows",
        value=int(len(trades_window)),
        expected=">0",
        operator=">",
        detail="rows for symbol in requested window",
    )

    # With strict windowing, only rows *before* start are a hard mismatch.
    # Rows after end are common when reconciling a partial span from a longer run.
    trades_outside_hard = trades_outside_before_start if strict_window else 0
    outside_ok = trades_outside_hard == 0
    _add_check(
        checks,
        check_id="TRADES_OUTSIDE_WINDOW_ZERO" if strict_window else "TRADES_OUTSIDE_WINDOW_INFO",
        ok=outside_ok,
        severity="high" if strict_window else "medium",
        metric="trades_rows_outside_window",
        value=int(trades_outside_hard if strict_window else (trades_outside_before_start + trades_outside_after_end)),
        expected=0,
        operator="==",
        detail=(
            f"strict_window={strict_window}; "
            f"before_start={trades_outside_before_start}; after_end={trades_outside_after_end}"
        ),
    )
    _add_check(
        checks,
        check_id="TRADES_AFTER_WINDOW_ROWS_INFO",
        ok=True,
        severity="medium",
        metric="trades_rows_after_window",
        value=int(trades_outside_after_end),
        expected="informational",
        operator="info",
        detail=(
            "non-zero is expected when reconciling a partial window from an in-progress or multi-month runtime DB"
        ),
    )
    if trades_outside_before_start > 0:
        s = trades[before_start_mask].head(25)
        for _, r in s.iterrows():
            mismatches.append(
                {
                    "type": "trade_entry_before_window",
                    "symbol": sym,
                    "candidate_uid": str(r.get("candidate_uid", "")),
                    "model_month": "",
                    "runtime_ts": r.get("entry_ts"),
                    "research_ts": pd.NaT,
                    "detail": "entry_ts before requested start_ts",
                }
            )

    _add_check(
        checks,
        check_id="AUDIT_SYMBOL_ROWS_PRESENT",
        ok=len(audit) > 0,
        severity="high",
        metric="audit_symbol_rows",
        value=int(len(audit)),
        expected=">0",
        operator=">",
        detail="rows for symbol in runtime audit_logs table",
    )

    audit_window_ratio = float(len(audit_event_window)) / float(len(audit)) if len(audit) > 0 else 0.0
    audit_event_ratio_required = audit_window_source != "close_ts"
    _add_check(
        checks,
        check_id=(
            "AUDIT_EVENT_WINDOW_RATIO_GE_0_95"
            if audit_event_ratio_required
            else "AUDIT_EVENT_WINDOW_RATIO_INFO"
        ),
        ok=(audit_window_ratio >= 0.95) if audit_event_ratio_required else True,
        severity="high" if audit_event_ratio_required else "medium",
        metric="audit_event_window_ratio",
        value=float(audit_window_ratio),
        expected=0.95 if audit_event_ratio_required else "informational",
        operator=">=" if audit_event_ratio_required else "info",
        detail=(
            "low ratio usually means mixed-run DB or wall-clock event timestamps"
            if audit_event_ratio_required
            else "event_ts is wall-clock; close_ts is used for audit-window reconciliation"
        ),
    )
    if len(audit) > 0 and audit_window_ratio < 0.95 and audit_event_ratio_required:
        s = audit[~_window_mask(audit["event_ts"], start, end)].head(25)
        for _, r in s.iterrows():
            mismatches.append(
                {
                    "type": "audit_event_ts_outside_window",
                    "symbol": sym,
                    "candidate_uid": str(r.get("candidate_uid", "")),
                    "model_month": str(r.get("model_month", "")),
                    "runtime_ts": r.get("event_ts"),
                    "research_ts": pd.NaT,
                    "detail": "audit event_ts outside requested run window",
                }
            )

    unknown_model_month_ratio = 0.0
    if len(audit_window) > 0:
        unknown_model_month_ratio = float(
            (audit_window["model_month"].astype(str).str.strip().str.lower().isin({"", "unknown", "nan"})).sum()
        ) / float(len(audit_window))
    _add_check(
        checks,
        check_id="AUDIT_MODEL_MONTH_KNOWN_RATIO_GE_0_95",
        ok=unknown_model_month_ratio <= 0.05,
        severity="high",
        metric="audit_unknown_model_month_ratio",
        value=float(unknown_model_month_ratio),
        expected=0.05,
        operator="<=",
        detail=f"audit_window_source={audit_window_source}",
    )

    hist_tick_ts = _load_hist_tick_timestamps(
        symbol=sym,
        start=start,
        end=end,
        tick_root=tick_root,
    )
    runtime_raw_tick_rows = int(len(raw_ticks_window))
    hist_tick_rows = int(len(hist_tick_ts))
    raw_tick_coverage_ratio = (
        float(runtime_raw_tick_rows) / float(hist_tick_rows)
        if hist_tick_rows > 0
        else float("nan")
    )
    runtime_raw_median_intertick_ms = _median_intertick_ms(
        raw_ticks_window.get("tick_ts", pd.Series(dtype=object))
    )
    hist_median_intertick_ms = _median_intertick_ms(hist_tick_ts)
    intertick_ratio_runtime_vs_hist = (
        float(runtime_raw_median_intertick_ms) / float(hist_median_intertick_ms)
        if pd.notna(runtime_raw_median_intertick_ms)
        and pd.notna(hist_median_intertick_ms)
        and float(hist_median_intertick_ms) > 0.0
        else float("nan")
    )

    _add_check(
        checks,
        check_id="RAW_TICK_ROWS_WINDOW_PRESENT",
        ok=runtime_raw_tick_rows > 0,
        severity="high",
        metric="runtime_raw_tick_rows_window",
        value=int(runtime_raw_tick_rows),
        expected=">0",
        operator=">",
        detail="runtime raw_ticks rows in requested window",
    )
    if hist_tick_rows > 0:
        _add_check(
            checks,
            check_id="RAW_TICK_COVERAGE_RATIO_GE_0_95",
            ok=float(raw_tick_coverage_ratio) >= 0.95,
            severity="high",
            metric="raw_tick_coverage_ratio_runtime_vs_hist",
            value=float(raw_tick_coverage_ratio),
            expected=0.95,
            operator=">=",
            detail=f"tick_root={tick_root}",
        )
        _add_check(
            checks,
            check_id="RUNTIME_MEDIAN_INTERTICK_MS_LE_2X_HIST",
            ok=(
                float(intertick_ratio_runtime_vs_hist) <= 2.0
                if pd.notna(intertick_ratio_runtime_vs_hist)
                else False
            ),
            severity="high",
            metric="median_intertick_ratio_runtime_vs_hist",
            value=(
                float(intertick_ratio_runtime_vs_hist)
                if pd.notna(intertick_ratio_runtime_vs_hist)
                else float("nan")
            ),
            expected=2.0,
            operator="<=",
            detail=(
                f"runtime_median_ms={runtime_raw_median_intertick_ms}; "
                f"hist_median_ms={hist_median_intertick_ms}"
            ),
        )
    else:
        _add_check(
            checks,
            check_id="HIST_TICK_ROWS_WINDOW_INFO",
            ok=True,
            severity="medium",
            metric="hist_tick_rows_window",
            value=int(hist_tick_rows),
            expected="informational",
            operator="info",
            detail=f"tick_root={tick_root}; no HistData rows found for requested window",
        )

    _add_check(
        checks,
        check_id="RESEARCH_ROWS_WINDOW_PRESENT",
        ok=len(research_window) > 0,
        severity="critical",
        metric="research_window_rows",
        value=int(len(research_window)),
        expected=">0",
        operator=">",
        detail="research parquet rows in requested window",
    )
    _add_check(
        checks,
        check_id="RESEARCH_SELECTED_ROWS_WINDOW_PRESENT",
        ok=len(research_sel) > 0,
        severity="critical",
        metric="research_selected_rows_window",
        value=int(len(research_sel)),
        expected=">0",
        operator=">",
        detail="selected_exec==1 rows in requested window",
    )

    expected_keys = (
        research_sel[["candidate_uid", "model_month"]]
        .dropna(subset=["candidate_uid", "model_month"])
        .drop_duplicates()
    )
    actual_for_keys = (
        audit_window[["candidate_uid", "model_month"]]
        if len(audit_window) > 0
        else audit[["candidate_uid", "model_month"]]
    )
    actual_keys = (
        actual_for_keys
        .dropna(subset=["candidate_uid", "model_month"])
        .copy()
    )
    actual_keys["model_month"] = actual_keys["model_month"].astype(str).str.strip()
    actual_keys = actual_keys[actual_keys["model_month"] != ""].drop_duplicates()

    expected_set = set(map(tuple, expected_keys.to_records(index=False).tolist()))
    actual_set = set(map(tuple, actual_keys.to_records(index=False).tolist()))
    missing = sorted(list(expected_set - actual_set))
    extra = sorted(list(actual_set - expected_set))
    inter = len(expected_set & actual_set)
    union = len(expected_set | actual_set)
    jaccard = float(inter) / float(union) if union > 0 else 1.0

    _add_check(
        checks,
        check_id="SELECTED_KEY_MISSING_EQ_0",
        ok=len(missing) == 0,
        severity="high",
        metric="selected_key_missing_count",
        value=int(len(missing)),
        expected=0,
        operator="==",
        detail="key=(candidate_uid, model_month)",
    )
    _add_check(
        checks,
        check_id="SELECTED_KEY_EXTRA_EQ_0",
        ok=len(extra) == 0,
        severity="high",
        metric="selected_key_extra_count",
        value=int(len(extra)),
        expected=0,
        operator="==",
        detail="key=(candidate_uid, model_month)",
    )
    _add_check(
        checks,
        check_id="SELECTED_KEY_JACCARD_GE_0_95",
        ok=jaccard >= 0.95,
        severity="high",
        metric="selected_key_jaccard",
        value=float(jaccard),
        expected=0.95,
        operator=">=",
        detail="key=(candidate_uid, model_month)",
    )

    expected_counts = (
        research_sel[["candidate_uid", "model_month"]]
        .dropna(subset=["candidate_uid", "model_month"])
        .astype({"candidate_uid": str, "model_month": str})
        .groupby(["candidate_uid", "model_month"], as_index=False)
        .size()
        .rename(columns={"size": "expected_count"})
    )
    actual_counts = (
        audit_window[["candidate_uid", "model_month"]]
        .dropna(subset=["candidate_uid", "model_month"])
        .astype({"candidate_uid": str, "model_month": str})
        .groupby(["candidate_uid", "model_month"], as_index=False)
        .size()
        .rename(columns={"size": "actual_count"})
    )
    count_cmp = expected_counts.merge(
        actual_counts,
        on=["candidate_uid", "model_month"],
        how="outer",
    ).fillna(0)
    if not count_cmp.empty:
        count_cmp["expected_count"] = count_cmp["expected_count"].astype(int)
        count_cmp["actual_count"] = count_cmp["actual_count"].astype(int)
    count_missing_rows = int((count_cmp["expected_count"] - count_cmp["actual_count"]).clip(lower=0).sum()) if not count_cmp.empty else 0
    count_extra_rows = int((count_cmp["actual_count"] - count_cmp["expected_count"]).clip(lower=0).sum()) if not count_cmp.empty else 0
    if len(research_sel) == 0:
        count_ratio = 0.0 if len(audit_window) == 0 else float("inf")
        count_ratio_ok = len(audit_window) == 0
    else:
        count_ratio = float(len(audit_window)) / float(len(research_sel))
        count_ratio_ok = 0.80 <= count_ratio <= 1.20
    _add_check(
        checks,
        check_id="SELECTED_COUNT_MISSING_ROWS_EQ_0",
        ok=count_missing_rows == 0,
        severity="high",
        metric="selected_count_missing_rows",
        value=int(count_missing_rows),
        expected=0,
        operator="==",
        detail="row-count delta by key=(candidate_uid, model_month)",
    )
    _add_check(
        checks,
        check_id="SELECTED_COUNT_EXTRA_ROWS_EQ_0",
        ok=count_extra_rows == 0,
        severity="high",
        metric="selected_count_extra_rows",
        value=int(count_extra_rows),
        expected=0,
        operator="==",
        detail="row-count delta by key=(candidate_uid, model_month)",
    )
    _add_check(
        checks,
        check_id="SELECTED_COUNT_RATIO_BETWEEN_0_8_1_2",
        ok=count_ratio_ok,
        severity="high",
        metric="selected_count_ratio_runtime_vs_research",
        value=float(count_ratio),
        expected="[0.8,1.2]",
        operator="between",
        detail="ratio=len(audit_window)/len(research_selected_window)",
    )

    for uid, mm in missing[:1000]:
        mismatches.append(
            {
                "type": "missing_selected_key",
                "symbol": sym,
                "candidate_uid": uid,
                "model_month": mm,
                "runtime_ts": pd.NaT,
                "research_ts": pd.NaT,
                "detail": "present in research selected set but absent in runtime selected set",
                }
            )
    if not count_cmp.empty:
        extra_rows = count_cmp[count_cmp["actual_count"] > count_cmp["expected_count"]].copy()
        for _, r in extra_rows.sort_values("actual_count", ascending=False).head(25).iterrows():
            mismatches.append(
                {
                    "type": "extra_selected_count_by_key",
                    "symbol": sym,
                    "candidate_uid": str(r.get("candidate_uid", "")),
                    "model_month": str(r.get("model_month", "")),
                    "runtime_ts": pd.NaT,
                    "research_ts": pd.NaT,
                    "detail": (
                        f"actual_count={int(r.get('actual_count', 0))} "
                        f"expected_count={int(r.get('expected_count', 0))}"
                    ),
                }
            )
        missing_rows = count_cmp[count_cmp["expected_count"] > count_cmp["actual_count"]].copy()
        for _, r in missing_rows.sort_values("expected_count", ascending=False).head(25).iterrows():
            mismatches.append(
                {
                    "type": "missing_selected_count_by_key",
                    "symbol": sym,
                    "candidate_uid": str(r.get("candidate_uid", "")),
                    "model_month": str(r.get("model_month", "")),
                    "runtime_ts": pd.NaT,
                    "research_ts": pd.NaT,
                    "detail": (
                        f"actual_count={int(r.get('actual_count', 0))} "
                        f"expected_count={int(r.get('expected_count', 0))}"
                    ),
                }
            )
    for uid, mm in extra[:1000]:
        mismatches.append(
            {
                "type": "extra_selected_key",
                "symbol": sym,
                "candidate_uid": uid,
                "model_month": mm,
                "runtime_ts": pd.NaT,
                "research_ts": pd.NaT,
                "detail": "present in runtime selected set but absent in research selected set",
            }
        )

    # Timestamp-level match (only meaningful when audit timestamps are in run window).
    ts_match_ratio = 0.0
    lag_diag = {
        "lag_sample_count": 0.0,
        "best_lag_minutes": float("nan"),
        "median_abs_gap_sec": float("nan"),
        "p95_abs_gap_sec": float("nan"),
        "match_ratio_lag0": 0.0,
        "match_ratio_best_lag": 0.0,
    }
    if len(research_sel) > 0 and len(audit_window) > 0:
        audit_ts_col = "close_ts" if audit_window_source == "close_ts" else "event_ts"
        left = research_sel[["close_ts", "candidate_uid", "model_month"]].copy()
        right = audit_window[[audit_ts_col, "candidate_uid", "model_month"]].copy()
        right = right.rename(columns={audit_ts_col: "audit_ts"})

        left["close_ts"] = _asof_ts_ns(left["close_ts"])
        right["audit_ts"] = _asof_ts_ns(right["audit_ts"])
        left["candidate_uid"] = left["candidate_uid"].astype(str)
        right["candidate_uid"] = right["candidate_uid"].astype(str)
        left["model_month"] = left["model_month"].astype(str)
        right["model_month"] = right["model_month"].astype(str)

        left = left[left["close_ts"].notna()].copy()
        right = right[right["audit_ts"].notna()].copy()
        # Restrict right-side rows to keys that actually appear in research selections.
        if len(left) > 0 and len(right) > 0:
            key_df = left[["candidate_uid", "model_month"]].drop_duplicates()
            right = right.merge(key_df, on=["candidate_uid", "model_month"], how="inner")

        left = left.sort_values("close_ts")
        right = right.sort_values("audit_ts")

        if len(left) > 0 and len(right) > 0:
            tol = pd.Timedelta(seconds=max(0.0, float(timestamp_tolerance_sec)))
            matched = pd.merge_asof(
                left,
                right,
                left_on="close_ts",
                right_on="audit_ts",
                by=["candidate_uid", "model_month"],
                tolerance=tol,
                direction="nearest",
            )
            ts_match_ratio = float(matched["audit_ts"].notna().sum()) / float(len(left))
            lag_diag = _timestamp_alignment_diagnostics(
                left=left,
                right=right,
                left_ts_col="close_ts",
                right_ts_col="audit_ts",
                key_cols=["candidate_uid", "model_month"],
                tolerance_sec=float(timestamp_tolerance_sec),
            )

    _add_check(
        checks,
        check_id="TIMESTAMP_MATCH_RATIO_GE_0_80",
        ok=ts_match_ratio >= 0.80,
        severity="medium",
        metric="timestamp_match_ratio",
        value=float(ts_match_ratio),
        expected=0.80,
        operator=">=",
        detail=(
            f"tolerance_sec={timestamp_tolerance_sec} audit_window_source={audit_window_source}; "
            "low ratio often indicates event_ts clock mismatch"
        ),
    )
    lag_samples = int(lag_diag["lag_sample_count"])
    lag_thresh_min = 1.0
    gap_thresh_sec = max(60.0, float(timestamp_tolerance_sec) * 2.0)
    lag_checks_required = lag_samples >= 20
    _add_check(
        checks,
        check_id="TIMESTAMP_BEST_LAG_MIN_ABS_LE_1",
        ok=(abs(float(lag_diag["best_lag_minutes"])) <= lag_thresh_min) if lag_checks_required else True,
        severity="high" if lag_checks_required else "medium",
        metric="timestamp_best_lag_minutes",
        value=float(lag_diag["best_lag_minutes"]),
        expected=lag_thresh_min if lag_checks_required else "informational",
        operator="<=" if lag_checks_required else "info",
        detail=(
            f"sample_count={lag_samples}; tolerance_sec={timestamp_tolerance_sec}; "
            "lag from nearest-key timestamp alignment"
        ),
    )
    _add_check(
        checks,
        check_id="TIMESTAMP_MEDIAN_ABS_GAP_SEC_LE_THRESHOLD",
        ok=(float(lag_diag["median_abs_gap_sec"]) <= gap_thresh_sec) if lag_checks_required else True,
        severity="high" if lag_checks_required else "medium",
        metric="timestamp_median_abs_gap_sec",
        value=float(lag_diag["median_abs_gap_sec"]),
        expected=gap_thresh_sec if lag_checks_required else "informational",
        operator="<=" if lag_checks_required else "info",
        detail=f"sample_count={lag_samples}; threshold=max(60,2*tolerance_sec)",
    )
    _add_check(
        checks,
        check_id="TIMESTAMP_MATCH_RATIO_BEST_LAG_GE_0_90",
        ok=(float(lag_diag["match_ratio_best_lag"]) >= 0.90) if lag_checks_required else True,
        severity="medium",
        metric="timestamp_match_ratio_best_lag",
        value=float(lag_diag["match_ratio_best_lag"]),
        expected=0.90 if lag_checks_required else "informational",
        operator=">=" if lag_checks_required else "info",
        detail=f"sample_count={lag_samples}; compare with lag0 metric for timezone drift",
    )

    dup_broker = 0
    if not trades_window.empty:
        bp = trades_window.get("broker_pos_id", pd.Series(dtype=str)).astype(str).str.strip()
        dup_broker = int(bp[bp != ""].duplicated().sum())
    _add_check(
        checks,
        check_id="BROKER_POS_ID_DUPLICATES_EQ_0",
        ok=dup_broker == 0,
        severity="medium",
        metric="broker_pos_id_duplicate_count",
        value=int(dup_broker),
        expected=0,
        operator="==",
        detail="computed on trades_window non-empty broker_pos_id",
    )

    checks_df = pd.DataFrame([c.__dict__ for c in checks])
    if checks_df.empty:
        checks_df = pd.DataFrame(
            columns=["check_id", "status", "severity", "metric", "value", "expected", "operator", "detail"]
        )

    mismatches_df = pd.DataFrame(mismatches)
    if mismatches_df.empty:
        mismatches_df = pd.DataFrame(
            columns=["type", "symbol", "candidate_uid", "model_month", "runtime_ts", "research_ts", "detail"]
        )

    failed_hc = checks_df[
        (checks_df["status"] == "fail")
        & (checks_df["severity"].astype(str).str.lower().isin({"critical", "high"}))
    ]
    overall_pass = len(failed_hc) == 0

    summary = pd.DataFrame(
        [
            {
                "symbol": sym,
                "runtime_db_path": str(runtime_db_path),
                "predictions_parquet": str(predictions_parquet),
                "history_dir": str(history_dir) if history_dir is not None else "",
                "start_ts": start.isoformat() if start is not None else "",
                "end_ts": end.isoformat() if end is not None else "",
                "strict_window": bool(strict_window),
                "history_filter_applied": bool(history_filter_applied),
                "hist_lock_month_coverage_ratio": float(history_filter_month_coverage_ratio),
                "research_selected_rows_window_pre_filter": int(history_filter_selected_rows_before),
                "research_selected_rows_window_post_filter": int(history_filter_selected_rows_after),
                "trades_symbol_rows": int(len(trades)),
                "trades_window_rows": int(len(trades_window)),
                "audit_symbol_rows": int(len(audit)),
                "audit_window_rows": int(len(audit_window)),
                "runtime_raw_tick_rows_window": int(runtime_raw_tick_rows),
                "hist_tick_rows_window": int(hist_tick_rows),
                "raw_tick_coverage_ratio_runtime_vs_hist": (
                    float(raw_tick_coverage_ratio)
                    if pd.notna(raw_tick_coverage_ratio)
                    else float("nan")
                ),
                "runtime_median_intertick_ms": (
                    float(runtime_raw_median_intertick_ms)
                    if pd.notna(runtime_raw_median_intertick_ms)
                    else float("nan")
                ),
                "hist_median_intertick_ms": (
                    float(hist_median_intertick_ms)
                    if pd.notna(hist_median_intertick_ms)
                    else float("nan")
                ),
                "median_intertick_ratio_runtime_vs_hist": (
                    float(intertick_ratio_runtime_vs_hist)
                    if pd.notna(intertick_ratio_runtime_vs_hist)
                    else float("nan")
                ),
                "research_window_rows": int(len(research_window)),
                "research_selected_rows_window": int(len(research_sel)),
                "selected_key_missing_count": int(len(missing)),
                "selected_key_extra_count": int(len(extra)),
                "selected_key_jaccard": float(jaccard),
                "selected_count_missing_rows": int(count_missing_rows),
                "selected_count_extra_rows": int(count_extra_rows),
                "selected_count_ratio_runtime_vs_research": float(count_ratio),
                "audit_event_window_ratio": float(audit_window_ratio),
                "timestamp_match_ratio": float(ts_match_ratio),
                "timestamp_best_lag_minutes": float(lag_diag["best_lag_minutes"]),
                "timestamp_median_abs_gap_sec": float(lag_diag["median_abs_gap_sec"]),
                "timestamp_p95_abs_gap_sec": float(lag_diag["p95_abs_gap_sec"]),
                "timestamp_match_ratio_lag0": float(lag_diag["match_ratio_lag0"]),
                "timestamp_match_ratio_best_lag": float(lag_diag["match_ratio_best_lag"]),
                "timestamp_lag_sample_count": int(lag_samples),
                "overall_pass": bool(overall_pass),
                "evaluated_at_utc": now_utc,
            }
        ]
    )

    out_checks_csv.parent.mkdir(parents=True, exist_ok=True)
    out_mismatches_csv.parent.mkdir(parents=True, exist_ok=True)
    report_out.parent.mkdir(parents=True, exist_ok=True)

    checks_df.to_csv(out_checks_csv, index=False)
    mismatches_df.to_csv(out_mismatches_csv, index=False)

    fail_preview = checks_df[checks_df["status"] == "fail"].copy()
    if not fail_preview.empty:
        fail_preview = fail_preview[["check_id", "severity", "metric", "value", "expected", "detail"]]

    mismatch_preview = mismatches_df.head(30).copy()
    report = [
        "# cTrader vs Research Reconciliation",
        "",
        f"- symbol: `{sym}`",
        f"- runtime_db: `{runtime_db_path}`",
        f"- predictions_parquet: `{predictions_parquet}`",
        f"- history_dir: `{history_dir if history_dir is not None else ''}`",
        f"- strict_window: `{strict_window}`",
        f"- timestamp_tolerance_sec: `{timestamp_tolerance_sec}`",
        "",
        "## Summary",
        _table(summary),
        "",
        "## Failed Checks",
        _table(fail_preview),
        "",
        "## Mismatch Preview",
        _table(mismatch_preview),
        "",
        "## All Checks",
        _table(checks_df),
        "",
    ]
    report_out.write_text("\n".join(report), encoding="utf-8")
    return checks_df, mismatches_df


def main() -> None:
    p = argparse.ArgumentParser(description="Reconcile cTrader runtime signals vs research")
    p.add_argument("--symbol", required=True)
    p.add_argument("--runtime-db", default="data/db/behemoth_runtime.db")
    p.add_argument("--predictions-parquet", required=True)
    p.add_argument("--history-dir", default="")
    p.add_argument("--tick-root", default="/Users/danielfisher/Desktop/tick")
    p.add_argument("--start-ts", default="")
    p.add_argument("--end-ts", default="")
    p.add_argument("--strict-window", default="true", choices=["true", "false"])
    p.add_argument("--timestamp-tolerance-sec", type=float, default=2.0)
    p.add_argument(
        "--out-checks-csv",
        default="data/analysis/backtest_reconcile/ctrader_vs_research_checks.csv",
    )
    p.add_argument(
        "--out-mismatches-csv",
        default="data/analysis/backtest_reconcile/ctrader_vs_research_mismatches.csv",
    )
    p.add_argument(
        "--report-out",
        default="docs/analysis/ctrader_vs_research_reconciliation.md",
    )
    args = p.parse_args()

    checks, mismatches = run(
        symbol=str(args.symbol).upper().strip(),
        runtime_db_path=Path(str(args.runtime_db)),
        predictions_parquet=Path(str(args.predictions_parquet)),
        history_dir=(Path(str(args.history_dir)) if str(args.history_dir).strip() else None),
        tick_root=(Path(str(args.tick_root)) if str(args.tick_root).strip() else None),
        start_ts=str(args.start_ts).strip() or None,
        end_ts=str(args.end_ts).strip() or None,
        strict_window=(str(args.strict_window).strip().lower() == "true"),
        timestamp_tolerance_sec=float(args.timestamp_tolerance_sec),
        out_checks_csv=Path(str(args.out_checks_csv)),
        out_mismatches_csv=Path(str(args.out_mismatches_csv)),
        report_out=Path(str(args.report_out)),
    )

    failed_hc = checks[
        (checks["status"].astype(str) == "fail")
        & (checks["severity"].astype(str).str.lower().isin({"critical", "high"}))
    ]

    print(f"wrote checks: {args.out_checks_csv} rows={len(checks)}")
    print(f"wrote mismatches: {args.out_mismatches_csv} rows={len(mismatches)}")
    print(f"wrote report: {args.report_out}")
    print(f"high_or_critical_failures={len(failed_hc)}")
    if len(failed_hc) > 0:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
