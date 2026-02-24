# EURUSD OCO Reduced-Core Selection

## Setup
- family_keep: `oco_first_touch_clean`
- barrier_keep: `[2.0, 3.0]`
- horizon_keep: `[5, 6]`
- locked_quantile: `0.9`
- selection_mode: `auto`
- overlap_corr_max: `0.85`
- max_states: `12`
- min_states: `4`

## Selected States
| symbol   |   bar_ticks |   horizon | state_id                                    | family                | regime_desc                  |   barrier_pips |   rows |   months |   avg_month_rows |   mean_gross_pips |   median_gross_pips |   pos_rate |   positive_months |   lb95_trade_mean_gross_pips |   lb95_month_mean_gross_pips | gate_pass   |   selected_rank |   overlap_corr_max |
|:---------|------------:|----------:|:--------------------------------------------|:----------------------|:-----------------------------|---------------:|-------:|---------:|-----------------:|------------------:|--------------------:|-----------:|------------------:|-----------------------------:|-----------------------------:|:------------|----------------:|-------------------:|
| EURUSD   |         100 |         6 | oco_first_touch_clean__high_abs_vel_q70__k2 | oco_first_touch_clean | high_abs_vel_q70;barrier=2.0 |              2 |    678 |        9 |         75.3333  |         2.55605   |                2.1  |   0.70649  |                 9 |                     2.24667  |                    1.77712   | False       |               1 |           0        |
| EURUSD   |         100 |         5 | oco_first_touch_clean__high_abs_vel_q70__k2 | oco_first_touch_clean | high_abs_vel_q70;barrier=2.0 |              2 |    460 |        9 |         51.1111  |         2.27413   |                1.8  |   0.682609 |                 9 |                     1.94129  |                    1.42843   | False       |               1 |           0        |
| EURUSD   |         100 |         6 | oco_first_touch_clean__high_range_q70__k2   | oco_first_touch_clean | high_range_q70;barrier=2.0   |              2 |    836 |        9 |         92.8889  |         2.69306   |                2.1  |   0.699761 |                 9 |                     2.40786  |                    1.73629   | False       |               2 |           0.972385 |
| EURUSD   |         100 |         5 | oco_first_touch_clean__high_range_q70__k2   | oco_first_touch_clean | high_range_q70;barrier=2.0   |              2 |    537 |        9 |         59.6667  |         2.14544   |                1.7  |   0.675978 |                 9 |                     1.8186   |                    1.62879   | False       |               2 |           0.972385 |
| EURUSD   |         100 |         6 | oco_first_touch_clean__ny_overlap__k2       | oco_first_touch_clean | ny_overlap;barrier=2.0       |              2 |    671 |        9 |         74.5556  |         2.24352   |                2.1  |   0.679583 |                 9 |                     1.94259  |                    1.4957    | False       |               3 |           0.91523  |
| EURUSD   |         100 |         5 | oco_first_touch_clean__ny_overlap__k2       | oco_first_touch_clean | ny_overlap;barrier=2.0       |              2 |    407 |        9 |         45.2222  |         1.79189   |                1.2  |   0.638821 |                 8 |                     1.42381  |                    0.809847  | False       |               3 |           0.91523  |
| EURUSD   |         100 |         5 | oco_first_touch_clean__all__k2              | oco_first_touch_clean | all;barrier=2.0              |              2 |    457 |        9 |         50.7778  |         1.97374   |                1.4  |   0.669584 |                 9 |                     1.62316  |                    1.33548   | False       |               4 |           0.947582 |
| EURUSD   |         100 |         6 | oco_first_touch_clean__all__k2              | oco_first_touch_clean | all;barrier=2.0              |              2 |    726 |        9 |         80.6667  |         1.95028   |                1.5  |   0.662534 |                 9 |                     1.66679  |                    1.33354   | False       |               4 |           0.947582 |
| EURUSD   |         100 |         6 | oco_first_touch_clean__london__k3           | oco_first_touch_clean | london;barrier=3.0           |              3 |     93 |        9 |         10.3333  |         1.28817   |                0.7  |   0.602151 |                 6 |                     0.435376 |                    0.305111  | False       |               5 |           0.69778  |
| EURUSD   |         100 |         5 | oco_first_touch_clean__london__k3           | oco_first_touch_clean | london;barrier=3.0           |              3 |     68 |        9 |          7.55556 |         0.0808824 |               -0.15 |   0.455882 |                 4 |                    -0.672721 |                   -0.452989  | False       |               5 |           0.69778  |
| EURUSD   |         100 |         6 | oco_first_touch_clean__all__k3              | oco_first_touch_clean | all;barrier=3.0              |              3 |    122 |        9 |         13.5556  |         1.2541    |                1.4  |   0.606557 |                 7 |                     0.590164 |                    0.24953   | False       |               6 |           0.847733 |
| EURUSD   |         100 |         5 | oco_first_touch_clean__all__k3              | oco_first_touch_clean | all;barrier=3.0              |              3 |     98 |        9 |         10.8889  |         0.734694  |                0.05 |   0.5      |                 6 |                    -0.182704 |                    0.234606  | False       |               6 |           0.847733 |
| EURUSD   |         100 |         6 | oco_first_touch_clean__ny_overlap__k3       | oco_first_touch_clean | ny_overlap;barrier=3.0       |              3 |    129 |        9 |         14.3333  |         0.914729  |                0.9  |   0.565891 |                 7 |                     0.266279 |                    0.113818  | False       |               7 |           0.289875 |
| EURUSD   |         100 |         5 | oco_first_touch_clean__ny_overlap__k3       | oco_first_touch_clean | ny_overlap;barrier=3.0       |              3 |     99 |        9 |         11       |         1.06566   |                0.8  |   0.565657 |                 6 |                     0.29697  |                   -0.0848427 | False       |               7 |           0.289875 |

## Reduced Portfolio Monthly
| test_month   |   rows |   mean_gross_pips |   median_gross_pips |   pos_rate |   threshold |
|:-------------|-------:|------------------:|--------------------:|-----------:|------------:|
| 2025-04      |   1350 |          2.98119  |                2.3  |   0.717778 |    0.582272 |
| 2025-05      |    688 |          2.10698  |                1.7  |   0.671512 |    0.588835 |
| 2025-06      |    763 |          1.62359  |                1.2  |   0.625164 |    0.579694 |
| 2025-07      |    611 |          2.9252   |                2.4  |   0.710311 |    0.592514 |
| 2025-08      |    454 |          2.35551  |                2.15 |   0.696035 |    0.603285 |
| 2025-09      |    441 |          1.72494  |                1.3  |   0.648526 |    0.604969 |
| 2025-10      |    352 |          1.01023  |                1.15 |   0.605114 |    0.602742 |
| 2025-11      |    342 |          0.79883  |                0.5  |   0.576023 |    0.594961 |
| 2025-12      |    380 |          0.920526 |                0.8  |   0.602632 |    0.581245 |

## Reduced Portfolio Gate
- avg_month_rows: `597.89`
- monthly_positive_count: `9`
- capacity_floor_monthly: `3000.00`
- capacity_pass: `False`
