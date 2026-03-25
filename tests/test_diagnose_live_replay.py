from __future__ import annotations

import json
from pathlib import Path

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
    assert {"timestamp", "close_ts", "open", "high", "low", "close", "spread", "tick_volume", "hl_first", "hl_pos_frac"}.issubset(
        set(bars.columns)
    )
    assert float(bars[0, "open"]) == pytest.approx(1.1000)
    assert float(bars[0, "close"]) == pytest.approx(1.1099)


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
            "timestamp": pd.date_range("2026-03-01T00:00:00Z", periods=2, freq="100s", tz="UTC").to_list(),
            "close_ts": pd.date_range("2026-03-01T00:01:39Z", periods=2, freq="100s", tz="UTC").to_list(),
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
    assert float(results[1, "gap"]) == pytest.approx(0.25)
    assert int(results[0, "selected"]) == 0


def test_score_bars_filters_invalid_feature_rows_before_inference(monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts import diagnose_live_replay as module

    bars = pl.DataFrame(
        {
            "timestamp": pd.date_range("2026-03-01T00:00:00Z", periods=2, freq="100s", tz="UTC").to_list(),
            "close_ts": pd.to_datetime(["2026-03-01T00:01:39Z", "2026-03-02T00:01:39Z"], utc=True).to_list(),
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
        return pd.DataFrame({"feat_1": [1.0, float("nan")], "feat_2": [3.0, 4.0]})

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
    assert results[0, "close_ts"] == pd.Timestamp("2026-03-01T00:01:39Z")


def test_score_bars_applies_threshold_schedule_per_row_date(monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts import diagnose_live_replay as module

    bars = pl.DataFrame(
        {
            "timestamp": pd.date_range("2026-03-01T00:00:00Z", periods=2, freq="100s", tz="UTC").to_list(),
            "close_ts": pd.to_datetime(["2026-03-01T00:01:39Z", "2026-03-02T00:01:39Z"], utc=True).to_list(),
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
            return [[0.2, 0.58], [0.2, 0.57]]

    monkeypatch.setattr(module, "compute_feature_matrix_from_bars", fake_features)

    results = module._score_bars(
        bars=bars,
        symbol="EURUSD",
        state={"state_id": "s1"},
        model=DummyModel(),
        thresholds={"threshold_exec": 0.55, "threshold_schedule": {"2026-03-01": 0.60}},
        threshold_exec=0.55,
    )

    assert results.height == 2
    assert float(results[0, "threshold"]) == pytest.approx(0.60)
    assert float(results[1, "threshold"]) == pytest.approx(0.55)
    assert int(results[0, "selected"]) == 0
    assert int(results[1, "selected"]) == 1


def test_section_near_miss_orders_by_gap_ascending() -> None:
    from scripts.diagnose_live_replay import _section_near_miss

    results = pl.DataFrame(
        {
            "close_ts": pd.to_datetime(["2026-03-01T00:00:00Z", "2026-03-01T00:01:00Z"], utc=True).to_list(),
            "state_id": ["s1", "s2"],
            "pred_prob": [0.51, 0.53],
            "threshold": [0.55, 0.60],
            "selected": [0, 0],
            "gap": [-0.04, -0.07],
        }
    )

    lines = _section_near_miss(results)
    text = "\n".join(lines)

    assert text.index("s2") < text.index("s1")


def test_section_sensitivity_sweep_includes_expected_thresholds() -> None:
    from scripts.diagnose_live_replay import _section_sensitivity_sweep

    results = pl.DataFrame(
        {
            "close_ts": pd.to_datetime(["2026-03-01T00:00:00Z", "2026-03-01T00:01:00Z"], utc=True).to_list(),
            "state_id": ["s1", "s1"],
            "pred_prob": [0.51, 0.68],
            "threshold": [0.55, 0.55],
            "selected": [0, 1],
            "gap": [-0.04, 0.13],
        }
    )

    lines = _section_sensitivity_sweep(results)
    text = "\n".join(lines)

    assert "0.50" in text
    assert "0.65" in text
