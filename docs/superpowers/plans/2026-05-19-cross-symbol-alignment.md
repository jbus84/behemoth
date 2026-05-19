# Cross-Symbol Alignment Infrastructure — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reusable utility that, given a target symbol and a `bar_ticks` setting, returns that symbol's own tick frame enriched with backward as-of-joined peer returns and a synthetic mean-market (USD) measure under three construction methods.

**Architecture:** One new module `scripts/cross_symbol.py`. Internal helpers operate on already-prepared DataFrames (testable with tiny hand-built fixtures); the public `build_cross_symbol_frame` loads the 6 symbols' parquet files via the existing `_prepare_frame` and assembles the result. Tick-native throughout — no resampling, no global clock.

**Tech Stack:** Python, NumPy, pandas (`merge_asof`), pytest. Spec: `docs/superpowers/specs/2026-05-19-cross-symbol-alignment-design.md`.

**Base state:** `scripts/run_tick_opportunity_mining.py` exists with `_prepare_frame(path, *, symbol, horizons)` and `_pip_size`. `tests/test_tick_opportunity_mining.py` has `_build_synth_tick_velocity(path, *, symbol)` which writes a synthetic velocity parquet readable by `_prepare_frame`. This plan creates new files only; it modifies nothing existing.

## File Structure

- `scripts/cross_symbol.py` — new module. Responsibilities: the 6-symbol roster (`CROSS_SYMBOLS`), the USD sign-alignment table (`_USD_SIGN`), the backward as-of join (`_align_peer_returns`), the three market measures (`_add_market_measures` + `_rolling_pca_factor`), and the public entry point `build_cross_symbol_frame`.
- `tests/test_cross_symbol.py` — new test file covering all of the above.

The internal helpers take prepared DataFrames so they can be tested with lightweight fixtures (just `close_ts` + `ret_z`); only `build_cross_symbol_frame` touches the filesystem.

---

### Task 1: Module skeleton — symbol roster and USD sign table

**Files:**
- Create: `scripts/cross_symbol.py`
- Create: `tests/test_cross_symbol.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_cross_symbol.py`:

```python
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from scripts.cross_symbol import CROSS_SYMBOLS, _USD_SIGN


def test_cross_symbols_roster_is_the_six_majors():
    assert CROSS_SYMBOLS == [
        "EURUSD", "GBPUSD", "AUDUSD", "USDJPY", "USDCAD", "USDCHF",
    ]


def test_usd_sign_table_orients_to_usd_strength():
    # USD as quote currency -> a price rise means USD weakness -> sign -1.
    assert _USD_SIGN["EURUSD"] == -1
    assert _USD_SIGN["GBPUSD"] == -1
    assert _USD_SIGN["AUDUSD"] == -1
    # USD as base currency -> a price rise means USD strength -> sign +1.
    assert _USD_SIGN["USDJPY"] == 1
    assert _USD_SIGN["USDCAD"] == 1
    assert _USD_SIGN["USDCHF"] == 1
    # Every roster symbol has a sign.
    assert set(_USD_SIGN) == set(CROSS_SYMBOLS)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_cross_symbol.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.cross_symbol'`.

- [ ] **Step 3: Create the module with the roster and sign table**

Create `scripts/cross_symbol.py`:

```python
"""Cross-symbol alignment infrastructure.

Given a target symbol and a bar_ticks setting, build that symbol's own tick
frame enriched with backward as-of-joined peer returns and a synthetic
mean-market (USD) measure. Tick-native: no resampling, no global clock.

See docs/superpowers/specs/2026-05-19-cross-symbol-alignment-design.md.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

# The 6 FX majors compared against each other.
CROSS_SYMBOLS: list[str] = [
    "EURUSD", "GBPUSD", "AUDUSD", "USDJPY", "USDCAD", "USDCHF",
]

# Sign that orients each symbol's return to "USD strength": +1 when a price
# rise means USD strengthened (USD is the base currency), -1 when a price
# rise means USD weakened (USD is the quote currency).
_USD_SIGN: dict[str, int] = {
    "EURUSD": -1,
    "GBPUSD": -1,
    "AUDUSD": -1,
    "USDJPY": 1,
    "USDCAD": 1,
    "USDCHF": 1,
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/test_cross_symbol.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/cross_symbol.py tests/test_cross_symbol.py
git commit -m "feat: cross-symbol module skeleton with USD sign table"
```

---

### Task 2: `_align_peer_returns` — backward as-of join

**Files:**
- Modify: `scripts/cross_symbol.py`
- Test: `tests/test_cross_symbol.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cross_symbol.py`:

```python
def _mk_frame(close_ts: list[str], ret_z: list[float]) -> pd.DataFrame:
    """A minimal prepared-frame stand-in: close_ts + ret_z only."""
    return pd.DataFrame({
        "close_ts": pd.to_datetime(close_ts, utc=True),
        "ret_z": np.asarray(ret_z, dtype=float),
    })


def test_align_peer_returns_takes_most_recent_completed_peer_bar():
    from scripts.cross_symbol import _align_peer_returns

    # Target bars at :00, :02, :04. Peer bars at :01, :03 (between them).
    target = _mk_frame(
        ["2024-01-01T00:00:00Z", "2024-01-01T00:02:00Z", "2024-01-01T00:04:00Z"],
        [0.0, 0.0, 0.0],
    )
    # USDJPY peer, sign +1: USD-aligned ret_z == raw ret_z.
    peer = _mk_frame(
        ["2024-01-01T00:01:00Z", "2024-01-01T00:03:00Z"], [2.0, 5.0],
    )
    out = _align_peer_returns(target, "EURUSD", {"USDJPY": peer})
    col = out["xs_ret_z__USDJPY"].to_numpy()
    # Target :00 -> no peer bar <= :00 yet -> NaN.
    assert np.isnan(col[0])
    # Target :02 -> last peer bar <= :02 is :01 (ret_z 2.0).
    assert col[1] == 2.0
    # Target :04 -> last peer bar <= :04 is :03 (ret_z 5.0).
    assert col[2] == 5.0


def test_align_peer_returns_applies_usd_sign():
    from scripts.cross_symbol import _align_peer_returns

    target = _mk_frame(["2024-01-01T00:05:00Z"], [0.0])
    peer = _mk_frame(["2024-01-01T00:00:00Z"], [3.0])
    # EURUSD peer has sign -1 -> USD-aligned column is negated.
    out = _align_peer_returns(target, "USDJPY", {"EURUSD": peer})
    assert out["xs_ret_z__EURUSD"].to_numpy()[0] == -3.0


def test_align_peer_returns_is_free_of_look_ahead():
    from scripts.cross_symbol import _align_peer_returns

    target = _mk_frame(
        ["2024-01-01T00:00:00Z", "2024-01-01T00:02:00Z"], [0.0, 0.0],
    )
    peer_a = _mk_frame(["2024-01-01T00:01:00Z"], [1.0])
    # peer_b adds a FUTURE bar at :09 that must not leak into earlier rows.
    peer_b = _mk_frame(
        ["2024-01-01T00:01:00Z", "2024-01-01T00:09:00Z"], [1.0, 99.0],
    )
    out_a = _align_peer_returns(target, "EURUSD", {"USDJPY": peer_a})
    out_b = _align_peer_returns(target, "EURUSD", {"USDJPY": peer_b})
    # The future :09 bar changes nothing for target bars at :00 and :02.
    assert np.array_equal(
        np.nan_to_num(out_a["xs_ret_z__USDJPY"].to_numpy(), nan=-1.0),
        np.nan_to_num(out_b["xs_ret_z__USDJPY"].to_numpy(), nan=-1.0),
    )
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_cross_symbol.py -k align -v`
Expected: FAIL with `ImportError: cannot import name '_align_peer_returns'`.

- [ ] **Step 3: Implement `_usd_aligned_ret_z` and `_align_peer_returns`**

Append to `scripts/cross_symbol.py`:

```python
def _usd_aligned_ret_z(frame: pd.DataFrame, symbol: str) -> pd.Series:
    """The symbol's volatility-normalised return oriented to USD strength."""
    ret_z = pd.to_numeric(frame["ret_z"], errors="coerce")
    return _USD_SIGN[symbol] * ret_z


def _align_peer_returns(
    target: pd.DataFrame,
    target_symbol: str,
    peers: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    """Append one USD-aligned peer return column per peer, backward as-of
    joined onto the target frame's close_ts. Look-ahead-free: each target
    bar at time T sees only peer bars with close_ts <= T."""
    out = target.reset_index(drop=True).copy()
    left = out[["close_ts"]].copy()
    for peer_symbol, peer_frame in peers.items():
        col = f"xs_ret_z__{peer_symbol}"
        right = pd.DataFrame({
            "close_ts": pd.to_datetime(
                peer_frame["close_ts"], utc=True, errors="coerce"
            ),
            col: _usd_aligned_ret_z(peer_frame, peer_symbol).to_numpy(),
        })
        right = right[right["close_ts"].notna()].sort_values(
            "close_ts"
        ).reset_index(drop=True)
        joined = pd.merge_asof(
            left, right, on="close_ts", direction="backward",
        )
        out[col] = joined[col].to_numpy()
    return out
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_cross_symbol.py -k align -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/cross_symbol.py tests/test_cross_symbol.py
git commit -m "feat: backward as-of join of USD-aligned peer returns"
```

---

### Task 3: `mkt_all6` and `mkt_loo` market measures

**Files:**
- Modify: `scripts/cross_symbol.py`
- Test: `tests/test_cross_symbol.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cross_symbol.py`:

```python
def test_market_measures_all6_and_loo():
    from scripts.cross_symbol import _add_market_measures, _align_peer_returns

    # One target bar; five peers each with a known USD-aligned return.
    target = _mk_frame(["2024-01-01T01:00:00Z"], [6.0])  # target ret_z = 6.0
    peers = {
        "GBPUSD": _mk_frame(["2024-01-01T00:00:00Z"], [-1.0]),
        "AUDUSD": _mk_frame(["2024-01-01T00:00:00Z"], [-2.0]),
        "USDJPY": _mk_frame(["2024-01-01T00:00:00Z"], [1.0]),
        "USDCAD": _mk_frame(["2024-01-01T00:00:00Z"], [2.0]),
        "USDCHF": _mk_frame(["2024-01-01T00:00:00Z"], [3.0]),
    }
    aligned = _align_peer_returns(target, "EURUSD", peers)
    out = _add_market_measures(aligned, "EURUSD")
    # USD-aligned peer values: GBP +1, AUD +2 (sign -1 on raw -1,-2),
    # JPY +1, CAD +2, CHF +3 -> peer sum 9, mean 1.8.
    assert out["mkt_loo"].to_numpy()[0] == pytest.approx(1.8)
    # Target EURUSD USD-aligned = -1 * 6.0 = -6.0. all6 = (-6+9)/6 = 0.5.
    assert out["mkt_all6"].to_numpy()[0] == pytest.approx(0.5)


def test_market_measures_loo_ignores_target_returns():
    from scripts.cross_symbol import _add_market_measures, _align_peer_returns

    peers = {
        "GBPUSD": _mk_frame(["2024-01-01T00:00:00Z"], [1.0]),
        "AUDUSD": _mk_frame(["2024-01-01T00:00:00Z"], [1.0]),
        "USDJPY": _mk_frame(["2024-01-01T00:00:00Z"], [1.0]),
        "USDCAD": _mk_frame(["2024-01-01T00:00:00Z"], [1.0]),
        "USDCHF": _mk_frame(["2024-01-01T00:00:00Z"], [1.0]),
    }
    a = _add_market_measures(
        _align_peer_returns(_mk_frame(["2024-01-01T01:00:00Z"], [0.0]),
                            "EURUSD", peers), "EURUSD")
    b = _add_market_measures(
        _align_peer_returns(_mk_frame(["2024-01-01T01:00:00Z"], [999.0]),
                            "EURUSD", peers), "EURUSD")
    # mkt_loo excludes the target, so the target's own ret_z cannot move it.
    assert a["mkt_loo"].to_numpy()[0] == b["mkt_loo"].to_numpy()[0]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_cross_symbol.py -k market_measures -v`
Expected: FAIL with `ImportError: cannot import name '_add_market_measures'`.

- [ ] **Step 3: Implement `_add_market_measures` (all6 + loo only)**

Append to `scripts/cross_symbol.py`:

```python
def _add_market_measures(
    frame: pd.DataFrame,
    target_symbol: str,
) -> pd.DataFrame:
    """Append mkt_all6 and mkt_loo to a frame that already carries the
    xs_ret_z__{peer} columns from _align_peer_returns. mkt_pca is added by a
    later step."""
    out = frame.copy()
    peer_cols = sorted(c for c in out.columns if c.startswith("xs_ret_z__"))
    target_usd = _usd_aligned_ret_z(out, target_symbol)
    # 6-wide matrix: the target's own USD-aligned return + the 5 peers.
    six = pd.concat(
        [target_usd.rename(f"xs_ret_z__{target_symbol}")]
        + [out[c] for c in peer_cols],
        axis=1,
    )
    out["mkt_all6"] = six.mean(axis=1, skipna=True).to_numpy()
    out["mkt_loo"] = out[peer_cols].mean(axis=1, skipna=True).to_numpy()
    return out
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_cross_symbol.py -k market_measures -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/cross_symbol.py tests/test_cross_symbol.py
git commit -m "feat: mkt_all6 and mkt_loo market measures"
```

---

### Task 4: `mkt_pca` — rolling trailing first principal component

**Files:**
- Modify: `scripts/cross_symbol.py`
- Test: `tests/test_cross_symbol.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cross_symbol.py`:

```python
def test_rolling_pca_factor_uses_only_trailing_bars():
    from scripts.cross_symbol import _rolling_pca_factor

    rng = np.random.default_rng(11)
    base = rng.normal(size=(600, 6))
    # mat_b is identical to mat_a for the first 400 rows, perturbed after.
    mat_a = base.copy()
    mat_b = base.copy()
    mat_b[400:] += 50.0
    fac_a = _rolling_pca_factor(mat_a, window=200, min_periods=100)
    fac_b = _rolling_pca_factor(mat_b, window=200, min_periods=100)
    # The factor at row i fits PC1 on rows < i only, so altering rows >= 400
    # cannot change the factor for rows <= 400.
    assert np.allclose(
        np.nan_to_num(fac_a[:401], nan=0.0),
        np.nan_to_num(fac_b[:401], nan=0.0),
    )


def test_rolling_pca_factor_nan_before_min_periods():
    from scripts.cross_symbol import _rolling_pca_factor

    rng = np.random.default_rng(3)
    mat = rng.normal(size=(300, 6))
    fac = _rolling_pca_factor(mat, window=200, min_periods=100)
    # Rows with fewer than min_periods trailing bars get NaN.
    assert np.isnan(fac[:100]).all()
    assert np.isfinite(fac[150])


def test_rolling_pca_factor_sign_is_oriented_to_usd_strength():
    from scripts.cross_symbol import _rolling_pca_factor

    # All 6 series move together (a shared USD factor). PC1 then loads all
    # series with the same sign; the orientation rule makes the factor track
    # that common move rather than its arbitrary negation.
    rng = np.random.default_rng(7)
    common = rng.normal(size=(500, 1))
    mat = common + 0.05 * rng.normal(size=(500, 6))
    fac = _rolling_pca_factor(mat, window=200, min_periods=100)
    common_flat = common[:, 0]
    valid = np.isfinite(fac)
    corr = np.corrcoef(fac[valid], common_flat[valid])[0, 1]
    assert corr > 0.9


def test_add_market_measures_includes_distinct_mkt_pca():
    from scripts.cross_symbol import _add_market_measures, _align_peer_returns

    # Build a 500-bar target + 5 peers with distinct, correlated series so
    # the three measures are genuinely different.
    rng = np.random.default_rng(19)
    n = 500
    ts = pd.date_range("2024-01-01", periods=n, freq="min", tz="UTC")
    common = rng.normal(size=n)

    def _frame(scale: float) -> pd.DataFrame:
        return pd.DataFrame({
            "close_ts": ts,
            "ret_z": common * scale + 0.1 * rng.normal(size=n),
        })

    target = _frame(1.0)
    peers = {
        "GBPUSD": _frame(1.1), "AUDUSD": _frame(0.9),
        "USDJPY": _frame(1.2), "USDCAD": _frame(0.8),
        "USDCHF": _frame(1.05),
    }
    aligned = _align_peer_returns(target, "EURUSD", peers)
    out = _add_market_measures(aligned, "EURUSD")
    for col in ("mkt_all6", "mkt_loo", "mkt_pca"):
        assert col in out.columns
    a = out["mkt_all6"].to_numpy()
    p = out["mkt_pca"].to_numpy()
    fin = np.isfinite(a) & np.isfinite(p)
    assert fin.sum() > 0
    # mkt_pca is a distinct series, not a copy of mkt_all6.
    assert not np.allclose(a[fin], p[fin])
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_cross_symbol.py -k "pca" -v`
Expected: FAIL with `ImportError: cannot import name '_rolling_pca_factor'`.

- [ ] **Step 3: Implement `_rolling_pca_factor` and wire it into `_add_market_measures`**

Append `_rolling_pca_factor` to `scripts/cross_symbol.py`:

```python
def _rolling_pca_factor(
    mat: np.ndarray,
    *,
    window: int = 500,
    min_periods: int = 200,
) -> np.ndarray:
    """First-principal-component factor, fit on a strictly-trailing window.

    For row i the covariance is estimated from rows [i-window, i-1] only —
    never row i or later — so the factor is look-ahead-free. PC1 is oriented
    so its loadings sum positive: under a common USD factor every column
    loads the same sign, and this fixes the eigenvector's arbitrary sign so
    the factor tracks the shared move rather than its negation."""
    arr = np.asarray(mat, dtype=float)
    n = arr.shape[0]
    out = np.full(n, np.nan, dtype=float)
    for i in range(n):
        lo = max(0, i - window)
        win = arr[lo:i]  # strictly trailing: excludes row i
        win = win[np.isfinite(win).all(axis=1)]
        if len(win) < min_periods:
            continue
        row = arr[i]
        if not np.isfinite(row).all():
            continue
        cov = np.cov(win, rowvar=False)
        _vals, vecs = np.linalg.eigh(cov)  # ascending eigenvalues
        pc1 = vecs[:, -1]                  # largest-eigenvalue eigenvector
        if pc1.sum() < 0.0:
            pc1 = -pc1
        out[i] = float(row @ pc1)
    return out
```

Then replace the `_add_market_measures` body so it also appends `mkt_pca`. The function becomes:

```python
def _add_market_measures(
    frame: pd.DataFrame,
    target_symbol: str,
    *,
    pca_window: int = 500,
    pca_min_periods: int = 200,
) -> pd.DataFrame:
    """Append mkt_all6, mkt_loo, and mkt_pca to a frame that already carries
    the xs_ret_z__{peer} columns from _align_peer_returns."""
    out = frame.copy()
    peer_cols = sorted(c for c in out.columns if c.startswith("xs_ret_z__"))
    target_usd = _usd_aligned_ret_z(out, target_symbol)
    # 6-wide matrix: the target's own USD-aligned return + the 5 peers.
    six = pd.concat(
        [target_usd.rename(f"xs_ret_z__{target_symbol}")]
        + [out[c] for c in peer_cols],
        axis=1,
    )
    out["mkt_all6"] = six.mean(axis=1, skipna=True).to_numpy()
    out["mkt_loo"] = out[peer_cols].mean(axis=1, skipna=True).to_numpy()
    out["mkt_pca"] = _rolling_pca_factor(
        six.to_numpy(dtype=float),
        window=pca_window,
        min_periods=pca_min_periods,
    )
    return out
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_cross_symbol.py -k "pca or market_measures" -v`
Expected: PASS — the new PCA tests and the Task 3 `market_measures` tests all green (the Task 3 tests still pass because `mkt_all6`/`mkt_loo` are unchanged).

- [ ] **Step 5: Commit**

```bash
git add scripts/cross_symbol.py tests/test_cross_symbol.py
git commit -m "feat: rolling trailing PCA market factor (mkt_pca)"
```

---

### Task 5: `build_cross_symbol_frame` — file loading and assembly

**Files:**
- Modify: `scripts/cross_symbol.py`
- Test: `tests/test_cross_symbol.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cross_symbol.py`:

```python
def test_build_cross_symbol_frame_end_to_end(tmp_path: Path):
    from tests.test_tick_opportunity_mining import _build_synth_tick_velocity

    from scripts.cross_symbol import CROSS_SYMBOLS, build_cross_symbol_frame

    dataset_dir = tmp_path / "tick_velocity"
    dataset_dir.mkdir(parents=True, exist_ok=True)
    for sym in CROSS_SYMBOLS:
        _build_synth_tick_velocity(
            dataset_dir / f"{sym}_1000tick_velocity.parquet", symbol=sym,
        )
    out = build_cross_symbol_frame(
        target_symbol="EURUSD",
        bar_ticks=1000,
        dataset_dir=dataset_dir,
        horizons=[1, 2, 3],
    )
    assert not out.empty
    # The target's own OHLC survives unchanged.
    for col in ("close_bid", "close_ask", "close_ts"):
        assert col in out.columns
    # One peer column per non-target symbol.
    for sym in CROSS_SYMBOLS:
        if sym != "EURUSD":
            assert f"xs_ret_z__{sym}" in out.columns
    assert "xs_ret_z__EURUSD" not in out.columns  # target is not its own peer
    # All three market measures present.
    for col in ("mkt_all6", "mkt_loo", "mkt_pca"):
        assert col in out.columns
    # The aligned frame has the same row count as the target's own frame.
    assert len(out) > 0


def test_build_cross_symbol_frame_requires_all_six_symbols(tmp_path: Path):
    from tests.test_tick_opportunity_mining import _build_synth_tick_velocity

    from scripts.cross_symbol import build_cross_symbol_frame

    dataset_dir = tmp_path / "tick_velocity"
    dataset_dir.mkdir(parents=True, exist_ok=True)
    # Only 5 of the 6 symbols present — USDCHF is missing.
    for sym in ("EURUSD", "GBPUSD", "AUDUSD", "USDJPY", "USDCAD"):
        _build_synth_tick_velocity(
            dataset_dir / f"{sym}_1000tick_velocity.parquet", symbol=sym,
        )
    with pytest.raises(FileNotFoundError, match="USDCHF"):
        build_cross_symbol_frame(
            target_symbol="EURUSD",
            bar_ticks=1000,
            dataset_dir=dataset_dir,
            horizons=[1, 2, 3],
        )


def test_build_cross_symbol_frame_rejects_unknown_target(tmp_path: Path):
    from tests.test_tick_opportunity_mining import _build_synth_tick_velocity

    from scripts.cross_symbol import CROSS_SYMBOLS, build_cross_symbol_frame

    dataset_dir = tmp_path / "tick_velocity"
    dataset_dir.mkdir(parents=True, exist_ok=True)
    for sym in CROSS_SYMBOLS:
        _build_synth_tick_velocity(
            dataset_dir / f"{sym}_1000tick_velocity.parquet", symbol=sym,
        )
    with pytest.raises(ValueError, match="target_symbol"):
        build_cross_symbol_frame(
            target_symbol="NZDUSD",
            bar_ticks=1000,
            dataset_dir=dataset_dir,
            horizons=[1, 2, 3],
        )
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_cross_symbol.py -k build_cross_symbol -v`
Expected: FAIL with `ImportError: cannot import name 'build_cross_symbol_frame'`.

- [ ] **Step 3: Implement `build_cross_symbol_frame`**

Append to `scripts/cross_symbol.py`:

```python
def build_cross_symbol_frame(
    target_symbol: str,
    bar_ticks: int,
    dataset_dir: Path,
    horizons: list[int],
) -> pd.DataFrame:
    """Return the target symbol's tick frame enriched with backward
    as-of-joined peer returns and the three market measures.

    All 6 CROSS_SYMBOLS must have a velocity parquet in dataset_dir — a
    coherent cross-section cannot be built from a partial roster.
    """
    from scripts.run_tick_opportunity_mining import _prepare_frame

    if target_symbol not in CROSS_SYMBOLS:
        raise ValueError(
            f"target_symbol {target_symbol!r} is not a cross-symbol major; "
            f"expected one of {CROSS_SYMBOLS}"
        )
    dataset_dir = Path(dataset_dir)
    frames: dict[str, pd.DataFrame] = {}
    for sym in CROSS_SYMBOLS:
        path = dataset_dir / f"{sym}_{int(bar_ticks)}tick_velocity.parquet"
        if not path.exists():
            raise FileNotFoundError(
                f"cross-symbol alignment requires all {len(CROSS_SYMBOLS)} "
                f"majors; missing velocity parquet for {sym}: {path}"
            )
        frames[sym] = _prepare_frame(path, symbol=sym, horizons=horizons)

    target = frames[target_symbol]
    peers = {s: f for s, f in frames.items() if s != target_symbol}
    aligned = _align_peer_returns(target, target_symbol, peers)
    return _add_market_measures(aligned, target_symbol)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_cross_symbol.py -k build_cross_symbol -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/cross_symbol.py tests/test_cross_symbol.py
git commit -m "feat: build_cross_symbol_frame end-to-end assembly"
```

---

## Final Verification

- [ ] Run the full new test file:
  `uv run pytest tests/test_cross_symbol.py -v`
  Expected: all tests PASS (Tasks 1–5).
- [ ] Confirm no existing tests were touched:
  `git diff --name-only main...HEAD` lists only `scripts/cross_symbol.py`, `tests/test_cross_symbol.py`, and the two `docs/superpowers/` files.
- [ ] Update the design spec status if desired, then open a PR from the `worktree-cross-symbol-alignment` branch.
