import math

import numpy as np

from scripts.era_scalp.deflated_selection import (
    deflated_edge_prob,
    expected_max_sharpe,
    is_significant_after_deflation,
)


def test_expected_max_zero_for_trivial():
    assert expected_max_sharpe(1, 0.3) == 0.0
    assert expected_max_sharpe(50, 0.0) == 0.0


def test_expected_max_grows_with_n():
    a = expected_max_sharpe(5, 0.3)
    b = expected_max_sharpe(50, 0.3)
    c = expected_max_sharpe(1000, 0.3)
    assert c > b > a > 0


def test_noise_winner_not_significant():
    rng = np.random.default_rng(0)
    trials = rng.normal(0, 0.25, 150)           # 150 pure-noise program edges
    winner_mean = float(trials.max())           # the lucky best-of-150
    dsr = deflated_edge_prob(winner_mean, 0.25, trials)
    assert dsr < 0.95
    assert not is_significant_after_deflation(dsr)


def test_genuine_winner_significant():
    rng = np.random.default_rng(1)
    trials = rng.normal(0, 0.25, 150)
    dsr = deflated_edge_prob(2.5, 0.25, trials)  # edge far above the noise envelope
    assert dsr > 0.95
    assert is_significant_after_deflation(dsr)


def test_undefined_with_few_trials_or_bad_se():
    assert math.isnan(deflated_edge_prob(1.0, 0.2, [0.5]))
    assert math.isnan(deflated_edge_prob(1.0, 0.0, [0.1, 0.2, 0.3]))
