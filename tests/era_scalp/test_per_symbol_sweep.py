import numpy as np
import pandas as pd

from scripts.era_scalp import per_symbol_sweep as pss
from scripts.era_scalp.load_splits import WHITELIST, TradeSplitData


def _split(n=900, seed=0):
    rng = np.random.default_rng(seed)
    mid = 1.10 + np.cumsum(rng.standard_normal(n)) * 1e-4
    months = ([f"2024-{m:02d}" for m in range(1, 13)] * (n // 12 + 1))[:n]
    return TradeSplitData(
        X=rng.standard_normal((n, len(WHITELIST))), names=list(WHITELIST),
        hour=(np.arange(n) % 24).astype(float), mid=mid, cost=np.full(n, 0.4),
        test_month=np.array(months),
    )


def test_dev_signal_runs_and_is_finite_mostly():
    sig = pss.dev_signal(_split())
    assert sig.shape[0] == 900
    assert np.isfinite(sig).any()


def test_directions_are_exact_negations():
    sp = _split()
    sig = pss.dev_signal(sp)
    fade = pss.cell_net(sig, sp, "EURUSD", "fade", q=0.90, h=100)
    cont = pss.cell_net(sig, sp, "EURUSD", "continue", q=0.90, h=100)
    assert len(fade) == len(cont) and len(fade) > 0
    paired = fade["net"].to_numpy() + cont["net"].to_numpy()
    assert np.allclose(paired, -2 * 0.4)


def test_diagnostics_match_hand_values():
    frame = pd.DataFrame({
        "net": [1.0, 3.0, -1.0, -1.0, 2.0],
        "test_month": ["2025-01", "2025-01", "2025-02", "2025-02", "2025-03"],
    })
    d = pss.diagnostics(frame)
    assert d["n_trades"] == 5
    assert d["n_months"] == 3
    assert np.isclose(d["month_hit"], 2 / 3)
    assert np.isclose(d["raw_mean"], (1 + 3 - 1 - 1 + 2) / 5)


def test_diagnostics_empty_frame():
    d = pss.diagnostics(pd.DataFrame({"net": [], "test_month": []}))
    assert d["n_trades"] == 0 and d["n_months"] == 0
    assert d["month_hit"] == 0.0 and np.isnan(d["raw_mean"])
