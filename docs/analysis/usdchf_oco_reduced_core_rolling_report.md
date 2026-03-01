# OCO Tick-Exact Shortlist Verification

## Setup
- symbol: `USDCHF`
- family_required: `oco_first_touch_clean`
- locked_quantile: `0.9`
- selection_mode: `auto`
- oco_hold_mode: `from_touch`
- oco_include_no_touch: `True`
- abs_tol_pips: `1e-09`

## Summary
| symbol   |   locked_quantile | oco_hold_mode   | oco_include_no_touch   |   rows_selected |   rows_mapped |   rows_verified |   mean_abs_err_pips |   p99_abs_err_pips |   max_abs_err_pips |   exact_match_rate |   sign_match_rate |   pos_label_match_rate |   clean_violation_count |   both_window_count |   undecided_count |   min_exact_match_rate |   min_pos_label_match_rate | pass_exact_match   | pass_pos_label_match   | pass_clean   | overall_pass   |
|:---------|------------------:|:----------------|:-----------------------|----------------:|--------------:|----------------:|--------------------:|-------------------:|-------------------:|-------------------:|------------------:|-----------------------:|------------------------:|--------------------:|------------------:|-----------------------:|---------------------------:|:-------------------|:-----------------------|:-------------|:---------------|
| USDCHF   |               0.9 | from_touch      | True                   |           29279 |         29279 |           29279 |           0.0554595 |                  0 |               48.8 |           0.991154 |          0.991086 |               0.998258 |                     261 |                 261 |                56 |                  0.999 |                      0.999 | False              | False                  | False        | False          |

## By State
|   bar_ticks |   horizon | state_id                                    |   rows_selected |   rows_mapped |   rows_verified |   mean_abs_err_pips |   p99_abs_err_pips |   max_abs_err_pips |   exact_match_rate |   sign_match_rate |   pos_label_match_rate |   clean_violation_count |   both_window_count |   undecided_count |
|------------:|----------:|:--------------------------------------------|----------------:|--------------:|----------------:|--------------------:|-------------------:|-------------------:|-------------------:|------------------:|-----------------------:|------------------------:|--------------------:|------------------:|
|         100 |         6 | oco_first_touch_clean__asia__k2             |            7179 |          7179 |            7179 |             0       |              0     |                0   |             1      |            1      |                 1      |                       0 |                   0 |                 0 |
|         100 |         6 | oco_first_touch_clean__high_abs_vel_q70__k2 |            6154 |          6154 |            6154 |             0       |              0     |                0   |             1      |            1      |                 1      |                       0 |                   0 |                 0 |
|         100 |         6 | oco_first_touch_clean__high_abs_vel_q80__k2 |            6513 |          6513 |            6513 |             0       |              0     |                0   |             1      |            1      |                 1      |                       0 |                   0 |                 0 |
|         100 |         6 | oco_first_touch_clean__high_range_q80__k2   |            8183 |          8183 |            8183 |             0       |              0     |                0   |             1      |            1      |                 1      |                       0 |                   0 |                 0 |
|         100 |         6 | oco_first_touch_clean__ny_overlap__k2       |            1250 |          1250 |            1250 |             1.29904 |             16.712 |               48.8 |             0.7928 |            0.7912 |                 0.9592 |                     261 |                 261 |                56 |

## By Month
| test_month   |   rows_selected |   rows_mapped |   rows_verified |   mean_abs_err_pips |   p99_abs_err_pips |   max_abs_err_pips |   exact_match_rate |   sign_match_rate |   pos_label_match_rate |   clean_violation_count |   both_window_count |   undecided_count |
|:-------------|----------------:|--------------:|----------------:|--------------------:|-------------------:|-------------------:|-------------------:|------------------:|-----------------------:|------------------------:|--------------------:|------------------:|
| 2025-04      |            9606 |          9606 |            9606 |           0.107329  |              3.585 |               48.8 |           0.984905 |          0.984697 |               0.996877 |                     147 |                 147 |                 7 |
| 2025-05      |            4583 |          4583 |            4583 |           0.0281257 |              0     |               13   |           0.994545 |          0.994545 |               0.998691 |                      25 |                  25 |                 1 |
| 2025-06      |            3021 |          3021 |            3021 |           0.0112877 |              0     |                8.9 |           0.997352 |          0.997352 |               0.998676 |                       8 |                   8 |                 0 |
| 2025-07      |            2778 |          2778 |            2778 |           0.0267819 |              0     |                9.3 |           0.99388  |          0.99388  |               0.99892  |                      17 |                  17 |                13 |
| 2025-08      |            2397 |          2397 |            2397 |           0.0122236 |              0     |               10.2 |           0.997497 |          0.997497 |               0.999583 |                       6 |                   6 |                 6 |
| 2025-09      |            1947 |          1947 |            1947 |           0.0449409 |              0     |               14.4 |           0.992296 |          0.992296 |               0.997946 |                      15 |                  15 |                 4 |
| 2025-10      |            1905 |          1905 |            1905 |           0.067664  |              0.192 |               21   |           0.989501 |          0.989501 |               0.999475 |                      20 |                  20 |                 6 |
| 2025-11      |            1868 |          1868 |            1868 |           0.0501071 |              1.057 |                7.8 |           0.989293 |          0.989293 |               0.998929 |                      20 |                  20 |                18 |
| 2025-12      |            1174 |          1174 |            1174 |           0.0137138 |              0     |                6   |           0.997445 |          0.997445 |               1        |                       3 |                   3 |                 1 |
