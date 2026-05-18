# Pullback Continuation Family — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `pullback` mining family that detects an impulse → pullback → resumption price sequence and scores continuation past the resumption point against the random-entry baseline.

**Architecture:** A new vectorised four-stage touch engine (`_pullback_precompute`) finds, per regime entry bar `i0`, a first impulse-barrier touch within `window_I` bars, then a first pullback-barrier touch within `window_P` bars, then a first resumption touch (back at the impulse extreme) within `window_R` bars. A `PullbackFamily` implementing the existing `MiningFamily` protocol wraps it, with the same per-frame precompute cache the `double_touch` family uses. Its candidate rows are signed-return outcomes, so they fold into the `directional` output frame.

**Tech Stack:** Python, NumPy, pandas, pytest. Follows `scripts/mining_family.py` + `scripts/run_tick_opportunity_mining.py`. Spec: `docs/superpowers/specs/2026-05-18-pullback-continuation-design.md`.

**Base state:** Sub-project 3 (`double_touch`) is merged to `main` — `scripts/mining_family.py` (with `MiningFamily`, `_frame_fingerprint`, `DoubleTouchFamily`, `FAMILY_REGISTRY`, `_LIBRARY_TYPE_ALIASES`), `_double_touch_precompute`, `_mine_frame_pair`, and `scripts/mining_random_baseline.py` all exist. This plan extends those files; it does not create them.

## File Structure

- `scripts/run_tick_opportunity_mining.py` — add `_pullback_precompute` (new four-stage engine); extend the `run()` `library_type` check and family-merge branch, and the `_mine_frame_pair` `selection_pass` branch.
- `scripts/mining_family.py` — add `PullbackFamily`; register it in `FAMILY_REGISTRY`; add the `pullback` alias to `_LIBRARY_TYPE_ALIASES`.
- `tests/test_tick_opportunity_mining.py` — add `_build_pullback_frame` builder; precompute tests; end-to-end mining test.
- `tests/test_mining_family.py` — `pullback` conformance, hook, and statistical tests.

---

### Task 1: `_pullback_precompute` four-stage engine

**Files:**
- Modify: `scripts/run_tick_opportunity_mining.py` (add function immediately after `_double_touch_precompute`, before `_assign_quality_tier`)
- Modify: `tests/test_tick_opportunity_mining.py` (add builder + tests; extend the import from `scripts.run_tick_opportunity_mining`)

- [ ] **Step 1: Add the test frame builder and the first failing test**

In `tests/test_tick_opportunity_mining.py`, add `_pullback_precompute` to the existing import block from `scripts.run_tick_opportunity_mining` (alongside `_double_touch_precompute`, `run`, etc.). Then append:

```python
def _build_pullback_frame(n: int = 800) -> pd.DataFrame:
    """Steady uptrend (0.5 pip/bar) with a single-bar low_bid dip every 30
    bars. From a regime bar, the uptrend touches an up-impulse barrier; the
    dip retraces price back through the pullback barrier; the uptrend then
    resumes back to the impulse extreme and continues up. Deterministic —
    used to assert a completed impulse->pullback->resumption is detected and
    that the continuation bet is long-profitable."""
    pip = 0.0001
    close = 1.20000 + 0.5 * pip * np.arange(n)
    spread = 0.2 * pip
    dip = np.where(np.arange(n) % 30 == 15, 6.0 * pip, 0.0)
    return pd.DataFrame({
        "close_bid": close,
        "close_ask": close + spread,
        "low_bid": close - 0.3 * pip - dip,
        "high_ask": close + spread + 0.3 * pip,
    })


def test_pullback_precompute_detects_up_pullback() -> None:
    frame = _build_pullback_frame()
    out = _pullback_precompute(
        frame, symbol="EURUSD", impulse_dir="up",
        m_pips=3.0, r_frac=0.5, window_I=15, window_P=15, window_R=10, h=5,
    )
    assert out, "engine should return a populated dict for a long-enough frame"
    decided = np.asarray(out["decided"], dtype=bool)
    gross = np.asarray(out["gross"], dtype=float)
    assert decided.sum() > 0, "an impulse->pullback->resumption should complete"
    # Up-impulse bets long; the uptrend continuation makes that profitable.
    assert np.nanmean(gross) > 0.0
    # Diagnostics are -1 where a leg did not fire, >=1 where it did.
    t_i = np.asarray(out["t_i_step"], dtype=np.int64)
    t_p = np.asarray(out["t_p_step"], dtype=np.int64)
    t_r = np.asarray(out["t_r_step"], dtype=np.int64)
    assert (t_i[decided] >= 1).all()
    assert (t_p[decided] >= 1).all()
    assert (t_r[decided] >= 1).all()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_tick_opportunity_mining.py::test_pullback_precompute_detects_up_pullback -v`
Expected: FAIL with `ImportError` / `cannot import name '_pullback_precompute'`.

- [ ] **Step 3: Implement `_pullback_precompute`**

In `scripts/run_tick_opportunity_mining.py`, add this function immediately after `_double_touch_precompute` (after its `return {...}` block, before `_assign_quality_tier`):

```python
def _pullback_precompute(
    frame: pd.DataFrame,
    *,
    symbol: str,
    impulse_dir: str,
    m_pips: float,
    r_frac: float,
    window_I: int,
    window_P: int,
    window_R: int,
    h: int,
) -> dict[str, np.ndarray]:
    """Anchored four-stage pullback-continuation engine.

    For each regime entry bar i0: place an impulse barrier m_pips in the
    impulse_dir direction from i0's signal close; find the first touch within
    window_I bars (tI). The impulse extreme pI is the barrier price itself.
    Place a pullback barrier r_frac*m_pips from pI in the OPPOSITE direction;
    find the first touch within window_P bars of tI (tP). Place a resumption
    barrier back at pI; find the first touch within window_R bars of tP (tR).
    Continuation gross is the signed h-bar return from tR in the impulse
    direction. Look-ahead-free: entry conditioning is i0 only; tI, tP, tR and
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

    wI, wP, wR, hh = int(window_I), int(window_P), int(window_R), int(h)
    n = len(frame)
    # i0 upper bound reserves room for the worst-case forward index across all
    # three scans plus the continuation horizon. The +2 covers the inf-padded
    # steps of i0 bars that never complete an earlier stage (tI <= i0+wI+1,
    # tP <= tI+wP+1), so every index read below stays in-bounds unconditionally.
    n_eff = n - (wI + wP + wR + hh + 2)
    if n_eff <= 100:
        return {}

    pip = float(_pip_size(symbol))
    up = str(impulse_dir).strip().lower() == "up"

    i0 = np.arange(n_eff, dtype=np.int64)
    sig = close_ask[i0] if up else close_bid[i0]
    valid = np.isfinite(sig)
    i0 = i0[valid]
    sig = sig[valid]

    # Stage 1: impulse barrier in the impulse direction.
    i_price = sig + m_pips * pip if up else sig - m_pips * pip
    inf_i = wI + 1
    i_step = np.full(len(i0), inf_i, dtype=np.int32)
    for s in range(1, wI + 1):
        idx = i0 + int(s)
        hit = high_ask[idx] >= i_price if up else low_bid[idx] <= i_price
        first = (i_step == inf_i) & hit
        i_step[first] = int(s)
    i_touched = i_step <= wI
    tI = i0 + i_step.astype(np.int64)

    # Stage 2: pullback barrier r_frac*m_pips OPPOSITE the impulse extreme pI.
    p_price = (
        i_price - r_frac * m_pips * pip if up else i_price + r_frac * m_pips * pip
    )
    inf_p = wP + 1
    p_step = np.full(len(i0), inf_p, dtype=np.int32)
    for s in range(1, wP + 1):
        idx = tI + int(s)
        hit = low_bid[idx] <= p_price if up else high_ask[idx] >= p_price
        first = i_touched & (p_step == inf_p) & hit
        p_step[first] = int(s)
    p_touched = i_touched & (p_step <= wP)
    tP = tI + p_step.astype(np.int64)

    # Stage 3: resumption barrier back at the impulse extreme pI.
    inf_r = wR + 1
    r_step = np.full(len(i0), inf_r, dtype=np.int32)
    for s in range(1, wR + 1):
        idx = tP + int(s)
        hit = high_ask[idx] >= i_price if up else low_bid[idx] <= i_price
        first = p_touched & (r_step == inf_r) & hit
        r_step[first] = int(s)
    decided = p_touched & (r_step <= wR)
    tR = tP + r_step.astype(np.int64)

    # Continuation: signed h-bar return from tR in the impulse direction.
    exit_i = tR + hh
    gross = np.full(len(i0), np.nan, dtype=float)
    ok = decided & (exit_i < n)
    if np.any(ok):
        ok_idx = np.flatnonzero(ok)
        if up:
            # Up-impulse -> continuation bet is long.
            entry_price = close_ask[tR[ok_idx]]
            exit_price = close_bid[exit_i[ok_idx]]
            g = (exit_price - entry_price) / pip
        else:
            # Down-impulse -> continuation bet is short.
            entry_price = close_bid[tR[ok_idx]]
            exit_price = close_ask[exit_i[ok_idx]]
            g = (entry_price - exit_price) / pip
        num_ok = np.isfinite(entry_price) & np.isfinite(exit_price)
        gross[ok_idx[num_ok]] = g[num_ok]

    return {
        "i0": i0,
        "decided": decided,
        "gross": gross,
        "t_i_step": np.where(i_touched, i_step, -1).astype(np.int64),
        "t_p_step": np.where(p_touched, p_step, -1).astype(np.int64),
        "t_r_step": np.where(decided, r_step, -1).astype(np.int64),
    }
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/test_tick_opportunity_mining.py::test_pullback_precompute_detects_up_pullback -v`
Expected: PASS.

- [ ] **Step 5: Add the no-setup and too-short tests**

Append to `tests/test_tick_opportunity_mining.py` (the `_build_flat_frame` builder already exists in this file — reuse it, do not redefine it):

```python
def test_pullback_precompute_no_setup_on_flat_frame() -> None:
    frame = _build_flat_frame()
    out = _pullback_precompute(
        frame, symbol="EURUSD", impulse_dir="up",
        m_pips=3.0, r_frac=0.5, window_I=15, window_P=15, window_R=10, h=5,
    )
    assert out, "engine should still return a dict for a long-enough frame"
    decided = np.asarray(out["decided"], dtype=bool)
    gross = np.asarray(out["gross"], dtype=float)
    assert decided.sum() == 0, "a flat frame touches no impulse barrier"
    assert np.isnan(gross).all()


def test_pullback_precompute_empty_when_frame_too_short() -> None:
    frame = _build_flat_frame(n=140)
    out = _pullback_precompute(
        frame, symbol="EURUSD", impulse_dir="up",
        m_pips=3.0, r_frac=0.5, window_I=15, window_P=15, window_R=10, h=5,
    )
    assert out == {}
```

- [ ] **Step 6: Run the new tests**

Run: `uv run pytest tests/test_tick_opportunity_mining.py -k pullback_precompute -v`
Expected: 3 PASS.

- [ ] **Step 7: Commit**

```bash
git add scripts/run_tick_opportunity_mining.py tests/test_tick_opportunity_mining.py
git commit -m "feat: _pullback_precompute four-stage pullback engine"
```

---

### Task 2: `PullbackFamily` and registry wiring

**Files:**
- Modify: `scripts/mining_family.py` (add `PullbackFamily` after `DoubleTouchFamily`; add to `FAMILY_REGISTRY` and `_LIBRARY_TYPE_ALIASES`)
- Modify: `tests/test_mining_family.py` (add conformance + hook tests)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_mining_family.py`:

```python
def test_pullback_family_registered_and_resolves():
    from scripts.mining_family import (
        FAMILY_REGISTRY,
        MiningFamily,
        resolve_families,
    )

    assert resolve_families("pullback") == ["pullback"]
    fam = FAMILY_REGISTRY["pullback"]
    assert fam.name == "pullback"
    assert isinstance(fam, MiningFamily)


def test_pullback_family_grid_and_metadata():
    from scripts.mining_family import FAMILY_REGISTRY

    fam = FAMILY_REGISTRY["pullback"]
    grid = fam.param_grid({"barrier_grid_pips": "2,3", "horizons": "1,2"})
    dirs = sorted({g["impulse_dir"] for g in grid})
    assert dirs == ["down", "up"]
    # 2 impulse_dir x 2 m_pips x 3 r_frac x 2 window_I x 2 window_P x 2 horizons
    assert len(grid) == 2 * 2 * 3 * 2 * 2 * 2
    assert all(g["window_R"] == 10 for g in grid)
    meta = fam.candidate_metadata(
        "london",
        {"impulse_dir": "up", "m_pips": 3.0, "r_frac": 0.5,
         "window_I": 5, "window_P": 15, "window_R": 10, "horizon": 2},
    )
    assert meta["family"] == "pullback"
    assert meta["state_id"] == "pullback__london__up_M3_R0.5_wI5_wP15_wR10_h2"
    assert meta["ml_ready_target_type"] == "pullback"
    assert "impulse=up" in meta["regime_desc"]


def test_pullback_family_entry_and_gross():
    import numpy as np

    from scripts.mining_family import FAMILY_REGISTRY
    from tests.test_tick_opportunity_mining import _build_pullback_frame

    fam = FAMILY_REGISTRY["pullback"]
    frame = _build_pullback_frame()
    allmask = np.ones(len(frame), dtype=bool)
    params = {"symbol": "EURUSD", "impulse_dir": "up", "m_pips": 3.0,
              "r_frac": 0.5, "window_I": 15, "window_P": 15,
              "window_R": 10, "horizon": 5}
    entries = fam.entry_indices(frame, allmask, params)
    assert len(entries) > 0
    gross = fam.measure_gross(frame, entries, params)
    assert len(gross) == len(entries)
    assert np.isfinite(gross).sum() > 0


def test_pullback_family_param_grid_rejects_nonpositive():
    import pytest

    from scripts.mining_family import FAMILY_REGISTRY

    fam = FAMILY_REGISTRY["pullback"]
    with pytest.raises(ValueError):
        fam.param_grid({"barrier_grid_pips": "0", "horizons": "1"})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_mining_family.py -k pullback -v`
Expected: FAIL with `KeyError: 'pullback'` (not in `FAMILY_REGISTRY` / `_LIBRARY_TYPE_ALIASES`).

- [ ] **Step 3: Add `PullbackFamily`**

In `scripts/mining_family.py`, add this class immediately after `DoubleTouchFamily` (before the `FAMILY_REGISTRY` assignment):

```python
class PullbackFamily:
    name = "pullback"

    _R_FRACS = [0.382, 0.5, 0.618]
    _WINDOWS = [5, 15]
    _WINDOW_R = 10

    def __init__(self) -> None:
        self._cache: dict[tuple[int, tuple[tuple[str, Any], ...]], dict[str, Any] | None] = {}

    def clear_cache(self) -> None:
        """Drop cached precompute results. Long-lived processes should call
        this between mining batches to avoid unbounded growth."""
        self._cache.clear()

    def param_grid(self, cfg: dict[str, Any]) -> list[dict[str, Any]]:
        from scripts.run_tick_opportunity_mining import _parse_floats, _parse_ints

        m_grid = _parse_floats(str(cfg["barrier_grid_pips"]))
        horizons = _parse_ints(str(cfg["horizons"]))
        grid: list[dict[str, Any]] = []
        for impulse_dir in ("up", "down"):
            for m in m_grid:
                for r in self._R_FRACS:
                    for wi in self._WINDOWS:
                        for wp in self._WINDOWS:
                            for h2 in horizons:
                                if (
                                    m <= 0.0 or wi <= 0 or wp <= 0 or h2 <= 0
                                    or not (0.0 < r < 1.0)
                                ):
                                    raise ValueError(
                                        f"invalid grid value: m={m} r={r} "
                                        f"wI={wi} wP={wp} h={h2}"
                                    )
                                grid.append({
                                    "impulse_dir": impulse_dir,
                                    "m_pips": float(m),
                                    "r_frac": float(r),
                                    "window_I": int(wi),
                                    "window_P": int(wp),
                                    "window_R": int(self._WINDOW_R),
                                    "horizon": int(h2),
                                })
        return grid

    def _precompute(
        self, frame: pd.DataFrame, symbol: str, params: dict[str, Any]
    ) -> dict[str, Any] | None:
        from scripts.run_tick_opportunity_mining import _pullback_precompute

        key = (_frame_fingerprint(frame), tuple(sorted(params.items())))
        if key in self._cache:
            return self._cache[key]
        try:
            result = _pullback_precompute(
                frame,
                symbol=symbol,
                impulse_dir=str(params["impulse_dir"]),
                m_pips=float(params["m_pips"]),
                r_frac=float(params["r_frac"]),
                window_I=int(params["window_I"]),
                window_P=int(params["window_P"]),
                window_R=int(params["window_R"]),
                h=int(params["horizon"]),
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
        d = str(params["impulse_dir"])
        m = float(params["m_pips"])
        r = float(params["r_frac"])
        wi = int(params["window_I"])
        wp = int(params["window_P"])
        wr = int(params["window_R"])
        h2 = int(params["horizon"])
        return {
            "family": "pullback",
            "state_id": (
                f"pullback__{regime_name}__{d}_M{m:g}_R{r:g}"
                f"_wI{wi}_wP{wp}_wR{wr}_h{h2}"
            ),
            "regime_desc": (
                f"{regime_name};impulse={d};M={m:g};R={r:g}"
                f";wI={wi};wP={wp};wR={wr};h={h2}"
            ),
            "ml_ready_target_type": "pullback",
        }
```

- [ ] **Step 4: Register the family and the library-type alias**

In `scripts/mining_family.py`, add the `pullback` entry to `_LIBRARY_TYPE_ALIASES` (the dict near the top of the file). The current dict is:

```python
_LIBRARY_TYPE_ALIASES: dict[str, list[str]] = {
    "oco": ["oco_first_touch"],
    "directional": ["directional"],
    "double_touch": ["double_touch"],
    "separate": ["oco_first_touch", "directional"],
}
```

Add the `pullback` line so it reads:

```python
_LIBRARY_TYPE_ALIASES: dict[str, list[str]] = {
    "oco": ["oco_first_touch"],
    "directional": ["directional"],
    "double_touch": ["double_touch"],
    "pullback": ["pullback"],
    "separate": ["oco_first_touch", "directional"],
}
```

And add `PullbackFamily()` to `FAMILY_REGISTRY` at the bottom of the file. The current registry is:

```python
FAMILY_REGISTRY: dict[str, MiningFamily] = {
    "oco_first_touch": OcoFirstTouchFamily(),
    "directional": DirectionalFamily(),
    "double_touch": DoubleTouchFamily(),
}
```

Add the `pullback` line so it reads:

```python
FAMILY_REGISTRY: dict[str, MiningFamily] = {
    "oco_first_touch": OcoFirstTouchFamily(),
    "directional": DirectionalFamily(),
    "double_touch": DoubleTouchFamily(),
    "pullback": PullbackFamily(),
}
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/test_mining_family.py -k pullback -v`
Expected: 4 PASS.

- [ ] **Step 6: Run the OCO allowlist contract to confirm `pullback` is not falsely caught**

Run: `uv run pytest tests/test_oco_candidate_family_allowlist.py -v`
Expected: PASS (`pullback` does not start with `oco_`, so it is correctly outside `ALLOWED_OCO_FAMILIES`).

- [ ] **Step 7: Commit**

```bash
git add scripts/mining_family.py tests/test_mining_family.py
git commit -m "feat: PullbackFamily implementing the MiningFamily protocol"
```

---

### Task 3: Wire `pullback` into `run()` and `_mine_frame_pair`

**Files:**
- Modify: `scripts/run_tick_opportunity_mining.py` (`run()` `library_type` check + family-merge branch; `_mine_frame_pair` `selection_pass` branch)
- Modify: `tests/test_tick_opportunity_mining.py` (end-to-end test)

- [ ] **Step 1: Write the failing end-to-end test**

Append to `tests/test_tick_opportunity_mining.py` (the `_build_synth_tick_velocity` helper already exists in this file — reuse it):

```python
def test_run_mines_pullback(tmp_path: Path) -> None:
    dataset_dir = tmp_path / "tick_velocity"
    dataset_dir.mkdir(parents=True, exist_ok=True)
    _build_synth_tick_velocity(dataset_dir / "EURUSD_1000tick_velocity.parquet",
                               symbol="EURUSD")
    cfg = {
        "symbol": "EURUSD", "dataset_dir": str(dataset_dir),
        "bar_ticks_grid": "1000", "horizons": "1,2,3",
        "train_years": "2022,2023,2024", "test_year": 2025,
        "min_annual_fills": 50.0, "gross_metric": "mean",
        "library_type": "pullback", "barrier_grid_pips": "2,3",
        "baseline_seed": 12345, "baseline_draws": 20,
    }
    directional, oco, _ = run(cfg)
    # pullback is a signed-return family -> lands in the directional frame.
    assert oco.empty
    assert not directional.empty, "pullback should produce candidates"
    assert (directional["family"] == "pullback").all()
    for col in ("random_baseline_z", "random_baseline_p"):
        assert col in directional.columns
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_tick_opportunity_mining.py::test_run_mines_pullback -v`
Expected: FAIL — `run()` rejects `library_type="pullback"` with `ValueError("library_type must be separate|directional|oco|double_touch")`.

- [ ] **Step 3: Extend the `run()` `library_type` check**

In `scripts/run_tick_opportunity_mining.py`, inside `run()`, find this check:

```python
    if library_type not in {"separate", "directional", "oco", "double_touch"}:
        raise ValueError("library_type must be separate|directional|oco|double_touch")
```

Replace it with:

```python
    if library_type not in {"separate", "directional", "oco", "double_touch", "pullback"}:
        raise ValueError(
            "library_type must be separate|directional|oco|double_touch|pullback"
        )
```

- [ ] **Step 4: Extend the `run()` family-merge branch**

In `scripts/run_tick_opportunity_mining.py`, inside `run()`, find the directional-frame assembly:

```python
    directional = pd.DataFrame(
        per_family_rows.get("directional", [])
        + per_family_rows.get("double_touch", [])
    )
```

Replace it with:

```python
    directional = pd.DataFrame(
        per_family_rows.get("directional", [])
        + per_family_rows.get("double_touch", [])
        + per_family_rows.get("pullback", [])
    )
```

- [ ] **Step 5: Extend the `_mine_frame_pair` `selection_pass` branch**

In `scripts/run_tick_opportunity_mining.py`, inside `_mine_frame_pair`, find the directional `selection_pass` branch (it currently reads `if fam_name in ("directional", "double_touch"):`) and update it to include `pullback`:

```python
                if fam_name in ("directional", "double_touch", "pullback"):
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `uv run pytest tests/test_tick_opportunity_mining.py::test_run_mines_pullback -v`
Expected: PASS.

If `directional` comes back empty, the synthetic velocity frame produced no completed four-stage setups across the grid. Confirm by widening the grid — temporarily set `"barrier_grid_pips": "1,2"` in the test `cfg` (smaller impulse barriers complete more often) and re-run. Keep the widened value only if needed to make the test pass.

- [ ] **Step 7: Run the full mining + family suites for regressions**

Run: `uv run pytest tests/test_tick_opportunity_mining.py tests/test_mining_family.py tests/test_oco_candidate_family_allowlist.py -q`
Expected: all PASS.

- [ ] **Step 8: Commit**

```bash
git add scripts/run_tick_opportunity_mining.py tests/test_tick_opportunity_mining.py
git commit -m "feat: run() mines the pullback family"
```

---

### Task 4: Statistical tests — no-false-edge and detects-structure

**Files:**
- Modify: `tests/test_mining_family.py` (two statistical tests)

- [ ] **Step 1: Write the no-false-edge test**

Append to `tests/test_mining_family.py`:

```python
def test_pullback_no_false_edge_on_driftless_data():
    import numpy as np
    import pandas as pd

    from scripts.mining_family import FAMILY_REGISTRY
    from scripts.mining_random_baseline import random_entry_baseline

    fam = FAMILY_REGISTRY["pullback"]
    rng = np.random.default_rng(99)
    n = 2500
    pip = 0.0001
    # Driftless random walk — impulse/pullback/resumption setups occur but
    # carry no continuation edge.
    base = 1.20000 + np.cumsum(rng.normal(0, 0.3 * pip, n))
    frame = pd.DataFrame({
        "close_bid": base,
        "close_ask": base + 0.2 * pip,
        "low_bid": base - rng.uniform(0.1, 0.5, n) * pip,
        "high_ask": base + 0.2 * pip + rng.uniform(0.1, 0.5, n) * pip,
    })
    allmask = np.ones(len(frame), dtype=bool)
    params = {"symbol": "EURUSD", "impulse_dir": "up", "m_pips": 3.0,
              "r_frac": 0.5, "window_I": 15, "window_P": 15,
              "window_R": 10, "horizon": 5}
    entries = fam.entry_indices(frame, allmask, params)
    assert len(entries) > 0, "driftless fixture should still produce setups"
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

Run: `uv run pytest tests/test_mining_family.py::test_pullback_no_false_edge_on_driftless_data -v`
Expected: PASS. (No implementation change — the family already exists; this test pins behaviour.) If it fails because the driftless fixture produces no entries, increase `n` to `4000` and re-run.

- [ ] **Step 3: Write the detects-structure test**

This mirrors `test_double_touch_detects_structure_on_post_sweep_continuation`: a frame with a trending region followed by a flat region, with the regime restricted to the trending region. Random-baseline draws sample completed setups from the flat region too, diluting the control mean below the candidate EV. Append to `tests/test_mining_family.py`:

```python
def test_pullback_detects_structure_on_post_resumption_continuation():
    import numpy as np
    import pandas as pd

    from scripts.mining_family import FAMILY_REGISTRY
    from scripts.mining_random_baseline import random_entry_baseline

    fam = FAMILY_REGISTRY["pullback"]
    pip = 0.0001
    # One 30-bar cycle: 10 flat bars, a 6-pip impulse held 3 bars, a pullback
    # down to +1 pip held 3 bars, a resumption back to +6 pip, then a hold.
    # Tiled across the frame so an impulse->pullback->resumption completes
    # once per cycle.
    cycle = np.array(
        [0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
         6, 6, 6,
         1, 1, 1,
         6, 6, 6,
         6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6],
        dtype=float,
    )
    assert cycle.size == 30
    bump = np.tile(cycle, 60) * pip
    n = bump.size  # 1800
    # First 1200 bars: a 0.5 pip/bar uptrend supplies real post-resumption
    # continuation. Last 600 bars: flat — setups still complete on the bump
    # shape but carry no continuation, diluting the control mean.
    trend_len = 1200
    drift = np.concatenate([
        0.5 * pip * np.arange(trend_len),
        np.full(n - trend_len, 0.5 * pip * trend_len),
    ])
    close = 1.30000 + drift + bump
    frame = pd.DataFrame({
        "close_bid": close,
        "close_ask": close + 0.2 * pip,
        "low_bid": close - 0.1 * pip,
        "high_ask": close + 0.2 * pip + 0.1 * pip,
    })
    regime_mask = np.zeros(n, dtype=bool)
    regime_mask[:trend_len] = True
    params = {"symbol": "EURUSD", "impulse_dir": "up", "m_pips": 3.0,
              "r_frac": 0.5, "window_I": 15, "window_P": 15,
              "window_R": 10, "horizon": 5}
    entries = fam.entry_indices(frame, regime_mask, params)
    assert len(entries) > 0, "trending region should produce setups"
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

Run: `uv run pytest tests/test_mining_family.py::test_pullback_detects_structure_on_post_resumption_continuation -v`
Expected: PASS.

If `z` is not above 2.0, the trending and flat regions are not separating cleanly. Tune in this order, re-running after each change: (a) lengthen the trending region's edge by raising the drift from `0.5` to `1.0` pip/bar; (b) raise `trend_len` to `1500` so more candidate entries are trending; (c) raise `n_draws` to `400`. Keep the smallest change that makes `z > 2.0`.

- [ ] **Step 5: Run the full suite and quality checks**

Run: `uv run pytest -q` then `make quality`
Expected: full suite PASS; ruff + ty + vulture clean.

- [ ] **Step 6: Commit**

```bash
git add tests/test_mining_family.py
git commit -m "test: no-false-edge + detects-structure tests for pullback"
```

---

## Self-Review

**Spec coverage:**
- Design §1 (anchored four-stage engine) → Task 1 (`_pullback_precompute`) + Task 2 (`PullbackFamily`).
- Design §2 (touch & gross discipline: deterministic `pI`, spread-aware gross) → Task 1 Step 3.
- Design §3 (new precompute engine; dict shape `i0`/`decided`/`gross`/`t_i_step`/`t_p_step`/`t_r_step`) → Task 1 Step 3.
- Design §4 (family hooks, cache, schema 4.0 unchanged) → Task 2 Step 3.
- Design §5 (parameter grid; `window_R` fixed at 10; `ValueError` on invalid values) → Task 2 Step 3 + `test_pullback_family_param_grid_rejects_nonpositive` + `test_pullback_family_grid_and_metadata` (asserts `window_R == 10`).
- Design §6 (output wiring: `resolve_families` alias, `run()` check + merge, `_mine_frame_pair` `selection_pass`) → Task 2 Step 4 + Task 3 Steps 3–5.
- Design §7 (governance: not `oco_`-prefixed, allowlist unbroadened) → Task 2 Step 6.
- Design Testing (precompute correctness, no-setup, bet direction, no-false-edge, detects-structure, registry conformance, end-to-end) → Tasks 1, 2, 3, 4. Bet direction is verified by the up-impulse long-continuation gross sign in `test_pullback_precompute_detects_up_pullback` and the structure test.
- Design Error Handling (invalid params, short frame, impulse-without-pullback, pullback-without-resumption, off-frame continuation) → Task 1 (`test_..._empty_when_frame_too_short`, `test_..._no_setup_on_flat_frame`) + Task 2 (`..._rejects_nonpositive`).

**Placeholder scan:** No `TBD`/`TODO`; every code step contains complete code. The two tuning notes (Task 3 Step 6, Task 4 Steps 2 & 4) are explicit conditional fallbacks with concrete values, not placeholders.

**Type consistency:** `_pullback_precompute` returns keys `i0`, `decided`, `gross`, `t_i_step`, `t_p_step`, `t_r_step` — consumed exactly so by `PullbackFamily._precompute`/`entry_indices`/`measure_gross` and asserted in `test_pullback_precompute_detects_up_pullback`. The params dict uses keys `impulse_dir`, `m_pips`, `r_frac`, `window_I`, `window_P`, `window_R`, `horizon` consistently across `param_grid`, `_precompute`, `candidate_metadata`, and the `_pullback_precompute` keyword arguments (`horizon` → `h`). `_frame_fingerprint`, `Any`, `pd`, `np` are already in scope in `mining_family.py`; `_pip_size` and `load_bar_frame` are already in scope in `run_tick_opportunity_mining.py` (used by `_double_touch_precompute`).
