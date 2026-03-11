#!/usr/bin/env python3
"""Replay HistData ticks through FastAPI TestClient using cBot-like cadence.

This script is the no-cTrader harness for pre-deploy iteration:
1) Replays raw HistData ticks into API `/backfill` + `/ticks` or `/ticks/batch`.
2) Triggers `/predict` only when bars complete (`completed_bar_ticks`) like cBot.
3) Matches runtime selected rows against reduced-core repo execution truth keys
   (`candidate_uid`, `close_ts`) and writes synthetic trade lifecycle rows
   (`/trades/open`, `/trades/update`) plus an events JSON.
4) Runs `validate_histdata_ctrader_execution_parity.py` for a strict parity gate.
"""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@dataclass
class ReplayStats:
    ticks_streamed: int
    ticks_accepted: int
    ticks_dropped: int
    bars_completed_events: int
    predict_calls: int
    predict_warmup_422: int
    predict_errors: int
    selected_rows_runtime: int
    expected_rows_reduced: int
    selected_missing_expected: int
    selected_extra_runtime: int
    fallback_match_count: int


def _load_exec_parity_module():
    here = Path(__file__).resolve().parent
    target = here / "validate_histdata_ctrader_execution_parity.py"
    spec = importlib.util.spec_from_file_location(
        "validate_histdata_ctrader_execution_parity", target
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module spec for {target}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _table(df: pd.DataFrame) -> str:
    if df.empty:
        return "_empty_"
    try:
        return df.to_markdown(index=False)
    except Exception:
        return df.to_csv(index=False)


def _to_utc(s: pd.Series) -> pd.Series:
    try:
        return pd.to_datetime(s, utc=True, errors="coerce", format="mixed")
    except TypeError:
        return pd.to_datetime(s, utc=True, errors="coerce")


def _parse_ts(name: str, raw: str) -> pd.Timestamp:
    txt = str(raw).strip()
    if not txt:
        raise ValueError(f"{name} is required")
    ts = pd.to_datetime(txt, utc=True, errors="coerce")
    if pd.isna(ts):
        raise ValueError(f"invalid {name}: {raw!r}")
    return ts


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
    if len(txt) == 7 and txt[4] == "-":
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
        out = out[out["symbol"] == symbol.upper().strip()].copy()

    out["state_id"] = out["state_id"].astype(str).str.strip()
    out["test_month"] = out["test_month"].map(_normalize_test_month)
    out = out[(out["state_id"] != "") & (out["test_month"] != "")].copy()

    months = set(_month_tags_iso_between(start, end))
    out = out[out["test_month"].isin(months)].copy()

    out["bar_ticks"] = pd.to_numeric(out["bar_ticks"], errors="coerce").astype("Int64")
    out["horizon"] = pd.to_numeric(out["horizon"], errors="coerce").astype("Int64")
    out = out.dropna(subset=["bar_ticks", "horizon"]).copy()
    if out.empty:
        return pd.DataFrame(columns=["test_month", "bar_ticks", "horizon", "state_id"])

    out["bar_ticks"] = out["bar_ticks"].astype(int)
    out["horizon"] = out["horizon"].astype(int)
    out = out[["test_month", "bar_ticks", "horizon", "state_id"]].drop_duplicates()
    out = out.sort_values(["test_month", "bar_ticks", "horizon", "state_id"]).reset_index(drop=True)
    return out


def _load_expected_detail_rows(
    *,
    detail_csv: Path,
    symbol: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.DataFrame:
    if not detail_csv.exists():
        return pd.DataFrame(
            columns=[
                "candidate_uid",
                "close_ts",
                "side",
                "entry_price",
                "entry_ts",
                "exit_ts",
            ]
        )

    df = pd.read_csv(detail_csv)
    if df.empty:
        return pd.DataFrame(
            columns=[
                "candidate_uid",
                "close_ts",
                "side",
                "entry_price",
                "entry_ts",
                "exit_ts",
            ]
        )

    out = pd.DataFrame()
    out["candidate_uid"] = df.get("candidate_uid", pd.Series(dtype=str)).astype(str)
    out["close_ts"] = _to_utc(df.get("close_ts", pd.Series(dtype=object)))
    out["side"] = df.get("side", pd.Series(dtype=str)).astype(str).str.upper().str.strip()
    out["entry_price"] = pd.to_numeric(
        df.get("barrier_px", pd.Series(dtype=float)), errors="coerce"
    )
    out["entry_ts"] = _to_utc(df.get("touch_open_ts", pd.Series(dtype=object)))
    out["exit_ts"] = _to_utc(df.get("touch_close_ts", pd.Series(dtype=object)))

    parts = out["candidate_uid"].str.split("|", expand=True)
    if parts.shape[1] >= 2:
        out["uid_symbol"] = parts[1].astype(str).str.upper().str.strip()
    else:
        out["uid_symbol"] = ""

    out = out[out["uid_symbol"] == symbol.upper().strip()].copy()
    out = out[out["entry_ts"].notna()].copy()
    out = out[(out["entry_ts"] >= start) & (out["entry_ts"] < end)].copy()
    out = out.dropna(subset=["candidate_uid", "close_ts", "entry_price", "entry_ts", "side"])
    out = out[["candidate_uid", "close_ts", "side", "entry_price", "entry_ts", "exit_ts"]]
    out = out.reset_index(drop=True)
    return out


def _load_expected_selected_rows(
    *,
    predictions_parquet: Path,
    symbol: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.DataFrame:
    if not predictions_parquet.exists():
        return pd.DataFrame(columns=["candidate_uid", "close_ts"])

    con = duckdb.connect()
    try:
        close_ts_expr = "try_cast(close_ts AS TIMESTAMP WITH TIME ZONE)"
        df = con.execute(
            f"""
            SELECT
                candidate_uid,
                {close_ts_expr} AS close_ts,
                try_cast(selected_exec AS INTEGER) AS selected_exec
            FROM read_parquet(?)
            WHERE upper(split_part(candidate_uid, '|', 2)) = ?
              AND {close_ts_expr} >= ?
              AND {close_ts_expr} < ?
            ORDER BY {close_ts_expr}
            """,
            [
                str(predictions_parquet),
                str(symbol).upper().strip(),
                start.to_pydatetime(),
                end.to_pydatetime(),
            ],
        ).fetchdf()
    finally:
        con.close()

    if df.empty:
        return pd.DataFrame(columns=["candidate_uid", "close_ts"])

    out = pd.DataFrame()
    out["candidate_uid"] = df.get("candidate_uid", pd.Series(dtype=str)).astype(str)
    out["close_ts"] = _to_utc(df.get("close_ts", pd.Series(dtype=object)))
    out["selected_exec"] = pd.to_numeric(
        df.get("selected_exec", pd.Series(dtype=float)), errors="coerce"
    ).fillna(0).astype(int)
    out = out[out["selected_exec"] == 1].copy()
    out = out.dropna(subset=["candidate_uid", "close_ts"]).reset_index(drop=True)
    return out[["candidate_uid", "close_ts"]]


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
    out = out.drop(columns=["state_id", "bar_ticks", "horizon", "test_month"])
    return out.reset_index(drop=True)


def _quote_sql_path(path: Path) -> str:
    return "'" + str(path).replace("'", "''") + "'"


def _all_symbol_tick_files(symbol: str, tick_root: Path) -> list[Path]:
    return sorted(
        p
        for p in (tick_root / symbol).glob(f"{symbol}_*_ticks.parquet")
        if p.is_file()
    )


def _load_hist_ticks_for_replay(
    *,
    symbol: str,
    tick_root: Path,
    start: pd.Timestamp,
    end: pd.Timestamp,
    warmup_ticks: int,
    lookback_days: int,
    warmup_source: str,
    phase_bar_ticks: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    src_mode = str(warmup_source or "history_tail").strip().lower()
    all_files = _all_symbol_tick_files(symbol, tick_root)
    if not all_files:
        return (
            pd.DataFrame(columns=["ts", "bid", "ask"]),
            pd.DataFrame(columns=["ts", "bid", "ask"]),
        )

    if src_mode == "month_start":
        query_start = start.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        files = [
            tick_root / symbol / f"{symbol}_{m}_ticks.parquet"
            for m in _month_tags_between(query_start, end)
            if (tick_root / symbol / f"{symbol}_{m}_ticks.parquet").exists()
        ]
    elif src_mode == "lookback_days":
        query_start = start - pd.Timedelta(days=max(1, int(lookback_days)))
        files = [
            tick_root / symbol / f"{symbol}_{m}_ticks.parquet"
            for m in _month_tags_between(query_start, end)
            if (tick_root / symbol / f"{symbol}_{m}_ticks.parquet").exists()
        ]
    else:
        query_start = None
        files = all_files

    if not files:
        return (
            pd.DataFrame(columns=["ts", "bid", "ask"]),
            pd.DataFrame(columns=["ts", "bid", "ask"]),
        )

    files_sql = "[" + ",".join(_quote_sql_path(p) for p in files) + "]"
    con = duckdb.connect()
    try:
        ts_expr = "try_cast(timestamp AS TIMESTAMP WITH TIME ZONE)"
        if src_mode == "history_tail":
            pre_count = int(
                con.execute(
                    f"""
                    SELECT COUNT(*)
                    FROM read_parquet({files_sql})
                    WHERE {ts_expr} < ?
                    """,
                    [start.to_pydatetime()],
                ).fetchone()[0]
                or 0
            )
            phase_mod = 0
            if int(phase_bar_ticks) > 0:
                phase_mod = int(pre_count % int(phase_bar_ticks))
            keep = max(0, int(warmup_ticks)) + int(phase_mod)
            warmup = (
                con.execute(
                    f"""
                    SELECT ts, bid, ask
                    FROM (
                        SELECT
                            {ts_expr} AS ts,
                            try_cast(bid AS DOUBLE) AS bid,
                            try_cast(ask AS DOUBLE) AS ask
                        FROM read_parquet({files_sql})
                        WHERE {ts_expr} < ?
                        ORDER BY {ts_expr} DESC
                        LIMIT {keep}
                    ) q
                    ORDER BY ts
                    """,
                    [start.to_pydatetime()],
                ).fetchdf()
                if keep > 0
                else pd.DataFrame(columns=["ts", "bid", "ask"])
            )
            stream = con.execute(
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
            df = pd.concat([warmup, stream], ignore_index=True)
        else:
            df = con.execute(
                f"""
                SELECT
                    {ts_expr} AS ts,
                    try_cast(bid AS DOUBLE) AS bid,
                    try_cast(ask AS DOUBLE) AS ask
                FROM read_parquet({files_sql})
                WHERE {ts_expr} >= ? AND {ts_expr} < ?
                ORDER BY {ts_expr}
                """,
                [query_start.to_pydatetime(), end.to_pydatetime()],
            ).fetchdf()
    finally:
        con.close()

    if df.empty:
        return (
            pd.DataFrame(columns=["ts", "bid", "ask"]),
            pd.DataFrame(columns=["ts", "bid", "ask"]),
        )

    df["ts"] = _to_utc(df.get("ts", pd.Series(dtype=object)))
    df["bid"] = pd.to_numeric(df.get("bid", pd.Series(dtype=float)), errors="coerce")
    df["ask"] = pd.to_numeric(df.get("ask", pd.Series(dtype=float)), errors="coerce")
    df = df.dropna(subset=["ts", "bid", "ask"]).reset_index(drop=True)

    stream = df[(df["ts"] >= start) & (df["ts"] < end)].copy().reset_index(drop=True)
    if stream.empty:
        return (
            pd.DataFrame(columns=["ts", "bid", "ask"]),
            pd.DataFrame(columns=["ts", "bid", "ask"]),
        )

    pre = df[df["ts"] < start].copy()
    if src_mode in {"month_start", "history_tail"}:
        warmup = pre.reset_index(drop=True)
    else:
        phase_mod = 0
        if int(phase_bar_ticks) > 0:
            phase_mod = int(len(pre) % int(phase_bar_ticks))
        keep = max(0, int(warmup_ticks)) + int(phase_mod)
        warmup = pre.tail(keep if keep > 0 else len(pre)).reset_index(drop=True)
    return warmup[["ts", "bid", "ask"]], stream[["ts", "bid", "ask"]]


def _norm_ts_key(ts: pd.Timestamp | datetime | Any) -> pd.Timestamp:
    return pd.to_datetime(ts, utc=True, errors="coerce").floor("us")


def _match_expected_runtime_on_close_ts(
    *,
    expected: pd.DataFrame,
    runtime: pd.DataFrame,
    tolerance_sec: float,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if expected.empty and runtime.empty:
        empty = pd.DataFrame(columns=["expected_idx", "runtime_idx", "abs_dt_sec"])
        return empty, expected.copy(), runtime.copy()

    exp = expected.copy().reset_index(drop=True)
    act = runtime.copy().reset_index(drop=True)
    exp["expected_idx"] = exp.index
    act["runtime_idx"] = act.index

    unmatched_runtime: set[int] = set(act["runtime_idx"].astype(int).tolist())
    matched: list[dict[str, Any]] = []

    for _, er in exp.sort_values("close_ts").iterrows():
        exp_idx = int(er["expected_idx"])
        uid = str(er["candidate_uid"])
        eclose = _norm_ts_key(er["close_ts"])
        if pd.isna(eclose):
            continue

        cands = act[
            (act["candidate_uid"].astype(str) == uid)
            & (act["runtime_idx"].astype(int).isin(unmatched_runtime))
        ].copy()
        if cands.empty:
            continue

        cands["close_ts_norm"] = cands["close_ts"].map(_norm_ts_key)
        cands["abs_dt_sec"] = (cands["close_ts_norm"] - eclose).dt.total_seconds().abs()
        cands = cands[cands["abs_dt_sec"] <= float(tolerance_sec)].copy()
        if cands.empty:
            continue

        cands = cands.sort_values(["abs_dt_sec", "runtime_idx"])
        best = cands.iloc[0]
        runtime_idx = int(best["runtime_idx"])
        unmatched_runtime.discard(runtime_idx)
        matched.append(
            {
                "expected_idx": exp_idx,
                "runtime_idx": runtime_idx,
                "abs_dt_sec": float(best["abs_dt_sec"]),
                "match_mode": "timestamp",
            }
        )

    matched_df = pd.DataFrame(matched)
    matched_expected = (
        set(matched_df["expected_idx"].astype(int).tolist()) if not matched_df.empty else set()
    )
    matched_runtime = (
        set(matched_df["runtime_idx"].astype(int).tolist()) if not matched_df.empty else set()
    )

    missing_expected = exp[~exp["expected_idx"].astype(int).isin(matched_expected)].copy()
    extra_runtime = act[~act["runtime_idx"].astype(int).isin(matched_runtime)].copy()
    return matched_df, missing_expected, extra_runtime


def _apply_sequence_fallback_matches(
    *,
    all_expected: pd.DataFrame,
    all_runtime: pd.DataFrame,
    matches: pd.DataFrame,
    missing_expected: pd.DataFrame,
    extra_runtime: pd.DataFrame,
    max_gap_sec: float,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    exp_all = all_expected.copy().reset_index(drop=True)
    act_all = all_runtime.copy().reset_index(drop=True)
    if "expected_idx" not in exp_all.columns:
        exp_all["expected_idx"] = exp_all.index
    if "runtime_idx" not in act_all.columns:
        act_all["runtime_idx"] = act_all.index

    miss = missing_expected.copy().reset_index(drop=True)
    if "expected_idx" not in miss.columns:
        miss = miss.merge(
            exp_all[["expected_idx", "candidate_uid", "close_ts"]],
            on=["candidate_uid", "close_ts"],
            how="left",
        )

    extra = extra_runtime.copy().reset_index(drop=True)
    if "runtime_idx" not in extra.columns:
        extra = extra.merge(
            act_all[["runtime_idx", "candidate_uid", "close_ts"]],
            on=["candidate_uid", "close_ts"],
            how="left",
        )

    if miss.empty or extra.empty:
        return matches, miss, extra

    fallback_rows: list[dict[str, Any]] = []
    max_gap = float(max_gap_sec)
    unmatched_runtime: set[int] = set(extra["runtime_idx"].astype(int).tolist())

    for _, er in miss.sort_values("close_ts").iterrows():
        exp_idx = int(er["expected_idx"])
        uid = str(er["candidate_uid"])
        e_ts = _norm_ts_key(er.get("close_ts"))
        if pd.isna(e_ts):
            continue

        cands = extra[
            (extra["candidate_uid"].astype(str) == uid)
            & (extra["runtime_idx"].astype(int).isin(unmatched_runtime))
        ].copy()
        if cands.empty:
            continue
        cands["close_ts_norm"] = cands["close_ts"].map(_norm_ts_key)
        cands["abs_dt_sec"] = (cands["close_ts_norm"] - e_ts).dt.total_seconds().abs()
        cands = cands[cands["abs_dt_sec"] <= max_gap].copy()
        if cands.empty:
            continue
        cands = cands.sort_values(["abs_dt_sec", "runtime_idx"])
        best = cands.iloc[0]
        runtime_idx = int(best["runtime_idx"])
        unmatched_runtime.discard(runtime_idx)
        fallback_rows.append(
            {
                "expected_idx": exp_idx,
                "runtime_idx": runtime_idx,
                "abs_dt_sec": float(best["abs_dt_sec"]),
                "match_mode": "fallback_nearest",
            }
        )

    if fallback_rows:
        fdf = pd.DataFrame(fallback_rows)
        all_matches = pd.concat([matches, fdf], ignore_index=True)
    else:
        all_matches = matches.copy()

    matched_expected_ids = (
        set(all_matches["expected_idx"].astype(int).tolist()) if not all_matches.empty else set()
    )
    matched_runtime_ids = (
        set(all_matches["runtime_idx"].astype(int).tolist()) if not all_matches.empty else set()
    )
    out_missing_expected = exp_all[
        ~exp_all["expected_idx"].astype(int).isin(matched_expected_ids)
    ].copy()
    out_extra_runtime = act_all[
        ~act_all["runtime_idx"].astype(int).isin(matched_runtime_ids)
    ].copy()
    return all_matches, out_missing_expected, out_extra_runtime


def _ts_to_iso(ts: pd.Timestamp | datetime) -> str:
    out = _norm_ts_key(ts)
    if pd.isna(out):
        raise ValueError(f"invalid timestamp: {ts!r}")
    return out.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _ts_to_epoch_ms(ts: pd.Timestamp | datetime) -> int:
    out = _norm_ts_key(ts)
    if pd.isna(out):
        raise ValueError(f"invalid timestamp: {ts!r}")
    return int(out.value // 1_000_000)


def _norm_side(raw: str) -> str:
    txt = str(raw).strip().upper()
    if txt in {"BUY", "B", "LONG", "1", "+1", "TRUE"}:
        return "BUY"
    if txt in {"SELL", "S", "SHORT", "-1", "0", "FALSE"}:
        return "SELL"
    return txt


def _predict_warmup_422(resp: Any) -> bool:
    if int(getattr(resp, "status_code", 0)) != 422:
        return False
    txt = str(getattr(resp, "text", "") or "")
    return "insufficient warmup bars" in txt.lower()


def _simulate(
    *,
    symbol: str,
    runtime_db: Path,
    expected_selected_keys: pd.DataFrame,
    expected_detail: pd.DataFrame,
    warmup: pd.DataFrame,
    stream: pd.DataFrame,
    events_json: Path,
    model_month: str,
    models_dir: Path,
    history_dir: Path,
    missing_month_policy: str,
    ftmo_enabled_override: bool,
    requested_lot_size: float,
    enable_tick_batch: bool,
    tick_batch_size: int,
    selected_time_tolerance_sec: float,
    enable_sequence_fallback: bool,
    sequence_fallback_max_gap_sec: float,
    reset_runtime_db: bool,
    record_raw_ticks: bool,
) -> tuple[ReplayStats, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    runtime_db.parent.mkdir(parents=True, exist_ok=True)
    events_json.parent.mkdir(parents=True, exist_ok=True)
    if reset_runtime_db and runtime_db.exists():
        runtime_db.unlink()

    os.environ["BEHEMOTH_GOVERNANCE_MODE"] = "historical_auto"
    os.environ["BEHEMOTH_GOVERNANCE_HISTORY_DIR"] = str(history_dir)
    os.environ["BEHEMOTH_GOVERNANCE_MISSING_MONTH_POLICY"] = str(missing_month_policy)
    os.environ["BEHEMOTH_MODELS_DIR"] = str(models_dir)
    os.environ["BEHEMOTH_STATE_DB"] = str(runtime_db)
    os.environ["BEHEMOTH_RECORD_RAW_TICKS"] = "true" if record_raw_ticks else "false"
    if model_month:
        os.environ["BEHEMOTH_FORCE_MODEL_MONTH"] = model_month
    else:
        os.environ.pop("BEHEMOTH_FORCE_MODEL_MONTH", None)

    server = importlib.import_module("src.behemoth.api.server")
    app = server.app

    requested_volume_units = float(requested_lot_size) * 100000.0

    selected_rows: list[dict[str, Any]] = []
    ticks_accepted = 0
    ticks_dropped = 0
    bars_completed_events = 0
    predict_calls = 0
    predict_warmup_422 = 0
    predict_errors = 0
    client_tick_seq = 0

    with TestClient(app) as client:
        health = client.get("/health")
        if health.status_code != 200:
            raise RuntimeError(f"/health failed: status={health.status_code} body={health.text}")

        warmup_payload = {
            "symbol": symbol,
            "bar_ticks": 100,
            "ticks": [
                {
                    "symbol": symbol,
                    "timestamp": _ts_to_iso(ts),
                    "bid": float(bid),
                    "ask": float(ask),
                    "tick_volume": 1.0,
                }
                for ts, bid, ask in zip(warmup["ts"], warmup["bid"], warmup["ask"], strict=False)
            ],
        }
        backfill = client.post("/backfill", json=warmup_payload)
        if backfill.status_code != 201:
            raise RuntimeError(
                f"/backfill failed: status={backfill.status_code} body={backfill.text}"
            )

        if ftmo_enabled_override:
            # Prime FTMO snapshot so risk status has account context.
            snapshot = client.post(
                "/risk/ftmo/snapshot",
                json={
                    "symbol": symbol,
                    "balance": 100000.0,
                    "equity": 100000.0,
                    "snapshot_ts": _ts_to_iso(datetime.now(timezone.utc)),
                },
            )
            if snapshot.status_code not in {200, 201}:
                raise RuntimeError(
                    f"/risk/ftmo/snapshot failed: status={snapshot.status_code} body={snapshot.text}"
                )

        pending_batch: list[dict[str, Any]] = []

        def _predict_on_completed(completed_bar_ticks: list[int]) -> None:
            nonlocal predict_calls, predict_warmup_422, predict_errors
            if not completed_bar_ticks:
                return
            unique_ticks = sorted({int(x) for x in completed_bar_ticks if int(x) > 0})
            if not unique_ticks:
                return

            predict_calls += 1
            payload = {
                "symbol": symbol,
                "requested_volume_units": requested_volume_units,
                "requested_lot_size": requested_lot_size,
                "ftmo_enabled_override": bool(ftmo_enabled_override),
                "completed_bar_ticks": unique_ticks,
            }
            pr = client.post("/predict", json=payload)
            if pr.status_code == 200:
                rows = pr.json()
                for row in rows:
                    if int(row.get("selected_exec", 0)) != 1:
                        continue
                    if bool(row.get("risk_blocked", False)):
                        continue
                    selected_rows.append(
                        {
                            "candidate_uid": str(row.get("candidate_uid", "")).strip(),
                            "close_ts": _norm_ts_key(row.get("close_ts")),
                            "pred_prob": float(row.get("pred_prob", 0.0)),
                            "threshold_exec": float(row.get("threshold_exec", 0.0)),
                            "bar_ticks": int(row.get("bar_ticks", 0) or 0),
                            "horizon": int(row.get("horizon", 0) or 0),
                        }
                    )
                return

            if _predict_warmup_422(pr):
                predict_warmup_422 += 1
                return

            predict_errors += 1

        def _post_tick_batch(chunk: list[dict[str, Any]]) -> None:
            nonlocal ticks_accepted, ticks_dropped, bars_completed_events
            if not chunk:
                return
            resp = client.post(
                "/ticks/batch",
                json={"symbol": symbol, "ticks": chunk},
            )
            if resp.status_code != 201:
                raise RuntimeError(
                    f"/ticks/batch failed: status={resp.status_code} body={resp.text}"
                )
            body = resp.json()
            ticks_accepted += int(body.get("accepted_count", 0) or 0)
            ticks_dropped += int(body.get("dropped_count", 0) or 0)
            completed = [int(x) for x in (body.get("completed_bar_ticks") or [])]
            if completed:
                bars_completed_events += len(completed)
                _predict_on_completed(completed)

        def _post_tick_single(tick: dict[str, Any]) -> None:
            nonlocal ticks_accepted, ticks_dropped, bars_completed_events
            resp = client.post("/ticks", json=tick)
            if resp.status_code != 201:
                raise RuntimeError(f"/ticks failed: status={resp.status_code} body={resp.text}")
            body = resp.json()
            if bool(body.get("tick_accepted", False)):
                ticks_accepted += 1
            else:
                ticks_dropped += 1
            completed = [int(x) for x in (body.get("completed_bar_ticks") or [])]
            if completed:
                bars_completed_events += len(completed)
                _predict_on_completed(completed)

        for ts, bid, ask in zip(stream["ts"], stream["bid"], stream["ask"], strict=False):
            client_tick_seq += 1
            tick = {
                "symbol": symbol,
                "timestamp": _ts_to_iso(ts),
                "bid": float(bid),
                "ask": float(ask),
                "tick_volume": 1.0,
                "client_tick_seq": int(client_tick_seq),
            }

            if enable_tick_batch:
                pending_batch.append(tick)
                if len(pending_batch) >= max(1, int(tick_batch_size)):
                    _post_tick_batch(pending_batch)
                    pending_batch = []
            else:
                _post_tick_single(tick)

        if pending_batch:
            _post_tick_batch(pending_batch)

        runtime_selected = pd.DataFrame(selected_rows)
        if runtime_selected.empty:
            runtime_selected = pd.DataFrame(
                columns=[
                    "candidate_uid",
                    "close_ts",
                    "pred_prob",
                    "threshold_exec",
                    "bar_ticks",
                    "horizon",
                ]
            )
        else:
            runtime_selected["candidate_uid"] = runtime_selected["candidate_uid"].astype(str)
            runtime_selected["close_ts"] = _to_utc(runtime_selected["close_ts"])

        expected_keys = expected_selected_keys[["candidate_uid", "close_ts"]].copy()
        expected_keys["candidate_uid"] = expected_keys["candidate_uid"].astype(str)
        expected_keys["close_ts"] = _to_utc(expected_keys["close_ts"])

        runtime_keys = runtime_selected[["candidate_uid", "close_ts"]].copy()
        runtime_keys = runtime_keys.dropna(subset=["candidate_uid", "close_ts"]).reset_index(
            drop=True
        )

        strict_matches, strict_missing_expected, strict_extra_runtime = _match_expected_runtime_on_close_ts(
            expected=expected_keys,
            runtime=runtime_keys,
            tolerance_sec=float(selected_time_tolerance_sec),
        )
        trade_matches = strict_matches.copy()
        trade_missing_expected = strict_missing_expected.copy()
        trade_extra_runtime = strict_extra_runtime.copy()

        if enable_sequence_fallback:
            trade_matches, trade_missing_expected, trade_extra_runtime = _apply_sequence_fallback_matches(
                all_expected=expected_keys,
                all_runtime=runtime_keys,
                matches=trade_matches,
                missing_expected=trade_missing_expected,
                extra_runtime=trade_extra_runtime,
                max_gap_sec=float(sequence_fallback_max_gap_sec),
            )

        if not trade_matches.empty:
            matched_signal_keys = expected_keys.iloc[
                trade_matches["expected_idx"].astype(int).tolist()
            ].copy()
            matched_expected = matched_signal_keys.merge(
                expected_detail,
                on=["candidate_uid", "close_ts"],
                how="inner",
            )
            matched_expected = matched_expected.drop_duplicates(
                subset=["candidate_uid", "close_ts", "entry_ts"]
            ).copy()
        else:
            matched_expected = pd.DataFrame(columns=expected_detail.columns)

        events: list[dict[str, Any]] = []
        broker_pos_seq = 100000

        for _, row in matched_expected.sort_values("entry_ts").iterrows():
            pos_id = str(broker_pos_seq)
            broker_pos_seq += 1

            side = _norm_side(str(row.get("side", "BUY")))
            side_for_open = "BUY" if side == "BUY" else "SELL"
            side_for_event = "Buy" if side_for_open == "BUY" else "Sell"

            open_resp = client.post(
                "/trades/open",
                json={
                    "symbol": symbol,
                    "candidate_uid": str(row.get("candidate_uid", "")),
                    "broker_pos_id": pos_id,
                    "side": side_for_open,
                    "entry_price": float(row.get("entry_price", 0.0)),
                    "entry_ts": _ts_to_iso(row.get("entry_ts")),
                    "horizon": int(_candidate_uid_horizon(row.get("candidate_uid")) or 1),
                },
            )
            if open_resp.status_code != 200:
                raise RuntimeError(
                    f"/trades/open failed: status={open_resp.status_code} body={open_resp.text}"
                )

            entry_ts = _norm_ts_key(row.get("entry_ts"))
            entry_px = float(row.get("entry_price", 0.0))
            events.append(
                {
                    "event": "Create Position",
                    "positionId": int(pos_id),
                    "time": _ts_to_epoch_ms(entry_ts),
                    "type": side_for_event,
                    "entryPrice": entry_px,
                }
            )

            exit_ts = _norm_ts_key(row.get("exit_ts"))
            if pd.notna(exit_ts):
                close_resp = client.post(
                    "/trades/update",
                    json={
                        "symbol": symbol,
                        "broker_pos_id": pos_id,
                        "status": "CLOSED",
                        "exit_price": entry_px,
                        "exit_ts": _ts_to_iso(exit_ts),
                        "pnl_pips": 0.0,
                    },
                )
                if close_resp.status_code != 200:
                    raise RuntimeError(
                        f"/trades/update failed: status={close_resp.status_code} body={close_resp.text}"
                    )
                events.append(
                    {
                        "event": "Position closed",
                        "positionId": int(pos_id),
                        "time": _ts_to_epoch_ms(exit_ts),
                        "closePrice": entry_px,
                        "pips": 0.0,
                    }
                )

        events_json.write_text(json.dumps(events, indent=2), encoding="utf-8")

    stats = ReplayStats(
        ticks_streamed=int(len(stream)),
        ticks_accepted=int(ticks_accepted),
        ticks_dropped=int(ticks_dropped),
        bars_completed_events=int(bars_completed_events),
        predict_calls=int(predict_calls),
        predict_warmup_422=int(predict_warmup_422),
        predict_errors=int(predict_errors),
        selected_rows_runtime=int(len(runtime_keys)),
        expected_rows_reduced=int(len(expected_keys)),
        selected_missing_expected=int(len(strict_missing_expected)),
        selected_extra_runtime=int(len(strict_extra_runtime)),
        fallback_match_count=int(
            (
                trade_matches.get("match_mode", pd.Series(dtype=str)).astype(str)
                == "fallback_nearest"
            ).sum()
        ),
    )
    return stats, runtime_keys, strict_missing_expected, strict_extra_runtime


def _build_stage12_checks_df(
    *,
    symbol: str,
    stats: ReplayStats,
    execution_checks_df: pd.DataFrame,
) -> pd.DataFrame:
    signal_pass = stats.selected_missing_expected == 0 and stats.selected_extra_runtime == 0
    signal_rows = pd.DataFrame(
        [
            {
                "check_family": "signal",
                "symbol": symbol,
                "check_id": "API_SIGNAL_MISSING_EXPECTED_EQ_0",
                "check_name": "api_signal_missing_expected_eq_0",
                "status": "pass" if stats.selected_missing_expected == 0 else "fail",
                "severity": "critical",
                "metric_name": "selected_missing_expected",
                "metric_value": int(stats.selected_missing_expected),
                "threshold": 0,
                "comparator": "==",
                "details": "",
            },
            {
                "check_family": "signal",
                "symbol": symbol,
                "check_id": "API_SIGNAL_EXTRA_RUNTIME_EQ_0",
                "check_name": "api_signal_extra_runtime_eq_0",
                "status": "pass" if stats.selected_extra_runtime == 0 else "fail",
                "severity": "critical",
                "metric_name": "selected_extra_runtime",
                "metric_value": int(stats.selected_extra_runtime),
                "threshold": 0,
                "comparator": "==",
                "details": "",
            },
            {
                "check_family": "signal",
                "symbol": symbol,
                "check_id": "API_SIGNAL_PARITY_PASS_TRUE",
                "check_name": "api_signal_parity_pass_true",
                "status": "pass" if signal_pass else "fail",
                "severity": "critical",
                "metric_name": "signal_parity_pass",
                "metric_value": int(signal_pass),
                "threshold": 1,
                "comparator": "==",
                "details": "",
            },
        ]
    )
    if execution_checks_df.empty:
        return signal_rows
    exec_rows = execution_checks_df.copy()
    exec_rows.insert(0, "check_family", "execution")
    if "symbol" not in exec_rows.columns:
        exec_rows["symbol"] = symbol
    return pd.concat([signal_rows, exec_rows], ignore_index=True, sort=False)


def _build_stage12_summary_df(
    *,
    symbol: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
    runtime_db: Path,
    events_json: Path,
    stats: ReplayStats,
    execution_summary_df: pd.DataFrame,
    execution_checks_df: pd.DataFrame,
    warmup_source: str,
    warmup_ticks: int,
    warmup_sent: int,
) -> pd.DataFrame:
    signal_pass = stats.selected_missing_expected == 0 and stats.selected_extra_runtime == 0
    execution_pass = (
        bool(execution_summary_df.iloc[0].get("overall_pass", False))
        if not execution_summary_df.empty
        else False
    )
    execution_verdict = (
        str(execution_summary_df.iloc[0].get("histdata_execution_parity_verdict", "red")).lower()
        if not execution_summary_df.empty
        else "red"
    )
    exec_fail_total = (
        int((execution_checks_df.get("status", pd.Series(dtype=str)).astype(str) == "fail").sum())
        if not execution_checks_df.empty
        else 0
    )
    exec_fail_hc = (
        int(
            (
                (execution_checks_df.get("status", pd.Series(dtype=str)).astype(str) == "fail")
                & execution_checks_df.get("severity", pd.Series(dtype=str))
                .astype(str)
                .str.lower()
                .isin({"high", "critical"})
            ).sum()
        )
        if not execution_checks_df.empty
        else 0
    )
    stage12_pass = bool(signal_pass and execution_pass)
    return pd.DataFrame(
        [
            {
                "symbol": symbol,
                "start_ts": start.isoformat(),
                "end_ts": end.isoformat(),
                "runtime_db": str(runtime_db),
                "events_json": str(events_json),
                "warmup_source": str(warmup_source),
                "warmup_ticks_requested": int(warmup_ticks),
                "warmup_ticks_sent": int(warmup_sent),
                "ticks_streamed": int(stats.ticks_streamed),
                "ticks_accepted": int(stats.ticks_accepted),
                "ticks_dropped": int(stats.ticks_dropped),
                "bars_completed_events": int(stats.bars_completed_events),
                "predict_calls": int(stats.predict_calls),
                "predict_warmup_422": int(stats.predict_warmup_422),
                "predict_errors": int(stats.predict_errors),
                "selected_rows_runtime": int(stats.selected_rows_runtime),
                "expected_rows_reduced": int(stats.expected_rows_reduced),
                "selected_missing_expected": int(stats.selected_missing_expected),
                "selected_extra_runtime": int(stats.selected_extra_runtime),
                "signal_parity_pass": bool(signal_pass),
                "fallback_match_count": int(stats.fallback_match_count),
                "execution_parity_verdict": execution_verdict,
                "execution_parity_pass": bool(execution_pass),
                "execution_failed_checks_total": int(exec_fail_total),
                "execution_failed_checks_high_critical": int(exec_fail_hc),
                "stage12_api_parity_pass": bool(stage12_pass),
                "stage12_api_parity_verdict": "green" if stage12_pass else "red",
                "severity": "info" if stage12_pass else "critical",
                "evaluated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        ]
    )


def _write_stage12_report(
    *,
    stage12_summary_df: pd.DataFrame,
    stage12_checks_df: pd.DataFrame,
    stage12_mismatches_df: pd.DataFrame,
    stage12_report_out: Path,
    execution_report_out: Path,
) -> None:
    stage12_report_out.parent.mkdir(parents=True, exist_ok=True)
    row = stage12_summary_df.iloc[0].to_dict() if not stage12_summary_df.empty else {}
    lines = [
        "# Stage 12 API Parity Report",
        "",
        f"- verdict: `{str(row.get('stage12_api_parity_verdict', 'red')).upper()}`",
        f"- stage12_api_parity_pass: `{bool(row.get('stage12_api_parity_pass', False))}`",
        f"- signal_parity_pass: `{bool(row.get('signal_parity_pass', False))}`",
        f"- execution_parity_pass: `{bool(row.get('execution_parity_pass', False))}`",
        "",
        "## Summary",
        "",
        _table(stage12_summary_df),
        "",
        "## Checks",
        "",
        _table(stage12_checks_df),
        "",
        "## Mismatches",
        "",
        _table(stage12_mismatches_df),
        "",
        "## Linked Reports",
        "",
        f"- execution parity detail: `{execution_report_out}`",
    ]
    stage12_report_out.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def run(
    *,
    symbol: str,
    tick_root: Path,
    runtime_db: Path,
    events_json: Path,
    repo_predictions_parquet: Path,
    repo_stoplimit_detail_csv: Path,
    reduced_core_state_schedule_csv: Path,
    start_ts: str,
    end_ts: str,
    warmup_ticks: int,
    lookback_days: int,
    warmup_source: str,
    phase_bar_ticks: int,
    model_month: str,
    models_dir: Path,
    history_dir: Path,
    missing_month_policy: str,
    ftmo_enabled_override: bool,
    requested_lot_size: float,
    enable_tick_batch: bool,
    tick_batch_size: int,
    selected_time_tolerance_sec: float,
    enable_sequence_fallback: bool,
    sequence_fallback_max_gap_sec: float,
    reset_runtime_db: bool,
    record_raw_ticks: bool,
    time_tolerance_sec: float,
    price_tolerance_pips: float,
    out_summary_csv: Path,
    out_checks_csv: Path,
    out_mismatches_csv: Path,
    report_out: Path,
    local_summary_csv: Path,
    local_selected_mismatches_csv: Path,
    stage12_summary_csv: Path,
    stage12_checks_csv: Path,
    stage12_mismatches_csv: Path,
    stage12_report_out: Path,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    sym = str(symbol).upper().strip()
    if not sym:
        raise ValueError("symbol is required")

    start = _parse_ts("start_ts", start_ts)
    end = _parse_ts("end_ts", end_ts)
    if not (start < end):
        raise ValueError("start_ts must be earlier than end_ts")

    warmup, stream = _load_hist_ticks_for_replay(
        symbol=sym,
        tick_root=tick_root,
        start=start,
        end=end,
        warmup_ticks=int(warmup_ticks),
        lookback_days=int(lookback_days),
        warmup_source=warmup_source,
        phase_bar_ticks=int(phase_bar_ticks),
    )
    if stream.empty:
        raise ValueError(f"no HistData ticks found for {sym} in [{start}, {end})")

    expected_detail = _load_expected_detail_rows(
        detail_csv=repo_stoplimit_detail_csv,
        symbol=sym,
        start=start,
        end=end,
    )
    expected_selected = _load_expected_selected_rows(
        predictions_parquet=repo_predictions_parquet,
        symbol=sym,
        start=start,
        end=end,
    )
    reduced_schedule = _load_reduced_core_schedule(
        schedule_csv=reduced_core_state_schedule_csv,
        symbol=sym,
        start=start,
        end=end,
    )
    expected_detail = _filter_expected_to_reduced_core(
        expected=expected_detail,
        schedule=reduced_schedule,
    )
    expected_selected = _filter_expected_to_reduced_core(
        expected=expected_selected.assign(
            side="",
            entry_price=float("nan"),
            entry_ts=expected_selected["close_ts"],
            exit_ts=pd.NaT,
        ),
        schedule=reduced_schedule,
    )[["candidate_uid", "close_ts"]]

    stats, runtime_keys, missing_expected, extra_runtime = _simulate(
        symbol=sym,
        runtime_db=runtime_db,
        expected_selected_keys=expected_selected,
        expected_detail=expected_detail,
        warmup=warmup,
        stream=stream,
        events_json=events_json,
        model_month=model_month,
        models_dir=models_dir,
        history_dir=history_dir,
        missing_month_policy=missing_month_policy,
        ftmo_enabled_override=ftmo_enabled_override,
        requested_lot_size=float(requested_lot_size),
        enable_tick_batch=bool(enable_tick_batch),
        tick_batch_size=int(tick_batch_size),
        selected_time_tolerance_sec=float(selected_time_tolerance_sec),
        enable_sequence_fallback=bool(enable_sequence_fallback),
        sequence_fallback_max_gap_sec=float(sequence_fallback_max_gap_sec),
        reset_runtime_db=bool(reset_runtime_db),
        record_raw_ticks=bool(record_raw_ticks),
    )

    exec_parity = _load_exec_parity_module()

    summary_df, checks_df, mismatches_df = exec_parity.run(
        symbol=sym,
        runtime_db=runtime_db,
        ctrader_events_json=events_json,
        repo_stoplimit_detail_csv=repo_stoplimit_detail_csv,
        reduced_core_state_schedule_csv=reduced_core_state_schedule_csv,
        require_reduced_core_filter=True,
        tick_root=tick_root,
        start_ts=start.isoformat(),
        end_ts=end.isoformat(),
        time_tolerance_sec=float(time_tolerance_sec),
        price_tolerance_pips=float(price_tolerance_pips),
        out_summary_csv=out_summary_csv,
        out_checks_csv=out_checks_csv,
        out_mismatches_csv=out_mismatches_csv,
        report_out=report_out,
    )

    local_summary_csv.parent.mkdir(parents=True, exist_ok=True)
    local_selected_mismatches_csv.parent.mkdir(parents=True, exist_ok=True)
    stage12_summary_csv.parent.mkdir(parents=True, exist_ok=True)
    stage12_checks_csv.parent.mkdir(parents=True, exist_ok=True)
    stage12_mismatches_csv.parent.mkdir(parents=True, exist_ok=True)

    selected_mismatches = []
    for _, row in missing_expected.iterrows():
        selected_mismatches.append(
            {
                "type": "missing_expected_selected_key",
                "candidate_uid": str(row.get("candidate_uid", "")),
                "close_ts": row.get("close_ts"),
                "detail": "repo reduced-core expected key not found in runtime selected set",
            }
        )
    for _, row in extra_runtime.iterrows():
        selected_mismatches.append(
            {
                "type": "extra_runtime_selected_key",
                "candidate_uid": str(row.get("candidate_uid", "")),
                "close_ts": row.get("close_ts"),
                "detail": "runtime selected key absent from repo reduced-core expected set",
            }
        )
    selected_mismatches_df = pd.DataFrame(selected_mismatches)
    selected_mismatches_df.to_csv(local_selected_mismatches_csv, index=False)

    stage12_summary = _build_stage12_summary_df(
        symbol=sym,
        start=start,
        end=end,
        runtime_db=runtime_db,
        events_json=events_json,
        stats=stats,
        execution_summary_df=summary_df,
        execution_checks_df=checks_df,
        warmup_source=warmup_source,
        warmup_ticks=int(warmup_ticks),
        warmup_sent=int(len(warmup)),
    )
    stage12_checks = _build_stage12_checks_df(
        symbol=sym,
        stats=stats,
        execution_checks_df=checks_df,
    )
    exec_mismatches = mismatches_df.copy()
    if not exec_mismatches.empty:
        exec_mismatches["mismatch_family"] = "execution"
    signal_mismatches = selected_mismatches_df.copy()
    if not signal_mismatches.empty:
        signal_mismatches["mismatch_family"] = "signal"
    if signal_mismatches.empty:
        stage12_mismatches = exec_mismatches
    elif exec_mismatches.empty:
        stage12_mismatches = signal_mismatches
    else:
        stage12_mismatches = pd.concat(
            [signal_mismatches, exec_mismatches],
            ignore_index=True,
            sort=False,
        )

    stage12_summary.to_csv(stage12_summary_csv, index=False)
    stage12_checks.to_csv(stage12_checks_csv, index=False)
    stage12_mismatches.to_csv(stage12_mismatches_csv, index=False)
    _write_stage12_report(
        stage12_summary_df=stage12_summary,
        stage12_checks_df=stage12_checks,
        stage12_mismatches_df=stage12_mismatches,
        stage12_report_out=stage12_report_out,
        execution_report_out=report_out,
    )

    local_summary = stage12_summary.rename(
        columns={
            "signal_parity_pass": "selected_parity_pass",
            "execution_parity_pass": "overall_pass",
        }
    ).copy()
    local_summary.to_csv(local_summary_csv, index=False)

    return local_summary, summary_df, checks_df, mismatches_df


def _str_to_bool(raw: str | bool) -> bool:
    if isinstance(raw, bool):
        return raw
    txt = str(raw).strip().lower()
    return txt in {"1", "true", "yes", "y", "on"}


def main() -> None:
    p = argparse.ArgumentParser(
        description="Replay HistData through TestClient + run reduced-core parity gate"
    )
    p.add_argument("--symbol", required=True)
    p.add_argument("--tick-root", default="/Users/danielfisher/Desktop/tick")
    p.add_argument("--runtime-db", required=True)
    p.add_argument("--events-json", required=True)
    p.add_argument("--repo-predictions-parquet", required=True)
    p.add_argument("--repo-stoplimit-detail-csv", required=True)
    p.add_argument("--reduced-core-state-schedule-csv", required=True)
    p.add_argument("--start-ts", required=True)
    p.add_argument("--end-ts", required=True)
    p.add_argument("--warmup-ticks", type=int, default=30000)
    p.add_argument("--lookback-days", type=int, default=31)
    p.add_argument("--warmup-source", default="history_tail")
    p.add_argument("--phase-bar-ticks", type=int, default=100)
    p.add_argument("--model-month", default="")
    p.add_argument("--models-dir", default="models/oco")
    p.add_argument("--history-dir", default="configs/research/governance/oco_history")
    p.add_argument("--missing-month-policy", default="error")
    p.add_argument("--ftmo-enabled-override", default="false")
    p.add_argument("--requested-lot-size", type=float, default=0.05)
    p.add_argument("--enable-tick-batch", default="true")
    p.add_argument("--tick-batch-size", type=int, default=20)
    p.add_argument("--selected-time-tolerance-sec", type=float, default=1.0)
    p.add_argument("--enable-sequence-fallback", default="false")
    p.add_argument("--sequence-fallback-max-gap-sec", type=float, default=21600.0)
    p.add_argument("--reset-runtime-db", default="true")
    p.add_argument("--record-raw-ticks", default="true")
    p.add_argument("--time-tolerance-sec", type=float, default=1.0)
    p.add_argument("--price-tolerance-pips", type=float, default=0.1)
    p.add_argument(
        "--out-summary-csv",
        default="data/analysis/backtest_reconcile/histdata_testclient_execution_parity_summary.csv",
    )
    p.add_argument(
        "--out-checks-csv",
        default="data/analysis/backtest_reconcile/histdata_testclient_execution_parity_checks.csv",
    )
    p.add_argument(
        "--out-mismatches-csv",
        default="data/analysis/backtest_reconcile/histdata_testclient_execution_parity_mismatches.csv",
    )
    p.add_argument(
        "--report-out",
        default="docs/analysis/histdata_testclient_execution_parity_report.md",
    )
    p.add_argument(
        "--local-summary-csv",
        default="data/analysis/backtest_reconcile/histdata_testclient_replay_summary.csv",
    )
    p.add_argument(
        "--local-selected-mismatches-csv",
        default="data/analysis/backtest_reconcile/histdata_testclient_selected_mismatches.csv",
    )
    p.add_argument(
        "--stage12-summary-csv",
        default="data/analysis/backtest_reconcile/histdata_testclient_stage12_api_parity_summary.csv",
    )
    p.add_argument(
        "--stage12-checks-csv",
        default="data/analysis/backtest_reconcile/histdata_testclient_stage12_api_parity_checks.csv",
    )
    p.add_argument(
        "--stage12-mismatches-csv",
        default="data/analysis/backtest_reconcile/histdata_testclient_stage12_api_parity_mismatches.csv",
    )
    p.add_argument(
        "--stage12-report-out",
        default="docs/analysis/histdata_testclient_stage12_api_parity_report.md",
    )
    p.add_argument("--fail-on-gate", default="true")
    p.add_argument("--require-selected-parity", default="true")

    args = p.parse_args()

    local_summary, _, _, _ = run(
        symbol=str(args.symbol),
        tick_root=Path(str(args.tick_root)),
        runtime_db=Path(str(args.runtime_db)),
        events_json=Path(str(args.events_json)),
        repo_predictions_parquet=Path(str(args.repo_predictions_parquet)),
        repo_stoplimit_detail_csv=Path(str(args.repo_stoplimit_detail_csv)),
        reduced_core_state_schedule_csv=Path(str(args.reduced_core_state_schedule_csv)),
        start_ts=str(args.start_ts),
        end_ts=str(args.end_ts),
        warmup_ticks=int(args.warmup_ticks),
        lookback_days=int(args.lookback_days),
        warmup_source=str(args.warmup_source).strip().lower(),
        phase_bar_ticks=int(args.phase_bar_ticks),
        model_month=str(args.model_month).strip(),
        models_dir=Path(str(args.models_dir)),
        history_dir=Path(str(args.history_dir)),
        missing_month_policy=str(args.missing_month_policy).strip().lower(),
        ftmo_enabled_override=_str_to_bool(args.ftmo_enabled_override),
        requested_lot_size=float(args.requested_lot_size),
        enable_tick_batch=_str_to_bool(args.enable_tick_batch),
        tick_batch_size=int(args.tick_batch_size),
        selected_time_tolerance_sec=float(args.selected_time_tolerance_sec),
        enable_sequence_fallback=_str_to_bool(args.enable_sequence_fallback),
        sequence_fallback_max_gap_sec=float(args.sequence_fallback_max_gap_sec),
        reset_runtime_db=_str_to_bool(args.reset_runtime_db),
        record_raw_ticks=_str_to_bool(args.record_raw_ticks),
        time_tolerance_sec=float(args.time_tolerance_sec),
        price_tolerance_pips=float(args.price_tolerance_pips),
        out_summary_csv=Path(str(args.out_summary_csv)),
        out_checks_csv=Path(str(args.out_checks_csv)),
        out_mismatches_csv=Path(str(args.out_mismatches_csv)),
        report_out=Path(str(args.report_out)),
        local_summary_csv=Path(str(args.local_summary_csv)),
        local_selected_mismatches_csv=Path(str(args.local_selected_mismatches_csv)),
        stage12_summary_csv=Path(str(args.stage12_summary_csv)),
        stage12_checks_csv=Path(str(args.stage12_checks_csv)),
        stage12_mismatches_csv=Path(str(args.stage12_mismatches_csv)),
        stage12_report_out=Path(str(args.stage12_report_out)),
    )

    row = local_summary.iloc[0].to_dict() if not local_summary.empty else {}
    print(
        "replay_complete "
        f"symbol={row.get('symbol')} "
        f"ticks_streamed={row.get('ticks_streamed')} "
        f"selected_runtime={row.get('selected_rows_runtime')} "
        f"expected_reduced={row.get('expected_rows_reduced')} "
        f"missing={row.get('selected_missing_expected')} "
        f"extra={row.get('selected_extra_runtime')} "
        f"selected_parity_pass={row.get('selected_parity_pass')} "
        f"execution_verdict={row.get('execution_parity_verdict')} "
        f"stage12_api_parity_pass={row.get('stage12_api_parity_pass')}"
    )

    if _str_to_bool(args.fail_on_gate):
        execution_ok = bool(row.get("overall_pass"))
        selected_ok = bool(row.get("selected_parity_pass"))
        require_selected = _str_to_bool(args.require_selected_parity)
        gate_ok = execution_ok and (selected_ok if require_selected else True)
        if not gate_ok:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
