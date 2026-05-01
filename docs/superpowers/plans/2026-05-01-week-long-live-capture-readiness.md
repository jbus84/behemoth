# Week-long live capture — readiness implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the broker-tick capture changes + comparison scripts on a feature branch, open a PR, smoke-test the model-independent comparison on today's data, and lay down a manifest template — so the week-long live capture can start cleanly once the new model is deployed.

**Architecture:** No new code beyond a markdown manifest template. The comparison scripts (`scripts/compare_live_broker_ticks.py`, `scripts/diagnose_live_replay_parity.py`) and their tests already exist as untracked files. The Java/Python broker-tick capture changes already exist as uncommitted modifications. This plan bundles them into one coherent PR, validates the pipeline end-to-end on today's data, and prepares the manifest format the operator will fill in at week-start.

**Tech Stack:** git + git worktrees, GitHub CLI (`gh`), DuckDB CLI / Python `duckdb` library, pytest, the existing comparison scripts.

**Spec:** [`docs/superpowers/specs/2026-05-01-week-long-live-capture-readiness-design.md`](../specs/2026-05-01-week-long-live-capture-readiness-design.md)

---

## File Structure

| Path | Status | Responsibility |
|---|---|---|
| `scripts/compare_live_broker_ticks.py` | Existing untracked | Comparison script — broker CSV vs Dukascopy parquet, optional vs API DB |
| `scripts/diagnose_live_replay_parity.py` | Existing untracked | Decision-parity replay vs reconstructed Dukascopy bars (needs trained model) |
| `tests/test_compare_live_broker_ticks.py` | Existing untracked | Unit tests for the broker-vs-archive comparison |
| `tests/test_diagnose_live_replay_parity.py` | Existing untracked | Unit tests for the decision-parity replay |
| `scripts/run_jforex_live.py` | Existing modified | Wires the `record_broker_ticks` flag into the JForex subprocess |
| `src/behemoth/api/server.py` | Existing modified | API surface tweaks for tick recording |
| `src/jforex/src/main/java/com/behemoth/jforex/...` | Existing modified | `recordBrokerTick` writer + JForex strategy + config + bridge loader |
| `src/jforex/src/test/java/.../*Test.java` | Existing modified | Java tests covering the broker tick writer |
| `tests/test_api_server.py` | Existing modified | Python API server tests for the tick recording surface |
| `uv.lock` | Existing modified | Lock file regeneration that came with the dependency changes |
| `data/analysis/backtest_reconcile/run_manifest_TEMPLATE.md` | **Create** | Markdown template the operator copies + fills in at week-start |
| `data/analysis/backtest_reconcile/smoke_test_2026-05-01/` | **Create** | Output dir for tonight's smoke-test artifacts; lives in repo as the day-1 reference (gitignored payload, kept locally) |

## Branching

The repository policy is to develop in worktrees and merge via PR. The current `main` working tree already has the uncommitted JForex / API / script changes. We move them into a fresh worktree on a new branch.

**Branch name:** `feat/live-broker-tick-capture-and-comparison`
**Worktree path:** `../behemoth-broker-tick-capture` (sibling to the main checkout)

---

## Task 1: Move uncommitted work to a fresh worktree

**Files (all already present in main working tree):**
- Modify (move): `scripts/run_jforex_live.py`
- Modify (move): `src/behemoth/api/server.py`
- Modify (move): `src/jforex/src/main/java/com/behemoth/jforex/config/JForexSessionConfig.java`
- Modify (move): `src/jforex/src/main/java/com/behemoth/jforex/core/BehemothStrategyCore.java`
- Modify (move): `src/jforex/src/main/java/com/behemoth/jforex/live/BrokerBridgeLoader.java`
- Modify (move): `src/jforex/src/main/java/com/behemoth/jforex/reporting/Stage14ArtifactWriter.java`
- Modify (move): `src/jforex/src/test/java/com/behemoth/jforex/BehemothStrategyCoreTest.java`
- Modify (move): `src/jforex/src/test/java/com/behemoth/jforex/Stage14ArtifactWriterTest.java`
- Modify (move): `tests/test_api_server.py`
- Modify (move): `uv.lock`
- Move (untracked → tracked): `scripts/compare_live_broker_ticks.py`
- Move (untracked → tracked): `scripts/diagnose_live_replay_parity.py`
- Move (untracked → tracked): `tests/test_compare_live_broker_ticks.py`
- Move (untracked → tracked): `tests/test_diagnose_live_replay_parity.py`

- [ ] **Step 1: From `/Users/danielfisher/repositories/behemoth`, snapshot uncommitted work into a stash**

```bash
git stash push -u -m "broker-tick capture + comparison scripts"
```

Expected output: `Saved working directory and index state On main: broker-tick capture + comparison scripts`. After this, `git status` reports a clean tree on main (apart from the existing `docs/superpowers/specs/...` and `docs/superpowers/plans/...` files, which can stay tracked-on-main).

- [ ] **Step 2: Create a worktree on a new feature branch from current main HEAD**

```bash
git worktree add ../behemoth-broker-tick-capture -b feat/live-broker-tick-capture-and-comparison
```

Expected output: `Preparing worktree (new branch 'feat/live-broker-tick-capture-and-comparison')` + `HEAD is now at <sha> docs: week-long live capture readiness plan`.

- [ ] **Step 3: Switch to the new worktree and pop the stash**

```bash
cd ../behemoth-broker-tick-capture
git stash pop
```

Expected: the stash is applied cleanly. `git status -s` now shows the same `M` and `??` entries that were on main before, but in the worktree.

- [ ] **Step 4: Verify main is back to clean**

```bash
git -C /Users/danielfisher/repositories/behemoth status -s
```

Expected: only `docs/superpowers/specs/...` and `docs/superpowers/plans/...` listed (these are committed on main as part of the readiness work). No `M` lines on the JForex / API / script files.

---

## Task 2: Verify the full relevant test suite passes in the worktree

**Files:** No file changes in this task — read-only validation.

- [ ] **Step 1: Run the new comparison-script tests**

```bash
uv run pytest tests/test_compare_live_broker_ticks.py tests/test_diagnose_live_replay_parity.py -q
```

Expected: `7 passed` (with 3 numpy `RuntimeWarning`s about degrees-of-freedom — those are pre-existing in `compare_symbol`'s correlation calc on tiny synthetic test inputs and are not blockers).

- [ ] **Step 2: Run the modified API server tests**

```bash
uv run pytest tests/test_api_server.py -q
```

Expected: all tests pass.

- [ ] **Step 3: Run the JForex Java tests**

```bash
cd src/jforex && ./gradlew --no-daemon test
```

Expected: `BUILD SUCCESSFUL`. The `--no-daemon` flag is required (per repo convention — see commit `8901962f`).

- [ ] **Step 4: Return to the worktree root**

```bash
cd ../..
```

If any test fails: stop. Do not proceed to commit. Investigate the failure, fix it on the worktree, re-run.

---

## Task 3: Commit the broker-tick capture + comparison work

**Files:** All from Task 1.

- [ ] **Step 1: Stage everything**

```bash
git add \
  scripts/run_jforex_live.py \
  scripts/compare_live_broker_ticks.py \
  scripts/diagnose_live_replay_parity.py \
  src/behemoth/api/server.py \
  src/jforex/src/main/java/com/behemoth/jforex/config/JForexSessionConfig.java \
  src/jforex/src/main/java/com/behemoth/jforex/core/BehemothStrategyCore.java \
  src/jforex/src/main/java/com/behemoth/jforex/live/BrokerBridgeLoader.java \
  src/jforex/src/main/java/com/behemoth/jforex/reporting/Stage14ArtifactWriter.java \
  src/jforex/src/test/java/com/behemoth/jforex/BehemothStrategyCoreTest.java \
  src/jforex/src/test/java/com/behemoth/jforex/Stage14ArtifactWriterTest.java \
  tests/test_api_server.py \
  tests/test_compare_live_broker_ticks.py \
  tests/test_diagnose_live_replay_parity.py \
  uv.lock
```

- [ ] **Step 2: Verify only the intended files are staged**

```bash
git diff --cached --name-only
```

Expected: exactly the 14 paths above. If any extra path appears, unstage it with `git restore --staged <path>` before committing.

- [ ] **Step 3: Commit with a conventional message**

```bash
git commit -m "$(cat <<'EOF'
feat: capture JForex broker ticks + add live/archive comparison scripts

Adds per-tick broker capture inside the JForex strategy
(Stage14ArtifactWriter.recordBrokerTick) and two diagnostic scripts:
compare_live_broker_ticks (broker CSV vs Dukascopy parquet, optional
vs API raw_ticks) and diagnose_live_replay_parity (selected-action
parity vs reconstructed replay). Together these let us answer where
discrepancies between live runtime and offline replay actually enter.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

Expected: pre-commit hooks run and pass; commit is created on `feat/live-broker-tick-capture-and-comparison`.

If a hook fails: fix the underlying issue, re-stage if needed, create a NEW commit (do not `--amend`).

---

## Task 4: Create the run-manifest template

**Files:**
- Create: `data/analysis/backtest_reconcile/run_manifest_TEMPLATE.md`

- [ ] **Step 1: Write the template**

```bash
mkdir -p data/analysis/backtest_reconcile
```

Then create `data/analysis/backtest_reconcile/run_manifest_TEMPLATE.md` with this content:

```markdown
# Run manifest — week starting <YYYY-MM-DD>

> Operator copies this template to `run_manifest_<YYYY-MM-DD>.md` at week-start
> and fills in every field below. Friday's analysis reads this file to load the
> same model and threshold artifacts that ran live.

## Versions

- **Git SHA at week-start:** `<full 40-char SHA — the merge commit of feat/live-broker-tick-capture-and-comparison>`
- **JForex strategy version:** `<from src/jforex/build.gradle or VERSION>`
- **Python package version:** `<from pyproject.toml / src/behemoth/__init__.py>`

## Model

- **Model month (YYYYMM):** `<e.g. 202604>`
- **Model artifact path:** `<absolute path to the .cbm or model dir loaded by the live runtime>`
- **Model artifact SHA-256:** `<sha256sum output>`

## Thresholds

- **Threshold config path:** `<absolute path>`
- **Threshold config SHA-256:** `<sha256sum output>`

## Capture window

- **Symbols:** `AUDUSD,EURUSD,GBPUSD,USDCAD,USDCHF,USDJPY`
- **Start (UTC):** `<YYYY-MM-DDTHH:MM:SSZ — moment the live runtime first ingested a tick>`
- **End (UTC):** `<filled in Friday at snapshot time>`

## Gaps

> Append a `### Gap` subsection here for each downtime window during the week.
> Format: down-from / up-from in UTC, plus a short note on the cause.

(none)

## Notes

(free-form operator notes)
```

- [ ] **Step 2: Stage and commit the template**

```bash
git add data/analysis/backtest_reconcile/run_manifest_TEMPLATE.md
git commit -m "$(cat <<'EOF'
chore: add run-manifest template for live capture weeks

Operator copies this to run_manifest_<date>.md at week-start, fills in
the live model + threshold artifact hashes, and updates the End/Gaps
sections through the week. Friday's analysis reads this manifest to
reproduce the exact live configuration in the offline replay.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

Expected: commit succeeds.

---

## Task 5: Smoke-test `compare_live_broker_ticks.py` on today's captured data

**Files:**
- Read: `data/analysis/backtest_reconcile/<SYMBOL>_jforex_broker_ticks.csv` (in main checkout — cross-worktree access is fine because the data is outside git)
- Read: `data/analysis/backtest_reconcile/runtime/live_state.db` (DuckDB; live runtime may be writing — snapshot first)
- Read: `/Users/danielfisher/Desktop/dukascopy_ticks/<SYMBOL>/<SYMBOL>_2026{04,05}_ticks.parquet`
- Create (output): `data/analysis/backtest_reconcile/smoke_test_2026-05-01/`

- [ ] **Step 1: Snapshot the live DB to /tmp**

The live runtime may still be writing to `live_state.db`. Copy with WAL + SHM so the snapshot is internally consistent.

```bash
mkdir -p /tmp/live_state_smoke
cp /Users/danielfisher/repositories/behemoth/data/analysis/backtest_reconcile/runtime/live_state.db /tmp/live_state_smoke/live_state.db
cp /Users/danielfisher/repositories/behemoth/data/analysis/backtest_reconcile/runtime/live_state.db.wal /tmp/live_state_smoke/live_state.db.wal 2>/dev/null || true
cp /Users/danielfisher/repositories/behemoth/data/analysis/backtest_reconcile/runtime/live_state.db.shm /tmp/live_state_smoke/live_state.db.shm 2>/dev/null || true
```

- [ ] **Step 2: Verify the snapshot opens and has expected counts**

```bash
uv run --no-project python -c "
import duckdb
con = duckdb.connect('/tmp/live_state_smoke/live_state.db', read_only=True)
print(con.execute('SELECT symbol, COUNT(*) FROM raw_ticks GROUP BY symbol ORDER BY symbol').fetchall())
"
```

Expected: six rows, one per symbol, counts in the tens of thousands. If you get `Error: file is not a database`, the WAL/SHM weren't copied — repeat Step 1.

- [ ] **Step 3: Run the comparison**

```bash
mkdir -p data/analysis/backtest_reconcile/smoke_test_2026-05-01

uv run python scripts/compare_live_broker_ticks.py \
  --broker-ticks /Users/danielfisher/repositories/behemoth/data/analysis/backtest_reconcile \
  --tick-root /Users/danielfisher/Desktop/dukascopy_ticks \
  --symbols AUDUSD,EURUSD,GBPUSD,USDCAD,USDCHF,USDJPY \
  --start-ts 2026-04-30T10:00:00Z \
  --end-ts 2026-05-01T03:45:00Z \
  --api-db /tmp/live_state_smoke/live_state.db \
  --out-dir data/analysis/backtest_reconcile/smoke_test_2026-05-01
```

Expected: script prints `wrote tick comparison artifacts to data/analysis/backtest_reconcile/smoke_test_2026-05-01` followed by a markdown table of the broker-vs-Dukascopy summary (one row per symbol).

- [ ] **Step 4: Verify the output artifacts exist and are non-empty**

```bash
ls -lah data/analysis/backtest_reconcile/smoke_test_2026-05-01/
```

Expected files:
- `report.md` (markdown report with `## Broker vs Dukascopy` and `## Broker vs API Raw Ticks` sections)
- `broker_vs_dukascopy_tick_summary.csv` (one row per symbol)
- `broker_vs_dukascopy_hourly_coverage.csv`
- `broker_vs_api_tick_seq_summary.csv` (one row per symbol; API DB was passed)

All four should be non-empty.

- [ ] **Step 5: Sanity-check the report contents**

```bash
cat data/analysis/backtest_reconcile/smoke_test_2026-05-01/report.md
```

Sanity criteria (compare against the audit doc's day-1 numbers):
- All six symbols appear in `## Broker vs Dukascopy`.
- All six symbols appear in `## Broker vs API Raw Ticks`.
- Tick counts in `broker_vs_dukascopy_tick_summary.csv` are within ~1k of yesterday's audit numbers (broker_csv 72,044 / 82,832 / 88,058 / 53,550 / 59,129 / 117,560).
- API parity counts match raw_ticks rows from `live_state.db` within the overlap window.

If any sanity check fails: investigate before committing the smoke-test outputs. The most likely cause is a bad `--start-ts` / `--end-ts` window — adjust to the actual capture span (use `MIN(tick_ts)` / `MAX(tick_ts)` from the DB).

If the script errors out: do **not** push the PR until the script is fixed on the feature branch.

---

## Task 6: Push the branch and open the PR

**Files:** No file changes — git + GitHub operations only.

- [ ] **Step 1: Confirm branch state**

```bash
git log --oneline main..HEAD
```

Expected: exactly two commits — the `feat: capture JForex broker ticks ...` commit and the `chore: add run-manifest template ...` commit.

- [ ] **Step 2: Push the branch with upstream tracking**

```bash
git push -u origin feat/live-broker-tick-capture-and-comparison
```

Expected: branch is pushed; remote tracking is set.

- [ ] **Step 3: Open the PR**

```bash
gh pr create --title "feat: live broker tick capture + comparison scripts" --body "$(cat <<'EOF'
## Summary

- JForex strategy now captures every broker tick to `<SYMBOL>_jforex_broker_ticks.csv` via `Stage14ArtifactWriter.recordBrokerTick`, before sending to the Python API. This is the third tick stream needed for the Live Runtime / archive parity audit.
- Adds `scripts/compare_live_broker_ticks.py` — broker CSV vs Dukascopy parquet, optionally joined to API `raw_ticks` on `client_tick_seq` for a Java→Python ingestion-path bit-exact check.
- Adds `scripts/diagnose_live_replay_parity.py` — selected-action parity between live `predict_evaluations` and a reconstructed-replay re-run of the same window, to test whether tick-source variance shifts decisions.
- Adds Python and Java test coverage for the new code paths.
- Adds `data/analysis/backtest_reconcile/run_manifest_TEMPLATE.md` — the operator-filled manifest that pins the live model + threshold artifacts at week-start, so Friday's replay reproduces the live configuration.

This unblocks the week-long capture described in `docs/superpowers/specs/2026-05-01-week-long-live-capture-readiness-design.md`.

## Test plan

- [x] `uv run pytest tests/test_compare_live_broker_ticks.py tests/test_diagnose_live_replay_parity.py -q` (7 passed)
- [x] `uv run pytest tests/test_api_server.py -q`
- [x] `cd src/jforex && ./gradlew --no-daemon test`
- [x] End-to-end smoke test of `compare_live_broker_ticks.py` against today's captured 17.7-hour live window (output in `data/analysis/backtest_reconcile/smoke_test_2026-05-01/`)
- [ ] Smoke test of `diagnose_live_replay_parity.py` runs after the new model is deployed (separate, before week-start)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected: PR URL is printed. Capture the PR number for the next step.

- [ ] **Step 4: Record the PR URL in the spec for traceability**

Edit `docs/superpowers/specs/2026-05-01-week-long-live-capture-readiness-design.md`. At the bottom of the "Pre-flight checklist" section 1, append:

```markdown
**PR:** <URL printed by gh pr create>
```

Then commit (still on the feature branch — this commit will land alongside the others when the PR merges):

```bash
git add docs/superpowers/specs/2026-05-01-week-long-live-capture-readiness-design.md
git commit -m "$(cat <<'EOF'
docs: record PR URL in readiness spec

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
git push
```

---

## Task 7: After PR merges — record the merge SHA

**Files:**
- Modify: `data/analysis/backtest_reconcile/live_data_audit_2026-05-01.md`

This task runs **after** the PR is merged to main (could be a follow-up turn).

- [ ] **Step 1: Capture the merge SHA**

From the main checkout:

```bash
cd /Users/danielfisher/repositories/behemoth
git checkout main
git pull
git log --oneline -5
```

Note the commit SHA of the `feat: live broker tick capture + comparison scripts (#NNN)` merge commit.

- [ ] **Step 2: Record the SHA in the audit doc**

Append to `data/analysis/backtest_reconcile/live_data_audit_2026-05-01.md`:

```markdown
## Locked reference for week-long capture

Comparison scripts and broker-tick capture are locked to merge commit `<full-sha>` (PR #NNN). Friday's analysis checks out this SHA before running `compare_live_broker_ticks.py` and `diagnose_live_replay_parity.py`.
```

- [ ] **Step 3: Open a one-line PR for the lock record**

Per the project rule (PRs only, never direct commits to main), open a tiny PR even for this one-line edit.

```bash
git worktree add ../behemoth-lock-sha -b docs/lock-sha-week-2026-05-01
cd ../behemoth-lock-sha
# (the audit doc edit from Step 2 is already on main locally; redo the same one-line edit here)
git add data/analysis/backtest_reconcile/live_data_audit_2026-05-01.md
git commit -m "$(cat <<'EOF'
docs: record locked-reference SHA for week-long capture

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
git push -u origin docs/lock-sha-week-2026-05-01
gh pr create --title "docs: record locked-reference SHA for week-long capture" --body "One-line lock record. Merge after the feat PR is merged."
```

Expected: PR URL is printed. Self-merge (or get a quick review) and close out.

---

## Self-Review Notes

Spec coverage:
- Pre-flight item 1 (commit + PR comparison scripts): Tasks 1–3, 6.
- Pre-flight item 2 (manifest at week-start): Task 4 (template only — operator fills in at week-start, deliberately not auto-generated per minimum-infra choice).
- Pre-flight item 3 part A (smoke-test `compare_live_broker_ticks.py` tonight): Task 5.
- Pre-flight item 3 part B (smoke-test `diagnose_live_replay_parity.py` after new model deploys): Out of scope for this plan — it's a one-liner the operator runs once the model artifact exists. The PR description's test plan flags it as a follow-up checkbox.
- Locked-SHA reference: Task 7.

Daily-week and Friday-analysis steps from the spec are operator procedures, not implementation tasks — they intentionally have no plan task.
