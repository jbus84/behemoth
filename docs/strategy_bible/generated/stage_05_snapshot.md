### Auto Snapshot - Stage 05

- generated_at: `2026-02-28 20:57:22 UTC`
- State schedule is selected month-by-month using only prior-month train data.
- Summary emphasizes full-path gross behavior after reduced-core filtering.
- R01-R03 track pruning severity, state concentration, and re-selection stability.

#### Key Results
| symbol   |   rows_total |   mean_gross_pips |   lb95_month_mean_gross_pips |   fill_rate_overall |   positive_months |   months_total |   r01_post_pre_row_ratio |   r02_top_state_dependency |   r03_reselection_stability |
|:---------|-------------:|------------------:|-----------------------------:|--------------------:|------------------:|---------------:|-------------------------:|---------------------------:|----------------------------:|
| EURUSD   |         4898 |           1.59847 |                      1.30417 |            0.994922 |                 6 |              9 |                0.0150469 |                       0.35 |                    0.361111 |
| GBPUSD   |            0 |         nan       |                    nan       |          nan        |                 0 |              9 |                0         |                       0.35 |                    0        |
| AUDUSD   |            0 |         nan       |                    nan       |          nan        |                 0 |              9 |                0         |                       0.35 |                    0        |
| USDJPY   |            0 |         nan       |                    nan       |          nan        |                 0 |              9 |                0         |                       0.35 |                    0        |
| USDCHF   |         4074 |           1.33073 |                      1.04729 |            0.976276 |                 6 |              9 |                0.0111155 |                       0.35 |                    0.472222 |
| USDCAD   |          nan |         nan       |                    nan       |          nan        |               nan |            nan |                0         |                       0    |                    0.444444 |

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
| AUDUSD   |        9 |            0 |       nan        |    nan       |
| EURUSD   |        9 |         4898 |         0.994601 |      1.67778 |
| GBPUSD   |        9 |            0 |       nan        |    nan       |
| USDCAD   |        9 |            0 |       nan        |    nan       |
| USDCHF   |        9 |         4074 |         0.976843 |      1.26051 |
| USDJPY   |        9 |            0 |       nan        |    nan       |

#### Plots
![stage_05_reduced_monthly_gross](../../figures/oco_bible/stage_05_reduced_monthly_gross.png)

#### State Churn
| symbol   | test_month   |   states_selected |   state_churn_rate |   top_state_share |   state_hhi |   stability_pass | status         |
|:---------|:-------------|------------------:|-------------------:|------------------:|------------:|-----------------:|:---------------|
| EURUSD   | 2025-04      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip    |
| EURUSD   | 2025-05      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip    |
| EURUSD   | 2025-06      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip    |
| EURUSD   | 2025-07      |                 1 |           0        |          1        |    1        |                0 | ok             |
| EURUSD   | 2025-08      |                 1 |           1        |          1        |    1        |                0 | ok             |
| EURUSD   | 2025-09      |                 2 |           0.5      |          0.538173 |    0.502914 |                0 | ok             |
| EURUSD   | 2025-10      |                 2 |           1        |          0.591503 |    0.516746 |                0 | ok             |
| EURUSD   | 2025-11      |                 2 |           0.666667 |          0.508966 |    0.500161 |                0 | ok             |
| EURUSD   | 2025-12      |                 2 |           0.666667 |          0.598883 |    0.519556 |                0 | ok             |
| GBPUSD   | 2025-04      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip    |
| GBPUSD   | 2025-05      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip    |
| GBPUSD   | 2025-06      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip    |
| GBPUSD   | 2025-07      |                 0 |         nan        |        nan        |  nan        |              nan | no_gate_states |
| GBPUSD   | 2025-08      |                 0 |         nan        |        nan        |  nan        |              nan | no_gate_states |
| GBPUSD   | 2025-09      |                 0 |         nan        |        nan        |  nan        |              nan | no_gate_states |
| GBPUSD   | 2025-10      |                 0 |         nan        |        nan        |  nan        |              nan | no_gate_states |
| GBPUSD   | 2025-11      |                 0 |         nan        |        nan        |  nan        |              nan | no_gate_states |
| GBPUSD   | 2025-12      |                 0 |         nan        |        nan        |  nan        |              nan | no_gate_states |
| AUDUSD   | 2025-04      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip    |
| AUDUSD   | 2025-05      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip    |
| AUDUSD   | 2025-06      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip    |
| AUDUSD   | 2025-07      |                 0 |         nan        |        nan        |  nan        |              nan | no_gate_states |
| AUDUSD   | 2025-08      |                 0 |         nan        |        nan        |  nan        |              nan | no_gate_states |
| AUDUSD   | 2025-09      |                 0 |         nan        |        nan        |  nan        |              nan | no_gate_states |
| AUDUSD   | 2025-10      |                 0 |         nan        |        nan        |  nan        |              nan | no_gate_states |
| AUDUSD   | 2025-11      |                 0 |         nan        |        nan        |  nan        |              nan | no_gate_states |
| AUDUSD   | 2025-12      |                 0 |         nan        |        nan        |  nan        |              nan | no_gate_states |
| USDJPY   | 2025-04      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip    |
| USDJPY   | 2025-05      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip    |
| USDJPY   | 2025-06      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip    |
| USDJPY   | 2025-07      |                 0 |         nan        |        nan        |  nan        |              nan | no_gate_states |
| USDJPY   | 2025-08      |                 0 |         nan        |        nan        |  nan        |              nan | no_gate_states |
| USDJPY   | 2025-09      |                 0 |         nan        |        nan        |  nan        |              nan | no_gate_states |
| USDJPY   | 2025-10      |                 0 |         nan        |        nan        |  nan        |              nan | no_gate_states |
| USDJPY   | 2025-11      |                 0 |         nan        |        nan        |  nan        |              nan | no_gate_states |
| USDJPY   | 2025-12      |                 0 |         nan        |        nan        |  nan        |              nan | no_gate_states |
| USDCHF   | 2025-04      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip    |
| USDCHF   | 2025-05      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip    |
| USDCHF   | 2025-06      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip    |
| USDCHF   | 2025-07      |                 1 |           0        |          1        |    1        |                0 | ok             |
| USDCHF   | 2025-08      |                 2 |           0.5      |          0.587036 |    0.51515  |                0 | ok             |
| USDCHF   | 2025-09      |                 2 |           0.666667 |          0.589744 |    0.516108 |                0 | ok             |
| USDCHF   | 2025-10      |                 2 |           0.666667 |          0.565306 |    0.50853  |                0 | ok             |
| USDCHF   | 2025-11      |                 2 |           0.666667 |          0.54797  |    0.504602 |                0 | ok             |
| USDCHF   | 2025-12      |                 2 |           0.666667 |          0.526596 |    0.501415 |                0 | ok             |
| USDCAD   | 2025-04      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip    |
| USDCAD   | 2025-05      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip    |
| USDCAD   | 2025-06      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip    |
| USDCAD   | 2025-07      |                 2 |           0        |          0.885587 |    0.797355 |                0 | ok             |
| USDCAD   | 2025-08      |                 2 |           0.666667 |          0.513308 |    0.500354 |                0 | ok             |
| USDCAD   | 2025-09      |                 2 |           0        |          0.509489 |    0.50018  |                0 | ok             |
| USDCAD   | 2025-10      |                 2 |           0.666667 |          0.76482  |    0.640259 |                0 | ok             |
| USDCAD   | 2025-11      |                 1 |           1        |          1        |    1        |                0 | ok             |
| USDCAD   | 2025-12      |                 2 |           1        |          0.60231  |    0.520935 |                0 | ok             |

#### Leakage/Label Integrity (Reduced-Core Focus)
| symbol   |   checks_total |   checks_failed | failed_check_ids   |
|:---------|---------------:|----------------:|:-------------------|
| EURUSD   |              3 |               0 |                    |
| GBPUSD   |              3 |               0 |                    |
| USDJPY   |              3 |               0 |                    |
