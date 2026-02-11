# Repo Structure (Production Baseline)

## Core layout

- `src/behemoth/`: production logic (Kalman, Z-score, features, guardrail, metrics)
- `pipelines/`: deterministic batch runs (event generation + diagnostics)
- `scripts/`: thin wrappers that call pipelines
- `services/api/`: FastAPI position + order state service
- `docs/`: documentation (MkDocs site uses these markdown files)
- `mkdocs.yml`: MkDocs configuration
- `configs/`: YAML config for API and pair weights
- `configs/prometheus.yml`: Prometheus scrape config
- `configs/grafana/`: Grafana provisioning
- `services/api/migrations/`: Alembic migrations for DB schema
- `scripts/export_openapi.py`: generate OpenAPI spec for docs
- `data/baselines/`: golden snapshot metrics for M5/M15 regression tests


## Notes

- The live strategy is rule-based and **does not use ML**.
- Large data artifacts remain in `data/` and are gitignored, except for `data/baselines/`.
