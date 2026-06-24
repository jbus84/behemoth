import numpy as np

from scripts.fx_coint.pnl_walkforward import greedy_nonoverlap, train_relative_topdecile


def test_greedy_nonoverlap_excludes_overlapping_holds():
    entry = np.array([0, 1, 5, 6, 12])
    t1 = np.array([4, 5, 9, 10, 14])     # each trade exits at t1
    keep = greedy_nonoverlap(entry, t1)
    # 0 kept (exit 4); 1 starts at 1<4 skip; 5>=4 keep (exit 9); 6<9 skip; 12>=9 keep
    assert keep.tolist() == [True, False, True, False, True]


def test_greedy_nonoverlap_all_disjoint_kept():
    entry = np.array([0, 10, 20])
    t1 = np.array([5, 15, 25])
    assert greedy_nonoverlap(entry, t1).all()


def test_train_relative_topdecile_no_leakage():
    """Selection threshold must be calibrated on train rows only.

    We build 100 train rows with sel_abs/feat_abs drawn from U[0,1] and 10 test
    rows containing extreme values (1000x train scale).  The helper should return
    the same train-row selected fraction whether or not the test extremes are present,
    because the threshold is computed purely from train combined scores.
    """
    rng = np.random.default_rng(42)
    n_train = 100
    n_test = 10

    # train rows: moderate values
    tr_sel = rng.uniform(0, 1, n_train)
    tr_feat = rng.uniform(0, 1, n_train)

    # test rows WITHOUT extremes
    te_sel_normal = rng.uniform(0, 1, n_test)
    te_feat_normal = rng.uniform(0, 1, n_test)

    # test rows WITH extremes (1000× scale — would dominate full-array ranking)
    te_sel_extreme = rng.uniform(900, 1000, n_test)
    te_feat_extreme = rng.uniform(900, 1000, n_test)

    def run(te_sel, te_feat):
        sel_abs = np.concatenate([tr_sel, te_sel])
        feat_abs = np.concatenate([tr_feat, te_feat])
        tr_mask = np.array([True] * n_train + [False] * n_test)
        mask = train_relative_topdecile(sel_abs, feat_abs, tr_mask, q=0.90)
        # fraction of train rows selected
        return mask[:n_train].sum() / n_train

    frac_normal = run(te_sel_normal, te_feat_normal)
    frac_extreme = run(te_sel_extreme, te_feat_extreme)

    # train-selected fraction must be identical regardless of test extremes
    assert frac_normal == frac_extreme, (
        f"Train fraction changed with extreme test values: {frac_normal} vs {frac_extreme} "
        "(look-ahead leakage detected)"
    )
