import numpy as np
import pandas as pd

from scripts.era.harness import task_score


def _df(nets, months):
    return pd.DataFrame({"net": nets, "test_month": months})


def test_warmer_scores_higher():
    good = _df([2.0] * 60 + [1.0] * 60, ["2025-01"] * 60 + ["2025-02"] * 60)
    weak = _df([0.1] * 60 + [-0.1] * 60, ["2025-01"] * 60 + ["2025-02"] * 60)
    assert task_score(good) > task_score(weak)


def test_empty_is_finite_floor():
    s = task_score(_df([], []))
    assert np.isfinite(s) and s < -1e3


def test_more_months_positive_helps():
    a = _df([1.0] * 100, ["2025-01"] * 50 + ["2025-02"] * 50)  # 2/2 months +
    b = _df([1.0] * 50 + [-3.0] * 50, ["2025-01"] * 50 + ["2025-02"] * 50)  # 1/2 months +
    assert task_score(a) > task_score(b)
