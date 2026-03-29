from __future__ import annotations

import pandas as pd

from scripts.run_offset_tickbar_robustness import (
    _choose_refine_centers,
    _classification,
    _cleanup_symbol_stage_roots,
    _coarse_offsets,
    _offsets_for_api_and_warmup,
    _offsets_to_retain,
    _pct_delta,
    _refined_offsets,
    _selected_overlap_rate,
    _state_overlap_rows,
)


def test_pct_delta_handles_zero_baseline() -> None:
    assert _pct_delta(0, 0) == 0.0
    assert _pct_delta(10, 0) == float("inf")


def test_state_overlap_rows_and_selected_overlap_rate() -> None:
    baseline_states = pd.DataFrame(
        [
            {"test_month": "2025-07", "state_key": "a|100|5"},
            {"test_month": "2025-07", "state_key": "b|100|6"},
        ]
    )
    current_states = pd.DataFrame(
        [
            {"test_month": "2025-07", "state_key": "a|100|5"},
            {"test_month": "2025-07", "state_key": "c|100|6"},
        ]
    )
    rows, overall = _state_overlap_rows(
        symbol="EURUSD",
        offset=25,
        baseline_states=baseline_states,
        current_states=current_states,
    )
    assert len(rows) == 2
    assert overall == 1 / 3

    baseline_sel = pd.DataFrame(
        [
            {"candidate_uid": "u1", "close_ts": "2025-07-07T00:00:00Z"},
            {"candidate_uid": "u2", "close_ts": "2025-07-07T00:01:00Z"},
        ]
    )
    current_sel = pd.DataFrame(
        [
            {"candidate_uid": "u1", "close_ts": "2025-07-07T00:00:00Z"},
            {"candidate_uid": "u3", "close_ts": "2025-07-07T00:02:00Z"},
        ]
    )
    assert _selected_overlap_rate(baseline_sel, current_sel) == 0.5


def test_classification_escalates_for_api_fail_and_plateau_gap() -> None:
    by_offset = pd.DataFrame(
        [
            {"offset_status": "ok"},
            {"offset_status": "degraded"},
        ]
    )
    api_df = pd.DataFrame([{"api_confirmation_status": "fail"}])
    warmup_df = pd.DataFrame([{"plateau_warmup_bars": pd.NA}])
    assert _classification(by_offset, api_df, warmup_df) == "materially_phase_sensitive"


def test_adaptive_offset_selection_helpers() -> None:
    all_offsets = list(range(10))
    coarse = _coarse_offsets(all_offsets, [0, 3, 6, 9])
    assert coarse == [0, 3, 6, 9]

    by_offset = pd.DataFrame(
        [
            {
                "offset": 0,
                "offset_status": "ok",
                "degrade_reasons": "",
                "lb95_trade_mean_gross_pips_delta": 0.0,
                "selected_rows_delta_pct": 0.0,
            },
            {
                "offset": 3,
                "offset_status": "degraded",
                "degrade_reasons": "lb95_trade_mean_gross_drop",
                "lb95_trade_mean_gross_pips_delta": -0.4,
                "selected_rows_delta_pct": 5.0,
            },
            {
                "offset": 6,
                "offset_status": "degraded",
                "degrade_reasons": "selected_rows_delta_gt_20pct",
                "lb95_trade_mean_gross_pips_delta": -0.1,
                "selected_rows_delta_pct": 25.0,
            },
        ]
    )
    centers = _choose_refine_centers(by_offset_df=by_offset, max_centers=1)
    assert centers == [3]
    refined = _refined_offsets(
        all_offsets=all_offsets, coarse_offsets=coarse, centers=centers, radius=2
    )
    assert refined == [1, 2, 4, 5]


def test_api_and_retention_offsets() -> None:
    completed = [0, 1, 2, 3, 4, 5]
    flagged = [3]
    assert _offsets_for_api_and_warmup(
        completed_offsets=completed, flagged_centers=flagged, api_confirm_offsets=[0, 25, 50]
    ) == [0, 3]
    assert _offsets_to_retain(
        completed_offsets=completed, flagged_centers=flagged, retain_flagged_offset_runs=True
    ) == [0, 3]
    assert (
        _offsets_to_retain(
            completed_offsets=completed, flagged_centers=flagged, retain_flagged_offset_runs=False
        )
        == []
    )


def test_cleanup_symbol_stage_roots_removes_unkept_offsets(tmp_path) -> None:
    out_dir = tmp_path / "study"
    for off in [0, 1, 2]:
        stage_root = out_dir / "runs" / "EURUSD" / f"offset_{off:03d}"
        stage_root.mkdir(parents=True)
        (stage_root / "marker.txt").write_text("x", encoding="utf-8")

    _cleanup_symbol_stage_roots(
        out_dir=out_dir,
        symbol="EURUSD",
        completed_offsets=[0, 1, 2],
        keep_offsets=[0, 2],
    )

    assert (out_dir / "runs" / "EURUSD" / "offset_000").exists()
    assert not (out_dir / "runs" / "EURUSD" / "offset_001").exists()
    assert (out_dir / "runs" / "EURUSD" / "offset_002").exists()
