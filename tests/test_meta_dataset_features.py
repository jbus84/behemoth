import numpy as np
import pandas as pd
import polars as pl
import pytest

from behemoth.core.features import compute_features_at_entry
from behemoth.core.kalman import compute_kalman_states
from behemoth.io.loaders import load_pair_data


def test_load_pair_data_success(tmp_path):
    ts = np.array(
        [np.datetime64("2019-01-01"), np.datetime64("2027-01-01")],
        dtype="datetime64[ns]",
    )
    df_x = pl.DataFrame({"timestamp": ts, "close_X": [1.0, 2.0]})
    df_y = pl.DataFrame({"timestamp": ts, "close_Y": [1.5, 2.5]})

    df_x.write_parquet(tmp_path / "x.parquet")
    df_y.write_parquet(tmp_path / "y.parquet")

    out = load_pair_data(str(tmp_path), "x.parquet", "y.parquet", "close_X", "close_Y")
    assert out is not None
    assert out.shape[0] == 1
    assert "X" in out.columns and "Y" in out.columns


def test_load_pair_data_missing(tmp_path):
    out = load_pair_data(str(tmp_path), "missing_x.parquet", "missing_y.parquet", "close_X", "close_Y")
    assert out is None


def test_compute_kalman_states_len1():
    y = np.array([1.0])
    x = np.array([1.0])
    betas, errors, ret_betas = compute_kalman_states(y, x)
    assert len(betas) == 1
    assert len(errors) == 1
    assert len(ret_betas) == 1


def test_compute_kalman_states_len2():
    y = np.array([1.0, 1.01])
    x = np.array([1.0, 1.02])
    _, _, ret_betas = compute_kalman_states(y, x)
    assert ret_betas[0] == ret_betas[1]


@pytest.mark.parametrize("bar_minutes", [5, 15])
def test_compute_features_at_entry_small(bar_minutes):
    n = 600
    i = 10
    y = np.linspace(1.0, 1.2, n)
    x = np.linspace(1.0, 1.1, n)
    betas = np.zeros(n)
    errors = y - betas * x
    ret_betas = np.zeros(n)
    z_scores = np.linspace(-1.0, 1.0, n)
    ts = np.array([np.datetime64("2020-01-01")] * n, dtype="datetime64[ns]")

    feats = compute_features_at_entry(
        i, y, x, betas, errors, ret_betas, z_scores, ts, bar_minutes=bar_minutes
    )
    assert feats["correlation_500"] == 0.0
    assert feats["trend_strength"] == 0.0
    assert feats["atr_ratio"] == 1.0
    assert feats["entry_atr"] == 0.0
    assert feats["vol_regime"] == 1.0
    assert feats["beta_mismatch"] == 0.0


@pytest.mark.parametrize("bar_minutes", [5, 15])
def test_compute_features_at_entry_large(bar_minutes):
    n = 600
    i = 550
    x = np.linspace(1.0, 2.0, n)
    noise = 0.001 * np.sin(np.linspace(0, 20, n))
    y = 1.1 * x + noise
    betas = np.full(n, 1.1)
    errors = y - betas * x
    ret_betas = np.full(n, 0.9)
    z_scores = np.linspace(-2.0, 2.0, n)
    ts = pd.date_range("2020-01-01", periods=n, freq="min", tz="UTC")

    feats = compute_features_at_entry(
        i, y, x, betas, errors, ret_betas, z_scores, ts, bar_minutes=bar_minutes
    )
    assert feats["correlation_500"] != 0.0
    assert feats["trend_strength"] != 0.0
    assert feats["atr_ratio"] > 0.0
    assert feats["entry_atr"] > 0.0
    assert feats["vol_regime"] > 0.0
    assert feats["beta_mismatch"] != 0.0
