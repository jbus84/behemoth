import numpy as np

from scripts.fx_coint.purged_kfold import PurgedKFold


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
