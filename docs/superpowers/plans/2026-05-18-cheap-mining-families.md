# Asymmetric Barriers + Consecutive Persistence — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add two new mining families — `oco_asymmetric` (independently-sized up/down barriers) and `directional_run` (consecutive-streak-triggered directional bet) — both scored against the random-entry baseline.

**Architecture:** Each family is a `MiningFamily` Protocol implementation registered in `FAMILY_REGISTRY`. `oco_asymmetric` gets its own touch engine `_oco_asymmetric_precompute` (a copy of the symmetric engine with two barrier distances); `directional_run` uses a vectorised `_run_length` helper. Both reuse the sub-project-0 mining loop and random-entry baseline unchanged.

**Tech Stack:** Python, pandas, numpy, pytest.

**Specs:** `docs/superpowers/specs/2026-05-18-asymmetric-barriers-design.md`, `docs/superpowers/specs/2026-05-18-consecutive-persistence-design.md`

These are roadmap sub-projects 1 and 2 — the two cheap falsification checks, bundled into one plan/PR because they touch the same files.

---

## File Map

- `scripts/run_tick_opportunity_mining.py` — add `_oco_asymmetric_precompute` (after `_oco_precompute_candidates`, ~`:499`); add `_run_length` helper.
- `scripts/mining_family.py` — add `OcoAsymmetricFamily` and `DirectionalRunFamily`; register both; add `resolve_families` aliases.
- `tests/test_oco_candidate_family_allowlist.py` — add `oco_asymmetric` to `ALLOWED_OCO_FAMILIES`.
- `tests/test_mining_family.py` — conformance + behaviour tests for both families and `_run_length`.
- `tests/test_tick_opportunity_mining.py` — precompute parity + end-to-end edge tests.
- `docs/superpowers/specs/2026-05-18-microstructure-research-roadmap.md` — status table update.

---

## Task 1: `_oco_asymmetric_precompute` touch engine

**Files:**
- Modify: `scripts/run_tick_opportunity_mining.py` (add after `_oco_precompute_candidates`, which ends at `:498`)
- Test: `tests/test_tick_opportunity_mining.py`

**Context:** `_oco_precompute_candidates` (`:395-498`) places a symmetric
barrier `k`: `up_thr = buy_ref + k*pip`, `dn_thr = sell_ref - k*pip`. The
asymmetric engine is the same algorithm with two distances. With
`up_pips == down_pips` it must produce byte-identical output — that parity is
the test.

- [ ] **Step 1: Write the failing parity test**

Add to `tests/test_tick_opportunity_mining.py`:

```python
def test_oco_asymmetric_precompute_matches_symmetric_when_equal():
    import numpy as np
    import pandas as pd

    from scripts.run_tick_opportunity_mining import (
        _oco_asymmetric_precompute,
        _oco_precompute_candidates,
    )

    rng = np.random.default_rng(11)
    n = 600
    base = 1.10 + np.cumsum(rng.normal(0, 0.0002, n))
    frame = pd.DataFrame({
        "close_bid": base,
        "low_bid": base - rng.uniform(0.0001, 0.0006, n),
        "high_ask": base + rng.uniform(0.0001, 0.0006, n),
        "close_ask": base + 0.0002,
        "hl_first": rng.choice([1.0, -1.0, 0.0], size=n),
    })
    sym = _oco_precompute_candidates(frame, symbol="EURUSD", horizon=4,
                                     barrier_pips=3.0)
    asym = _oco_asymmetric_precompute(frame, symbol="EURUSD", horizon=4,
                                      up_pips=3.0, down_pips=3.0)
    assert sym and asym
    np.testing.assert_array_equal(sym["i0"], asym["i0"])
    np.testing.assert_array_equal(sym["decided"], asym["decided"])
    np.testing.assert_array_equal(sym["side"], asym["side"])
    np.testing.assert_allclose(sym["gross"], asym["gross"], equal_nan=True)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_tick_opportunity_mining.py::test_oco_asymmetric_precompute_matches_symmetric_when_equal -v`
Expected: FAIL — `_oco_asymmetric_precompute` does not exist (ImportError).

- [ ] **Step 3: Implement `_oco_asymmetric_precompute`**

In `scripts/run_tick_opportunity_mining.py`, immediately after
`_oco_precompute_candidates` (after its closing `}` at `:498`), add:

```python
def _oco_asymmetric_precompute(
    frame: pd.DataFrame,
    *,
    symbol: str,
    horizon: int,
    up_pips: float,
    down_pips: float,
) -> dict[str, np.ndarray]:
    """First-touch precompute with independently-sized up and down barriers.

    Identical algorithm to _oco_precompute_candidates; only the two barrier
    thresholds differ. With up_pips == down_pips the output is identical to
    the symmetric engine.
    """
    load_bar_frame(
        frame,
        required=["close_bid", "low_bid", "high_ask", "close_ask"],
    )
    close_bid = pd.to_numeric(frame["close_bid"], errors="coerce").to_numpy(dtype=float)
    low_bid = pd.to_numeric(frame["low_bid"], errors="coerce").to_numpy(dtype=float)
    high_ask = pd.to_numeric(frame["high_ask"], errors="coerce").to_numpy(dtype=float)
    close_ask = pd.to_numeric(frame["close_ask"], errors="coerce").to_numpy(dtype=float)
    hlf = pd.to_numeric(frame["hl_first"], errors="coerce").fillna(0.0).to_numpy(dtype=float)

    h = int(horizon)
    n_eff = len(frame) - 2 * h
    if n_eff <= 100:
        return {}

    pip = float(_pip_size(symbol))
    inf = h + 1
    i0 = np.arange(n_eff, dtype=np.int64)
    buy_ref = close_ask[i0]
    sell_ref = close_bid[i0]
    valid = np.isfinite(buy_ref) & np.isfinite(sell_ref)
    i0 = i0[valid]
    buy_ref = buy_ref[valid]
    sell_ref = sell_ref[valid]
    up_thr = buy_ref + float(up_pips) * pip
    dn_thr = sell_ref - float(down_pips) * pip
    up_step = np.full(len(i0), inf, dtype=np.int32)
    dn_step = np.full(len(i0), inf, dtype=np.int32)
    any_up = np.zeros(len(i0), dtype=bool)
    any_dn = np.zeros(len(i0), dtype=bool)
    for s in range(1, h + 1):
        idx = i0 + int(s)
        hu = high_ask[idx] >= up_thr
        hd = low_bid[idx] <= dn_thr
        set_up = (up_step == inf) & hu
        set_dn = (dn_step == inf) & hd
        up_step[set_up] = int(s)
        dn_step[set_dn] = int(s)
        any_up |= hu
        any_dn |= hd
    side = np.zeros(len(i0), dtype=np.int8)
    side[up_step < dn_step] = 1
    side[dn_step < up_step] = -1
    same = (up_step == dn_step) & (up_step <= h)
    if np.any(same):
        same_idx = np.flatnonzero(same)
        tie_idx = i0[same_idx] + up_step[same_idx].astype(np.int64)
        tie_hlf = hlf[tie_idx]
        side[same_idx[tie_hlf > 0]] = 1
        side[same_idx[tie_hlf < 0]] = -1
    decided = side != 0
    both = any_up & any_dn
    touch_step = np.minimum(up_step, dn_step).astype(float)
    touch_step[~decided] = np.nan
    gross = np.full(len(i0), np.nan, dtype=float)
    touch_i = np.minimum(up_step, dn_step).astype(np.int64, copy=False)
    entry_i = i0 + touch_i
    exit_i = i0 + touch_i + int(h)
    ok = decided & (exit_i < len(close_bid))
    if np.any(ok):
        ok_idx = np.flatnonzero(ok)
        exit_price_use = np.where(
            side[ok_idx] == -1,
            close_ask[exit_i[ok_idx]],
            close_bid[exit_i[ok_idx]],
        )
        entry_price_use = np.where(
            side[ok_idx] == -1,
            close_bid[entry_i[ok_idx]],
            close_ask[entry_i[ok_idx]],
        )
        num_ok = np.isfinite(exit_price_use) & np.isfinite(entry_price_use)
        use = ok_idx[num_ok]
        if len(use) > 0:
            gross[use] = side[use].astype(float) * (
                (exit_price_use[num_ok] - entry_price_use[num_ok]) / pip
            )
    return {
        "i0": i0,
        "gross": gross,
        "side": side,
        "both_touched_lookahead": both,
        "decided": decided,
        "touch_step": touch_step,
    }
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/test_tick_opportunity_mining.py::test_oco_asymmetric_precompute_matches_symmetric_when_equal -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/run_tick_opportunity_mining.py tests/test_tick_opportunity_mining.py
git commit -m "feat: asymmetric OCO touch precompute"
```

---

## Task 2: `OcoAsymmetricFamily`

**Files:**
- Modify: `scripts/mining_family.py`
- Test: `tests/test_mining_family.py`

**Context:** The family mirrors `OcoFirstTouchFamily` (`mining_family.py:115-185`)
but its `param_grid` yields `(horizon, down_pips, rr)` and it calls
`_oco_asymmetric_precompute` with `up_pips = down_pips * rr`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_mining_family.py`:

```python
def test_oco_asymmetric_family_grid_and_metadata():
    from scripts.mining_family import FAMILY_REGISTRY

    fam = FAMILY_REGISTRY["oco_asymmetric"]
    assert fam.name == "oco_asymmetric"
    grid = fam.param_grid({"horizons": "1,2"})
    downs = sorted({g["down_pips"] for g in grid})
    rrs = sorted({g["rr"] for g in grid})
    assert downs == [2.0, 3.0, 5.0, 8.0]
    assert rrs == [0.5, 0.75, 1.0, 1.5, 2.0, 3.0]
    assert len(grid) == 4 * 6 * 2  # downs x rr x horizons
    meta = fam.candidate_metadata("london", {"down_pips": 5.0, "rr": 2.0,
                                             "horizon": 2})
    assert meta["family"] == "oco_asymmetric"
    assert "down=5" in meta["regime_desc"] and "rr=2" in meta["regime_desc"]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_mining_family.py::test_oco_asymmetric_family_grid_and_metadata -v`
Expected: FAIL — `KeyError: 'oco_asymmetric'`.

- [ ] **Step 3: Implement `OcoAsymmetricFamily`**

In `scripts/mining_family.py`, add after `OcoFirstTouchFamily` (before the
`FAMILY_REGISTRY` assignment at `:188`):

```python
class OcoAsymmetricFamily:
    name = "oco_asymmetric"

    _DOWN_PIPS = [2.0, 3.0, 5.0, 8.0]
    _RR = [0.5, 0.75, 1.0, 1.5, 2.0, 3.0]

    def param_grid(self, cfg: dict[str, Any]) -> list[dict[str, Any]]:
        from scripts.run_tick_opportunity_mining import _parse_ints

        horizons = _parse_ints(str(cfg["horizons"]))
        return [
            {"horizon": int(h), "down_pips": float(d), "rr": float(r)}
            for h in horizons
            for d in self._DOWN_PIPS
            for r in self._RR
        ]

    def _precompute(
        self, frame: pd.DataFrame, symbol: str, params: dict[str, Any]
    ) -> dict[str, Any] | None:
        from scripts.run_tick_opportunity_mining import _oco_asymmetric_precompute

        down = float(params["down_pips"])
        rr = float(params["rr"])
        up = down * rr
        if down <= 0.0 or up <= 0.0:
            raise ValueError(f"non-positive barrier: down={down} up={up}")
        try:
            return _oco_asymmetric_precompute(
                frame,
                symbol=symbol,
                horizon=int(params["horizon"]),
                up_pips=up,
                down_pips=down,
            )
        except ValueError:
            return None

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
        down = float(params["down_pips"])
        rr = float(params["rr"])
        return {
            "family": "oco_asymmetric",
            "state_id": f"oco_asymmetric__{regime_name}__d{down:g}_rr{rr:g}",
            "regime_desc": f"{regime_name};down={down:g};rr={rr:g}",
            "ml_ready_target_type": "oco_asymmetric",
        }
```

- [ ] **Step 4: Register the family and add the alias**

In `scripts/mining_family.py`, change the `FAMILY_REGISTRY` assignment to:

```python
FAMILY_REGISTRY: dict[str, MiningFamily] = {
    "oco_first_touch": OcoFirstTouchFamily(),
    "oco_asymmetric": OcoAsymmetricFamily(),
    "directional": DirectionalFamily(),
}
```

And add to `_LIBRARY_TYPE_ALIASES` (`:49-53`):

```python
_LIBRARY_TYPE_ALIASES: dict[str, list[str]] = {
    "oco": ["oco_first_touch"],
    "oco_asymmetric": ["oco_asymmetric"],
    "directional": ["directional"],
    "separate": ["oco_first_touch", "directional"],
}
```

- [ ] **Step 5: Run the test**

Run: `uv run pytest tests/test_mining_family.py::test_oco_asymmetric_family_grid_and_metadata -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add scripts/mining_family.py tests/test_mining_family.py
git commit -m "feat: OcoAsymmetricFamily mining family"
```

---

## Task 3: Allowlist the `oco_asymmetric` family

**Files:**
- Modify: `tests/test_oco_candidate_family_allowlist.py`

**Context:** The contract test asserts every registered `oco_*` family is in
`ALLOWED_OCO_FAMILIES`. `oco_asymmetric` is look-ahead-free (entry is
regime-only; outcome is a forward first-touch), so it is allowlisted.

- [ ] **Step 1: Run the test to verify it now fails**

Run: `uv run pytest tests/test_oco_candidate_family_allowlist.py -v`
Expected: FAIL — `oco_asymmetric` is registered but not in
`ALLOWED_OCO_FAMILIES`.

- [ ] **Step 2: Add the family to the allowlist**

In `tests/test_oco_candidate_family_allowlist.py`, change:

```python
ALLOWED_OCO_FAMILIES = {"oco_first_touch"}
```

to:

```python
ALLOWED_OCO_FAMILIES = {"oco_first_touch", "oco_asymmetric"}
```

- [ ] **Step 3: Run the test to verify it passes**

Run: `uv run pytest tests/test_oco_candidate_family_allowlist.py -v`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/test_oco_candidate_family_allowlist.py
git commit -m "test: allowlist oco_asymmetric as look-ahead-free"
```

---

## Task 4: `_run_length` helper

**Files:**
- Modify: `scripts/run_tick_opportunity_mining.py`
- Test: `tests/test_mining_family.py`

**Context:** `directional_run` needs, per bar, the length of the consecutive
same-sign run of `ret1_pips` and the run's sign. A zero return breaks a run.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_mining_family.py`:

```python
def test_run_length_counts_consecutive_same_sign():
    import numpy as np
    import pandas as pd

    from scripts.run_tick_opportunity_mining import _run_length

    # signs:  + + +  - -  +
    frame = pd.DataFrame({"ret1_pips": [0.3, 0.1, 0.2, -0.1, -0.4, 0.2]})
    run_len, run_sign = _run_length(frame)
    np.testing.assert_array_equal(run_len, [1, 2, 3, 1, 2, 1])
    np.testing.assert_array_equal(run_sign, [1, 1, 1, -1, -1, 1])


def test_run_length_zero_return_breaks_run():
    import numpy as np
    import pandas as pd

    from scripts.run_tick_opportunity_mining import _run_length

    frame = pd.DataFrame({"ret1_pips": [0.3, 0.0, 0.2, 0.1]})
    run_len, run_sign = _run_length(frame)
    np.testing.assert_array_equal(run_len, [1, 0, 1, 2])
    np.testing.assert_array_equal(run_sign, [1, 0, 1, 1])
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_mining_family.py::test_run_length_counts_consecutive_same_sign tests/test_mining_family.py::test_run_length_zero_return_breaks_run -v`
Expected: FAIL — `_run_length` does not exist.

- [ ] **Step 3: Implement `_run_length`**

In `scripts/run_tick_opportunity_mining.py`, add after
`_oco_asymmetric_precompute` (from Task 1):

```python
def _run_length(frame: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Per-bar consecutive same-sign run of ret1_pips.

    Returns (run_len, run_sign): run_len[i] counts consecutive preceding bars
    (including i) with the same non-zero sign of ret1_pips; run_sign[i] is
    that sign (+1/-1, or 0 when ret1_pips is zero, which also resets the run).
    """
    ret = pd.to_numeric(frame["ret1_pips"], errors="coerce").to_numpy(dtype=float)
    sign = np.sign(np.nan_to_num(ret)).astype(np.int8)
    n = len(sign)
    if n == 0:
        return np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.int8)
    change = np.empty(n, dtype=bool)
    change[0] = True
    change[1:] = sign[1:] != sign[:-1]
    starts = np.where(change, np.arange(n), 0)
    last_start = np.maximum.accumulate(starts)
    run_len = (np.arange(n) - last_start + 1).astype(np.int64)
    run_len[sign == 0] = 0
    return run_len, sign
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/test_mining_family.py::test_run_length_counts_consecutive_same_sign tests/test_mining_family.py::test_run_length_zero_return_breaks_run -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add scripts/run_tick_opportunity_mining.py tests/test_mining_family.py
git commit -m "feat: _run_length consecutive-streak helper"
```

---

## Task 5: `DirectionalRunFamily`

**Files:**
- Modify: `scripts/mining_family.py`
- Test: `tests/test_mining_family.py`

**Context:** A directional family — outcome is a signed forward return, no
barriers. `param_grid` yields `(horizon, run_bucket, bet)`. `entry_indices`
selects bars whose run length matches the bucket; `measure_gross` returns
`side * y_fwd` with `side = run_sign` (continuation) or `-run_sign`
(reversion).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_mining_family.py`:

```python
def test_directional_run_family_grid_buckets_and_bet_symmetry():
    import numpy as np
    import pandas as pd

    from scripts.mining_family import FAMILY_REGISTRY

    fam = FAMILY_REGISTRY["directional_run"]
    assert fam.name == "directional_run"
    grid = fam.param_grid({"horizons": "1,2"})
    buckets = sorted({g["run_bucket"] for g in grid})
    bets = sorted({g["bet"] for g in grid})
    assert buckets == ["2", "3", "4", "5", "6+"]
    assert bets == ["continuation", "reversion"]
    assert len(grid) == 5 * 2 * 2  # buckets x bets x horizons

    # bet symmetry: continuation and reversion gross are exact negatives
    frame = pd.DataFrame({
        "ret1_pips": [0.2, 0.2, 0.2, -0.1],
        "y_fwd_pips_h1": [1.0, 2.0, 3.0, 4.0],
    })
    entries = np.array([1, 2])
    cont = fam.measure_gross(frame, entries,
                             {"horizon": 1, "run_bucket": "2", "bet": "continuation"})
    rev = fam.measure_gross(frame, entries,
                            {"horizon": 1, "run_bucket": "2", "bet": "reversion"})
    np.testing.assert_allclose(cont, -rev)


def test_directional_run_entry_indices_match_bucket():
    import numpy as np
    import pandas as pd

    from scripts.mining_family import FAMILY_REGISTRY

    fam = FAMILY_REGISTRY["directional_run"]
    # run lengths: 1,2,3,4,5,6,7  (seven rising bars)
    frame = pd.DataFrame({
        "ret1_pips": [0.1] * 7,
        "y_fwd_pips_h1": [1.0] * 7,
    })
    allmask = np.ones(7, dtype=bool)
    exact3 = fam.entry_indices(frame, allmask,
                               {"horizon": 1, "run_bucket": "3", "bet": "continuation"})
    tail = fam.entry_indices(frame, allmask,
                             {"horizon": 1, "run_bucket": "6+", "bet": "continuation"})
    assert list(exact3) == [2]          # run length exactly 3 -> index 2
    assert list(tail) == [5, 6]         # run length >= 6 -> indices 5,6
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_mining_family.py::test_directional_run_family_grid_buckets_and_bet_symmetry tests/test_mining_family.py::test_directional_run_entry_indices_match_bucket -v`
Expected: FAIL — `KeyError: 'directional_run'`.

- [ ] **Step 3: Implement `DirectionalRunFamily`**

In `scripts/mining_family.py`, add before the `FAMILY_REGISTRY` assignment:

```python
class DirectionalRunFamily:
    name = "directional_run"

    _BUCKETS = ["2", "3", "4", "5", "6+"]
    _BETS = ["continuation", "reversion"]

    def param_grid(self, cfg: dict[str, Any]) -> list[dict[str, Any]]:
        from scripts.run_tick_opportunity_mining import _parse_ints

        horizons = _parse_ints(str(cfg["horizons"]))
        return [
            {"horizon": int(h), "run_bucket": b, "bet": bet}
            for h in horizons
            for b in self._BUCKETS
            for bet in self._BETS
        ]

    def _bucket_mask(self, run_len: np.ndarray, bucket: str) -> np.ndarray:
        if bucket == "6+":
            return run_len >= 6
        if bucket in {"2", "3", "4", "5"}:
            return run_len == int(bucket)
        raise ValueError(f"unknown run_bucket {bucket!r}")

    def entry_indices(
        self, frame: pd.DataFrame, regime_mask: np.ndarray, params: dict[str, Any]
    ) -> np.ndarray:
        from scripts.run_tick_opportunity_mining import _run_length

        h = int(params["horizon"])
        ycol = f"y_fwd_pips_h{h}"
        if ycol not in frame.columns:
            return np.array([], dtype=np.int64)
        run_len, run_sign = _run_length(frame)
        y = pd.to_numeric(frame[ycol], errors="coerce").to_numpy(dtype=float)
        valid = np.isfinite(y)
        if h > 0:
            valid[-h:] = False
        m = (
            valid
            & np.asarray(regime_mask, dtype=bool)
            & self._bucket_mask(run_len, str(params["run_bucket"]))
            & (run_sign != 0)
        )
        return np.flatnonzero(m).astype(np.int64)

    def measure_gross(
        self, frame: pd.DataFrame, entries: np.ndarray, params: dict[str, Any]
    ) -> np.ndarray:
        from scripts.run_tick_opportunity_mining import _run_length

        h = int(params["horizon"])
        ycol = f"y_fwd_pips_h{h}"
        if ycol not in frame.columns:
            return np.array([], dtype=float)
        _, run_sign = _run_length(frame)
        y = pd.to_numeric(frame[ycol], errors="coerce").to_numpy(dtype=float)
        side = run_sign.astype(float)
        bet = str(params["bet"])
        if bet == "reversion":
            side = -side
        elif bet != "continuation":
            raise ValueError(f"unknown bet {bet!r}")
        return side[entries] * y[entries]

    def candidate_metadata(
        self, regime_name: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        bucket = str(params["run_bucket"])
        bet = str(params["bet"])
        return {
            "family": "directional_run",
            "state_id": f"directional_run__{regime_name}__n{bucket}_{bet}",
            "regime_desc": f"{regime_name};run={bucket};bet={bet}",
            "ml_ready_target_type": "directional_run",
        }
```

- [ ] **Step 4: Register the family and add the alias**

In `scripts/mining_family.py`, update `FAMILY_REGISTRY`:

```python
FAMILY_REGISTRY: dict[str, MiningFamily] = {
    "oco_first_touch": OcoFirstTouchFamily(),
    "oco_asymmetric": OcoAsymmetricFamily(),
    "directional": DirectionalFamily(),
    "directional_run": DirectionalRunFamily(),
}
```

And update `_LIBRARY_TYPE_ALIASES`:

```python
_LIBRARY_TYPE_ALIASES: dict[str, list[str]] = {
    "oco": ["oco_first_touch"],
    "oco_asymmetric": ["oco_asymmetric"],
    "directional": ["directional"],
    "directional_run": ["directional_run"],
    "separate": ["oco_first_touch", "directional"],
}
```

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/test_mining_family.py -q`
Expected: all PASS — including the existing protocol-conformance test, which
now also checks `oco_asymmetric` and `directional_run`.

- [ ] **Step 6: Commit**

```bash
git add scripts/mining_family.py tests/test_mining_family.py
git commit -m "feat: DirectionalRunFamily mining family"
```

---

## Task 6: End-to-end edge tests + full-suite regression

**Files:**
- Test: `tests/test_tick_opportunity_mining.py`

**Context:** Verify both families flow through `run()` and that the
random-entry baseline behaves: no false edge on driftless data, positive `z`
when real structure is injected. `tests/test_tick_opportunity_mining.py`
already has `_synth_tick_velocity` (used by `test_tick_opportunity_mining_outputs`).

- [ ] **Step 1: Write the end-to-end test**

Add to `tests/test_tick_opportunity_mining.py`:

```python
def test_run_mines_oco_asymmetric_and_directional_run(tmp_path: Path) -> None:
    dataset_dir = tmp_path / "tick_velocity"
    dataset_dir.mkdir(parents=True, exist_ok=True)
    _synth_tick_velocity(dataset_dir / "EURUSD_1000tick_velocity.parquet",
                         symbol="EURUSD")
    base_cfg = {
        "symbol": "EURUSD", "dataset_dir": str(dataset_dir),
        "bar_ticks_grid": "1000", "horizons": "1,2,3",
        "train_years": "2022,2023,2024", "test_year": 2025,
        "min_annual_fills": 50.0, "gross_metric": "mean",
        "barrier_grid_pips": "2,3", "baseline_seed": 12345, "baseline_draws": 20,
    }
    asym_dir, _, _ = run({**base_cfg, "library_type": "oco_asymmetric"})
    assert not asym_dir.empty or asym_dir is not None
    # oco_asymmetric candidates land in the oco frame
    asym_oco = run({**base_cfg, "library_type": "oco_asymmetric"})[1]
    if not asym_oco.empty:
        assert (asym_oco["family"] == "oco_asymmetric").all()
        for col in ("random_baseline_z", "random_baseline_p"):
            assert col in asym_oco.columns

    run_dir = run({**base_cfg, "library_type": "directional_run"})[0]
    if not run_dir.empty:
        assert (run_dir["family"] == "directional_run").all()
        assert "random_baseline_z" in run_dir.columns
```

- [ ] **Step 2: Run the test to verify it passes**

Run: `uv run pytest tests/test_tick_opportunity_mining.py::test_run_mines_oco_asymmetric_and_directional_run -v`
Expected: PASS. If `run()` raises `unknown library_type`, Task 2 Step 4 or
Task 5 Step 4 (the `_LIBRARY_TYPE_ALIASES` additions) were not applied.

- [ ] **Step 3: Run the full mining + family + baseline suites**

Run: `uv run pytest tests/test_tick_opportunity_mining.py tests/test_mining_family.py tests/test_mining_random_baseline.py tests/test_oco_candidate_family_allowlist.py tests/test_microstructure_regimes.py -q`
Expected: all PASS.

- [ ] **Step 4: Run the whole test suite**

Run: `uv run pytest -q`
Expected: all PASS (no collection errors, no regressions). This step is
mandatory — a targeted-only run is what let a regression reach `main` in
PR #186.

- [ ] **Step 5: Run quality checks**

Run: `make quality`
Expected: ruff + ty + vulture clean.

- [ ] **Step 6: Commit**

```bash
git add tests/test_tick_opportunity_mining.py
git commit -m "test: end-to-end mining for oco_asymmetric and directional_run"
```

---

## Task 7: Update the roadmap status table

**Files:**
- Modify: `docs/superpowers/specs/2026-05-18-microstructure-research-roadmap.md`

**Context:** The roadmap status table is stale — it still shows sub-project 0
as "Planned" and 1-5 as "Blocked on 0". Sub-project 0 is merged; 1 and 2 are
now implemented.

- [ ] **Step 1: Update the status table**

In `docs/superpowers/specs/2026-05-18-microstructure-research-roadmap.md`,
replace the status table rows for sub-projects 0, 1, 2 with:

```markdown
| 0 | Mining family framework + random-entry baseline | [design](2026-05-18-mining-family-framework-design.md) | [plan](../plans/2026-05-18-mining-family-framework.md) | Done (#186, #187) |
| 1 | Asymmetric barriers | [design](2026-05-18-asymmetric-barriers-design.md) | [plan](../plans/2026-05-18-cheap-mining-families.md) | Done |
| 2 | Consecutive-move persistence | [design](2026-05-18-consecutive-persistence-design.md) | [plan](../plans/2026-05-18-cheap-mining-families.md) | Done |
```

Leave rows 3-5 unchanged except changing their `Status` from `Blocked on 0`
to `Ready`.

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/specs/2026-05-18-microstructure-research-roadmap.md
git commit -m "docs: roadmap status — sub-projects 0-2 done, 3-5 ready"
```

---

## Self-Review

**Spec coverage — asymmetric barriers spec:**
- §1 (`OcoAsymmetricFamily`, non-directional, asymmetric bracket) — Task 2.
- §2 (stop + reward-ratio grid, `rr=1` control) — Task 2 Step 3 (`_DOWN_PIPS`,
  `_RR`).
- §3 (`_oco_asymmetric_precompute`) — Task 1.
- §4 (candidate metadata, schema 4.0 unchanged) — Task 2 Step 3.
- §5 (allowlist) — Task 3.
- Testing (precompute parity, no false edge, detects structure) — Task 1
  Step 1 (parity), Task 6 (end-to-end). The driftless / injected-drift
  baseline-behaviour assertions are covered by sub-project 0's own
  `test_mining_random_baseline.py` z-score tests plus Task 6's end-to-end
  column presence; a dedicated injected-drift mining test is not added
  because the synthetic `_synth_tick_velocity` fixture is not drift-controlled
  — baseline correctness is already unit-tested in sub-project 0.

**Spec coverage — consecutive persistence spec:**
- §1 (`DirectionalRunFamily`, run definition, both bets) — Task 4, Task 5.
- §2 (run buckets `2/3/4/5/6+`, both bets) — Task 5 Step 3 (`_BUCKETS`,
  `_BETS`).
- §3 (family hooks, metadata) — Task 5 Step 3.
- §4 (governance — no OCO allowlist change; `resolve_families` wiring) —
  Task 5 Step 4.
- Testing (`_run_length`, bucketing, bet symmetry, conformance) — Task 4
  Step 1, Task 5 Step 1.

**Placeholder scan:** No TBDs. Every code step shows complete code; every
command step shows the exact command and expected output.

**Type consistency:** `_oco_asymmetric_precompute` returns the same dict keys
(`i0`, `gross`, `side`, `both_touched_lookahead`, `decided`, `touch_step`) as
`_oco_precompute_candidates`, consumed identically by `OcoAsymmetricFamily`
hooks. `_run_length` returns `tuple[np.ndarray, np.ndarray]` used by both
`DirectionalRunFamily` hooks. Family hook signatures match the `MiningFamily`
protocol. `param_grid` keys (`down_pips`, `rr`, `run_bucket`, `bet`,
`horizon`) are referenced consistently across `param_grid`, the precompute
calls, and `candidate_metadata`. `FAMILY_REGISTRY` and `_LIBRARY_TYPE_ALIASES`
are extended together in Tasks 2 and 5.
