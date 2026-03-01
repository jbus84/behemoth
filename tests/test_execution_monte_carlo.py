from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts.run_execution_monte_carlo import run_for_symbol


def _write_detail(path: Path) -> None:
    rows = [
        {
            "close_ts": "2025-01-01 00:00:00+00:00",
            "candidate_uid": "oco|EURUSD|100|h6|x",
            "target_gross_pips": 1.2,
            "bar_ticks": 100,
            "horizon": 6,
            "barrier_pips": 2.0,
            "side": 1,
            "barrier_px": 1.10,
            "touch_open_ts": "2025-01-01 08:00:00+00:00",
            "touch_close_ts": "2025-01-01 08:05:00+00:00",
            "touch_month": 202501,
            "touch_found_tick": 1,
            "overshoot_tick_pips": 0.1,
        },
        {
            "close_ts": "2025-01-02 00:00:00+00:00",
            "candidate_uid": "oco|EURUSD|100|h6|y",
            "target_gross_pips": 0.8,
            "bar_ticks": 100,
            "horizon": 6,
            "barrier_pips": 2.0,
            "side": -1,
            "barrier_px": 1.09,
            "touch_open_ts": "2025-01-02 14:00:00+00:00",
            "touch_close_ts": "2025-01-02 14:05:00+00:00",
            "touch_month": 202501,
            "touch_found_tick": 1,
            "overshoot_tick_pips": 0.2,
        },
        {
            "close_ts": "2025-02-02 00:00:00+00:00",
            "candidate_uid": "oco|EURUSD|100|h6|z",
            "target_gross_pips": -0.4,
            "bar_ticks": 100,
            "horizon": 6,
            "barrier_pips": 2.0,
            "side": 1,
            "barrier_px": 1.08,
            "touch_open_ts": "2025-02-02 22:00:00+00:00",
            "touch_close_ts": "2025-02-02 22:05:00+00:00",
            "touch_month": 202502,
            "touch_found_tick": 1,
            "overshoot_tick_pips": 0.7,
        },
    ]
    pd.DataFrame(rows).to_csv(path, index=False)


def _write_caps(path: Path) -> None:
    pd.DataFrame(
        [
            {
                "symbol": "EURUSD",
                "cap_pips": 0.8,
                "fill_rate": 0.97,
                "mean_gross_filled_no_extra_slip": 1.0,
                "mean_net_filled_full_overshoot": 0.9,
                "mean_per_signal_no_extra_slip": 0.95,
                "mean_per_signal_full_overshoot": 0.85,
            },
            {
                "symbol": "EURUSD",
                "cap_pips": 1.0,
                "fill_rate": 0.99,
                "mean_gross_filled_no_extra_slip": 1.02,
                "mean_net_filled_full_overshoot": 0.92,
                "mean_per_signal_no_extra_slip": 0.97,
                "mean_per_signal_full_overshoot": 0.88,
            },
        ]
    ).to_csv(path, index=False)


def test_run_for_symbol_produces_all_scenarios(tmp_path: Path) -> None:
    detail = tmp_path / "EURUSD_stop_limit_tickfill_detail.csv"
    caps = tmp_path / "EURUSD_stop_limit_tickfill_caps.csv"
    _write_detail(detail)
    _write_caps(caps)

    group_df, month_df, symbol_df = run_for_symbol(
        symbol="EURUSD",
        detail_path=detail,
        caps_path=caps,
        iterations=200,
        seed=123,
    )

    assert not group_df.empty
    assert not month_df.empty
    assert not symbol_df.empty
    assert set(symbol_df["scenario_id"].astype(str).unique().tolist()) == {
        "S0_baseline",
        "S1_mild",
        "S2_moderate",
        "S3_severe",
    }
    assert {"lb95_per_signal_pips", "mean_fill_rate", "prob_negative_month"}.issubset(
        set(symbol_df.columns)
    )
