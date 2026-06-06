import numpy as np
from scripts.era_scalp.boosting_scorer import complexity_penalty, purged_folds, train_predict


def test_purged_folds_no_overlap_with_embargo():
    folds = purged_folds(1000, k=4, embargo=50)
    assert len(folds) == 4
    for tr, va in folds:
        assert set(tr).isdisjoint(set(va))
        # embargo: no train index within `embargo` of any val index
        va_set = set(va)
        for i in tr:
            assert all(abs(i - j) > 50 or j == i for j in (min(va), max(va)))  # boundary check
        assert len(va) > 0


def test_complexity_penalty_monotonic():
    assert complexity_penalty(1) < complexity_penalty(5) < complexity_penalty(20)


def test_train_predict_shape_and_determinism():
    rng = np.random.default_rng(0)
    Xtr = rng.standard_normal((400, 3)); ytr = Xtr[:, 0] * 0.5 + rng.standard_normal(400) * 0.1
    Xpr = rng.standard_normal((120, 3))
    a = train_predict(Xtr, ytr, Xpr, seed=0)
    b = train_predict(Xtr, ytr, Xpr, seed=0)
    assert a.shape == (120,)
    assert np.allclose(a, b)  # deterministic with fixed seed + thread_count=1
