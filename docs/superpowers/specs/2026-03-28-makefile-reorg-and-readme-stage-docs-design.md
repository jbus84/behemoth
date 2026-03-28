# Makefile Reorganization & README Stage Documentation

## Goal

Reorganize the Makefile into logical sections, add `make stageN` alias targets for every pipeline stage (0-14), extract shared parameter blocks to eliminate duplication, and update the README with a stage-to-command reference table and a full step-by-step operator workflow.

## Architecture

Single-file Makefile reorganization (no splitting into includes). README gains two new sections: a pipeline stage reference table and a complete operator workflow showing which stages each composite command covers.

## Makefile Section Layout

The Makefile will be reorganized into these sections, in this order:

```
##==============================##
##  Variables & Configuration   ##
##==============================##

##==============================##
##  Development                 ##
##==============================##

##==============================##
##  Infrastructure              ##
##==============================##

##==============================##
##  Stages (0-14)               ##
##==============================##

##==============================##
##  Release Lifecycle           ##
##==============================##

##==============================##
##  Operations                  ##
##==============================##

##==============================##
##  Analysis                    ##
##==============================##

##==============================##
##  Documentation               ##
##==============================##

##==============================##
##  Help                        ##
##==============================##
```

### Variables & Configuration

Contains:
- `COLOR_*` variables
- `.env` include logic
- `REBUILD_SYMBOLS`, `SYMBOLS` definitions
- `CTRADER_*` path variables
- `OFFSET_ROBUSTNESS_*` defaults
- `.PHONY` declarations (split across multiple lines, grouped by section)
- Shared parameter blocks (`JFOREX_MATRIX_ARGS`)

### Development

Targets: `test`, `test-java`, `quality`, `ty`, `vulture`, `smellcheck`, `radon`, `xenon`, `lint`, `format`, `precommit-install`, `precommit-run`, `check-legacy-drift`

### Infrastructure

Targets: `provision`, `observability-up`, `observability-down`

### Stages (0-14)

Stage alias targets plus the underlying real targets, grouped by stage.

#### Stage Alias Targets

```makefile
stage0 stage1 stage2 stage3 stage4 stage5:
	@echo "Stages 0-5 run via 'make retrain-all' (skip data) or 'make rebuild-all MONTHS=...' (with data)."
	@echo "For a single symbol: make onboard-symbol SYMBOL=EURUSD MONTHS=201801-202602"

stage6:
	@echo "Stage 6 (tick-exact verification) runs as part of onboard-symbol when reduced core has states."
	@echo "Standalone not supported - run via make retrain-all or make rebuild-all."

stage7: audit-all

stage8:
	@echo "Stage 8 (robustness) runs as part of onboard-symbol when reduced core has states."
	@echo "Standalone not supported - run via make retrain-all or make rebuild-all."

stage9: freeze-oco

stage10:
	@echo "Stage 10 is documentation/risk tracking. See docs/strategy_bible/stage_10_known_risks_and_backlog.md"

stage11:
	@echo "Stage 11 (execution Monte Carlo) runs as part of onboard-symbol."
	@echo "Standalone not supported - run via make retrain-all or make rebuild-all."

stage12: stage12-api-parity

stage13: stage13-dukascopy-cert

stage14: stage14-jforex-cert
```

#### Underlying Targets by Stage

Targets grouped within this section:

- `onboard-symbol`, `retrain-all`, `rebuild-all` (stages 0-11 composite)
- `audit-all` (stage 7)
- `freeze-oco`, `freeze-oco-history`, `freeze-oco-dukascopy-candidate`, `validate-oco-history` (stage 9)
- `stage12-api-parity` (stage 12)
- `local-jforex-parity`, `local-jforex-parity-matrix`, `local-jforex-parity-ordinal`, `local-jforex-parity-spotlight`, `local-jforex-cert` (stage 12.5)
- `jforex-dukascopy-matrix` (stage 12, run within monthly-recert)
- `stage13-dukascopy-cert` (stage 13)
- `stage14-jforex-cert`, `full-stage14-cert`, `jforex-outcome-parity` (stage 14)

### Release Lifecycle

Targets: `monthly-build`, `monthly-recert`, `promote-live`

### Operations

Targets: `jforex-live`, `demo-cert-monitor`

### Analysis

Targets: `offset-robustness-study`, `offset-frozen-screen`, `dukascopy-source-audit`, `reconcile-historical-predictions`, `summarize-runtime-db-run`, `account-risk-monitoring-report`, `reconcile-account-risk-reservations`

### Documentation

Targets: `docs`, `docs-build`, `docs-contract`, `docs-contract-ci`, `docs-clean`

### Help

The `help` target will be updated to mirror the new section structure with sections: Development, Infrastructure, Stages, Release Lifecycle, Operations, Analysis, Documentation.

## Shared Parameter Block

Extract common JForex matrix parameters into a `define` block:

```makefile
define JFOREX_MATRIX_ARGS
	$(if $(SYMBOLS),--symbols "$(SYMBOLS)",) \
	--model-month $(or $(MODEL_MONTH),2025-07) \
	--models-dir $(or $(MODELS_DIR),models/oco_dukascopy_candidate) \
	--history-dir $(or $(HISTORY_DIR),configs/research/governance/oco_history_dukascopy_candidate) \
	--predictions-dir $(or $(PREDICTIONS_DIR),data/analysis/tick_opportunity_mining_dukascopy_candidate/wfo_2025_m3to1_oco_fullcap) \
	--report-dir $(or $(REPORT_DIR),data/analysis/backtest_reconcile) \
	--api-port $(or $(API_PORT),8000) \
	--requested-volume-units $(or $(REQUESTED_VOLUME_UNITS),10000) \
	--tick-batch-size $(or $(TICK_BATCH_SIZE),200) \
	--order-ttl-seconds $(or $(ORDER_TTL_SECONDS),900) \
	--api-timeout-seconds $(or $(API_TIMEOUT_SECONDS),60) \
	--metrics-port-base $(or $(METRICS_PORT_BASE),9465)
endef
```

Consumers (`local-jforex-parity-matrix`, `local-jforex-parity-ordinal`, `local-jforex-parity-spotlight`, `jforex-dukascopy-matrix`) reference `$(JFOREX_MATRIX_ARGS)` and add only their unique parameters.

## `.PHONY` Declaration

Split the current single-line `.PHONY` into grouped multi-line declarations, one per section:

```makefile
# Development
.PHONY: test test-java quality ty vulture smellcheck radon xenon \
        lint format precommit-install precommit-run check-legacy-drift

# Infrastructure
.PHONY: provision observability-up observability-down

# Stages
.PHONY: stage0 stage1 stage2 stage3 stage4 stage5 stage6 stage7 \
        stage8 stage9 stage10 stage11 stage12 stage13 stage14 \
        onboard-symbol retrain-all rebuild-all audit-all \
        freeze-oco freeze-oco-history freeze-oco-dukascopy-candidate \
        validate-oco-history stage12-api-parity \
        local-jforex-parity local-jforex-parity-matrix \
        local-jforex-parity-ordinal local-jforex-parity-spotlight \
        local-jforex-cert jforex-dukascopy-matrix \
        stage13-dukascopy-cert stage14-jforex-cert \
        full-stage14-cert jforex-outcome-parity

# Release Lifecycle
.PHONY: monthly-build monthly-recert promote-live

# Operations
.PHONY: jforex-live demo-cert-monitor

# Analysis
.PHONY: offset-robustness-study offset-frozen-screen \
        dukascopy-source-audit reconcile-historical-predictions \
        summarize-runtime-db-run account-risk-monitoring-report \
        reconcile-account-risk-reservations

# Documentation
.PHONY: docs docs-build docs-contract docs-contract-ci docs-clean

# Help
.PHONY: help
```

## README Changes

### New Section: Pipeline Stages

Added after "Monthly Release Flow". A table mapping every stage (0-14) to its command:

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
| 9 | Live Governance | `make stage9` | Alias for `make freeze-oco` |
| 10 | Known Risks & Backlog | -- | Documentation only; see `docs/strategy_bible/` |
| 11 | Execution Monte Carlo | `make retrain-all` | Runs within onboard pipeline |
| 12 | API Parity | `make monthly-recert` | Runs as step 1 (jforex-dukascopy-matrix) |
| 12.5 | Local JForex Surrogate | `make monthly-recert` | Runs as step 3 (local-jforex-parity-matrix) |
| 13 | Dukascopy TestClient | `make monthly-recert` | Runs as step 2 (stage13-dukascopy-cert) |
| 14 | JForex Runtime Cert | `make monthly-recert` | Runs as step 4 (full-stage14-cert) |

Individual stages can also be run standalone via `make stageN` (e.g., `make stage12`, `make stage14`).

### Replace: Practical Release Check

The current "Practical Release Check (Short)" section is replaced with a full operator workflow:

#### Initial Setup (one-time)

```bash
make provision              # Configure Alertmanager
make precommit-install      # Install git hooks
```

#### Monthly Release Cycle

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
make freeze-oco
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

#### Ad-hoc Commands

```bash
make quality                # Run all code quality checks
make test                   # Run pytest
make docs                   # Serve docs locally
make docs-contract-ci       # Refresh governance docs
make observability-up       # Start Prometheus + Grafana
```

## What Does Not Change

- No new Python scripts or modifications to existing scripts
- No changes to `onboard_symbol.py` (no stage-isolation flags)
- The README sections "What This Repo Is", "Source of Truth", "Active Symbol Universe", "Docs-Driven Contract", "Governance Freeze", and "Certification Semantics" remain unchanged
- The "Core Operator Commands" section remains but is updated to reference the new workflow section for details
- The "Monthly Release Flow" section remains as-is (it describes semantics, not step-by-step commands)

## Testing

- `make help` prints all targets organized by section
- `make stage7` runs `audit-all`
- `make stage9` runs `freeze-oco`
- `make stage12` runs `stage12-api-parity`
- `make stage13` runs `stage13-dukascopy-cert`
- `make stage14` runs `stage14-jforex-cert`
- `make stage0` through `make stage5` print guidance
- `make stage6`, `make stage8`, `make stage10`, `make stage11` print guidance
- All existing targets continue to work identically
- Shared `JFOREX_MATRIX_ARGS` produces identical CLI invocations to the current duplicated blocks
