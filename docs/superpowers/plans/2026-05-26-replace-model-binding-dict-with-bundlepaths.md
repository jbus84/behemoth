# Replace `model_binding` Dict with `BundlePaths` Handle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Dependency:** None — independent of the other follow-ups. Can ship before, after, or in parallel with the family-parameterization plan.

**Goal:** Delete the legacy flat `model_binding` dict shape (`{"model_cbm_path": ..., "model_cbm_sha256": ..., "model_threshold_json_path": ..., "model_threshold_json_sha256": ..., "model_month": ...}`) and pass `BundlePaths` directly to downstream consumers. Today `model_binding` is built *from* `BundlePaths` accessors and then handed off — that translation shim leaks v1 vocabulary forward and is a maintenance trap (anyone adding a new model artifact has to update two places).

**Architecture:** `CandidateContract` (in `src/behemoth/core/governance_lock_loader.py`) currently exposes `model_binding: dict[str, Any]`. Replace that field with `bundle_paths: BundlePaths`. Every consumer that today reads `binding["model_cbm_path"]` reads `contract.bundle_paths.model_cbm()` instead. Same for `model_threshold_json`, `model_month`, sha256s. The flat dict and its construction code are deleted.

**Tech Stack:** Python 3.12, `uv`, `pytest`, `ruff`. No new dependencies.

---

## Current State

Consumers of `model_binding["..."]`, found via:

```bash
grep -rn 'model_binding\["\|model_binding\.get\|_model_bindings_by_symbol' src/ scripts/ | grep -v __pycache__
```

The known list (verify before starting — file may have moved):

- `src/behemoth/core/governance_lock_loader.py` — builds `model_binding`.
- `src/behemoth/core/registry.py` — stores `_model_bindings_by_symbol`, exposes `get_model_binding()`.
- `src/behemoth/core/historical_registry.py` — same pattern for historical bundles.
- `src/behemoth/core/model_registry.py` — consumer; loads CatBoost model from `binding["model_cbm_path"]`.
- `src/behemoth/core/historical_prediction_stage.py` — consumer.
- `src/behemoth/api/server.py` — consumer; surfaces binding shape via API.
- `scripts/seed_rolling_threshold.py` — consumer.

`model_binding` keys in active use:
- `model_cbm_path` (str)
- `model_cbm_sha256` (str)
- `model_threshold_json_path` (str)
- `model_threshold_json_sha256` (str)
- `model_month` (str)
- `locked_runtime_overrides` (sometimes, dict)  ← see `test_load_resolves_model_paths_against_models_dir`

The `locked_runtime_overrides` sub-dict carries data that doesn't come from `BundlePaths` — it comes from `locked_runtime` in the lock. That has to be preserved on `CandidateContract` separately.

---

## File Structure

**Modified files:**
- `src/behemoth/core/governance_lock_loader.py` — replace `model_binding` with `bundle_paths`; lift `locked_runtime_overrides` to its own field.
- `src/behemoth/core/registry.py` — replace `_model_bindings_by_symbol: dict[str, dict]` with `_bundle_paths_by_symbol: dict[str, BundlePaths]`.
- `src/behemoth/core/historical_registry.py` — same.
- `src/behemoth/core/model_registry.py` — call `bp.model_cbm()` instead of reading the dict.
- `src/behemoth/core/historical_prediction_stage.py` — same.
- `src/behemoth/api/server.py` — same; the API response shape may need a careful change (see Task 5).
- `scripts/seed_rolling_threshold.py` — same.
- Affected tests in `tests/`.

---

## Task 1: Extend `CandidateContract` with `bundle_paths` — failing test

**Files:**
- Test: `tests/test_governance_lock_loader.py`

- [ ] **Step 1: Add a failing test**

Append:

```python
def test_load_contract_exposes_bundle_paths(tmp_path: Path) -> None:
    """CandidateContract surfaces BundlePaths so consumers don't need model_binding."""
    from src.behemoth.core.bundle_paths import BundlePaths

    lock = _write_v3_lock(tmp_path)  # the existing v3 fixture helper
    loader = GovernanceLockLoader(FakeLiveSource(lock))
    contract = loader.load_contract("EURUSD")

    assert isinstance(contract.bundle_paths, BundlePaths)
    assert contract.bundle_paths.model_cbm().name == "EURUSD_model_2026-01.cbm"
    assert contract.bundle_paths.model_month == "2026-01"


def test_load_contract_exposes_locked_runtime_overrides(tmp_path: Path) -> None:
    """The locked_runtime block becomes its own field; it does NOT live on model_binding."""
    lock = _write_v3_lock(tmp_path, locked_runtime={
        "production_cap_pips": 1.5,
        "threshold_mode": "rolling_days",
        "rolling_threshold_days": 20,
        "rolling_threshold_min_history": 300,
        "execution_quantile": 0.9,
    })
    loader = GovernanceLockLoader(FakeLiveSource(lock))
    contract = loader.load_contract("EURUSD")

    assert contract.locked_runtime["threshold_mode"] == "rolling_days"
    assert contract.locked_runtime["rolling_threshold_days"] == 20
```

- [ ] **Step 2: Run failing tests**

Run: `uv run pytest tests/test_governance_lock_loader.py -v`
Expected: FAIL — `bundle_paths` attribute and `locked_runtime` field don't exist on `CandidateContract`.

---

## Task 2: Extend `CandidateContract` — implementation

**Files:**
- Modify: `src/behemoth/core/governance_lock_loader.py`

- [ ] **Step 1: Add fields**

```python
# In governance_lock_loader.py:

from src.behemoth.core.bundle_paths import BundlePaths

@dataclass(frozen=True)
class CandidateContract:
    symbol: str
    model_month: str
    cache_key: str
    candidates: list[CandidateSpec]
    bundle_paths: BundlePaths
    locked_runtime: dict[str, Any]
    cap_pips: float
    source: str
    lock_path: str | None = None
    # model_binding remains for one transition release; mark it deprecated.
    model_binding: dict[str, Any] = field(default_factory=dict)
```

In `_parse_lock`, populate the new fields **alongside** the existing `model_binding` for one transition:

```python
bp = BundlePaths.from_lock(path)
locked = data.get("locked_runtime", {}) or {}
# model_binding kept temporarily; will be removed in Task 6.
artifacts = data.get("artifacts", {})
cbm_entry = artifacts.get("model_cbm", {}) or {}
thr_entry = artifacts.get("model_threshold_json", {}) or {}
model_binding = {
    "model_cbm_path":              str(bp.model_cbm()),
    "model_cbm_sha256":            str(cbm_entry.get("sha256", "")).strip(),
    "model_threshold_json_path":   str(bp.model_threshold_json()),
    "model_threshold_json_sha256": str(thr_entry.get("sha256", "")).strip(),
    "model_month":                 bp.model_month,
}
return CandidateContract(
    symbol=sym,
    model_month=bp.model_month,
    cache_key=...,
    candidates=candidates,
    bundle_paths=bp,
    locked_runtime=dict(locked),
    cap_pips=float(locked.get("production_cap_pips", 1.2)),
    source=...,
    lock_path=str(path),
    model_binding=model_binding,
)
```

- [ ] **Step 2: Run tests**

Run: `uv run pytest tests/test_governance_lock_loader.py -v`
Expected: PASS.

- [ ] **Step 3: Lint + commit**

```bash
uv run ruff check src/behemoth/core/governance_lock_loader.py
git add src/behemoth/core/governance_lock_loader.py tests/test_governance_lock_loader.py
git commit -m "feat(governance): CandidateContract exposes BundlePaths + locked_runtime"
```

---

## Task 3: Migrate `model_registry.py` to `BundlePaths`

**Files:**
- Modify: `src/behemoth/core/model_registry.py`
- Modify: `tests/test_model_registry.py` (if present)

- [ ] **Step 1: Identify model_binding reads**

```bash
grep -n 'model_binding\|model_cbm_path\|model_threshold_json_path' src/behemoth/core/model_registry.py
```

- [ ] **Step 2: Replace dict reads with `BundlePaths` accessors**

Every call site that today does `binding["model_cbm_path"]` becomes `bp.model_cbm()`. Pass `BundlePaths` through the API the registry exposes instead of the dict. If `model_registry.py` has a `register(symbol, binding)` style entrypoint, change the signature to `register(symbol, bundle_paths: BundlePaths)`.

- [ ] **Step 3: Update tests**

Tests that build a `model_binding` dict fixture now build a `BundlePaths` fixture via `_write_v3_bundle`.

- [ ] **Step 4: Run + commit**

Run: `uv run pytest tests/test_model_registry.py -v`
Expected: PASS.

```bash
git add src/behemoth/core/model_registry.py tests/test_model_registry.py
git commit -m "refactor(governance): model_registry consumes BundlePaths directly"
```

---

## Task 4: Migrate `historical_prediction_stage.py` and `seed_rolling_threshold.py`

Same pattern as Task 3. One file per commit if both have non-trivial diffs.

- [ ] **Step 1: `historical_prediction_stage.py`**

Replace `binding["model_cbm_path"]`, `binding["model_threshold_json_path"]`, `binding["model_month"]` with `bp.model_cbm()`, `bp.model_threshold_json()`, `bp.model_month`. Run `uv run pytest -q tests/ -k "historical_prediction"`.

```bash
git add src/behemoth/core/historical_prediction_stage.py tests/
git commit -m "refactor(governance): historical_prediction_stage consumes BundlePaths"
```

- [ ] **Step 2: `seed_rolling_threshold.py`**

Same pattern. Run `uv run pytest -q tests/ -k "seed_rolling_threshold"`.

```bash
git add scripts/seed_rolling_threshold.py tests/
git commit -m "refactor(governance): seed_rolling_threshold consumes BundlePaths"
```

---

## Task 5: Migrate `api/server.py`

**Files:**
- Modify: `src/behemoth/api/server.py`
- Modify: `tests/test_api_server.py`

The API may serialise `model_binding` in responses. Changing the wire shape is observable to clients.

- [ ] **Step 1: Identify whether `model_binding` is exposed in any HTTP response**

```bash
grep -n 'model_binding\|model_cbm_path\|model_threshold_json_path' src/behemoth/api/server.py
```

- [ ] **Step 2: For internal use, switch to `BundlePaths`. For external responses, keep the JSON shape stable.**

If `model_binding` appears in an API response, **do not break the wire format in this PR**. Build the response dict from `bp` accessors at the response boundary:

```python
def _binding_payload(bp: BundlePaths, lock_data: dict) -> dict[str, Any]:
    artifacts = lock_data.get("artifacts", {})
    return {
        "model_cbm_path":              str(bp.model_cbm()),
        "model_cbm_sha256":            str(artifacts.get("model_cbm", {}).get("sha256", "")),
        "model_threshold_json_path":   str(bp.model_threshold_json()),
        "model_threshold_json_sha256": str(artifacts.get("model_threshold_json", {}).get("sha256", "")),
        "model_month":                 bp.model_month,
    }
```

This pushes the v1-shape dict to the response boundary only — internal flow uses `BundlePaths`.

If `model_binding` is **not** in any HTTP response, just replace dict reads with accessors and delete the construction.

- [ ] **Step 3: Run tests**

Run: `uv run pytest -q tests/test_api_server.py`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add src/behemoth/api/server.py tests/test_api_server.py
git commit -m "refactor(governance): api/server consumes BundlePaths internally"
```

---

## Task 6: Delete `model_binding` from `CandidateContract` and registries

This is the load-bearing change. Only do it after Tasks 3–5 are merged.

**Files:**
- Modify: `src/behemoth/core/governance_lock_loader.py`
- Modify: `src/behemoth/core/registry.py`
- Modify: `src/behemoth/core/historical_registry.py`
- Modify: tests touching `get_model_binding()` or `_model_bindings_by_symbol`.

- [ ] **Step 1: Confirm zero remaining `model_binding` reads**

```bash
grep -rn 'model_binding\|_model_bindings_by_symbol\|get_model_binding' src/ scripts/ tests/ | grep -v __pycache__
```

Expected: zero hits in `src/` and `scripts/`. Only hits inside tests that verify *removal* should remain at the end of this task.

If any consumer still reads `model_binding`, **stop and migrate it before continuing**. Do not add a fallback.

- [ ] **Step 2: Delete the field**

In `CandidateContract`, remove `model_binding`. In `_parse_lock`, remove its construction. In `registry.py` and `historical_registry.py`, replace `_model_bindings_by_symbol: dict[str, dict]` with `_bundle_paths_by_symbol: dict[str, BundlePaths]`. Replace `get_model_binding()` with `get_bundle_paths()`.

- [ ] **Step 3: Delete tests asserting the dict shape**

Tests like `test_model_binding_present` should be rewritten to assert `reg.get_bundle_paths("EURUSD")` returns a `BundlePaths` instance with the right `model_cbm()` path.

- [ ] **Step 4: Run full suite**

Run: `uv run pytest -q`
Expected: PASS.

- [ ] **Step 5: Lint**

Run: `uv run ruff check`
Expected: clean.

- [ ] **Step 6: Final verification grep**

```bash
grep -rn 'model_binding' src/ scripts/ | grep -v __pycache__
```
Expected: empty.

- [ ] **Step 7: Commit**

```bash
git add src tests
git commit -m "refactor(governance): delete model_binding dict; consumers use BundlePaths"
```

---

## Task 7: Open the PR

Use `superpowers:finishing-a-development-branch`. PR title: `refactor(governance): consumers read BundlePaths directly, model_binding removed`.

PR body must note:
- Internal flow no longer constructs `model_binding` dicts.
- If Task 5 kept the dict at the HTTP response boundary, call that out explicitly — anyone wanting to change the response shape now knows where to look.
- Adding a new model artifact in v3 means: add a row to `BUNDLE_LAYOUTS` + add a `BundlePaths` accessor. No translation dict to update.

---

## Notes for the Implementer

- **`BundlePaths` instances are frozen dataclasses.** Passing the same instance through multiple consumers is safe.
- **`bp.model_cbm()` verifies sha256 on every call.** This was the design choice in ADR 0001 — paying the read cost guarantees integrity. If a hot loop becomes a problem, cache via `functools.lru_cache` on a wrapper, but do not introduce a "verified once, trust forever" shortcut.
- **Do not preserve `model_binding` as a deprecated-but-working compat field beyond Task 6.** The whole point of this plan is to delete it. Leaving it accessible means new code will reach for it.
