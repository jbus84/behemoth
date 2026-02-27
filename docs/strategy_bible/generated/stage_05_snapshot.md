### Auto Snapshot - Stage 05

- generated_at: `2026-02-27 15:20:50 UTC`
- State schedule is selected month-by-month using only prior-month train data.
- Summary emphasizes full-path gross behavior after reduced-core filtering.
- R01-R03 track pruning severity, state concentration, and re-selection stability.

#### Key Results
| symbol   |   rows_total |   mean_gross_pips |   lb95_month_mean_gross_pips |   fill_rate_overall |   positive_months |   months_total |   r01_post_pre_row_ratio |   r02_top_state_dependency |   r03_reselection_stability |
|:---------|-------------:|------------------:|-----------------------------:|--------------------:|------------------:|---------------:|-------------------------:|---------------------------:|----------------------------:|
| EURUSD   |         4898 |           1.59847 |                      1.30417 |            0.994922 |                 6 |              9 |                0.0150469 |                       0.35 |                    0.361111 |
| GBPUSD   |         6824 |           2.51775 |                      2.21592 |            0.990421 |                 6 |              9 |                0.016478  |                       0.35 |                    0.430556 |
| USDJPY   |         7843 |           3.31998 |                      2.95901 |            0.987783 |                 6 |              9 |                0.0170654 |                       0.35 |                    0.416667 |

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
| EURUSD   |        9 |         4898 |         0.994601 |      1.67778 |
| GBPUSD   |        9 |         6824 |         0.99016  |      2.54028 |
| USDJPY   |        9 |         7843 |         0.987666 |      3.24827 |

#### Plots
![stage_05_reduced_monthly_gross](../../figures/oco_bible/stage_05_reduced_monthly_gross.png)

#### State Churn
| symbol   | test_month   |   states_selected |   state_churn_rate |   top_state_share |   state_hhi |   stability_pass | status      |
|:---------|:-------------|------------------:|-------------------:|------------------:|------------:|-----------------:|:------------|
| EURUSD   | 2025-04      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip |
| EURUSD   | 2025-05      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip |
| EURUSD   | 2025-06      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip |
| EURUSD   | 2025-07      |                 1 |           0        |          1        |    1        |                0 | ok          |
| EURUSD   | 2025-08      |                 1 |           1        |          1        |    1        |                0 | ok          |
| EURUSD   | 2025-09      |                 2 |           0.5      |          0.538173 |    0.502914 |                0 | ok          |
| EURUSD   | 2025-10      |                 2 |           1        |          0.591503 |    0.516746 |                0 | ok          |
| EURUSD   | 2025-11      |                 2 |           0.666667 |          0.508966 |    0.500161 |                0 | ok          |
| EURUSD   | 2025-12      |                 2 |           0.666667 |          0.598883 |    0.519556 |                0 | ok          |
| GBPUSD   | 2025-04      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip |
| GBPUSD   | 2025-05      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip |
| GBPUSD   | 2025-06      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip |
| GBPUSD   | 2025-07      |                 2 |           0        |          0.634304 |    0.536075 |                0 | ok          |
| GBPUSD   | 2025-08      |                 2 |           0.666667 |          0.503041 |    0.500018 |                0 | ok          |
| GBPUSD   | 2025-09      |                 2 |           0.666667 |          0.626556 |    0.532033 |                0 | ok          |
| GBPUSD   | 2025-10      |                 2 |           0.666667 |          0.512739 |    0.500325 |                0 | ok          |
| GBPUSD   | 2025-11      |                 2 |           0.666667 |          0.523355 |    0.501091 |                0 | ok          |
| GBPUSD   | 2025-12      |                 3 |           0.75     |          0.371124 |    0.33619  |                0 | ok          |
| USDJPY   | 2025-04      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip |
| USDJPY   | 2025-05      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip |
| USDJPY   | 2025-06      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip |
| USDJPY   | 2025-07      |                 2 |           0        |          0.501431 |    0.500004 |                0 | ok          |
| USDJPY   | 2025-08      |                 2 |           0.666667 |          0.508951 |    0.50016  |                0 | ok          |
| USDJPY   | 2025-09      |                 3 |           0.75     |          0.385125 |    0.339225 |                0 | ok          |
| USDJPY   | 2025-10      |                 2 |           0.75     |          0.666951 |    0.555745 |                0 | ok          |
| USDJPY   | 2025-11      |                 2 |           0.666667 |          0.543775 |    0.503833 |                0 | ok          |
| USDJPY   | 2025-12      |                 2 |           0.666667 |          0.54269  |    0.503645 |                0 | ok          |

#### Leakage/Label Integrity (Reduced-Core Focus)
| symbol   |   checks_total |   checks_failed | failed_check_ids   |
|:---------|---------------:|----------------:|:-------------------|
| EURUSD   |              3 |               0 |                    |
| GBPUSD   |              3 |               0 |                    |
| USDJPY   |              3 |               0 |                    |
