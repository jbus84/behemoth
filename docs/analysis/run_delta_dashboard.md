# Run Delta Dashboard

- generated_at_utc: `2026-02-27T11:13:02Z`
- registry_csv: `data/analysis/tick_opportunity_mining/run_registry.csv`
- summary_csv: `data/analysis/tick_opportunity_mining/run_delta_summary.csv`
- metric_changes_csv: `data/analysis/tick_opportunity_mining/run_delta_metric_changes.csv`
- gate_changes_csv: `data/analysis/tick_opportunity_mining/run_delta_gate_changes.csv`

## Summary
| baseline_run_id      | latest_run_id        | baseline_generated_at_utc   | latest_generated_at_utc   |   metric_rows_baseline |   metric_rows_latest |   metric_rows_changed |   gate_rows_changed |   symbols_total_baseline |   symbols_total_latest |   symbols_pass_baseline |   symbols_pass_latest |   docs_failed_baseline |   docs_failed_latest |
|:---------------------|:---------------------|:----------------------------|:--------------------------|-----------------------:|---------------------:|----------------------:|--------------------:|-------------------------:|-----------------------:|------------------------:|----------------------:|-----------------------:|---------------------:|
| run_20260227T104945Z | run_20260227T111254Z | 2026-02-27T09:11:26Z        | 2026-02-27T11:12:11Z      |                     99 |                  102 |                    12 |                   0 |                        3 |                      3 |                       3 |                     3 |                      0 |                    0 |

## Gate Changes
_empty_

## Top Metric Changes
|   stage_id | symbol   | metric_id                        |   metric_value_baseline | note_baseline                                    |   metric_value_latest | note_latest                                                                          |      delta |   abs_delta | changed   |
|-----------:|:---------|:---------------------------------|------------------------:|:-------------------------------------------------|----------------------:|:-------------------------------------------------------------------------------------|-----------:|------------:|:----------|
|          1 | USDJPY   | D18_clock_jitter_cv              |              10.4984    | Inter-bar timing jitter coefficient of variation |              0.608004 | Normalized inter-bar timing jitter CV after hour-of-week baseline adjustment         |  -9.89041  |    9.89041  | True      |
|          1 | EURUSD   | D18_clock_jitter_cv              |               7.90046   | Inter-bar timing jitter coefficient of variation |              0.63644  | Normalized inter-bar timing jitter CV after hour-of-week baseline adjustment         |  -7.26402  |    7.26402  | True      |
|          1 | GBPUSD   | D18_clock_jitter_cv              |               7.41284   | Inter-bar timing jitter coefficient of variation |              0.592694 | Normalized inter-bar timing jitter CV after hour-of-week baseline adjustment         |  -6.82015  |    6.82015  | True      |
|          8 | EURUSD   | T03_post_worst_month_recovery    |              -0.0974308 | One-month rebound after worst reduced-core month |              0.915934 | Next-month / abs(worst-month) gross ratio after worst reduced-core month             |   1.01336  |    1.01336  | True      |
|          4 | GBPUSD   | E11_session_overshoot_dispersion |               1.20518   | CV of mean overshoot across UTC hours            |              0.26181  | CV of mean overshoot across sessions after causal rolling session caps (20D, q=0.90) |  -0.943368 |    0.943368 | True      |
|          8 | USDJPY   | T03_post_worst_month_recovery    |               0.116104  | One-month rebound after worst reduced-core month |              1.04299  | Next-month / abs(worst-month) gross ratio after worst reduced-core month             |   0.926882 |    0.926882 | True      |
|          4 | USDJPY   | E11_session_overshoot_dispersion |               0.958511  | CV of mean overshoot across UTC hours            |              0.133612 | CV of mean overshoot across sessions after causal rolling session caps (20D, q=0.90) |  -0.824899 |    0.824899 | True      |
|          4 | EURUSD   | E11_session_overshoot_dispersion |               0.851988  | CV of mean overshoot across UTC hours            |              0.199265 | CV of mean overshoot across sessions after causal rolling session caps (20D, q=0.90) |  -0.652723 |    0.652723 | True      |
|          8 | GBPUSD   | T03_post_worst_month_recovery    |               0.765238  | One-month rebound after worst reduced-core month |              1.33224  | Next-month / abs(worst-month) gross ratio after worst reduced-core month             |   0.567002 |    0.567002 | True      |
|          1 | EURUSD   | D18_clock_jitter_cv_raw          |             nan         | nan                                              |              7.90046  | Raw inter-bar timing jitter coefficient of variation                                 | nan        |  nan        | True      |
|          1 | GBPUSD   | D18_clock_jitter_cv_raw          |             nan         | nan                                              |              7.41284  | Raw inter-bar timing jitter coefficient of variation                                 | nan        |  nan        | True      |
|          1 | USDJPY   | D18_clock_jitter_cv_raw          |             nan         | nan                                              |             10.4984   | Raw inter-bar timing jitter coefficient of variation                                 | nan        |  nan        | True      |