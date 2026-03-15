#!/usr/bin/env python3
"""Validate canonical-feed execution parity between repo and cTrader backtests.

Repo reference source:
  stop_limit_tickfill_detail.csv (candidate_uid, side, touch_open_ts, touch_close_ts, barrier_px)
  Optional reduced-core state schedule filtering:
  <SYMBOL>_oco_reduced_state_schedule.csv (test_month, state_id)

cTrader sources:
  - runtime DB (trades/raw_ticks)
  - events.json (position lifecycle)
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

try:
    from scripts.canonical_tick_feed import DEFAULT_CANONICAL_ROOT
except ModuleNotFoundError:
    from canonical_tick_feed import DEFAULT_CANONICAL_ROOT


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


def _parse_ts(name: str, raw: str | None) -> pd.Timestamp:
    txt = str(raw or "").strip()
    if not txt:
        raise ValueError(f"{name} is required")
    ts = pd.to_datetime(txt, utc=True, errors="coerce")
    if pd.isna(ts):
        raise ValueError(f"invalid {name}: {raw!r}")
    return ts


def _window_mask(ts: pd.Series, start: pd.Timestamp, end: pd.Timestamp) -> pd.Series:
    return ts.notna() & (ts >= start) & (ts < end)


def _month_tags_between(start: pd.Timestamp, end: pd.Timestamp) -> list[str]:
    if not (start < end):
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


def _month_tags_iso_between(start: pd.Timestamp, end: pd.Timestamp) -> list[str]:
    return [f"{m[:4]}-{m[4:]}" for m in _month_tags_between(start, end)]


def _normalize_test_month(raw: Any) -> str:
    txt = str(raw or "").strip()
    if not txt:
        return ""
    if len(txt) == 6 and txt.isdigit():
        return f"{txt[:4]}-{txt[4:]}"
    if re.fullmatch(r"\d{4}-\d{2}", txt):
        return txt
    return ""


def _candidate_uid_state_id(uid: Any) -> str:
    parts = str(uid or "").split("|", 4)
    if len(parts) != 5:
        return ""
    return str(parts[4]).strip()


def _candidate_uid_bar_ticks(uid: Any) -> int | None:
    parts = str(uid or "").split("|", 4)
    if len(parts) != 5:
        return None
    try:
        return int(str(parts[2]).strip())
    except Exception:
        return None


def _candidate_uid_horizon(uid: Any) -> int | None:
    parts = str(uid or "").split("|", 4)
    if len(parts) != 5:
        return None
    raw = str(parts[3]).strip()
    try:
        return int(raw.lstrip("hH"))
    except Exception:
        return None


def _quote_sql_path(path: Path) -> str:
    return "'" + str(path).replace("'", "''") + "'"


def _pip_size(symbol: str) -> float:
    sym = str(symbol).upper().strip()
    return 0.01 if sym.endswith("JPY") else 0.0001


def _norm_side(raw: Any) -> str:
    txt = str(raw).strip().upper()
    if txt in {"BUY", "B", "LONG", "1", "+1", "TRUE"}:
        return "BUY"
    if txt in {"SELL", "S", "SHORT", "-1", "0", "FALSE"}:
        return "SELL"
    try:
        num = float(txt)
        return "BUY" if num > 0 else "SELL"
    except Exception:
        return txt


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


def _safe_query(
    con: duckdb.DuckDBPyConnection,
    sql: str,
    params: list[Any],
) -> pd.DataFrame:
    try:
        return con.execute(sql, params).fetchdf()
    except Exception:
        return pd.DataFrame()


def _load_runtime_trades(
    con: duckdb.DuckDBPyConnection,
    symbol: str,
) -> pd.DataFrame:
    return _safe_query(
        con,
        """
        SELECT broker_pos_id, candidate_uid, side, entry_price, entry_ts, exit_price, exit_ts, pnl_pips, status
        FROM trades
        WHERE upper(symbol) = ?
        """,
        [str(symbol).upper().strip()],
    )


def _load_runtime_raw_ticks(
    con: duckdb.DuckDBPyConnection,
    symbol: str,
) -> pd.DataFrame:
    cols_df = _safe_query(
        con,
        """
        SELECT lower(column_name) AS col
        FROM information_schema.columns
        WHERE lower(table_name) = 'raw_ticks'
        """,
        [],
    )
    if cols_df.empty:
        return pd.DataFrame(columns=["ts", "bid", "ask"])

    cols = set(cols_df["col"].astype(str).tolist())
    ts_col = next((c for c in ["tick_ts", "timestamp_utc", "timestamp", "ts"] if c in cols), "")
    if not ts_col:
        return pd.DataFrame(columns=["ts", "bid", "ask"])
    bid_col = "bid" if "bid" in cols else ""
    ask_col = "ask" if "ask" in cols else ""

    bid_expr = bid_col if bid_col else "NULL::DOUBLE"
    ask_expr = ask_col if ask_col else "NULL::DOUBLE"
    sql = f"""
        SELECT
            try_cast({ts_col} AS TIMESTAMP WITH TIME ZONE) AS ts,
            try_cast({bid_expr} AS DOUBLE) AS bid,
            try_cast({ask_expr} AS DOUBLE) AS ask
        FROM raw_ticks
        WHERE upper(symbol) = ?
    """
    return _safe_query(con, sql, [str(symbol).upper().strip()])


def _load_hist_ticks(
    *,
    symbol: str,
    tick_root: Path,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.DataFrame:
    months = _month_tags_between(start, end)
    files = [
        tick_root / symbol / f"{symbol}_{m}_ticks.parquet"
        for m in months
        if (tick_root / symbol / f"{symbol}_{m}_ticks.parquet").exists()
    ]
    if not files:
        return pd.DataFrame(columns=["ts", "bid", "ask"])

    files_sql = "[" + ",".join(_quote_sql_path(p) for p in files) + "]"
    con = duckdb.connect()
    try:
        ts_expr = "try_cast(timestamp AS TIMESTAMP WITH TIME ZONE)"
        out = con.execute(
            f"""
            SELECT
                {ts_expr} AS ts,
                try_cast(bid AS DOUBLE) AS bid,
                try_cast(ask AS DOUBLE) AS ask
            FROM read_parquet({files_sql})
            WHERE {ts_expr} >= ? AND {ts_expr} < ?
            ORDER BY {ts_expr}
            """,
            [start.to_pydatetime(), end.to_pydatetime()],
        ).fetchdf()
    finally:
        con.close()

    if out.empty:
        return pd.DataFrame(columns=["ts", "bid", "ask"])
    out["ts"] = _to_utc(out.get("ts", pd.Series(dtype=object)))
    out["bid"] = pd.to_numeric(out.get("bid", pd.Series(dtype=float)), errors="coerce")
    out["ask"] = pd.to_numeric(out.get("ask", pd.Series(dtype=float)), errors="coerce")
    out = out.dropna(subset=["ts", "bid", "ask"]).reset_index(drop=True)
    return out[["ts", "bid", "ask"]]


def _load_expected_repo_executions(
    *,
    detail_csv: Path,
    symbol: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.DataFrame:
    con = duckdb.connect()
    sym = str(symbol).upper().strip()
    try:
        ts_expr = "try_cast(touch_open_ts AS TIMESTAMP WITH TIME ZONE)"
        out = con.execute(
            f"""
            SELECT
                candidate_uid,
                side,
                try_cast(barrier_px AS DOUBLE) AS entry_price,
                {ts_expr} AS entry_ts,
                try_cast(touch_close_ts AS TIMESTAMP WITH TIME ZONE) AS exit_ts
            FROM read_csv_auto(?, header=true)
            WHERE upper(split_part(candidate_uid, '|', 2)) = ?
              AND {ts_expr} IS NOT NULL
              AND {ts_expr} >= ?
              AND {ts_expr} < ?
            ORDER BY {ts_expr}
            """,
            [str(detail_csv), sym, start.to_pydatetime(), end.to_pydatetime()],
        ).fetchdf()
    finally:
        con.close()

    if out.empty:
        return pd.DataFrame(columns=["candidate_uid", "side", "entry_price", "entry_ts", "exit_ts"])
    out["candidate_uid"] = out["candidate_uid"].astype(str)
    out["side"] = out["side"].map(_norm_side)
    out["entry_ts"] = _to_utc(out.get("entry_ts", pd.Series(dtype=object)))
    out["exit_ts"] = _to_utc(out.get("exit_ts", pd.Series(dtype=object)))
    out["entry_price"] = pd.to_numeric(out.get("entry_price", pd.Series(dtype=float)), errors="coerce")
    out = out.dropna(subset=["candidate_uid", "side", "entry_ts", "entry_price"]).reset_index(drop=True)
    return out


def _load_reduced_core_schedule(
    *,
    schedule_csv: Path,
    symbol: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.DataFrame:
    if not schedule_csv.exists():
        return pd.DataFrame(columns=["test_month", "bar_ticks", "horizon", "state_id"])
    raw = pd.read_csv(schedule_csv)
    if raw.empty:
        return pd.DataFrame(columns=["test_month", "bar_ticks", "horizon", "state_id"])
    req = {"state_id", "test_month", "bar_ticks", "horizon"}
    if not req.issubset(set(raw.columns)):
        return pd.DataFrame(columns=["test_month", "bar_ticks", "horizon", "state_id"])

    out = raw.copy()
    if "symbol" in out.columns:
        out["symbol"] = out["symbol"].astype(str).str.upper().str.strip()
        out = out[out["symbol"] == str(symbol).upper().strip()].copy()
    out["state_id"] = out["state_id"].astype(str).str.strip()
    out["test_month"] = out["test_month"].map(_normalize_test_month)
    out = out[(out["state_id"] != "") & (out["test_month"] != "")].copy()

    months = set(_month_tags_iso_between(start, end))
    out = out[out["test_month"].isin(months)].copy()
    out["bar_ticks"] = pd.to_numeric(out["bar_ticks"], errors="coerce").astype("Int64")
    out["horizon"] = pd.to_numeric(out["horizon"], errors="coerce").astype("Int64")
    out = out.dropna(subset=["bar_ticks", "horizon"]).copy()
    out["bar_ticks"] = out["bar_ticks"].astype(int)
    out["horizon"] = out["horizon"].astype(int)
    if out.empty:
        return pd.DataFrame(columns=["test_month", "bar_ticks", "horizon", "state_id"])
    out = out[["test_month", "bar_ticks", "horizon", "state_id"]].drop_duplicates().sort_values(
        ["test_month", "bar_ticks", "horizon", "state_id"]
    )
    return out.reset_index(drop=True)


def _filter_expected_to_reduced_core(
    *,
    expected: pd.DataFrame,
    schedule: pd.DataFrame,
) -> pd.DataFrame:
    if expected.empty or schedule.empty:
        return expected.copy()
    out = expected.copy()
    out["state_id"] = out["candidate_uid"].map(_candidate_uid_state_id)
    out["bar_ticks"] = out["candidate_uid"].map(_candidate_uid_bar_ticks).astype("Int64")
    out["horizon"] = out["candidate_uid"].map(_candidate_uid_horizon).astype("Int64")
    out["test_month"] = out["entry_ts"].dt.strftime("%Y-%m")
    allowed = schedule[["test_month", "bar_ticks", "horizon", "state_id"]].drop_duplicates()
    out = out.merge(allowed, on=["test_month", "bar_ticks", "horizon", "state_id"], how="inner")
    return out.drop(columns=["state_id", "test_month", "bar_ticks", "horizon"]).reset_index(drop=True)


def _load_ctrader_events(path: Path) -> pd.DataFrame:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        return pd.DataFrame(
            columns=["position_id", "side", "entry_ts", "entry_price", "exit_ts", "exit_price", "pips"]
        )

    rows = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        event = str(item.get("event", "")).strip()
        pos_id_raw = item.get("positionId")
        if pos_id_raw is None:
            continue
        try:
            pos_id = str(int(pos_id_raw))
        except Exception:
            pos_id = str(pos_id_raw).strip()
        if not pos_id:
            continue

        ts = pd.to_datetime(item.get("time"), unit="ms", utc=True, errors="coerce")
        rec = rows.get(
            pos_id,
            {
                "position_id": pos_id,
                "side": "",
                "entry_ts": pd.NaT,
                "entry_price": float("nan"),
                "exit_ts": pd.NaT,
                "exit_price": float("nan"),
                "pips": float("nan"),
            },
        )

        if event == "Create Position":
            rec["side"] = _norm_side(item.get("type", ""))
            rec["entry_ts"] = ts
            rec["entry_price"] = pd.to_numeric(item.get("entryPrice"), errors="coerce")
        elif event == "Position closed":
            rec["exit_ts"] = ts
            rec["exit_price"] = pd.to_numeric(item.get("closePrice"), errors="coerce")
            rec["pips"] = pd.to_numeric(item.get("pips"), errors="coerce")

        rows[pos_id] = rec

    out = pd.DataFrame(list(rows.values()))
    if out.empty:
        return pd.DataFrame(
            columns=["position_id", "side", "entry_ts", "entry_price", "exit_ts", "exit_price", "pips"]
        )
    out["entry_ts"] = _to_utc(out.get("entry_ts", pd.Series(dtype=object)))
    out["exit_ts"] = _to_utc(out.get("exit_ts", pd.Series(dtype=object)))
    out["entry_price"] = pd.to_numeric(out.get("entry_price", pd.Series(dtype=float)), errors="coerce")
    out["exit_price"] = pd.to_numeric(out.get("exit_price", pd.Series(dtype=float)), errors="coerce")
    out["pips"] = pd.to_numeric(out.get("pips", pd.Series(dtype=float)), errors="coerce")
    out["side"] = out.get("side", pd.Series(dtype=str)).map(_norm_side)
    return out


def _pair_expected_actual(
    *,
    expected: pd.DataFrame,
    actual: pd.DataFrame,
    time_tolerance_sec: float,
    price_tolerance_abs: float,
    pip_size: float,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if expected.empty and actual.empty:
        return (
            pd.DataFrame(columns=["exp_idx", "act_idx", "entry_time_abs_sec", "entry_price_abs_pips"]),
            expected.copy(),
            actual.copy(),
        )

    exp = expected.copy().reset_index(drop=True)
    act = actual.copy().reset_index(drop=True)
    exp["exp_idx"] = exp.index
    act["act_idx"] = act.index

    unmatched_actual: set[int] = set(act["act_idx"].astype(int).tolist())
    matched_rows: list[dict[str, Any]] = []

    for _, erow in exp.sort_values("entry_ts").iterrows():
        exp_idx = int(erow["exp_idx"])
        key_uid = str(erow["candidate_uid"])
        key_side = str(erow["side"])

        cands = act[
            (act["candidate_uid"].astype(str) == key_uid)
            & (act["side"].astype(str) == key_side)
            & (act["act_idx"].astype(int).isin(unmatched_actual))
        ].copy()
        if cands.empty:
            continue

        cands["entry_time_abs_sec"] = (
            cands["entry_ts"] - erow["entry_ts"]
        ).dt.total_seconds().abs()
        cands["entry_price_abs"] = (cands["entry_price"] - float(erow["entry_price"])).abs()
        cands["entry_price_abs_pips"] = cands["entry_price_abs"] / float(pip_size)

        cands = cands[
            (cands["entry_time_abs_sec"] <= float(time_tolerance_sec))
            & (cands["entry_price_abs"] <= float(price_tolerance_abs))
        ].copy()
        if cands.empty:
            continue

        cands = cands.sort_values(["entry_time_abs_sec", "entry_price_abs", "act_idx"])
        best = cands.iloc[0]
        act_idx = int(best["act_idx"])
        unmatched_actual.discard(act_idx)

        matched_rows.append(
            {
                "exp_idx": exp_idx,
                "act_idx": act_idx,
                "entry_time_abs_sec": float(best["entry_time_abs_sec"]),
                "entry_price_abs_pips": float(best["entry_price_abs_pips"]),
            }
        )

    matches = pd.DataFrame(matched_rows)
    matched_exp_ids = set(matches["exp_idx"].astype(int).tolist()) if not matches.empty else set()
    matched_act_ids = set(matches["act_idx"].astype(int).tolist()) if not matches.empty else set()
    unmatched_expected = exp[~exp["exp_idx"].astype(int).isin(matched_exp_ids)].copy()
    unmatched_actual_df = act[~act["act_idx"].astype(int).isin(matched_act_ids)].copy()
    return matches, unmatched_expected, unmatched_actual_df


def _evaluate_exit_mismatches(
    *,
    expected: pd.DataFrame,
    actual: pd.DataFrame,
    matches: pd.DataFrame,
    time_tolerance_sec: float,
    price_tolerance_abs: float,
    pip_size: float,
) -> tuple[pd.DataFrame, float, float]:
    rows: list[dict[str, Any]] = []
    max_time_abs_sec = float("nan")
    max_price_abs_pips = float("nan")
    if matches.empty:
        return pd.DataFrame(rows), max_time_abs_sec, max_price_abs_pips

    exp_map = expected.reset_index(drop=True)
    act_map = actual.reset_index(drop=True)

    time_diffs: list[float] = []
    price_diffs_pips: list[float] = []

    for _, m in matches.iterrows():
        e = exp_map.iloc[int(m["exp_idx"])]
        a = act_map.iloc[int(m["act_idx"])]
        e_exit = e.get("exit_ts")
        a_exit = a.get("exit_ts")
        e_exit_price = e.get("exit_price", float("nan"))
        a_exit_price = a.get("exit_price", float("nan"))
        key_uid = str(e.get("candidate_uid", ""))
        key_side = str(e.get("side", ""))

        e_exit_isna = pd.isna(e_exit)
        a_exit_isna = pd.isna(a_exit)
        if e_exit_isna and a_exit_isna:
            continue
        if e_exit_isna != a_exit_isna:
            rows.append(
                {
                    "type": "exit_missing",
                    "candidate_uid": key_uid,
                    "side": key_side,
                    "expected_entry_ts": e.get("entry_ts"),
                    "actual_entry_ts": a.get("entry_ts"),
                    "expected_exit_ts": e_exit,
                    "actual_exit_ts": a_exit,
                    "detail": "expected and actual exit presence differ",
                }
            )
            continue

        dt = abs((a_exit - e_exit).total_seconds())
        time_diffs.append(float(dt))
        if dt > float(time_tolerance_sec):
            rows.append(
                {
                    "type": "exit_time_mismatch",
                    "candidate_uid": key_uid,
                    "side": key_side,
                    "expected_entry_ts": e.get("entry_ts"),
                    "actual_entry_ts": a.get("entry_ts"),
                    "expected_exit_ts": e_exit,
                    "actual_exit_ts": a_exit,
                    "detail": f"abs_exit_time_sec={dt:.6f} > tol_sec={float(time_tolerance_sec):.6f}",
                }
            )

        if pd.notna(e_exit_price) and pd.notna(a_exit_price):
            px_abs = abs(float(a_exit_price) - float(e_exit_price))
            price_diffs_pips.append(float(px_abs / float(pip_size)))
            if px_abs > float(price_tolerance_abs):
                rows.append(
                    {
                        "type": "exit_price_mismatch",
                        "candidate_uid": key_uid,
                        "side": key_side,
                        "expected_entry_ts": e.get("entry_ts"),
                        "actual_entry_ts": a.get("entry_ts"),
                        "expected_exit_ts": e_exit,
                        "actual_exit_ts": a_exit,
                        "detail": (
                            f"abs_exit_price={px_abs:.8f} > tol_abs={float(price_tolerance_abs):.8f}"
                        ),
                    }
                )

    if time_diffs:
        max_time_abs_sec = float(max(time_diffs))
    if price_diffs_pips:
        max_price_abs_pips = float(max(price_diffs_pips))
    return pd.DataFrame(rows), max_time_abs_sec, max_price_abs_pips


def _verdict(checks: pd.DataFrame) -> str:
    if checks.empty:
        return "red"
    fails = checks[checks["status"].astype(str) == "fail"]
    if fails.empty:
        return "green"
    fails_hc = fails[fails["severity"].astype(str).str.lower().isin({"critical", "high"})]
    if not fails_hc.empty:
        return "red"
    return "yellow"


def run(
    *,
    symbol: str,
    runtime_db: Path,
    ctrader_events_json: Path,
    repo_stoplimit_detail_csv: Path,
    reduced_core_state_schedule_csv: Path | None = None,
    require_reduced_core_filter: bool = False,
    tick_root: Path,
    start_ts: str,
    end_ts: str,
    time_tolerance_sec: float = 1.0,
    price_tolerance_pips: float = 0.1,
    out_summary_csv: Path = Path(
        "data/analysis/backtest_reconcile/ctrader_execution_parity_summary.csv"
    ),
    out_checks_csv: Path = Path(
        "data/analysis/backtest_reconcile/ctrader_execution_parity_checks.csv"
    ),
    out_mismatches_csv: Path = Path(
        "data/analysis/backtest_reconcile/ctrader_execution_parity_mismatches.csv"
    ),
    report_out: Path = Path("docs/analysis/ctrader_execution_parity_report.md"),
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    sym = str(symbol).upper().strip()
    if not sym:
        raise ValueError("symbol is required")
    start = _parse_ts("start_ts", start_ts)
    end = _parse_ts("end_ts", end_ts)
    if not (start < end):
        raise ValueError("start_ts must be earlier than end_ts")

    out_summary_csv.parent.mkdir(parents=True, exist_ok=True)
    out_checks_csv.parent.mkdir(parents=True, exist_ok=True)
    out_mismatches_csv.parent.mkdir(parents=True, exist_ok=True)
    report_out.parent.mkdir(parents=True, exist_ok=True)

    checks: list[Check] = []
    mismatch_rows: list[dict[str, Any]] = []
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    pip_size = _pip_size(sym)
    price_tolerance_abs = float(price_tolerance_pips) * float(pip_size)

    _add_check(
        checks,
        check_id="RUNTIME_DB_EXISTS",
        ok=runtime_db.exists(),
        severity="critical",
        metric="runtime_db_exists",
        value=bool(runtime_db.exists()),
        expected=True,
        operator="==",
        detail=f"path={runtime_db}",
    )
    _add_check(
        checks,
        check_id="CTRADER_EVENTS_JSON_EXISTS",
        ok=ctrader_events_json.exists(),
        severity="critical",
        metric="ctrader_events_json_exists",
        value=bool(ctrader_events_json.exists()),
        expected=True,
        operator="==",
        detail=f"path={ctrader_events_json}",
    )
    _add_check(
        checks,
        check_id="REPO_STOPLIMIT_DETAIL_EXISTS",
        ok=repo_stoplimit_detail_csv.exists(),
        severity="critical",
        metric="repo_stoplimit_detail_exists",
        value=bool(repo_stoplimit_detail_csv.exists()),
        expected=True,
        operator="==",
        detail=f"path={repo_stoplimit_detail_csv}",
    )
    if reduced_core_state_schedule_csv is not None:
        _add_check(
            checks,
            check_id="REDUCED_CORE_STATE_SCHEDULE_EXISTS",
            ok=reduced_core_state_schedule_csv.exists(),
            severity="critical" if require_reduced_core_filter else "high",
            metric="reduced_core_state_schedule_exists",
            value=bool(reduced_core_state_schedule_csv.exists()),
            expected=True,
            operator="==",
            detail=f"path={reduced_core_state_schedule_csv}",
        )
    _add_check(
        checks,
        check_id="TICK_ROOT_EXISTS",
        ok=tick_root.exists(),
        severity="critical",
        metric="tick_root_exists",
        value=bool(tick_root.exists()),
        expected=True,
        operator="==",
        detail=f"path={tick_root}",
    )

    required_missing = (
        (not runtime_db.exists())
        or (not ctrader_events_json.exists())
        or (not repo_stoplimit_detail_csv.exists())
        or (
            bool(require_reduced_core_filter)
            and reduced_core_state_schedule_csv is not None
            and (not reduced_core_state_schedule_csv.exists())
        )
    )
    if required_missing:
        checks_df = pd.DataFrame([c.__dict__ for c in checks])
        summary_df = pd.DataFrame(
            [
                {
                    "symbol": sym,
                    "runtime_db": str(runtime_db),
                    "ctrader_events_json": str(ctrader_events_json),
                    "repo_stoplimit_detail_csv": str(repo_stoplimit_detail_csv),
                    "reduced_core_state_schedule_csv": str(reduced_core_state_schedule_csv)
                    if reduced_core_state_schedule_csv is not None
                    else "",
                    "require_reduced_core_filter": bool(require_reduced_core_filter),
                    "tick_root": str(tick_root),
                    "start_ts": start.isoformat(),
                    "end_ts": end.isoformat(),
                    "time_tolerance_sec": float(time_tolerance_sec),
                    "price_tolerance_pips": float(price_tolerance_pips),
                    "overall_pass": False,
                    "execution_parity_verdict": "red",
                    "histdata_execution_parity_verdict": "red",
                    "evaluated_at_utc": now_utc,
                }
            ]
        )
        mismatches_df = pd.DataFrame(mismatch_rows)
        summary_df.to_csv(out_summary_csv, index=False)
        checks_df.to_csv(out_checks_csv, index=False)
        mismatches_df.to_csv(out_mismatches_csv, index=False)
        report_out.write_text(
            "# cTrader Execution Parity\n\nMissing required input files.\n",
            encoding="utf-8",
        )
        return summary_df, checks_df, mismatches_df

    db_open_error = ""
    con = None
    try:
        con = duckdb.connect(str(runtime_db), read_only=True)
        runtime_trades = _load_runtime_trades(con, sym)
        runtime_raw_ticks = _load_runtime_raw_ticks(con, sym)
    except Exception as exc:
        db_open_error = str(exc)
        runtime_trades = pd.DataFrame()
        runtime_raw_ticks = pd.DataFrame()
    finally:
        if con is not None:
            con.close()

    _add_check(
        checks,
        check_id="RUNTIME_DB_READABLE",
        ok=(db_open_error == ""),
        severity="critical",
        metric="runtime_db_readable",
        value=(db_open_error == ""),
        expected=True,
        operator="==",
        detail=f"error={db_open_error}" if db_open_error else "ok",
    )

    ctrader_events = _load_ctrader_events(ctrader_events_json)
    expected_repo = _load_expected_repo_executions(
        detail_csv=repo_stoplimit_detail_csv,
        symbol=sym,
        start=start,
        end=end,
    )
    expected_rows_before_reduced_filter = int(len(expected_repo))
    reduced_core_schedule = pd.DataFrame(columns=["test_month", "bar_ticks", "horizon", "state_id"])
    if reduced_core_state_schedule_csv is not None and reduced_core_state_schedule_csv.exists():
        reduced_core_schedule = _load_reduced_core_schedule(
            schedule_csv=reduced_core_state_schedule_csv,
            symbol=sym,
            start=start,
            end=end,
        )
    reduced_schedule_rows = int(len(reduced_core_schedule))
    if reduced_core_state_schedule_csv is not None:
        _add_check(
            checks,
            check_id="REDUCED_CORE_SCHEDULE_ROWS_GT_0",
            ok=(reduced_schedule_rows > 0),
            severity="critical" if require_reduced_core_filter else "high",
            metric="reduced_core_schedule_rows_window",
            value=reduced_schedule_rows,
            expected=">0",
            operator=">",
            detail="rows from reduced state schedule in requested window",
        )
        if reduced_schedule_rows > 0:
            expected_repo = _filter_expected_to_reduced_core(
                expected=expected_repo,
                schedule=reduced_core_schedule,
            )

    expected_rows_after_reduced_filter = int(len(expected_repo))
    if reduced_core_state_schedule_csv is not None:
        _add_check(
            checks,
            check_id="REPO_EXPECTED_ROWS_REDUCED_FILTER_GT_0",
            ok=(expected_rows_after_reduced_filter > 0),
            severity="critical" if require_reduced_core_filter else "high",
            metric="repo_expected_rows_after_reduced_filter",
            value=expected_rows_after_reduced_filter,
            expected=">0",
            operator=">",
            detail=(
                f"before_filter={expected_rows_before_reduced_filter} "
                f"after_filter={expected_rows_after_reduced_filter}"
            ),
        )
    hist_ticks = _load_hist_ticks(symbol=sym, tick_root=tick_root, start=start, end=end)

    if not runtime_trades.empty:
        runtime_trades["candidate_uid"] = runtime_trades.get("candidate_uid", pd.Series(dtype=str)).astype(str)
        runtime_trades["side"] = runtime_trades.get("side", pd.Series(dtype=str)).map(_norm_side)
        runtime_trades["entry_price"] = pd.to_numeric(
            runtime_trades.get("entry_price", pd.Series(dtype=float)),
            errors="coerce",
        )
        runtime_trades["exit_price"] = pd.to_numeric(
            runtime_trades.get("exit_price", pd.Series(dtype=float)),
            errors="coerce",
        )
        runtime_trades["entry_ts"] = _to_utc(runtime_trades.get("entry_ts", pd.Series(dtype=object)))
        runtime_trades["exit_ts"] = _to_utc(runtime_trades.get("exit_ts", pd.Series(dtype=object)))
        runtime_trades["pnl_pips"] = pd.to_numeric(
            runtime_trades.get("pnl_pips", pd.Series(dtype=float)),
            errors="coerce",
        )
        runtime_trades["broker_pos_id"] = runtime_trades.get("broker_pos_id", pd.Series(dtype=str)).astype(str)
        runtime_trades_window = runtime_trades[_window_mask(runtime_trades["entry_ts"], start, end)].copy()
    else:
        runtime_trades_window = pd.DataFrame(
            columns=[
                "candidate_uid",
                "side",
                "entry_price",
                "entry_ts",
                "exit_price",
                "exit_ts",
                "pnl_pips",
                "broker_pos_id",
            ]
        )

    if not runtime_raw_ticks.empty:
        runtime_raw_ticks["ts"] = _to_utc(runtime_raw_ticks.get("ts", pd.Series(dtype=object)))
        runtime_raw_ticks["bid"] = pd.to_numeric(runtime_raw_ticks.get("bid", pd.Series(dtype=float)), errors="coerce")
        runtime_raw_ticks["ask"] = pd.to_numeric(runtime_raw_ticks.get("ask", pd.Series(dtype=float)), errors="coerce")
        runtime_raw_ticks_window = runtime_raw_ticks[_window_mask(runtime_raw_ticks["ts"], start, end)].copy()
    else:
        runtime_raw_ticks_window = pd.DataFrame(columns=["ts", "bid", "ask"])

    ctrader_events_window = ctrader_events[_window_mask(ctrader_events["entry_ts"], start, end)].copy()

    runtime_rows = int(len(runtime_trades_window))
    runtime_closed_rows = int(
        runtime_trades_window.get("exit_ts", pd.Series(dtype=object)).notna().sum()
    ) if not runtime_trades_window.empty else 0
    events_rows = int(len(ctrader_events_window))
    events_closed_rows = int(
        ctrader_events_window.get("exit_ts", pd.Series(dtype=object)).notna().sum()
    ) if not ctrader_events_window.empty else 0

    runtime_net_pips_closed = float(
        runtime_trades_window.loc[runtime_trades_window.get("exit_ts", pd.Series(dtype=object)).notna(), "pnl_pips"]
        .fillna(0.0)
        .sum()
    ) if not runtime_trades_window.empty else 0.0
    events_net_pips_closed = float(
        ctrader_events_window.get("pips", pd.Series(dtype=float)).fillna(0.0).sum()
    ) if not ctrader_events_window.empty else 0.0
    net_pips_abs_diff = abs(runtime_net_pips_closed - events_net_pips_closed)

    if runtime_trades_window.empty:
        noncanonical_candidate_uid_rows = 0
        candidate_uid_oco_only_rows = 0
        noncanonical_uid_samples: list[str] = []
    else:
        uid_series = runtime_trades_window.get("candidate_uid", pd.Series(dtype=str)).astype(str).str.strip()
        noncanonical_mask = uid_series.str.count(r"\|") < 4
        noncanonical_candidate_uid_rows = int(noncanonical_mask.sum())
        candidate_uid_oco_only_rows = int((uid_series.str.lower() == "oco").sum())
        noncanonical_uid_samples = (
            uid_series[noncanonical_mask].drop_duplicates().head(5).astype(str).tolist()
        )

    _add_check(
        checks,
        check_id="CTRADER_EVENT_POSITIONS_GT_0",
        ok=events_rows > 0,
        severity="high",
        metric="ctrader_event_positions",
        value=events_rows,
        expected=">0",
        operator=">",
        detail="Create Position / Position closed lifecycle rows from events.json",
    )
    _add_check(
        checks,
        check_id="RUNTIME_TRADES_WINDOW_GT_0",
        ok=runtime_rows > 0,
        severity="high",
        metric="runtime_trades_window_rows",
        value=runtime_rows,
        expected=">0",
        operator=">",
        detail="runtime DB trades rows in window",
    )
    _add_check(
        checks,
        check_id="RUNTIME_CANDIDATE_UID_NONCANONICAL_EQ_0",
        ok=noncanonical_candidate_uid_rows == 0,
        severity="critical",
        metric="runtime_candidate_uid_noncanonical_rows",
        value=noncanonical_candidate_uid_rows,
        expected=0,
        operator="==",
        detail=(
            f"oco_only_rows={candidate_uid_oco_only_rows} "
            f"samples={noncanonical_uid_samples if noncanonical_uid_samples else '[]'}"
        ),
    )
    _add_check(
        checks,
        check_id="EVENTS_RUNTIME_TRADE_COUNT_EQ",
        ok=runtime_rows == events_rows,
        severity="high",
        metric="events_vs_runtime_trade_count",
        value=int(runtime_rows - events_rows),
        expected=0,
        operator="==",
        detail=f"runtime={runtime_rows} events={events_rows}",
    )
    _add_check(
        checks,
        check_id="EVENTS_RUNTIME_CLOSED_COUNT_EQ",
        ok=runtime_closed_rows == events_closed_rows,
        severity="high",
        metric="events_vs_runtime_closed_count",
        value=int(runtime_closed_rows - events_closed_rows),
        expected=0,
        operator="==",
        detail=f"runtime_closed={runtime_closed_rows} events_closed={events_closed_rows}",
    )
    _add_check(
        checks,
        check_id="EVENTS_RUNTIME_NET_PIPS_DRIFT_LE_0_1",
        ok=net_pips_abs_diff <= 0.1,
        severity="high",
        metric="events_vs_runtime_net_pips_abs_diff",
        value=float(net_pips_abs_diff),
        expected=0.1,
        operator="<=",
        detail=f"runtime={runtime_net_pips_closed:.6f} events={events_net_pips_closed:.6f}",
    )

    runtime_ids: set[str] = set(runtime_trades_window["broker_pos_id"].astype(str).str.strip().tolist())
    event_ids: set[str] = set(ctrader_events_window["position_id"].astype(str).str.strip().tolist())
    _add_check(
        checks,
        check_id="BROKER_POS_ID_SET_MATCH",
        ok=runtime_ids == event_ids,
        severity="high",
        metric="broker_pos_id_set_symdiff_count",
        value=int(len(runtime_ids.symmetric_difference(event_ids))),
        expected=0,
        operator="==",
        detail=f"runtime_only={len(runtime_ids - event_ids)} events_only={len(event_ids - runtime_ids)}",
    )
    if noncanonical_candidate_uid_rows > 0 and not runtime_trades_window.empty:
        bad = runtime_trades_window[
            runtime_trades_window["candidate_uid"].astype(str).str.count(r"\|") < 4
        ].copy()
        for _, r in bad.head(200).iterrows():
            mismatch_rows.append(
                {
                    "type": "runtime_candidate_uid_noncanonical",
                    "candidate_uid": str(r.get("candidate_uid", "")),
                    "side": str(r.get("side", "")),
                    "expected_entry_ts": pd.NaT,
                    "actual_entry_ts": r.get("entry_ts"),
                    "expected_entry_price": float("nan"),
                    "actual_entry_price": r.get("entry_price"),
                    "detail": "runtime candidate_uid is not canonical oco|SYMBOL|BT|hH|state_id",
                }
            )

    raw_rows = int(len(runtime_raw_ticks_window))
    raw_dedup = runtime_raw_ticks_window.drop_duplicates(subset=["ts", "bid", "ask"]).reset_index(drop=True)
    raw_distinct_rows = int(len(raw_dedup))
    raw_duplicate_rows = int(raw_rows - raw_distinct_rows)
    hist_rows = int(len(hist_ticks.drop_duplicates(subset=["ts", "bid", "ask"])))
    raw_coverage_ratio = (
        float(raw_distinct_rows) / float(hist_rows)
        if hist_rows > 0
        else float("nan")
    )

    _add_check(
        checks,
        check_id="RUNTIME_RAW_TICKS_GT_0",
        ok=raw_rows > 0,
        severity="high",
        metric="runtime_raw_tick_rows_window",
        value=raw_rows,
        expected=">0",
        operator=">",
        detail="runtime raw tick rows in window",
    )
    _add_check(
        checks,
        check_id="HISTDATA_TICKS_GT_0",
        ok=hist_rows > 0,
        severity="critical",
        metric="hist_tick_rows_window",
        value=hist_rows,
        expected=">0",
        operator=">",
        detail=f"tick_root={tick_root}",
    )
    _add_check(
        checks,
        check_id="RUNTIME_RAW_TICK_DUPLICATE_TRIPLETS_EQ_0",
        ok=raw_duplicate_rows == 0,
        severity="critical",
        metric="runtime_raw_tick_duplicate_triplets",
        value=raw_duplicate_rows,
        expected=0,
        operator="==",
        detail="duplicate key=(ts,bid,ask) in requested window",
    )
    _add_check(
        checks,
        check_id="RUNTIME_RAW_TICK_COVERAGE_BETWEEN_0_98_1_02",
        ok=pd.notna(raw_coverage_ratio) and (0.98 <= float(raw_coverage_ratio) <= 1.02),
        severity="high",
        metric="runtime_raw_tick_distinct_coverage_ratio_vs_hist",
        value=float(raw_coverage_ratio) if pd.notna(raw_coverage_ratio) else float("nan"),
        expected="[0.98,1.02]",
        operator="between",
        detail=f"runtime_distinct={raw_distinct_rows} hist={hist_rows}",
    )

    expected_rows = int(len(expected_repo))
    _add_check(
        checks,
        check_id="REPO_EXPECTED_EXECUTIONS_GT_0",
        ok=expected_rows > 0,
        severity="critical",
        metric="repo_expected_execution_rows_window",
        value=expected_rows,
        expected=">0",
        operator=">",
        detail=(
            "rows from stop_limit_tickfill_detail in window"
            + (" filtered by reduced-core schedule" if reduced_core_state_schedule_csv is not None else "")
        ),
    )

    actual_cols = ["candidate_uid", "side", "entry_price", "entry_ts", "exit_price", "exit_ts", "broker_pos_id"]
    actual_exec = runtime_trades_window.copy()
    for col in actual_cols:
        if col not in actual_exec.columns:
            actual_exec[col] = pd.NA
    actual_exec = actual_exec[actual_cols].copy()

    matches, missing_expected, extra_actual = _pair_expected_actual(
        expected=expected_repo,
        actual=actual_exec,
        time_tolerance_sec=float(time_tolerance_sec),
        price_tolerance_abs=float(price_tolerance_abs),
        pip_size=float(pip_size),
    )

    for _, r in missing_expected.iterrows():
        mismatch_rows.append(
            {
                "type": "missing_expected_execution",
                "candidate_uid": str(r.get("candidate_uid", "")),
                "side": str(r.get("side", "")),
                "expected_entry_ts": r.get("entry_ts"),
                "actual_entry_ts": pd.NaT,
                "expected_entry_price": r.get("entry_price"),
                "actual_entry_price": float("nan"),
                "detail": "expected trade from repo stop-limit detail not found in runtime trades",
            }
        )
    for _, r in extra_actual.iterrows():
        mismatch_rows.append(
            {
                "type": "extra_actual_execution",
                "candidate_uid": str(r.get("candidate_uid", "")),
                "side": str(r.get("side", "")),
                "expected_entry_ts": pd.NaT,
                "actual_entry_ts": r.get("entry_ts"),
                "expected_entry_price": float("nan"),
                "actual_entry_price": r.get("entry_price"),
                "detail": "runtime trade has no matching repo expected execution",
            }
        )

    matched_rows = int(len(matches))
    missing_rows = int(len(missing_expected))
    extra_rows = int(len(extra_actual))
    max_entry_time_abs_sec = float(matches["entry_time_abs_sec"].max()) if not matches.empty else float("nan")
    max_entry_price_abs_pips = (
        float(matches["entry_price_abs_pips"].max()) if not matches.empty else float("nan")
    )

    _add_check(
        checks,
        check_id="ENTRY_MATCHED_COUNT_EQ_EXPECTED",
        ok=(matched_rows == expected_rows),
        severity="high",
        metric="entry_matched_count",
        value=matched_rows,
        expected=expected_rows,
        operator="==",
        detail=f"missing={missing_rows} extra={extra_rows}",
    )
    _add_check(
        checks,
        check_id="ENTRY_MISSING_EXPECTED_EQ_0",
        ok=(missing_rows == 0),
        severity="high",
        metric="entry_missing_expected_count",
        value=missing_rows,
        expected=0,
        operator="==",
        detail="strict parity requires no missing expected executions",
    )
    _add_check(
        checks,
        check_id="ENTRY_EXTRA_ACTUAL_EQ_0",
        ok=(extra_rows == 0),
        severity="high",
        metric="entry_extra_actual_count",
        value=extra_rows,
        expected=0,
        operator="==",
        detail="strict parity requires no extra actual executions",
    )
    _add_check(
        checks,
        check_id="ENTRY_MAX_ABS_TIME_SEC_LE_TOL",
        ok=pd.notna(max_entry_time_abs_sec) and (float(max_entry_time_abs_sec) <= float(time_tolerance_sec)),
        severity="high",
        metric="entry_max_abs_time_sec",
        value=float(max_entry_time_abs_sec) if pd.notna(max_entry_time_abs_sec) else float("nan"),
        expected=float(time_tolerance_sec),
        operator="<=",
        detail="max absolute entry timestamp delta across matched entries",
    )
    _add_check(
        checks,
        check_id="ENTRY_MAX_ABS_PRICE_PIPS_LE_TOL",
        ok=pd.notna(max_entry_price_abs_pips)
        and (float(max_entry_price_abs_pips) <= float(price_tolerance_pips)),
        severity="high",
        metric="entry_max_abs_price_pips",
        value=float(max_entry_price_abs_pips) if pd.notna(max_entry_price_abs_pips) else float("nan"),
        expected=float(price_tolerance_pips),
        operator="<=",
        detail="max absolute entry price delta in pips across matched entries",
    )

    exit_mismatches_df, max_exit_time_abs_sec, max_exit_price_abs_pips = _evaluate_exit_mismatches(
        expected=expected_repo,
        actual=actual_exec,
        matches=matches,
        time_tolerance_sec=float(time_tolerance_sec),
        price_tolerance_abs=float(price_tolerance_abs),
        pip_size=float(pip_size),
    )
    if not exit_mismatches_df.empty:
        mismatch_rows.extend(exit_mismatches_df.to_dict(orient="records"))

    exit_mismatch_count = int(len(exit_mismatches_df))
    _add_check(
        checks,
        check_id="EXIT_MISMATCH_COUNT_EQ_0",
        ok=(exit_mismatch_count == 0),
        severity="high",
        metric="exit_mismatch_count",
        value=exit_mismatch_count,
        expected=0,
        operator="==",
        detail="strict parity requires matched exits for all matched entries",
    )
    _add_check(
        checks,
        check_id="EXIT_MAX_ABS_TIME_SEC_LE_TOL",
        ok=pd.isna(max_exit_time_abs_sec) or (float(max_exit_time_abs_sec) <= float(time_tolerance_sec)),
        severity="high",
        metric="exit_max_abs_time_sec",
        value=float(max_exit_time_abs_sec) if pd.notna(max_exit_time_abs_sec) else float("nan"),
        expected=float(time_tolerance_sec),
        operator="<=",
        detail="max absolute exit timestamp delta across matched exits",
    )
    _add_check(
        checks,
        check_id="EXIT_MAX_ABS_PRICE_PIPS_LE_TOL",
        ok=pd.isna(max_exit_price_abs_pips)
        or (float(max_exit_price_abs_pips) <= float(price_tolerance_pips)),
        severity="high",
        metric="exit_max_abs_price_pips",
        value=float(max_exit_price_abs_pips) if pd.notna(max_exit_price_abs_pips) else float("nan"),
        expected=float(price_tolerance_pips),
        operator="<=",
        detail="max absolute exit price delta in pips across matched exits",
    )

    checks_df = pd.DataFrame([c.__dict__ for c in checks])
    mismatches_df = pd.DataFrame(mismatch_rows)
    verdict = _verdict(checks_df)
    overall_pass = not bool(
        (
            (checks_df["status"].astype(str) == "fail")
            & (checks_df["severity"].astype(str).str.lower().isin({"critical", "high"}))
        ).any()
    )

    summary_df = pd.DataFrame(
        [
            {
                "symbol": sym,
                "runtime_db": str(runtime_db),
                "ctrader_events_json": str(ctrader_events_json),
                "repo_stoplimit_detail_csv": str(repo_stoplimit_detail_csv),
                "reduced_core_state_schedule_csv": str(reduced_core_state_schedule_csv)
                if reduced_core_state_schedule_csv is not None
                else "",
                "require_reduced_core_filter": bool(require_reduced_core_filter),
                "tick_root": str(tick_root),
                "start_ts": start.isoformat(),
                "end_ts": end.isoformat(),
                "time_tolerance_sec": float(time_tolerance_sec),
                "price_tolerance_pips": float(price_tolerance_pips),
                "truth_source": (
                    "repo_stoplimit_detail_reduced_core"
                    if reduced_core_state_schedule_csv is not None
                    else "repo_stoplimit_detail_full"
                ),
                "reduced_core_schedule_rows": reduced_schedule_rows,
                "repo_expected_rows_before_reduced_filter": expected_rows_before_reduced_filter,
                "repo_expected_rows": expected_rows,
                "runtime_trade_rows": runtime_rows,
                "runtime_candidate_uid_noncanonical_rows": noncanonical_candidate_uid_rows,
                "runtime_candidate_uid_oco_only_rows": candidate_uid_oco_only_rows,
                "ctrader_event_position_rows": events_rows,
                "matched_entry_rows": matched_rows,
                "missing_expected_rows": missing_rows,
                "extra_actual_rows": extra_rows,
                "exit_mismatch_rows": exit_mismatch_count,
                "entry_max_abs_time_sec": float(max_entry_time_abs_sec)
                if pd.notna(max_entry_time_abs_sec)
                else float("nan"),
                "entry_max_abs_price_pips": float(max_entry_price_abs_pips)
                if pd.notna(max_entry_price_abs_pips)
                else float("nan"),
                "exit_max_abs_time_sec": float(max_exit_time_abs_sec)
                if pd.notna(max_exit_time_abs_sec)
                else float("nan"),
                "exit_max_abs_price_pips": float(max_exit_price_abs_pips)
                if pd.notna(max_exit_price_abs_pips)
                else float("nan"),
                "runtime_closed_rows": runtime_closed_rows,
                "ctrader_closed_rows": events_closed_rows,
                "runtime_net_pips_closed": float(runtime_net_pips_closed),
                "ctrader_net_pips_closed": float(events_net_pips_closed),
                "net_pips_abs_diff": float(net_pips_abs_diff),
                "runtime_raw_tick_rows": raw_rows,
                "runtime_raw_tick_distinct_triplets": raw_distinct_rows,
                "runtime_raw_tick_duplicate_triplets": raw_duplicate_rows,
                "hist_tick_rows": hist_rows,
                "runtime_raw_tick_distinct_coverage_ratio_vs_hist": (
                    float(raw_coverage_ratio) if pd.notna(raw_coverage_ratio) else float("nan")
                ),
                "overall_pass": bool(overall_pass),
                "execution_parity_verdict": verdict,
                "histdata_execution_parity_verdict": verdict,
                "evaluated_at_utc": now_utc,
            }
        ]
    )

    summary_df.to_csv(out_summary_csv, index=False)
    checks_df.to_csv(out_checks_csv, index=False)
    mismatches_df.to_csv(out_mismatches_csv, index=False)

    failed_checks = checks_df[checks_df["status"].astype(str) == "fail"].copy()
    report_lines = [
        "# cTrader Execution Parity",
        "",
        f"- symbol: `{sym}`",
        f"- runtime_db: `{runtime_db}`",
        f"- ctrader_events_json: `{ctrader_events_json}`",
        f"- repo_stoplimit_detail_csv: `{repo_stoplimit_detail_csv}`",
        f"- reduced_core_state_schedule_csv: `{reduced_core_state_schedule_csv}`",
        f"- require_reduced_core_filter: `{bool(require_reduced_core_filter)}`",
        f"- tick_root: `{tick_root}`",
        f"- start_ts: `{start.isoformat()}`",
        f"- end_ts: `{end.isoformat()}`",
        f"- time_tolerance_sec: `{float(time_tolerance_sec)}`",
        f"- price_tolerance_pips: `{float(price_tolerance_pips)}`",
        "",
        "## Verdict",
        f"- execution_parity_verdict: `{verdict.upper()}`",
        f"- overall_pass: `{bool(overall_pass)}`",
        "",
        "## Summary",
        _table(summary_df),
        "",
        "## Failed Checks",
        _table(failed_checks),
        "",
        "## All Checks",
        _table(checks_df),
        "",
        "## Mismatches",
        _table(mismatches_df.head(200)),
        "",
    ]
    report_out.write_text("\n".join(report_lines), encoding="utf-8")
    return summary_df, checks_df, mismatches_df


def main() -> None:
    p = argparse.ArgumentParser(description="Validate cTrader execution parity: repo vs cTrader")
    p.add_argument("--symbol", required=True)
    p.add_argument("--runtime-db", required=True)
    p.add_argument("--ctrader-events-json", required=True)
    p.add_argument("--repo-stoplimit-detail-csv", required=True)
    p.add_argument("--reduced-core-state-schedule-csv", default="")
    p.add_argument("--require-reduced-core-filter", default="false")
    p.add_argument("--tick-root", default=str(DEFAULT_CANONICAL_ROOT))
    p.add_argument("--start-ts", required=True)
    p.add_argument("--end-ts", required=True)
    p.add_argument("--time-tolerance-sec", type=float, default=1.0)
    p.add_argument("--price-tolerance-pips", type=float, default=0.1)
    p.add_argument(
        "--out-summary-csv",
        default="data/analysis/backtest_reconcile/ctrader_execution_parity_summary.csv",
    )
    p.add_argument(
        "--out-checks-csv",
        default="data/analysis/backtest_reconcile/ctrader_execution_parity_checks.csv",
    )
    p.add_argument(
        "--out-mismatches-csv",
        default="data/analysis/backtest_reconcile/ctrader_execution_parity_mismatches.csv",
    )
    p.add_argument(
        "--report-out",
        default="docs/analysis/ctrader_execution_parity_report.md",
    )
    args = p.parse_args()

    summary, checks, mismatches = run(
        symbol=str(args.symbol),
        runtime_db=Path(str(args.runtime_db)),
        ctrader_events_json=Path(str(args.ctrader_events_json)),
        repo_stoplimit_detail_csv=Path(str(args.repo_stoplimit_detail_csv)),
        reduced_core_state_schedule_csv=(
            Path(str(args.reduced_core_state_schedule_csv))
            if str(args.reduced_core_state_schedule_csv).strip()
            else None
        ),
        require_reduced_core_filter=str(args.require_reduced_core_filter).strip().lower()
        in {"1", "true", "yes", "y"},
        tick_root=Path(str(args.tick_root)),
        start_ts=str(args.start_ts),
        end_ts=str(args.end_ts),
        time_tolerance_sec=float(args.time_tolerance_sec),
        price_tolerance_pips=float(args.price_tolerance_pips),
        out_summary_csv=Path(str(args.out_summary_csv)),
        out_checks_csv=Path(str(args.out_checks_csv)),
        out_mismatches_csv=Path(str(args.out_mismatches_csv)),
        report_out=Path(str(args.report_out)),
    )
    verdict = (
        str(
            summary.iloc[0].get(
                "execution_parity_verdict",
                summary.iloc[0].get("histdata_execution_parity_verdict", "red"),
            )
        ).upper()
        if len(summary) > 0
        else "RED"
    )
    print(f"wrote summary: {args.out_summary_csv} rows={len(summary)}")
    print(f"wrote checks: {args.out_checks_csv} rows={len(checks)}")
    print(f"wrote mismatches: {args.out_mismatches_csv} rows={len(mismatches)}")
    print(f"wrote report: {args.report_out}")
    print(f"execution_parity_verdict={verdict.lower()}")


if __name__ == "__main__":
    main()
