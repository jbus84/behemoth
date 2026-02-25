# OCO Logical Audit (EURUSD/GBPUSD/USDJPY)

## Outputs
- checks_csv: `data/analysis/tick_opportunity_mining/oco_logical_audit_checks.csv`
- issues_csv: `data/analysis/tick_opportunity_mining/oco_logical_audit_issues.csv`

## Severity Counts
```
severity  size
  medium     3
    high     1
```

## Check Status By Symbol
```
symbol  fail  pass
EURUSD     2     8
GBPUSD     1     9
USDJPY     1     9
```

## Failed Issues
```
  issue_id symbol severity               component                                                           description                                                        impact_estimate                                                                         proposed_fix                                            acceptance_test
EURUSD_C05 EURUSD     high         stop_limit_join      Stop-limit detail join has duplicates or low key-match coverage. Execution model can silently drop/alter rows if key integrity is weak. Deduplicate detail at source and enforce key uniqueness + match-rate gate per month. No duplicate keys and monthly/overall match rate >= 99.5%.
EURUSD_C04 EURUSD   medium overlap_diversification Dependence measured via activity counts diverges from pnl dependence.          Portfolio overlap filter may understate true pnl co-movement.        Compute overlap on monthly pnl vectors (or blended activity+pnl correlation).  median_abs_corr_diff <= 0.40 after overlap metric switch.
GBPUSD_C04 GBPUSD   medium overlap_diversification Dependence measured via activity counts diverges from pnl dependence.          Portfolio overlap filter may understate true pnl co-movement.        Compute overlap on monthly pnl vectors (or blended activity+pnl correlation).  median_abs_corr_diff <= 0.40 after overlap metric switch.
USDJPY_C04 USDJPY   medium overlap_diversification Dependence measured via activity counts diverges from pnl dependence.          Portfolio overlap filter may understate true pnl co-movement.        Compute overlap on monthly pnl vectors (or blended activity+pnl correlation).  median_abs_corr_diff <= 0.40 after overlap metric switch.
```

## All Checks
```
symbol check_id status severity_if_fail               component                  metric_name  metric_value                                                                          threshold
EURUSD      C01   pass         critical        threshold_timing         selected_consistency      1.000000 pred_prob >= threshold_exec for selected rows; month mismatch=0; threshold_days>=1
EURUSD      C02   pass             high        threshold_timing          unstable_group_rate      0.000000                                                                                  0
EURUSD      C03   pass             high         state_selection     selected_non_gate_states      0.000000                                                                                  0
EURUSD      C04   fail           medium overlap_diversification         median_abs_corr_diff      0.527424                                                                             <=0.40
EURUSD      C05   fail             high         stop_limit_join         min_month_match_rate      0.991427                                                       >=0.995 and duplicate_keys=0
EURUSD      C06   pass             high        stop_limit_model      monotonicity_violations      0.000000                                                                                  0
EURUSD      C07   pass         critical       metrics_semantics              rows_total_diff      0.000000                                             0 (and signal diff=0, fill diff<=1e-9)
EURUSD      C08   pass           medium           wfo_windowing                 warmup_count      3.000000                                         ==3, missing_months=0, unexpected_non_ok=0
EURUSD      C09   pass             high       robustness_metric          lb95_gross_abs_diff      0.000000                                                     <=1e-8 (and signal diff<=1e-8)
EURUSD      C10   pass         critical     timestamp_causality max_timestamp_violation_rate      0.000000                                      0 (and touch_order=0, touch_month_mismatch=0)
GBPUSD      C01   pass         critical        threshold_timing         selected_consistency      1.000000 pred_prob >= threshold_exec for selected rows; month mismatch=0; threshold_days>=1
GBPUSD      C02   pass             high        threshold_timing          unstable_group_rate      0.000000                                                                                  0
GBPUSD      C03   pass             high         state_selection     selected_non_gate_states      0.000000                                                                                  0
GBPUSD      C04   fail           medium overlap_diversification         median_abs_corr_diff      0.533805                                                                             <=0.40
GBPUSD      C05   pass             high         stop_limit_join         min_month_match_rate      0.999912                                                       >=0.995 and duplicate_keys=0
GBPUSD      C06   pass             high        stop_limit_model      monotonicity_violations      0.000000                                                                                  0
GBPUSD      C07   pass         critical       metrics_semantics              rows_total_diff      0.000000                                             0 (and signal diff=0, fill diff<=1e-9)
GBPUSD      C08   pass           medium           wfo_windowing                 warmup_count      3.000000                                         ==3, missing_months=0, unexpected_non_ok=0
GBPUSD      C09   pass             high       robustness_metric          lb95_gross_abs_diff      0.000000                                                     <=1e-8 (and signal diff<=1e-8)
GBPUSD      C10   pass         critical     timestamp_causality max_timestamp_violation_rate      0.000000                                      0 (and touch_order=0, touch_month_mismatch=0)
USDJPY      C01   pass         critical        threshold_timing         selected_consistency      1.000000 pred_prob >= threshold_exec for selected rows; month mismatch=0; threshold_days>=1
USDJPY      C02   pass             high        threshold_timing          unstable_group_rate      0.000000                                                                                  0
USDJPY      C03   pass             high         state_selection     selected_non_gate_states      0.000000                                                                                  0
USDJPY      C04   fail           medium overlap_diversification         median_abs_corr_diff      0.684660                                                                             <=0.40
USDJPY      C05   pass             high         stop_limit_join         min_month_match_rate      1.000000                                                       >=0.995 and duplicate_keys=0
USDJPY      C06   pass             high        stop_limit_model      monotonicity_violations      0.000000                                                                                  0
USDJPY      C07   pass         critical       metrics_semantics              rows_total_diff      0.000000                                             0 (and signal diff=0, fill diff<=1e-9)
USDJPY      C08   pass           medium           wfo_windowing                 warmup_count      3.000000                                         ==3, missing_months=0, unexpected_non_ok=0
USDJPY      C09   pass             high       robustness_metric          lb95_gross_abs_diff      0.000000                                                     <=1e-8 (and signal diff<=1e-8)
USDJPY      C10   pass         critical     timestamp_causality max_timestamp_violation_rate      0.000000                                      0 (and touch_order=0, touch_month_mismatch=0)
```
