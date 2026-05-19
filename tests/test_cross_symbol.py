from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from scripts.cross_symbol import CROSS_SYMBOLS, _USD_SIGN


def test_cross_symbols_roster_is_the_six_majors():
    assert CROSS_SYMBOLS == [
        "EURUSD", "GBPUSD", "AUDUSD", "USDJPY", "USDCAD", "USDCHF",
    ]


def test_usd_sign_table_orients_to_usd_strength():
    # USD as quote currency -> a price rise means USD weakness -> sign -1.
    assert _USD_SIGN["EURUSD"] == -1
    assert _USD_SIGN["GBPUSD"] == -1
    assert _USD_SIGN["AUDUSD"] == -1
    # USD as base currency -> a price rise means USD strength -> sign +1.
    assert _USD_SIGN["USDJPY"] == 1
    assert _USD_SIGN["USDCAD"] == 1
    assert _USD_SIGN["USDCHF"] == 1
    # Every roster symbol has a sign.
    assert set(_USD_SIGN) == set(CROSS_SYMBOLS)


def _mk_frame(close_ts: list[str], ret_z: list[float]) -> pd.DataFrame:
    """A minimal prepared-frame stand-in: close_ts + ret_z only."""
    return pd.DataFrame({
        "close_ts": pd.to_datetime(close_ts, utc=True),
        "ret_z": np.asarray(ret_z, dtype=float),
    })


def test_align_peer_returns_takes_most_recent_completed_peer_bar():
    from scripts.cross_symbol import _align_peer_returns

    # Target bars at :00, :02, :04. Peer bars at :01, :03 (between them).
    target = _mk_frame(
        ["2024-01-01T00:00:00Z", "2024-01-01T00:02:00Z", "2024-01-01T00:04:00Z"],
        [0.0, 0.0, 0.0],
    )
    # USDJPY peer, sign +1: USD-aligned ret_z == raw ret_z.
    peer = _mk_frame(
        ["2024-01-01T00:01:00Z", "2024-01-01T00:03:00Z"], [2.0, 5.0],
    )
    out = _align_peer_returns(target, {"USDJPY": peer})
    col = out["xs_ret_z__USDJPY"].to_numpy()
    # Target :00 -> no peer bar <= :00 yet -> NaN.
    assert np.isnan(col[0])
    # Target :02 -> last peer bar <= :02 is :01 (ret_z 2.0).
    assert col[1] == 2.0
    # Target :04 -> last peer bar <= :04 is :03 (ret_z 5.0).
    assert col[2] == 5.0


def test_align_peer_returns_applies_usd_sign():
    from scripts.cross_symbol import _align_peer_returns

    target = _mk_frame(["2024-01-01T00:05:00Z"], [0.0])
    peer = _mk_frame(["2024-01-01T00:00:00Z"], [3.0])
    # EURUSD peer has sign -1 -> USD-aligned column is negated.
    out = _align_peer_returns(target, {"EURUSD": peer})
    assert out["xs_ret_z__EURUSD"].to_numpy()[0] == -3.0


def test_align_peer_returns_is_free_of_look_ahead():
    from scripts.cross_symbol import _align_peer_returns

    target = _mk_frame(
        ["2024-01-01T00:00:00Z", "2024-01-01T00:02:00Z"], [0.0, 0.0],
    )
    peer_a = _mk_frame(["2024-01-01T00:01:00Z"], [1.0])
    # peer_b adds a FUTURE bar at :09 that must not leak into earlier rows.
    peer_b = _mk_frame(
        ["2024-01-01T00:01:00Z", "2024-01-01T00:09:00Z"], [1.0, 99.0],
    )
    out_a = _align_peer_returns(target, {"USDJPY": peer_a})
    out_b = _align_peer_returns(target, {"USDJPY": peer_b})
    # The future :09 bar changes nothing for target bars at :00 and :02.
    assert np.array_equal(
        np.nan_to_num(out_a["xs_ret_z__USDJPY"].to_numpy(), nan=-1.0),
        np.nan_to_num(out_b["xs_ret_z__USDJPY"].to_numpy(), nan=-1.0),
    )


def test_market_measures_all6_and_loo():
    from scripts.cross_symbol import _add_market_measures, _align_peer_returns

    # One target bar; five peers each with a known USD-aligned return.
    target = _mk_frame(["2024-01-01T01:00:00Z"], [6.0])  # target ret_z = 6.0
    peers = {
        "GBPUSD": _mk_frame(["2024-01-01T00:00:00Z"], [-1.0]),
        "AUDUSD": _mk_frame(["2024-01-01T00:00:00Z"], [-2.0]),
        "USDJPY": _mk_frame(["2024-01-01T00:00:00Z"], [1.0]),
        "USDCAD": _mk_frame(["2024-01-01T00:00:00Z"], [2.0]),
        "USDCHF": _mk_frame(["2024-01-01T00:00:00Z"], [3.0]),
    }
    aligned = _align_peer_returns(target, peers)
    out = _add_market_measures(aligned, "EURUSD")
    # USD-aligned peer values: GBP +1, AUD +2 (sign -1 on raw -1,-2),
    # JPY +1, CAD +2, CHF +3 -> peer sum 9, mean 1.8.
    assert out["mkt_loo"].to_numpy()[0] == pytest.approx(1.8)
    # Target EURUSD USD-aligned = -1 * 6.0 = -6.0. all6 = (-6+9)/6 = 0.5.
    assert out["mkt_all6"].to_numpy()[0] == pytest.approx(0.5)


def test_market_measures_loo_ignores_target_returns():
    from scripts.cross_symbol import _add_market_measures, _align_peer_returns

    peers = {
        "GBPUSD": _mk_frame(["2024-01-01T00:00:00Z"], [1.0]),
        "AUDUSD": _mk_frame(["2024-01-01T00:00:00Z"], [1.0]),
        "USDJPY": _mk_frame(["2024-01-01T00:00:00Z"], [1.0]),
        "USDCAD": _mk_frame(["2024-01-01T00:00:00Z"], [1.0]),
        "USDCHF": _mk_frame(["2024-01-01T00:00:00Z"], [1.0]),
    }
    a = _add_market_measures(
        _align_peer_returns(_mk_frame(["2024-01-01T01:00:00Z"], [0.0]),
                            peers), "EURUSD")
    b = _add_market_measures(
        _align_peer_returns(_mk_frame(["2024-01-01T01:00:00Z"], [999.0]),
                            peers), "EURUSD")
    # mkt_loo excludes the target, so the target's own ret_z cannot move it.
    assert a["mkt_loo"].to_numpy()[0] == b["mkt_loo"].to_numpy()[0]


def test_rolling_pca_factor_uses_only_trailing_bars():
    from scripts.cross_symbol import _rolling_pca_factor

    rng = np.random.default_rng(11)
    base = rng.normal(size=(600, 6))
    # mat_b is identical to mat_a for the first 400 rows, perturbed after.
    mat_a = base.copy()
    mat_b = base.copy()
    mat_b[400:] += 50.0
    fac_a = _rolling_pca_factor(mat_a, window=200, min_periods=100)
    fac_b = _rolling_pca_factor(mat_b, window=200, min_periods=100)
    # The factor at row i fits PC1 on rows < i only, so altering rows >= 400
    # cannot change the factor for rows < 400.
    assert np.allclose(
        np.nan_to_num(fac_a[:400], nan=0.0),
        np.nan_to_num(fac_b[:400], nan=0.0),
    )


def test_rolling_pca_factor_nan_before_min_periods():
    from scripts.cross_symbol import _rolling_pca_factor

    rng = np.random.default_rng(3)
    mat = rng.normal(size=(300, 6))
    fac = _rolling_pca_factor(mat, window=200, min_periods=100)
    # Rows with fewer than min_periods trailing bars get NaN.
    assert np.isnan(fac[:100]).all()
    assert np.isfinite(fac[150])


def test_rolling_pca_factor_sign_is_oriented_to_usd_strength():
    from scripts.cross_symbol import _rolling_pca_factor

    # All 6 series move together (a shared USD factor). PC1 then loads all
    # series with the same sign; the orientation rule makes the factor track
    # that common move rather than its arbitrary negation.
    rng = np.random.default_rng(7)
    common = rng.normal(size=(500, 1))
    mat = common + 0.05 * rng.normal(size=(500, 6))
    fac = _rolling_pca_factor(mat, window=200, min_periods=100)
    common_flat = common[:, 0]
    valid = np.isfinite(fac)
    corr = np.corrcoef(fac[valid], common_flat[valid])[0, 1]
    assert corr > 0.9


def test_add_market_measures_includes_distinct_mkt_pca():
    from scripts.cross_symbol import _add_market_measures, _align_peer_returns

    # Build a 500-bar target + 5 peers with distinct, correlated series so
    # the three measures are genuinely different.
    rng = np.random.default_rng(19)
    n = 500
    ts = pd.date_range("2024-01-01", periods=n, freq="min", tz="UTC")
    common = rng.normal(size=n)

    def _frame(scale: float) -> pd.DataFrame:
        return pd.DataFrame({
            "close_ts": ts,
            "ret_z": common * scale + 0.1 * rng.normal(size=n),
        })

    target = _frame(1.0)
    peers = {
        "GBPUSD": _frame(1.1), "AUDUSD": _frame(0.9),
        "USDJPY": _frame(1.2), "USDCAD": _frame(0.8),
        "USDCHF": _frame(1.05),
    }
    aligned = _align_peer_returns(target, peers)
    out = _add_market_measures(aligned, "EURUSD")
    for col in ("mkt_all6", "mkt_loo", "mkt_pca"):
        assert col in out.columns
    a = out["mkt_all6"].to_numpy()
    p = out["mkt_pca"].to_numpy()
    fin = np.isfinite(a) & np.isfinite(p)
    assert fin.sum() > 0
    # mkt_pca is a distinct series, not a copy of mkt_all6.
    assert not np.allclose(a[fin], p[fin])


def test_build_cross_symbol_frame_end_to_end(tmp_path: Path):
    from tests.test_tick_opportunity_mining import _build_synth_tick_velocity

    from scripts.cross_symbol import CROSS_SYMBOLS, build_cross_symbol_frame

    dataset_dir = tmp_path / "tick_velocity"
    dataset_dir.mkdir(parents=True, exist_ok=True)
    for sym in CROSS_SYMBOLS:
        _build_synth_tick_velocity(
            dataset_dir / f"{sym}_1000tick_velocity.parquet", symbol=sym,
        )
    out = build_cross_symbol_frame(
        target_symbol="EURUSD",
        bar_ticks=1000,
        dataset_dir=dataset_dir,
        horizons=[1, 2, 3],
    )
    assert not out.empty
    # The target's own OHLC survives unchanged.
    for col in ("close_bid", "close_ask", "close_ts"):
        assert col in out.columns
    # One peer column per non-target symbol.
    for sym in CROSS_SYMBOLS:
        if sym != "EURUSD":
            assert f"xs_ret_z__{sym}" in out.columns
    assert "xs_ret_z__EURUSD" not in out.columns  # target is not its own peer
    # All three market measures present.
    for col in ("mkt_all6", "mkt_loo", "mkt_pca"):
        assert col in out.columns
    # The aligned frame is non-empty.
    assert len(out) > 0
    assert np.isfinite(out["mkt_all6"]).any()


def test_build_cross_symbol_frame_requires_all_six_symbols(tmp_path: Path):
    from tests.test_tick_opportunity_mining import _build_synth_tick_velocity

    from scripts.cross_symbol import build_cross_symbol_frame

    dataset_dir = tmp_path / "tick_velocity"
    dataset_dir.mkdir(parents=True, exist_ok=True)
    # Only 5 of the 6 symbols present — USDCHF is missing.
    for sym in ("EURUSD", "GBPUSD", "AUDUSD", "USDJPY", "USDCAD"):
        _build_synth_tick_velocity(
            dataset_dir / f"{sym}_1000tick_velocity.parquet", symbol=sym,
        )
    with pytest.raises(FileNotFoundError, match="USDCHF"):
        build_cross_symbol_frame(
            target_symbol="EURUSD",
            bar_ticks=1000,
            dataset_dir=dataset_dir,
            horizons=[1, 2, 3],
        )


def test_build_cross_symbol_frame_rejects_unknown_target(tmp_path: Path):
    from tests.test_tick_opportunity_mining import _build_synth_tick_velocity

    from scripts.cross_symbol import CROSS_SYMBOLS, build_cross_symbol_frame

    dataset_dir = tmp_path / "tick_velocity"
    dataset_dir.mkdir(parents=True, exist_ok=True)
    for sym in CROSS_SYMBOLS:
        _build_synth_tick_velocity(
            dataset_dir / f"{sym}_1000tick_velocity.parquet", symbol=sym,
        )
    with pytest.raises(ValueError, match="target_symbol"):
        build_cross_symbol_frame(
            target_symbol="NZDUSD",
            bar_ticks=1000,
            dataset_dir=dataset_dir,
            horizons=[1, 2, 3],
        )
