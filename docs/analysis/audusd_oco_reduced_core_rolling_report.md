# OCO Tick-Exact Shortlist Verification

## Setup
- symbol: `AUDUSD`
- family_required: `oco_first_touch_clean`
- locked_quantile: `0.9`
- selection_mode: `auto`
- oco_hold_mode: `from_touch`
- oco_include_no_touch: `True`
- abs_tol_pips: `1e-09`

## Summary
| symbol   |   locked_quantile | oco_hold_mode   | oco_include_no_touch   |   rows_selected |   rows_mapped |   rows_verified |   mean_abs_err_pips |   p99_abs_err_pips |   max_abs_err_pips |   exact_match_rate |   sign_match_rate |   pos_label_match_rate |   clean_violation_count |   both_window_count |   undecided_count |   min_exact_match_rate |   min_pos_label_match_rate | pass_exact_match   | pass_pos_label_match   | pass_clean   | overall_pass   |
|:---------|------------------:|:----------------|:-----------------------|----------------:|--------------:|----------------:|--------------------:|-------------------:|-------------------:|-------------------:|------------------:|-----------------------:|------------------------:|--------------------:|------------------:|-----------------------:|---------------------------:|:-------------------|:-----------------------|:-------------|:---------------|
| AUDUSD   |               0.9 | from_touch      | True                   |           25308 |         25308 |           25308 |           0.0715347 |                1.9 |               38.6 |            0.98704 |          0.986961 |               0.997195 |                     330 |                 330 |               100 |                  0.999 |                      0.999 | False              | False                  | False        | False          |

## By State
|   bar_ticks |   horizon | state_id                                    |   rows_selected |   rows_mapped |   rows_verified |   mean_abs_err_pips |   p99_abs_err_pips |   max_abs_err_pips |   exact_match_rate |   sign_match_rate |   pos_label_match_rate |   clean_violation_count |   both_window_count |   undecided_count |
|------------:|----------:|:--------------------------------------------|----------------:|--------------:|----------------:|--------------------:|-------------------:|-------------------:|-------------------:|------------------:|-----------------------:|------------------------:|--------------------:|------------------:|
|         100 |         6 | oco_first_touch_clean__asia__k2             |            4767 |          4767 |            4767 |             0       |                0   |                0   |           1        |           1       |               1        |                       0 |                   0 |                 0 |
|         100 |         6 | oco_first_touch_clean__high_abs_vel_q70__k2 |            5692 |          5692 |            5692 |             0       |                0   |                0   |           1        |           1       |               1        |                       0 |                   0 |                 0 |
|         100 |         6 | oco_first_touch_clean__high_abs_vel_q80__k2 |            6237 |          6237 |            6237 |             0       |                0   |                0   |           1        |           1       |               1        |                       0 |                   0 |                 0 |
|         100 |         6 | oco_first_touch_clean__high_range_q80__k2   |            7158 |          7158 |            7158 |             0       |                0   |                0   |           1        |           1       |               1        |                       0 |                   0 |                 0 |
|         100 |         6 | oco_first_touch_clean__ny_overlap__k2       |            1454 |          1454 |            1454 |             1.24512 |               14.7 |               38.6 |           0.774415 |           0.77304 |               0.951169 |                     330 |                 330 |               100 |

## By Month
| test_month   |   rows_selected |   rows_mapped |   rows_verified |   mean_abs_err_pips |   p99_abs_err_pips |   max_abs_err_pips |   exact_match_rate |   sign_match_rate |   pos_label_match_rate |   clean_violation_count |   both_window_count |   undecided_count |
|:-------------|----------------:|--------------:|----------------:|--------------------:|-------------------:|-------------------:|-------------------:|------------------:|-----------------------:|------------------------:|--------------------:|------------------:|
| 2025-04      |            7085 |          7085 |            7085 |          0.196246   |              6.316 |               38.6 |           0.965843 |          0.965561 |               0.993225 |                     244 |                 244 |                87 |
| 2025-05      |            4455 |          4455 |            4455 |          0.0109989  |              0     |               10.8 |           0.996633 |          0.996633 |               0.999327 |                      15 |                  15 |                 2 |
| 2025-06      |            3668 |          3668 |            3668 |          0.0165213  |              0     |                9   |           0.996183 |          0.996183 |               0.998092 |                      14 |                  14 |                 1 |
| 2025-07      |            2442 |          2442 |            2442 |          0.0308354  |              0     |                9.3 |           0.993448 |          0.993448 |               0.998362 |                      16 |                  16 |                 1 |
| 2025-08      |            1447 |          1447 |            1447 |          0.00621977 |              0     |                4.2 |           0.997927 |          0.997927 |               1        |                       3 |                   3 |                 3 |
| 2025-09      |            1697 |          1697 |            1697 |          0.0638774  |              0.924 |               11.3 |           0.987625 |          0.987625 |               0.997054 |                      21 |                  21 |                 2 |
| 2025-10      |            1726 |          1726 |            1726 |          0.0428737  |              0     |               29.8 |           0.995944 |          0.995944 |               0.998262 |                       7 |                   7 |                 0 |
| 2025-11      |            1605 |          1605 |            1605 |          0.0122118  |              0     |                9.3 |           0.996885 |          0.996885 |               0.999377 |                       5 |                   5 |                 4 |
| 2025-12      |            1183 |          1183 |            1183 |          0.0203719  |              0     |               11   |           0.995773 |          0.995773 |               1        |                       5 |                   5 |                 0 |
