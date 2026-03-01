# Symbol Onboarding Playbook

- generated_at_utc: `2026-03-01T07:42:31Z`

This playbook documents how to onboard a new symbol into the OCO strategy pipeline.
It is **auto-generated** on every `make docs-contract` run to stay in sync with the current codebase.

---

## Quick Start (One Command)

The entire process is automated via a single Makefile target:

```bash
# Full onboarding (downloads 8 years of tick data, runs ML pipeline, builds docs):
make onboard-symbol SYMBOL=USDCAD MONTHS=201801-202602

# Dry-run (prints every command without executing):
make onboard-symbol SYMBOL=USDCAD MONTHS=201801-202602 ONBOARD_FLAGS='--dry-run'

# Skip data download (tick bars already built):
make onboard-symbol SYMBOL=USDCAD ONBOARD_FLAGS='--skip-data'

# Force re-download and rebuild everything:
make onboard-symbol SYMBOL=USDCAD MONTHS=201801-202602 ONBOARD_FLAGS='--force'
```

> [!TIP]
> Always start with `--dry-run` to review what will happen before committing to a full run.

---

## Pipeline Stages (Detail)

The orchestrator (`scripts/onboard_symbol.py`) runs these stages in order:

### Stage 0: Data Acquisition

Downloads raw ticks from HistData and converts them to tick bars and velocity features.

| Step | Script | Output |
|------|--------|--------|
| 0a | `download_histdata_ticks.py` | `~/Desktop/tick/<SYM>/<SYM>_YYYYMM_ticks.parquet` |
| 0b | `build_global_tick_bars.py` | `data/global_tickbars/<SYM>_{50,100,200}tick.parquet` |
| 0c | `build_tick_velocity_dataset.py` | `data/analysis/tick_velocity/<SYM>_*_velocity.parquet` |

Skip with `--skip-data` if tick bars are already built.

### Stage 1: Configuration Cloning

Duplicates the EURUSD baseline configs, substituting the symbol name.

Templates cloned from `configs/research/experiments/`:
- `eurusd_oco_reduced_core_2025.yaml` → `<sym>_oco_reduced_core_2025.yaml`
- `eurusd_oco_reduced_core_rolling_2025.yaml` → `<sym>_oco_reduced_core_rolling_2025.yaml`
- `eurusd_tick_opportunity_mining.yaml` → `<sym>_tick_opportunity_mining.yaml`
- `eurusd_tick_opportunity_ml_dataset.yaml` → `<sym>_tick_opportunity_ml_dataset.yaml`
- `eurusd_tick_opportunity_monthly_wfo_2025.yaml` → `<sym>_tick_opportunity_monthly_wfo_2025.yaml`
- `eurusd_tick_opportunity_monthly_wfo_oco_fullcap_2025.yaml` → `<sym>_tick_opportunity_monthly_wfo_oco_fullcap_2025.yaml`

The script handles `EURUSD`→`<SYM>` and `eurusd`→`<sym>` substitution,
and fixes `stop_limit_detail_csv` to point at `stop_limit_tickfill_fullcap/`.

### Stage 2: ML Pipeline

Runs the 6 core analysis scripts in sequence:

| Step | Script | Purpose |
|------|--------|---------|
| 2a | `build_tick_opportunity_ml_dataset.py` | Feature engineering |
| 2b | `run_tick_opportunity_mining.py` | Candidate discovery |
| 2c | `run_tick_opportunity_monthly_wfo.py` | Base Walk-Forward Optimization |
| 2d | `run_tick_opportunity_monthly_wfo.py` | OCO Fullcap WFO |
| 2e | `analyze_oco_stop_limit_tickfill.py` | Stop-limit realism check |
| 2f | `select_oco_reduced_core_rolling.py` | Reduced core state selection |

Skip with `--skip-ml` if analysis data is already generated.

### Stage 3: Conditional Steps

These only run if the reduced core produced qualifying states (i.e. the state schedule CSV is non-empty):

| Step | Script | Purpose |
|------|--------|---------|
| 3a | `verify_oco_tick_exact_shortlist.py` | Tick-exact contract verification |
| 3b | `analyze_oco_monthly_wfo_robustness.py` | Cost-stress robustness analysis |

> [!NOTE]
> If the symbol fails the Reduced Core gate (yields an empty state schedule), these steps are
> automatically skipped. The documentation pipeline gracefully handles missing downstream reports.

### Stage 4: Registration

Programmatically patches all hardcoded symbol references:

| File | What gets patched |
|------|-------------------|
| `scripts/build_docs_catalog.py` | `SYMBOLS` tuple |
| `scripts/build_oco_execution_drift_report.py` | `--symbols` default |
| `scripts/build_oco_threshold_sensitivity_report.py` | `--symbols` default |
| `configs/research/docs/oco_bible_manifest.yaml` | New symbol block with all CSV/MD paths |
| `mkdocs.yml` | Navigation entries (conditional on which reports exist) |

> [!WARNING]
> The Python source patching uses regex to find and extend symbol lists. Review the diffs after
> onboarding to confirm correctness.

### Stage 5: Docs Rebuild

Runs the full documentation pipeline:

```bash
make docs-contract    # Catalog, drift, threshold, bible, validation
make docs-build       # mkdocs build --strict
```

Skip with `--skip-docs` to handle docs separately.

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `DOC_C` validation failures | Check `data/analysis/tick_opportunity_mining/docs_contract_issues.csv` |
| `mkdocs build --strict` fails | Likely a nav entry pointing to a non-existent report — remove it from `mkdocs.yml` |
| Symbol passes WFO but fails reduced core | Check per-state trade volume (`min_state_avg_rows: 200` gate) |
| HistData download fails | Check network; HistData may throttle requests |
