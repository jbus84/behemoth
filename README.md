# Behemoth (Tick OCO Governance Pipeline)

**Status**: Active production research baseline  
**Strategy**: Tick-based OCO stop-limit selection with docs-driven governance

## What This Repo Is
This repository is an artifact-first, stage-gated pipeline for OCO research and governance.  
The strategy lifecycle is encoded as reproducible scripts + generated artifacts + docs contracts.

## Source of Truth
For strategy behavior and operating policy, use:
- `docs/STRATEGY_MASTER_MANUAL.md`
- `docs/strategy_bible/`
- `docs/analysis/`

`README.md` is onboarding-level and intentionally high level.

Artifact priority (highest first):
1. `data/analysis/tick_opportunity_mining/*` governed artifacts
2. `docs/strategy_bible/generated/*` snapshots
3. `docs/analysis/*` governed reports
4. narrative docs (`README.md`, manuals)

## Active Symbol Universe
- `EURUSD`
- `GBPUSD`
- `USDJPY`
- `USDCHF`
- `AUDUSD`
- `USDCAD`

## Docs-Driven Contract: What It Guarantees
`scripts/validate_oco_docs_contract.py` enforces that:
- required docs/snapshots exist and are structurally complete,
- core governance/report artifacts are present, recent, and schema-valid,
- rule-universe and monitoring explainability/disposition artifacts are coherent.

## Docs-Driven Contract: What It Does Not Guarantee
A passing docs contract alone does not mean all symbols are deploy-ready.  
Always verify symbol-level governance posture in:
- `docs/strategy_bible/generated/stage_09_snapshot.md`
- `docs/analysis/operator_action_report.md`
- `docs/analysis/oco_alert_remediation_report.md`

## Core Operator Commands
```bash
# Refresh docs/governance contracts
make docs-contract-ci

# Build docs site
uv run mkdocs build --strict

# Serve docs locally
make docs
```

## Governance Freeze
```bash
# Freeze governance locks for all active symbols (defaults to registry symbols)
uv run python scripts/freeze_oco_live_governance.py
```

Registry source:
- `configs/research/governance/oco_rule_universe_registry.yaml`

## Practical Release Check (Short)
1. Run `make docs-contract-ci`.
2. Confirm Stage 9 predeploy coverage has no missing symbols.
3. Confirm no unresolved red/high blockers in operator/remediation reports.
4. Rebuild docs with `uv run mkdocs build --strict`.
