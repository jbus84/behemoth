# OCO Monthly WFO Robustness

- predictions: `data/analysis/tick_opportunity_mining/wfo_2025_m3to1_oco_smoke_usdjpy/USDJPY_oco_monthly_predictions.parquet`
- quantiles: `0.9`
- bootstrap_paths: `300`
- stress_extra_cost_grid: `0.0,0.2,0.4,0.6`
- use_exec_selection: `True`
- execution_quantile: `0.9`

## Summary
|   quantile | selection_mode   |   rows |   months |   coverage |   mean_gross_pips |   median_gross_pips |   pos_rate |   lb95_trade_mean_gross_pips |   lb95_month_mean_gross_pips |   positive_months |   pvalue_month_mean_gt0 |   mean_net_pips_costplus_0.00 |   lb95_trade_mean_net_pips_costplus_0.00 |   mean_net_pips_costplus_0.20 |   lb95_trade_mean_net_pips_costplus_0.20 |   mean_net_pips_costplus_0.40 |   lb95_trade_mean_net_pips_costplus_0.40 |   mean_net_pips_costplus_0.60 |   lb95_trade_mean_net_pips_costplus_0.60 |   pvalue_bonferroni |   pvalue_fdr_bh |
|-----------:|:-----------------|-------:|---------:|-----------:|------------------:|--------------------:|-----------:|-----------------------------:|-----------------------------:|------------------:|------------------------:|------------------------------:|-----------------------------------------:|------------------------------:|-----------------------------------------:|------------------------------:|-----------------------------------------:|------------------------------:|-----------------------------------------:|--------------------:|----------------:|
|        0.9 | exec_flag        |  34674 |        9 |    0.10339 |           1.18714 |                 1.1 |   0.584963 |                      1.12905 |                      1.06928 |                 9 |                       0 |                       1.18714 |                                  1.12905 |                      0.987143 |                                 0.929976 |                      0.787143 |                                 0.734484 |                      0.587143 |                                 0.532717 |                   0 |               0 |

## Monthly Details
|   quantile | test_month   |   rows |   mean_gross_pips |   median_gross_pips |   pos_rate |
|-----------:|:-------------|-------:|------------------:|--------------------:|-----------:|
|        0.9 | 2025-04      |   5998 |          1.2357   |                 1   |   0.577859 |
|        0.9 | 2025-05      |   4129 |          1.42017  |                 1.3 |   0.598934 |
|        0.9 | 2025-06      |   5313 |          1.11265  |                 1.2 |   0.592133 |
|        0.9 | 2025-07      |   3700 |          1.32643  |                 1   |   0.576757 |
|        0.9 | 2025-08      |   2704 |          1.63232  |                 1.5 |   0.60429  |
|        0.9 | 2025-09      |   3673 |          0.95309  |                 0.8 |   0.569834 |
|        0.9 | 2025-10      |   3890 |          1.06429  |                 1.1 |   0.593316 |
|        0.9 | 2025-11      |   2812 |          0.876067 |                 0.7 |   0.560455 |
|        0.9 | 2025-12      |   2455 |          1.0387   |                 1.1 |   0.591853 |
