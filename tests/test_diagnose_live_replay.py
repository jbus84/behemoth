from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
import pytest


def _tick_frame(n: int) -> pl.DataFrame:
    ts = pd.date_range("2026-03-01T00:00:00Z", periods=n, freq="s", tz="UTC")
    base = pd.Series(range(n), dtype="float64")
    return pl.DataFrame(
        {
            "timestamp": ts.to_list(),
            "bid": (1.1000 + base * 0.0001).to_list(),
            "ask": (1.1003 + base * 0.0001).to_list(),
            "mid": (9.9001 + base * 0.0001).to_list(),
            "spread": [0.0002] * n,
            "log_return": [0.0] * n,
        }
    )


def test_build_bars_from_ticks_aggregates_1000_ticks_into_10_bars() -> None:
    from scripts.diagnose_live_replay import _build_bars_from_ticks

    bars = _build_bars_from_ticks(_tick_frame(1000))

    assert bars.height == 10
    assert {
        "timestamp",
        "close_ts",
        "open",
        "high",
        "low",
        "close",
        "spread",
        "tick_volume",
        "hl_first",
        "hl_pos_frac",
    }.issubset(set(bars.columns))
    assert float(bars[0, "open"]) == pytest.approx(1.1000)
    assert float(bars[0, "close"]) == pytest.approx(1.1099)
    assert float(bars[0, "open"]) != pytest.approx(9.9001)


def test_build_bars_from_ticks_drops_partial_final_bar() -> None:
    from scripts.diagnose_live_replay import _build_bars_from_ticks

    bars = _build_bars_from_ticks(_tick_frame(150))

    assert bars.height == 1
    assert int(bars[0, "tick_volume"]) == 100


def test_load_states_reads_state_universe_rows(tmp_path: Path) -> None:
    from scripts.diagnose_live_replay import _load_states

    governance_dir = tmp_path / "gov"
    governance_dir.mkdir()
    lock = {
        "state_universe": {
            "rows": [
                {"symbol": "EURUSD", "bar_ticks": 100, "horizon": 6, "state_id": "s1"},
                {"symbol": "EURUSD", "bar_ticks": 100, "horizon": 8, "state_id": "s2"},
            ]
        }
    }
    (governance_dir / "eurusd_oco_live_lock.json").write_text(json.dumps(lock), encoding="utf-8")

    rows = _load_states("EURUSD", str(governance_dir))

    assert len(rows) == 2
    assert rows[0]["state_id"] == "s1"


def test_load_thresholds_reads_threshold_json(tmp_path: Path) -> None:
    from scripts.diagnose_live_replay import _load_thresholds

    models_dir = tmp_path / "models" / "oco"
    models_dir.mkdir(parents=True)
    payload = {
        "symbol": "EURUSD",
        "model_month": "2026-02",
        "threshold_exec": 0.61,
        "threshold_schedule": {"2026-03-01": 0.60},
        "features": ["a", "b"],
    }
    (models_dir / "EURUSD_model_2026-02.json").write_text(json.dumps(payload), encoding="utf-8")

    thresholds, threshold_exec = _load_thresholds("EURUSD", str(models_dir), "2026-02")

    assert thresholds["model_month"] == "2026-02"
    assert threshold_exec == pytest.approx(0.61)


def test_score_bars_returns_required_columns(monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts import diagnose_live_replay as module

    bars = pl.DataFrame(
        {
            "timestamp": pd.date_range(
                "2026-03-01T00:00:00Z", periods=2, freq="100s", tz="UTC"
            ).to_list(),
            "close_ts": pd.date_range(
                "2026-03-01T00:01:39Z", periods=2, freq="100s", tz="UTC"
            ).to_list(),
            "open": [1.0, 1.1],
            "high": [1.2, 1.3],
            "low": [0.9, 1.0],
            "close": [1.15, 1.25],
            "spread": [0.0002, 0.0002],
            "tick_volume": [100, 100],
            "hl_first": [1, -1],
            "hl_pos_frac": [0.4, 0.6],
        }
    )

    def fake_features(*args, **kwargs):
        return pd.DataFrame({"feat_1": [1.0, 2.0], "feat_2": [3.0, 4.0]})

    class DummyModel:
        def predict_proba(self, matrix):
            return [[0.7, 0.3], [0.2, 0.8]]

    monkeypatch.setattr(module, "compute_feature_matrix_from_bars", fake_features)

    results = module._score_bars(
        bars=bars,
        symbol="EURUSD",
        state={"state_id": "s1"},
        model=DummyModel(),
        thresholds={"threshold_exec": 0.55},
        threshold_exec=0.55,
    )

    assert {"close_ts", "state_id", "pred_prob", "threshold", "selected", "gap"}.issubset(
        set(results.columns)
    )
    assert results.height == 2
    assert float(results[1, "gap"]) == pytest.approx(-0.25)
    assert int(results[0, "selected"]) == 0


def test_score_bars_filters_invalid_feature_rows_before_inference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts import diagnose_live_replay as module

    bars = pl.DataFrame(
        {
            "timestamp": pd.date_range(
                "2026-03-01T00:00:00Z", periods=289, freq="100s", tz="UTC"
            ).to_list(),
            "close_ts": pd.date_range(
                "2026-03-01T00:01:39Z", periods=289, freq="100s", tz="UTC"
            ).to_list(),
            "open": [1.0 + i * 0.001 for i in range(289)],
            "high": [1.1 + i * 0.001 for i in range(289)],
            "low": [0.9 + i * 0.001 for i in range(289)],
            "close": [1.05 + i * 0.001 for i in range(289)],
            "spread": [0.0002] * 289,
            "tick_volume": [100] * 289,
            "hl_first": [1] * 289,
            "hl_pos_frac": [0.4] * 289,
        }
    )

    def fake_features(*args, **kwargs):
        rows = [{"feat_1": float("nan"), "feat_2": float("nan")} for _ in range(288)]
        rows.append({"feat_1": 1.0, "feat_2": 3.0})
        return pd.DataFrame(rows)

    calls: dict[str, tuple[int, int]] = {}

    class DummyModel:
        def predict_proba(self, matrix):
            calls["shape"] = matrix.shape
            return [[0.2, 0.8]]

    monkeypatch.setattr(module, "compute_feature_matrix_from_bars", fake_features)

    results = module._score_bars(
        bars=bars,
        symbol="EURUSD",
        state={"state_id": "s1"},
        model=DummyModel(),
        thresholds={"threshold_exec": 0.55},
        threshold_exec=0.55,
    )

    assert calls["shape"] == (1, 2)
    assert results.height == 1
    assert float(results[0, "pred_prob"]) == pytest.approx(0.8)
    assert results[0, "close_ts"] == pd.Timestamp("2026-03-01T08:01:39Z")


def test_score_bars_applies_threshold_schedule_per_row_date_and_blocks_expired(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts import diagnose_live_replay as module

    bars = pl.DataFrame(
        {
            "timestamp": pd.date_range(
                "2026-03-01T00:00:00Z", periods=3, freq="100s", tz="UTC"
            ).to_list(),
            "close_ts": pd.to_datetime(
                ["2026-03-01T00:01:39Z", "2026-03-02T00:01:39Z", "2026-03-03T00:01:39Z"], utc=True
            ).to_list(),
            "open": [1.0, 1.1, 1.2],
            "high": [1.2, 1.3, 1.4],
            "low": [0.9, 1.0, 1.1],
            "close": [1.15, 1.25, 1.35],
            "spread": [0.0002, 0.0002, 0.0002],
            "tick_volume": [100, 100, 100],
            "hl_first": [1, -1, 1],
            "hl_pos_frac": [0.4, 0.6, 0.5],
        }
    )

    def fake_features(*args, **kwargs):
        return pd.DataFrame({"feat_1": [1.0, 2.0, 3.0], "feat_2": [3.0, 4.0, 5.0]})

    class DummyModel:
        def predict_proba(self, matrix):
            return [[0.2, 0.58], [0.2, 0.57], [0.2, 0.70]]

    monkeypatch.setattr(module, "compute_feature_matrix_from_bars", fake_features)

    results = module._score_bars(
        bars=bars,
        symbol="EURUSD",
        state={"state_id": "s1"},
        model=DummyModel(),
        thresholds={
            "threshold_exec": 0.55,
            "threshold_schedule": {"2026-03-01": 0.60},
            "rolling_threshold_days": 20,
            "rolling_threshold_min_history": 2,
            "execution_quantile": 0.5,
        },
        threshold_exec=0.55,
    )

    assert results.height == 3
    assert float(results[0, "threshold"]) == pytest.approx(0.60)
    assert float(results[1, "threshold"]) == pytest.approx(2.0)
    assert float(results[2, "threshold"]) == pytest.approx(0.575)
    assert int(results[0, "selected"]) == 0
    assert int(results[1, "selected"]) == 0
    assert int(results[2, "selected"]) == 1


def test_score_bars_uses_rolling_threshold_success_path(monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts import diagnose_live_replay as module

    bars = pl.DataFrame(
        {
            "timestamp": pd.date_range(
                "2026-03-01T00:00:00Z", periods=3, freq="100s", tz="UTC"
            ).to_list(),
            "close_ts": pd.to_datetime(
                ["2026-03-01T00:01:39Z", "2026-03-02T00:01:39Z", "2026-03-03T00:01:39Z"], utc=True
            ).to_list(),
            "open": [1.0, 1.1, 1.2],
            "high": [1.2, 1.3, 1.4],
            "low": [0.9, 1.0, 1.1],
            "close": [1.15, 1.25, 1.35],
            "spread": [0.0002, 0.0002, 0.0002],
            "tick_volume": [100, 100, 100],
            "hl_first": [1, -1, 1],
            "hl_pos_frac": [0.4, 0.6, 0.5],
        }
    )

    def fake_features(*args, **kwargs):
        return pd.DataFrame({"feat_1": [1.0, 2.0, 3.0], "feat_2": [3.0, 4.0, 5.0]})

    class DummyModel:
        def predict_proba(self, matrix):
            return [[0.2, 0.58], [0.2, 0.57], [0.2, 0.70]]

    monkeypatch.setattr(module, "compute_feature_matrix_from_bars", fake_features)

    results = module._score_bars(
        bars=bars,
        symbol="EURUSD",
        state={"state_id": "s1"},
        model=DummyModel(),
        thresholds={
            "threshold_exec": 0.55,
            "rolling_threshold_days": 20,
            "rolling_threshold_min_history": 2,
            "execution_quantile": 0.5,
        },
        threshold_exec=0.55,
    )

    assert results.height == 3
    assert float(results[2, "threshold"]) == pytest.approx(0.575)
    assert int(results[2, "selected"]) == 1
    assert int(results[1, "selected"]) == 0


def test_score_bars_applies_regime_gating(monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts import diagnose_live_replay as module

    bars = pl.DataFrame(
        {
            "timestamp": pd.date_range(
                "2026-03-01T00:00:00Z", periods=2, freq="100s", tz="UTC"
            ).to_list(),
            "close_ts": pd.to_datetime(
                ["2026-03-01T00:01:39Z", "2026-03-01T14:01:39Z"], utc=True
            ).to_list(),
            "open": [1.0, 1.1],
            "high": [1.2, 1.3],
            "low": [0.9, 1.0],
            "close": [1.15, 1.25],
            "spread": [0.0002, 0.0002],
            "tick_volume": [100, 100],
            "hl_first": [1, -1],
            "hl_pos_frac": [0.4, 0.6],
        }
    )

    def fake_features(*args, **kwargs):
        return pd.DataFrame({"feat_1": [1.0, 2.0], "feat_2": [3.0, 4.0]})

    class DummyModel:
        def predict_proba(self, matrix):
            return [[0.2, 0.8], [0.2, 0.8]]

    monkeypatch.setattr(module, "compute_feature_matrix_from_bars", fake_features)

    results = module._score_bars(
        bars=bars,
        symbol="EURUSD",
        state={
            "state_id": "s1",
            "regime_desc": "ny_overlap",
            "bar_ticks": 100,
            "horizon": 6,
            "barrier_pips": 2.0,
        },
        model=DummyModel(),
        thresholds={"threshold_exec": 0.55},
        threshold_exec=0.55,
    )

    assert bool(results[0, "regime_active"]) is False
    assert bool(results[1, "regime_active"]) is True
    assert int(results[0, "selected"]) == 0
    assert int(results[1, "selected"]) == 1


def test_score_bars_uses_causal_quantile_regime_thresholds(monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts import diagnose_live_replay as module

    bars = pl.DataFrame(
        {
            "timestamp": pd.date_range(
                "2026-03-01T00:00:00Z", periods=3, freq="100s", tz="UTC"
            ).to_list(),
            "close_ts": pd.to_datetime(
                ["2026-03-01T00:01:39Z", "2026-03-01T00:03:19Z", "2026-03-01T00:04:59Z"], utc=True
            ).to_list(),
            "open": [1.0, 1.1, 1.2],
            "high": [1.2, 1.3, 1.4],
            "low": [0.9, 1.0, 1.1],
            "close": [1.15, 1.25, 1.35],
            "spread": [0.0002, 0.0002, 0.0002],
            "tick_volume": [100, 100, 100],
            "hl_first": [1, -1, 1],
            "hl_pos_frac": [0.4, 0.6, 0.5],
        }
    )

    def fake_features(*args, **kwargs):
        return pd.DataFrame(
            {
                "range_pips": [10.0, 20.0, 30.0],
                "cost_est_pips": [1.0, 1.0, 1.0],
                "vel_abs_cost_units_h1": [1.0, 1.0, 1.0],
            }
        )

    calls: list[int] = []

    def fake_quantiles(frame, *, symbol):
        calls.append(len(frame))
        n = len(frame)
        return {"rng_q80": {1: 9.0, 2: 19.0, 3: 29.0}.get(n, 29.0)}

    class DummyModel:
        def predict_proba(self, matrix):
            return [[0.05, 0.95], [0.05, 0.95], [0.05, 0.95]]

    monkeypatch.setattr(module, "compute_feature_matrix_from_bars", fake_features)
    monkeypatch.setattr(module, "compute_regime_quantiles_from_bars", fake_quantiles)

    results = module._score_bars(
        bars=bars,
        symbol="EURUSD",
        state={
            "state_id": "s1",
            "regime_desc": "high_range_q80",
            "bar_ticks": 100,
            "horizon": 6,
            "barrier_pips": 2.0,
        },
        model=DummyModel(),
        thresholds={"threshold_exec": 0.55},
        threshold_exec=0.55,
    )

    assert calls == [1, 2, 3]
    assert int(results[0, "selected"]) == 1
    assert int(results[1, "selected"]) == 1
    assert int(results[2, "selected"]) == 1


def test_score_bars_preserves_source_indices_for_causal_quantiles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts import diagnose_live_replay as module

    bars = pl.DataFrame(
        {
            "timestamp": pd.date_range(
                "2026-03-01T00:00:00Z", periods=4, freq="100s", tz="UTC"
            ).to_list(),
            "close_ts": pd.to_datetime(
                [
                    "2026-03-01T00:01:39Z",
                    "2026-03-01T00:03:19Z",
                    "2026-03-01T00:04:59Z",
                    "2026-03-01T00:06:39Z",
                ],
                utc=True,
            ).to_list(),
            "open": [1.0, 1.1, 1.2, 1.3],
            "high": [1.2, 1.3, 1.4, 1.5],
            "low": [0.9, 1.0, 1.1, 1.2],
            "close": [1.15, 1.25, 1.35, 1.45],
            "spread": [0.0002, 0.0002, 0.0002, 0.0002],
            "tick_volume": [100, 100, 100, 100],
            "hl_first": [1, -1, 1, -1],
            "hl_pos_frac": [0.4, 0.6, 0.5, 0.7],
        }
    )

    def fake_features(*args, **kwargs):
        return pd.DataFrame(
            {
                "range_pips": [10.0, np.nan, 30.0, 40.0],
                "cost_est_pips": [1.0, np.nan, 1.0, 1.0],
                "vel_abs_cost_units_h1": [1.0, np.nan, 1.0, 1.0],
            }
        )

    calls: list[int] = []

    def fake_quantiles(frame, *, symbol):
        calls.append(len(frame))
        return {"rng_q80": 9.0}

    class DummyModel:
        def predict_proba(self, matrix):
            return [[0.05, 0.95], [0.05, 0.95], [0.05, 0.95]]

    monkeypatch.setattr(module, "compute_feature_matrix_from_bars", fake_features)
    monkeypatch.setattr(module, "compute_regime_quantiles_from_bars", fake_quantiles)

    results = module._score_bars(
        bars=bars,
        symbol="EURUSD",
        state={
            "state_id": "s1",
            "regime_desc": "high_range_q80",
            "bar_ticks": 100,
            "horizon": 6,
            "barrier_pips": 2.0,
        },
        model=DummyModel(),
        thresholds={"threshold_exec": 0.55},
        threshold_exec=0.55,
    )

    assert calls == [1, 3, 4]
    assert results.height == 3


def test_score_bars_skips_non_100_tick_states(monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts import diagnose_live_replay as module

    bars = pl.DataFrame(
        {
            "timestamp": pd.date_range(
                "2026-03-01T00:00:00Z", periods=3, freq="100s", tz="UTC"
            ).to_list(),
            "close_ts": pd.to_datetime(
                ["2026-03-01T00:01:39Z", "2026-03-02T00:01:39Z", "2026-03-03T00:01:39Z"], utc=True
            ).to_list(),
            "open": [1.0, 1.1, 1.2],
            "high": [1.2, 1.3, 1.4],
            "low": [0.9, 1.0, 1.1],
            "close": [1.15, 1.25, 1.35],
            "spread": [0.0002, 0.0002, 0.0002],
            "tick_volume": [100, 100, 100],
            "hl_first": [1, -1, 1],
            "hl_pos_frac": [0.4, 0.6, 0.5],
        }
    )

    def fake_features(*args, **kwargs):
        return pd.DataFrame({"feat_1": [1.0, 2.0, 3.0], "feat_2": [3.0, 4.0, 5.0]})

    class DummyModel:
        def predict_proba(self, matrix):
            pytest.fail("non-100 bar_ticks states should not score")

    monkeypatch.setattr(module, "compute_feature_matrix_from_bars", fake_features)

    results = module._score_bars(
        bars=bars,
        symbol="EURUSD",
        state={"state_id": "s1", "bar_ticks": 200},
        model=DummyModel(),
        thresholds={"threshold_exec": 0.55},
        threshold_exec=0.55,
    )

    assert results.is_empty()


def test_section_near_miss_orders_by_gap_ascending() -> None:
    from scripts.diagnose_live_replay import _section_near_miss

    results = pl.DataFrame(
        {
            "symbol": ["EURUSD", "EURUSD"],
            "candidate_uid": ["oco|EURUSD|100|h6|s1", "oco|EURUSD|100|h6|s1"],
            "state_id": ["s1", "s1"],
            "close_ts": pd.to_datetime(
                ["2026-03-01T00:00:00Z", "2026-03-01T00:01:00Z"], utc=True
            ).to_list(),
            "pred_prob": [0.53, 0.51],
            "threshold": [0.55, 0.55],
            "selected": [0, 0],
            "gap": [0.02, 0.04],
        }
    )

    lines = _section_near_miss(results)
    text = "\n".join(lines)

    assert text.index("0.02") < text.index("0.04")


def test_section_score_distribution_outputs_percentiles() -> None:
    from scripts.diagnose_live_replay import _section_score_distribution

    results = pl.DataFrame(
        {
            "symbol": ["EURUSD"] * 4,
            "candidate_uid": ["oco|EURUSD|100|h6|s1"] * 4,
            "state_id": ["s1"] * 4,
            "close_ts": pd.date_range(
                "2026-03-01T00:00:00Z", periods=4, freq="100s", tz="UTC"
            ).to_list(),
            "pred_prob": [0.1, 0.2, 0.3, 0.4],
            "threshold": [0.5, 0.5, 0.5, 0.5],
            "selected": [0, 0, 0, 0],
            "gap": [0.4, 0.3, 0.2, 0.1],
        }
    )

    text = "\n".join(_section_score_distribution(results))

    for token in ["p25", "p50", "p75", "p90", "p95", "p99", "threshold", "n"]:
        assert token in text


def test_section_sensitivity_sweep_includes_expected_thresholds() -> None:
    from scripts.diagnose_live_replay import _section_sensitivity_sweep

    results = pl.DataFrame(
        {
            "symbol": ["EURUSD", "EURUSD"],
            "candidate_uid": ["oco|EURUSD|100|h6|s1", "oco|EURUSD|100|h6|s2"],
            "state_id": ["s1", "s2"],
            "close_ts": pd.to_datetime(
                ["2026-03-01T00:00:00Z", "2026-03-01T00:01:00Z"], utc=True
            ).to_list(),
            "pred_prob": [0.51, 0.68],
            "threshold": [0.55, 0.55],
            "selected": [0, 1],
            "gap": [0.04, -0.13],
            "regime_active": [True, True],
        }
    )

    lines = _section_sensitivity_sweep(results)
    text = "\n".join(lines)

    assert "0.50" in text
    assert "0.65" in text
    assert "trade_count" in text
    assert "freq_per_100_bars" in text
    assert "s1" in text and "s2" in text


def test_section_score_drift_reports_rolling_50_bar_average() -> None:
    from scripts.diagnose_live_replay import _section_score_drift

    rows = []
    for i in range(100):
        rows.append(
            {
                "symbol": "EURUSD",
                "candidate_uid": f"oco|EURUSD|100|h6|s{i % 2}",
                "state_id": f"s{i % 2}",
                "close_ts": pd.Timestamp("2026-03-01T00:00:00Z") + pd.Timedelta(minutes=i),
                "pred_prob": float(i),
                "threshold": 0.5,
                "selected": 0,
                "gap": 0.5 - float(i),
            }
        )
    results = pl.DataFrame(rows)

    text = "\n".join(_section_score_drift(results))

    assert "rolling_50_pred_prob" in text
    assert "EURUSD" in text
    assert "24.5" in text or "74.5" in text
