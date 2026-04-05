# Stage 14 - JForex Runtime Certification

## Objective
Certify that the Dukascopy JForex adapter reproduces the execution-lifecycle contract after Stage 13 and the local JForex surrogate have already established the prerequisite runtime and parity surface.

## Inputs
- `data/analysis/backtest_reconcile/stage13_dukascopy_testclient_summary.csv`
- `data/analysis/backtest_reconcile/*_jforex_signal_parity_summary.csv`
- `data/analysis/backtest_reconcile/*_jforex_execution_parity_summary.csv`
- `data/analysis/backtest_reconcile/*_jforex_execution_lifecycle_summary.csv`
- `data/analysis/backtest_reconcile/*_jforex_operational_ready_summary.csv`
- `data/analysis/backtest_reconcile/jforex_outcome_parity_summary.csv`
- `data/analysis/backtest_reconcile/local_jforex_surrogate_summary.csv`
- `configs/research/governance/oco_history_dukascopy_candidate/`
- `models/oco_dukascopy_candidate/`
- `docs/analysis/stage14_jforex_runtime_certification_report.md`

## Exact Calculations
- `stage14_jforex_cert_pass` is the conjunction of:
  - `stage13_dukascopy_testclient_pass`
  - `jforex_signal_parity_pass`
  - `jforex_execution_parity_pass`
  - `execution_lifecycle_pass`
  - `operational_ready_pass`
  - `jforex_outcome_parity_pass`
  - `local_jforex_surrogate_pass`
- `THRESHOLD_PARITY_PASS` is emitted as a certification check for the current model/history pair, but it is informational and does not gate `stage14_jforex_cert_pass`.
- Missing inputs are recorded explicitly as `missing input artifact` and count toward `missing_inputs`.

## Causality / Leakage Controls
- Stage 14 only consumes broker/tester summaries written by the JForex adapter or the certification harness.
- Local surrogate outputs are accepted as surrogate evidence only when the source summary marks the symbol as historically non-deployable.
- The execution-lifecycle check is sourced from the adapter runtime summary, not from the OCO research artifacts.

## Failure Modes
- Missing Stage 13, JForex parity, execution lifecycle, operational readiness, outcome parity, or surrogate summaries produce a failed gate with `missing input artifact`.
- A red execution lifecycle summary means the adapter did not emit a complete execution lifecycle for certification.
- If the historical summary marks a symbol as non-deployable, the report surfaces `nogo` for the affected parity checks instead of treating the symbol as deployable.

## Interpretation Guide
- Green means the Stage 13 prerequisite remains green and every Stage 14 gate in the summary is green.
- Red means at least one required input or gate failed and the adapter is not Stage 14 certified.
- Nogo means the symbol is historically non-deployable and should be interpreted as a blocked certification path, not as a green deployable result.

## Validation Gates
- `stage13_dukascopy_testclient_pass`
- `jforex_signal_parity_pass`
- `jforex_execution_parity_pass`
- `execution_lifecycle_pass`
- `operational_ready_pass`
- `jforex_outcome_parity_pass`
- `local_jforex_surrogate_pass`

## Operator Decision Tree
- If a required CSV is missing, regenerate the adapter/runtime artifact that owns that summary.
- If `execution_lifecycle_pass` is red, inspect the JForex execution lifecycle summary and adapter runtime event stream.
- If `operational_ready_pass` is red, inspect the operational step coverage in the adapter runtime.
- If a symbol is `nogo`, treat it as a historical non-deployable case and do not reinterpret it as a deployable green.

## How To Run
```bash
make stage14-jforex-cert
```

## How To Interpret Outputs
- The summary CSV is the certification ledger for each active symbol.
- The checks CSV shows the source path, metric name, severity, and failure detail for each gate.
- The generated report and snapshot are direct renderings of the validator output and should match the CSV state for the same run.

## What To Do If It Fails
- Rebuild the missing adapter/runtime artifact and rerun the certification target.
- Do not use the Stage 14 report as a substitute for the missing source summary.
- Keep the failure interpretation anchored to the current branch state, not to older OCO-language documents.

## Reproduction Commands
```bash
make stage14-jforex-cert
uv run mkdocs build
```

## Process
- Treat Stage 13 as a prerequisite, not a substitute for Stage 14.
- Treat the local parquet-driven JForex surrogate as a prerequisite debug gate before Stage 14 tester/demo certification.
- Do not use `*_local_jforex_*` surrogate summaries as Stage 14 evidence; Stage 14 consumes only real JForex tester/demo artifacts.
- When running the Python API in `historical_auto`, scope the certification surface with `BEHEMOTH_SYMBOLS`.
- Historical Stage 14 replay should use tolerant locked-prediction matching so broker-side timestamp drift does not suppress otherwise valid locked selections.
- Run the Java JForex tester path against the same governed truth window used for certification.
- Treat `ITesterClient` as the official broker-certification harness for Stage 14.
- Confirm the adapter reproduces the execution lifecycle contract:
  - signal, execution, lifecycle, and operational summaries are emitted for the same symbol set,
  - one fill cancels the sibling leg without leaving an inconsistent live-leg state,
  - replay recovery and reconnect paths preserve the same execution-lifecycle result.
- Confirm demo-session readiness separately from tester parity:
  - authentication,
  - subscriptions,
  - account snapshot publication,
  - reservation lifecycle,
  - metrics/logging path from both Python and JForex Prometheus endpoints.

## Hard Gates
- `stage13_dukascopy_testclient_pass=true`
- `jforex_signal_parity_pass=true`
- `jforex_execution_parity_pass=true`
- `execution_lifecycle_pass=true`
- `local_jforex_surrogate_pass=true`
- `operational_ready_pass=true`

Stage 14 passes only when all seven gates are green.

## Failure Interpretation
- If Stage 13 is red, do not trust any JForex tester/demo result.
- If JForex signal parity is red, the adapter is not reproducing research-approved selection timing.
- If JForex execution parity is red, the adapter lifecycle diverges after nominally matched signals.
- If execution lifecycle is red, the adapter cannot safely enforce the runtime lifecycle contract.
- If the local JForex surrogate is red, the shared Java strategy core is not validated before Stage 14 tester/demo certification.
- If operational readiness is red, the adapter is not deployable even if tester parity is green.

## Canonical Command
```bash
make stage14-jforex-cert
```

## Outputs
- `data/analysis/backtest_reconcile/stage14_jforex_runtime_certification_summary.csv`
- `data/analysis/backtest_reconcile/stage14_jforex_runtime_certification_checks.csv`
- `docs/analysis/stage14_jforex_runtime_certification_report.md`
- `docs/strategy_bible/generated/stage_14_snapshot.md`

## Traceability
- `src/jforex/`
- `scripts/validate_stage14_jforex_runtime_certification.py`
- `docs/strategy_bible/stage_13_dukascopy_testclient_parity.md`

### Auto Snapshot - Stage 14
<!-- GENERATED:STAGE_14:START -->
### Auto Snapshot - Stage 14

- generated_at: `pending`
- Stage 14 is a hard gate for the Dukascopy JForex adapter.
- Stage 13 Dukascopy TestClient parity, JForex tester parity, execution lifecycle correctness, local JForex surrogate readiness, and operational readiness must all be green.

#### Key Results
_pending_
<!-- GENERATED:STAGE_14:END -->
