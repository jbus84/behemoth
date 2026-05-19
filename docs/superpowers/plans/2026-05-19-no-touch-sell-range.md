# No-touch / Sell-the-Range Family — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `no_touch` mining family that places a symmetric `±K` range-fade bet at every regime bar and scores it as a capped-win (`+K` if no touch) / variable-loss (breakout continuation if touched) payoff against the random-entry baseline.

**Architecture:** `NoTouchFamily` implements the existing `MiningFamily` protocol. It adds **no new precompute engine** — it reuses `_oco_precompute_candidates`, re-interpreting its `decided` / `gross` output as `where(decided, -oco_gross, +K)`. `run()` returns a new fourth frame `(directional, oco, no_touch, summary)`.

**Tech Stack:** Python, NumPy, pandas, pytest. Follows `scripts/mining_family.py` + `scripts/run_tick_opportunity_mining.py`. Spec: `docs/superpowers/specs/2026-05-19-no-touch-sell-range-design.md`.

**Base state:** Sub-project 4 (`pullback`) is merged to `main`. `scripts/mining_family.py` has `MiningFamily`, `_frame_fingerprint`, `FAMILY_REGISTRY`, `_LIBRARY_TYPE_ALIASES`, and `DirectionalFamily`/`OcoFirstTouchFamily`/`DoubleTouchFamily`/`PullbackFamily`. `_oco_precompute_candidates`, `_mine_frame_pair`, `run()` (a 3-tuple), `_build_summary`, `_save_report`, and `scripts/mining_random_baseline.py` all exist. This plan extends those files; it does not create them.

## File Structure

- `scripts/mining_family.py` — add `NoTouchFamily`; register in `FAMILY_REGISTRY`; add the `no_touch` alias to `_LIBRARY_TYPE_ALIASES`.
- `scripts/run_tick_opportunity_mining.py` — extend `run()` (`library_type` check, build the `no_touch` frame, 4-tuple return), `_mine_frame_pair` (`selection_pass` branch), `_build_summary`, `_save_report`, and `main()`.
- `scripts/build_tick_opportunity_ml_dataset.py` — update the `run()` unpack (`no_touch` unused there).
- `tests/test_mining_family.py` — `no_touch` conformance, grid, metadata, hook, and statistical tests.
- `tests/test_tick_opportunity_mining.py` — `_build_range_bound_frame` + `_build_breakout_frame` builders; end-to-end `test_run_mines_no_touch`; update five `run()` unpack sites.
- `tests/test_tick_opportunity_ml_dataset.py` — update the `run()` unpack.
- `tests/test_oco_candidate_family_allowlist.py` — add an explicit `no_touch`-absent assertion.
- `docs/superpowers/specs/2026-05-18-microstructure-research-roadmap.md` — status table row 5 → `Planned`.

---

### Task 1: `NoTouchFamily` — class, registry, alias

**Files:**
- Modify: `scripts/mining_family.py` (add class after `PullbackFamily`, before `FAMILY_REGISTRY`; extend `_LIBRARY_TYPE_ALIASES` and `FAMILY_REGISTRY`)
- Test: `tests/test_mining_family.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_mining_family.py`:

```python
def test_no_touch_family_registered_and_resolves():
    from scripts.mining_family import (
        FAMILY_REGISTRY,
        MiningFamily,
        resolve_families,
    )

    assert resolve_families("no_touch") == ["no_touch"]
    fam = FAMILY_REGISTRY["no_touch"]
    assert fam.name == "no_touch"
    assert isinstance(fam, MiningFamily)


def test_no_touch_family_grid_and_metadata():
    from scripts.mining_family import FAMILY_REGISTRY

    fam = FAMILY_REGISTRY["no_touch"]
    grid = fam.param_grid({"barrier_grid_pips": "2,3", "horizons": "1,2,3"})
    # 2 barrier widths x 3 horizons; symmetric barriers -> no direction axis.
    assert len(grid) == 2 * 3
    assert sorted({g["barrier_pips"] for g in grid}) == [2.0, 3.0]
    assert sorted({g["horizon"] for g in grid}) == [1, 2, 3]
    meta = fam.candidate_metadata(
        "london", {"barrier_pips": 3.0, "horizon": 2}
    )
    assert meta["family"] == "no_touch"
    assert meta["state_id"] == "no_touch__london__K3_h2"
    assert meta["ml_ready_target_type"] == "no_touch"
    assert "K=3" in meta["regime_desc"]


def test_no_touch_family_grid_rejects_non_positive():
    from scripts.mining_family import FAMILY_REGISTRY

    fam = FAMILY_REGISTRY["no_touch"]
    with pytest.raises(ValueError, match="non-positive"):
        fam.param_grid({"barrier_grid_pips": "0,3", "horizons": "1"})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_mining_family.py::test_no_touch_family_registered_and_resolves -v`
Expected: FAIL — `resolve_families("no_touch")` raises `ValueError: unknown library_type`.

- [ ] **Step 3: Add the `no_touch` alias**

In `scripts/mining_family.py`, in `_LIBRARY_TYPE_ALIASES`, add the `no_touch` entry (keep keys readable):

```python
_LIBRARY_TYPE_ALIASES: dict[str, list[str]] = {
    "oco": ["oco_first_touch"],
    "directional": ["directional"],
    "double_touch": ["double_touch"],
    "pullback": ["pullback"],
    "no_touch": ["no_touch"],
    "separate": ["oco_first_touch", "directional"],
}
```

- [ ] **Step 4: Add the `NoTouchFamily` class**

In `scripts/mining_family.py`, immediately after the `PullbackFamily` class and before `FAMILY_REGISTRY`, add:

```python
class NoTouchFamily:
    """Range-fade / sell-the-range family — the honest inverse of
    oco_first_touch. A symmetric +/-K range bet is placed at every regime
    bar: a horizon that completes without touching either barrier wins a
    fixed +K pips; a touch books the breakout continuation as a loss. Reuses
    _oco_precompute_candidates rather than adding a new engine."""

    name = "no_touch"

    def __init__(self) -> None:
        self._cache: dict[tuple[int, tuple[tuple[str, Any], ...]], dict[str, Any] | None] = {}

    def clear_cache(self) -> None:
        """Drop cached precompute results. Long-lived processes should call
        this between mining batches to avoid unbounded growth."""
        self._cache.clear()

    def param_grid(self, cfg: dict[str, Any]) -> list[dict[str, Any]]:
        from scripts.run_tick_opportunity_mining import _parse_floats, _parse_ints

        barriers = _parse_floats(str(cfg["barrier_grid_pips"]))
        horizons = _parse_ints(str(cfg["horizons"]))
        grid: list[dict[str, Any]] = []
        for k in barriers:
            for h in horizons:
                if k <= 0.0 or h <= 0:
                    raise ValueError(f"non-positive grid value: k={k} h={h}")
                grid.append({"barrier_pips": float(k), "horizon": int(h)})
        return grid

    def _precompute(
        self, frame: pd.DataFrame, symbol: str, params: dict[str, Any]
    ) -> dict[str, Any] | None:
        from scripts.run_tick_opportunity_mining import _oco_precompute_candidates

        key = (_frame_fingerprint(frame), tuple(sorted(params.items())))
        if key in self._cache:
            return self._cache[key]
        try:
            result = _oco_precompute_candidates(
                frame,
                symbol=symbol,
                horizon=int(params["horizon"]),
                barrier_pips=float(params["barrier_pips"]),
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
        # Not gated on `decided`: un-touched bars are the wins, not dropped
        # candidates. Every valid regime bar is an entry.
        i0 = np.asarray(prep["i0"], dtype=np.int64)
        reg = np.asarray(regime_mask, dtype=bool)[i0]
        return i0[reg]

    def measure_gross(
        self, frame: pd.DataFrame, entries: np.ndarray, params: dict[str, Any]
    ) -> np.ndarray:
        if "symbol" not in params:
            return np.array([], dtype=float)
        prep = self._precompute(frame, str(params["symbol"]), params)
        if not prep:
            return np.array([], dtype=float)
        i0 = np.asarray(prep["i0"], dtype=np.int64)
        decided = np.asarray(prep["decided"], dtype=bool)
        oco_gross = np.asarray(prep["gross"], dtype=float)
        k = float(params["barrier_pips"])
        # No touch -> +K win. Touch -> -(signed breakout continuation); a
        # decided entry whose continuation exit is out of bounds keeps the
        # NaN that _oco_precompute_candidates already produced.
        nt_gross = np.where(decided, -oco_gross, k)
        pos = pd.Series(np.arange(len(i0)), index=i0)
        mapped = pos.reindex(entries).to_numpy(dtype=float)
        out = np.full(len(entries), np.nan, dtype=float)
        valid = np.isfinite(mapped)
        out[valid] = nt_gross[mapped[valid].astype(np.int64)]
        return out

    def candidate_metadata(
        self, regime_name: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        k = float(params["barrier_pips"])
        h = int(params["horizon"])
        return {
            "family": "no_touch",
            "state_id": f"no_touch__{regime_name}__K{k:g}_h{h}",
            "regime_desc": f"{regime_name};K={k:g};h={h}",
            "ml_ready_target_type": "no_touch",
        }
```

- [ ] **Step 5: Register the family**

In `scripts/mining_family.py`, extend `FAMILY_REGISTRY`:

```python
FAMILY_REGISTRY: dict[str, MiningFamily] = {
    "oco_first_touch": OcoFirstTouchFamily(),
    "directional": DirectionalFamily(),
    "double_touch": DoubleTouchFamily(),
    "pullback": PullbackFamily(),
    "no_touch": NoTouchFamily(),
}
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run pytest tests/test_mining_family.py -k no_touch -v`
Expected: PASS for the three Task 1 tests. `test_registry_entries_satisfy_protocol` also still passes.

- [ ] **Step 7: Commit**

```bash
git add scripts/mining_family.py tests/test_mining_family.py
git commit -m "feat: NoTouchFamily implementing the MiningFamily protocol"
```

---

### Task 2: `no_touch` entry / gross hooks against frame builders

**Files:**
- Create builders in: `tests/test_tick_opportunity_mining.py`
- Test: `tests/test_mining_family.py`

- [ ] **Step 1: Add the frame builders**

In `tests/test_tick_opportunity_mining.py`, append two builders (next to `_build_pullback_frame`):

```python
def _build_range_bound_frame(n: int = 800) -> pd.DataFrame:
    """Flat price with a tiny sub-pip sawtooth — never travels far enough to
    touch a +/-3 pip barrier (peak-to-peak swing 1.2 pips, plus 0.1 pip of
    high/low offset, stays well inside 3 pips). Deterministic: every no_touch
    candidate is a win (decided False -> gross +K)."""
    pip = 0.0001
    saw = (np.arange(n) % 4 - 1.5) * 0.4 * pip  # in [-0.6, +0.6] pips
    close = 1.20000 + saw
    spread = 0.2 * pip
    return pd.DataFrame({
        "close_bid": close,
        "close_ask": close + spread,
        "low_bid": close - 0.1 * pip,
        "high_ask": close + spread + 0.1 * pip,
        "hl_first": np.zeros(n, dtype=float),
    })


def _build_breakout_frame(n: int = 800) -> pd.DataFrame:
    """Steady uptrend (0.8 pip/bar) — from any bar the +K barrier is touched
    fast and price keeps rising. Deterministic: every no_touch candidate is a
    loss (decided True, up-continuation -> negative gross)."""
    pip = 0.0001
    close = 1.20000 + 0.8 * pip * np.arange(n)
    spread = 0.2 * pip
    return pd.DataFrame({
        "close_bid": close,
        "close_ask": close + spread,
        "low_bid": close - 0.1 * pip,
        "high_ask": close + spread + 0.1 * pip,
        "hl_first": np.zeros(n, dtype=float),
    })
```

- [ ] **Step 2: Write the failing hook tests**

Append to `tests/test_mining_family.py`:

```python
def test_no_touch_entry_indices_not_gated_on_decided():
    import numpy as np

    from scripts.mining_family import FAMILY_REGISTRY
    from tests.test_tick_opportunity_mining import _build_breakout_frame

    fam = FAMILY_REGISTRY["no_touch"]
    frame = _build_breakout_frame()
    allmask = np.ones(len(frame), dtype=bool)
    params = {"symbol": "EURUSD", "barrier_pips": 3.0, "horizon": 5}
    entries = fam.entry_indices(frame, allmask, params)
    prep = fam._precompute(frame, "EURUSD", params)
    i0 = np.asarray(prep["i0"], dtype=np.int64)
    # Every barrier is touched on a breakout frame, yet entry_indices still
    # returns the full i0 universe — no_touch does not gate on `decided`.
    assert np.asarray(prep["decided"], dtype=bool).all()
    assert np.array_equal(entries, i0)


def test_no_touch_gross_is_plus_k_when_no_touch():
    import numpy as np

    from scripts.mining_family import FAMILY_REGISTRY
    from tests.test_tick_opportunity_mining import _build_range_bound_frame

    fam = FAMILY_REGISTRY["no_touch"]
    frame = _build_range_bound_frame()
    allmask = np.ones(len(frame), dtype=bool)
    params = {"symbol": "EURUSD", "barrier_pips": 3.0, "horizon": 5}
    entries = fam.entry_indices(frame, allmask, params)
    assert len(entries) > 0
    gross = fam.measure_gross(frame, entries, params)
    gross = gross[np.isfinite(gross)]
    assert gross.size > 0
    # Range never touches a +/-3 pip barrier -> every candidate wins +K.
    assert np.allclose(gross, 3.0)


def test_no_touch_gross_is_negative_on_breakout():
    import numpy as np

    from scripts.mining_family import FAMILY_REGISTRY
    from tests.test_tick_opportunity_mining import _build_breakout_frame

    fam = FAMILY_REGISTRY["no_touch"]
    frame = _build_breakout_frame()
    allmask = np.ones(len(frame), dtype=bool)
    params = {"symbol": "EURUSD", "barrier_pips": 3.0, "horizon": 5}
    entries = fam.entry_indices(frame, allmask, params)
    gross = fam.measure_gross(frame, entries, params)
    gross = gross[np.isfinite(gross)]
    assert gross.size > 0
    # Up-breakout that keeps running -> the range-fade loses.
    assert np.mean(gross) < 0.0
```

- [ ] **Step 3: Run the tests to verify they pass**

Run: `uv run pytest tests/test_mining_family.py -k "no_touch" -v`
Expected: PASS. The hooks are already implemented in Task 1; this task adds the builders and proves the behaviour against them. (If a test errors on `_build_*_frame` import, confirm Step 1 was appended to `tests/test_tick_opportunity_mining.py`.)

- [ ] **Step 4: Commit**

```bash
git add tests/test_tick_opportunity_mining.py tests/test_mining_family.py
git commit -m "test: no_touch entry/gross hooks against range-bound and breakout frames"
```

---

### Task 3: OCO allowlist governance test

**Files:**
- Test: `tests/test_oco_candidate_family_allowlist.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_oco_candidate_family_allowlist.py`:

```python
def test_no_touch_is_not_an_oco_bracket_family() -> None:
    """no_touch reuses the OCO precompute but is a range-fade payoff bet, not
    an OCO bracket family. It must stay out of ALLOWED_OCO_FAMILIES, and the
    `oco_`-prefixed allowlist must not be broadened to cover it."""
    from scripts.mining_family import FAMILY_REGISTRY

    assert "no_touch" in FAMILY_REGISTRY
    assert "no_touch" not in ALLOWED_OCO_FAMILIES
    assert not "no_touch".startswith("oco_")
```

- [ ] **Step 2: Run the test to verify it passes**

Run: `uv run pytest tests/test_oco_candidate_family_allowlist.py -v`
Expected: PASS — `no_touch` is registered (after Task 1), is absent from `ALLOWED_OCO_FAMILIES`, and does not carry the `oco_` prefix, so the existing `test_mining_family_definitions_are_allowlisted` contract still holds.

- [ ] **Step 3: Commit**

```bash
git add tests/test_oco_candidate_family_allowlist.py
git commit -m "test: assert no_touch is not an OCO bracket family"
```

---

### Task 4: Wire `no_touch` into `run()` as a fourth frame

**Files:**
- Modify: `scripts/run_tick_opportunity_mining.py` (`_build_summary`, `_save_report`, `_mine_frame_pair`, `run()`, `main()`)
- Modify: `scripts/build_tick_opportunity_ml_dataset.py:882`
- Modify: `tests/test_tick_opportunity_mining.py` (five unpack sites)
- Modify: `tests/test_tick_opportunity_ml_dataset.py:126`

- [ ] **Step 1: Extend `_build_summary` to accept the `no_touch` frame**

In `scripts/run_tick_opportunity_mining.py`, change the `_build_summary` signature and add the frame:

```python
def _build_summary(
    directional: pd.DataFrame, oco: pd.DataFrame, no_touch: pd.DataFrame
) -> pd.DataFrame:
    frames = []
    if not directional.empty:
        frames.append(directional.assign(library="directional"))
    if not oco.empty:
        frames.append(oco.assign(library="oco"))
    if not no_touch.empty:
        frames.append(no_touch.assign(library="no_touch"))
    summary_rows: list[dict[str, Any]] = []
```

Leave the rest of the function body unchanged — it already groups by `library`.

- [ ] **Step 2: Extend `_save_report` to accept and render the `no_touch` frame**

In `scripts/run_tick_opportunity_mining.py`, change the `_save_report` signature:

```python
def _save_report(
    *,
    report_out: Path,
    cfg: dict[str, Any],
    directional: pd.DataFrame,
    oco: pd.DataFrame,
    no_touch: pd.DataFrame,
    summary: pd.DataFrame,
) -> None:
```

Then, in the body, after the existing `## OCO Top` block (the two `lines.append` for OCO and the blank line), add a `no_touch` section:

```python
    lines.append("## OCO Top")
    lines.append(_top_table(oco))
    lines.append("")
    lines.append("## No-Touch Top")
    lines.append(_top_table(no_touch))
    lines.append("")
```

- [ ] **Step 3: Add `no_touch` to the `_mine_frame_pair` selection branch**

In `scripts/run_tick_opportunity_mining.py`, in `_mine_frame_pair`, extend the `selection_pass` family tuple so `no_touch` uses the annualized-fills criterion:

```python
                # selection_pass
                if fam_name in (
                    "directional", "double_touch", "pullback", "no_touch"
                ):
                    train_annual = (
```

Leave the `else` branch unchanged.

- [ ] **Step 4: Extend `run()` — `library_type`, build the frame, 4-tuple return**

In `scripts/run_tick_opportunity_mining.py`, change the `run()` signature return type:

```python
def run(cfg: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
```

Change the `library_type` validation:

```python
    if library_type not in {
        "separate", "directional", "oco", "double_touch", "pullback", "no_touch"
    }:
        raise ValueError(
            "library_type must be "
            "separate|directional|oco|double_touch|pullback|no_touch"
        )
```

Replace the frame-assembly + return block at the end of `run()` (currently `directional = ...` through `return directional, oco, summary`) with:

```python
    directional = pd.DataFrame(
        per_family_rows.get("directional", [])
        + per_family_rows.get("double_touch", [])
        + per_family_rows.get("pullback", [])
    )
    oco = pd.DataFrame(per_family_rows.get("oco_first_touch", []))
    no_touch = pd.DataFrame(per_family_rows.get("no_touch", []))
    if not directional.empty:
        directional = _assign_quality_tier(directional, library="directional")
        directional = _stamp_candidate_contract(directional)
    if not oco.empty:
        oco = _assign_quality_tier(oco, library="oco")
        oco = _stamp_candidate_contract(oco)
    if not no_touch.empty:
        no_touch = _assign_quality_tier(no_touch, library="no_touch")
        no_touch = _stamp_candidate_contract(no_touch)
    summary = _build_summary(directional, oco, no_touch)
    return directional, oco, no_touch, summary
```

- [ ] **Step 5: Update `main()` — unpack the 4-tuple and write the CSV**

In `scripts/run_tick_opportunity_mining.py` `main()`, change the unpack and add the `no_touch` CSV. Replace:

```python
    directional, oco, summary = run(cfg)

    out_dir = Path(str(cfg["out_dir"]))
    out_dir.mkdir(parents=True, exist_ok=True)
    symbol = str(cfg["symbol"]).upper().strip()

    d_path = out_dir / f"{symbol}_directional_candidates.csv"
    o_path = out_dir / f"{symbol}_oco_candidates.csv"
    s_path = out_dir / f"{symbol}_candidate_summary.csv"
    directional.to_csv(d_path, index=False)
    oco.to_csv(o_path, index=False)
    summary.to_csv(s_path, index=False)
    print(f"wrote: {d_path}")
    print(f"wrote: {o_path}")
    print(f"wrote: {s_path}")

    report_out = Path(str(cfg["report_out"]))
    _save_report(report_out=report_out, cfg=cfg, directional=directional, oco=oco, summary=summary)
```

with:

```python
    directional, oco, no_touch, summary = run(cfg)

    out_dir = Path(str(cfg["out_dir"]))
    out_dir.mkdir(parents=True, exist_ok=True)
    symbol = str(cfg["symbol"]).upper().strip()

    d_path = out_dir / f"{symbol}_directional_candidates.csv"
    o_path = out_dir / f"{symbol}_oco_candidates.csv"
    nt_path = out_dir / f"{symbol}_no_touch_candidates.csv"
    s_path = out_dir / f"{symbol}_candidate_summary.csv"
    directional.to_csv(d_path, index=False)
    oco.to_csv(o_path, index=False)
    no_touch.to_csv(nt_path, index=False)
    summary.to_csv(s_path, index=False)
    print(f"wrote: {d_path}")
    print(f"wrote: {o_path}")
    print(f"wrote: {nt_path}")
    print(f"wrote: {s_path}")

    report_out = Path(str(cfg["report_out"]))
    _save_report(
        report_out=report_out, cfg=cfg, directional=directional,
        oco=oco, no_touch=no_touch, summary=summary,
    )
```

- [ ] **Step 6: Update the `build_tick_opportunity_ml_dataset.py` unpack**

In `scripts/build_tick_opportunity_ml_dataset.py:882`, change:

```python
    directional, oco, summary = run(cfg)
```

to (the `no_touch` frame is intentionally unused here — Non-Goal: no ml-dataset change):

```python
    directional, oco, _no_touch, summary = run(cfg)
```

- [ ] **Step 7: Update the test unpack sites**

In `tests/test_tick_opportunity_mining.py`, update all five `run()` unpack sites:

- Line 204, 534, 565 — change `directional, oco, summary = run(cfg)` to `directional, oco, _no_touch, summary = run(cfg)`.
- Line 657, 741 — change `directional, oco, _ = run(cfg)` to `directional, oco, _no_touch, _ = run(cfg)`.

In `tests/test_tick_opportunity_ml_dataset.py:126`, change `directional, oco, summary = run(cfg)` to `directional, oco, _no_touch, summary = run(cfg)`.

- [ ] **Step 8: Run the full affected suite to verify nothing regressed**

Run: `uv run pytest tests/test_tick_opportunity_mining.py tests/test_mining_family.py tests/test_oco_candidate_family_allowlist.py tests/test_tick_opportunity_ml_dataset.py -q`
Expected: PASS — all existing tests green with the 4-tuple `run()`.

- [ ] **Step 9: Commit**

```bash
git add scripts/run_tick_opportunity_mining.py scripts/build_tick_opportunity_ml_dataset.py tests/test_tick_opportunity_mining.py tests/test_tick_opportunity_ml_dataset.py
git commit -m "feat: run() returns a fourth no_touch candidate frame"
```

---

### Task 5: End-to-end `test_run_mines_no_touch`

**Files:**
- Test: `tests/test_tick_opportunity_mining.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_tick_opportunity_mining.py` (next to `test_run_mines_pullback`):

```python
def test_run_mines_no_touch(tmp_path: Path) -> None:
    dataset_dir = tmp_path / "tick_velocity"
    dataset_dir.mkdir(parents=True, exist_ok=True)
    _build_synth_tick_velocity(dataset_dir / "EURUSD_1000tick_velocity.parquet",
                               symbol="EURUSD")
    cfg = {
        "symbol": "EURUSD", "dataset_dir": str(dataset_dir),
        "bar_ticks_grid": "1000", "horizons": "1,2,3",
        "train_years": "2022,2023,2024", "test_year": 2025,
        "min_annual_fills": 50.0, "gross_metric": "mean",
        "library_type": "no_touch", "barrier_grid_pips": "2,3",
        "baseline_seed": 12345, "baseline_draws": 20,
    }
    directional, oco, no_touch, _ = run(cfg)
    # no_touch is a payoff family -> its own frame; others stay empty.
    assert directional.empty
    assert oco.empty
    assert not no_touch.empty, "no_touch should produce candidates"
    assert (no_touch["family"] == "no_touch").all()
    assert no_touch["selection_pass"].isin([True, False]).all()
    for col in ("random_baseline_z", "random_baseline_p"):
        assert col in no_touch.columns
```

- [ ] **Step 2: Run the test to verify it passes**

Run: `uv run pytest tests/test_tick_opportunity_mining.py::test_run_mines_no_touch -v`
Expected: PASS — `run()` mines the `no_touch` family end to end and returns a populated fourth frame.

- [ ] **Step 3: Commit**

```bash
git add tests/test_tick_opportunity_mining.py
git commit -m "test: end-to-end run() mines the no_touch family"
```

---

### Task 6: Statistical tests — no-false-edge and detects-structure

**Files:**
- Test: `tests/test_mining_family.py`

- [ ] **Step 1: Write the failing statistical tests**

Append to `tests/test_mining_family.py`:

```python
def test_no_touch_no_false_edge_on_driftless_data():
    import numpy as np

    from scripts.mining_family import FAMILY_REGISTRY
    from scripts.mining_random_baseline import random_entry_baseline

    fam = FAMILY_REGISTRY["no_touch"]
    # A driftless random walk: no regime is structurally calmer than another,
    # so a no_touch bet must NOT clear the random-entry baseline.
    rng = np.random.default_rng(20260519)
    n = 4000
    pip = 0.0001
    steps = rng.normal(0.0, 0.6 * pip, size=n)
    close = 1.30000 + np.cumsum(steps)
    spread = 0.2 * pip
    frame = pd.DataFrame({
        "close_bid": close,
        "close_ask": close + spread,
        "low_bid": close - 0.2 * pip,
        "high_ask": close + spread + 0.2 * pip,
        "hl_first": np.zeros(n, dtype=float),
    })
    regime_mask = np.zeros(len(frame), dtype=bool)
    regime_mask[: n // 2] = True
    params = {"symbol": "EURUSD", "barrier_pips": 3.0, "horizon": 8}
    entries = fam.entry_indices(frame, regime_mask, params)
    assert len(entries) > 0
    gross = fam.measure_gross(frame, entries, params)
    gross = gross[np.isfinite(gross)]
    cand_ev = float(np.mean(gross))
    baseline = random_entry_baseline(
        fam, frame, params,
        n_entries=len(entries), n_draws=200,
        rng=np.random.default_rng(7),
        candidate_gross_ev=cand_ev,
    )
    assert abs(baseline["random_baseline_z"]) < 2.0


def test_no_touch_detects_structure_on_range_bound_regime():
    import numpy as np

    from scripts.mining_family import FAMILY_REGISTRY
    from scripts.mining_random_baseline import random_entry_baseline

    fam = FAMILY_REGISTRY["no_touch"]
    # First 2000 bars are a tight range (no barrier ever touched -> +K wins);
    # last 2000 are a strong trend (barriers touched, breakouts run -> losses).
    # A regime restricted to the range should beat the random-entry baseline,
    # because random draws sample the trending half too, diluting the control.
    n = 4000
    pip = 0.0001
    saw = (np.arange(2000) % 4 - 1.5) * 0.4 * pip  # +/-0.6 pip, never touches
    calm = 1.30000 + saw
    trend = calm[-1] + 0.8 * pip * np.arange(1, 2001)
    close = np.concatenate([calm, trend])
    spread = 0.2 * pip
    frame = pd.DataFrame({
        "close_bid": close,
        "close_ask": close + spread,
        "low_bid": close - 0.1 * pip,
        "high_ask": close + spread + 0.1 * pip,
        "hl_first": np.zeros(n, dtype=float),
    })
    regime_mask = np.zeros(len(frame), dtype=bool)
    regime_mask[:2000] = True
    params = {"symbol": "EURUSD", "barrier_pips": 3.0, "horizon": 8}
    entries = fam.entry_indices(frame, regime_mask, params)
    assert len(entries) > 0
    gross = fam.measure_gross(frame, entries, params)
    gross = gross[np.isfinite(gross)]
    cand_ev = float(np.mean(gross))
    baseline = random_entry_baseline(
        fam, frame, params,
        n_entries=len(entries), n_draws=200,
        rng=np.random.default_rng(7),
        candidate_gross_ev=cand_ev,
    )
    assert baseline["random_baseline_z"] > 2.0
```

- [ ] **Step 2: Run the tests to verify they pass**

Run: `uv run pytest tests/test_mining_family.py -k "no_touch and (false_edge or structure)" -v`
Expected: PASS — driftless data yields `|z| < 2.0`; the range-bound regime yields `z > 2.0`, both without tuning. If `detects_structure` does not clear `z > 2.0`, widen the range/trend separation (longer horizon or steeper trend) rather than lowering the threshold.

- [ ] **Step 3: Commit**

```bash
git add tests/test_mining_family.py
git commit -m "test: no-false-edge + detects-structure tests for no_touch"
```

---

### Task 7: Update the roadmap status table

**Files:**
- Modify: `docs/superpowers/specs/2026-05-18-microstructure-research-roadmap.md`

- [ ] **Step 1: Update row 5 to `Planned`**

In `docs/superpowers/specs/2026-05-18-microstructure-research-roadmap.md`, change the row:

```
| 5 | No-touch / sell-the-range | [design](2026-05-19-no-touch-sell-range-design.md) | — | Specced |
```

to:

```
| 5 | No-touch / sell-the-range | [design](2026-05-19-no-touch-sell-range-design.md) | [plan](../plans/2026-05-19-no-touch-sell-range.md) | Planned |
```

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/specs/2026-05-18-microstructure-research-roadmap.md
git commit -m "docs: mark no_touch sub-project 5 as Planned"
```

---

## Final Verification

- [ ] Run the full mining + family suite:
  `uv run pytest tests/test_tick_opportunity_mining.py tests/test_mining_family.py tests/test_oco_candidate_family_allowlist.py tests/test_tick_opportunity_ml_dataset.py -q`
  Expected: all PASS.
- [ ] Confirm `library_type=no_touch` runs end to end via `test_run_mines_no_touch`.
- [ ] Open a PR from the `worktree-no-touch-sell-range` branch.
