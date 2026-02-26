# OCO Live Governance Lock

## Purpose
- Freeze the exact OCO state universe and runtime config used for live deployment.
- Prevent accidental drift from re-mining/reselection.
- Enforce scheduled retrain windows.

## Artifacts
- `configs/research/governance/oco/eurusd_oco_live_lock.json`
- `configs/research/governance/oco/eurusd_oco_allowed_states.csv`
- `configs/research/governance/oco/gbpusd_oco_live_lock.json`
- `configs/research/governance/oco/gbpusd_oco_allowed_states.csv`
- policy: `configs/research/governance/oco_live_policy.yaml`

## Freeze Command
```bash
python scripts/freeze_oco_live_governance.py \
  --symbols EURUSD,GBPUSD \
  --out-dir configs/research/governance/oco
```

## Validate Command (Deploy)
```bash
python scripts/validate_oco_live_governance.py \
  --lock-path configs/research/governance/oco/eurusd_oco_live_lock.json \
  --mode deploy \
  --state-csv data/analysis/tick_opportunity_mining/reduced_core/EURUSD_oco_reduced_states.csv \
  --wfo-config configs/research/experiments/eurusd_tick_opportunity_monthly_wfo_oco_fullcap_2025.yaml \
  --reduced-config configs/research/experiments/eurusd_oco_reduced_core_2025.yaml \
  --data-reliability-checks-csv data/analysis/tick_opportunity_mining/data_reliability_checks.csv \
  --leakage-checks-csv data/analysis/tick_opportunity_mining/oco_leakage_integrity_checks.csv \
  --execution-risk-checks-csv data/analysis/tick_opportunity_mining/oco_execution_risk_checks.csv
```

## Validate Command (Retrain Window)
```bash
python scripts/validate_oco_live_governance.py \
  --lock-path configs/research/governance/oco/eurusd_oco_live_lock.json \
  --mode retrain \
  --as-of 2026-03-27
```

## Current Cadence
- policy mode: `calendar_window`
- cadence: `30` days
- retrain window: `due +/- 3 days`
