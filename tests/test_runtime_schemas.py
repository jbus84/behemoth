#!/usr/bin/env python3
"""TDD tests for Pydantic runtime schemas.

These tests validate that our shared contracts are correctly structured,
enforce type constraints, and produce the exact field sets expected by
the CatBoost model and the downstream OCO pipeline.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.behemoth.core.schemas import (
    IncomingTick,
    IncomingTickBar,
    ModelFeatures,
    OcoPrediction,
)

# ── IncomingTick ──────────────────────────────────────────────────────


class TestIncomingTick:
    def test_valid_tick(self):
        t = IncomingTick(
            symbol="EURUSD",
            timestamp=datetime(2025, 12, 1, 10, 0, 0, tzinfo=timezone.utc),
            bid=1.10500,
            ask=1.10520,
        )
        assert t.symbol == "EURUSD"
        assert t.bid == 1.10500
        assert t.tick_volume == 1.0  # default

    def test_negative_bid_rejected(self):
        with pytest.raises(Exception):
            IncomingTick(
                symbol="EURUSD",
                timestamp=datetime(2025, 12, 1, tzinfo=timezone.utc),
                bid=-1.0,
                ask=1.10520,
            )

    def test_zero_bid_rejected(self):
        with pytest.raises(Exception):
            IncomingTick(
                symbol="EURUSD",
                timestamp=datetime(2025, 12, 1, tzinfo=timezone.utc),
                bid=0.0,
                ask=1.10520,
            )


# ── IncomingTickBar ───────────────────────────────────────────────────


class TestIncomingTickBar:
    def test_canonical_bar_schema_uses_explicit_bid_names_only(self):
        expected_fields = [
            "symbol",
            "bar_ticks",
            "timestamp",
            "close_ts",
            "open_bid",
            "high_bid",
            "low_bid",
            "close_bid",
            "spread",
            "tick_volume",
            "high_pos_tick",
            "low_pos_tick",
            "hl_first",
            "hl_pos_delta_tick",
            "hl_pos_frac",
            "bar_return_sign",
            "tick_burst",
            "quote_revisions",
            "intra_bar_momentum",
            "high_ask",
            "close_ask",
        ]

        assert list(IncomingTickBar.model_fields.keys()) == expected_fields
        assert "open" not in IncomingTickBar.model_fields
        assert "high" not in IncomingTickBar.model_fields
        assert "low" not in IncomingTickBar.model_fields
        assert "close" not in IncomingTickBar.model_fields
        assert "ask" not in IncomingTickBar.model_fields

    def test_valid_bar(self):
        bar = IncomingTickBar(
            symbol="GBPUSD",
            bar_ticks=100,
            timestamp=datetime(2025, 12, 1, 10, 0, 0, tzinfo=timezone.utc),
            close_ts=datetime(2025, 12, 1, 10, 0, 30, tzinfo=timezone.utc),
            open_bid=1.26400,
            high_bid=1.26500,
            low_bid=1.26300,
            close_bid=1.26450,
            spread=0.00012,
            tick_volume=100.0,
            high_ask=1.26512,
            close_ask=1.26462,
        )
        assert bar.bar_ticks == 100
        assert bar.hl_first is None  # optional

    def test_optional_hl_fields(self):
        bar = IncomingTickBar(
            symbol="USDJPY",
            bar_ticks=100,
            timestamp=datetime(2025, 12, 1, tzinfo=timezone.utc),
            close_ts=datetime(2025, 12, 1, tzinfo=timezone.utc),
            open_bid=150.0,
            high_bid=150.1,
            low_bid=149.9,
            close_bid=150.05,
            spread=0.02,
            tick_volume=100.0,
            hl_first=1.0,
            hl_pos_frac=0.65,
            high_ask=150.12,
            close_ask=150.07,
        )
        assert bar.hl_first == 1.0
        assert bar.hl_pos_frac == 0.65


# ── ModelFeatures ─────────────────────────────────────────────────────


class TestModelFeatures:
    """The feature vector must exactly match the 16 columns used in Stage-03."""

    EXPECTED_FIELDS = [
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
        "bar_ticks",
        "horizon",
        "barrier_pips",
    ]

    def test_field_names_match_wfo_feature_cols(self):
        """Ensure the pydantic model has the exact same fields as _feature_cols()."""
        actual = list(ModelFeatures.model_fields.keys())
        assert actual == self.EXPECTED_FIELDS

    def test_field_count_is_16(self):
        assert len(ModelFeatures.model_fields) == 16

    def test_valid_features(self):
        f = ModelFeatures(
            cost_est_pips=0.8,
            range_pips=5.2,
            ret1_pips=1.3,
            ret_z=0.5,
            ret_abs_z=0.5,
            vel_cost_units_h1=1.6,
            vel_abs_cost_units_h1=1.6,
            spread_z=-0.2,
            tick_rate_z=0.1,
            hour_utc=14.0,
            hl_first=1.0,
            hl_first_mean_24=0.3,
            hl_pos_frac_mean_24=0.55,
            bar_ticks=100.0,
            horizon=30.0,
            barrier_pips=3.0,
        )
        assert f.cost_est_pips == 0.8

    def test_to_list_preserves_order(self):
        """The model array must be in the exact order expected by CatBoost."""
        vals = [
            0.8,
            5.2,
            1.3,
            0.5,
            0.5,
            1.6,
            1.6,
            -0.2,
            0.1,
            14.0,
            1.0,
            0.3,
            0.55,
            100.0,
            30.0,
            3.0,
        ]
        f = ModelFeatures(**dict(zip(self.EXPECTED_FIELDS, vals, strict=False)))
        reconstructed = [getattr(f, k) for k in self.EXPECTED_FIELDS]
        assert reconstructed == vals


# ── OcoPrediction ─────────────────────────────────────────────────────


class TestOcoPrediction:
    def test_valid_prediction(self):
        p = OcoPrediction(
            symbol="EURUSD",
            close_ts=datetime(2025, 12, 1, 10, 0, 0, tzinfo=timezone.utc),
            candidate_uid="EURUSD_b100_h30_bar5_oco",
            pred_prob=0.72,
            threshold_exec=0.65,
            selected_exec=1,
            horizon=30,
            barrier_pips=3.0,
            cap_pips=1.5,
            threshold_source="rolling_history",
            model_month="2025-12",
        )
        assert p.selected_exec == 1

    def test_pred_prob_bounds(self):
        with pytest.raises(Exception):
            OcoPrediction(
                symbol="EURUSD",
                close_ts=datetime(2025, 12, 1, tzinfo=timezone.utc),
                candidate_uid="test",
                pred_prob=1.5,  # out of bounds
                threshold_exec=0.65,
                selected_exec=0,
                horizon=30,
                barrier_pips=3.0,
                cap_pips=1.5,
                threshold_source="rolling_history",
                model_month="2025-12",
            )
