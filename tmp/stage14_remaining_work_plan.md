# Temporary Markdown Plan: Remaining Stage 14 Work

## Summary

Current state:
- Stage 12 is green for all six symbols.
- Local JForex surrogate is green for all six symbols.
- Stage 13 Dukascopy TestClient summary is stale and must be rerun.
- Stage 14 is entirely blocked because the required JForex artifacts do not exist yet.

Goal:
- Produce a decision-complete runbook to finish Stage 14 JForex runtime certification.
- Split every step into `Human` and `LLM` ownership.
- End with a clean, reproducible evidence set for:
  - `stage13_dukascopy_testclient_pass=true`
  - `jforex_signal_parity_pass=true`
  - `jforex_execution_parity_pass=true`
  - `oco_lifecycle_pass=true`
  - `operational_ready_pass=true`

Active symbol universe:
- `EURUSD`
- `GBPUSD`
- `USDJPY`
- `USDCHF`
- `AUDUSD`
- `USDCAD`

## Stage 14 Deliverables

The implementation is complete only when these artifacts exist for every active symbol under `data/analysis/backtest_reconcile/`:
- `*_jforex_signal_parity_summary.csv`
- `*_jforex_execution_parity_summary.csv`
- `*_jforex_oco_lifecycle_summary.csv`
- `*_jforex_operational_ready_summary.csv`

And these stage-level outputs are regenerated:
- `data/analysis/backtest_reconcile/stage14_jforex_runtime_certification_summary.csv`
- `data/analysis/backtest_reconcile/stage14_jforex_runtime_certification_checks.csv`
- `docs/analysis/stage14_jforex_runtime_certification_report.md`
- `docs/strategy_bible/generated/stage_14_snapshot.md`

Prerequisite evidence that must also be current:
- `data/analysis/backtest_reconcile/stage13_dukascopy_testclient_summary.csv`
- `docs/analysis/stage13_dukascopy_testclient_report.md`
- `docs/strategy_bible/generated/stage_13_snapshot.md`

## Human Steps

### 1. Obtain and configure Dukascopy access
- Create or confirm a Dukascopy JForex demo account.
- Capture the exact values for:
  - `BEHEMOTH_JFOREX_JNLP_URI`
  - `BEHEMOTH_JFOREX_USERNAME`
  - `BEHEMOTH_JFOREX_PASSWORD`
  - optional `BEHEMOTH_JFOREX_ACCOUNT_ID`
- Confirm the account has JForex API/tester access and can log in from this machine.
- Confirm the historical tester window to certify first.
  Default:
  - `BEHEMOTH_JFOREX_START_UTC=2025-07-07T00:00:00Z`
  - `BEHEMOTH_JFOREX_END_UTC=2025-07-09T00:00:00Z`

### 2. Provide secure runtime secrets
- Export the Dukascopy credentials into the shell or provide them through a local untracked env file.
- Do not commit any secrets into the repo.
- Reserve ports that will be used during validation:
  - Python API: `8000`
  - JForex metrics: `9464` or symbol-specific alternate ports
  - Prometheus/Grafana if used

### 3. Execute supervised certification
- Be available for the first JForex tester run in case Dukascopy login, account approval, or network/IP prompts appear.
- Review any login/auth errors from the first run and resolve broker-side issues.
- Decide whether to certify all six symbols in one pass or seed with `GBPUSD` first.
  Default:
  - first successful run on `GBPUSD`
  - then widen to all six symbols

### 4. Review final evidence
- Review generated Stage 13 and Stage 14 reports.
- Confirm the final verdict is green before any release decision.
- If the repo is intended for release, decide whether to keep or discard generated docs/site churn before the release commit.

## LLM Steps

### 1. Refresh the prerequisite gates
- Rerun Stage 13 Dukascopy TestClient parity so it matches the current green Stage 12 and local-surrogate state.
- Regenerate:
  - `stage13_dukascopy_testclient_summary.csv`
  - `stage13_dukascopy_testclient_checks.csv`
  - `docs/analysis/stage13_dukascopy_testclient_report.md`
  - `docs/strategy_bible/generated/stage_13_snapshot.md`
- Confirm all six symbols are green before trusting any Stage 14 result.

### 2. Prepare the JForex execution environment
- Start the Python API in the required historical/tester-compatible mode.
- Start observability if used for validation:
  - Prometheus
  - Grafana
  - Java JForex metrics endpoint
- Confirm the Java toolchain is active through `mise`.
- Confirm the JForex adapter still compiles and tests cleanly before runtime execution.

### 3. Run Stage 14 historical tester certification
- For each symbol, run the Java tester path through `ITesterClient` using the governed certification window.
- Use the existing JForex runner and artifact writer path.
- Ensure each tester run emits:
  - signal parity summary
  - execution parity summary
  - OCO lifecycle summary
- Preserve a deterministic `run_id` per symbol/window so outputs are reproducible and traceable.

### 4. Run Stage 14 operational readiness validation
- Run the Java live/demo path against the Dukascopy demo environment.
- Validate:
  - authentication succeeds
  - instrument subscription succeeds
  - Python API requests succeed
  - account snapshot publication succeeds
  - reservation lifecycle succeeds
  - Java metrics endpoint is scrapeable
- Emit `*_jforex_operational_ready_summary.csv` for each symbol or for the covered symbol set, matching the validator’s expected shape.

### 5. Diagnose and fix any Stage 14 failures
- If `jforex_signal_parity_pass` is red:
  - compare tester prediction cadence against Stage 13 truth
  - inspect completed-bar trigger timing
  - inspect symbol subscription and tick batching boundaries
- If `jforex_execution_parity_pass` is red:
  - compare selected predictions to submitted orders
  - compare price/trigger/cap mapping against the OCO planner
  - inspect Python trade sync and deduplication behavior
- If `oco_lifecycle_pass` is red:
  - inspect paired-leg submission
  - inspect sibling cancel fallback
  - inspect partial-fill and reconnect handling
  - inspect stale local state restoration
- If `operational_ready_pass` is red:
  - inspect login/auth
  - inspect metrics server startup
  - inspect account snapshot and reservation endpoints
  - inspect reconnect/idempotency paths
- After each fix, rerun only the smallest affected slice first, then widen again.

### 6. Regenerate the canonical Stage 14 outputs
- Run `make stage14-jforex-cert`.
- Confirm the validator consumes:
  - refreshed Stage 13 summary
  - all four JForex artifact families
- Regenerate:
  - `stage14_jforex_runtime_certification_summary.csv`
  - `stage14_jforex_runtime_certification_checks.csv`
  - `docs/analysis/stage14_jforex_runtime_certification_report.md`
  - `docs/strategy_bible/generated/stage_14_snapshot.md`

### 7. Perform release-hardening only after Stage 14 is green
- Rebuild docs if release evidence must be current.
- Clean or intentionally capture remaining docs/site churn.
- Confirm `git status` is clean before any release tag or release branch cut.

## Commands and Runtime Contract

### Standard environment
Use these defaults unless the human operator overrides them:
- `BEHEMOTH_API_BASE_URI=http://127.0.0.1:8000`
- `BEHEMOTH_JFOREX_INSTRUMENTS=GBPUSD` for first pass
- `BEHEMOTH_JFOREX_START_UTC=2025-07-07T00:00:00Z`
- `BEHEMOTH_JFOREX_END_UTC=2025-07-09T00:00:00Z`
- `BEHEMOTH_JFOREX_REPORT_DIR=data/analysis/backtest_reconcile`
- `BEHEMOTH_JFOREX_RUN_ID=stage14_gbpusd_20250707_20250709`
- `BEHEMOTH_JFOREX_RISK_ENABLED=true`
- `BEHEMOTH_JFOREX_REQUESTED_VOLUME_UNITS=10000`
- `BEHEMOTH_JFOREX_TICK_BATCH_SIZE=256`
- `BEHEMOTH_JFOREX_ORDER_TTL_SECONDS=900`
- `BEHEMOTH_JFOREX_NATIVE_OCO_ENABLED=false`
- `BEHEMOTH_JFOREX_API_TIMEOUT_SECONDS=120`
- `BEHEMOTH_JFOREX_METRICS_ENABLED=true`
- `BEHEMOTH_JFOREX_METRICS_HOST=127.0.0.1`
- `BEHEMOTH_JFOREX_METRICS_PORT=9464`

### Expected execution sequence
1. Start Python API.
2. Start observability stack if operational metrics are part of the run.
3. Refresh Stage 13.
4. Run JForex tester for `GBPUSD`.
5. Validate Stage 14 for `GBPUSD`.
6. Widen to all six symbols.
7. Run JForex demo/live operational readiness checks.
8. Regenerate final Stage 14 summary and report.

## Acceptance Criteria

Stage 14 is complete only when all of the following are true:
- refreshed Stage 13 is green for all six symbols
- all six symbols have the four required JForex artifact families
- `stage14_jforex_runtime_certification_summary.csv` is green for all six symbols
- no symbol shows `missing_inputs > 0`
- `docs/analysis/stage14_jforex_runtime_certification_report.md` reflects the current run, not stale data
- the repo worktree is intentionally clean or intentionally documented before release

## Important Interfaces and Artifacts

No new public API is required for this remaining work. The work should use the existing contract:
- Python API endpoints already used by the Java adapter
- JForex tester and live runners already implemented in `src/jforex/`
- Stage 14 validator:
  - `scripts/validate_stage14_jforex_runtime_certification.py`

The remaining work is operational certification, artifact generation, debugging, and evidence refresh, not a new architecture change.

## Assumptions and Defaults

- Stage 14 remains defined around the real Dukascopy JForex connection.
- `ITesterClient` is the official historical certification harness.
- Dukascopy parquet replay and local surrogate remain prerequisites, not substitutes.
- The first Stage 14 pass should seed on `GBPUSD` before widening to all six symbols.
- Demo credentials are sufficient for Stage 14 operational readiness; live credentials are not required.
- Secrets stay outside the repo.
- This plan is temporary working documentation and should not be treated as canonical repo documentation unless later promoted.
