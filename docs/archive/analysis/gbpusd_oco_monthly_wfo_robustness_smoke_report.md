# OCO Monthly WFO Robustness

- predictions: `data/analysis/tick_opportunity_mining/wfo_2025_m3to1_oco_smoke_gbpusd/GBPUSD_oco_monthly_predictions.parquet`
- quantiles: `0.9`
- bootstrap_paths: `300`
- stress_extra_cost_grid: `0.0,0.2,0.4,0.6`
- use_exec_selection: `True`
- execution_quantile: `0.9`

## Summary
|   quantile | selection_mode   |   rows |   months |   coverage |   mean_gross_pips |   median_gross_pips |   pos_rate |   lb95_trade_mean_gross_pips |   lb95_month_mean_gross_pips |   positive_months |   pvalue_month_mean_gt0 |   mean_net_pips_costplus_0.00 |   lb95_trade_mean_net_pips_costplus_0.00 |   mean_net_pips_costplus_0.20 |   lb95_trade_mean_net_pips_costplus_0.20 |   mean_net_pips_costplus_0.40 |   lb95_trade_mean_net_pips_costplus_0.40 |   mean_net_pips_costplus_0.60 |   lb95_trade_mean_net_pips_costplus_0.60 |   pvalue_bonferroni |   pvalue_fdr_bh |
|-----------:|:-----------------|-------:|---------:|-----------:|------------------:|--------------------:|-----------:|-----------------------------:|-----------------------------:|------------------:|------------------------:|------------------------------:|-----------------------------------------:|------------------------------:|-----------------------------------------:|------------------------------:|-----------------------------------------:|------------------------------:|-----------------------------------------:|--------------------:|----------------:|
|        0.9 | exec_flag        |  32026 |        9 |   0.101441 |           0.75262 |                 0.6 |   0.553019 |                     0.707345 |                     0.613412 |                 9 |                       0 |                       0.75262 |                                 0.707345 |                       0.55262 |                                 0.505569 |                       0.35262 |                                  0.30839 |                       0.15262 |                                   0.1002 |                   0 |               0 |

## Monthly Details
|   quantile | test_month   |   rows |   mean_gross_pips |   median_gross_pips |   pos_rate |
|-----------:|:-------------|-------:|------------------:|--------------------:|-----------:|
|        0.9 | 2025-04      |   5977 |          0.956584 |                 0.8 |   0.561653 |
|        0.9 | 2025-05      |   3382 |          0.807451 |                 0.7 |   0.559728 |
|        0.9 | 2025-06      |   3343 |          0.763805 |                 0.8 |   0.559677 |
|        0.9 | 2025-07      |   3473 |          1.10737  |                 1   |   0.596602 |
|        0.9 | 2025-08      |   2756 |          0.709289 |                 0.6 |   0.545356 |
|        0.9 | 2025-09      |   2897 |          0.612979 |                 0.6 |   0.550224 |
|        0.9 | 2025-10      |   3665 |          0.730177 |                 0.5 |   0.539973 |
|        0.9 | 2025-11      |   3565 |          0.505442 |                 0.4 |   0.531276 |
|        0.9 | 2025-12      |   2968 |          0.35283  |                 0.3 |   0.521563 |
