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


## Stage 02 I/O Contract

**Input artifacts:**
- `data/analysis/tick_velocity/{symbol}_{bar_ticks}tick_velocity.parquet`
- `configs/research/experiments/{symbol}_tick_opportunity_mining.yaml`

**Output artifacts:**
- `data/analysis/tick_opportunity_mining/{symbol}_candidate_summary.csv`
- `data/analysis/tick_opportunity_mining/{symbol}_candidate_fills.parquet`
- `data/analysis/tick_opportunity_mining/{symbol}_directional_candidates.csv`
- `data/analysis/tick_opportunity_mining/{symbol}_oco_candidates.csv`
- `data/analysis/tick_opportunity_mining/{symbol}_oco_asymmetric_candidates.csv`
- `data/analysis/tick_opportunity_mining/{symbol}_no_touch_candidates.csv`
- `data/analysis/tick_opportunity_mining/{symbol}_dollar_residual_candidates.csv`
- `data/analysis/tick_opportunity_mining/{symbol}_dispersion_rank_candidates.csv`
- `data/analysis/tick_opportunity_mining/{symbol}_lead_lag_candidates.csv`

**Library → family expansion:**

| Library file | Families contained |
|--------------|--------------------|
| `<SYMBOL>_directional_candidates.csv` | directional, directional_inverse, directional_run, double_touch, pullback |
| `<SYMBOL>_oco_candidates.csv` | oco_first_touch |
| `<SYMBOL>_oco_asymmetric_candidates.csv` | oco_asymmetric |
| `<SYMBOL>_no_touch_candidates.csv` | no_touch |
| `<SYMBOL>_dollar_residual_candidates.csv` | dollar_residual |
| `<SYMBOL>_dispersion_rank_candidates.csv` | dispersion_rank |
| `<SYMBOL>_lead_lag_candidates.csv` | lead_lag |

**Required columns per candidate CSV:**
```
annualized_test_fills, bar_ticks, both_window_rate, both_window_rate_train, candidate_id, candidate_schema_version, family, gross_std_test, hit_rate_gross_test, horizon, mean_flow_persistence_train, mean_gross_pips_test, mean_gross_pips_train, mean_tick_burst_train, mean_vol_cluster_train, median_gross_pips_test, median_gross_pips_train, ml_ready_target_type, p_up_first, quality_score, quality_tier, quality_tier_basis, random_baseline_control_mean, random_baseline_p, random_baseline_z, regime_desc, selection_pass, selection_pass_basis, session_coverage, state_id, symbol, test_count, train_count
```
