import numpy as np

from scripts.era_scalp.bracket_harness import deploy_gate, evaluate_deploy, simulate_bracket


def test_deploy_gate_topq():
    score = np.array([1.0, 2.0, 3.0, 4.0, 5.0, np.nan])
    g = deploy_gate(score, q=0.4)  # top 40% of 5 finite -> top 2: values 4,5
    assert g.tolist() == [False, False, False, True, True, False]


def test_simulate_bracket_oscillation_tp():
    n = 6
    close = np.array([1.1000, 1.1000, 1.0996, 1.1000, 1.1000, 1.1000])
    high = np.array([1.1000, 1.1001, 1.0998, 1.1001, 1.1000, 1.1000])
    low = np.array([1.1000, 1.0999, 1.0995, 1.0998, 1.1000, 1.1000])
    out = simulate_bracket(k=0, close=close, high=high, low=low, spread=np.full(n, 0.3),
                           delta_pips=3.0, stop_pips=3.0, max_hold=4, pip=1e-4,
                           commission_pips=0.07)
    assert out["filled"] and out["side"] == 1
    assert out["exit"] == "tp"
    assert abs(out["net_pips"] - (3.0 - 0.07)) < 1e-6


def test_simulate_bracket_trend_sl():
    n = 6
    close = np.array([1.1000, 1.0996, 1.0990, 1.0985, 1.0980, 1.0975])
    high = np.array([1.1000, 1.0999, 1.0996, 1.0990, 1.0985, 1.0980])
    low = np.array([1.1000, 1.0995, 1.0989, 1.0984, 1.0979, 1.0974])
    out = simulate_bracket(k=0, close=close, high=high, low=low, spread=np.full(n, 0.3),
                           delta_pips=3.0, stop_pips=3.0, max_hold=4, pip=1e-4,
                           commission_pips=0.07)
    assert out["filled"] and out["side"] == 1 and out["exit"] == "sl"
    assert out["net_pips"] < 0


def test_evaluate_deploy_returns_net_frame():
    n = 50
    rng = np.random.default_rng(0)
    close = 1.1 + np.cumsum(rng.standard_normal(n)) * 1e-4
    high = close + 2e-4
    low = close - 2e-4
    score = rng.standard_normal(n)
    df = evaluate_deploy(
        deploy_score=score, close=close, high=high, low=low,
        spread=np.full(n, 0.3), cost=np.full(n, 0.4),
        test_month=np.array(["2024-01"] * n),
        q=0.4, delta_pips=3.0, stop_pips=3.0, max_hold=5, pip=1e-4, commission_pips=0.07,
    )
    assert set(df.columns) == {"net", "test_month"}
