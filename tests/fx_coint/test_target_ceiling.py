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
    splits = purged_embargo_splits(n, t1, n_splits=4, embargo=5)
    assert len(splits) == 3          # forward-chaining -> n_splits-1 usable folds
    for tr, te in splits:
        assert tr.max() < te.min()   # train strictly before test
        # no train label leaks into [test_start - 0, test_end + embargo]
        gap_ok = t1[tr] < te.min()
        assert gap_ok.all()
