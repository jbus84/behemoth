### Auto Snapshot - Stage 05

- generated_at: `2026-03-15 12:55:53 UTC`
- State schedule is selected month-by-month using only prior-month train data.
- Summary emphasizes full-path gross behavior after reduced-core filtering.
- R01-R03 track pruning severity, state concentration, and re-selection stability.

#### Key Results
| symbol   |   rows_total |   mean_gross_pips |   lb95_month_mean_gross_pips |   fill_rate_overall |   positive_months |   months_total |   r01_post_pre_row_ratio |   r02_top_state_dependency |   r03_reselection_stability |
|:---------|-------------:|------------------:|-----------------------------:|--------------------:|------------------:|---------------:|-------------------------:|---------------------------:|----------------------------:|
| EURUSD   |         5021 |           2.61095 |                     1.59103  |            0.992292 |                11 |             15 |                0.0118705 |                       0.35 |                    0.527778 |
| GBPUSD   |        12466 |           2.65258 |                     2.43814  |            0.993623 |                11 |             15 |                0.0284943 |                       0.35 |                    0.361111 |
| USDJPY   |        15606 |           3.52291 |                     3.23465  |            0.987347 |                11 |             15 |                0.0328278 |                       0.35 |                    0.402778 |
| USDCHF   |         8228 |           1.89655 |                     1.0844   |            0.984211 |                11 |             15 |                0.0236763 |                       0.35 |                    0.305556 |
| AUDUSD   |         8270 |           1.67881 |                     0.939409 |            0.995187 |                11 |             15 |                0.018392  |                       0.35 |                    0.395833 |
| USDCAD   |         9148 |           2.30449 |                     1.26532  |            0.988545 |                10 |             15 |                0.0188482 |                       0.35 |                    0.318182 |

#### Interpretation Notes
- State schedule is selected month-by-month using only prior-month train data.
- Summary emphasizes full-path gross behavior after reduced-core filtering.
- R01-R03 track pruning severity, state concentration, and re-selection stability.

#### Action Trigger Summary
| trigger            | threshold_or_signal   | action_code                   | action_summary                                                          |
|:-------------------|:----------------------|:------------------------------|:------------------------------------------------------------------------|
| hard_gate_fail     | status=fail           | A3_HALT_RECALIBRATE           | Block promotion and rerun upstream stage diagnostics before continuing. |
| monitoring_warning | band=amber            | A0_MONITOR/A1_RECALIBRATE_CAP | Apply stage runbook remediation and confirm next-run recovery.          |

#### Details
| symbol   |   months |   rows_total |   mean_fill_rate |   mean_gross |
|:---------|---------:|-------------:|-----------------:|-------------:|
| AUDUSD   |       15 |         8270 |         0.994891 |      1.17922 |
| EURUSD   |       15 |         5021 |         0.994442 |      1.99965 |
| GBPUSD   |       15 |        12466 |         0.993291 |      2.54846 |
| USDCAD   |       15 |         9148 |         0.99368  |      1.55093 |
| USDCHF   |       15 |         8228 |         0.981636 |      1.42181 |
| USDJPY   |       15 |        15606 |         0.988294 |      3.50471 |

#### Plots
![stage_05_reduced_monthly_gross](../../figures/oco_bible/stage_05_reduced_monthly_gross.png)

#### State Churn
| symbol   | test_month   |   states_selected |   state_churn_rate |   top_state_share |   state_hhi |   stability_pass | status         |
|:---------|:-------------|------------------:|-------------------:|------------------:|------------:|-----------------:|:---------------|
| EURUSD   | 2025-01      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip    |
| EURUSD   | 2025-02      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip    |
| EURUSD   | 2025-03      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip    |
| EURUSD   | 2025-04      |                 2 |           0        |          0.659363 |    0.550793 |                0 | ok             |
| EURUSD   | 2025-05      |                 2 |           0.666667 |          0.768229 |    0.643894 |                0 | ok             |
| EURUSD   | 2025-06      |                 1 |           0.5      |          1        |    1        |                0 | ok             |
| EURUSD   | 2025-07      |                 1 |           0        |          1        |    1        |                0 | ok             |
| EURUSD   | 2025-08      |                 1 |           0        |          1        |    1        |                0 | ok             |
| EURUSD   | 2025-09      |                 2 |           1        |          0.547287 |    0.504472 |                0 | ok             |
| EURUSD   | 2025-10      |                 2 |           0.666667 |          0.557778 |    0.506677 |                0 | ok             |
| EURUSD   | 2025-11      |                 2 |           0.666667 |          0.524096 |    0.501161 |                0 | ok             |
| EURUSD   | 2025-12      |                 2 |           0.666667 |          0.661202 |    0.551972 |                0 | ok             |
| EURUSD   | 2026-01      |                 1 |           0.5      |          1        |    1        |                0 | ok             |
| EURUSD   | 2026-02      |                 1 |           0        |          1        |    1        |                0 | ok             |
| EURUSD   | 2026-03      |                 1 |           1        |        nan        |  nan        |                0 | no_test_rows   |
| GBPUSD   | 2025-01      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip    |
| GBPUSD   | 2025-02      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip    |
| GBPUSD   | 2025-03      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip    |
| GBPUSD   | 2025-04      |                 2 |           0        |          0.531989 |    0.502047 |                0 | ok             |
| GBPUSD   | 2025-05      |                 2 |           0.666667 |          0.817287 |    0.701342 |                0 | ok             |
| GBPUSD   | 2025-06      |                 2 |           0.666667 |          0.723569 |    0.599967 |                0 | ok             |
| GBPUSD   | 2025-07      |                 2 |           1        |          0.502568 |    0.500013 |                0 | ok             |
| GBPUSD   | 2025-08      |                 2 |           0        |          0.554535 |    0.505948 |                0 | ok             |
| GBPUSD   | 2025-09      |                 2 |           1        |          0.736607 |    0.611966 |                0 | ok             |
| GBPUSD   | 2025-10      |                 2 |           0.666667 |          0.501333 |    0.500004 |                0 | ok             |
| GBPUSD   | 2025-11      |                 2 |           0.666667 |          0.515403 |    0.500474 |                0 | ok             |
| GBPUSD   | 2025-12      |                 2 |           1        |          0.536885 |    0.502721 |                0 | ok             |
| GBPUSD   | 2026-01      |                 2 |           0.666667 |          0.522976 |    0.501056 |                0 | ok             |
| GBPUSD   | 2026-02      |                 2 |           0.666667 |          0.584682 |    0.514342 |                0 | ok             |
| GBPUSD   | 2026-03      |                 2 |           0.666667 |        nan        |  nan        |                0 | no_test_rows   |
| USDJPY   | 2025-01      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip    |
| USDJPY   | 2025-02      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip    |
| USDJPY   | 2025-03      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip    |
| USDJPY   | 2025-04      |                 2 |           0        |          0.552345 |    0.50548  |                0 | ok             |
| USDJPY   | 2025-05      |                 2 |           0.666667 |          0.548884 |    0.504779 |                0 | ok             |
| USDJPY   | 2025-06      |                 2 |           0.666667 |          0.521709 |    0.500943 |                0 | ok             |
| USDJPY   | 2025-07      |                 2 |           0.666667 |          0.556429 |    0.506368 |                0 | ok             |
| USDJPY   | 2025-08      |                 2 |           0.666667 |          0.54779  |    0.504568 |                0 | ok             |
| USDJPY   | 2025-09      |                 3 |           0.75     |          0.506257 |    0.378935 |                0 | ok             |
| USDJPY   | 2025-10      |                 2 |           1        |          0.518955 |    0.500719 |                0 | ok             |
| USDJPY   | 2025-11      |                 2 |           0        |          0.544937 |    0.504039 |                0 | ok             |
| USDJPY   | 2025-12      |                 2 |           0.666667 |          0.516255 |    0.500528 |                0 | ok             |
| USDJPY   | 2026-01      |                 2 |           0.666667 |          0.515586 |    0.500486 |                0 | ok             |
| USDJPY   | 2026-02      |                 2 |           0.666667 |          0.551317 |    0.505267 |                0 | ok             |
| USDJPY   | 2026-03      |                 3 |           0.75     |        nan        |  nan        |                0 | no_test_rows   |
| USDCHF   | 2025-01      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip    |
| USDCHF   | 2025-02      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip    |
| USDCHF   | 2025-03      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip    |
| USDCHF   | 2025-04      |                 2 |           0        |          0.744459 |    0.61952  |                0 | ok             |
| USDCHF   | 2025-05      |                 2 |           1        |          0.758004 |    0.633132 |                0 | ok             |
| USDCHF   | 2025-06      |                 2 |           0.666667 |          0.576408 |    0.511676 |                0 | ok             |
| USDCHF   | 2025-07      |                 1 |           1        |          1        |    1        |                0 | ok             |
| USDCHF   | 2025-08      |                 2 |           0.5      |          0.602812 |    0.521141 |                0 | ok             |
| USDCHF   | 2025-09      |                 2 |           0.666667 |          0.633127 |    0.535446 |                0 | ok             |
| USDCHF   | 2025-10      |                 3 |           0.75     |          0.398637 |    0.341717 |                0 | ok             |
| USDCHF   | 2025-11      |                 3 |           0.5      |          0.379019 |    0.336477 |                0 | ok             |
| USDCHF   | 2025-12      |                 2 |           0.75     |          0.507812 |    0.500122 |                0 | ok             |
| USDCHF   | 2026-01      |                 1 |           0.5      |          1        |    1        |                0 | ok             |
| USDCHF   | 2026-02      |                 1 |           1        |          1        |    1        |                0 | ok             |
| USDCHF   | 2026-03      |                 1 |           1        |        nan        |  nan        |                0 | no_test_rows   |
| AUDUSD   | 2025-01      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip    |
| AUDUSD   | 2025-02      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip    |
| AUDUSD   | 2025-03      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip    |
| AUDUSD   | 2025-04      |                 2 |           0        |          0.632405 |    0.535062 |                0 | ok             |
| AUDUSD   | 2025-05      |                 2 |           0.666667 |          0.56686  |    0.508941 |                0 | ok             |
| AUDUSD   | 2025-06      |                 2 |           0.666667 |          0.787197 |    0.664964 |                0 | ok             |
| AUDUSD   | 2025-07      |                 2 |           1        |          0.754098 |    0.629132 |                0 | ok             |
| AUDUSD   | 2025-08      |                 3 |           1        |          0.366788 |    0.337292 |                0 | ok             |
| AUDUSD   | 2025-09      |                 2 |           0.75     |          0.51682  |    0.500566 |                0 | ok             |
| AUDUSD   | 2025-10      |                 2 |           0        |          0.52     |    0.5008   |                0 | ok             |
| AUDUSD   | 2025-11      |                 2 |           0.666667 |          0.557576 |    0.50663  |                0 | ok             |
| AUDUSD   | 2025-12      |                 1 |           0.5      |          1        |    1        |                0 | ok             |
| AUDUSD   | 2026-01      |                 1 |           0        |          1        |    1        |                0 | ok             |
| AUDUSD   | 2026-02      |                 2 |           1        |          0.681818 |    0.566116 |                0 | ok             |
| AUDUSD   | 2026-03      |                 2 |           1        |        nan        |  nan        |                0 | no_test_rows   |
| USDCAD   | 2025-01      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip    |
| USDCAD   | 2025-02      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip    |
| USDCAD   | 2025-03      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip    |
| USDCAD   | 2025-04      |                 3 |           0        |          0.47591  |    0.394186 |                0 | ok             |
| USDCAD   | 2025-05      |                 2 |           0.333333 |          0.522255 |    0.500991 |                0 | ok             |
| USDCAD   | 2025-06      |                 2 |           1        |          0.701812 |    0.581456 |                0 | ok             |
| USDCAD   | 2025-07      |                 2 |           1        |          0.660345 |    0.551421 |                0 | ok             |
| USDCAD   | 2025-08      |                 2 |           0.666667 |          0.697813 |    0.57826  |                0 | ok             |
| USDCAD   | 2025-09      |                 2 |           1        |          0.509383 |    0.500176 |                0 | ok             |
| USDCAD   | 2025-10      |                 2 |           1        |          0.560714 |    0.507372 |                0 | ok             |
| USDCAD   | 2025-11      |                 1 |           0.5      |          1        |    1        |                0 | ok             |
| USDCAD   | 2025-12      |                 1 |           1        |          1        |    1        |                0 | ok             |
| USDCAD   | 2026-01      |                 1 |           0        |          1        |    1        |                0 | ok             |
| USDCAD   | 2026-02      |                 0 |         nan        |        nan        |  nan        |              nan | no_gate_states |
| USDCAD   | 2026-03      |                 1 |           1        |        nan        |  nan        |                0 | no_test_rows   |
