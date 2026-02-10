# Repo Structure (Production Baseline)

## Core layout

- `src/behemoth/`: production logic (Kalman, Z-score, features, guardrail, metrics)
- `pipelines/`: deterministic batch runs (event generation + diagnostics)
- `scripts/`: thin wrappers that call pipelines
- `services/api/`: FastAPI position + order state service
- `docs/`: documentation (MkDocs site uses these markdown files)
- `mkdocs.yml`: MkDocs configuration
- `configs/`: YAML config for API and pair weights


## Notes

- The live strategy is rule-based and **does not use ML**.
- Data artifacts remain in `data/` and are gitignored.
