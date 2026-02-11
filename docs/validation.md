# Validation & Testing

This project includes reproducibility, causality, and API alignment checks.

## Reproducibility
- `scripts/build_repro_manifest.py` → `data/analysis/repro_manifest.json`

## API vs Pipeline Alignment
- `scripts/validate_api_vs_pipeline.py`
- `scripts/validate_api_predictions_vs_pipeline.py`
- `scripts/validate_db_predictions_vs_pipeline.py`

## Baseline Snapshots (M5/M15)
- `scripts/build_baselines.py` → `data/baselines/baseline_m5.json`, `data/baselines/baseline_m15.json`
- `tests/test_baseline_snapshots.py`

## Guardrail Causality
- `tests/test_guardrail_semantics.py`
- `tests/test_guardrail_ordering.py`
- `tests/test_guardrail_deep_dive.py`

## Hard Gates
- `tests/test_hard_gates.py`
- `tests/test_api_risk_controls.py`

## Visual Diagnostics
Charts in `docs/figures` and summary CSVs in `data/analysis/*`.
