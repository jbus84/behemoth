from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from scripts.mining_random_baseline import random_entry_baseline


class _ConstGrossFamily:
    """Test double: measure_gross returns the frame's `g` column."""

    name = "const"

    def measure_gross(
        self, frame: pd.DataFrame, entries: np.ndarray, params: dict[str, Any], *, precomputed: Any = None
    ) -> np.ndarray:
        return frame["g"].to_numpy(dtype=float)[entries]


def _frame(n: int) -> pd.DataFrame:
    return pd.DataFrame({"g": np.arange(n, dtype=float)})


def test_baseline_is_deterministic_under_fixed_seed():
    fam, frame = _ConstGrossFamily(), _frame(1000)
    a = random_entry_baseline(fam, frame, {}, n_entries=50, n_draws=100,
                              rng=np.random.default_rng(7))
    b = random_entry_baseline(fam, frame, {}, n_entries=50, n_draws=100,
                              rng=np.random.default_rng(7))
    assert a["random_baseline_control_mean"] == b["random_baseline_control_mean"]
    assert np.isnan(a["random_baseline_z"]) and np.isnan(b["random_baseline_z"])


def test_baseline_z_positive_for_best_n_entries(monkeypatch):
    fam, frame = _ConstGrossFamily(), _frame(1000)
    # candidate EV = mean of the top-50 g values (the best entries)
    cand_ev = float(np.mean(np.arange(950, 1000, dtype=float)))
    res = random_entry_baseline(fam, frame, {}, n_entries=50, n_draws=200,
                                rng=np.random.default_rng(1),
                                candidate_gross_ev=cand_ev)
    assert res["random_baseline_z"] > 3.0
    assert res["random_baseline_p"] < 0.05


def test_baseline_returns_nan_when_n_entries_exceeds_frame():
    fam, frame = _ConstGrossFamily(), _frame(20)
    res = random_entry_baseline(fam, frame, {}, n_entries=50, n_draws=100,
                                rng=np.random.default_rng(1),
                                candidate_gross_ev=1.0)
    assert np.isnan(res["random_baseline_z"])
    assert np.isnan(res["random_baseline_p"])
    assert np.isnan(res["random_baseline_control_mean"])


def test_baseline_returns_nan_for_zero_entries():
    fam, frame = _ConstGrossFamily(), _frame(100)
    res = random_entry_baseline(fam, frame, {}, n_entries=0, n_draws=100,
                                rng=np.random.default_rng(1),
                                candidate_gross_ev=1.0)
    assert np.isnan(res["random_baseline_z"])
    assert np.isnan(res["random_baseline_p"])
    assert np.isnan(res["random_baseline_control_mean"])


def test_baseline_returns_nan_when_all_gross_are_nan():
    fam = _ConstGrossFamily()
    frame = pd.DataFrame({"g": [np.nan, np.nan, np.nan]})
    res = random_entry_baseline(fam, frame, {}, n_entries=2, n_draws=10,
                                rng=np.random.default_rng(1),
                                candidate_gross_ev=1.0)
    assert np.isnan(res["random_baseline_z"])
    assert np.isnan(res["random_baseline_p"])
    assert np.isnan(res["random_baseline_control_mean"])


def test_baseline_returns_nan_when_control_std_is_zero():
    fam = _ConstGrossFamily()
    frame = pd.DataFrame({"g": [5.0, 5.0, 5.0, 5.0]})
    res = random_entry_baseline(fam, frame, {}, n_entries=2, n_draws=50,
                                rng=np.random.default_rng(1),
                                candidate_gross_ev=5.0)
    assert np.isnan(res["random_baseline_z"])
    assert np.isnan(res["random_baseline_p"])
    assert res["random_baseline_control_mean"] == 5.0
