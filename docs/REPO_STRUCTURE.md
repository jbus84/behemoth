# Repo Structure (Production Baseline)

## Core layout

- `src/behemoth/`: production logic (Kalman, Z-score, features, guardrail, metrics)
- `pipelines/`: deterministic batch runs (event generation + diagnostics)
- `scripts/`: thin wrappers that call pipelines


## Notes

- The live strategy is rule-based and **does not use ML**.
- Data artifacts remain in `data/` and are gitignored.
