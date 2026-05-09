# Live Governance Deviation Analytics Design

## Status

Approved for implementation planning on 2026-05-09.

## Purpose

Build a standalone analytics workflow that explains the magnitude and likely source of recent differences between the Live Runtime and the Governance Runtime.

The workflow answers:

> Over the most recent useful DuckDB-covered window, how far do Live Runtime Tick Bars, predictions, selected signals, and outcomes deviate from the Governance Runtime replay built from canonical Dukascopy Raw Tick Data?

This is not a Promotion gate, restart gate, Stage 13 verdict, or Stage 14 verdict. It may classify observations using the canonical parity language, such as Runtime Variance, Material Drift, and possible Parity Breach, but those classifications are analytics findings only.

## Existing Tooling To Reuse

The implementation should prefer orchestration, small adapters, and function extraction over new parallel diagnostics.

Primary existing inputs and scripts:

- Runtime State DuckDB tables: `raw_ticks`, `tick_bars`, `predict_evaluations`, `audit_logs`, `barrier_scans`, and `trades`.
- `scripts/summarize_runtime_db_run.py` for per-symbol runtime-window sanity summaries.
- `scripts/diagnose_live_audit.py` for Prediction Funnel, score distribution, risk blocking, and trade outcome summaries.
- `scripts/diagnose_live_thresholds.py` for Rolling Threshold investigation when enough live prediction rows exist.
- `scripts/diagnose_live_performance_gap.py` for outcome, Candidate State, and Rolling Threshold integrity checks.
- `scripts/diagnose_live_replay.py` for rebuilding Tick Bars from Raw Tick Data and scoring governed Candidate States.
- `scripts/compare_tick_data_sources.py` for tick-source and bar-distribution comparison helpers.
- `scripts/audit_runtime_parity.py` and `scripts/build_demo_live_offline_comparison_report.py` as reference material only; this workflow is not a parity gate.

If an existing script is close but accepts the wrong input shape, prefer extracting a narrow reusable helper or adding an adapter over copying logic.

## Entry Point

Add one orchestration script:

```bash
uv run python scripts/analyze_live_governance_deviation.py
```

Expected CLI:

```bash
uv run python scripts/analyze_live_governance_deviation.py \
  --runtime-db data/analysis/backtest_reconcile/runtime/live_state.db \
  --tick-root /Users/danielfisher/Desktop/dukascopy_ticks \
  --symbols EURUSD,GBPUSD,USDJPY,USDCHF,AUDUSD,USDCAD \
  --lookback-days 7 \
  --run-id jforex_live \
  --out-dir data/analysis/live_governance_deviation
```

Optional overrides:

- `--start-ts` and `--end-ts` replace automatic recent-window discovery.
- `--api` checkpoints the Live Runtime with `/state/checkpoint` before reading Runtime State.
- `--governance-dir` defaults to `configs/research/governance/oco`.
- `--models-dir` defaults to `models/oco`.

## Window Discovery

The default comparison window is recent completed data coverage, not a calendar month and not necessarily the full live session.

For each symbol, query Runtime State DuckDB:

- `raw_ticks` for latest tick coverage.
- `tick_bars` for latest completed Tick Bar coverage.

The workflow should select the latest interval inside `--lookback-days` that has enough completed Tick Bars to make bar and prediction comparisons meaningful. The implementation plan should set a conservative default minimum bar count and expose it as an option, for example `--min-bars`.

If `--start-ts` and `--end-ts` are supplied, skip discovery and use that explicit interval.

The selected window must be recorded in `run_manifest.json` and `window_summary.csv`, including per-symbol skip reasons.

## Data Flow

### 1. Snapshot Or Open Runtime State

If `--api` is supplied, call `/state/checkpoint` before reading Runtime State. If active DuckDB access is blocked by a lock or WAL state, copy a snapshot into the output directory and read that snapshot. Do not mutate the Live Runtime except for the explicit checkpoint call.

### 2. Extract Live Evidence

For the comparison window, export normalized live evidence per symbol:

- Live Raw Tick Data from `raw_ticks`.
- Live Tick Bars from `tick_bars`.
- Prediction rows from `predict_evaluations` when available, otherwise `audit_logs`.
- Barrier Scans and trades when present.

Live exports should go under the run output directory and should not overwrite Stage or governance artifacts.

### 3. Build Governance Replay Evidence

For the same symbol/window, read canonical Dukascopy Raw Tick Data from `--tick-root`.

Reuse the bar-building and scoring logic from `scripts/diagnose_live_replay.py` where possible. The governance replay should:

- Rebuild Tick Bars from canonical Raw Tick Data.
- Load governed Candidate States from the Promoted Lock Set.
- Load the bound model and threshold artifacts.
- Score the same window for governed Candidate States.
- Emit comparable prediction, threshold, selected-signal, and Candidate State rows.

The first version may support only Candidate States whose `bar_ticks` path is already supported by the reused replay logic, but unsupported states must be written as structured skip rows.

### 4. Compute Deviation Metrics

Compute deviation at four layers:

1. Tick coverage
   - row counts
   - first and last timestamps
   - duplicate timestamp ratio
   - intertick timing distribution
   - spread distribution
   - missing canonical or live tick coverage

2. Tick Bars
   - bar count
   - close timestamp alignment
   - missing and extra bars
   - seconds per bar deltas
   - spread deltas
   - high, low, close deltas
   - largest absolute deviations by symbol

3. Feature, prediction, and signal behavior
   - prediction row count
   - Candidate State coverage
   - `pred_prob` distribution deltas
   - threshold distribution deltas
   - selected signal count deltas
   - near-threshold concentration
   - live source used: `predict_evaluations` or `audit_logs`

4. Runtime outcome context
   - Governance Selected Signal Count
   - Runtime Trade Count
   - Runtime Realized P&L
   - Independent Label P&L where available, clearly labeled as label evidence only
   - Stateful Lifecycle Expected P&L only if already available or cheaply derivable from existing tooling

The report must not imply that Independent Label P&L is the direct target for Runtime Realized P&L.

## Outputs

All machine-readable outputs go under `--out-dir`, preferably with a timestamped run subdirectory unless the user explicitly disables it.

Required outputs:

- `run_manifest.json`
- `window_summary.csv`
- `symbol_skips.csv`
- `tick_coverage_deviation.csv`
- `bar_deviation.csv`
- `signal_deviation.csv`
- `outcome_deviation.csv`
- `findings.csv`
- `live_governance_deviation_report.md`

Optional convenience output:

- Copy or render the Markdown report to `docs/analysis/live_governance_deviation_report.md`.

The report should lead with the magnitude of deviation and the most likely source layer:

- tick coverage
- bar construction
- Rolling Threshold or prediction behavior
- selected signal behavior
- order lifecycle or outcome behavior

## Findings Classification

`findings.csv` should use analytics classifications, not certification verdicts.

Suggested fields:

- `symbol`
- `layer`
- `finding_id`
- `classification`
- `metric_name`
- `metric_value`
- `reference_value`
- `details`
- `source_path`

Allowed `classification` values:

- `info`
- `Runtime Variance`
- `Material Drift`
- `possible Parity Breach`
- `incomplete_evidence`

No finding from this workflow blocks Promotion, restart, Stage 13, or Stage 14.

## Error Handling

- If active DuckDB cannot be opened, try checkpoint/snapshot only when `--api` is supplied; otherwise fail with a clear Runtime State unavailable error.
- If a symbol has no recent live `raw_ticks` or no recent completed `tick_bars`, skip that symbol and write a structured skip row.
- If canonical Dukascopy Raw Tick Data is missing for the inferred window, still write live-side diagnostics and mark governance replay incomplete for that symbol.
- If Governance Locks or model artifacts are missing, still write tick and bar diagnostics and mark signal/outcome sections unavailable.
- If `predict_evaluations` exists and has rows for the run/window, prefer it over `audit_logs`.
- If only `audit_logs` are available, state that score visibility may be admission-only.
- Never overwrite Stage, certification, Promotion, or governance artifacts.

## Testing

Add focused tests rather than broad integration runs:

- Synthetic DuckDB Runtime State tables for window discovery and skip rows.
- Controlled live/governance Tick Bar frames for missing, extra, aligned, and numeric-delta bar cases.
- Output-schema tests for `run_manifest.json`, `window_summary.csv`, `findings.csv`, and the Markdown report.
- CLI smoke test using a temp DuckDB and temp canonical tick root.
- Existing script tests should remain green. If helpers are extracted from existing scripts, preserve or add tests around the extracted behavior.

## Non-Goals

- No changes to Promotion, restart, Stage 13, or Stage 14 gates.
- No new strategy research or Candidate State selection.
- No mutation of canonical Raw Tick Data.
- No rewriting historical governance artifacts.
- No replacement of existing diagnostics where a wrapper or adapter is sufficient.

## Implementation Notes

The likely implementation shape is:

- Keep `scripts/analyze_live_governance_deviation.py` as orchestration.
- Extract small reusable helpers only where existing scripts make direct reuse awkward.
- Use existing canonical vocabulary from `UBIQUITOUS_LANGUAGE.md`.
- Keep all generated analytics under `data/analysis/live_governance_deviation/`.
- Keep the first implementation conservative: produce complete tick/bar diagnostics even when signal replay is unavailable, and make unavailable sections explicit rather than silently empty.
