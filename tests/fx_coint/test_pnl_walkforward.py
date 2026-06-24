import numpy as np

from scripts.fx_coint.pnl_walkforward import greedy_nonoverlap


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
