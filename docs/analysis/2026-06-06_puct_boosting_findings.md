# PUCT Boosting Smoke Test Findings — 2026-06-06

## Smoke-test command

```bash
PYTHONPATH=/Users/danielfisher/repositories/behemoth/.claude/worktrees/era-puct-boosting \
  /Users/danielfisher/repositories/behemoth/.venv/bin/python \
  scripts/era_scalp/_smoke_boost.py
```

The script calls `build_trade_splits('EURUSD', path)` and then `run_boost_search(..., budget=20)` for both targets.

## Velocity file used

`/Users/danielfisher/repositories/behemoth/data/analysis/tick_velocity/EURUSD_1000tick_velocity.parquet`

## Per-target results

### forward (horizon=12, budget=20)

| Metric | Value |
|--------|-------|
| V1 | -1.089 |
| V1_penalised | -1.229 |
| V2 | -3.507 |
| n_feat | 7 |
| holdout branch | flow_vol |
| holdout p_positive | 0.487 |
| holdout mean | -0.046 |
| holdout raw_mean | -2.178 |
| temporal p_positive | 0.875 |
| robust | False |
| dsr_sig | False |

### fair (horizon=3, budget=20)

| Metric | Value |
|--------|-------|
| V1 | -0.514 |
| V1_penalised | -0.554 |
| V2 | -0.962 |
| n_feat | 2 |
| holdout branch | flow_vol |
| holdout p_positive | 0.847 |
| holdout mean | 0.316 |
| holdout raw_mean | 0.144 |
| temporal p_positive | 0.975 |
| robust | False |
| dsr_sig | False |

## Honest verdict per [[feedback_gross_cost_significance_decomposition]]

A survivor is real ONLY if **V2 confirms V1** AND the holdout edge is positive with **DSR/temporal guards passing**.

- **forward**: V1 = -1.089, V2 = -3.507. V2 is much *worse* than V1 → clear overfit. Holdout mean is negative (-0.046) and raw_mean is -2.178 (deeply underwater). `robust=False`, `dsr_sig=False`. **Not a real survivor. Cost wall hit.**
- **fair**: V1 = -0.514, V2 = -0.962. V2 again worse than V1 → overfit. Holdout mean is positive (0.316) but `robust=False`, `dsr_sig=False`. Raw mean is only 0.144 pips, which is below the realistic spread/cost floor for retail FX. **Not a real survivor. Cost wall hit.**

## Additional observations

- Both survivors come from the `flow_vol` seed branch; PUCT did not discover a better composition than the seed.
- `n_feat` is small (2–7) so complexity penalty is not the issue.
- The negative V1 values on validation mean the GBDT + microstructure-feature pipeline is producing **no gross edge** on EURUSD 1000-tick data.
- This is consistent with the established finding: [[project_retail_fx_edge_cost_wall]] — every approach tested so far (scalp, cross-sectional, seasonality, TSMOM) shows gross ≤ retail cost or no gross edge on this data.
- Runtime for budget=20 was ~460 s (~7.7 min) per symbol pair of targets, dominated by single-threaded CatBoost training on ~1.7 M train rows.
