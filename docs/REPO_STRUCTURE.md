# Repo Structure (Production Baseline)

## Core layout

- `src/behemoth/`: production logic (Kalman, Z-score, features, guardrail, metrics)
- `pipelines/`: deterministic batch runs (event generation + diagnostics)
- `scripts/`: thin wrappers that call pipelines
- `services/api/`: FastAPI position + order state service
- `docs/`: documentation (MkDocs site uses these markdown files)
- `mkdocs.yml`: MkDocs configuration
- `configs/`: YAML config for API and pair weights
- `services/api/migrations/`: Alembic migrations for DB schema
- `scripts/export_openapi.py`: generate OpenAPI spec for docs


## Notes

- The live strategy is rule-based and **does not use ML**.
- Data artifacts remain in `data/` and are gitignored.
