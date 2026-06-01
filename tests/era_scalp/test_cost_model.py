import numpy as np

from scripts.era_scalp.cost_model import COMMISSION_PIPS, SLIPPAGE_PIPS, realistic_cost


def test_realistic_cost_adds_commission_and_slippage():
    spread = np.array([0.3, 0.5, 1.0])
    out = realistic_cost(spread)
    assert np.allclose(out, spread + COMMISSION_PIPS + SLIPPAGE_PIPS)
    assert np.isclose(COMMISSION_PIPS + SLIPPAGE_PIPS, 0.16)


def test_realistic_cost_accepts_list():
    assert np.allclose(realistic_cost([0.4]), np.array([0.4 + 0.16]))
