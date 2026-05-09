from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd
import pytest

from src.behemoth.diagnostics.live_governance_deviation import (
    DeviationConfig,
    compute_bar_deviation,
    compute_tick_coverage,
    discover_symbol_windows,
    extract_live_evidence,
)


def _create_runtime_db(path: Path) -> None:
    con = duckdb.connect(str(path))
    try:
        con.execute(
            """
            CREATE TABLE raw_ticks (
                tick_ts TIMESTAMP WITH TIME ZONE,
                ingest_ts TIMESTAMP WITH TIME ZONE,
                symbol VARCHAR,
                bid DOUBLE,
                ask DOUBLE,
                spread DOUBLE,
                tick_volume DOUBLE,
                source VARCHAR,
                client_tick_seq BIGINT,
                run_id VARCHAR
            )
            """
        )
        con.execute(
            """
            CREATE TABLE tick_bars (
                row_id BIGINT,
                ts TIMESTAMP WITH TIME ZONE,
                close_ts TIMESTAMP WITH TIME ZONE,
                symbol VARCHAR,
                bar_ticks BIGINT,
                open_bid DOUBLE,
                high_bid DOUBLE,
                low_bid DOUBLE,
                close_bid DOUBLE,
                spread DOUBLE,
                tick_volume DOUBLE,
                hl_first BIGINT,
                hl_pos_frac DOUBLE,
                high_ask DOUBLE,
                close_ask DOUBLE
            )
            """
        )
        ticks = pd.DataFrame(
            {
                "tick_ts": pd.date_range("2026-05-02T00:00:00Z", periods=300, freq="s"),
                "ingest_ts": pd.date_range("2026-05-02T00:00:00Z", periods=300, freq="s"),
                "symbol": ["EURUSD"] * 300,
                "bid": [1.1] * 300,
                "ask": [1.1002] * 300,
                "spread": [0.0002] * 300,
                "tick_volume": [1.0] * 300,
                "source": ["jforex"] * 300,
                "client_tick_seq": list(range(300)),
                "run_id": ["jforex_live"] * 300,
            }
        )
        con.register("ticks_df", ticks)
        con.execute("INSERT INTO raw_ticks SELECT * FROM ticks_df")
        bars = pd.DataFrame(
            {
                "row_id": [0, 1, 2],
                "ts": pd.to_datetime(
                    [
                        "2026-05-02T00:00:00Z",
                        "2026-05-02T00:01:40Z",
                        "2026-05-02T00:03:20Z",
                    ],
                    utc=True,
                ),
                "close_ts": pd.to_datetime(
                    [
                        "2026-05-02T00:01:39Z",
                        "2026-05-02T00:03:19Z",
                        "2026-05-02T00:04:59Z",
                    ],
                    utc=True,
                ),
                "symbol": ["EURUSD"] * 3,
                "bar_ticks": [100] * 3,
                "open_bid": [1.1, 1.1001, 1.1002],
                "high_bid": [1.1002, 1.1003, 1.1004],
                "low_bid": [1.0999, 1.1, 1.1001],
                "close_bid": [1.1001, 1.1002, 1.1003],
                "spread": [0.0002] * 3,
                "tick_volume": [100.0] * 3,
                "hl_first": [1, -1, 1],
                "hl_pos_frac": [0.1, 0.2, 0.3],
                "high_ask": [1.1004, 1.1005, 1.1006],
                "close_ask": [1.1003, 1.1004, 1.1005],
            }
        )
        con.register("bars_df", bars)
        con.execute("INSERT INTO tick_bars SELECT * FROM bars_df")
    finally:
        con.close()


def test_discover_symbol_windows_uses_latest_completed_tick_bars(tmp_path: Path) -> None:
    db_path = tmp_path / "runtime.db"
    _create_runtime_db(db_path)
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        cfg = DeviationConfig(
            runtime_db=db_path,
            tick_root=tmp_path / "ticks",
            symbols=("EURUSD", "GBPUSD"),
            lookback_days=7,
            min_bars=2,
            run_id="jforex_live",
            out_dir=tmp_path / "out",
        )
        windows, skips = discover_symbol_windows(con, cfg)
    finally:
        con.close()

    assert len(windows) == 1
    assert windows[0].symbol == "EURUSD"
    assert windows[0].bar_count == 3
    assert windows[0].start_ts.isoformat() == "2026-05-02T00:00:00+00:00"
    assert windows[0].end_ts.isoformat() == "2026-05-02T00:04:59+00:00"
    assert skips.iloc[0]["symbol"] == "GBPUSD"
    assert skips.iloc[0]["reason"] == "missing_recent_tick_bars"


def test_extract_live_evidence_and_compute_live_metrics(tmp_path: Path) -> None:
    db_path = tmp_path / "runtime.db"
    _create_runtime_db(db_path)
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        window = discover_symbol_windows(
            con,
            DeviationConfig(
                runtime_db=db_path,
                tick_root=tmp_path / "ticks",
                symbols=("EURUSD",),
                lookback_days=7,
                min_bars=2,
                run_id="jforex_live",
                out_dir=tmp_path / "out",
            ),
        )[0][0]
        evidence = extract_live_evidence(con, window, run_id="jforex_live")
    finally:
        con.close()

    assert len(evidence.raw_ticks) == 300
    assert len(evidence.tick_bars) == 3
    tick_metrics = compute_tick_coverage("EURUSD", evidence.raw_ticks, evidence.raw_ticks)
    assert tick_metrics.loc[0, "live_rows"] == 300
    assert tick_metrics.loc[0, "governance_rows"] == 300
    bar_metrics = compute_bar_deviation("EURUSD", evidence.tick_bars, evidence.tick_bars)
    assert bar_metrics.loc[0, "live_bar_count"] == 3
    assert bar_metrics.loc[0, "missing_live_bars"] == 0
    assert bar_metrics.loc[0, "extra_live_bars"] == 0
    assert bar_metrics.loc[0, "max_abs_close_delta_pips"] == 0.0


def test_extract_live_evidence_filters_raw_ticks_by_run_id(tmp_path: Path) -> None:
    db_path = tmp_path / "runtime.db"
    _create_runtime_db(db_path)
    con = duckdb.connect(str(db_path))
    try:
        con.execute(
            """
            INSERT INTO raw_ticks
            SELECT tick_ts, ingest_ts, symbol, bid, ask, spread, tick_volume, source,
                   client_tick_seq + 1000, 'other_run'
            FROM raw_ticks
            WHERE run_id = 'jforex_live'
            """
        )
        window = discover_symbol_windows(
            con,
            DeviationConfig(
                runtime_db=db_path,
                tick_root=tmp_path / "ticks",
                symbols=("EURUSD",),
                lookback_days=7,
                min_bars=2,
                run_id="jforex_live",
                out_dir=tmp_path / "out",
            ),
        )[0][0]
        evidence = extract_live_evidence(con, window, run_id="jforex_live")
    finally:
        con.close()

    assert len(evidence.raw_ticks) == 300
    assert set(evidence.raw_ticks["run_id"]) == {"jforex_live"}


def test_extract_live_evidence_filters_trades_by_entry_window(tmp_path: Path) -> None:
    db_path = tmp_path / "runtime.db"
    _create_runtime_db(db_path)
    con = duckdb.connect(str(db_path))
    try:
        con.execute(
            """
            CREATE TABLE trades (
                internal_trade_id VARCHAR,
                symbol VARCHAR,
                entry_ts TIMESTAMP WITH TIME ZONE,
                run_id VARCHAR
            )
            """
        )
        con.execute(
            """
            INSERT INTO trades VALUES
                ('in-window', 'EURUSD', TIMESTAMPTZ '2026-05-02T00:02:00Z', 'jforex_live'),
                ('out-window', 'EURUSD', TIMESTAMPTZ '2026-05-03T00:02:00Z', 'jforex_live')
            """
        )
        window = discover_symbol_windows(
            con,
            DeviationConfig(
                runtime_db=db_path,
                tick_root=tmp_path / "ticks",
                symbols=("EURUSD",),
                lookback_days=7,
                min_bars=2,
                run_id="jforex_live",
                out_dir=tmp_path / "out",
            ),
        )[0][0]
        evidence = extract_live_evidence(con, window, run_id="jforex_live")
    finally:
        con.close()

    assert evidence.trades["internal_trade_id"].tolist() == ["in-window"]


def test_compute_bar_deviation_returns_nan_when_delta_columns_missing() -> None:
    live_bars = pd.DataFrame(
        {"close_ts": pd.to_datetime(["2026-05-02T00:01:39Z"], utc=True)}
    )
    governance_bars = pd.DataFrame(
        {"close_ts": pd.to_datetime(["2026-05-02T00:01:39Z"], utc=True)}
    )

    metrics = compute_bar_deviation("EURUSD", live_bars, governance_bars)

    assert metrics.loc[0, "matched_bars"] == 1
    assert pd.isna(metrics.loc[0, "max_abs_close_delta_pips"])
    assert pd.isna(metrics.loc[0, "max_abs_spread_delta_pips"])


def test_compute_bar_deviation_deduplicates_close_ts_before_matching() -> None:
    close_ts = pd.to_datetime(
        [
            "2026-05-02T00:01:39Z",
            "2026-05-02T00:01:39Z",
            "2026-05-02T00:03:19Z",
        ],
        utc=True,
    )
    live_bars = pd.DataFrame(
        {
            "row_id": [1, 2, 3],
            "close_ts": close_ts,
            "close_bid": [1.1001, 1.1002, 1.1003],
            "spread": [0.0002, 0.0003, 0.0002],
        }
    )
    governance_bars = pd.DataFrame(
        {
            "row_id": [4, 5, 6],
            "close_ts": close_ts,
            "close_bid": [1.1001, 1.1002, 1.1004],
            "spread": [0.0002, 0.0003, 0.0004],
        }
    )

    metrics = compute_bar_deviation("EURUSD", live_bars, governance_bars)

    assert metrics.loc[0, "live_bar_count"] == 3
    assert metrics.loc[0, "governance_bar_count"] == 3
    assert metrics.loc[0, "matched_bars"] == 2
    assert metrics.loc[0, "live_duplicate_close_ts"] == 1
    assert metrics.loc[0, "governance_duplicate_close_ts"] == 1
    assert metrics.loc[0, "max_abs_close_delta_pips"] == pytest.approx(1.0)


from src.behemoth.diagnostics.live_governance_deviation import (
    build_governance_bars_for_window,
    load_canonical_ticks_for_window,
)


def test_load_canonical_ticks_and_build_governance_bars(tmp_path: Path) -> None:
    tick_root = tmp_path / "dukascopy_ticks"
    sym_dir = tick_root / "EURUSD"
    sym_dir.mkdir(parents=True)
    ticks = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-05-02T00:00:00Z", periods=250, freq="s"),
            "bid": [1.1 + i * 0.000001 for i in range(250)],
            "ask": [1.1002 + i * 0.000001 for i in range(250)],
            "mid": [1.1001 + i * 0.000001 for i in range(250)],
            "spread": [0.0002] * 250,
            "log_return": [0.0] * 250,
        }
    )
    ticks.to_parquet(sym_dir / "EURUSD_202605_ticks.parquet", index=False)

    loaded = load_canonical_ticks_for_window(
        tick_root=tick_root,
        symbol="EURUSD",
        start_ts=pd.Timestamp("2026-05-02T00:00:00Z"),
        end_ts=pd.Timestamp("2026-05-02T00:04:10Z"),
    )
    bars = build_governance_bars_for_window(loaded, bar_ticks=100)

    assert len(loaded) == 250
    assert len(bars) == 2
    assert {
        "close_ts",
        "open_bid",
        "high_bid",
        "low_bid",
        "close_bid",
        "high_ask",
        "close_ask",
    }.issubset(bars.columns)
