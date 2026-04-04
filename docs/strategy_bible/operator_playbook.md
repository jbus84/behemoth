# OCO Operator Playbook

- generated_at_utc: `2026-04-03T12:49:18Z`
- source_rules: `configs/research/docs/operator_action_rules.yaml`

## Action Codes
| action_code           | description                                                             |
|:----------------------|:------------------------------------------------------------------------|
| A0_MONITOR            | Metric within policy band.                                              |
| A1_REVIEW             | Investigate and monitor; no deploy block by itself.                     |
| A2_RECALIBRATE        | Recalibrate threshold/cost assumptions for the affected symbol.         |
| A3_HALT_AND_REMEDIATE | Block deployment for symbol until remediation and rerun.                |
| A9_DATA_GAP           | Data/schema gap; restore artifact integrity before governance sign-off. |

## Operator Checklist
1. Review `operator_action_status.csv` after each full pipeline run.
2. Confirm Stage-3 model lifecycle: one-month validity and monthly retrain for current test month.
3. Execute all `red` actions before deployment decisions.
4. Open a remediation task for persistent `amber` metrics (>=3 consecutive runs).
5. Block deployment if any `A3_` action remains unresolved.

## Current Escalations
| symbol   | metric_id                                        | band   | action_code           | owner     | action_summary         |
|:---------|:-------------------------------------------------|:-------|:----------------------|:----------|:-----------------------|
| AUDUSD   | S01_lb95_dependence_gap                          | amber  | A1_REVIEW             | research  | review and monitor     |
| EURUSD   | FTMO_ALLOC_BLOCK_RATE                            | amber  | A1_REVIEW             | risk      | review and monitor     |
| EURUSD   | FTMO_ALLOC_BUDGET_EXCEEDED_RATE                  | amber  | A1_REVIEW             | risk      | review and monitor     |
| GBPUSD   | T03_post_worst_month_recovery                    | amber  | A1_REVIEW             | risk      | review and monitor     |
| USDCHF   | E11_session_overshoot_dispersion                 | amber  | A2_RECALIBRATE        | execution | review and monitor     |
| USDCHF   | S01_lb95_dependence_gap                          | amber  | A1_REVIEW             | research  | review and monitor     |
| USDJPY   | S01_lb95_dependence_gap                          | amber  | A1_REVIEW             | research  | review and monitor     |
| AUDUSD   | E11_session_overshoot_dispersion                 | red    | A3_HALT_AND_REMEDIATE | execution | escalate and remediate |
| EURUSD   | E11_session_overshoot_dispersion                 | red    | A3_HALT_AND_REMEDIATE | execution | escalate and remediate |
| EURUSD   | FTMO_ALLOC_ADMITTED_MISSING_RESERVATION_ID_COUNT | red    | A3_HALT_AND_REMEDIATE | risk      | escalate and remediate |
| EURUSD   | S01_lb95_dependence_gap                          | red    | A2_RECALIBRATE        | research  | escalate and remediate |
| EURUSD   | W13_threshold_fragility                          | red    | A3_HALT_AND_REMEDIATE | research  | escalate and remediate |
| GBPUSD   | E11_session_overshoot_dispersion                 | red    | A3_HALT_AND_REMEDIATE | execution | escalate and remediate |
| USDCAD   | E11_session_overshoot_dispersion                 | red    | A3_HALT_AND_REMEDIATE | execution | escalate and remediate |
| USDCAD   | S01_lb95_dependence_gap                          | red    | A2_RECALIBRATE        | research  | escalate and remediate |