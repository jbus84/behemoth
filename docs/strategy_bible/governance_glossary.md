# Governance Rule Glossary

## Objective
This glossary centralizes the definitions of every individual governance diagnostic and hard-gate rule code used throughout the Behemoth deployment pipeline. These codes represent distinct operational, statistical, and execution requirements evaluated during the 11-stage opportunity pipeline.

## Exhaustive Rule Definitions

### Stage 1: Data Foundation
| Code | Governance Category | Purpose / Abstract Meaning |
| --- | --- | --- |
| **`DR01_required_columns_present`** | Data Reliability | Validates all necessary OHLC, spread, and velocity feature columns are present in the bar schema. |
| **`DR02_minimum_rows`** | Data Reliability | Enforces a minimum sample size (e.g. 500,000 tick bars) to ensure statistical validity. |
| **`DR03_close_ts_parse_rate`** | Data Reliability | High limit on the ratio of corrupted or un-parseable timestamps. |
| **`DR04_close_ts_monotonic`** | Data Reliability | Hard-fails if time travels backward (non-monotonic sorting), which breaks causality. |
| **`DR05_duplicate_close_ts_rate`** | Data Reliability | Protects against structural broker data replication errors (max allowed duplicates). |
| **`DR06_numeric_parse_rate_min`** | Data Reliability | Protects against structural type corruption in price-fields. |
| **`DR07_core_null_rate_max`** | Data Reliability | Bounds how many `NaN` or missing values are permitted in core fields. |
| **`DR08_ohlc_consistency`** | Data Reliability | Enforces Open/High/Low/Close geometry (High must be max, Low must be min). |
| **`DR09_cost_range_nonnegative`** | Data Reliability | Prevents impossible negative spreads or negative bar ranges. |
| **`DR10_hour_utc_valid_rate`** | Data Reliability | Ensures the `hour_utc` parses exclusively into valid 0-23 integers. |
| **`DR11_finite_feature_rate`** | Data Reliability | Ensures z-scored and velocity statistical features haven't exploded to Infinity. |
| **`DR12_extreme_move_rate`** | Data Reliability | Flags abnormal spikes or mathematically erratic price jumps vs. robust median. |
| **`DR13_trading_day_coverage`** | Data Reliability | Ensures the dataset actually covers sufficient trading days (e.g., min 220 calendar days). |
| **`DR14_hour_coverage`** | Data Reliability | Ensures the dataset isn't missing large blocks of hours within days. |
| **`DR15_hour_concentration`** | Data Reliability | Prevents the dataset from artificially occurring mostly at one time of day. |
| **`D16_spread_regime_shift_z`** | Data Foundation | Measures recent spread changes against historical norms. Protects against broken broker data feeds or sudden macro regime shifts in liquidity. |
| **`D17_gap_burst_ratio`** | Data Foundation | Detects an abnormal ratio of large tick gaps. Protects against stale execution modeling by flagging illiquid trading sessions. |
| **`D18_clock_jitter_cv_raw`** | Data Foundation | Identifies inconsistent broker update latencies without session adjustment. |
| **`D18_clock_jitter_cv`** | Data Foundation | Identifies clock irregularities and missing ticks normalized for time-of-day. Protects derived velocity features from corrupt timestamps. |

### Stage 2: Opportunity Mining
| Code | Governance Category | Purpose / Abstract Meaning |
| --- | --- | --- |
| **`M01_top3_contrib_share`** | Opportunity Mining | Prevents the model's aggregate edge from being overly concentrated in just 3 outlier states. |
| **`M02_smoothness_abs_jump`** | Opportunity Mining | Measures how drastically gross pipeline profit jumps between adjacent time horizons. Higher values indicate an unstable threshold surface. |
| **`M03_positive_density`** | Opportunity Mining | Demands a minimum percentage of the generated label space has positive expectancy, ensuring the strategy isn't hunting for rare statistical anomalies. |

### Stage 3: Monthly Walk-Forward Optimization (WFO)
*(Note: Walk-Forward checks start at `W13` historically tied to external validation metrics; `W01` through `W12` are deprecated/non-existent.)*
| Code | Governance Category | Purpose / Abstract Meaning |
| --- | --- | --- |
| **`W13_threshold_fragility`** | WFO Stability | Checks the steepness of the profit curve around the execution threshold. Steep slopes fail this check to avoid edge-case overfitting. |
| **`W14_brier_drift_std`** | WFO Stability | Tracks the standard deviation of the CatBoost model's probabilistic Brier score. High drift indicates the model is struggling to calibrate out-of-sample. |
| **`W15_selection_turnover`** | WFO Stability | Evaluates how often the model flips strategies month-over-month (Jaccard distance). Punishes hyperactive threshold jumping. |

### Stage 4: Execution Realism (Prelive Risk)
| Code | Governance Category | Purpose / Abstract Meaning |
| --- | --- | --- |
| **`E01_join_integrity`** | Execution Hardening | Enforces near-perfect join match rates against tick data with zero duplicated timestamp keys. |
| **`E02_fill_rate_envelope`** | Execution Hardening | Checks the actual simulated fill percentage against required limits, assuring strategy triggers actually execute. |
| **`E03_overshoot_tail`** | Execution Hardening | Asserts the 95th percentile of price overshoot doesn't aggressively exceed the production limit cap. |
| **`E04_latency_control`** | Execution Hardening | Validates the actual measured touch-to-fill latency conforms to realistic broker latency medians and tails. |
| **`E05_no_touch_rate`** | Execution Hardening | Limits the percentage of orders that enter the book but never touch the limit price. |
| **`E06_cap_curve_monotonicity`** | Execution Hardening | Ensures profit scaling behaves monotonically up to the barrier plateau, proving the barrier mathematically acts as a ceiling. |
| **`E07_session_dispersion`** | Execution Hardening | Enforces variance limits on overshoot globally to detect reliance on hyper-specific timezone volatility. |
| **`E08_state_fragility`** | Execution Hardening | Detects if performance depends excessively on statistically fragile, low-volume sub-states. |
| **`E09_worst_window_stress`** | Execution Hardening | Guards against catastrophic out-of-sample monthly tail drops. Guarantees worst-month performance exceeds the acceptable floor constraint. |
| **`E10_execution_net_viability`** | Execution Hardening | Final aggregate execution check. Mandates strictly positive theoretical net-spread Lower Bound 95% over acceptable trade volumes. |
| **`E11_session_overshoot_dispersion`** | Execution Hardening | Checks the variance of profit overshoot after enforcing causal session caps specifically. |
| **`E12_cap_plateau_width_pips`** | Execution Hardening | Ensures there is a reasonably wide "plateau" of profitable cap settings, proving the strategy isn't dependent on a lucky, hyper-specific barrier size. |
| **`E13_nonfill_opportunity_cost_pips`** | Execution Hardening | Calculates the theoretical profit lost to the barrier cap limitation. Severe opportunity costs flag models that rely heavily on unbound trend runs. |

### Stage 5: Reduced Core
| Code | Governance Category | Purpose / Abstract Meaning |
| --- | --- | --- |
| **`R01_post_pre_row_ratio`** | Reduced-Core Stability | Ensures the dimensionality reduction process doesn't trim the candidate universe down to practically zero rows (over-pruning). |
| **`R02_top_state_dependency`** | Reduced-Core Stability | Caps the maximum statistical contribution a single market state can provide to the summarized cluster. |
| **`R03_reselection_stability`** | Reduced-Core Stability | Enforces consecutive consistency in state selection over rolling windows. |

### Stage 6: Tick-Exact Portability
| Code | Governance Category | Purpose / Abstract Meaning |
| --- | --- | --- |
| **`X01_portable_family_count`** | Portability | The count of strategy families that remain profitable across multiple currency symbols. |
| **`X02_family_std_mean`** | Portability | Protects against wildly volatile strategy families across different symbols. |
| **`X03_family_spread_mean`** | Portability | Minimizes the divergence between the best-performing and worst-performing implementation of the same strategy family. |

### Stage 7: Logical & Statistical Audit
| Code | Governance Category | Purpose / Abstract Meaning |
| --- | --- | --- |
| **`S01_lb95_dependence_gap`** | Statistical Audit | Validates that assuming independent-and-identically-distributed (IID) events doesn't aggressively inflate the Lower Bound 95% threshold compared to cluster-aware stats. |
| **`S02_practical_lb95_gt0`** | Statistical Audit | The ultimate hard-gate: The trade-weighted, dependence-aware 95% confidence lower-bound of gross profit MUST remain above zero. |
| **`S03_multiplicity_survival`** | Statistical Audit | Proves the discovery survives Bonferroni or False Discovery Rate (FDR) penalties for p-hacking across thousands of tested barriers. |
| **`C01_threshold_timing`** | Pipeline Logical Audit | Enforces that every selected row satisfies `pred_prob >= threshold_exec`, month labels align with close timestamps, and threshold lookback is at least 1 day. Prevents leakage or malformed execution selection. |
| **`C02_threshold_stability`** | Pipeline Logical Audit | Asserts each (month, candidate) group uses exactly one threshold value. In rolling mode, stability is checked per day. Prevents inconsistent thresholding that invalidates signal-selection reproducibility. |
| **`C03_state_gate_integrity`** | Pipeline Logical Audit | Ensures no selected states failed train-time gate checks. Prevents weak, ungated states from inflating apparent diversification or capacity. |
| **`C04_overlap_divergence`** | Pipeline Logical Audit | Detects when activity-count-based correlation diverges significantly from PnL-based correlation across states. Flags hidden co-movement understated by the portfolio overlap filter. |
| **`C05_stop_limit_join`** | Pipeline Logical Audit | Validates stop-limit detail join integrity: zero duplicate keys and ≥99.5% monthly match rate between prediction rows and tick-level detail records. |
| **`C06_fill_rate_monotonicity`** | Pipeline Logical Audit | Asserts fill rate increases (or stays flat) monotonically as the stop-limit cap widens. Violations imply inconsistent cap simulation or merge logic. |
| **`C07_denominator_consistency`** | Pipeline Logical Audit | Verifies that summary-level row counts, signal counts, and fill rates are exactly reproducible from the monthly table. Prevents misstated capacity or expectancy. |
| **`C08_warmup_continuity`** | Pipeline Logical Audit | Enforces contiguous month coverage with exactly `min_train_months` warmup rows and no unexpected status values. Prevents silent omission of difficult months. |
| **`C09_bootstrap_reproducibility`** | Pipeline Logical Audit | Recomputes LB95 gross and signal confidence bounds from the monthly series and asserts they match the summary output to within ≤1e-8. Guards against mislabeled robustness claims. |
| **`C10_timestamp_causality`** | Pipeline Logical Audit | Validates strict temporal ordering: `close_ts ≤ touch_open_ts ≤ touch_close_ts`, and touch month labels match the actual touch timestamp. Catches timezone coercion or bar alignment bugs that invalidate execution simulation. |

### Stage 8: Robustness & Stress
| Code | Governance Category | Purpose / Abstract Meaning |
| --- | --- | --- |
| **`T01_stress_elasticity`** | Margin Stress | Calculates the slope of performance degradation as simulated trading costs are artificially increased. |
| **`T02_first_negative_costplus`** | Margin Stress | Pinpoints the exact amount of extra slippage/spread required to push the strategy into negative expectancy. |
| **`T03_post_worst_month_recovery`** | Margin Stress | Measures the bounce-back ratio after the strategy experiences its worst month. Prevents deploying models that enter terminal drawdowns. |
| **`T04_max_survivable_cost_lb95_trade`** | Margin Stress | The ultimate stress hard-gate: how much exogenous cost shock the strategy can absorb while keeping the LB95 confidence interval perfectly bounded above zero. |

### Stage 9: Live Governance Deploy Locks
| Code | Governance Category | Purpose / Abstract Meaning |
| --- | --- | --- |
| **`G01_near_fail_count`** | Predeploy Pressure | Tracks how many gates were passed by uncomfortably tight margins. |
| **`G02_open_warning_age_days`** | Predeploy Pressure | Monitors the average age of unresolved informational warnings logged by operators. |
| **`G03_lock_drift_flags`** | Predeploy Pressure | Triggers an immediate halt if the configuration hash of the candidate lock mismatches the compiled artifact. |

### Stage 10: Known Risks Backlog
| Code | Governance Category | Purpose / Abstract Meaning |
| --- | --- | --- |
| **`B10.1` - `B10.7`** | Base SLA Backlog | The structural process risks implemented and evaluated manually (e.g. documentation freshness, escalation SLAs). |
| **`B11_open_risks`** | SLA Targets | The absolute count of manually recorded Jira/runbook risks currently marked open for a given symbol. |
| **`B12_high_open`** | SLA Targets | The count of High/Critical severity open infrastructural risks. |
| **`B13_avg_days_open`** | SLA Targets | Tracks team compliance on fixing known alpha threats within service-level agreements. |

### Stage 11: Execution Monte Carlo (Tick-Level Uncertainty)
| Code | Governance Category | Purpose / Abstract Meaning |
| --- | --- | --- |
| **`EM01_lb95_per_signal_s1`** | Execution MC | Simulates mild structural adversity (S1) across execution factors and asserts the net profit remains positive. |
| **`EM02_lb95_per_signal_s2`** | Execution MC | Simulates moderate structural adversity (S2) and enforces a minimum strict confidence lower-bound. |
| **`EM03_prob_negative_month_s1`** | Execution MC | Asserts the probability of experiencing a net negative month under S1 latency assumptions is below the acceptable ruin tolerance limit. |
| **`EM04_fill_rate_drop_vs_s0_s1`** | Execution MC | Ensures that adding variable latency (S1) doesn't cause the strategy's order fill-rate to plummet artificially compared to zero-latency (S0). |
| **`EM05_nan_core_fields`** | Execution MC | Integrity check asserting zero corrupted executions occurred during the thousands of Monte Carlo branching simulations. |

### Stage 12: API Parity Against Reduced Core
| Code | Governance Category | Purpose / Abstract Meaning |
| --- | --- | --- |
| **`AP01_signal_missing_expected_count`** | API Signal Parity | Counts reduced-core selected keys missing from the API runtime output. |
| **`AP02_signal_extra_runtime_count`** | API Signal Parity | Counts extra API-selected keys absent from reduced-core truth. |
| **`AP03_signal_parity_pass`** | API Signal Parity | Binary hard gate indicating exact selected-key parity was achieved. |
| **`AP04_execution_failed_checks_high_critical`** | API Execution Parity | Counts high/critical execution parity failures in the downstream trade lifecycle validator. |
| **`AP05_execution_parity_pass`** | API Execution Parity | Binary hard gate indicating execution parity passed against reduced-core truth. |
| **`AP06_api_parity_stage_pass`** | API Parity Stage | Final Stage 12 pass indicator. It is green only when both signal parity and execution parity are green. |

## Interpretation Guide
- **Early Stages (D -> E):** Focuses heavily on the mechanics of data integrity, CatBoost model stability, and realistic spread/slippage parameterization.
- **Middle Stages (R -> T):** Focuses on the composition of the selected sub-universe and mathematically proving the statistical edge is immune to multiple-comparisons and cost-friction shocks.
- **Late Stages (G -> EM):** Focuses on human operational SLA compliance, code-drift prevention, and absolute final-mile execution non-determinism checks.
