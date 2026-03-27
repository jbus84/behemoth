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

# Build a month-scoped candidate certification bundle
make monthly-build MODEL_MONTH=2026-02

# Run the definitive monthly certification gate
make monthly-recert MODEL_MONTH=2026-02

# Archive only after monthly-recert is green
make promote-live MODEL_MONTH=2026-02

# Build docs site
uv run mkdocs build --strict

# Serve docs locally
make docs
```

## Monthly Release Flow
The active release flow is split into build, recertification, and promotion.

1. `make monthly-build MODEL_MONTH=YYYY-MM`
Builds the frozen candidate month bundle under
`configs/research/governance/oco_candidate_builds/<YYYY-MM>/`.
This is the certification input. It is not a promoted archive.

2. `make monthly-recert MODEL_MONTH=YYYY-MM`
Runs the definitive certification chain against that frozen month bundle:
- Dukascopy JForex matrix
- formal Stage 13 certification
- local JForex surrogate parity
- formal Stage 14 runtime certification

3. `make promote-live MODEL_MONTH=YYYY-MM`
Archives only a certified month into
`configs/research/governance/oco_history_dukascopy_candidate/<YYYY-MM>/`.

## Certification Semantics
`monthly-recert` is green when all historically deployable symbols pass and any remaining non-pass symbols are expected non-deployable `NO_GO` cases.

Current expected `NO_GO` example:
- `USDCAD 2026-02` with `reason=no_gate_states`

Interpretation:
- `green` means the symbol is certified for deployment.
- `nogo` means governance correctly determined the symbol-month is non-deployable and it must not be traded.
- `red` means certification failed and blocks promotion.

`NO_GO` is not a silent pass-through. It is acceptable only when the historical governance lock explicitly marks the symbol-month non-deployable.

## Governance Freeze
```bash
# Freeze governance locks for all active symbols (defaults to registry symbols)
uv run python scripts/freeze_oco_live_governance.py
```

Registry source:
- `configs/research/governance/oco_rule_universe_registry.yaml`

## Practical Release Check (Short)
1. Run `make docs-contract-ci`.
2. Run `make monthly-build MODEL_MONTH=YYYY-MM`.
3. Run `make monthly-recert MODEL_MONTH=YYYY-MM`.
4. Confirm the result is `overall_pass: true` in `data/analysis/backtest_reconcile/monthly_recert_status.json`.
5. Confirm any non-green symbol is an expected `nogo`, not a `red` certification failure.
6. Run `make promote-live MODEL_MONTH=YYYY-MM`.
7. Rebuild docs with `uv run mkdocs build --strict`.
