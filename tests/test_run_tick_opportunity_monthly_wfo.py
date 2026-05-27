import pandas as pd
import pytest

from scripts.run_tick_opportunity_monthly_wfo import _wfo_monthly


def test_parse_requested_families_accepts_yaml_list_and_csv_string():
    from scripts.run_tick_opportunity_monthly_wfo import _parse_requested_families

    assert _parse_requested_families(["directional", "pullback"]) == [
        "directional",
        "pullback",
    ]
    assert _parse_requested_families("directional, pullback") == [
        "directional",
        "pullback",
    ]


def test_parse_requested_families_rejects_unknown_family():
    from scripts.run_tick_opportunity_monthly_wfo import _parse_requested_families

    with pytest.raises(ValueError, match="unknown family"):
        _parse_requested_families("directional,not_a_family")


def test_libraries_for_requested_families_groups_by_event_builder_library():
    from scripts.run_tick_opportunity_monthly_wfo import _libraries_for_requested_families

    assert _libraries_for_requested_families(["oco_first_touch", "directional"]) == [
        "directional",
        "oco",
    ]


def test_plan_wfo_inputs_uses_families_when_present_and_keeps_legacy_library():
    from scripts.run_tick_opportunity_monthly_wfo import _plan_wfo_inputs

    assert _plan_wfo_inputs({"library": "oco", "families": ""}) == {
        "oco": None,
    }
    assert _plan_wfo_inputs({"library": "both", "families": ["directional"]}) == {
        "directional": ["directional"],
    }


def test_filter_candidate_families_keeps_only_requested_family_rows():
    from scripts.run_tick_opportunity_monthly_wfo import _filter_candidate_families

    cands = pd.DataFrame(
        {
            "symbol": ["EURUSD", "EURUSD", "EURUSD"],
            "family": ["directional", "pullback", "oco_first_touch"],
            "train_count": [10, 10, 10],
            "mean_gross_pips_train": [0.1, 0.1, 0.1],
        }
    )

    out = _filter_candidate_families(cands, families=["pullback"])

    assert out["family"].tolist() == ["pullback"]


def test_filter_candidate_families_fails_loud_when_family_column_missing():
    from scripts.run_tick_opportunity_monthly_wfo import _filter_candidate_families

    with pytest.raises(ValueError, match="family"):
        _filter_candidate_families(pd.DataFrame({"symbol": ["EURUSD"]}), families=["directional"])


def test_build_events_filters_requested_family_before_candidate_cap(tmp_path):
    import scripts.run_tick_opportunity_monthly_wfo as wfo

    candidate_dir = tmp_path / "candidates"
    dataset_dir = tmp_path / "datasets"
    candidate_dir.mkdir()
    dataset_dir.mkdir()
    pd.DataFrame(
        {
            "symbol": ["EURUSD", "EURUSD"],
            "family": ["pullback", "directional"],
            "bar_ticks": [100, 100],
            "horizon": [6, 6],
            "train_count": [99_999, 1_000],
            "mean_gross_pips_train": [10.0, 0.1],
        }
    ).to_csv(candidate_dir / "EURUSD_directional_candidates.csv", index=False)
    (dataset_dir / "EURUSD_100tick_velocity.parquet").touch()
    seen: dict[str, list[str]] = {}

    def fake_prepare_frame(path, *, symbol, horizons):
        seen["horizons"] = list(horizons)
        return pd.DataFrame(
            {
                "year": [2024, 2025],
                "close_ts": pd.to_datetime(
                    ["2024-01-01", "2025-01-01"], utc=True
                ),
            }
        )

    def fake_build_directional_events(**kwargs):
        seen["families"] = kwargs["cands"]["family"].tolist()
        return pd.DataFrame()

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(wfo, "_prepare_frame", fake_prepare_frame)
    monkeypatch.setattr(wfo, "_quantiles", lambda df: {})
    monkeypatch.setattr(wfo, "_build_directional_events", fake_build_directional_events)
    try:
        wfo._build_events_for_library(
            library="directional",
            families=["directional"],
            symbol="EURUSD",
            dataset_dir=dataset_dir,
            candidate_dir=candidate_dir,
            train_years_fit={2024},
            eval_year=2025,
            eval_start_ts=None,
            eval_end_ts_excl=None,
            min_candidate_train_count=0,
            max_candidates=1,
            max_events_per_candidate=10,
            oco_include_no_touch=False,
            oco_hold_mode="from_touch",
        )
    finally:
        monkeypatch.undo()

    assert seen["families"] == ["directional"]


def test_build_events_for_unsupported_family_fails_loud_with_family_name(tmp_path):
    import scripts.run_tick_opportunity_monthly_wfo as wfo

    with pytest.raises(NotImplementedError, match="not_a_family"):
        wfo._build_events_for_library(
            library="directional",
            families=["not_a_family"],
            symbol="EURUSD",
            dataset_dir=tmp_path,
            candidate_dir=tmp_path,
            train_years_fit={2024},
            eval_year=2025,
            eval_start_ts=None,
            eval_end_ts_excl=None,
            min_candidate_train_count=0,
            max_candidates=1,
            max_events_per_candidate=10,
            oco_include_no_touch=False,
            oco_hold_mode="from_touch",
        )


def test_wfo_monthly_empty_input_returns_four_values():
    """An empty events frame must return the same 4-tuple shape as the
    normal path (metrics, thresholds, preds, importance).

    The caller unpacks 4 values; the empty-input early return previously
    yielded only 3, crashing retrain-all whenever a library/window mined
    no events (e.g. the look-ahead-free OCO universe in an eval window).
    """
    result = _wfo_monthly(
        pd.DataFrame(),
        library="oco",
        months=[],
        score_start_ts=None,
        rolling_train_months=3,
        min_month_train_rows=0,
        min_month_test_rows=0,
        min_candidate_rows_in_train_window=0,
        threshold_quantiles=[0.9],
        threshold_mode="static",
        rolling_threshold_days=0,
        rolling_threshold_min_history=0,
        execution_quantile=0.9,
        seed=0,
    )
    assert len(result) == 4
    m, t, p, imp = result
    assert all(isinstance(x, pd.DataFrame) and x.empty for x in (m, t, p, imp))


def test_wfo_main_overwrites_stale_predictions_when_empty(tmp_path, monkeypatch):
    """A WFO run that produces no OCO predictions must still overwrite the
    per-library predictions parquet with a current empty file, not leave a
    stale one from a prior run in place."""
    import pandas as pd

    import scripts.run_tick_opportunity_monthly_wfo as wfo

    out_dir = tmp_path / "wfo_out"
    out_dir.mkdir()
    stale = out_dir / "EURUSD_oco_monthly_predictions.parquet"
    pd.DataFrame({"candidate_uid": ["oco|EURUSD|100|h1|stale__all__k2"]}).to_parquet(
        stale, index=False
    )

    written = wfo._write_library_outputs(
        out_dir=out_dir,
        symbol="EURUSD",
        lib="oco",
        m=pd.DataFrame(),
        t=pd.DataFrame(),
        p=pd.DataFrame(),
        imp=pd.DataFrame(),
    )
    assert stale.exists()
    assert pd.read_parquet(stale).empty
    assert set(written) == {
        out_dir / "EURUSD_oco_monthly_metrics.csv",
        out_dir / "EURUSD_oco_monthly_thresholds.csv",
        out_dir / "EURUSD_oco_monthly_predictions.parquet",
        out_dir / "EURUSD_oco_monthly_importance.csv",
    }


def test_feature_cols_includes_microstructure_features_when_present():
    from scripts.run_tick_opportunity_monthly_wfo import (
        _MICROSTRUCTURE_FEATURES,
        _feature_cols,
    )

    cols = [
        "cost_est_pips", "range_pips", "ret1_pips", "ret_z", "ret_abs_z",
        "vel_cost_units_h1", "vel_abs_cost_units_h1", "spread_z",
        "tick_rate_z", "hour_utc", "hl_first", "hl_first_mean_24",
        "hl_pos_frac_mean_24", "bar_ticks", "horizon", "barrier_pips",
    ] + _MICROSTRUCTURE_FEATURES
    df = pd.DataFrame({c: [0.0] for c in cols})
    feats = _feature_cols(df)
    for c in _MICROSTRUCTURE_FEATURES:
        assert c in feats


def test_feature_cols_omits_microstructure_features_when_absent():
    from scripts.run_tick_opportunity_monthly_wfo import (
        _MICROSTRUCTURE_FEATURES,
        _feature_cols,
    )

    df = pd.DataFrame({c: [0.0] for c in ["ret_z", "bar_ticks", "horizon"]})
    feats = _feature_cols(df)
    for c in _MICROSTRUCTURE_FEATURES:
        assert c not in feats
    assert "bar_ticks" in feats
    assert "horizon" in feats


def test_check_microstructure_columns_raises_when_all_absent():
    from scripts.run_tick_opportunity_monthly_wfo import _check_microstructure_columns

    df = pd.DataFrame({"ret_z": [0.1, 0.2], "bar_ticks": [1000, 1000]})
    with pytest.raises(FileNotFoundError, match="rebuild-all"):
        _check_microstructure_columns(df)


def test_check_microstructure_columns_passes_when_all_present():
    from scripts.run_tick_opportunity_monthly_wfo import (
        _MICROSTRUCTURE_FEATURES,
        _check_microstructure_columns,
    )

    df = pd.DataFrame({c: [0.0, 1.0] for c in _MICROSTRUCTURE_FEATURES})
    _check_microstructure_columns(df)  # must not raise


def test_check_microstructure_columns_warns_on_partial_absence(capsys):
    from scripts.run_tick_opportunity_monthly_wfo import (
        _MICROSTRUCTURE_FEATURES,
        _check_microstructure_columns,
    )

    df = pd.DataFrame({c: [0.0, 1.0] for c in _MICROSTRUCTURE_FEATURES[:2]})
    _check_microstructure_columns(df)  # must not raise
    captured = capsys.readouterr()
    assert "warning:" in captured.out
    assert "missing" in captured.out


def test_symbol_local_family_set_excludes_cross_symbol_families() -> None:
    import scripts.run_tick_opportunity_monthly_wfo as wfo

    assert {
        "oco_first_touch",
        "oco_asymmetric",
        "directional",
        "directional_inverse",
        "directional_run",
        "double_touch",
        "pullback",
        "no_touch",
    } == wfo.SYMBOL_LOCAL_WFO_FAMILIES
    assert "dollar_residual" not in wfo.SYMBOL_LOCAL_WFO_FAMILIES
    assert "dispersion_rank" not in wfo.SYMBOL_LOCAL_WFO_FAMILIES
    assert "lead_lag" not in wfo.SYMBOL_LOCAL_WFO_FAMILIES


def test_registry_event_builder_uses_family_protocol_for_pullback(tmp_path) -> None:
    import numpy as np
    import pandas as pd

    import scripts.run_tick_opportunity_monthly_wfo as wfo
    from scripts.mining_family import FAMILY_REGISTRY

    orig_entry = FAMILY_REGISTRY["pullback"].entry_indices
    orig_gross = FAMILY_REGISTRY["pullback"].measure_gross

    def _fake_entry(frame, mask, params):
        return np.array([0, 1])

    def _fake_gross(frame, entries, params):
        return np.array([1.5, -0.5])

    FAMILY_REGISTRY["pullback"].entry_indices = _fake_entry
    FAMILY_REGISTRY["pullback"].measure_gross = _fake_gross

    try:
        df = pd.DataFrame(
            {
                "close_ts": pd.to_datetime(
                    ["2025-01-01T00:00:00Z", "2025-01-01T00:01:00Z", "2025-01-01T00:02:00Z"],
                    utc=True,
                ),
                "year": [2025, 2025, 2025],
                "ret1_pips": [1.0, -2.0, 3.0],
                "y_fwd_pips_h1": [2.0, -1.0, 0.0],
                "_dir_side_h1": [1, -1, 1],
                "cost_est_pips": [0.1, 0.1, 0.1],
                "range_pips": [1.0, 1.0, 1.0],
                "ret_z": [0.0, 0.0, 0.0],
                "ret_abs_z": [0.0, 0.0, 0.0],
                "vel_cost_units_h1": [1.0, 1.0, 1.0],
                "vel_abs_cost_units_h1": [1.0, 1.0, 1.0],
                "spread_z": [0.0, 0.0, 0.0],
                "tick_rate_z": [0.0, 0.0, 0.0],
                "hour_utc": [0, 0, 0],
                "hl_first": [0, 0, 0],
                "hl_first_mean_24": [0.0, 0.0, 0.0],
                "hl_pos_frac_mean_24": [0.5, 0.5, 0.5],
                "tick_burst_score": [0.0, 0.0, 0.0],
                "quote_revision_rate_z": [0.0, 0.0, 0.0],
                "directional_persistence_8": [0.0, 0.0, 0.0],
                "signed_flow_24": [0.0, 0.0, 0.0],
                "vol_cluster_score": [0.0, 0.0, 0.0],
            }
        )
        cands = pd.DataFrame(
            {
                "symbol": ["EURUSD"],
                "bar_ticks": [100],
                "horizon": [1],
                "family": ["pullback"],
                "state_id": ["pullback__all__up_M2.0_R0.5_wI3_wP5_wR3_h1"],
                "regime_desc": ["all"],
                "quality_tier": ["A"],
                "quality_score": [3],
                "annualized_test_fills": [100.0],
                "mean_gross_pips_test": [0.5],
            }
        )

        events = wfo._build_registry_family_events(
            split_name="eval",
            df=df,
            q_fit={},
            cands=cands,
            max_events_per_candidate=10,
            bar_ticks=100,
            dataset_dir=tmp_path,
            horizons=[1],
        )

        assert not events.empty
        assert set(events["family"]) == {"pullback"}
        assert events["library"].unique().tolist() == ["pullback"]
    finally:
        FAMILY_REGISTRY["pullback"].entry_indices = orig_entry
        FAMILY_REGISTRY["pullback"].measure_gross = orig_gross


def test_wfo_monthly_invokes_guard_on_stale_data():
    from scripts.run_tick_opportunity_monthly_wfo import _wfo_monthly

    df = pd.DataFrame({"ret_z": [0.1, 0.2], "bar_ticks": [1000, 1000]})
    with pytest.raises(FileNotFoundError, match="rebuild-all"):
        _wfo_monthly(
            df,
            library="oco",
            months=[],
            score_start_ts=None,
            rolling_train_months=3,
            min_month_train_rows=0,
            min_month_test_rows=0,
            min_candidate_rows_in_train_window=0,
            threshold_quantiles=[0.9],
            threshold_mode="static",
            rolling_threshold_days=0,
            rolling_threshold_min_history=0,
            execution_quantile=0.9,
            seed=0,
        )


def test_cross_symbol_families_plan_to_their_candidate_libraries() -> None:
    from scripts.run_tick_opportunity_monthly_wfo import _plan_wfo_inputs

    assert _plan_wfo_inputs({"library": "both", "families": ["dollar_residual"]}) == {
        "dollar_residual": ["dollar_residual"]
    }
    assert _plan_wfo_inputs({"library": "both", "families": ["dispersion_rank", "lead_lag"]}) == {
        "dispersion_rank": ["dispersion_rank"],
        "lead_lag": ["lead_lag"],
    }


def test_cross_symbol_replay_support_gate_accepts_cross_symbol_families() -> None:
    import scripts.run_tick_opportunity_monthly_wfo as wfo

    wfo._ensure_wfo_replay_supported(["dollar_residual", "dispersion_rank", "lead_lag"])
