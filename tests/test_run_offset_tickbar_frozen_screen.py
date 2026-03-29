from __future__ import annotations

import pandas as pd

from scripts.run_offset_tickbar_frozen_screen import (
    _add_event_ordinal,
    _baseline_gate,
    _build_baseline_parity,
    _canonical_state_coverage,
    _classify_offset_row,
    _cleanup_completed_symbol_artifacts,
    _frozen_event_window,
    _load_canonical_event_universe,
    _load_canonical_selected,
    _map_offset_events_to_canonical_universe,
    _selected_overlap_rate_by_event_id,
)


def test_canonical_state_coverage_counts_missing_states() -> None:
    canonical = pd.DataFrame(
        [
            {"test_month": "2025-07", "state_key": "s1|100|5"},
            {"test_month": "2025-07", "state_key": "s2|100|6"},
            {"test_month": "2025-08", "state_key": "s3|100|5"},
        ]
    )
    selected = pd.DataFrame(
        [
            {"test_month": "2025-07", "candidate_uid": "oco|EURUSD|100|h5|s1"},
            {"test_month": "2025-08", "candidate_uid": "oco|EURUSD|100|h5|s3"},
        ]
    )
    overall, monthly = _canonical_state_coverage(
        selected_keys=selected,
        canonical_schedule=canonical,
    )
    assert overall == 2 / 3
    july = monthly[monthly["test_month"] == "2025-07"].iloc[0].to_dict()
    assert july["canonical_state_count"] == 2
    assert july["covered_state_count"] == 1
    assert july["canonical_state_coverage_rate"] == 0.5


def test_canonical_state_coverage_empty_selection() -> None:
    canonical = pd.DataFrame(
        [
            {"test_month": "2025-07", "state_key": "s1|100|5"},
        ]
    )
    overall, monthly = _canonical_state_coverage(
        selected_keys=pd.DataFrame(columns=["test_month", "candidate_uid"]),
        canonical_schedule=canonical,
    )
    assert overall == 0.0
    row = monthly.iloc[0].to_dict()
    assert row["covered_state_count"] == 0
    assert row["canonical_state_coverage_rate"] == 0.0


def test_add_event_ordinal_counts_occurrences_within_candidate_and_month() -> None:
    df = pd.DataFrame(
        [
            {"candidate_uid": "c1", "close_ts": "2025-07-01T00:00:01Z"},
            {"candidate_uid": "c1", "close_ts": "2025-07-01T00:00:03Z"},
            {"candidate_uid": "c2", "close_ts": "2025-07-01T00:00:02Z"},
        ]
    )
    out = _add_event_ordinal(df)
    c1 = out[out["candidate_uid"] == "c1"].sort_values("close_ts")
    assert c1["event_ordinal"].tolist() == [0, 1]
    assert c1["frozen_event_id"].tolist()[0] == "2025-07|c1|0"


def test_map_offset_events_to_canonical_universe_matches_by_occurrence_order() -> None:
    canonical = _add_event_ordinal(
        pd.DataFrame(
            [
                {
                    "candidate_uid": "c1",
                    "close_ts": "2025-07-01T00:00:01Z",
                    "library": "oco",
                    "target_gross_pips": 1.0,
                    "target_gross_pos": 1,
                },
                {
                    "candidate_uid": "c1",
                    "close_ts": "2025-07-01T00:00:05Z",
                    "library": "oco",
                    "target_gross_pips": 2.0,
                    "target_gross_pos": 1,
                },
            ]
        )
    ).rename(columns={"close_ts": "canonical_close_ts"})
    offset = pd.DataFrame(
        [
            {
                "candidate_uid": "c1",
                "close_ts": "2025-07-01T00:00:02Z",
                "library": "oco",
                "target_gross_pips": 1.5,
                "target_gross_pos": 1,
            },
            {
                "candidate_uid": "c1",
                "close_ts": "2025-07-01T00:00:06Z",
                "library": "oco",
                "target_gross_pips": 2.5,
                "target_gross_pos": 1,
            },
        ]
    )
    mapped, details = _map_offset_events_to_canonical_universe(
        offset_events=offset, canonical_events=canonical
    )
    assert len(mapped) == 2
    assert mapped["close_ts"].dt.strftime("%Y-%m-%dT%H:%M:%SZ").tolist() == [
        "2025-07-01T00:00:02Z",
        "2025-07-01T00:00:06Z",
    ]
    assert details["mapping_status"].tolist() == ["mapped", "mapped"]


def test_selected_overlap_uses_event_identity_not_close_ts() -> None:
    canonical = pd.DataFrame(
        [
            {"test_month": "2025-07", "candidate_uid": "c1", "event_ordinal": 0},
        ]
    )
    current = pd.DataFrame(
        [
            {"test_month": "2025-07", "candidate_uid": "c1", "event_ordinal": 0},
        ]
    )
    assert _selected_overlap_rate_by_event_id(canonical, current) == 1.0


def test_build_baseline_parity_flags_unmapped_events() -> None:
    canonical_events = pd.DataFrame(
        [
            {
                "frozen_event_id": "2025-07|c1|0",
                "candidate_uid": "c1",
                "test_month": "2025-07",
                "canonical_close_ts": pd.Timestamp("2025-07-01T00:00:01Z"),
            },
            {
                "frozen_event_id": "2025-07|c1|1",
                "candidate_uid": "c1",
                "test_month": "2025-07",
                "canonical_close_ts": pd.Timestamp("2025-07-01T00:00:05Z"),
            },
        ]
    )
    mapped = pd.DataFrame(
        [
            {
                "frozen_event_id": "2025-07|c1|0",
                "offset_close_ts": pd.Timestamp("2025-07-01T00:00:01Z"),
            },
        ]
    )
    canonical_selected = pd.DataFrame(
        [
            {
                "test_month": "2025-07",
                "candidate_uid": "c1",
                "event_ordinal": 0,
                "frozen_event_id": "2025-07|c1|0",
            },
            {
                "test_month": "2025-07",
                "candidate_uid": "c1",
                "event_ordinal": 1,
                "frozen_event_id": "2025-07|c1|1",
            },
        ]
    )
    current_selected = canonical_selected.iloc[[0]].copy()
    summary, mismatches = _build_baseline_parity(
        symbol="EURUSD",
        canonical_events=canonical_events,
        mapped_events=mapped,
        current_selected=current_selected,
        canonical_selected=canonical_selected,
    )
    assert summary["baseline_parity_pass"] is False
    assert summary["unmapped_event_rows_total"] == 1
    assert len(mismatches) == 1


def test_baseline_gate_allows_modest_selection_drift_without_unmapped_events() -> None:
    passed, reasons = _baseline_gate(
        {
            "baseline_selected_rows_canonical": 1000,
            "baseline_selected_rows_offset0": 960,
            "unmapped_event_rows_total": 0,
        }
    )
    assert passed is True
    assert reasons == ""


def test_baseline_gate_blocks_unmapped_or_large_row_drift() -> None:
    passed, reasons = _baseline_gate(
        {
            "baseline_selected_rows_canonical": 1000,
            "baseline_selected_rows_offset0": 760,
            "unmapped_event_rows_total": 5,
        }
    )
    assert passed is False
    assert reasons == "unmapped_event_rows,selected_rows_delta_gt_20pct"


def test_classify_offset_row_treats_overlap_and_state_coverage_as_diagnostics_only() -> None:
    status, degrade_reasons, diagnostic_reasons = _classify_offset_row(
        {
            "selected_rows_delta_pct": 1.5,
            "trade_rows_delta_pct": -2.0,
            "lb95_trade_mean_gross_pips_delta": -0.05,
            "lb95_trade_mean_net_pips_delta": -0.04,
            "canonical_state_coverage_rate": 0.88,
            "candidate_uid_close_ts_overlap_rate": 0.35,
        }
    )
    assert status == "ok"
    assert degrade_reasons == ""
    assert diagnostic_reasons == "canonical_state_coverage_lt_90pct,selected_overlap_lt_0.60"


def test_classify_offset_row_keeps_material_performance_drops_as_degraded() -> None:
    status, degrade_reasons, diagnostic_reasons = _classify_offset_row(
        {
            "selected_rows_delta_pct": 1.5,
            "trade_rows_delta_pct": -2.0,
            "lb95_trade_mean_gross_pips_delta": -0.30,
            "lb95_trade_mean_net_pips_delta": -0.31,
            "canonical_state_coverage_rate": 1.0,
            "candidate_uid_close_ts_overlap_rate": 1.0,
        }
    )
    assert status == "degraded"
    assert degrade_reasons == "lb95_trade_mean_gross_drop,lb95_trade_mean_net_drop"
    assert diagnostic_reasons == ""


def test_load_canonical_selected_falls_back_when_optional_event_id_columns_missing(
    tmp_path,
) -> None:
    pred_path = tmp_path / "pred.parquet"
    schedule_path = tmp_path / "schedule.csv"
    pd.DataFrame(
        [
            {
                "candidate_uid": "oco|EURUSD|100|h5|s1",
                "close_ts": "2025-07-01T00:00:01Z",
                "selected_exec": 1,
                "test_month": "2025-07",
            },
        ]
    ).to_parquet(pred_path, index=False)
    pd.DataFrame(
        [
            {"test_month": "2025-07", "state_id": "s1", "bar_ticks": 100, "horizon": 5},
        ]
    ).to_csv(schedule_path, index=False)
    canonical_events = pd.DataFrame(
        [
            {
                "candidate_uid": "oco|EURUSD|100|h5|s1",
                "test_month": "2025-07",
                "event_ordinal": 0,
                "frozen_event_id": "2025-07|oco|EURUSD|100|h5|s1|0",
                "canonical_close_ts": pd.Timestamp("2025-07-01T00:00:01Z"),
            }
        ]
    )
    out = _load_canonical_selected(pred_path, schedule_path, canonical_events)
    assert len(out) == 1
    assert out.iloc[0]["event_ordinal"] == 0


def test_load_canonical_selected_uses_scored_row_id_when_present(tmp_path) -> None:
    pred_path = tmp_path / "pred.parquet"
    schedule_path = tmp_path / "schedule.csv"
    pd.DataFrame(
        [
            {
                "candidate_uid": "oco|EURUSD|100|h5|s1",
                "close_ts": "2025-07-01T00:00:09Z",
                "selected_exec": 1,
                "test_month": "2025-07",
                "event_ordinal": 0,
                "scored_row_id": "2025-07|oco|EURUSD|100|h5|s1|0",
            },
        ]
    ).to_parquet(pred_path, index=False)
    pd.DataFrame(
        [
            {"test_month": "2025-07", "state_id": "s1", "bar_ticks": 100, "horizon": 5},
        ]
    ).to_csv(schedule_path, index=False)
    canonical_events = pd.DataFrame(
        [
            {
                "candidate_uid": "oco|EURUSD|100|h5|s1",
                "test_month": "2025-07",
                "event_ordinal": 0,
                "frozen_event_id": "2025-07|oco|EURUSD|100|h5|s1|0",
                "canonical_close_ts": pd.Timestamp("2025-07-01T00:00:01Z"),
            }
        ]
    )
    out = _load_canonical_selected(pred_path, schedule_path, canonical_events)
    assert len(out) == 1
    assert out.iloc[0]["frozen_event_id"] == "2025-07|oco|EURUSD|100|h5|s1|0"


def test_frozen_event_window_matches_canonical_hist_start() -> None:
    start_ts, end_ts_excl = _frozen_event_window(
        {
            "eval_start_month": "2025-01",
            "eval_end_month": "2026-02",
            "rolling_train_months": 3,
        }
    )
    assert start_ts == pd.Timestamp("2024-10-01T00:00:00Z")
    assert end_ts_excl == pd.Timestamp("2026-03-01T00:00:00Z")


def test_load_canonical_event_universe_falls_back_without_optional_id_columns(tmp_path) -> None:
    events_path = tmp_path / "events.parquet"
    pred_path = tmp_path / "pred.parquet"
    pd.DataFrame(
        [
            {
                "candidate_uid": "oco|EURUSD|100|h5|s1",
                "close_ts": "2025-07-01T00:00:01Z",
                "library": "oco",
                "target_gross_pips": 1.0,
                "target_gross_pos": 1,
            }
        ]
    ).to_parquet(events_path, index=False)
    pd.DataFrame(
        [
            {
                "candidate_uid": "oco|EURUSD|100|h5|s1",
                "close_ts": "2025-07-01T00:00:01Z",
                "test_month": "2025-07",
            }
        ]
    ).to_parquet(pred_path, index=False)
    out = _load_canonical_event_universe(events_path, pred_path)
    assert len(out) == 1
    assert out.iloc[0]["frozen_event_id"] == "2025-07|oco|EURUSD|100|h5|s1|0"


def test_cleanup_completed_symbol_artifacts_removes_stage_roots_and_offset_bars(tmp_path) -> None:
    out_dir = tmp_path / "out"
    offset_bar_dir = tmp_path / "bars"
    symbol = "EURUSD"
    offsets = [0, 10]
    for offset in offsets:
        stage_root = out_dir / "runs" / symbol / f"offset_{offset:03d}"
        (stage_root / "wfo").mkdir(parents=True, exist_ok=True)
        (stage_root / "wfo" / "dummy.txt").write_text("x", encoding="utf-8")
        for bar_ticks in [100, 1000, 2000]:
            path = offset_bar_dir / f"{symbol}_{bar_ticks}tick_offset_{offset:03d}.parquet"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("x", encoding="utf-8")
    _cleanup_completed_symbol_artifacts(
        symbol=symbol,
        offsets=offsets,
        offset_bar_dir=offset_bar_dir,
        out_dir=out_dir,
        bar_ticks_grid=[100, 1000, 2000],
    )
    for offset in offsets:
        assert not (out_dir / "runs" / symbol / f"offset_{offset:03d}").exists()
        for bar_ticks in [100, 1000, 2000]:
            assert not (
                offset_bar_dir / f"{symbol}_{bar_ticks}tick_offset_{offset:03d}.parquet"
            ).exists()
