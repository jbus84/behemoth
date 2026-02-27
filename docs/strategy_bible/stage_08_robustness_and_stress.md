# Stage 8 - Robustness and Stress

## Objective
Quantify conservative expectancy and stress elasticity under cost and regime perturbations.

## Inputs
- Robustness summary:
- `data/analysis/tick_opportunity_mining/full_robustness/<SYMBOL>_oco_robustness_summary.csv`
- Reduced monthly outputs:
- `data/analysis/tick_opportunity_mining/reduced_core_rolling*/<SYMBOL>_oco_reduced_monthly.csv`

## Process
- Evaluate bootstrap LB95 and multiplicity-adjusted metrics.
- Evaluate cost-plus stress curve behavior.
- Compute stress diagnostics (`T01-T03`).

## Exact Calculations
- `T01_stress_elasticity`:
- slope across available `mean_net_pips_costplus_*` levels
- `T02_first_negative_costplus`:
- minimum stress level where net turns negative; if never negative, set to max tested level
- `T03_post_worst_month_recovery`:
- `mean_gross(next_month_after_worst) / abs(mean_gross(worst_month))`

## Causality / Leakage Controls
- Uses finalized out-of-sample monthly artifacts only.

## Failure Modes
- Positive mean but negative conservative lower bound.
- Excessive sensitivity to cost assumptions.
- Poor recovery after adverse month.

## Interpretation Guide
- `T01` less negative is more resilient.
- Higher `T02` implies deeper cost resilience.
- Higher `T03` suggests stronger post-worst-month recovery efficiency.

## Validation Gates
- Robustness LB95 and monthly consistency are hard promotion criteria.
- `T01-T03` are stress diagnostics for hardening.

## Canonical Analysis Reports
- `docs/analysis/eurusd_oco_monthly_wfo_robustness_fullcap_report.md`
- `docs/analysis/gbpusd_oco_monthly_wfo_robustness_fullcap_report.md`
- `docs/analysis/usdjpy_oco_monthly_wfo_robustness_fullcap_report.md`
- `docs/analysis/remediation_metric_decomposition.md`

## Reproduction Commands
```bash
uv run python scripts/analyze_oco_monthly_wfo_robustness.py \
  --symbols EURUSD,GBPUSD,USDJPY
```

## Traceability
- `scripts/analyze_oco_monthly_wfo_robustness.py`
- `docs/analysis/*_oco_monthly_wfo_robustness_*_report.md`
- `docs/strategy_bible/generated/stage_08_snapshot.md`

## Generated Run Snapshot
<!-- GENERATED:STAGE_08:START -->
### Auto Snapshot - Stage 08

- generated_at: `2026-02-27 12:15:07 UTC`
- Robustness summary uses bootstrap lower bounds from the configured smoke/full run artifacts.
- Interpretation: LB95 > 0 indicates conservative positive expectancy under sampled uncertainty.
- Overfit panel adds month-stratified null uplift and dependence-aware LB95 comparisons.
- T01-T03 summarize stress elasticity, negative-cost crossing, and post-worst-month recovery efficiency.

#### Key Results
| symbol   |   quantile |   rows |   months |   mean_gross_pips |   lb95_trade_mean_gross_pips |   positive_months |
|:---------|-----------:|-------:|---------:|------------------:|-----------------------------:|------------------:|
| EURUSD   |        0.9 | 325515 |        9 |           1.03932 |                      1.02232 |                 9 |
| GBPUSD   |        0.9 | 414128 |        9 |           1.01745 |                      1.00211 |                 9 |
| USDJPY   |        0.9 | 459585 |        9 |           1.37853 |                      1.36145 |                 9 |

#### Details
| symbol   |   pvalue_month_mean_gt0 |   pvalue_bonferroni |   pvalue_fdr_bh |   t01_stress_elasticity |   t02_first_negative_costplus |   t03_post_worst_month_recovery |   lb95_trade_mean_net_pips_costplus_0.00 |   lb95_trade_mean_net_pips_costplus_0.20 |   lb95_trade_mean_net_pips_costplus_0.40 |   lb95_trade_mean_net_pips_costplus_0.60 |
|:---------|------------------------:|--------------------:|----------------:|------------------------:|------------------------------:|--------------------------------:|-----------------------------------------:|-----------------------------------------:|-----------------------------------------:|-----------------------------------------:|
| EURUSD   |             1.15261e-09 |         1.15261e-09 |     1.15261e-09 |                      -1 |                             1 |                        0.915934 |                                  1.02232 |                                 0.821562 |                                 0.621901 |                                 0.423091 |
| GBPUSD   |             0           |         0           |     0           |                      -1 |                             1 |                        1.33224  |                                  1.00211 |                                 0.804603 |                                 0.603551 |                                 0.404395 |
| USDJPY   |             0           |         0           |     0           |                      -1 |                             1 |                        1.04299  |                                  1.36145 |                                 1.16268  |                                 0.961219 |                                 0.762256 |

#### Plots
![stage_08_robustness_lb95](../figures/oco_bible/stage_08_robustness_lb95.png)
![stage_08_overfit_symbol_panel](../figures/oco_bible/stage_08_overfit_symbol_panel.png)
<!-- GENERATED:STAGE_08:END -->
