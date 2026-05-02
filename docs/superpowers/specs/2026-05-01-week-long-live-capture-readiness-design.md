# Week-long live capture — readiness plan

**Date:** 2026-05-01
**Status:** Design

## Goal

Run the live JForex strategy for one week, capture broker ticks + API `raw_ticks` + Dukascopy parquet, then on Friday produce a single end-of-week verdict on whether the live runtime's selected actions are consistent with offline reconstructed replay. The verdict feeds the diagnostic decision tree in `data/analysis/backtest_reconcile/live_data_audit_2026-05-01.md`.

## Scope

This is a readiness plan for the capture, not a redesign of the runtime or the comparison pipeline. The infrastructure already exists. What this spec defines is the minimum set of pre-flight, daily, and end-of-week steps that ensure Friday's analysis is reproducible and not blocked by avoidable failures.

## Operating mode

Three explicit choices that constrain everything else:

- **Single end-of-week verdict.** No daily comparison reports. Analysis runs once on Friday over the full week's snapshot.
- **Manual terminal launch.** No persistence wrapper, no auto-restart, no daemon. The runtime is whatever a `python scripts/run_jforex_live.py` invocation produces in a foreground terminal.
- **Best-effort uptime.** If the runtime dies mid-week, restart it, accept the gap, continue. A lost day is not a reset; only a model/config change is a reset.

## Pre-flight checklist (before pressing go)

### 1. Commit the comparison scripts on a branch and PR them

The two comparison scripts are currently in the working tree and uncommitted:

- `scripts/compare_live_broker_ticks.py`
- `scripts/diagnose_live_replay_parity.py`
- `tests/test_compare_live_broker_ticks.py`
- `tests/test_diagnose_live_replay_parity.py`

Commit and PR these onto a branch tonight. The merge SHA becomes the **locked reference** for Friday's analysis. If anyone edits these files in another worktree during the week, the locked SHA still has the smoke-tested version.

### 2. Pin and record the live config (at week-start, after new model is deployed)

Once the retrain finishes and the new model is deployed in the live runtime, write a manifest alongside the captured data before pressing go:

- Path: `data/analysis/backtest_reconcile/run_manifest_<YYYY-MM-DD>.md`
- Contents:
  - Git SHA at week-start (the locked-comparison-scripts commit)
  - New model month, model artifact path, file content hash
  - Threshold config path + content hash
  - Strategy version (JForex)
  - Symbol list
  - Start timestamp (UTC)

The manifest is the "what was actually running" record. Friday's replay reads it to load the same model and threshold artifacts.

### 3. Smoke-test the comparison pipeline

Two parts, because the new model is not yet available:

- **Tonight:** Run `compare_live_broker_ticks.py` against today's captured data (broker CSVs, `live_state.db`, Dukascopy parquet). Confirm it produces a non-empty markdown report with sane numbers. This is model-independent — no new artifacts required.
- **After new model deploys, before week-start:** Run `diagnose_live_replay_parity.py` against a short test window (e.g. one hour of live capture once the new model is running). Confirm it loads the new model, generates predicts, and writes its report. If it errors, fix before pressing go.

If either smoke test errors, fix tonight (or pre-week-start) — not Friday.

## During the week

Each morning, ~30 seconds:

1. **Process alive.** `ps` or glance at the terminal where the runtime is running.
2. **Files growing.** `ls -lah data/analysis/backtest_reconcile/*_jforex_broker_ticks.csv` — mtime within the last few minutes during market hours, file size larger than yesterday.
3. **Disk free.** `df -h ~`. Headroom check, not a precise budget. Throughput is ~50MB/day broker CSVs + ~25MB/day DB.

If the process died: restart it, append a `## Gap` section to the manifest recording the down window (last-known-alive timestamp → restart timestamp, in UTC), continue. Do not backfill, do not merge fragments.

Things to avoid mid-week:
- Editing the locked comparison scripts.
- Changing the model, threshold config, or strategy version. Any of these resets the week.
- Running `download_tick_vault_data.py`. It won't revise existing data (drops duplicates by timestamp, keeping the existing row), but skipping it mid-week removes a variable from Friday's analysis.

## End-of-week analysis (Friday)

1. **Snapshot, don't stop.** Copy `live_state.db` (with `.wal` and `.shm`) and the broker CSVs to a dated read-only folder: `data/analysis/backtest_reconcile/week_<start>_<end>/`. The runtime can keep running.

2. **Check out the locked commit.** Use the SHA from the manifest. This guarantees the comparison scripts are the version smoke-tested at the start.

3. **Run `compare_live_broker_ticks.py`** over the snapshot. Inputs: snapshot broker CSV directory, snapshot DB, Dukascopy parquet root. Output: a markdown report covering Comparison 1 (Java→Python bit-exact check) and Comparison 2 (broker feed vs historical archive) for the full week.

4. **Run `diagnose_live_replay_parity.py`** over the snapshot, using the model and threshold artifacts recorded in the manifest. Output: per-candidate selected-action match rate vs reconstructed replay (Comparison 3).

5. **Write the verdict** against the decision tree:
   - If Comparison 1 deviates from bit-exact: Live Runtime bridge regression — investigate.
   - If Comparisons 1+2 hold and `selected_exec` parity is high: Live Runtime is consistent with itself; live P&L gaps are sample noise.
   - If `selected_exec` parity is low: stage analyses' tolerance is too loose; tick-source / phase-sensitivity gap is real.

   The verdict report sits next to the snapshot folder, dated.

## Out of scope / accepted risks

Explicitly not doing:

- No persistence wrapper (tmux / launchd / systemd).
- No heartbeat or alerting.
- No daily checkpoint reports.
- No daily parquet snapshot — single Friday snapshot is sufficient because `download_tick_vault_data.py` is append-and-fill-only and never revises existing tick values (`download_tick_vault_data.py:303-305` drops duplicates by timestamp, keeping the existing row).
- No structured run logging beyond the manifest. Forensics from file mtimes + DB queries if needed.
- No trade reconciliation against broker statements. The `trades` table is authoritative for this exercise.

Accepted failure modes — week is still usable:

- Process dies → restart, note gap in manifest, continue.
- Broker CSV has a partial last line from a crash → reads as one short row, immaterial.
- Verdict is "not enough trades to conclude" → run another week.

Week resets if:

- Model swap, threshold config change, or strategy version bump during the week.
- Comparison scripts get edited on the locked branch.

## Files referenced

- Comparison scripts: `scripts/compare_live_broker_ticks.py`, `scripts/diagnose_live_replay_parity.py`
- Live state: `data/analysis/backtest_reconcile/runtime/live_state.db` (DuckDB)
- Broker CSVs: `data/analysis/backtest_reconcile/<SYMBOL>_jforex_broker_ticks.csv`
- Dukascopy parquet: `/Users/danielfisher/Desktop/dukascopy_ticks/<SYMBOL>/<SYMBOL>_<YYYYMM>_ticks.parquet`
- Audit doc (decision tree): `data/analysis/backtest_reconcile/live_data_audit_2026-05-01.md`
- Broker tick writer (Java): `src/jforex/src/main/java/com/behemoth/jforex/reporting/Stage14ArtifactWriter.java:142`
