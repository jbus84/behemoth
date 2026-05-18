# Double-Touch / Liquidity Sweep Family — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `double_touch` mining family that detects an A→B price sweep (stop-hunt / false breakout) and scores continuation past B against the random-entry baseline.

**Architecture:** A new vectorised two-stage touch engine (`_double_touch_precompute`) finds, per regime entry bar `i0`, a first A-barrier touch within `window_A` bars, then a first opposite-direction B-barrier touch within `window_B` bars of the A-touch. A `DoubleTouchFamily` implementing the existing `MiningFamily` protocol wraps it, with the same per-frame precompute cache the OCO families use. Its candidate rows are signed-return outcomes, so they fold into the `directional` output frame.

**Tech Stack:** Python, NumPy, pandas, pytest. Follows `scripts/mining_family.py` + `scripts/run_tick_opportunity_mining.py`.

**Base-state assumption:** This plan assumes PR #188 (sub-projects 1–2: `oco_asymmetric`, `directional_run`, the `_frame_fingerprint` precompute cache, and the `{directional, directional_run}` merge branch) is **merged to main**. Cut the execution worktree from `main` after #188 lands. Spec: `docs/superpowers/specs/2026-05-18-double-touch-sweep-design.md`.

---

### Task 1: `_double_touch_precompute` two-stage sweep engine

**Files:**
- Modify: `scripts/run_tick_opportunity_mining.py` (add function immediately after `_run_length`)
- Modify: `tests/test_tick_opportunity_mining.py` (add builder + tests; extend the import from `scripts.run_tick_opportunity_mining`)

- [ ] **Step 1: Add the test frame builder and the first failing test**

In `tests/test_tick_opportunity_mining.py`, add `_double_touch_precompute` to the existing import block from `scripts.run_tick_opportunity_mining` (it currently imports `_oco_asymmetric_precompute`, `_oco_precompute_candidates`, `run`). Then append:

```python
def _build_sweep_frame(n: int = 600) -> pd.DataFrame:
    """Steady downtrend with single-bar up-blips every 25 bars. A regime bar
    just before a blip sees an up-A barrier touched (the blip), then price
    drops back through the down-B barrier on the next bar, and the downtrend
    is the continuation. Deterministic — used to assert a sweep is detected."""
    pip = 0.0001
    drift = 1.20000 - 0.5 * pip * np.arange(n)
    blip = np.where(np.arange(n) % 25 == 1, 5.0 * pip, 0.0)
    close = drift + blip
    spread = 0.2 * pip
    return pd.DataFrame({
        "close_bid": close,
        "close_ask": close + spread,
        "low_bid": close - 0.3 * pip,
        "high_ask": close + spread + 0.3 * pip,
    })


def _build_flat_frame(n: int = 300) -> pd.DataFrame:
    """Constant price — no barrier is ever touched, so no sweep completes."""
    pip = 0.0001
    close = np.full(n, 1.20000)
    spread = 0.2 * pip
    return pd.DataFrame({
        "close_bid": close,
        "close_ask": close + spread,
        "low_bid": close - 0.1 * pip,
        "high_ask": close + spread + 0.1 * pip,
    })


def test_double_touch_precompute_detects_up_sweep() -> None:
    frame = _build_sweep_frame()
    out = _double_touch_precompute(
        frame, symbol="EURUSD", sweep_dir="up",
        a_pips=3.0, b_pips=3.0, window_A=5, window_B=5, h2=5,
    )
    assert out, "engine should return a populated dict for a long-enough frame"
    decided = np.asarray(out["decided"], dtype=bool)
    gross = np.asarray(out["gross"], dtype=float)
    assert decided.sum() > 0, "at least one A->B sweep should complete"
    # Up-sweep bets short; the downtrend continuation makes that profitable.
    assert np.nanmean(gross) > 0.0
    # Diagnostics are -1 where the leg did not fire, >=1 where it did.
    t_a = np.asarray(out["t_a_step"], dtype=np.int64)
    t_b = np.asarray(out["t_b_step"], dtype=np.int64)
    assert (t_a[decided] >= 1).all() and (t_b[decided] >= 1).all()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_tick_opportunity_mining.py::test_double_touch_precompute_detects_up_sweep -v`
Expected: FAIL with `ImportError` / `cannot import name '_double_touch_precompute'`.

- [ ] **Step 3: Implement `_double_touch_precompute`**

In `scripts/run_tick_opportunity_mining.py`, add this function immediately after `_run_length` (after its `return run_len, sign` line, before `_assign_quality_tier`):

```python
def _double_touch_precompute(
    frame: pd.DataFrame,
    *,
    symbol: str,
    sweep_dir: str,
    a_pips: float,
    b_pips: float,
    window_A: int,
    window_B: int,
    h2: int,
) -> dict[str, np.ndarray]:
    """Anchored two-stage sweep engine.

    For each regime entry bar i0: place an A-barrier a_pips in the sweep_dir
    direction from i0's signal close; find the first touch within window_A
    bars (tA). Then place a B-barrier b_pips in the OPPOSITE direction from
    the A-barrier price; find the first touch within window_B bars of tA
    (tB). Continuation gross is the signed h2-bar return from tB in the
    B-direction. Look-ahead-free: entry conditioning is i0 only; tA, tB and
    the continuation window are all strictly forward of i0.
    """
    load_bar_frame(
        frame,
        required=["close_bid", "low_bid", "high_ask", "close_ask"],
    )
    close_bid = pd.to_numeric(frame["close_bid"], errors="coerce").to_numpy(dtype=float)
    low_bid = pd.to_numeric(frame["low_bid"], errors="coerce").to_numpy(dtype=float)
    high_ask = pd.to_numeric(frame["high_ask"], errors="coerce").to_numpy(dtype=float)
    close_ask = pd.to_numeric(frame["close_ask"], errors="coerce").to_numpy(dtype=float)

    wA, wB, h = int(window_A), int(window_B), int(h2)
    n = len(frame)
    n_eff = n - (wA + wB + h)
    if n_eff <= 100:
        return {}

    pip = float(_pip_size(symbol))
    up = str(sweep_dir).strip().lower() == "up"

    i0 = np.arange(n_eff, dtype=np.int64)
    sig = close_ask[i0] if up else close_bid[i0]
    valid = np.isfinite(sig)
    i0 = i0[valid]
    sig = sig[valid]

    # Stage 1: A-barrier in the sweep direction.
    a_price = sig + a_pips * pip if up else sig - a_pips * pip
    inf_a = wA + 1
    a_step = np.full(len(i0), inf_a, dtype=np.int32)
    for s in range(1, wA + 1):
        idx = i0 + int(s)
        hit = high_ask[idx] >= a_price if up else low_bid[idx] <= a_price
        first = (a_step == inf_a) & hit
        a_step[first] = int(s)
    a_touched = a_step <= wA
    tA = i0 + a_step.astype(np.int64)

    # Stage 2: B-barrier b_pips OPPOSITE the A-barrier price.
    b_price = a_price - b_pips * pip if up else a_price + b_pips * pip
    inf_b = wB + 1
    b_step = np.full(len(i0), inf_b, dtype=np.int32)
    for s in range(1, wB + 1):
        idx = tA + int(s)
        # idx stays in-bounds: tA <= i0+wA+1 and i0 <= n_eff-1, so
        # idx <= n_eff-1 + wA + 1 + wB = n - h <= n - 1.
        hit = low_bid[idx] <= b_price if up else high_ask[idx] >= b_price
        first = a_touched & (b_step == inf_b) & hit
        b_step[first] = int(s)
    decided = a_touched & (b_step <= wB)
    tB = tA + b_step.astype(np.int64)

    # Continuation: signed h2-bar return from tB in the B-direction.
    exit_i = tB + h
    gross = np.full(len(i0), np.nan, dtype=float)
    ok = decided & (exit_i < n)
    if np.any(ok):
        ok_idx = np.flatnonzero(ok)
        if up:
            # B is down -> continuation bet is short.
            entry_price = close_bid[tB[ok_idx]]
            exit_price = close_ask[exit_i[ok_idx]]
            g = (entry_price - exit_price) / pip
        else:
            # B is up -> continuation bet is long.
            entry_price = close_ask[tB[ok_idx]]
            exit_price = close_bid[exit_i[ok_idx]]
            g = (exit_price - entry_price) / pip
        num_ok = np.isfinite(entry_price) & np.isfinite(exit_price)
        gross[ok_idx[num_ok]] = g[num_ok]

    return {
        "i0": i0,
        "decided": decided,
        "gross": gross,
        "t_a_step": np.where(a_touched, a_step, -1).astype(np.int64),
        "t_b_step": np.where(decided, b_step, -1).astype(np.int64),
    }
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/test_tick_opportunity_mining.py::test_double_touch_precompute_detects_up_sweep -v`
Expected: PASS.

- [ ] **Step 5: Add the no-sweep test**

Append to `tests/test_tick_opportunity_mining.py`:

```python
def test_double_touch_precompute_no_sweep_on_flat_frame() -> None:
    frame = _build_flat_frame()
    out = _double_touch_precompute(
        frame, symbol="EURUSD", sweep_dir="up",
        a_pips=3.0, b_pips=3.0, window_A=5, window_B=5, h2=5,
    )
    assert out, "engine should still return a dict for a long-enough frame"
    decided = np.asarray(out["decided"], dtype=bool)
    gross = np.asarray(out["gross"], dtype=float)
    assert decided.sum() == 0, "a flat frame touches no barrier"
    assert np.isnan(gross).all()


def test_double_touch_precompute_empty_when_frame_too_short() -> None:
    frame = _build_flat_frame(n=110)
    out = _double_touch_precompute(
        frame, symbol="EURUSD", sweep_dir="up",
        a_pips=3.0, b_pips=3.0, window_A=5, window_B=5, h2=5,
    )
    assert out == {}
```

- [ ] **Step 6: Run the new tests**

Run: `uv run pytest tests/test_tick_opportunity_mining.py -k double_touch_precompute -v`
Expected: 3 PASS.

- [ ] **Step 7: Commit**

```bash
git add scripts/run_tick_opportunity_mining.py tests/test_tick_opportunity_mining.py
git commit -m "feat: _double_touch_precompute two-stage sweep engine"
```

---

### Task 2: `DoubleTouchFamily` and registry wiring

**Files:**
- Modify: `scripts/mining_family.py` (add `DoubleTouchFamily` after `DirectionalRunFamily`; add to `FAMILY_REGISTRY` and `_LIBRARY_TYPE_ALIASES`)
- Modify: `tests/test_mining_family.py` (add conformance + hook tests)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_mining_family.py`:

```python
def test_double_touch_family_registered_and_resolves():
    from scripts.mining_family import (
        FAMILY_REGISTRY,
        MiningFamily,
        resolve_families,
    )

    assert resolve_families("double_touch") == ["double_touch"]
    fam = FAMILY_REGISTRY["double_touch"]
    assert fam.name == "double_touch"
    assert isinstance(fam, MiningFamily)


def test_double_touch_family_grid_and_metadata():
    from scripts.mining_family import FAMILY_REGISTRY

    fam = FAMILY_REGISTRY["double_touch"]
    grid = fam.param_grid({"barrier_grid_pips": "2,3", "horizons": "1,2"})
    sweeps = sorted({g["sweep_dir"] for g in grid})
    assert sweeps == ["down", "up"]
    # 2 sweep_dir x 2 a_pips x 2 b_pips x 2 window_A x 2 window_B x 2 horizons
    assert len(grid) == 2 * 2 * 2 * 2 * 2 * 2
    meta = fam.candidate_metadata(
        "london",
        {"sweep_dir": "up", "a_pips": 3.0, "b_pips": 2.0,
         "window_A": 5, "window_B": 15, "horizon": 2},
    )
    assert meta["family"] == "double_touch"
    assert meta["state_id"] == "double_touch__london__up_a3_b2_wA5_wB15_h2"
    assert meta["ml_ready_target_type"] == "double_touch"
    assert "sweep=up" in meta["regime_desc"]


def test_double_touch_family_entry_and_gross():
    import numpy as np

    from scripts.mining_family import FAMILY_REGISTRY
    from tests.test_tick_opportunity_mining import _build_sweep_frame

    fam = FAMILY_REGISTRY["double_touch"]
    frame = _build_sweep_frame()
    allmask = np.ones(len(frame), dtype=bool)
    params = {"symbol": "EURUSD", "sweep_dir": "up", "a_pips": 3.0,
              "b_pips": 3.0, "window_A": 5, "window_B": 5, "horizon": 5}
    entries = fam.entry_indices(frame, allmask, params)
    assert len(entries) > 0
    gross = fam.measure_gross(frame, entries, params)
    assert len(gross) == len(entries)
    assert np.isfinite(gross).sum() > 0


def test_double_touch_family_param_grid_rejects_nonpositive():
    import pytest

    from scripts.mining_family import FAMILY_REGISTRY

    fam = FAMILY_REGISTRY["double_touch"]
    with pytest.raises(ValueError):
        fam.param_grid({"barrier_grid_pips": "0", "horizons": "1"})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_mining_family.py -k double_touch -v`
Expected: FAIL with `KeyError: 'double_touch'` (not in `FAMILY_REGISTRY` / `_LIBRARY_TYPE_ALIASES`).

- [ ] **Step 3: Add `DoubleTouchFamily`**

In `scripts/mining_family.py`, add this class immediately after `DirectionalRunFamily` (before the `FAMILY_REGISTRY` assignment):

```python
class DoubleTouchFamily:
    name = "double_touch"

    _B_PIPS = [2.0, 4.0]
    _WINDOWS = [5, 15]

    def __init__(self) -> None:
        self._cache: dict[tuple[int, tuple[tuple[str, Any], ...]], dict[str, Any] | None] = {}

    def clear_cache(self) -> None:
        """Drop cached precompute results. Long-lived processes should call
        this between mining batches to avoid unbounded growth."""
        self._cache.clear()

    def param_grid(self, cfg: dict[str, Any]) -> list[dict[str, Any]]:
        from scripts.run_tick_opportunity_mining import _parse_floats, _parse_ints

        a_grid = _parse_floats(str(cfg["barrier_grid_pips"]))
        horizons = _parse_ints(str(cfg["horizons"]))
        grid: list[dict[str, Any]] = []
        for sweep_dir in ("up", "down"):
            for a in a_grid:
                for b in self._B_PIPS:
                    for wa in self._WINDOWS:
                        for wb in self._WINDOWS:
                            for h2 in horizons:
                                if (
                                    a <= 0.0 or b <= 0.0
                                    or wa <= 0 or wb <= 0 or h2 <= 0
                                ):
                                    raise ValueError(
                                        f"non-positive grid value: a={a} b={b} "
                                        f"wA={wa} wB={wb} h2={h2}"
                                    )
                                grid.append({
                                    "sweep_dir": sweep_dir,
                                    "a_pips": float(a),
                                    "b_pips": float(b),
                                    "window_A": int(wa),
                                    "window_B": int(wb),
                                    "horizon": int(h2),
                                })
        return grid

    def _precompute(
        self, frame: pd.DataFrame, symbol: str, params: dict[str, Any]
    ) -> dict[str, Any] | None:
        from scripts.run_tick_opportunity_mining import _double_touch_precompute

        key = (_frame_fingerprint(frame), tuple(sorted(params.items())))
        if key in self._cache:
            return self._cache[key]
        try:
            result = _double_touch_precompute(
                frame,
                symbol=symbol,
                sweep_dir=str(params["sweep_dir"]),
                a_pips=float(params["a_pips"]),
                b_pips=float(params["b_pips"]),
                window_A=int(params["window_A"]),
                window_B=int(params["window_B"]),
                h2=int(params["horizon"]),
            )
        except ValueError:
            result = None
        self._cache[key] = result
        return result

    def entry_indices(
        self, frame: pd.DataFrame, regime_mask: np.ndarray, params: dict[str, Any]
    ) -> np.ndarray:
        if "symbol" not in params:
            return np.array([], dtype=np.int64)
        prep = self._precompute(frame, str(params["symbol"]), params)
        if not prep:
            return np.array([], dtype=np.int64)
        i0 = np.asarray(prep["i0"], dtype=np.int64)
        decided = np.asarray(prep["decided"], dtype=bool)
        reg = np.asarray(regime_mask, dtype=bool)[i0]
        return i0[decided & reg]

    def measure_gross(
        self, frame: pd.DataFrame, entries: np.ndarray, params: dict[str, Any]
    ) -> np.ndarray:
        if "symbol" not in params:
            return np.array([], dtype=float)
        prep = self._precompute(frame, str(params["symbol"]), params)
        if not prep:
            return np.array([], dtype=float)
        i0 = np.asarray(prep["i0"], dtype=np.int64)
        gross = np.asarray(prep["gross"], dtype=float)
        pos = pd.Series(np.arange(len(i0)), index=i0)
        mapped = pos.reindex(entries).to_numpy(dtype=float)
        out = np.full(len(entries), np.nan, dtype=float)
        valid = np.isfinite(mapped)
        out[valid] = gross[mapped[valid].astype(np.int64)]
        return out

    def candidate_metadata(
        self, regime_name: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        sd = str(params["sweep_dir"])
        a = float(params["a_pips"])
        b = float(params["b_pips"])
        wa = int(params["window_A"])
        wb = int(params["window_B"])
        h2 = int(params["horizon"])
        return {
            "family": "double_touch",
            "state_id": (
                f"double_touch__{regime_name}__{sd}_a{a:g}_b{b:g}"
                f"_wA{wa}_wB{wb}_h{h2}"
            ),
            "regime_desc": (
                f"{regime_name};sweep={sd};a={a:g};b={b:g}"
                f";wA={wa};wB={wb};h={h2}"
            ),
            "ml_ready_target_type": "double_touch",
        }
```

- [ ] **Step 4: Register the family and the library-type alias**

In `scripts/mining_family.py`, add the `double_touch` entry to `_LIBRARY_TYPE_ALIASES` (the dict near the top of the file):

```python
_LIBRARY_TYPE_ALIASES: dict[str, list[str]] = {
    "oco": ["oco_first_touch"],
    "oco_asymmetric": ["oco_asymmetric"],
    "directional": ["directional"],
    "directional_run": ["directional_run"],
    "double_touch": ["double_touch"],
    "separate": ["oco_first_touch", "directional"],
}
```

And add it to `FAMILY_REGISTRY` at the bottom of the file:

```python
FAMILY_REGISTRY: dict[str, MiningFamily] = {
    "oco_first_touch": OcoFirstTouchFamily(),
    "oco_asymmetric": OcoAsymmetricFamily(),
    "directional": DirectionalFamily(),
    "directional_run": DirectionalRunFamily(),
    "double_touch": DoubleTouchFamily(),
}
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/test_mining_family.py -k double_touch -v`
Expected: 4 PASS.

- [ ] **Step 6: Run the OCO allowlist contract to confirm `double_touch` is not falsely caught**

Run: `uv run pytest tests/test_oco_candidate_family_allowlist.py -v`
Expected: PASS (`double_touch` does not start with `oco_`, so it is correctly outside `ALLOWED_OCO_FAMILIES`).

- [ ] **Step 7: Commit**

```bash
git add scripts/mining_family.py tests/test_mining_family.py
git commit -m "feat: DoubleTouchFamily implementing the MiningFamily protocol"
```

---

### Task 3: Wire `double_touch` into `run()` and `_mine_frame_pair`

**Files:**
- Modify: `scripts/run_tick_opportunity_mining.py` (`run()` family-merge branch; `_mine_frame_pair` `selection_pass` branch)
- Modify: `tests/test_tick_opportunity_mining.py` (end-to-end test)

- [ ] **Step 1: Write the failing end-to-end test**

Append to `tests/test_tick_opportunity_mining.py`:

```python
def test_run_mines_double_touch(tmp_path: Path) -> None:
    dataset_dir = tmp_path / "tick_velocity"
    dataset_dir.mkdir(parents=True, exist_ok=True)
    _build_synth_tick_velocity(dataset_dir / "EURUSD_1000tick_velocity.parquet",
                               symbol="EURUSD")
    cfg = {
        "symbol": "EURUSD", "dataset_dir": str(dataset_dir),
        "bar_ticks_grid": "1000", "horizons": "1,2,3",
        "train_years": "2022,2023,2024", "test_year": 2025,
        "min_annual_fills": 50.0, "gross_metric": "mean",
        "library_type": "double_touch", "barrier_grid_pips": "2,3",
        "baseline_seed": 12345, "baseline_draws": 20,
    }
    directional, oco, _ = run(cfg)
    # double_touch is a signed-return family -> lands in the directional frame.
    assert oco.empty
    assert not directional.empty, "double_touch should produce candidates"
    assert (directional["family"] == "double_touch").all()
    for col in ("random_baseline_z", "random_baseline_p"):
        assert col in directional.columns
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_tick_opportunity_mining.py::test_run_mines_double_touch -v`
Expected: FAIL — `directional` is empty because `run()` does not route `double_touch` rows into the directional frame.

- [ ] **Step 3: Extend the `run()` family-merge branch**

In `scripts/run_tick_opportunity_mining.py`, inside `run()`, find the family-merge loop and add `"double_touch"` to the directional set:

```python
        if fam_name in {"directional", "directional_run", "double_touch"}:
            directional_rows.extend(rows)
        elif fam_name in {"oco_first_touch", "oco_asymmetric"}:
            oco_rows.extend(rows)
```

- [ ] **Step 4: Extend the `_mine_frame_pair` `selection_pass` branch**

In `scripts/run_tick_opportunity_mining.py`, inside `_mine_frame_pair`, update the directional `selection_pass` branch to include `double_touch` (it currently reads `if fam_name in ("directional", "directional_run"):`):

```python
                if fam_name in ("directional", "directional_run", "double_touch"):
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `uv run pytest tests/test_tick_opportunity_mining.py::test_run_mines_double_touch -v`
Expected: PASS.

- [ ] **Step 6: Run the full mining + family suites for regressions**

Run: `uv run pytest tests/test_tick_opportunity_mining.py tests/test_mining_family.py tests/test_oco_candidate_family_allowlist.py -q`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add scripts/run_tick_opportunity_mining.py tests/test_tick_opportunity_mining.py
git commit -m "feat: run() mines the double_touch family"
```

---

### Task 4: Statistical tests — no-false-edge and detects-structure

**Files:**
- Modify: `tests/test_mining_family.py` (two statistical tests)

- [ ] **Step 1: Write the no-false-edge test**

Append to `tests/test_mining_family.py`:

```python
def test_double_touch_no_false_edge_on_driftless_data():
    import numpy as np
    import pandas as pd

    from scripts.mining_family import FAMILY_REGISTRY
    from scripts.mining_random_baseline import random_entry_baseline

    fam = FAMILY_REGISTRY["double_touch"]
    rng = np.random.default_rng(99)
    n = 1500
    pip = 0.0001
    # Driftless random walk — sweeps occur but carry no continuation edge.
    base = 1.20000 + np.cumsum(rng.normal(0, 0.3 * pip, n))
    frame = pd.DataFrame({
        "close_bid": base,
        "close_ask": base + 0.2 * pip,
        "low_bid": base - rng.uniform(0.1, 0.4, n) * pip,
        "high_ask": base + 0.2 * pip + rng.uniform(0.1, 0.4, n) * pip,
    })
    allmask = np.ones(len(frame), dtype=bool)
    params = {"symbol": "EURUSD", "sweep_dir": "up", "a_pips": 3.0,
              "b_pips": 3.0, "window_A": 15, "window_B": 15, "horizon": 5}
    entries = fam.entry_indices(frame, allmask, params)
    assert len(entries) > 0, "driftless fixture should still produce sweeps"
    gross = fam.measure_gross(frame, entries, params)
    gross = gross[np.isfinite(gross)]
    assert gross.size > 0
    cand_ev = float(np.mean(gross))
    baseline = random_entry_baseline(
        fam, frame, params,
        n_entries=len(entries), n_draws=100,
        rng=np.random.default_rng(7),
        candidate_gross_ev=cand_ev,
    )
    z = baseline["random_baseline_z"]
    assert np.isnan(z) or z < 2.0
```

- [ ] **Step 2: Run it to verify it passes**

Run: `uv run pytest tests/test_mining_family.py::test_double_touch_no_false_edge_on_driftless_data -v`
Expected: PASS. (No implementation change — the family already exists; this test pins behaviour. If it fails because the driftless fixture produces no entries, widen `window_A`/`window_B` to 25 in the test `params` and re-run.)

- [ ] **Step 3: Write the detects-structure test**

Append to `tests/test_mining_family.py`:

```python
def test_double_touch_detects_structure_on_post_sweep_continuation():
    import numpy as np
    import pandas as pd

    from scripts.mining_family import FAMILY_REGISTRY
    from scripts.mining_random_baseline import random_entry_baseline

    fam = FAMILY_REGISTRY["double_touch"]
    n = 1500
    pip = 0.0001
    # Steady downtrend with single-bar up-blips: every completed up-sweep is
    # followed by a real downward continuation. A regime restricted to the
    # trending bars should score well above the random-entry baseline.
    drift = 1.30000 - 0.5 * pip * np.arange(n)
    blip = np.where(np.arange(n) % 25 == 1, 5.0 * pip, 0.0)
    close = drift + blip
    frame = pd.DataFrame({
        "close_bid": close,
        "close_ask": close + 0.2 * pip,
        "low_bid": close - 0.3 * pip,
        "high_ask": close + 0.2 * pip + 0.3 * pip,
    })
    allmask = np.ones(len(frame), dtype=bool)
    params = {"symbol": "EURUSD", "sweep_dir": "up", "a_pips": 3.0,
              "b_pips": 3.0, "window_A": 5, "window_B": 5, "horizon": 5}
    entries = fam.entry_indices(frame, allmask, params)
    assert len(entries) > 0, "sweep frame should produce entries"
    gross = fam.measure_gross(frame, entries, params)
    gross = gross[np.isfinite(gross)]
    assert gross.size > 0
    cand_ev = float(np.mean(gross))
    baseline = random_entry_baseline(
        fam, frame, params,
        n_entries=len(entries), n_draws=200,
        rng=np.random.default_rng(7),
        candidate_gross_ev=cand_ev,
    )
    assert baseline["random_baseline_z"] > 2.0
```

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/test_mining_family.py::test_double_touch_detects_structure_on_post_sweep_continuation -v`
Expected: PASS.

- [ ] **Step 5: Run the full suite and quality checks**

Run: `uv run pytest -q` then `make quality`
Expected: full suite PASS; ruff + ty + vulture clean.

- [ ] **Step 6: Commit**

```bash
git add tests/test_mining_family.py
git commit -m "test: no-false-edge + detects-structure tests for double_touch"
```

---

## Self-Review

**Spec coverage:**
- Design §1 (anchored two-stage sweep) → Task 1 (`_double_touch_precompute`) + Task 2 (`DoubleTouchFamily`).
- Design §2 (touch & gross discipline: deterministic `pA`, spread-aware gross) → Task 1 Step 3.
- Design §3 (new precompute engine, dict shape `i0`/`decided`/`gross`/`t_a_step`/`t_b_step`) → Task 1 Step 3.
- Design §4 (family hooks, cache, schema 4.0 unchanged) → Task 2 Step 3.
- Design §5 (parameter grid; `ValueError` on non-positive) → Task 2 Step 3 + `test_double_touch_family_param_grid_rejects_nonpositive`.
- Design §6 (output wiring: `resolve_families` alias, `run()` merge, `selection_pass`) → Task 2 Step 4 + Task 3 Steps 3–4.
- Design §7 (governance: not `oco_`-prefixed, allowlist unbroadened) → Task 2 Step 6.
- Design Testing (precompute correctness, no-sweep, bet direction, no-false-edge, detects-structure, registry conformance, end-to-end) → Tasks 1, 2, 3, 4. Bet direction is verified by the up-sweep gross sign in `test_double_touch_precompute_detects_up_sweep` and the structure test.
- Design Error Handling (non-positive params, short frame, A-without-B, off-frame continuation) → Task 1 (`test_..._empty_when_frame_too_short`, no-sweep test) + Task 2 (`..._rejects_nonpositive`).

**Placeholder scan:** No `TBD`/`TODO`; every code step contains complete code.

**Type consistency:** `_double_touch_precompute` returns keys `i0`, `decided`, `gross`, `t_a_step`, `t_b_step` — consumed exactly so by `DoubleTouchFamily._precompute`/`entry_indices`/`measure_gross`. The params dict uses key `"horizon"` for the continuation horizon `h2` consistently across `param_grid`, `_precompute`, `candidate_metadata`, and the `_mine_frame_pair` row. `_frame_fingerprint` and `Any` are already in scope in `mining_family.py` (introduced by PR #188 / the framework).
