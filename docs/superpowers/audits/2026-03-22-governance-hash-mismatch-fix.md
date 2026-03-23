# Governance Hash Mismatch Fix — Evidence Log

## Environment
- Branch: main
- Commit: 403c9e6
- Date (UTC): 2026-03-23T11:01:23Z

## Pre-flight: Hash Mismatch Confirmation
- Validate command: `UV_CACHE_DIR=.uv_cache uv run python scripts/validate_oco_live_governance.py --lock-path configs/research/governance/oco/eurusd_oco_live_lock.json --mode deploy --wfo-config configs/research/experiments/eurusd_tick_opportunity_monthly_wfo_oco_fullcap_2025.yaml --reduced-config configs/research/experiments/eurusd_oco_reduced_core_2025.yaml --data-reliability-checks-csv data/analysis/tick_opportunity_mining/data_reliability_checks.csv --leakage-checks-csv data/analysis/tick_opportunity_mining/oco_leakage_integrity_checks.csv --execution-risk-checks-csv data/analysis/tick_opportunity_mining/oco_execution_risk_checks.csv`
- Exit code: 2
- Symbols with mismatch: EURUSD (confirmed; all six symbols expected to match — only EURUSD validated pre-flight per task scope)
- Failed checks:
  - `reduced_states_hash`: FAIL
  - `predictions_hash`: FAIL
  - `model_cbm_hash`: FAIL — expected=9ddbfbdbf0dd99071b460e3f8b2bdfaafbfbd8ef35854cfe6cf1cc2c2def4543 got=a95e12548194ec3dcef61d57478a6dbec009918ffe1e23be716b3cb0d5724dc8
  - `model_threshold_json_hash`: FAIL — expected=d991f45bb5eef34143ca0abec2c5bae9540ae16664c151d810cbd3e7e02b7314 got=2f86bcbd338d6342a254cecac7f7e36a30f78f54b9c3a6c9127da3ced3a3f00f
  - `tick_exact_summary_hash`: FAIL
  - `reduced_summary_hash`: FAIL
  - `state_universe_exact_match`: FAIL (missing=1, extra=1)

## Worktree State Before Freeze
- git status (short):
  ```
   M data/analysis/backtest_reconcile/AUDUSD_local_jforex_outcome_parity_summary.csv
   M data/analysis/backtest_reconcile/EURUSD_local_jforex_outcome_parity_summary.csv
   M data/analysis/backtest_reconcile/GBPUSD_local_jforex_outcome_parity_summary.csv
   M data/analysis/backtest_reconcile/USDCAD_local_jforex_outcome_parity_summary.csv
   M data/analysis/backtest_reconcile/USDCHF_local_jforex_outcome_parity_summary.csv
   M data/analysis/backtest_reconcile/USDJPY_local_jforex_outcome_parity_summary.csv
   M data/analysis/backtest_reconcile/jforex_outcome_parity_summary.csv
   M tick_vault_data/logs.log
  ?? docs/superpowers/plans/2026-03-17-jforex-outcome-parity.md
  ?? docs/superpowers/plans/2026-03-18-diagnose-gbpusd-predict-slowdown.md
  ?? docs/superpowers/plans/2026-03-18-fix-spotlight-parity-coverage.md
  ?? docs/superpowers/plans/2026-03-18-spotlight-coverage-fix.md
  ?? docs/superpowers/plans/2026-03-18-stage14-full-outcome-reconciliation.md
  ?? docs/superpowers/plans/2026-03-18-state-bar-cache.md
  ?? docs/superpowers/plans/2026-03-19-jforex-production-readiness.md
  ?? docs/superpowers/plans/2026-03-19-stage14-completion.md
  ?? docs/superpowers/plans/2026-03-20-doc-first-docs-update.md
  ?? docs/superpowers/plans/2026-03-20-documentation-enhancement-roadmap.md
  ?? docs/superpowers/plans/2026-03-20-full-documentation-audit.md
  ?? docs/superpowers/plans/2026-03-20-jforex-tester-shutdown-fix.md
  ?? docs/superpowers/plans/2026-03-21-monthly-recert-manual-verification.md
  ?? docs/superpowers/plans/2026-03-22-dukascopy-paper-trading-readiness.md
  ?? docs/superpowers/plans/2026-03-22-governance-hash-mismatch-fix.md
  ?? docs/superpowers/specs/2026-03-20-doc-first-docs-update-design.md
  ?? docs/superpowers/specs/2026-03-20-documentation-enhancement-roadmap-design.md
  ?? docs/superpowers/specs/2026-03-20-full-documentation-audit-design.md
  ```
- Pending files committed in prep-commit:
  - Commit 1b0adac: "chore: record demo rerun artefacts and JForex session config from 403c9e6 validation"
    - 7 backtest_reconcile CSVs (AUDUSD, EURUSD, GBPUSD, USDCAD, USDCHF, USDJPY, jforex_outcome_parity_summary)
    - tick_vault_data/logs.log
  - Commit f118ff9: "chore: add plan, spec and audit documents"
    - 15 plan files under docs/superpowers/plans/
    - 3 spec files under docs/superpowers/specs/
    - 1 audit file docs/superpowers/audits/2026-03-22-governance-hash-mismatch-fix.md
  - Note: src/jforex/src/main/java/com/behemoth/jforex/config/JForexSessionConfig.java was NOT modified (not in git status output)
  - Note: src/jforex/src/test/ untracked files were NOT present

## freeze-oco Result
- Command:
- Exit code:
- API parity: pass/fail per symbol
- Audit result:

## Post-freeze: Lock Validation
- Symbols validated:
- All pass?:

## /predict Smoke Test
- API start command:
- Per-symbol results (symbol → HTTP status):
- All 200?:

## Outstanding Issues
- EURUSD BRIDGING status:
- Other:

## Final Outcome
- Status:
- Commit:
