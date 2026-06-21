import numpy as np

from scripts.fx_coint.path_geometry_opt import (
    BASELINE_CELL,
    GRID,
    Trade,
    cell_net,
    fold_trades,
    optimize_geometry,
)


def _trade(bps_path, sigma=10.0, side="long", cost=0.6):
    entry = 1.0
    mins = entry * np.exp(np.array(bps_path) / 1e4)
    return Trade(entry, mins, side, sigma, np.datetime64("2022-01-03"), cost)


def test_grid_has_baseline_and_20_cells():
    assert BASELINE_CELL in GRID
    assert len(GRID) == 20


def test_cell_net_baseline_equals_terminal():
    trades = [_trade([5, -5, 12], cost=0.6)]
    net = cell_net(trades, BASELINE_CELL)
    assert np.isclose(net[0], 12 - 0.6, atol=1e-6)


def test_optimize_picks_protective_stop_when_it_helps_on_train():
    # train: a few trades with big losers a stop would cut; test mirrors
    losers = [_trade([-50, -60], cost=0.0) for _ in range(5)]
    winners = [_trade([10, 40], cost=0.0) for _ in range(5)]
    folds = [{"train": losers + winners, "test": losers + winners}]
    r = optimize_geometry(folds)
    assert r["net_oos"].mean() >= r["baseline_oos"].mean()  # geometry >= baseline on train-selected cell


def test_fold_trades_structure_and_causality():
    folds = fold_trades("EURUSD", freq="2h", q=0.95, n_folds=5, n_bars=1)
    assert len(folds) >= 3
    total_test = sum(len(f["test"]) for f in folds)
    assert total_test > 30
    for f in folds:
        assert all(isinstance(t, Trade) for t in f["train"] + f["test"])
        # every trade has a non-empty path and positive sigma
        assert all(len(t.minutes) > 0 and t.sigma_bps > 0 for t in f["test"])
        # causal: max train bucket < min test bucket within a fold
        if f["train"] and f["test"]:
            assert max(t.bucket for t in f["train"]) < min(t.bucket for t in f["test"])
