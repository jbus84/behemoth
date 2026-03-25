# Registry Models-Dir-Aware Path Resolution

## Problem

`CandidateRegistry.load()` treats model artifact paths from governance lock files as repo-relative. When the live stack launches with `--models-dir models/oco_dukascopy_candidate`, the registry still looks for files at `models/oco/` (the path baked into the lock JSON), quarantining all symbols.

## Design

Add an optional `models_dir: Path | None` parameter to `CandidateRegistry.load()`. When provided, resolve model artifact paths as `models_dir / filename` instead of using the raw lock-file path. Store the resolved paths in the binding dict so all downstream consumers get correct paths automatically.

### Changes

**`src/behemoth/core/registry.py` — `CandidateRegistry.load()`**

- Add parameter: `models_dir: Path | None = None`
- After reading `model_cbm_path` and `model_threshold_json_path` from lock JSON, if `models_dir` is set:
  - `cbm_path = models_dir / Path(cbm_path_txt).name`
  - `thr_path = models_dir / Path(thr_path_txt).name`
- Use resolved paths for existence check, SHA-256 verification, and binding dict storage

**`src/behemoth/api/server.py` — lifespan handler (~line 475)**

- Pass `models_dir=_models_dir` to `CandidateRegistry.load()`
- `_models_dir` is already resolved from `BEHEMOTH_MODELS_DIR` env var at startup

### Invariants preserved

- Lock file contents are never modified
- SHA-256 verification runs against on-disk files at the resolved path
- `_load_model_binding_into_cache` reads paths from the binding dict unchanged
- Without `models_dir`, behavior is identical to today (backward compatible)

### Test

- Unit test: `CandidateRegistry.load()` with `models_dir` pointing to a directory containing model files, while lock files reference a different directory prefix. Verify symbols are not quarantined and binding paths point to the resolved location.
