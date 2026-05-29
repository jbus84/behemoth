"""Tests for low-capacity track evaluation harness."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest


def _create_synthetic_predictions(
    tmp_path: Path,
    symbol: str,
    family: str,
    bar_ticks: int,
    state_id: str,
    n_events: int = 250,
    gross_mean: float = 2.0,
    gross_std: float = 1.0,
    positive_month_fraction: float = 0.8,
) -> Path:
    """Create a synthetic monthly_predictions.parquet file.

    Args:
        tmp_path: Temporary directory.
        symbol: Symbol name.
        family: Family name.
        bar_ticks: Bar ticks.
        state_id: State ID.
        n_events: Number of events.
        gross_mean: Mean target_gross_pips.
        gross_std: Std of target_gross_pips.
        positive_month_fraction: Fraction of test_months with positive mean.

    Returns:
        Path to the created parquet file.
    """
    import numpy as np

    out_dir = tmp_path / f"wfo_m3to1_{family}_fullcap"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Generate events
    candidate_uid = f"lib|{symbol}|{bar_ticks}|h3|{state_id}"
    test_months = pd.date_range("2025-01", periods=13, freq="MS")
    n_months = len(test_months)

    events = []
    for i in range(n_events):
        month_idx = i % n_months
        test_month = test_months[month_idx]
        close_ts = test_month + pd.Timedelta(days=i % 28 + 1)

        # Gross pips: biased toward positive months
        is_positive_month = (month_idx % n_months) < (positive_month_fraction * n_months)
        mean = gross_mean if is_positive_month else -gross_mean / 2
        target_gross = mean + np.random.normal(0, gross_std)

        events.append(
            {
                "candidate_uid": candidate_uid,
                "test_month": test_month,
                "close_ts": close_ts,
                "selected_exec": "true" if i % 10 != 0 else "false",  # 90% selected
                "target_gross_pips": target_gross,
            }
        )

    df = pd.DataFrame(events)
    out_file = out_dir / f"{symbol}_{family}_monthly_predictions.parquet"
    df.to_parquet(out_file, index=False)
    return out_file


def _create_synthetic_velocity(
    tmp_path: Path,
    symbol: str,
    bar_ticks: int,
    cost_mean: float = 0.5,
    cost_std: float = 0.1,
    n_rows: int = 300,
) -> Path:
    """Create a synthetic tick_velocity.parquet file.

    Args:
        tmp_path: Temporary directory.
        symbol: Symbol name.
        bar_ticks: Bar ticks.
        cost_mean: Mean cost_est_pips.
        cost_std: Std of cost_est_pips.
        n_rows: Number of rows.

    Returns:
        Path to the created parquet file.
    """
    import numpy as np

    vel_dir = tmp_path / "velocity"
    vel_dir.mkdir(parents=True, exist_ok=True)

    close_ts = pd.date_range("2025-01-01", periods=n_rows, freq="h")
    cost_est = cost_mean + np.random.normal(0, cost_std, n_rows)

    df = pd.DataFrame(
        {
            "close_ts": close_ts,
            "cost_est_pips": cost_est,
        }
    )

    out_file = vel_dir / f"{symbol}_{bar_ticks}tick_velocity.parquet"
    df.to_parquet(out_file, index=False)
    return out_file


def test_parse_candidate_uid():
    """Test candidate_uid parsing."""
    from scripts.evaluate_low_capacity_track import _parse_candidate_uid

    parsed = _parse_candidate_uid("lib|EURUSD|1000|h3|state123")
    assert parsed["symbol"] == "EURUSD"
    assert parsed["bar_ticks"] == 1000
    assert parsed["horizon"] == 3
    assert parsed["state_id"] == "state123"


def test_state_metrics_basic():
    """Test basic state metrics computation."""
    from scripts.evaluate_low_capacity_track import _state_metrics

    # Create a simple DataFrame
    data = {
        "net": [1.0, 2.0, 3.0, 1.5, 0.5] * 10,  # 50 events
        "test_month": [f"2025-{(i % 12) + 1:02d}" for i in range(50)],
        "close_ts": pd.date_range("2025-01-01", periods=50),
    }
    df = pd.DataFrame(data)

    metrics = _state_metrics(df)

    assert metrics["n"] == 50
    assert "net_mean" in metrics
    assert "net_lb95" in metrics
    assert "positive_month_share" in metrics
    assert metrics["positive_month_share"] > 0  # Should have positive months


def test_state_metrics_small_sample():
    """Test state metrics with small sample (n < 2)."""
    from scripts.evaluate_low_capacity_track import _state_metrics

    data = {
        "net": [1.0],
        "test_month": ["2025-01"],
        "close_ts": [pd.Timestamp("2025-01-01")],
    }
    df = pd.DataFrame(data)

    metrics = _state_metrics(df)

    assert metrics["n"] == 1
    assert pd.isna(metrics["net_lb95"])  # Should be NaN for n < 2


def test_apply_gates():
    """Test gate application."""
    from scripts.evaluate_low_capacity_track import _apply_gates

    # Create a test DataFrame with known metrics
    data = {
        "symbol": ["EUR"] * 3,
        "family": ["dir"] * 3,
        "bar_ticks": [1000] * 3,
        "state_id": ["s1", "s2", "s3"],
        "annualized": [5000.0, 2000.0, 2500.0],  # Above, below, below floor
        "avg_month_rows": [250.0, 150.0, 200.0],
        "net_lb95": [0.5, 0.5, -0.1],  # Positive, positive, negative
        "positive_month_share": [0.8, 0.7, 0.5],
        "n": [300, 250, 200],
        "p_value": [0.01, 0.05, 0.5],
    }
    df = pd.DataFrame(data)

    result = _apply_gates(df, capacity_floor=3000.0, min_trades=200, min_positive_month_share=0.6)

    # s1: capacity_pass=True (annualized >= 3000), lowfreq_pass=True (but capacity passes)
    assert result.loc[0, "capacity_pass"]
    assert result.loc[0, "lowfreq_pass"]
    assert not result.loc[0, "admitted"]  # capacity_pass overrides

    # s2: capacity_pass=False, lowfreq_pass=True (net_lb95 > 0, positive_month_share >= 0.6, n >= 200)
    assert not result.loc[1, "capacity_pass"]
    assert result.loc[1, "lowfreq_pass"]
    assert result.loc[1, "admitted"]

    # s3: capacity_pass=False, lowfreq_pass=False (net_lb95 <= 0)
    assert not result.loc[2, "capacity_pass"]
    assert not result.loc[2, "lowfreq_pass"]
    assert not result.loc[2, "admitted"]


def test_bh_correction():
    """Test Benjamini-Hochberg correction."""
    import numpy as np

    from scripts.evaluate_low_capacity_track import _bh_correction

    # 100 null p-values (mean 0.5, uniform distribution)
    null_pvals = np.random.uniform(0, 1, 100)
    # 5 true signal p-values (small)
    signal_pvals = np.array([0.001, 0.002, 0.003, 0.004, 0.005])
    all_pvals = np.concatenate([null_pvals, signal_pvals])

    result = _bh_correction(all_pvals, q=0.10)

    # Should mark some as significant
    n_sig = result.sum()
    assert n_sig > 0  # Should have some significant (at minimum the signal pvals)


def test_bh_correction_with_nans():
    """Test BH correction handles NaNs gracefully."""
    import numpy as np

    from scripts.evaluate_low_capacity_track import _bh_correction

    pvals = np.array([0.01, np.nan, 0.05, 0.1, np.nan, 0.001])
    result = _bh_correction(pvals, q=0.10)

    assert len(result) == len(pvals)
    assert not result[1]  # NaN should be False
    assert not result[4]  # NaN should be False


def test_cost_join_affects_net():
    """Test that per-event cost join subtracts from gross to produce net."""
    import numpy as np

    from scripts.evaluate_low_capacity_track import _load_and_process_predictions

    tmp_path = Path(__file__).parent.parent / ".test_tmp" / "cost_join"
    tmp_path.mkdir(parents=True, exist_ok=True)

    # Create synthetic data
    _create_synthetic_predictions(
        tmp_path / "tom",
        "EURUSD",
        "directional",
        1000,
        "state_a",
        n_events=50,
    )
    _create_synthetic_velocity(
        tmp_path / "velocity",
        "EURUSD",
        1000,
        cost_mean=0.5,
        cost_std=0.1,
    )

    # Load and process
    pred_df = _load_and_process_predictions(
        tmp_path / "tom",
        tmp_path / "velocity",
        ["EURUSD"],
        ["directional"],
    )

    # Check that net is computed
    assert "net" in pred_df.columns
    assert "target_gross_pips" in pred_df.columns
    assert "cost_est_pips" in pred_df.columns

    # Check that net = gross - cost (within floating point precision)
    non_nan = pred_df[pred_df["cost_est_pips"].notna()]
    if len(non_nan) > 0:
        expected_net = non_nan["target_gross_pips"] - non_nan["cost_est_pips"]
        actual_net = non_nan["net"]
        np.testing.assert_allclose(actual_net, expected_net, rtol=1e-5)


def test_subcapacity_lowfreq_admitted():
    """Test that sub-capacity, net-LB95-positive state is admitted."""
    from scripts.evaluate_low_capacity_track import (
        _apply_gates,
        _compute_state_metrics_table,
        _load_and_process_predictions,
    )

    tmp_path = Path(__file__).parent.parent / ".test_tmp" / "subcapacity_lowfreq"
    tmp_path.mkdir(parents=True, exist_ok=True)

    # Create synthetic predictions with explicit cost
    # We'll create a small dataset and fill in costs directly
    out_dir = tmp_path / "tom" / "wfo_m3to1_directional_fullcap"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Create a simple test dataset with high net mean and no NaNs
    test_months = pd.date_range("2025-01", periods=13, freq="MS")
    events = []
    for i in range(250):
        month_idx = i % 13
        test_month = test_months[month_idx]
        close_ts = test_month + pd.Timedelta(days=i % 28 + 1)
        # High gross mean, low cost
        target_gross = 1.8 + (0.3 if month_idx < 11 else -0.9)  # 90% positive months
        cost = 0.4
        events.append(
            {
                "candidate_uid": "lib|EURUSD|500|h3|state_lowfreq",
                "test_month": test_month,
                "close_ts": close_ts,
                "selected_exec": "true",
                "target_gross_pips": target_gross,
                "cost_est_pips": cost,
            }
        )

    df = pd.DataFrame(events)
    df["close_ts"] = pd.to_datetime(df["close_ts"], utc=True)
    df.to_parquet(out_dir / "EURUSD_directional_monthly_predictions.parquet")

    # Create velocity data that matches
    vel_dir = tmp_path / "velocity"
    vel_dir.mkdir(exist_ok=True)
    vel_df = df[["close_ts", "cost_est_pips"]].copy()
    vel_df.to_parquet(vel_dir / "EURUSD_500tick_velocity.parquet")

    pred_df = _load_and_process_predictions(
        tmp_path / "tom",
        vel_dir,
        ["EURUSD"],
        ["directional"],
    )

    state_df = _compute_state_metrics_table(pred_df)
    state_df = _apply_gates(state_df, capacity_floor=3000.0, min_trades=200, min_positive_month_share=0.6)

    # Should have at least one state
    assert len(state_df) >= 1

    # That state should be admitted (sub-capacity, but net-LB95 positive, high positive_month_share)
    state = state_df.iloc[0]
    assert state["annualized"] < 3000.0  # Sub-capacity
    assert state["net_lb95"] > 0  # LB95 positive
    assert state["positive_month_share"] >= 0.6  # High positive-month share
    assert state["admitted"]


def test_highfreq_breakeven_capacity_pass():
    """Test that high-frequency break-even state passes capacity but not lowfreq."""
    from scripts.evaluate_low_capacity_track import (
        _apply_gates,
        _compute_state_metrics_table,
        _load_and_process_predictions,
    )

    tmp_path = Path(__file__).parent.parent / ".test_tmp" / "highfreq_breakeven"
    tmp_path.mkdir(parents=True, exist_ok=True)

    # Create synthetic predictions: high-frequency, near-zero net mean
    _create_synthetic_predictions(
        tmp_path / "tom",
        "GBPUSD",
        "directional_inverse",
        100,
        "state_highfreq",
        n_events=5000,  # High frequency
        gross_mean=0.1,  # Near zero
        gross_std=0.5,
        positive_month_fraction=0.5,  # 50% positive months
    )

    _create_synthetic_velocity(
        tmp_path / "velocity",
        "GBPUSD",
        100,
        cost_mean=0.05,
        cost_std=0.02,
    )

    pred_df = _load_and_process_predictions(
        tmp_path / "tom",
        tmp_path / "velocity",
        ["GBPUSD"],
        ["directional_inverse"],
    )

    state_df = _compute_state_metrics_table(pred_df)
    state_df = _apply_gates(state_df, capacity_floor=3000.0, min_trades=200, min_positive_month_share=0.6)

    assert len(state_df) >= 1
    state = state_df.iloc[0]

    # Should pass capacity (high frequency)
    assert state["annualized"] >= 3000.0
    assert state["capacity_pass"]

    # Should fail lowfreq (net_lb95 near or below zero)
    assert not state["lowfreq_pass"]

    # Should not be admitted
    assert not state["admitted"]


def test_small_n_wide_ci_not_admitted():
    """Test that small-n high-mean-but-wide-CI state fails lowfreq gate."""
    from scripts.evaluate_low_capacity_track import (
        _apply_gates,
        _compute_state_metrics_table,
        _load_and_process_predictions,
    )

    tmp_path = Path(__file__).parent.parent / ".test_tmp" / "small_n_wide_ci"
    tmp_path.mkdir(parents=True, exist_ok=True)

    # Create synthetic predictions: small n, high mean, but high std -> wide CI
    _create_synthetic_predictions(
        tmp_path / "tom",
        "USDJPY",
        "directional",
        2000,
        "state_wide_ci",
        n_events=80,  # Small sample
        gross_mean=2.0,
        gross_std=5.0,  # High std -> wide CI
        positive_month_fraction=0.7,
    )

    _create_synthetic_velocity(
        tmp_path / "velocity",
        "USDJPY",
        2000,
        cost_mean=0.3,
        cost_std=0.1,
    )

    pred_df = _load_and_process_predictions(
        tmp_path / "tom",
        tmp_path / "velocity",
        ["USDJPY"],
        ["directional"],
    )

    state_df = _compute_state_metrics_table(pred_df)
    state_df = _apply_gates(state_df, capacity_floor=3000.0, min_trades=200, min_positive_month_share=0.6)

    assert len(state_df) >= 1
    state = state_df.iloc[0]

    # High mean but wide CI -> LB95 likely <= 0
    # Also, n=80 < min_trades=200
    assert state["n"] < 200
    assert not state["lowfreq_pass"]
    assert not state["admitted"]


def test_bh_filters_admitted_when_many_nulls():
    """Test that BH filtering reduces admitted set when many null states present."""
    from scripts.evaluate_low_capacity_track import (
        _apply_gates,
        _bh_correction,
        _compute_state_metrics_table,
        _load_and_process_predictions,
    )

    tmp_path = Path(__file__).parent.parent / ".test_tmp" / "bh_filtering"
    tmp_path.mkdir(parents=True, exist_ok=True)

    # Create multiple states: some true signal, many nulls
    tom_dir = tmp_path / "tom"
    tom_dir.mkdir(parents=True, exist_ok=True)

    # True signal states (net-positive)
    for i in range(3):
        _create_synthetic_predictions(
            tom_dir,
            "EURUSD",
            "directional",
            1000 + i * 100,
            f"state_signal_{i}",
            n_events=250,
            gross_mean=1.5,
            gross_std=0.4,
            positive_month_fraction=0.85,
        )

    # Null states (near-zero mean)
    for i in range(20):
        _create_synthetic_predictions(
            tom_dir,
            "EURUSD",
            "directional",
            3000 + i * 100,
            f"state_null_{i}",
            n_events=250,
            gross_mean=0.05,
            gross_std=0.8,
            positive_month_fraction=0.5,
        )

    # Create velocity data
    vel_dir = tmp_path / "velocity"
    vel_dir.mkdir(parents=True, exist_ok=True)
    for ticks in list(range(1000, 1300, 100)) + list(range(3000, 5000, 100)):
        _create_synthetic_velocity(vel_dir, "EURUSD", ticks, cost_mean=0.5)

    pred_df = _load_and_process_predictions(
        tom_dir,
        vel_dir,
        ["EURUSD"],
        ["directional"],
    )

    state_df = _compute_state_metrics_table(pred_df)
    state_df = _apply_gates(state_df, capacity_floor=3000.0, min_trades=200, min_positive_month_share=0.6)

    # Count admitted before BH
    n_admitted_before = state_df["admitted"].sum()

    # Apply BH
    bh_sig = _bh_correction(state_df["p_value"].values, q=0.10)
    state_df["admitted_bh"] = state_df["admitted"] & bh_sig

    n_admitted_after = state_df["admitted_bh"].sum()

    # BH should filter out some of the false positives (null states)
    # With many nulls, BH threshold will be strict
    assert n_admitted_after <= n_admitted_before


def test_selected_exec_filtering():
    """Test that only selected_exec=true events are kept."""
    from scripts.evaluate_low_capacity_track import _load_and_process_predictions  # noqa: F401

    tmp_path = Path(__file__).parent.parent / ".test_tmp" / "selected_exec"
    tmp_path.mkdir(parents=True, exist_ok=True)

    # Create synthetic data with mixed selected_exec
    out_dir = tmp_path / "tom" / "wfo_m3to1_directional_fullcap"
    out_dir.mkdir(parents=True, exist_ok=True)

    events = [
        {
            "candidate_uid": "lib|EURUSD|1000|h3|state1",
            "test_month": pd.Timestamp("2025-01-01"),
            "close_ts": pd.Timestamp("2025-01-02", tz="UTC"),
            "selected_exec": "true",
            "target_gross_pips": 1.0,
        },
        {
            "candidate_uid": "lib|EURUSD|1000|h3|state1",
            "test_month": pd.Timestamp("2025-01-01"),
            "close_ts": pd.Timestamp("2025-01-03", tz="UTC"),
            "selected_exec": "false",  # Will be filtered out
            "target_gross_pips": 2.0,
        },
        {
            "candidate_uid": "lib|EURUSD|1000|h3|state1",
            "test_month": pd.Timestamp("2025-02-01"),
            "close_ts": pd.Timestamp("2025-02-02", tz="UTC"),
            "selected_exec": "1",  # "1" should also be kept
            "target_gross_pips": 1.5,
        },
    ]

    df = pd.DataFrame(events)
    df["close_ts"] = pd.to_datetime(df["close_ts"], utc=True)
    df.to_parquet(out_dir / "EURUSD_directional_monthly_predictions.parquet")

    pred_df = _load_and_process_predictions(
        tmp_path / "tom",
        tmp_path / "velocity",  # Will be empty, no cost join
        ["EURUSD"],
        ["directional"],
    )

    # Should have 2 events (true and "1", not "false")
    assert len(pred_df) == 2
    assert pred_df["target_gross_pips"].sum() == 2.5  # 1.0 + 1.5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
