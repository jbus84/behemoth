### Auto Snapshot - Stage 05

- generated_at: `2026-02-27 18:50:29 UTC`
- State schedule is selected month-by-month using only prior-month train data.
- Summary emphasizes full-path gross behavior after reduced-core filtering.
- R01-R03 track pruning severity, state concentration, and re-selection stability.

#### Key Results
| symbol   |   rows_total |   mean_gross_pips |   lb95_month_mean_gross_pips |   fill_rate_overall |   positive_months |   months_total |   r01_post_pre_row_ratio |   r02_top_state_dependency |   r03_reselection_stability |
|:---------|-------------:|------------------:|-----------------------------:|--------------------:|------------------:|---------------:|-------------------------:|---------------------------:|----------------------------:|
| EURUSD   |          661 |           2.76929 |                      2.30087 |            0.991004 |                 3 |              9 |                0.0110249 |                       0.35 |                    0.5      |
| GBPUSD   |         1916 |           2.07056 |                      1.80556 |            0.995842 |                 6 |              9 |                0.0271469 |                       0.35 |                    0.5      |
| USDJPY   |         2258 |           3.00368 |                      2.54229 |            0.990351 |                 6 |              9 |                0.0290287 |                       0.35 |                    0.305556 |

#### Interpretation Notes
- State schedule is selected month-by-month using only prior-month train data.
- Summary emphasizes full-path gross behavior after reduced-core filtering.
- R01-R03 track pruning severity, state concentration, and re-selection stability.

#### Action Trigger Summary
| symbol   | metric_id                | band   | severity   | action_code   | action_summary     | owner    |
|:---------|:-------------------------|:-------|:-----------|:--------------|:-------------------|:---------|
| EURUSD   | R02_top_state_dependency | green  | info       | A0_MONITOR    | within policy band | research |
| GBPUSD   | R02_top_state_dependency | green  | info       | A0_MONITOR    | within policy band | research |
| USDJPY   | R02_top_state_dependency | green  | info       | A0_MONITOR    | within policy band | research |

#### Details
| symbol   |   months |   rows_total |   mean_fill_rate |   mean_gross |
|:---------|---------:|-------------:|-----------------:|-------------:|
| EURUSD   |        9 |          661 |         0.989648 |      2.64718 |
| GBPUSD   |        9 |         1916 |         0.996571 |      2.13763 |
| USDJPY   |        9 |         2258 |         0.990604 |      2.98447 |

#### Plots
![stage_05_reduced_monthly_gross](../../figures/oco_bible/stage_05_reduced_monthly_gross.png)

#### State Churn
| symbol   | test_month   |   states_selected |   state_churn_rate |   top_state_share |   state_hhi |   stability_pass | status         |
|:---------|:-------------|------------------:|-------------------:|------------------:|------------:|-----------------:|:---------------|
| EURUSD   | 2025-04      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip    |
| EURUSD   | 2025-05      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip    |
| EURUSD   | 2025-06      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip    |
| EURUSD   | 2025-07      |                 2 |           0        |          0.610169 |    0.524275 |                0 | ok             |
| EURUSD   | 2025-08      |                 2 |           1        |          0.590551 |    0.516399 |                0 | ok             |
| EURUSD   | 2025-09      |                 1 |           0.5      |          1        |    1        |                0 | ok             |
| EURUSD   | 2025-10      |                 0 |         nan        |        nan        |  nan        |              nan | no_gate_states |
| EURUSD   | 2025-11      |                 0 |         nan        |        nan        |  nan        |              nan | no_gate_states |
| EURUSD   | 2025-12      |                 0 |         nan        |        nan        |  nan        |              nan | no_gate_states |
| GBPUSD   | 2025-04      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip    |
| GBPUSD   | 2025-05      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip    |
| GBPUSD   | 2025-06      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip    |
| GBPUSD   | 2025-07      |                 1 |           0        |          1        |    1        |                0 | ok             |
| GBPUSD   | 2025-08      |                 2 |           0.5      |          0.5053   |    0.500056 |                0 | ok             |
| GBPUSD   | 2025-09      |                 1 |           1        |          1        |    1        |                0 | ok             |
| GBPUSD   | 2025-10      |                 2 |           0.5      |          0.54321  |    0.503734 |                0 | ok             |
| GBPUSD   | 2025-11      |                 1 |           0.5      |          1        |    1        |                0 | ok             |
| GBPUSD   | 2025-12      |                 2 |           0.5      |          0.530726 |    0.501888 |                0 | ok             |
| USDJPY   | 2025-04      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip    |
| USDJPY   | 2025-05      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip    |
| USDJPY   | 2025-06      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip    |
| USDJPY   | 2025-07      |                 2 |           0        |          0.614525 |    0.526232 |                0 | ok             |
| USDJPY   | 2025-08      |                 2 |           0.666667 |          0.522124 |    0.500979 |                0 | ok             |
| USDJPY   | 2025-09      |                 1 |           1        |          1        |    1        |                0 | ok             |
| USDJPY   | 2025-10      |                 2 |           0.5      |          0.605206 |    0.522137 |                0 | ok             |
| USDJPY   | 2025-11      |                 1 |           1        |          1        |    1        |                0 | ok             |
| USDJPY   | 2025-12      |                 2 |           1        |          0.639469 |    0.538903 |                0 | ok             |

#### Leakage/Label Integrity (Reduced-Core Focus)
| symbol   |   checks_total |   checks_failed | failed_check_ids   |
|:---------|---------------:|----------------:|:-------------------|
| EURUSD   |              3 |               0 |                    |
| GBPUSD   |              3 |               0 |                    |
| USDJPY   |              3 |               0 |                    |
