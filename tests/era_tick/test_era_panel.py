from __future__ import annotations

import numpy as np

from scripts.era_tick.era_panel import FEATURE_NAMES, panel_from_replay
from scripts.era_tick.tick_replay import TickReplay
from tests.era_tick._synthetic import make_frame, oscillation


def _panel(mids):
    return panel_from_replay(TickReplay("EURUSD", make_frame(mids)), "2024-01-02")


def test_panel_has_all_features_and_is_finite():
    df = _panel(oscillation(n=1500, seed=1))
    assert list(FEATURE_NAMES) == [c for c in FEATURE_NAMES if c in df.columns]
    assert np.isfinite(df[FEATURE_NAMES].to_numpy()).all()  # warmup NaNs filled with 0
    assert len(df) == 1500


def test_panel_features_are_causal():
    """Perturbing FUTURE ticks must not change PAST panel feature rows."""
    mids = oscillation(n=1200, seed=2)
    base = _panel(mids)
    k = 700

    perturbed = mids.copy()
    perturbed[k + 1 :] += np.linspace(0, 30e-4, len(perturbed) - (k + 1))  # warp the future
    after = _panel(perturbed)

    a = base[FEATURE_NAMES].to_numpy()[: k + 1]
    b = after[FEATURE_NAMES].to_numpy()[: k + 1]
    assert np.allclose(a, b, atol=1e-9), "panel feature depends on future ticks"
