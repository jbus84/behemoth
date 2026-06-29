"""Tests for 4-channel flagging."""
from __future__ import annotations

import numpy as np


def _mock_preds(n: int = 200) -> dict[str, np.ndarray]:
    """Synthetic OOS predictions — NaN for first 100 (train), values for rest."""
    rng = np.random.default_rng(42)
    preds = {
        "mu": np.concatenate([np.full(100, np.nan), rng.normal(0, 2.0, 100)]),
        "sigma": np.concatenate([np.full(100, np.nan), rng.uniform(0.5, 3.0, 100)]),
        "nu": np.concatenate([np.full(100, np.nan), rng.uniform(1.5, 20.0, 100)]),
    }
    return preds


def test_flag_channels_returns_expected_keys():
    from scripts.boostlss_xs.flagging import flag_channels

    preds = _mock_preds()
    y = np.random.default_rng(0).normal(0, 1, 200)
    result = flag_channels(preds, y, "StudentTLSS")
    for key in ["mu_flag", "mu_mag", "sigma_flag", "sigma_mag", "nu_flag", "nu_mag", "direction"]:
        assert key in result, f"missing key: {key}"


def test_mu_flag_fires_on_large_predicted_mu():
    from scripts.boostlss_xs.flagging import flag_channels

    preds = _mock_preds()
    y = np.random.default_rng(0).normal(0, 1, 200)
    # Force a large mu prediction
    preds["mu"][150] = 100.0
    result = flag_channels(preds, y, "StudentTLSS")
    assert result["mu_flag"][150] == 1


def test_mu_flag_zero_for_small_predicted_mu():
    from scripts.boostlss_xs.flagging import flag_channels

    preds = _mock_preds()
    y = np.zeros(200)
    preds["mu"][150] = 0.001  # tiny
    result = flag_channels(preds, y, "StudentTLSS")
    assert result["mu_flag"][150] == 0


def test_nu_flag_student_t_fires_below_5():
    from scripts.boostlss_xs.flagging import flag_channels

    preds = _mock_preds()
    preds["nu"][150] = 2.0  # below threshold of 5
    y = np.ones(200)
    result = flag_channels(preds, y, "StudentTLSS")
    assert result["nu_flag"][150] == 1


def test_nu_flag_gev_fires_on_large_abs_shape():
    from scripts.boostlss_xs.flagging import flag_channels

    preds = _mock_preds()
    preds["nu"][150] = 0.5  # |0.5| > 0.2
    y = np.ones(200)
    result = flag_channels(preds, y, "GEVLSS")
    assert result["nu_flag"][150] == 1


def test_direction_sign_matches_mu():
    from scripts.boostlss_xs.flagging import flag_channels

    preds = _mock_preds()
    preds["mu"][150] = 5.0
    preds["mu"][160] = -5.0
    y = np.ones(200)
    result = flag_channels(preds, y, "StudentTLSS")
    assert result["direction"][150] == 1.0
    assert result["direction"][160] == -1.0


def test_nan_propagated_for_train_rows():
    from scripts.boostlss_xs.flagging import flag_channels

    preds = _mock_preds()
    y = np.ones(200)
    result = flag_channels(preds, y, "StudentTLSS")
    assert np.isnan(result["mu_flag"][:100]).all()


def test_gaussian_no_nu_key_returns_nan_nu_channels():
    from scripts.boostlss_xs.flagging import flag_channels

    rng = np.random.default_rng(42)
    preds = {
        "mu": np.concatenate([np.full(100, np.nan), rng.normal(0, 2.0, 100)]),
        "sigma": np.concatenate([np.full(100, np.nan), rng.uniform(0.5, 3.0, 100)]),
    }
    y = np.ones(200)
    result = flag_channels(preds, y, "GaussianLSS")
    assert np.isnan(result["nu_flag"]).all()
    assert np.isnan(result["nu_mag"]).all()
