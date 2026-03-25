# Candidate Artifact Sync For Authoritative Live Locks

## Problem

The live runtime now resolves model paths against `models/oco_dukascopy_candidate/`, but the directory can drift away from the authoritative live locks in `configs/research/governance/oco/`.

The concrete failure mode observed on 2026-03-25 was:

- all active live locks were pinned to `model_month=2026-02`
- `models/oco_dukascopy_candidate/` only contained `EURUSD` artifacts for that month
- the existing `EURUSD` candidate artifacts did not match the lock-file hashes
- startup quarantined every symbol, so no symbols could load governance-bound models and `predict_evaluations` remained empty

The root issue is not runtime path resolution anymore. It is the lack of a deterministic, repo-owned step that materializes the candidate deployment artifacts from the authoritative source and proves they match the live locks before certification or restart.

## Chosen Approach

Use the live locks as the contract, use `models/oco/` as the authoritative upstream artifact store, and add a dedicated sync step that populates `models/oco_dukascopy_candidate/` from that source.

This is the selected version of approach 2:

- governance stays authoritative
- candidate deployment artifacts are synchronized, not hand-managed
- `monthly-recert` becomes the enforced entrypoint that assembles and verifies the candidate artifact set before certification
- `promote-live` archives the certified candidate artifact lineage, not the root `models/oco/` lineage

## Control Points

### Authority

- `configs/research/governance/oco/*.json` defines the authoritative live-lock contract
- `models/oco/` is the authoritative source of model binaries and threshold JSONs
- `models/oco_dukascopy_candidate/` is a synchronized deployment/cache directory derived from the two sources above

### Non-goals

- Do not modify live-lock hash fields to match whatever files happen to exist
- Do not let `jforex-live` mutate deployment state
- Do not silently fall back to a different model month
- Do not add ad hoc operator steps outside the existing `make monthly-recert` / `make promote-live` flow

## Design

### 1. New Sync Script

Add a new script: `scripts/sync_candidate_model_artifacts.py`.

Responsibilities:

- read the authoritative live locks from `configs/research/governance/oco/`
- for each active symbol, extract:
  - `model_month`
  - expected `model_cbm_sha256`
  - expected `model_threshold_json_sha256`
  - canonical filenames from the lock artifact paths
- resolve the authoritative source files in `models/oco/`
- copy the exact `{SYMBOL}_model_{MODEL_MONTH}.cbm` and `.json` files into `models/oco_dukascopy_candidate/`
- verify the copied files against the lock hashes
- print a per-symbol summary and exit non-zero if any symbol fails

Expected CLI shape:

```bash
uv run python scripts/sync_candidate_model_artifacts.py \
  --lock-dir configs/research/governance/oco \
  --source-models-dir models/oco \
  --target-models-dir models/oco_dukascopy_candidate \
  --symbols EURUSD,GBPUSD,USDJPY,USDCHF,AUDUSD,USDCAD
```

### 2. Monthly Recert Integration

Update `scripts/run_monthly_recert.py` so the sync step runs before the existing certification steps.

New order:

1. sync candidate artifacts from `models/oco/` into `models/oco_dukascopy_candidate/`
2. run `make jforex-dukascopy-matrix`
3. run `make full-stage14-cert`
4. print go/no-go summary

Rationale:

- recert is already the operator entrypoint for certifying the monthly candidate deployment set
- this makes candidate artifact assembly mandatory rather than tribal knowledge
- if the authoritative artifacts are missing or hashes drift, recert fails before expensive certification work begins

### 3. Promote-Live Integration

Update `scripts/run_promote_live.py` so historical governance archival uses the certified candidate artifact directory instead of root `models/oco/`.

Change:

- replace hardcoded `--models-dir models/oco`
- use `--models-dir models/oco_dukascopy_candidate`

Rationale:

- the historical archive should record the exact certified candidate artifact set
- promotion should not accidentally archive a different artifact lineage than the one used in recert or live startup

### 4. Makefile / Operator Contract

Keep the operator flow, but make it accurate and self-enforcing.

Updated intended flow:

1. retrain/export models into `models/oco/`
2. freeze live locks
3. run `make monthly-recert`
   - this now syncs candidate artifacts and certifies them
4. run `make promote-live`
5. restart with `make jforex-live`

Update help/prerequisite comments so `monthly-recert` no longer implies the candidate directory is already correct by manual action.

## Error Handling

The sync step should be strict and non-healing.

### Hard failures

Fail the whole run if any active symbol has:

- missing source `.cbm` in `models/oco/`
- missing source `.json` in `models/oco/`
- copied `.cbm` hash mismatch vs live lock
- copied `.json` hash mismatch vs live lock
- malformed or incomplete lock artifact metadata

### Output contract

The script should print one result line per symbol with:

- symbol
- model month
- source paths
- target paths
- status
- precise failure reason when applicable

### Safety

- overwriting target files for the exact synced symbol/month is allowed
- broad deletion of unrelated candidate artifacts is out of scope for this change
- lock files are never rewritten by the sync step

## Testing

### New Unit Tests

Add focused tests for the sync helper and script behavior:

- happy path: copies `.cbm` and `.json` into target dir and verifies hashes
- missing source artifact: fails with the exact missing symbol/path
- hash mismatch: fails with expected vs actual hash
- mixed run: one symbol passes, another fails, script exits non-zero

### Pipeline Tests

Add targeted tests proving:

- `run_monthly_recert.py` invokes the sync step before certification
- `run_promote_live.py` archives with `models/oco_dukascopy_candidate`

### Test Style

- use temp dirs and synthetic lock JSON
- do not depend on real exported models or long-running certification commands
- keep integration coverage lightweight and deterministic

## Invariants Preserved

- live locks remain the authoritative governance contract
- runtime still verifies hashes against on-disk files
- `models/oco/` remains the authoritative upstream export location
- `models/oco_dukascopy_candidate/` remains the runtime-facing candidate directory
- `jforex-live` remains a consumer of prepared artifacts, not a producer of them

## Out Of Scope

- regenerating models from training data inside the sync step
- relaxing or rewriting lock hashes
- changing live startup to auto-heal candidate artifacts
- changing model-month selection logic in the live locks
