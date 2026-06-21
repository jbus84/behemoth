from scripts.fx_coint.path_geometry_opt import Trade, fold_trades


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
