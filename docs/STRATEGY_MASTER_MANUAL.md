# Strategy Master Manual - Causal Mixed Portfolio (FX + Commodities ex-Oil)

**Version**: 9.0  
**Date**: February 15, 2026  
**Status**: Active

[!IMPORTANT]
This manual is the canonical runbook for the current causal mixed-strategy pipeline.
It documents exactly how to recreate the mixed MOM/REV results, append them to the strategy report, and produce the recommended top-2 mixes.

## Scope
- Universe: FX + commodities whitelist excluding oil-linked pairs
- Excluded pairs: `Gold/Oil`, `Oil/Silver`
- Included pair examples: `EUR/GBP`, `AUD/NZD`, `EUR/CHF`, `EUR/JPY`, `GBP/JPY`, `CHF/JPY`, `EUR/AUD`, `GBP/AUD`, `AUD/CAD`, `GBP/CAD`, `NZD/CAD`, `Gold/Silver`
- Timeframes: `m5`, `m15`, `m60` (`h1` source for `m60`)
- Strategy families: `MOM`, `REV` across each timeframe
- Mixed search space: all 8 combinations of `MOM/REV` over `m5/m15/m60`

## Causal Rules

### Exit Contract
Exit conditions are frozen at entry in the event builders/reports:
- `max_hold_bars`
- `entry_cross_zero_level`
- `entry_stop_win_level_abs_z`
- `entry_use_stop_win`

No future information is used to modify an already-open trade's exit contract.

### Guardrail Contract
Guardrail is strictly causal and pair-local:
1. Check pause at entry timestamp.
2. If pair is paused, block the new entry.
3. Update loss streak only when accepted trades exit.
4. Never cancel already-open accepted trades.

This prevents the prior Sharpe/DD inflation bug from retroactive trade cancellation.

## Pipeline Overview
1. Run mixed triple-barrier meta filter over all 8 mixes.
2. Append mixed OOS variants into strategy report outputs.
3. Select top-2 promoted mixes by Sharpe (tie-break annualized bps).
4. Materialize top-2-only mixed report slices.

## Reproduction Commands
Run from repo root.

### 1) Run all mixed combinations (authoritative)
```bash
python scripts/meta_triple_barrier_mixed_dd.py \
  --mixes all \
  --exclude-oil \
  --out-prefix meta_tb_mixed_no_oil_allmix
```

Primary outputs:
- `data/analysis/meta_tb_mixed_no_oil_allmix_summary.csv`
- `data/analysis/meta_tb_mixed_no_oil_allmix_folds.csv`
- `data/analysis/meta_tb_mixed_no_oil_allmix_oos_trades.csv`
- `data/analysis/meta_tb_mixed_no_oil_allmix_oos_scored_trades.csv`
- `data/analysis/meta_tb_mixed_no_oil_allmix_threshold_grid.csv`
- `data/analysis/meta_tb_mixed_no_oil_allmix_label_ablation.csv`
- `data/analysis/meta_tb_mixed_no_oil_allmix_fold_calibration.csv`
- `data/analysis/meta_tb_mixed_no_oil_allmix_mc_daily_paths.csv`
- `data/analysis/meta_tb_mixed_no_oil_allmix_mc_daily_summary.csv`

### 2) Build strategy report with mixed variants included
```bash
python scripts/report_strategy_fx_comm_multi_tf.py \
  --exclude-oil \
  --include-meta-mixed \
  --meta-mixed-path data/analysis/meta_tb_mixed_no_oil_allmix_oos_trades.csv
```

Outputs:
- `data/analysis/strategy_fx_comm_no_oil_overall.csv`
- `data/analysis/strategy_fx_comm_no_oil_yearly.csv`
- `data/analysis/strategy_fx_comm_no_oil_pair.csv`
- `data/analysis/strategy_fx_comm_no_oil_pair_yearly.csv`
- `data/analysis/strategy_fx_comm_no_oil_accel_thresholds.csv`

Notes:
- Mixed rows are emitted as distinct variants: `mixed_<mix_id>__<variant>`
- No blending across mixes.

### 3) Produce recommended top-2 and filtered mixed report slices
```bash
python scripts/select_meta_mixed_top2.py
```

Outputs:
- `data/analysis/meta_tb_mixed_no_oil_allmix_recommended_top2.csv`
- `data/analysis/strategy_fx_comm_no_oil_mixed_top2_overall.csv`
- `data/analysis/strategy_fx_comm_no_oil_mixed_top2_yearly.csv`
- `data/analysis/strategy_fx_comm_no_oil_mixed_top2_pair.csv`
- `data/analysis/strategy_fx_comm_no_oil_mixed_top2_pair_yearly.csv`

## Current Recommended Top-2 (from full all-mix run)

Selection rule:
- Rank `meta_tb_promoted` mixes by `sharpe` descending, tie-break `annualized_bps_calendar` descending.

| Rank | Mix | Trades | Mean PnL/Trade (bps) | Sharpe | Annualized BPS | Max Daily DD (bps) | MC Pass Rate |
|---|---|---:|---:|---:|---:|---:|---:|
| 1 | `m5_mom__m15_mom__m60_rev` | 13,539 | 20.37 | 5.097 | 46,027.29 | -5,437.81 | 1.00 |
| 2 | `m5_mom__m15_rev__m60_rev` | 8,432 | 19.26 | 4.032 | 27,147.51 | -3,504.99 | 1.00 |

## Interpretation Notes
- `annualized_bps_calendar`: average daily bps over calendar days annualized by `365.25`.
- `max_daily_dd_bps`: worst peak-to-trough drawdown on the calendar-day cumulative bps curve (more negative is worse).
- `cagr` in report tables is account-equity CAGR under risk sizing (`risk_per_trade_pct=1%`); it is not directly comparable to raw bps without the risk-sizing context.

## Strategy Guide Hygiene
- This manual intentionally excludes deprecated or non-causal reporting sections.
- Source-of-truth artifacts are the CSVs listed above.
- If rerunning with changed parameters, update this guide with the exact command line and new result table.
