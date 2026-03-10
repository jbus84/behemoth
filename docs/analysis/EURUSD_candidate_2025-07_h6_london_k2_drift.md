# Candidate-Month Runtime Drift Trace

- symbol: `EURUSD`
- candidate_uid: `oco|EURUSD|100|h6|oco_first_touch_clean__london__k2`
- model_month: `2025-07`
- window: `2025-07-01T00:00:00+00:00` to `2025-08-01T00:00:00+00:00`

## Summary
- runtime_selected_rows: `4115`
- runtime_selected_unique_close_ts: `4115`
- research_selected_rows: `254`
- total_eval_events_rows: `907`
- runtime_london_hour_rows: `808`
- research_london_hour_rows: `254`
- runtime_london_hour_share: `0.19635479951397328`
- research_london_hour_share: `1.0`
- runtime_pred_minus_thr_mean: `0.03432763150411601`
- research_pred_minus_thr_mean: `0.014819428619125228`

## Derived Diagnostics
- runtime_vs_research_selected_ratio: `16.20` (`4115 / 254`)
- runtime_london_vs_research_selected_ratio: `3.18` (`808 / 254`)
- excess_removed_if_london_regime_enforced: `3307` rows (`80.36%` of runtime-selected rows)
- exact_close_ts_intersection_runtime_vs_research_selected: `0`
- interpretation:
runtime row inflation is not duplicate logging on the same close timestamp (all 4115 rows have unique close_ts); the largest driver is regime-hour mismatch, with residual drift still present after applying london hours.

## Top Feature Drift (abs SMD)
| feature               |   runtime_mean |   research_mean |   smd_runtime_minus_research |   smd_runtime_london_minus_research |
|:----------------------|---------------:|----------------:|-----------------------------:|------------------------------------:|
| cost_est_pips         |     0.274574   |       0.61787   |                   -6.88149   |                          -6.82813   |
| hour_utc              |    13.5674     |       9.61417   |                    1.23203   |                           0.165257  |
| vel_abs_cost_units_h1 |     6.06351    |       3.13837   |                    0.510438  |                           0.494102  |
| tick_rate_z           |    -0.0764365  |       0.354362  |                   -0.280408  |                          -0.485082  |
| ret_abs_z             |     0.662962   |       0.855908  |                   -0.235638  |                          -0.269074  |
| hl_first              |    -0.114459   |       0.0314961 |                   -0.146472  |                          -0.158405  |
| hl_pos_frac_mean_24   |     0.00494997 |       0.0222501 |                   -0.142664  |                           0.0732936 |
| spread_z              |     0.118706   |      -0.0621816 |                    0.0649676 |                          -0.313329  |
| ret_z                 |     0.0444279  |      -0.02749   |                    0.064193  |                           0.0707218 |
| vel_cost_units_h1     |     0.346903   |      -0.0313748 |                    0.0505101 |                           0.0557415 |
| ret1_pips             |     0.0923189  |      -0.0251969 |                    0.0422877 |                           0.0466837 |
| range_pips            |     3.3278     |       3.42087   |                   -0.0416582 |                          -0.336531  |

## Runtime Hour Distribution
|   close_ts |   rows |
|-----------:|-------:|
|          0 |     21 |
|          1 |     30 |
|          2 |     33 |
|          3 |     42 |
|          4 |     43 |
|          5 |     46 |
|          6 |     69 |
|          7 |     57 |
|          8 |     56 |
|          9 |    164 |
|         10 |    231 |
|         11 |    300 |
|         12 |    401 |
|         13 |    489 |
|         14 |    510 |
|         15 |    430 |
|         16 |    205 |
|         17 |    239 |
|         18 |    238 |
|         19 |    232 |
|         20 |     71 |
|         21 |     24 |
|         22 |     91 |
|         23 |     93 |

## Research Hour Distribution
|   close_ts |   rows |
|-----------:|-------:|
|          7 |     13 |
|          8 |     50 |
|          9 |     42 |
|         10 |     66 |
|         11 |     83 |

- full feature diff csv: `data/analysis/backtest_reconcile/EURUSD_candidate_2025-07_h6_london_k2_feature_diff.csv`
