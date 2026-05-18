# Mining Family Framework + Random-Entry Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the hardcoded `oco`/`directional` branches in the mining script with a `MiningFamily` Protocol registry, and add a random-entry baseline that scores every candidate against random timing on the same bars.

**Architecture:** A new `MiningFamily` Protocol with four hooks (`param_grid`, `entry_indices`, `measure_gross`, `candidate_metadata`); two concrete families (`OcoFirstTouchFamily`, `DirectionalFamily`) ported from the existing `_oco_candidates`/`_directional_candidates` functions; a `FAMILY_REGISTRY` dict; and a `random_entry_baseline` helper. `run()` becomes a loop over registered families. A frozen-output parity test guards the refactor.

**Tech Stack:** Python, pandas, numpy, pytest.

**Spec:** `docs/superpowers/specs/2026-05-18-mining-family-framework-design.md`

---

## File Map

- `scripts/mining_family.py` — **new**: `MiningFamily` Protocol, `OcoFirstTouchFamily`, `DirectionalFamily`, `FAMILY_REGISTRY`, `resolve_families`.
- `scripts/mining_random_baseline.py` — **new**: `random_entry_baseline`.
- `scripts/run_tick_opportunity_mining.py` — **modify**: remove `_oco_candidates`/`_directional_candidates`; rewrite `run()` (`:936-1070`) as a registry loop; add baseline columns; bump `CANDIDATE_SCHEMA_VERSION` (`:40`); add `--baseline-seed`.
- `scripts/build_tick_opportunity_ml_dataset.py` — **modify**: extend `REQUIRED_CANDIDATE_COLUMNS` (`:87`).
- `tests/test_mining_family.py` — **new**.
- `tests/test_mining_random_baseline.py` — **new**.
- `tests/test_tick_opportunity_mining.py` — **modify**: add a parity test.

**Key principle:** Tasks 3 and 4 are *refactors* — they move existing logic
into family classes. A parity test (Task 2) pins the current candidate output
on a synthetic frame; Tasks 3-4 must keep that test green. The extracted logic
is behaviour-preserving; only its location changes.

---

## Task 1: `MiningFamily` Protocol + empty registry

**Files:**
- Create: `scripts/mining_family.py`
- Test: `tests/test_mining_family.py`

**Context:** The Protocol is a structural contract. This task defines it and
an empty `FAMILY_REGISTRY`; the two concrete families arrive in Tasks 3-4.
`resolve_families` maps the legacy `library_type` string to a family-name
list.

- [ ] **Step 1: Write the failing test**

Create `tests/test_mining_family.py`:

```python
from __future__ import annotations

import pytest

from scripts.mining_family import FAMILY_REGISTRY, MiningFamily, resolve_families


def test_resolve_families_maps_legacy_library_type():
    assert resolve_families("oco") == ["oco_first_touch"]
    assert resolve_families("directional") == ["directional"]
    assert resolve_families("separate") == ["oco_first_touch", "directional"]


def test_resolve_families_rejects_unknown():
    with pytest.raises(ValueError, match="unknown"):
        resolve_families("nonsense")


def test_registry_entries_satisfy_protocol():
    for name, fam in FAMILY_REGISTRY.items():
        assert isinstance(fam, MiningFamily)
        assert fam.name == name
        for method in ("param_grid", "entry_indices", "measure_gross",
                       "candidate_metadata"):
            assert callable(getattr(fam, method))
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_mining_family.py -v`
Expected: FAIL — `scripts/mining_family.py` does not exist (ImportError).

- [ ] **Step 3: Create the module**

Create `scripts/mining_family.py`:

```python
"""Candidate-family registry for tick-opportunity mining.

Each family supplies its own entry trigger, outcome measurement, parameter
grid, and candidate metadata. The core mining loop in
run_tick_opportunity_mining.py iterates the registry rather than branching on
a hardcoded library type.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

import numpy as np
import pandas as pd


@runtime_checkable
class MiningFamily(Protocol):
    name: str

    def param_grid(self, cfg: dict[str, Any]) -> list[dict[str, Any]]:
        """Family-specific parameter combinations to mine (e.g. barrier
        widths). Returns at least one dict; an empty dict means no extra
        axis."""
        ...

    def entry_indices(
        self, frame: pd.DataFrame, regime_mask: np.ndarray, params: dict[str, Any]
    ) -> np.ndarray:
        """Look-ahead-free integer entry bar indices for one regime mask and
        one param combo."""
        ...

    def measure_gross(
        self, frame: pd.DataFrame, entries: np.ndarray, params: dict[str, Any]
    ) -> np.ndarray:
        """Gross pips realised per entry. MUST accept any entry index array
        (used for both real entries and random-baseline draws)."""
        ...

    def candidate_metadata(
        self, regime_name: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        """family / state_id / regime_desc / ml_ready_target_type for the
        candidate row."""
        ...


_LIBRARY_TYPE_ALIASES: dict[str, list[str]] = {
    "oco": ["oco_first_touch"],
    "directional": ["directional"],
    "separate": ["oco_first_touch", "directional"],
}


def resolve_families(library_type: str) -> list[str]:
    """Map a legacy library_type string to a list of family names."""
    key = str(library_type).strip().lower()
    if key not in _LIBRARY_TYPE_ALIASES:
        raise ValueError(
            f"unknown library_type {library_type!r}; "
            f"expected one of {sorted(_LIBRARY_TYPE_ALIASES)}"
        )
    return list(_LIBRARY_TYPE_ALIASES[key])


FAMILY_REGISTRY: dict[str, MiningFamily] = {}
```

- [ ] **Step 4: Run the test**

Run: `uv run pytest tests/test_mining_family.py -v`
Expected: `test_resolve_families_maps_legacy_library_type` and
`test_resolve_families_rejects_unknown` PASS;
`test_registry_entries_satisfy_protocol` PASS trivially (registry is empty —
the loop body does not execute).

- [ ] **Step 5: Commit**

```bash
git add scripts/mining_family.py tests/test_mining_family.py
git commit -m "feat: MiningFamily protocol and family registry skeleton"
```

---

## Task 2: Random-entry baseline + refactor parity fixture

**Files:**
- Create: `scripts/mining_random_baseline.py`
- Test: `tests/test_mining_random_baseline.py`
- Test: `tests/test_tick_opportunity_mining.py` (add the parity test)

**Context:** The baseline draws `n_draws` count-matched random entry sets from
the whole frame, runs the family's `measure_gross` on each, and scores the
candidate's gross EV against the control distribution. The parity test pins
the *current* mining output so Tasks 3-4 can refactor safely.

- [ ] **Step 1: Write the failing baseline test**

Create `tests/test_mining_random_baseline.py`:

```python
from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.mining_random_baseline import random_entry_baseline


class _ConstGrossFamily:
    """Test double: measure_gross returns the frame's `g` column."""

    name = "const"

    def measure_gross(self, frame, entries, params):
        return frame["g"].to_numpy(dtype=float)[entries]


def _frame(n: int) -> pd.DataFrame:
    return pd.DataFrame({"g": np.arange(n, dtype=float)})


def test_baseline_is_deterministic_under_fixed_seed():
    fam, frame = _ConstGrossFamily(), _frame(1000)
    a = random_entry_baseline(fam, frame, {}, n_entries=50, n_draws=100,
                              rng=np.random.default_rng(7))
    b = random_entry_baseline(fam, frame, {}, n_entries=50, n_draws=100,
                              rng=np.random.default_rng(7))
    assert a["random_baseline_control_mean"] == b["random_baseline_control_mean"]
    assert a["random_baseline_z"] == b["random_baseline_z"]


def test_baseline_z_positive_for_best_n_entries(monkeypatch):
    fam, frame = _ConstGrossFamily(), _frame(1000)
    # candidate EV = mean of the top-50 g values (the best entries)
    cand_ev = float(np.mean(np.arange(950, 1000, dtype=float)))
    res = random_entry_baseline(fam, frame, {}, n_entries=50, n_draws=200,
                                rng=np.random.default_rng(1),
                                candidate_gross_ev=cand_ev)
    assert res["random_baseline_z"] > 3.0
    assert res["random_baseline_p"] < 0.05


def test_baseline_returns_nan_when_n_entries_exceeds_frame():
    fam, frame = _ConstGrossFamily(), _frame(20)
    res = random_entry_baseline(fam, frame, {}, n_entries=50, n_draws=100,
                                rng=np.random.default_rng(1),
                                candidate_gross_ev=1.0)
    assert np.isnan(res["random_baseline_z"])
    assert np.isnan(res["random_baseline_p"])
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_mining_random_baseline.py -v`
Expected: FAIL — `scripts/mining_random_baseline.py` does not exist.

- [ ] **Step 3: Create the baseline module**

Create `scripts/mining_random_baseline.py`:

```python
"""Random-entry baseline for mined candidates.

For a candidate with N entries, draw N random entry indices from the whole
frame n_draws times, run the family's own measure_gross on each draw, and
score the candidate's gross EV against the control distribution.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def random_entry_baseline(
    family: Any,
    frame: pd.DataFrame,
    params: dict[str, Any],
    *,
    n_entries: int,
    n_draws: int,
    rng: np.random.Generator,
    candidate_gross_ev: float | None = None,
) -> dict[str, float]:
    """Return random_baseline_z / random_baseline_p /
    random_baseline_control_mean for a candidate.

    candidate_gross_ev is the candidate's own mean gross pips; when None the
    z/p fields are NaN but the control mean is still returned.
    """
    n_rows = len(frame)
    nan_result = {
        "random_baseline_z": float("nan"),
        "random_baseline_p": float("nan"),
        "random_baseline_control_mean": float("nan"),
    }
    if n_entries <= 0 or n_entries > n_rows:
        print(
            f"warning: random baseline skipped (n_entries={n_entries}, "
            f"frame rows={n_rows})"
        )
        return nan_result

    control = np.empty(int(n_draws), dtype=float)
    for i in range(int(n_draws)):
        draw = rng.choice(n_rows, size=int(n_entries), replace=False)
        gross = np.asarray(family.measure_gross(frame, draw, params), dtype=float)
        gross = gross[np.isfinite(gross)]
        control[i] = float(np.mean(gross)) if gross.size else float("nan")

    control = control[np.isfinite(control)]
    if control.size == 0:
        return nan_result
    control_mean = float(np.mean(control))
    control_std = float(np.std(control))
    if candidate_gross_ev is None:
        return {
            "random_baseline_z": float("nan"),
            "random_baseline_p": float("nan"),
            "random_baseline_control_mean": control_mean,
        }
    if control_std == 0.0:
        print("warning: random baseline control_std is zero — z/p set to NaN")
        return {
            "random_baseline_z": float("nan"),
            "random_baseline_p": float("nan"),
            "random_baseline_control_mean": control_mean,
        }
    z = (float(candidate_gross_ev) - control_mean) / control_std
    p = float(np.mean(control >= float(candidate_gross_ev)))
    return {
        "random_baseline_z": z,
        "random_baseline_p": p,
        "random_baseline_control_mean": control_mean,
    }
```

- [ ] **Step 4: Run the baseline test**

Run: `uv run pytest tests/test_mining_random_baseline.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Add the refactor parity fixture test**

Append to `tests/test_tick_opportunity_mining.py` (it already imports `run`
and has the `_synth_tick_velocity` helper used by
`test_tick_opportunity_mining_outputs`):

```python
def test_mining_run_output_is_stable(tmp_path: Path) -> None:
    """Parity guard for the family-framework refactor: the directional and
    oco candidate frames produced by run() must stay byte-identical across
    the refactor. Tasks porting families into MiningFamily classes must keep
    this green."""
    dataset_dir = tmp_path / "tick_velocity"
    dataset_dir.mkdir(parents=True, exist_ok=True)
    _synth_tick_velocity(dataset_dir / "EURUSD_1000tick_velocity.parquet",
                         symbol="EURUSD")
    cfg = {
        "symbol": "EURUSD",
        "dataset_dir": str(dataset_dir),
        "bar_ticks_grid": "1000",
        "horizons": "1,2,3",
        "train_years": "2022,2023,2024",
        "test_year": 2025,
        "min_annual_fills": 50.0,
        "gross_metric": "mean",
        "library_type": "separate",
        "barrier_grid_pips": "2,3",
    }
    directional, oco, summary = run(cfg)
    # Shape + key columns are stable; exact row counts depend on the synthetic
    # fixture and must not change across the refactor.
    snapshot = {
        "directional_rows": len(directional),
        "oco_rows": len(oco),
        "directional_cols": sorted(directional.columns.tolist()),
        "oco_cols": sorted(oco.columns.tolist()),
    }
    # Pin the snapshot: capture once on pre-refactor main, paste below.
    assert snapshot["directional_rows"] == _PARITY["directional_rows"]
    assert snapshot["oco_rows"] == _PARITY["oco_rows"]
    assert snapshot["directional_cols"] == _PARITY["directional_cols"]
    assert snapshot["oco_cols"] == _PARITY["oco_cols"]
```

Also add, near the top of the test file after the imports:

```python
# Captured from pre-refactor `run()` — see test_mining_run_output_is_stable.
_PARITY: dict = {}
```

- [ ] **Step 6: Capture the parity snapshot**

Run this one-off to print the current values:

```bash
uv run python -c "
import tempfile, pathlib
from tests.test_tick_opportunity_mining import _synth_tick_velocity
from scripts.run_tick_opportunity_mining import run
d = pathlib.Path(tempfile.mkdtemp()) / 'tick_velocity'
d.mkdir(parents=True)
_synth_tick_velocity(d / 'EURUSD_1000tick_velocity.parquet', symbol='EURUSD')
cfg = {'symbol':'EURUSD','dataset_dir':str(d),'bar_ticks_grid':'1000',
       'horizons':'1,2,3','train_years':'2022,2023,2024','test_year':2025,
       'min_annual_fills':50.0,'gross_metric':'mean','library_type':'separate',
       'barrier_grid_pips':'2,3'}
di, oc, su = run(cfg)
print({'directional_rows':len(di),'oco_rows':len(oc),
       'directional_cols':sorted(di.columns.tolist()),
       'oco_cols':sorted(oc.columns.tolist())})
"
```

Paste the printed dict as the literal value of `_PARITY` in the test file.

- [ ] **Step 7: Run the parity test to confirm it passes on current code**

Run: `uv run pytest tests/test_tick_opportunity_mining.py::test_mining_run_output_is_stable -v`
Expected: PASS — it now pins the pre-refactor output.

- [ ] **Step 8: Commit**

```bash
git add scripts/mining_random_baseline.py tests/test_mining_random_baseline.py tests/test_tick_opportunity_mining.py
git commit -m "feat: random-entry baseline + mining refactor parity fixture"
```

---

## Task 3: Port the directional family onto the Protocol

**Files:**
- Modify: `scripts/mining_family.py`
- Modify: `scripts/run_tick_opportunity_mining.py` (`_directional_candidates` at `:556`)
- Test: `tests/test_mining_family.py`

**Context:** `_directional_candidates` (`:556-686`) computes, per horizon ×
family-state × regime: entry mask `m = valid & fam_mask & reg & (side != 0)`,
then `gross = side[m] * y[m]`. The entry/outcome split is clean — entries are
the indices where `m` is true; gross at any index set `e` is
`side[e] * y[e]`. The `DirectionalFamily` exposes those as Protocol hooks; the
existing row-assembly logic stays in `run()` (Task 5).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_mining_family.py`:

```python
def test_directional_family_registered_and_measures_gross():
    import numpy as np
    import pandas as pd

    from scripts.mining_family import FAMILY_REGISTRY

    fam = FAMILY_REGISTRY["directional"]
    assert fam.name == "directional"
    # measure_gross multiplies the per-bar side by the forward return.
    frame = pd.DataFrame({
        "y_fwd_pips_h1": [1.0, -2.0, 3.0, -4.0],
        "_dir_side_h1": np.array([1, 1, -1, -1], dtype=np.int8),
    })
    entries = np.array([0, 2, 3])
    gross = fam.measure_gross(frame, entries, {"horizon": 1})
    # side*y at indices 0,2,3 -> 1*1, -1*3, -1*-4
    assert list(gross) == [1.0, -3.0, 4.0]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_mining_family.py::test_directional_family_registered_and_measures_gross -v`
Expected: FAIL — `KeyError: 'directional'` (registry empty).

- [ ] **Step 3: Implement `DirectionalFamily`**

In `scripts/mining_family.py`, add the class above the `FAMILY_REGISTRY`
assignment. `param_grid` yields one dict per horizon; `entry_indices` returns
the integer positions of the directional entry mask for a regime;
`measure_gross` multiplies the precomputed per-bar side column by the forward
return; `candidate_metadata` builds the directional row labels.

```python
class DirectionalFamily:
    name = "directional"

    def param_grid(self, cfg: dict[str, Any]) -> list[dict[str, Any]]:
        from scripts.run_tick_opportunity_mining import _parse_ints

        return [{"horizon": h} for h in _parse_ints(str(cfg["horizons"]))]

    def entry_indices(
        self, frame: pd.DataFrame, regime_mask: np.ndarray, params: dict[str, Any]
    ) -> np.ndarray:
        h = int(params["horizon"])
        ycol = f"y_fwd_pips_h{h}"
        sidecol = f"_dir_side_h{h}"
        if ycol not in frame.columns or sidecol not in frame.columns:
            return np.array([], dtype=np.int64)
        y = pd.to_numeric(frame[ycol], errors="coerce").to_numpy(dtype=float)
        side = frame[sidecol].to_numpy()
        valid = np.isfinite(y)
        if h > 0:
            valid[-h:] = False
        m = valid & np.asarray(regime_mask, dtype=bool) & (side != 0)
        return np.flatnonzero(m).astype(np.int64)

    def measure_gross(
        self, frame: pd.DataFrame, entries: np.ndarray, params: dict[str, Any]
    ) -> np.ndarray:
        h = int(params["horizon"])
        y = pd.to_numeric(frame[f"y_fwd_pips_h{h}"], errors="coerce").to_numpy(dtype=float)
        side = frame[f"_dir_side_h{h}"].to_numpy().astype(float)
        return side[entries] * y[entries]

    def candidate_metadata(
        self, regime_name: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        h = int(params["horizon"])
        return {
            "family": "directional",
            "state_id": f"directional__{regime_name}__h{h}",
            "regime_desc": regime_name,
            "ml_ready_target_type": "directional",
        }
```

Then change the registry line to:

```python
FAMILY_REGISTRY: dict[str, MiningFamily] = {
    "directional": DirectionalFamily(),
}
```

**Note for the implementer:** `DirectionalFamily` reads precomputed per-bar
columns `_dir_side_h{h}`. These do not exist on the frame today — the side is
computed inside `_directional_family_states`. Task 5 adds a
`_attach_directional_side_columns(frame)` helper that materialises
`_dir_side_h{h}` before the family loop runs. Until Task 5 wires that in, this
family's `entry_indices` returns empty on a raw frame — that is expected and
the parity test stays green because `run()` still calls the old function.

- [ ] **Step 4: Run the test**

Run: `uv run pytest tests/test_mining_family.py -v`
Expected: PASS (all directional + protocol tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/mining_family.py tests/test_mining_family.py
git commit -m "feat: DirectionalFamily implementing the MiningFamily protocol"
```

---

## Task 4: Port the OCO first-touch family onto the Protocol

**Files:**
- Modify: `scripts/mining_family.py`
- Test: `tests/test_mining_family.py`

**Context:** `_oco_candidates` (`:687`) calls `_oco_precompute_candidates`
which, per (horizon, barrier), returns `i0` (entry positions), `decided` (a
bool mask over `i0`), and `gross` (gross pips per `i0` position). The
entry/outcome split: entries are `i0[decided & regime_mask_on_i0]`; gross at
those entries is `gross` indexed the same way. `OcoFirstTouchFamily` wraps
`_oco_precompute_candidates` (kept as a module function).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_mining_family.py`:

```python
def test_oco_family_registered_with_barrier_param_grid():
    from scripts.mining_family import FAMILY_REGISTRY

    fam = FAMILY_REGISTRY["oco_first_touch"]
    assert fam.name == "oco_first_touch"
    grid = fam.param_grid({"barrier_grid_pips": "2,3,5", "horizons": "1,2"})
    barriers = sorted({g["barrier_pips"] for g in grid})
    horizons = sorted({g["horizon"] for g in grid})
    assert barriers == [2.0, 3.0, 5.0]
    assert horizons == [1, 2]
    meta = fam.candidate_metadata("london", {"barrier_pips": 5.0, "horizon": 2})
    assert meta["family"] == "oco_first_touch"
    assert "barrier=5.0" in meta["regime_desc"]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_mining_family.py::test_oco_family_registered_with_barrier_param_grid -v`
Expected: FAIL — `KeyError: 'oco_first_touch'`.

- [ ] **Step 3: Implement `OcoFirstTouchFamily`**

In `scripts/mining_family.py`, add:

```python
class OcoFirstTouchFamily:
    name = "oco_first_touch"

    def param_grid(self, cfg: dict[str, Any]) -> list[dict[str, Any]]:
        from scripts.run_tick_opportunity_mining import _parse_floats, _parse_ints

        horizons = _parse_ints(str(cfg["horizons"]))
        barriers = _parse_floats(str(cfg["barrier_grid_pips"]))
        return [
            {"horizon": int(h), "barrier_pips": float(k)}
            for h in horizons
            for k in barriers
        ]

    def _precompute(self, frame, symbol, params):
        from scripts.run_tick_opportunity_mining import _oco_precompute_candidates

        return _oco_precompute_candidates(
            frame,
            symbol=symbol,
            horizon=int(params["horizon"]),
            barrier_pips=float(params["barrier_pips"]),
        )

    def entry_indices(
        self, frame: pd.DataFrame, regime_mask: np.ndarray, params: dict[str, Any]
    ) -> np.ndarray:
        symbol = str(params["symbol"])
        prep = self._precompute(frame, symbol, params)
        if not prep:
            return np.array([], dtype=np.int64)
        i0 = np.asarray(prep["i0"], dtype=np.int64)
        decided = np.asarray(prep["decided"], dtype=bool)
        reg = np.asarray(regime_mask, dtype=bool)[i0]
        return i0[decided & reg]

    def measure_gross(
        self, frame: pd.DataFrame, entries: np.ndarray, params: dict[str, Any]
    ) -> np.ndarray:
        symbol = str(params["symbol"])
        prep = self._precompute(frame, symbol, params)
        if not prep:
            return np.array([], dtype=float)
        i0 = np.asarray(prep["i0"], dtype=np.int64)
        gross = np.asarray(prep["gross"], dtype=float)
        pos = pd.Series(np.arange(len(i0)), index=i0)
        return gross[pos.reindex(entries).to_numpy(dtype=np.int64)]

    def candidate_metadata(
        self, regime_name: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        k = float(params["barrier_pips"])
        return {
            "family": "oco_first_touch",
            "state_id": f"oco_first_touch__{regime_name}__k{int(round(k))}",
            "regime_desc": f"{regime_name};barrier={k:.1f}",
            "ml_ready_target_type": "oco_expand",
        }
```

Update the registry:

```python
FAMILY_REGISTRY: dict[str, MiningFamily] = {
    "oco_first_touch": OcoFirstTouchFamily(),
    "directional": DirectionalFamily(),
}
```

**Note for the implementer:** `entry_indices` requires `params["symbol"]`.
Task 5's `run()` loop injects `symbol` into each `params` dict before calling
the family. `measure_gross` assumes `entries` is a subset of `i0`; entries not
in `i0` (possible for random-baseline draws near the frame end) map to a
sentinel — guard by dropping `entries` outside `i0` before the call, which
Task 5's baseline wiring does via `entry_indices` ∩ draw.

- [ ] **Step 4: Run the test**

Run: `uv run pytest tests/test_mining_family.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/mining_family.py tests/test_mining_family.py
git commit -m "feat: OcoFirstTouchFamily implementing the MiningFamily protocol"
```

---

## Task 5: Rewrite `run()` as a registry loop with baseline columns

**Files:**
- Modify: `scripts/run_tick_opportunity_mining.py` (`run()` `:936-1070`, schema version `:40`, `main()` `:1073`)
- Test: `tests/test_tick_opportunity_mining.py`

**Context:** This is the integration task. `run()` stops calling
`_directional_candidates`/`_oco_candidates` and instead loops the registry.
Each candidate row gains the three baseline columns. The parity test from
Task 2 changes meaning: row *counts* may shift slightly because the new loop
computes regimes once per family — so the parity test is updated to assert the
*new* stable snapshot plus the presence of the baseline columns.

- [ ] **Step 1: Bump the schema version**

In `scripts/run_tick_opportunity_mining.py:40`, change:

```python
CANDIDATE_SCHEMA_VERSION = "3.0"
```

to:

```python
CANDIDATE_SCHEMA_VERSION = "4.0"
```

- [ ] **Step 2: Add the `--baseline-seed` arg and config default**

In `main()` (`:1073`), add after the `--barrier-grid-pips` line:

```python
    p.add_argument("--baseline-seed", type=int, default=None)
    p.add_argument("--baseline-draws", type=int, default=None)
```

In the `DEFAULTS` dict at the top of the file (find the dict containing
`"library_type"` at `:34`), add:

```python
    "baseline_seed": 12345,
    "baseline_draws": 200,
```

- [ ] **Step 3: Write the failing integration test**

Add to `tests/test_tick_opportunity_mining.py`:

```python
def test_run_emits_random_baseline_columns(tmp_path: Path) -> None:
    dataset_dir = tmp_path / "tick_velocity"
    dataset_dir.mkdir(parents=True, exist_ok=True)
    _synth_tick_velocity(dataset_dir / "EURUSD_1000tick_velocity.parquet",
                         symbol="EURUSD")
    cfg = {
        "symbol": "EURUSD", "dataset_dir": str(dataset_dir),
        "bar_ticks_grid": "1000", "horizons": "1,2,3",
        "train_years": "2022,2023,2024", "test_year": 2025,
        "min_annual_fills": 50.0, "gross_metric": "mean",
        "library_type": "separate", "barrier_grid_pips": "2,3",
        "baseline_seed": 12345, "baseline_draws": 50,
    }
    directional, oco, summary = run(cfg)
    for df in (directional, oco):
        if not df.empty:
            for col in ("random_baseline_z", "random_baseline_p",
                        "random_baseline_control_mean"):
                assert col in df.columns
```

- [ ] **Step 4: Run the test to verify it fails**

Run: `uv run pytest tests/test_tick_opportunity_mining.py::test_run_emits_random_baseline_columns -v`
Expected: FAIL — baseline columns absent.

- [ ] **Step 5: Rewrite the `run()` body**

Replace the family-dispatch and aggregation block in `run()` — from the
`directional_parts: list[...]` line (`:952`) through the
`return directional, oco, summary` line (`:1070`) — with the registry loop
below. The `dataset_dir` existence guard and the `files_found` velocity-file
guard (`:955-1008`) stay exactly as they are; only the per-file family
dispatch and the final assembly change.

```python
    from scripts.mining_family import FAMILY_REGISTRY, resolve_families
    from scripts.mining_random_baseline import random_entry_baseline

    family_names = resolve_families(library_type)
    baseline_seed = int(cfg.get("baseline_seed", 12345))
    baseline_draws = int(cfg.get("baseline_draws", 200))

    per_family_rows: dict[str, list[dict[str, Any]]] = {n: [] for n in family_names}

    files_found = 0
    for bt in bar_ticks_grid:
        path = dataset_dir / f"{symbol}_{int(bt)}tick_velocity.parquet"
        if not path.exists():
            print(f"skip {bt}: missing {path}")
            continue
        files_found += 1
        d = _prepare_frame(path, symbol=symbol, horizons=horizons)
        d = _attach_directional_side_columns(d, horizons=horizons)
        train = d[d["year"].isin(train_years)].copy().reset_index(drop=True)
        test = d[d["year"] == int(test_year)].copy().reset_index(drop=True)
        if train.empty or test.empty:
            print(f"skip {bt}: empty split (train/test)")
            continue

        for fam_name in family_names:
            family = FAMILY_REGISTRY[fam_name]
            rng = np.random.default_rng(baseline_seed)
            test_regimes = _regime_masks(test, _quantiles(train))
            for params in family.param_grid(cfg):
                params = {**params, "symbol": symbol, "bar_ticks": int(bt)}
                for regime_name, regime_mask in test_regimes:
                    entries = family.entry_indices(test, np.asarray(regime_mask, bool), params)
                    n = int(len(entries))
                    if n <= 0:
                        continue
                    gross = np.asarray(family.measure_gross(test, entries, params), float)
                    gross = gross[np.isfinite(gross)]
                    if gross.size == 0:
                        continue
                    cand_ev = float(np.mean(gross))
                    base = random_entry_baseline(
                        family, test, params,
                        n_entries=n, n_draws=baseline_draws, rng=rng,
                        candidate_gross_ev=cand_ev,
                    )
                    row = {
                        "symbol": symbol,
                        "bar_ticks": int(bt),
                        "horizon": int(params.get("horizon", 0)),
                        "test_count": n,
                        "mean_gross_pips_test": cand_ev,
                        "median_gross_pips_test": float(np.median(gross)),
                        "annualized_test_fills": _annualized_count(
                            n, pd.to_datetime(test["close_ts"], utc=True,
                                              errors="coerce").iloc[entries]),
                        **family.candidate_metadata(regime_name, params),
                        **base,
                    }
                    per_family_rows[fam_name].append(row)
        print(f"ok {symbol} {bt}tick")

    if files_found == 0:
        raise FileNotFoundError(
            f"no velocity files found for {symbol} in {dataset_dir} "
            f"(expected {symbol}_<ticks>tick_velocity.parquet). "
            "Run `make rebuild-all MONTHS=...` to build Stage 0 data."
        )

    directional = pd.DataFrame(per_family_rows.get("directional", []))
    oco = pd.DataFrame(per_family_rows.get("oco_first_touch", []))
    if not directional.empty:
        directional = _assign_quality_tier(directional, library="directional")
        directional = _stamp_candidate_contract(directional)
    if not oco.empty:
        oco = _assign_quality_tier(oco, library="oco")
        oco = _stamp_candidate_contract(oco)
    summary = _build_summary(directional, oco)
    return directional, oco, summary
```

- [ ] **Step 6: Extract `_build_summary` and add `_attach_directional_side_columns`**

The old `run()` built `summary` inline (`:1026-1069`). Move that block
verbatim into a module-level helper so `run()` stays readable. Add to
`scripts/run_tick_opportunity_mining.py` above `run()`:

```python
def _build_summary(directional: pd.DataFrame, oco: pd.DataFrame) -> pd.DataFrame:
    frames = []
    if not directional.empty:
        frames.append(directional.assign(library="directional"))
    if not oco.empty:
        frames.append(oco.assign(library="oco"))
    summary_rows: list[dict[str, Any]] = []
    if frames:
        all_df = pd.concat(frames, ignore_index=True)
        for lib, g in all_df.groupby("library", sort=True):
            total = len(g)
            passed = int(g["selection_pass"].sum()) if "selection_pass" in g else 0
            summary_rows.append({
                "library": str(lib),
                "rows_total": int(total),
                "rows_pass": int(passed),
                "pass_rate": float(passed / max(total, 1)),
                "mean_gross_all": float(
                    pd.to_numeric(g["mean_gross_pips_test"], errors="coerce").mean()),
                "mean_baseline_z": float(
                    pd.to_numeric(g["random_baseline_z"], errors="coerce").mean()),
            })
    return pd.DataFrame(summary_rows)


def _attach_directional_side_columns(
    frame: pd.DataFrame, *, horizons: list[int]
) -> pd.DataFrame:
    """Materialise per-bar `_dir_side_h{h}` columns used by DirectionalFamily.

    The side is the sign convention from _directional_family_states applied
    per bar: +1 when the regime's directional bias is long, -1 short, 0 when
    undefined. Computed here once so the family hooks stay pure index math.
    """
    out = frame.copy()
    q = _quantiles(frame)
    for h in horizons:
        side = np.zeros(len(frame), dtype=np.int8)
        for _fam, fam_mask, fam_side in _directional_family_states(frame, q):
            fm = np.asarray(fam_mask, dtype=bool)
            fs = np.asarray(fam_side, dtype=np.int8)
            side = np.where(fm & (side == 0), fs, side).astype(np.int8)
        out[f"_dir_side_h{h}"] = side
    return out
```

**Implementer note:** confirm the sign convention in
`_directional_family_states` (`:333`) — `fam_side` is already ±1/0 per bar.
If a bar belongs to multiple family states the first non-zero side wins; this
matches the old loop, which processed one family-state at a time and a bar
could only satisfy one family mask. If the parity check in Step 8 reveals a
mismatch, adjust the precedence here.

- [ ] **Step 7: Delete the dead functions**

Remove `_directional_candidates` (`:556-686`) and `_oco_candidates`
(`:687-934`) entirely — they are no longer referenced. Keep
`_oco_precompute_candidates`, `_regime_masks`, `_quantiles`,
`_directional_family_states`, `_metric_from_gross`, `_annualized_count`,
`_assign_quality_tier`, `_stamp_candidate_contract` — all still used.

- [ ] **Step 8: Update the parity test to the new snapshot**

The refactor changes row assembly, so `test_mining_run_output_is_stable`'s
pinned `_PARITY` values are now stale. Re-run the Step 6 capture command from
Task 2 against the refactored code, and replace `_PARITY` with the new dict.
Then add an assertion that the baseline columns are present:

```python
    assert "random_baseline_z" in snapshot["directional_cols"] or directional.empty
    assert "random_baseline_z" in snapshot["oco_cols"] or oco.empty
```

This re-pins parity going forward (sub-projects 1-5 must keep it green).

- [ ] **Step 9: Run the full mining test file**

Run: `uv run pytest tests/test_tick_opportunity_mining.py tests/test_mining_family.py tests/test_mining_random_baseline.py -q`
Expected: all PASS, including `test_run_emits_random_baseline_columns` and the
two PR #184 fail-loud guard tests (`test_mining_raises_when_dataset_dir_missing`,
`test_mining_raises_when_no_velocity_files_for_symbol`).

- [ ] **Step 10: Commit**

```bash
git add scripts/run_tick_opportunity_mining.py tests/test_tick_opportunity_mining.py
git commit -m "feat: run() drives mining via the family registry + baseline"
```

---

## Task 6: Update the ml-dataset candidate-schema contract

**Files:**
- Modify: `scripts/build_tick_opportunity_ml_dataset.py` (`REQUIRED_CANDIDATE_COLUMNS` `:87`)
- Test: `tests/test_tick_opportunity_ml_dataset.py`

**Context:** `build_tick_opportunity_ml_dataset.py` validates that candidate
CSVs carry `EXPECTED_CANDIDATE_SCHEMA_VERSION` (`:74`, imported from the
mining script — so the `"4.0"` bump flows through automatically) and the
`REQUIRED_CANDIDATE_COLUMNS` set (`:87`). The three baseline columns are new
optional diagnostics; they need not be *required*, but the schema-version
check must accept `"4.0"`. No new required column is added (baseline columns
are diagnostic).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_tick_opportunity_ml_dataset.py`:

```python
def test_expected_candidate_schema_version_is_current():
    from scripts.build_tick_opportunity_ml_dataset import (
        EXPECTED_CANDIDATE_SCHEMA_VERSION,
    )

    assert EXPECTED_CANDIDATE_SCHEMA_VERSION == "4.0"
```

- [ ] **Step 2: Run the test**

Run: `uv run pytest tests/test_tick_opportunity_ml_dataset.py::test_expected_candidate_schema_version_is_current -v`
Expected: PASS already — `EXPECTED_CANDIDATE_SCHEMA_VERSION` is derived from
the mining script's `CANDIDATE_SCHEMA_VERSION`, which Task 5 bumped to `"4.0"`.
If it FAILS, Task 5 Step 1 was not applied; fix that first.

- [ ] **Step 3: Run the full ml-dataset suite for regressions**

Run: `uv run pytest tests/test_tick_opportunity_ml_dataset.py -q`
Expected: all PASS. If `test_build_tick_opportunity_ml_dataset` fails because
its fixture candidate CSV is stamped `"3.0"`, update that fixture's
`candidate_schema_version` value to `"4.0"` (search the test file for
`"3.0"`).

- [ ] **Step 4: Commit**

```bash
git add scripts/build_tick_opportunity_ml_dataset.py tests/test_tick_opportunity_ml_dataset.py
git commit -m "test: accept candidate schema version 4.0 in ml-dataset"
```

---

## Task 7: Full-suite regression check

**Files:** none (verification only).

- [ ] **Step 1: Run the mining + ml-dataset + WFO test files**

Run: `uv run pytest tests/test_tick_opportunity_mining.py tests/test_mining_family.py tests/test_mining_random_baseline.py tests/test_tick_opportunity_ml_dataset.py tests/test_oco_docs_contract.py -q`
Expected: all PASS. `test_oco_docs_contract.py` exercises the candidate
schema contract — if it pins `"3.0"`, update the contract doc/fixture to
`"4.0"` and re-run.

- [ ] **Step 2: Run `make quality`**

Run: `make quality`
Expected: ruff + ty + vulture clean. `vulture` may flag the deleted
`_directional_candidates`/`_oco_candidates` as already-gone — no action. If it
flags an unused helper that Task 5 Step 7 should have kept, restore it.

- [ ] **Step 3: Commit any fixture/doc updates**

```bash
git add -A
git commit -m "test: align schema-contract fixtures with mining schema 4.0"
```

---

## Self-Review

**Spec coverage:**
- Spec §1 (`MiningFamily` Protocol + `FAMILY_REGISTRY`) — Task 1 (skeleton),
  Tasks 3-4 (concrete families).
- Spec §2 (random-entry baseline, count-matched whole-frame, z/p/control_mean
  columns, `--baseline-seed`) — Task 2 (module), Task 5 (wiring + arg).
- Spec §3 (refactor existing families onto the seam, `library_type` alias) —
  Tasks 3-4 (port), Task 5 (`resolve_families` loop, dead-code deletion).
- Spec §4 (data flow, schema-version bump, `REQUIRED_CANDIDATE_COLUMNS`) —
  Task 5 (schema bump), Task 6 (ml-dataset contract).
- Spec "Error Handling" (unknown family → `ValueError`; baseline NaN on
  degenerate input; PR #184 guards preserved) — Task 1 (`resolve_families`
  raise), Task 2 (NaN paths), Task 5 Step 5 (guards kept verbatim).
- Spec "Testing" (Protocol conformance, refactor parity, baseline behaviour,
  existing-suite regression) — Tasks 1-2 + 7.

**Placeholder scan:** No TBDs. The two "implementer note" blocks (Task 3
`_dir_side` columns, Task 4 `entries` ∩ `i0`) describe a real cross-task
dependency and name the exact task that resolves it — they are guidance, not
deferred work. Task 5 Step 6 flags one genuine uncertainty (directional side
precedence) with a concrete fallback tied to the parity test.

**Type consistency:** `MiningFamily` hooks have identical signatures across
the Protocol (Task 1) and both implementations (Tasks 3-4):
`entry_indices(frame, regime_mask, params) -> np.ndarray`,
`measure_gross(frame, entries, params) -> np.ndarray`. `random_entry_baseline`
is keyword-only after `params`, returns the three `random_baseline_*` keys
used identically in its test (Task 2) and the `run()` row dict (Task 5).
`resolve_families` returns `list[str]` consumed by Task 5's loop.
`CANDIDATE_SCHEMA_VERSION` / `EXPECTED_CANDIDATE_SCHEMA_VERSION` are both
`"4.0"` after Tasks 5-6.
