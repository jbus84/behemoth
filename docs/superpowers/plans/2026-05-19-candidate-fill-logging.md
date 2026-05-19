# Candidate Fill Logging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a per-fill log to the tick opportunity mining pipeline — one parquet row per individual fill for every positive-EV candidate, capturing the fill outcome and a snapshot of entry-time features.

**Architecture:** A new focused module `scripts/candidate_fills.py` provides three pure helpers (`candidate_id`, `expand_fills`, `write_candidate_fills`) testable with tiny fixtures. The mining loop in `scripts/run_tick_opportunity_mining.py` accumulates per-fill rows for `selection_pass`-or-near-miss candidates by reusing the already-computed `entries`/`gross` arrays, and `main()` writes one parquet per symbol alongside the existing summary CSVs.

**Tech Stack:** Python, NumPy, pandas (parquet), pytest. Spec: `docs/superpowers/specs/2026-05-19-candidate-fill-logging-design.md`.

**Base state:** `scripts/run_tick_opportunity_mining.py` has `_mine_frame_pair(...)` (line 890) returning `dict[str, list[dict]]`, called by `run()` (line 1116) and by `tests/test_microstructure_regimes.py:41`. `run()` (line 1068) returns `(directional, oco, no_touch, summary)`; `main()` (line 1153) calls it and writes CSVs. `tests/test_tick_opportunity_mining.py` has `_build_synth_tick_velocity(path, *, symbol)` writing a synthetic velocity parquet readable by `_prepare_frame`.

## File Structure

- `scripts/candidate_fills.py` — new module. Three helpers: `candidate_id` (deterministic hash), `expand_fills` (entries+gross → per-fill row dicts with entry-time feature snapshot), `write_candidate_fills` (row list → parquet).
- `tests/test_candidate_fills.py` — new test file for the module's unit behaviour.
- `scripts/run_tick_opportunity_mining.py` — modified: `_mine_frame_pair` accumulates fills and returns a tuple; `run()` collects fills and returns a 5-tuple; `main()` writes the parquet.
- `tests/test_microstructure_regimes.py` — modified: update the one `_mine_frame_pair` call site for the new tuple return.
- `tests/test_tick_opportunity_mining.py` — modified: update six `run()` call sites for the new 5-tuple return; add one end-to-end fills test.

---

### Task 1: `candidate_id` — deterministic candidate hash

**Files:**
- Create: `scripts/candidate_fills.py`
- Create: `tests/test_candidate_fills.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_candidate_fills.py`:

```python
from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.candidate_fills import candidate_id


def test_candidate_id_is_deterministic_and_12_hex():
    a = candidate_id(
        "EURUSD", "oco", "oco_first_touch", 1000, 6, "high_vol_cluster",
        {"horizon": 6, "barrier_pips": 2.0},
    )
    b = candidate_id(
        "EURUSD", "oco", "oco_first_touch", 1000, 6, "high_vol_cluster",
        {"horizon": 6, "barrier_pips": 2.0},
    )
    assert a == b
    assert len(a) == 12
    assert all(c in "0123456789abcdef" for c in a)


def test_candidate_id_differs_when_params_differ():
    a = candidate_id(
        "EURUSD", "oco", "oco_first_touch", 1000, 6, "r",
        {"horizon": 6, "barrier_pips": 2.0},
    )
    b = candidate_id(
        "EURUSD", "oco", "oco_first_touch", 1000, 6, "r",
        {"horizon": 6, "barrier_pips": 3.0},
    )
    assert a != b


def test_candidate_id_is_param_order_independent():
    a = candidate_id("EURUSD", "oco", "f", 1000, 6, "r", {"a": 1, "b": 2})
    b = candidate_id("EURUSD", "oco", "f", 1000, 6, "r", {"b": 2, "a": 1})
    assert a == b
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_candidate_fills.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.candidate_fills'`.

- [ ] **Step 3: Create the module with `candidate_id`**

Create `scripts/candidate_fills.py`:

```python
"""Per-fill logging for the tick opportunity mining pipeline.

One row per individual fill for every positive-EV candidate, capturing the
fill outcome and a snapshot of the entry-time features. See
docs/superpowers/specs/2026-05-19-candidate-fill-logging-design.md.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


def candidate_id(
    symbol: str,
    library_type: str,
    family: str,
    bar_ticks: int,
    horizon: int,
    regime: str,
    params: dict[str, Any],
) -> str:
    """A deterministic 12-hex-char identifier for one mining candidate.

    Stable across runs, so a candidate's fills can be diffed between retrains.
    The param dict is sorted so dict ordering does not affect the hash.
    """
    payload = repr((
        str(symbol),
        str(library_type),
        str(family),
        int(bar_ticks),
        int(horizon),
        str(regime),
        sorted((str(k), repr(v)) for k, v in params.items()),
    ))
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/test_candidate_fills.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/candidate_fills.py tests/test_candidate_fills.py
git commit -m "feat: candidate_id deterministic hash for fill logging"
```

---

### Task 2: `expand_fills` — entries + gross to per-fill rows

**Files:**
- Modify: `scripts/candidate_fills.py`
- Test: `tests/test_candidate_fills.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_candidate_fills.py`:

```python
def _full_frame() -> pd.DataFrame:
    return pd.DataFrame({
        "close_ts": pd.to_datetime(
            ["2024-01-01T00:00:00Z", "2024-01-01T00:01:00Z",
             "2024-01-01T00:02:00Z"], utc=True),
        "tick_burst_score": [0.1, 0.2, 0.3],
        "directional_persistence_8": [1.0, 2.0, 3.0],
        "vol_cluster_score": [0.5, 0.6, 0.7],
        "session_marker": ["LON", "NY", "TOK"],
    })


def test_expand_fills_one_row_per_finite_entry():
    from scripts.candidate_fills import expand_fills

    frame = _full_frame()
    rows = expand_fills(
        frame, np.array([0, 2]), np.array([1.5, -0.5]),
        split="test", identity={"candidate_id": "abc", "symbol": "EURUSD"},
    )
    assert len(rows) == 2
    assert rows[0]["candidate_id"] == "abc"
    assert rows[0]["symbol"] == "EURUSD"
    assert rows[0]["split"] == "test"
    assert rows[0]["entry_index"] == 0
    assert rows[0]["entry_ts"] == frame["close_ts"].iloc[0]
    assert rows[0]["gross_pips"] == 1.5
    assert rows[0]["tick_burst_score"] == 0.1
    assert rows[0]["directional_persistence_8"] == 1.0
    assert rows[0]["vol_cluster_score"] == 0.5
    assert rows[0]["session_marker"] == "LON"
    assert rows[1]["entry_index"] == 2
    assert rows[1]["gross_pips"] == -0.5
    assert rows[1]["session_marker"] == "TOK"


def test_expand_fills_drops_non_finite_gross_keeping_alignment():
    from scripts.candidate_fills import expand_fills

    frame = _full_frame()
    # Middle fill has non-finite gross -> dropped; the other two survive
    # with their correct entry indices.
    rows = expand_fills(
        frame, np.array([0, 1, 2]), np.array([1.0, np.nan, 2.0]),
        split="train", identity={"candidate_id": "abc"},
    )
    assert [r["entry_index"] for r in rows] == [0, 2]
    assert [r["gross_pips"] for r in rows] == [1.0, 2.0]


def test_expand_fills_missing_feature_columns_degrade():
    from scripts.candidate_fills import expand_fills

    frame = pd.DataFrame({
        "close_ts": pd.to_datetime(["2024-01-01T00:00:00Z"], utc=True),
    })
    rows = expand_fills(
        frame, np.array([0]), np.array([1.0]),
        split="test", identity={"candidate_id": "abc"},
    )
    assert len(rows) == 1
    assert np.isnan(rows[0]["tick_burst_score"])
    assert np.isnan(rows[0]["directional_persistence_8"])
    assert np.isnan(rows[0]["vol_cluster_score"])
    assert rows[0]["session_marker"] == ""
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_candidate_fills.py -k expand_fills -v`
Expected: FAIL with `ImportError: cannot import name 'expand_fills'`.

- [ ] **Step 3: Implement `expand_fills`**

Append to `scripts/candidate_fills.py`:

```python
_FEATURE_FLOAT_COLS = (
    "tick_burst_score",
    "directional_persistence_8",
    "vol_cluster_score",
)
_SESSION_COL = "session_marker"


def expand_fills(
    frame: pd.DataFrame,
    entries: np.ndarray,
    gross: np.ndarray,
    *,
    split: str,
    identity: dict[str, Any],
) -> list[dict[str, Any]]:
    """Expand one candidate's fills into per-fill row dicts.

    `gross` must be the raw, unfiltered array aligned 1:1 with `entries`;
    fills whose gross is non-finite are dropped per-row so the entry-to-gross
    correspondence is never broken. Missing feature columns degrade to NaN
    (or empty string for session_marker) rather than raising.
    """
    entries = np.asarray(entries, dtype=np.int64)
    gross = np.asarray(gross, dtype=float)
    close_ts = pd.to_datetime(frame["close_ts"], utc=True, errors="coerce")
    rows: list[dict[str, Any]] = []
    for k, idx in enumerate(entries):
        g = float(gross[k])
        if not np.isfinite(g):
            continue
        i = int(idx)
        row = dict(identity)
        row["split"] = split
        row["entry_index"] = i
        row["entry_ts"] = close_ts.iloc[i]
        row["gross_pips"] = g
        for col in _FEATURE_FLOAT_COLS:
            row[col] = (
                float(frame[col].iloc[i])
                if col in frame.columns
                else float("nan")
            )
        row[_SESSION_COL] = (
            str(frame[_SESSION_COL].iloc[i])
            if _SESSION_COL in frame.columns
            else ""
        )
        rows.append(row)
    return rows
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_candidate_fills.py -k expand_fills -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/candidate_fills.py tests/test_candidate_fills.py
git commit -m "feat: expand_fills per-fill row expansion"
```

---

### Task 3: `write_candidate_fills` — parquet writer

**Files:**
- Modify: `scripts/candidate_fills.py`
- Test: `tests/test_candidate_fills.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_candidate_fills.py`:

```python
def test_write_candidate_fills_writes_parquet(tmp_path):
    from scripts.candidate_fills import write_candidate_fills

    rows = [
        {"candidate_id": "abc", "symbol": "EURUSD", "gross_pips": 1.0},
        {"candidate_id": "abc", "symbol": "EURUSD", "gross_pips": -0.5},
    ]
    path = write_candidate_fills(rows, tmp_path, "EURUSD")
    assert path.exists()
    assert path.parent.name == "candidate_fills"
    df = pd.read_parquet(path)
    assert len(df) == 2
    assert set(df["candidate_id"]) == {"abc"}


def test_write_candidate_fills_empty_writes_empty_schema_parquet(tmp_path):
    from scripts.candidate_fills import write_candidate_fills, FILL_COLUMNS

    path = write_candidate_fills([], tmp_path, "EURUSD")
    assert path.exists()
    df = pd.read_parquet(path)
    assert df.empty
    assert list(df.columns) == list(FILL_COLUMNS)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_candidate_fills.py -k write_candidate_fills -v`
Expected: FAIL with `ImportError: cannot import name 'write_candidate_fills'`.

- [ ] **Step 3: Implement `write_candidate_fills`**

Append to `scripts/candidate_fills.py`:

```python
# Canonical per-fill column order; also the schema of an empty fills parquet.
FILL_COLUMNS: tuple[str, ...] = (
    "candidate_id",
    "symbol",
    "family",
    "library_type",
    "bar_ticks",
    "horizon",
    "regime",
    "split",
    "entry_index",
    "entry_ts",
    "gross_pips",
    "tick_burst_score",
    "directional_persistence_8",
    "vol_cluster_score",
    "session_marker",
    "selection_pass",
    "near_miss",
)


def write_candidate_fills(
    rows: list[dict[str, Any]],
    out_dir: Path | str,
    symbol: str,
) -> Path:
    """Write per-fill rows to `<out_dir>/candidate_fills/<symbol>_candidate_fills.parquet`.

    An empty `rows` list still produces a parquet with the canonical schema so
    downstream readers never have to handle a missing file.
    """
    fills_dir = Path(out_dir) / "candidate_fills"
    fills_dir.mkdir(parents=True, exist_ok=True)
    path = fills_dir / f"{symbol}_candidate_fills.parquet"
    if rows:
        df = pd.DataFrame(rows)
    else:
        df = pd.DataFrame({c: [] for c in FILL_COLUMNS})
    df.to_parquet(path, index=False)
    return path
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_candidate_fills.py -k write_candidate_fills -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/candidate_fills.py tests/test_candidate_fills.py
git commit -m "feat: write_candidate_fills parquet writer"
```

---

### Task 4: Accumulate fills inside `_mine_frame_pair`

**Files:**
- Modify: `scripts/run_tick_opportunity_mining.py` (`_mine_frame_pair`, lines 890-1065)
- Modify: `tests/test_microstructure_regimes.py:41`

- [ ] **Step 1: Update the contract-test caller for the new tuple return**

In `tests/test_microstructure_regimes.py`, the helper at line 41 currently is:

```python
    rows = _mine_frame_pair(
        train=train,
        test=test,
        symbol="EURUSD",
        bar_ticks=1000,
        cfg={"horizons": horizons, "barrier_grid_pips": barriers},
        family_names=families,
        baseline_seed=12345,
        baseline_draws=20,
        min_annual_fills=50.0,
    )
    return {fam: pd.DataFrame(fam_rows) for fam, fam_rows in rows.items()}
```

Change the first line to unpack the new 2-tuple `(per_family_rows, fill_rows)`:

```python
    rows, _fill_rows = _mine_frame_pair(
        train=train,
        test=test,
        symbol="EURUSD",
        bar_ticks=1000,
        cfg={"horizons": horizons, "barrier_grid_pips": barriers},
        family_names=families,
        baseline_seed=12345,
        baseline_draws=20,
        min_annual_fills=50.0,
    )
    return {fam: pd.DataFrame(fam_rows) for fam, fam_rows in rows.items()}
```

- [ ] **Step 2: Add the import at the top of `scripts/run_tick_opportunity_mining.py`**

Find the existing project imports near the top of the file (the block importing from `scripts.*`). Add:

```python
from scripts.candidate_fills import candidate_id, expand_fills
```

- [ ] **Step 3: Add the `fill_rows` accumulator in `_mine_frame_pair`**

In `_mine_frame_pair`, find line 907:

```python
    per_family_rows: dict[str, list[dict[str, Any]]] = {n: [] for n in family_names}
```

Add immediately after it:

```python
    fill_rows: list[dict[str, Any]] = []
```

- [ ] **Step 4: Capture the raw (unfiltered) test gross array**

In `_mine_frame_pair`, find lines 940-941:

```python
                gross = np.asarray(family.measure_gross(test, entries, params), float)
                gross = gross[np.isfinite(gross)]
```

Replace with (keep the raw array aligned to `entries`, derive the filtered one):

```python
                gross_raw = np.asarray(family.measure_gross(test, entries, params), float)
                gross = gross_raw[np.isfinite(gross_raw)]
```

- [ ] **Step 5: Capture the raw (unfiltered) train gross array**

In `_mine_frame_pair`, find lines 951-952:

```python
                train_gross = np.asarray(family.measure_gross(train, train_entries, params), float)
                train_gross = train_gross[np.isfinite(train_gross)]
```

Replace with:

```python
                train_gross_raw = np.asarray(family.measure_gross(train, train_entries, params), float)
                train_gross = train_gross_raw[np.isfinite(train_gross_raw)]
```

- [ ] **Step 6: Add the emission gate and fill expansion**

In `_mine_frame_pair`, find the `row = {` line (line 1038). Immediately *before* it, insert the gate block. `selection_pass` and `mean_train` are already in scope from the preceding code:

```python
                _library_type = str(cfg.get("library_type", "separate"))
                _cid = candidate_id(
                    symbol, _library_type, fam_name, int(bar_ticks),
                    int(params.get("horizon", 0)), regime_name, params,
                )
                _near_miss = bool(
                    np.isfinite(mean_train)
                    and mean_train > 0.0
                    and not selection_pass
                )
                if selection_pass or _near_miss:
                    _identity = {
                        "candidate_id": _cid,
                        "symbol": symbol,
                        "family": fam_name,
                        "library_type": _library_type,
                        "bar_ticks": int(bar_ticks),
                        "horizon": int(params.get("horizon", 0)),
                        "regime": regime_name,
                        "selection_pass": bool(selection_pass),
                        "near_miss": _near_miss,
                    }
                    fill_rows.extend(expand_fills(
                        test, entries, gross_raw,
                        split="test", identity=_identity,
                    ))
                    fill_rows.extend(expand_fills(
                        train, train_entries, train_gross_raw,
                        split="train", identity=_identity,
                    ))
```

- [ ] **Step 7: Add `candidate_id` to the candidate row dict**

In `_mine_frame_pair`, the `row` dict starts at line 1038 with `"symbol": symbol,`. Add `candidate_id` as the first entry of the dict:

```python
                row = {
                    "candidate_id": _cid,
                    "symbol": symbol,
                    "bar_ticks": int(bar_ticks),
```

(The remaining keys of `row` are unchanged.)

- [ ] **Step 8: Change the return statement to a tuple**

In `_mine_frame_pair`, find the final line `return per_family_rows` (line 1065). Replace with:

```python
    return per_family_rows, fill_rows
```

- [ ] **Step 9: Update the return type annotation**

In `_mine_frame_pair`'s signature, find the return annotation (line 901):

```python
) -> dict[str, list[dict[str, Any]]]:
```

Replace with:

```python
) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
```

- [ ] **Step 10: Update the `run()` call site of `_mine_frame_pair`**

In `run()`, find lines 1116-1123:

```python
        pair_rows = _mine_frame_pair(
            train=train, test=test, symbol=symbol, bar_ticks=int(bt),
            cfg=cfg, family_names=family_names,
            baseline_seed=baseline_seed, baseline_draws=baseline_draws,
            min_annual_fills=min_annual_fills,
        )
        for fam_name, fam_rows in pair_rows.items():
            per_family_rows[fam_name].extend(fam_rows)
```

Replace with (the `all_fills` accumulator is created in Task 5 Step 1):

```python
        pair_rows, pair_fills = _mine_frame_pair(
            train=train, test=test, symbol=symbol, bar_ticks=int(bt),
            cfg=cfg, family_names=family_names,
            baseline_seed=baseline_seed, baseline_draws=baseline_draws,
            min_annual_fills=min_annual_fills,
        )
        for fam_name, fam_rows in pair_rows.items():
            per_family_rows[fam_name].extend(fam_rows)
        all_fills.extend(pair_fills)
```

- [ ] **Step 11: Run the microstructure-regime contract tests**

Run: `uv run pytest tests/test_microstructure_regimes.py -q`
Expected: PASS — the contract tests are unchanged in behaviour; only the tuple unpacking was updated.

Note: `run()` will not import-error here because `all_fills` is referenced inside the loop body which Task 5 completes; if running `run()` directly before Task 5, it raises `NameError`. The contract tests call `_mine_frame_pair` directly, not `run()`, so they pass. Proceed to Task 5 immediately.

- [ ] **Step 12: Commit**

```bash
git add scripts/run_tick_opportunity_mining.py tests/test_microstructure_regimes.py
git commit -m "feat: _mine_frame_pair accumulates per-fill rows"
```

---

### Task 5: Collect fills in `run()` and write parquet in `main()`

**Files:**
- Modify: `scripts/run_tick_opportunity_mining.py` (`run()` lines 1068-1150, `main()` lines 1153-1199)
- Modify: `tests/test_tick_opportunity_mining.py` (six `run()` call sites)

- [ ] **Step 1: Add the `all_fills` accumulator in `run()`**

In `run()`, find line 1092:

```python
    per_family_rows: dict[str, list[dict[str, Any]]] = {n: [] for n in family_names}
```

Add immediately after it:

```python
    all_fills: list[dict[str, Any]] = []
```

- [ ] **Step 2: Change the `run()` return statement**

In `run()`, find line 1150 `return directional, oco, no_touch, summary`. Replace with:

```python
    return directional, oco, no_touch, summary, all_fills
```

- [ ] **Step 3: Update the `run()` return type annotation**

In `run()`'s signature, find line 1068:

```python
def run(cfg: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
```

Replace with:

```python
def run(
    cfg: dict[str, Any],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, list[dict[str, Any]]]:
```

- [ ] **Step 4: Update `main()` to unpack the 5-tuple and write the parquet**

In `main()`, find line 1175:

```python
    directional, oco, no_touch, summary = run(cfg)
```

Replace with:

```python
    directional, oco, no_touch, summary, fills = run(cfg)
```

Then find lines 1187-1192:

```python
    no_touch.to_csv(nt_path, index=False)
    summary.to_csv(s_path, index=False)
    print(f"wrote: {d_path}")
    print(f"wrote: {o_path}")
    print(f"wrote: {nt_path}")
    print(f"wrote: {s_path}")
```

Replace with (adds the parquet write after the CSVs):

```python
    no_touch.to_csv(nt_path, index=False)
    summary.to_csv(s_path, index=False)
    fills_path = write_candidate_fills(fills, out_dir, symbol)
    print(f"wrote: {d_path}")
    print(f"wrote: {o_path}")
    print(f"wrote: {nt_path}")
    print(f"wrote: {s_path}")
    print(f"wrote: {fills_path}")
```

- [ ] **Step 5: Add `write_candidate_fills` to the import**

In `scripts/run_tick_opportunity_mining.py`, find the import line added in Task 4 Step 2:

```python
from scripts.candidate_fills import candidate_id, expand_fills
```

Replace with:

```python
from scripts.candidate_fills import (
    candidate_id,
    expand_fills,
    write_candidate_fills,
)
```

- [ ] **Step 6: Update the six `run()` call sites in `tests/test_tick_opportunity_mining.py`**

Each of these lines unpacks a 4-tuple and must become a 5-tuple by appending `, _fills`:

- Line 204: `directional, oco, _no_touch, summary = run(cfg)` → `directional, oco, _no_touch, summary, _fills = run(cfg)`
- Line 534: `directional, oco, _no_touch, summary = run(cfg)` → `directional, oco, _no_touch, summary, _fills = run(cfg)`
- Line 565: `directional, oco, _no_touch, summary = run(cfg)` → `directional, oco, _no_touch, summary, _fills = run(cfg)`
- Line 657: `directional, oco, _no_touch, _ = run(cfg)` → `directional, oco, _no_touch, _, _fills = run(cfg)`
- Line 775: `directional, oco, _no_touch, _ = run(cfg)` → `directional, oco, _no_touch, _, _fills = run(cfg)`
- Line 797: `directional, oco, no_touch, _ = run(cfg)` → `directional, oco, no_touch, _, _fills = run(cfg)`

(Lines 491 and 510 call `run(cfg)` without unpacking — leave them unchanged.)

- [ ] **Step 7: Run the mining test suite**

Run: `uv run pytest tests/test_tick_opportunity_mining.py tests/test_microstructure_regimes.py -q`
Expected: PASS — all existing tests green with the new 5-tuple return.

- [ ] **Step 8: Commit**

```bash
git add scripts/run_tick_opportunity_mining.py tests/test_tick_opportunity_mining.py
git commit -m "feat: run() returns fills; main() writes candidate_fills parquet"
```

---

### Task 6: End-to-end fills test

**Files:**
- Modify: `tests/test_tick_opportunity_mining.py`

- [ ] **Step 1: Write the failing end-to-end test**

Append to `tests/test_tick_opportunity_mining.py`. The `cfg` dict below is copied verbatim from the working `test_tick_opportunity_mining_outputs` test (`tests/test_tick_opportunity_mining.py:192-202`) so the keys exactly match what `run()` reads. The test asserts the fills parquet is produced and that every fill joins to a mined candidate:

```python
def test_run_emits_candidate_fills_joinable_to_summary(tmp_path: Path) -> None:
    from scripts.candidate_fills import FILL_COLUMNS, write_candidate_fills

    dataset_dir = tmp_path / "tick_velocity"
    dataset_dir.mkdir(parents=True, exist_ok=True)
    symbol = "EURUSD"
    _build_synth_tick_velocity(
        dataset_dir / f"{symbol}_1000tick_velocity.parquet", symbol=symbol,
    )

    cfg = {
        "symbol": symbol,
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
    directional, oco, no_touch, summary, fills = run(cfg)

    # run() returns fills as a list of row dicts.
    assert isinstance(fills, list)

    # Writing them yields a parquet with the canonical schema.
    out_dir = tmp_path / "out"
    path = write_candidate_fills(fills, out_dir, symbol)
    assert path.exists()
    fills_df = pd.read_parquet(path)
    assert list(fills_df.columns) == list(FILL_COLUMNS)

    if not fills_df.empty:
        # Every fill carries one of the two splits.
        assert set(fills_df["split"]).issubset({"train", "test"})
        # Every fill's candidate_id is present in some mined candidate frame
        # (library_type "separate" mines directional + oco).
        known_ids: set[str] = set()
        for frame in (directional, oco, no_touch):
            if not frame.empty and "candidate_id" in frame.columns:
                known_ids |= set(frame["candidate_id"])
        assert set(fills_df["candidate_id"]).issubset(known_ids)
        # Only positive-EV candidates emit fills.
        assert bool(fills_df["selection_pass"].any()) or bool(
            fills_df["near_miss"].any()
        )
```

- [ ] **Step 2: Run the test to verify it passes**

Run: `uv run pytest tests/test_tick_opportunity_mining.py::test_run_emits_candidate_fills_joinable_to_summary -v`
Expected: PASS. If the synthetic frame produces zero positive-EV candidates, the `if not fills_df.empty` guard still lets the schema assertions pass; the test remains meaningful.

- [ ] **Step 3: Commit**

```bash
git add tests/test_tick_opportunity_mining.py
git commit -m "test: end-to-end candidate fills emission and summary join"
```

---

## Final Verification

- [ ] Run the new module's unit tests:
  `uv run pytest tests/test_candidate_fills.py -v`
  Expected: all PASS (8 tests).
- [ ] Run the mining + regime suites:
  `uv run pytest tests/test_tick_opportunity_mining.py tests/test_microstructure_regimes.py -q`
  Expected: all PASS.
- [ ] Confirm the changed files vs `main` are only:
  `git diff --name-only main...HEAD` → `scripts/candidate_fills.py`, `tests/test_candidate_fills.py`, `scripts/run_tick_opportunity_mining.py`, `tests/test_microstructure_regimes.py`, `tests/test_tick_opportunity_mining.py`, and the two `docs/superpowers/` files.
- [ ] Open a PR from the `worktree-candidate-fill-logging` branch.
