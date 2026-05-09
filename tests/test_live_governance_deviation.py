from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import duckdb
import pandas as pd
import pytest

import scripts.analyze_live_governance_deviation as cli
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


def test_parse_symbols_deduplicates_and_ignores_blank_tokens() -> None:
    assert cli._parse_symbols(" eurusd, ,GBPUSD,eurusd,, gbpusd ") == (
        "EURUSD",
        "GBPUSD",
    )
    assert cli._parse_symbols(None) == cli.ACTIVE_SYMBOLS
    assert cli._parse_symbols(" , ") == cli.ACTIVE_SYMBOLS


def test_cli_rejects_invalid_timestamp_without_pandas_traceback(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/analyze_live_governance_deviation.py",
            "--runtime-db",
            str(tmp_path / "missing.db"),
            "--tick-root",
            str(tmp_path / "ticks"),
            "--symbols",
            "EURUSD",
            "--start-ts",
            "not-a-date",
            "--end-ts",
            "2026-05-02T00:00:00Z",
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode != 0
    assert "invalid timestamp" in result.stderr
    assert "not-a-date" in result.stderr
    assert "Traceback" not in result.stderr
    assert "pandas" not in result.stderr


@pytest.mark.parametrize("partial_arg", ["--start-ts", "--end-ts"])
def test_cli_rejects_partial_explicit_window(
    tmp_path: Path, partial_arg: str
) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/analyze_live_governance_deviation.py",
            "--runtime-db",
            str(tmp_path / "missing.db"),
            "--tick-root",
            str(tmp_path / "ticks"),
            "--symbols",
            "EURUSD",
            partial_arg,
            "2026-05-02T00:00:00Z",
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode != 0
    assert "--start-ts and --end-ts must be supplied together" in result.stderr
    assert "Traceback" not in result.stderr


def test_cli_smoke_writes_report(tmp_path: Path) -> None:
    db_path = tmp_path / "runtime.db"
    _create_runtime_db(db_path)
    tick_root = tmp_path / "dukascopy_ticks"
    sym_dir = tick_root / "EURUSD"
    sym_dir.mkdir(parents=True)
    canonical = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-05-02T00:00:00Z", periods=300, freq="s"),
            "bid": [1.1] * 300,
            "ask": [1.1002] * 300,
            "mid": [1.1001] * 300,
            "spread": [0.0002] * 300,
            "log_return": [0.0] * 300,
        }
    )
    canonical.to_parquet(sym_dir / "EURUSD_202605_ticks.parquet", index=False)
    out_dir = tmp_path / "out"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/analyze_live_governance_deviation.py",
            "--runtime-db",
            str(db_path),
            "--tick-root",
            str(tick_root),
            "--symbols",
            "EURUSD",
            "--lookback-days",
            "7",
            "--min-bars",
            "2",
            "--run-id",
            "jforex_live",
            "--out-dir",
            str(out_dir),
        ],
        check=False,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    assert "report=" in result.stdout
    assert list(out_dir.glob("*/live_governance_deviation_report.md"))


def test_cli_accepts_complete_explicit_window(tmp_path: Path) -> None:
    db_path = tmp_path / "runtime.db"
    _create_runtime_db(db_path)
    tick_root = tmp_path / "dukascopy_ticks"
    sym_dir = tick_root / "EURUSD"
    sym_dir.mkdir(parents=True)
    canonical = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-05-02T00:00:00Z", periods=300, freq="s"),
            "bid": [1.1] * 300,
            "ask": [1.1002] * 300,
            "mid": [1.1001] * 300,
            "spread": [0.0002] * 300,
            "log_return": [0.0] * 300,
        }
    )
    canonical.to_parquet(sym_dir / "EURUSD_202605_ticks.parquet", index=False)
    out_dir = tmp_path / "out"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/analyze_live_governance_deviation.py",
            "--runtime-db",
            str(db_path),
            "--tick-root",
            str(tick_root),
            "--symbols",
            "EURUSD",
            "--lookback-days",
            "7",
            "--min-bars",
            "2",
            "--run-id",
            "jforex_live",
            "--out-dir",
            str(out_dir),
            "--start-ts",
            "2026-05-02T00:00:00Z",
            "--end-ts",
            "2026-05-02T00:04:59Z",
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    assert "report=" in result.stdout
    assert list(out_dir.glob("*/live_governance_deviation_report.md"))


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
        tick_root,
        "EURUSD",
        pd.Timestamp("2026-05-02T00:00:00Z"),
        pd.Timestamp("2026-05-02T00:04:10Z"),
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


def test_load_canonical_ticks_retains_mixed_timestamp_formats_across_months(
    tmp_path: Path,
) -> None:
    tick_root = tmp_path / "dukascopy_ticks"
    sym_dir = tick_root / "EURUSD"
    sym_dir.mkdir(parents=True)
    pd.DataFrame(
        {
            "timestamp": ["2026-04-30 23:59:59+00:00"],
            "bid": [1.1],
            "ask": [1.1002],
            "mid": [1.1001],
            "spread": [0.0002],
            "log_return": [0.0],
        }
    ).to_parquet(sym_dir / "EURUSD_202604_ticks.parquet", index=False)
    pd.DataFrame(
        {
            "timestamp": ["2026-05-01T00:00:00Z"],
            "bid": [1.1001],
            "ask": [1.1003],
            "mid": [1.1002],
            "spread": [0.0002],
            "log_return": [0.0],
        }
    ).to_parquet(sym_dir / "EURUSD_202605_ticks.parquet", index=False)

    loaded = load_canonical_ticks_for_window(
        tick_root,
        "EURUSD",
        pd.Timestamp("2026-04-30T23:59:58Z"),
        pd.Timestamp("2026-05-01T00:00:01Z"),
    )

    assert loaded["timestamp"].dt.strftime("%Y-%m-%dT%H:%M:%SZ").tolist() == [
        "2026-04-30T23:59:59Z",
        "2026-05-01T00:00:00Z",
    ]


def test_mid_only_canonical_ticks_build_governance_bars(tmp_path: Path) -> None:
    tick_root = tmp_path / "dukascopy_ticks"
    sym_dir = tick_root / "EURUSD"
    sym_dir.mkdir(parents=True)
    pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-05-02T00:00:00Z", periods=100, freq="s"),
            "mid": [1.1001 + i * 0.000001 for i in range(100)],
            "spread": [0.0002] * 100,
            "log_return": [0.0] * 100,
        }
    ).to_parquet(sym_dir / "EURUSD_202605_ticks.parquet", index=False)

    loaded = load_canonical_ticks_for_window(
        tick_root,
        "EURUSD",
        pd.Timestamp("2026-05-02T00:00:00Z"),
        pd.Timestamp("2026-05-02T00:01:39Z"),
    )
    bars = build_governance_bars_for_window(loaded, bar_ticks=100)

    assert "bid" not in loaded.columns
    assert len(bars) == 1
    assert bars.loc[0, "open_bid"] == pytest.approx(1.1001)


def test_build_governance_bars_returns_empty_for_unsupported_bar_ticks() -> None:
    ticks = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-05-02T00:00:00Z", periods=100, freq="s"),
            "bid": [1.1] * 100,
            "ask": [1.1002] * 100,
            "mid": [1.1001] * 100,
            "spread": [0.0002] * 100,
            "log_return": [0.0] * 100,
        }
    )

    bars = build_governance_bars_for_window(ticks, bar_ticks=1000)

    assert bars.empty


from src.behemoth.diagnostics.live_governance_deviation import (
    build_findings,
    compute_outcome_deviation,
    compute_signal_deviation,
    render_report,
)


def test_signal_outcome_findings_and_report() -> None:
    live_predictions = pd.DataFrame(
        {
            "symbol": ["EURUSD", "EURUSD"],
            "candidate_uid": ["oco|EURUSD|100|h6|a", "oco|EURUSD|100|h6|a"],
            "pred_prob": [0.7, 0.8],
            "threshold": [0.75, 0.75],
            "selected_exec": [0, 1],
        }
    )
    governance_predictions = pd.DataFrame(
        {
            "symbol": ["EURUSD", "EURUSD", "EURUSD"],
            "candidate_uid": ["oco|EURUSD|100|h6|a"] * 3,
            "pred_prob": [0.7, 0.8, 0.9],
            "threshold": [0.75, 0.75, 0.75],
            "selected": [0, 1, 1],
        }
    )
    signal = compute_signal_deviation(
        "EURUSD", live_predictions, governance_predictions, live_source="predict_evaluations"
    )
    assert signal.loc[0, "live_prediction_rows"] == 2
    assert signal.loc[0, "governance_prediction_rows"] == 3
    assert signal.loc[0, "live_selected_signal_count"] == 1
    assert signal.loc[0, "governance_selected_signal_count"] == 2

    trades = pd.DataFrame({"status": ["CLOSED", "OPEN"], "pnl_pips": [3.0, 0.0]})
    outcome = compute_outcome_deviation("EURUSD", trades, governance_selected_signal_count=2)
    assert outcome.loc[0, "Runtime Trade Count"] == 2
    assert outcome.loc[0, "Runtime Closed Trade Count"] == 1
    assert outcome.loc[0, "Runtime Realized P&L"] == 3.0
    assert outcome.loc[0, "runtime_trade_count"] == 2
    assert outcome.loc[0, "runtime_realized_pnl_pips"] == 3.0

    findings = build_findings(
        bar_deviation=pd.DataFrame(
            [
                {
                    "symbol": "EURUSD",
                    "missing_live_bars": 1,
                    "extra_live_bars": 0,
                    "max_abs_close_delta_pips": 0.0,
                }
            ]
        ),
        signal_deviation=signal,
        incomplete_rows=pd.DataFrame(),
    )
    assert "Material Drift" in set(findings["classification"])
    report = render_report(
        manifest={"run_id": "unit", "generated_at_utc": "2026-05-09T00:00:00Z"},
        window_summary=pd.DataFrame([{"symbol": "EURUSD", "bar_count": 2}]),
        findings=findings,
        tick_coverage=pd.DataFrame(),
        bar_deviation=pd.DataFrame(),
        signal_deviation=signal,
        outcome_deviation=outcome,
        skips=pd.DataFrame(),
    )
    assert "# Live Governance Deviation Report" in report
    assert "not a Promotion gate" in report


def test_signal_deviation_counts_common_truthy_selected_values() -> None:
    live_predictions = pd.DataFrame(
        {
            "selected_exec": [
                "true",
                "TRUE",
                "yes",
                "t",
                "y",
                "1",
                True,
                1,
                "false",
                "0",
                None,
            ]
        }
    )
    governance_predictions = pd.DataFrame(
        {"selected": ["true", "yes", "1", "no", False, 0, None]}
    )

    signal = compute_signal_deviation(
        "EURUSD", live_predictions, governance_predictions, live_source="unit"
    )

    assert signal.loc[0, "live_selected_signal_count"] == 8
    assert signal.loc[0, "governance_selected_signal_count"] == 3


def test_outcome_deviation_preserves_unknown_missing_runtime_evidence() -> None:
    missing_status = compute_outcome_deviation(
        "EURUSD",
        pd.DataFrame({"pnl_pips": [3.0]}),
        governance_selected_signal_count=1,
    )
    assert pd.isna(missing_status.loc[0, "Runtime Closed Trade Count"])
    assert pd.isna(missing_status.loc[0, "runtime_closed_trade_count"])
    assert pd.isna(missing_status.loc[0, "Runtime Realized P&L"])
    assert pd.isna(missing_status.loc[0, "runtime_realized_pnl_pips"])

    missing_pnl = compute_outcome_deviation(
        "EURUSD",
        pd.DataFrame({"status": ["CLOSED"]}),
        governance_selected_signal_count=1,
    )
    assert missing_pnl.loc[0, "Runtime Closed Trade Count"] == 1
    assert missing_pnl.loc[0, "runtime_closed_trade_count"] == 1
    assert pd.isna(missing_pnl.loc[0, "Runtime Realized P&L"])
    assert pd.isna(missing_pnl.loc[0, "runtime_realized_pnl_pips"])


def test_report_mentions_existing_diagnostic_subreports() -> None:
    report = render_report(
        manifest={
            "run_id": "unit",
            "generated_at_utc": "2026-05-09T00:00:00Z",
            "subreports": {
                "live_audit": "live_audit.md",
                "performance_gap": "performance_gap.md",
                "runtime_summary": "runtime_summary.csv",
            },
        },
        window_summary=pd.DataFrame(),
        findings=pd.DataFrame(),
        tick_coverage=pd.DataFrame(),
        bar_deviation=pd.DataFrame(),
        signal_deviation=pd.DataFrame(),
        outcome_deviation=pd.DataFrame(),
        skips=pd.DataFrame(),
    )
    assert "Existing Diagnostic Subreports" in report
    assert "live_audit.md" in report
    assert "performance_gap.md" in report


import src.behemoth.diagnostics.live_governance_deviation as live_governance_deviation
from src.behemoth.diagnostics.live_governance_deviation import run_analysis


def test_run_analysis_writes_required_outputs(tmp_path: Path) -> None:
    db_path = tmp_path / "runtime.db"
    _create_runtime_db(db_path)
    tick_root = tmp_path / "dukascopy_ticks"
    sym_dir = tick_root / "EURUSD"
    sym_dir.mkdir(parents=True)
    canonical = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-05-02T00:00:00Z", periods=300, freq="s"),
            "bid": [1.1] * 300,
            "ask": [1.1002] * 300,
            "mid": [1.1001] * 300,
            "spread": [0.0002] * 300,
            "log_return": [0.0] * 300,
        }
    )
    canonical.to_parquet(sym_dir / "EURUSD_202605_ticks.parquet", index=False)
    out_dir = tmp_path / "out"

    result = run_analysis(
        DeviationConfig(
            runtime_db=db_path,
            tick_root=tick_root,
            symbols=("EURUSD",),
            lookback_days=7,
            min_bars=2,
            run_id="jforex_live",
            out_dir=out_dir,
        )
    )

    assert result["manifest_path"].exists()
    assert (result["run_dir"] / "window_summary.csv").exists()
    assert (result["run_dir"] / "symbol_skips.csv").exists()
    assert (result["run_dir"] / "tick_coverage_deviation.csv").exists()
    assert (result["run_dir"] / "bar_deviation.csv").exists()
    assert (result["run_dir"] / "signal_deviation.csv").exists()
    assert (result["run_dir"] / "outcome_deviation.csv").exists()
    assert (result["run_dir"] / "findings.csv").exists()
    assert (result["run_dir"] / "live_governance_deviation_report.md").exists()
    assert (result["run_dir"] / "EURUSD_live_raw_ticks.parquet").exists()
    assert (result["run_dir"] / "EURUSD_live_tick_bars.parquet").exists()
    assert (result["run_dir"] / "EURUSD_governance_raw_ticks.parquet").exists()
    manifest = json.loads(result["manifest_path"].read_text(encoding="utf-8"))
    assert manifest["subreports"] == {
        "runtime_summary": str(result["run_dir"] / "window_summary.csv"),
        "live_audit": str(result["run_dir"] / "live_audit_report.md"),
        "performance_gap": str(result["run_dir"] / "live_performance_gap_report.md"),
    }
    assert (result["run_dir"] / "EURUSD_governance_tick_bars.parquet").exists()


def test_run_analysis_creates_distinct_run_dirs_for_immediate_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "runtime.db"
    _create_runtime_db(db_path)
    out_dir = tmp_path / "out"
    fixed_now = pd.Timestamp("2026-05-09T16:30:00Z")
    monkeypatch.setattr(live_governance_deviation, "utc_now", lambda: fixed_now)
    cfg = DeviationConfig(
        runtime_db=db_path,
        tick_root=tmp_path / "missing_ticks",
        symbols=("EURUSD",),
        lookback_days=7,
        min_bars=2,
        run_id="jforex_live",
        out_dir=out_dir,
    )

    first = run_analysis(cfg)
    stale_marker = first["run_dir"] / "stale_artifact.txt"
    stale_marker.write_text("stale", encoding="utf-8")
    second = run_analysis(cfg)

    assert first["run_dir"] != second["run_dir"]
    assert stale_marker.exists()
    assert not (second["run_dir"] / "stale_artifact.txt").exists()


def test_run_analysis_all_skipped_writes_parseable_required_csvs(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "runtime.db"
    _create_runtime_db(db_path)
    result = run_analysis(
        DeviationConfig(
            runtime_db=db_path,
            tick_root=tmp_path / "missing_ticks",
            symbols=("GBPUSD",),
            lookback_days=7,
            min_bars=2,
            run_id="jforex_live",
            out_dir=tmp_path / "out",
        )
    )

    expected_columns = {
        "window_summary.csv": [
            "symbol",
            "start_ts",
            "end_ts",
            "raw_tick_count",
            "bar_count",
            "bar_ticks",
        ],
        "symbol_skips.csv": ["symbol", "reason"],
        "tick_coverage_deviation.csv": [
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
        ],
        "bar_deviation.csv": [
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
        ],
        "signal_deviation.csv": [
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
        ],
        "outcome_deviation.csv": [
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
        ],
        "findings.csv": ["symbol", "classification", "code", "severity", "summary"],
    }
    for filename, columns in expected_columns.items():
        frame = pd.read_csv(result["run_dir"] / filename)
        assert list(frame.columns) == columns


def test_run_analysis_missing_canonical_ticks_writes_schemaful_governance_bars(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "runtime.db"
    _create_runtime_db(db_path)

    result = run_analysis(
        DeviationConfig(
            runtime_db=db_path,
            tick_root=tmp_path / "missing_ticks",
            symbols=("EURUSD",),
            lookback_days=7,
            min_bars=2,
            run_id="jforex_live",
            out_dir=tmp_path / "out",
        )
    )

    governance_bars = pd.read_parquet(
        result["run_dir"] / "EURUSD_governance_tick_bars.parquet"
    )
    assert len(governance_bars) == 0
    assert {
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
    }.issubset(governance_bars.columns)
