import pandas as pd

from scripts.run_tick_opportunity_monthly_wfo import _wfo_monthly


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
