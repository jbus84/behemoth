# KF Directional Q80 One-Bar Report

## Scope
- Mix: `m5=NONE,m15=MOM+REV,m60=REV`
- Trade timeframes: `m15,m60` (with `m5` as feature context only)
- Decision timeframes: `m15,m60`
- Actionable regime: `|kf_z_accel| >= q80` (train-only threshold per timeframe)
- Label horizon: 1 bar (`+1/-1/0` directional triple-barrier style)
- Model families: `heuristic,logit,hgbt,dual_head,regime_expert`
- Universe: FX + commodities excluding oil-linked pairs

## Reproduction Command (Smoke)
```bash
python scripts/meta_kf_directional_wfo.py \
  --mixes "m5=NONE,m15=MOM+REV,m60=REV" \
  --trade-timeframes m15,m60 \
  --start-test-year 2024 \
  --end-test-year 2024 \
  --decision-timeframes m15,m60 \
  --models heuristic,logit,hgbt,dual_head,regime_expert \
  --accel-quantile 0.80 \
  --pt-quantile 0.60 \
  --sl-quantile 0.60 \
  --exclude-oil \
  --out-prefix kf_dir_q80_1bar_trade_m15m60_smoke
```

## Headline Smoke Result (2024 fold)
| Variant | Trades | Mean PnL/Trade (bps) | Sharpe | Annualized BPS | CAGR | TIM % | Worst Single Day (bps) | Max Daily DD (bps) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| baseline | 1,271 | -0.951 | -0.414 | -1,190.268 | -0.008 | 76.908 | -653.76 | -3,590.13 |
| directional_candidate | 1,254 | -0.875 | -0.376 | -1,079.703 | -0.007 | 76.506 | -653.76 | -3,619.31 |
| directional_promoted | 1,271 | -0.951 | -0.414 | -1,190.268 | -0.008 | 76.908 | -653.76 | -3,590.13 |

Promotion outcome:
- `oos_hard_pass=false`
- `promoted_source=baseline_hard_fail`
- Selected decision config in smoke fold: `m15:logit@p0.45/ev0.00`

## Generated Artifacts
- `data/analysis/kf_dir_q80_1bar_trade_m15m60_smoke_summary.csv`
- `data/analysis/kf_dir_q80_1bar_trade_m15m60_smoke_folds.csv`
- `data/analysis/kf_dir_q80_1bar_trade_m15m60_smoke_model_grid.csv`
- `data/analysis/kf_dir_q80_1bar_trade_m15m60_smoke_oos_trades.csv`
- `data/analysis/kf_dir_q80_1bar_trade_m15m60_smoke_oos_scored.csv`
- `data/analysis/kf_dir_q80_1bar_trade_m15m60_smoke_yearly.csv`
- `data/analysis/kf_dir_q80_1bar_trade_m15m60_smoke_pair_timeframe_breakdown.csv`

## Notes
- This smoke run validates wiring, causality, and outputs. It is not a full multi-year promotion run.
- Full production assessment should be run across `2020-2025` and compared against hard promotion gates.

## Z-Cross Objective Update
- Production objective should use `--target-mode z_cross` (full trade outcomes), not one-bar outcomes.
- Latest full run command:
```bash
python scripts/meta_kf_directional_wfo.py \
  --mixes "m5=NONE,m15=MOM+REV,m60=REV" \
  --trade-timeframes m15,m60 \
  --decision-timeframes m15,m60 \
  --models heuristic,logit,hgbt,dual_head,regime_expert \
  --pair-sharpe-cutoff 0.10 \
  --target-mode z_cross \
  --start-test-year 2020 \
  --end-test-year 2025 \
  --out-prefix kf_dir_zcross_trade_m15m60_ps10_full
```
