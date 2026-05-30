import numpy as np

from scripts.era.select import bh_fdr


def test_bh_basic():
    p = np.array([0.001, 0.2, 0.03, 0.8])
    sig = bh_fdr(p, q=0.1)
    assert sig[0] and not sig[3]
    assert sig.dtype == bool and sig.shape == (4,)


def test_bh_all_null():
    assert not bh_fdr(np.array([0.9, 0.8, 0.95]), q=0.1).any()
