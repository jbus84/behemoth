# Pipeline Snapshot

- generated_at: `2026-02-28 08:46:09 UTC`
- title: `OCO Rolling Strategy Bible`

## Symbol Summary
| symbol   |   mean_gross_pips |   lb95_month_mean_gross_pips |   positive_months |   months_total |   rows_total |   fill_rate_overall |   exact_match_rate |   pos_label_match_rate | tick_exact_overall_pass   |   robustness_quantile |   robustness_rows |   robustness_mean_gross_pips |   robustness_lb95_trade_mean_gross_pips |   robustness_positive_months |   robustness_months |   tick_overshoot_mean_pips |   tick_overshoot_p95_pips | gate_reduced_lb95_month_gt0   | gate_tick_exact   | gate_robust_lb95_trade_gt0   | gate_robust_months_majority   | symbol_all_gates_pass   |
|:---------|------------------:|-----------------------------:|------------------:|---------------:|-------------:|--------------------:|-------------------:|-----------------------:|:--------------------------|----------------------:|------------------:|-----------------------------:|----------------------------------------:|-----------------------------:|--------------------:|---------------------------:|--------------------------:|:------------------------------|:------------------|:-----------------------------|:------------------------------|:------------------------|
| EURUSD   |           1.59847 |                      1.30417 |                 6 |              9 |         4898 |            0.994922 |                  1 |                      1 | True                      |                   0.9 |             59955 |                      1.08782 |                                1.04912  |                            9 |                   9 |                   0.134215 |                       0.5 | True                          | True              | True                         | True                          | True                    |
| GBPUSD   |         nan       |                    nan       |                 0 |              9 |            0 |          nan        |                  1 |                      1 | True                      |                   0.9 |             70579 |                      1.0077  |                                0.973913 |                            9 |                   9 |                   0.134215 |                       0.5 | False                         | True              | True                         | True                          | False                   |
| USDJPY   |         nan       |                    nan       |                 0 |              9 |            0 |          nan        |                  1 |                      1 | True                      |                   0.9 |             77785 |                      1.37716 |                                1.33687  |                            9 |                   9 |                   0.223021 |                       0.7 | False                         | True              | True                         | True                          | False                   |

## Stage Gate Status
| symbol   | gate_reduced_lb95_month_gt0   | gate_tick_exact   | gate_robust_lb95_trade_gt0   | gate_robust_months_majority   | symbol_all_gates_pass   |
|:---------|:------------------------------|:------------------|:-----------------------------|:------------------------------|:------------------------|
| EURUSD   | True                          | True              | True                         | True                          | True                    |
| GBPUSD   | False                         | True              | True                         | True                          | False                   |
| USDJPY   | False                         | True              | True                         | True                          | False                   |

## Figures
- `fig01_symbol_gross_vs_lb95.png`
  ![](../../figures/oco_bible/fig01_symbol_gross_vs_lb95.png)
- `fig02_symbol_tick_exact_rates.png`
  ![](../../figures/oco_bible/fig02_symbol_tick_exact_rates.png)