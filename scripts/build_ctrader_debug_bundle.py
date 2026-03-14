#!/usr/bin/env python3
"""Build a repo-side debug bundle for a cTrader backtest session."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd
try:
    from scripts.replay_histdata_cbot_testclient import (
        _build_signal_feature_diff,
        _build_signal_gap_analysis,
        _load_expected_selected_detail_rows,
        _load_predict_trace_rows,
    )
except ModuleNotFoundError:
    from replay_histdata_cbot_testclient import (
        _build_signal_feature_diff,
        _build_signal_gap_analysis,
        _load_expected_selected_detail_rows,
        _load_predict_trace_rows,
    )


LOG_LINE_RE = re.compile(
    r"^(?P<ts>\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}(?:\.\d{3})?) \| [^|]+ \| (?P<msg>.*)$"
)
REPO_ROOT = Path(__file__).resolve().parents[1]


@dataclass
class BundleOutputs:
    joined_timeline_csv: Path
    joined_timeline_md: Path
    debug_summary_csv: Path
    offline_compare_csv: Path
    offline_compare_exact_csv: Path
    offline_compare_tolerant_csv: Path
    signal_gap_analysis_csv: Path
    signal_feature_diff_csv: Path
    execution_gap_analysis_csv: Path


_COMPARE_TOLERANCE_SEC = 30.0


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _safe_to_utc(series: pd.Series) -> pd.Series:
    try:
        return pd.to_datetime(series, utc=True, errors="coerce", format="mixed")
    except TypeError:
        return pd.to_datetime(series, utc=True, errors="coerce")


def _load_http_trace(path: Path) -> pd.DataFrame:
    if not str(path).strip() or not path.exists() or not path.is_file():
        return pd.DataFrame(
            columns=[
                "ts_utc",
                "endpoint",
                "phase",
                "run_id",
                "symbol",
                "status_code",
                "request",
                "response",
                "extra",
            ]
        )
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        txt = line.strip()
        if not txt:
            continue
        try:
            rows.append(json.loads(txt))
        except Exception:
            continue
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    if "ts_utc" in df.columns:
        df["ts_utc"] = _safe_to_utc(df["ts_utc"])
    return df


def _table_columns(con: duckdb.DuckDBPyConnection, table_name: str) -> set[str]:
    rows = con.execute(
        """
        SELECT lower(column_name)
        FROM information_schema.columns
        WHERE lower(table_name) = ?
        """,
        [str(table_name).lower()],
    ).fetchall()
    return {str(r[0]).lower() for r in rows}


def _safe_query(con: duckdb.DuckDBPyConnection, sql: str, params: list[Any]) -> pd.DataFrame:
    try:
        return con.execute(sql, params).fetchdf()
    except Exception:
        return pd.DataFrame()


def _load_runtime_raw_ticks(con: duckdb.DuckDBPyConnection, symbol: str, run_id: str | None) -> pd.DataFrame:
    cols = _table_columns(con, "raw_ticks")
    if not cols:
        return pd.DataFrame()
    ts_col = next((c for c in ["tick_ts", "timestamp_utc", "timestamp", "ts"] if c in cols), "")
    if not ts_col:
        return pd.DataFrame()
    run_expr = "run_id" if "run_id" in cols else "NULL::VARCHAR AS run_id"
    client_expr = "client_tick_seq" if "client_tick_seq" in cols else "NULL::BIGINT AS client_tick_seq"
    sql = f"""
        SELECT
            try_cast({ts_col} AS TIMESTAMP WITH TIME ZONE) AS tick_ts,
            symbol,
            bid,
            ask,
            spread,
            tick_volume,
            source,
            {client_expr},
            {run_expr}
        FROM raw_ticks
        WHERE upper(symbol) = ?
    """
    params: list[Any] = [str(symbol).upper().strip()]
    if "run_id" in cols and str(run_id or "").strip():
        sql += " AND coalesce(run_id, '') = ?"
        params.append(str(run_id).strip())
    df = _safe_query(con, sql, params)
    if not df.empty:
        df["tick_ts"] = _safe_to_utc(df.get("tick_ts", pd.Series(dtype=object)))
    return df


def _load_runtime_audit(con: duckdb.DuckDBPyConnection, symbol: str, run_id: str | None) -> pd.DataFrame:
    cols = _table_columns(con, "audit_logs")
    if not cols:
        return pd.DataFrame()
    run_expr = "run_id" if "run_id" in cols else "NULL::VARCHAR AS run_id"
    close_expr = "close_ts" if "close_ts" in cols else "NULL::TIMESTAMP WITH TIME ZONE AS close_ts"
    sql = f"""
        SELECT
            event_ts,
            {close_expr},
            symbol,
            candidate_uid,
            pred_prob,
            threshold,
            model_month,
            {run_expr}
        FROM audit_logs
        WHERE upper(symbol) = ?
    """
    params: list[Any] = [str(symbol).upper().strip()]
    if "run_id" in cols and str(run_id or "").strip():
        sql += " AND coalesce(run_id, '') = ?"
        params.append(str(run_id).strip())
    df = _safe_query(con, sql, params)
    if not df.empty:
        df["event_ts"] = _safe_to_utc(df.get("event_ts", pd.Series(dtype=object)))
        df["close_ts"] = _safe_to_utc(df.get("close_ts", pd.Series(dtype=object)))
    return df


def _load_runtime_trades(con: duckdb.DuckDBPyConnection, symbol: str, run_id: str | None) -> pd.DataFrame:
    cols = _table_columns(con, "trades")
    if not cols:
        return pd.DataFrame()
    run_expr = "run_id" if "run_id" in cols else "NULL::VARCHAR AS run_id"
    sql = f"""
        SELECT
            internal_trade_id,
            broker_pos_id,
            symbol,
            candidate_uid,
            side,
            entry_price,
            entry_ts,
            exit_price,
            exit_ts,
            pnl_pips,
            status,
            {run_expr}
        FROM trades
        WHERE upper(symbol) = ?
    """
    params: list[Any] = [str(symbol).upper().strip()]
    if "run_id" in cols and str(run_id or "").strip():
        sql += " AND coalesce(run_id, '') = ?"
        params.append(str(run_id).strip())
    df = _safe_query(con, sql, params)
    if not df.empty:
        df["entry_ts"] = _safe_to_utc(df.get("entry_ts", pd.Series(dtype=object)))
        df["exit_ts"] = _safe_to_utc(df.get("exit_ts", pd.Series(dtype=object)))
    return df


def _load_ctrader_events(path: Path) -> pd.DataFrame:
    if not str(path).strip() or not path.exists() or not path.is_file():
        return pd.DataFrame()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return pd.DataFrame()
    if not isinstance(raw, list):
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "ts_utc": pd.to_datetime(item.get("time"), unit="ms", utc=True, errors="coerce"),
                "event": str(item.get("event", "")).strip(),
                "position_id": str(item.get("positionId", "")).strip(),
                "side": str(item.get("type", "")).strip(),
                "entry_price": pd.to_numeric(item.get("entryPrice"), errors="coerce"),
                "exit_price": pd.to_numeric(item.get("closePrice"), errors="coerce"),
                "pips": pd.to_numeric(item.get("pips"), errors="coerce"),
                "detail_json": json.dumps(item, sort_keys=True),
            }
        )
    return pd.DataFrame(rows)


def _load_cbot_log(path: Path) -> pd.DataFrame:
    if not str(path).strip() or not path.exists() or not path.is_file():
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = LOG_LINE_RE.match(line.strip())
        if not m:
            continue
        msg = str(m.group("msg")).strip()
        tag = ""
        if msg.startswith("[") and "]" in msg:
            tag = msg[1 : msg.index("]")]
        rows.append(
            {
                "ts_utc": pd.to_datetime(m.group("ts"), utc=True, errors="coerce"),
                "event_type": tag.lower().replace(" ", "_") if tag else "log",
                "message": msg,
            }
        )
    return pd.DataFrame(rows)


def _detail_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, default=str)


def _timeline_from_http_trace(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    out = pd.DataFrame(
        {
            "ts_utc": df.get("ts_utc", pd.Series(dtype="datetime64[ns, UTC]")),
            "source": "http_trace",
            "event_type": df.get("endpoint", pd.Series(dtype=str)).astype(str).str.replace("/", "_", regex=False).str.strip("_"),
            "symbol": df.get("symbol", pd.Series(dtype=str)),
            "run_id": df.get("run_id", pd.Series(dtype=str)),
            "candidate_uid": df.get("request", pd.Series(dtype=object)).map(
                lambda x: x.get("candidate_uid") if isinstance(x, dict) else None
            ),
            "broker_pos_id": df.get("request", pd.Series(dtype=object)).map(
                lambda x: x.get("broker_pos_id") if isinstance(x, dict) else None
            ),
            "client_tick_seq": df.get("request", pd.Series(dtype=object)).map(
                lambda x: x.get("client_tick_seq") if isinstance(x, dict) else None
            ),
            "http_endpoint": df.get("endpoint", pd.Series(dtype=str)),
            "http_phase": df.get("phase", pd.Series(dtype=str)),
            "status": df.get("status_code", pd.Series(dtype=object)).astype("string"),
            "detail_json": df.apply(
                lambda row: _detail_json(
                    {
                        "request": row.get("request"),
                        "response": row.get("response"),
                        "extra": row.get("extra"),
                    }
                ),
                axis=1,
            ),
        }
    )
    return out


def _timeline_from_raw_ticks(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    return pd.DataFrame(
        {
            "ts_utc": df.get("tick_ts", pd.Series(dtype="datetime64[ns, UTC]")),
            "source": "runtime_db",
            "event_type": "raw_tick",
            "symbol": df.get("symbol", pd.Series(dtype=str)),
            "run_id": df.get("run_id", pd.Series(dtype=str)),
            "candidate_uid": None,
            "broker_pos_id": None,
            "client_tick_seq": df.get("client_tick_seq", pd.Series(dtype=object)),
            "http_endpoint": None,
            "http_phase": None,
            "status": "accepted",
            "detail_json": df.apply(
                lambda row: _detail_json(
                    {
                        "bid": row.get("bid"),
                        "ask": row.get("ask"),
                        "spread": row.get("spread"),
                        "tick_volume": row.get("tick_volume"),
                        "source": row.get("source"),
                    }
                ),
                axis=1,
            ),
        }
    )


def _timeline_from_audit(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    return pd.DataFrame(
        {
            "ts_utc": df.get("event_ts", pd.Series(dtype="datetime64[ns, UTC]")),
            "source": "runtime_db",
            "event_type": "predict_audit",
            "symbol": df.get("symbol", pd.Series(dtype=str)),
            "run_id": df.get("run_id", pd.Series(dtype=str)),
            "candidate_uid": df.get("candidate_uid", pd.Series(dtype=str)),
            "broker_pos_id": None,
            "client_tick_seq": None,
            "http_endpoint": "/predict",
            "http_phase": "audit",
            "status": "logged",
            "detail_json": df.apply(
                lambda row: _detail_json(
                    {
                        "close_ts": row.get("close_ts"),
                        "pred_prob": row.get("pred_prob"),
                        "threshold": row.get("threshold"),
                        "model_month": row.get("model_month"),
                    }
                ),
                axis=1,
            ),
        }
    )


def _timeline_from_trades(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    for row in df.to_dict(orient="records"):
        rows.append(
            {
                "ts_utc": row.get("entry_ts"),
                "source": "runtime_db",
                "event_type": "trade_open",
                "symbol": row.get("symbol"),
                "run_id": row.get("run_id"),
                "candidate_uid": row.get("candidate_uid"),
                "broker_pos_id": row.get("broker_pos_id"),
                "client_tick_seq": None,
                "http_endpoint": "/trades/open",
                "http_phase": "db",
                "status": "open",
                "detail_json": _detail_json(
                    {
                        "side": row.get("side"),
                        "entry_price": row.get("entry_price"),
                        "internal_trade_id": row.get("internal_trade_id"),
                    }
                ),
            }
        )
        if pd.notna(row.get("exit_ts")):
            rows.append(
                {
                    "ts_utc": row.get("exit_ts"),
                    "source": "runtime_db",
                    "event_type": "trade_close",
                    "symbol": row.get("symbol"),
                    "run_id": row.get("run_id"),
                    "candidate_uid": row.get("candidate_uid"),
                    "broker_pos_id": row.get("broker_pos_id"),
                    "client_tick_seq": None,
                    "http_endpoint": "/trades/update",
                    "http_phase": "db",
                    "status": row.get("status"),
                    "detail_json": _detail_json(
                        {
                            "exit_price": row.get("exit_price"),
                            "pnl_pips": row.get("pnl_pips"),
                        }
                    ),
                }
            )
    return pd.DataFrame(rows)


def _timeline_from_ctrader_events(df: pd.DataFrame, symbol: str, run_id: str | None) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    return pd.DataFrame(
        {
            "ts_utc": df.get("ts_utc", pd.Series(dtype="datetime64[ns, UTC]")),
            "source": "ctrader_events",
            "event_type": df.get("event", pd.Series(dtype=str)).astype(str).str.lower().str.replace(" ", "_", regex=False),
            "symbol": str(symbol).upper().strip(),
            "run_id": run_id,
            "candidate_uid": None,
            "broker_pos_id": df.get("position_id", pd.Series(dtype=str)),
            "client_tick_seq": None,
            "http_endpoint": None,
            "http_phase": None,
            "status": df.get("side", pd.Series(dtype=str)),
            "detail_json": df.get("detail_json", pd.Series(dtype=str)),
        }
    )


def _timeline_from_cbot_log(df: pd.DataFrame, symbol: str, run_id: str | None) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    return pd.DataFrame(
        {
            "ts_utc": df.get("ts_utc", pd.Series(dtype="datetime64[ns, UTC]")),
            "source": "cbot_log",
            "event_type": df.get("event_type", pd.Series(dtype=str)),
            "symbol": str(symbol).upper().strip(),
            "run_id": run_id,
            "candidate_uid": None,
            "broker_pos_id": None,
            "client_tick_seq": None,
            "http_endpoint": None,
            "http_phase": None,
            "status": "info",
            "detail_json": df.apply(lambda row: _detail_json({"message": row.get("message")}), axis=1),
        }
    )


def _load_expected_offline_compare(session: dict[str, Any], bundle_dir: Path) -> pd.DataFrame:
    symbol = str(session.get("symbol", "")).upper().strip()
    start_ts = pd.to_datetime(session.get("start_ts"), utc=True, errors="coerce")
    end_ts = pd.to_datetime(session.get("end_ts"), utc=True, errors="coerce")
    detail_path = Path(
        str(
            session.get(
                "offline_stop_limit_detail_csv",
                bundle_dir.parents[2]
                / "tick_opportunity_mining"
                / "stop_limit_tickfill_fullcap"
                / f"{symbol}_stop_limit_tickfill_detail.csv",
            )
        )
    )
    if not detail_path.exists():
        return pd.DataFrame(
            [{"status": "missing_expected_detail", "candidate_uid": None, "close_ts": None}]
        )
    expected = pd.read_csv(detail_path)
    expected["close_ts"] = _safe_to_utc(expected.get("close_ts", pd.Series(dtype=object)))
    if pd.notna(start_ts) and pd.notna(end_ts):
        expected = expected[(expected["close_ts"] >= start_ts) & (expected["close_ts"] < end_ts)].copy()
    return expected


def _filter_expected_to_historical_lock_universe(
    expected: pd.DataFrame,
    *,
    session: dict[str, Any],
) -> pd.DataFrame:
    if expected.empty or "candidate_uid" not in expected.columns or "close_ts" not in expected.columns:
        return expected
    history_dir = Path(
        str(
            session.get(
                "history_dir",
                Path("configs/research/governance/oco_history"),
            )
        )
    )
    if not history_dir.exists():
        return expected
    try:
        from src.behemoth.core.historical_registry import HistoricalCandidateRegistry
    except Exception:
        return expected

    reg = HistoricalCandidateRegistry.load(history_dir)
    symbol = str(session.get("symbol", "")).upper().strip()
    allowed_by_month: dict[str, set[str]] = {}
    for month in reg.months_for_symbol(symbol):
        entry = reg.get_entry(symbol, month)
        if entry is None:
            continue
        allowed_by_month[month] = {
            f"oco|{symbol}|{cand.bar_ticks}|h{cand.horizon}|{cand.candidate_uid}"
            for cand in entry.candidates
        }

    if not allowed_by_month:
        return expected

    out = expected.copy()
    out["close_ts"] = _safe_to_utc(out.get("close_ts", pd.Series(dtype=object)))
    out["close_month"] = out["close_ts"].dt.strftime("%Y-%m")
    mask = out.apply(
        lambda row: str(row.get("candidate_uid", "")) in allowed_by_month.get(str(row.get("close_month", "")), set()),
        axis=1,
    )
    out = out.loc[mask].copy()
    return out.drop(columns=["close_month"], errors="ignore")


def _build_offline_compare(
    *,
    session: dict[str, Any],
    bundle_dir: Path,
    audit_df: pd.DataFrame,
    trades_df: pd.DataFrame,
) -> pd.DataFrame:
    return _build_offline_compare_tolerant(
        session=session,
        bundle_dir=bundle_dir,
        audit_df=audit_df,
        trades_df=trades_df,
    )


def _prepare_expected_compare(expected: pd.DataFrame) -> pd.DataFrame:
    out = expected.copy()
    out["candidate_uid"] = out.get("candidate_uid", pd.Series(dtype=str)).astype(str)
    out["close_ts"] = _safe_to_utc(out.get("close_ts", pd.Series(dtype=object)))
    out["touch_open_ts"] = _safe_to_utc(
        out.get("touch_open_ts", out.get("entry_ts", pd.Series(dtype=object)))
    )
    return out


def _month_tags_iso_between(start: pd.Timestamp, end: pd.Timestamp) -> list[str]:
    if pd.isna(start) or pd.isna(end):
        return []
    start0 = start.tz_convert("UTC").tz_localize(None) if start.tzinfo is not None else start
    end_inclusive = end - pd.Timedelta(microseconds=1)
    if end_inclusive < start:
        return []
    end0 = (
        end_inclusive.tz_convert("UTC").tz_localize(None)
        if end_inclusive.tzinfo is not None
        else end_inclusive
    )
    pr = pd.period_range(start=start0.to_period("M"), end=end0.to_period("M"), freq="M")
    return [str(p) for p in pr]


def _load_expected_selected_detail_for_session(session: dict[str, Any]) -> pd.DataFrame:
    symbol = str(session.get("symbol", "")).upper().strip()
    start_ts = pd.to_datetime(session.get("start_ts"), utc=True, errors="coerce")
    end_ts = pd.to_datetime(session.get("end_ts"), utc=True, errors="coerce")
    if not symbol or pd.isna(start_ts) or pd.isna(end_ts):
        return pd.DataFrame(
            columns=["candidate_uid", "close_ts", "pred_prob", "threshold_exec", "selected_exec"]
        )
    history_dir = Path(
        str(
            session.get(
                "history_dir",
                REPO_ROOT / "configs" / "research" / "governance" / "oco_history",
            )
        )
    )
    if not history_dir.exists():
        return pd.DataFrame(
            columns=["candidate_uid", "close_ts", "pred_prob", "threshold_exec", "selected_exec"]
        )
    try:
        from src.behemoth.core.historical_registry import HistoricalCandidateRegistry
    except Exception:
        return pd.DataFrame(
            columns=["candidate_uid", "close_ts", "pred_prob", "threshold_exec", "selected_exec"]
        )

    reg = HistoricalCandidateRegistry.load(history_dir)
    parts: list[pd.DataFrame] = []
    for month in _month_tags_iso_between(start_ts, end_ts):
        binding = reg.get_model_binding(symbol, month)
        if not binding:
            continue
        pred_path = Path(str(binding.get("predictions_path", "")).strip())
        if not pred_path.exists():
            continue
        part = _load_expected_selected_detail_rows(
            predictions_parquet=pred_path,
            symbol=symbol,
            start=start_ts,
            end=end_ts,
        )
        if not part.empty:
            parts.append(part)
    if not parts:
        return pd.DataFrame(
            columns=["candidate_uid", "close_ts", "pred_prob", "threshold_exec", "selected_exec"]
        )
    out = pd.concat(parts, ignore_index=True).drop_duplicates(
        subset=["candidate_uid", "close_ts"], keep="first"
    )
    out["close_ts"] = _safe_to_utc(out.get("close_ts", pd.Series(dtype=object)))
    return out.sort_values(["close_ts", "candidate_uid"]).reset_index(drop=True)


def _runtime_predict_keys(audit_df: pd.DataFrame) -> pd.DataFrame:
    if audit_df.empty:
        return pd.DataFrame(
            {
                "candidate_uid": pd.Series(dtype=str),
                "close_ts": pd.Series(dtype="datetime64[ns, UTC]"),
                "event_ts": pd.Series(dtype="datetime64[ns, UTC]"),
            }
        )
    out = audit_df.copy()
    out["candidate_uid"] = out.get("candidate_uid", pd.Series(dtype=str)).astype(str)
    out["close_ts"] = _safe_to_utc(out.get("close_ts", pd.Series(dtype=object)))
    out["event_ts"] = _safe_to_utc(out.get("event_ts", pd.Series(dtype=object)))
    out = out.dropna(subset=["candidate_uid", "close_ts"]).copy()
    out = out.sort_values(["candidate_uid", "close_ts", "event_ts"]).drop_duplicates(
        subset=["candidate_uid", "close_ts"],
        keep="first",
    )
    return out.reset_index(drop=True)[["candidate_uid", "close_ts", "event_ts"]]


def _runtime_trade_keys(trades_df: pd.DataFrame) -> pd.DataFrame:
    if trades_df.empty:
        return pd.DataFrame(
            {
                "candidate_uid": pd.Series(dtype=str),
                "entry_ts": pd.Series(dtype="datetime64[ns, UTC]"),
                "broker_pos_id": pd.Series(dtype=str),
                "status": pd.Series(dtype=str),
                "side": pd.Series(dtype=str),
            }
        )
    out = trades_df.copy()
    out["candidate_uid"] = out.get("candidate_uid", pd.Series(dtype=str)).astype(str)
    out["entry_ts"] = _safe_to_utc(out.get("entry_ts", pd.Series(dtype=object)))
    out = out.dropna(subset=["candidate_uid", "entry_ts"]).copy()
    out = out.sort_values(["candidate_uid", "entry_ts", "broker_pos_id"]).reset_index(drop=True)
    cols = [col for col in ["candidate_uid", "entry_ts", "broker_pos_id", "status", "side"] if col in out.columns]
    return out[cols]


def _nearest_match(
    *,
    expected: pd.DataFrame,
    runtime: pd.DataFrame,
    expected_ts_col: str,
    runtime_ts_col: str,
    tolerance_sec: float,
) -> pd.DataFrame:
    if expected.empty or runtime.empty:
        return pd.DataFrame(columns=["expected_idx", "runtime_idx", "delta_sec"])
    tol = pd.Timedelta(seconds=float(tolerance_sec))
    left = expected.reset_index(drop=True).copy()
    right = runtime.reset_index(drop=True).copy()
    left["expected_idx"] = left.index.astype(int)
    right["runtime_idx"] = right.index.astype(int)
    pairs: list[dict[str, Any]] = []
    for candidate_uid, exp_group in left.groupby("candidate_uid", dropna=False):
        rt_group = right[right["candidate_uid"] == candidate_uid]
        if rt_group.empty:
            continue
        for _, exp_row in exp_group.iterrows():
            exp_ts = exp_row.get(expected_ts_col)
            if pd.isna(exp_ts):
                continue
            deltas = (rt_group[runtime_ts_col] - exp_ts).abs()
            eligible = rt_group.loc[deltas <= tol].copy()
            if eligible.empty:
                continue
            eligible["delta_sec"] = (
                (eligible[runtime_ts_col] - exp_ts).abs().dt.total_seconds()
            )
            for _, rt_row in eligible.iterrows():
                pairs.append(
                    {
                        "expected_idx": int(exp_row["expected_idx"]),
                        "runtime_idx": int(rt_row["runtime_idx"]),
                        "delta_sec": float(rt_row["delta_sec"]),
                    }
                )
    if not pairs:
        return pd.DataFrame(columns=["expected_idx", "runtime_idx", "delta_sec"])
    pair_df = pd.DataFrame(pairs).sort_values(["delta_sec", "expected_idx", "runtime_idx"])
    used_expected: set[int] = set()
    used_runtime: set[int] = set()
    chosen: list[dict[str, Any]] = []
    for row in pair_df.to_dict(orient="records"):
        exp_idx = int(row["expected_idx"])
        rt_idx = int(row["runtime_idx"])
        if exp_idx in used_expected or rt_idx in used_runtime:
            continue
        used_expected.add(exp_idx)
        used_runtime.add(rt_idx)
        chosen.append(row)
    return pd.DataFrame(chosen)


def _build_offline_compare_exact(
    *,
    session: dict[str, Any],
    bundle_dir: Path,
    audit_df: pd.DataFrame,
    trades_df: pd.DataFrame,
) -> pd.DataFrame:
    expected = _load_expected_offline_compare(session, bundle_dir)
    expected = _filter_expected_to_historical_lock_universe(expected, session=session)
    if "status" in expected.columns and "candidate_uid" in expected.columns and len(expected) == 1:
        return expected

    expected = _prepare_expected_compare(expected)
    audit = _runtime_predict_keys(audit_df)
    trades = _runtime_trade_keys(trades_df)
    predicted = (
        audit.groupby(["candidate_uid", "close_ts"], dropna=False)
        .size()
        .rename("runtime_predict_count")
        .reset_index()
    )
    executed = (
        trades.groupby(["candidate_uid", "entry_ts"], dropna=False)
        .agg(
            runtime_trade_count=("broker_pos_id", "count"),
            runtime_trade_status=("status", "last"),
            runtime_trade_side=("side", "last"),
        )
        .reset_index()
    )
    merged = expected.merge(predicted, how="left", on=["candidate_uid", "close_ts"])
    merged = merged.merge(
        executed,
        how="left",
        left_on=["candidate_uid", "touch_open_ts"],
        right_on=["candidate_uid", "entry_ts"],
    )
    merged["runtime_predict_count"] = merged["runtime_predict_count"].fillna(0).astype(int)
    merged["runtime_trade_count"] = merged["runtime_trade_count"].fillna(0).astype(int)
    merged["runtime_predicted"] = merged["runtime_predict_count"] > 0
    merged["runtime_executed"] = merged["runtime_trade_count"] > 0
    merged["compare_mode"] = "exact"
    return merged


def _build_offline_compare_tolerant(
    *,
    session: dict[str, Any],
    bundle_dir: Path,
    audit_df: pd.DataFrame,
    trades_df: pd.DataFrame,
) -> pd.DataFrame:
    expected = _load_expected_offline_compare(session, bundle_dir)
    expected = _filter_expected_to_historical_lock_universe(expected, session=session)
    if "status" in expected.columns and "candidate_uid" in expected.columns and len(expected) == 1:
        return expected

    expected = _prepare_expected_compare(expected).reset_index(drop=True)
    expected["expected_idx"] = expected.index.astype(int)
    audit = _runtime_predict_keys(audit_df)
    trades = _runtime_trade_keys(trades_df)
    predict_matches = _nearest_match(
        expected=expected[["candidate_uid", "close_ts", "expected_idx"]],
        runtime=audit,
        expected_ts_col="close_ts",
        runtime_ts_col="close_ts",
        tolerance_sec=float(_COMPARE_TOLERANCE_SEC),
    )
    trade_matches = _nearest_match(
        expected=expected[["candidate_uid", "touch_open_ts", "expected_idx"]],
        runtime=trades,
        expected_ts_col="touch_open_ts",
        runtime_ts_col="entry_ts",
        tolerance_sec=float(_COMPARE_TOLERANCE_SEC),
    )

    out = expected.copy()
    out["runtime_predict_count"] = 0
    out["runtime_trade_count"] = 0
    out["runtime_predicted"] = False
    out["runtime_executed"] = False
    out["runtime_predict_match_close_ts"] = pd.Series([None] * len(out), dtype=object)
    out["runtime_trade_match_entry_ts"] = pd.Series([None] * len(out), dtype=object)
    out["runtime_predict_delta_sec"] = pd.NA
    out["runtime_trade_delta_sec"] = pd.NA
    out["runtime_trade_status"] = pd.NA
    out["runtime_trade_side"] = pd.NA
    out["compare_mode"] = "tolerant"

    if not predict_matches.empty:
        for row in predict_matches.to_dict(orient="records"):
            exp_idx = int(row["expected_idx"])
            rt_idx = int(row["runtime_idx"])
            out.loc[exp_idx, "runtime_predict_count"] = 1
            out.loc[exp_idx, "runtime_predicted"] = True
            out.loc[exp_idx, "runtime_predict_match_close_ts"] = audit.loc[rt_idx, "close_ts"]
            out.loc[exp_idx, "runtime_predict_delta_sec"] = float(row["delta_sec"])

    if not trade_matches.empty:
        for row in trade_matches.to_dict(orient="records"):
            exp_idx = int(row["expected_idx"])
            rt_idx = int(row["runtime_idx"])
            out.loc[exp_idx, "runtime_trade_count"] = 1
            out.loc[exp_idx, "runtime_executed"] = True
            out.loc[exp_idx, "runtime_trade_match_entry_ts"] = trades.loc[rt_idx, "entry_ts"]
            out.loc[exp_idx, "runtime_trade_delta_sec"] = float(row["delta_sec"])
            if "status" in trades.columns:
                out.loc[exp_idx, "runtime_trade_status"] = trades.loc[rt_idx, "status"]
            if "side" in trades.columns:
                out.loc[exp_idx, "runtime_trade_side"] = trades.loc[rt_idx, "side"]

    return out.drop(columns=["expected_idx"], errors="ignore")


def _build_signal_gap_bundle(
    *,
    session: dict[str, Any],
    audit_df: pd.DataFrame,
    http_trace_path: Path,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    expected_selected_detail = _load_expected_selected_detail_for_session(session)
    if expected_selected_detail.empty:
        empty_gap = pd.DataFrame(
            columns=[
                "gap_side",
                "gap_reason",
                "candidate_uid",
                "reference_close_ts",
                "nearest_runtime_selected_close_ts",
                "nearest_predict_close_ts",
                "nearest_predict_trace_ts",
                "nearest_delta_sec",
                "nearest_predict_selected_exec",
                "nearest_predict_pred_prob",
                "nearest_predict_threshold_exec",
                "nearest_predict_margin",
                "nearest_predict_risk_blocked",
                "nearest_predict_reason",
                "nearest_predict_features_json",
                "offline_pred_prob",
                "offline_threshold_exec",
                "offline_margin",
                "margin_delta_runtime_minus_offline",
            ]
        )
        empty_diff = pd.DataFrame(
            columns=[
                "gap_side",
                "gap_reason",
                "candidate_uid",
                "reference_close_ts",
                "feature_name",
                "offline_value",
                "runtime_value",
                "runtime_minus_offline",
                "abs_delta",
                "offline_pred_prob",
                "offline_threshold_exec",
                "offline_margin",
                "runtime_pred_prob",
                "runtime_threshold_exec",
                "runtime_margin",
                "margin_delta_runtime_minus_offline",
            ]
        )
        return empty_gap, empty_diff

    expected_keys = expected_selected_detail[["candidate_uid", "close_ts"]].copy().reset_index(drop=True)
    expected_keys["expected_idx"] = expected_keys.index.astype(int)
    runtime_keys = _runtime_predict_keys(audit_df).reset_index(drop=True)
    runtime_keys["runtime_idx"] = runtime_keys.index.astype(int)
    matches = _nearest_match(
        expected=expected_keys[["candidate_uid", "close_ts", "expected_idx"]],
        runtime=runtime_keys[["candidate_uid", "close_ts", "runtime_idx"]],
        expected_ts_col="close_ts",
        runtime_ts_col="close_ts",
        tolerance_sec=float(_COMPARE_TOLERANCE_SEC),
    )
    used_expected = set(matches["expected_idx"].astype(int).tolist()) if not matches.empty else set()
    used_runtime = set(matches["runtime_idx"].astype(int).tolist()) if not matches.empty else set()
    missing_expected = expected_keys.loc[~expected_keys["expected_idx"].isin(used_expected), ["candidate_uid", "close_ts"]].reset_index(drop=True)
    extra_runtime = runtime_keys.loc[~runtime_keys["runtime_idx"].isin(used_runtime), ["candidate_uid", "close_ts"]].reset_index(drop=True)
    predict_trace_rows = _load_predict_trace_rows(http_trace_path)
    signal_gap = _build_signal_gap_analysis(
        expected_selected_detail=expected_selected_detail,
        expected_keys=expected_keys[["candidate_uid", "close_ts"]],
        runtime_keys=runtime_keys[["candidate_uid", "close_ts"]],
        missing_expected=missing_expected,
        extra_runtime=extra_runtime,
        predict_trace_rows=predict_trace_rows,
        classify_window_sec=float(_COMPARE_TOLERANCE_SEC),
    )
    signal_feature_diff = _build_signal_feature_diff(
        signal_gap_analysis=signal_gap,
        symbol=str(session.get("symbol", "")).upper().strip(),
        tick_velocity_dir=Path(
            str(session.get("tick_velocity_dir", REPO_ROOT / "data" / "analysis" / "tick_velocity"))
        ),
    )
    return signal_gap, signal_feature_diff


def _build_execution_gap_analysis(
    *,
    offline_compare: pd.DataFrame,
    trades_df: pd.DataFrame,
) -> pd.DataFrame:
    cols = [
        "gap_side",
        "gap_reason",
        "candidate_uid",
        "reference_close_ts",
        "reference_touch_open_ts",
        "runtime_predict_match_close_ts",
        "runtime_trade_match_entry_ts",
        "runtime_predict_delta_sec",
        "runtime_trade_delta_sec",
        "runtime_trade_status",
        "runtime_trade_side",
    ]
    if offline_compare.empty:
        return pd.DataFrame(columns=cols)
    out = offline_compare.copy()
    out["runtime_predicted"] = out.get("runtime_predicted", pd.Series(dtype=bool)).fillna(False).astype(bool)
    out["runtime_executed"] = out.get("runtime_executed", pd.Series(dtype=bool)).fillna(False).astype(bool)
    rows: list[dict[str, Any]] = []
    for row in out.to_dict(orient="records"):
        if bool(row.get("runtime_executed")):
            gap_reason = "executed_matched"
        elif bool(row.get("runtime_predicted")):
            gap_reason = "predicted_not_executed"
        else:
            gap_reason = "no_prediction_no_execution"
        rows.append(
            {
                "gap_side": "expected_execution",
                "gap_reason": gap_reason,
                "candidate_uid": row.get("candidate_uid"),
                "reference_close_ts": row.get("close_ts"),
                "reference_touch_open_ts": row.get("touch_open_ts"),
                "runtime_predict_match_close_ts": row.get("runtime_predict_match_close_ts"),
                "runtime_trade_match_entry_ts": row.get("runtime_trade_match_entry_ts"),
                "runtime_predict_delta_sec": row.get("runtime_predict_delta_sec"),
                "runtime_trade_delta_sec": row.get("runtime_trade_delta_sec"),
                "runtime_trade_status": row.get("runtime_trade_status"),
                "runtime_trade_side": row.get("runtime_trade_side"),
            }
        )
    expected = _prepare_expected_compare(offline_compare).reset_index(drop=True)
    expected["expected_idx"] = expected.index.astype(int)
    trades = _runtime_trade_keys(trades_df).reset_index(drop=True)
    trades["runtime_idx"] = trades.index.astype(int)
    matches = _nearest_match(
        expected=expected[["candidate_uid", "touch_open_ts", "expected_idx"]],
        runtime=trades[["candidate_uid", "entry_ts", "runtime_idx"]],
        expected_ts_col="touch_open_ts",
        runtime_ts_col="entry_ts",
        tolerance_sec=float(_COMPARE_TOLERANCE_SEC),
    )
    used_runtime = set(matches["runtime_idx"].astype(int).tolist()) if not matches.empty else set()
    extras = trades.loc[~trades["runtime_idx"].isin(used_runtime)].copy()
    for row in extras.to_dict(orient="records"):
        rows.append(
            {
                "gap_side": "extra_runtime_execution",
                "gap_reason": "runtime_trade_without_expected_entry",
                "candidate_uid": row.get("candidate_uid"),
                "reference_close_ts": pd.NaT,
                "reference_touch_open_ts": pd.NaT,
                "runtime_predict_match_close_ts": pd.NaT,
                "runtime_trade_match_entry_ts": row.get("entry_ts"),
                "runtime_predict_delta_sec": pd.NA,
                "runtime_trade_delta_sec": pd.NA,
                "runtime_trade_status": row.get("status"),
                "runtime_trade_side": row.get("side"),
            }
        )
    return pd.DataFrame(rows, columns=cols)


def _write_markdown_summary(
    *,
    path: Path,
    session: dict[str, Any],
    timeline: pd.DataFrame,
    offline_compare: pd.DataFrame,
    offline_compare_exact: pd.DataFrame,
    duplicate_trade_rows: int,
    artifacts: dict[str, Any],
) -> None:
    counts = timeline["source"].value_counts().to_dict() if not timeline.empty else {}
    lines = [
        f"# cTrader Debug Bundle: {session.get('run_id', '')}",
        "",
        f"- symbol: `{session.get('symbol', '')}`",
        f"- run_id: `{session.get('run_id', '')}`",
        f"- timeline_rows: `{len(timeline)}`",
        f"- offline_compare_rows: `{len(offline_compare)}`",
        f"- offline_compare_exact_rows: `{len(offline_compare_exact)}`",
        f"- duplicate_trade_rows: `{int(duplicate_trade_rows)}`",
        f"- artifacts: `{json.dumps(artifacts, sort_keys=True)}`",
        f"- source_counts: `{json.dumps(counts, sort_keys=True)}`",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_bundle(*, session_path: Path, bundle_dir: Path | None = None) -> dict[str, str]:
    session = _read_json(session_path)
    out_dir = bundle_dir or Path(str(session.get("bundle_dir", ""))).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    symbol = str(session.get("symbol", "")).upper().strip()
    run_id = str(session.get("run_id", "")).strip() or None

    http_trace_path = Path(str(session.get("bundle_http_trace", session.get("http_trace_path", ""))))
    runtime_db_path = Path(str(session.get("bundle_runtime_db", session.get("runtime_db", ""))))
    cbot_log_path = Path(str(session.get("bundle_cbot_log", "")))
    ctrader_events_path = Path(str(session.get("bundle_ctrader_events", "")))

    http_df = _load_http_trace(http_trace_path)
    cbot_log_df = _load_cbot_log(cbot_log_path)
    ctrader_events_df = _load_ctrader_events(ctrader_events_path)

    audit_df = pd.DataFrame()
    trades_df = pd.DataFrame()
    raw_ticks_df = pd.DataFrame()
    if runtime_db_path.exists():
        con = duckdb.connect(str(runtime_db_path), read_only=True)
        try:
            raw_ticks_df = _load_runtime_raw_ticks(con, symbol, run_id)
            audit_df = _load_runtime_audit(con, symbol, run_id)
            trades_df = _load_runtime_trades(con, symbol, run_id)
        finally:
            con.close()

    timeline_parts = [
        _timeline_from_http_trace(http_df),
        _timeline_from_raw_ticks(raw_ticks_df),
        _timeline_from_audit(audit_df),
        _timeline_from_trades(trades_df),
        _timeline_from_ctrader_events(ctrader_events_df, symbol, run_id),
        _timeline_from_cbot_log(cbot_log_df, symbol, run_id),
    ]
    timeline = pd.concat([df for df in timeline_parts if not df.empty], ignore_index=True) if any(
        not df.empty for df in timeline_parts
    ) else pd.DataFrame(
        columns=[
            "ts_utc",
            "source",
            "event_type",
            "symbol",
            "run_id",
            "candidate_uid",
            "broker_pos_id",
            "client_tick_seq",
            "http_endpoint",
            "http_phase",
            "status",
            "detail_json",
        ]
    )
    if not timeline.empty:
        timeline["ts_utc"] = _safe_to_utc(timeline.get("ts_utc", pd.Series(dtype=object)))
        timeline = timeline.sort_values(["ts_utc", "source", "event_type"], na_position="last").reset_index(drop=True)

    offline_compare_exact = _build_offline_compare_exact(
        session=session,
        bundle_dir=out_dir,
        audit_df=audit_df,
        trades_df=trades_df,
    )
    offline_compare = _build_offline_compare_tolerant(
        session=session,
        bundle_dir=out_dir,
        audit_df=audit_df,
        trades_df=trades_df,
    )

    joined_timeline_csv = out_dir / "joined_timeline.csv"
    joined_timeline_md = out_dir / "joined_timeline.md"
    debug_summary_csv = out_dir / "debug_summary.csv"
    offline_compare_csv = out_dir / "offline_compare.csv"
    offline_compare_exact_csv = out_dir / "offline_compare_exact.csv"
    offline_compare_tolerant_csv = out_dir / "offline_compare_tolerant.csv"
    signal_gap_analysis_csv = out_dir / "ctrader_signal_gap_analysis.csv"
    signal_feature_diff_csv = out_dir / "ctrader_signal_feature_diff.csv"
    execution_gap_analysis_csv = out_dir / "ctrader_execution_gap_analysis.csv"

    timeline.to_csv(joined_timeline_csv, index=False)
    offline_compare.to_csv(offline_compare_csv, index=False)
    offline_compare_exact.to_csv(offline_compare_exact_csv, index=False)
    offline_compare.to_csv(offline_compare_tolerant_csv, index=False)
    signal_gap_analysis, signal_feature_diff = _build_signal_gap_bundle(
        session=session,
        audit_df=audit_df,
        http_trace_path=http_trace_path,
    )
    execution_gap_analysis = _build_execution_gap_analysis(
        offline_compare=offline_compare,
        trades_df=trades_df,
    )
    signal_gap_analysis.to_csv(signal_gap_analysis_csv, index=False)
    signal_feature_diff.to_csv(signal_feature_diff_csv, index=False)
    execution_gap_analysis.to_csv(execution_gap_analysis_csv, index=False)

    duplicate_trade_rows = 0
    if not trades_df.empty:
        dup = (
            trades_df.assign(
                entry_ts=_safe_to_utc(trades_df.get("entry_ts", pd.Series(dtype=object)))
            )
            .groupby(["candidate_uid", "entry_ts", "side"], dropna=False)
            .size()
            .reset_index(name="trade_count")
        )
        duplicate_trade_rows = int(dup.loc[dup["trade_count"] > 1, "trade_count"].sum())

    summary = pd.DataFrame(
        [
            {
                "run_id": session.get("run_id", ""),
                "symbol": symbol,
                "timeline_rows": int(len(timeline)),
                "http_trace_rows": int(len(http_df)),
                "raw_tick_rows": int(len(raw_ticks_df)),
                "audit_rows": int(len(audit_df)),
                "trade_rows": int(len(trades_df)),
                "ctrader_event_rows": int(len(ctrader_events_df)),
                "cbot_log_rows": int(len(cbot_log_df)),
                "offline_compare_rows": int(len(offline_compare)),
                "offline_compare_exact_rows": int(len(offline_compare_exact)),
                "signal_gap_rows": int(len(signal_gap_analysis)),
                "signal_missing_expected_rows": int(
                    (signal_gap_analysis.get("gap_side", pd.Series(dtype=str)).astype(str) == "missing_expected").sum()
                ),
                "signal_extra_runtime_rows": int(
                    (signal_gap_analysis.get("gap_side", pd.Series(dtype=str)).astype(str) == "extra_runtime").sum()
                ),
                "execution_gap_rows": int(len(execution_gap_analysis)),
                "execution_predicted_not_executed_rows": int(
                    (
                        (execution_gap_analysis.get("gap_side", pd.Series(dtype=str)).astype(str) == "expected_execution")
                        & (
                            execution_gap_analysis.get("gap_reason", pd.Series(dtype=str)).astype(str)
                            == "predicted_not_executed"
                        )
                    ).sum()
                ),
                "execution_missing_both_rows": int(
                    (
                        (execution_gap_analysis.get("gap_side", pd.Series(dtype=str)).astype(str) == "expected_execution")
                        & (
                            execution_gap_analysis.get("gap_reason", pd.Series(dtype=str)).astype(str)
                            == "no_prediction_no_execution"
                        )
                    ).sum()
                ),
                "execution_extra_runtime_rows": int(
                    (
                        execution_gap_analysis.get("gap_side", pd.Series(dtype=str)).astype(str)
                        == "extra_runtime_execution"
                    ).sum()
                ),
                "duplicate_trade_rows": int(duplicate_trade_rows),
                "events_json_found": bool(ctrader_events_path.exists()),
                "cbot_log_found": bool(cbot_log_path.exists()),
                "runtime_db_found": bool(runtime_db_path.exists()),
                "http_trace_found": bool(http_trace_path.exists()),
            }
        ]
    )
    summary.to_csv(debug_summary_csv, index=False)

    _write_markdown_summary(
        path=joined_timeline_md,
        session=session,
        timeline=timeline,
        offline_compare=offline_compare,
        offline_compare_exact=offline_compare_exact,
        duplicate_trade_rows=duplicate_trade_rows,
        artifacts={
            "http_trace": str(http_trace_path),
            "runtime_db": str(runtime_db_path),
            "cbot_log": str(cbot_log_path),
            "ctrader_events": str(ctrader_events_path),
        },
    )

    return {
        "joined_timeline_csv": str(joined_timeline_csv),
        "joined_timeline_md": str(joined_timeline_md),
        "debug_summary_csv": str(debug_summary_csv),
        "offline_compare_csv": str(offline_compare_csv),
        "offline_compare_exact_csv": str(offline_compare_exact_csv),
        "offline_compare_tolerant_csv": str(offline_compare_tolerant_csv),
        "signal_gap_analysis_csv": str(signal_gap_analysis_csv),
        "signal_feature_diff_csv": str(signal_feature_diff_csv),
        "execution_gap_analysis_csv": str(execution_gap_analysis_csv),
    }


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Build a cTrader debug bundle")
    p.add_argument("--session-json", required=True)
    p.add_argument("--bundle-dir", default="")
    return p


def main() -> None:
    args = _build_parser().parse_args()
    out = build_bundle(
        session_path=Path(str(args.session_json)),
        bundle_dir=(Path(str(args.bundle_dir)) if str(args.bundle_dir).strip() else None),
    )
    print(json.dumps(out, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
