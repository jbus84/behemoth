import numpy as np

from scripts.era_scalp.trade_harness import (
    evaluate_trades,
    forward_return,
    per_symbol_net,
    pooled_task_score,
)


def test_forward_return_matches_naive():
    mid = np.array([1.0, 1.1, 1.2, 1.3, 1.4])
    pip = 0.1
    fr = forward_return(mid, pip, 2)
    assert np.allclose(fr[:3], [2.0, 2.0, 2.0])
    assert not np.isfinite(fr[3]) and not np.isfinite(fr[4])


def test_evaluate_trades_net_and_gate():
    n = 100
    signal = np.concatenate([np.full(50, 2.0), np.full(50, 0.0)])
    mid = 1.0 + np.arange(n) * 1e-4
    cost = np.full(n, 0.4)
    tm = np.array(["2024-01"] * n)
    df = evaluate_trades(signal, mid, cost, tm, pip=1e-4, q=0.50, h=10)
    assert len(df) > 0
    assert df["net"].mean() > 0


def test_pooled_task_score_concats():
    import pandas as pd

    f1 = pd.DataFrame({"net": np.full(150, 0.5), "test_month": ["2024-01"] * 150})
    f2 = pd.DataFrame({"net": np.full(150, 0.5), "test_month": ["2024-02"] * 150})
    assert pooled_task_score([f1, f2]) > 0


def test_per_symbol_net():
    sigs = {"A": np.array([2.0, 2.0, -2.0, -2.0]), "B": np.array([2.0, 2.0, 2.0, 2.0])}
    mids = {"A": np.array([1.0, 1.001, 1.0, 1.001]), "B": np.array([1.0, 1.0, 1.0, 1.0])}
    costs = {"A": np.full(4, 0.0), "B": np.full(4, 0.0)}
    tms = {"A": np.array(["m"] * 4), "B": np.array(["m"] * 4)}
    out = per_symbol_net(sigs, mids, costs, tms, {"A": 1e-4, "B": 1e-4}, q=0.0, h=1)
    assert set(out) == {"A", "B"}
    assert "n" in out["A"] and "mean_net" in out["A"]
