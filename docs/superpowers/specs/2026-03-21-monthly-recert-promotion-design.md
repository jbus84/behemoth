# Monthly Recertification and Promotion Design

## Problem

There is no single command that runs the full monthly recertification pipeline and produces a human-readable go/no-go summary. After Stage 14 passes, there is also no `make promote-live` equivalent to freeze the new month's governance locks and confirm readiness to restart the live runner.

The existing `jforex-dukascopy-matrix` target has hardcoded `--model-month`, `--start-ts`, and `--end-ts` values that must be manually updated each month — an error-prone step with no documentation.

## Scope

**In scope:** Certification (stages 12→14) + promotion. Assumes models are already retrained and a base governance lock exists in the dukascopy-candidate directory.

**Out of scope:** Retraining within the dukascopy-candidate pipeline (stages 1–11). The operator runs `make retrain-all` and `make freeze-oco-dukascopy-candidate` manually as prerequisites. This is a deliberate YAGNI decision; the dukascopy-candidate retraining pipeline would require changes to `onboard_symbol.py` and is tracked separately.

## Requirements

1. `scripts/run_monthly_recert.py` auto-derives the model month (last complete calendar month) and test window (4th–9th of that month), runs `make jforex-dukascopy-matrix` and `make full-stage14-cert` as subprocesses, reads `stage14_jforex_runtime_certification_checks.csv`, and prints a per-symbol go/no-go summary. Exits 0 if all symbols pass, exits 1 if any fail.
2. `scripts/run_promote_live.py` verifies the stage14 cert passed, runs `freeze_oco_historical_governance.py` to archive the current `oco_dukascopy_candidate/` locks under the new month in `oco_history_dukascopy_candidate/`, and prints a restart reminder. Exits non-zero if cert has not passed.
3. `make freeze-oco-dukascopy-candidate` freezes governance locks to `configs/research/governance/oco_dukascopy_candidate/` using `freeze_oco_live_governance.py --out-dir configs/research/governance/oco_dukascopy_candidate`. This is a manual prerequisite step, not called by `monthly-recert`.
4. `make monthly-recert` and `make promote-live` wrap the respective scripts. Both added to `.PHONY` and `make help`.
5. No automated restart of `make jforex-live` — human-in-the-loop on the live restart.
6. No crash recovery or automatic retry.

## Architecture

### Manual prerequisites (run once before `monthly-recert`)

```
make retrain-all
    → trains models to models/oco/ for all 6 symbols

make freeze-oco-dukascopy-candidate
    → freeze_oco_live_governance.py --out-dir configs/research/governance/oco_dukascopy_candidate
    → freezes SHA256-locked manifest for each symbol
```

### `make monthly-recert` sequence

```
run_monthly_recert.py
  → derive MODEL_MONTH = last complete calendar month (YYYY-MM)
  → derive START_TS  = MODEL_MONTH-04T00:00:00Z  (matrix window start, includes warmup)
  → derive END_TS    = MODEL_MONTH-09T00:00:00Z  (matrix window end)
  → derive EVAL_START = MODEL_MONTH-07T00:00:00Z  (outcome parity eval start, post-warmup)
  → derive EVAL_END   = MODEL_MONTH-09T00:00:00Z  (outcome parity eval end)
  → derive LOCK_DIR  = configs/research/governance/oco_history_dukascopy_candidate/MODEL_MONTH
  → print "[monthly-recert] running for MODEL_MONTH=YYYY-MM window=..."
  → subprocess: make jforex-dukascopy-matrix
      MODEL_MONTH=... START_TS=... END_TS=...
      (all other defaults unchanged)
  → on non-zero exit: print error, exit 1
  → subprocess: make full-stage14-cert
      LOCK_DIR=... EVAL_START=... EVAL_END=...
      (passes derived vars through to jforex-outcome-parity sub-target)
  → on non-zero exit: print error, exit 1
  → read data/analysis/backtest_reconcile/stage14_jforex_runtime_certification_checks.csv
  → aggregate pass/fail per symbol (status column; critical checks only)
  → print per-symbol summary
  → if all pass: print "go/no-go: GO — run make promote-live to archive locks", exit 0
  → if any fail: print "go/no-go: NO-GO — N symbol(s) failed", exit 1
```

Note: `full-stage14-cert` chains three sub-targets: `jforex-outcome-parity` (uses `LOCK_DIR`, `EVAL_START`, `EVAL_END`), `local-jforex-cert` (uses glob patterns against report dir, no date variables), and `stage14-jforex-cert`. Only `jforex-outcome-parity` requires the derived date variables to be passed through.

### `make promote-live` sequence

```
run_promote_live.py
  → derive MODEL_MONTH (same logic, overridable via --model-month)
  → read stage14_jforex_runtime_certification_checks.csv
  → if CSV missing: exit 1 — "no cert results found; run make monthly-recert first"
  → if evaluated_at_utc date != today's date: exit 1 — "cert results are stale (DATE); rerun make monthly-recert"
  → if any critical check failed: exit 1 — "cert failed for N symbol(s); cannot promote"
  → subprocess: freeze_oco_historical_governance.py
      --symbols EURUSD,GBPUSD,USDJPY,USDCHF,AUDUSD,USDCAD
      --out-dir configs/research/governance/oco_history_dukascopy_candidate
      --months MODEL_MONTH
      --config-dir configs/research/experiments_dukascopy_candidate
      --analysis-dir data/analysis/tick_opportunity_mining_dukascopy_candidate
      --models-dir models/oco
  → print "[promote-live] locks archived for MODEL_MONTH"
  → print reminder: "Next step: restart the live runner with: make jforex-live"
  → exit 0
```

**Note on `--models-dir models/oco`:** Governance locks store SHA256 fingerprints of model artifacts in `models/oco/` (both the `oco/` and `oco_dukascopy_candidate/` locks reference this path — the dukascopy-candidate lock does not use a separate model directory). `BEHEMOTH_MODELS_DIR=models/oco_dukascopy_candidate` used by the live harness is a runtime lookup path independent of the SHA256-locked paths in the governance manifest.

### `make freeze-oco-dukascopy-candidate` recipe

Calls `freeze_oco_live_governance.py` with dukascopy-candidate artifact dirs:

```makefile
freeze-oco-dukascopy-candidate:
	uv run python scripts/freeze_oco_live_governance.py \
		--symbols $(shell echo $(REBUILD_SYMBOLS) | sed 's/ /,/g') \
		--out-dir configs/research/governance/oco_dukascopy_candidate \
		--config-dir configs/research/experiments_dukascopy_candidate \
		--analysis-dir data/analysis/tick_opportunity_mining_dukascopy_candidate
```

## Go/No-Go Summary Format

```
[monthly-recert] 2026-02 results
  EURUSD  PASS
  GBPUSD  PASS
  USDJPY  FAIL  JFOREX_SIGNAL_PARITY_PASS: signal coverage below threshold
  USDCHF  PASS
  AUDUSD  PASS
  USDCAD  PASS
go/no-go: NO-GO — 1 symbol(s) failed
```

Only `critical` severity checks determine go/no-go. For failing rows the `check_id` column and `details` column from the CSV are shown (e.g. `JFOREX_SIGNAL_PARITY_PASS: <details>`). If `details` is empty, only `check_id` is shown.

## Date Derivation

```python
from datetime import date

def _last_complete_month() -> tuple[str, str, str]:
    today = date.today()
    # Last complete month
    if today.month == 1:
        year, month = today.year - 1, 12
    else:
        year, month = today.year, today.month - 1
    model_month = f"{year:04d}-{month:02d}"
    start_ts = f"{year:04d}-{month:02d}-04T00:00:00Z"
    end_ts   = f"{year:04d}-{month:02d}-09T00:00:00Z"
    return model_month, start_ts, end_ts
```

All derived values overridable: `--model-month`, `--start-ts`, `--end-ts`, `--eval-start`, `--eval-end`. `LOCK_DIR` is derived from `MODEL_MONTH` and cannot be set independently.

## File Map

| File | Change |
|------|--------|
| `scripts/run_monthly_recert.py` | Create |
| `scripts/run_promote_live.py` | Create |
| `Makefile` | Add `freeze-oco-dukascopy-candidate`, `monthly-recert`, `promote-live` targets; add to `.PHONY` and `make help` |

## Testing

No automated tests — both scripts invoke subprocesses requiring real data. Manual verification:

1. `make monthly-recert` → confirm correct `MODEL_MONTH` derived, both subprocesses invoked, go/no-go summary printed.
2. `make monthly-recert MODEL_MONTH=2025-07` → confirm override works.
3. With a failing row in `stage14_jforex_runtime_certification_checks.csv` → confirm exit 1 and failing check name shown.
4. `make promote-live` before recert passes → confirm exits non-zero with clear error.
5. `make promote-live` after recert passes → confirm locks archived to `oco_history_dukascopy_candidate/`, restart reminder printed.
6. `make freeze-oco-dukascopy-candidate` → confirm writes to `configs/research/governance/oco_dukascopy_candidate/`.
