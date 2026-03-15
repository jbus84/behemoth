### Auto Snapshot - Stage 04

- generated_at: `2026-03-15 12:55:53 UTC`
- Execution realism is applied with tick first-cross overshoot.
- Session-aware rolling caps are built causally (20D lookback, q=0.90) before E11 dispersion is measured.
- Cap curve highlights fill-rate versus signal-level expectancy.
- E11-E13 are informational execution diagnostics: session dispersion, plateau width, and non-fill opportunity cost.
- Policy status artifact: data/analysis/tick_opportunity_mining_dukascopy_candidate/stage04_execution_policy_status.csv
- Session cap artifact: data/analysis/tick_opportunity_mining_dukascopy_candidate/stage04_cap_policy_by_session.csv

#### Key Results
| symbol   |   rows |   touch_found_rate |   base_mean_gross_pips |   tick_overshoot_mean_pips |   tick_overshoot_p95_pips |   e11_session_overshoot_dispersion |   e12_cap_plateau_width_pips |   e13_nonfill_opportunity_cost_pips |
|:---------|-------:|-------------------:|-----------------------:|---------------------------:|--------------------------:|-----------------------------------:|-----------------------------:|------------------------------------:|
| EURUSD   | 422980 |           0.999794 |               1.62782  |                   0.146332 |                       0.5 |                           0.292584 |                          1.2 |                           0.121346  |
| GBPUSD   | 437491 |           0.999995 |               0.996428 |                   0.141709 |                       0.5 |                           0.474851 |                          1.2 |                           0.118672  |
| USDJPY   | 475390 |           0.999922 |               1.54201  |                   0.226204 |                       0.7 |                           0.234236 |                          1.2 |                           0.197218  |
| USDCHF   | 347520 |           0.998806 |               0.713835 |                   0.150078 |                       0.5 |                           0.799323 |                          1.2 |                           0.10578   |
| AUDUSD   | 449651 |           0.993924 |               0.693111 |                   0.114049 |                       0.4 |                           0.239465 |                          1.2 |                           0.0935749 |
| USDCAD   | 485352 |           0.998995 |               1.19391  |                   0.227835 |                       0.9 |                           0.366785 |                          0.8 |                           0.171319  |

#### Interpretation Notes
- Execution realism is applied with tick first-cross overshoot.
- Session-aware rolling caps are built causally (20D lookback, q=0.90) before E11 dispersion is measured.
- Cap curve highlights fill-rate versus signal-level expectancy.

#### Action Trigger Summary
| trigger            | threshold_or_signal   | action_code                   | action_summary                                                          |
|:-------------------|:----------------------|:------------------------------|:------------------------------------------------------------------------|
| hard_gate_fail     | status=fail           | A3_HALT_RECALIBRATE           | Block promotion and rerun upstream stage diagnostics before continuing. |
| monitoring_warning | band=amber            | A0_MONITOR/A1_RECALIBRATE_CAP | Apply stage runbook remediation and confirm next-run recovery.          |

#### Details
| symbol   |   cap_pips |   fill_rate |   mean_per_signal_full_overshoot |
|:---------|-----------:|------------:|---------------------------------:|
| AUDUSD   |        0.5 |    0.962019 |                         0.539424 |
| AUDUSD   |        0.8 |    0.978981 |                         0.55708  |
| AUDUSD   |        1   |    0.983681 |                         0.566019 |
| AUDUSD   |        1.2 |    0.985604 |                         0.571121 |
| AUDUSD   |        1.5 |    0.988364 |                         0.573006 |
| AUDUSD   |        2   |    0.990582 |                         0.579132 |
| EURUSD   |        0.5 |    0.938775 |                         1.33977  |
| EURUSD   |        0.8 |    0.97211  |                         1.40998  |
| EURUSD   |        1   |    0.984635 |                         1.44246  |
| EURUSD   |        1.2 |    0.988288 |                         1.4503   |
| EURUSD   |        1.5 |    0.99234  |                         1.46262  |
| EURUSD   |        2   |    0.995657 |                         1.47161  |
| GBPUSD   |        0.5 |    0.94583  |                         0.793709 |
| GBPUSD   |        0.8 |    0.979721 |                         0.828556 |
| GBPUSD   |        1   |    0.987316 |                         0.841986 |
| GBPUSD   |        1.2 |    0.990299 |                         0.848876 |
| GBPUSD   |        1.5 |    0.993259 |                         0.85082  |
| GBPUSD   |        2   |    0.995591 |                         0.849092 |
| USDCAD   |        0.5 |    0.886499 |                         0.752302 |
| USDCAD   |        0.8 |    0.940513 |                         0.844493 |
| USDCAD   |        1   |    0.961937 |                         0.88737  |
| USDCAD   |        1.2 |    0.969729 |                         0.91343  |
| USDCAD   |        1.5 |    0.977567 |                         0.925304 |
| USDCAD   |        2   |    0.98654  |                         0.940711 |
| USDCHF   |        0.5 |    0.950239 |                         0.521361 |
| USDCHF   |        0.8 |    0.972076 |                         0.540015 |
| USDCHF   |        1   |    0.978496 |                         0.547474 |
| USDCHF   |        1.2 |    0.981037 |                         0.552098 |
| USDCHF   |        1.5 |    0.9851   |                         0.555174 |
| USDCHF   |        2   |    0.988602 |                         0.560666 |
| USDJPY   |        0.5 |    0.915009 |                         1.1819   |
| USDJPY   |        0.8 |    0.962246 |                         1.25544  |
| USDJPY   |        1   |    0.977713 |                         1.27857  |
| USDJPY   |        1.2 |    0.982408 |                         1.28485  |
| USDJPY   |        1.5 |    0.989335 |                         1.29846  |
| USDJPY   |        2   |    0.993715 |                         1.30666  |

#### Plots
![stage_04_stop_limit_caps](../../figures/oco_bible/stage_04_stop_limit_caps.png)
![stage_04_execution_policy_bands](../../figures/oco_bible/stage_04_execution_policy_bands.png)

#### Policy Status
| symbol   |   metrics_total |   green_metric_count |   amber_metric_count |   red_metric_count | worst_band   | recommended_action_code   | recommended_action_summary                               | red_metrics   | amber_metrics           |
|:---------|----------------:|---------------------:|---------------------:|-------------------:|:-------------|:--------------------------|:---------------------------------------------------------|:--------------|:------------------------|
| AUDUSD   |               5 |                    5 |                    0 |                  0 | green        | A0_MONITOR                | within execution policy limits; monitor only             |               |                         |
| EURUSD   |               5 |                    5 |                    0 |                  0 | green        | A0_MONITOR                | within execution policy limits; monitor only             |               |                         |
| GBPUSD   |               5 |                    5 |                    0 |                  0 | green        | A0_MONITOR                | within execution policy limits; monitor only             |               |                         |
| USDCAD   |               5 |                    4 |                    1 |                  0 | amber        | A2_SESSION_GUARD          | overshoot tail elevated; apply session guard and monitor |               | tick_overshoot_p95_pips |
| USDCHF   |               5 |                    5 |                    0 |                  0 | green        | A0_MONITOR                | within execution policy limits; monitor only             |               |                         |
| USDJPY   |               5 |                    4 |                    1 |                  0 | amber        | A2_SESSION_GUARD          | overshoot tail elevated; apply session guard and monitor |               | tick_overshoot_p95_pips |

- policy_csv: `data/analysis/tick_opportunity_mining_dukascopy_candidate/stage04_execution_policy_status.csv`

#### Policy Metric Mapping (Detail)
| symbol   | metric_id                         |   metric_value | band   | action_code      | green_threshold   | amber_threshold   |
|:---------|:----------------------------------|---------------:|:-------|:-----------------|:------------------|:------------------|
| EURUSD   | E11_session_overshoot_dispersion  |      0.292584  | green  | A0_MONITOR       | <= 1.0000         | <= 1.3000         |
| EURUSD   | E12_cap_plateau_width_pips        |      1.2       | green  | A0_MONITOR       | >= 0.5000         | >= 0.3000         |
| EURUSD   | E13_nonfill_opportunity_cost_pips |      0.121346  | green  | A0_MONITOR       | <= 0.2000         | <= 0.3500         |
| EURUSD   | erosion_spread_fee_plus_slip      |      0.156207  | green  | A0_MONITOR       | <= 0.3000         | <= 0.5000         |
| EURUSD   | tick_overshoot_p95_pips           |      0.5       | green  | A0_MONITOR       | <= 0.7000         | <= 1.0000         |
| GBPUSD   | E11_session_overshoot_dispersion  |      0.474851  | green  | A0_MONITOR       | <= 1.0000         | <= 1.3000         |
| GBPUSD   | E12_cap_plateau_width_pips        |      1.2       | green  | A0_MONITOR       | >= 0.5000         | >= 0.3000         |
| GBPUSD   | E13_nonfill_opportunity_cost_pips |      0.118672  | green  | A0_MONITOR       | <= 0.2000         | <= 0.3500         |
| GBPUSD   | erosion_spread_fee_plus_slip      |      0.145608  | green  | A0_MONITOR       | <= 0.3000         | <= 0.5000         |
| GBPUSD   | tick_overshoot_p95_pips           |      0.5       | green  | A0_MONITOR       | <= 0.7000         | <= 1.0000         |
| USDJPY   | E11_session_overshoot_dispersion  |      0.234236  | green  | A0_MONITOR       | <= 1.0000         | <= 1.3000         |
| USDJPY   | E12_cap_plateau_width_pips        |      1.2       | green  | A0_MONITOR       | >= 0.5000         | >= 0.3000         |
| USDJPY   | E13_nonfill_opportunity_cost_pips |      0.197218  | green  | A0_MONITOR       | <= 0.2000         | <= 0.3500         |
| USDJPY   | erosion_spread_fee_plus_slip      |      0.235347  | green  | A0_MONITOR       | <= 0.3000         | <= 0.5000         |
| USDJPY   | tick_overshoot_p95_pips           |      0.7       | amber  | A2_SESSION_GUARD | <= 0.7000         | <= 1.0000         |
| USDCHF   | E11_session_overshoot_dispersion  |      0.799323  | green  | A0_MONITOR       | <= 1.0000         | <= 1.3000         |
| USDCHF   | E12_cap_plateau_width_pips        |      1.2       | green  | A0_MONITOR       | >= 0.5000         | >= 0.3000         |
| USDCHF   | E13_nonfill_opportunity_cost_pips |      0.10578   | green  | A0_MONITOR       | <= 0.2000         | <= 0.3500         |
| USDCHF   | erosion_spread_fee_plus_slip      |      0.153169  | green  | A0_MONITOR       | <= 0.3000         | <= 0.5000         |
| USDCHF   | tick_overshoot_p95_pips           |      0.5       | green  | A0_MONITOR       | <= 0.7000         | <= 1.0000         |
| AUDUSD   | E11_session_overshoot_dispersion  |      0.239465  | green  | A0_MONITOR       | <= 1.0000         | <= 1.3000         |
| AUDUSD   | E12_cap_plateau_width_pips        |      1.2       | green  | A0_MONITOR       | >= 0.5000         | >= 0.3000         |
| AUDUSD   | E13_nonfill_opportunity_cost_pips |      0.0935749 | green  | A0_MONITOR       | <= 0.2000         | <= 0.3500         |
| AUDUSD   | erosion_spread_fee_plus_slip      |      0.113979  | green  | A0_MONITOR       | <= 0.3000         | <= 0.5000         |
| AUDUSD   | tick_overshoot_p95_pips           |      0.4       | green  | A0_MONITOR       | <= 0.7000         | <= 1.0000         |
| USDCAD   | E11_session_overshoot_dispersion  |      0.366785  | green  | A0_MONITOR       | <= 1.0000         | <= 1.3000         |
| USDCAD   | E12_cap_plateau_width_pips        |      0.8       | green  | A0_MONITOR       | >= 0.5000         | >= 0.3000         |
| USDCAD   | E13_nonfill_opportunity_cost_pips |      0.171319  | green  | A0_MONITOR       | <= 0.2000         | <= 0.3500         |
| USDCAD   | erosion_spread_fee_plus_slip      |      0.253196  | green  | A0_MONITOR       | <= 0.3000         | <= 0.5000         |
| USDCAD   | tick_overshoot_p95_pips           |      0.9       | amber  | A2_SESSION_GUARD | <= 0.7000         | <= 1.0000         |

#### Session Rolling Cap Policy
| symbol   | session_bucket   |   lookback_days |   cap_quantile |   cap_pips |   rows_used |   session_cap_rows |   global_cap_rows |   fallback_rows |
|:---------|:-----------------|----------------:|---------------:|-----------:|------------:|-------------------:|------------------:|----------------:|
| EURUSD   | ASIA             |              20 |            0.9 |        0.1 |      101477 |             101277 |               149 |              51 |
| EURUSD   | LATE             |              20 |            0.9 |        0.4 |       24807 |              23809 |               996 |               2 |
| EURUSD   | LONDON           |              20 |            0.9 |        0.2 |       97412 |              97212 |                53 |             147 |
| EURUSD   | NY               |              20 |            0.9 |        0.2 |      198920 |             198720 |               200 |               0 |
| GBPUSD   | ASIA             |              20 |            0.9 |        0.3 |       81502 |              81302 |               190 |              10 |
| GBPUSD   | LATE             |              20 |            0.9 |        0.6 |       12138 |              11176 |               927 |              35 |
| GBPUSD   | LONDON           |              20 |            0.9 |        0.3 |      134125 |             133925 |                45 |             155 |
| GBPUSD   | NY               |              20 |            0.9 |        0.3 |      209464 |             209264 |               200 |               0 |
| USDJPY   | ASIA             |              20 |            0.9 |        0.5 |      205299 |             205099 |                65 |             135 |
| USDJPY   | LATE             |              20 |            0.9 |        1.9 |       31191 |              30991 |               135 |              65 |
| USDJPY   | LONDON           |              20 |            0.9 |        0.5 |       85986 |              85786 |               200 |               0 |
| USDJPY   | NY               |              20 |            0.9 |        0.6 |      152464 |             152264 |               200 |               0 |
| USDCHF   | ASIA             |              20 |            0.9 |        0.1 |       75624 |              75424 |                87 |             113 |
| USDCHF   | LATE             |              20 |            0.9 |        1.4 |       11870 |              10861 |               925 |              84 |
| USDCHF   | LONDON           |              20 |            0.9 |        0.1 |       90500 |              90300 |               197 |               3 |
| USDCHF   | NY               |              20 |            0.9 |        0.2 |      168850 |             168650 |               200 |               0 |
| AUDUSD   | ASIA             |              20 |            0.9 |        0.2 |      181402 |             181202 |                81 |             119 |
| AUDUSD   | LATE             |              20 |            0.9 |        1.4 |       19151 |              18198 |               920 |              33 |
| AUDUSD   | LONDON           |              20 |            0.9 |        0.2 |       57712 |              57512 |               152 |              48 |
| AUDUSD   | NY               |              20 |            0.9 |        0.2 |      188330 |             188130 |               200 |               0 |
| USDCAD   | ASIA             |              20 |            0.9 |        0.2 |       72192 |              71992 |               162 |              38 |
| USDCAD   | LATE             |              20 |            0.9 |        0.7 |       24790 |              23899 |               729 |             162 |
| USDCAD   | LONDON           |              20 |            0.9 |        0.3 |       67635 |              67435 |               200 |               0 |
| USDCAD   | NY               |              20 |            0.9 |        0.3 |      319751 |             319551 |               200 |               0 |
