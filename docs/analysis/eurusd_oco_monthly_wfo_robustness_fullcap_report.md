# OCO Monthly WFO Robustness

- predictions: `data/analysis/tick_opportunity_mining/wfo_2025_m3to1_oco_fullcap/EURUSD_oco_monthly_predictions.parquet`
- quantiles: `0.9`
- bootstrap_paths: `600`
- stress_extra_cost_grid: `0.0,0.2,0.4,0.6,0.8,1.0`
- use_exec_selection: `True`
- execution_quantile: `0.9`

## Summary
|   quantile | selection_mode   |   rows |   months |   coverage |   mean_gross_pips |   median_gross_pips |   pos_rate |   lb95_trade_mean_gross_pips |   lb95_month_mean_gross_pips |   positive_months |   pvalue_month_mean_gt0 |   mean_net_pips_costplus_0.00 |   lb95_trade_mean_net_pips_costplus_0.00 |   mean_net_pips_costplus_0.20 |   lb95_trade_mean_net_pips_costplus_0.20 |   mean_net_pips_costplus_0.40 |   lb95_trade_mean_net_pips_costplus_0.40 |   mean_net_pips_costplus_0.60 |   lb95_trade_mean_net_pips_costplus_0.60 |   mean_net_pips_costplus_0.80 |   lb95_trade_mean_net_pips_costplus_0.80 |   mean_net_pips_costplus_1.00 |   lb95_trade_mean_net_pips_costplus_1.00 |   pvalue_bonferroni |   pvalue_fdr_bh |
|-----------:|:-----------------|-------:|---------:|-----------:|------------------:|--------------------:|-----------:|-----------------------------:|-----------------------------:|------------------:|------------------------:|------------------------------:|-----------------------------------------:|------------------------------:|-----------------------------------------:|------------------------------:|-----------------------------------------:|------------------------------:|-----------------------------------------:|------------------------------:|-----------------------------------------:|------------------------------:|-----------------------------------------:|--------------------:|----------------:|
|        0.9 | exec_flag        | 325515 |        9 |  0.0969864 |           1.03932 |                 0.8 |   0.567215 |                      1.02232 |                     0.650819 |                 9 |             1.15261e-09 |                       1.03932 |                                  1.02232 |                      0.839322 |                                 0.821562 |                      0.639322 |                                 0.621901 |                      0.439322 |                                 0.423091 |                      0.239322 |                                 0.221963 |                     0.0393223 |                                0.0234005 |         1.15261e-09 |     1.15261e-09 |

## Monthly Details
|   quantile | test_month   |   rows |   mean_gross_pips |   median_gross_pips |   pos_rate |
|-----------:|:-------------|-------:|------------------:|--------------------:|-----------:|
|        0.9 | 2025-04      | 104584 |         1.37988   |         1.1         |   0.581925 |
|        0.9 | 2025-05      |  38609 |         0.865951  |         0.8         |   0.569945 |
|        0.9 | 2025-06      |  35301 |         0.818351  |         0.7         |   0.565253 |
|        0.9 | 2025-07      |  33004 |         1.40612   |         1.2         |   0.597291 |
|        0.9 | 2025-08      |  28109 |         1.39673   |         1           |   0.586716 |
|        0.9 | 2025-09      |  24657 |         0.736387  |         0.5         |   0.547431 |
|        0.9 | 2025-10      |  25971 |         0.544407  |         0.4         |   0.540796 |
|        0.9 | 2025-11      |  18664 |         0.0903933 |        -2.20268e-13 |   0.480926 |
|        0.9 | 2025-12      |  16616 |         0.723875  |         0.5         |   0.547304 |
