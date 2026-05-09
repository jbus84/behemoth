from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd
import polars as pl

ACTIVE_SYMBOLS = ("EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD")

SKIP_COLUMNS = ["symbol", "reason"]
CANONICAL_TICK_COLUMNS = ["timestamp", "bid", "ask", "mid", "spread", "log_return"]


@dataclass(frozen=True)
class DeviationConfig:
    runtime_db: Path
    tick_root: Path
    symbols: tuple[str, ...]
    lookback_days: int
    min_bars: int
    run_id: str
    out_dir: Path
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


@dataclass(frozen=True)
class LiveEvidence:
    raw_ticks: pd.DataFrame
    tick_bars: pd.DataFrame
    predictions: pd.DataFrame
    prediction_source: str
    trades: pd.DataFrame


def utc_now() -> pd.Timestamp:
    return pd.Timestamp(datetime.now(timezone.utc))


def _to_timestamp(value: pd.Timestamp | datetime | str | None) -> pd.Timestamp | None:
    if value is None:
        return None
    return pd.to_datetime(value, utc=True)


def _month_tokens(start_ts: pd.Timestamp, end_ts: pd.Timestamp) -> list[str]:
    start = pd.to_datetime(start_ts, utc=True)
    end = pd.to_datetime(end_ts, utc=True)
    if end < start:
        return []
    start_period = pd.Period(f"{start.year:04d}-{start.month:02d}", freq="M")
    end_period = pd.Period(f"{end.year:04d}-{end.month:02d}", freq="M")
    return [
        period.strftime("%Y%m")
        for period in pd.period_range(start_period, end_period, freq="M")
    ]


def _empty_canonical_ticks() -> pd.DataFrame:
    return pd.DataFrame(columns=CANONICAL_TICK_COLUMNS)


def _parse_timestamp_series(values: pd.Series) -> pd.Series:
    source_has_values = values.notna().any()
    try:
        parsed = pd.to_datetime(values, utc=True, errors="coerce", format="mixed")
        if not source_has_values or parsed.notna().any():
            return parsed
    except (TypeError, ValueError):
        pass
    try:
        return pd.to_datetime(values, utc=True, errors="coerce")
    except TypeError:
        return pd.to_datetime(values, utc=True)


def load_canonical_ticks_for_window(
    tick_root: Path,
    symbol: str,
    start_ts: pd.Timestamp,
    end_ts: pd.Timestamp,
) -> pd.DataFrame:
    symbol_upper = symbol.upper()
    window_start = pd.to_datetime(start_ts, utc=True)
    window_end = pd.to_datetime(end_ts, utc=True)
    tick_dir = Path(tick_root) / symbol_upper

    frames: list[pd.DataFrame] = []
    for month_token in _month_tokens(window_start, window_end):
        tick_path = tick_dir / f"{symbol_upper}_{month_token}_ticks.parquet"
        if tick_path.exists():
            frames.append(pd.read_parquet(tick_path))

    if not frames:
        return _empty_canonical_ticks()

    ticks = pd.concat(frames, ignore_index=True)
    existing_columns = [
        column for column in CANONICAL_TICK_COLUMNS if column in ticks.columns
    ]
    ticks = ticks[existing_columns].copy()
    if "timestamp" not in ticks.columns:
        return pd.DataFrame(columns=existing_columns)
    ticks["timestamp"] = _parse_timestamp_series(ticks["timestamp"])
    ticks = ticks[
        ticks["timestamp"].notna()
        & (ticks["timestamp"] >= window_start)
        & (ticks["timestamp"] <= window_end)
    ]
    return ticks.sort_values("timestamp", kind="mergesort").reset_index(drop=True)


def build_governance_bars_for_window(
    canonical_ticks: pd.DataFrame, bar_ticks: int
) -> pd.DataFrame:
    if canonical_ticks.empty or int(bar_ticks) != 100:
        return pd.DataFrame()

    from scripts.diagnose_live_replay import _build_bars_from_ticks

    ticks = canonical_ticks.copy()
    ticks["timestamp"] = _parse_timestamp_series(ticks["timestamp"])
    ticks = ticks[ticks["timestamp"].notna()]
    if ticks.empty:
        return pd.DataFrame()

    return _build_bars_from_ticks(pl.from_pandas(ticks)).to_pandas()


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


def _table_columns(con: duckdb.DuckDBPyConnection, table_name: str) -> set[str]:
    try:
        rows = con.execute(f"DESCRIBE {table_name}").fetchall()
    except Exception:
        return set()
    return {str(row[0]) for row in rows}


def _read_df(
    con: duckdb.DuckDBPyConnection, sql: str, params: list[Any]
) -> pd.DataFrame:
    try:
        return con.execute(sql, params).fetchdf()
    except Exception:
        return pd.DataFrame()


def _normalise_ts_column(df: pd.DataFrame, column: str) -> pd.DataFrame:
    if column in df.columns:
        df[column] = pd.to_datetime(df[column], utc=True, errors="coerce")
    return df


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


def extract_live_evidence(
    con: duckdb.DuckDBPyConnection, window: SymbolWindow, *, run_id: str
) -> LiveEvidence:
    symbol = window.symbol.upper()
    start_ts = window.start_ts.to_pydatetime()
    end_ts = window.end_ts.to_pydatetime()

    raw_ticks = _read_df(
        con,
        """
        SELECT tick_ts, ingest_ts, symbol, bid, ask, spread, tick_volume, source,
               client_tick_seq, run_id
        FROM raw_ticks
        WHERE upper(symbol) = ?
          AND lower(coalesce(run_id, '')) = lower(?)
          AND tick_ts BETWEEN ? AND ?
        ORDER BY tick_ts, client_tick_seq
        """,
        [symbol, run_id, start_ts, end_ts],
    )
    raw_ticks = _normalise_ts_column(raw_ticks, "tick_ts")
    raw_ticks = _normalise_ts_column(raw_ticks, "ingest_ts")

    tick_bars = _read_df(
        con,
        """
        SELECT row_id, ts, close_ts, symbol, bar_ticks, open_bid, high_bid, low_bid,
               close_bid, spread, tick_volume, hl_first, hl_pos_frac, high_ask, close_ask
        FROM tick_bars
        WHERE upper(symbol) = ?
          AND close_ts BETWEEN ? AND ?
        ORDER BY close_ts, row_id
        """,
        [symbol, start_ts, end_ts],
    )
    tick_bars = _normalise_ts_column(tick_bars, "ts")
    tick_bars = _normalise_ts_column(tick_bars, "close_ts")

    prediction_source = "none"
    predictions = pd.DataFrame()
    if _table_exists(con, "predict_evaluations"):
        predictions = _read_df(
            con,
            """
            SELECT *
            FROM predict_evaluations
            WHERE upper(symbol) = ?
              AND lower(coalesce(run_id, '')) = lower(?)
              AND close_ts BETWEEN ? AND ?
            ORDER BY close_ts, candidate_uid
            """,
            [symbol, run_id, start_ts, end_ts],
        )
        if not predictions.empty:
            prediction_source = "predict_evaluations"

    if predictions.empty and _table_exists(con, "audit_logs"):
        predictions = _read_df(
            con,
            """
            SELECT *
            FROM audit_logs
            WHERE upper(symbol) = ?
              AND lower(coalesce(run_id, '')) = lower(?)
              AND close_ts BETWEEN ? AND ?
            ORDER BY close_ts, candidate_uid
            """,
            [symbol, run_id, start_ts, end_ts],
        )
        if not predictions.empty:
            prediction_source = "audit_logs"
    predictions = _normalise_ts_column(predictions, "event_ts")
    predictions = _normalise_ts_column(predictions, "close_ts")

    trades = pd.DataFrame()
    if _table_exists(con, "trades"):
        trade_columns = _table_columns(con, "trades")
        entry_ts_filter = (
            "AND entry_ts BETWEEN ? AND ?" if "entry_ts" in trade_columns else ""
        )
        trade_params: list[object] = [symbol, run_id]
        if entry_ts_filter:
            trade_params.extend([start_ts, end_ts])
        trades = _read_df(
            con,
            f"""
            SELECT *
            FROM trades
            WHERE upper(symbol) = ?
              AND lower(coalesce(run_id, '')) = lower(?)
              {entry_ts_filter}
            """,
            trade_params,
        )
    trades = _normalise_ts_column(trades, "entry_ts")
    trades = _normalise_ts_column(trades, "exit_ts")

    return LiveEvidence(
        raw_ticks=raw_ticks,
        tick_bars=tick_bars,
        predictions=predictions,
        prediction_source=prediction_source,
        trades=trades,
    )


def _pip_size(symbol: str) -> float:
    return 0.01 if symbol.upper().endswith("JPY") else 0.0001


def _series_quantile(series: pd.Series, q: float) -> float:
    values = pd.to_numeric(series, errors="coerce").dropna()
    if values.empty:
        return float("nan")
    return float(values.quantile(q))


def _timestamp_bounds(df: pd.DataFrame, column: str) -> tuple[str, str]:
    if column not in df.columns:
        return "", ""
    timestamps = pd.to_datetime(df[column], utc=True, errors="coerce")
    if not timestamps.notna().any():
        return "", ""
    return timestamps.min().isoformat(), timestamps.max().isoformat()


def _duplicate_ratio(df: pd.DataFrame, column: str) -> float:
    if df.empty or column not in df.columns:
        return float("nan")
    timestamps = pd.to_datetime(df[column], utc=True, errors="coerce")
    if timestamps.empty:
        return float("nan")
    return float(timestamps.duplicated().mean())


def _spread_quantiles(df: pd.DataFrame) -> tuple[float, float]:
    if "spread" not in df.columns:
        return float("nan"), float("nan")
    spread = pd.to_numeric(df["spread"], errors="coerce")
    return _series_quantile(spread, 0.50), _series_quantile(spread, 0.95)


def _deduplicate_bars_for_close_ts(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    if "close_ts" not in df.columns:
        df = df.copy()
        df["close_ts"] = pd.Series(dtype="datetime64[ns, UTC]")
    sort_columns = ["close_ts"]
    if "row_id" in df.columns:
        sort_columns.append("row_id")
    sorted_df = df.sort_values(sort_columns, kind="mergesort")
    duplicate_count = int(sorted_df["close_ts"].duplicated(keep="last").sum())
    return (
        sorted_df.drop_duplicates(subset=["close_ts"], keep="last").reset_index(
            drop=True
        ),
        duplicate_count,
    )


def _max_abs_delta_pips(
    df: pd.DataFrame, live_column: str, governance_column: str, pip_size: float
) -> float:
    if live_column not in df.columns or governance_column not in df.columns:
        return float("nan")
    live_values = pd.to_numeric(df[live_column], errors="coerce")
    governance_values = pd.to_numeric(df[governance_column], errors="coerce")
    deltas = ((live_values - governance_values) / pip_size).abs().dropna()
    if deltas.empty:
        return float("nan")
    return float(deltas.max())


def compute_tick_coverage(
    symbol: str, live_ticks: pd.DataFrame, governance_ticks: pd.DataFrame
) -> pd.DataFrame:
    live_first_ts, live_last_ts = _timestamp_bounds(live_ticks, "tick_ts")
    governance_ts_col = "tick_ts" if "tick_ts" in governance_ticks.columns else "timestamp"
    governance_first_ts, governance_last_ts = _timestamp_bounds(
        governance_ticks, governance_ts_col
    )
    live_spread_p50, live_spread_p95 = _spread_quantiles(live_ticks)
    governance_spread_p50, governance_spread_p95 = _spread_quantiles(governance_ticks)

    live_rows = int(len(live_ticks))
    governance_rows = int(len(governance_ticks))
    return pd.DataFrame(
        [
            {
                "symbol": symbol.upper(),
                "live_rows": live_rows,
                "governance_rows": governance_rows,
                "live_first_ts": live_first_ts,
                "live_last_ts": live_last_ts,
                "governance_first_ts": governance_first_ts,
                "governance_last_ts": governance_last_ts,
                "live_duplicate_ts_ratio": _duplicate_ratio(live_ticks, "tick_ts"),
                "governance_duplicate_ts_ratio": _duplicate_ratio(
                    governance_ticks, governance_ts_col
                ),
                "live_spread_p50": live_spread_p50,
                "live_spread_p95": live_spread_p95,
                "governance_spread_p50": governance_spread_p50,
                "governance_spread_p95": governance_spread_p95,
                "row_delta": live_rows - governance_rows,
            }
        ]
    )


def compute_bar_deviation(
    symbol: str, live_bars: pd.DataFrame, governance_bars: pd.DataFrame
) -> pd.DataFrame:
    live = live_bars.copy()
    governance = governance_bars.copy()
    live = _normalise_ts_column(live, "close_ts")
    governance = _normalise_ts_column(governance, "close_ts")
    live_bar_count = int(len(live))
    governance_bar_count = int(len(governance))

    if "close_ts" not in live.columns:
        live["close_ts"] = pd.Series(dtype="datetime64[ns, UTC]")
    if "close_ts" not in governance.columns:
        governance["close_ts"] = pd.Series(dtype="datetime64[ns, UTC]")

    live, live_duplicate_close_ts = _deduplicate_bars_for_close_ts(live)
    governance, governance_duplicate_close_ts = _deduplicate_bars_for_close_ts(
        governance
    )

    merged = live.merge(
        governance,
        on="close_ts",
        how="outer",
        suffixes=("_live", "_governance"),
        indicator=True,
    )
    matched = merged[merged["_merge"] == "both"]
    if matched.empty:
        max_abs_close_delta_pips = float("nan")
        max_abs_spread_delta_pips = float("nan")
    else:
        pip_size = _pip_size(symbol)
        max_abs_close_delta_pips = _max_abs_delta_pips(
            matched, "close_bid_live", "close_bid_governance", pip_size
        )
        max_abs_spread_delta_pips = _max_abs_delta_pips(
            matched, "spread_live", "spread_governance", pip_size
        )

    return pd.DataFrame(
        [
            {
                "symbol": symbol.upper(),
                "live_bar_count": live_bar_count,
                "governance_bar_count": governance_bar_count,
                "matched_bars": int((merged["_merge"] == "both").sum()),
                "missing_live_bars": int((merged["_merge"] == "right_only").sum()),
                "extra_live_bars": int((merged["_merge"] == "left_only").sum()),
                "live_duplicate_close_ts": live_duplicate_close_ts,
                "governance_duplicate_close_ts": governance_duplicate_close_ts,
                "max_abs_close_delta_pips": max_abs_close_delta_pips,
                "max_abs_spread_delta_pips": max_abs_spread_delta_pips,
            }
        ]
    )
