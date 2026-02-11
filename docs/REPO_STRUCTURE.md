# Repo Structure (Production Baseline)

## Core layout

- `src/behemoth/`: production logic (Kalman, Z-score, guardrail, metrics)
- `pipelines/`: deterministic batch runs (event generation + diagnostics)
- `scripts/`: thin wrappers and analysis/validation utilities used by docs/tests
- `services/api/`: FastAPI position + order state service
- `docs/`: documentation (MkDocs site uses these markdown files)
- `mkdocs.yml`: MkDocs configuration
- `configs/`: YAML config for API and pair weights
- `configs/prometheus.yml`: Prometheus scrape config
- `configs/grafana/`: Grafana provisioning
  - `configs/grafana/datasources`: Prometheus datasource config
  - `configs/grafana/dashboards`: Prebuilt Grafana dashboard JSON
- `services/api/migrations/`: Alembic migrations for DB schema
- `data/baselines/`: golden snapshot metrics for M5/M15 regression tests


## Scripts (curated)

**Script taxonomy**
- **Production wrappers**: `build_events_m5.py`, `build_events_m15.py`, `replay_pipeline_to_db.py`
- **Validation & baselines**: `build_baselines.py`, `build_repro_manifest.py`, `validate_*`, `reconcile_db_vs_pipeline.py`, `integrity_audit.py`
- **Guardrail/robustness studies**: `analyze_*` in this list (kept because referenced by docs)
- **Visualization**: `scripts/visualization/*`

**Script → doc mapping (primary reference)**

| Script | Primary Doc Section |
| --- | --- |
| `scripts/build_events_m5.py` | `docs/STRATEGY_MASTER_MANUAL.md` (Event builders) |
| `scripts/build_events_m15.py` | `docs/STRATEGY_MASTER_MANUAL.md` (Event builders) |
| `scripts/build_baselines.py` | `docs/validation.md` |
| `scripts/build_repro_manifest.py` | `docs/validation.md` |
| `scripts/validate_api_vs_pipeline.py` | `docs/validation.md` |
| `scripts/validate_api_predictions_vs_pipeline.py` | `docs/validation.md` |
| `scripts/validate_db_predictions_vs_pipeline.py` | `docs/validation.md` |
| `scripts/replay_pipeline_to_db.py` | `docs/monitoring.md`, `docs/deployment.md` |
| `scripts/export_openapi.py` | `docs/api.md` |
| `scripts/db_backup_restore_smoke.py` | `docs/deployment.md` |
| `scripts/report_m5_guardrail_diagnostics.py` | `docs/STRATEGY_MASTER_MANUAL.md` (Guardrail diagnostics) |
| `scripts/report_mom_guardrail_diagnostics.py` | `docs/STRATEGY_MASTER_MANUAL.md` (Guardrail diagnostics) |
| `scripts/wfo_mom_loss_streak.py` | `docs/analysis/mom_loss_limiter_wfo.md` |
| `scripts/analyze_mom_robustness_suite.py` | `docs/STRATEGY_MASTER_MANUAL.md` (Robustness suite) |
| `scripts/analyze_mom_robustness_suite_m5.py` | `docs/STRATEGY_MASTER_MANUAL.md` (Robustness suite) |
| `scripts/analyze_guardrail_effectiveness.py` | `docs/STRATEGY_MASTER_MANUAL.md` (Guardrail effectiveness) |
| `scripts/analyze_dd_timeweighted.py` | `docs/STRATEGY_MASTER_MANUAL.md` (Integrity checks) |
| `scripts/visualization/plot_guardrail_monthly_and_dd.py` | `docs/STRATEGY_MASTER_MANUAL.md` (Figures) |
| `scripts/visualization/render_pipeline_diagram.py` | `docs/architecture.md` |

**Where to start**
- Build or refresh events: `scripts/build_events_m5.py`, `scripts/build_events_m15.py`
- Validate outputs vs baselines: `scripts/build_baselines.py`, then `uv run pytest -q`
- Replay into DB and verify API alignment: `scripts/replay_pipeline_to_db.py`, `scripts/validate_db_predictions_vs_pipeline.py`

- `scripts/analyze_dd_timeweighted.py`
- `scripts/analyze_execution_latency.py`
- `scripts/analyze_execution_latency_resim.py`
- `scripts/analyze_guardrail_effectiveness.py`
- `scripts/analyze_guardrail_entry_exit_timing.py`
- `scripts/analyze_mom_robustness_suite.py`
- `scripts/analyze_mom_robustness_suite_m5.py`
- `scripts/analyze_outlier_filter_with_guardrail.py`
- `scripts/analyze_pair_stability_filter.py`
- `scripts/analyze_portfolio_constraints.py`
- `scripts/analyze_stress_tests.py`
- `scripts/analyze_tail_risk_guardrail.py`
- `scripts/analyze_tick_bar_consistency.py`
- `scripts/build_all_1m_data.py`
- `scripts/build_baselines.py`
- `scripts/build_events_m15.py`
- `scripts/build_events_m5.py`
- `scripts/build_repro_manifest.py`
- `scripts/compare_timeout_convention.py`
- `scripts/db_backup_restore_smoke.py`
- `scripts/explore_mom_loss_limiter_combos.py`
- `scripts/explore_mom_loss_limiters.py`
- `scripts/export_openapi.py`
- `scripts/integrity_audit.py`
- `scripts/metrics.py`
- `scripts/reconcile_db_vs_pipeline.py`
- `scripts/replay_pipeline_to_db.py`
- `scripts/report_m5_guardrail_diagnostics.py`
- `scripts/report_mom_guardrail_diagnostics.py`
- `scripts/validate_api_predictions_vs_pipeline.py`
- `scripts/validate_api_vs_pipeline.py`
- `scripts/validate_db_predictions_vs_pipeline.py`
- `scripts/wfo_mom_full_params.py`
- `scripts/wfo_mom_full_params_m5.py`
- `scripts/wfo_mom_loss_streak.py`

### Visualization
- `scripts/visualization/plot_guardrail_monthly_and_dd.py`
- `scripts/visualization/plot_monthly_net.py`
- `scripts/visualization/plot_session_risk_spx.py`
- `scripts/visualization/render_pipeline_diagram.py`

## Notes

- The live strategy is rule-based and **does not use ML**.
- Large data artifacts remain in `data/` and are gitignored, except for `data/baselines/`.
