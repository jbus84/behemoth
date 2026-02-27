# Pipeline Snapshot

- generated_at: `2026-02-27 18:50:29 UTC`
- title: `OCO Rolling Strategy Bible`

## Symbol Summary
| symbol   |   mean_gross_pips |   lb95_month_mean_gross_pips |   positive_months |   months_total |   rows_total |   fill_rate_overall |   exact_match_rate |   pos_label_match_rate | tick_exact_overall_pass   |   robustness_quantile |   robustness_rows |   robustness_mean_gross_pips |   robustness_lb95_trade_mean_gross_pips |   robustness_positive_months |   robustness_months |   tick_overshoot_mean_pips |   tick_overshoot_p95_pips | gate_reduced_lb95_month_gt0   | gate_tick_exact   | gate_robust_lb95_trade_gt0   | gate_robust_months_majority   | symbol_all_gates_pass   |
|:---------|------------------:|-----------------------------:|------------------:|---------------:|-------------:|--------------------:|-------------------:|-----------------------:|:--------------------------|----------------------:|------------------:|-----------------------------:|----------------------------------------:|-----------------------------:|--------------------:|---------------------------:|--------------------------:|:------------------------------|:------------------|:-----------------------------|:------------------------------|:------------------------|
| EURUSD   |           2.76929 |                      2.30087 |                 3 |              9 |          661 |            0.991004 |                  1 |                      1 | True                      |                   0.9 |             59955 |                      1.08782 |                                1.04912  |                            9 |                   9 |                   0.142048 |                       0.6 | True                          | True              | True                         | True                          | True                    |
| GBPUSD   |           2.07056 |                      1.80556 |                 6 |              9 |         1916 |            0.995842 |                  1 |                      1 | True                      |                   0.9 |             70579 |                      1.0077  |                                0.973913 |                            9 |                   9 |                   0.136394 |                       0.5 | True                          | True              | True                         | True                          | True                    |
| USDJPY   |           3.00368 |                      2.54229 |                 6 |              9 |         2258 |            0.990351 |                  1 |                      1 | True                      |                   0.9 |             77785 |                      1.37716 |                                1.33687  |                            9 |                   9 |                   0.230743 |                       0.7 | True                          | True              | True                         | True                          | True                    |

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