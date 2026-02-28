# USDJPY OCO Reduced-Core Rolling Selection

## Setup
- family_keep: `oco_first_touch_clean`
- barrier_keep: `[2.0, 3.0]`
- horizon_keep: `[5, 6]`
- locked_quantile: `0.9`
- selection_mode: `auto`
- execution_mode: `gross`
- state_train_months: `3`
- min_train_months: `3`
- overlap_corr_max: `0.85`
- overlap_divergence_max: `0.4`
- max_state_churn: `0.45`
- max_top_state_share: `0.35`
- max_state_hhi: `0.25`
- enforce_state_stability_gates: `False`
- max_states/min_states: `12/4`
- strict_gate_only: `True`

## Summary
| symbol   |   locked_quantile | selection_mode   | execution_mode   |   state_train_months |   months_total |   months_scored |   rows_total |   signal_rows_total |   mean_gross_pips |   monthly_mean_gross_pips |   lb95_month_mean_gross_pips |   mean_signal_pips |   monthly_mean_signal_pips |   lb95_month_mean_signal_pips |   positive_months |   positive_months_signal |   avg_month_rows |   avg_month_signal_rows |   fill_rate_overall |   annualized_rows |   capacity_floor_monthly |   capacity_floor_annual | capacity_pass_monthly_or_annual   |   max_state_churn |   max_top_state_share |   max_state_hhi |   stability_months_pass |
|:---------|------------------:|:-----------------|:-----------------|---------------------:|---------------:|----------------:|-------------:|--------------------:|------------------:|--------------------------:|-----------------------------:|-------------------:|---------------------------:|------------------------------:|------------------:|-------------------------:|-----------------:|------------------------:|--------------------:|------------------:|-------------------------:|------------------------:|:----------------------------------|------------------:|----------------------:|----------------:|------------------------:|
| USDJPY   |               0.9 | auto             | gross            |                    3 |              9 |               0 |            0 |                   0 |               nan |                       nan |                          nan |                nan |                        nan |                           nan |                 0 |                        0 |                0 |                       0 |                 nan |                 0 |                     3000 |                    5000 | False                             |              0.45 |                  0.35 |            0.25 |                       0 |

## Reduced State Universe
_empty_

## Monthly Portfolio
| symbol   | test_month   | train_months            |   states_selected |   rows |   signal_rows |   fill_rate |   mean_gross_pips |   mean_signal_pips |   median_gross_pips |   pos_rate |   state_churn_rate |   top_state_share |   state_hhi |   stability_pass | status         |
|:---------|:-------------|:------------------------|------------------:|-------:|--------------:|------------:|------------------:|-------------------:|--------------------:|-----------:|-------------------:|------------------:|------------:|-----------------:|:---------------|
| USDJPY   | 2025-04      |                         |                 0 |      0 |             0 |         nan |               nan |                nan |                 nan |        nan |                nan |               nan |         nan |              nan | warmup_skip    |
| USDJPY   | 2025-05      | 2025-04                 |                 0 |      0 |             0 |         nan |               nan |                nan |                 nan |        nan |                nan |               nan |         nan |              nan | warmup_skip    |
| USDJPY   | 2025-06      | 2025-04,2025-05         |                 0 |      0 |             0 |         nan |               nan |                nan |                 nan |        nan |                nan |               nan |         nan |              nan | warmup_skip    |
| USDJPY   | 2025-07      | 2025-04,2025-05,2025-06 |                 0 |      0 |             0 |         nan |               nan |                nan |                 nan |        nan |                nan |               nan |         nan |              nan | no_gate_states |
| USDJPY   | 2025-08      | 2025-05,2025-06,2025-07 |                 0 |      0 |             0 |         nan |               nan |                nan |                 nan |        nan |                nan |               nan |         nan |              nan | no_gate_states |
| USDJPY   | 2025-09      | 2025-06,2025-07,2025-08 |                 0 |      0 |             0 |         nan |               nan |                nan |                 nan |        nan |                nan |               nan |         nan |              nan | no_gate_states |
| USDJPY   | 2025-10      | 2025-07,2025-08,2025-09 |                 0 |      0 |             0 |         nan |               nan |                nan |                 nan |        nan |                nan |               nan |         nan |              nan | no_gate_states |
| USDJPY   | 2025-11      | 2025-08,2025-09,2025-10 |                 0 |      0 |             0 |         nan |               nan |                nan |                 nan |        nan |                nan |               nan |         nan |              nan | no_gate_states |
| USDJPY   | 2025-12      | 2025-09,2025-10,2025-11 |                 0 |      0 |             0 |         nan |               nan |                nan |                 nan |        nan |                nan |               nan |         nan |              nan | no_gate_states |

## State Stability
| symbol   | test_month   |   states_selected |   state_churn_rate |   top_state_share |   state_hhi |   stability_pass | status         |
|:---------|:-------------|------------------:|-------------------:|------------------:|------------:|-----------------:|:---------------|
| USDJPY   | 2025-04      |                 0 |                nan |               nan |         nan |              nan | warmup_skip    |
| USDJPY   | 2025-05      |                 0 |                nan |               nan |         nan |              nan | warmup_skip    |
| USDJPY   | 2025-06      |                 0 |                nan |               nan |         nan |              nan | warmup_skip    |
| USDJPY   | 2025-07      |                 0 |                nan |               nan |         nan |              nan | no_gate_states |
| USDJPY   | 2025-08      |                 0 |                nan |               nan |         nan |              nan | no_gate_states |
| USDJPY   | 2025-09      |                 0 |                nan |               nan |         nan |              nan | no_gate_states |
| USDJPY   | 2025-10      |                 0 |                nan |               nan |         nan |              nan | no_gate_states |
| USDJPY   | 2025-11      |                 0 |                nan |               nan |         nan |              nan | no_gate_states |
| USDJPY   | 2025-12      |                 0 |                nan |               nan |         nan |              nan | no_gate_states |

## State Schedule (Top Rows)
_empty_
