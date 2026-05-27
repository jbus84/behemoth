#!/usr/bin/env python3
"""TDD tests for the FastAPI inference server.

Uses httpx + FastAPI TestClient to validate endpoints
without needing CatBoost models (mocked where necessary).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from src.behemoth.api import server
from src.behemoth.api.server import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Create a test client with an isolated runtime DB and empty governance dir per test."""
    empty_gov = tmp_path / "governance_empty"
    empty_gov.mkdir()
    monkeypatch.setenv("BEHEMOTH_GOVERNANCE_DIR", str(empty_gov))
    original_persist_db_path = server._config.persist_db_path
    server._config.persist_db_path = str(tmp_path / "behemoth_runtime.duckdb")
    try:
        with TestClient(app) as c:
            yield c
    finally:
        server._config.persist_db_path = original_persist_db_path


class TestHealthEndpoint:
    def test_health_returns_ok(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] in ("ok", "no_models")
        assert "utc_now" in body
        assert "bar_counts" in body

    def test_health_contains_all_symbols(self, client):
        r = client.get("/health")
        body = r.json()
        for sym in ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD"]:
            assert sym in body["bar_counts"]

    def test_health_reports_active_bar_ticks_and_governance_dir(self, client, monkeypatch):
        monkeypatch.setattr(server, "_effective_governance_dir", lambda: "configs/research/governance/oco")
        monkeypatch.setattr(server, "_active_bar_ticks_for_symbol", lambda sym: [1000])
        monkeypatch.setattr(
            server,
            "_state",
            type(
                "StateStub",
                (),
                {"bar_count": staticmethod(lambda sym, bt: 7 if bt == 1000 else 0)},
            )(),
        )

        r = client.get("/health")

        assert r.status_code == 200
        body = r.json()
        assert body["governance_dir"] == "configs/research/governance/oco"
        assert body["bar_ticks"]["EURUSD"] == [1000]
        assert body["bar_counts"]["EURUSD"] == 7

    def test_health_uninitialized_state(self, client):
        """If the state manager is missing, health should return 503."""
        from src.behemoth.api import server

        original_state = server._state
        server._state = None
        try:
            r = client.get("/health")
            assert r.status_code == 503
            assert "State manager not initialized" in r.json()["detail"]
        finally:
            server._state = original_state

    def test_health_returns_503_before_lifespan_ready(self, client):
        """Health must return 503 while lifespan initialization is in progress."""
        from src.behemoth.api import server

        original = server._lifespan_ready
        server._lifespan_ready = False
        try:
            r = client.get("/health")
            assert r.status_code == 503
            assert "Lifespan initialization in progress" in r.json()["detail"]
        finally:
            server._lifespan_ready = original


class TestBundlePathsThresholdOverrides:
    def test_load_bundle_paths_prefers_locked_runtime_thresholds(self, tmp_path, monkeypatch):
        import hashlib

        from src.behemoth.core.bundle_paths import BundlePaths
        from src.behemoth.core.model_registry import ModelRegistry

        bundle_dir = tmp_path
        models_dir = bundle_dir / "models"
        models_dir.mkdir()
        model_path = models_dir / "GBPUSD_model_2026-03.cbm"
        threshold_path = models_dir / "GBPUSD_model_2026-03.json"
        model_path.write_bytes(b"fake-cbm")
        threshold_path.write_text(
            json.dumps(
                {
                    "symbol": "GBPUSD",
                    "model_month": "2026-03",
                    "threshold_exec": 0.66,
                    "threshold_source": "rolling_days",
                    "rolling_threshold_days": 20,
                    "rolling_threshold_min_history": 1000,
                    "execution_quantile": 0.9,
                    "feature_schema_version": "1.0",
                }
            ),
            encoding="utf-8",
        )
        pred = bundle_dir / "gbpusd_oco_locked_predictions.parquet"
        states = bundle_dir / "gbpusd_oco_allowed_states.csv"
        pred.write_bytes(b"p")
        states.write_bytes(b"s")

        def _sha(b: bytes) -> str:
            return hashlib.sha256(b).hexdigest()

        lock = {
            "schema_version": 3,
            "symbol": "GBPUSD",
            "bundle": {
                "month": "2026-03",
                "dir_relpath": str(bundle_dir),
                "family": "oco_first_touch",
            },
            "artifacts": {
                "predictions":          {"path": "gbpusd_oco_locked_predictions.parquet", "sha256": _sha(b"p")},
                "allowed_states_csv":   {"path": "gbpusd_oco_allowed_states.csv",         "sha256": _sha(b"s")},
                "model_cbm":            {"path": "models/GBPUSD_model_2026-03.cbm",       "sha256": _sha(b"fake-cbm")},
                "model_threshold_json": {"path": "models/GBPUSD_model_2026-03.json",      "sha256": hashlib.sha256(threshold_path.read_bytes()).hexdigest()},
            },
            "deployability": {"live_deployable": True, "model_month": "2026-03"},
        }
        lock_path = bundle_dir / "gbpusd_oco_first_touch_live_lock.json"
        lock_path.write_text(json.dumps(lock))

        bp = BundlePaths.from_lock(lock_path)

        class FakeCatBoost:
            def load_model(self, path: str) -> None:
                self.loaded_path = path

        registry = ModelRegistry()
        ok, month = registry.load_bundle_paths(
            symbol="GBPUSD",
            bundle_paths=bp,
            cache_key="GBPUSD",
            locked_runtime_overrides={
                "threshold_source": "rolling_days",
                "rolling_threshold_days": 20,
                "rolling_threshold_min_history": 300,
                "execution_quantile": 0.9,
            },
            expected_month="2026-03",
            catboost_cls=FakeCatBoost,
        )

        assert ok is True
        assert month == "2026-03"
        _, thr_cfg = registry.get_model_and_threshold("GBPUSD")
        assert thr_cfg["rolling_threshold_min_history"] == 300


class TestModelRegistryFamilyCacheKey:
    def test_family_cache_key(self) -> None:
        from src.behemoth.core.model_registry import ModelRegistry

        assert ModelRegistry.make_cache_key("EURUSD", "2026-04", "directional") == "EURUSD|2026-04|directional"
        assert ModelRegistry.make_cache_key("EURUSD", None, "directional") == "EURUSD|directional"
        assert ModelRegistry.make_cache_key("EURUSD", "2026-04") == "EURUSD|2026-04"
        assert ModelRegistry.make_cache_key("EURUSD") == "EURUSD"


class TestModelRegistryCacheFallback:
    def test_exact_lookup_works(self) -> None:
        from src.behemoth.core.model_registry import ModelRegistry

        reg = ModelRegistry()
        reg.set_model_and_threshold("EURUSD|oco_first_touch", "model_a", {"t": 0.5}, "2026-04")
        model, thr = reg.get_model_and_threshold("EURUSD|oco_first_touch")
        assert model == "model_a"
        assert thr == {"t": 0.5}

    def test_symbol_fallback_with_single_family(self) -> None:
        from src.behemoth.core.model_registry import ModelRegistry

        reg = ModelRegistry()
        reg.set_model_and_threshold("EURUSD|oco_first_touch", "model_a", {"t": 0.5}, "2026-04")
        model, thr = reg.get_model_and_threshold("EURUSD")
        assert model == "model_a"
        assert thr == {"t": 0.5}

    def test_symbol_month_fallback_with_single_family(self) -> None:
        from src.behemoth.core.model_registry import ModelRegistry

        reg = ModelRegistry()
        reg.set_model_and_threshold("EURUSD|2026-04|oco_first_touch", "model_a", {"t": 0.5}, "2026-04")
        model, thr = reg.get_model_and_threshold("EURUSD|2026-04")
        assert model == "model_a"
        assert thr == {"t": 0.5}

    def test_fallback_returns_none_when_multiple_families(self) -> None:
        from src.behemoth.core.model_registry import ModelRegistry

        reg = ModelRegistry()
        reg.set_model_and_threshold("EURUSD|oco_first_touch", "model_a", {"t": 0.5}, "2026-04")
        reg.set_model_and_threshold("EURUSD|directional", "model_b", {"t": 0.6}, "2026-04")
        model, thr = reg.get_model_and_threshold("EURUSD")
        assert model is None
        assert thr is None

    def test_fallback_returns_none_when_multiple_symbol_month_families(self) -> None:
        from src.behemoth.core.model_registry import ModelRegistry

        reg = ModelRegistry()
        reg.set_model_and_threshold("EURUSD|2026-04|oco_first_touch", "model_a", {"t": 0.5}, "2026-04")
        reg.set_model_and_threshold("EURUSD|2026-04|directional", "model_b", {"t": 0.6}, "2026-04")
        model, thr = reg.get_model_and_threshold("EURUSD|2026-04")
        assert model is None
        assert thr is None


class TestLoadModelsMultiFamily:
    def test_load_models_skips_when_no_families(self, monkeypatch) -> None:
        from src.behemoth.core.registry import CandidateRegistry
        from src.behemoth.api import server

        empty_reg = CandidateRegistry()
        monkeypatch.setattr(server, "_registry", empty_reg)
        monkeypatch.setattr(server, "_is_historical_mode", lambda: False)
        monkeypatch.setattr(server._model_registry, "clear", lambda: None)

        original_symbols = server._config.symbols
        server._config.symbols = ["EURUSD"]
        try:
            server._load_models()
        finally:
            server._config.symbols = original_symbols


class TestMetricsEndpoint:
    def test_metrics_returns_prometheus_format(self, client):
        r = client.get("/metrics")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/plain")
        assert "behemoth_" in r.text

    def test_metrics_drop_stale_equity_symbols_when_current_ledger_is_empty(self, client):
        server.METRIC_EQUITY_PIPS.clear()

        server._sync_equity_pips_metrics(
            [{"symbol": "GBPUSD", "total_pnl": -17.9}]
        )
        populated = client.get("/metrics")
        assert 'behemoth_equity_pips{symbol="GBPUSD"} -17.9' in populated.text

        server._sync_equity_pips_metrics([])
        cleared = client.get("/metrics")
        assert 'behemoth_equity_pips{symbol="GBPUSD"}' not in cleared.text

    def test_metrics_publish_broker_open_positions_separately_from_reservations(self, client):
        import unittest.mock as mock

        now = datetime(2026, 4, 10, 11, 30, 0, tzinfo=timezone.utc)
        created = now - timedelta(minutes=5)
        reservations = [
            {
                "reservation_id": "eur-open",
                "created_ts": created,
                "updated_ts": created,
                "symbol": "EURUSD",
                "candidate_uid": "cand-1",
                "broker_pos_id": "bp-eur-1",
                "status": "OPEN",
                "reserved_loss_ccy": 10.0,
                "barrier_pips": 20.0,
                "cap_pips": 30.0,
                "cost_est_pips": 5.0,
                "volume_units": 1000.0,
                "side": "BUY",
                "source": "algo",
            },
            {
                "reservation_id": "eur-pending",
                "created_ts": created,
                "updated_ts": created,
                "symbol": "EURUSD",
                "candidate_uid": "cand-2",
                "broker_pos_id": None,
                "status": "PENDING",
                "reserved_loss_ccy": 10.0,
                "barrier_pips": 20.0,
                "cap_pips": 30.0,
                "cost_est_pips": 5.0,
                "volume_units": 1000.0,
                "side": "BUY",
                "source": "algo",
            },
            {
                "reservation_id": "gbp-open",
                "created_ts": created,
                "updated_ts": created,
                "symbol": "GBPUSD",
                "candidate_uid": "cand-3",
                "broker_pos_id": "bp-gbp-1",
                "status": "OPEN",
                "reserved_loss_ccy": 10.0,
                "barrier_pips": 20.0,
                "cap_pips": 30.0,
                "cost_est_pips": 5.0,
                "volume_units": 1000.0,
                "side": "SELL",
                "source": "algo",
            },
            {
                "reservation_id": "usdcad-open",
                "created_ts": created,
                "updated_ts": created,
                "symbol": "USDCAD",
                "candidate_uid": "cand-4",
                "broker_pos_id": "bp-cad-1",
                "status": "OPEN",
                "reserved_loss_ccy": 10.0,
                "barrier_pips": 20.0,
                "cap_pips": 30.0,
                "cost_est_pips": 5.0,
                "volume_units": 1000.0,
                "side": "BUY",
                "source": "algo",
            },
            {
                "reservation_id": "aud-pending",
                "created_ts": created,
                "updated_ts": created,
                "symbol": "AUDUSD",
                "candidate_uid": "cand-5",
                "broker_pos_id": None,
                "status": "PENDING",
                "reserved_loss_ccy": 10.0,
                "barrier_pips": 20.0,
                "cap_pips": 30.0,
                "cost_est_pips": 5.0,
                "volume_units": 1000.0,
                "side": "BUY",
                "source": "algo",
            },
        ]

        active_trades = {
            "EURUSD": [{"broker_pos_id": "bp-eur-1", "entry_bar_id": 10, "horizon": 6, "touch_bar_id": None}],
            "GBPUSD": [{"broker_pos_id": "bp-gbp-1", "entry_bar_id": 10, "horizon": 6, "touch_bar_id": None}],
            "USDCAD": [{"broker_pos_id": "bp-cad-1", "entry_bar_id": 10, "horizon": 6, "touch_bar_id": None}],
            "AUDUSD": [],
            "USDCHF": [],
            "USDJPY": [],
        }

        with (
            mock.patch.object(server._state, "list_active_account_risk_reservations", return_value=reservations),
            mock.patch.object(server._state, "get_last_bar_close_price", return_value=None),
            mock.patch.object(server._state, "get_all_symbols", return_value=["EURUSD", "GBPUSD", "USDCAD", "AUDUSD", "USDCHF", "USDJPY"]),
            mock.patch.object(server._state, "get_active_trades", side_effect=lambda symbol: active_trades[symbol]),
        ):
            summary = server._build_open_positions_summary(server._state, now)

        assert summary["total_open"] == 5
        assert summary["broker_confirmed"] == 3
        assert summary["pending_broker_confirm"] == 2

        metrics = client.get("/metrics")
        assert 'behemoth_open_positions_total{symbol="EURUSD"} 2.0' in metrics.text
        assert 'behemoth_pending_broker_confirm_positions_total{symbol="EURUSD"} 1.0' in metrics.text
        assert 'behemoth_broker_open_positions_total{symbol="EURUSD"} 1.0' in metrics.text
        assert 'behemoth_pending_broker_confirm_positions_total{symbol="GBPUSD"} 0.0' in metrics.text
        assert 'behemoth_broker_open_positions_total{symbol="GBPUSD"} 1.0' in metrics.text
        assert 'behemoth_pending_broker_confirm_positions_total{symbol="USDCAD"} 0.0' in metrics.text
        assert 'behemoth_broker_open_positions_total{symbol="USDCAD"} 1.0' in metrics.text
        assert 'behemoth_pending_broker_confirm_positions_total{symbol="AUDUSD"} 1.0' in metrics.text
        assert 'behemoth_broker_open_positions_total{symbol="AUDUSD"} 0.0' in metrics.text
        assert 'behemoth_pending_broker_confirm_positions_total{symbol="USDCHF"} 0.0' in metrics.text
        assert 'behemoth_pending_broker_confirm_positions_total{symbol="USDJPY"} 0.0' in metrics.text

    def test_open_position_age_seconds_uses_oldest_broker_confirmed_trade(self, client):
        import unittest.mock as mock

        now = datetime(2026, 4, 10, 11, 30, 0, tzinfo=timezone.utc)
        older_pending = now - timedelta(minutes=20)
        newer_confirmed = now - timedelta(minutes=5)
        reservations = [
            {
                "reservation_id": "eur-pending",
                "created_ts": older_pending,
                "updated_ts": older_pending,
                "symbol": "EURUSD",
                "candidate_uid": "cand-1",
                "broker_pos_id": None,
                "status": "PENDING",
                "reserved_loss_ccy": 10.0,
                "barrier_pips": 20.0,
                "cap_pips": 30.0,
                "cost_est_pips": 5.0,
                "volume_units": 1000.0,
                "side": "BUY",
                "source": "algo",
            },
            {
                "reservation_id": "eur-open",
                "created_ts": newer_confirmed,
                "updated_ts": newer_confirmed,
                "symbol": "EURUSD",
                "candidate_uid": "cand-2",
                "broker_pos_id": "bp-eur-1",
                "status": "OPEN",
                "reserved_loss_ccy": 10.0,
                "barrier_pips": 20.0,
                "cap_pips": 30.0,
                "cost_est_pips": 5.0,
                "volume_units": 1000.0,
                "side": "BUY",
                "source": "algo",
            },
        ]

        active_trades = {
            "EURUSD": [{"broker_pos_id": "bp-eur-1", "entry_bar_id": 10, "horizon": 6, "touch_bar_id": None}],
            "GBPUSD": [],
            "USDCAD": [],
            "AUDUSD": [],
            "USDCHF": [],
            "USDJPY": [],
        }

        with (
            mock.patch.object(server._state, "list_active_account_risk_reservations", return_value=reservations),
            mock.patch.object(server._state, "get_last_bar_close_price", return_value=None),
            mock.patch.object(
                server._state,
                "get_all_symbols",
                return_value=["EURUSD", "GBPUSD", "USDCAD", "AUDUSD", "USDCHF", "USDJPY"],
            ),
            mock.patch.object(server._state, "get_active_trades", side_effect=lambda symbol: active_trades[symbol]),
        ):
            server._build_open_positions_summary(server._state, now)

        metrics = client.get("/metrics")
        assert 'behemoth_open_position_age_seconds{symbol="EURUSD"} 300.0' in metrics.text


@pytest.mark.requires_models
class TestPredictLatestBarSchema:
    def test_predict_uses_explicit_bid_latest_bar_keys_for_barrier_lifecycle(self, client):
        import unittest.mock as mock
        from datetime import datetime, timezone
        from types import SimpleNamespace

        import numpy as np

        from src.behemoth.api import server
        from src.behemoth.core.schemas import BarContext, BarPrices, ModelFeatures, OcoPrediction

        dummy_cand = mock.MagicMock()
        dummy_cand.bar_ticks = 100
        dummy_cand.horizon = 24
        dummy_cand.barrier_pips = 15.0
        dummy_cand.candidate_uid = "cand1"

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
        prediction = OcoPrediction(
            symbol="EURUSD",
            close_ts=datetime(2025, 1, 1, tzinfo=timezone.utc),
            candidate_uid="cand1",
            pred_prob=0.85,
            threshold_exec=0.5,
            selected_exec=1,
            bar_ticks=100,
            horizon=24,
            barrier_pips=15.0,
            cap_pips=1.2,
            threshold_source="test",
            model_month="2025-01",
        )
        barrier_manager = mock.MagicMock()
        barrier_manager.evaluate_bar.return_value = []
        barrier_manager.has_active_scan.return_value = False
        latest_bar = {
            "row_id": 17,
            "open_bid": 1.1000,
            "high_bid": 1.1025,
            "low_bid": 1.0985,
            "close_bid": 1.1015,
            "hl_first": 1.0,
            "high_ask": 1.1027,
            "close_ask": 1.1017,
        }
        latest_context = BarContext(
            symbol="EURUSD",
            bar_ticks=100,
            bar_idx=latest_bar["row_id"],
            bid=BarPrices(
                high=latest_bar["high_bid"],
                low=latest_bar["low_bid"],
                close=latest_bar["close_bid"],
            ),
            ask=BarPrices(
                high=latest_bar["high_ask"],
                low=latest_bar["close_ask"],
                close=latest_bar["close_ask"],
            ),
            hl_first=latest_bar["hl_first"],
        )

        original_barrier_manager = server._barrier_manager
        server._barrier_manager = barrier_manager
        try:
            with (
                mock.patch.object(
                    server,
                    "_resolve_runtime_contract",
                    return_value=SimpleNamespace(
                        candidates=[dummy_cand],
                        model_month="2025-01",
                        cap_pips=1.2,
                    ),
                ),
                mock.patch.object(
                    server,
                    "_ensure_model_and_threshold",
                    return_value=(
                        mock.MagicMock(predict_proba=mock.MagicMock(return_value=np.array([[0.1, 0.85]]))),
                        {
                            "threshold_exec": 0.5,
                            "threshold_source": "test",
                            "rolling_threshold_days": 20,
                            "rolling_threshold_min_history": 1,
                            "execution_quantile": 0.9,
                        },
                    ),
                ),
                mock.patch.object(server, "_check_warmup", return_value=None),
                mock.patch.object(server._state, "compute_features", return_value=dummy_features),
                mock.patch.object(
                    server._state,
                    "get_latest_close_ts",
                    return_value=datetime(2025, 1, 1, tzinfo=timezone.utc),
                ),
                mock.patch.object(server._state, "get_rolling_threshold", return_value=0.5),
                mock.patch.object(server._state, "get_latest_bar", return_value=latest_bar),
                mock.patch.object(server._state, "get_latest_bar_context", return_value=latest_context),
                mock.patch.object(server, "_build_predictions", return_value=([prediction], [])),
            ):
                response = client.post(
                    "/predict",
                    json={
                        "symbol": "EURUSD",
                        "requested_volume_units": 10000,
                        "account_risk_enabled_override": False,
                    },
                )

            assert response.status_code == 200
            barrier_manager.evaluate_bar.assert_called_once()
            bar_context = barrier_manager.evaluate_bar.call_args.args[0]
            assert isinstance(bar_context, BarContext)
            assert bar_context.symbol == "EURUSD"
            assert bar_context.bar_ticks == 100
            assert bar_context.bar_idx == latest_bar["row_id"]
            assert bar_context.bid.high == latest_bar["high_bid"]
            assert bar_context.bid.low == latest_bar["low_bid"]
            assert bar_context.bid.close == latest_bar["close_bid"]
            assert bar_context.ask.high == latest_bar["high_ask"]
            assert bar_context.ask.close == latest_bar["close_ask"]
            assert bar_context.hl_first == latest_bar["hl_first"]
            barrier_manager.register_scan.assert_called_once_with(
                symbol="EURUSD",
                candidate_uid="cand1",
                signal_bar_idx=latest_bar["row_id"],
                ref_price=latest_bar["close_bid"],
                signal_close_ask=latest_bar["close_ask"],
                signal_close_bid=latest_bar["close_bid"],
                barrier_pips=15.0,
                horizon=24,
                pip_size=0.0001,
                pred_prob=0.85,
                threshold=0.5,
                model_month="2025-01",
                reservation_id=None,
                run_id=mock.ANY,
            )
        finally:
            server._barrier_manager = original_barrier_manager

    def test_predict_rejects_legacy_latest_bar_keys(self, client):
        import unittest.mock as mock
        from datetime import datetime, timezone
        from types import SimpleNamespace

        import numpy as np

        dummy_cand = mock.MagicMock()
        dummy_cand.bar_ticks = 100
        dummy_cand.horizon = 24
        dummy_cand.barrier_pips = 15.0
        dummy_cand.candidate_uid = "cand1"

        latest_bar = {
            "row_id": 17,
            "high": 1.1025,
            "low": 1.0985,
            "close": 1.1015,
            "hl_first": 1.0,
            "high_ask": 1.1027,
            "close_ask": 1.1017,
        }

        with (
            mock.patch.object(
                server,
                "_resolve_runtime_contract",
                return_value=SimpleNamespace(
                    candidates=[dummy_cand],
                    model_month="2025-01",
                    cap_pips=1.2,
                ),
            ),
            mock.patch.object(
                server,
                "_ensure_model_and_threshold",
                return_value=(
                    mock.MagicMock(predict_proba=mock.MagicMock(return_value=np.array([[0.1, 0.85]]))),
                    {
                        "threshold_exec": 0.5,
                        "threshold_source": "test",
                        "rolling_threshold_days": 20,
                        "rolling_threshold_min_history": 1,
                        "execution_quantile": 0.9,
                    },
                ),
            ),
            mock.patch.object(server, "_check_warmup", return_value=None),
            mock.patch.object(
                server._state,
                "compute_features",
                return_value=mock.MagicMock(),
            ),
            mock.patch.object(
                server._state,
                "get_latest_close_ts",
                return_value=datetime(2025, 1, 1, tzinfo=timezone.utc),
            ),
            mock.patch.object(server._state, "get_rolling_threshold", return_value=0.5),
            mock.patch.object(server._state, "get_latest_bar", return_value=latest_bar),
            mock.patch.object(server, "_build_predictions", return_value=([], [])),
        ):
            response = client.post(
                "/predict",
                json={
                    "symbol": "EURUSD",
                    "requested_volume_units": 10000,
                    "account_risk_enabled_override": False,
                },
            )

        assert response.status_code == 422
        assert "legacy ambiguous bar schema unsupported" in response.json()["detail"]


class TestAccountRiskEndpoints:
    def test_account_limits_endpoint(self, client):
        r = client.get("/risk/account/limits")
        assert r.status_code == 200
        body = r.json()
        assert "enabled" in body

    def test_account_snapshot_and_status(self, client):
        r = client.post(
            "/risk/account/snapshot",
            json={
                "symbol": "EURUSD",
                "balance": 10000.0,
                "equity": 9950.0,
                "snapshot_ts": "2025-01-01T10:00:00Z",
            },
        )
        assert r.status_code == 201
        status = client.get("/risk/account/status?symbol=EURUSD")
        assert status.status_code == 200
        body = status.json()
        assert "allow_trading" in body
        assert body["snapshot_available"] in (True, False)

    def test_account_reservations_status_and_release(self, client):
        status = client.get("/risk/account/reservations/status?symbol=EURUSD")
        assert status.status_code == 200
        body = status.json()
        assert "active_count" in body
        release = client.post(
            "/risk/account/reservations/release",
            json={"candidate_uid": "missing_candidate_uid"},
        )
        assert release.status_code == 200
        assert "released_count" in release.json()

    def test_account_risk_limits_endpoint(self, client):
        r = client.get("/risk/account_risk/limits")
        assert r.status_code == 200
        body = r.json()
        assert "enabled" in body
        if body["enabled"]:
            assert body["profile_id"] is not None
            assert body["daily_loss_limit_hard"] is not None
            assert body["max_loss_limit_hard"] is not None

    def test_account_risk_snapshot_and_status(self, client):
        r = client.post(
            "/risk/account_risk/snapshot",
            json={
                "symbol": "EURUSD",
                "balance": 10000.0,
                "equity": 9950.0,
                "snapshot_ts": "2025-01-01T10:00:00Z",
            },
        )
        assert r.status_code == 201
        status = client.get("/risk/account_risk/status?symbol=EURUSD")
        assert status.status_code == 200
        body = status.json()
        assert "allow_trading" in body
        assert body["snapshot_available"] in (True, False)

    def test_account_risk_reservations_status_and_release(self, client):
        status = client.get("/risk/account_risk/reservations/status?symbol=EURUSD")
        assert status.status_code == 200
        body = status.json()
        assert "active_count" in body
        release = client.post(
            "/risk/account_risk/reservations/release",
            json={"candidate_uid": "missing_candidate_uid"},
        )
        assert release.status_code == 200
        assert "released_count" in release.json()


class TestStatusEndpoint:
    def test_status_returns_list(self, client):
        r = client.get("/status")
        assert r.status_code == 200
        body = r.json()
        assert isinstance(body, list)
        assert len(body) == 6
        symbols = {s["symbol"] for s in body}
        assert symbols == {"EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD"}

    def test_status_uses_active_candidate_bar_ticks(self, client, monkeypatch):
        monkeypatch.setattr(server, "_effective_governance_dir", lambda: "configs/research/governance/oco")
        monkeypatch.setattr(server, "_active_bar_ticks_for_symbol", lambda sym: [1000])
        monkeypatch.setattr(
            server,
            "_state",
            type(
                "StateStub",
                (),
                {"bar_count": staticmethod(lambda sym, bt: 11 if bt == 1000 else 0)},
            )(),
        )

        r = client.get("/status")

        assert r.status_code == 200
        body = r.json()
        eurusd = next(row for row in body if row["symbol"] == "EURUSD")
        assert eurusd["governance_dir"] == "configs/research/governance/oco"
        assert eurusd["bar_ticks"] == [1000]
        assert eurusd["bar_count"] == 11

    @pytest.mark.requires_models
    def test_status_reports_no_go_not_promoted_symbol(self, client, monkeypatch):
        monkeypatch.setattr(server, "_effective_governance_dir", lambda: "configs/research/governance/oco")
        monkeypatch.setattr(server, "_is_historical_mode", lambda: False)
        monkeypatch.setattr(
            server,
            "_config",
            type("Cfg", (), {"symbols": ["EURUSD", "AUDUSD"], "governance_mode": "live"})(),
        )
        monkeypatch.setattr(server, "_active_bar_ticks_for_symbol", lambda sym: [1000] if sym == "EURUSD" else [])
        monkeypatch.setattr(
            server,
            "_state",
            type(
                "StateStub",
                (),
                {"bar_count": staticmethod(lambda sym, bt: 11 if (sym, bt) == ("EURUSD", 1000) else 0)},
            )(),
        )
        monkeypatch.setattr(server, "_has_loaded_model_for_symbol", lambda sym: sym == "EURUSD")
        monkeypatch.setattr(server, "_latest_loaded_month_for_symbol", lambda sym: "2026-03" if sym == "EURUSD" else None)
        monkeypatch.setattr(server, "_thresholds", {"EURUSD": {"threshold": 0.9}})

        r = client.get("/status")

        assert r.status_code == 200
        body = r.json()
        audusd = next(row for row in body if row["symbol"] == "AUDUSD")
        assert audusd["deployment_state"] == "no_go_not_promoted"
        assert audusd["bar_ticks"] == []
        assert audusd["bar_count"] == 0
        assert audusd["model_loaded"] is False
        assert audusd["model_month"] is None
        assert audusd["has_threshold"] is False
        assert audusd["restart_verdict"] is None
        assert audusd["restart_reasons"] == []

    def test_status_surfaces_restart_reconciliation_failure(self, client, monkeypatch):
        monkeypatch.setattr(server, "_effective_governance_dir", lambda: "configs/research/governance/oco")
        monkeypatch.setattr(server, "_is_historical_mode", lambda: False)
        monkeypatch.setattr(
            server,
            "_config",
            type("Cfg", (), {"symbols": ["EURUSD", "GBPUSD"], "governance_mode": "live"})(),
        )
        monkeypatch.setattr(server, "_active_bar_ticks_for_symbol", lambda sym: [1000])
        monkeypatch.setattr(
            server,
            "_state",
            type(
                "StateStub",
                (),
                {
                    "bar_count": staticmethod(lambda sym, bt: 11),
                    "db_path": "data/analysis/backtest_reconcile/runtime/live_state.db",
                },
            )(),
        )
        monkeypatch.setattr(server, "_has_loaded_model_for_symbol", lambda sym: True)
        monkeypatch.setattr(server, "_latest_loaded_month_for_symbol", lambda sym: "2026-03")
        monkeypatch.setattr(
            server,
            "_load_restart_reconciliation_report",
            lambda: {
                "verdict": "incompatible",
                "reasons": [
                    "broker-linked symbols do not match broker snapshot symbols",
                    "broker-linked position ids do not match broker snapshot order ids",
                ],
            },
        )

        r = client.get("/status")

        assert r.status_code == 200
        body = r.json()
        eurusd = next(row for row in body if row["symbol"] == "EURUSD")
        assert eurusd["restart_verdict"] == "incompatible"
        assert eurusd["restart_reasons"] == [
            "broker-linked symbols do not match broker snapshot symbols",
            "broker-linked position ids do not match broker snapshot order ids",
        ]

    def test_active_bar_ticks_for_live_symbol_without_registry_candidates_is_empty(self, monkeypatch):
        monkeypatch.setattr(server, "_is_historical_mode", lambda: False)

        class RegistryStub:
            @staticmethod
            def get_candidates(symbol: str):
                return []

        monkeypatch.setattr(server, "_registry", RegistryStub())

        assert server._active_bar_ticks_for_symbol("AUDUSD") == []

    def test_runtime_feed_status_returns_symbols(self, client):
        r = client.get("/runtime/feed/status")
        assert r.status_code == 200
        body = r.json()
        assert "as_of_utc" in body
        assert "symbols" in body
        listed = {row["symbol"] for row in body["symbols"]}
        assert {"EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD"}.issubset(listed)


class TestDashboard:
    def test_dashboard_includes_deployment_state_label(self, client):
        r = client.get("/dashboard/")
        assert r.status_code == 200
        html = r.text
        assert "deployment_state" in html
        assert "NO_GO / Not Promoted" in html


class TestBarsEndpoint:
    def test_ingest_bar(self, client):
        bar = {
            "symbol": "EURUSD",
            "bar_ticks": 100,
            "timestamp": "2025-12-01T10:00:00Z",
            "close_ts": "2025-12-01T10:00:30Z",
            "open_bid": 1.10500,
            "high_bid": 1.10600,
            "low_bid": 1.10400,
            "close_bid": 1.10550,
            "spread": 0.00012,
            "tick_volume": 100,
            "high_ask": 1.10612,
            "close_ask": 1.10562,
        }
        r = client.post("/bars", json=bar)
        assert r.status_code == 201
        body = r.json()
        assert body["ok"] is True
        assert body["symbol"] == "EURUSD"
        assert body["bar_count"] >= 1

    def test_ingest_bar_validation_error(self, client):
        bar = {
            "symbol": "EURUSD",
            "bar_ticks": 100,
            "timestamp": "2025-12-01T10:00:00Z",
            "close_ts": "2025-12-01T10:00:30Z",
            "open_bid": -1.0,  # invalid
            "high_bid": 1.10600,
            "low_bid": 1.10400,
            "close_bid": 1.10550,
            "spread": 0.00012,
            "tick_volume": 100,
            "high_ask": 1.10612,
            "close_ask": 1.10562,
        }
        r = client.post("/bars", json=bar)
        assert r.status_code == 422

    def test_ingest_bar_uninitialized_state(self, client):
        """If _state is None, ingest_bar returns 503."""
        from src.behemoth.api import server

        original_state = server._state
        server._state = None
        try:
            bar = {
                "symbol": "EURUSD",
                "bar_ticks": 100,
                "timestamp": "2025-12-01T10:00:00Z",
                "close_ts": "2025-12-01T10:00:30Z",
                "open_bid": 1.10500,
                "high_bid": 1.10600,
                "low_bid": 1.10400,
                "close_bid": 1.10550,
                "spread": 0.00012,
                "tick_volume": 100,
                "high_ask": 1.10612,
                "close_ask": 1.10562,
            }
            r = client.post("/bars", json=bar)
            assert r.status_code == 503
            assert "State manager not initialized" in r.json()["detail"]
        finally:
            server._state = original_state


@pytest.mark.requires_models
class TestPredictEndpoint:
    def test_historical_prediction_universe_tolerant_mode_accepts_nearby_row(self, tmp_path):
        from types import SimpleNamespace

        import duckdb

        from src.behemoth.api import server

        pred_path = tmp_path / "predictions.parquet"
        con = duckdb.connect()
        try:
            con.execute(
                """
                CREATE TABLE pred AS
                SELECT
                    TIMESTAMPTZ '2025-07-07 00:00:15+00:00' AS close_ts,
                    '2025-07' AS test_month,
                    'oco|EURUSD|100|h6|state_a' AS candidate_uid
                """
            )
            con.execute("COPY pred TO ? (FORMAT 'parquet')", [str(pred_path)])
        finally:
            con.close()

        cand = SimpleNamespace(bar_ticks=100, horizon=6, candidate_uid="state_a")
        contract = SimpleNamespace(
            symbol="EURUSD",
            model_month="2025-07",
            cache_key="EURUSD|2025-07",
            model_binding={"predictions_path": str(pred_path)},
        )

        orig_mode = server._config.governance_mode
        orig_gate_mode = server._config.historical_prediction_universe_mode
        server._historical_prediction_universes = {}
        server._historical_prediction_candidate_index = {}
        server._historical_prediction_candidate_cursor = {}
        try:
            server._config.governance_mode = "historical"
            server._config.historical_prediction_universe_mode = "tolerant"
            out = server._apply_historical_prediction_universe_gate(
                contract=contract,
                close_ts=datetime(2025, 7, 7, 0, 0, 0, tzinfo=timezone.utc),
                candidates=[cand],
            )
            assert len(out) == 1
        finally:
            server._config.governance_mode = orig_mode
            server._config.historical_prediction_universe_mode = orig_gate_mode
            server._historical_prediction_universes = {}
            server._historical_prediction_candidate_index = {}

    def test_historical_prediction_universe_tolerant_mode_suppresses_tied_match(self, tmp_path):
        from types import SimpleNamespace

        import duckdb

        from src.behemoth.api import server

        pred_path = tmp_path / "predictions.parquet"
        con = duckdb.connect()
        try:
            con.execute(
                """
                CREATE TABLE pred AS
                SELECT * FROM (
                    VALUES
                        (TIMESTAMPTZ '2025-07-07 00:00:10+00:00', '2025-07', 'oco|EURUSD|100|h6|state_a'),
                        (TIMESTAMPTZ '2025-07-07 00:00:20+00:00', '2025-07', 'oco|EURUSD|100|h6|state_a')
                ) AS t(close_ts, test_month, candidate_uid)
                """
            )
            con.execute("COPY pred TO ? (FORMAT 'parquet')", [str(pred_path)])
        finally:
            con.close()

        cand = SimpleNamespace(bar_ticks=100, horizon=6, candidate_uid="state_a")
        contract = SimpleNamespace(
            symbol="EURUSD",
            model_month="2025-07",
            cache_key="EURUSD|2025-07",
            model_binding={"predictions_path": str(pred_path)},
        )

        orig_mode = server._config.governance_mode
        orig_gate_mode = server._config.historical_prediction_universe_mode
        server._historical_prediction_universes = {}
        server._historical_prediction_candidate_index = {}
        server._historical_prediction_candidate_cursor = {}
        try:
            server._config.governance_mode = "historical"
            server._config.historical_prediction_universe_mode = "tolerant"
            out = server._apply_historical_prediction_universe_gate(
                contract=contract,
                close_ts=datetime(2025, 7, 7, 0, 0, 15, tzinfo=timezone.utc),
                candidates=[cand],
            )
            assert out == []
        finally:
            server._config.governance_mode = orig_mode
            server._config.historical_prediction_universe_mode = orig_gate_mode
            server._historical_prediction_universes = {}
            server._historical_prediction_candidate_index = {}
            server._historical_prediction_candidate_cursor = {}

    def test_historical_prediction_universe_tolerant_mode_does_not_reuse_locked_row(self, tmp_path):
        from types import SimpleNamespace

        import duckdb

        from src.behemoth.api import server

        pred_path = tmp_path / "predictions.parquet"
        con = duckdb.connect()
        try:
            con.execute(
                """
                CREATE TABLE pred AS
                SELECT
                    TIMESTAMPTZ '2025-07-07 00:00:15+00:00' AS close_ts,
                    '2025-07' AS test_month,
                    'oco|EURUSD|100|h6|state_a' AS candidate_uid
                """
            )
            con.execute("COPY pred TO ? (FORMAT 'parquet')", [str(pred_path)])
        finally:
            con.close()

        cand = SimpleNamespace(bar_ticks=100, horizon=6, candidate_uid="state_a")
        contract = SimpleNamespace(
            symbol="EURUSD",
            model_month="2025-07",
            cache_key="EURUSD|2025-07",
            model_binding={"predictions_path": str(pred_path)},
        )

        orig_mode = server._config.governance_mode
        orig_gate_mode = server._config.historical_prediction_universe_mode
        server._historical_prediction_universes = {}
        server._historical_prediction_candidate_index = {}
        server._historical_prediction_candidate_cursor = {}
        try:
            server._config.governance_mode = "historical"
            server._config.historical_prediction_universe_mode = "tolerant"
            first = server._apply_historical_prediction_universe_gate(
                contract=contract,
                close_ts=datetime(2025, 7, 7, 0, 0, 0, tzinfo=timezone.utc),
                candidates=[cand],
            )
            second = server._apply_historical_prediction_universe_gate(
                contract=contract,
                close_ts=datetime(2025, 7, 7, 0, 0, 5, tzinfo=timezone.utc),
                candidates=[cand],
            )
            assert len(first) == 1
            assert second == []
        finally:
            server._config.governance_mode = orig_mode
            server._config.historical_prediction_universe_mode = orig_gate_mode
            server._historical_prediction_universes = {}
            server._historical_prediction_candidate_index = {}
            server._historical_prediction_candidate_cursor = {}

    def test_historical_prediction_payload_override_requires_exact_row(self, tmp_path):
        from types import SimpleNamespace

        import duckdb

        from src.behemoth.api import server

        pred_path = tmp_path / "predictions.parquet"
        con = duckdb.connect()
        try:
            con.execute(
                """
                CREATE TABLE pred AS
                SELECT * FROM (
                    VALUES
                        (TIMESTAMPTZ '2025-07-07 00:00:12+00:00', '2025-07', 'oco|EURUSD|100|h6|state_a', 0.71, 0.61, 1),
                        (TIMESTAMPTZ '2025-07-07 00:10:12+00:00', '2025-07', 'oco|EURUSD|100|h6|state_a', 0.42, 0.61, 0)
                ) AS t(close_ts, test_month, candidate_uid, pred_prob, threshold_exec, selected_exec)
                """
            )
            con.execute("COPY pred TO ? (FORMAT 'parquet')", [str(pred_path)])
        finally:
            con.close()

        cand = SimpleNamespace(bar_ticks=100, horizon=6, candidate_uid="state_a")
        contract = SimpleNamespace(
            symbol="EURUSD",
            model_month="2025-07",
            cache_key="EURUSD|2025-07",
            model_binding={"predictions_path": str(pred_path)},
        )

        orig_mode = server._config.governance_mode
        orig_payload_mode = server._config.historical_prediction_payload_mode
        server._historical_prediction_payload_rows = {}
        try:
            server._config.governance_mode = "historical"
            server._config.historical_prediction_payload_mode = "locked"
            out = server._resolve_historical_prediction_payload_overrides(
                contract=contract,
                close_ts=datetime(2025, 7, 7, 0, 0, 0, tzinfo=timezone.utc),
                candidates=[cand],
            )
            assert out == {}
        finally:
            server._config.governance_mode = orig_mode
            server._config.historical_prediction_payload_mode = orig_payload_mode
            server._historical_prediction_payload_rows = {}

    def test_historical_prediction_payload_override_does_not_prefer_nearby_selected_row(
        self, tmp_path
    ):
        from types import SimpleNamespace

        import duckdb

        from src.behemoth.api import server

        pred_path = tmp_path / "predictions.parquet"
        con = duckdb.connect()
        try:
            con.execute(
                """
                CREATE TABLE pred AS
                SELECT * FROM (
                    VALUES
                        (TIMESTAMPTZ '2025-07-07 00:00:10+00:00', '2025-07', 'oco|EURUSD|100|h6|state_a', 0.52, 0.61, 0),
                        (TIMESTAMPTZ '2025-07-07 00:00:20+00:00', '2025-07', 'oco|EURUSD|100|h6|state_a', 0.72, 0.61, 1)
                ) AS t(close_ts, test_month, candidate_uid, pred_prob, threshold_exec, selected_exec)
                """
            )
            con.execute("COPY pred TO ? (FORMAT 'parquet')", [str(pred_path)])
        finally:
            con.close()

        cand = SimpleNamespace(bar_ticks=100, horizon=6, candidate_uid="state_a")
        contract = SimpleNamespace(
            symbol="EURUSD",
            model_month="2025-07",
            cache_key="EURUSD|2025-07",
            model_binding={"predictions_path": str(pred_path)},
        )

        orig_mode = server._config.governance_mode
        orig_payload_mode = server._config.historical_prediction_payload_mode
        orig_tol = server._config.historical_prediction_tolerance_sec
        server._historical_prediction_payload_rows = {}
        try:
            server._config.governance_mode = "historical"
            server._config.historical_prediction_payload_mode = "locked"
            server._config.historical_prediction_tolerance_sec = 30.0
            out = server._resolve_historical_prediction_payload_overrides(
                contract=contract,
                close_ts=datetime(2025, 7, 7, 0, 0, 10, tzinfo=timezone.utc),
                candidates=[cand],
            )
            row = out["oco|EURUSD|100|h6|state_a"]
            assert row["selected_exec"] == 0
            assert row["pred_prob"] == pytest.approx(0.52)
        finally:
            server._config.governance_mode = orig_mode
            server._config.historical_prediction_payload_mode = orig_payload_mode
            server._config.historical_prediction_tolerance_sec = orig_tol
            server._historical_prediction_payload_rows = {}

    def test_historical_prediction_payload_override_does_not_reuse_locked_row(self, tmp_path):
        from types import SimpleNamespace

        import duckdb

        from src.behemoth.api import server

        pred_path = tmp_path / "predictions.parquet"
        con = duckdb.connect()
        try:
            con.execute(
                """
                CREATE TABLE pred AS
                SELECT * FROM (
                    VALUES
                        (TIMESTAMPTZ '2025-07-08 04:30:34.649+00:00', '2025-07', 'oco|AUDUSD|100|h6|state_a', 0.58, 0.56, 1)
                ) AS t(close_ts, test_month, candidate_uid, pred_prob, threshold_exec, selected_exec)
                """
            )
            con.execute("COPY pred TO ? (FORMAT 'parquet')", [str(pred_path)])
        finally:
            con.close()

        cand = SimpleNamespace(bar_ticks=100, horizon=6, candidate_uid="state_a")
        contract = SimpleNamespace(
            symbol="AUDUSD",
            model_month="2025-07",
            cache_key="AUDUSD|2025-07",
            model_binding={"predictions_path": str(pred_path)},
        )

        orig_mode = server._config.governance_mode
        orig_payload_mode = server._config.historical_prediction_payload_mode
        orig_tol = server._config.historical_prediction_tolerance_sec
        server._historical_prediction_payload_rows = {}
        server._historical_prediction_payload_cursor = {}
        try:
            server._config.governance_mode = "historical"
            server._config.historical_prediction_payload_mode = "locked"
            server._config.historical_prediction_tolerance_sec = 60.0
            first = server._resolve_historical_prediction_payload_overrides(
                contract=contract,
                close_ts=datetime(2025, 7, 8, 4, 29, 45, 999000, tzinfo=timezone.utc),
                candidates=[cand],
            )
            second = server._resolve_historical_prediction_payload_overrides(
                contract=contract,
                close_ts=datetime(2025, 7, 8, 4, 30, 34, 649000, tzinfo=timezone.utc),
                candidates=[cand],
            )
            assert first == {}
            assert second["oco|AUDUSD|100|h6|state_a"]["selected_exec"] == 1
        finally:
            server._config.governance_mode = orig_mode
            server._config.historical_prediction_payload_mode = orig_payload_mode
            server._config.historical_prediction_tolerance_sec = orig_tol
            server._historical_prediction_payload_rows = {}
            server._historical_prediction_payload_cursor = {}

    def test_historical_prediction_universe_tolerant_mode_does_not_late_release_locked_payload(
        self, tmp_path
    ):
        from types import SimpleNamespace

        import duckdb

        from src.behemoth.api import server

        pred_path = tmp_path / "predictions.parquet"
        con = duckdb.connect()
        try:
            con.execute(
                """
                CREATE TABLE pred AS
                SELECT
                    TIMESTAMPTZ '2025-07-07 00:00:15+00:00' AS close_ts,
                    '2025-07' AS test_month,
                    'oco|EURUSD|100|h6|state_a' AS candidate_uid
                """
            )
            con.execute("COPY pred TO ? (FORMAT 'parquet')", [str(pred_path)])
        finally:
            con.close()

        cand = SimpleNamespace(bar_ticks=100, horizon=6, candidate_uid="state_a")
        contract = SimpleNamespace(
            symbol="EURUSD",
            model_month="2025-07",
            cache_key="EURUSD|2025-07",
            model_binding={"predictions_path": str(pred_path)},
        )

        orig_mode = server._config.governance_mode
        orig_gate_mode = server._config.historical_prediction_universe_mode
        orig_payload_mode = server._config.historical_prediction_payload_mode
        server._historical_prediction_universes = {}
        server._historical_prediction_candidate_index = {}
        server._historical_prediction_candidate_cursor = {}
        try:
            server._config.governance_mode = "historical"
            server._config.historical_prediction_universe_mode = "tolerant"
            server._config.historical_prediction_payload_mode = "locked"
            out = server._apply_historical_prediction_universe_gate(
                contract=contract,
                close_ts=datetime(2025, 7, 7, 0, 1, 15, tzinfo=timezone.utc),
                candidates=[cand],
            )
            assert out == []
        finally:
            server._config.governance_mode = orig_mode
            server._config.historical_prediction_universe_mode = orig_gate_mode
            server._config.historical_prediction_payload_mode = orig_payload_mode
            server._historical_prediction_universes = {}
            server._historical_prediction_candidate_index = {}
            server._historical_prediction_candidate_cursor = {}

    def test_historical_prediction_universe_tolerant_mode_does_not_release_stale_row(
        self, tmp_path
    ):
        from types import SimpleNamespace

        import duckdb

        from src.behemoth.api import server

        pred_path = tmp_path / "predictions.parquet"
        con = duckdb.connect()
        try:
            con.execute(
                """
                CREATE TABLE pred AS
                SELECT
                    TIMESTAMPTZ '2025-07-07 00:00:15+00:00' AS close_ts,
                    '2025-07' AS test_month,
                    'oco|EURUSD|100|h6|state_a' AS candidate_uid
                """
            )
            con.execute("COPY pred TO ? (FORMAT 'parquet')", [str(pred_path)])
        finally:
            con.close()

        cand = SimpleNamespace(bar_ticks=100, horizon=6, candidate_uid="state_a")
        contract = SimpleNamespace(
            symbol="EURUSD",
            model_month="2025-07",
            cache_key="EURUSD|2025-07",
            model_binding={"predictions_path": str(pred_path)},
        )

        orig_mode = server._config.governance_mode
        orig_gate_mode = server._config.historical_prediction_universe_mode
        orig_payload_mode = server._config.historical_prediction_payload_mode
        orig_tol = server._config.historical_prediction_tolerance_sec
        server._historical_prediction_universes = {}
        server._historical_prediction_candidate_index = {}
        server._historical_prediction_candidate_cursor = {}
        try:
            server._config.governance_mode = "historical"
            server._config.historical_prediction_universe_mode = "tolerant"
            server._config.historical_prediction_payload_mode = "locked"
            server._config.historical_prediction_tolerance_sec = 30.0
            out = server._apply_historical_prediction_universe_gate(
                contract=contract,
                close_ts=datetime(2025, 7, 7, 0, 10, 15, tzinfo=timezone.utc),
                candidates=[cand],
            )
            assert out == []
        finally:
            server._config.governance_mode = orig_mode
            server._config.historical_prediction_universe_mode = orig_gate_mode
            server._config.historical_prediction_payload_mode = orig_payload_mode
            server._config.historical_prediction_tolerance_sec = orig_tol
            server._historical_prediction_universes = {}
            server._historical_prediction_candidate_index = {}
            server._historical_prediction_candidate_cursor = {}

    def test_predict_requires_size(self, client):
        r = client.post(
            "/predict",
            json={"symbol": "EURUSD", "account_risk_enabled_override": True},
        )
        assert r.status_code == 422

    def test_predict_requires_risk_override(self, client):
        r = client.post(
            "/predict",
            json={"symbol": "EURUSD", "requested_volume_units": 10000},
        )
        assert r.status_code == 422
        detail = str(r.json().get("detail", "")).lower()
        assert "risk_enabled_override" in detail or "account_risk_enabled_override" in detail

    def test_predict_request_accepts_canonical_risk_override(self):
        from src.behemoth.api.server import PredictRequest

        req = PredictRequest.model_validate(
            {
                "symbol": "EURUSD",
                "risk_enabled_override": True,
                "requested_volume_units": 10000,
                "completed_bar_ticks": [100],
                "run_id": "jforex-gbpusd-slice",
            }
        )

        assert req.effective_risk_enabled_override() is True
        assert req.completed_bar_ticks == [100]

    def test_predict_insufficient_warmup(self, client):
        """With no bars ingested, predict should return 422."""
        r = client.post(
            "/predict",
            json={
                "symbol": "EURUSD",
                "requested_volume_units": 10000,
                "account_risk_enabled_override": True,
            },
        )
        assert r.status_code in (200, 422, 503)
        if r.status_code == 200:
            assert isinstance(r.json(), list)
        else:
            detail = r.json()["detail"].lower()
            assert (
                "warmup" in detail
                or "candidate" in detail
                or "registry" in detail
                or "model" in detail
            )

    def test_predict_uninitialized_state(self, client):
        """If _state is None, predict returns 503."""
        from src.behemoth.api import server

        original_state = server._state
        server._state = None
        try:
            r = client.post(
                "/predict",
                json={
                    "symbol": "EURUSD",
                    "requested_volume_units": 10000,
                    "account_risk_enabled_override": True,
                },
            )
            assert r.status_code == 503
            assert "State manager not initialized" in r.json()["detail"]
        finally:
            server._state = original_state

    def test_predict_unloaded_registry(self, client):
        """If _registry is None, predict returns 503."""
        from src.behemoth.api import server

        original_registry = server._registry
        server._registry = None
        try:
            r = client.post(
                "/predict",
                json={
                    "symbol": "EURUSD",
                    "requested_volume_units": 10000,
                    "account_risk_enabled_override": True,
                },
            )
            assert r.status_code == 503
            assert "Candidate registry not loaded" in r.json()["detail"]
        finally:
            server._registry = original_registry

    def test_predict_no_candidates(self, client):
        """If registry returns empty candidates, predict returns 422."""
        import unittest.mock as mock
        from types import SimpleNamespace

        from src.behemoth.api import server

        with mock.patch.object(
            server,
            "_resolve_runtime_contract",
            return_value=SimpleNamespace(
                candidates=[],
                model_month="2025-01",
                cap_pips=1.2,
            ),
        ):
            r = client.post(
                "/predict",
                json={
                    "symbol": "EURUSD",
                    "requested_volume_units": 10000,
                    "account_risk_enabled_override": True,
                },
            )
            assert r.status_code == 422
            assert "No candidates registered" in r.json()["detail"]

    def test_predict_traces_empty_response_reason(self, client, tmp_path):
        import unittest.mock as mock
        from types import SimpleNamespace

        from src.behemoth.api import server

        trace_path = tmp_path / "predict_trace.ndjson"
        dummy_cand = mock.MagicMock()
        dummy_cand.bar_ticks = 100
        dummy_cand.horizon = 6
        dummy_cand.barrier_pips = 2.0
        dummy_cand.candidate_uid = "state_a"

        orig_trace = server._config.debug_http_trace
        orig_trace_path = server._config.debug_http_trace_path
        orig_debug_run_id = server._config.debug_run_id
        try:
            server._config.debug_http_trace = True
            server._config.debug_http_trace_path = str(trace_path)
            server._config.debug_run_id = "predict_trace_case"
            with (
                mock.patch.object(
                    server,
                    "_resolve_runtime_contract",
                    return_value=SimpleNamespace(
                        symbol="EURUSD",
                        candidates=[dummy_cand],
                        model_month="2025-07",
                        cap_pips=1.2,
                        model_binding={},
                    ),
                ),
                mock.patch.object(
                    server,
                    "_apply_historical_prediction_universe_gate",
                    return_value=[],
                ),
            ):
                r = client.post(
                    "/predict",
                    json={
                        "symbol": "EURUSD",
                        "requested_volume_units": 10000,
                        "account_risk_enabled_override": True,
                        "completed_bar_ticks": [100],
                        "run_id": "predict_trace_case",
                    },
                )
                assert r.status_code == 200
                assert r.json()["predictions"] == []

            rows = [
                json.loads(line)
                for line in trace_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            response_rows = [
                row for row in rows if row["endpoint"] == "/predict" and row["phase"] == "response"
            ]
            assert len(response_rows) == 1
            assert (
                response_rows[0]["extra"]["reason"]
                == "historical_prediction_universe_gate_filtered_all_candidates"
            )
            assert response_rows[0]["extra"]["result_count"] == 0
        finally:
            server._config.debug_http_trace = orig_trace
            server._config.debug_http_trace_path = orig_trace_path
            server._config.debug_run_id = orig_debug_run_id

    def test_predict_no_model(self, client):
        """If CatBoost model isn't loaded, predict returns 503."""
        import unittest.mock as mock
        from types import SimpleNamespace

        from fastapi import HTTPException

        from src.behemoth.api import server

        dummy_cand = mock.MagicMock()
        dummy_cand.bar_ticks = 100
        dummy_cand.horizon = 12
        dummy_cand.barrier_pips = 10.0

        with (
            mock.patch.object(
                server,
                "_resolve_runtime_contract",
                return_value=SimpleNamespace(
                    candidates=[dummy_cand],
                    model_month="2025-01",
                    cap_pips=1.2,
                ),
            ),
            mock.patch.object(server, "_check_warmup", return_value=None),
            mock.patch.object(
                server,
                "_ensure_model_and_threshold",
                side_effect=HTTPException(
                    status_code=503,
                    detail="Unable to load lock-bound model for EURUSD: artifact_missing",
                ),
            ),
        ):
            r = client.post(
                "/predict",
                json={
                    "symbol": "EURUSD",
                    "requested_volume_units": 10000,
                    "account_risk_enabled_override": True,
                },
            )
            assert r.status_code == 503
            assert "Unable to load lock-bound model" in r.json()["detail"]

    def test_predict_feature_computation_fails(self, client):
        """If _state.compute_features returns None, predict returns 422."""
        import unittest.mock as mock
        from types import SimpleNamespace

        from src.behemoth.api import server

        dummy_cand = mock.MagicMock()
        dummy_cand.bar_ticks = 100
        dummy_cand.horizon = 12
        dummy_cand.barrier_pips = 10.0

        with (
            mock.patch.object(
                server,
                "_resolve_runtime_contract",
                return_value=SimpleNamespace(
                    candidates=[dummy_cand],
                    model_month="2025-01",
                    cap_pips=1.2,
                ),
            ),
            mock.patch.object(server, "_check_warmup", return_value=None),
            mock.patch.object(
                server,
                "_ensure_model_and_threshold",
                return_value=(
                    mock.MagicMock(),
                    {"threshold_exec": 0.5, "threshold_source": "test"},
                ),
            ),
            mock.patch.object(server._state, "compute_features", return_value=None),
        ):
            r = client.post(
                "/predict",
                json={
                    "symbol": "EURUSD",
                    "requested_volume_units": 10000,
                    "account_risk_enabled_override": True,
                },
            )
            assert r.status_code == 422
            assert "Feature computation failed" in r.json()["detail"]

    def test_predict_success(self, client):
        """Mock the pipeline to simulate a successful prediction return."""
        import unittest.mock as mock
        from datetime import datetime, timezone
        from types import SimpleNamespace

        from src.behemoth.api import server
        from src.behemoth.core.schemas import ModelFeatures

        dummy_cand = mock.MagicMock()
        dummy_cand.bar_ticks = 100
        dummy_cand.horizon = 24
        dummy_cand.barrier_pips = 15.0
        dummy_cand.candidate_uid = "cand1"

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

        dummy_model = mock.MagicMock()
        import numpy as np

        dummy_model.predict_proba.return_value = np.array([[0.1, 0.85]])  # 85% probability

        with (
            mock.patch.object(
                server,
                "_resolve_runtime_contract",
                return_value=SimpleNamespace(
                    candidates=[dummy_cand],
                    model_month="2025-01",
                    cap_pips=1.2,
                ),
            ),
            mock.patch.object(
                server,
                "_ensure_model_and_threshold",
                return_value=(
                    dummy_model,
                    {
                        "threshold_exec": 0.5,
                        "threshold_source": "test",
                        "rolling_threshold_days": 20,
                        "rolling_threshold_min_history": 1,
                        "execution_quantile": 0.9,
                    },
                ),
            ),
            mock.patch.object(server, "_check_warmup", return_value=None),
            mock.patch.object(server._state, "compute_features", return_value=dummy_features),
            mock.patch.object(
                server._state,
                "get_latest_close_ts",
                return_value=datetime(2025, 1, 1, tzinfo=timezone.utc),
            ),
            mock.patch.object(server._state, "get_rolling_threshold", return_value=0.5),
        ):
            snap = client.post(
                "/risk/account_risk/snapshot",
                json={
                    "symbol": "EURUSD",
                    "balance": 10000.0,
                    "equity": 10000.0,
                    "snapshot_ts": "2025-01-01T00:00:00Z",
                },
            )
            assert snap.status_code == 201
            r = client.post(
                "/predict",
                json={
                    "symbol": "EURUSD",
                    "requested_volume_units": 10000,
                    "account_risk_enabled_override": True,
                },
            )
            assert r.status_code == 200
            results = r.json()["predictions"]
            assert isinstance(results, list)
            assert len(results) == 1
            assert results[0]["pred_prob"] == 0.85
            assert results[0]["selected_exec"] == 1
            assert "risk_blocked" in results[0]
            assert results[0]["risk_metrics_snapshot"]["account_risk_enabled_effective"] is True
            assert results[0]["risk_metrics_snapshot"]["account_risk_enabled_override"] is True
            assert (
                results[0]["risk_metrics_snapshot"]["account_risk_mode_source"]
                == "request_override"
            )

    def test_predict_logs_evaluation_for_blocked_candidate(self, client):
        import unittest.mock as mock
        from datetime import datetime, timezone
        from types import SimpleNamespace

        import numpy as np

        from src.behemoth.api import server
        from src.behemoth.core.schemas import ModelFeatures

        dummy_cand = mock.MagicMock()
        dummy_cand.bar_ticks = 100
        dummy_cand.horizon = 24
        dummy_cand.barrier_pips = 15.0
        dummy_cand.candidate_uid = "cand-blocked"

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

        dummy_model = mock.MagicMock()
        dummy_model.predict_proba.return_value = np.array([[0.7, 0.3]])

        with (
            mock.patch.object(
                server,
                "_resolve_runtime_contract",
                return_value=SimpleNamespace(
                    candidates=[dummy_cand],
                    model_month="2025-01",
                    cap_pips=1.2,
                ),
            ),
            mock.patch.object(
                server,
                "_ensure_model_and_threshold",
                return_value=(
                    dummy_model,
                    {
                        "threshold_exec": 0.5,
                        "threshold_source": "test",
                        "rolling_threshold_days": 20,
                        "rolling_threshold_min_history": 1,
                        "execution_quantile": 0.9,
                    },
                ),
            ),
            mock.patch.object(server, "_check_warmup", return_value=None),
            mock.patch.object(server._state, "compute_features", return_value=dummy_features),
            mock.patch.object(
                server._state,
                "get_latest_close_ts",
                return_value=datetime(2025, 1, 1, tzinfo=timezone.utc),
            ),
            mock.patch.object(server._state, "get_rolling_threshold", return_value=0.5),
            mock.patch.object(
                server._state,
                "log_predict_evaluation",
                wraps=server._state.log_predict_evaluation,
            ) as log_predict_evaluation,
        ):
            r = client.post(
                "/predict",
                json={
                    "symbol": "EURUSD",
                    "requested_volume_units": 10000,
                    "account_risk_enabled_override": False,
                },
            )
            assert r.status_code == 200
            rows = r.json()["predictions"]
            assert len(rows) == 1
            assert rows[0]["selected_exec"] == 0
            log_predict_evaluation.assert_called_once()
            kwargs = log_predict_evaluation.call_args.kwargs
            assert "event_ts" not in kwargs
            assert kwargs["close_ts"] == datetime(2025, 1, 1, tzinfo=timezone.utc)
            assert kwargs["symbol"] == "EURUSD"
            assert kwargs["candidate_uid"] == "oco|EURUSD|100|h24|cand-blocked"
            assert kwargs["pred_prob"] == 0.3
            assert kwargs["threshold"] == 0.5
            assert kwargs["preselected_exec"] == 0
            assert kwargs["selected_exec"] == 0
            assert kwargs["threshold_blocked"] is False
            assert kwargs["threshold_block_reason"] is None
            assert kwargs["risk_blocked"] is False
            assert kwargs["risk_block_reason"] is None
            assert kwargs["model_month"] == "2025-01"
            assert kwargs["run_id"] is None

    def test_predict_live_persists_audit_history_for_threshold_blocked_candidate(self, client):
        import unittest.mock as mock
        from datetime import datetime, timezone
        from types import SimpleNamespace

        import numpy as np

        from src.behemoth.api import server
        from src.behemoth.core.schemas import ModelFeatures

        dummy_cand = mock.MagicMock()
        dummy_cand.bar_ticks = 100
        dummy_cand.horizon = 24
        dummy_cand.barrier_pips = 15.0
        dummy_cand.candidate_uid = "cand-history-gap"

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

        dummy_model = mock.MagicMock()
        dummy_model.predict_proba.return_value = np.array([[0.7, 0.3]])
        close_ts = datetime(2025, 1, 1, tzinfo=timezone.utc)
        run_id = "threshold-gap-recovery"
        candidate_uid = "oco|EURUSD|100|h24|cand-history-gap"
        original_mode = server._config.governance_mode

        try:
            server._config.governance_mode = "live"
            with (
                mock.patch.object(
                    server,
                    "_resolve_runtime_contract",
                    return_value=SimpleNamespace(
                        candidates=[dummy_cand],
                        model_month="2025-01",
                        cap_pips=1.2,
                    ),
                ),
                mock.patch.object(
                    server,
                    "_ensure_model_and_threshold",
                    return_value=(
                        dummy_model,
                        {
                            "threshold_exec": 0.5,
                            "threshold_source": "test",
                            "rolling_threshold_days": 20,
                            "rolling_threshold_min_history": 1,
                            "execution_quantile": 0.9,
                        },
                    ),
                ),
                mock.patch.object(server, "_check_warmup", return_value=None),
                mock.patch.object(server._state, "compute_features", return_value=dummy_features),
                mock.patch.object(server._state, "get_latest_close_ts", return_value=close_ts),
                mock.patch.object(server._state, "get_rolling_threshold", return_value=None),
            ):
                r = client.post(
                    "/predict",
                    json={
                        "symbol": "EURUSD",
                        "requested_volume_units": 10000,
                        "account_risk_enabled_override": False,
                        "run_id": run_id,
                    },
                )

            assert r.status_code == 200
            rows = r.json()["predictions"]
            assert len(rows) == 1
            assert rows[0]["selected_exec"] == 0
            assert rows[0]["threshold_blocked"] is True
            assert rows[0]["threshold_block_reason"] == "ROLLING_HISTORY_GAP"

            audit_row = server._state._con.execute(
                """
                SELECT close_ts, symbol, candidate_uid, pred_prob, threshold, model_month, run_id
                FROM audit_logs
                WHERE symbol = ? AND candidate_uid = ? AND run_id = ?
                ORDER BY event_ts DESC
                LIMIT 1
                """,
                ["EURUSD", candidate_uid, run_id],
            ).fetchone()
            assert audit_row is not None
            assert audit_row[0] == close_ts
            assert audit_row[1] == "EURUSD"
            assert audit_row[2] == candidate_uid
            assert audit_row[3] == 0.3
            assert audit_row[4] == 2.0
            assert audit_row[5] == "2025-01"
            assert audit_row[6] == run_id
        finally:
            server._config.governance_mode = original_mode

    def test_predict_scopes_candidates_to_completed_bar_ticks(self, client):
        import unittest.mock as mock
        from datetime import datetime, timezone
        from types import SimpleNamespace

        import numpy as np

        from src.behemoth.api import server
        from src.behemoth.core.schemas import ModelFeatures

        cand_100 = mock.MagicMock()
        cand_100.bar_ticks = 100
        cand_100.horizon = 6
        cand_100.barrier_pips = 2.0
        cand_100.candidate_uid = "cand_100"
        cand_100.regime_desc = "all;barrier=2.0"

        cand_1000 = mock.MagicMock()
        cand_1000.bar_ticks = 1000
        cand_1000.horizon = 6
        cand_1000.barrier_pips = 2.0
        cand_1000.candidate_uid = "cand_1000"
        cand_1000.regime_desc = "all;barrier=2.0"

        feat_100 = ModelFeatures(
            cost_est_pips=0.3,
            range_pips=6.0,
            ret1_pips=1.0,
            ret_z=0.4,
            ret_abs_z=0.4,
            vel_cost_units_h1=1.2,
            vel_abs_cost_units_h1=1.2,
            spread_z=0.2,
            tick_rate_z=0.1,
            hour_utc=10.0,
            hl_first=1.0,
            hl_first_mean_24=0.5,
            hl_pos_frac_mean_24=0.5,
            bar_ticks=100.0,
            horizon=6.0,
            barrier_pips=2.0,
        )
        feat_1000 = feat_100.model_copy(update={"bar_ticks": 1000.0})

        def _compute_features(*, symbol, bar_ticks, horizon, barrier_pips):
            if int(bar_ticks) == 100:
                return feat_100
            if int(bar_ticks) == 1000:
                return feat_1000
            return None

        dummy_model = mock.MagicMock()
        dummy_model.predict_proba.side_effect = [
            np.array([[0.1, 0.80]]),
            np.array([[0.1, 0.90]]),
        ]

        with (
            mock.patch.object(
                server,
                "_resolve_runtime_contract",
                return_value=SimpleNamespace(
                    candidates=[cand_100, cand_1000],
                    model_month="2025-01",
                    cap_pips=1.2,
                ),
            ),
            mock.patch.object(
                server,
                "_ensure_model_and_threshold",
                return_value=(dummy_model, {"threshold_exec": 0.5, "threshold_source": "test"}),
            ),
            mock.patch.object(server, "_check_warmup", return_value=None),
            mock.patch.object(server._state, "compute_features", side_effect=_compute_features),
            mock.patch.object(server._state, "compute_regime_quantiles", return_value={}),
            mock.patch.object(
                server._state,
                "get_latest_close_ts",
                return_value=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            ),
        ):
            r = client.post(
                "/predict",
                json={
                    "symbol": "EURUSD",
                    "requested_volume_units": 10000,
                    "account_risk_enabled_override": False,
                    "completed_bar_ticks": [100],
                },
            )
            assert r.status_code == 200
            rows = r.json()["predictions"]
            assert len(rows) == 1
            assert rows[0]["bar_ticks"] == 100
            assert rows[0]["candidate_uid"].endswith("|cand_100")

    def test_predict_returns_empty_when_completed_ticks_exclude_all_candidates(self, client):
        import unittest.mock as mock
        from datetime import datetime, timezone
        from types import SimpleNamespace

        import numpy as np

        from src.behemoth.api import server
        from src.behemoth.core.schemas import ModelFeatures

        cand_1000 = mock.MagicMock()
        cand_1000.bar_ticks = 1000
        cand_1000.horizon = 6
        cand_1000.barrier_pips = 2.0
        cand_1000.candidate_uid = "cand_1000"
        cand_1000.regime_desc = "all;barrier=2.0"

        feat_1000 = ModelFeatures(
            cost_est_pips=0.3,
            range_pips=6.0,
            ret1_pips=1.0,
            ret_z=0.4,
            ret_abs_z=0.4,
            vel_cost_units_h1=1.2,
            vel_abs_cost_units_h1=1.2,
            spread_z=0.2,
            tick_rate_z=0.1,
            hour_utc=10.0,
            hl_first=1.0,
            hl_first_mean_24=0.5,
            hl_pos_frac_mean_24=0.5,
            bar_ticks=1000.0,
            horizon=6.0,
            barrier_pips=2.0,
        )

        dummy_model = mock.MagicMock()
        dummy_model.predict_proba.return_value = np.array([[0.1, 0.90]])

        with (
            mock.patch.object(
                server,
                "_resolve_runtime_contract",
                return_value=SimpleNamespace(
                    candidates=[cand_1000],
                    model_month="2025-01",
                    cap_pips=1.2,
                ),
            ),
            mock.patch.object(
                server,
                "_ensure_model_and_threshold",
                return_value=(dummy_model, {"threshold_exec": 0.5, "threshold_source": "test"}),
            ),
            mock.patch.object(server, "_check_warmup", return_value=None),
            mock.patch.object(server._state, "compute_features", return_value=feat_1000),
            mock.patch.object(server._state, "compute_regime_quantiles", return_value={}),
            mock.patch.object(
                server._state,
                "get_latest_close_ts",
                return_value=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            ),
        ):
            r = client.post(
                "/predict",
                json={
                    "symbol": "EURUSD",
                    "requested_volume_units": 10000,
                    "account_risk_enabled_override": False,
                    "completed_bar_ticks": [100],
                },
            )
            assert r.status_code == 200
            assert r.json()["predictions"] == []

    def test_predict_override_false_disables_account_risk_guard_eval(self, client):
        import unittest.mock as mock
        from datetime import datetime, timezone
        from types import SimpleNamespace

        import numpy as np

        from src.behemoth.api import server
        from src.behemoth.core.schemas import ModelFeatures

        dummy_cand = mock.MagicMock()
        dummy_cand.bar_ticks = 100
        dummy_cand.horizon = 24
        dummy_cand.barrier_pips = 15.0
        dummy_cand.candidate_uid = "cand1"

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

        dummy_model = mock.MagicMock()
        dummy_model.predict_proba.return_value = np.array([[0.1, 0.85]])

        with (
            mock.patch.object(
                server,
                "_resolve_runtime_contract",
                return_value=SimpleNamespace(
                    candidates=[dummy_cand],
                    model_month="2025-01",
                    cap_pips=1.2,
                ),
            ),
            mock.patch.object(
                server,
                "_ensure_model_and_threshold",
                return_value=(
                    dummy_model,
                    {
                        "threshold_exec": 0.5,
                        "threshold_source": "test",
                        "rolling_threshold_days": 20,
                        "rolling_threshold_min_history": 1,
                        "execution_quantile": 0.9,
                    },
                ),
            ),
            mock.patch.object(server, "_check_warmup", return_value=None),
            mock.patch.object(server._state, "compute_features", return_value=dummy_features),
            mock.patch.object(
                server._state,
                "get_latest_close_ts",
                return_value=datetime(2025, 1, 1, tzinfo=timezone.utc),
            ),
            mock.patch.object(server._state, "get_rolling_threshold", return_value=0.5),
            mock.patch.object(
                server,
                "evaluate_trade_guard",
                side_effect=AssertionError("guard should be skipped"),
            ),
        ):
            r = client.post(
                "/predict",
                json={
                    "symbol": "EURUSD",
                    "requested_volume_units": 10000,
                    "account_risk_enabled_override": False,
                },
            )
            assert r.status_code == 200
            results = r.json()["predictions"]
            assert len(results) == 1
            assert results[0]["selected_exec"] == 1
            assert results[0]["risk_metrics_snapshot"]["account_risk_enabled_effective"] is False
            assert results[0]["risk_metrics_snapshot"]["account_risk_enabled_override"] is False

    def test_predict_warn_trade_cost_gate_keeps_selection(self, client):
        import unittest.mock as mock
        from dataclasses import replace
        from datetime import datetime, timezone
        from types import SimpleNamespace

        import numpy as np

        from src.behemoth.api import server
        from src.behemoth.core.schemas import ModelFeatures

        dummy_cand = mock.MagicMock()
        dummy_cand.bar_ticks = 100
        dummy_cand.horizon = 24
        dummy_cand.barrier_pips = 15.0
        dummy_cand.candidate_uid = "cand1"

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

        dummy_model = mock.MagicMock()
        dummy_model.predict_proba.return_value = np.array([[0.1, 0.85]])
        profile = server._account_risk_profile or server.load_account_risk_profile(
            Path("configs/research/governance/account_risk/account_risk_rules.yaml"),
            "ftmo_10k_challenge_2step",
        )
        profile = replace(
            profile,
            allocator=replace(profile.allocator, allocator_enabled=False),
        )

        with (
            mock.patch.object(
                server,
                "_resolve_runtime_contract",
                return_value=SimpleNamespace(
                    candidates=[dummy_cand],
                    model_month="2025-01",
                    cap_pips=1.2,
                ),
            ),
            mock.patch.object(
                server,
                "_ensure_model_and_threshold",
                return_value=(
                    dummy_model,
                    {
                        "threshold_exec": 0.5,
                        "threshold_source": "test",
                        "rolling_threshold_days": 20,
                        "rolling_threshold_min_history": 1,
                        "execution_quantile": 0.9,
                    },
                ),
            ),
            mock.patch.object(server, "_check_warmup", return_value=None),
            mock.patch.object(server._state, "compute_features", return_value=dummy_features),
            mock.patch.object(
                server._state,
                "get_latest_close_ts",
                return_value=datetime(2025, 1, 1, tzinfo=timezone.utc),
            ),
            mock.patch.object(server._state, "get_rolling_threshold", return_value=0.5),
            mock.patch.object(server, "_account_risk_profile", profile),
            mock.patch.object(
                server,
                "evaluate_trade_guard",
                return_value={
                    "allow_trade": True,
                    "block_reason": None,
                    "trade_cost_gate_block_reason": "ACCOUNT_RISK_COST_VIABILITY_FAIL",
                    "trade_cost_gate_mode": "warn",
                    "would_block_under_trade_cost_gate": True,
                    "estimated_trade_cost_pips": 1.2,
                    "expected_edge_proxy_pips": 0.8,
                    "net_viability_margin_pips": -0.4,
                    "cost_to_barrier_ratio": 0.08,
                },
            ),
        ):
            snap = client.post(
                "/risk/account_risk/snapshot",
                json={
                    "symbol": "EURUSD",
                    "balance": 10000.0,
                    "equity": 10000.0,
                    "snapshot_ts": "2025-01-01T00:00:00Z",
                },
            )
            assert snap.status_code == 201
            r = client.post(
                "/predict",
                json={
                    "symbol": "EURUSD",
                    "requested_volume_units": 10000,
                    "account_risk_enabled_override": True,
                },
            )
            assert r.status_code == 200
            rows = r.json()["predictions"]
            assert len(rows) == 1
            assert rows[0]["selected_exec"] == 1
            assert rows[0]["risk_blocked"] is False
            assert rows[0]["risk_metrics_snapshot"]["trade_cost_gate_mode"] == "warn"
            assert (
                rows[0]["risk_metrics_snapshot"]["trade_cost_gate_block_reason"]
                == "ACCOUNT_RISK_COST_VIABILITY_FAIL"
            )
            assert rows[0]["risk_metrics_snapshot"]["would_block_under_trade_cost_gate"] is True

    def test_predict_enforce_trade_cost_gate_blocks_selection(self, client):
        import unittest.mock as mock
        from dataclasses import replace
        from datetime import datetime, timezone
        from types import SimpleNamespace

        import numpy as np

        from src.behemoth.api import server
        from src.behemoth.core.schemas import ModelFeatures

        dummy_cand = mock.MagicMock()
        dummy_cand.bar_ticks = 100
        dummy_cand.horizon = 24
        dummy_cand.barrier_pips = 15.0
        dummy_cand.candidate_uid = "cand1"

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

        dummy_model = mock.MagicMock()
        dummy_model.predict_proba.return_value = np.array([[0.1, 0.85]])
        profile = server._account_risk_profile or server.load_account_risk_profile(
            Path("configs/research/governance/account_risk/account_risk_rules.yaml"),
            "ftmo_10k_challenge_2step",
        )
        profile = replace(
            profile,
            allocator=replace(profile.allocator, allocator_enabled=False),
        )

        with (
            mock.patch.object(
                server,
                "_resolve_runtime_contract",
                return_value=SimpleNamespace(
                    candidates=[dummy_cand],
                    model_month="2025-01",
                    cap_pips=1.2,
                ),
            ),
            mock.patch.object(
                server,
                "_ensure_model_and_threshold",
                return_value=(
                    dummy_model,
                    {
                        "threshold_exec": 0.5,
                        "threshold_source": "test",
                        "rolling_threshold_days": 20,
                        "rolling_threshold_min_history": 1,
                        "execution_quantile": 0.9,
                    },
                ),
            ),
            mock.patch.object(server, "_check_warmup", return_value=None),
            mock.patch.object(server._state, "compute_features", return_value=dummy_features),
            mock.patch.object(
                server._state,
                "get_latest_close_ts",
                return_value=datetime(2025, 1, 1, tzinfo=timezone.utc),
            ),
            mock.patch.object(server._state, "get_rolling_threshold", return_value=0.5),
            mock.patch.object(server, "_account_risk_profile", profile),
            mock.patch.object(
                server,
                "evaluate_trade_guard",
                return_value={
                    "allow_trade": False,
                    "block_reason": "ACCOUNT_RISK_COST_VIABILITY_FAIL",
                    "trade_cost_gate_block_reason": "ACCOUNT_RISK_COST_VIABILITY_FAIL",
                    "trade_cost_gate_mode": "enforce",
                    "would_block_under_trade_cost_gate": True,
                    "estimated_trade_cost_pips": 1.2,
                    "expected_edge_proxy_pips": 0.8,
                    "net_viability_margin_pips": -0.4,
                    "cost_to_barrier_ratio": 0.08,
                },
            ),
        ):
            snap = client.post(
                "/risk/account_risk/snapshot",
                json={
                    "symbol": "EURUSD",
                    "balance": 10000.0,
                    "equity": 10000.0,
                    "snapshot_ts": "2025-01-01T00:00:00Z",
                },
            )
            assert snap.status_code == 201
            r = client.post(
                "/predict",
                json={
                    "symbol": "EURUSD",
                    "requested_volume_units": 10000,
                    "account_risk_enabled_override": True,
                },
            )
            assert r.status_code == 200
            rows = r.json()["predictions"]
            assert len(rows) == 1
            assert rows[0]["selected_exec"] == 0
            assert rows[0]["risk_blocked"] is True
            assert rows[0]["risk_block_reason"] == "ACCOUNT_RISK_COST_VIABILITY_FAIL"

    def test_predict_blocks_candidate_when_regime_inactive(self, client):
        import unittest.mock as mock
        from datetime import datetime, timezone
        from types import SimpleNamespace

        import numpy as np

        from src.behemoth.api import server
        from src.behemoth.core.schemas import ModelFeatures

        dummy_cand = mock.MagicMock()
        dummy_cand.bar_ticks = 100
        dummy_cand.horizon = 6
        dummy_cand.barrier_pips = 2.0
        dummy_cand.candidate_uid = "oco_first_touch__london__k2"
        dummy_cand.regime_desc = "london;barrier=2.0"

        dummy_features = ModelFeatures(
            cost_est_pips=0.3,
            range_pips=6.0,
            ret1_pips=1.0,
            ret_z=0.4,
            ret_abs_z=0.4,
            vel_cost_units_h1=1.2,
            vel_abs_cost_units_h1=1.2,
            spread_z=0.2,
            tick_rate_z=0.1,
            hour_utc=2.0,
            hl_first=1.0,
            hl_first_mean_24=0.5,
            hl_pos_frac_mean_24=0.5,
            bar_ticks=100.0,
            horizon=6.0,
            barrier_pips=2.0,
        )
        dummy_model = mock.MagicMock()
        dummy_model.predict_proba.return_value = np.array([[0.01, 0.95]])

        with (
            mock.patch.object(
                server,
                "_resolve_runtime_contract",
                return_value=SimpleNamespace(
                    candidates=[dummy_cand],
                    model_month="2025-01",
                    cap_pips=1.2,
                ),
            ),
            mock.patch.object(
                server,
                "_ensure_model_and_threshold",
                return_value=(dummy_model, {"threshold_exec": 0.5, "threshold_source": "test"}),
            ),
            mock.patch.object(server, "_check_warmup", return_value=None),
            mock.patch.object(server._state, "compute_features", return_value=dummy_features),
            mock.patch.object(server._state, "compute_regime_quantiles", return_value={}),
            mock.patch.object(
                server._state,
                "get_latest_close_ts",
                return_value=datetime(2025, 1, 1, 2, 0, tzinfo=timezone.utc),
            ),
        ):
            snap = client.post(
                "/risk/account_risk/snapshot",
                json={
                    "symbol": "EURUSD",
                    "balance": 10000.0,
                    "equity": 10000.0,
                    "snapshot_ts": "2025-01-01T02:00:00Z",
                },
            )
            assert snap.status_code == 201
            r = client.post(
                "/predict",
                json={
                    "symbol": "EURUSD",
                    "requested_volume_units": 10000,
                    "account_risk_enabled_override": True,
                },
            )
            assert r.status_code == 200
            rows = r.json()["predictions"]
            assert len(rows) == 1
            assert rows[0]["selected_exec"] == 0
            assert rows[0]["risk_metrics_snapshot"]["regime_name"] == "london"
            assert rows[0]["risk_metrics_snapshot"]["regime_active"] is False

    def test_predict_allocator_blocks_when_budget_exceeded(self, client):
        import unittest.mock as mock
        from datetime import datetime, timezone
        from types import SimpleNamespace

        import numpy as np

        from src.behemoth.api import server
        from src.behemoth.core.schemas import ModelFeatures

        cand_small = mock.MagicMock()
        cand_small.bar_ticks = 100
        cand_small.horizon = 6
        cand_small.barrier_pips = 3.0
        cand_small.candidate_uid = "cand_small"

        cand_large = mock.MagicMock()
        cand_large.bar_ticks = 100
        cand_large.horizon = 6
        cand_large.barrier_pips = 200.0
        cand_large.candidate_uid = "cand_large"

        dummy_features = ModelFeatures(
            cost_est_pips=0.1,
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
            horizon=6.0,
            barrier_pips=3.0,
        )
        dummy_model = mock.MagicMock()
        dummy_model.predict_proba.side_effect = [
            np.array([[0.1, 0.90]]),
            np.array([[0.1, 0.85]]),
        ]

        with (
            mock.patch.object(
                server,
                "_resolve_runtime_contract",
                return_value=SimpleNamespace(
                    candidates=[cand_small, cand_large],
                    model_month="2025-01",
                    cap_pips=1.2,
                ),
            ),
            mock.patch.object(
                server,
                "_ensure_model_and_threshold",
                return_value=(
                    dummy_model,
                    {
                        "threshold_exec": 0.5,
                        "threshold_source": "test",
                        "rolling_threshold_days": 20,
                        "rolling_threshold_min_history": 1,
                        "execution_quantile": 0.9,
                    },
                ),
            ),
            mock.patch.object(server, "_check_warmup", return_value=None),
            mock.patch.object(server._state, "compute_features", return_value=dummy_features),
            mock.patch.object(
                server._state,
                "get_latest_close_ts",
                return_value=datetime(2025, 1, 1, tzinfo=timezone.utc),
            ),
            mock.patch.object(server._state, "get_rolling_threshold", return_value=0.5),
            mock.patch.object(
                server,
                "_resolve_account_risk_eval",
                return_value={
                    "enabled": True,
                    "profile_id": "ftmo_10k_challenge_2step",
                    "allow_trading": True,
                    "block_reason": None,
                    "snapshot_available": True,
                    "daily_loss_headroom": 200.0,
                    "max_loss_headroom": 200.0,
                    "daily_loss_used": 0.0,
                    "max_loss_used": 0.0,
                    "trading_day_id": "2025-01-01",
                },
            ),
        ):
            snap = client.post(
                "/risk/account_risk/snapshot",
                json={
                    "symbol": "EURUSD",
                    "balance": 10000.0,
                    "equity": 10000.0,
                    "snapshot_ts": "2025-01-01T00:00:00Z",
                },
            )
            assert snap.status_code == 201
            r = client.post(
                "/predict",
                json={
                    "symbol": "EURUSD",
                    "requested_volume_units": 10000,
                    "account_risk_enabled_override": True,
                },
            )
            assert r.status_code == 200
            rows = r.json()["predictions"]
            assert len(rows) == 2
            blocked = [
                x for x in rows if x["risk_block_reason"] == "ACCOUNT_RISK_RESERVED_BUDGET_EXCEEDED"
            ]
            admitted = [x for x in rows if x["selected_exec"] == 1]
            assert len(blocked) == 1
            assert len(admitted) == 1
            assert admitted[0]["risk_reserved"] is True
            assert admitted[0]["risk_reservation_id"] is not None


class TestCrossFamilyAllocator:
    def test_global_allocator_admits_higher_ranked_later_family(self, client):
        import unittest.mock as mock
        from datetime import datetime, timezone
        from types import SimpleNamespace

        from src.behemoth.api import server
        from src.behemoth.core.schemas import ModelFeatures
        from src.behemoth.risk.account import AccountRiskAllocator

        features = ModelFeatures(
            cost_est_pips=0.1,
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
            horizon=6.0,
            barrier_pips=3.0,
        )

        # Lower-ranked candidate from family A
        cand_a = SimpleNamespace(
            bar_ticks=100, horizon=6, barrier_pips=10.0, candidate_uid="cand_a",
        )
        decision_a = server._CandidateDecision(
            candidate_uid="oco_first_touch|EURUSD|100|h6|cand_a",
            cand=cand_a,
            features=features,
            pred_prob=0.60,
            curr_threshold=0.50,
            curr_source="test",
            preselected_exec=1,
            selected_exec=1,
            risk_blocked=False,
            risk_block_reason=None,
            risk_metrics_snapshot={"estimated_trade_cost_pips": 0.1, "expected_edge_proxy_pips": 1.0},
            trade_eval={"estimated_trade_cost_pips": 0.1, "expected_edge_proxy_pips": 1.0, "allow_trade": True},
            risk_rank_score=0.9,
            family="oco_first_touch",
            model_month="2025-01",
            cap_pips=1.2,
        )

        # Higher-ranked candidate from family B
        cand_b = SimpleNamespace(
            bar_ticks=100, horizon=6, barrier_pips=10.0, candidate_uid="cand_b",
        )
        decision_b = server._CandidateDecision(
            candidate_uid="directional|EURUSD|100|h6|cand_b",
            cand=cand_b,
            features=features,
            pred_prob=0.80,
            curr_threshold=0.50,
            curr_source="test",
            preselected_exec=1,
            selected_exec=1,
            risk_blocked=False,
            risk_block_reason=None,
            risk_metrics_snapshot={"estimated_trade_cost_pips": 0.1, "expected_edge_proxy_pips": 2.0},
            trade_eval={"estimated_trade_cost_pips": 0.1, "expected_edge_proxy_pips": 2.0, "allow_trade": True},
            risk_rank_score=1.9,
            family="directional",
            model_month="2025-01",
            cap_pips=1.2,
        )

        decisions = [decision_a, decision_b]

        allocator = AccountRiskAllocator(
            allocator_enabled=True,
            allocator_budget_fraction_daily=1.0,
            allocator_budget_fraction_max=1.0,
            allocator_min_headroom_buffer_ccy=0.0,
            allocator_reserve_pending=True,
            allocator_reserve_open=True,
            allocator_priority="rank_score",
        )
        profile = mock.MagicMock()
        profile.allocator = allocator
        profile.cost_gate.trade_cost_gate_mode = "warn"

        account_risk_eval = SimpleNamespace(
            daily_loss_headroom=12000.0,
            max_loss_headroom=12000.0,
        )

        with (
            mock.patch.object(server, "_account_risk_profile", profile),
            mock.patch.object(server._config, "account_risk_enforce_blocks", True),
            mock.patch.object(
                server._state,
                "sum_active_account_risk_reserved_loss_ccy",
                return_value=0.0,
            ),
            mock.patch.object(
                server,
                "_pip_value_per_unit_usd",
                return_value={"conversion_status": "ok", "pip_value_per_unit_usd": 0.1},
            ),
        ):
            server._run_allocator(
                sym="EURUSD",
                decisions=decisions,
                account_risk_eval=account_risk_eval,
                account_risk_enabled_effective=True,
                requested_volume_units=10000.0,
                close_ts=datetime(2025, 1, 1, tzinfo=timezone.utc),
            )

        # Higher-ranked family B should be admitted, lower-ranked family A blocked
        assert decision_b.selected_exec == 1, "higher-ranked family B should be admitted"
        assert decision_b.risk_reserved is True
        assert decision_a.selected_exec == 0, "lower-ranked family A should be blocked"
        assert decision_a.risk_block_reason == "ACCOUNT_RISK_RESERVED_BUDGET_EXCEEDED"


class TestReloadEndpoint:
    def test_reload_returns_ok(self, client):
        r = client.post("/reload")
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True


class TestTradeEndpoints:
    def test_open_trade_success(self, client):
        import unittest.mock as mock

        from src.behemoth.api import server

        with mock.patch.object(server._state, "open_trade", return_value=123):
            r = client.post(
                "/trades/open",
                json={
                    "symbol": "EURUSD",
                    "candidate_uid": "test_cand",
                    "broker_pos_id": "456",
                    "side": "BUY",
                    "entry_price": 1.1000,
                    "entry_ts": "2025-01-01T00:00:00Z",
                    "horizon": 12,
                },
            )
            assert r.status_code == 200
            assert r.json()["internal_trade_id"] == 123

    def test_open_trade_passes_family(self, client):
        import unittest.mock as mock

        from src.behemoth.api import server

        with mock.patch.object(server._state, "open_trade", return_value=123) as mock_open:
            r = client.post(
                "/trades/open",
                json={
                    "symbol": "EURUSD",
                    "candidate_uid": "test_cand",
                    "broker_pos_id": "456",
                    "side": "BUY",
                    "entry_price": 1.1000,
                    "entry_ts": "2025-01-01T00:00:00Z",
                    "horizon": 12,
                    "family": "directional",
                },
            )
            assert r.status_code == 200
            call_kwargs = mock_open.call_args.kwargs
            assert call_kwargs.get("family") == "directional"

    @pytest.mark.requires_models
    def test_touch_trade_success(self, client):
        import unittest.mock as mock

        from src.behemoth.api import server

        mock_con = mock.MagicMock()
        mock_con.execute().fetchone.return_value = [999]

        with (
            mock.patch.object(server._state, "_con", mock_con),
            mock.patch.object(server._state, "touch_trade"),
        ):
            r = client.post(
                "/trades/touch",
                json={
                    "symbol": "EURUSD",
                    "broker_pos_id": "456",
                },
            )
            assert r.status_code == 200
            assert r.json()["status"] == "ok"

    def test_update_trade_success(self, client):
        import unittest.mock as mock

        from src.behemoth.api import server

        with mock.patch.object(server._state, "update_trade"):
            r = client.post(
                "/trades/update",
                json={
                    "symbol": "EURUSD",
                    "broker_pos_id": "456",
                    "status": "CLOSED",
                    "exit_price": 1.1050,
                    "exit_ts": "2025-01-01T02:00:00Z",
                    "pnl_pips": 50.0,
                },
            )
            assert r.status_code == 200
            assert r.json()["status"] == "ok"

    def test_get_active_trades_success(self, client):
        import unittest.mock as mock

        from src.behemoth.api import server

        with mock.patch.object(server._state, "get_active_trades", return_value=[]):
            r = client.get("/trades/active?symbol=EURUSD")
            assert r.status_code == 200
            assert r.json() == []

    def test_trade_endpoints_uninitialized_state(self, client):
        from src.behemoth.api import server

        original_state = server._state
        server._state = None
        try:
            assert (
                client.post(
                    "/trades/open",
                    json={
                        "symbol": "E",
                        "candidate_uid": "C",
                        "broker_pos_id": "1",
                        "side": "BUY",
                        "entry_price": 1.0,
                        "entry_ts": "2025-01-01T00:00:00Z",
                        "horizon": 12,
                    },
                ).status_code
                == 503
            )
            assert (
                client.post("/trades/touch", json={"symbol": "E", "broker_pos_id": "1"}).status_code
                == 503
            )
            assert (
                client.post(
                    "/trades/update", json={"symbol": "E", "broker_pos_id": "1", "status": "CLOSED"}
                ).status_code
                == 503
            )
            assert client.get("/trades/active?symbol=E").status_code == 503
        finally:
            server._state = original_state

    def test_open_trade_passes_reservation_id(self, client):
        import unittest.mock as mock

        from src.behemoth.api import server

        with mock.patch.object(server._state, "open_trade", return_value="trade-abc") as mock_open:
            r = client.post(
                "/trades/open",
                json={
                    "symbol": "EURUSD",
                    "candidate_uid": "test_cand",
                    "broker_pos_id": "456",
                    "side": "BUY",
                    "entry_price": 1.1000,
                    "entry_ts": "2025-01-01T00:00:00Z",
                    "horizon": 12,
                    "reservation_id": "res-xyz-999",
                },
            )
            assert r.status_code == 200
            call_kwargs = mock_open.call_args.kwargs
            assert call_kwargs["reservation_id"] == "res-xyz-999"

    def test_update_trade_passes_close_reason_and_commission(self, client):
        import unittest.mock as mock

        from src.behemoth.api import server

        with mock.patch.object(server._state, "update_trade") as mock_update:
            r = client.post(
                "/trades/update",
                json={
                    "symbol": "EURUSD",
                    "broker_pos_id": "456",
                    "status": "CLOSED",
                    "exit_price": 1.1050,
                    "exit_ts": "2025-01-01T02:00:00Z",
                    "pnl_pips": 50.0,
                    "close_reason": "HORIZON_COMPLETED",
                    "commission_ccy": -0.46,
                },
            )
            assert r.status_code == 200
            call_kwargs = mock_update.call_args.kwargs
            assert call_kwargs["close_reason"] == "HORIZON_COMPLETED"
            assert abs(call_kwargs["commission_ccy"] - (-0.46)) < 1e-9
            assert call_kwargs["symbol"] == "EURUSD"


class TestIngestionEndpoints:
    def test_backfill_uninitialized(self, client):
        from src.behemoth.api import server

        original_state = server._state
        server._state = None
        try:
            r = client.post("/backfill", json={"symbol": "EURUSD", "ticks": []})
            assert r.status_code == 503
        finally:
            server._state = original_state

    def test_ingest_tick_uninitialized(self, client):
        from src.behemoth.api import server

        original_state = server._state
        server._state = None
        try:
            r = client.post(
                "/ticks",
                json={
                    "symbol": "EURUSD",
                    "timestamp": "2025-01-01T00:00:00Z",
                    "bid": 1.1,
                    "ask": 1.1,
                },
            )
            assert r.status_code == 503
        finally:
            server._state = original_state

    def test_backfill_success(self, client):
        import unittest.mock as mock

        from src.behemoth.api import server

        dummy_agg = mock.MagicMock()
        dummy_agg.add_ticks.return_value = ["bar1", "bar2"]

        with (
            mock.patch.dict(server._aggregators, {"EURUSD": dummy_agg}),
            mock.patch.object(server._state, "append_bar") as mock_append,
            mock.patch.object(server._state, "bar_count", return_value=300),
        ):
            r = client.post(
                "/backfill",
                json={
                    "symbol": "EURUSD",
                    "ticks": [
                        {
                            "symbol": "EURUSD",
                            "timestamp": "2025-01-01T00:00:00Z",
                            "bid": 1.1,
                            "ask": 1.1,
                        },
                    ],
                },
            )
            assert r.status_code == 201
            res = r.json()
            assert res["bars_created"] == 2
            assert mock_append.call_count == 2
            assert res["warm"] is True

    def test_ingest_tick_success(self, client):
        import unittest.mock as mock

        from src.behemoth.api import server
        from src.behemoth.runtime.tick_aggregator import IncomingTickBar

        dummy_agg = mock.MagicMock()
        dummy_bar = IncomingTickBar(
            symbol="EURUSD",
            bar_ticks=100,
            timestamp="2025-01-01T00:00:00Z",
            close_ts="2025-01-01T00:00:10Z",
            open_bid=1.0,
            high_bid=1.0,
            low_bid=1.0,
            close_bid=1.0,
            spread=0.0,
            tick_volume=100.0,
            hl_first=1.0,
            hl_pos_frac=0.5,
            high_ask=1.0,
            close_ask=1.0,
        )
        dummy_agg.add_ticks.return_value = [dummy_bar]

        with (
            mock.patch.dict(server._aggregators, {"EURUSD": dummy_agg}),
            mock.patch.object(server._state, "append_bar") as mock_append,
            mock.patch.object(server._state, "bar_count", return_value=150),
        ):
            r = client.post(
                "/ticks",
                json={
                    "symbol": "EURUSD",
                    "timestamp": "2025-01-01T00:00:10Z",
                    "bid": 1.1,
                    "ask": 1.1,
                },
            )
            assert r.status_code == 201
            res = r.json()
            assert res["tick_accepted"] is True
            assert res["bar_completed"] is True
            assert res["completed_bar_ticks"] == [100]
            assert mock_append.call_count == 1

    def test_ingest_tick_drops_duplicate_timestamp(self, client):
        import unittest.mock as mock

        from src.behemoth.api import server

        dummy_agg = mock.MagicMock()
        dummy_agg.add_ticks.return_value = []

        with (
            mock.patch.dict(server._aggregators, {100: dummy_agg}, clear=True),
            mock.patch.object(server._state, "bar_count", return_value=0),
        ):
            t = {
                "symbol": "EURUSD",
                "timestamp": "2025-01-01T00:00:10Z",
                "bid": 1.1,
                "ask": 1.1001,
            }
            r1 = client.post("/ticks", json=t)
            assert r1.status_code == 201
            assert r1.json()["tick_accepted"] is True

            r2 = client.post("/ticks", json=t)
            assert r2.status_code == 201
            body = r2.json()
            assert body["tick_accepted"] is False
            assert body["drop_reason"] == "duplicate_timestamp"
            assert body["bar_completed"] is False
            assert body["completed_bar_ticks"] == []
            assert dummy_agg.add_ticks.call_count == 1

    def test_ingest_tick_accepts_duplicate_timestamp_when_client_tick_seq_monotonic(self, client):
        import unittest.mock as mock

        from src.behemoth.api import server

        dummy_agg = mock.MagicMock()
        dummy_agg.add_ticks.return_value = []

        with (
            mock.patch.dict(server._aggregators, {100: dummy_agg}, clear=True),
            mock.patch.object(server._state, "bar_count", return_value=0),
        ):
            r1 = client.post(
                "/ticks",
                json={
                    "symbol": "EURUSD",
                    "timestamp": "2025-01-01T00:00:10Z",
                    "bid": 1.1,
                    "ask": 1.1001,
                    "client_tick_seq": 1,
                },
            )
            assert r1.status_code == 201
            assert r1.json()["tick_accepted"] is True

            r2 = client.post(
                "/ticks",
                json={
                    "symbol": "EURUSD",
                    "timestamp": "2025-01-01T00:00:10Z",
                    "bid": 1.1,
                    "ask": 1.1001,
                    "client_tick_seq": 2,
                },
            )
            assert r2.status_code == 201
            body = r2.json()
            assert body["tick_accepted"] is True
            assert body["drop_reason"] is None
            assert body["symbol_tick_seq"] == 2
            assert dummy_agg.add_ticks.call_count == 2

    def test_ingest_tick_records_raw_tick_when_enabled(self, client):
        import unittest.mock as mock

        from src.behemoth.api import server

        orig_mode = server._config.governance_mode
        orig_record = server._config.record_raw_ticks
        try:
            # Historical mode
            server._config.governance_mode = "historical"
            server._config.record_raw_ticks = True
            with (
                mock.patch.object(server._state, "record_raw_tick") as mock_raw,
                mock.patch.object(server._state, "bar_count", return_value=0),
                mock.patch.dict(
                    server._aggregators,
                    {100: mock.MagicMock(add_ticks=mock.MagicMock(return_value=[]))},
                    clear=True,
                ),
            ):
                r = client.post(
                    "/ticks",
                    json={
                        "symbol": "EURUSD",
                        "timestamp": "2025-01-01T00:00:00Z",
                        "bid": 1.1,
                        "ask": 1.1001,
                    },
                )
                assert r.status_code == 201
                mock_raw.assert_called_once()
                assert mock_raw.call_args.kwargs.get("source") == "historical_backtest"

            # Live mode
            server._config.governance_mode = "live"
            server._config.record_raw_ticks = True
            with (
                mock.patch.object(server._state, "record_raw_tick") as mock_raw,
                mock.patch.object(server._state, "bar_count", return_value=0),
                mock.patch.dict(
                    server._aggregators,
                    {100: mock.MagicMock(add_ticks=mock.MagicMock(return_value=[]))},
                    clear=True,
                ),
            ):
                r = client.post(
                    "/ticks",
                    json={
                        "symbol": "EURUSD",
                        "timestamp": "2025-01-02T00:00:00Z",
                        "bid": 1.1,
                        "ask": 1.1001,
                    },
                )
                assert r.status_code == 201
                mock_raw.assert_called_once()
                assert mock_raw.call_args.kwargs.get("source") == "live"
        finally:
            server._config.governance_mode = orig_mode
            server._config.record_raw_ticks = orig_record

    def test_ingest_tick_writes_debug_http_trace(self, client, tmp_path):
        import unittest.mock as mock

        from src.behemoth.api import server

        trace_path = tmp_path / "http_trace.ndjson"
        orig_mode = server._config.governance_mode
        orig_record = server._config.record_raw_ticks
        orig_trace = server._config.debug_http_trace
        orig_trace_path = server._config.debug_http_trace_path
        orig_debug_run_id = server._config.debug_run_id
        dummy_agg = mock.MagicMock()
        dummy_agg.add_ticks.return_value = []
        try:
            server._config.governance_mode = "historical"
            server._config.record_raw_ticks = False
            server._config.debug_http_trace = True
            server._config.debug_http_trace_path = str(trace_path)
            server._config.debug_run_id = "trace_fallback_run"
            with (
                mock.patch.dict(server._aggregators, {100: dummy_agg}, clear=True),
                mock.patch.object(server._state, "bar_count", return_value=0),
            ):
                r = client.post(
                    "/ticks",
                    json={
                        "symbol": "EURUSD",
                        "timestamp": "2025-01-01T00:00:00Z",
                        "bid": 1.1,
                        "ask": 1.1001,
                        "client_tick_seq": 7,
                        "run_id": "tick_run_01",
                    },
                )
                assert r.status_code == 201

            rows = [
                json.loads(line)
                for line in trace_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            assert len(rows) >= 3
            assert {row["phase"] for row in rows} >= {"request", "tick_result", "response"}
            assert all(row["run_id"] == "tick_run_01" for row in rows)
            assert any(
                (row.get("request") or {}).get("client_tick_seq") == 7
                for row in rows
                if isinstance(row.get("request"), dict)
            )
        finally:
            server._config.governance_mode = orig_mode
            server._config.record_raw_ticks = orig_record
            server._config.debug_http_trace = orig_trace
            server._config.debug_http_trace_path = orig_trace_path
            server._config.debug_run_id = orig_debug_run_id

    def test_ingest_tick_drops_duplicate_client_tick_seq(self, client):
        import unittest.mock as mock

        from src.behemoth.api import server

        dummy_agg = mock.MagicMock()
        dummy_agg.add_ticks.return_value = []

        with (
            mock.patch.dict(server._aggregators, {100: dummy_agg}, clear=True),
            mock.patch.object(server._state, "bar_count", return_value=0),
        ):
            r1 = client.post(
                "/ticks",
                json={
                    "symbol": "EURUSD",
                    "timestamp": "2025-01-01T00:00:10Z",
                    "bid": 1.1,
                    "ask": 1.1001,
                    "client_tick_seq": 1,
                },
            )
            assert r1.status_code == 201
            assert r1.json()["tick_accepted"] is True

            r2 = client.post(
                "/ticks",
                json={
                    "symbol": "EURUSD",
                    "timestamp": "2025-01-01T00:00:11Z",
                    "bid": 1.1,
                    "ask": 1.1001,
                    "client_tick_seq": 1,
                },
            )
            assert r2.status_code == 201
            assert r2.json()["tick_accepted"] is False
            assert r2.json()["drop_reason"] == "duplicate_client_tick_seq"

            r3 = client.post(
                "/ticks",
                json={
                    "symbol": "EURUSD",
                    "timestamp": "2025-01-01T00:00:12Z",
                    "bid": 1.1,
                    "ask": 1.1001,
                    "client_tick_seq": 0,
                },
            )
            assert r3.status_code == 201
            assert r3.json()["tick_accepted"] is False
            assert r3.json()["drop_reason"] == "non_monotonic_client_tick_seq"

    def test_ingest_ticks_batch_success(self, client):
        import unittest.mock as mock

        from src.behemoth.api import server
        from src.behemoth.runtime.tick_aggregator import IncomingTickBar

        dummy_agg = mock.MagicMock()
        dummy_bar = IncomingTickBar(
            symbol="EURUSD",
            bar_ticks=100,
            timestamp="2025-01-01T00:00:00Z",
            close_ts="2025-01-01T00:00:10Z",
            open_bid=1.0,
            high_bid=1.0,
            low_bid=1.0,
            close_bid=1.0,
            spread=0.0,
            tick_volume=100.0,
            hl_first=1.0,
            hl_pos_frac=0.5,
            high_ask=1.0,
            close_ask=1.0,
        )
        dummy_agg.add_ticks.side_effect = [[], [dummy_bar]]

        with (
            mock.patch.dict(server._aggregators, {100: dummy_agg}, clear=True),
            mock.patch.object(server._state, "append_bar") as mock_append,
            mock.patch.object(server._state, "bar_count", return_value=150),
        ):
            r = client.post(
                "/ticks/batch",
                json={
                    "symbol": "EURUSD",
                    "ticks": [
                        {
                            "symbol": "EURUSD",
                            "timestamp": "2025-01-01T00:00:10Z",
                            "bid": 1.1,
                            "ask": 1.1001,
                            "client_tick_seq": 1,
                        },
                        {
                            "symbol": "EURUSD",
                            "timestamp": "2025-01-01T00:00:11Z",
                            "bid": 1.1,
                            "ask": 1.1001,
                            "client_tick_seq": 2,
                        },
                    ],
                },
            )
            assert r.status_code == 201
            body = r.json()
            assert body["accepted_count"] == 2
            assert body["dropped_count"] == 0
            assert body["bar_completed"] is True
            assert body["completed_bar_ticks"] == [100]
            assert mock_append.call_count == 1

    def test_ingest_ticks_batch_symbol_mismatch(self, client):
        import unittest.mock as mock

        from src.behemoth.api import server

        with (
            mock.patch.object(server._state, "bar_count", return_value=0),
            mock.patch.dict(
                server._aggregators,
                {100: mock.MagicMock(add_ticks=mock.MagicMock(return_value=[]))},
                clear=True,
            ),
        ):
            r = client.post(
                "/ticks/batch",
                json={
                    "symbol": "EURUSD",
                    "ticks": [
                        {
                            "symbol": "GBPUSD",
                            "timestamp": "2025-01-01T00:00:10Z",
                            "bid": 1.1,
                            "ask": 1.1001,
                        }
                    ],
                },
            )
            assert r.status_code == 422


class TestCheckpointEndpoint:
    def test_checkpoint_returns_ok(self, client):
        r = client.get("/state/checkpoint")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert "checkpointed_at" in body

    def test_checkpoint_503_when_state_uninitialized(self, client):
        from src.behemoth.api import server

        original = server._state
        server._state = None
        try:
            r = client.get("/state/checkpoint")
            assert r.status_code == 503
        finally:
            server._state = original


@pytest.mark.requires_models
class TestPredictWarmup:
    def _seed_bars(self, sym: str, n: int, *, start_close: float = 1.30000) -> None:
        """Populate _state.tick_bars with n varied bars for the given symbol.

        Each bar has slightly different OHLC so the feature builder produces
        a non-constant feature matrix. Writes bars with bar_ticks=100 to match
        the dummy candidate used in these tests.
        """
        from datetime import datetime, timedelta, timezone

        from src.behemoth.api import server

        base_ts = datetime(2026, 4, 1, 0, 0, tzinfo=timezone.utc)
        for i in range(n):
            ts = base_ts + timedelta(minutes=i)
            close_ts = ts + timedelta(seconds=30)
            bid = start_close + 0.0001 * (i % 50) - 0.00005 * ((i * 7) % 11)
            server._state._con.execute(
                "INSERT INTO tick_bars VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    i,
                    sym.upper(),
                    100,
                    ts,
                    close_ts,
                    bid,
                    bid + 0.0005,
                    bid - 0.0005,
                    bid + 0.0001,
                    0.00015,
                    100.0 + (i % 30),
                    bid + 0.0002,
                    0.55,
                    bid + 0.00065,
                    bid + 0.00025,
                ],
            )

    def test_warmup_returns_201_with_count(self, client):
        import unittest.mock as mock
        from types import SimpleNamespace

        from src.behemoth.api import server

        dummy_cand = mock.MagicMock()
        dummy_cand.bar_ticks = 100
        dummy_cand.horizon = 24
        dummy_cand.barrier_pips = 15.0
        dummy_cand.candidate_uid = "cand1"

        dummy_model = mock.MagicMock()

        with (
            mock.patch.object(
                server,
                "_resolve_runtime_contract",
                return_value=SimpleNamespace(
                    candidates=[dummy_cand],
                    model_month="2025-01",
                    cap_pips=1.2,
                ),
            ),
            mock.patch.object(
                server,
                "_ensure_model_and_threshold",
                return_value=(dummy_model, {"threshold_exec": 0.5, "threshold_source": "test"}),
            ),
        ):
            r = client.post("/predict/warmup", json={"symbol": "GBPUSD", "run_id": "warmup"})
        assert r.status_code == 201
        body = r.json()
        assert body["ok"] is True
        assert "audit_events_written" in body
        assert isinstance(body["audit_events_written"], int)

    def test_warmup_503_when_state_uninitialized(self, client):
        from src.behemoth.api import server

        original = server._state
        server._state = None
        try:
            r = client.post("/predict/warmup", json={"symbol": "GBPUSD", "run_id": "warmup"})
            assert r.status_code == 503
        finally:
            server._state = original

    def test_warmup_writes_varied_pred_probs_per_bar(self, client):
        import unittest.mock as mock
        from types import SimpleNamespace

        import numpy as np

        from src.behemoth.api import server

        sym = "GBPUSD"
        run_id = "warmup-varied"
        self._seed_bars(sym, 340)

        dummy_cand = mock.MagicMock()
        dummy_cand.bar_ticks = 100
        dummy_cand.horizon = 24
        dummy_cand.barrier_pips = 15.0
        dummy_cand.candidate_uid = "cand1"

        dummy_model = mock.MagicMock()
        dummy_model.predict_proba.side_effect = lambda X: np.column_stack(
            [1.0 - np.linspace(0.11, 0.91, len(X)), np.linspace(0.11, 0.91, len(X))]
        )

        with (
            mock.patch.object(
                server,
                "_resolve_runtime_contract",
                return_value=SimpleNamespace(
                    candidates=[dummy_cand],
                    model_month="2025-01",
                    cap_pips=1.2,
                ),
            ),
            mock.patch.object(
                server,
                "_ensure_model_and_threshold",
                return_value=(dummy_model, {"threshold_exec": 0.5, "threshold_source": "test"}),
            ),
        ):
            r = client.post("/predict/warmup", json={"symbol": sym, "run_id": run_id})

        assert r.status_code == 201
        body = r.json()
        canonical_uid = f"oco|{sym}|{dummy_cand.bar_ticks}|h{dummy_cand.horizon}|{dummy_cand.candidate_uid}"
        assert body["audit_events_written"] >= 30
        assert body["stats"][canonical_uid]["unique_values"] >= 10

        rows = server._state._con.execute(
            """
            SELECT pred_prob
            FROM audit_logs
            WHERE symbol = ? AND run_id = ? AND candidate_uid = ?
            ORDER BY close_ts
            """,
            [sym, run_id, canonical_uid],
        ).fetchall()
        unique_probs = {round(float(row[0]), 6) for row in rows}

        assert len(rows) == body["audit_events_written"]
        assert len(unique_probs) >= 10

    def test_warmup_is_idempotent_and_purges_prior(self, client):
        import unittest.mock as mock
        from types import SimpleNamespace

        import numpy as np

        from src.behemoth.api import server

        sym = "GBPUSD"
        run_id = "warmup-idempotent"
        self._seed_bars(sym, 340)

        dummy_cand = mock.MagicMock()
        dummy_cand.bar_ticks = 100
        dummy_cand.horizon = 24
        dummy_cand.barrier_pips = 15.0
        dummy_cand.candidate_uid = "cand1"

        dummy_model = mock.MagicMock()
        dummy_model.predict_proba.side_effect = lambda X: np.column_stack(
            [1.0 - np.linspace(0.2, 0.8, len(X)), np.linspace(0.2, 0.8, len(X))]
        )

        with (
            mock.patch.object(
                server,
                "_resolve_runtime_contract",
                return_value=SimpleNamespace(
                    candidates=[dummy_cand],
                    model_month="2025-01",
                    cap_pips=1.2,
                ),
            ),
            mock.patch.object(
                server,
                "_ensure_model_and_threshold",
                return_value=(dummy_model, {"threshold_exec": 0.5, "threshold_source": "test"}),
            ),
        ):
            r1 = client.post("/predict/warmup", json={"symbol": sym, "run_id": run_id})
            r2 = client.post("/predict/warmup", json={"symbol": sym, "run_id": run_id})

        assert r1.status_code == 201
        assert r2.status_code == 201

        body1 = r1.json()
        body2 = r2.json()
        written1 = body1["audit_events_written"]

        assert body1["audit_events_purged"] == 0
        assert written1 >= 30
        assert body2["audit_events_purged"] == written1
        assert body2["audit_events_written"] == written1

        final_count = server._state._con.execute(
            "SELECT COUNT(*) FROM audit_logs WHERE symbol = ? AND run_id = ?",
            [sym, run_id],
        ).fetchone()[0]
        assert final_count == written1

    def test_warmup_refuses_degenerate_distribution(self, client):
        import unittest.mock as mock
        from datetime import datetime, timezone
        from types import SimpleNamespace

        import numpy as np

        from src.behemoth.api import server

        sym = "GBPUSD"
        run_id = "warmup-degenerate"
        self._seed_bars(sym, 340)

        server._state._con.execute(
            "INSERT INTO audit_logs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                datetime(2026, 4, 1, 0, 0, tzinfo=timezone.utc),
                datetime(2026, 4, 1, 0, 0, tzinfo=timezone.utc),
                sym,
                "sentinel",
                0.42,
                0.5,
                "{}",
                "2025-01",
                run_id,
            ],
        )

        dummy_cand = mock.MagicMock()
        dummy_cand.bar_ticks = 100
        dummy_cand.horizon = 24
        dummy_cand.barrier_pips = 15.0
        dummy_cand.candidate_uid = "cand1"

        dummy_model = mock.MagicMock()
        dummy_model.predict_proba.side_effect = lambda X: np.column_stack(
            [np.full(len(X), 0.33), np.full(len(X), 0.67)]
        )

        with (
            mock.patch.object(
                server,
                "_resolve_runtime_contract",
                return_value=SimpleNamespace(
                    candidates=[dummy_cand],
                    model_month="2025-01",
                    cap_pips=1.2,
                ),
            ),
            mock.patch.object(
                server,
                "_ensure_model_and_threshold",
                return_value=(dummy_model, {"threshold_exec": 0.5, "threshold_source": "test"}),
            ),
        ):
            r = client.post("/predict/warmup", json={"symbol": sym, "run_id": run_id})

        assert r.status_code == 500
        assert "degenerate distribution" in r.json()["detail"]

        sentinel_count = server._state._con.execute(
            """
            SELECT COUNT(*)
            FROM audit_logs
            WHERE symbol = ? AND run_id = ? AND candidate_uid = 'sentinel'
            """,
            [sym, run_id],
        ).fetchone()[0]
        assert sentinel_count == 1

    def test_warmup_preserves_prior_rows_when_no_valid_events_generated(self, client):
        import unittest.mock as mock
        from datetime import datetime, timezone
        from types import SimpleNamespace

        import pandas as pd

        from src.behemoth.api import server
        from src.behemoth.core.schemas import ModelFeatures

        sym = "GBPUSD"
        run_id = "warmup-empty-valid"
        self._seed_bars(sym, 340)

        server._state._con.execute(
            "INSERT INTO audit_logs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                datetime(2026, 4, 1, 0, 0, tzinfo=timezone.utc),
                datetime(2026, 4, 1, 0, 0, tzinfo=timezone.utc),
                sym,
                "sentinel",
                0.42,
                0.5,
                "{}",
                "2025-01",
                run_id,
            ],
        )

        dummy_cand = mock.MagicMock()
        dummy_cand.bar_ticks = 100
        dummy_cand.horizon = 24
        dummy_cand.barrier_pips = 15.0
        dummy_cand.candidate_uid = "cand1"

        dummy_model = mock.MagicMock()

        with (
            mock.patch.object(
                server,
                "_resolve_runtime_contract",
                return_value=SimpleNamespace(
                    candidates=[dummy_cand],
                    model_month="2025-01",
                    cap_pips=1.2,
                ),
            ),
            mock.patch.object(
                server,
                "_ensure_model_and_threshold",
                return_value=(dummy_model, {"threshold_exec": 0.5, "threshold_source": "test"}),
            ),
            mock.patch.object(
                server,
                "compute_feature_matrix_from_bars",
                return_value=pd.DataFrame(columns=list(ModelFeatures.model_fields)),
            ),
        ):
            r = client.post("/predict/warmup", json={"symbol": sym, "run_id": run_id})

        assert r.status_code == 201
        body = r.json()
        assert body["audit_events_purged"] == 0
        assert body["audit_events_written"] == 0
        assert body["skipped_reason"] == "no_valid_warmup_events"
        assert body["stats"] == {}
        dummy_model.predict_proba.assert_not_called()

        sentinel_count = server._state._con.execute(
            """
            SELECT COUNT(*)
            FROM audit_logs
            WHERE symbol = ? AND run_id = ? AND candidate_uid = 'sentinel'
            """,
            [sym, run_id],
        ).fetchone()[0]
        total_count = server._state._con.execute(
            "SELECT COUNT(*) FROM audit_logs WHERE symbol = ? AND run_id = ?",
            [sym, run_id],
        ).fetchone()[0]
        assert sentinel_count == 1
        assert total_count == 1


class TestRollingThresholdDrift:
    def test_drift_helper_records_ok_when_within_band(self, client):
        from src.behemoth.api import server

        server._record_rolling_threshold_drift(
            symbol="GBPUSD",
            candidate_uid="oco|GBPUSD|100|h6|cand_ok",
            rolling=0.72,
            baseline=0.70,
        )

        metrics = client.get("/metrics")

        assert metrics.status_code == 200
        assert "behemoth_rolling_threshold_drift_total" in metrics.text
        assert 'candidate="oco|GBPUSD|100|h6|cand_ok"' in metrics.text
        assert 'state="ok"' in metrics.text
        assert 'symbol="GBPUSD"' in metrics.text

    def test_drift_helper_records_drift_when_beyond_band_and_logs_warning(self, client, caplog):
        from src.behemoth.api import server

        with caplog.at_level("WARNING"):
            server._record_rolling_threshold_drift(
                symbol="USDJPY",
                candidate_uid="oco|USDJPY|100|h6|cand_drift",
                rolling=0.771,
                baseline=0.686,
            )

        metrics = client.get("/metrics")

        assert metrics.status_code == 200
        assert "behemoth_rolling_threshold_drift_total" in metrics.text
        assert 'candidate="oco|USDJPY|100|h6|cand_drift"' in metrics.text
        assert 'state="drift"' in metrics.text
        assert 'symbol="USDJPY"' in metrics.text
        assert "Rolling threshold drift" in caplog.text
        assert "USDJPY" in caplog.text

    def test_drift_helper_noop_when_baseline_missing(self, client):
        from src.behemoth.api import server

        server._record_rolling_threshold_drift(
            symbol="EURUSD",
            candidate_uid="oco|EURUSD|100|h6|cand_none",
            rolling=0.72,
            baseline=0.0,
        )

        metrics = client.get("/metrics")

        assert metrics.status_code == 200
        assert "cand_none" not in metrics.text

    @pytest.mark.requires_models
    def test_build_predictions_records_drift_for_rolling_threshold_path(self, client):
        import unittest.mock as mock
        from datetime import datetime, timezone
        from types import SimpleNamespace

        import numpy as np

        from src.behemoth.api import server
        from src.behemoth.core.schemas import ModelFeatures

        sym = "EURUSD"
        candidate_uid = "cand_roll"
        canonical_uid = f"oco|{sym}|100|h6|{candidate_uid}"
        rolling_threshold = 0.74
        threshold_exec = 0.70
        candidate = SimpleNamespace(
            bar_ticks=100,
            horizon=6,
            barrier_pips=2.0,
            candidate_uid=candidate_uid,
            regime_desc="all;barrier=2.0",
        )
        features = ModelFeatures(
            cost_est_pips=0.3,
            range_pips=6.0,
            ret1_pips=1.0,
            ret_z=0.4,
            ret_abs_z=0.4,
            vel_cost_units_h1=1.2,
            vel_abs_cost_units_h1=1.2,
            spread_z=0.2,
            tick_rate_z=0.1,
            hour_utc=10.0,
            hl_first=1.0,
            hl_first_mean_24=0.5,
            hl_pos_frac_mean_24=0.5,
            bar_ticks=100.0,
            horizon=6.0,
            barrier_pips=2.0,
        )
        model = mock.MagicMock()
        model.predict_proba.return_value = np.array([[0.4, 0.6]])

        with (
            mock.patch.object(
                server,
                "_pip_value_per_unit_usd",
                return_value={"conversion_status": "ok", "pip_value_per_unit_usd": 0.1},
            ),
            mock.patch.object(server._state, "get_rolling_threshold", return_value=rolling_threshold) as get_threshold,
            mock.patch.object(server._state, "log_predict_evaluation"),
            mock.patch.object(server, "_record_rolling_threshold_drift") as record_drift,
        ):
            results, _ = server._build_predictions(
                sym=sym,
                candidates=[candidate],
                model=model,
                base_features_by_ticks={100: features},
                regime_quantiles_by_ticks={100: {}},
                close_ts=datetime(2025, 1, 1, tzinfo=timezone.utc),
                thr_cfg={
                    "threshold_exec": threshold_exec,
                    "threshold_source": "test",
                    "rolling_threshold_days": 20,
                    "rolling_threshold_min_history": 1,
                    "execution_quantile": 0.9,
                },
                account_risk_eval={"enabled": False, "allow_trading": True, "snapshot_available": False},
                account_risk_enabled_effective=False,
                account_risk_enabled_override=False,
                requested_volume_units=10000.0,
                model_month="2025-01",
                cap_pips=1.2,
            )

        assert len(results) == 1
        get_threshold.assert_called_once_with(
            symbol=sym,
            candidate_uid=canonical_uid,
            exec_q=0.9,
            lookback_days=20,
            min_history=1,
        )
        record_drift.assert_called_once_with(
            symbol=sym,
            candidate_uid=canonical_uid,
            rolling=rolling_threshold,
            baseline=threshold_exec,
        )


class TestSeedAuditHistory:
    def test_config_has_dukascopy_ticks_dir(self):
        from src.behemoth.api import server

        assert hasattr(server._config, "dukascopy_ticks_dir")
        assert server._config.dukascopy_ticks_dir  # non-empty string

    def test_seed_503_when_state_uninitialized(self, client):
        from src.behemoth.api import server

        original = server._state
        server._state = None
        try:
            r = client.post("/state/seed_audit_history", json={})
            assert r.status_code == 503
        finally:
            server._state = original

    def test_seed_returns_201_with_few_ticks(self, client, tmp_path):
        """500 ticks = 5 bars < 289 warmup → valid 201 with total_events=0."""
        import numpy as np
        import pandas as pd

        sym = "GBPUSD"
        sym_dir = tmp_path / sym
        sym_dir.mkdir()
        now = datetime.now(tz=timezone.utc)
        ts = pd.date_range(start=now - timedelta(days=25), periods=500, freq="1s", tz="UTC")
        df = pd.DataFrame(
            {
                "timestamp": ts,
                "bid": np.full(500, 1.3000),
                "ask": np.full(500, 1.3001),
                "mid": np.full(500, 1.30005),
                "spread": np.full(500, 0.0001),
                "log_return": np.zeros(500),
            }
        )
        month_str = (now - timedelta(days=25)).strftime("%Y%m")
        df.to_parquet(sym_dir / f"{sym}_{month_str}_ticks.parquet", index=False)

        from src.behemoth.api import server

        original_dir = server._config.dukascopy_ticks_dir
        server._config.dukascopy_ticks_dir = str(tmp_path)
        try:
            r = client.post("/state/seed_audit_history", json={"symbols": [sym], "days_back": 30})
            assert r.status_code == 201
            body = r.json()
            assert body["ok"] is True
            assert isinstance(body["total_events"], int)
            assert body["total_events"] >= 0
        finally:
            server._config.dukascopy_ticks_dir = original_dir

    def test_seed_writes_events_when_sufficient_ticks(self, client, tmp_path):
        """30,000 ticks = 300 bars > 289 warmup → events written to audit_logs."""
        import unittest.mock as mock
        from types import SimpleNamespace

        import numpy as np
        import pandas as pd

        sym = "GBPUSD"
        sym_dir = tmp_path / sym
        sym_dir.mkdir()
        n = 30_000
        now = datetime.now(tz=timezone.utc)
        ts = pd.date_range(start=now - timedelta(days=25), periods=n, freq="1s", tz="UTC")
        df = pd.DataFrame(
            {
                "timestamp": ts,
                "bid": np.full(n, 1.3000),
                "ask": np.full(n, 1.3001),
                "mid": np.full(n, 1.30005),
                "spread": np.full(n, 0.0001),
                "log_return": np.zeros(n),
            }
        )
        month_str = (now - timedelta(days=25)).strftime("%Y%m")
        df.to_parquet(sym_dir / f"{sym}_{month_str}_ticks.parquet", index=False)

        from src.behemoth.api import server

        dummy_cand = mock.MagicMock()
        dummy_cand.bar_ticks = 100
        dummy_cand.horizon = 24
        dummy_cand.barrier_pips = 15.0
        dummy_cand.candidate_uid = "cand1"

        dummy_model = mock.MagicMock()
        dummy_model.predict_proba.side_effect = lambda X: np.column_stack(
            [np.full(len(X), 0.15), np.full(len(X), 0.85)]
        )

        original_dir = server._config.dukascopy_ticks_dir
        server._config.dukascopy_ticks_dir = str(tmp_path)
        try:
            with (
                mock.patch.object(
                    server,
                    "_resolve_runtime_contract",
                    return_value=SimpleNamespace(
                        candidates=[dummy_cand],
                        model_month="2025-01",
                        cap_pips=1.2,
                    ),
                ),
                mock.patch.object(
                    server,
                    "_ensure_model_and_threshold",
                    return_value=(dummy_model, {"threshold_exec": 0.5, "threshold_source": "test"}),
                ),
            ):
                r = client.post(
                    "/state/seed_audit_history", json={"symbols": [sym], "days_back": 30}
                )
            assert r.status_code == 201
            body = r.json()
            assert body["ok"] is True
            assert body["total_events"] > 0
            assert body["phase2_events"][sym] > 0
        finally:
            server._config.dukascopy_ticks_dir = original_dir

    def test_seed_skips_missing_symbol_gracefully(self, client, tmp_path):
        """Symbol with no parquet dir → 201 with 0 events for that symbol."""
        from src.behemoth.api import server

        original_dir = server._config.dukascopy_ticks_dir
        server._config.dukascopy_ticks_dir = str(tmp_path)
        try:
            r = client.post(
                "/state/seed_audit_history", json={"symbols": ["GBPUSD"], "days_back": 20}
            )
            assert r.status_code == 201
            body = r.json()
            assert body["ok"] is True
            assert body["phase2_events"].get("GBPUSD", 0) == 0
        finally:
            server._config.dukascopy_ticks_dir = original_dir

    def test_seed_422_when_ticks_dir_missing(self, client):
        """If dukascopy_ticks_dir does not exist on disk, return 422."""
        from src.behemoth.api import server

        original_dir = server._config.dukascopy_ticks_dir
        server._config.dukascopy_ticks_dir = "/nonexistent/path/that/does/not/exist"
        try:
            r = client.post("/state/seed_audit_history", json={})
            assert r.status_code == 422
        finally:
            server._config.dukascopy_ticks_dir = original_dir


class TestSeedFileLoading:
    @pytest.mark.requires_models
    def test_seed_parquet_loaded_into_audit_logs(self, client, tmp_path):
        """Seed parquets in BEHEMOTH_SEED_DIR are loaded into audit_logs on startup."""
        from src.behemoth.api import server

        # Create a seed parquet with known data
        seed_df = pd.DataFrame(
            {
                "close_ts": [pd.Timestamp("2026-03-30T12:00:00", tz="UTC")],
                "symbol": ["TESTSYM"],
                "candidate_uid": ["oco|TESTSYM|100|h300|test_state"],
                "pred_prob": [0.75],
                "threshold": [0.5],
                "features_json": ["{}"],
                "model_month": ["2026-02"],
                "run_id": ["threshold_seed"],
            }
        )
        seed_file = tmp_path / "TESTSYM_threshold_seed.parquet"
        seed_df.to_parquet(seed_file, index=False)

        # Inject seed into audit_logs via the loader function
        assert server._state is not None
        server._load_seed_files(tmp_path)

        # Verify the row was inserted
        row = server._state._con.execute(
            "SELECT pred_prob FROM audit_logs WHERE symbol = 'TESTSYM' AND run_id = 'threshold_seed'"
        ).fetchone()
        assert row is not None
        assert abs(row[0] - 0.75) < 1e-6


class TestOpenSummaryEndpoint:
    def test_fx_snapshot_and_conversion_use_canonical_close_bid_schema(self):
        from datetime import datetime, timezone

        from src.behemoth.api import server
        from src.behemoth.core.schemas import IncomingTickBar
        from src.behemoth.runtime.state import StateManager

        original_state = server._state
        server._state = StateManager()
        try:
            server._state.append_bar(
                IncomingTickBar(
                    symbol="USDJPY",
                    bar_ticks=100,
                    timestamp=datetime(2026, 4, 10, 10, 0, tzinfo=timezone.utc),
                    close_ts=datetime(2026, 4, 10, 10, 1, tzinfo=timezone.utc),
                    open_bid=145.10,
                    high_bid=145.22,
                    low_bid=145.05,
                    close_bid=145.20,
                    spread=0.02,
                    tick_volume=100.0,
                    high_ask=145.24,
                    close_ask=145.22,
                )
            )

            snapshot = server._latest_tick_price_snapshot("USDJPY")
            conversion = server._pip_value_per_unit_usd(
                "USDJPY",
                now_utc=datetime(2026, 4, 10, 10, 1, 30, tzinfo=timezone.utc),
                max_age_sec=300,
            )

            assert snapshot is not None
            assert snapshot["price"] == pytest.approx(145.20)
            assert conversion["conversion_status"] == "direct_base_usd"
            assert conversion["conversion_pair"] == "USDJPY"
            assert conversion["conversion_rate"] == pytest.approx(145.20)
            assert conversion["pip_value_per_unit_usd"] == pytest.approx(0.01 / 145.20)
        finally:
            server._state = original_state

    def test_open_summary_empty(self, client):
        """No open reservations → empty positions list."""
        r = client.get("/trades/open-summary")
        assert r.status_code == 200
        body = r.json()
        assert body["total_open"] == 0
        assert body["broker_confirmed"] == 0
        assert body["pending_broker_confirm"] == 0
        assert body["positions"] == []
        assert "as_of_utc" in body

    def test_get_last_bar_close_price_returns_none_when_no_bars(self, client):
        """StateManager returns None when tick_bars has no rows for symbol."""
        from src.behemoth.api import server
        result = server._state.get_last_bar_close_price("EURUSD")
        assert result is None

    def test_build_summary_with_pending_reservation(self, client):
        """PENDING reservation with no broker_pos_id → entry_price null, unrealized null."""
        import unittest.mock as mock
        from datetime import datetime, timedelta, timezone

        from src.behemoth.api import server

        now = datetime(2026, 4, 7, 14, 15, 0, tzinfo=timezone.utc)
        created = now - timedelta(minutes=12, seconds=30)
        fake_reservation = {
            "reservation_id": "res-001",
            "created_ts": created,
            "updated_ts": created,
            "symbol": "USDCHF",
            "candidate_uid": "cand-001",
            "broker_pos_id": None,
            "status": "PENDING",
            "reserved_loss_ccy": 10.0,
            "barrier_pips": 20.0,
            "cap_pips": 30.0,
            "cost_est_pips": 5.0,
            "volume_units": 1000.0,
            "side": "BUY",
            "source": "algo",
        }
        with (
            mock.patch.object(
                server._state,
                "list_active_account_risk_reservations",
                return_value=[fake_reservation],
            ),
            mock.patch.object(server._state, "get_last_bar_close_price", return_value=None),
            mock.patch.object(server._state, "get_all_symbols", return_value=["USDCHF"]),
        ):
            summary = server._build_open_positions_summary(server._state, now)

        assert summary["total_open"] == 1
        assert summary["broker_confirmed"] == 0
        assert summary["pending_broker_confirm"] == 1
        pos = summary["positions"][0]
        assert pos["symbol"] == "USDCHF"
        assert pos["status"] == "PENDING"
        assert pos["broker_confirmed"] is False
        assert pos["broker_pos_id"] is None
        assert pos["entry_price"] is None
        assert pos["estimated_unrealized_pips"] is None
        assert pos["open_minutes"] == 12.5

    def test_open_summary_with_pending_reservation(self, client):
        """Endpoint returns one PENDING position with correct shape."""
        import unittest.mock as mock
        from datetime import datetime, timedelta, timezone

        from src.behemoth.api import server

        now_fixed = datetime(2026, 4, 7, 14, 15, 0, tzinfo=timezone.utc)
        created = now_fixed - timedelta(minutes=5)
        fake_reservation = {
            "reservation_id": "res-001",
            "created_ts": created,
            "updated_ts": created,
            "symbol": "EURUSD",
            "candidate_uid": "cand-001",
            "broker_pos_id": None,
            "status": "PENDING",
            "reserved_loss_ccy": 10.0,
            "barrier_pips": 20.0,
            "cap_pips": 30.0,
            "cost_est_pips": 5.0,
            "volume_units": 1000.0,
            "side": "BUY",
            "source": "algo",
        }
        with (
            mock.patch.object(
                server._state,
                "list_active_account_risk_reservations",
                return_value=[fake_reservation],
            ),
            mock.patch.object(server._state, "get_last_bar_close_price", return_value=None),
            mock.patch.object(server._state, "get_all_symbols", return_value=["EURUSD"]),
        ):
            r = client.get("/trades/open-summary")

        assert r.status_code == 200
        body = r.json()
        assert body["total_open"] == 1
        assert body["pending_broker_confirm"] == 1
        assert len(body["positions"]) == 1
        pos = body["positions"][0]
        assert pos["symbol"] == "EURUSD"
        assert pos["status"] == "PENDING"
        assert pos["broker_confirmed"] is False
        assert pos["entry_price"] is None
        assert pos["estimated_unrealized_pips"] is None

    def test_open_summary_uninitialized_state(self, client):
        """Returns 503 when state manager is not initialized."""
        from src.behemoth.api import server

        original = server._state
        server._state = None
        try:
            r = client.get("/trades/open-summary")
            assert r.status_code == 503
        finally:
            server._state = original

    def test_position_summary_writer_skips_without_persist_path(self, client):
        """Writer loop body does not write when persist_db_path is falsy."""
        import asyncio
        import unittest.mock as mock

        from src.behemoth.api import server

        original_path = server._config.persist_db_path
        server._config.persist_db_path = ""
        written_paths = []
        real_write_text = Path.write_text

        def tracking_write_text(self, *args, **kwargs):
            written_paths.append(str(self))
            return real_write_text(self, *args, **kwargs)

        server._config.persist_db_path = ""
        try:
            with mock.patch.object(Path, "write_text", tracking_write_text):
                # Run one iteration of the loop body manually
                coro = server._write_position_summary_loop()
                try:
                    # Drive the coroutine until the first sleep (which we interrupt)
                    loop = asyncio.new_event_loop()
                    task = loop.create_task(coro)
                    loop.call_soon(task.cancel)
                    loop.run_until_complete(asyncio.gather(task, return_exceptions=True))
                    loop.close()
                except Exception:
                    pass
        finally:
            server._config.persist_db_path = original_path

        assert not any("live_position_summary" in p for p in written_paths)


class TestPredictionFamilyField:
    def test_oco_prediction_has_family_field(self):
        from src.behemoth.core.schemas import OcoPrediction
        p = OcoPrediction(
            symbol="EURUSD",
            close_ts=datetime(2026, 5, 1, tzinfo=timezone.utc),
            candidate_uid="directional|eurusd|100|h4|k1",
            pred_prob=0.75,
            threshold_exec=0.5,
            selected_exec=1,
            bar_ticks=100,
            horizon=4,
            barrier_pips=10.0,
            cap_pips=1.5,
            threshold_source="test",
            model_month="2026-04",
            family="directional",
        )
        assert p.family == "directional"

    def test_trade_open_request_has_family_field(self):
        from src.behemoth.core.schemas import TradeOpenRequest
        req = TradeOpenRequest(
            symbol="EURUSD",
            candidate_uid="directional|eurusd|100|h4|k1",
            broker_pos_id="bp-1",
            side="Buy",
            entry_price=1.1000,
            entry_ts=datetime(2026, 5, 1, tzinfo=timezone.utc),
            horizon=4,
            family="directional",
        )
        assert req.family == "directional"
