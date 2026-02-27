# Stage 6 - Tick-Exact Verification and Portability

## Objective
Verify label/path correctness at tick level and assess whether family-level edge transfers across symbols.

## Inputs
- Tick-exact summary/monthly/replay:
- `data/analysis/tick_opportunity_mining/reduced_core_rolling*/<SYMBOL>_oco_tick_exact_*.csv`
- Candidate catalogs across symbols:
- `data/analysis/tick_opportunity_mining/<SYMBOL>_oco_candidates.csv`

## Process
- Recompute outcomes with independent tick replay checks.
- Compare replay outcomes vs stored labels.
- Build cross-symbol family portability diagnostics (`X01-X03`).

## Exact Calculations
- `X01_portable_family_count`:
- count of families with positive mean gross across all tracked symbols
- `X02_family_std_mean`:
- mean across families of std(symbol-level family mean gross)
- `X03_family_spread_mean`:
- mean across families of (max-min symbol-level family mean gross)

## Causality / Leakage Controls
- Replay validation uses the same event keys and tick chronology.
- Portability uses historical outcomes only; no forward leakage.

## Failure Modes
- Hidden replay mismatches despite aggregate pass rates.
- Edge that appears strong but is symbol-specific and non-transferable.

## Interpretation Guide
- Higher tick-exact rates imply contract fidelity.
- Higher `X01` implies better transferability.
- Lower `X02/X03` imply lower cross-symbol dispersion.

## Validation Gates
- Tick-exact contract checks are hard.
- `X01-X03` are informational for universality assessment.

## Reproduction Commands
```bash
uv run python scripts/verify_oco_tick_exact_shortlist.py \
  --symbols EURUSD,GBPUSD,USDJPY
```

## Traceability
- `scripts/verify_oco_tick_exact_shortlist.py`
- `docs/analysis/*_oco_tick_exact_rolling_report.md`
- `docs/strategy_bible/generated/stage_06_snapshot.md`

## Generated Run Snapshot
<!-- GENERATED:STAGE_06:START -->
### Auto Snapshot - Stage 06

- generated_at: `2026-02-27 07:51:49 UTC`
- Verifier recomputes OCO outcomes independently from stored labels.
- All summary rates should remain near 1.0 for contract consistency.

#### Key Results
| symbol   |   rows_selected |   rows_verified |   exact_match_rate |   pos_label_match_rate | overall_pass   |
|:---------|----------------:|----------------:|-------------------:|-----------------------:|:---------------|
| EURUSD   |           31507 |           31507 |                  1 |                      1 | True           |
| GBPUSD   |           34861 |           34861 |                  1 |                      1 | True           |
| USDJPY   |           50326 |           50326 |                  1 |                      1 | True           |

#### Details
| symbol   |   months |   exact_min |   exact_mean |   pos_min |   pos_mean |
|:---------|---------:|------------:|-------------:|----------:|-----------:|
| EURUSD   |        9 |           1 |            1 |         1 |          1 |
| GBPUSD   |        9 |           1 |            1 |         1 |          1 |
| USDJPY   |        9 |           1 |            1 |         1 |          1 |

#### Plots
![stage_06_tick_exact_monthly](../figures/oco_bible/stage_06_tick_exact_monthly.png)

#### Cross-Symbol Portability (X01-X03)
| family                |   symbols_covered |   mean_across_symbols |   std_across_symbols |   spread_max_min |   x01_all_symbols_positive |
|:----------------------|------------------:|----------------------:|---------------------:|-----------------:|---------------------------:|
| oco_first_touch_clean |                 3 |              2.33238  |            0.638742  |        1.13561   |                        nan |
| oco_first_touch       |                 3 |              0.214237 |            0.0474996 |        0.0851724 |                        nan |
<!-- GENERATED:STAGE_06:END -->
