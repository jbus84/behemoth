import numpy as np
import pandas as pd

from scripts.era_scalp.temporal_robustness import (
    is_temporally_robust,
    temporal_robustness_verdict,
)


def _frame(month_means, n_per_month=60, seed=0):
    """Build a (net, test_month) frame: each month's trades ~ Normal(mean, 1.0)."""
    rng = np.random.default_rng(seed)
    nets, months = [], []
    for i, m in enumerate(month_means):
        nets.append(rng.normal(m, 1.0, n_per_month))
        months.extend([f"2024-{i + 1:02d}"] * n_per_month)
    return pd.DataFrame({"net": np.concatenate(nets), "test_month": np.array(months)})


def test_insufficient_windows():
    v = temporal_robustness_verdict(_frame([1.0, 1.0]), num_warmup=150, num_samples=150, num_chains=1)
    assert v["status"] == "insufficient_windows"
    assert not is_temporally_robust(v)


def test_consistent_positive_edge_is_robust():
    v = temporal_robustness_verdict(_frame([0.8, 0.9, 1.0, 0.85, 0.95, 0.9]),
                                    num_warmup=300, num_samples=300, num_chains=1)
    assert v["status"] == "ok"
    assert v["p_positive"] > 0.85
    assert v["worst_window_p_positive"] > 0.5
    assert is_temporally_robust(v)


def test_lumpy_edge_flagged_not_robust():
    # one strong month, the rest slightly negative -> positive-ish mu but a weak worst window
    v = temporal_robustness_verdict(_frame([12.0, -0.4, -0.4, -0.4, -0.4, -0.4]),
                                    num_warmup=300, num_samples=300, num_chains=1)
    assert v["status"] == "ok"
    assert v["worst_window_p_positive"] < 0.5     # weakest window not reliably positive
    assert not is_temporally_robust(v)


def test_lumpy_has_higher_dispersion_than_consistent():
    cons = temporal_robustness_verdict(_frame([0.8, 0.8, 0.8, 0.8, 0.8, 0.8], seed=2),
                                       num_warmup=400, num_samples=400, num_chains=1)
    lumpy = temporal_robustness_verdict(_frame([0.5, 1.1, 0.5, 1.1, 0.5, 1.1], seed=2),
                                        num_warmup=400, num_samples=400, num_chains=1)
    assert lumpy["tau_mean"] > cons["tau_mean"]


def test_deterministic_same_seed():
    f = _frame([0.5, 0.6, 0.7, 0.4], seed=3)
    a = temporal_robustness_verdict(f, seed=7, num_warmup=200, num_samples=200, num_chains=1)
    b = temporal_robustness_verdict(f, seed=7, num_warmup=200, num_samples=200, num_chains=1)
    assert abs(a["p_positive"] - b["p_positive"]) < 1e-9
