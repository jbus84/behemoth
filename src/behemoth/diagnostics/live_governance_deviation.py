from __future__ import annotations

import json
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
WINDOW_SUMMARY_COLUMNS = [
    "symbol",
    "start_ts",
    "end_ts",
    "raw_tick_count",
    "bar_count",
    "bar_ticks",
]
TICK_COVERAGE_COLUMNS = [
    "symbol",
    "live_rows",
    "governance_rows",
    "live_first_ts",
    "live_last_ts",
    "governance_first_ts",
    "governance_last_ts",
    "live_duplicate_ts_ratio",
    "governance_duplicate_ts_ratio",
    "live_spread_p50",
    "live_spread_p95",
    "governance_spread_p50",
    "governance_spread_p95",
    "row_delta",
]
BAR_DEVIATION_COLUMNS = [
    "symbol",
    "live_bar_count",
    "governance_bar_count",
    "matched_bars",
    "missing_live_bars",
    "extra_live_bars",
    "live_duplicate_close_ts",
    "governance_duplicate_close_ts",
    "max_abs_close_delta_pips",
    "max_abs_spread_delta_pips",
]
SIGNAL_DEVIATION_COLUMNS = [
    "symbol",
    "live_source",
    "live_prediction_rows",
    "governance_prediction_rows",
    "prediction_row_delta",
    "live_selected_signal_count",
    "governance_selected_signal_count",
    "selected_signal_delta",
    "live_pred_prob_p50",
    "governance_pred_prob_p50",
    "live_threshold_p50",
    "governance_threshold_p50",
]
OUTCOME_DEVIATION_COLUMNS = [
    "symbol",
    "Governance Selected Signal Count",
    "Runtime Trade Count",
    "Runtime closed trade count",
    "Runtime Closed Trade Count",
    "Runtime Realized P&L",
    "governance_selected_signal_count",
    "runtime_trade_count",
    "runtime_closed_trade_count",
    "runtime_realized_pnl_pips",
]
FINDINGS_COLUMNS = ["symbol", "classification", "code", "severity", "summary"]
GOVERNANCE_TICK_BAR_COLUMNS = [
    "close_ts",
    "open_bid",
    "high_bid",
    "low_bid",
    "close_bid",
    "spread",
    "tick_volume",
    "hl_first",
    "hl_pos_frac",
    "high_ask",
    "close_ask",
]


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


def _empty_governance_bars() -> pd.DataFrame:
    return pd.DataFrame(columns=GOVERNANCE_TICK_BAR_COLUMNS)


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
        return _empty_governance_bars()

    from scripts.diagnose_live_replay import _build_bars_from_ticks

    ticks = canonical_ticks.copy()
    ticks["timestamp"] = _parse_timestamp_series(ticks["timestamp"])
    ticks = ticks[ticks["timestamp"].notna()]
    if ticks.empty:
        return _empty_governance_bars()

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


def _run_dir(out_dir: Path) -> Path:
    base = Path(out_dir) / utc_now().strftime("%Y%m%dT%H%M%S%fZ")
    if not base.exists():
        return base
    suffix = 1
    while True:
        candidate = base.with_name(f"{base.name}-{suffix}")
        if not candidate.exists():
            return candidate
        suffix += 1


def _window_summary_frame(windows: list[SymbolWindow]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "symbol": window.symbol,
                "start_ts": window.start_ts.isoformat(),
                "end_ts": window.end_ts.isoformat(),
                "raw_tick_count": window.raw_tick_count,
                "bar_count": window.bar_count,
                "bar_ticks": window.bar_ticks,
            }
            for window in windows
        ],
        columns=WINDOW_SUMMARY_COLUMNS,
    )


def _write_df(path: Path, df: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


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


TRUTHY_SELECTED_VALUES = {"true", "t", "yes", "y", "1"}


def _is_selected_value(value: object) -> bool:
    if pd.isna(value):
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in TRUTHY_SELECTED_VALUES
    numeric_value = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(numeric_value):
        return False
    return bool(numeric_value != 0)


def _selected_count(df: pd.DataFrame) -> int:
    if df.empty:
        return 0
    if "selected_exec" in df.columns:
        return int(df["selected_exec"].map(_is_selected_value).sum())
    if "selected" in df.columns:
        return int(df["selected"].map(_is_selected_value).sum())
    return int(len(df))


def _column_p50(df: pd.DataFrame, column: str) -> float:
    if column not in df.columns:
        return float("nan")
    return _series_quantile(df[column], 0.50)


def compute_signal_deviation(
    symbol: str,
    live_predictions: pd.DataFrame,
    governance_predictions: pd.DataFrame,
    *,
    live_source: str,
) -> pd.DataFrame:
    live_prediction_rows = int(len(live_predictions))
    governance_prediction_rows = int(len(governance_predictions))
    live_selected_signal_count = _selected_count(live_predictions)
    governance_selected_signal_count = _selected_count(governance_predictions)

    return pd.DataFrame(
        [
            {
                "symbol": symbol.upper(),
                "live_source": live_source,
                "live_prediction_rows": live_prediction_rows,
                "governance_prediction_rows": governance_prediction_rows,
                "prediction_row_delta": live_prediction_rows
                - governance_prediction_rows,
                "live_selected_signal_count": live_selected_signal_count,
                "governance_selected_signal_count": governance_selected_signal_count,
                "selected_signal_delta": live_selected_signal_count
                - governance_selected_signal_count,
                "live_pred_prob_p50": _column_p50(live_predictions, "pred_prob"),
                "governance_pred_prob_p50": _column_p50(
                    governance_predictions, "pred_prob"
                ),
                "live_threshold_p50": _column_p50(live_predictions, "threshold"),
                "governance_threshold_p50": _column_p50(
                    governance_predictions, "threshold"
                ),
            }
        ]
    )


def compute_outcome_deviation(
    symbol: str, trades: pd.DataFrame, *, governance_selected_signal_count: int
) -> pd.DataFrame:
    runtime_trade_count = int(len(trades))
    status_missing = runtime_trade_count > 0 and "status" not in trades.columns
    pnl_missing = runtime_trade_count > 0 and "pnl_pips" not in trades.columns
    if trades.empty:
        closed_trades = trades.iloc[0:0]
        runtime_closed_trade_count: float = 0.0
        runtime_realized_pnl_pips = 0.0
    elif status_missing:
        closed_trades = trades.iloc[0:0]
        runtime_closed_trade_count = float("nan")
        runtime_realized_pnl_pips = float("nan")
    else:
        closed_trades = trades[
            trades["status"].astype("string").str.upper().fillna("") == "CLOSED"
        ]
        runtime_closed_trade_count = float(len(closed_trades))
        if pnl_missing:
            runtime_realized_pnl_pips = float("nan")
        else:
            runtime_realized_pnl_pips = float(
                pd.to_numeric(closed_trades["pnl_pips"], errors="coerce")
                .fillna(0)
                .sum()
            )

    return pd.DataFrame(
        [
            {
                "symbol": symbol.upper(),
                "Governance Selected Signal Count": int(
                    governance_selected_signal_count
                ),
                "Runtime Trade Count": runtime_trade_count,
                "Runtime closed trade count": runtime_closed_trade_count,
                "Runtime Closed Trade Count": runtime_closed_trade_count,
                "Runtime Realized P&L": runtime_realized_pnl_pips,
                "governance_selected_signal_count": int(
                    governance_selected_signal_count
                ),
                "runtime_trade_count": runtime_trade_count,
                "runtime_closed_trade_count": runtime_closed_trade_count,
                "runtime_realized_pnl_pips": runtime_realized_pnl_pips,
            }
        ]
    )


def _numeric_row_value(row: pd.Series, column: str, default: float = 0.0) -> float:
    value = row.get(column, default)
    if pd.isna(value):
        return default
    return float(value)


def build_findings(
    bar_deviation: pd.DataFrame,
    signal_deviation: pd.DataFrame,
    incomplete_rows: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []

    for _, row in bar_deviation.iterrows():
        missing_live_bars = int(_numeric_row_value(row, "missing_live_bars"))
        extra_live_bars = int(_numeric_row_value(row, "extra_live_bars"))
        if missing_live_bars or extra_live_bars:
            rows.append(
                {
                    "symbol": str(row.get("symbol", "")).upper(),
                    "classification": "Material Drift",
                    "code": "BAR_COUNT_DEVIATION",
                    "severity": "high",
                    "summary": (
                        f"Missing live bars: {missing_live_bars}; "
                        f"extra live bars: {extra_live_bars}."
                    ),
                }
            )

    for _, row in signal_deviation.iterrows():
        selected_signal_delta = int(_numeric_row_value(row, "selected_signal_delta"))
        if selected_signal_delta:
            rows.append(
                {
                    "symbol": str(row.get("symbol", "")).upper(),
                    "classification": "Runtime Variance",
                    "code": "SELECTED_SIGNAL_DELTA",
                    "severity": "medium",
                    "summary": (
                        "Live selected signal count differs from governance by "
                        f"{selected_signal_delta}."
                    ),
                }
            )

    for _, row in incomplete_rows.iterrows():
        symbol = str(row.get("symbol", "")).upper()
        reason = str(row.get("reason", "incomplete_evidence"))
        rows.append(
            {
                "symbol": symbol,
                "classification": "Incomplete Evidence",
                "code": "incomplete_evidence",
                "severity": "medium",
                "summary": reason,
            }
        )

    if not rows:
        rows.append(
            {
                "symbol": "",
                "classification": "Info",
                "code": "NO_MATERIAL_FINDINGS",
                "severity": "info",
                "summary": "No material live governance deviation findings.",
            }
        )

    return pd.DataFrame(rows, columns=FINDINGS_COLUMNS)


def _markdown_table(df: pd.DataFrame) -> str:
    if df.empty:
        return "_empty_"
    try:
        return df.to_markdown(index=False)
    except Exception:
        return df.to_string(index=False)


def render_report(
    *,
    manifest: dict[str, object],
    window_summary: pd.DataFrame,
    findings: pd.DataFrame,
    tick_coverage: pd.DataFrame,
    bar_deviation: pd.DataFrame,
    signal_deviation: pd.DataFrame,
    outcome_deviation: pd.DataFrame,
    skips: pd.DataFrame,
) -> str:
    generated_at_utc = manifest.get("generated_at_utc", "")
    run_id = manifest.get("run_id", "")
    subreports = manifest.get("subreports")
    subreport_section: list[str] = []
    if isinstance(subreports, dict) and subreports:
        subreport_section = [
            "## Existing Diagnostic Subreports",
            "",
            *[
                f"- {name}: `{path}`"
                for name, path in sorted(subreports.items(), key=lambda item: item[0])
            ],
            "",
        ]
    sections = [
        "# Live Governance Deviation Report",
        "",
        f"- generated_at_utc: {generated_at_utc}",
        f"- run_id: {run_id}",
        "",
        (
            "This report is diagnostic evidence only and is not a Promotion gate; "
            "Promotion authority remains with the stage certification process."
        ),
        "",
        (
            "Runtime Realized P&L is not treated as equivalent to Independent "
            "Label P&L."
        ),
        "",
        *subreport_section,
        "## Findings",
        "",
        _markdown_table(findings),
        "",
        "## Window Summary",
        "",
        _markdown_table(window_summary),
        "",
        "## Tick Coverage Deviation",
        "",
        _markdown_table(tick_coverage),
        "",
        "## Bar Deviation",
        "",
        _markdown_table(bar_deviation),
        "",
        "## Signal Deviation",
        "",
        _markdown_table(signal_deviation),
        "",
        "## Outcome Context",
        "",
        _markdown_table(outcome_deviation),
        "",
        "## Skipped Symbols",
        "",
        _markdown_table(skips),
        "",
    ]
    return "\n".join(sections)


def _concat_frames(frames: list[pd.DataFrame], columns: list[str]) -> pd.DataFrame:
    non_empty = [frame for frame in frames if not frame.empty]
    if not non_empty:
        return pd.DataFrame(columns=columns)
    return pd.concat(non_empty, ignore_index=True).reindex(columns=columns)


def _write_parquet(path: Path, df: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)


def _json_default(value: object) -> object:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, datetime):
        return pd.Timestamp(value).isoformat()
    return str(value)


def _governance_selected_count(signal_deviation: pd.DataFrame) -> int:
    if signal_deviation.empty:
        return 0
    row = signal_deviation.iloc[0]
    if "governance_selected_signal_count" in signal_deviation.columns:
        value = row.get("governance_selected_signal_count", 0)
    else:
        value = row.get("Governance Selected Signal Count", 0)
    if pd.isna(value):
        return 0
    return int(value)


def run_analysis(cfg: DeviationConfig) -> dict[str, Path]:
    run_dir = _run_dir(cfg.out_dir)
    run_dir.mkdir(parents=True, exist_ok=False)

    tick_coverage_frames: list[pd.DataFrame] = []
    bar_deviation_frames: list[pd.DataFrame] = []
    signal_deviation_frames: list[pd.DataFrame] = []
    outcome_deviation_frames: list[pd.DataFrame] = []
    incomplete_rows: list[dict[str, object]] = []

    con = duckdb.connect(str(cfg.runtime_db), read_only=True)
    try:
        windows, skips = discover_symbol_windows(con, cfg)
        window_summary = _window_summary_frame(windows)

        for window in windows:
            evidence = extract_live_evidence(con, window, run_id=cfg.run_id)
            canonical_ticks = load_canonical_ticks_for_window(
                cfg.tick_root,
                window.symbol,
                window.start_ts,
                window.end_ts,
            )
            governance_bars = build_governance_bars_for_window(
                canonical_ticks, window.bar_ticks
            )

            symbol_prefix = window.symbol.upper()
            _write_parquet(
                run_dir / f"{symbol_prefix}_live_raw_ticks.parquet",
                evidence.raw_ticks,
            )
            _write_parquet(
                run_dir / f"{symbol_prefix}_live_tick_bars.parquet",
                evidence.tick_bars,
            )
            _write_parquet(
                run_dir / f"{symbol_prefix}_governance_raw_ticks.parquet",
                canonical_ticks,
            )
            _write_parquet(
                run_dir / f"{symbol_prefix}_governance_tick_bars.parquet",
                governance_bars,
            )

            if canonical_ticks.empty:
                incomplete_rows.append(
                    {
                        "symbol": window.symbol,
                        "reason": "missing_canonical_ticks",
                    }
                )

            tick_coverage_frames.append(
                compute_tick_coverage(
                    window.symbol, evidence.raw_ticks, canonical_ticks
                )
            )
            bar_deviation_frames.append(
                compute_bar_deviation(
                    window.symbol, evidence.tick_bars, governance_bars
                )
            )
            signal_deviation = compute_signal_deviation(
                window.symbol,
                evidence.predictions,
                pd.DataFrame(),
                live_source=evidence.prediction_source,
            )
            signal_deviation_frames.append(signal_deviation)
            outcome_deviation_frames.append(
                compute_outcome_deviation(
                    window.symbol,
                    evidence.trades,
                    governance_selected_signal_count=_governance_selected_count(
                        signal_deviation
                    ),
                )
            )
    finally:
        con.close()

    tick_coverage = _concat_frames(tick_coverage_frames, TICK_COVERAGE_COLUMNS)
    bar_deviation = _concat_frames(bar_deviation_frames, BAR_DEVIATION_COLUMNS)
    signal_deviation = _concat_frames(signal_deviation_frames, SIGNAL_DEVIATION_COLUMNS)
    outcome_deviation = _concat_frames(
        outcome_deviation_frames, OUTCOME_DEVIATION_COLUMNS
    )
    incomplete = pd.DataFrame(incomplete_rows, columns=SKIP_COLUMNS)
    findings = build_findings(bar_deviation, signal_deviation, incomplete)

    manifest = {
        "generated_at_utc": utc_now().isoformat(),
        "run_id": cfg.run_id,
        "runtime_db": cfg.runtime_db,
        "tick_root": cfg.tick_root,
        "symbols": list(cfg.symbols),
        "lookback_days": cfg.lookback_days,
        "min_bars": cfg.min_bars,
        "run_dir": run_dir,
        "window_count": len(window_summary),
        "skip_count": len(skips),
        "incomplete_evidence_count": len(incomplete),
    }
    manifest["subreports"] = {
        "runtime_summary": str(run_dir / "window_summary.csv"),
        "live_audit": str(run_dir / "live_audit_report.md"),
        "performance_gap": str(run_dir / "live_performance_gap_report.md"),
    }

    manifest_path = run_dir / "run_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, default=_json_default) + "\n",
        encoding="utf-8",
    )
    _write_df(run_dir / "window_summary.csv", window_summary)
    _write_df(run_dir / "symbol_skips.csv", skips)
    _write_df(run_dir / "tick_coverage_deviation.csv", tick_coverage)
    _write_df(run_dir / "bar_deviation.csv", bar_deviation)
    _write_df(run_dir / "signal_deviation.csv", signal_deviation)
    _write_df(run_dir / "outcome_deviation.csv", outcome_deviation)
    _write_df(run_dir / "findings.csv", findings)

    report = render_report(
        manifest=manifest,
        window_summary=window_summary,
        findings=findings,
        tick_coverage=tick_coverage,
        bar_deviation=bar_deviation,
        signal_deviation=signal_deviation,
        outcome_deviation=outcome_deviation,
        skips=skips,
    )
    report_path = run_dir / "live_governance_deviation_report.md"
    report_path.write_text(report, encoding="utf-8")

    if cfg.copy_report_to_docs:
        docs_report_path = Path("docs/analysis/live_governance_deviation_report.md")
        docs_report_path.parent.mkdir(parents=True, exist_ok=True)
        docs_report_path.write_text(report, encoding="utf-8")

    return {
        "run_dir": run_dir,
        "manifest_path": manifest_path,
        "report_path": report_path,
    }
