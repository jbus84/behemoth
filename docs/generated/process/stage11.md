# Stage 11 Execution Monte Carlo

Stage ID: `stage11`

Runs Execution Monte Carlo and validation checks over governed execution evidence to quantify account-level and session-level risk.

## Canonical Commands

- `make onboard-symbol`

## Required Inputs

- `data/analysis/tick_opportunity_mining/stop_limit_tickfill_fullcap/`
- `data/analysis/tick_opportunity_mining/reduced_core_rolling/`

## Produced Evidence

- `data/analysis/tick_opportunity_mining/execution_mc_checks.csv`
- `data/analysis/tick_opportunity_mining/execution_mc_issues.csv`
- `docs/analysis/oco_execution_monte_carlo_report.md`
- `docs/analysis/oco_execution_monte_carlo_validation_report.md`

## Gates

- `execution_monte_carlo_pass`: `PASS_FAIL`, severity `high`

## Implementation Scope

- `Makefile` (registry)
- `scripts/onboard_symbol.py` (registry)
- `scripts/run_execution_monte_carlo.py` (registry)
- `scripts/validate_execution_monte_carlo.py` (registry)

## Tests

- `tests/test_execution_monte_carlo.py`
