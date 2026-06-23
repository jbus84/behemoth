import numpy as np

from scripts.fx_coint.target_ceiling import (
    knn_mi,
    lag_embedding,
    model_lower_bound,
    purged_embargo_splits,
)


def test_lag_embedding_shape_and_nan_warmup():
    r = np.arange(100, dtype=float)
    X = lag_embedding(r, lags=(1, 5, 10))
    assert X.shape == (100, 6)
    assert np.all(np.isnan(X[0]))          # no history at t=0
    assert np.all(np.isfinite(X[20]))      # plenty of history by t=20


def test_lag_embedding_return_column_is_lagged():
    r = np.array([0.0, 1.0, 2.0, 3.0, 4.0, 5.0])
    X = lag_embedding(r, lags=(1,))
    # column 0 = return at t-1
    assert X[3, 0] == 2.0
    assert X[5, 0] == 4.0


def test_purged_embargo_splits_no_leakage():
    n = 1000
    t1 = np.arange(n) + 3            # each label ends 3 bars later
    embargo = 5
    splits = purged_embargo_splits(n, t1, n_splits=4, embargo=embargo)
    assert len(splits) == 3          # forward-chaining -> n_splits-1 usable folds
    for tr, te in splits:
        assert tr.max() < te.min()   # train strictly before test
        # no train label leaks into [test_start - 0, test_end + embargo]
        gap_ok = t1[tr] < te.min()
        assert gap_ok.all()
        # embargo has a real effect: no train label may end within `embargo`
        # bars before the test block start
        assert (t1[tr] < te.min() - embargo).all()


def test_purged_embargo_splits_embargo_is_not_a_noop():
    # With a wider embargo, strictly fewer (or equal) train labels survive than
    # with no embargo -- guards against the embargo parameter being ignored.
    n = 1000
    t1 = np.arange(n) + 3
    none = purged_embargo_splits(n, t1, n_splits=4, embargo=0)
    wide = purged_embargo_splits(n, t1, n_splits=4, embargo=20)
    assert len(none) == len(wide) == 3
    for (tr0, _), (tr1, _) in zip(none, wide, strict=True):
        assert tr1.size < tr0.size   # embargo actually purges more


def test_model_lower_bound_recovers_learnable_signal():
    rng = np.random.default_rng(0)
    n = 3000
    r = rng.standard_normal(n)
    X = lag_embedding(r, lags=(1, 2))
    # target depends on lag-1 return -> learnable from own history
    # y[t] = 0.5 * r[t-1] + 0.3 * r[t-2] + noise
    y = np.zeros(n)
    for t in range(2, n):
        y[t] = 0.5 * r[t-1] + 0.3 * r[t-2] + 0.2 * rng.standard_normal()
    y[:2] = np.nan
    t1 = np.arange(n) + 1
    ic = model_lower_bound(X, y, t1, kind="continuous")
    assert ic > 0.1


def test_model_lower_bound_pure_noise_near_zero():
    rng = np.random.default_rng(1)
    n = 3000
    X = lag_embedding(rng.standard_normal(n), lags=(1, 2))
    y = rng.standard_normal(n)               # independent of X
    t1 = np.arange(n) + 1
    ic = model_lower_bound(X, y, t1, kind="continuous")
    assert abs(ic) < 0.1


def test_knn_mi_detects_dependence():
    rng = np.random.default_rng(2)
    n = 2000
    r = rng.standard_normal(n)
    X = lag_embedding(r, lags=(1,))
    # y_dep[t] = r[t-1] (strong dependence on lag-1)
    y_dep = np.concatenate([[np.nan], r[:-1]])
    y_indep = rng.standard_normal(n)
    mi_dep = knn_mi(X, y_dep, kind="continuous")
    mi_indep = knn_mi(X, y_indep, kind="continuous")
    assert mi_dep > mi_indep
    assert mi_dep > 0.05
