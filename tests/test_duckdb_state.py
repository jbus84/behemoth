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

from src.behemoth.core.schemas import IncomingTick, IncomingTickBar, ModelFeatures

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

        bars.append(
            IncomingTickBar(
                symbol=symbol,
                bar_ticks=bar_ticks,
                timestamp=t,
                close_ts=close_ts,
                open_bid=round(o, 5),
                high_bid=round(h, 5),
                low_bid=round(l, 5),
                close_bid=round(c, 5),
                spread=round(spread, 6),
                tick_volume=tv,
                hl_first=hl_first_val,
                hl_pos_frac=hl_pos_frac_val,
                high_ask=round(h + spread, 5),
                close_ask=round(c + spread, 5),
            )
        )
        t = close_ts + timedelta(seconds=rng.uniform(0.5, 5.0))
        base_price = round(c, 5)
    return bars


def test_state_manager_builds_bar_context_from_internal_tick_bar_schema() -> None:
    from src.behemoth.runtime.state import StateManager

    state = StateManager()
    bar = _make_synthetic_bars(symbol="EURUSD", bar_ticks=100, n=1)[0]
    state.append_bar(bar)

    ctx = state.get_latest_bar_context("EURUSD", 100)

    assert ctx is not None
    assert ctx.symbol == "EURUSD"
    assert ctx.bar_ticks == 100
    assert ctx.bar_idx == 0
    assert ctx.bid.high == pytest.approx(bar.high_bid)
    assert ctx.bid.low == pytest.approx(bar.low_bid)
    assert ctx.bid.close == pytest.approx(bar.close_bid)
    assert ctx.ask.high == pytest.approx(bar.high_ask)
    assert ctx.ask.close == pytest.approx(bar.close_ask)
    assert ctx.hl_first == pytest.approx(float(bar.hl_first))


def test_state_manager_builds_side_aware_bar_context_by_bar_number() -> None:
    from src.behemoth.runtime.state import StateManager

    state = StateManager()
    bars = _make_synthetic_bars(symbol="EURUSD", bar_ticks=100, n=3)
    for bar in bars:
        state.append_bar(bar)

    buy_ctx = state.get_bar_context("EURUSD", 100, bar_number=1, side="BUY")
    sell_ctx = state.get_bar_context("EURUSD", 100, bar_number=1, side="SELL")

    assert buy_ctx is not None
    assert sell_ctx is not None
    assert buy_ctx.bar_number == 1
    assert buy_ctx.timestamp == bars[1].timestamp
    assert buy_ctx.close_ts == bars[1].close_ts
    assert buy_ctx.spread == pytest.approx(bars[1].spread)
    assert buy_ctx.side == "BUY"
    assert sell_ctx.side == "SELL"
    assert buy_ctx.touch_high == pytest.approx(bars[1].high_ask)
    assert buy_ctx.touch_low == pytest.approx(bars[1].low_bid)
    assert sell_ctx.touch_high == pytest.approx(bars[1].high_ask)
    assert sell_ctx.touch_low == pytest.approx(bars[1].low_bid)


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
        records.append(
            {
                "timestamp": b.timestamp,
                "close_ts": b.close_ts,
                "open_bid": b.open_bid,
                "high_bid": b.high_bid,
                "low_bid": b.low_bid,
                "close_bid": b.close_bid,
                "spread": b.spread,
                "tick_volume": b.tick_volume,
                "bar_ticks": b.bar_ticks,
                "hl_first": b.hl_first if b.hl_first is not None else np.nan,
                "hl_pos_frac": b.hl_pos_frac if b.hl_pos_frac is not None else np.nan,
            }
        )
    df = pd.DataFrame(records)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df["close_ts"] = pd.to_datetime(df["close_ts"], utc=True)
    df = df.sort_values("close_ts").reset_index(drop=True)

    close = df["close_bid"].astype(float)
    open_ = df["open_bid"].astype(float)
    high = df["high_bid"].astype(float)
    low = df["low_bid"].astype(float)

    df["hour_utc"] = df["close_ts"].dt.hour.astype(int)
    df["duration_sec"] = (df["close_ts"] - df["timestamp"]).dt.total_seconds().clip(lower=1e-6)
    df["tick_rate_hz"] = df["tick_volume"] / df["duration_sec"]

    tr_mu = (
        df["tick_rate_hz"].rolling(vol_window, min_periods=max(8, vol_window // 3)).mean().shift(1)
    )
    tr_sd = (
        df["tick_rate_hz"]
        .rolling(vol_window, min_periods=max(8, vol_window // 3))
        .std(ddof=0)
        .shift(1)
    )
    df["tick_rate_z"] = (df["tick_rate_hz"] - tr_mu) / tr_sd.replace(0.0, np.nan)

    df["spread_pips"] = df["spread"] / pip
    df["range_pips"] = (high - low) / pip

    sp_mu = (
        df["spread_pips"].rolling(vol_window, min_periods=max(8, vol_window // 3)).mean().shift(1)
    )
    sp_sd = (
        df["spread_pips"]
        .rolling(vol_window, min_periods=max(8, vol_window // 3))
        .std(ddof=0)
        .shift(1)
    )
    df["spread_z"] = (df["spread_pips"] - sp_mu) / sp_sd.replace(0.0, np.nan)

    df["vel_pips_h1"] = (close - close.shift(1)) / pip
    df["ret1_pips"] = df["vel_pips_h1"]

    vol_ref = (
        df["vel_pips_h1"]
        .rolling(vol_window, min_periods=max(8, vol_window // 3))
        .std(ddof=0)
        .shift(1)
    )
    df["ret_z"] = df["vel_pips_h1"] / (vol_ref * np.sqrt(1.0))
    df["ret_abs_z"] = df["vel_pips_h1"].abs() / (vol_ref * np.sqrt(1.0))

    spread_recent = (
        df["spread_pips"]
        .rolling(cost_window, min_periods=max(8, cost_window // 4))
        .median()
        .shift(1)
    )
    gap_abs = (open_ - close.shift(1)).abs() / pip
    slip_proxy = (
        gap_abs.rolling(cost_window, min_periods=max(8, cost_window // 6)).quantile(0.75).shift(1)
    )
    slip_fallback = (
        df["range_pips"]
        .rolling(cost_window, min_periods=max(8, cost_window // 6))
        .quantile(0.75)
        .shift(1)
        * 0.2
    )
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
            "cost_est_pips",
            "range_pips",
            "ret1_pips",
            "ret_z",
            "ret_abs_z",
            "vel_cost_units_h1",
            "vel_abs_cost_units_h1",
            "spread_z",
            "tick_rate_z",
            "hour_utc",
            "hl_first",
            "hl_first_mean_24",
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
            symbol="EURUSD",
            candidate_uid="cand_1",
            broker_pos_id="bp_100",
            side="BUY",
            entry_price=1.1000,
            entry_ts=datetime(2025, 1, 1, tzinfo=timezone.utc),
            horizon=12,
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
            cost_est_pips=1.0,
            range_pips=10.0,
            ret1_pips=2.0,
            ret_z=0.5,
            ret_abs_z=0.5,
            vel_cost_units_h1=2.0,
            vel_abs_cost_units_h1=2.0,
            spread_z=0.1,
            tick_rate_z=0.1,
            hour_utc=10.0,
            hl_first=1.0,
            hl_first_mean_24=0.5,
            hl_pos_frac_mean_24=0.5,
            bar_ticks=100.0,
            horizon=24.0,
            barrier_pips=15.0,
        )
        sm.log_audit_event("EURUSD", "cand1", 0.9, 0.5, dummy_features, "2025-01")
        res = sm._store.execute("SELECT COUNT(*) FROM audit_logs").fetchone()
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

    def test_record_raw_tick(self):
        from src.behemoth.runtime.state import StateManager

        sm = StateManager()
        tick = IncomingTick(
            symbol="EURUSD",
            timestamp=datetime(2025, 1, 1, tzinfo=timezone.utc),
            bid=1.1000,
            ask=1.1002,
            tick_volume=1.0,
        )
        sm.record_raw_tick(tick, source="historical_backtest")
        assert sm.raw_tick_count("EURUSD") == 1
        row = sm._store.execute("SELECT symbol, bid, ask, spread, source FROM raw_ticks").fetchone()
        assert row[0] == "EURUSD"
        assert row[1] == pytest.approx(1.1)
        assert row[2] == pytest.approx(1.1002)
        assert row[3] == pytest.approx(0.0002)
        assert row[4] == "historical_backtest"
        sm.close()


class TestAccountRiskReservationLedger:
    @pytest.fixture
    def sm(self):
        from src.behemoth.runtime.state import StateManager

        sm = StateManager()
        yield sm
        sm.close()

    def test_create_and_sum_active_reservations(self, sm):
        sm.create_account_risk_reservation(
            symbol="EURUSD",
            candidate_uid="oco|EURUSD|100|h5|cand_a",
            reserved_loss_ccy=120.0,
            barrier_pips=3.0,
            cap_pips=1.2,
            cost_est_pips=1.0,
            volume_units=10000.0,
        )
        sm.create_account_risk_reservation(
            symbol="USDJPY",
            candidate_uid="oco|USDJPY|100|h5|cand_b",
            reserved_loss_ccy=80.0,
            barrier_pips=3.0,
            cap_pips=1.2,
            cost_est_pips=1.0,
            volume_units=10000.0,
            status="OPEN",
        )
        total = sm.sum_active_account_risk_reserved_loss_ccy(
            include_pending=True, include_open=True
        )
        assert total == 200.0
        eur_only = sm.sum_active_account_risk_reserved_loss_ccy(
            symbol="EURUSD",
            include_pending=True,
            include_open=True,
        )
        assert eur_only == 120.0

    def test_promote_and_release_reservation(self, sm):
        rid = sm.create_account_risk_reservation(
            symbol="EURUSD",
            candidate_uid="oco|EURUSD|100|h5|cand_a",
            reserved_loss_ccy=90.0,
            barrier_pips=2.0,
            cap_pips=1.2,
            cost_est_pips=0.8,
            volume_units=10000.0,
        )
        promoted = sm.promote_account_risk_reservation(
            reservation_id=rid,
            broker_pos_id="bp_1",
        )
        assert promoted == rid
        released = sm.release_account_risk_reservation(broker_pos_id="bp_1")
        assert released == 1
        assert (
            sm.sum_active_account_risk_reserved_loss_ccy(include_pending=True, include_open=True)
            == 0.0
        )

    def test_reservation_state_machine_rejects_invalid_transition(self, sm):
        rid = sm.create_account_risk_reservation(
            symbol="EURUSD",
            candidate_uid="oco|EURUSD|100|h5|cand_a",
            reserved_loss_ccy=90.0,
            barrier_pips=2.0,
            cap_pips=1.2,
            cost_est_pips=0.8,
            volume_units=10000.0,
        )
        sm.promote_account_risk_reservation(reservation_id=rid, broker_pos_id="bp_1")

        with pytest.raises(ValueError, match="invalid reservation transition OPEN -> PENDING"):
            sm.transition_account_risk_reservation(rid, "PENDING")

    def test_expire_stale_pending_reservations(self, sm):
        rid = sm.create_account_risk_reservation(
            symbol="EURUSD",
            candidate_uid="oco|EURUSD|100|h5|cand_old",
            reserved_loss_ccy=30.0,
            barrier_pips=2.0,
            cap_pips=1.2,
            cost_est_pips=0.8,
            volume_units=10000.0,
        )
        sm._store.execute(
            "UPDATE account_risk_reservations SET created_ts = ? WHERE reservation_id = ?",
            [datetime(2020, 1, 1, tzinfo=timezone.utc), rid],
        )
        expired = sm.expire_stale_account_risk_pending_reservations(max_age_seconds=60)
        assert expired == 1
        rows = sm.list_active_account_risk_reservations()
        assert rows == []

    def test_log_account_risk_allocator_event(self, sm):
        sm.log_account_risk_allocator_event(
            symbol="EURUSD",
            candidate_uid="oco|EURUSD|100|h5|cand_a",
            status="ADMITTED",
            block_reason=None,
            reserved_loss_ccy=25.0,
            requested_volume_units=10000.0,
            pred_prob=0.8,
            threshold_exec=0.6,
            risk_rank_score=0.2,
            reservation_id="r1",
        )
        rows = sm._store.execute(
            "SELECT symbol, status, reservation_id FROM account_risk_allocator_events"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][0] == "EURUSD"
        assert rows[0][1] == "ADMITTED"
        assert rows[0][2] == "r1"


class TestRollingThreshold:
    def test_returns_none_when_no_audit_history(self):
        from src.behemoth.runtime.state import StateManager

        sm = StateManager()
        result = sm.get_rolling_threshold(
            symbol="GBPUSD",
            candidate_uid="oco|GBPUSD|100|h6|oco_first_touch__ny_overlap__k2",
            exec_q=0.9,
            lookback_days=20,
            min_history=10,
        )
        assert result is None

    def test_returns_quantile_when_sufficient_history(self):
        from datetime import datetime, timedelta, timezone

        from src.behemoth.runtime.state import StateManager

        sm = StateManager()
        now = datetime.now(tz=timezone.utc)
        uid = "oco|GBPUSD|100|h6|oco_first_touch__ny_overlap__k2"
        # Insert 20 pred_probs ranging from 0.50 to 0.69
        for i in range(20):
            sm._store.execute(
                "INSERT INTO audit_logs(event_ts, close_ts, symbol, candidate_uid, "
                "pred_prob, threshold, features_json, model_month, run_id) "
                "VALUES (?, ?, 'GBPUSD', ?, ?, 0.5, '{}', '2026-02', 'warmup')",
                [now - timedelta(days=i), now - timedelta(days=i), uid, 0.50 + i * 0.01],
            )
        result = sm.get_rolling_threshold(
            symbol="GBPUSD",
            candidate_uid=uid,
            exec_q=0.9,
            lookback_days=20,
            min_history=10,
        )
        assert result is not None
        assert 0.50 <= result <= 0.69

    def test_returns_none_when_below_min_history(self):
        from datetime import datetime, timedelta, timezone

        from src.behemoth.runtime.state import StateManager

        sm = StateManager()
        now = datetime.now(tz=timezone.utc)
        uid = "oco|GBPUSD|100|h6|oco_first_touch__ny_overlap__k2"
        # Only 5 events, min_history=10
        for i in range(5):
            sm._store.execute(
                "INSERT INTO audit_logs(event_ts, close_ts, symbol, candidate_uid, "
                "pred_prob, threshold, features_json, model_month, run_id) "
                "VALUES (?, ?, 'GBPUSD', ?, 0.60, 0.5, '{}', '2026-02', 'warmup')",
                [now - timedelta(days=i), now - timedelta(days=i), uid],
            )
        result = sm.get_rolling_threshold(
            symbol="GBPUSD",
            candidate_uid=uid,
            exec_q=0.9,
            lookback_days=20,
            min_history=10,
        )
        assert result is None


class TestPurgeAuditEvents:
    def test_purge_removes_only_matching_symbol_and_run_id(self):
        from datetime import datetime, timezone

        from src.behemoth.runtime.state import StateManager

        sm = StateManager()
        now = datetime.now(tz=timezone.utc)
        uid = "oco|GBPUSD|100|h6|oco_first_touch__ny_overlap__k2"
        # 5 warmup rows for GBPUSD
        for i in range(5):
            sm._store.execute(
                "INSERT INTO audit_logs(event_ts, close_ts, symbol, candidate_uid, "
                "pred_prob, threshold, features_json, model_month, run_id) "
                "VALUES (?, ?, 'GBPUSD', ?, ?, 0.5, '{}', '2026-02', 'warmup')",
                [now, now, uid, 0.60 + i * 0.01],
            )
        # 3 jforex_live rows for GBPUSD (must NOT be purged)
        for i in range(3):
            sm._store.execute(
                "INSERT INTO audit_logs(event_ts, close_ts, symbol, candidate_uid, "
                "pred_prob, threshold, features_json, model_month, run_id) "
                "VALUES (?, ?, 'GBPUSD', ?, ?, 0.5, '{}', '2026-02', 'jforex_live')",
                [now, now, uid, 0.70 + i * 0.01],
            )
        # 2 warmup rows for EURUSD (must NOT be purged — different symbol)
        for i in range(2):
            sm._store.execute(
                "INSERT INTO audit_logs(event_ts, close_ts, symbol, candidate_uid, "
                "pred_prob, threshold, features_json, model_month, run_id) "
                "VALUES (?, ?, 'EURUSD', ?, ?, 0.5, '{}', '2026-02', 'warmup')",
                [now, now, uid, 0.65 + i * 0.01],
            )

        purged = sm.purge_audit_events(symbol="GBPUSD", run_id="warmup")

        assert purged == 5
        # GBPUSD warmup gone
        n_gbp_warmup = sm._store.execute(
            "SELECT COUNT(*) FROM audit_logs WHERE symbol='GBPUSD' AND run_id='warmup'"
        ).fetchone()[0]
        assert n_gbp_warmup == 0
        # GBPUSD jforex_live untouched
        n_gbp_live = sm._store.execute(
            "SELECT COUNT(*) FROM audit_logs WHERE symbol='GBPUSD' AND run_id='jforex_live'"
        ).fetchone()[0]
        assert n_gbp_live == 3
        # EURUSD warmup untouched
        n_eur_warmup = sm._store.execute(
            "SELECT COUNT(*) FROM audit_logs WHERE symbol='EURUSD' AND run_id='warmup'"
        ).fetchone()[0]
        assert n_eur_warmup == 2
        sm.close()

    def test_purge_returns_zero_when_nothing_matches(self):
        from src.behemoth.runtime.state import StateManager

        sm = StateManager()
        purged = sm.purge_audit_events(symbol="NOPE", run_id="warmup")
        assert purged == 0
        sm.close()


class TestTradeRicherRecording:
    @pytest.fixture
    def sm(self):
        from src.behemoth.runtime.state import StateManager

        sm = StateManager()
        bars = _make_synthetic_bars(n=3)
        for b in bars:
            sm.append_bar(b)
        yield sm
        sm.close()

    def test_open_trade_stores_reservation_id(self, sm):
        sm.open_trade(
            symbol="EURUSD",
            candidate_uid="cand_1",
            broker_pos_id="bp_1",
            side="BUY",
            entry_price=1.1,
            entry_ts=datetime(2025, 1, 1, tzinfo=timezone.utc),
            horizon=6,
            reservation_id="res-abc-123",
        )
        row = sm._store.execute(
            "SELECT reservation_id FROM trades WHERE broker_pos_id = 'bp_1'"
        ).fetchone()
        assert row[0] == "res-abc-123"

    def test_open_trade_populates_model_context_from_audit_logs(self, sm):
        sm._store.execute(
            "INSERT INTO audit_logs (event_ts, close_ts, symbol, candidate_uid, pred_prob, "
            "threshold, features_json, model_month, run_id) "
            "VALUES (CURRENT_TIMESTAMP, ?, ?, ?, ?, ?, '{}', ?, ?)",
            [
                datetime(2025, 1, 1, tzinfo=timezone.utc),
                "EURUSD",
                "cand_1",
                0.85,
                0.72,
                "2025-01",
                "r1",
            ],
        )
        sm.open_trade(
            symbol="EURUSD",
            candidate_uid="cand_1",
            broker_pos_id="bp_2",
            side="BUY",
            entry_price=1.1,
            entry_ts=datetime(2025, 1, 1, tzinfo=timezone.utc),
            horizon=6,
        )
        row = sm._store.execute(
            "SELECT entry_pred_prob, entry_threshold, entry_model_month FROM trades WHERE broker_pos_id = 'bp_2'"
        ).fetchone()
        assert abs(row[0] - 0.85) < 1e-9
        assert abs(row[1] - 0.72) < 1e-9
        assert row[2] == "2025-01"

    def test_open_trade_nulls_model_context_when_no_audit_row(self, sm):
        sm.open_trade(
            symbol="EURUSD",
            candidate_uid="no_match",
            broker_pos_id="bp_3",
            side="BUY",
            entry_price=1.1,
            entry_ts=datetime(2025, 1, 1, tzinfo=timezone.utc),
            horizon=6,
        )
        row = sm._store.execute(
            "SELECT entry_pred_prob, entry_threshold, entry_model_month FROM trades WHERE broker_pos_id = 'bp_3'"
        ).fetchone()
        assert row[0] is None
        assert row[1] is None
        assert row[2] is None

    def test_update_trade_stores_exit_fields(self, sm):
        sm.open_trade(
            symbol="EURUSD",
            candidate_uid="cand_1",
            broker_pos_id="bp_4",
            side="BUY",
            entry_price=1.1,
            entry_ts=datetime(2025, 1, 1, tzinfo=timezone.utc),
            horizon=6,
        )
        sm.update_trade(
            broker_pos_id="bp_4",
            status="CLOSED",
            exit_price=1.105,
            exit_ts=datetime(2025, 1, 1, 1, tzinfo=timezone.utc),
            pnl_pips=50.0,
            symbol="EURUSD",
            close_reason="HORIZON_COMPLETED",
            commission_ccy=-0.46,
        )
        row = sm._store.execute(
            "SELECT exit_bar_id, close_reason, commission_ccy FROM trades WHERE broker_pos_id = 'bp_4'"
        ).fetchone()
        assert row[0] is not None
        assert row[1] == "HORIZON_COMPLETED"
        assert abs(row[2] - (-0.46)) < 1e-9

    def test_bars_held_is_positive(self, sm):
        sm.open_trade(
            symbol="EURUSD",
            candidate_uid="cand_1",
            broker_pos_id="bp_5",
            side="BUY",
            entry_price=1.1,
            entry_ts=datetime(2025, 1, 1, tzinfo=timezone.utc),
            horizon=6,
        )
        for b in _make_synthetic_bars(n=3):
            sm.append_bar(b)
        sm.update_trade(
            broker_pos_id="bp_5",
            status="CLOSED",
            exit_price=1.105,
            exit_ts=datetime(2025, 1, 1, 1, tzinfo=timezone.utc),
            pnl_pips=50.0,
            symbol="EURUSD",
            close_reason="HORIZON_COMPLETED",
        )
        row = sm._store.execute(
            "SELECT entry_bar_id, exit_bar_id FROM trades WHERE broker_pos_id = 'bp_5'"
        ).fetchone()
        assert row[1] > row[0]


class TestHighAskPersistence:
    """high_ask and close_ask survive the append_bar → get_latest_bar round-trip."""

    def test_get_latest_bar_returns_high_ask(self):
        from src.behemoth.runtime.state import StateManager

        mgr = StateManager()
        bar = _make_synthetic_bars(n=1)[0]
        # Override to known values so the assertion is unambiguous
        bar = bar.model_copy(update={"high_ask": 1.30050, "close_ask": 1.29980})
        mgr.append_bar(bar)
        latest = mgr.get_latest_bar(bar.symbol, bar.bar_ticks)
        assert latest is not None
        assert latest["high_ask"] == pytest.approx(1.30050)


class TestCanonicalBarSchemaNames:
    def test_latest_bar_uses_explicit_bid_field_names_only(self):
        from src.behemoth.runtime.state import StateManager

        mgr = StateManager()
        bar = _make_synthetic_bars(n=1)[0]
        mgr.append_bar(bar)
        latest = mgr.get_latest_bar(bar.symbol, bar.bar_ticks)
        assert latest is not None
        assert "open_bid" in latest
        assert "high_bid" in latest
        assert "low_bid" in latest
        assert "close_bid" in latest
        assert "open" not in latest
        assert "high" not in latest
        assert "low" not in latest
        assert "close" not in latest


class TestTickBarSchemaMigration:
    def test_state_manager_renames_legacy_price_columns_to_explicit_bid_columns(self, tmp_path):
        import duckdb

        from src.behemoth.runtime.state import StateManager

        db_path = tmp_path / "runtime.duckdb"
        con = duckdb.connect(str(db_path))
        con.execute(
            """
            CREATE TABLE tick_bars (
                row_id INTEGER,
                symbol VARCHAR,
                bar_ticks INTEGER,
                ts TIMESTAMP WITH TIME ZONE,
                close_ts TIMESTAMP WITH TIME ZONE,
                open_price DOUBLE,
                high_price DOUBLE,
                low_price DOUBLE,
                close_price DOUBLE,
                spread DOUBLE,
                tick_volume DOUBLE,
                hl_first DOUBLE,
                hl_pos_frac DOUBLE
            )
            """
        )
        con.execute(
            """
            INSERT INTO tick_bars VALUES
            (1, 'EURUSD', 100, TIMESTAMPTZ '2025-01-01 00:00:00+00', TIMESTAMPTZ '2025-01-01 00:01:00+00',
             1.1000, 1.1010, 1.0990, 1.1005, 0.0002, 100.0, 1.0, 0.6)
            """
        )
        con.close()

        mgr = StateManager(persist_path=str(db_path))
        columns = {
            row[0]
            for row in mgr._store.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'tick_bars'
                """
            ).fetchall()
        }
        latest = mgr.get_latest_bar("EURUSD", 100)

        assert {"open_bid", "high_bid", "low_bid", "close_bid"} <= columns
        assert "open_price" not in columns
        assert "high_price" not in columns
        assert "low_price" not in columns
        assert "close_price" not in columns
        assert latest is not None
        assert latest["open_bid"] == pytest.approx(1.1)
        assert latest["high_bid"] == pytest.approx(1.101)
        assert latest["low_bid"] == pytest.approx(1.099)
        assert latest["close_bid"] == pytest.approx(1.1005)
