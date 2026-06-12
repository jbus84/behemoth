import numpy as np

from scripts.fx_coint.stability import bh_fdr, fraction_stationary


def test_bh_fdr_basic():
    pvals = [0.001, 0.01, 0.2, 0.8]
    keep = bh_fdr(pvals, alpha=0.10)
    assert keep[0] and keep[1]
    assert not keep[3]


def test_bh_fdr_all_null():
    assert bh_fdr([0.9, 0.95, 0.99], alpha=0.10) == [False, False, False]


def test_fraction_stationary_counts_oos_passes():
    # 4 windows, 3 with p<0.05
    pvals = [0.01, 0.02, 0.04, 0.6]
    frac = fraction_stationary(pvals, p_thresh=0.05)
    assert np.isclose(frac, 0.75)
