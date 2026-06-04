import numpy as np
import pandas as pd

from scripts.era_scalp.cost_aware_score import effective_n_tests


def _series(vals, months):
    return pd.Series(np.asarray(vals, float), index=list(months))


def test_empty_is_one():
    assert effective_n_tests([]) == 1.0


def test_single_series_is_one():
    m = [f"2024-{i:02d}" for i in range(1, 9)]
    assert effective_n_tests([_series(np.arange(8), m)]) == 1.0


def test_identical_series_collapse_toward_one():
    m = [f"2024-{i:02d}" for i in range(1, 9)]
    s = _series([1, 2, 3, 4, 5, 6, 7, 8], m)
    meff = effective_n_tests([s, s.copy(), s.copy(), s.copy()])
    assert meff < 1.2


def test_independent_series_approach_count():
    rng = np.random.default_rng(0)
    months = [f"2024-{i:03d}" for i in range(1, 41)]   # 40 common windows
    k = 6
    series = [_series(rng.standard_normal(40), months) for _ in range(k)]
    meff = effective_n_tests(series)
    assert meff > 0.6 * k


def test_bounded_by_count():
    rng = np.random.default_rng(1)
    months = [f"2024-{i:03d}" for i in range(1, 31)]
    series = [_series(rng.standard_normal(30), months) for _ in range(4)]
    meff = effective_n_tests(series)
    assert 1.0 <= meff <= 4.0
