from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import polars as pl

from scripts.replay_histdata_cbot_testclient import (
    ReplayStats,
    _apply_sequence_fallback_matches,
    _build_signal_feature_diff,
    _build_signal_gap_analysis,
    _build_stage12_summary_df,
    _filter_expected_to_reduced_core,
    _load_hist_ticks_for_replay,
    _match_expected_runtime_on_close_ts,
    _should_filter_first_partial_selected_row,
)
from src.behemoth.core.features import compute_features_from_bars


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


def test_locked_payload_mode_keeps_first_partial_selected_row() -> None:
    assert _should_filter_first_partial_selected_row(
        historical_prediction_payload_mode="locked"
    ) is False
    assert _should_filter_first_partial_selected_row(
        historical_prediction_payload_mode="model"
    ) is True


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
        selected_parity_mode="strict",
        strict_selected_missing_expected=1,
        strict_selected_extra_runtime=0,
        event_aligned_selected_missing_expected=1,
        event_aligned_selected_extra_runtime=0,
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
        tick_offset=25,
    )

    assert bool(out.iloc[0]["execution_parity_pass"]) is True
    assert bool(out.iloc[0]["signal_parity_pass"]) is False
    assert bool(out.iloc[0]["stage12_api_parity_pass"]) is False


def test_build_signal_gap_analysis_classifies_seen_but_not_selected_vs_no_bar() -> None:
    expected = pd.DataFrame(
        [
            {"candidate_uid": "oco|EURUSD|100|h5|state_a", "close_ts": pd.Timestamp("2025-07-07T10:00:00Z")},
            {"candidate_uid": "oco|EURUSD|100|h5|state_b", "close_ts": pd.Timestamp("2025-07-07T11:00:00Z")},
        ]
    )
    runtime = pd.DataFrame(
        [{"candidate_uid": "oco|EURUSD|100|h5|state_a", "close_ts": pd.Timestamp("2025-07-07T10:00:40Z")}]
    )
    missing = expected.copy()
    extra = pd.DataFrame(columns=["candidate_uid", "close_ts"])
    predict_trace = pd.DataFrame(
        [
            {
                "trace_ts": pd.Timestamp("2025-07-07T10:00:00Z"),
                "candidate_uid": "oco|EURUSD|100|h5|state_a",
                "close_ts": pd.Timestamp("2025-07-07T10:00:20Z"),
                "selected_exec": 0,
                "pred_prob": 0.55,
                "threshold_exec": 0.60,
                "risk_blocked": False,
                "reason": "ok",
            },
            {
                "trace_ts": pd.Timestamp("2025-07-07T09:00:00Z"),
                "candidate_uid": "oco|EURUSD|100|h5|state_b",
                "close_ts": pd.Timestamp("2025-07-07T09:00:00Z"),
                "selected_exec": 0,
                "pred_prob": 0.40,
                "threshold_exec": 0.60,
                "risk_blocked": False,
                "reason": "ok",
            },
        ]
    )

    out = _build_signal_gap_analysis(
        expected_keys=expected,
        runtime_keys=runtime,
        missing_expected=missing,
        extra_runtime=extra,
        predict_trace_rows=predict_trace,
        classify_window_sec=300.0,
    )

    a_reason = out.loc[out["candidate_uid"] == "oco|EURUSD|100|h5|state_a", "gap_reason"].iloc[0]
    b_reason = out.loc[out["candidate_uid"] == "oco|EURUSD|100|h5|state_b", "gap_reason"].iloc[0]
    assert a_reason == "candidate_seen_but_not_selected"
    assert b_reason == "no_equivalent_runtime_bar_nearby"


def test_build_signal_feature_diff_reconstructs_offline_features(tmp_path: Path) -> None:
    n = 320
    ts = pd.date_range("2025-07-07T00:00:00Z", periods=n, freq="90s", tz="UTC")
    bars = pd.DataFrame(
        {
            "timestamp": ts - pd.to_timedelta(20, unit="s"),
            "close_ts": ts,
            "open": 1.1000 + pd.Series(range(n)) * 0.00001,
            "high": 1.1004 + pd.Series(range(n)) * 0.00001,
            "low": 1.0997 + pd.Series(range(n)) * 0.00001,
            "close": 1.1002 + pd.Series(range(n)) * 0.00001,
            "spread": 0.00012,
            "tick_volume": 100.0,
            "hl_first": 1.0,
            "hl_pos_frac": 0.25,
        }
    )
    tick_velocity_dir = tmp_path / "tick_velocity"
    tick_velocity_dir.mkdir(parents=True, exist_ok=True)
    bars.to_parquet(tick_velocity_dir / "EURUSD_100tick_velocity.parquet", index=False)

    ref_ts = pd.Timestamp(ts[-1])
    offline = compute_features_from_bars(
        bars,
        symbol="EURUSD",
        bar_ticks=100,
        horizon=5,
        barrier_pips=2.0,
    )
    assert offline is not None
    runtime_features = offline.model_dump()
    runtime_features["ret1_pips"] = float(runtime_features["ret1_pips"]) + 0.25

    signal_gap = pd.DataFrame(
        [
            {
                "gap_side": "missing_expected",
                "gap_reason": "candidate_seen_but_not_selected",
                "candidate_uid": "oco|EURUSD|100|h5|state_a__k2",
                "reference_close_ts": ref_ts,
                "nearest_predict_features_json": json.dumps(runtime_features),
                "offline_pred_prob": 0.61,
                "offline_threshold_exec": 0.60,
                "offline_margin": 0.01,
                "nearest_predict_pred_prob": 0.59,
                "nearest_predict_threshold_exec": 0.60,
                "nearest_predict_margin": -0.01,
                "margin_delta_runtime_minus_offline": -0.02,
            }
        ]
    )

    out = _build_signal_feature_diff(
        signal_gap_analysis=signal_gap,
        symbol="EURUSD",
        tick_velocity_dir=tick_velocity_dir,
    )

    assert not out.empty
    ret1 = out[out["feature_name"] == "ret1_pips"].iloc[0]
    assert abs(float(ret1["runtime_minus_offline"]) - 0.25) < 1e-9
    assert float(ret1["offline_margin"]) == 0.01
    assert float(ret1["runtime_margin"]) == -0.01


def test_load_hist_ticks_for_replay_applies_tick_offset(tmp_path: Path) -> None:
    tick_dir = tmp_path / "tick" / "EURUSD"
    tick_dir.mkdir(parents=True, exist_ok=True)
    ts = pd.date_range("2025-07-07T00:00:00Z", periods=8, freq="1s", tz="UTC")
    pl.DataFrame(
        {
            "timestamp": ts.to_pydatetime().tolist(),
            "bid": [1.10 + 0.0001 * i for i in range(8)],
            "ask": [1.1002 + 0.0001 * i for i in range(8)],
        },
        schema_overrides={"timestamp": pl.Datetime("ns", "UTC")},
    ).write_parquet(tick_dir / "EURUSD_202507_ticks.parquet")

    warmup, stream = _load_hist_ticks_for_replay(
        symbol="EURUSD",
        tick_root=tmp_path / "tick",
        start=pd.Timestamp("2025-07-07T00:00:04Z"),
        end=pd.Timestamp("2025-07-07T00:00:08Z"),
        warmup_ticks=2,
        lookback_days=31,
        warmup_source="history_tail",
        phase_bar_ticks=100,
        tick_offset=2,
    )

    assert len(warmup) == 2
    assert len(stream) == 4
    assert warmup["ts"].iloc[0] == pd.Timestamp("2025-07-07T00:00:02Z")
    assert stream["ts"].iloc[0] == pd.Timestamp("2025-07-07T00:00:04Z")


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


def test_load_hist_ticks_for_replay_history_tail_preserves_duplicate_timestamp_order(
    tmp_path: Path,
) -> None:
    symbol = "EURUSD"
    sym_dir = tmp_path / symbol
    sym_dir.mkdir(parents=True, exist_ok=True)

    df = pd.DataFrame(
        {
            "timestamp": [
                pd.Timestamp("2025-07-01T00:00:00Z"),
                pd.Timestamp("2025-07-01T00:00:01Z"),
                pd.Timestamp("2025-07-01T00:00:01Z"),
                pd.Timestamp("2025-07-01T00:00:01Z"),
                pd.Timestamp("2025-07-01T00:00:02Z"),
                pd.Timestamp("2025-07-01T00:00:03Z"),
                pd.Timestamp("2025-07-01T00:00:04Z"),
            ],
            "bid": [1.1000, 1.1001, 1.1002, 1.1003, 1.1004, 1.1005, 1.1006],
            "ask": [1.1002, 1.1003, 1.1004, 1.1005, 1.1006, 1.1007, 1.1008],
        }
    )
    df.to_parquet(sym_dir / f"{symbol}_202507_ticks.parquet", index=False)

    warmup, stream = _load_hist_ticks_for_replay(
        symbol=symbol,
        tick_root=tmp_path,
        start=pd.Timestamp("2025-07-01T00:00:03Z"),
        end=pd.Timestamp("2025-07-01T00:00:05Z"),
        warmup_ticks=2,
        lookback_days=1,
        warmup_source="history_tail",
        phase_bar_ticks=2,
    )

    assert warmup["bid"].tolist() == [1.1002, 1.1003, 1.1004]
    assert stream["bid"].tolist() == [1.1005, 1.1006]
