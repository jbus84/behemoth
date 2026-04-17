# JForex Live vs Python Backtest Parity Assessment

**Date:** 2026-04-17
**Branch:** fix/2026-03-live-promote-and-recert-fixes (and descendants)
**Scope:** AUDUSD + USDCHF + EURUSD for the one-shot replay; all 6 live symbols for the durable harness
**Type:** Hybrid — one-shot gap inventory report + durable parity-contract harness

## Goal

Identify every gap between JForex live/demo-live logic and the Python backtesting logic that will or could cause divergence between backtest and live outcomes, and close the loop with a durable harness that fails Stage 14 certification if known-divergence patterns recur.

"Live" in this spec means both:

1. The JForex demo-live runner (`JForexLiveRunner` against Dukascopy demo).
2. The Stage 14 JForex tester (`JForexTesterRunner` via `ITesterClient`) — same `BehemothStrategyCore`, real Dukascopy ticks, replay-deterministic.

The Stage 14 tester is treated as an authoritative proxy for live evidence because the two paths share the strategy core.

## Background

Python owns features, prediction, governance, the barrier manager, risk sizing, and trade bookkeeping. JForex is intentionally a thin shim: ticks and bar events flow into `BehemothStrategyCore`, which batches ticks to the Python API (`/ticks/batch`), receives bar-completed signals, calls `/predict`, then executes the returned `OPEN_MARKET` / `CLOSE_MARKET` actions through `JForexExecutionPort`.

Existing parity infrastructure:

- Per-session per-symbol CSVs: `*_signal_parity_summary.csv`, `*_execution_parity_summary.csv`, `*_outcome_parity_summary.csv`.
- `scripts/reconcile_jforex_outcomes.py` — month-level outcome reconciliation.
- `scripts/build_demo_live_offline_comparison_report.py` — post-session three-phase comparison.
- `scripts/validate_stage14_jforex_runtime_certification.py` — Stage 14 cert.

The 2026-04-17 demo-live comparison already surfaced a live-only divergence: AUDUSD and USDCHF had zero `/predict` cycles despite 165 and 82 JForex bar events respectively, while EURUSD / GBPUSD / USDCAD / USDJPY passed signal parity. That finding is the motivating example for this spec: static code reading alone did not catch it, and a one-shot report alone would not catch it if it recurs.

## Non-goals

- Not a full refactor of the runtime boundary. Findings become follow-up plans, not inline fixes here.
- Not a replacement for existing parity CSVs or Stage 14 cert. The harness complements them.
- Not a feature-equivalence regression test (probabilities, feature values) beyond what the one-shot replay day proves. Ongoing probability parity is a separate workstream.
- Not a check on the Python pipeline against itself (backtest vs backtest); divergence only means live vs backtest.

## Scope layers

Surfaces are grouped under four in-scope layers plus a named shortlist of failure paths:

| Layer | Example surfaces |
|---|---|
| **Core trading path** | Tick ingestion, bar completion, feature computation, prediction, selection thresholds, barrier touch detection, order submit, fill handling, close |
| **Lifecycle & state** | `client_tick_seq` ordering, reservation IDs, restart recovery, active-OCO state persistence, barrier-manager DB |
| **Risk & governance** | Volume sizing (`requestedVolumeUnits` vs Python `risk/account.py`), governance lock enforcement (model_month pin, run_id plumbing), entry gating (`entriesAllowed`) |
| **Time & data** | Tick timestamp source + tz, bar boundary alignment, bid/ask schema, spread handling, weekend gap skip, DST boundaries |
| **Failure paths (shortlist)** | `tick_batch_599_fallback` (timeout retry → single-tick fallback), `predict_422_warmup` (insufficient warmup bars skip), `submit_rejected` (SUBMIT_REJECTED from broker) |

Out of scope for this cycle: FILL_REJECTED, CLOSE_REJECTED, CHANGE_REJECTED, Python API unreachable recovery, general broker reconnect. These will be inventoried as `layer = failure` surfaces with `fix_owner = future` where observed.

## Deliverables

Two artifacts in one spec cycle:

1. **Gap inventory report** — `docs/analysis/2026-04-17-jforex-python-parity-assessment.md`
2. **Durable parity-contract harness** — `scripts/audit_runtime_parity.py` + supporting module `src/behemoth/parity/checks/`

## Inventory report structure

The report is a flat list of **divergence surfaces**, grouped by layer. Each surface is the unit of analysis and also the unit the harness's checks map to.

Per-surface fields:

| Field | Purpose |
|---|---|
| `surface_id` | Stable identifier (`core.bar_boundary_alignment`, `failure.tick_batch_599_fallback`). Used by the harness to reference checks. |
| `layer` | `core` / `lifecycle` / `risk_gov` / `time_data` / `failure` |
| `python_locus` | `file:line-range` where the Python side defines behavior |
| `jforex_locus` | `file:line-range` where JForex defines behavior |
| `contract` | Plain-English statement of what both sides must agree on |
| `observed_state` | What the static audit + replay diff actually found |
| `divergence` | `none` / `latent` (code diverges but not yet observed) / `observed` (replay produced a measurable diff) / `runtime_only` (only appears in demo-live, not backtest) |
| `severity` | `critical` / `high` / `medium` / `low` |
| `evidence` | Links to replay diff artifacts, existing parity CSVs, or logged events |
| `harness_check` | `yes` / `no` — and if yes, the check's name |
| `fix_owner` | `this_spec` (follow-up plan) / `future` (noted, deferred) / `wontfix` (accepted divergence with rationale) |

Document layout:

1. Executive summary (severity tally per layer + top 5 findings)
2. Methodology (what was read, what was replayed, what tolerances)
3. Per-layer surface sections (one table + narrative per surface, critical/high first)
4. Harness coverage matrix (`surface_id` → check name; gaps deliberately not monitored, with rationale)
5. Appendix: replay diff artifacts index

Framing principles:

- **`surface_id` is the spine.** The same id appears in the report, in the harness check registry, and in any follow-up plan. That is how findings survive the transition from one-shot doc to durable harness.
- **"No divergence" surfaces are still listed.** If a surface was audited and found clean, it is recorded so the next audit cycle does not re-derive it.

## Severity scheme

Applies to both the inventory and the harness:

| Level | Definition | Action |
|---|---|---|
| `critical` | Incorrect trade placed, missed trade, or governance lock violated. Backtest and live diverge on *what* gets executed. | Fail Stage 14 cert. Block live launch. |
| `high` | Correct decisions but outcome drift beyond the per-symbol tolerance from the inventory. | Fail cert; require an explanation + remediation plan. |
| `medium` | Observability / reporting drift. Same decisions, same outcomes, but artifacts disagree. | Warn; do not fail cert. Escalate on repeat. |
| `low` | Cosmetic or docstring-level. | Inventory only; no harness check. |

The seed harness check set is scoped to `critical` and `high`.

## Replay methodology (one-shot evidence for the inventory)

One replay day, two sides, one diff.

**Replay day:** 2026-04-15 (Wednesday). Recent, weekday, not month boundary, not DST transition, within the currently governance-locked month. Pinned in the spec for reproducibility.

**Flexibility clause:** Replay day, Side B reference, per-symbol tolerances, and diff column set are the planned starting point. The implementation plan may substitute any of them with recorded rationale — e.g. swap the date if tick coverage is incomplete, swap the Stage 6 verifier for the Stage 4 stop-limit tickfill script if the former does not expose needed intermediates, tighten/loosen tolerances once diff distributions are observed. Substitutions go in the implementation plan's "Deviations" log.

**Side A — JForex tester (live proxy):**

- Runner: `JForexTesterRunner` via `make stage14-jforex-cert`, narrowed to 2026-04-15 + {AUDUSD, USDCHF, EURUSD}.
- Drives `BehemothStrategyCore` with real Dukascopy ticks via `ITesterClient`.
- Python API server running against the governance-locked model month.
- Captured artifacts: `stage14_*_runtime_events.csv`, per-symbol signal/execution/outcome parity CSVs, `live_state.db` post-run snapshot, HTTP request log from the API server, `active_oco_state.json`.

**Side B — Python offline reference:**

- Runner: `scripts/verify_oco_tick_exact_shortlist.py` for the same day + symbols + locked model month.
- Same Dukascopy tick parquets as Side A.
- Captured artifacts: tick-exact predictions parquet, expected barrier-touch table, expected fill bid/ask, expected outcomes.

**Diff harness (one-shot, appendix evidence — not the durable harness):**

Join Side A and Side B per symbol on `(symbol, bar_close_ts)` and emit a single `parity_replay_diff.parquet` with one row per bar-event.

| Column | A-value | B-value | Diff rule |
|---|---|---|---|
| `bar_closed` | HTTP predict trigger | verifier tick-idx | boolean equality |
| `bar_close_tick_idx` | tick batch seq | verifier tick idx | exact |
| `feature_vector_hash` | `/predict` request body | verifier feature build | exact |
| `pred_prob` | `/predict` response | verifier | ≤1e-6 absolute |
| `selected_exec` | response | verifier | exact |
| `barrier_scan_registered` | `live_state.db` | verifier scan table | exact on `scan_id` equivalent |
| `touch_side` | barrier_manager action | verifier touch detection | exact |
| `fill_price` | `OrderEvent.openPrice` | tick-exact expected fill | ≤1 pip, symbol-aware |
| `gross_pips_outcome` | close event | verifier outcome | ≤2 pips |

Rows beyond tolerance become evidence for a surface in the inventory. Clean rows become positive evidence — the surface is recorded as verified in parity on this day.

**Replay diff error handling:**

- Missing Side B tick coverage for a symbol on the chosen day → fall back to the next available weekday for that symbol only; record in methodology.
- Legitimate demo-live-only gap (e.g. broker SUBMIT_REJECTED) → record as `divergence = runtime_only` in the inventory, not as a symbol failure.
- Governance lock hash differs between Side A and Side B → drop the row from the diff; surface as a standalone `critical` `risk_gov.governance_lock_pin` finding.

The resulting diff parquet is checked into `data/analysis/backtest_reconcile/replay_diff/2026-04-15/` for reproducibility.

## Durable harness (`scripts/audit_runtime_parity.py`)

Per-run pass/fail across the top-N surfaces the inventory names. One script, one CSV + one markdown output, no persistent state of its own.

**Inputs:**

- `--run-id` (e.g. `jforex_live` or a Stage 14 run_id)
- `--db data/analysis/backtest_reconcile/runtime/live_state.db` (opened read-only)
- `--report-dir data/analysis/backtest_reconcile/` (existing parity CSVs)
- `--model-month 2026-04` (governance lock pin to verify against)
- `--out-report docs/analysis/runtime_parity_audit/<run_id>_<timestamp>.md`
- `--out-csv <same_dir>/<run_id>_<timestamp>_surface_findings.csv`

**Check registry (`src/behemoth/parity/checks/`):**

Each surface in the inventory with `harness_check = yes` has a check function:

```python
@register_check(surface_id="core.predict_cycles_per_bar", severity="critical")
def check_predict_cycles_match_bar_events(ctx: CheckContext) -> CheckResult: ...
```

`CheckContext` carries the run inputs + loaded DataFrames of the existing parity CSVs + a read-only `live_state.db` handle + the governance lock for the pinned month. `CheckResult` is `{pass, severity, observed, expected, evidence}`. Checks never write. Tolerances live on the check; changing one is a code change + commit, captured in the Stage 14 lock.

**Seed check set (`critical` / `high` only):**

1. `core.predict_cycles_per_bar` — predict cycles per symbol ≥ bar events (catches the AUDUSD/USDCHF zero-predict pattern).
2. `risk_gov.governance_lock_pin` — run's model_month matches the governance-locked month and the locked hash matches.
3. `core.tick_seq_monotonic` — `client_tick_seq` per symbol is strictly monotonic, no gaps.
4. `lifecycle.active_oco_reconciled` — every `active_oco_state.json` entry has a matching row in `live_state.db` and in `barrier_scans`.
5. `failure.tick_batch_599_fallback_consistency` — every 599-retry tick fell through single-tick fallback and shows a matching accepted count.
6. `failure.predict_422_warmup_only` — every predict failure is classified as warmup, not an unclassified error.
7. `core.entries_allowed_vs_readiness` — every `entry_blocked_not_ready` event correlates with a `LiveReadinessState` at the same tick that was not `READY`.
8. `time_data.bar_close_ts_sorted_per_symbol` — bar close timestamps are weakly monotonic per symbol within a session.

The seed set is additive. New checks land when the inventory names a surface with `harness_check = yes`. Checks are never removed silently; removal requires a recorded rationale in the registry file.

**Outputs:**

- Markdown report: one row per check, pass/fail + evidence snippet.
- CSV: machine-readable for downstream dashboards.
- Non-zero exit code on any `critical` failure.

**Error handling:**

- Missing input (CSV absent, `live_state.db` locked) → `INPUT_MISSING` exit; never emit a false pass.
- Check crash (unexpected schema, duckdb error) → that check returns `ERROR` with traceback in evidence; other checks continue; overall exit non-zero.
- Unknown / orphan `surface_id` in the registry → startup failure, loud, not a silent no-op at runtime.
- `live_state.db` is always opened read-only so the harness runs concurrently with live sessions without contention.

**What this is deliberately NOT:**

- Not a full replay harness (that is the one-shot Section 2 diff).
- Not a feature / prediction / probability check (those need Side B; the harness only inspects what was produced on Side A against locked invariants).
- Not a source of truth (the parity CSVs and `live_state.db` are).

## CI and ops wiring

- Added to `make stage14-jforex-cert` — a `critical` failure blocks cert.
- Added to the demo-live session wrap-up via `scripts/build_demo_live_offline_comparison_report.py`'s Phase 3 stage.
- Output directory: `docs/analysis/runtime_parity_audit/`. Retention policy for the timestamped per-run files is deferred to the implementation plan (see Open Questions).

## Testing

- **Unit tests per check** under `tests/parity/checks/`. Two tests per check minimum: a known-good fixture and a known-bad fixture. The seed check `core.predict_cycles_per_bar` must fail on the 2026-04-17 AUDUSD evidence and pass on the EURUSD evidence from the same session — this closes the motivating-example loop.
- **Harness smoke test** `tests/test_audit_runtime_parity.py` — runs the script against a fixture run and asserts output artifacts, schema, and exit code.
- **Replay diff one-shot** — not unit-tested (evidence, not a standing surface). The diff parquet is checked into `data/analysis/backtest_reconcile/replay_diff/2026-04-15/` for reproducibility.
- **Inventory coverage test** `tests/test_parity_audit_inventory.py` — asserts every `surface_id` with `harness_check = yes` in the inventory markdown has a registered check in code and vice versa. Prevents drift between the doc and the harness.

## Success criteria

1. Inventory report published at `docs/analysis/2026-04-17-jforex-python-parity-assessment.md` covering all four in-scope layers + the three shortlisted failure paths across AUDUSD, USDCHF, EURUSD.
2. Every surface in the inventory has a `surface_id`, a severity, and a `harness_check` disposition with rationale.
3. The AUDUSD/USDCHF zero-predict divergence from 2026-04-17 appears in the inventory as a `critical` / `observed` surface backed by a registered harness check that fails on the 2026-04-17 evidence and passes on a clean run.
4. `scripts/audit_runtime_parity.py` runs under `make stage14-jforex-cert` and in the demo-live wrap-up with non-zero exit on `critical` failures.
5. `tests/test_parity_audit_inventory.py` passes — inventory and registry are in sync.
6. Replay diff parquet for 2026-04-15 across the three symbols is produced and linked from the inventory appendix.

## Open questions deferred to the implementation plan

- Exact tolerance values per symbol for `pred_prob` and `fill_price` (seeded from Section 2 values, refined once the 2026-04-15 diff distribution is observed).
- Whether the harness CSV should include timing metrics per check (useful for performance tracking; not required for correctness).
- Whether `docs/analysis/runtime_parity_audit/` timestamped outputs should be kept, truncated to last N runs, or rotated by session.

These do not block brainstorming completion.
