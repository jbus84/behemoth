# Behemoth (OCO Architecture)

**Status**: Production Baseline
**Strategy**: Tick-based ML Opportunity Cost Optimization (OCO)

This repository holds the quantitative research pipeline and active execution artifacts for the Behemoth OCO strategy. The legacy stat-arb systems have been entirely removed.

## 1. Architecture
The codebase operates as a script-orchestrated pipeline generating static, rolling artifacts:
- **Ticks to Features**: Processes tick streams into highly structured ML datasets.
- **Model Training**: WFO orchestration trains and cross-validates tree-based scoring thresholds.
- **Stop-Limit Scenarios**: Offline simulation (S04) ensures predictive edges survive realistic execution latency and exact-tick fill rates.
- **Governance**: Models achieving necessary criteria freeze generating static policy maps (`_oco_live_lock.json` and `_oco_allowed_states.csv`).
- **Docs Contracts**: All strategy changes are gated via programmatic, artifact-driven assertions tracking strategy documentation.

## 2. Quickstart

### Data Pipelines
To onboard and execute the full routine for a symbol:
```bash
python scripts/onboard_symbol.py
```

### Automated Documentation and Reporting
Regenerate all system reference endpoints, diagnostic tables, and validation tests:
```bash
make docs
```

## 3. Operations
For execution details, architecture flows, and the comprehensive "Strategy Bible", please run `make docs` and view the generated MkDocs site using:
```bash
mkdocs serve
```
