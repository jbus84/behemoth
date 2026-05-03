# Stage 02 Opportunity Mining

Stage ID: `stage02`

Runs Opportunity Mining over the Velocity Dataset to create broad train-only Candidate State evidence.

## Canonical Commands

- `make onboard-symbol`

## Required Inputs

- `data/analysis/tick_velocity/${SYMBOL}_{100,1000,2000}tick_velocity.parquet`
- `configs/research/experiments/${symbol}_tick_opportunity_mining.yaml`

## Produced Evidence

- `data/analysis/tick_opportunity_mining/${SYMBOL}_tick_opportunity_mining_summary.csv`
- `docs/analysis/${symbol}_tick_opportunity_mining_report.md`

## Gates

- `opportunity_mining_pass`: `PASS_FAIL`, severity `critical`

## Implementation Scope

- `Makefile` (registry)
- `scripts/onboard_symbol.py` (registry)
- `scripts/run_tick_opportunity_mining.py` (registry)

## Tests

- `tests/test_tick_opportunity_mining.py`
