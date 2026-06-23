import numpy as np

from scripts.fx_coint.target_ceiling import lag_embedding, purged_embargo_splits


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
