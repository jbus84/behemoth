# OCO Monthly WFO Robustness

- predictions: `data/analysis/tick_opportunity_mining/wfo_2025_m3to1_oco_smoke/EURUSD_oco_monthly_predictions.parquet`
- quantiles: `0.9`
- bootstrap_paths: `300`
- stress_extra_cost_grid: `0.0,0.2,0.4,0.6`
- use_exec_selection: `True`
- execution_quantile: `0.9`

## Summary
|   quantile | selection_mode   |   rows |   months |   coverage |   mean_gross_pips |   median_gross_pips |   pos_rate |   lb95_trade_mean_gross_pips |   lb95_month_mean_gross_pips |   positive_months |   pvalue_month_mean_gt0 |   mean_net_pips_costplus_0.00 |   lb95_trade_mean_net_pips_costplus_0.00 |   mean_net_pips_costplus_0.20 |   lb95_trade_mean_net_pips_costplus_0.20 |   mean_net_pips_costplus_0.40 |   lb95_trade_mean_net_pips_costplus_0.40 |   mean_net_pips_costplus_0.60 |   lb95_trade_mean_net_pips_costplus_0.60 |   pvalue_bonferroni |   pvalue_fdr_bh |
|-----------:|:-----------------|-------:|---------:|-----------:|------------------:|--------------------:|-----------:|-----------------------------:|-----------------------------:|------------------:|------------------------:|------------------------------:|-----------------------------------------:|------------------------------:|-----------------------------------------:|------------------------------:|-----------------------------------------:|------------------------------:|-----------------------------------------:|--------------------:|----------------:|
|        0.9 | exec_flag        |  24494 |        9 |  0.0969775 |          0.866184 |                 0.7 |   0.561689 |                      0.80384 |                     0.530805 |                 8 |             1.38864e-07 |                      0.866184 |                                  0.80384 |                      0.666184 |                                 0.606268 |                      0.466184 |                                 0.409112 |                      0.266184 |                                 0.209505 |         1.38864e-07 |     1.38864e-07 |

## Monthly Details
|   quantile | test_month   |   rows |   mean_gross_pips |   median_gross_pips |   pos_rate |
|-----------:|:-------------|-------:|------------------:|--------------------:|-----------:|
|        0.9 | 2025-04      |   7576 |        1.07002    |                 0.8 |   0.56349  |
|        0.9 | 2025-05      |   2795 |        0.823435   |                 0.8 |   0.568515 |
|        0.9 | 2025-06      |   3008 |        0.791755   |                 0.7 |   0.573803 |
|        0.9 | 2025-07      |   2393 |        1.53811    |                 1.4 |   0.608023 |
|        0.9 | 2025-08      |   2110 |        0.977393   |                 0.7 |   0.564455 |
|        0.9 | 2025-09      |   1875 |        0.609813   |                 0.5 |   0.552533 |
|        0.9 | 2025-10      |   1878 |        0.549627   |                 0.6 |   0.560703 |
|        0.9 | 2025-11      |   1567 |       -0.00682833 |                -0.1 |   0.476707 |
|        0.9 | 2025-12      |   1292 |        0.401548   |                 0.4 |   0.535604 |
