import numpy as np

from scripts.era_scalp.trade_harness import evaluate_fair_price_trades, evaluate_trades


def test_fill_lag_one_realizes_next_bar_move():
    n = 50
    rng = np.random.default_rng(0)
    rets = rng.standard_normal(n) * 1e-4
    mid = 1.0 + np.cumsum(rets)
    signal = np.ones(n)                      # all long, equal conviction
    cost = np.zeros(n)
    tm = np.array(["2024-01"] * n)
    f0 = evaluate_trades(signal, mid, cost, tm, pip=1e-4, q=0.0, h=1, fill_lag=0)
    f1 = evaluate_trades(signal, mid, cost, tm, pip=1e-4, q=0.0, h=1, fill_lag=1)
    a = f0["net"].to_numpy()
    b = f1["net"].to_numpy()
    assert len(b) <= len(a)                  # one fewer realizable bar
    # decision at t with fill_lag=1 realizes the SAME move as fill_lag=0 at t+1
    assert np.allclose(b[:5], a[1:6], atol=1e-12)


def test_fill_lag_default_unchanged():
    n = 100
    signal = np.concatenate([np.full(50, 2.0), np.full(50, 0.0)])
    mid = 1.0 + np.arange(n) * 1e-4
    cost = np.full(n, 0.4)
    tm = np.array(["2024-01"] * n)
    base = evaluate_trades(signal, mid, cost, tm, pip=1e-4, q=0.50, h=10)
    explicit = evaluate_trades(signal, mid, cost, tm, pip=1e-4, q=0.50, h=10, fill_lag=0)
    assert len(base) == len(explicit)


def test_fair_price_fill_lag_accepted_and_default_unchanged():
    n = 200
    rng = np.random.default_rng(1)
    fair = np.cumsum(rng.standard_normal(n))
    mid = 1.0 + np.cumsum(rng.standard_normal(n)) * 1e-5
    cost = np.zeros(n)
    tm = np.array(["2024-01"] * n)
    base = evaluate_fair_price_trades(fair, mid, cost, tm, pip=1e-4, q=0.9, h=5)
    lagged = evaluate_fair_price_trades(fair, mid, cost, tm, pip=1e-4, q=0.9, h=5, fill_lag=2)
    assert len(lagged) <= len(base)
    explicit0 = evaluate_fair_price_trades(fair, mid, cost, tm, pip=1e-4, q=0.9, h=5, fill_lag=0)
    assert len(base) == len(explicit0)
