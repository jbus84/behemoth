#!/usr/bin/env python3
"""Shared loader for canonical monthly parquet tick feeds."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

DEFAULT_HISTDATA_ROOT = Path("/Users/danielfisher/Desktop/tick")
DEFAULT_DUKASCOPY_ROOT = Path("/Users/danielfisher/Desktop/dukascopy_ticks")
DEFAULT_CANONICAL_SOURCE = "dukascopy"
DEFAULT_CANONICAL_ROOT = DEFAULT_DUKASCOPY_ROOT


def normalize_source(source: str) -> str:
    txt = str(source or "").strip().lower()
    if txt in {"", "histdata"}:
        return "histdata"
    if txt == "dukascopy":
        return "dukascopy"
    raise ValueError(f"unsupported source: {source!r}")


def source_kind(source: str) -> str:
    normalized = normalize_source(source)
    if normalized == "dukascopy":
        return "dukascopy_parquet"
    return "histdata_parquet"


def default_root_for_source(source: str) -> Path:
    normalized = normalize_source(source)
    if normalized == "dukascopy":
        return DEFAULT_DUKASCOPY_ROOT
    return DEFAULT_HISTDATA_ROOT


def month_tags_between(start: pd.Timestamp, end: pd.Timestamp) -> list[str]:
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


def quote_sql_path(path: Path) -> str:
    return "'" + str(path).replace("'", "''") + "'"


def to_utc(series: pd.Series) -> pd.Series:
    try:
        return pd.to_datetime(series, utc=True, errors="coerce", format="mixed")
    except TypeError:
        return pd.to_datetime(series, utc=True, errors="coerce")


def all_symbol_tick_files(symbol: str, root: Path) -> list[Path]:
    sym = str(symbol).upper().strip()
    return sorted(p for p in (root / sym).glob(f"{sym}_*_ticks.parquet") if p.is_file())


def month_scoped_tick_files(
    symbol: str, root: Path, start: pd.Timestamp, end: pd.Timestamp
) -> list[Path]:
    sym = str(symbol).upper().strip()
    return [
        root / sym / f"{sym}_{m}_ticks.parquet"
        for m in month_tags_between(start, end)
        if (root / sym / f"{sym}_{m}_ticks.parquet").exists()
    ]


def load_ticks_window(
    *,
    symbol: str,
    root: Path,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.DataFrame:
    files = month_scoped_tick_files(symbol, root, start, end)
    if not files:
        return pd.DataFrame(columns=["timestamp", "bid", "ask"])

    files_sql = "[" + ",".join(quote_sql_path(p) for p in files) + "]"
    con = duckdb.connect()
    try:
        ts_expr = "try_cast(timestamp AS TIMESTAMP WITH TIME ZONE)"
        sql = (
            f"SELECT {ts_expr} AS timestamp, try_cast(bid AS DOUBLE) AS bid, "
            f"try_cast(ask AS DOUBLE) AS ask FROM read_parquet({files_sql}) "
            f"WHERE {ts_expr} >= ? AND {ts_expr} < ? ORDER BY {ts_expr}"
        )
        out = con.execute(sql, [start.to_pydatetime(), end.to_pydatetime()]).fetchdf()
    finally:
        con.close()
    if out.empty:
        return pd.DataFrame(columns=["timestamp", "bid", "ask"])
    out["timestamp"] = to_utc(out.get("timestamp", pd.Series(dtype=object)))
    out["bid"] = pd.to_numeric(out.get("bid", pd.Series(dtype=float)), errors="coerce")
    out["ask"] = pd.to_numeric(out.get("ask", pd.Series(dtype=float)), errors="coerce")
    out = out.dropna(subset=["timestamp", "bid", "ask"]).reset_index(drop=True)
    return out[["timestamp", "bid", "ask"]]


def load_ticks_by_count(
    *,
    symbol: str,
    root: Path,
    anchor: pd.Timestamp,
    ticks_before: int,
    ticks_after: int,
) -> pd.DataFrame:
    files = all_symbol_tick_files(symbol, root)
    if not files:
        return pd.DataFrame(columns=["timestamp", "bid", "ask"])

    files_sql = "[" + ",".join(quote_sql_path(p) for p in files) + "]"
    con = duckdb.connect()
    try:
        ts_expr = "try_cast(timestamp AS TIMESTAMP WITH TIME ZONE)"
        before = (
            con.execute(
                f"""
                SELECT timestamp, bid, ask
                FROM (
                    SELECT
                        {ts_expr} AS timestamp,
                        try_cast(bid AS DOUBLE) AS bid,
                        try_cast(ask AS DOUBLE) AS ask
                    FROM read_parquet({files_sql})
                    WHERE {ts_expr} < ?
                    ORDER BY {ts_expr} DESC
                    LIMIT {max(0, int(ticks_before))}
                ) q
                ORDER BY timestamp
                """,
                [anchor.to_pydatetime()],
            ).fetchdf()
            if int(ticks_before) > 0
            else pd.DataFrame(columns=["timestamp", "bid", "ask"])
        )
        after = (
            con.execute(
                f"""
                SELECT
                    {ts_expr} AS timestamp,
                    try_cast(bid AS DOUBLE) AS bid,
                    try_cast(ask AS DOUBLE) AS ask
                FROM read_parquet({files_sql})
                WHERE {ts_expr} >= ?
                ORDER BY {ts_expr}
                LIMIT {max(0, int(ticks_after))}
                """,
                [anchor.to_pydatetime()],
            ).fetchdf()
            if int(ticks_after) > 0
            else pd.DataFrame(columns=["timestamp", "bid", "ask"])
        )
    finally:
        con.close()

    out = pd.concat([before, after], ignore_index=True)
    if out.empty:
        return pd.DataFrame(columns=["timestamp", "bid", "ask"])
    out["timestamp"] = to_utc(out.get("timestamp", pd.Series(dtype=object)))
    out["bid"] = pd.to_numeric(out.get("bid", pd.Series(dtype=float)), errors="coerce")
    out["ask"] = pd.to_numeric(out.get("ask", pd.Series(dtype=float)), errors="coerce")
    out = out.dropna(subset=["timestamp", "bid", "ask"]).reset_index(drop=True)
    return out[["timestamp", "bid", "ask"]]
