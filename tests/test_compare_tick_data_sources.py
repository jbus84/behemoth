from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from scripts.compare_tick_data_sources import (
    analyze_symbol_month,
    infer_daily_lag_schedule,
    run,
    trim_to_overlap,
)


def _ticks_for_range(
    start: str,
    periods: int,
    *,
    freq: str = "1min",
    mid_start: float = 1.1000,
    shift_hours: int = 0,
) -> pd.DataFrame:
    ts = pd.date_range(start=start, periods=periods, freq=freq, tz="UTC")
    ts = ts + pd.Timedelta(hours=int(shift_hours))
    mids = mid_start + np.linspace(0.0, 0.0010, periods)
    spreads = np.full(periods, 0.0002)
    out = pd.DataFrame(
        {
            "timestamp": ts,
            "bid": mids - spreads / 2.0,
            "ask": mids + spreads / 2.0,
            "mid": mids,
            "spread": spreads,
            "log_return": np.concatenate([[0.0], np.diff(np.log(mids))]),
        }
    )
    return out


def test_trim_to_overlap_handles_partial_month_window() -> None:
    reference = _ticks_for_range("2018-06-01T00:00:00Z", 10)
    candidate = _ticks_for_range("2018-06-01T00:05:00Z", 10)

    ref_trim, cand_trim = trim_to_overlap(reference, candidate)

    assert len(ref_trim) == 5
    assert len(cand_trim) == 5
    assert ref_trim["timestamp"].min().isoformat() == "2018-06-01T00:05:00+00:00"
    assert cand_trim["timestamp"].max().isoformat() == "2018-06-01T00:09:00+00:00"


def test_infer_daily_lag_schedule_detects_constant_shift() -> None:
    reference = _ticks_for_range("2018-01-03T00:00:00Z", 24 * 60 * 2)
    candidate = reference.copy()
    candidate["timestamp"] = candidate["timestamp"] - pd.Timedelta(hours=5)

    schedule = infer_daily_lag_schedule(
        reference, candidate, max_lag_hours=8, min_overlap_minutes=60
    )

    assert not schedule.empty
    inferred = set(schedule["inferred_lag_hours"].dropna().astype(int).tolist())
    assert inferred == {5}
    assert set(schedule["lag_source"].astype(str).tolist()) == {"inferred"}


def test_infer_daily_lag_schedule_handles_dst_like_shift_change() -> None:
    day1 = _ticks_for_range("2018-03-10T00:00:00Z", 24 * 60)
    day2 = _ticks_for_range("2018-03-11T00:00:00Z", 24 * 60, mid_start=1.2000)
    reference = pd.concat([day1, day2], ignore_index=True)
    candidate = reference.copy()
    first_mask = candidate["timestamp"] < pd.Timestamp("2018-03-11T00:00:00Z")
    candidate.loc[first_mask, "timestamp"] = candidate.loc[first_mask, "timestamp"] - pd.Timedelta(
        hours=5
    )
    candidate.loc[~first_mask, "timestamp"] = candidate.loc[
        ~first_mask, "timestamp"
    ] - pd.Timedelta(hours=4)

    schedule = infer_daily_lag_schedule(
        reference, candidate, max_lag_hours=8, min_overlap_minutes=60
    )

    lag_map = {
        str(row["date_utc"])[:10]: int(row["inferred_lag_hours"])
        for _, row in schedule.dropna(subset=["inferred_lag_hours"]).iterrows()
    }
    assert lag_map["2018-03-10"] == 5
    assert lag_map["2018-03-11"] == 4


def test_analyze_symbol_month_returns_expected_metrics(tmp_path: Path) -> None:
    ref_root = tmp_path / "reference" / "EURUSD"
    cand_root = tmp_path / "candidate" / "EURUSD"
    ref_root.mkdir(parents=True, exist_ok=True)
    cand_root.mkdir(parents=True, exist_ok=True)

    month = "201801"
    reference = _ticks_for_range("2018-01-02T00:00:00Z", 300, freq="1min")
    candidate = reference.copy()
    candidate["timestamp"] = candidate["timestamp"] - pd.Timedelta(hours=5)
    reference.to_parquet(ref_root / f"EURUSD_{month}_ticks.parquet", index=False)
    candidate.to_parquet(cand_root / f"EURUSD_{month}_ticks.parquet", index=False)

    summary, lag_schedule, coverage = analyze_symbol_month(
        symbol="EURUSD",
        month=month,
        reference_path=ref_root / f"EURUSD_{month}_ticks.parquet",
        candidate_path=cand_root / f"EURUSD_{month}_ticks.parquet",
        bar_ticks=100,
        max_lag_hours=8,
        min_overlap_minutes=60,
    )

    assert set(summary["lens"].astype(str)) == {"as_is", "lag_corrected"}
    corrected = summary[summary["lens"].astype(str) == "lag_corrected"].iloc[0]
    assert corrected["candidate_to_reference_row_ratio"] == 1.0
    assert corrected["lag_schedule_mode_hours"] == 5
    assert corrected["minute_return_corr"] > 0.99
    assert corrected["reference_bar_count"] == 3
    assert corrected["candidate_bar_count"] == 3
    assert not lag_schedule.empty
    assert not coverage.empty


def test_run_skips_missing_pairs_and_writes_outputs(tmp_path: Path) -> None:
    reference_root = tmp_path / "dukascopy"
    candidate_root = tmp_path / "tick"
    out_dir = tmp_path / "out"
    report_out = tmp_path / "report.md"
    symbol = "EURUSD"
    month_present = "201801"
    month_missing = "201802"

    ref_dir = reference_root / symbol
    cand_dir = candidate_root / symbol
    ref_dir.mkdir(parents=True, exist_ok=True)
    cand_dir.mkdir(parents=True, exist_ok=True)

    reference = _ticks_for_range("2018-01-02T00:00:00Z", 240)
    candidate = reference.copy()
    candidate["timestamp"] = candidate["timestamp"] - pd.Timedelta(hours=5)
    reference.to_parquet(ref_dir / f"{symbol}_{month_present}_ticks.parquet", index=False)
    candidate.to_parquet(cand_dir / f"{symbol}_{month_present}_ticks.parquet", index=False)

    summary, lag_schedule, coverage = run(
        reference_root=reference_root,
        candidate_root=candidate_root,
        symbols=[symbol],
        months=[month_present, month_missing],
        bar_ticks=100,
        max_lag_hours=8,
        out_dir=out_dir,
        report_out=report_out,
        min_overlap_minutes=60,
    )

    assert set(summary["month"].astype(str)) == {month_present, "OVERALL"}
    assert not lag_schedule.empty
    assert not coverage.empty
    assert (out_dir / "tick_source_similarity_summary.csv").exists()
    assert (out_dir / "tick_source_similarity_lag_schedule.csv").exists()
    assert (out_dir / "tick_source_similarity_hourly_coverage.csv").exists()
    assert report_out.exists()
