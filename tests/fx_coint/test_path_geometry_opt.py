from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from scripts.fx_coint.path_geometry_opt import (
    BASELINE_CELL,
    GRID,
    Trade,
    cell_net,
    fold_trades,
    optimize_geometry,
    paired_day_clustered_p,
    positive_years,
    year_block_bootstrap_ci,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_requires_tick_bars = pytest.mark.skipif(
    not (_REPO_ROOT / "data/tick_bars/EURUSD_1m_flow.parquet").exists(),
    reason="requires data/tick_bars/*_1m_flow.parquet (gitignored; absent in CI)",
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


@_requires_tick_bars
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


def test_positive_years():
    bk = pd.to_datetime(["2020-01-01", "2020-06-01", "2021-01-01"]).values
    pos, tot = positive_years(np.array([1.0, 1.0, -2.0]), bk)
    assert (pos, tot) == (1, 2)


def test_bootstrap_ci_order():
    rng = np.random.default_rng(0)
    bk = pd.to_datetime(np.repeat(["2019", "2020", "2021", "2022"], 25)).values
    lo, hi = year_block_bootstrap_ci(rng.normal(0.5, 1, 100), bk, n_boot=400, seed=1)
    assert lo < hi


def test_paired_day_clustered_zero_when_identical():
    bk = pd.to_datetime(np.repeat(pd.date_range("2020-01-01", periods=10), 1)).values
    net = np.arange(10.0)
    base = np.arange(10.0)
    r = paired_day_clustered_p(net, base, bk)
    assert np.isclose(r["mean_diff"], 0.0)


from scripts.fx_coint.path_geometry_opt import prescreen  # noqa: E402


@_requires_tick_bars
def test_prescreen_returns_bool_per_tf_and_2h_true():
    res = prescreen(timeframes=("2h",), pairs=["EURUSD", "GBPUSD", "USDJPY"], seed=0)
    assert set(res.keys()) == {"2h"}
    assert isinstance(res["2h"], bool)
    assert res["2h"] is True  # 2h shifted in Phase A
