# Behemoth OCO Strategy Documentation

This documentation set orients operators and new contributors to the active **tick-based OCO stop-limit research/governance pipeline**. The active execution path is monthly walk-forward, Python-led, and broker-adapter targeted at JForex.

## What Is Active
- Strategy type: directional OCO candidate selection with stop-limit entry realism and fixed-horizon post-touch outcome labeling.
- Core model engine: CatBoost-based monthly WFO probability ranking (`pred_prob`) for execution-threshold selection.
- Model lifecycle policy: one-month validity and monthly retrain, with predictions expiring at the next test-month boundary.
- Active symbol universe: `EURUSD`, `GBPUSD`, `USDJPY`, `USDCHF`, `AUDUSD`, `USDCAD`.
- Core objective: find high-count, positive gross microstructure opportunities and govern them with strict causal validation.
- Validation posture: stage-gated, artifact-driven, and contract-checked.

## Who This Is For
- Operators should use this page to jump to current readiness, governing reports, and the runbook.
- New contributors should use this page to find the manual, the walkthrough, and the stage specs in order.

## Key Sources
1. Strategy manual and stage bible: [`STRATEGY_MASTER_MANUAL.md`](./STRATEGY_MASTER_MANUAL.md), [`docs/strategy_bible/stage_01_data_foundation.md`](./strategy_bible/stage_01_data_foundation.md)
2. Generated snapshots and governed status: [`docs/strategy_bible/generated/pipeline_snapshot.md`](./strategy_bible/generated/pipeline_snapshot.md), [`docs/analysis/index.md`](./analysis/index.md)
3. Contract checks and issues: [`docs/analysis/oco_docs_contract_report.md`](./analysis/oco_docs_contract_report.md)

## Authority
- `canonical`: governing synthesis or policy source.
- `generated truth snapshot`: generated status surface tied to current artifacts.
- `interpretive report`: analysis or operator guidance derived from governed artifacts.
- `compatibility`: legacy or optional surface that does not define the active path.
- `candidate`: pre-governance or proposed material that is not yet binding.
- `archive`: historical reference only.

### Authority Note
- Authority label: `canonical`
- Authoritative for: entrypoint guidance, authority hierarchy, and source-routing across the active docs set.
- Not authoritative for: live symbol readiness, stage gate outcomes, or deployment decisions by itself.
- Depends on: [`STRATEGY_MASTER_MANUAL.md`](./STRATEGY_MASTER_MANUAL.md), [`docs/strategy_bible/generated/pipeline_snapshot.md`](./strategy_bible/generated/pipeline_snapshot.md), and [`docs/analysis/oco_docs_contract_report.md`](./analysis/oco_docs_contract_report.md).

## Start Here
- Full strategy definition: [`STRATEGY_MASTER_MANUAL.md`](./STRATEGY_MASTER_MANUAL.md)
- Stage-by-stage specs: [`docs/strategy_bible/stage_01_data_foundation.md`](./strategy_bible/stage_01_data_foundation.md) through [`docs/strategy_bible/stage_14_jforex_runtime_certification.md`](./strategy_bible/stage_14_jforex_runtime_certification.md)
- Daily operator flow: [`docs/strategy_bible/operator_runbook.md`](./strategy_bible/operator_runbook.md)
- Current generated snapshot: [`docs/strategy_bible/generated/pipeline_snapshot.md`](./strategy_bible/generated/pipeline_snapshot.md)

## Read This Next
- Operator path: [`docs/strategy_bible/generated/pipeline_snapshot.md`](./strategy_bible/generated/pipeline_snapshot.md), [`docs/analysis/operator_action_report.md`](./analysis/operator_action_report.md), [`docs/analysis/oco_alert_remediation_report.md`](./analysis/oco_alert_remediation_report.md), [`docs/analysis/oco_docs_contract_report.md`](./analysis/oco_docs_contract_report.md)
- New contributor path: [`docs/walkthrough.md`](./walkthrough.md), [`STRATEGY_MASTER_MANUAL.md`](./STRATEGY_MASTER_MANUAL.md), [`docs/strategy_bible/stage_01_data_foundation.md`](./strategy_bible/stage_01_data_foundation.md), [`docs/strategy_bible/stage_03_monthly_wfo.md`](./strategy_bible/stage_03_monthly_wfo.md)

## Current Symbol Status
Use `docs/strategy_bible/generated/pipeline_snapshot.md` as the current per-symbol status view for all active symbols. It is the highest-signal top-level source for:
- current symbol coverage across the six-symbol active universe
- per-symbol mean gross and LB95 summary metrics
- gate outcomes and all-gates-pass status

The strategy manual remains the synthesis layer. When the manual and generated symbol status differ, the generated snapshot and docs-contract outputs win.

## Standard Refresh Cycle
```bash
make docs-contract-ci
uv run python scripts/build_oco_strategy_bible.py --manifest configs/research/docs/oco_bible_manifest.yaml --strict false
uv run python scripts/build_oco_system_reference_docs.py
uv run mkdocs build
```

## Local Docs
```bash
make docs
```
Serves on `127.0.0.1:8001`.
