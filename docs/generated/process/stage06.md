# Stage 06 Tick-Exact Verification

Stage ID: `stage06`

Replays the Shortlist at exact tick granularity to verify selected opportunities and portability assumptions before robustness checks.

## Canonical Commands

- `make onboard-symbol`

## Required Inputs

- `data/analysis/tick_opportunity_mining/reduced_core_rolling/${SYMBOL}_oco_reduced_state_schedule.csv`
- `data/analysis/tick_opportunity_mining/wfo_m3to1_oco_fullcap_${symbol}/${SYMBOL}_oco_monthly_predictions.parquet`

## Produced Evidence

- `data/analysis/tick_opportunity_mining/tick_exact/${SYMBOL}_oco_tick_exact_summary.csv`
- `docs/analysis/${symbol}_oco_tick_exact_rolling_report.md`

## Gates

- `tick_exact_verification_pass`: `PASS_FAIL`, severity `critical`

## Implementation Scope

- `Makefile` (registry)
- `scripts/onboard_symbol.py` (registry)
- `scripts/verify_oco_tick_exact_shortlist.py` (registry)

## Tests

- `tests/test_oco_leakage_label_integrity.py`
