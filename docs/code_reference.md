# Code Reference

This page provides a structured map of the codebase. It is not exhaustive API documentation, but it **covers all core modules** and their responsibilities.

## Core Strategy Logic (`src/behemoth/`)

**`src/behemoth/core/kalman.py`**
- `compute_kalman_states(y, x, window, warmup)` — rolling Kalman filter for dynamic hedge ratio and spread error.

**`src/behemoth/core/zscore.py`**
- `compute_z_scores(errors, window)` — rolling Z‑score of spread error (causal).

**`src/behemoth/core/active_leg.py`**
- `select_active_leg(beta, low, high)` — pick which leg to trade based on beta band.

**`src/behemoth/core/events.py`**
- `simulate_trade(...)` — MOM/REV trade simulation with Z‑crossing exits and timeout.

**`src/behemoth/core/guardrail.py`**
- `apply_loss_streak_guardrail(df, ...)` — loss‑streak cooldown by pair (exit‑ordered).

**`src/behemoth/core/`**
- Feature extraction module removed (no ML features in core pipeline).

**`src/behemoth/core/metrics.py`**
- `sharpe_daily`, `sharpe_daily_active`, `sharpe_trade` — standard metrics.

**`src/behemoth/io/loaders.py`**
- `load_pair_data(...)` — load and align legs from parquet bars.

## API Service (`services/api/`)

**`services/api/main.py`**
- FastAPI endpoints for positions, orders, guardrail, and risk.

**`services/api/models.py`**
- SQLAlchemy models for positions, orders, guardrail state, account state.

**`services/api/schemas.py`**
- Pydantic request/response schemas for API endpoints.

**`services/api/settings.py`**
- Pydantic settings with YAML + env overrides (`configs/api.yaml`).

**`services/api/guardrail.py`**
- Guardrail state read/update logic.

**`services/api/risk.py`**
- Exposure limits and kill‑switch logic.

**`services/api/weights.py`**
- Pair weight loader (`configs/pair_weights.yaml`).

**`services/api/validation.py`**
- Pipeline vs DB validation utilities.

**`services/api/predict.py`**
- Rebuilds MOM signals for API/pipeline alignment checks.

## Pipelines & Scripts

**Pipelines (`pipelines/`)**
- `build_events_m5.py`, `build_events_m15.py` — MOM trade event generation.
- `wfo_mom_full_params*.py` — WFO parameter sweeps.

**Scripts (`scripts/`)**
- Validation: `validate_api_vs_pipeline.py`, `validate_db_predictions_vs_pipeline.py`
- Cost model: `analyze_cost_model.py`
- Stress tests, guardrail diagnostics, execution sensitivity.

## Migrations

**`services/api/migrations/versions/`**
- `001_create_positions.py`
- `002_create_guardrail_state.py`
- `003_add_account_state_and_position_alloc.py`
