# AGENTS Guide (Repo Onboarding)

This file is the fastest path to becoming productive in this repo.

## 1) What Is Actually Active

The active system is the tick-based OCO stop-limit research/governance pipeline documented in:

- `docs/STRATEGY_MASTER_MANUAL.md`
- `docs/strategy_bible/`
- `docs/analysis/`

Do not treat `README.md` as authoritative for detailed strategy behavior. Read the strategy bible and master manual instead.

## 2) Active Symbol Universe

- `EURUSD`
- `GBPUSD`
- `USDJPY`
- `USDCHF`
- `AUDUSD`
- `USDCAD`

## 3) Core Data Paths

- Raw ticks (external, local machine): `/Users/danielfisher/Desktop/tick/<SYMBOL>/<SYMBOL>_YYYYMM_ticks.parquet`
- Tick bars: `data/global_tickbars/<SYMBOL>_{100,1000,2000}tick.parquet`
- Velocity datasets: `data/analysis/tick_velocity/<SYMBOL>_{100,1000,2000}tick_velocity.parquet`
- Main pipeline artifacts: `data/analysis/tick_opportunity_mining/`

Canonical raw tick parquet schema:

- `timestamp` (UTC)
- `bid`
- `ask`
- `mid`
- `spread`
- `log_return`

## 4) Key Scripts (OCO Path)

- Ingestion helper: `scripts/download_histdata_ticks.py`
- Tick bars: `scripts/build_global_tick_bars.py`
- Velocity features: `scripts/build_tick_velocity_dataset.py`
- Stage 2 mining: `scripts/run_tick_opportunity_mining.py`
- Stage 3 monthly WFO (CatBoost): `scripts/run_tick_opportunity_monthly_wfo.py`
- Stage 4 stop-limit realism: `scripts/analyze_oco_stop_limit_tickfill.py`
- Stage 5 reduced-core rolling: `scripts/select_oco_reduced_core_rolling.py`
- Stage 6 tick-exact verifier: `scripts/verify_oco_tick_exact_shortlist.py`
- Stage 8 robustness: `scripts/analyze_oco_monthly_wfo_robustness.py`
- Docs contract: `scripts/validate_oco_docs_contract.py`

## 5) Config Entry Points

Experiment configs:

- `configs/research/experiments/eurusd_tick_opportunity_mining.yaml`
- `configs/research/experiments/eurusd_tick_opportunity_monthly_wfo_oco_fullcap_2025.yaml`
- `configs/research/experiments/eurusd_oco_reduced_core_rolling_2025.yaml`
- `configs/research/experiments/gbpusd_tick_opportunity_monthly_wfo_oco_fullcap_2025.yaml`
- `configs/research/experiments/gbpusd_oco_reduced_core_rolling_2025.yaml`
- `configs/research/experiments/usdjpy_tick_opportunity_monthly_wfo_oco_fullcap_2025.yaml`
- `configs/research/experiments/usdjpy_oco_reduced_core_rolling_2025.yaml`
- `configs/research/experiments/usdchf_tick_opportunity_mining.yaml`
- `configs/research/experiments/usdchf_tick_opportunity_monthly_wfo_oco_fullcap_2025.yaml`
- `configs/research/experiments/usdchf_oco_reduced_core_rolling_2025.yaml`

Docs/build manifest:

- `configs/research/docs/oco_bible_manifest.yaml`

Governance locks:

- `configs/research/governance/oco/*_oco_live_lock.json`

## 6) 5-Minute Health Check

Run from repo root:

```bash
git status --short
uv run pytest -q tests/test_oco_docs_contract.py tests/test_tick_opportunity_mining.py tests/test_tick_opportunity_ml_dataset.py tests/test_oco_leakage_label_integrity.py tests/test_monthly_wfo_threshold_causality.py
uv run python scripts/validate_oco_docs_contract.py --out-checks-csv data/analysis/tick_opportunity_mining/docs_contract_checks.csv --out-issues-csv data/analysis/tick_opportunity_mining/docs_contract_issues.csv --report-out docs/analysis/oco_docs_contract_report.md
```

Current known docs-contract failure may remain:

- `C4A` (`nan_metric_values`) in `edge_clarity_stage_metrics.csv`

Treat that as a known issue unless user explicitly asks to fix it.

## 7) Standard Docs Rebuild

Fast full docs/gov refresh:

```bash
make docs-contract-ci
uv run mkdocs build
```

Serve docs locally:

```bash
make docs
```

Serves at `127.0.0.1:8001`.

## 8) End-to-End Symbol Pipeline (Template)

Replace `<SYM>` and config paths as needed.

1. Build bars:

```bash
uv run python scripts/build_global_tick_bars.py \
  --tick-root /Users/danielfisher/Desktop/tick \
  --output-dir data/global_tickbars \
  --symbols <SYM> \
  --base-ticks 100 \
  --aggregate-multiples 1,10,20 \
  --price-source bid \
  --timestamp-mode as_utc \
  --overwrite
```

2. Build velocity:

```bash
uv run python scripts/build_tick_velocity_dataset.py \
  --tick-root /Users/danielfisher/Desktop/tick \
  --tickbar-dir data/global_tickbars \
  --out-dir data/analysis/tick_velocity \
  --symbols <SYM> \
  --bar-ticks-grid 100,1000,2000 \
  --overwrite
```

3. Mining:

```bash
uv run python scripts/run_tick_opportunity_mining.py --config configs/research/experiments/<sym>_tick_opportunity_mining.yaml
```

4. Monthly WFO:

```bash
uv run python scripts/run_tick_opportunity_monthly_wfo.py --config configs/research/experiments/<sym>_tick_opportunity_monthly_wfo_oco_fullcap_2025.yaml
```

5. Stop-limit realism:

```bash
uv run python scripts/analyze_oco_stop_limit_tickfill.py \
  --symbols <SYM> \
  --pred-paths data/analysis/tick_opportunity_mining/wfo_2025_m3to1_oco_fullcap_<sym>/<SYM>_oco_monthly_predictions.parquet \
  --velocity-dir data/analysis/tick_velocity \
  --tick-root /Users/danielfisher/Desktop/tick \
  --caps 0.5,0.8,1.0,1.2,1.5,2.0 \
  --use-exec-selected true \
  --quantile 0.9 \
  --out-dir data/analysis/tick_opportunity_mining/stop_limit_tickfill_fullcap
```

6. Reduced-core rolling:

```bash
uv run python scripts/select_oco_reduced_core_rolling.py --config configs/research/experiments/<sym>_oco_reduced_core_rolling_2025.yaml
```

7. Tick-exact:

```bash
uv run python scripts/verify_oco_tick_exact_shortlist.py \
  --symbol <SYM> \
  --dataset-dir data/analysis/tick_velocity \
  --pred-path data/analysis/tick_opportunity_mining/wfo_2025_m3to1_oco_fullcap_<sym>/<SYM>_oco_monthly_predictions.parquet \
  --shortlist-state-csv data/analysis/tick_opportunity_mining/reduced_core_<sym>/<SYM>_oco_reduced_states.csv \
  --locked-quantile 0.9 \
  --selection-mode auto \
  --family-required oco_first_touch_clean \
  --oco-hold-mode from_touch \
  --oco-include-no-touch true
```

8. Robustness:

```bash
uv run python scripts/analyze_oco_monthly_wfo_robustness.py \
  --pred-path data/analysis/tick_opportunity_mining/wfo_2025_m3to1_oco_fullcap_<sym>/<SYM>_oco_monthly_predictions.parquet \
  --quantiles 0.5,0.6,0.7,0.8,0.9,0.95 \
  --bootstrap-paths 600 \
  --stress-extra-cost-grid 0.1,0.2,0.3,0.5
```

## 9) HistData Ingestion (New Months)

Use:

```bash
uv run python scripts/download_histdata_ticks.py \
  --symbols EURUSD,GBPUSD,USDJPY,USDCHF,AUDUSD,USDCAD \
  --months 202601,202602 \
  --tick-root /Users/danielfisher/Desktop/tick \
  --skip-existing true
```

This downloads monthly ZIPs from HistData and writes canonical parquet. It does not keep ZIP/CSV artifacts.

## 10) Governance/Docs Integration Notes

- Many governance reports read shared aggregate files in `data/analysis/tick_opportunity_mining/`.
- If you rerun stop-limit with one symbol only, you may overwrite shared summary files. Prefer running all active symbols when updating shared reports.
- After changing symbol universe, regenerate:
  - `oco_execution_drift_*`
  - `oco_threshold_sensitivity*`
  - `oco_alert_disposition.csv`
  - `oco_governance_explainability.csv`
  - strategy bible and docs contract outputs

## 11) Common Pitfalls

- `README.md` can mislead strategy context; use strategy bible/manual instead.
- Some scripts still encode assumptions around historical 3-symbol universe. If adding/removing symbols, check for hardcoded symbol sets.
- Long robustness runs can take several minutes and often produce output only at completion.
- `uv run` can hit sandbox cache permission issues in restricted execution; rerun with elevated permissions when needed.
- Do not delete or rewrite user data under `/Users/danielfisher/Desktop/tick` unless explicitly asked.

## 12) Definition of Done for Agent Changes

Before finalizing substantial changes:

1. Relevant pipeline scripts executed and artifacts produced.
2. Targeted tests pass.
3. `mkdocs build` succeeds.
4. `docs_contract_checks.csv` regenerated and reviewed.
5. `git status` is clean after commit, and changes are pushed if requested.
