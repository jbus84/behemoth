# Governance Hash Mismatch Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Re-freeze live OCO governance locks so all six symbol hashes match the current model files on disk, unblocking `/predict` from returning 503 and restoring full demo workflow capability.

**Architecture:** All six live governance lock files in `configs/research/governance/oco/` were frozen on 2026-03-06. The `2026-02` model `.cbm` and `.json` files in `models/oco/` were regenerated after that date, so every symbol now quarantines with an artifact hash mismatch. The fix is to commit the pending worktree changes to get a clean state, then run `make freeze-oco` which recomputes hashes, re-validates API parity, and re-runs the audit suite before writing new lock files.

**Tech Stack:** `make`, `uv`, Python — `scripts/freeze_oco_live_governance.py`, `scripts/validate_oco_live_governance.py`, `scripts/validate_api_parity.py`, Python API server (`src/behemoth/api/server.py`), `curl`

---

## File Structure

- Modify: `configs/research/governance/oco/audusd_oco_live_lock.json` — re-frozen with current artifact hashes
- Modify: `configs/research/governance/oco/eurusd_oco_live_lock.json`
- Modify: `configs/research/governance/oco/gbpusd_oco_live_lock.json`
- Modify: `configs/research/governance/oco/usdcad_oco_live_lock.json`
- Modify: `configs/research/governance/oco/usdchf_oco_live_lock.json`
- Modify: `configs/research/governance/oco/usdjpy_oco_live_lock.json`
- Create: `docs/superpowers/audits/2026-03-22-governance-hash-mismatch-fix.md` — evidence log

---

## Execution Rules

- Do not modify model `.cbm` or `.json` files. The lock must come to the models, not the other way around.
- Do not patch the server to skip hash validation. The validation is the safety gate.
- Do not amend the 403c9e6 commit. The JForex runtime fix is already merged and proven — leave it.
- If `make freeze-oco` fails at the API parity step for a symbol, stop and open a follow-up bugfix plan. Do not bypass.
- If EURUSD remains in BRIDGING after a successful freeze and working `/predict`, that is a separate broker-history catch-up issue — record it and do not treat it as a freeze failure.

---

## Task 1: Pre-flight — confirm the mismatch and worktree state

**Files:**
- Create: `docs/superpowers/audits/2026-03-22-governance-hash-mismatch-fix.md`
- Reference: `scripts/validate_oco_live_governance.py`
- Reference: `configs/research/governance/oco/eurusd_oco_live_lock.json`

- [ ] **Step 1: Create the evidence log skeleton**

Create `docs/superpowers/audits/2026-03-22-governance-hash-mismatch-fix.md`:

```markdown
# Governance Hash Mismatch Fix — Evidence Log

## Environment
- Branch:
- Commit:
- Date (UTC):

## Pre-flight: Hash Mismatch Confirmation
- Validate command:
- Exit code:
- Symbols with mismatch:

## Worktree State Before Freeze
- git status (short):
- Pending files committed in prep-commit:

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
```

- [ ] **Step 2: Check git status and record the worktree state**

Run:

```bash
git status --short
```

Expected: you can see the uncommitted changes from the JForex fix (data CSVs, `JForexSessionConfig.java`). Record these in the evidence log under "Worktree State Before Freeze".

- [ ] **Step 3: Formally validate one symbol to confirm the hash mismatch class**

Run:

```bash
UV_CACHE_DIR=.uv_cache uv run python scripts/validate_oco_live_governance.py \
  --lock-path configs/research/governance/oco/eurusd_oco_live_lock.json \
  --mode deploy \
  --wfo-config configs/research/experiments/eurusd_tick_opportunity_monthly_wfo_oco_fullcap_2025.yaml \
  --reduced-config configs/research/experiments/eurusd_oco_reduced_core_2025.yaml \
  --data-reliability-checks-csv data/analysis/tick_opportunity_mining/data_reliability_checks.csv \
  --leakage-checks-csv data/analysis/tick_opportunity_mining/oco_leakage_integrity_checks.csv \
  --execution-risk-checks-csv data/analysis/tick_opportunity_mining/oco_execution_risk_checks.csv
```

Expected:
- the command prints a table or summary
- `model_cbm_hash` and `model_threshold_json_hash` rows show **FAIL** or equivalent
- Exit code is non-zero

Record the output excerpt in the evidence log. This is the baseline proof that the mismatch is real and the category is "hash mismatch" not "file missing".

If the validate script has a different argument signature (check `uv run python scripts/validate_oco_live_governance.py --help`), adapt accordingly.

---

## Task 2: Commit the pending worktree changes

**Files:**
- Modify: `data/analysis/backtest_reconcile/*.csv` (already changed, not authored here)
- Modify: `src/jforex/src/main/java/com/behemoth/jforex/config/JForexSessionConfig.java`

`make freeze-oco` blocks on a dirty worktree. The pending changes are legitimate outputs from the JForex runtime fix (commit 403c9e6) and its demo rerun. They need to land in a commit before the freeze can proceed.

- [ ] **Step 1: Stage and commit the pending artefacts**

Run:

```bash
git add \
  data/analysis/backtest_reconcile/AUDUSD_local_jforex_outcome_parity_summary.csv \
  data/analysis/backtest_reconcile/EURUSD_local_jforex_outcome_parity_summary.csv \
  data/analysis/backtest_reconcile/GBPUSD_local_jforex_outcome_parity_summary.csv \
  data/analysis/backtest_reconcile/USDCAD_local_jforex_outcome_parity_summary.csv \
  data/analysis/backtest_reconcile/USDCHF_local_jforex_outcome_parity_summary.csv \
  data/analysis/backtest_reconcile/USDJPY_local_jforex_outcome_parity_summary.csv \
  data/analysis/backtest_reconcile/jforex_outcome_parity_summary.csv \
  src/jforex/src/main/java/com/behemoth/jforex/config/JForexSessionConfig.java
git commit -m "chore: record demo rerun artefacts and JForex session config from 403c9e6 validation"
```

Expected: commit succeeds, exit 0.

- [ ] **Step 2: Confirm the worktree is now clean**

Run:

```bash
git status --porcelain
```

Expected: completely empty output — no modified tracked files (`M`), no staged files, and no untracked files (`??`). Untracked files (e.g. the plan and spec docs under `docs/superpowers/`) also trigger the dirty-worktree guard in the freeze script. If any `??` lines appear for files that belong in the repo, stage and commit them before continuing:

```bash
git add docs/superpowers/plans/ docs/superpowers/specs/
git commit -m "chore: add plan and spec documents"
git status --porcelain   # must be empty before proceeding
```

---

## Task 3: Run `make freeze-oco`

**Files:**
- Modify: `configs/research/governance/oco/*_oco_live_lock.json` (all six)
- Reference: `Makefile` target `freeze-oco`
- Reference: `scripts/freeze_oco_live_governance.py`
- Reference: `scripts/validate_api_parity.py`

The `freeze-oco` target does three things in sequence:
1. Runs `validate_api_parity.py` for each of the six symbols
2. Runs `freeze_oco_live_governance.py` to write new lock files with fresh hashes
3. Runs `make audit-all` and `make docs-contract-ci`

- [ ] **Step 1: Run the freeze target**

Run:

```bash
make freeze-oco 2>&1 | tee /tmp/freeze-oco.log; echo "EXIT: ${PIPESTATUS[0]}"
```

Expected:
- Output contains `--- Verifying API Parity ---`
- Parity check lines appear for each symbol
- Output contains `--- Refreezing Governance Locks ---`
- Output ends with `✅ Successfully audited and frozen all locks.`
- Exit code 0

- [ ] **Step 2: Confirm all six lock files have a fresh `frozen_at_utc`**

Run:

```bash
UV_CACHE_DIR=.uv_cache uv run python - <<'PY'
import json
from pathlib import Path

symbols = ["audusd", "eurusd", "gbpusd", "usdcad", "usdchf", "usdjpy"]
for sym in symbols:
    p = Path(f"configs/research/governance/oco/{sym}_oco_live_lock.json")
    d = json.loads(p.read_text())
    ts = d.get("frozen_at_utc", "MISSING")
    month = d.get("artifacts", {}).get("model_month", "?")
    print(f"{sym}: frozen_at_utc={ts}  model_month={month}")
PY
```

Expected: all six symbols print a `frozen_at_utc` timestamp from today (2026-03-22 or later) and `model_month=2026-02`.

- [ ] **Step 3: Record the outcome in the evidence log**

Record the key output lines from `/tmp/freeze-oco.log` and the per-symbol `frozen_at_utc` values.

If `make freeze-oco` fails at the API parity step: stop, record the symbol and error in the evidence log, and open a follow-up bugfix plan for that parity failure. Do not continue to Task 4.

---

## Task 4: Post-freeze hash validation

**Files:**
- Reference: `scripts/validate_oco_live_governance.py`
- Reference: `configs/research/governance/oco/*_oco_live_lock.json`

- [ ] **Step 1: Re-run validate for EURUSD to confirm the hash gates now pass**

Run the same command as Task 1 Step 3:

```bash
UV_CACHE_DIR=.uv_cache uv run python scripts/validate_oco_live_governance.py \
  --lock-path configs/research/governance/oco/eurusd_oco_live_lock.json \
  --mode deploy \
  --wfo-config configs/research/experiments/eurusd_tick_opportunity_monthly_wfo_oco_fullcap_2025.yaml \
  --reduced-config configs/research/experiments/eurusd_oco_reduced_core_2025.yaml \
  --data-reliability-checks-csv data/analysis/tick_opportunity_mining/data_reliability_checks.csv \
  --leakage-checks-csv data/analysis/tick_opportunity_mining/oco_leakage_integrity_checks.csv \
  --execution-risk-checks-csv data/analysis/tick_opportunity_mining/oco_execution_risk_checks.csv
```

Expected:
- `model_cbm_hash` and `model_threshold_json_hash` rows both show **PASS**
- Exit code 0

- [ ] **Step 2: Run a quick Python hash check across all six symbols**

Run:

```bash
UV_CACHE_DIR=.uv_cache uv run python - <<'PY'
import hashlib, json
from pathlib import Path

def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

symbols = ["audusd", "eurusd", "gbpusd", "usdcad", "usdchf", "usdjpy"]
all_ok = True
for sym in symbols:
    lock = json.loads(Path(f"configs/research/governance/oco/{sym}_oco_live_lock.json").read_text())
    arts = lock.get("artifacts", {})
    cbm_path = Path(arts["model_cbm_path"])
    thr_path = Path(arts["model_threshold_json_path"])
    cbm_ok = sha256(cbm_path) == arts["model_cbm_sha256"]
    thr_ok = sha256(thr_path) == arts["model_threshold_json_sha256"]
    status = "OK" if (cbm_ok and thr_ok) else f"FAIL cbm={cbm_ok} thr={thr_ok}"
    print(f"{sym.upper()}: {status}")
    if not (cbm_ok and thr_ok):
        all_ok = False

print()
print("ALL PASS" if all_ok else "FAILURES DETECTED")
PY
```

Expected: each symbol prints `OK` and the final line is `ALL PASS`.

---

## Task 5: Commit the new lock files

**Files:**
- Modify: `configs/research/governance/oco/*_oco_live_lock.json` (all six)

- [ ] **Step 1: Stage and commit the six updated lock files**

Run:

```bash
git add configs/research/governance/oco/
git commit -m "chore: re-freeze live governance locks to match 2026-02 model artifacts"
```

Expected: commit succeeds, exit 0.

---

## Task 6: Smoke-test `/predict` with the fresh locks

**Files:**
- Reference: `src/behemoth/api/server.py`
- Reference: `Makefile` (look at the `jforex-live` target for the API start command)

- [ ] **Step 1: Start the Python API server in the background**

Run `make jforex-live` redirected to a log file, then wait a few seconds for it to bind:

```bash
make jforex-live > /tmp/api-server.log 2>&1 &
sleep 5
grep -E "Quarantining|No governance model binding|Application startup complete|Uvicorn running" /tmp/api-server.log
```

Expected:
- Server starts without quarantine errors for any symbol
- No `Quarantining` log lines appear during startup
- No `No governance model binding` errors

If you still see quarantine errors after a successful freeze, check that the server is loading governance locks from `configs/research/governance/oco/` (not a stale path). Check `BEHEMOTH_GOVERNANCE_DIR` env var.

- [ ] **Step 2: Hit `/predict` for each symbol**

For each symbol in `EURUSD GBPUSD USDJPY USDCHF AUDUSD USDCAD`, call `/predict` with a minimal valid payload. The exact payload shape is in `src/behemoth/api/server.py` around the `PredictRequest` model, or look at any existing test fixtures.

The `PredictRequest` model requires `symbol` (str) and exactly one of `risk_enabled_override` (bool) or `ftmo_enabled_override` (bool). There are no `close` or `close_ts` fields.

Run:

```bash
for sym in EURUSD GBPUSD USDJPY USDCHF AUDUSD USDCAD; do
  echo -n "$sym: "
  curl -s -o /dev/null -w "%{http_code}" -X POST http://127.0.0.1:8000/predict \
    -H "Content-Type: application/json" \
    -d "{\"symbol\": \"$sym\", \"risk_enabled_override\": false}"
  echo
done
```

Expected:
- All six symbols return HTTP 200 (not 503)
- Record the status code per symbol in the evidence log

- [ ] **Step 3: Stop the background server and update the evidence log**

Kill the server process and fill in the `/predict` results in the audit note under "Smoke Test".

---

## Task 7: Record final outcome and outstanding issues

**Files:**
- Modify: `docs/superpowers/audits/2026-03-22-governance-hash-mismatch-fix.md`

- [ ] **Step 1: Record EURUSD BRIDGING status as a separate concern**

EURUSD remained in `BRIDGING` during the demo rerun. This is consistent with a stale local parquet tail requiring broker-history catch-up before the symbol is declared READY. It is not related to the governance hash fix — the governance fix restores the capability for EURUSD to attempt a trade if it does become READY. Record this in the "Outstanding Issues" section of the evidence log.

- [ ] **Step 2: Fill in the Final Outcome section**

Expected entries:
- Status: `governance hash mismatch resolved — /predict returning 200 for all 6 symbols`
- Commit: the hash of the re-freeze commit from Task 5

---

## Success Criteria

This plan is complete when:

- `docs/superpowers/audits/2026-03-22-governance-hash-mismatch-fix.md` exists with evidence for every task
- All six `*_oco_live_lock.json` files have `frozen_at_utc` from 2026-03-22 or later
- The Task 4 Step 2 hash-check script prints `ALL PASS`
- `/predict` returns HTTP 200 for all six symbols against the running API server
- The re-frozen locks are committed to `main`
