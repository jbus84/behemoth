from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from src.behemoth.diagnostics.live_governance_deviation import (
    DeviationConfig,
    discover_symbol_windows,
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
