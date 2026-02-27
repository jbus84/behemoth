# Stage 7 - Logical and Statistical Audit

## Objective
Enforce logical pipeline contracts and summarize multiplicity-aware significance diagnostics.

## Inputs
- Logical audit checks/issues:
- `data/analysis/tick_opportunity_mining/oco_logical_audit_checks.csv`
- `data/analysis/tick_opportunity_mining/oco_logical_audit_issues.csv`
- Robustness summary (for inference ladder inputs):
- `data/analysis/tick_opportunity_mining/full_robustness/<SYMBOL>_oco_robustness_summary.csv`

## Process
- Evaluate `C01-C10` logical checks.
- Aggregate fails by symbol/severity.
- Build inference ladder diagnostics (`S01-S03`).

## Exact Calculations
- `S01_lb95_dependence_gap`:
- preferred: `lb95_trade_mean_gross_pips_iid - lb95_trade_mean_gross_pips_month_block`
- fallback: `lb95_trade_mean_gross_pips - lb95_trade_mean_gross_pips_month_block`
- sentinel if unavailable: `0.0`
- `S02_practical_lb95_gt0 = 1[lb95_trade_mean_gross_pips > 0]`
- `S03_multiplicity_survival = 1[bonferroni_pass OR fdr_pass]`

## Causality / Leakage Controls
- Logical checks include key ordering, partitioning, and lineage integrity.
- Significance metrics are interpreted only on out-of-sample WFO outputs.

## Failure Modes
- Hidden contract breaks despite positive PnL.
- Multiplicity-adjusted significance collapse.

## Interpretation Guide
- `S01` near 0 means minimal gap under dependence-aware lower bounds.
- `S02=1` indicates practical conservative positivity.
- `S03=1` indicates survival under multiplicity correction.

## Validation Gates
- `C01-C10` are hard logical gates.
- `S01-S03` are statistical interpretation diagnostics.

## Operator MRM Checks
- Verify any `S01` jump is explained by known dependence structure changes.
- Escalate if `S02` drops below 1 for any production symbol.
- Treat repeated `S03=0` as a model-risk event requiring re-selection review.

## Escalation Matrix
| condition | owner | action |
| --- | --- | --- |
| `S02 < 1` | research | halt symbol from promotion pipeline |
| `S03 = 0` in two consecutive runs | research + risk | rerun Stage 2-5 with constrained state family |
| `S01` exceeds historical p95 | risk | add temporary uncertainty uplift and monitor |

## Reproduction Commands
```bash
uv run python scripts/audit_oco_pipeline_logical_issues.py
```

## Traceability
- `scripts/audit_oco_pipeline_logical_issues.py`
- `docs/analysis/oco_logical_audit_report.md`
- `docs/strategy_bible/generated/stage_07_snapshot.md`

## Generated Run Snapshot
<!-- GENERATED:STAGE_07:START -->
### Auto Snapshot - Stage 07

- generated_at: `2026-02-27 09:11:16 UTC`
- C01..C10 checks are the logical contract gate before robustness sign-off.
- Open issue rows: 0.

#### Key Results
| symbol   |   total_checks |   failed_checks |
|:---------|---------------:|----------------:|
| EURUSD   |             10 |               0 |
| GBPUSD   |             10 |               0 |
| USDJPY   |             10 |               0 |

#### Details
| check_id   | status   |   size |
|:-----------|:---------|-------:|
| C01        | pass     |      3 |
| C02        | pass     |      3 |
| C03        | pass     |      3 |
| C04        | pass     |      3 |
| C05        | pass     |      3 |
| C06        | pass     |      3 |
| C07        | pass     |      3 |
| C08        | pass     |      3 |
| C09        | pass     |      3 |
| C10        | pass     |      3 |

#### Plots
![stage_07_audit_failures](../figures/oco_bible/stage_07_audit_failures.png)

#### Statistical Inference Ladder (S01-S03)
| symbol   |   lb95_trade_mean_gross_pips |   s01_lb95_dependence_gap |   pvalue_bonferroni |   pvalue_fdr_bh |   s02_practical_lb95_gt0 |   s03_multiplicity_survival |
|:---------|-----------------------------:|--------------------------:|--------------------:|----------------:|-------------------------:|----------------------------:|
| EURUSD   |                      1.02232 |                         0 |         1.15261e-09 |     1.15261e-09 |                        1 |                           1 |
| GBPUSD   |                      1.00211 |                         0 |         0           |     0           |                        1 |                           1 |
| USDJPY   |                      1.36145 |                         0 |         0           |     0           |                        1 |                           1 |
<!-- GENERATED:STAGE_07:END -->
