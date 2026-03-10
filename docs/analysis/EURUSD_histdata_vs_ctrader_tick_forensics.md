# EURUSD HistData vs cTrader Tick Forensics

Window analyzed:
- Start: `2025-07-07T00:00:00Z`
- End: `2025-07-09T00:00:00Z`
- Runtime DB: `data/db/backtests/eurusd_reconcile.db`
- HistData source: `/Users/danielfisher/Desktop/tick/EURUSD/EURUSD_202507_ticks.parquet`

Generated artifacts:
- `data/analysis/backtest_reconcile/EURUSD_histdata_vs_ctrader_tick_forensics_summary.csv`
- `data/analysis/backtest_reconcile/EURUSD_histdata_vs_ctrader_hourly_coverage.csv`
- `data/analysis/backtest_reconcile/EURUSD_histdata_vs_ctrader_missing_runs.csv`

## Key Findings

1. Tick cadence differs materially.
   - Runtime rows: `98,518`
   - HistData rows: `136,043`
   - Coverage ratio (runtime/hist): `0.7242`
   - Median intertick: runtime `909 ms` vs HistData `307 ms` (`2.96x` slower)

2. Price path is still very close at minute level.
   - Minute close-return correlation: `0.9904`
   - Minute return absolute MAE: `0.118 pips`
   - Minute return absolute p90: `0.25 pips`

3. Spread profile diverges strongly.
   - Runtime spread mean: `0.000015` (about `0.15 pips`)
   - HistData spread mean: `0.000047` (about `0.47 pips`)
   - Runtime zero-spread ratio: `53.9%`
   - HistData zero-spread ratio: `0%`

4. Divergence is regime-dependent, worst around rollover.
   - Lowest pooled UTC-hour coverage: hour `20` with `0.3476`.
   - Top HistData-only run (shown as Europe/London BST): `2025-07-07 21:29:59+01:00` to `2025-07-07 22:00:31+01:00` (`477s`)
   - Next day similar gap: `2025-07-08 21:29:51+01:00` to `2025-07-08 22:00:34+01:00` (`397s`)
   - In UTC, these are approximately `20:30` to `21:00`, i.e. rollover window.

## Interpretation

- This does not look like a pure timezone-offset bug:
  - Best lag on second-count alignment is at `0s`.
  - Minute returns align very tightly.
- The evidence is more consistent with feed microstructure differences between cTrader historical ticks and HistData:
  - Different tick event timing/density.
  - Different spread model (runtime much tighter and often zero).
- These differences can directly drive strategy divergence through:
  - Different 100-tick bar close times (feature timestamp shift),
  - Lower runtime `cost_est_pips`,
  - Different execution gate outcomes (observed extra selected rows).
