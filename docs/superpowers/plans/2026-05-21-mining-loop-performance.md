# Mining-Loop Performance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Speed up `make retrain-all` 4-12× end-to-end by (a) vectorising the two per-bar Python loops in the cross-symbol mining families, (b) batching `random_entry_baseline`'s `measure_gross` call, and (c) parallelising the per-symbol retrain via a new orchestrator script.

**Architecture:** Three independent items behind one design (`docs/superpowers/specs/2026-05-21-mining-loop-performance-design.md`). Each item is self-contained, parity-tested against its loop reference, and can ship as its own PR — or all together as one PR if you prefer a single deploy. Items 1+3 are pure replacements inside existing files with rtol=1e-6 numerical-parity tests; Item 2 is a new orchestrator + a 5-line Makefile change. No protocol changes to `MiningFamily`.

**Tech Stack:** Python, numpy, pandas, `concurrent.futures.ProcessPoolExecutor`, subprocess, pytest, the existing `scripts/mining_family.py` / `scripts/mining_random_baseline.py` / `scripts/onboard_symbol.py` / `scripts/classify_retrain_outcome.py`.

---

## File Structure

**New files:**
- `scripts/retrain_all_parallel.py` — process-pool orchestrator (Item 2)
- `tests/test_retrain_all_parallel.py` — orchestrator smoke + failure-isolation tests

**Modified files:**
- `scripts/mining_family.py` — vectorise two functions (Items 1a + 1b)
- `scripts/mining_random_baseline.py` — batched `measure_gross` call (Item 3)
- `Makefile` — `retrain-all` body redirected to new orchestrator (Item 2)
- `tests/test_mining_family.py` — parity tests for vectorised functions
- `tests/test_mining_random_baseline.py` — parity test for batched baseline

**Read but not modified:**
- `scripts/classify_retrain_outcome.py` — `classify_outcome(*, exit_code, schedule_csv)` is imported as a Python function by the orchestrator
- `scripts/onboard_symbol.py` — launched as a subprocess by each worker

---

## Task ordering and PR strategy

Tasks 1, 2, 3 are independent — any order works, each can ship alone. Task 4 (orchestrator) depends on Task 5 (Makefile wiring) only at the integration step. Recommended sequence below assumes one combined PR; to split into three PRs, commit and push after Task 2 / Task 3 / Task 5 respectively.

| Task | What | Item | Touches |
|---|---|---|---|
| 1 | Vectorise `_rolling_regression` | 1a | `mining_family.py`, `test_mining_family.py` |
| 2 | Vectorise `_per_bar_rank_and_side` | 1b | `mining_family.py`, `test_mining_family.py` |
| 3 | Batched random baseline | 3 | `mining_random_baseline.py`, `test_mining_random_baseline.py` |
| 4 | Parallel orchestrator script | 2 | `scripts/retrain_all_parallel.py` (new), `tests/test_retrain_all_parallel.py` (new) |
| 5 | Makefile wiring + PR housekeeping | 2 | `Makefile`, PR #195 close |

---

## Task 1: Vectorise `DollarFactorResidualFamily._rolling_regression`

**Files:**
- Modify: `scripts/mining_family.py` — the method body of `_rolling_regression` (currently around lines 896-958; the surrounding class structure stays unchanged)
- Test: `tests/test_mining_family.py` — append two new tests at end of file

The current implementation has `for t in range(int(window), n):` (Python loop over up to 2.2 M bars). The replacement uses pandas rolling sums to derive α, β, σ closed-form in O(n) vectorised numpy.

- [ ] **Step 1: Read current implementation and capture its exact behaviour**

Read `scripts/mining_family.py` lines 880-960 to see the current `_rolling_regression`. Note these characteristics that the parity test must preserve:
- Inputs: `cs_frame` (the cross-symbol-aligned frame), `target_symbol`, `window`.
- Computes `r = _usd_aligned_ret_z(cs_frame, target_symbol).to_numpy(float)` and `m = pd.to_numeric(cs_frame["mkt_loo"], errors="coerce").to_numpy(float)`.
- Output dict: `{"alpha": …, "beta": …, "sigma": …, "eps": …, "z": …}` — each a length-`n` float array, NaN until enough trailing bars exist.
- For each bar `t ∈ [window, n)`: fit OLS on `(r[t-window:t], m[t-window:t])`, skipping NaN pairs. Skip if fewer than `min_obs = max(window // 4, 20)` finite pairs, or `var(m) ≤ 0`, or `std(residuals) ≤ 0`.
- `eps[t] = r[t] - α[t] - β[t]·m[t]` (only if both `r[t]` and `m[t]` are finite); `z[t] = eps[t] / σ[t]`.

The vectorised version must produce arrays that match within `rtol=1e-6` on a synthetic fixture, with bitwise-identical NaN positions.

- [ ] **Step 2: Add a private reference implementation `_rolling_regression_loop` next to the current one**

Above the current `_rolling_regression`, paste an exact copy renamed to `_rolling_regression_loop`. This is the parity oracle the test compares against. After the test passes we keep it (as `_loop` suffix) until the PR review confirms confidence; do not delete in this task.

```python
    def _rolling_regression_loop(
        self, cs_frame: pd.DataFrame, target_symbol: str, window: int
    ) -> dict[str, np.ndarray]:
        """REFERENCE — loop version, kept for parity testing. Do not call
        from production code; use `_rolling_regression` (vectorised)."""
        from scripts.cross_symbol import _usd_aligned_ret_z

        r = _usd_aligned_ret_z(cs_frame, target_symbol).to_numpy(dtype=float)
        m = pd.to_numeric(cs_frame["mkt_loo"], errors="coerce").to_numpy(dtype=float)
        n = len(r)
        alpha = np.full(n, np.nan, dtype=float)
        beta = np.full(n, np.nan, dtype=float)
        sigma = np.full(n, np.nan, dtype=float)
        eps = np.full(n, np.nan, dtype=float)
        z = np.full(n, np.nan, dtype=float)
        min_obs = max(int(window // 4), 20)

        for t in range(int(window), n):
            lo = t - int(window)
            rr = r[lo:t]
            mm = m[lo:t]
            ok = np.isfinite(rr) & np.isfinite(mm)
            if int(ok.sum()) < min_obs:
                continue
            rr = rr[ok]
            mm = mm[ok]
            m_var = float(np.var(mm))
            if m_var <= 0.0:
                continue
            m_mean = float(np.mean(mm))
            r_mean = float(np.mean(rr))
            b = float(np.cov(rr, mm, ddof=0)[0, 1] / m_var)
            a = r_mean - b * m_mean
            e_train = rr - a - b * mm
            s = float(np.std(e_train, ddof=0))
            if not np.isfinite(s) or s <= 0.0:
                continue
            alpha[t] = a
            beta[t] = b
            sigma[t] = s
            if np.isfinite(r[t]) and np.isfinite(m[t]):
                eps_t = r[t] - a - b * m[t]
                eps[t] = eps_t
                z[t] = eps_t / s

        return {"alpha": alpha, "beta": beta, "sigma": sigma, "eps": eps, "z": z}
```

- [ ] **Step 3: Write the failing parity test**

Add to `tests/test_mining_family.py` at end of file:

```python
def test_dollar_residual_rolling_regression_vectorised_matches_loop(tmp_path):
    """Item 1a parity: vectorised _rolling_regression must match the
    loop version within rtol=1e-6 on a synthetic 6-symbol fixture."""
    from scripts.cross_symbol import CROSS_SYMBOLS
    from scripts.mining_family import DollarFactorResidualFamily
    from scripts.run_tick_opportunity_mining import _prepare_frame
    from tests.test_tick_opportunity_mining import _build_synth_tick_velocity

    dataset_dir = tmp_path / "tick_velocity"
    dataset_dir.mkdir(parents=True, exist_ok=True)
    for sym in CROSS_SYMBOLS:
        _build_synth_tick_velocity(
            dataset_dir / f"{sym}_1000tick_velocity.parquet", symbol=sym,
        )
    fam = DollarFactorResidualFamily()
    frame = _prepare_frame(
        dataset_dir / "EURUSD_1000tick_velocity.parquet",
        symbol="EURUSD", horizons=[1, 2, 3],
    )
    params = {
        "symbol": "EURUSD", "bar_ticks": 1000,
        "horizon": 1, "residual_window": 200, "threshold_z": 1.5,
        "_dataset_dir": str(dataset_dir),
        "_horizons": (1, 2, 3),
    }
    cs = fam._build_cs_frame(frame, params)
    assert cs is not None

    looped = fam._rolling_regression_loop(cs, "EURUSD", 200)
    vectorised = fam._rolling_regression(cs, "EURUSD", 200)

    for key in ("alpha", "beta", "sigma", "eps", "z"):
        np.testing.assert_allclose(
            vectorised[key], looped[key],
            rtol=1e-6, atol=1e-12, equal_nan=True,
            err_msg=f"mismatch in {key!r}",
        )
```

- [ ] **Step 4: Run the test to verify it fails**

```bash
uv run pytest tests/test_mining_family.py::test_dollar_residual_rolling_regression_vectorised_matches_loop -v
```

Expected: PASS if Step 2 didn't rename anything yet (both functions exist), or FAIL with `AttributeError: '_rolling_regression_loop'` if you forgot Step 2.

Note: the test passes trivially right now because `_rolling_regression` IS the loop. The real failing-test moment is Step 6 (after the vectorised rewrite, before tightening the existing cache logic). Continue.

- [ ] **Step 5: Rewrite `_rolling_regression` body with vectorised numpy**

Replace the entire body of `_rolling_regression` (keep the signature, the `_reg_cache` lookup, and the cache write) with:

```python
    def _rolling_regression(
        self, cs_frame: pd.DataFrame, target_symbol: str, window: int
    ) -> dict[str, np.ndarray]:
        """Trailing-window OLS of target USD-aligned ret_z on mkt_loo —
        vectorised. Matches `_rolling_regression_loop` within rtol=1e-6;
        ~100-500x faster at n=2M."""
        from scripts.cross_symbol import _usd_aligned_ret_z

        key = (_frame_fingerprint(cs_frame), int(window))
        if key in self._reg_cache:
            return self._reg_cache[key]

        r = _usd_aligned_ret_z(cs_frame, target_symbol).to_numpy(dtype=float)
        m = pd.to_numeric(cs_frame["mkt_loo"], errors="coerce").to_numpy(dtype=float)
        n = len(r)
        w = int(window)
        min_obs = max(w // 4, 20)

        # NaN-safe: replace NaNs with 0 in r,m AND track count of valid pairs.
        ok = np.isfinite(r) & np.isfinite(m)
        r0 = np.where(ok, r, 0.0)
        m0 = np.where(ok, m, 0.0)

        # Rolling sums shifted by 1 so bar t's window is [t-w, t) strictly.
        # min_periods=1 to get partials; we'll mask insufficient counts after.
        def _roll_sum(a: np.ndarray) -> np.ndarray:
            s = pd.Series(a).rolling(w, min_periods=1).sum().to_numpy(dtype=float)
            return np.concatenate(([np.nan], s[:-1]))  # shift(1)

        cnt = _roll_sum(ok.astype(float))
        sum_r = _roll_sum(r0)
        sum_m = _roll_sum(m0)
        sum_rm = _roll_sum(r0 * m0)
        sum_r2 = _roll_sum(r0 * r0)
        sum_m2 = _roll_sum(m0 * m0)

        with np.errstate(invalid="ignore", divide="ignore"):
            mean_r = sum_r / cnt
            mean_m = sum_m / cnt
            mean_rm = sum_rm / cnt
            mean_r2 = sum_r2 / cnt
            mean_m2 = sum_m2 / cnt

            var_m = mean_m2 - mean_m * mean_m
            cov_rm = mean_rm - mean_r * mean_m
            beta = np.where(var_m > 0.0, cov_rm / np.where(var_m > 0.0, var_m, 1.0), np.nan)
            alpha = mean_r - beta * mean_m

            # σ² = E[(r - α - β m)²]_window expanded in moments:
            sigma2 = (
                mean_r2
                - 2.0 * alpha * mean_r
                - 2.0 * beta * mean_rm
                + alpha * alpha
                + 2.0 * alpha * beta * mean_m
                + beta * beta * mean_m2
            )
            sigma2 = np.maximum(sigma2, 0.0)
            sigma = np.sqrt(sigma2)
            sigma = np.where(sigma > 0.0, sigma, np.nan)

            eps_now = r - alpha - beta * m
            z_now = eps_now / sigma

        # Apply gating: NaN out bars that didn't have enough trailing pairs.
        insufficient = ~(cnt >= float(min_obs))
        for arr in (alpha, beta, sigma):
            arr[insufficient] = np.nan
        # eps/z further require r[t] and m[t] to be finite themselves.
        eps_out = np.where(
            insufficient | ~np.isfinite(r) | ~np.isfinite(m) | ~np.isfinite(sigma),
            np.nan,
            eps_now,
        )
        z_out = np.where(
            insufficient | ~np.isfinite(r) | ~np.isfinite(m) | ~np.isfinite(sigma),
            np.nan,
            z_now,
        )

        # Bars 0..w-1: by definition no window of size `w` exists -> all NaN.
        for arr in (alpha, beta, sigma, eps_out, z_out):
            arr[:w] = np.nan

        out = {"alpha": alpha, "beta": beta, "sigma": sigma,
               "eps": eps_out, "z": z_out}
        self._reg_cache[key] = out
        return out
```

- [ ] **Step 6: Run the parity test — must pass**

```bash
uv run pytest tests/test_mining_family.py::test_dollar_residual_rolling_regression_vectorised_matches_loop -v
```

Expected: PASS.

If it fails with rtol violations, the most likely culprit is the `shift(1)` semantics differing from `[lo:t]` slicing at the very first valid bar. Inspect the failing index with:

```python
np.where(~np.isclose(vectorised["alpha"], looped["alpha"], rtol=1e-6, equal_nan=True))[0][:5]
```

and adjust the `_roll_sum` shift accordingly.

- [ ] **Step 7: Run the broader mining-family test suite to confirm no regression**

```bash
uv run pytest tests/test_mining_family.py tests/test_oco_candidate_family_allowlist.py tests/test_cross_symbol.py tests/test_tick_opportunity_mining.py -q
```

Expected: all pass (currently 108+).

- [ ] **Step 8: Add a microbenchmark assertion**

Append to `tests/test_mining_family.py`:

```python
def test_dollar_residual_rolling_regression_vectorised_is_at_least_50x_faster(tmp_path):
    """Item 1a perf gate: ≥50x faster than the loop on a 5000-bar synthetic
    frame. Skipped if `BENCH_SKIP=1` is set in the env."""
    import os
    import time

    if os.environ.get("BENCH_SKIP") == "1":
        import pytest as _pt
        _pt.skip("benchmark gated off via BENCH_SKIP=1")

    from scripts.cross_symbol import CROSS_SYMBOLS
    from scripts.mining_family import DollarFactorResidualFamily
    from scripts.run_tick_opportunity_mining import _prepare_frame
    from tests.test_tick_opportunity_mining import _build_synth_tick_velocity

    dataset_dir = tmp_path / "tick_velocity"
    dataset_dir.mkdir(parents=True, exist_ok=True)
    for sym in CROSS_SYMBOLS:
        _build_synth_tick_velocity(
            dataset_dir / f"{sym}_1000tick_velocity.parquet", symbol=sym, n_bars=5000,
        )
    fam = DollarFactorResidualFamily()
    frame = _prepare_frame(
        dataset_dir / "EURUSD_1000tick_velocity.parquet",
        symbol="EURUSD", horizons=[1, 2, 3],
    )
    params = {
        "symbol": "EURUSD", "bar_ticks": 1000,
        "horizon": 1, "residual_window": 200, "threshold_z": 1.5,
        "_dataset_dir": str(dataset_dir), "_horizons": (1, 2, 3),
    }
    cs = fam._build_cs_frame(frame, params)
    assert cs is not None and len(cs) >= 1000

    # Best-of-3 wall-clock on the two implementations.
    def _time(fn) -> float:
        best = float("inf")
        for _ in range(3):
            fam._reg_cache.clear()
            t0 = time.perf_counter()
            fn()
            best = min(best, time.perf_counter() - t0)
        return best

    t_loop = _time(lambda: fam._rolling_regression_loop(cs, "EURUSD", 200))
    fam._reg_cache.clear()
    t_vec = _time(lambda: fam._rolling_regression(cs, "EURUSD", 200))

    speedup = t_loop / max(t_vec, 1e-9)
    assert speedup >= 50.0, f"got {speedup:.1f}x; loop={t_loop:.3f}s vec={t_vec:.3f}s"
```

The `n_bars=5000` argument may need to be added to `_build_synth_tick_velocity` if it doesn't accept it — check its signature with `grep -n "def _build_synth_tick_velocity" tests/test_tick_opportunity_mining.py` and use its existing default if `n_bars` isn't a parameter (the test still demonstrates the speedup; only the magnitude varies with frame size).

- [ ] **Step 9: Run the benchmark to confirm ≥50x speedup**

```bash
uv run pytest tests/test_mining_family.py::test_dollar_residual_rolling_regression_vectorised_is_at_least_50x_faster -v
```

Expected: PASS with a logged speedup ≥50x.

- [ ] **Step 10: Commit Task 1**

```bash
git add scripts/mining_family.py tests/test_mining_family.py
git commit -m "perf: vectorise DollarFactorResidualFamily._rolling_regression

Replaces the O(n) Python loop over bars with closed-form rolling-sum
algebra in numpy. At n=2.2M (EURUSD 100-tick) the loop was the
dominant cost in cross-symbol family A mining.

- Rolling sums of r, m, r·m, r², m² computed once via pd.Series.rolling
  shifted by 1 so bar t's fit window is [t-w, t) strictly.
- α, β, σ derived in closed form; σ² clamped to ≥0 (catastrophic-
  cancellation safety).
- Matches the loop reference within rtol=1e-6 on a 6-symbol synth
  fixture (parity test pinned).
- ≥50x faster microbenchmark gate added.
- Loop kept as _rolling_regression_loop reference for the parity test;
  removable in a follow-up PR if review confidence is high.

Item 1a of docs/superpowers/specs/2026-05-21-mining-loop-performance-design.md.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 2: Vectorise `DispersionRankFamily._per_bar_rank_and_side`

**Files:**
- Modify: `scripts/mining_family.py` — method body of `_per_bar_rank_and_side` (currently around line 1103-1145)
- Test: `tests/test_mining_family.py` — append two new tests

The current implementation has `for i in range(n):` calling `np.argsort` per row. The replacement uses one full-matrix `np.argsort(..., axis=1)`.

- [ ] **Step 1: Add a `_per_bar_rank_and_side_loop` reference next to the current implementation**

Above the current `_per_bar_rank_and_side`, paste:

```python
    def _per_bar_rank_and_side_loop(
        self, cs_frame: pd.DataFrame, target_symbol: str
    ) -> tuple[np.ndarray, np.ndarray]:
        """REFERENCE — loop version, kept for parity testing."""
        from scripts.cross_symbol import (
            CROSS_SYMBOLS,
            _USD_SIGN,
            _usd_aligned_ret_z,
        )

        n = len(cs_frame)
        target_usd = _usd_aligned_ret_z(cs_frame, target_symbol).to_numpy(float)
        peers = sorted(s for s in CROSS_SYMBOLS if s != target_symbol)
        peer_cols = [f"xs_ret_z__{s}" for s in peers]
        cols = peer_cols + ["__target"]
        matrix = cs_frame[peer_cols].copy()
        matrix["__target"] = target_usd
        arr = matrix[cols].to_numpy(float)

        target_rank = np.full(n, np.nan, dtype=float)
        for i in range(n):
            row = arr[i]
            if not np.isfinite(row).all():
                continue
            order = np.argsort(-row, kind="stable")
            rank_of_col = np.empty(len(row), dtype=np.int64)
            rank_of_col[order] = np.arange(1, len(row) + 1)
            target_rank[i] = float(rank_of_col[-1])

        usd = _USD_SIGN[target_symbol]
        return (target_rank, np.full(n, usd, dtype=np.int8))
```

- [ ] **Step 2: Write the failing parity test**

Append to `tests/test_mining_family.py`:

```python
def test_dispersion_rank_per_bar_vectorised_matches_loop(tmp_path):
    """Item 1b parity: vectorised _per_bar_rank_and_side must produce
    bitwise-identical output to the loop on a synthetic frame."""
    from scripts.cross_symbol import CROSS_SYMBOLS
    from scripts.mining_family import DispersionRankFamily
    from scripts.run_tick_opportunity_mining import _prepare_frame
    from tests.test_tick_opportunity_mining import _build_synth_tick_velocity

    dataset_dir = tmp_path / "tick_velocity"
    dataset_dir.mkdir(parents=True, exist_ok=True)
    for sym in CROSS_SYMBOLS:
        _build_synth_tick_velocity(
            dataset_dir / f"{sym}_1000tick_velocity.parquet", symbol=sym,
        )
    fam = DispersionRankFamily()
    frame = _prepare_frame(
        dataset_dir / "EURUSD_1000tick_velocity.parquet",
        symbol="EURUSD", horizons=[1, 2, 3],
    )
    params = {
        "symbol": "EURUSD", "bar_ticks": 1000,
        "horizon": 1, "rank_k": 1,
        "_dataset_dir": str(dataset_dir), "_horizons": (1, 2, 3),
    }
    cs = fam._build_cs_frame(frame, params)
    assert cs is not None

    rank_loop, usd_loop = fam._per_bar_rank_and_side_loop(cs, "EURUSD")
    rank_vec, usd_vec = fam._per_bar_rank_and_side(cs, "EURUSD")

    np.testing.assert_array_equal(usd_vec, usd_loop)
    # rank is float (NaN-bearing) — compare with equal_nan and exact int values.
    np.testing.assert_array_equal(
        np.where(np.isnan(rank_vec), -1, rank_vec.astype(np.int64)),
        np.where(np.isnan(rank_loop), -1, rank_loop.astype(np.int64)),
    )
```

- [ ] **Step 3: Run the test — should pass trivially (both call the loop today)**

```bash
uv run pytest tests/test_mining_family.py::test_dispersion_rank_per_bar_vectorised_matches_loop -v
```

Expected: PASS (because `_per_bar_rank_and_side` IS the loop today; the test pins behaviour before the rewrite).

- [ ] **Step 4: Rewrite `_per_bar_rank_and_side` body with vectorised numpy**

Replace the entire body (keep the signature, the `_rank_cache` lookup, and the cache write) with:

```python
    def _per_bar_rank_and_side(
        self, cs_frame: pd.DataFrame, target_symbol: str
    ) -> tuple[np.ndarray, np.ndarray]:
        """Per-bar descending rank of the target's USD-aligned return among
        the 6 majors. Vectorised — one np.argsort on the full (n,6) matrix
        replaces the per-row argsort loop. Matches `_loop` exactly."""
        from scripts.cross_symbol import (
            CROSS_SYMBOLS,
            _USD_SIGN,
            _usd_aligned_ret_z,
        )

        key = (_frame_fingerprint(cs_frame), target_symbol)
        if key in self._rank_cache:
            return self._rank_cache[key]

        n = len(cs_frame)
        target_usd = _usd_aligned_ret_z(cs_frame, target_symbol).to_numpy(float)
        peers = sorted(s for s in CROSS_SYMBOLS if s != target_symbol)
        peer_cols = [f"xs_ret_z__{s}" for s in peers]
        cols = peer_cols + ["__target"]
        matrix = cs_frame[peer_cols].copy()
        matrix["__target"] = target_usd
        arr = matrix[cols].to_numpy(float)  # shape (n, 6)

        target_rank = np.full(n, np.nan, dtype=float)
        all_finite = np.isfinite(arr).all(axis=1)
        if np.any(all_finite):
            # Descending stable argsort: order[i, k] = column index of the
            # k-th largest value in row i.
            order = np.argsort(-arr[all_finite], axis=1, kind="stable")
            # Inverse permutation per row -> rank of each column (1-based).
            ranks = np.empty_like(order)
            row_idx = np.arange(order.shape[0])[:, None]
            rank_values = np.broadcast_to(
                np.arange(1, arr.shape[1] + 1), order.shape
            )
            ranks[row_idx, order] = rank_values
            # Target was placed in the last column.
            target_rank[all_finite] = ranks[:, -1].astype(float)

        usd = _USD_SIGN[target_symbol]
        result = (target_rank, np.full(n, usd, dtype=np.int8))
        self._rank_cache[key] = result
        return result
```

- [ ] **Step 5: Run the parity test — must pass**

```bash
uv run pytest tests/test_mining_family.py::test_dispersion_rank_per_bar_vectorised_matches_loop -v
```

Expected: PASS.

- [ ] **Step 6: Run the broader test suite**

```bash
uv run pytest tests/test_mining_family.py tests/test_cross_symbol.py tests/test_tick_opportunity_mining.py -q
```

Expected: all pass.

- [ ] **Step 7: Add the perf-gate benchmark**

Append to `tests/test_mining_family.py`:

```python
def test_dispersion_rank_vectorised_is_at_least_100x_faster(tmp_path):
    """Item 1b perf gate: ≥100x faster than the loop."""
    import os
    import time

    if os.environ.get("BENCH_SKIP") == "1":
        import pytest as _pt
        _pt.skip("benchmark gated off via BENCH_SKIP=1")

    from scripts.cross_symbol import CROSS_SYMBOLS
    from scripts.mining_family import DispersionRankFamily
    from scripts.run_tick_opportunity_mining import _prepare_frame
    from tests.test_tick_opportunity_mining import _build_synth_tick_velocity

    dataset_dir = tmp_path / "tick_velocity"
    dataset_dir.mkdir(parents=True, exist_ok=True)
    for sym in CROSS_SYMBOLS:
        _build_synth_tick_velocity(
            dataset_dir / f"{sym}_1000tick_velocity.parquet", symbol=sym,
        )
    fam = DispersionRankFamily()
    frame = _prepare_frame(
        dataset_dir / "EURUSD_1000tick_velocity.parquet",
        symbol="EURUSD", horizons=[1, 2, 3],
    )
    params = {
        "symbol": "EURUSD", "bar_ticks": 1000,
        "horizon": 1, "rank_k": 1,
        "_dataset_dir": str(dataset_dir), "_horizons": (1, 2, 3),
    }
    cs = fam._build_cs_frame(frame, params)
    assert cs is not None and len(cs) >= 1000

    def _time(fn) -> float:
        best = float("inf")
        for _ in range(3):
            fam._rank_cache.clear()
            t0 = time.perf_counter()
            fn()
            best = min(best, time.perf_counter() - t0)
        return best

    t_loop = _time(lambda: fam._per_bar_rank_and_side_loop(cs, "EURUSD"))
    fam._rank_cache.clear()
    t_vec = _time(lambda: fam._per_bar_rank_and_side(cs, "EURUSD"))

    speedup = t_loop / max(t_vec, 1e-9)
    assert speedup >= 100.0, f"got {speedup:.1f}x; loop={t_loop:.3f}s vec={t_vec:.3f}s"
```

- [ ] **Step 8: Run the benchmark**

```bash
uv run pytest tests/test_mining_family.py::test_dispersion_rank_vectorised_is_at_least_100x_faster -v
```

Expected: PASS with ≥100x.

- [ ] **Step 9: Commit Task 2**

```bash
git add scripts/mining_family.py tests/test_mining_family.py
git commit -m "perf: vectorise DispersionRankFamily._per_bar_rank_and_side

One np.argsort on the full (n, 6) matrix + an inverse-permutation
broadcast replaces the per-row np.argsort loop. Bit-identical output
to the loop reference (_per_bar_rank_and_side_loop kept for parity).

At n=2.2M this drops the per-bar Python iteration that dominated
cross-symbol family B mining.

≥100x faster microbenchmark gate added.

Item 1b of docs/superpowers/specs/2026-05-21-mining-loop-performance-design.md.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 3: Batched `random_entry_baseline`

**Files:**
- Modify: `scripts/mining_random_baseline.py` — the body of `random_entry_baseline` (line 18 onwards)
- Test: `tests/test_mining_random_baseline.py` — append two new tests

The current implementation calls `family.measure_gross` 200 times in a Python for-loop. The replacement stacks all draws into one (n_draws × n_entries) array and makes a single call.

- [ ] **Step 1: Write the failing parity test**

Append to `tests/test_mining_random_baseline.py`:

```python
def test_random_entry_baseline_batched_matches_loop(tmp_path):
    """Item 3 parity: same seed -> bit-identical control distribution
    whether the family is called once per draw or once for all draws."""
    import numpy as np
    import pandas as pd

    from scripts.mining_family import FAMILY_REGISTRY
    from scripts.mining_random_baseline import random_entry_baseline

    rng_a = np.random.default_rng(12345)
    rng_b = np.random.default_rng(12345)

    # A directional-style family (cheap, exercises the indexing path).
    frame = pd.DataFrame({
        "y_fwd_pips_h1": np.arange(1000, dtype=float),
        "_dir_side_h1": np.tile([1, -1], 500).astype(np.int8),
    })
    fam = FAMILY_REGISTRY["directional"]
    params = {"horizon": 1, "symbol": "EURUSD", "bar_ticks": 1000}

    # Reference: the old looped implementation (inline to avoid coupling).
    def _looped(rng):
        n_rows = len(frame)
        n_entries = 50
        n_draws = 25
        control = np.empty(n_draws, dtype=float)
        for i in range(n_draws):
            draw = rng.choice(n_rows, size=n_entries, replace=False)
            gross = np.asarray(fam.measure_gross(frame, draw, params), dtype=float)
            gross = gross[np.isfinite(gross)]
            control[i] = float(np.mean(gross)) if gross.size else float("nan")
        return float(np.mean(control[np.isfinite(control)]))

    loop_control_mean = _looped(rng_a)
    batched = random_entry_baseline(
        fam, frame, params,
        n_entries=50, n_draws=25, rng=rng_b,
        candidate_gross_ev=None,
    )
    assert abs(batched["random_baseline_control_mean"] - loop_control_mean) < 1e-12
```

- [ ] **Step 2: Run the test — currently it passes (the production code is still the loop)**

```bash
uv run pytest tests/test_mining_random_baseline.py::test_random_entry_baseline_batched_matches_loop -v
```

Expected: PASS. The test pins the bit-identical-result requirement before the rewrite.

- [ ] **Step 3: Rewrite `random_entry_baseline` to batch the `measure_gross` call**

Replace the body of `random_entry_baseline` in `scripts/mining_random_baseline.py` (keep the signature and the NaN-result fast-path):

```python
def random_entry_baseline(
    family: MiningFamily,
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

    Vectorised: draws all n_draws entry-sets upfront, calls
    family.measure_gross ONCE on the flattened (n_draws * n_entries)
    indices, and reshapes back to per-draw means. Same RNG seed yields
    bit-identical control statistics as the per-draw loop.
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

    n_draws = int(n_draws)
    n_entries = int(n_entries)
    draws = np.stack([
        rng.choice(n_rows, size=n_entries, replace=False)
        for _ in range(n_draws)
    ])  # (n_draws, n_entries)
    gross_flat = np.asarray(
        family.measure_gross(frame, draws.ravel(), params),
        dtype=float,
    )
    if gross_flat.shape[0] != n_draws * n_entries:
        # Defensive: family contract says measure_gross returns one value
        # per entry. Anything else is a bug; fall back to NaN result.
        print(
            f"warning: family {getattr(family, 'name', '?')!r} returned "
            f"gross of length {gross_flat.shape[0]} for "
            f"{n_draws * n_entries} entries; baseline skipped"
        )
        return nan_result
    gross_per_draw = gross_flat.reshape(n_draws, n_entries)
    with np.errstate(invalid="ignore"):
        control = np.nanmean(gross_per_draw, axis=1)

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

- [ ] **Step 4: Run the parity test — must still pass**

```bash
uv run pytest tests/test_mining_random_baseline.py::test_random_entry_baseline_batched_matches_loop -v
```

Expected: PASS. If a family's `measure_gross` doesn't tolerate the flattened large-N draw, this will surface here. The directional family used in the test is the cheapest exercise; the cross-symbol families share the same protocol so they will work too.

- [ ] **Step 5: Add a perf-gate benchmark**

Append to `tests/test_mining_random_baseline.py`:

```python
def test_random_entry_baseline_batched_is_at_least_5x_faster():
    """Item 3 perf gate: ≥5x faster than the per-draw loop on a
    representative cached-precompute family (OCO)."""
    import os
    import time

    if os.environ.get("BENCH_SKIP") == "1":
        import pytest as _pt
        _pt.skip("benchmark gated off via BENCH_SKIP=1")

    import numpy as np
    import pandas as pd
    from scripts.mining_family import FAMILY_REGISTRY
    from scripts.mining_random_baseline import random_entry_baseline

    n_rows = 10_000
    rng = np.random.default_rng(0)
    # Synthetic OHLC sufficient for the directional family.
    frame = pd.DataFrame({
        "y_fwd_pips_h1": rng.normal(0.0, 1.0, n_rows),
        "_dir_side_h1": rng.choice([-1, 1], size=n_rows).astype(np.int8),
    })
    fam = FAMILY_REGISTRY["directional"]
    params = {"horizon": 1, "symbol": "EURUSD", "bar_ticks": 1000}

    def _looped():
        rng2 = np.random.default_rng(42)
        for _ in range(200):
            draw = rng2.choice(n_rows, size=500, replace=False)
            _ = np.asarray(fam.measure_gross(frame, draw, params), float)

    def _batched():
        rng2 = np.random.default_rng(42)
        random_entry_baseline(
            fam, frame, params,
            n_entries=500, n_draws=200, rng=rng2,
            candidate_gross_ev=None,
        )

    def _time(fn) -> float:
        best = float("inf")
        for _ in range(3):
            t0 = time.perf_counter()
            fn()
            best = min(best, time.perf_counter() - t0)
        return best

    t_loop = _time(_looped)
    t_batch = _time(_batched)
    speedup = t_loop / max(t_batch, 1e-9)
    assert speedup >= 5.0, f"got {speedup:.1f}x; loop={t_loop:.3f}s batch={t_batch:.3f}s"
```

- [ ] **Step 6: Run benchmark**

```bash
uv run pytest tests/test_mining_random_baseline.py::test_random_entry_baseline_batched_is_at_least_5x_faster -v
```

Expected: PASS ≥5x.

- [ ] **Step 7: Run the full mining test surface to confirm no regression**

```bash
uv run pytest tests/test_mining_random_baseline.py tests/test_mining_family.py tests/test_tick_opportunity_mining.py tests/test_oco_candidate_family_allowlist.py tests/test_cross_symbol.py -q
```

Expected: all pass.

- [ ] **Step 8: Commit Task 3**

```bash
git add scripts/mining_random_baseline.py tests/test_mining_random_baseline.py
git commit -m "perf: batch random_entry_baseline's measure_gross call

Previously the baseline called family.measure_gross 200 times in a
Python for-loop. Now it stacks all draws once and calls measure_gross
on the flattened (n_draws * n_entries) array, paying family-side
overhead (cache lookup, reindex, NaN-mask) once per candidate instead
of 200x.

Same RNG seed yields bit-identical control statistics (parity test
pinned). ≥5x faster microbenchmark gate added.

No MiningFamily protocol change — all families already accept arbitrary
entry-index arrays (the baseline contract relied on this).

Item 3 of docs/superpowers/specs/2026-05-21-mining-loop-performance-design.md.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 4: New parallel orchestrator `scripts/retrain_all_parallel.py`

**Files:**
- Create: `scripts/retrain_all_parallel.py`
- Create: `tests/test_retrain_all_parallel.py`

A new script that takes over what the Makefile's `for sym in $(REBUILD_SYMBOLS)` loop did, running each symbol's `onboard_symbol.py` invocation in a worker subprocess via `ProcessPoolExecutor`.

- [ ] **Step 1: Write the failing test for outcome collection**

Create `tests/test_retrain_all_parallel.py`:

```python
"""Tests for the parallel retrain orchestrator."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from scripts.retrain_all_parallel import (
    WorkerResult,
    collect_outcomes,
    run_orchestrator,
)


def _stub_schedule(path: Path, n_rows: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if n_rows == 0:
        path.write_text("")
    else:
        pd.DataFrame({"state_id": [f"s{i}" for i in range(n_rows)]}).to_csv(path, index=False)


def test_collect_outcomes_orders_results_and_summarises(tmp_path):
    """Worker results may arrive in any order; the summary must be in
    REBUILD_SYMBOLS order with the right outcome per symbol."""
    ad = tmp_path / "analysis"
    (ad / "reduced_core_rolling").mkdir(parents=True)
    _stub_schedule(ad / "reduced_core_rolling" / "EURUSD_oco_reduced_state_schedule.csv", 3)
    _stub_schedule(ad / "reduced_core_rolling" / "GBPUSD_oco_reduced_state_schedule.csv", 0)
    # USDJPY: no schedule file at all

    results = [
        WorkerResult(symbol="GBPUSD", exit_code=0, log_path=tmp_path / "g.log", elapsed_s=10.0),
        WorkerResult(symbol="EURUSD", exit_code=0, log_path=tmp_path / "e.log", elapsed_s=20.0),
        WorkerResult(symbol="USDJPY", exit_code=1, log_path=tmp_path / "u.log", elapsed_s=5.0),
    ]
    summary = collect_outcomes(
        results,
        symbols_order=["EURUSD", "GBPUSD", "USDJPY"],
        analysis_dir=ad,
    )
    assert [s.symbol for s in summary] == ["EURUSD", "GBPUSD", "USDJPY"]
    assert [s.outcome for s in summary] == ["DEPLOY", "NO_TRADE", "FAILED"]


def test_orchestrator_isolates_worker_failure(tmp_path):
    """One worker failing must not cancel siblings; final exit is 1."""
    ad = tmp_path / "analysis"
    (ad / "reduced_core_rolling").mkdir(parents=True)
    _stub_schedule(ad / "reduced_core_rolling" / "EURUSD_oco_reduced_state_schedule.csv", 1)
    _stub_schedule(ad / "reduced_core_rolling" / "GBPUSD_oco_reduced_state_schedule.csv", 1)

    def fake_run_worker(symbol: str, *, eval_end_month, log_dir):
        if symbol == "GBPUSD":
            return WorkerResult(symbol=symbol, exit_code=1, log_path=log_dir / f"{symbol}.log", elapsed_s=1.0)
        return WorkerResult(symbol=symbol, exit_code=0, log_path=log_dir / f"{symbol}.log", elapsed_s=1.0)

    with patch("scripts.retrain_all_parallel.run_worker", side_effect=fake_run_worker):
        exit_code, summary = run_orchestrator(
            symbols=["EURUSD", "GBPUSD"],
            max_workers=2,
            eval_end_month=None,
            log_dir=tmp_path,
            analysis_dir=ad,
        )
    assert exit_code == 1
    by_sym = {s.symbol: s.outcome for s in summary}
    assert by_sym["EURUSD"] == "DEPLOY"
    assert by_sym["GBPUSD"] == "FAILED"
```

- [ ] **Step 2: Run the test to confirm it fails**

```bash
uv run pytest tests/test_retrain_all_parallel.py -v
```

Expected: FAIL with `ImportError: No module named 'scripts.retrain_all_parallel'` or `cannot import name 'WorkerResult'`.

- [ ] **Step 3: Implement `scripts/retrain_all_parallel.py`**

```python
"""Parallel orchestrator for `make retrain-all`.

Spawns one subprocess per symbol via ProcessPoolExecutor and aggregates
outcomes in REBUILD_SYMBOLS order. Replaces the Makefile's serial
`for sym in $(REBUILD_SYMBOLS)` loop while keeping the per-symbol
onboard_symbol.py invocation unchanged.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from scripts.classify_retrain_outcome import classify_outcome

DEFAULT_SYMBOLS: tuple[str, ...] = (
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD",
)


@dataclass(frozen=True)
class WorkerResult:
    symbol: str
    exit_code: int
    log_path: Path
    elapsed_s: float


@dataclass(frozen=True)
class SymbolSummary:
    symbol: str
    outcome: str       # "DEPLOY" | "NO_TRADE" | "FAILED"
    exit_code: int
    log_path: Path
    elapsed_s: float


def run_worker(
    symbol: str,
    *,
    eval_end_month: str | None,
    log_dir: Path,
) -> WorkerResult:
    """Invoke onboard_symbol.py for one symbol as a subprocess.

    Stdout+stderr stream to `{log_dir}/{symbol}.log` so concurrent
    workers don't interleave on the terminal.
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{symbol}.log"
    cmd = [
        sys.executable, "-m", "uv", "run", "python",
        "scripts/onboard_symbol.py",
        "--symbol", symbol,
        "--skip-data",
        "--skip-docs",
        "--skip-registration",
        "--model-export-dir", "models/oco",
    ]
    if eval_end_month:
        cmd += ["--eval-end-month", eval_end_month]
    t0 = time.perf_counter()
    with log_path.open("w") as fh:
        proc = subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT, check=False)
    return WorkerResult(
        symbol=symbol,
        exit_code=int(proc.returncode),
        log_path=log_path,
        elapsed_s=time.perf_counter() - t0,
    )


def collect_outcomes(
    results: Iterable[WorkerResult],
    *,
    symbols_order: list[str],
    analysis_dir: Path,
) -> list[SymbolSummary]:
    """Map WorkerResult → SymbolSummary in REBUILD_SYMBOLS order using
    classify_outcome on each symbol's reduced_state_schedule.csv."""
    by_sym: dict[str, WorkerResult] = {r.symbol: r for r in results}
    out: list[SymbolSummary] = []
    for sym in symbols_order:
        r = by_sym.get(sym)
        if r is None:
            # Should not happen with the current pool, but be defensive.
            out.append(SymbolSummary(
                symbol=sym, outcome="FAILED", exit_code=-1,
                log_path=Path(os.devnull), elapsed_s=0.0,
            ))
            continue
        sched = analysis_dir / "reduced_core_rolling" / f"{sym}_oco_reduced_state_schedule.csv"
        outcome = classify_outcome(exit_code=r.exit_code, schedule_csv=sched)
        out.append(SymbolSummary(
            symbol=sym, outcome=outcome, exit_code=r.exit_code,
            log_path=r.log_path, elapsed_s=r.elapsed_s,
        ))
    return out


def run_orchestrator(
    *,
    symbols: list[str],
    max_workers: int,
    eval_end_month: str | None,
    log_dir: Path,
    analysis_dir: Path,
) -> tuple[int, list[SymbolSummary]]:
    """Run all symbols concurrently, return (exit_code, ordered_summary).
    Exit code is 1 if any symbol FAILED, else 0."""
    print(f"=== Parallel retrain: {len(symbols)} symbols, {max_workers} workers ===")
    log_dir.mkdir(parents=True, exist_ok=True)
    results: list[WorkerResult] = []
    with ProcessPoolExecutor(max_workers=max_workers) as ex:
        futures = {
            ex.submit(run_worker, sym, eval_end_month=eval_end_month, log_dir=log_dir): sym
            for sym in symbols
        }
        for fut in as_completed(futures):
            r = fut.result()
            print(f"  [done {r.symbol} exit={r.exit_code} elapsed={r.elapsed_s:.0f}s log={r.log_path}]")
            results.append(r)

    summary = collect_outcomes(results, symbols_order=symbols, analysis_dir=analysis_dir)
    print("\n══════════ Retrain summary ══════════")
    for s in summary:
        print(f"  {s.symbol}: {s.outcome} (exit={s.exit_code}, elapsed={s.elapsed_s:.0f}s)")
    print("═════════════════════════════════════")

    any_failed = any(s.outcome == "FAILED" for s in summary)
    if any_failed:
        print("❌ One or more symbols FAILED")
        return 1, summary
    return 0, summary


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    p.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS),
                   help="Comma-separated symbols (default: all 6 majors)")
    p.add_argument("--max-workers", type=int, default=6,
                   help="ProcessPoolExecutor workers (default 6)")
    p.add_argument("--eval-end-month", default=None,
                   help="Passed through to onboard_symbol.py")
    p.add_argument("--log-dir", default="/tmp/retrain_logs",
                   help="Per-symbol log directory")
    p.add_argument("--analysis-dir",
                   default="data/analysis/tick_opportunity_mining",
                   help="Where reduced_core_rolling/*.csv lives (for outcome classification)")
    args = p.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    exit_code, _ = run_orchestrator(
        symbols=symbols,
        max_workers=int(args.max_workers),
        eval_end_month=args.eval_end_month,
        log_dir=Path(args.log_dir),
        analysis_dir=Path(args.analysis_dir),
    )
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests — must pass**

```bash
uv run pytest tests/test_retrain_all_parallel.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Lint the new file**

```bash
uv run ruff check scripts/retrain_all_parallel.py tests/test_retrain_all_parallel.py
```

Expected: All checks passed (or apply `--fix`).

- [ ] **Step 6: Commit Task 4**

```bash
git add scripts/retrain_all_parallel.py tests/test_retrain_all_parallel.py
git commit -m "feat: parallel orchestrator for retrain-all (ProcessPoolExecutor)

New scripts/retrain_all_parallel.py replaces the Makefile's serial
for-loop with a ProcessPoolExecutor (default 6 workers, --max-workers
configurable). Per-symbol stdout/stderr captured to /tmp/retrain_logs
so concurrent workers do not interleave on the terminal.

Outcome classification happens in the parent via the existing
classify_outcome() Python function (imported, not invoked as a
subprocess). Final summary printed in REBUILD_SYMBOLS order regardless
of worker completion order. Exit code is 1 if any symbol FAILED.

Item 2 of docs/superpowers/specs/2026-05-21-mining-loop-performance-design.md.
Makefile wiring lives in Task 5.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 5: Makefile wiring + PR housekeeping

**Files:**
- Modify: `Makefile` — the `retrain-all` target body (lines 189-215)

The Makefile's `retrain-all` target replaces its serial loop with one call to the new orchestrator. The `clean-mining-outputs` precondition from PR #205 is preserved. The post-mining audit / docs-contract / mkdocs lines stay sequential because they depend on all symbols having finished.

- [ ] **Step 1: Read the current `retrain-all` body to confirm the slice you're replacing**

```bash
grep -nA 26 "^retrain-all:" Makefile | head -32
```

The body to replace is the multi-line `summary=""; failed=0; for sym in $(REBUILD_SYMBOLS); do ... done; ... exit 1; fi` block (lines 192-207 in the post-PR-#205 main). The `@if SKIP_CLEAN` clean line and the post-mining audit/docs-contract/mkdocs lines stay.

- [ ] **Step 2: Make the Makefile edit**

Replace the block exactly:

```make
retrain-all:
	@if [ -z "$(SKIP_CLEAN)" ]; then $(MAKE) clean-mining-outputs; else echo "SKIP_CLEAN set — keeping existing Stage 2-5 outputs"; fi
	@echo "══════════════════════════════════════════"
	@echo "  Retraining all symbols (Stages 2-5)    "
	@echo "══════════════════════════════════════════"
	uv run python scripts/retrain_all_parallel.py \
		--symbols "$(shell echo $(REBUILD_SYMBOLS) | sed 's/ /,/g')" \
		--max-workers $(or $(MAX_WORKERS),6) \
		$(if $(EVAL_END_MONTH),--eval-end-month $(EVAL_END_MONTH),)
	@echo "\n=== Running Stage-1 data reliability audit (all active symbols) ==="
	uv run python scripts/audit_data_reliability.py \
		--symbols $(shell echo $(REBUILD_SYMBOLS) | sed 's/ /,/g')
	@echo "\n=== Running docs-contract ==="
	$(MAKE) docs-contract
	@echo "\n=== Building mkdocs ==="
	uv run mkdocs build --strict
	@echo "\n✅ Full retrain complete"
```

- [ ] **Step 3: Dry-run the new target to verify the recipe is well-formed**

```bash
make -n retrain-all | head -20
```

Expected first lines:
```
if [ -z "" ]; then /Library/Developer/CommandLineTools/usr/bin/make clean-mining-outputs; else echo "SKIP_CLEAN set ..."; fi
echo "══════════════════════════════════════════"
echo "  Retraining all symbols (Stages 2-5)    "
echo "══════════════════════════════════════════"
uv run python scripts/retrain_all_parallel.py --symbols "EURUSD,GBPUSD,USDJPY,USDCHF,AUDUSD,USDCAD" --max-workers 6
```

- [ ] **Step 4: Update help text for retrain-all to mention --max-workers**

In the `help:` target (around line 752 in the post-PR-#205 main), update the `retrain-all` description:

```make
	@printf "  $(COLOR_TARGET)%-30s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "retrain-all" "Re-run ML pipeline + docs for all symbols, parallel across symbols (skip data; cleans Stage 2-5 first; MAX_WORKERS=N to cap)"
```

- [ ] **Step 5: Run a final integration smoke**

```bash
uv run pytest tests/test_retrain_all_parallel.py tests/test_mining_family.py tests/test_mining_random_baseline.py tests/test_oco_candidate_family_allowlist.py tests/test_tick_opportunity_mining.py tests/test_cross_symbol.py -q
```

Expected: all pass.

- [ ] **Step 6: Lint the Makefile-adjacent changes**

```bash
uv run ruff check scripts/retrain_all_parallel.py scripts/mining_family.py scripts/mining_random_baseline.py tests/
```

Expected: All checks passed.

- [ ] **Step 7: Commit Task 5**

```bash
git add Makefile
git commit -m "feat: retrain-all uses parallel orchestrator (Item 2 wiring)

Replaces the serial for-loop in the retrain-all recipe with one call
to scripts/retrain_all_parallel.py. Preserves the clean-mining-outputs
precondition from PR #205 and the sequential post-mining audit /
docs-contract / mkdocs stages. MAX_WORKERS env var supports capping
the worker count for memory-constrained machines.

Completes Item 2 of docs/superpowers/specs/2026-05-21-mining-loop-performance-design.md.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

- [ ] **Step 8: Push the branch and open a PR**

```bash
git push -u origin mining-perf-spec
gh pr create --title "perf: vectorise mining hot paths + parallelise retrain-all" \
  --body-file /tmp/pr-body-mining-perf.md
```

PR body (write to `/tmp/pr-body-mining-perf.md` first):

```markdown
## Summary

Implements docs/superpowers/specs/2026-05-21-mining-loop-performance-design.md — three independent perf items:

1. **Vectorise `DollarFactorResidualFamily._rolling_regression`** (Item 1a) — closed-form rolling OLS via pandas rolling sums. ≥50× perf gate.
2. **Vectorise `DispersionRankFamily._per_bar_rank_and_side`** (Item 1b) — one full-matrix `np.argsort`. ≥100× perf gate.
3. **Batched `random_entry_baseline`** (Item 3) — single `measure_gross` call across all draws. ≥5× perf gate.
4. **`scripts/retrain_all_parallel.py`** (Item 2) — `ProcessPoolExecutor` over symbols (default 6 workers, `MAX_WORKERS=N` env override).
5. **Makefile**: `retrain-all` body redirected to the new orchestrator.

Combined estimated wall-clock improvement on `make retrain-all`: 4–12× on a 6-core machine (hardware-dependent; not a CI gate).

## Why not Polars

See spec §"Why not Polars". TL;DR: the bottleneck is per-bar numpy work and a serial Python loop, not DataFrame ops. Polars migration would touch 1000+ lines for ~0–10% mining-loop speedup; this PR moves the needle 4–12× in ~150 net lines.

## PR #195 closeout

This PR's design supersedes PR #195's `precomputed=` protocol-change approach. Once this merges, please close #195 as superseded (or I can do it).

## Test plan

- [x] `uv run pytest tests/test_mining_family.py tests/test_mining_random_baseline.py tests/test_retrain_all_parallel.py tests/test_oco_candidate_family_allowlist.py tests/test_tick_opportunity_mining.py tests/test_cross_symbol.py -q` — green
- [x] `uv run ruff check` — clean
- [x] All three parity tests (rtol=1e-6 / bit-identical) pass against the loop references
- [x] All three perf gates (≥50×, ≥100×, ≥5×) pass; loop references kept in code with `_loop` suffix
- [ ] CI green
- [ ] Empirical: run `make retrain-all` end-to-end and compare per-family CSVs to a sequential-mode run for bit-identical output (same RNG seed)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
```

```bash
cat > /tmp/pr-body-mining-perf.md <<'EOF'
(paste body)
EOF
```

- [ ] **Step 9: Close PR #195 after this one merges**

```bash
gh pr close 195 --comment "Superseded by PR [INSERT-NUMBER-HERE]. The new design avoids the `precomputed=` protocol change and is broader in scope (parallelism + baseline batching + per-bar vectorisation). The perf draft on worktree-perf-mining-loop is preserved on the remote for history."
```

---

## Self-review checklist (run before handoff)

- [x] Spec coverage: Items 1a, 1b, 2, 3 each have at least one task with parity test + perf gate + commit. Spec §"Open Risks" σ² fallback noted in Task 1 Step 6 troubleshooting.
- [x] Placeholders: none. Every step has exact commands and code.
- [x] Type consistency: `WorkerResult` and `SymbolSummary` defined in Task 4 Step 3, used unchanged in Task 4 Step 1 tests and Task 5 Makefile recipe (just passed through). `classify_outcome` signature `(*, exit_code, schedule_csv)` confirmed against source.
- [x] No protocol changes to `MiningFamily` — all three items work within the current `measure_gross(frame, entries, params) -> ndarray` contract.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-21-mining-loop-performance.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration. Best for this plan because each task is parity-test-gated and independent.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
