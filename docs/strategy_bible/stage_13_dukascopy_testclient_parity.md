# Stage 13 - Dukascopy TestClient Parity

## Objective
Certify that canonical Dukascopy parquet ticks reproduce Stage 12-approved Python-runtime behavior when replayed through the in-process FastAPI `TestClient`.

## Inputs
- `data/analysis/backtest_reconcile/*_stage12_api_parity_summary.csv`
- `data/analysis/backtest_reconcile/*_dukascopy_testclient_replay_summary.csv`
- `data/analysis/backtest_reconcile/*_jforex_runtime_events.csv`
- `docs/analysis/stage13_dukascopy_testclient_report.md`

## Exact Calculations
- Stage 13 evaluates four booleans per symbol:
  - `stage12_api_parity_pass`
  - `dukascopy_runtime_artifacts_complete_pass`
  - `dukascopy_testclient_signal_parity_pass`
  - `dukascopy_testclient_execution_parity_pass`
- `stage13_dukascopy_testclient_pass` is true only when all four booleans are true for the symbol.
- The Stage 12 prerequisite is an explicit dependency, not a substitute for Dukascopy/TestClient evidence.

## Causality / Leakage Controls
- Dukascopy replay must consume only the canonical historical tick inputs for the certification window.
- Stage 13 does not permit any lookahead from future ticks, future summary rows, or future execution artifacts.
- Local JForex surrogate artifacts are outside the Stage 13 causal boundary. They may exist as diagnostics, but they do not contribute to the Stage 13 result.

## Failure Modes
- `stage12_api_parity_pass=false` means the Python baseline prerequisite is not trusted for that symbol.
- `dukascopy_runtime_artifacts_complete_pass=false` means the current Dukascopy replay runtime-events artifact is missing or empty; the file still uses the legacy `*_jforex_runtime_events.csv` name on disk.
- `dukascopy_testclient_signal_parity_pass=false` means the Dukascopy replay did not reproduce governed signal timing or selection.
- `dukascopy_testclient_execution_parity_pass=false` means the Python runtime diverged after the replayed signal state matched.
- Local JForex surrogate artifacts are not a Stage 13 failure mode. They are not part of the hard-gate decision.

## Interpretation Guide
- Stage 13 is the Dukascopy-source certification gate for the Python decision layer.
- Read the four checks together:
  - Stage 12 red invalidates the prerequisite baseline.
  - Runtime-artifacts red means the certification bundle is incomplete.
  - Signal-parity red means the Dukascopy replay did not reproduce the governed Python selection behavior.
  - Execution-parity red means the Python-managed lifecycle diverged under Dukascopy replay.
- Local JForex surrogate files can help explain a Java-side prerequisite problem, but they do not flip Stage 13 green or red.

## Validation Gates
- `stage12_api_parity_pass=true`
- `dukascopy_runtime_artifacts_complete_pass=true`
- `dukascopy_testclient_signal_parity_pass=true`
- `dukascopy_testclient_execution_parity_pass=true`
- `stage13_dukascopy_testclient_pass=true`
- Stage 13 passes only when all four hard gates are true for the symbol.

## Operator Decision Tree
- If Stage 12 is red, stop and repair the Python baseline before trusting any Dukascopy replay.
- If runtime artifacts are red, regenerate or restore the missing Dukascopy evidence bundle.
- If signal parity is red, inspect replay timing, governed selection, and the Dukascopy/TestClient signal trace.
- If execution parity is red, inspect the lifecycle divergence after the signal trace matched.
- If a local JForex surrogate artifact is missing or red, treat that as a separate diagnostic issue outside the Stage 13 pass/fail decision.

## How To Run
- Run the Stage 13 certification target from the repo root:

```bash
make stage13-dukascopy-cert
```

- To inspect the underlying validator directly, run:

```bash
uv run python scripts/validate_stage13_dukascopy_testclient.py \
  --lock-dir configs/research/governance/oco_history_dukascopy_candidate/2025-07 \
  --stage12-api-parity-summary-glob 'data/analysis/backtest_reconcile/*_stage12_api_parity_summary.csv' \
  --dukascopy-testclient-replay-summary-glob 'data/analysis/backtest_reconcile/*_dukascopy_testclient_replay_summary.csv' \
  --dukascopy-testclient-signal-summary-glob 'data/analysis/backtest_reconcile/*_jforex_signal_parity_summary.csv' \
  --dukascopy-testclient-execution-summary-glob 'data/analysis/backtest_reconcile/*_jforex_execution_parity_summary.csv' \
  --reconcile-dir data/analysis/backtest_reconcile \
  --out-summary-csv data/analysis/backtest_reconcile/stage13_dukascopy_testclient_summary.csv \
  --out-checks-csv data/analysis/backtest_reconcile/stage13_dukascopy_testclient_checks.csv \
  --report-out docs/analysis/stage13_dukascopy_testclient_report.md \
  --snapshot-out docs/strategy_bible/generated/stage_13_snapshot.md
```

## How To Interpret Outputs
- Review the summary CSV for the per-symbol `stage13_dukascopy_testclient_pass` verdict and the four gate columns.
- Review the checks CSV for the exact missing artifact or mismatch that drove each red check.
- Review the report and snapshot to confirm the textual contract matches the validator output.

## What To Do If It Fails
- Do not infer Stage 13 health from local JForex surrogate artifacts.
- Fix the failing prerequisite or evidence family, rerun `make stage13-dukascopy-cert`, and inspect the regenerated Stage 13 outputs.
- Use the checks CSV to localize whether the issue is prerequisite, runtime-artifact completeness, signal parity, or execution parity.

## Reproduction Commands
- Same as `How To Run`. The authoritative Stage 13 entrypoint is `make stage13-dukascopy-cert`, which regenerates the summary, checks, report, and snapshot from the repaired validator.

## Process
- Treat Stage 12 as a prerequisite, not a substitute for Stage 13.
- Treat the local JForex surrogate as a Java-side diagnostic prerequisite, not as a Stage 13 hard-gate input.
- Replay canonical Dukascopy parquet ticks from `/Users/danielfisher/Desktop/dukascopy_ticks`.
- Drive the Python runtime in-process through the FastAPI `TestClient` harness.
- Validate governed signal parity and execution parity on the same certification window used by Stage 12.
- Treat this as the official credential-free broker-source gate before any JForex runtime certification work.

## Hard Gates
- `stage12_api_parity_pass=true`
- `dukascopy_runtime_artifacts_complete_pass=true`
- `dukascopy_testclient_signal_parity_pass=true`
- `dukascopy_testclient_execution_parity_pass=true`

Stage 13 passes only when all four are green.

## Failure Interpretation
- If Stage 12 is red, do not trust any Dukascopy replay result.
- If runtime artifacts are red, the replay bundle is incomplete and Stage 13 is not certifiable.
- If Dukascopy TestClient signal parity is red, broker-source replay is not reproducing governed selection timing.
- If Dukascopy TestClient execution parity is red, the Python runtime diverges after nominally matched signals.
- If a local JForex surrogate artifact is red, treat that as a separate Java-side diagnostic and do not use it to decide Stage 13.

## Canonical Commands
```bash
make dukascopy-testclient-parity \
  SYMBOL=GBPUSD \
  START_TS=2025-07-07T00:00:00Z \
  END_TS=2025-07-09T00:00:00Z

make stage13-dukascopy-cert
```

## Outputs
- `data/analysis/backtest_reconcile/stage13_dukascopy_testclient_summary.csv`
- `data/analysis/backtest_reconcile/stage13_dukascopy_testclient_checks.csv`
- `docs/analysis/stage13_dukascopy_testclient_report.md`
- `docs/strategy_bible/generated/stage_13_snapshot.md`

## Traceability
- `scripts/replay_dukascopy_testclient.py`
- `scripts/validate_stage13_dukascopy_testclient.py`
- `docs/strategy_bible/stage_12_api_parity.md`
