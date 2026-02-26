# Pipeline Snapshot

- generated_at: `2026-02-26 21:20:14 UTC`
- title: `OCO Rolling Strategy Bible`

## Symbol Summary
| symbol   |   mean_gross_pips |   lb95_month_mean_gross_pips |   positive_months |   months_total |   rows_total |   fill_rate_overall |   exact_match_rate |   pos_label_match_rate | tick_exact_overall_pass   |   robustness_quantile |   robustness_rows |   robustness_mean_gross_pips |   robustness_lb95_trade_mean_gross_pips |   robustness_positive_months |   robustness_months |   tick_overshoot_mean_pips |   tick_overshoot_p95_pips | gate_reduced_lb95_month_gt0   | gate_tick_exact   | gate_robust_lb95_trade_gt0   | gate_robust_months_majority   | symbol_all_gates_pass   |
|:---------|------------------:|-----------------------------:|------------------:|---------------:|-------------:|--------------------:|-------------------:|-----------------------:|:--------------------------|----------------------:|------------------:|-----------------------------:|----------------------------------------:|-----------------------------:|--------------------:|---------------------------:|--------------------------:|:------------------------------|:------------------|:-----------------------------|:------------------------------|:------------------------|
| EURUSD   |           1.59847 |                      1.30417 |                 6 |              9 |         4898 |            0.994922 |                  1 |                      1 | True                      |                   0.9 |            325515 |                      1.03932 |                                 1.02232 |                            9 |                   9 |                   0.136206 |                       0.5 | True                          | True              | True                         | True                          | True                    |
| GBPUSD   |           2.51775 |                      2.21592 |                 6 |              9 |         6824 |            0.990421 |                  1 |                      1 | True                      |                   0.9 |            414128 |                      1.01745 |                                 1.00211 |                            9 |                   9 |                   0.141476 |                       0.5 | True                          | True              | True                         | True                          | True                    |
| USDJPY   |           3.31998 |                      2.95901 |                 6 |              9 |         7843 |            0.987783 |                  1 |                      1 | True                      |                   0.9 |            459585 |                      1.37853 |                                 1.36145 |                            9 |                   9 |                   0.221513 |                       0.7 | True                          | True              | True                         | True                          | True                    |

## Stage Gate Status
| symbol   | gate_reduced_lb95_month_gt0   | gate_tick_exact   | gate_robust_lb95_trade_gt0   | gate_robust_months_majority   | symbol_all_gates_pass   |
|:---------|:------------------------------|:------------------|:-----------------------------|:------------------------------|:------------------------|
| EURUSD   | True                          | True              | True                         | True                          | True                    |
| GBPUSD   | True                          | True              | True                         | True                          | True                    |
| USDJPY   | True                          | True              | True                         | True                          | True                    |

## Figures
- `fig01_symbol_gross_vs_lb95.png`
  ![](../../figures/oco_bible/fig01_symbol_gross_vs_lb95.png)
- `fig02_symbol_tick_exact_rates.png`
  ![](../../figures/oco_bible/fig02_symbol_tick_exact_rates.png)