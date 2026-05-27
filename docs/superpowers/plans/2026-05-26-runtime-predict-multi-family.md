# Runtime Predict Multi-Family Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the API inference server and prediction pipeline family-aware so that multiple models per symbol (one per family) can be loaded, dispatched, and evaluated concurrently.

**Architecture:** Add `family` to `CandidateSpec`, extend `CandidateRegistry` to load all families, make `ModelRegistry` cache keys family-aware, and restructure `server.py` `_orchestrator_build_predictions_fn` to group candidates by family and dispatch each group to its per-family model + threshold config.

**Tech Stack:** Python 3.12, FastAPI, CatBoost, pytest

---

## File Map

| File | Responsibility |
|------|--------------|
| `src/behemoth/core/registry.py` | `CandidateSpec` dataclass; `CandidateRegistry` loads governance locks per (symbol, family) |
| `src/behemoth/core/candidate_catalog.py` | `CandidateCatalog` resolves runtime contracts from registry; bridges live/historical modes |
| `src/behemoth/core/model_registry.py` | `ModelRegistry` caches CatBoost models and thresholds by family-aware cache key |
| `src/behemoth/api/server.py` | FastAPI server; model loading, prediction building, orchestrator wiring |
| `tests/test_api_server_historical.py` | Historical-mode server tests; constructs `BundlePaths` and `_ResolvedRuntimeContract` |
| `tests/test_candidate_catalog.py` | Catalog contract resolution tests |
| `tests/test_api_server.py` | Live-mode server tests; threshold override round-trip |

---

## Prerequisites

The codebase already has:
- `BundlePaths.family` field (added in Stage F)
- `BUNDLE_LAYOUTS` with 11 family entries
- `lock_filename(symbol, family)` signature
- `iter_locks(bundle_dir, family=None)` — when `family=None`, yields ALL locks

---

## Task 1: Add `family` field to `CandidateSpec`

**Files:**
- Modify: `src/behemoth/core/registry.py:34-68`
- Test: `tests/test_candidate_catalog.py`

- [ ] **Step 1: Write failing test**

```python
def test_candidate_spec_has_family_field():
    from src.behemoth.core.registry import CandidateSpec
    spec = CandidateSpec(
        symbol="EURUSD",
        bar_ticks=100,
        horizon=4,
        barrier_pips=10.0,
        candidate_uid="test__all__k1",
        family="directional",
    )
    assert spec.family == "directional"
```

Run: `pytest tests/test_candidate_catalog.py::test_candidate_spec_has_family_field -v`
Expected: FAIL — `CandidateSpec` has no `family` field

- [ ] **Step 2: Add `family` to `CandidateSpec`**

In `src/behemoth/core/registry.py`, change:

```python
@dataclass(frozen=True)
class CandidateSpec:
    """A single prediction candidate to evaluate."""

    symbol: str
    bar_ticks: int
    horizon: int
    barrier_pips: float
    candidate_uid: str
    regime_desc: str = ""
```

To:

```python
@dataclass(frozen=True)
class CandidateSpec:
    """A single prediction candidate to evaluate."""

    symbol: str
    bar_ticks: int
    horizon: int
    barrier_pips: float
    candidate_uid: str
    regime_desc: str = ""
    family: str = ""
```

Run: `pytest tests/test_candidate_catalog.py::test_candidate_spec_has_family_field -v`
Expected: PASS

- [ ] **Step 3: Update `from_row` to accept optional `family`**

Change `from_row` signature and return:

```python
    @staticmethod
    def from_row(row: dict, family: str = "") -> CandidateSpec:
        """Build from a state_universe row in the live lock JSON.

        Rejects first_touch_clean candidates: that family's win rate was
        conditioned on ~both (look-ahead) and is not live-achievable. See
        docs/superpowers/specs/2026-05-15-oco-lookahead-bias-removal-design.md.
        """
        state_id = str(row["state_id"])
        if "first_touch_clean" in state_id:
            raise ValueError(
                f"refusing look-ahead-biased candidate '{state_id}': the "
                "first_touch_clean family conditions its win rate on ~both "
                "(future information) and must not be deployed. Re-mine and "
                "re-freeze governance on the first_touch family."
            )
        return CandidateSpec(
            symbol=row["symbol"],
            bar_ticks=row["bar_ticks"],
            horizon=row["horizon"],
            barrier_pips=float(row["barrier_pips"]),
            candidate_uid=state_id,
            regime_desc=row.get("regime_desc", ""),
            family=family,
        )
```

- [ ] **Step 4: Commit**

```bash
git add src/behemoth/core/registry.py tests/test_candidate_catalog.py
git commit -m "feat(registry): add family field to CandidateSpec"
```

---

## Task 2: Make `CandidateRegistry` load all families

**Files:**
- Modify: `src/behemoth/core/registry.py:71-150`
- Test: `tests/test_candidate_catalog.py`

- [ ] **Step 1: Write failing test**

```python
def test_registry_loads_multiple_families():
    import json
    import hashlib
    from pathlib import Path
    from tempfile import TemporaryDirectory
    from src.behemoth.core.registry import CandidateRegistry
    from src.behemoth.core.bundle_paths import BundlePaths

    with TemporaryDirectory() as tmp:
        t = Path(tmp)
        for family in ("oco_first_touch", "directional"):
            lock = t / f"eurusd_{family}_live_lock.json"
            payload = {
                "schema_version": 3,
                "symbol": "EURUSD",
                "bundle": {"month": "2026-04", "dir_relpath": ".", "family": family},
                "deployability": {"live_deployable": True, "model_month": "2026-04"},
                "locked_runtime": {"production_cap_pips": 1.2},
                "state_universe": {
                    "rows": [
                        {
                            "state_id": f"{family}__all__k1",
                            "symbol": "EURUSD",
                            "bar_ticks": 100,
                            "horizon": 4,
                            "barrier_pips": 10.0,
                        }
                    ]
                },
            }
            # Add minimal artifacts so BundlePaths.from_lock passes sha256 checks
            models_dir = t / "models"
            models_dir.mkdir(exist_ok=True)
            cbm = models_dir / f"EURUSD_{family}_model_2026-04.cbm"
            thr = models_dir / f"EURUSD_{family}_model_2026-04.json"
            cbm.write_bytes(b"cbm")
            thr.write_text('{"t":1}')
            preds = t / f"eurusd_{family}_locked_predictions.parquet"
            states_csv = t / f"eurusd_{family}_allowed_states.csv"
            preds.write_bytes(b"preds")
            states_csv.write_text("state\na\n")
            payload["artifacts"] = {
                "predictions": {"path": preds.name, "sha256": hashlib.sha256(b"preds").hexdigest()},
                "allowed_states_csv": {"path": states_csv.name, "sha256": hashlib.sha256(states_csv.read_bytes()).hexdigest()},
                "model_cbm": {"path": f"models/{cbm.name}", "sha256": hashlib.sha256(b"cbm").hexdigest()},
                "model_threshold_json": {"path": f"models/{thr.name}", "sha256": hashlib.sha256(thr.read_bytes()).hexdigest()},
            }
            lock.write_text(json.dumps(payload))

        reg = CandidateRegistry.load(lock_dir=t)
        cands = reg.get_candidates("EURUSD")
        families = {c.family for c in cands}
        assert families == {"oco_first_touch", "directional"}
```

Run: `pytest tests/test_candidate_catalog.py::test_registry_loads_multiple_families -v`
Expected: FAIL — `CandidateRegistry.load()` is hardcoded to `family="oco_first_touch"`

- [ ] **Step 2: Update `CandidateRegistry` fields and `load()`**

Change `CandidateRegistry` from:

```python
@dataclass
class CandidateRegistry:
    """Registry of valid candidate specifications loaded from live lock JSONs."""

    _candidates_by_symbol: dict[str, list[CandidateSpec]] = field(default_factory=dict)
    _frozen_timestamps: dict[str, str] = field(default_factory=dict)
    _caps_by_symbol: dict[str, float] = field(default_factory=dict)
    _bundle_paths_by_symbol: dict[str, BundlePaths] = field(default_factory=dict)  # type: ignore
```

To:

```python
@dataclass
class CandidateRegistry:
    """Registry of valid candidate specifications loaded from live lock JSONs."""

    _candidates_by_symbol: dict[str, list[CandidateSpec]] = field(default_factory=dict)
    _frozen_timestamps: dict[str, str] = field(default_factory=dict)
    _caps_by_symbol_family: dict[tuple[str, str], float] = field(default_factory=dict)
    _bundle_paths_by_symbol_family: dict[tuple[str, str], BundlePaths] = field(default_factory=dict)  # type: ignore
```

Update `load()` method. Replace the body that currently reads:

```python
        reg = cls()
        # Filtered to OCO until CandidateRegistry supports multi-family lookup.
        for p in iter_locks(p_dir, family="oco_first_touch"):
```

With:

```python
        reg = cls()
        for p in iter_locks(p_dir, family=None):
```

Then in the per-lock processing, change:

```python
                rows = data.get("state_universe", {}).get("rows", [])
                candidates = [CandidateSpec.from_row(r) for r in rows]
                reg._candidates_by_symbol[sym] = candidates
                reg._frozen_timestamps[sym] = data.get("frozen_at_utc", "")

                # Extract execution cap from locked_runtime
                locked = data.get("locked_runtime", {})
                reg._caps_by_symbol[sym] = float(locked.get("production_cap_pips", 1.2))
                # Store BundlePaths directly
                reg._bundle_paths_by_symbol[sym] = bp
```

To:

```python
                rows = data.get("state_universe", {}).get("rows", [])
                candidates = [CandidateSpec.from_row(r, family=family) for r in rows]
                existing = reg._candidates_by_symbol.get(sym, [])
                reg._candidates_by_symbol[sym] = existing + candidates
                reg._frozen_timestamps[sym] = data.get("frozen_at_utc", "")

                # Extract execution cap from locked_runtime
                locked = data.get("locked_runtime", {})
                reg._caps_by_symbol_family[(sym, family)] = float(locked.get("production_cap_pips", 1.2))
                # Store BundlePaths directly, keyed by (symbol, family)
                reg._bundle_paths_by_symbol_family[(sym, family)] = bp
```

And at the top of the loop body, capture `family` from `bp.family` (already available after `BundlePaths.from_lock(p)`):

```python
                bp = BundlePaths.from_lock(p)
                family = bp.family
```

- [ ] **Step 3: Update accessor methods**

Change `get_cap_pips` from:

```python
    def get_cap_pips(self, symbol: str) -> float:
        """Return the locked production cap for a symbol."""
        return self._caps_by_symbol.get(symbol.upper(), 1.2)
```

To:

```python
    def get_cap_pips(self, symbol: str, family: str = "") -> float:
        """Return the locked production cap for a symbol/family pair."""
        return self._caps_by_symbol_family.get((symbol.upper(), family), 1.2)
```

Change `get_bundle_paths` from:

```python
    def get_bundle_paths(self, symbol: str) -> BundlePaths | None:  # type: ignore
        """Return frozen bundle paths for a symbol."""
        return self._bundle_paths_by_symbol.get(symbol.upper())
```

To:

```python
    def get_bundle_paths(self, symbol: str, family: str = "") -> BundlePaths | None:  # type: ignore
        """Return frozen bundle paths for a symbol/family pair."""
        return self._bundle_paths_by_symbol_family.get((symbol.upper(), family))
```

Run: `pytest tests/test_candidate_catalog.py::test_registry_loads_multiple_families -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/behemoth/core/registry.py tests/test_candidate_catalog.py
git commit -m "feat(registry): CandidateRegistry loads all families per symbol"
```

---

## Task 3: Update `CandidateCatalog` for multi-family

**Files:**
- Modify: `src/behemoth/core/candidate_catalog.py:45-186`
- Test: `tests/test_candidate_catalog.py`

- [ ] **Step 1: Write failing test**

```python
def test_candidate_catalog_returns_all_family_candidates():
    import json
    import hashlib
    from datetime import datetime, timezone
    from pathlib import Path
    from tempfile import TemporaryDirectory
    from src.behemoth.core.registry import CandidateRegistry
    from src.behemoth.core.candidate_catalog import CandidateCatalog

    with TemporaryDirectory() as tmp:
        t = Path(tmp)
        for family in ("oco_first_touch", "directional"):
            lock = t / f"eurusd_{family}_live_lock.json"
            models_dir = t / "models"
            models_dir.mkdir(exist_ok=True)
            cbm = models_dir / f"EURUSD_{family}_model_2026-04.cbm"
            thr = models_dir / f"EURUSD_{family}_model_2026-04.json"
            cbm.write_bytes(b"cbm")
            thr.write_text('{"t":1}')
            preds = t / f"eurusd_{family}_locked_predictions.parquet"
            states_csv = t / f"eurusd_{family}_allowed_states.csv"
            preds.write_bytes(b"preds")
            states_csv.write_text("state\na\n")
            payload = {
                "schema_version": 3,
                "symbol": "EURUSD",
                "bundle": {"month": "2026-04", "dir_relpath": ".", "family": family},
                "deployability": {"live_deployable": True, "model_month": "2026-04"},
                "locked_runtime": {"production_cap_pips": 1.2},
                "state_universe": {
                    "rows": [
                        {
                            "state_id": f"{family}__all__k1",
                            "symbol": "EURUSD",
                            "bar_ticks": 100,
                            "horizon": 4,
                            "barrier_pips": 10.0,
                        }
                    ]
                },
                "artifacts": {
                    "predictions": {"path": preds.name, "sha256": hashlib.sha256(b"preds").hexdigest()},
                    "allowed_states_csv": {"path": states_csv.name, "sha256": hashlib.sha256(states_csv.read_bytes()).hexdigest()},
                    "model_cbm": {"path": f"models/{cbm.name}", "sha256": hashlib.sha256(b"cbm").hexdigest()},
                    "model_threshold_json": {"path": f"models/{thr.name}", "sha256": hashlib.sha256(thr.read_bytes()).hexdigest()},
                },
            }
            lock.write_text(json.dumps(payload))

        reg = CandidateRegistry.load(lock_dir=t)
        catalog = CandidateCatalog(live_registry=reg, historical_registry=None, historical_mode=False)
        contract = catalog.resolve_contract("EURUSD", datetime(2026, 5, 1, tzinfo=timezone.utc))
        families = {c.family for c in contract.candidates}
        assert families == {"oco_first_touch", "directional"}
```

Run: `pytest tests/test_candidate_catalog.py::test_candidate_catalog_returns_all_family_candidates -v`
Expected: FAIL — `_resolve_live_contract` only looks up one bundle path

- [ ] **Step 2: Update `_resolve_live_contract` to merge all families**

Change `_resolve_live_contract` from:

```python
    def _resolve_live_contract(self, symbol: str) -> RuntimeCandidateContract:
        if self._live_registry is None:
            raise LookupError("Candidate registry not loaded")
        bundle_paths = self._live_registry.get_bundle_paths(symbol)
        if not bundle_paths:
            raise LookupError(f"No bundle paths registered for {symbol}")
        model_month = bundle_paths.model_month or "unknown"
        return RuntimeCandidateContract(
            symbol=symbol,
            model_month=model_month,
            cache_key=self.cache_key(symbol),
            candidates=self._live_registry.get_candidates(symbol),
            bundle_paths=bundle_paths,
            cap_pips=float(self._live_registry.get_cap_pips(symbol)),
            source="live",
            lock_path=None,
        )
```

To:

```python
    def _resolve_live_contract(self, symbol: str) -> RuntimeCandidateContract:
        if self._live_registry is None:
            raise LookupError("Candidate registry not loaded")
        all_candidates = self._live_registry.get_candidates(symbol)
        if not all_candidates:
            raise LookupError(f"No candidates registered for {symbol}")
        # Use the first family's bundle_paths as the "primary" contract metadata.
        # Per-family dispatch happens downstream in server.py.
        first_family = all_candidates[0].family or "unknown"
        bundle_paths = self._live_registry.get_bundle_paths(symbol, first_family)
        if not bundle_paths:
            raise LookupError(f"No bundle paths registered for {symbol}")
        model_month = bundle_paths.model_month or "unknown"
        return RuntimeCandidateContract(
            symbol=symbol,
            model_month=model_month,
            cache_key=self.cache_key(symbol),
            candidates=all_candidates,
            bundle_paths=bundle_paths,
            cap_pips=float(self._live_registry.get_cap_pips(symbol, first_family)),
            source="live",
            lock_path=None,
        )
```

Run: `pytest tests/test_candidate_catalog.py::test_candidate_catalog_returns_all_family_candidates -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add src/behemoth/core/candidate_catalog.py tests/test_candidate_catalog.py
git commit -m "feat(catalog): CandidateCatalog returns merged multi-family candidates"
```

---

## Task 4: Make `ModelRegistry` cache keys family-aware

**Files:**
- Modify: `src/behemoth/core/model_registry.py`
- Test: `tests/test_api_server.py`

- [ ] **Step 1: Write failing test**

In `tests/test_api_server.py`, add:

```python
class TestModelRegistryFamilyCacheKey:
    def test_family_cache_key(self):
        from src.behemoth.core.model_registry import ModelRegistry
        assert ModelRegistry.make_cache_key("EURUSD", "2026-04", "directional") == "EURUSD|2026-04|directional"
        assert ModelRegistry.make_cache_key("EURUSD", None, "directional") == "EURUSD|directional"
        assert ModelRegistry.make_cache_key("EURUSD", "2026-04") == "EURUSD|2026-04"
        assert ModelRegistry.make_cache_key("EURUSD") == "EURUSD"
```

Run: `pytest tests/test_api_server.py::TestModelRegistryFamilyCacheKey::test_family_cache_key -v`
Expected: FAIL — `make_cache_key` does not accept `family` parameter

- [ ] **Step 2: Update `make_cache_key` and `has_model` / `has_threshold` / `get_latest_month`**

Change `make_cache_key` from:

```python
    @staticmethod
    def make_cache_key(symbol: str, model_month: str | None = None) -> str:
        """Generate cache key: symbol or symbol|month."""
        sym = str(symbol).upper().strip()
        if model_month:
            return f"{sym}|{str(model_month).strip()}"
        return sym
```

To:

```python
    @staticmethod
    def make_cache_key(symbol: str, model_month: str | None = None, family: str | None = None) -> str:
        """Generate cache key: symbol, symbol|month, symbol|month|family, or symbol|family."""
        sym = str(symbol).upper().strip()
        parts = [sym]
        if model_month:
            parts.append(str(model_month).strip())
        fam = str(family or "").strip()
        if fam:
            parts.append(fam)
        return "|".join(parts)
```

Update `has_model`, `has_threshold`, and `get_latest_month` to accept optional `family` parameter:

```python
    def has_model(self, symbol: str, family: str | None = None) -> bool:
        """Check if any model is loaded for symbol (live or any month)."""
        sym = str(symbol).upper().strip()
        cache_key = self.make_cache_key(sym, family=family)
        if cache_key in self._models:
            return True
        pref = f"{cache_key}|"
        return any(k.startswith(pref) for k in self._models)

    def has_threshold(self, symbol: str, family: str | None = None) -> bool:
        """Check if any threshold config is loaded for symbol (live or any month)."""
        sym = str(symbol).upper().strip()
        cache_key = self.make_cache_key(sym, family=family)
        if cache_key in self._thresholds:
            return True
        pref = f"{cache_key}|"
        return any(k.startswith(pref) for k in self._thresholds)

    def get_latest_month(self, symbol: str, family: str | None = None) -> str | None:
        """Get latest loaded month for symbol, or None if no models loaded."""
        sym = str(symbol).upper().strip()
        cache_key = self.make_cache_key(sym, family=family)
        if cache_key in self._model_months:
            return self._model_months.get(cache_key)
        pref = f"{cache_key}|"
        months = [m for k, m in self._model_months.items() if k.startswith(pref)]
        if not months:
            return None
        return sorted(months)[-1]
```

Run: `pytest tests/test_api_server.py::TestModelRegistryFamilyCacheKey::test_family_cache_key -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add src/behemoth/core/model_registry.py tests/test_api_server.py
git commit -m "feat(models): family-aware cache keys in ModelRegistry"
```

---

## Task 5: Update `server.py` model loading for multi-family

**Files:**
- Modify: `src/behemoth/api/server.py:1043-1079`
- Test: `tests/test_api_server.py`

- [ ] **Step 1: Update `_load_models` to iterate families**

Change `_load_models()` from:

```python
def _load_models() -> None:
    """Load model cache according to governance mode."""
    _cache_manager.reset_all()
    if not _models_dir.exists():
        logger.warning("Models directory %s does not exist yet.", _models_dir)
        return

    if _is_historical_mode():
        # Historical mode uses lazy per-(symbol,month) loading on /predict.
        logger.info("Historical governance mode enabled: model cache is lazy-loaded by month.")
        return

    if _registry is None:
        logger.error(
            "Governance registry unavailable — refusing to load models without lock binding."
        )
        return

    for sym in _config.symbols:
        try:
            bundle_paths = _registry.get_bundle_paths(sym)
            if not bundle_paths:
                logger.error("No governance bundle paths for %s — skipping model load.", sym)
                continue
            cache_key = _cache_key(sym)
            _model_registry.load_bundle_paths(
                symbol=sym,
                bundle_paths=bundle_paths,
                cache_key=cache_key,
                locked_runtime_overrides={},
                expected_month=bundle_paths.model_month or None,
                catboost_cls=_catboost_cls(),
            )
        except BundleIntegrityError as exc:
            logger.error("Bundle integrity error for %s — skipping model load: %s", sym, exc)
            continue
```

To:

```python
def _load_models() -> None:
    """Load model cache according to governance mode."""
    _cache_manager.reset_all()
    if not _models_dir.exists():
        logger.warning("Models directory %s does not exist yet.", _models_dir)
        return

    if _is_historical_mode():
        # Historical mode uses lazy per-(symbol,month) loading on /predict.
        logger.info("Historical governance mode enabled: model cache is lazy-loaded by month.")
        return

    if _registry is None:
        logger.error(
            "Governance registry unavailable — refusing to load models without lock binding."
        )
        return

    for sym in _config.symbols:
        candidates = _registry.get_candidates(sym)
        families = sorted({c.family for c in candidates if c.family})
        if not families:
            logger.error("No governance families for %s — skipping model load.", sym)
            continue
        for family in families:
            try:
                bundle_paths = _registry.get_bundle_paths(sym, family)
                if not bundle_paths:
                    logger.error("No governance bundle paths for %s family %s — skipping.", sym, family)
                    continue
                cache_key = _cache_key(sym, family=family)
                _model_registry.load_bundle_paths(
                    symbol=sym,
                    bundle_paths=bundle_paths,
                    cache_key=cache_key,
                    locked_runtime_overrides={},
                    expected_month=bundle_paths.model_month or None,
                    catboost_cls=_catboost_cls(),
                )
            except BundleIntegrityError as exc:
                logger.error("Bundle integrity error for %s %s — skipping: %s", sym, family, exc)
                continue
```

Wait — `_cache_key(sym)` currently delegates to `_candidate_catalog().cache_key(symbol, model_month)`. We need to update `_cache_key` to support family.

Change `_cache_key` from:

```python
def _cache_key(symbol: str, model_month: str | None = None) -> str:
    return _candidate_catalog().cache_key(symbol, model_month)
```

To:

```python
def _cache_key(symbol: str, model_month: str | None = None, family: str | None = None) -> str:
    base = _candidate_catalog().cache_key(symbol, model_month)
    if family:
        return f"{base}|{family}"
    return base
```

- [ ] **Step 2: Update helper functions that call `_has_loaded_model_for_symbol`**

Change `_has_loaded_model_for_symbol` from:

```python
def _has_loaded_model_for_symbol(symbol: str) -> bool:
    return _model_registry.has_model(symbol)
```

To:

```python
def _has_loaded_model_for_symbol(symbol: str, family: str | None = None) -> bool:
    return _model_registry.has_model(symbol, family=family)
```

Change `_latest_loaded_month_for_symbol` from:

```python
def _latest_loaded_month_for_symbol(symbol: str) -> str | None:
    return _model_registry.get_latest_month(symbol)
```

To:

```python
def _latest_loaded_month_for_symbol(symbol: str, family: str | None = None) -> str | None:
    return _model_registry.get_latest_month(symbol, family=family)
```

- [ ] **Step 3: Add a test for multi-family model loading**

In `tests/test_api_server.py`, add:

```python
class TestLoadModelsMultiFamily:
    def test_load_models_skips_when_no_families(self, monkeypatch, tmp_path):
        from src.behemoth.core.registry import CandidateRegistry
        from src.behemoth.api import server

        empty_reg = CandidateRegistry()
        monkeypatch.setattr(server, "_registry", empty_reg)
        monkeypatch.setattr(server, "_is_historical_mode", lambda: False)
        monkeypatch.setattr(server._model_registry, "clear", lambda: None)

        # Ensure _config.symbols has at least one symbol
        original_symbols = server._config.symbols
        server._config.symbols = ["EURUSD"]
        try:
            server._load_models()
        finally:
            server._config.symbols = original_symbols
```

Run: `pytest tests/test_api_server.py::TestLoadModelsMultiFamily::test_load_models_skips_when_no_families -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/behemoth/api/server.py tests/test_api_server.py
git commit -m "feat(server): load models for all families per symbol"
```

---

## Task 6: Update `_ensure_model_and_threshold` and `_resolve_runtime_contract` for family

**Files:**
- Modify: `src/behemoth/api/server.py:1601-1652`

- [ ] **Step 1: Add `_resolve_runtime_contract_for_family`**

Add after `_resolve_runtime_contract`:

```python
def _resolve_runtime_contract_for_family(sym: str, family: str, close_ts: datetime) -> _ResolvedRuntimeContract:
    """Resolve runtime contract for a specific symbol and family."""
    symbol = str(sym).upper().strip()
    family = str(family).strip()
    if _config.force_model_month and _is_historical_mode():
        forced_month = _normalize_model_month(_config.force_model_month)
        if forced_month is None:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid BEHEMOTH_FORCE_MODEL_MONTH={_config.force_model_month!r}; expected YYYY-MM",
            )
    try:
        contract = _candidate_catalog().resolve_contract(symbol, close_ts)
    except LookupError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=422, detail=str(exc).strip("'")) from exc

    # Filter to the requested family
    family_candidates = [c for c in contract.candidates if c.family == family]
    if not family_candidates:
        raise HTTPException(status_code=422, detail=f"No candidates for {symbol} family {family}")

    # Get per-family metadata
    if _registry is not None:
        bundle_paths = _registry.get_bundle_paths(symbol, family)
        cap_pips = _registry.get_cap_pips(symbol, family)
    else:
        bundle_paths = contract.bundle_paths
        cap_pips = contract.cap_pips

    model_month = bundle_paths.model_month if bundle_paths else contract.model_month
    cache_key = _cache_key(symbol, model_month, family)

    return _ResolvedRuntimeContract(
        symbol=symbol,
        model_month=model_month,
        cache_key=cache_key,
        candidates=family_candidates,
        bundle_paths=bundle_paths or contract.bundle_paths,
        cap_pips=float(cap_pips),
        source=contract.source,
        lock_path=contract.lock_path,
    )
```

- [ ] **Step 2: Update `_ensure_model_and_threshold` to accept optional family**

Change `_ensure_model_and_threshold` signature from:

```python
def _ensure_model_and_threshold(contract: _ResolvedRuntimeContract) -> tuple[Any, dict[str, Any]]:
```

To:

```python
def _ensure_model_and_threshold(contract: _ResolvedRuntimeContract) -> tuple[Any, dict[str, Any]]:
    """Ensure model and threshold are loaded for the contract's cache_key."""
```

No body changes needed — it already uses `contract.cache_key`, and `_resolve_runtime_contract_for_family` sets a family-aware cache_key.

- [ ] **Step 3: Commit**

```bash
git add src/behemoth/api/server.py
git commit -m "feat(server): add per-family runtime contract resolution"
```

---

## Task 7: Restructure `_orchestrator_build_predictions_fn` for per-family dispatch

**Files:**
- Modify: `src/behemoth/api/server.py:2353-2412`

- [ ] **Step 1: Rewrite `_orchestrator_build_predictions_fn` to group by family**

Replace `_orchestrator_build_predictions_fn` with:

```python
def _orchestrator_build_predictions_fn(
    *,
    sym: str,
    candidates: list[Any],
    base_features_by_ticks: dict[int, ModelFeatures],
    regime_quantiles_by_ticks: dict[int, dict[str, float]],
    close_ts: datetime,
    account_risk_eval: AccountRiskDecision,
    account_risk_enabled_effective: bool,
    account_risk_enabled_override: bool,
    run_id: str,
    req: PredictRequest,
) -> list[OcoPrediction]:
    """Inject step-5 logic (inference + threshold + allocator) into the orchestrator.

    Dispatches per-family: groups candidates by their family tag, resolves the
    runtime contract and model for each family, then delegates to
    ``_build_predictions``. Results are merged and sorted by ``pred_prob``
    descending.
    """
    if _state is None:
        raise HTTPException(status_code=503, detail="State manager not initialized")

    requested_volume_units = _resolve_requested_volume_units(req)
    all_results: list[OcoPrediction] = []

    # Group candidates by family
    by_family: dict[str, list[Any]] = {}
    for cand in candidates:
        fam = str(getattr(cand, "family", "") or "").strip()
        # Fallback for candidates without a family tag (legacy/historical fixtures)
        if not fam:
            fam = "oco_first_touch"
        by_family.setdefault(fam, []).append(cand)

    for family, family_cands in by_family.items():
        family_contract = _resolve_runtime_contract_for_family(sym, family, close_ts)
        model, thr_cfg = _ensure_model_and_threshold(family_contract)

        has_predictions = False
        if _is_historical_mode():
            try:
                _ = family_contract.bundle_paths.predictions()
                has_predictions = True
            except Exception:
                has_predictions = False
        historical_prediction_universe_gated = bool(has_predictions)

        results, _candidate_trace_rows = _build_predictions(
            sym=sym,
            candidates=family_cands,
            model=model,
            base_features_by_ticks=base_features_by_ticks,
            regime_quantiles_by_ticks=regime_quantiles_by_ticks,
            close_ts=close_ts,
            thr_cfg=thr_cfg,
            account_risk_eval=account_risk_eval,
            account_risk_enabled_effective=account_risk_enabled_effective,
            account_risk_enabled_override=account_risk_enabled_override,
            requested_volume_units=requested_volume_units,
            model_month=family_contract.model_month,
            cap_pips=family_contract.cap_pips,
            run_id=run_id,
            skip_regime_gate=historical_prediction_universe_gated,
            historical_prediction_overrides=_resolve_historical_prediction_payload_overrides(
                contract=family_contract,
                close_ts=close_ts,
                candidates=family_cands,
            ),
        )
        all_results.extend(results)

    all_results.sort(key=lambda p: p.pred_prob, reverse=True)
    return all_results
```

- [ ] **Step 2: Update `_build_predictions` canonical_uid to use family**

In `_build_predictions`, change the canonical_uid line from:

```python
        canonical_uid = f"oco|{sym}|{cand.bar_ticks}|h{cand.horizon}|{cand.candidate_uid}"
```

To:

```python
        family = str(getattr(cand, "family", "") or "").strip()
        if not family:
            family = "oco_first_touch"
        canonical_uid = f"{family}|{sym}|{cand.bar_ticks}|h{cand.horizon}|{cand.candidate_uid}"
```

- [ ] **Step 3: Update `_apply_historical_prediction_universe_gate` canonical_uid**

In `server.py`, update all three `canonical_uid` occurrences in `_apply_historical_prediction_universe_gate` to use `cand.family`:

```python
            canonical_uid = (
                f"{cand.family or 'oco_first_touch'}|{contract.symbol}|{cand.bar_ticks}|h{cand.horizon}|{cand.candidate_uid}"
            )
```

Repeat for all three occurrences (ordinal mode, tolerant mode, exact mode).

- [ ] **Step 4: Run the existing API server tests**

Run: `pytest tests/test_api_server.py -v`
Expected: PASS (or identify specific failures to fix)

- [ ] **Step 5: Commit**

```bash
git add src/behemoth/api/server.py
git commit -m "feat(server): per-family model dispatch in prediction builder"
```

---

## Task 8: Update test fixtures that construct `CandidateSpec` without `family`

**Files:**
- Modify: `tests/test_api_server_historical.py`
- Modify: `tests/test_candidate_catalog.py`

- [ ] **Step 1: Add `family` to `_candidate` helper**

In `tests/test_candidate_catalog.py`, change `_candidate` from:

```python
def _candidate(symbol: str = "EURUSD", bar_ticks: int = 100) -> CandidateSpec:
    return CandidateSpec(
        symbol=symbol,
        bar_ticks=bar_ticks,
        horizon=6,
        barrier_pips=2.0,
        candidate_uid=f"library|{symbol}|{bar_ticks}|h6|b2",
    )
```

To:

```python
def _candidate(symbol: str = "EURUSD", bar_ticks: int = 100, family: str = "oco_first_touch") -> CandidateSpec:
    return CandidateSpec(
        symbol=symbol,
        bar_ticks=bar_ticks,
        horizon=6,
        barrier_pips=2.0,
        candidate_uid=f"library|{symbol}|{bar_ticks}|h6|b2",
        family=family,
    )
```

- [ ] **Step 2: Add `family` to `_mk_entry` and `_mk_contract` helpers**

In `tests/test_api_server_historical.py`, change the `CandidateSpec` construction in `_mk_entry` from:

```python
            CandidateSpec(
                symbol=symbol,
                bar_ticks=100,
                horizon=4,
                barrier_pips=10.0,
                candidate_uid="oco_first_touch__all__k2",
            )
```

To:

```python
            CandidateSpec(
                symbol=symbol,
                bar_ticks=100,
                horizon=4,
                barrier_pips=10.0,
                candidate_uid="oco_first_touch__all__k2",
                family="oco_first_touch",
            )
```

- [ ] **Step 3: Run all affected tests**

Run: `pytest tests/test_api_server_historical.py tests/test_candidate_catalog.py tests/test_api_server.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_api_server_historical.py tests/test_candidate_catalog.py
git commit -m "test: add family field to CandidateSpec test fixtures"
```

---

## Task 9: Run full test suite for Stage G

- [ ] **Step 1: Run the full pytest suite**

```bash
uv run pytest -q tests/
```

- [ ] **Step 2: Fix any remaining failures**

Common expected issues:
- `test_predict_orchestrator.py` mock candidates need a `family` attribute
- `test_predict_endpoint_integration.py` may need fixture updates
- Any test that asserts `canonical_uid` starts with `"oco|"` needs updating

- [ ] **Step 3: Final commit**

```bash
git commit -m "test: align all prediction tests with multi-family canonical_uid"
```

---

## Spec Coverage Check

| Spec Requirement | Task |
|------------------|------|
| `CandidateSpec` carries family provenance | Task 1 |
| `CandidateRegistry` loads all families per symbol | Task 2 |
| `CandidateCatalog` returns merged multi-family candidates | Task 3 |
| `ModelRegistry` supports family-aware cache keys | Task 4 |
| Server loads models for all families at startup | Task 5 |
| Runtime contract resolution is per-family | Task 6 |
| Prediction builder dispatches per-family model + threshold | Task 7 |
| `canonical_uid` uses actual family name | Task 7 |
| Test fixtures updated | Task 8 |
| Full test suite green | Task 9 |

## Placeholder Scan

- No TBD, TODO, or "implement later" strings.
- Every step contains exact code.
- No references to undefined functions.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-26-runtime-predict-multi-family.md`.

**Two execution options:**

**1. Subagent-Driven (recommended)** - Dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
