from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

ACTIVE_SYMBOLS = ("EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD")

SKIP_COLUMNS = ["symbol", "reason"]


@dataclass(frozen=True)
class DeviationConfig:
    runtime_db: Path
    tick_root: Path
    symbols: tuple[str, ...] = ACTIVE_SYMBOLS
    lookback_days: int = 7
    min_bars: int = 1
    run_id: str | None = None
    out_dir: Path | None = None
    start_ts: pd.Timestamp | datetime | str | None = None
    end_ts: pd.Timestamp | datetime | str | None = None
    governance_dir: Path | None = None
    models_dir: Path | None = None
    api: str | None = None
    copy_report_to_docs: bool = False


@dataclass(frozen=True)
class SymbolWindow:
    symbol: str
    start_ts: pd.Timestamp
    end_ts: pd.Timestamp
    raw_tick_count: int
    bar_count: int
    bar_ticks: int


def utc_now() -> pd.Timestamp:
    return pd.Timestamp(datetime.now(timezone.utc))


def _to_timestamp(value: pd.Timestamp | datetime | str | None) -> pd.Timestamp | None:
    if value is None:
        return None
    return pd.to_datetime(value, utc=True)


def _table_exists(con: duckdb.DuckDBPyConnection, table_name: str) -> bool:
    result = con.execute(
        """
        SELECT COUNT(*) AS table_count
        FROM information_schema.tables
        WHERE table_name = ?
        """,
        [table_name],
    ).fetchone()
    return bool(result and int(result[0]) > 0)


def _skip_frame(rows: list[dict[str, object]]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=SKIP_COLUMNS)


def _query_bar_summary(
    con: duckdb.DuckDBPyConnection,
    *,
    symbol: str,
    start_ts: pd.Timestamp,
    end_ts: pd.Timestamp,
) -> dict[str, Any] | None:
    row = con.execute(
        """
        SELECT
            MIN(ts) AS start_ts,
            MAX(close_ts) AS end_ts,
            COUNT(*) AS bar_count,
            COUNT(DISTINCT bar_ticks) AS bar_ticks_values,
            MIN(bar_ticks) AS bar_ticks
        FROM tick_bars
        WHERE upper(symbol) = ?
          AND close_ts BETWEEN ? AND ?
        """,
        [symbol.upper(), start_ts.to_pydatetime(), end_ts.to_pydatetime()],
    ).fetchone()
    if row is None:
        return None
    return {
        "start_ts": row[0],
        "end_ts": row[1],
        "bar_count": int(row[2] or 0),
        "bar_ticks_values": int(row[3] or 0),
        "bar_ticks": row[4],
    }


def _latest_close_ts(
    con: duckdb.DuckDBPyConnection, *, symbol: str
) -> pd.Timestamp | None:
    row = con.execute(
        """
        SELECT MAX(close_ts) AS latest_close_ts
        FROM tick_bars
        WHERE upper(symbol) = ?
        """,
        [symbol.upper()],
    ).fetchone()
    if row is None or row[0] is None:
        return None
    return _to_timestamp(row[0])


def _raw_tick_count(
    con: duckdb.DuckDBPyConnection,
    *,
    symbol: str,
    start_ts: pd.Timestamp,
    end_ts: pd.Timestamp,
    run_id: str | None,
) -> int:
    sql = """
        SELECT COUNT(*) AS raw_tick_count
        FROM raw_ticks
        WHERE upper(symbol) = ?
          AND tick_ts BETWEEN ? AND ?
    """
    params: list[object] = [
        symbol.upper(),
        start_ts.to_pydatetime(),
        end_ts.to_pydatetime(),
    ]
    if run_id is not None:
        sql += " AND run_id = ?"
        params.append(run_id)
    row = con.execute(sql, params).fetchone()
    return int(row[0] or 0) if row is not None else 0


def discover_symbol_windows(
    con: duckdb.DuckDBPyConnection, cfg: DeviationConfig
) -> tuple[list[SymbolWindow], pd.DataFrame]:
    missing_tables = [
        table_name
        for table_name in ("raw_ticks", "tick_bars")
        if not _table_exists(con, table_name)
    ]
    if missing_tables:
        reason = "missing_runtime_table"
        return [], _skip_frame(
            [{"symbol": symbol.upper(), "reason": reason} for symbol in cfg.symbols]
        )

    explicit_start = _to_timestamp(cfg.start_ts)
    explicit_end = _to_timestamp(cfg.end_ts)
    windows: list[SymbolWindow] = []
    skip_rows: list[dict[str, object]] = []

    for raw_symbol in cfg.symbols:
        symbol = raw_symbol.upper()
        if explicit_start is not None and explicit_end is not None:
            window_start = explicit_start
            window_end = explicit_end
        else:
            latest_close_ts = _latest_close_ts(con, symbol=symbol)
            if latest_close_ts is None:
                skip_rows.append(
                    {"symbol": symbol, "reason": "missing_recent_tick_bars"}
                )
                continue
            window_end = latest_close_ts
            window_start = window_end - pd.Timedelta(days=int(cfg.lookback_days))

        bar_summary = _query_bar_summary(
            con, symbol=symbol, start_ts=window_start, end_ts=window_end
        )
        if bar_summary is None or bar_summary["bar_count"] < int(cfg.min_bars):
            skip_rows.append({"symbol": symbol, "reason": "missing_recent_tick_bars"})
            continue
        if bar_summary["bar_ticks_values"] != 1 or bar_summary["bar_ticks"] is None:
            skip_rows.append({"symbol": symbol, "reason": "mixed_bar_ticks"})
            continue

        start_ts = _to_timestamp(bar_summary["start_ts"])
        end_ts = _to_timestamp(bar_summary["end_ts"])
        if start_ts is None or end_ts is None:
            skip_rows.append({"symbol": symbol, "reason": "missing_recent_tick_bars"})
            continue

        raw_tick_count = _raw_tick_count(
            con,
            symbol=symbol,
            start_ts=start_ts,
            end_ts=end_ts,
            run_id=cfg.run_id,
        )
        if raw_tick_count <= 0:
            skip_rows.append({"symbol": symbol, "reason": "missing_raw_tick_data"})
            continue

        windows.append(
            SymbolWindow(
                symbol=symbol,
                start_ts=start_ts,
                end_ts=end_ts,
                raw_tick_count=raw_tick_count,
                bar_count=bar_summary["bar_count"],
                bar_ticks=int(bar_summary["bar_ticks"]),
            )
        )

    return windows, _skip_frame(skip_rows)
