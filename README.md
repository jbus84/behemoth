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

## Pipeline Stages

| Stage | Name | Command | Notes |
|-------|------|---------|-------|
| 0 | Data Acquisition | `make rebuild-all MONTHS=...` | Downloads ticks, builds tick bars + velocity |
| 1 | Data Reliability | `make rebuild-all MONTHS=...` | Audit runs automatically within rebuild |
| 2 | Opportunity Mining | `make retrain-all` | Mine OCO candidate families |
| 3 | Monthly WFO | `make retrain-all` | CatBoost walk-forward + threshold schedules |
| 4 | Execution Realism | `make retrain-all` | Stop-limit tick-fill analysis |
| 5 | Reduced Core | `make retrain-all` | State-level governance selection |
| 6 | Tick-Exact Verification | `make retrain-all` | Runs within onboard when reduced core has states |
| 7 | Logical & Statistical Audit | `make retrain-all` | Also available standalone: `make stage7` |
| 8 | Robustness & Stress | `make retrain-all` | Runs within onboard when reduced core has states |
| 9 | Live Governance | `make stage9` | Alias for `make freeze-live-governance` |
| 10 | Known Risks & Backlog | -- | Documentation only; see `docs/strategy_bible/` |
| 11 | Execution Monte Carlo | `make retrain-all` | Runs within onboard pipeline |
| 12 | API Parity | `make monthly-recert` | Runs as step 1 (jforex-dukascopy-matrix) |
| 12.5 | Local JForex Surrogate | `make monthly-recert` | Runs as step 3 (local-jforex-parity-matrix) |
| 13 | Dukascopy TestClient | `make monthly-recert` | Runs as step 2 (stage13-dukascopy-cert) |
| 14 | JForex Runtime Cert | `make monthly-recert` | Runs as step 4 (full-stage14-cert) |

Individual stages can also be run standalone via `make stageN` (e.g., `make stage12`, `make stage14`).

## Full Operator Workflow

### Initial Setup (one-time)
```bash
make provision              # Configure Alertmanager
make precommit-install      # Install git hooks
```

### Monthly Release Cycle

**Step 1: Retrain models**
```bash
make retrain-all
```
Runs the following stages for all symbols:
- Stage 2: Opportunity mining
- Stage 3: Monthly WFO (CatBoost + threshold schedules)
- Stage 4: Execution realism (stop-limit tick-fill)
- Stage 5: Reduced core selection
- Stage 6: Tick-exact verification (when reduced core has states)
- Stage 7: Logical & statistical audit
- Stage 8: Robustness & stress (when reduced core has states)
- Stage 11: Execution Monte Carlo

For a full rebuild including data download (adds stages 0-1):
```bash
make rebuild-all MONTHS=201801-202602
```

**Step 2: Freeze governance (stage 9)**
```bash
make freeze-live-governance
```

**Step 3: Build candidate bundle**
```bash
make monthly-build MODEL_MONTH=2026-02
```
Freezes model artifacts and threshold schedules into
`configs/research/governance/oco_candidate_builds/2026-02/`.

**Step 4: Certify (stages 12-14)**
```bash
make monthly-recert MODEL_MONTH=2026-02
```
Runs the certification chain:
- Stage 12: API parity (jforex-dukascopy-matrix)
- Stage 12.5: Local JForex surrogate parity
- Stage 13: Dukascopy TestClient certification
- Stage 14: JForex runtime certification

Prints per-symbol go/no-go summary.

**Step 5: Promote**
```bash
make promote-live MODEL_MONTH=2026-02
```
Only run after `monthly-recert` is green.

**Step 6: Restart live system**
```bash
make jforex-live
```

### Ad-hoc Commands
```bash
make quality                # Run all code quality checks
make test                   # Run pytest
make docs                   # Serve docs locally
make docs-contract-ci       # Refresh governance docs
make observability-up       # Start Prometheus + Grafana
```
