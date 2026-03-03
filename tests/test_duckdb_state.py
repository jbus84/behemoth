#!/usr/bin/env python3
"""TDD tests for the DuckDB-backed tick-bar state manager.

These tests verify that rolling window calculations in DuckDB produce
float-identical results to the equivalent pandas rolling operations in
``scripts/build_tick_velocity_dataset.py``.

The key contract: for any given buffer of N tick bars, the 16 features
emitted by ``StateManager.compute_features()`` must match the pandas
pipeline output to within a strict floating-point tolerance.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from src.behemoth.core.schemas import IncomingTickBar, ModelFeatures

# ── Helpers ───────────────────────────────────────────────────────────

def _make_synthetic_bars(
    symbol: str = "EURUSD",
    bar_ticks: int = 100,
    n: int = 400,
    seed: int = 42,
) -> list[IncomingTickBar]:
    """Generate a deterministic stream of synthetic tick bars for testing."""
    rng = np.random.default_rng(seed)
    base_price = 1.10000
    bars: list[IncomingTickBar] = []
    t = datetime(2025, 6, 1, 8, 0, 0, tzinfo=timezone.utc)
    for _i in range(n):
        move = rng.normal(0, 0.00050)
        o = base_price + move
        h = o + abs(rng.normal(0, 0.00030))
        l = o - abs(rng.normal(0, 0.00030))
        c = o + rng.normal(0, 0.00020)
        spread = abs(rng.normal(0.00012, 0.00003))
        tv = float(bar_ticks)
        dur = rng.uniform(10, 120)
        close_ts = t + timedelta(seconds=dur)
        hl_first_val = rng.choice([-1.0, 0.0, 1.0])
        hl_pos_frac_val = rng.uniform(0.3, 0.7)

        bars.append(IncomingTickBar(
            symbol=symbol,
            bar_ticks=bar_ticks,
            timestamp=t,
            close_ts=close_ts,
            open=round(o, 5),
            high=round(h, 5),
            low=round(l, 5),
            close=round(c, 5),
            spread=round(spread, 6),
            tick_volume=tv,
            hl_first=hl_first_val,
            hl_pos_frac=hl_pos_frac_val,
        ))
        t = close_ts + timedelta(seconds=rng.uniform(0.5, 5.0))
        base_price = round(c, 5)
    return bars


def _pandas_velocity_features(
    bars: list[IncomingTickBar],
    vol_window: int = 96,
    cost_window: int = 288,
) -> pd.DataFrame:
    """
    Reference pandas implementation mirroring build_tick_velocity_dataset.py
    ``_build_symbol_dataset``. Returns a DataFrame with the exact feature columns.
    """
    pip = 0.0001  # EURUSD
    records = []
    for b in bars:
        records.append({
            "timestamp": b.timestamp,
            "close_ts": b.close_ts,
            "open": b.open,
            "high": b.high,
            "low": b.low,
            "close": b.close,
            "spread": b.spread,
            "tick_volume": b.tick_volume,
            "bar_ticks": b.bar_ticks,
            "hl_first": b.hl_first if b.hl_first is not None else np.nan,
            "hl_pos_frac": b.hl_pos_frac if b.hl_pos_frac is not None else np.nan,
        })
    df = pd.DataFrame(records)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df["close_ts"] = pd.to_datetime(df["close_ts"], utc=True)
    df = df.sort_values("close_ts").reset_index(drop=True)

    close = df["close"].astype(float)
    open_ = df["open"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)

    df["hour_utc"] = df["close_ts"].dt.hour.astype(int)
    df["duration_sec"] = (df["close_ts"] - df["timestamp"]).dt.total_seconds().clip(lower=1e-6)
    df["tick_rate_hz"] = df["tick_volume"] / df["duration_sec"]

    tr_mu = df["tick_rate_hz"].rolling(vol_window, min_periods=max(8, vol_window // 3)).mean().shift(1)
    tr_sd = df["tick_rate_hz"].rolling(vol_window, min_periods=max(8, vol_window // 3)).std(ddof=0).shift(1)
    df["tick_rate_z"] = (df["tick_rate_hz"] - tr_mu) / tr_sd.replace(0.0, np.nan)

    df["spread_pips"] = df["spread"] / pip
    df["range_pips"] = (high - low) / pip

    sp_mu = df["spread_pips"].rolling(vol_window, min_periods=max(8, vol_window // 3)).mean().shift(1)
    sp_sd = df["spread_pips"].rolling(vol_window, min_periods=max(8, vol_window // 3)).std(ddof=0).shift(1)
    df["spread_z"] = (df["spread_pips"] - sp_mu) / sp_sd.replace(0.0, np.nan)

    df["vel_pips_h1"] = (close - close.shift(1)) / pip
    df["ret1_pips"] = df["vel_pips_h1"]

    vol_ref = df["vel_pips_h1"].rolling(vol_window, min_periods=max(8, vol_window // 3)).std(ddof=0).shift(1)
    df["ret_z"] = df["vel_pips_h1"] / (vol_ref * np.sqrt(1.0))
    df["ret_abs_z"] = df["vel_pips_h1"].abs() / (vol_ref * np.sqrt(1.0))

    spread_recent = df["spread_pips"].rolling(cost_window, min_periods=max(8, cost_window // 4)).median().shift(1)
    gap_abs = (open_ - close.shift(1)).abs() / pip
    slip_proxy = gap_abs.rolling(cost_window, min_periods=max(8, cost_window // 6)).quantile(0.75).shift(1)
    slip_fallback = df["range_pips"].rolling(cost_window, min_periods=max(8, cost_window // 6)).quantile(0.75).shift(1) * 0.2
    df["slip_proxy_pips"] = slip_proxy.fillna(slip_fallback).fillna(0.1).clip(lower=0.01)
    df["cost_est_pips"] = (
        spread_recent.fillna(df["spread_pips"].shift(1)).fillna(df["spread_pips"].median())
        + df["slip_proxy_pips"]
    )

    df["vel_cost_units_h1"] = df["vel_pips_h1"] / df["cost_est_pips"].replace(0.0, np.nan)
    df["vel_abs_cost_units_h1"] = df["vel_pips_h1"].abs() / df["cost_est_pips"].replace(0.0, np.nan)

    df["hl_first_mean_24"] = df["hl_first"].rolling(24, min_periods=8).mean().shift(1)
    df["hl_pos_frac_mean_24"] = df["hl_pos_frac"].rolling(24, min_periods=8).mean().shift(1)

    df = df.replace([np.inf, -np.inf], np.nan)
    return df


# ── Tests ─────────────────────────────────────────────────────────────

class TestDuckDBStateFeatures:
    """Verify DuckDB state manager produces float-identical features to pandas."""

    @pytest.fixture
    def synthetic_bars(self) -> list[IncomingTickBar]:
        return _make_synthetic_bars(n=400, seed=42)

    @pytest.fixture
    def pandas_reference(self, synthetic_bars: list[IncomingTickBar]) -> pd.DataFrame:
        return _pandas_velocity_features(synthetic_bars)

    def test_pandas_reference_has_expected_columns(self, pandas_reference: pd.DataFrame):
        """Sanity check that the pandas reference generates valid features."""
        for col in ModelFeatures.model_fields:
            if col in ("horizon", "barrier_pips", "bar_ticks"):
                continue  # structural, not rolling
            assert col in pandas_reference.columns, f"Missing: {col}"

    def test_pandas_reference_has_valid_rows(self, pandas_reference: pd.DataFrame):
        """After warmup, the reference should have non-NaN features."""
        # Row 300+ should be fully warmed up (vol_window=96, cost_window=288)
        row = pandas_reference.iloc[350]
        assert np.isfinite(row["cost_est_pips"])
        assert np.isfinite(row["tick_rate_z"])
        assert np.isfinite(row["spread_z"])
        assert np.isfinite(row["ret_z"])

    def test_state_manager_matches_pandas(self, synthetic_bars, pandas_reference):
        """
        Core contract test: DuckDB features must match pandas to within tolerance.
        This test will initially fail (RED) until we implement the state manager.
        """
        from src.behemoth.runtime.state import StateManager

        sm = StateManager(vol_window=96, cost_window=288)
        for bar in synthetic_bars:
            sm.append_bar(bar)

        # Test the last bar's features against pandas reference
        last_idx = len(synthetic_bars) - 1
        duck_features = sm.compute_features(
            symbol="EURUSD",
            bar_ticks=100,
            horizon=30,
            barrier_pips=3.0,
        )
        ref = pandas_reference.iloc[last_idx]

        # Compare rolling features within tight tolerance
        FEATURE_COLS = [
            "cost_est_pips", "range_pips", "ret1_pips", "ret_z", "ret_abs_z",
            "vel_cost_units_h1", "vel_abs_cost_units_h1", "spread_z",
            "tick_rate_z", "hour_utc", "hl_first", "hl_first_mean_24",
            "hl_pos_frac_mean_24",
        ]
        for col in FEATURE_COLS:
            duck_val = getattr(duck_features, col)
            pd_val = float(ref[col])
            if np.isnan(pd_val):
                assert np.isnan(duck_val), f"{col}: expected NaN, got {duck_val}"
            else:
                assert abs(duck_val - pd_val) < 1e-6, (
                    f"{col}: duck={duck_val:.8f} vs pandas={pd_val:.8f}"
                )

        assert duck_features.bar_ticks == 100.0
        assert duck_features.horizon == 30.0
        assert duck_features.barrier_pips == 3.0


class TestDuckDBStateLifecycle:
    """Test state manager lifecycle operations."""

    def test_import_creates_without_error(self):
        from src.behemoth.runtime.state import StateManager
        sm = StateManager()
        assert sm is not None

    def test_append_single_bar(self):
        from src.behemoth.runtime.state import StateManager
        bars = _make_synthetic_bars(n=1)
        sm = StateManager()
        sm.append_bar(bars[0])
        assert sm.bar_count("EURUSD", 100) == 1

    def test_bar_count_increments(self):
        from src.behemoth.runtime.state import StateManager
        bars = _make_synthetic_bars(n=10)
        sm = StateManager()
        for b in bars:
            sm.append_bar(b)
        assert sm.bar_count("EURUSD", 100) == 10

    def test_insufficient_warmup_returns_none(self):
        """With fewer bars than vol_window, compute_features should return None."""
        from src.behemoth.runtime.state import StateManager
        bars = _make_synthetic_bars(n=50)
        sm = StateManager(vol_window=96)
        for b in bars:
            sm.append_bar(b)
        result = sm.compute_features(symbol="EURUSD", bar_ticks=100, horizon=30, barrier_pips=3.0)
        assert result is None


class TestDuckDBTradeTracking:
    """Test DuckDB state manager's trade lifecycle and ledger functions."""

    @pytest.fixture
    def sm(self):
        from src.behemoth.runtime.state import StateManager
        sm = StateManager()
        # Create a dummy bar to anchor entry_bar_id to row 1
        bars = _make_synthetic_bars(n=1)
        sm.append_bar(bars[0])
        yield sm
        sm.close()

    def test_open_trade(self, sm):
        trade_id = sm.open_trade(
            symbol="EURUSD",
            candidate_uid="cand_1",
            broker_pos_id="bp_100",
            side="BUY",
            entry_price=1.1000,
            entry_ts=datetime(2025, 1, 1, tzinfo=timezone.utc),
            horizon=12,
        )
        assert trade_id is not None

        # Verify it went into 'OPEN' state
        active = sm.get_active_trades("EURUSD")
        assert len(active) == 1
        assert active[0]["broker_pos_id"] == "bp_100"
        assert active[0]["entry_bar_id"] == 0
        assert active[0]["horizon"] == 12
        assert active[0]["touch_bar_id"] is None

    def test_touch_trade(self, sm):
        sm.open_trade(
            symbol="EURUSD",
            candidate_uid="cand_1",
            broker_pos_id="bp_100",
            side="BUY",
            entry_price=1.1000,
            entry_ts=datetime(2025, 1, 1, tzinfo=timezone.utc),
            horizon=12,
        )
        sm.touch_trade("bp_100", 5)

        active = sm.get_active_trades("EURUSD")
        assert len(active) == 1
        assert active[0]["touch_bar_id"] == 5

    def test_update_trade_closed(self, sm):
        sm.open_trade(
            symbol="EURUSD", candidate_uid="cand_1", broker_pos_id="bp_100",
            side="BUY", entry_price=1.1000, entry_ts=datetime(2025, 1, 1, tzinfo=timezone.utc),
            horizon=12
        )
        # Close the trade
        sm.update_trade(
            broker_pos_id="bp_100",
            status="CLOSED",
            exit_price=1.1050,
            exit_ts=datetime(2025, 1, 1, 1, tzinfo=timezone.utc),
            pnl_pips=50.0,
        )

        # Should no longer be active
        assert len(sm.get_active_trades("EURUSD")) == 0

        # Test Ledger Stats sum it correctly
        stats = sm.get_ledger_stats()
        assert len(stats) == 1
        assert stats[0]["symbol"] == "EURUSD"
        assert stats[0]["total_pnl"] == 50.0
        assert stats[0]["win_rate"] == 1.0
        assert stats[0]["closed_trades"] == 1

    def test_get_latest_close_ts(self, sm):
        ts = sm.get_latest_close_ts("EURUSD")
        assert ts is not None
        assert ts.year == 2025

        ts_none = sm.get_latest_close_ts("GBPUSD")
        assert ts_none is None

    def test_log_audit_event(self, sm):
        from src.behemoth.core.schemas import ModelFeatures
        dummy_features = ModelFeatures(
            cost_est_pips=1.0, range_pips=10.0, ret1_pips=2.0, ret_z=0.5, ret_abs_z=0.5,
            vel_cost_units_h1=2.0, vel_abs_cost_units_h1=2.0, spread_z=0.1, tick_rate_z=0.1,
            hour_utc=10.0, hl_first=1.0, hl_first_mean_24=0.5, hl_pos_frac_mean_24=0.5,
            bar_ticks=100.0, horizon=24.0, barrier_pips=15.0
        )
        sm.log_audit_event("EURUSD", "cand1", 0.9, 0.5, dummy_features, "2025-01")
        res = sm._con.execute("SELECT COUNT(*) FROM audit_logs").fetchone()
        assert res[0] == 1

    def test_get_all_symbols(self, sm):
        syms = sm.get_all_symbols()
        assert "EURUSD" in syms

    def test_state_close(self, sm):
        """Test DB connection cleanup."""
        sm.close()
        with pytest.raises(Exception):
            sm.bar_count("EURUSD", 100)

    def test_db_path_file_hydration(self, tmp_path, monkeypatch):
        """Test StateManager creation with a file path and verify counter hydration."""
        from src.behemoth.runtime.state import StateManager
        db_file = tmp_path / "test_hydrate.db"

        sm1 = StateManager(persist_path=str(db_file))
        bars = _make_synthetic_bars(n=1)
        sm1.append_bar(bars[0])
        sm1.close()

        # Reopen, should read the file and hydrate row_counters
        sm2 = StateManager(persist_path=str(db_file))
        assert sm2._row_counters["EURUSD_100"] == 1
        sm2.close()
