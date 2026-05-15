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
