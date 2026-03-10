from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from scripts.freeze_oco_historical_governance import _filter_months, _state_universe_for_month


def test_state_universe_for_month_hash_stable_under_row_order(tmp_path: Path) -> None:
    rows = [
        {
            "test_month": "2025-08",
            "symbol": "EURUSD",
            "bar_ticks": 100,
            "horizon": 5,
            "state_id": "s1",
            "family": "oco_first_touch_clean",
            "barrier_pips": 2.0,
            "regime_desc": "r1",
        },
        {
            "test_month": "2025-08",
            "symbol": "EURUSD",
            "bar_ticks": 100,
            "horizon": 6,
            "state_id": "s2",
            "family": "oco_first_touch_clean",
            "barrier_pips": 3.0,
            "regime_desc": "r2",
        },
    ]
    a = pd.DataFrame(rows)
    b = a.iloc[::-1].reset_index(drop=True)
    p1 = tmp_path / "a.csv"
    p2 = tmp_path / "b.csv"
    a.to_csv(p1, index=False)
    b.to_csv(p2, index=False)

    _, h1 = _state_universe_for_month(p1, "EURUSD", "2025-08")
    _, h2 = _state_universe_for_month(p2, "EURUSD", "2025-08")
    assert h1 == h2


def test_state_universe_for_month_requires_rows(tmp_path: Path) -> None:
    p = tmp_path / "states.csv"
    pd.DataFrame(
        [
            {
                "test_month": "2025-07",
                "symbol": "EURUSD",
                "bar_ticks": 100,
                "horizon": 5,
                "state_id": "s1",
                "family": "oco_first_touch_clean",
                "barrier_pips": 2.0,
                "regime_desc": "r1",
            }
        ]
    ).to_csv(p, index=False)

    with pytest.raises(ValueError):
        _state_universe_for_month(p, "EURUSD", "2025-08")


def test_filter_months_applies_explicit_and_bounds() -> None:
    out = _filter_months(
        months=["2025-07", "2025-08", "2025-09", "2025-10"],
        explicit_months=["2025-08", "2025-10"],
        start_month="2025-08",
        end_month="2025-09",
    )
    assert out == ["2025-08"]
