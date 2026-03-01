# Remediation Metric Decomposition

- generated_at_utc: `2026-02-27T11:12:44Z`
- baseline_csv: `data/analysis/tick_opportunity_mining/remediation_baseline_metrics.csv`
- delta_csv: `data/analysis/tick_opportunity_mining/remediation_metric_delta.csv`
- session_cap_policy_csv: `data/analysis/tick_opportunity_mining/stage04_cap_policy_by_session.csv`

## Target Metrics (Pre vs Post)
| symbol   | metric_id                        |   pre_metric_value | pre_band   |   post_metric_value | post_band   |
|:---------|:---------------------------------|-------------------:|:-----------|--------------------:|:------------|
| EURUSD   | D18_clock_jitter_cv              |          7.90046   | red        |            0.63644  | green       |
| EURUSD   | E11_session_overshoot_dispersion |          0.851988  | red        |            0.199265 | green       |
| EURUSD   | T03_post_worst_month_recovery    |         -0.0974308 | red        |            0.915934 | green       |
| GBPUSD   | D18_clock_jitter_cv              |          7.41284   | red        |            0.592694 | green       |
| GBPUSD   | E11_session_overshoot_dispersion |          1.20518   | red        |            0.26181  | green       |
| GBPUSD   | T03_post_worst_month_recovery    |          0.765238  | green      |            1.33224  | green       |
| USDJPY   | D18_clock_jitter_cv              |         10.4984    | red        |            0.608004 | green       |
| USDJPY   | E11_session_overshoot_dispersion |          0.958511  | red        |            0.133612 | green       |
| USDJPY   | T03_post_worst_month_recovery    |          0.116104  | red        |            1.04299  | green       |

## Stage 4 Session Cap Policy (Latest)
| symbol   | session_bucket   |   lookback_days |   cap_quantile |   cap_pips |   rows_used |   session_cap_rows |   global_cap_rows |   fallback_rows |
|:---------|:-----------------|----------------:|---------------:|-----------:|------------:|-------------------:|------------------:|----------------:|
| EURUSD   | ASIA             |              20 |            0.9 |        0.2 |      114171 |             113971 |                 2 |             198 |
| EURUSD   | LATE             |              20 |            0.9 |        0.1 |       11207 |              10377 |               830 |               0 |
| EURUSD   | LONDON           |              20 |            0.9 |        0.2 |      108028 |             107828 |               200 |               0 |
| EURUSD   | NY               |              20 |            0.9 |        0.2 |       91288 |              91088 |               200 |               0 |
| GBPUSD   | ASIA             |              20 |            0.9 |        0.3 |      170822 |             170622 |                 6 |             194 |
| GBPUSD   | LATE             |              20 |            0.9 |        0.3 |        5891 |               4867 |              1024 |               0 |
| GBPUSD   | LONDON           |              20 |            0.9 |        0.3 |      173809 |             173609 |               200 |               0 |
| GBPUSD   | NY               |              20 |            0.9 |        0.6 |       63280 |              63080 |               200 |               0 |
| USDJPY   | ASIA             |              20 |            0.9 |        0.4 |      194384 |             194184 |                 0 |             200 |
| USDJPY   | LATE             |              20 |            0.9 |        0.4 |       23720 |              23520 |               200 |               0 |
| USDJPY   | LONDON           |              20 |            0.9 |        0.4 |      119880 |             119680 |               200 |               0 |
| USDJPY   | NY               |              20 |            0.9 |        0.6 |      121207 |             121007 |               200 |               0 |

## Notes
- D18 now uses normalized jitter CV (hour-of-week baseline adjusted) with raw metric retained as `D18_clock_jitter_cv_raw`.
- E11 now measures dispersion after causal rolling session caps (20D, q0.90).
- T03 now uses recovery efficiency ratio: next-month gross / abs(worst-month gross).
