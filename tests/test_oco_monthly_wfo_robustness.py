from __future__ import annotations

import math

from scripts.analyze_oco_monthly_wfo_robustness import _max_survivable_cost_lb95_trade


def test_max_survivable_cost_lb95_trade_interpolates_crossing() -> None:
    max_cost, status, lo_c, hi_c, lo_y, hi_y = _max_survivable_cost_lb95_trade(
        stress_levels=[0.10, 0.20, 0.30, 0.50],
        stress_lb95=[0.35, 0.10, -0.10, -0.30],
    )
    assert status == "crossing_interpolated"
    assert abs(max_cost - 0.25) < 1e-9
    assert lo_c == 0.20
    assert hi_c == 0.30
    assert lo_y == 0.10
    assert hi_y == -0.10


def test_max_survivable_cost_lb95_trade_all_positive_returns_grid_max() -> None:
    max_cost, status, lo_c, hi_c, lo_y, hi_y = _max_survivable_cost_lb95_trade(
        stress_levels=[0.10, 0.20, 0.30, 0.50],
        stress_lb95=[0.60, 0.45, 0.30, 0.05],
    )
    assert status == "no_failure_in_grid"
    assert max_cost == 0.50
    assert lo_c == 0.50
    assert hi_c == 0.50
    assert lo_y == 0.05
    assert hi_y == 0.05


def test_max_survivable_cost_lb95_trade_all_non_positive_returns_zero() -> None:
    max_cost, status, lo_c, hi_c, lo_y, hi_y = _max_survivable_cost_lb95_trade(
        stress_levels=[0.10, 0.20, 0.30, 0.50],
        stress_lb95=[-0.01, -0.05, -0.10, -0.30],
    )
    assert status == "fails_at_zero_or_first_grid"
    assert max_cost == 0.0
    assert lo_c == 0.0
    assert hi_c == 0.10
    assert lo_y == 0.0
    assert hi_y == -0.01


def test_max_survivable_cost_lb95_trade_handles_missing_grid() -> None:
    max_cost, status, lo_c, hi_c, lo_y, hi_y = _max_survivable_cost_lb95_trade(
        stress_levels=[math.nan],
        stress_lb95=[math.nan],
    )
    assert math.isnan(max_cost)
    assert status == "missing_stress_grid"
    assert math.isnan(lo_c)
    assert math.isnan(hi_c)
    assert math.isnan(lo_y)
    assert math.isnan(hi_y)
