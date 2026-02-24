# EURUSD Tick Opportunity Monthly WFO (3M->1M)

## Setup
- library: `oco`
- train_years_for_state_fit: `2022,2023,2024`
- eval_year: `2025`
- min_candidate_train_count: `15000`
- max_candidates_per_library: `120`
- rolling_train_months: `3`
- oco_include_no_touch: `True`
- threshold_mode: `rolling_days`
- rolling_threshold_days: `20`
- rolling_threshold_min_history: `1000`
- execution_quantile: `0.9`
- oco_hold_mode: `from_touch`

## Monthly Metrics
| library   | test_month   | train_start   | train_end   | test_start   | test_end   |   train_rows |   test_rows |   train_candidates |   test_candidates |   base_pos_rate |      auc |    brier |
|:----------|:-------------|:--------------|:------------|:-------------|:-----------|-------------:|------------:|-------------------:|------------------:|----------------:|---------:|---------:|
| oco       | 2025-04      | 2025-01-01    | 2025-04-01  | 2025-04-01   | 2025-05-01 |       192848 |       65825 |                115 |                87 |        0.558238 | 0.510191 | 0.247918 |
| oco       | 2025-05      | 2025-02-01    | 2025-05-01  | 2025-05-01   | 2025-06-01 |       123412 |       37703 |                 89 |                89 |        0.536376 | 0.517356 | 0.248786 |
| oco       | 2025-06      | 2025-03-01    | 2025-06-01  | 2025-06-01   | 2025-07-01 |       139381 |       31642 |                 90 |                90 |        0.536565 | 0.507927 | 0.250604 |
| oco       | 2025-07      | 2025-04-01    | 2025-07-01  | 2025-07-01   | 2025-08-01 |       133216 |       25284 |                 87 |                87 |        0.550229 | 0.523802 | 0.247706 |
| oco       | 2025-08      | 2025-05-01    | 2025-08-01  | 2025-08-01   | 2025-09-01 |        88077 |       21754 |                 83 |                83 |        0.547348 | 0.520789 | 0.248161 |
| oco       | 2025-09      | 2025-06-01    | 2025-09-01  | 2025-09-01   | 2025-10-01 |        73144 |       20906 |                 81 |                81 |        0.545633 | 0.510959 | 0.248994 |
| oco       | 2025-10      | 2025-07-01    | 2025-10-01  | 2025-10-01   | 2025-11-01 |        68829 |       21236 |                 85 |                85 |        0.522744 | 0.515845 | 0.250965 |
| oco       | 2025-11      | 2025-08-01    | 2025-11-01  | 2025-11-01   | 2025-12-01 |        59263 |       13780 |                 77 |                77 |        0.509579 | 0.501177 | 0.253585 |
| oco       | 2025-12      | 2025-09-01    | 2025-12-01  | 2025-12-01   | 2026-01-01 |        48147 |       13400 |                 70 |                70 |        0.522015 | 0.513868 | 0.250963 |

## Threshold Outcomes
| library   | test_month   |   quantile | threshold_mode   |   threshold_median |   threshold_min |   threshold_max |   coverage |   mean_gross_pips |   median_gross_pips |   pos_rate |   selected_rows |
|:----------|:-------------|-----------:|:-----------------|-------------------:|----------------:|----------------:|-----------:|------------------:|--------------------:|-----------:|----------------:|
| oco       | 2025-04      |       0.5  | rolling_days     |           0.54053  |        0.533251 |        0.543386 |  0.524512  |          0.911484 |                 0.8 |   0.565632 |           34526 |
| oco       | 2025-04      |       0.6  | rolling_days     |           0.549172 |        0.540755 |        0.551861 |  0.426479  |          0.950639 |                 0.8 |   0.567164 |           28073 |
| oco       | 2025-04      |       0.7  | rolling_days     |           0.558493 |        0.549048 |        0.561006 |  0.326274  |          1.00278  |                 0.8 |   0.571029 |           21477 |
| oco       | 2025-04      |       0.8  | rolling_days     |           0.569116 |        0.558589 |        0.571909 |  0.223243  |          1.02789  |                 0.9 |   0.56965  |           14695 |
| oco       | 2025-04      |       0.9  | rolling_days     |           0.585063 |        0.572843 |        0.587743 |  0.112602  |          1.03033  |                 0.9 |   0.570561 |            7412 |
| oco       | 2025-04      |       0.95 | rolling_days     |           0.599137 |        0.585877 |        0.602483 |  0.056711  |          1.0404   |                 0.9 |   0.569515 |            3733 |
| oco       | 2025-05      |       0.5  | rolling_days     |           0.545637 |        0.539291 |        0.554427 |  0.44649   |          0.614667 |                 0.5 |   0.550612 |           16834 |
| oco       | 2025-05      |       0.6  | rolling_days     |           0.553503 |        0.54693  |        0.564233 |  0.348832  |          0.684672 |                 0.6 |   0.557026 |           13152 |
| oco       | 2025-05      |       0.7  | rolling_days     |           0.562141 |        0.555714 |        0.57487  |  0.25364   |          0.728767 |                 0.6 |   0.560389 |            9563 |
| oco       | 2025-05      |       0.8  | rolling_days     |           0.572545 |        0.566325 |        0.587946 |  0.160889  |          0.82786  |                 0.8 |   0.568909 |            6066 |
| oco       | 2025-05      |       0.9  | rolling_days     |           0.587033 |        0.581869 |        0.607176 |  0.0754847 |          1.09255  |                 1   |   0.580464 |            2846 |
| oco       | 2025-05      |       0.95 | rolling_days     |           0.600771 |        0.593866 |        0.626015 |  0.0339761 |          1.1904   |                 1.1 |   0.583138 |            1281 |
| oco       | 2025-06      |       0.5  | rolling_days     |           0.532767 |        0.527497 |        0.540285 |  0.458726  |          0.490637 |                 0.4 |   0.543024 |           14515 |
| oco       | 2025-06      |       0.6  | rolling_days     |           0.542047 |        0.538286 |        0.547973 |  0.369098  |          0.517399 |                 0.5 |   0.544567 |           11679 |
| oco       | 2025-06      |       0.7  | rolling_days     |           0.551311 |        0.549455 |        0.557161 |  0.278522  |          0.546261 |                 0.5 |   0.549302 |            8813 |
| oco       | 2025-06      |       0.8  | rolling_days     |           0.562846 |        0.561618 |        0.567525 |  0.189084  |          0.590339 |                 0.6 |   0.553568 |            5983 |
| oco       | 2025-06      |       0.9  | rolling_days     |           0.579514 |        0.578544 |        0.582833 |  0.0964225 |          0.622616 |                 0.6 |   0.553261 |            3051 |
| oco       | 2025-06      |       0.95 | rolling_days     |           0.592933 |        0.591977 |        0.595469 |  0.0482586 |          0.72279  |                 0.8 |   0.567125 |            1527 |
| oco       | 2025-07      |       0.5  | rolling_days     |           0.540383 |        0.539426 |        0.542225 |  0.486118  |          0.914254 |                 0.8 |   0.568302 |           12291 |
| oco       | 2025-07      |       0.6  | rolling_days     |           0.550116 |        0.548734 |        0.551867 |  0.385619  |          0.981344 |                 0.9 |   0.573744 |            9750 |
| oco       | 2025-07      |       0.7  | rolling_days     |           0.560904 |        0.559603 |        0.563091 |  0.285437  |          1.05835  |                 1   |   0.579742 |            7217 |
| oco       | 2025-07      |       0.8  | rolling_days     |           0.574828 |        0.573305 |        0.577207 |  0.186205  |          1.19484  |                 1.1 |   0.584749 |            4708 |
| oco       | 2025-07      |       0.9  | rolling_days     |           0.592499 |        0.591279 |        0.595051 |  0.0872489 |          1.39393  |                 1.3 |   0.593835 |            2206 |
| oco       | 2025-07      |       0.95 | rolling_days     |           0.608935 |        0.607648 |        0.612781 |  0.0410536 |          1.27447  |                 1.3 |   0.594412 |            1038 |
| oco       | 2025-08      |       0.5  | rolling_days     |           0.548769 |        0.547634 |        0.55016  |  0.506757  |          0.735949 |                 0.7 |   0.562863 |           11024 |
| oco       | 2025-08      |       0.6  | rolling_days     |           0.559418 |        0.557885 |        0.560998 |  0.405121  |          0.739135 |                 0.7 |   0.565869 |            8813 |
| oco       | 2025-08      |       0.7  | rolling_days     |           0.57051  |        0.568784 |        0.572494 |  0.30114   |          0.73891  |                 0.7 |   0.566326 |            6551 |
| oco       | 2025-08      |       0.8  | rolling_days     |           0.583703 |        0.581981 |        0.586237 |  0.198033  |          0.765204 |                 0.7 |   0.564299 |            4308 |
| oco       | 2025-08      |       0.9  | rolling_days     |           0.603171 |        0.599536 |        0.608702 |  0.0938678 |          0.891234 |                 0.9 |   0.56954  |            2042 |
| oco       | 2025-08      |       0.95 | rolling_days     |           0.621314 |        0.61585  |        0.632286 |  0.0435322 |          1.24836  |                 0.9 |   0.579725 |             947 |
| oco       | 2025-09      |       0.5  | rolling_days     |           0.550617 |        0.544652 |        0.552907 |  0.475127  |          0.569757 |                 0.5 |   0.550086 |            9933 |
| oco       | 2025-09      |       0.6  | rolling_days     |           0.561262 |        0.555965 |        0.563877 |  0.376447  |          0.581233 |                 0.5 |   0.551334 |            7870 |
| oco       | 2025-09      |       0.7  | rolling_days     |           0.573108 |        0.567289 |        0.575522 |  0.278676  |          0.600566 |                 0.6 |   0.555613 |            5826 |
| oco       | 2025-09      |       0.8  | rolling_days     |           0.586859 |        0.581399 |        0.589498 |  0.183966  |          0.638872 |                 0.6 |   0.559022 |            3846 |
| oco       | 2025-09      |       0.9  | rolling_days     |           0.605436 |        0.601944 |        0.609886 |  0.090883  |          0.663105 |                 0.6 |   0.566842 |            1900 |
| oco       | 2025-09      |       0.95 | rolling_days     |           0.621878 |        0.618632 |        0.629157 |  0.0453458 |          0.567722 |                 0.5 |   0.541139 |             948 |
| oco       | 2025-10      |       0.5  | rolling_days     |           0.547923 |        0.54473  |        0.550486 |  0.493784  |          0.375682 |                 0.4 |   0.535381 |           10486 |
| oco       | 2025-10      |       0.6  | rolling_days     |           0.558011 |        0.555627 |        0.560535 |  0.394754  |          0.441548 |                 0.4 |   0.542288 |            8383 |
| oco       | 2025-10      |       0.7  | rolling_days     |           0.569931 |        0.566915 |        0.571871 |  0.293276  |          0.458157 |                 0.4 |   0.543353 |            6228 |
| oco       | 2025-10      |       0.8  | rolling_days     |           0.584027 |        0.579656 |        0.586215 |  0.189301  |          0.411443 |                 0.4 |   0.535075 |            4020 |
| oco       | 2025-10      |       0.9  | rolling_days     |           0.603379 |        0.597747 |        0.606917 |  0.0894236 |          0.462559 |                 0.4 |   0.537125 |            1899 |
| oco       | 2025-10      |       0.95 | rolling_days     |           0.620957 |        0.615535 |        0.631396 |  0.0405444 |          0.402207 |                 0.2 |   0.521487 |             861 |
| oco       | 2025-11      |       0.5  | rolling_days     |           0.538635 |        0.533895 |        0.541442 |  0.49434   |          0.192557 |                 0.2 |   0.514093 |            6812 |
| oco       | 2025-11      |       0.6  | rolling_days     |           0.55011  |        0.545236 |        0.552386 |  0.395864  |          0.184106 |                 0.1 |   0.511274 |            5455 |
| oco       | 2025-11      |       0.7  | rolling_days     |           0.562497 |        0.557107 |        0.563929 |  0.299274  |          0.21421  |                 0.1 |   0.508002 |            4124 |
| oco       | 2025-11      |       0.8  | rolling_days     |           0.576609 |        0.571983 |        0.577854 |  0.200363  |          0.267802 |                 0.2 |   0.514669 |            2761 |
| oco       | 2025-11      |       0.9  | rolling_days     |           0.597056 |        0.590823 |        0.598695 |  0.0984761 |          0.323287 |                 0.3 |   0.530582 |            1357 |
| oco       | 2025-11      |       0.95 | rolling_days     |           0.619915 |        0.610774 |        0.622599 |  0.048984  |          0.337185 |                 0.2 |   0.524444 |             675 |
| oco       | 2025-12      |       0.5  | rolling_days     |           0.527126 |        0.523881 |        0.529257 |  0.508806  |          0.304561 |                 0.3 |   0.535641 |            6818 |
| oco       | 2025-12      |       0.6  | rolling_days     |           0.537898 |        0.534721 |        0.540819 |  0.404552  |          0.304261 |                 0.3 |   0.535879 |            5421 |
| oco       | 2025-12      |       0.7  | rolling_days     |           0.548759 |        0.546247 |        0.551727 |  0.300746  |          0.320769 |                 0.3 |   0.531017 |            4030 |
| oco       | 2025-12      |       0.8  | rolling_days     |           0.561343 |        0.558815 |        0.564339 |  0.198134  |          0.331714 |                 0.3 |   0.53484  |            2655 |
| oco       | 2025-12      |       0.9  | rolling_days     |           0.58176  |        0.577357 |        0.586362 |  0.0943284 |          0.365032 |                 0.4 |   0.540348 |            1264 |
| oco       | 2025-12      |       0.95 | rolling_days     |           0.602499 |        0.594892 |        0.614458 |  0.0403731 |          0.30647  |                 0.1 |   0.508318 |             541 |

## Fast Run Summary
- period: `2025-04` to `2025-12`
- thresholding: `rolling_days`, `20` day lookback, `1000` minimum prior rows/day
- execution slice (`q=0.9`, causal exec flags): `23977` rows, mean gross `0.8583` pips/trade, LB95 trade mean gross `0.8024` pips/trade
- reduced-core shortlist: `5381` rows, weighted mean gross `2.1017` pips/trade
- tick-exact parity on shortlisted rows: `exact_match_rate=1.0`, `clean_violation_count=0`

## Scripts Used
- `scripts/run_tick_opportunity_monthly_wfo.py`
- `scripts/analyze_oco_monthly_wfo_robustness.py`
- `scripts/select_oco_reduced_core.py`
- `scripts/verify_oco_tick_exact_shortlist.py`
- `scripts/build_tick_opportunity_ml_dataset.py`

## Commands Used (Fast Profile)
```bash
python scripts/run_tick_opportunity_monthly_wfo.py \
  --config configs/research/experiments/eurusd_tick_opportunity_monthly_wfo_oco_fullcap_2025.yaml \
  --max-candidates-per-library 120 \
  --max-events-per-candidate 4000 \
  --min-month-train-rows 3000 \
  --min-month-test-rows 1000 \
  --out-dir data/analysis/tick_opportunity_mining/wfo_2025_m3to1_oco_fast_r20 \
  --report-out docs/analysis/eurusd_tick_opportunity_monthly_wfo_oco_fast_r20_report.md

python scripts/analyze_oco_monthly_wfo_robustness.py \
  --pred-path data/analysis/tick_opportunity_mining/wfo_2025_m3to1_oco_fast_r20/EURUSD_oco_monthly_predictions.parquet \
  --bootstrap-paths 200 \
  --use-exec-selection true \
  --execution-quantile 0.9 \
  --out-summary-csv data/analysis/tick_opportunity_mining/wfo_2025_m3to1_oco_fast_r20/EURUSD_oco_robustness_summary.csv \
  --out-monthly-csv data/analysis/tick_opportunity_mining/wfo_2025_m3to1_oco_fast_r20/EURUSD_oco_robustness_monthly.csv \
  --report-out docs/analysis/eurusd_oco_monthly_wfo_robustness_fast_r20_report.md

python scripts/select_oco_reduced_core.py \
  --pred-path data/analysis/tick_opportunity_mining/wfo_2025_m3to1_oco_fast_r20/EURUSD_oco_monthly_predictions.parquet \
  --out-dir data/analysis/tick_opportunity_mining/reduced_core_fast_r20 \
  --report-out docs/analysis/eurusd_oco_reduced_core_selection_fast_r20_report.md \
  --selection-mode auto \
  --locked-quantile 0.9 \
  --family-keep oco_first_touch_clean \
  --barrier-keep 2,3 \
  --horizon-keep 5,6

python scripts/verify_oco_tick_exact_shortlist.py \
  --symbol EURUSD \
  --dataset-dir data/analysis/tick_velocity \
  --pred-path data/analysis/tick_opportunity_mining/wfo_2025_m3to1_oco_fast_r20/EURUSD_oco_monthly_predictions.parquet \
  --shortlist-state-csv data/analysis/tick_opportunity_mining/reduced_core_fast_r20/EURUSD_oco_reduced_states.csv \
  --locked-quantile 0.9 \
  --selection-mode auto \
  --family-required oco_first_touch_clean \
  --oco-hold-mode from_touch \
  --oco-include-no-touch true \
  --out-summary-csv data/analysis/tick_opportunity_mining/reduced_core_fast_r20/EURUSD_oco_tick_exact_summary.csv \
  --out-monthly-csv data/analysis/tick_opportunity_mining/reduced_core_fast_r20/EURUSD_oco_tick_exact_monthly.csv \
  --out-state-csv data/analysis/tick_opportunity_mining/reduced_core_fast_r20/EURUSD_oco_tick_exact_state.csv \
  --report-out docs/analysis/eurusd_oco_tick_exact_shortlist_fast_r20_report.md
```
