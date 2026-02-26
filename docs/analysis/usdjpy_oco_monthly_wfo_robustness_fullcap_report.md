# OCO Monthly WFO Robustness

- predictions: `data/analysis/tick_opportunity_mining/wfo_2025_m3to1_oco_fullcap_usdjpy/USDJPY_oco_monthly_predictions.parquet`
- quantiles: `0.9`
- bootstrap_paths: `600`
- stress_extra_cost_grid: `0.0,0.2,0.4,0.6,0.8,1.0`
- use_exec_selection: `True`
- execution_quantile: `0.9`

## Summary
|   quantile | selection_mode   |   rows |   months |   coverage |   mean_gross_pips |   median_gross_pips |   pos_rate |   lb95_trade_mean_gross_pips |   lb95_month_mean_gross_pips |   positive_months |   pvalue_month_mean_gt0 |   mean_net_pips_costplus_0.00 |   lb95_trade_mean_net_pips_costplus_0.00 |   mean_net_pips_costplus_0.20 |   lb95_trade_mean_net_pips_costplus_0.20 |   mean_net_pips_costplus_0.40 |   lb95_trade_mean_net_pips_costplus_0.40 |   mean_net_pips_costplus_0.60 |   lb95_trade_mean_net_pips_costplus_0.60 |   mean_net_pips_costplus_0.80 |   lb95_trade_mean_net_pips_costplus_0.80 |   mean_net_pips_costplus_1.00 |   lb95_trade_mean_net_pips_costplus_1.00 |   pvalue_bonferroni |   pvalue_fdr_bh |
|-----------:|:-----------------|-------:|---------:|-----------:|------------------:|--------------------:|-----------:|-----------------------------:|-----------------------------:|------------------:|------------------------:|------------------------------:|-----------------------------------------:|------------------------------:|-----------------------------------------:|------------------------------:|-----------------------------------------:|------------------------------:|-----------------------------------------:|------------------------------:|-----------------------------------------:|------------------------------:|-----------------------------------------:|--------------------:|----------------:|
|        0.9 | exec_flag        | 459585 |        9 |   0.101114 |           1.37853 |                 1.2 |   0.593838 |                      1.36145 |                      1.17962 |                 9 |                       0 |                       1.37853 |                                  1.36145 |                       1.17853 |                                  1.16268 |                      0.978528 |                                 0.961219 |                      0.778528 |                                 0.762256 |                      0.578528 |                                 0.560034 |                      0.378528 |                                 0.362218 |                   0 |               0 |

## Monthly Details
|   quantile | test_month   |   rows |   mean_gross_pips |   median_gross_pips |   pos_rate |
|-----------:|:-------------|-------:|------------------:|--------------------:|-----------:|
|        0.9 | 2025-04      |  84484 |          1.73024  |                 1.5 |   0.608115 |
|        0.9 | 2025-05      |  54903 |          1.79633  |                 1.6 |   0.61523  |
|        0.9 | 2025-06      |  61895 |          1.11865  |                 1.1 |   0.592213 |
|        0.9 | 2025-07      |  52735 |          1.28406  |                 1.1 |   0.583711 |
|        0.9 | 2025-08      |  36773 |          1.63566  |                 1.5 |   0.608327 |
|        0.9 | 2025-09      |  44757 |          1.15203  |                 1   |   0.585294 |
|        0.9 | 2025-10      |  51927 |          1.31118  |                 1.3 |   0.592697 |
|        0.9 | 2025-11      |  38970 |          0.826523 |                 0.5 |   0.548037 |
|        0.9 | 2025-12      |  33141 |          1.20066  |                 1.1 |   0.592257 |
