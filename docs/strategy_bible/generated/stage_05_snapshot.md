### Auto Snapshot - Stage 05

- generated_at: `2026-04-03 12:49:19 UTC`
- State schedule is selected month-by-month using only prior-month train data.
- Summary emphasizes full-path gross behavior after reduced-core filtering.
- R01-R03 track pruning severity, state concentration, and re-selection stability.

#### Key Results
| symbol   |   rows_total |   mean_gross_pips |   lb95_month_mean_gross_pips |   fill_rate_overall |   positive_months |   months_total |   r01_post_pre_row_ratio |   r02_top_state_dependency |   r03_reselection_stability |
|:---------|-------------:|------------------:|-----------------------------:|--------------------:|------------------:|---------------:|-------------------------:|---------------------------:|----------------------------:|
| EURUSD   |         6734 |           2.28759 |                     1.6048   |            0.994536 |                11 |             15 |                0.0168844 |                       0.35 |                    0.340278 |
| GBPUSD   |        13641 |           2.56616 |                     2.31434  |            0.993012 |                11 |             15 |                0.0298041 |                       0.35 |                    0.430556 |
| AUDUSD   |         8824 |           1.54805 |                     0.954024 |            0.995151 |                11 |             15 |                0.0212827 |                       0.35 |                    0.315278 |
| USDJPY   |        16864 |           3.41663 |                     3.1392   |            0.988164 |                11 |             15 |                0.0351748 |                       0.35 |                    0.355556 |
| USDCHF   |         8161 |           2.17551 |                     1.07661  |            0.984795 |                11 |             15 |                0.0218528 |                       0.35 |                    0.305556 |
| USDCAD   |         6841 |           1.60772 |                     1.17257  |            0.990731 |                11 |             15 |                0.0151447 |                       0.35 |                    0.236111 |

#### Interpretation Notes
- State schedule is selected month-by-month using only prior-month train data.
- Summary emphasizes full-path gross behavior after reduced-core filtering.
- R01-R03 track pruning severity, state concentration, and re-selection stability.

#### Action Trigger Summary
| symbol   | metric_id                | band   | severity   | action_code   | action_summary     | owner    |
|:---------|:-------------------------|:-------|:-----------|:--------------|:-------------------|:---------|
| AUDUSD   | R02_top_state_dependency | green  | info       | A0_MONITOR    | within policy band | research |
| EURUSD   | R02_top_state_dependency | green  | info       | A0_MONITOR    | within policy band | research |
| GBPUSD   | R02_top_state_dependency | green  | info       | A0_MONITOR    | within policy band | research |
| USDCAD   | R02_top_state_dependency | green  | info       | A0_MONITOR    | within policy band | research |
| USDCHF   | R02_top_state_dependency | green  | info       | A0_MONITOR    | within policy band | research |
| USDJPY   | R02_top_state_dependency | green  | info       | A0_MONITOR    | within policy band | research |

#### Details
| symbol   |   months |   rows_total |   mean_fill_rate |   mean_gross |
|:---------|---------:|-------------:|-----------------:|-------------:|
| AUDUSD   |       15 |         8824 |         0.995275 |      1.20716 |
| EURUSD   |       15 |         6734 |         0.994542 |      1.96339 |
| GBPUSD   |       15 |        13641 |         0.992776 |      2.4785  |
| USDCAD   |       15 |         6841 |         0.992733 |      1.38618 |
| USDCHF   |       15 |         8161 |         0.985956 |      1.3893  |
| USDJPY   |       15 |        16864 |         0.988259 |      3.35048 |

#### Plots
![stage_05_reduced_monthly_gross](../../figures/oco_bible/stage_05_reduced_monthly_gross.png)

#### State Churn
| symbol   | test_month   |   states_selected |   state_churn_rate |   top_state_share |   state_hhi |   stability_pass | status       |
|:---------|:-------------|------------------:|-------------------:|------------------:|------------:|-----------------:|:-------------|
| EURUSD   | 2025-01      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip  |
| EURUSD   | 2025-02      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip  |
| EURUSD   | 2025-03      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip  |
| EURUSD   | 2025-04      |                 2 |           0        |          0.651685 |    0.546017 |                0 | ok           |
| EURUSD   | 2025-05      |                 2 |           0.666667 |          0.567036 |    0.508988 |                0 | ok           |
| EURUSD   | 2025-06      |                 1 |           0.5      |          1        |    1        |                0 | ok           |
| EURUSD   | 2025-07      |                 1 |           0        |          1        |    1        |                0 | ok           |
| EURUSD   | 2025-08      |                 3 |           0.666667 |          0.374464 |    0.335899 |                0 | ok           |
| EURUSD   | 2025-09      |                 2 |           0.75     |          0.551053 |    0.505213 |                0 | ok           |
| EURUSD   | 2025-10      |                 2 |           1        |          0.774306 |    0.650487 |                0 | ok           |
| EURUSD   | 2025-11      |                 2 |           0.666667 |          0.534247 |    0.502346 |                0 | ok           |
| EURUSD   | 2025-12      |                 2 |           1        |          0.552699 |    0.505554 |                0 | ok           |
| EURUSD   | 2026-01      |                 2 |           0.666667 |          0.638847 |    0.538557 |                0 | ok           |
| EURUSD   | 2026-02      |                 1 |           1        |          1        |    1        |                0 | ok           |
| EURUSD   | 2026-03      |                 1 |           1        |        nan        |  nan        |                0 | no_test_rows |
| GBPUSD   | 2025-01      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip  |
| GBPUSD   | 2025-02      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip  |
| GBPUSD   | 2025-03      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip  |
| GBPUSD   | 2025-04      |                 2 |           0        |          0.53899  |    0.50304  |                0 | ok           |
| GBPUSD   | 2025-05      |                 2 |           0.666667 |          0.673291 |    0.560059 |                0 | ok           |
| GBPUSD   | 2025-06      |                 2 |           0        |          0.683219 |    0.567139 |                0 | ok           |
| GBPUSD   | 2025-07      |                 2 |           0.666667 |          0.575778 |    0.511484 |                0 | ok           |
| GBPUSD   | 2025-08      |                 2 |           0.666667 |          0.509195 |    0.500169 |                0 | ok           |
| GBPUSD   | 2025-09      |                 2 |           0.666667 |          0.543656 |    0.503812 |                0 | ok           |
| GBPUSD   | 2025-10      |                 2 |           0.666667 |          0.503882 |    0.50003  |                0 | ok           |
| GBPUSD   | 2025-11      |                 2 |           0.666667 |          0.644118 |    0.54154  |                0 | ok           |
| GBPUSD   | 2025-12      |                 2 |           0.666667 |          0.556716 |    0.506434 |                0 | ok           |
| GBPUSD   | 2026-01      |                 2 |           1        |          0.564677 |    0.508366 |                0 | ok           |
| GBPUSD   | 2026-02      |                 2 |           0.666667 |          0.552655 |    0.505545 |                0 | ok           |
| GBPUSD   | 2026-03      |                 1 |           0.5      |        nan        |  nan        |                0 | no_test_rows |
| AUDUSD   | 2025-01      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip  |
| AUDUSD   | 2025-02      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip  |
| AUDUSD   | 2025-03      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip  |
| AUDUSD   | 2025-04      |                 2 |           0        |          0.557899 |    0.506705 |                0 | ok           |
| AUDUSD   | 2025-05      |                 2 |           0.666667 |          0.575283 |    0.511335 |                0 | ok           |
| AUDUSD   | 2025-06      |                 2 |           0.666667 |          0.560299 |    0.507272 |                0 | ok           |
| AUDUSD   | 2025-07      |                 2 |           1        |          0.777559 |    0.654078 |                0 | ok           |
| AUDUSD   | 2025-08      |                 4 |           0.8      |          0.342484 |    0.289067 |                0 | ok           |
| AUDUSD   | 2025-09      |                 2 |           1        |          0.577017 |    0.511863 |                0 | ok           |
| AUDUSD   | 2025-10      |                 2 |           0.666667 |          0.510597 |    0.500225 |                0 | ok           |
| AUDUSD   | 2025-11      |                 3 |           0.333333 |          0.389365 |    0.339196 |                0 | ok           |
| AUDUSD   | 2025-12      |                 2 |           0.75     |          0.68306  |    0.567022 |                0 | ok           |
| AUDUSD   | 2026-01      |                 2 |           1        |          0.506369 |    0.500081 |                0 | ok           |
| AUDUSD   | 2026-02      |                 2 |           0.666667 |          0.554839 |    0.506015 |                0 | ok           |
| AUDUSD   | 2026-03      |                 2 |           0.666667 |        nan        |  nan        |                0 | no_test_rows |
| USDJPY   | 2025-01      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip  |
| USDJPY   | 2025-02      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip  |
| USDJPY   | 2025-03      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip  |
| USDJPY   | 2025-04      |                 2 |           0        |          0.608278 |    0.523448 |                0 | ok           |
| USDJPY   | 2025-05      |                 3 |           0.333333 |          0.419526 |    0.345646 |                0 | ok           |
| USDJPY   | 2025-06      |                 3 |           0.8      |          0.470968 |    0.415302 |                0 | ok           |
| USDJPY   | 2025-07      |                 1 |           1        |          1        |    1        |                0 | ok           |
| USDJPY   | 2025-08      |                 2 |           0.5      |          0.515371 |    0.500473 |                0 | ok           |
| USDJPY   | 2025-09      |                 2 |           0.666667 |          0.761364 |    0.636622 |                0 | ok           |
| USDJPY   | 2025-10      |                 2 |           0.666667 |          0.610429 |    0.524389 |                0 | ok           |
| USDJPY   | 2025-11      |                 4 |           0.8      |          0.288344 |    0.255373 |                0 | ok           |
| USDJPY   | 2025-12      |                 2 |           0.8      |          0.542469 |    0.503607 |                0 | ok           |
| USDJPY   | 2026-01      |                 2 |           0.666667 |          0.624346 |    0.530924 |                0 | ok           |
| USDJPY   | 2026-02      |                 1 |           1        |          1        |    1        |                0 | ok           |
| USDJPY   | 2026-03      |                 2 |           0.5      |        nan        |  nan        |                0 | no_test_rows |
| USDCHF   | 2025-01      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip  |
| USDCHF   | 2025-02      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip  |
| USDCHF   | 2025-03      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip  |
| USDCHF   | 2025-04      |                 3 |           0        |          0.545053 |    0.471653 |                0 | ok           |
| USDCHF   | 2025-05      |                 1 |           0.666667 |          1        |    1        |                0 | ok           |
| USDCHF   | 2025-06      |                 2 |           0.5      |          0.703704 |    0.58299  |                0 | ok           |
| USDCHF   | 2025-07      |                 2 |           1        |          0.87007  |    0.773903 |                0 | ok           |
| USDCHF   | 2025-08      |                 2 |           0.666667 |          0.774882 |    0.65112  |                0 | ok           |
| USDCHF   | 2025-09      |                 2 |           0.666667 |          0.586364 |    0.514917 |                0 | ok           |
| USDCHF   | 2025-10      |                 2 |           0.666667 |          0.54102  |    0.503365 |                0 | ok           |
| USDCHF   | 2025-11      |                 2 |           0.666667 |          0.511574 |    0.500268 |                0 | ok           |
| USDCHF   | 2025-12      |                 2 |           1        |          0.524272 |    0.501178 |                0 | ok           |
| USDCHF   | 2026-01      |                 1 |           0.5      |          1        |    1        |                0 | ok           |
| USDCHF   | 2026-02      |                 1 |           1        |          1        |    1        |                0 | ok           |
| USDCHF   | 2026-03      |                 2 |           1        |        nan        |  nan        |                0 | no_test_rows |
| USDCAD   | 2025-01      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip  |
| USDCAD   | 2025-02      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip  |
| USDCAD   | 2025-03      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip  |
| USDCAD   | 2025-04      |                 2 |           0        |          0.533278 |    0.502215 |                0 | ok           |
| USDCAD   | 2025-05      |                 2 |           1        |          0.511208 |    0.500251 |                0 | ok           |
| USDCAD   | 2025-06      |                 2 |           0.666667 |          0.812088 |    0.694798 |                0 | ok           |
| USDCAD   | 2025-07      |                 2 |           1        |          0.802158 |    0.682599 |                0 | ok           |
| USDCAD   | 2025-08      |                 2 |           1        |          0.612058 |    0.525114 |                0 | ok           |
| USDCAD   | 2025-09      |                 2 |           0        |          0.522305 |    0.500995 |                0 | ok           |
| USDCAD   | 2025-10      |                 1 |           1        |          1        |    1        |                0 | ok           |
| USDCAD   | 2025-11      |                 2 |           0.5      |          0.542125 |    0.503549 |                0 | ok           |
| USDCAD   | 2025-12      |                 1 |           1        |          1        |    1        |                0 | ok           |
| USDCAD   | 2026-01      |                 2 |           1        |          0.51927  |    0.500743 |                0 | ok           |
| USDCAD   | 2026-02      |                 1 |           1        |          1        |    1        |                0 | ok           |
| USDCAD   | 2026-03      |                 2 |           1        |        nan        |  nan        |                0 | no_test_rows |

#### Leakage/Label Integrity (Reduced-Core Focus)
| symbol   |   checks_total |   checks_failed | failed_check_ids   |
|:---------|---------------:|----------------:|:-------------------|
| EURUSD   |              3 |               0 |                    |
| GBPUSD   |              3 |               0 |                    |
| AUDUSD   |              3 |               0 |                    |
| USDJPY   |              3 |               0 |                    |
| USDCHF   |              3 |               0 |                    |
| USDCAD   |              3 |               0 |                    |
