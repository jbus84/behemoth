from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts.replay_histdata_cbot_testclient import (
    ReplayStats,
    _apply_sequence_fallback_matches,
    _build_stage12_summary_df,
    _filter_expected_to_reduced_core,
    _load_hist_ticks_for_replay,
    _match_expected_runtime_on_close_ts,
)


def test_filter_expected_to_reduced_core_full_key_match() -> None:
    expected = pd.DataFrame(
        [
            {
                "candidate_uid": "oco|EURUSD|100|h5|state_a",
                "close_ts": pd.Timestamp("2025-07-07T10:00:00Z"),
                "side": "BUY",
                "entry_price": 1.1000,
                "entry_ts": pd.Timestamp("2025-07-07T10:01:00Z"),
                "exit_ts": pd.Timestamp("2025-07-07T10:05:00Z"),
            },
            {
                "candidate_uid": "oco|EURUSD|100|h6|state_b",
                "close_ts": pd.Timestamp("2025-07-07T11:00:00Z"),
                "side": "SELL",
                "entry_price": 1.1010,
                "entry_ts": pd.Timestamp("2025-07-07T11:01:00Z"),
                "exit_ts": pd.Timestamp("2025-07-07T11:05:00Z"),
            },
        ]
    )
    schedule = pd.DataFrame(
        [
            {
                "test_month": "2025-07",
                "bar_ticks": 100,
                "horizon": 5,
                "state_id": "state_a",
            }
        ]
    )

    out = _filter_expected_to_reduced_core(expected=expected, schedule=schedule)

    assert len(out) == 1
    assert out.iloc[0]["candidate_uid"] == "oco|EURUSD|100|h5|state_a"


def test_match_expected_runtime_on_close_ts_reports_missing_and_extra() -> None:
    expected = pd.DataFrame(
        [
            {
                "candidate_uid": "oco|EURUSD|100|h5|state_a",
                "close_ts": pd.Timestamp("2025-07-07T10:00:00Z"),
            },
            {
                "candidate_uid": "oco|EURUSD|100|h6|state_b",
                "close_ts": pd.Timestamp("2025-07-07T10:00:10Z"),
            },
        ]
    )
    runtime = pd.DataFrame(
        [
            {
                "candidate_uid": "oco|EURUSD|100|h5|state_a",
                "close_ts": pd.Timestamp("2025-07-07T10:00:00.400000Z"),
            },
            {
                "candidate_uid": "oco|EURUSD|100|h7|state_x",
                "close_ts": pd.Timestamp("2025-07-07T10:00:20Z"),
            },
        ]
    )

    matches, missing, extra = _match_expected_runtime_on_close_ts(
        expected=expected,
        runtime=runtime,
        tolerance_sec=1.0,
    )

    assert len(matches) == 1
    assert len(missing) == 1
    assert missing.iloc[0]["candidate_uid"] == "oco|EURUSD|100|h6|state_b"
    assert len(extra) == 1
    assert extra.iloc[0]["candidate_uid"] == "oco|EURUSD|100|h7|state_x"


def test_match_expected_runtime_prefers_nearest_unmatched_row() -> None:
    expected = pd.DataFrame(
        [
            {
                "candidate_uid": "oco|EURUSD|100|h5|state_a",
                "close_ts": pd.Timestamp("2025-07-07T10:00:00Z"),
            },
            {
                "candidate_uid": "oco|EURUSD|100|h5|state_a",
                "close_ts": pd.Timestamp("2025-07-07T10:00:05Z"),
            },
        ]
    )
    runtime = pd.DataFrame(
        [
            {
                "candidate_uid": "oco|EURUSD|100|h5|state_a",
                "close_ts": pd.Timestamp("2025-07-07T10:00:00.900000Z"),
            },
            {
                "candidate_uid": "oco|EURUSD|100|h5|state_a",
                "close_ts": pd.Timestamp("2025-07-07T10:00:05.100000Z"),
            },
            {
                "candidate_uid": "oco|EURUSD|100|h5|state_a",
                "close_ts": pd.Timestamp("2025-07-07T10:00:05.700000Z"),
            },
        ]
    )

    matches, missing, extra = _match_expected_runtime_on_close_ts(
        expected=expected,
        runtime=runtime,
        tolerance_sec=1.0,
    )

    assert len(matches) == 2
    assert len(missing) == 0
    assert len(extra) == 1
    assert float(matches["abs_dt_sec"].max()) <= 1.0


def test_apply_sequence_fallback_matches_by_order_with_gap_cap() -> None:
    expected_all = pd.DataFrame(
        [
            {
                "candidate_uid": "oco|EURUSD|100|h5|state_a",
                "close_ts": pd.Timestamp("2025-07-07T10:00:00Z"),
            },
            {
                "candidate_uid": "oco|EURUSD|100|h5|state_a",
                "close_ts": pd.Timestamp("2025-07-07T10:01:00Z"),
            },
        ]
    )
    runtime_all = pd.DataFrame(
        [
            {
                "candidate_uid": "oco|EURUSD|100|h5|state_a",
                "close_ts": pd.Timestamp("2025-07-07T10:00:20Z"),
            },
            {
                "candidate_uid": "oco|EURUSD|100|h5|state_a",
                "close_ts": pd.Timestamp("2025-07-07T10:01:10Z"),
            },
        ]
    )
    strict_matches = pd.DataFrame(columns=["expected_idx", "runtime_idx", "abs_dt_sec", "match_mode"])
    strict_missing = expected_all.copy()
    strict_extra = runtime_all.copy()

    all_matches, miss_after, extra_after = _apply_sequence_fallback_matches(
        all_expected=expected_all,
        all_runtime=runtime_all,
        matches=strict_matches,
        missing_expected=strict_missing,
        extra_runtime=strict_extra,
        max_gap_sec=30.0,
    )

    assert len(all_matches) == 2
    assert set(all_matches["match_mode"].tolist()) == {"fallback_nearest"}
    assert len(miss_after) == 0
    assert len(extra_after) == 0


def test_stage12_summary_requires_both_signal_and_execution_parity() -> None:
    stats = ReplayStats(
        ticks_streamed=100,
        ticks_accepted=100,
        ticks_dropped=0,
        bars_completed_events=10,
        predict_calls=10,
        predict_warmup_422=0,
        predict_errors=0,
        selected_rows_runtime=5,
        expected_rows_reduced=4,
        selected_missing_expected=1,
        selected_extra_runtime=0,
        fallback_match_count=0,
    )
    exec_summary = pd.DataFrame(
        [{"histdata_execution_parity_verdict": "green", "overall_pass": True}]
    )
    exec_checks = pd.DataFrame(
        [{"status": "pass", "severity": "critical"}, {"status": "pass", "severity": "high"}]
    )

    out = _build_stage12_summary_df(
        symbol="EURUSD",
        start=pd.Timestamp("2025-07-07T00:00:00Z"),
        end=pd.Timestamp("2025-07-09T00:00:00Z"),
        runtime_db=Path("runtime.db"),
        events_json=Path("events.json"),
        stats=stats,
        execution_summary_df=exec_summary,
        execution_checks_df=exec_checks,
        warmup_source="month_start",
        warmup_ticks=30000,
        warmup_sent=1000,
    )

    assert bool(out.iloc[0]["execution_parity_pass"]) is True
    assert bool(out.iloc[0]["signal_parity_pass"]) is False
    assert bool(out.iloc[0]["stage12_api_parity_pass"]) is False


def test_load_hist_ticks_for_replay_history_tail_preserves_full_history_phase(
    tmp_path: Path,
) -> None:
    symbol = "EURUSD"
    sym_dir = tmp_path / symbol
    sym_dir.mkdir(parents=True, exist_ok=True)

    pre_1 = pd.DataFrame(
        {
            "timestamp": pd.date_range("2025-06-30T23:59:50Z", periods=7, freq="1s"),
            "bid": [1.1000 + i * 0.0001 for i in range(7)],
            "ask": [1.1002 + i * 0.0001 for i in range(7)],
        }
    )
    pre_2 = pd.DataFrame(
        {
            "timestamp": pd.date_range("2025-07-01T00:00:00Z", periods=8, freq="1s"),
            "bid": [1.2000 + i * 0.0001 for i in range(8)],
            "ask": [1.2002 + i * 0.0001 for i in range(8)],
        }
    )
    stream_df = pd.DataFrame(
        {
            "timestamp": pd.date_range("2025-07-01T00:00:08Z", periods=4, freq="1s"),
            "bid": [1.3000 + i * 0.0001 for i in range(4)],
            "ask": [1.3002 + i * 0.0001 for i in range(4)],
        }
    )

    pre_1.to_parquet(sym_dir / f"{symbol}_202506_ticks.parquet", index=False)
    pd.concat([pre_2, stream_df], ignore_index=True).to_parquet(
        sym_dir / f"{symbol}_202507_ticks.parquet",
        index=False,
    )

    warmup, stream = _load_hist_ticks_for_replay(
        symbol=symbol,
        tick_root=tmp_path,
        start=pd.Timestamp("2025-07-01T00:00:08Z"),
        end=pd.Timestamp("2025-07-01T00:00:12Z"),
        warmup_ticks=5,
        lookback_days=1,
        warmup_source="history_tail",
        phase_bar_ticks=4,
    )

    assert len(stream) == 4
    assert len(warmup) == 8
    assert warmup["ts"].iloc[0] == pd.Timestamp("2025-07-01T00:00:00Z")
    assert warmup["ts"].iloc[-1] == pd.Timestamp("2025-07-01T00:00:07Z")
