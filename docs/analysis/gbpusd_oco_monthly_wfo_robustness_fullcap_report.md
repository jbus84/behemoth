# OCO Monthly WFO Robustness

- predictions: `data/analysis/tick_opportunity_mining/wfo_2025_m3to1_oco_fullcap_gbpusd/GBPUSD_oco_monthly_predictions.parquet`
- quantiles: `0.9`
- bootstrap_paths: `600`
- stress_extra_cost_grid: `0.0,0.2,0.4,0.6,0.8,1.0`
- use_exec_selection: `True`
- execution_quantile: `0.9`

## Summary
|   quantile | selection_mode   |   rows |   months |   coverage |   mean_gross_pips |   median_gross_pips |   pos_rate |   lb95_trade_mean_gross_pips |   lb95_month_mean_gross_pips |   positive_months |   pvalue_month_mean_gt0 |   mean_net_pips_costplus_0.00 |   lb95_trade_mean_net_pips_costplus_0.00 |   mean_net_pips_costplus_0.20 |   lb95_trade_mean_net_pips_costplus_0.20 |   mean_net_pips_costplus_0.40 |   lb95_trade_mean_net_pips_costplus_0.40 |   mean_net_pips_costplus_0.60 |   lb95_trade_mean_net_pips_costplus_0.60 |   mean_net_pips_costplus_0.80 |   lb95_trade_mean_net_pips_costplus_0.80 |   mean_net_pips_costplus_1.00 |   lb95_trade_mean_net_pips_costplus_1.00 |   pvalue_bonferroni |   pvalue_fdr_bh |
|-----------:|:-----------------|-------:|---------:|-----------:|------------------:|--------------------:|-----------:|-----------------------------:|-----------------------------:|------------------:|------------------------:|------------------------------:|-----------------------------------------:|------------------------------:|-----------------------------------------:|------------------------------:|-----------------------------------------:|------------------------------:|-----------------------------------------:|------------------------------:|-----------------------------------------:|------------------------------:|-----------------------------------------:|--------------------:|----------------:|
|        0.9 | exec_flag        | 414128 |        9 |  0.0969355 |           1.01745 |                 0.9 |   0.572289 |                      1.00211 |                      0.92869 |                 9 |                       0 |                       1.01745 |                                  1.00211 |                      0.817446 |                                 0.804603 |                      0.617446 |                                 0.603551 |                      0.417446 |                                 0.404395 |                      0.217446 |                                 0.202803 |                     0.0174456 |                               0.00393244 |                   0 |               0 |

## Monthly Details
|   quantile | test_month   |   rows |   mean_gross_pips |   median_gross_pips |   pos_rate |
|-----------:|:-------------|-------:|------------------:|--------------------:|-----------:|
|        0.9 | 2025-04      |  83746 |          1.15913  |                 1   |   0.578416 |
|        0.9 | 2025-05      |  47327 |          1.00266  |                 0.9 |   0.572168 |
|        0.9 | 2025-06      |  41762 |          1.0272   |                 0.9 |   0.573632 |
|        0.9 | 2025-07      |  45641 |          1.1757   |                 1.1 |   0.593721 |
|        0.9 | 2025-08      |  34547 |          1.05943  |                 0.9 |   0.574985 |
|        0.9 | 2025-09      |  37499 |          0.931433 |                 0.7 |   0.565722 |
|        0.9 | 2025-10      |  45951 |          1.01951  |                 0.8 |   0.571565 |
|        0.9 | 2025-11      |  42786 |          0.808285 |                 0.7 |   0.554691 |
|        0.9 | 2025-12      |  34869 |          0.783257 |                 0.6 |   0.55502  |
