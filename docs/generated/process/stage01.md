# Stage 01 Data Foundation

Stage ID: `stage01`

Builds and audits Raw Tick Data, Tick Bars, and the Velocity Dataset used by downstream research and fitting stages.

## Canonical Commands

- `make rebuild-all`

## Required Inputs

- `/Users/danielfisher/Desktop/dukascopy_ticks/${SYMBOL}/${SYMBOL}_${YYYYMM}_ticks.parquet`
- `/Users/danielfisher/Desktop/tick/${SYMBOL}/${SYMBOL}_${YYYYMM}_ticks.parquet`

## Produced Evidence

- `data/global_tickbars/${SYMBOL}_{100,1000,2000}tick.parquet`
- `data/analysis/tick_velocity/${SYMBOL}_{100,1000,2000}tick_velocity.parquet`
- `docs/analysis/data_reliability_report.md`

## Gates

- `data_foundation_available`: `PASS_FAIL`, severity `critical`
- `data_reliability_audit_pass`: `PASS_FAIL`, severity `high`

## Implementation Scope

- `Makefile` (registry)
- `scripts/audit_data_reliability.py` (registry)
- `scripts/build_global_tick_bars.py` (registry)
- `scripts/build_tick_velocity_dataset.py` (registry)
- `scripts/download_histdata_ticks.py` (registry)
- `scripts/download_tick_vault_data.py` (registry)
- `scripts/onboard_symbol.py` (registry)

## Tests

- `tests/test_download_tick_vault_data.py`
- `tests/test_download_histdata_ticks.py`
- `tests/test_build_tick_velocity_dataset.py`
- `tests/test_data_reliability_audit.py`
