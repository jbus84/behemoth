# Repo Structure (Production Baseline)

The active system is a tick-based ML Opportunity Cost Optimization (OCO) governance/runtime pipeline. The legacy stat-arb approach is no longer authoritative, though some compatibility surfaces still remain.

## Core layout

- `configs/research/`: YAML configurations defining features, pairs, rolling windows, and governance thresholds for the OCO ML models.
  - `docs/`: Configs for documentation generation.
  - `experiments/`: Parameter definitions for model testing.
  - `governance/`: Execution locks and allowed state constraints.
- `scripts/`: The core Python orchestration for the Governance Runtime. Contains feature generation, model training, documentation builders, and validation tasks.
- `src/jforex/`: The active JForex broker-adapter/runtime surface used by Stage 14 and live execution paths.
- `docs/`: Markdown files for the MkDocs site containing the dynamically-generated "Strategy Bible" and System Reference.
- `mkdocs.yml`: MkDocs configuration for deploying documentation.
- `data/`: Local tick data, generated CSV/Parquet models, and configuration artifacts (gitignored).
- `tests/`: Pytest suite enforcing the OCO documentation contracts and gate integrity.

## Pipeline Orchestration

The daily/monthly Governance Runtime pipeline is driven through the `scripts/` directory, while the active broker-adapter/runtime surface lives under `src/jforex/`.

**Key Scripts:**
- **Onboarding**: `scripts/onboard_symbol.py` (Top-level orchestrator for taking a symbol from tick data to live configuration locks)
- **Data Prep**: `scripts/build_global_tick_bars.py`, `scripts/build_tick_opportunity_ml_dataset.py`, `scripts/build_tick_velocity_dataset.py`
- **Analysis**: `scripts/run_tick_opportunity_mining.py`, `scripts/run_tick_opportunity_monthly_wfo.py`, `scripts/run_execution_monte_carlo.py`
- **Governance**: `scripts/freeze_oco_live_governance.py` (Outputs `_oco_live_lock.json` and `_oco_allowed_states.csv` configuration maps)
- **Docs Generation**: `scripts/build_oco_strategy_bible.py`, `scripts/build_oco_system_reference_docs.py`, etc.

## Notes

- The Governance Runtime relies on rolling governance artifacts defined by the ML models.
- Execution relies completely on the generated JSON and CSV configuration locks.
- The pipeline architecture operates independently of any active always-on API service or database backend.
