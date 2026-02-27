# OCO Metric Dictionary

## Objective
Define metric semantics, formulas, units, interpretation bands, and missing-value policy.

## Inputs
- `data/analysis/tick_opportunity_mining/edge_clarity_stage_metrics.csv`
- `docs/analysis/oco_edge_clarity_report.md`

## Process
- Keep one authoritative row per `metric_id`.
- Update when computation logic changes.
- Use this file for docs-contract checks.

## Metric Definitions

| metric_id | stage | formula | unit | interpretation bands | missing policy |
| --- | --- | --- | --- | --- | --- |
| D16_spread_regime_shift_z | 1 | z-score of last month mean `cost_est_pips` vs prior months | z | abs<1 stable; 1-2 watch; >2 review | disallow |
| D17_gap_burst_ratio | 1 | share of inter-bar gaps >10x median positive gap | ratio | <0.01 good; 0.01-0.05 watch; >0.05 risk | disallow |
| D18_clock_jitter_cv | 1 | std(delta_t)/median positive delta_t | ratio | <5 good; 5-15 watch; >15 risk | disallow |
| M01_top3_contrib_share | 2 | top3 edge-weight share | ratio | <0.20 good; 0.20-0.40 watch; >0.40 risk | disallow |
| M02_smoothness_abs_jump | 2 | median abs adjacent-horizon gross jump | pips | lower is better; >0.30 fragile | disallow |
| M03_positive_density | 2 | share selected hypotheses with positive mean gross | ratio | >0.7 good; 0.5-0.7 watch; <0.5 weak | disallow |
| W13_threshold_fragility | 3 | local gross slope around execution quantile | pips/quantile | lower is better; >3 fragile | disallow |
| W14_brier_drift_std | 3 | std monthly Brier | score | <0.01 stable; >0.03 drift risk | disallow |
| W15_selection_turnover | 3 | 1-mean consecutive-month Jaccard | ratio | <0.2 stable; 0.2-0.4 watch; >0.4 unstable | disallow |
| E11_session_overshoot_dispersion | 4 | CV of hourly mean overshoot | ratio | <1 good; 1-1.5 watch; >1.5 risk | disallow |
| E12_cap_plateau_width_pips | 4 | cap interval width with >=95% best per-signal result | pips | wider is better; <0.2 fragile | disallow |
| E13_nonfill_opportunity_cost_pips | 4 | `(ideal-realized)*fill` at best cap | pips | lower is better; >0.3 high erosion | disallow |
| erosion_overshoot_component | 4 | mean overshoot pips | pips | lower is better | disallow |
| erosion_spread_fee_plus_slip | 4 | base gross - realized per-signal gross | pips | lower is better | disallow |
| R01_post_pre_row_ratio | 5 | reduced rows / prefilter rows | ratio | >0.01 viable; <0.005 over-prune risk | disallow |
| R02_top_state_dependency | 5 | top state share from reduced summary | ratio | <0.4 good; >0.6 concentrated | disallow |
| R03_reselection_stability | 5 | `1-mean(state_churn_rate)` | ratio | >0.6 stable; 0.4-0.6 watch; <0.4 unstable | disallow |
| X01_portable_family_count | 6 | count of families positive across all tracked symbols | count | higher is better | disallow |
| X02_family_std_mean | 6 | mean family std across symbols | pips | lower is better | disallow |
| X03_family_spread_mean | 6 | mean family max-min spread | pips | lower is better | disallow |
| S01_lb95_dependence_gap | 7 | iid LB95 - dependence-aware LB95 (or fallback) | pips | near 0 preferred | disallow |
| S02_practical_lb95_gt0 | 7 | indicator(`lb95_trade_mean_gross_pips > 0`) | binary | 1 pass; 0 fail | disallow |
| S03_multiplicity_survival | 7 | indicator(Bonferroni pass or FDR pass) | binary | 1 pass; 0 fail | disallow |
| T01_stress_elasticity | 8 | slope of mean net across cost-plus levels | pips/cost | less negative is better | disallow |
| T02_first_negative_costplus | 8 | first negative cost-plus level (or max tested) | pips | higher is better | disallow |
| T03_post_worst_month_recovery | 8 | next-month minus worst-month mean gross | pips | >0 preferred | disallow |
| G01_near_fail_count | 9 | count of low-margin pass checks | count | 0 preferred | disallow |
| G02_open_warning_age_days | 9 | mean age of open warnings from SLA tracker | days | lower is better | allow when no open risks |
| G03_lock_drift_flags | 9 | config/hash/state drift failures | count | 0 required | disallow |
| B11_open_risks | 10 | open risk count from SLA tracker | count | lower is better | allow when tracker empty |
| B12_high_open | 10 | open high/critical risk count | count | 0 preferred | allow when tracker empty |
| B13_avg_days_open | 10 | average days open | days | lower is better | allow when tracker empty |

## Causality / Leakage Controls
- Metrics are computed from finalized stage artifacts; no forward joins beyond each stage contract.

## Failure Modes
- Undocumented metrics in outputs.
- Mismatched formula after script updates.

## Interpretation Guide
- Use this dictionary first, then stage-specific context in Stage docs.

## Validation Gates
- Docs-contract check requires full coverage of observed metrics by this dictionary.

## Reproduction Commands
```bash
uv run python scripts/build_oco_strategy_bible.py \
  --manifest configs/research/docs/oco_bible_manifest.yaml --strict false
```

## Traceability
- `scripts/build_oco_strategy_bible.py`
- `docs/analysis/oco_edge_clarity_report.md`
