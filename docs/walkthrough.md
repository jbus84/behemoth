# OCO Onboarding Walkthrough

This is the primary onboarding route for the active tick-based **Opportunity Cost Optimization (OCO)** system. The legacy stat-arb strategy is deprecated; the active repository centers on the Python-led OCO research and governance pipeline with JForex as the broker-adapter target.

## What Is Active

- Python remains the authoritative research, inference, and governance runtime.
- JForex is the active broker-adapter target.
- Generated artifacts and contract checks govern what is eligible for promotion.
- The active symbol universe is `EURUSD`, `GBPUSD`, `USDJPY`, `USDCHF`, `AUDUSD`, `USDCAD`.

## Authority

- The strategy manual is the synthesis layer for the active system definition and stage interpretation.
- Generated snapshots and contract checks are authoritative for current status, deployment readiness, and conflicts.
- Analysis reports provide evidence and operator interpretation, but they do not override governed snapshots.

## How The Stages Fit Together

1. Stage 01 builds the tick data foundation and reliability checks.
2. Stage 02 mines OCO opportunities from the tick-velocity features.
3. Stage 03 applies monthly walk-forward ranking and selection.
4. Stage 04 adds stop-limit execution realism and cap policy.
5. Stage 05 reduces the candidate core, and Stage 06 verifies tick-exact portability.
6. Stage 07 and Stage 08 audit the logic and stress the selection under robustness checks.
7. Stage 09 through Stage 14 govern deployment readiness, runtime parity, and broker certification.

## Where To Start

- Operators should start with [`docs/strategy_bible/generated/pipeline_snapshot.md`](./strategy_bible/generated/pipeline_snapshot.md), then [`docs/analysis/operator_action_report.md`](./analysis/operator_action_report.md), and then [`docs/analysis/oco_alert_remediation_report.md`](./analysis/oco_alert_remediation_report.md).
- Contributors changing behavior should start with [`docs/STRATEGY_MASTER_MANUAL.md`](./STRATEGY_MASTER_MANUAL.md), then the stage bible entrypoint [`docs/strategy_bible/stage_01_data_foundation.md`](./strategy_bible/stage_01_data_foundation.md), and then the supporting analysis reports.
- Readers checking site hygiene or publication quality should start with [`docs/analysis/index.md`](./analysis/index.md) and [`docs/analysis/oco_docs_contract_report.md`](./analysis/oco_docs_contract_report.md).

## Read This Next

- [`docs/STRATEGY_MASTER_MANUAL.md`](./STRATEGY_MASTER_MANUAL.md)
- [`docs/strategy_bible/generated/pipeline_snapshot.md`](./strategy_bible/generated/pipeline_snapshot.md)
- [`docs/strategy_bible/operator_runbook.md`](./strategy_bible/operator_runbook.md)
- [`docs/analysis/index.md`](./analysis/index.md)
- [`docs/analysis/oco_docs_contract_report.md`](./analysis/oco_docs_contract_report.md)
- [`docs/strategy_bible/stage_09_live_governance_and_deployment.md`](./strategy_bible/stage_09_live_governance_and_deployment.md)
- [`docs/strategy_bible/stage_13_dukascopy_testclient_parity.md`](./strategy_bible/stage_13_dukascopy_testclient_parity.md)
- [`docs/strategy_bible/stage_14_jforex_runtime_certification.md`](./strategy_bible/stage_14_jforex_runtime_certification.md)
