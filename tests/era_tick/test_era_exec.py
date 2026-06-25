from __future__ import annotations

import numpy as np

from scripts.era_tick.era_exec import evaluate_full, make_score_frame
from scripts.era_tick.era_panel import DRIFT_CODE, FEATURE_NAMES, TickSplit


def _split(n=4000, n_days=10, pip=1e-4, seed=0):
    """Synthetic multi-day split with a few clean trends per day."""
    rng = np.random.default_rng(seed)
    per = n // n_days
    mid = np.zeros(n)
    price = 1.10
    day = np.empty(n, dtype=object)
    for d in range(n_days):
        sl = slice(d * per, (d + 1) * per)
        # one directional ramp + noise per day -> a rideable trend
        ramp = np.linspace(0, rng.choice([-1, 1]) * 8e-4, per)
        mid[sl] = price + ramp + rng.normal(0, 0.3e-4, per)
        day[sl] = f"2024-01-{d + 1:02d}"
    half = 0.5 * 0.2 * pip
    bid, ask = mid - half, mid + half
    X = np.zeros((n, len(FEATURE_NAMES)))
    reg_i = FEATURE_NAMES.index("regime_code")
    X[:, reg_i] = DRIFT_CODE  # always trending so entries are allowed
    return (
        TickSplit(
            X=X,
            names=list(FEATURE_NAMES),
            hour=np.zeros(n),
            bid=bid,
            ask=ask,
            mid=mid,
            day=day,
            pip=pip,
        ),
        mid,
        day,
    )


def test_cost_identity_gross_minus_net():
    split, mid, _ = _split()
    score = np.sign(np.diff(mid, prepend=mid[0])) * np.arange(len(mid))  # arbitrary conviction
    df = evaluate_full(score, split, q=0.5, h=500)
    assert len(df) > 0
    assert np.allclose(df["gross"] - df["net"], df["cost"], atol=1e-9)
    assert (df["cost"] > 0).all()  # taker always pays the spread


def test_min_days_floor_rejects_concentrated_signal():
    # A signal that only fires on ONE day must be rejected (the mirage guard).
    split, mid, day = _split()
    score = np.zeros(len(mid))
    one_day = day == "2024-01-01"
    score[one_day] = 5.0  # huge conviction, but all on a single day
    sf = make_score_frame(min_trades=1, min_days=8)
    frame = sf(score, split, q=0.5, h=500)
    assert frame.empty, "single-day signal should be floored out as a mirage"


def test_spread_across_days_passes_floor():
    split, mid, _ = _split()
    score = np.sign(np.diff(mid, prepend=mid[0])) * 3.0  # fires every day
    sf = make_score_frame(min_trades=5, min_days=8)
    frame = sf(score, split, q=0.5, h=500)
    assert not frame.empty
    assert set(frame.columns) == {"net", "test_month"}
    assert frame["test_month"].nunique() >= 8
