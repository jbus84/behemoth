"""Contract tests for microstructure regime mining.

All signals must be causal (no look-ahead).
New regimes must be additive (existing regimes unaffected).
Regime thresholds must be train-derived quantiles, not test-derived.

The `tick_burst_score`, `quote_revision_rate_z` and `vol_cluster_score`
regimes use a train-derived q70 cut — consistent with the cost/range/vel
regimes — so each selects a stable ~top-30% of bars across symbols and
volatility regimes. `directional_persistence_8` keeps a fixed +/-6 cut: it
is a bounded integer count over 8 bars, so the threshold is interpretable
and distribution-independent.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.build_tick_velocity_dataset import _build_symbol_dataset
from scripts.run_tick_opportunity_mining import (
    _mine_frame_pair,
    _quantiles,
    _regime_masks,
)


def _mine(
    train: pd.DataFrame,
    test: pd.DataFrame,
    families: list[str],
    *,
    horizons: str = "6",
    barriers: str = "2.0",
) -> dict[str, pd.DataFrame]:
    """Mine candidate frames for a (train, test) pair via the family registry.

    Replaces the removed `_oco_candidates` / `_directional_candidates`
    entrypoints; `_mine_frame_pair` is the post-refactor seam that both
    `run()` and these contract tests share.
    """
    rows, _fill_rows = _mine_frame_pair(
        train=train,
        test=test,
        symbol="EURUSD",
        bar_ticks=1000,
        cfg={"horizons": horizons, "barrier_grid_pips": barriers},
        family_names=families,
        baseline_seed=12345,
        baseline_draws=20,
        min_annual_fills=50.0,
        prescreen_min_train_entries=0,
    )
    return {fam: pd.DataFrame(fam_rows) for fam, fam_rows in rows.items()}

MICRO_REGIMES = [
    "high_intensity",
    "high_activity",
    "persistent_flow",
    "negative_flow",
    "high_vol_cluster",
]


def _build_oco_semantics_frame(rows: int = 4000, seed: int = 1) -> pd.DataFrame:
    """Build a synthetic velocity frame rich enough to mine candidates."""
    rng = np.random.default_rng(seed)
    ts = pd.date_range("2026-01-01", periods=rows, freq="1min", tz="UTC")
    base = 1.1000 + np.arange(rows) * 0.00025 + rng.normal(0.0, 0.0001, rows)
    open_bid = np.r_[base[0], base[:-1]]
    close_bid = base
    high_bid = base + rng.uniform(0.0001, 0.0010, rows)
    low_bid = base - rng.uniform(0.0001, 0.0010, rows)
    high_ask = base + rng.uniform(0.0002, 0.0012, rows)
    close_ask = base + 0.0002

    pip = 0.0001
    out = pd.DataFrame(
        {
            "timestamp": ts,
            "close_ts": ts,
            "open_bid": open_bid,
            "close_bid": close_bid,
            "high_bid": high_bid,
            "low_bid": low_bid,
            "high_ask": high_ask,
            "close_ask": close_ask,
            "cost_est_pips": rng.uniform(0.1, 0.5, rows),
            "range_pips": (high_bid - low_bid) / pip,
            "hour_utc": ts.hour.astype(int),
            "spread_z": rng.normal(0, 1, rows),
            "tick_rate_z": rng.normal(0, 1, rows),
            "vel_cost_units_h1": rng.normal(0, 1, rows),
            "vel_abs_cost_units_h1": np.abs(rng.normal(0, 1, rows)),
            "ret1_pips": (close_bid - open_bid) / pip,
            "ret_z": rng.normal(0, 1, rows),
            "ret_abs_z": np.abs(rng.normal(0, 1, rows)),
            "hl_first": rng.choice([1.0, -1.0, 0.0], size=rows),
            "hl_first_mean_24": rng.normal(0, 0.25, rows),
            "hl_pos_frac_mean_24": rng.uniform(0, 1, rows),
            "tick_burst_score": rng.normal(0, 1, rows),
            "quote_revision_rate_z": rng.normal(0, 1, rows),
            "directional_persistence_8": rng.integers(-8, 9, size=rows).astype(float),
            "signed_flow_24": rng.integers(-24, 25, size=rows).astype(float),
            "vol_cluster_score": rng.exponential(1.0, rows) + 0.5,
            "session_marker": rng.choice(
                ["london", "ny", "ny_overlap", "asia", "rollover"], size=rows
            ),
        }
    )
    # Causal signals use shift(1); first value is undefined before fillna
    out.loc[0, "tick_burst_score"] = np.nan

    # Forward-return targets required by directional mining
    for h in [1, 2, 3, 4, 5, 6]:
        out[f"y_fwd_pips_h{h}"] = (
            (out["close_bid"].shift(-h) - out["open_bid"].shift(-1)) / pip
        ).astype(float)

    return out


def _build_bars_frame(seed: int = 1, n: int = 60) -> pd.DataFrame:
    """Build a synthetic tick-bar frame for the velocity-dataset builder."""
    rng = np.random.default_rng(seed)
    ts = pd.date_range("2026-01-01", periods=n, freq="1min", tz="UTC")
    close_bid = 1.1000 + np.cumsum(rng.normal(0.0, 0.0003, n))
    open_bid = np.r_[close_bid[0], close_bid[:-1]]
    return pd.DataFrame(
        {
            "timestamp": ts,
            "close_ts": ts,
            "open_bid": open_bid,
            "close_bid": close_bid,
            "high_bid": close_bid + rng.uniform(0.0001, 0.0008, n),
            "low_bid": close_bid - rng.uniform(0.0001, 0.0008, n),
            "high_ask": close_bid + rng.uniform(0.0003, 0.0010, n),
            "close_ask": close_bid + 0.0002,
            "spread": rng.uniform(0.00015, 0.00025, n),
            "tick_volume": rng.integers(60, 160, n).astype(float),
            "bar_return_sign": rng.choice([1.0, -1.0, 0.0], size=n),
            "tick_burst": rng.integers(60, 160, n).astype(float),
            "quote_revisions": rng.integers(0, 15, n).astype(float),
            "intra_bar_momentum": rng.normal(0, 0.5, n),
            "range_pips": rng.uniform(2.0, 9.0, n),
            "ret1_pips": (close_bid - open_bid) / 0.0001,
        }
    )


def test_microstructure_signals_are_causal(tmp_path):
    """Perturbing a future bar must not change any microstructure signal at an
    earlier bar. This exercises the real velocity builder, so it fails if any
    signal drops its .shift(1) lag and reaches into future bars."""
    perturb_idx = 40
    signal_cols = [
        "tick_burst_score",
        "quote_revision_rate_z",
        "directional_persistence_8",
        "signed_flow_24",
        "vol_cluster_score",
    ]
    kwargs = dict(
        symbol="EURUSD",
        bar_ticks=100,
        vel_horizons=[1],
        target_horizons=[1],
        vol_window=24,
        cost_window=24,
    )

    bars = _build_bars_frame(seed=7)
    base_path = tmp_path / "base.parquet"
    bars.to_parquet(base_path, index=False)
    out_base = _build_symbol_dataset(bar_path=base_path, **kwargs)

    # Perturb every input that feeds a microstructure signal, from perturb_idx on.
    perturbed = bars.copy()
    perturbed.loc[perturb_idx:, "tick_burst"] *= 5.0
    perturbed.loc[perturb_idx:, "quote_revisions"] += 50.0
    perturbed.loc[perturb_idx:, "bar_return_sign"] *= -1.0
    perturbed.loc[perturb_idx:, "close_bid"] += 0.0050
    pert_path = tmp_path / "perturbed.parquet"
    perturbed.to_parquet(pert_path, index=False)
    out_pert = _build_symbol_dataset(bar_path=pert_path, **kwargs)

    assert len(out_base) == len(out_pert)
    assert len(out_base) >= perturb_idx
    for col in signal_cols:
        pd.testing.assert_series_equal(
            out_base[col].iloc[:perturb_idx].reset_index(drop=True),
            out_pert[col].iloc[:perturb_idx].reset_index(drop=True),
            check_names=False,
            obj=f"{col} before the perturbed bar",
        )


def test_regime_thresholds_are_train_derived():
    """The microstructure regime thresholds must come from train quantiles,
    never from the frame the mask is applied to. Built with a test frame whose
    signal distribution is shifted far above train: a train-derived q70 admits
    most test bars, a test-derived q70 would admit only ~30%."""
    train = _build_oco_semantics_frame(rows=2000, seed=8)
    test = _build_oco_semantics_frame(rows=2000, seed=9)
    # Shift the test frame's microstructure signals well above the train frame.
    test["tick_burst_score"] = test["tick_burst_score"] + 5.0
    test["quote_revision_rate_z"] = test["quote_revision_rate_z"] + 5.0
    test["vol_cluster_score"] = test["vol_cluster_score"] + 5.0

    train_q = _quantiles(train)
    masks = dict(_regime_masks(test, train_q))

    # Each mask equals the test signal compared against the *train* q70.
    np.testing.assert_array_equal(
        masks["high_intensity"],
        (test["tick_burst_score"].to_numpy() >= train_q["tick_burst_q70"]),
    )
    np.testing.assert_array_equal(
        masks["high_vol_cluster"],
        (test["vol_cluster_score"].to_numpy() >= train_q["vol_cluster_q70"]),
    )
    # Train-derived threshold admits far more shifted-up test bars than a
    # test-derived q70 would — proving the threshold is not recomputed on test.
    test_q70 = float(test["tick_burst_score"].quantile(0.70))
    assert train_q["tick_burst_q70"] < test_q70
    assert masks["high_intensity"].mean() > 0.70


def test_high_intensity_regime_is_a_train_q70_subset():
    """high_intensity must select the ~top-30% of bars by tick_burst_score
    (train q70 cut) and be a strict subset of the 'all' regime."""
    train = _build_oco_semantics_frame(rows=4000, seed=3)
    q = _quantiles(train)
    masks = dict(_regime_masks(train, q))

    expected = train["tick_burst_score"].to_numpy() >= q["tick_burst_q70"]
    np.testing.assert_array_equal(masks["high_intensity"], expected)

    # A q70 cut keeps ~30% of bars: strictly fewer than 'all', clearly non-empty.
    selected = masks["high_intensity"].mean()
    assert 0.20 < selected < 0.40
    assert (masks["high_intensity"] <= masks["all"]).all()


def test_directional_persistence_regimes_stay_fixed():
    """persistent_flow / negative_flow keep a fixed +/-6 cut on the bounded
    directional_persistence_8 count — they must not become quantile-based."""
    train = _build_oco_semantics_frame(rows=4000, seed=12)
    q = _quantiles(train)
    masks = dict(_regime_masks(train, q))
    persist = train["directional_persistence_8"].to_numpy()
    np.testing.assert_array_equal(masks["persistent_flow"], persist >= 6)
    np.testing.assert_array_equal(masks["negative_flow"], persist <= -6)


def test_new_regimes_are_additive():
    """New microstructure regimes must produce extra rows; existing regimes unchanged."""
    train = _build_oco_semantics_frame(rows=4000, seed=1)
    test = _build_oco_semantics_frame(rows=4000, seed=2)
    out = _mine(train, test, ["oco_first_touch"])["oco_first_touch"]
    regimes = set(out["regime_desc"].str.split(";").str[0])
    assert "all" in regimes, "baseline 'all' regime must still be present"
    assert set(MICRO_REGIMES) <= regimes, f"missing: {set(MICRO_REGIMES) - regimes}"
    for r in MICRO_REGIMES:
        count = (out["regime_desc"].str.startswith(r)).sum()
        assert count > 0, f"regime {r} produced zero candidates"


def test_microstructure_candidate_quality_vs_baseline():
    """Every new regime must mine a finite train mean gross that can be
    compared against the 'all' baseline. The spec's >=60%-beats-baseline
    success criterion is validated on real data by
    scripts/run_microstructure_diagnostics.py; synthetic random signals
    cannot prove it, so this test verifies the comparison is well-formed."""
    train = _build_oco_semantics_frame(rows=4000, seed=4)
    test = _build_oco_semantics_frame(rows=4000, seed=5)
    out = _mine(train, test, ["oco_first_touch"])["oco_first_touch"]
    out = out.assign(regime=out["regime_desc"].str.split(";").str[0])
    baseline = out.loc[out["regime"] == "all", "mean_gross_pips_train"].mean()
    assert np.isfinite(baseline), "baseline 'all' regime has no train mean gross"

    for r in MICRO_REGIMES:
        regime_rows = out.loc[out["regime"] == r, "mean_gross_pips_train"]
        assert len(regime_rows) > 0, f"regime {r} produced no candidates"
        assert regime_rows.notna().all(), f"regime {r} has a NaN train mean gross"
        delta = float(regime_rows.mean() - baseline)
        assert np.isfinite(delta), f"regime {r} delta-vs-baseline is not finite"


def test_directional_and_oco_both_mine_new_regimes():
    """Both OCO and directional libraries must produce candidates for each new regime."""
    train = _build_oco_semantics_frame(rows=4000, seed=6)
    test = _build_oco_semantics_frame(rows=4000, seed=7)

    mined = _mine(train, test, ["oco_first_touch", "directional"])
    oco = mined["oco_first_touch"]
    directional = mined["directional"]
    for lib, out in [("oco", oco), ("directional", directional)]:
        regimes = set(out["regime_desc"].str.split(";").str[0])
        for r in ["high_intensity", "persistent_flow", "high_vol_cluster"]:
            assert r in regimes, f"{lib} missing regime {r}"
