# OCO Operator Playbook

- generated_at_utc: `2026-03-03T12:43:32Z`
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
| symbol   | metric_id                        | band   | action_code           | owner     | action_summary         |
|:---------|:---------------------------------|:-------|:----------------------|:----------|:-----------------------|
| USDCAD   | E11_session_overshoot_dispersion | amber  | A2_RECALIBRATE        | execution | review and monitor     |
| AUDUSD   | T03_post_worst_month_recovery    | red    | A2_RECALIBRATE        | risk      | escalate and remediate |
| EURUSD   | T03_post_worst_month_recovery    | red    | A2_RECALIBRATE        | risk      | escalate and remediate |
| EURUSD   | W13_threshold_fragility          | red    | A3_HALT_AND_REMEDIATE | research  | escalate and remediate |
| USDCAD   | T03_post_worst_month_recovery    | red    | A2_RECALIBRATE        | risk      | escalate and remediate |
| USDCHF   | E11_session_overshoot_dispersion | red    | A3_HALT_AND_REMEDIATE | execution | escalate and remediate |