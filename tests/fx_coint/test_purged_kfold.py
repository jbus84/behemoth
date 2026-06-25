import numpy as np
from sklearn.linear_model import Ridge

from scripts.fx_coint.purged_kfold import PurgedKFold, ic_scorer, purged_cv_score


def test_purged_kfold_no_train_label_overlaps_test_interval():
    n = 500
    entry = np.arange(n) * 2            # entries at bars 0,2,4,...
    t1 = entry + 5                       # each label spans 5 bars
    pk = PurgedKFold(n_splits=5, embargo_pct=0.0)
    for tr, te in pk.split(entry, t1):
        t_lo, t_hi = entry[te].min(), t1[te].max()
        # no train label interval may intersect [t_lo, t_hi]
        overlap = (entry[tr] <= t_hi) & (t1[tr] >= t_lo)
        assert not overlap.any()


def test_purged_kfold_embargo_drops_post_test_rows():
    n = 500
    entry = np.arange(n)
    t1 = entry + 1
    no_emb = PurgedKFold(n_splits=5, embargo_pct=0.0)
    emb = PurgedKFold(n_splits=5, embargo_pct=0.05)
    # embargo can only REMOVE train rows -> train sets are subsets / smaller
    for (tr0, te0), (tr1, te1) in zip(no_emb.split(entry, t1), emb.split(entry, t1)):
        assert np.array_equal(te0, te1)
        assert len(tr1) <= len(tr0)
    # at least one fold actually loses rows to the embargo
    sizes0 = [len(tr) for tr, _ in no_emb.split(entry, t1)]
    sizes1 = [len(tr) for tr, _ in emb.split(entry, t1)]
    assert any(s1 < s0 for s0, s1 in zip(sizes0, sizes1))


def test_purged_kfold_covers_all_events_as_test_once():
    n = 300
    entry = np.arange(n)
    t1 = entry + 3
    pk = PurgedKFold(n_splits=6, embargo_pct=0.0)
    seen = np.concatenate([te for _, te in pk.split(entry, t1)])
    assert np.array_equal(np.sort(seen), np.arange(n))


def test_ic_scorer_basic():
    y = np.arange(100.0)
    assert ic_scorer(y, y) > 0.99
    assert abs(ic_scorer(y, np.random.default_rng(0).standard_normal(100))) < 0.3


def test_purged_cv_score_recovers_linear_signal():
    rng = np.random.default_rng(0)
    n = 2000
    X = rng.standard_normal((n, 3))
    y = X[:, 0] * 1.5 + 0.3 * rng.standard_normal(n)
    entry = np.arange(n)
    t1 = entry + 2
    scores = purged_cv_score(Ridge(alpha=1.0), X, y, entry, t1, n_splits=5)
    assert np.nanmean(scores) > 0.5
    assert len(scores) == 5
