import numpy as np
import pandas as pd

from scripts.fx_coint.pf_phase1_eval import positive_years, year_block_bootstrap_ci


def test_positive_years_counts_year_means():
    bucket = pd.to_datetime(["2020-01-01", "2020-06-01", "2021-01-01"]).values
    net = np.array([1.0, 1.0, -2.0])
    pos, tot = positive_years(net, bucket)
    assert (pos, tot) == (1, 2)


def test_bootstrap_ci_orders_lo_below_hi():
    rng = np.random.default_rng(0)
    bucket = pd.to_datetime(
        np.repeat(["2019", "2020", "2021", "2022"], 25)).values
    net = rng.normal(0.5, 1.0, size=100)
    lo, hi = year_block_bootstrap_ci(net, bucket, n_boot=500, seed=1)
    assert lo < hi
