# Behemoth OCO Strategy Documentation

This documentation set is for the active **tick-based OCO stop-limit strategy** with monthly walk-forward governance, where **CatBoost (Stage 3)** is the core probability-ranking model used to filter broad OCO event flow into executable reduced-core selections under strict causal thresholding.

## What System Is Active
- Strategy type: directional OCO candidate selection with stop-limit entry realism and fixed-horizon post-touch outcome labeling.
- Core model engine: CatBoost-based monthly WFO probability ranking (`pred_prob`) for execution-threshold selection.
- Model lifecycle policy: one-month validity and monthly retrain (predictions expire at new test-month boundary).
- Primary symbols: `EURUSD`, `GBPUSD`, `USDJPY`, `USDCHF`.
- Core objective: find high-count, positive gross microstructure opportunities and govern them with strict causal validation.
- Validation posture: stage-gated, artifact-driven, and contract-checked.

## Source of Truth
1. Strategy bible stages and snapshots: `docs/strategy_bible/`
2. Governed analysis reports: `docs/analysis/`
3. Contract checks and issues: `data/analysis/tick_opportunity_mining/docs_contract_checks.csv`, `data/analysis/tick_opportunity_mining/docs_contract_issues.csv`

## Start Here
- Full strategy definition: `STRATEGY_MASTER_MANUAL.md`
- Stage-by-stage specs: `docs/strategy_bible/stage_01_data_foundation.md` through `docs/strategy_bible/stage_11_execution_monte_carlo.md`
- Daily operator flow: `docs/strategy_bible/operator_runbook.md`
- Current generated snapshot: `docs/strategy_bible/generated/pipeline_snapshot.md`

## Latest Expected Gross (Training Window)
Using the latest available reduced-core month in current governed artifacts (`2025-12`):
- EURUSD: `1.061547` pips/trade (`status=ok`)
- GBPUSD: `n/a` (`status != ok`, rows `0`)
- USDJPY: `n/a` (`status != ok`, rows `0`)
- USDCHF: `0.723562` pips/trade (`status=ok`)

Full table and sources are in `STRATEGY_MASTER_MANUAL.md` Section `6.5`.

## Standard Refresh Cycle
```bash
make docs-contract-ci
uv run python scripts/build_oco_strategy_bible.py --manifest configs/research/docs/oco_bible_manifest.yaml --strict false
uv run python scripts/build_oco_system_reference_docs.py
uv run mkdocs build
```

## Local Docs
```bash
make docs
```
Serves on `127.0.0.1:8001`.
