# Repo Structure (Production Baseline)

The active system is a pure tick-based ML Opportunity Cost Optimization (OCO) research pipeline. The legacy stat-arb approach has been entirely removed.

## Core layout

- `configs/research/`: YAML configurations defining features, pairs, rolling windows, and governance thresholds for the OCO ML models.
  - `docs/`: Configs for documentation generation.
  - `experiments/`: Parameter definitions for model testing.
  - `governance/`: Execution locks and allowed state constraints.
- `scripts/`: The core python orchestration for the OCO pipeline. Contains feature generation, model training, documentation builders, and validation tests.
- `docs/`: Markdown files for the MkDocs site containing the dynamically-generated "Strategy Bible" and System Reference.
- `mkdocs.yml`: MkDocs configuration for deploying documentation.
- `data/`: Local tick data, generated CSV/Parquet models, and configuration artifacts (gitignored).
- `tests/`: Pytest suite enforcing the OCO documentation contracts and gate integrity.

## Pipeline Orchestration

The daily/monthly research and execution pipeline is driven entirely through the `scripts/` directory.

**Key Scripts:**
- **Onboarding**: `scripts/onboard_symbol.py` (Top-level orchestrator for taking a symbol from tick data to live configuration locks)
- **Data Prep**: `scripts/build_global_tick_bars.py`, `scripts/build_tick_opportunity_ml_dataset.py`, `scripts/build_tick_velocity_dataset.py`
- **Analysis**: `scripts/run_tick_opportunity_mining.py`, `scripts/run_tick_opportunity_monthly_wfo.py`, `scripts/run_execution_monte_carlo.py`
- **Governance**: `scripts/freeze_oco_live_governance.py` (Outputs `_oco_live_lock.json` and `_oco_allowed_states.csv` configuration maps)
- **Docs Generation**: `scripts/build_oco_strategy_bible.py`, `scripts/build_oco_system_reference_docs.py`, etc.

## Notes

- The live strategy is heavily reliant on rolling offline artifacts defined by the ML models.
- Execution relies completely on the generated JSON and CSV configuration locks.
- The pipeline architecture operates independently of any active realtime API or Database.
