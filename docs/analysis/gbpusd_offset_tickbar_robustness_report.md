# Offset Tick-Bar Robustness Report

- symbol: `GBPUSD`
- classification: `stable`
- study_mode: `adaptive`
- retention_mode: `compact`
- offsets_evaluated: `1`
- offsets_screened: `1`
- offsets_refined: `0`
- degraded_offsets: `0`
- failed_pipeline_offsets: `0`
- no_qualifying_states_offsets: `0`

## By Offset

| symbol   |   offset |   selected_rows_total |   trade_rows_total |   mean_gross_pips |   mean_net_pips |   lb95_trade_mean_gross_pips |   lb95_trade_mean_net_pips |   positive_months |   reduced_core_state_jaccard |   candidate_uid_close_ts_overlap_rate |   execution_fill_rate |   execution_no_touch_rate |   execution_overshoot_p95_pips |   warmup_skip_months_count | tick_exact_pass   | capacity_pass_monthly_or_annual   |   selected_rows_delta_pct |   trade_rows_delta_pct |   mean_gross_pips_delta |   mean_net_pips_delta |   lb95_trade_mean_gross_pips_delta |   lb95_trade_mean_net_pips_delta |   positive_months_delta |   execution_fill_rate_delta |   execution_no_touch_rate_delta |   execution_overshoot_p95_delta | offset_status   | degrade_reasons   | failure_reason   | prediction_path                                                                                                           | reduced_state_schedule_csv                                                                                                                | stop_limit_detail_csv                                                                                                           |
|:---------|---------:|----------------------:|-------------------:|------------------:|----------------:|-----------------------------:|---------------------------:|------------------:|-----------------------------:|--------------------------------------:|----------------------:|--------------------------:|-------------------------------:|---------------------------:|:------------------|:----------------------------------|--------------------------:|-----------------------:|------------------------:|----------------------:|-----------------------------------:|---------------------------------:|------------------------:|----------------------------:|--------------------------------:|--------------------------------:|:----------------|:------------------|:-----------------|:--------------------------------------------------------------------------------------------------------------------------|:------------------------------------------------------------------------------------------------------------------------------------------|:--------------------------------------------------------------------------------------------------------------------------------|
| GBPUSD   |        0 |                 12170 |              12054 |           2.57316 |         2.60202 |                      2.62007 |                    2.52204 |                11 |                            1 |                                     1 |              0.990468 |                0.00141241 |                            0.5 |                          3 | True              | True                              |                         0 |                      0 |                       0 |                     0 |                                  0 |                                0 |                       0 |                           0 |                               0 |                               0 | ok              |                   |                  | data/analysis/tick_opportunity_mining/offset_robustness/runs/GBPUSD/offset_000/wfo/GBPUSD_oco_monthly_predictions.parquet | data/analysis/tick_opportunity_mining/offset_robustness/runs/GBPUSD/offset_000/reduced_core_rolling/GBPUSD_oco_reduced_state_schedule.csv | data/analysis/tick_opportunity_mining/offset_robustness/runs/GBPUSD/offset_000/stop_limit/GBPUSD_stop_limit_tickfill_detail.csv |

## Warmup Sensitivity

_empty_

## API Confirmation

_empty_

## State Overlap

| symbol   |   offset | test_month   |   baseline_state_count |   offset_state_count |   intersection_count |   union_count |   state_jaccard |
|:---------|---------:|:-------------|-----------------------:|---------------------:|---------------------:|--------------:|----------------:|
| GBPUSD   |        0 | 2025-04      |                      2 |                    2 |                    2 |             2 |               1 |
| GBPUSD   |        0 | 2025-05      |                      2 |                    2 |                    2 |             2 |               1 |
| GBPUSD   |        0 | 2025-06      |                      2 |                    2 |                    2 |             2 |               1 |
| GBPUSD   |        0 | 2025-07      |                      2 |                    2 |                    2 |             2 |               1 |
| GBPUSD   |        0 | 2025-08      |                      2 |                    2 |                    2 |             2 |               1 |
| GBPUSD   |        0 | 2025-09      |                      2 |                    2 |                    2 |             2 |               1 |
| GBPUSD   |        0 | 2025-10      |                      3 |                    3 |                    3 |             3 |               1 |
| GBPUSD   |        0 | 2025-11      |                      3 |                    3 |                    3 |             3 |               1 |
| GBPUSD   |        0 | 2025-12      |                      3 |                    3 |                    3 |             3 |               1 |
| GBPUSD   |        0 | 2026-01      |                      2 |                    2 |                    2 |             2 |               1 |
| GBPUSD   |        0 | 2026-02      |                      3 |                    3 |                    3 |             3 |               1 |
| GBPUSD   |        0 | 2026-03      |                      3 |                    3 |                    3 |             3 |               1 |
| GBPUSD   |        0 | ALL          |                     11 |                   11 |                   11 |            11 |               1 |

## Interpretation

- `stable`: no advisory threshold breaches, no API sampled-offset failures, and warmup plateau observed across sampled offsets.
- `mildly_phase_sensitive`: repo pipeline completes but one or more advisory degradation thresholds breach.
- `materially_phase_sensitive`: sampled API parity fails, pipeline fails on one or more offsets, warmup plateau is not reached, or offsets lose qualifying states.

## Notes

- `mean_net_pips` and `lb95_trade_mean_net_pips` use the Stage 8 `costplus_0.10` fields because there is no plain net field in the current downstream artifacts.
- full_precision_warmup_bars: `289`
- minimum_usable_warmup_bars: `73`
