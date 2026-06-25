# FX Cluster Regimes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a causal UMAP+HDBSCAN pipeline that discovers recurring `(pair, time)` situations in the FX dollar complex and runs a single-split kill-test for an out-of-sample, cost-net, vol-scaled triple-barrier edge at the multi-hour-to-1-day horizon.

**Architecture:** A new `scripts/fx_cluster/` package of single-purpose modules: honest hourly bars from raw ticks → causal pair-normalized features → train-only UMAP embedding → HDBSCAN clusters (OOS via `approximate_predict`) → vol-scaled triple-barrier labels → per-cluster scoring (block bootstrap, persistence filter, BH-FDR) → kill-test orchestrator that writes a GO/NO-GO report. Every statistic is causal (data ≤ t); the embedding and clusters are fit on train only.

**Tech Stack:** Python, polars, numpy, scipy, `umap-learn`, `hdbscan`, pytest. Spec: `docs/superpowers/specs/2026-06-16-fx-cluster-regimes-design.md`.

---

## Conventions (apply to every task)

- Package: `scripts/fx_cluster/`. Tests: `tests/fx_cluster/`. Both get an `__init__.py`.
- Every module starts with `from __future__ import annotations`.
- Run a single test: `uv run pytest tests/fx_cluster/test_X.py::test_name -v`
- Run the package tests: `uv run pytest tests/fx_cluster/ -q`
- Before any "final" commit run the repo gate: `make quality` then `uv run pytest tests/fx_cluster/ -q`.
- Constants live in `scripts/fx_cluster/config.py` (Task 1) and are imported everywhere — never re-literal them.

---

## File Structure

| File | Responsibility |
|---|---|
| `scripts/fx_cluster/config.py` | Shared constants: pairs, pool, paths, freq, barrier/cost/embedding params, USD orientation signs. |
| `scripts/fx_cluster/bars.py` | Honest hourly bars from raw ticks (last tick per boundary + intrabar mid high/low). |
| `scripts/fx_cluster/factor.py` | USD-oriented returns, equal-weighted dollar factor, residuals. |
| `scripts/fx_cluster/causal.py` | Causal rolling utilities: EWMA vol, causal z-score, rolling min/max — no look-ahead. |
| `scripts/fx_cluster/features.py` | Assemble the `(pair, t)` feature matrix (temporal + spatial + regime), pair-normalized. |
| `scripts/fx_cluster/labels.py` | Vol-scaled symmetric triple-barrier outcomes: net long/short return, MFE, MAE, hold, exit reason. |
| `scripts/fx_cluster/embed.py` | Thin causal UMAP wrapper (`fit` / `transform`). |
| `scripts/fx_cluster/cluster.py` | Thin HDBSCAN wrapper (`fit` / `predict` via `approximate_predict`). |
| `scripts/fx_cluster/score.py` | Per-cluster scoring, block bootstrap, persistence filter, direction, selection, BH-FDR. |
| `scripts/fx_cluster/killtest.py` | Orchestrator: split, fit-on-train, assign-test, simulate, write GO/NO-GO report. |

---

## Task 1: Package scaffold, dependencies, and config

**Files:**
- Create: `scripts/fx_cluster/__init__.py`, `tests/fx_cluster/__init__.py`
- Create: `scripts/fx_cluster/config.py`
- Create: `tests/fx_cluster/test_config.py`
- Modify: `pyproject.toml` (add deps)

- [ ] **Step 1: Add dependencies**

Run:
```bash
uv add umap-learn hdbscan
```
Expected: `pyproject.toml` gains `umap-learn` and `hdbscan`; `uv.lock` updates; install succeeds.

- [ ] **Step 2: Create package + test `__init__.py` files**

```bash
mkdir -p scripts/fx_cluster tests/fx_cluster
touch scripts/fx_cluster/__init__.py tests/fx_cluster/__init__.py
```

- [ ] **Step 3: Write the failing test for config invariants**

Create `tests/fx_cluster/test_config.py`:
```python
from scripts.fx_cluster import config


def test_pool_excludes_jpy_by_default():
    assert "USDJPY" in config.PAIRS
    assert "USDJPY" not in config.POOL_PAIRS
    assert set(config.POOL_PAIRS) == set(config.PAIRS) - {"USDJPY"}


def test_usd_signs_cover_all_pairs_and_are_unit():
    assert set(config.USD_SIGN) == set(config.PAIRS)
    assert all(v in (-1.0, 1.0) for v in config.USD_SIGN.values())
    # USD is the quote ccy in EURUSD/GBPUSD/AUDUSD -> USD up = pair down -> -1
    assert config.USD_SIGN["EURUSD"] == -1.0
    # USD is the base ccy in USDJPY/USDCHF/USDCAD -> USD up = pair up -> +1
    assert config.USD_SIGN["USDJPY"] == 1.0


def test_split_dates_ordered():
    assert config.TRAIN_START < config.TRAIN_END <= config.TEST_START < config.TEST_END
```

- [ ] **Step 4: Run test to verify it fails**

Run: `uv run pytest tests/fx_cluster/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: scripts.fx_cluster.config`.

- [ ] **Step 5: Create `scripts/fx_cluster/config.py`**

```python
from __future__ import annotations

from datetime import datetime

# Raw tick source (dukascopy monthly parquets: cols timestamp, bid, ask, mid, spread).
TICK_SRC = "/Users/danielfisher/Desktop/dukascopy_ticks"
BAR_DIR = "data/tick_bars"
REPORT_PATH = "docs/analysis/fx_cluster_killtest_report.md"

PAIRS: list[str] = ["EURUSD", "GBPUSD", "AUDUSD", "USDCHF", "USDCAD", "USDJPY"]
# USDJPY held out of the pooled fit by default (behaves differently; spec section 4.4).
POOL_PAIRS: list[str] = [p for p in PAIRS if p != "USDJPY"]

# Sign that maps a pair's log return to a USD-strength ("dollar") return.
# USD is the QUOTE ccy (XXXUSD): USD up => pair down => -1.
# USD is the BASE ccy (USDXXX): USD up => pair up => +1.
USD_SIGN: dict[str, float] = {
    "EURUSD": -1.0, "GBPUSD": -1.0, "AUDUSD": -1.0,
    "USDJPY": 1.0, "USDCHF": 1.0, "USDCAD": 1.0,
}

FREQ = "1h"  # honest hourly base grid

# Triple-barrier (spec section 5). Barrier = K_BARRIER * sigma_bar * sqrt(TARGET_H).
EWMA_LAMBDA = 0.94          # causal vol smoother
K_BARRIER = 1.0             # barrier width in horizon-vol units
TARGET_H = 8               # horizon scaling (bars) for the barrier size
PATIENCE_BARS = 24          # vertical barrier (~1 trading day of hourly bars)

# Cost (spec section 5.2): cross full quoted spread once (RT taker, referenced to mid)
# plus flat cTrader-Razor commission. In basis points.
COMMISSION_BPS_RT = 0.6
SPREAD_STRESS = 1.5         # report sensitivity: net at +50% spread

# Embedding / clustering (spec section 3).
UMAP_N_COMPONENTS = 8
UMAP_N_NEIGHBORS = 30
UMAP_MIN_DIST = 0.0
HDBSCAN_MIN_CLUSTER_SIZE = 400
HDBSCAN_MIN_SAMPLES = 20
RANDOM_SEED = 17

# Scoring (spec section 6).
BOOTSTRAP_BLOCKS = 5000     # time-block bootstrap resamples
BLOCK_DAYS = 5              # block length for the bootstrap
FDR_ALPHA = 0.10
SELECT_MARGIN_BPS = 0.2     # train net edge must beat cost floor by this margin
PERSIST_MIN_MFE_MAE = 1.5   # winning-side MFE/|MAE| floor
PERSIST_MIN_HOLD_BARS = 3   # median hold-time floor

# Kill-test split (spec section 6.1).
TRAIN_START = datetime(2018, 1, 1)
TRAIN_END = datetime(2024, 1, 1)
TEST_START = datetime(2024, 1, 1)
TEST_END = datetime(2026, 6, 1)
```

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/fx_cluster/test_config.py -v`
Expected: PASS (3 tests).

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml uv.lock scripts/fx_cluster/__init__.py tests/fx_cluster/__init__.py scripts/fx_cluster/config.py tests/fx_cluster/test_config.py
git commit -m "feat(fx_cluster): package scaffold, deps (umap/hdbscan), config constants"
```

---

## Task 2: Honest hourly bars (`bars.py`)

Builds time bars from raw ticks: last tick per boundary (no tick-count resampling) plus
intrabar mid high/low so the triple-barrier can detect touches honestly.

**Files:**
- Create: `scripts/fx_cluster/bars.py`
- Create: `tests/fx_cluster/test_bars.py`

- [ ] **Step 1: Write the failing test**

Create `tests/fx_cluster/test_bars.py`:
```python
from datetime import datetime

import polars as pl

from scripts.fx_cluster.bars import aggregate_bars


def _ticks():
    # Two hourly buckets; second bucket has a high spike and a low dip between open/close.
    return pl.DataFrame(
        {
            "timestamp": [
                datetime(2020, 1, 1, 0, 5),
                datetime(2020, 1, 1, 0, 55),
                datetime(2020, 1, 1, 1, 1),   # bucket 1 open
                datetime(2020, 1, 1, 1, 20),  # high
                datetime(2020, 1, 1, 1, 40),  # low
                datetime(2020, 1, 1, 1, 59),  # close
            ],
            "bid": [1.0000, 1.0010, 1.0020, 1.0090, 0.9950, 1.0030],
            "ask": [1.0002, 1.0012, 1.0022, 1.0092, 0.9952, 1.0032],
            "mid": [1.0001, 1.0011, 1.0021, 1.0091, 0.9951, 1.0031],
        }
    )


def test_aggregate_bars_uses_last_tick_per_bucket():
    out = aggregate_bars(_ticks(), "1h").sort("bucket")
    assert out.height == 2
    row0 = out.row(0, named=True)
    # last tick of bucket 0 is the 00:55 tick
    assert row0["mid"] == 1.0011
    assert row0["bid"] == 1.0010
    assert row0["ask"] == 1.0012
    assert row0["bucket"] == datetime(2020, 1, 1, 0, 0)


def test_aggregate_bars_captures_intrabar_high_low():
    out = aggregate_bars(_ticks(), "1h").sort("bucket")
    row1 = out.row(1, named=True)
    assert row1["mid"] == 1.0031          # close = last tick
    assert row1["mid_high"] == 1.0091     # the 01:20 spike
    assert row1["mid_low"] == 0.9951      # the 01:40 dip
    assert row1["n_ticks"] == 4
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/fx_cluster/test_bars.py -v`
Expected: FAIL with `ModuleNotFoundError: scripts.fx_cluster.bars`.

- [ ] **Step 3: Implement `scripts/fx_cluster/bars.py`**

```python
"""Honest time bars from raw dukascopy ticks.

Last *tick* before each boundary (never a tick-count resample, which leaves a
~half-bar-stale close and manufactures reversion), plus intrabar mid high/low so
the triple-barrier in labels.py can detect touches without look-ahead.
Cache: data/tick_bars/{sym}_{freq}_cluster.parquet.

Usage: python scripts/fx_cluster/bars.py        # builds hourly bars, all pairs
"""

from __future__ import annotations

import argparse
import glob
import os

import polars as pl

from scripts.fx_cluster import config


def aggregate_bars(ticks: pl.DataFrame, freq: str) -> pl.DataFrame:
    """One bar per freq bucket: last bid/ask/mid + intrabar mid high/low + tick count."""
    return (
        ticks.sort("timestamp")
        .group_by(pl.col("timestamp").dt.truncate(freq).alias("bucket"))
        .agg(
            pl.col("bid").last().alias("bid"),
            pl.col("ask").last().alias("ask"),
            pl.col("mid").last().alias("mid"),
            pl.col("mid").max().alias("mid_high"),
            pl.col("mid").min().alias("mid_low"),
            pl.len().alias("n_ticks"),
        )
    )


def build(sym: str, freq: str = config.FREQ) -> pl.DataFrame:
    files = sorted(glob.glob(f"{config.TICK_SRC}/{sym}/*_ticks.parquet"))
    if not files:
        raise FileNotFoundError(f"no tick files for {sym} under {config.TICK_SRC}")
    parts = [
        aggregate_bars(
            pl.scan_parquet(f).select("timestamp", "bid", "ask", "mid").collect(), freq
        )
        for f in files
    ]
    return pl.concat(parts).sort("bucket").unique(subset="bucket", keep="last")


def load_bars(sym: str, freq: str = config.FREQ) -> pl.DataFrame:
    return pl.read_parquet(f"{config.BAR_DIR}/{sym}_{freq}_cluster.parquet")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build honest cluster bars from raw ticks.")
    parser.add_argument("--freq", default=config.FREQ)
    args = parser.parse_args()
    os.makedirs(config.BAR_DIR, exist_ok=True)
    for sym in config.PAIRS:
        df = build(sym, args.freq)
        path = f"{config.BAR_DIR}/{sym}_{args.freq}_cluster.parquet"
        df.write_parquet(path)
        print(f"{sym} {args.freq}: {df.height} bars  {df['bucket'].min()} -> {df['bucket'].max()}  -> {path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/fx_cluster/test_bars.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Build the real bars (data step, not a test)**

Run: `uv run python scripts/fx_cluster/bars.py`
Expected: 6 lines printed, one per pair, each ~46k hourly bars spanning 2018→2026; parquets written to `data/tick_bars/{sym}_1h_cluster.parquet`.

- [ ] **Step 6: Commit**

```bash
git add scripts/fx_cluster/bars.py tests/fx_cluster/test_bars.py
git commit -m "feat(fx_cluster): honest hourly bars from raw ticks with intrabar high/low"
```

---

## Task 3: Causal utilities (`causal.py`)

The look-ahead-critical primitives, isolated and property-tested.

**Files:**
- Create: `scripts/fx_cluster/causal.py`
- Create: `tests/fx_cluster/test_causal.py`

- [ ] **Step 1: Write the failing test**

Create `tests/fx_cluster/test_causal.py`:
```python
import numpy as np

from scripts.fx_cluster.causal import causal_zscore, ewma_vol, rolling_minmax_pos


def test_ewma_vol_is_causal_and_positive():
    x = np.array([0.0, 0.01, -0.02, 0.03, -0.01])
    v = ewma_vol(x, lam=0.94)
    assert v.shape == x.shape
    assert v[0] == 0.0  # no history yet
    assert np.all(v[1:] > 0.0)
    # changing a FUTURE value must not change an earlier vol estimate (no look-ahead)
    x2 = x.copy()
    x2[-1] = 99.0
    v2 = ewma_vol(x2, lam=0.94)
    assert np.allclose(v[:-1], v2[:-1])


def test_causal_zscore_no_lookahead():
    x = np.arange(10, dtype=float)
    z = causal_zscore(x, window=4)
    x2 = x.copy()
    x2[7:] = -50.0
    z2 = causal_zscore(x2, window=4)
    assert np.allclose(z[:7], z2[:7], equal_nan=True)


def test_rolling_minmax_pos_bounds():
    x = np.array([1.0, 2.0, 3.0, 2.0, 1.0, 5.0])
    p = rolling_minmax_pos(x, window=3)
    assert np.nanmin(p) >= 0.0 and np.nanmax(p) <= 1.0
    # last point is the window max -> pos == 1.0 (window = {1,5} over [1,1,5])
    assert p[-1] == 1.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/fx_cluster/test_causal.py -v`
Expected: FAIL with `ModuleNotFoundError: scripts.fx_cluster.causal`.

- [ ] **Step 3: Implement `scripts/fx_cluster/causal.py`**

```python
"""Causal rolling primitives. Every output at index i uses only x[:i+1]."""

from __future__ import annotations

import numpy as np


def ewma_vol(x: np.ndarray, lam: float) -> np.ndarray:
    """Causal EWMA volatility of x. var_i = lam*var_{i-1} + (1-lam)*x_i^2; vol_0 = 0."""
    x = np.asarray(x, dtype=float)
    var = np.zeros_like(x)
    for i in range(1, len(x)):
        var[i] = lam * var[i - 1] + (1.0 - lam) * x[i - 1] ** 2
    return np.sqrt(var)


def causal_zscore(x: np.ndarray, window: int) -> np.ndarray:
    """Trailing-window z-score: (x_i - mean(x[i-window+1:i+1])) / std(...). NaN until full."""
    x = np.asarray(x, dtype=float)
    out = np.full_like(x, np.nan)
    for i in range(window - 1, len(x)):
        w = x[i - window + 1 : i + 1]
        sd = w.std()
        out[i] = 0.0 if sd == 0 else (x[i] - w.mean()) / sd
    return out


def rolling_minmax_pos(x: np.ndarray, window: int) -> np.ndarray:
    """Position of x_i within its trailing window: (x_i - min) / (max - min) in [0, 1]."""
    x = np.asarray(x, dtype=float)
    out = np.full_like(x, np.nan)
    for i in range(window - 1, len(x)):
        w = x[i - window + 1 : i + 1]
        lo, hi = w.min(), w.max()
        out[i] = 0.5 if hi == lo else (x[i] - lo) / (hi - lo)
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/fx_cluster/test_causal.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/fx_cluster/causal.py tests/fx_cluster/test_causal.py
git commit -m "feat(fx_cluster): causal rolling primitives (ewma vol, zscore, minmax pos)"
```

---

## Task 4: USD factor and residuals (`factor.py`)

**Files:**
- Create: `scripts/fx_cluster/factor.py`
- Create: `tests/fx_cluster/test_factor.py`

- [ ] **Step 1: Write the failing test**

Create `tests/fx_cluster/test_factor.py`:
```python
import numpy as np

from scripts.fx_cluster.factor import dollar_factor, oriented_returns, residuals


def test_oriented_returns_sign_convention():
    # EURUSD up by 1% => USD weaker => oriented (USD-strength) return negative.
    logret = {"EURUSD": np.array([0.01]), "USDJPY": np.array([0.01])}
    o = oriented_returns(logret)
    assert o["EURUSD"][0] < 0       # -1 sign
    assert o["USDJPY"][0] > 0       # +1 sign


def test_dollar_factor_is_equal_weighted_mean():
    o = {"A": np.array([0.02]), "B": np.array([0.04]), "C": np.array([-0.06])}
    f = dollar_factor(o)
    assert np.isclose(f[0], (0.02 + 0.04 - 0.06) / 3)


def test_residual_removes_common_factor():
    o = {"A": np.array([0.02]), "B": np.array([0.04]), "C": np.array([-0.06])}
    res = residuals(o)
    f = dollar_factor(o)
    assert np.isclose(res["A"][0], o["A"][0] - f[0])
    # residuals sum to ~0 across the cross-section (factor is the mean)
    assert np.isclose(sum(r[0] for r in res.values()), 0.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/fx_cluster/test_factor.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `scripts/fx_cluster/factor.py`**

```python
"""Equal-weighted USD ("dollar") factor and per-pair residuals.

EW dollar factor == PC1 of the majors at ~0.997 in prior work, so no estimation
and no look-ahead. Residual = a pair's USD-oriented return minus the factor.
"""

from __future__ import annotations

import numpy as np

from scripts.fx_cluster import config


def oriented_returns(logret: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    """Map each pair's log return to a USD-strength return via config.USD_SIGN."""
    return {p: config.USD_SIGN.get(p, 1.0) * r for p, r in logret.items()}


def dollar_factor(oriented: dict[str, np.ndarray]) -> np.ndarray:
    """Equal-weighted mean of the oriented returns across the cross-section."""
    stack = np.vstack([oriented[p] for p in oriented])
    return stack.mean(axis=0)


def residuals(oriented: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    """Each pair's oriented return minus the equal-weighted dollar factor."""
    f = dollar_factor(oriented)
    return {p: oriented[p] - f for p in oriented}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/fx_cluster/test_factor.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/fx_cluster/factor.py tests/fx_cluster/test_factor.py
git commit -m "feat(fx_cluster): USD-oriented returns, EW dollar factor, residuals"
```

---

## Task 5: Triple-barrier labels (`labels.py`)

Vol-scaled symmetric triple-barrier per `(pair, t)`. The correctness-critical unit;
tested with hand-built paths covering target-hit, stop-hit, patience-timeout, and the
conservative same-bar ambiguity rule.

**Files:**
- Create: `scripts/fx_cluster/labels.py`
- Create: `tests/fx_cluster/test_labels.py`

- [ ] **Step 1: Write the failing test**

Create `tests/fx_cluster/test_labels.py`:
```python
import numpy as np

from scripts.fx_cluster.labels import barrier_outcome


def test_long_target_hit_before_stop():
    # flat then a jump up that crosses +target at bar 2.
    mid = np.array([100.0, 100.0, 100.0, 100.0])
    hi = np.array([100.0, 100.05, 102.0, 100.0])
    lo = np.array([100.0, 99.95, 100.0, 100.0])
    out = barrier_outcome(mid, hi, lo, i=0, target=1.0, patience=3, side=+1)
    assert out["exit_reason"] == "target"
    assert out["hold_bars"] == 2
    assert out["mfe"] >= 1.0          # reached at least +target
    assert out["gross"] > 0


def test_long_stop_hit():
    mid = np.array([100.0, 100.0, 100.0])
    hi = np.array([100.0, 100.1, 100.1])
    lo = np.array([100.0, 98.0, 100.0])   # crosses -target at bar 1
    out = barrier_outcome(mid, hi, lo, i=0, target=1.0, patience=2, side=+1)
    assert out["exit_reason"] == "stop"
    assert out["gross"] < 0


def test_patience_timeout_exits_at_last_close():
    mid = np.array([100.0, 100.2, 100.3, 100.25])
    hi = mid.copy()
    lo = mid.copy()
    out = barrier_outcome(mid, hi, lo, i=0, target=5.0, patience=3, side=+1)
    assert out["exit_reason"] == "timeout"
    assert out["hold_bars"] == 3
    assert np.isclose(out["gross"], 100.25 - 100.0)


def test_same_bar_ambiguity_is_conservative_stop_first():
    # bar 1 touches BOTH +target and -target -> must resolve as stop.
    mid = np.array([100.0, 100.0])
    hi = np.array([100.0, 102.0])
    lo = np.array([100.0, 98.0])
    out = barrier_outcome(mid, hi, lo, i=0, target=1.0, patience=1, side=+1)
    assert out["exit_reason"] == "stop"


def test_short_side_mirrors_long():
    mid = np.array([100.0, 100.0, 100.0])
    hi = np.array([100.0, 100.1, 100.1])
    lo = np.array([100.0, 99.95, 98.0])   # price falls -> good for a short
    out = barrier_outcome(mid, hi, lo, i=0, target=1.0, patience=2, side=-1)
    assert out["exit_reason"] == "target"
    assert out["gross"] > 0               # short profits from the fall
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/fx_cluster/test_labels.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `scripts/fx_cluster/labels.py`**

```python
"""Vol-scaled symmetric triple-barrier outcomes.

For each point (pair, t): a profit barrier at +target and a stop at -target (in
price units), evaluated for a given side (+1 long / -1 short) over <= patience
forward bars, using intrabar mid high/low for touch detection. Same-bar
ambiguity (both barriers inside one bar) resolves CONSERVATIVELY as the stop.
The gross return is in log-units; cost is applied later in build_labels.
"""

from __future__ import annotations

import math

import numpy as np
import polars as pl

from scripts.fx_cluster import config
from scripts.fx_cluster.causal import ewma_vol


def barrier_outcome(mid: np.ndarray, hi: np.ndarray, lo: np.ndarray,
                    i: int, target: float, patience: int, side: int) -> dict:
    """First-touch outcome for an entry at index i. Returns gross (log), mfe, mae,
    hold_bars, exit_reason in {"target","stop","timeout"}. target is in price units."""
    entry = mid[i]
    up = entry + target           # profit for long / stop for short
    dn = entry - target           # stop for long / profit for short
    mfe = mae = 0.0
    n = len(mid)
    last = min(i + patience, n - 1)
    for j in range(i + 1, last + 1):
        # running favourable/adverse excursion (signed by side), in log units
        fav = side * math.log(hi[j] / entry) if side > 0 else side * math.log(lo[j] / entry)
        adv = side * math.log(lo[j] / entry) if side > 0 else side * math.log(hi[j] / entry)
        mfe = max(mfe, fav)
        mae = min(mae, adv)
        hit_up = hi[j] >= up
        hit_dn = lo[j] <= dn
        target_hit = hit_up if side > 0 else hit_dn
        stop_hit = hit_dn if side > 0 else hit_up
        if stop_hit:  # conservative: stop wins same-bar ties
            return {"gross": side * math.log(dn / entry) if side > 0 else side * math.log(up / entry),
                    "mfe": mfe, "mae": mae, "hold_bars": j - i, "exit_reason": "stop"}
        if target_hit:
            return {"gross": side * math.log(up / entry) if side > 0 else side * math.log(dn / entry),
                    "mfe": mfe, "mae": mae, "hold_bars": j - i, "exit_reason": "target"}
    return {"gross": side * math.log(mid[last] / entry), "mfe": mfe, "mae": mae,
            "hold_bars": last - i, "exit_reason": "timeout"}


def build_labels(bars: pl.DataFrame) -> pl.DataFrame:
    """Per-bar triple-barrier outcomes for BOTH sides, net of cost. bars must have
    columns bucket, mid, mid_high, mid_low, bid, ask sorted by bucket."""
    mid = bars["mid"].to_numpy()
    hi = bars["mid_high"].to_numpy()
    lo = bars["mid_low"].to_numpy()
    logret = np.diff(np.log(mid), prepend=np.log(mid[0]))
    sigma = ewma_vol(logret, config.EWMA_LAMBDA)
    spread_bps = ((bars["ask"] - bars["bid"]) / bars["mid"]).to_numpy() * 1e4
    cost_bps = spread_bps + config.COMMISSION_BPS_RT

    rows = []
    n = len(mid)
    for i in range(n):
        target_price = mid[i] * config.K_BARRIER * sigma[i] * math.sqrt(config.TARGET_H)
        rec = {"row": i}
        if target_price <= 0:  # no vol estimate yet -> skip (NaN net)
            rec.update(ret_long=np.nan, ret_short=np.nan, mfe=np.nan, mae=np.nan,
                       hold_bars=0, exit_long="none", exit_short="none")
            rows.append(rec)
            continue
        long_o = barrier_outcome(mid, hi, lo, i, target_price, config.PATIENCE_BARS, +1)
        short_o = barrier_outcome(mid, hi, lo, i, target_price, config.PATIENCE_BARS, -1)
        rec.update(
            ret_long=long_o["gross"] * 1e4 - cost_bps[i],
            ret_short=short_o["gross"] * 1e4 - cost_bps[i],
            mfe=long_o["mfe"] * 1e4, mae=long_o["mae"] * 1e4,
            hold_bars=long_o["hold_bars"],
            exit_long=long_o["exit_reason"], exit_short=short_o["exit_reason"],
        )
        rows.append(rec)
    return bars.with_row_index("row").join(pl.DataFrame(rows), on="row", how="left")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/fx_cluster/test_labels.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/fx_cluster/labels.py tests/fx_cluster/test_labels.py
git commit -m "feat(fx_cluster): vol-scaled symmetric triple-barrier labels (net of cost)"
```

---

## Task 6: Feature matrix (`features.py`)

Assembles the `(pair, t)` causal, pair-normalized feature matrix from the per-pair bars.
Joins pairs on a common time index for the spatial (cross-currency) block.

**Files:**
- Create: `scripts/fx_cluster/features.py`
- Create: `tests/fx_cluster/test_features.py`

- [ ] **Step 1: Write the failing test**

Create `tests/fx_cluster/test_features.py`:
```python
from datetime import datetime, timedelta

import numpy as np
import polars as pl

from scripts.fx_cluster.features import build_features


def _synth_bars(seed: int) -> pl.DataFrame:
    rng = np.random.default_rng(seed)
    n = 600
    t0 = datetime(2020, 1, 1)
    mid = 1.0 + np.cumsum(rng.normal(0, 1e-4, n))
    return pl.DataFrame(
        {
            "bucket": [t0 + timedelta(hours=i) for i in range(n)],
            "mid": mid,
            "mid_high": mid + 1e-4,
            "mid_low": mid - 1e-4,
            "bid": mid - 5e-5,
            "ask": mid + 5e-5,
            "n_ticks": rng.integers(50, 200, n),
        }
    )


def test_build_features_shape_and_no_nan_tail():
    bars = {p: _synth_bars(i) for i, p in enumerate(["EURUSD", "GBPUSD", "AUDUSD"])}
    feats, names = build_features(bars)
    assert "pair" in feats.columns and "bucket" in feats.columns
    assert len(names) >= 15
    # after warmup there should be complete rows for every pair
    tail = feats.drop_nulls()
    assert set(tail["pair"].unique()) == {"EURUSD", "GBPUSD", "AUDUSD"}
    assert tail.height > 0


def test_features_are_causal():
    # mutating the FINAL bar must not change any earlier feature row
    base = {p: _synth_bars(i) for i, p in enumerate(["EURUSD", "GBPUSD", "AUDUSD"])}
    feats_a, names = build_features(base)
    bumped = {p: df.clone() for p, df in base.items()}
    df = bumped["EURUSD"]
    last = df.height - 1
    bumped["EURUSD"] = df.with_columns(
        pl.when(pl.arange(0, df.height) == last).then(pl.col("mid") * 1.05)
        .otherwise(pl.col("mid")).alias("mid")
    )
    feats_b, _ = build_features(bumped)
    a = feats_a.filter(pl.col("pair") == "EURUSD").sort("bucket").head(feats_a.height - 5)
    b = feats_b.filter(pl.col("pair") == "EURUSD").sort("bucket").head(feats_b.height - 5)
    for col in names:
        va, vb = a[col].to_numpy(), b[col].to_numpy()
        assert np.allclose(va, vb, equal_nan=True), f"look-ahead in {col}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/fx_cluster/test_features.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `scripts/fx_cluster/features.py`**

```python
"""Causal, pair-normalized (pair, t) feature matrix.

Three blocks (spec section 4): temporal (own path), spatial (cross-currency via the
USD factor + residual), regime context. Every column uses only data <= t and is
z-scored with trailing-window stats so points from different pairs are comparable.
"""

from __future__ import annotations

import numpy as np
import polars as pl

from scripts.fx_cluster import config
from scripts.fx_cluster.causal import causal_zscore, ewma_vol, rolling_minmax_pos
from scripts.fx_cluster.factor import oriented_returns, residuals

ZWIN = 250          # trailing window for cross-pair-comparability z-scores
LOOKBACKS = (1, 4, 12, 24)


def _common_grid(bars: dict[str, pl.DataFrame]) -> pl.DataFrame:
    """Inner-join all pairs' mid on bucket so the spatial block is aligned."""
    out = None
    for p, df in bars.items():
        col = df.select("bucket", pl.col("mid").alias(f"mid_{p}")).sort("bucket")
        out = col if out is None else out.join(col, on="bucket", how="inner")
    return out.sort("bucket")


def build_features(bars: dict[str, pl.DataFrame]) -> tuple[pl.DataFrame, list[str]]:
    pairs = list(bars.keys())
    grid = _common_grid(bars)
    buckets = grid["bucket"].to_numpy()
    logret = {p: np.diff(np.log(grid[f"mid_{p}"].to_numpy()), prepend=np.nan) for p in pairs}
    for p in pairs:
        logret[p][0] = 0.0
    oriented = oriented_returns(logret)
    res = residuals(oriented)
    factor = sum(oriented[p] for p in pairs) / len(pairs)
    disp = np.vstack([res[p] for p in pairs]).std(axis=0)  # cross-sectional dispersion

    names: list[str] = []
    frames = []
    for p in pairs:
        mid = grid[f"mid_{p}"].to_numpy()
        r = logret[p]
        sigma = ewma_vol(r, config.EWMA_LAMBDA)
        sig_safe = np.where(sigma > 0, sigma, np.nan)
        feat = {"pair": p, "bucket": buckets}
        # temporal block
        for lb in LOOKBACKS:
            cum = np.concatenate([np.full(lb, np.nan), np.log(mid[lb:] / mid[:-lb])])
            feat[f"ret_{lb}h"] = causal_zscore(cum / (sig_safe * np.sqrt(lb)), ZWIN)
        feat["vol"] = causal_zscore(sigma, ZWIN)
        feat["range_pos_24"] = rolling_minmax_pos(mid, 24)
        feat["range_pos_120"] = rolling_minmax_pos(mid, 120)
        feat["trend"] = causal_zscore(
            np.sign(r).astype(float), 24)  # short-run sign persistence (zscored)
        # spatial block
        feat["resid"] = causal_zscore(res[p], ZWIN)
        feat["factor"] = causal_zscore(factor, ZWIN)
        feat["dispersion"] = causal_zscore(disp, ZWIN)
        rank = np.full(len(buckets), np.nan)
        stack = np.vstack([res[q] for q in pairs])
        order = stack.argsort(axis=0).argsort(axis=0)[pairs.index(p)]
        rank = order / (len(pairs) - 1)
        feat["xs_rank"] = rank
        # regime block
        hour = (buckets.astype("datetime64[h]").astype(int) % 24)
        feat["tod_sin"] = np.sin(2 * np.pi * hour / 24)
        feat["tod_cos"] = np.cos(2 * np.pi * hour / 24)
        frames.append(pl.DataFrame(feat))

    if not names:
        names = [c for c in frames[0].columns if c not in ("pair", "bucket")]
    return pl.concat(frames).sort(["bucket", "pair"]), names
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/fx_cluster/test_features.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/fx_cluster/features.py tests/fx_cluster/test_features.py
git commit -m "feat(fx_cluster): causal pair-normalized (pair,t) feature matrix"
```

---

## Task 7: Embedding and clustering wrappers (`embed.py`, `cluster.py`)

**Files:**
- Create: `scripts/fx_cluster/embed.py`, `scripts/fx_cluster/cluster.py`
- Create: `tests/fx_cluster/test_embed_cluster.py`

- [ ] **Step 1: Write the failing test**

Create `tests/fx_cluster/test_embed_cluster.py`:
```python
import numpy as np

from scripts.fx_cluster.cluster import Clusterer
from scripts.fx_cluster.embed import Embedder


def _three_blobs(seed=0):
    rng = np.random.default_rng(seed)
    a = rng.normal([-5, -5], 0.3, (200, 2))
    b = rng.normal([5, 5], 0.3, (200, 2))
    c = rng.normal([-5, 5], 0.3, (200, 2))
    return np.vstack([a, b, c])


def test_embedder_fits_train_and_transforms_test_to_same_dim():
    x = _three_blobs()
    emb = Embedder(n_components=2).fit(x)
    z_train = emb.transform(x)
    z_test = emb.transform(_three_blobs(seed=1))
    assert z_train.shape == (600, 2)
    assert z_test.shape[1] == 2


def test_clusterer_recovers_blobs_and_predicts_oos():
    x = _three_blobs()
    clu = Clusterer(min_cluster_size=50, min_samples=5).fit(x)
    labels = clu.labels_
    assert len(set(labels) - {-1}) == 3
    new_labels, strengths = clu.predict(_three_blobs(seed=2))
    assert new_labels.shape == (600,)
    assert strengths.shape == (600,)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/fx_cluster/test_embed_cluster.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `scripts/fx_cluster/embed.py`**

```python
"""Causal UMAP wrapper: fit on train only, transform anything."""

from __future__ import annotations

import numpy as np
import umap

from scripts.fx_cluster import config


class Embedder:
    def __init__(self, n_components: int = config.UMAP_N_COMPONENTS,
                 n_neighbors: int = config.UMAP_N_NEIGHBORS,
                 min_dist: float = config.UMAP_MIN_DIST):
        self._um = umap.UMAP(
            n_components=n_components, n_neighbors=n_neighbors, min_dist=min_dist,
            random_state=config.RANDOM_SEED,
        )

    def fit(self, x: np.ndarray) -> "Embedder":
        self._um.fit(np.asarray(x, dtype=float))
        return self

    def transform(self, x: np.ndarray) -> np.ndarray:
        return self._um.transform(np.asarray(x, dtype=float))
```

- [ ] **Step 4: Implement `scripts/fx_cluster/cluster.py`**

```python
"""HDBSCAN wrapper: fit on train embedding, assign OOS via approximate_predict."""

from __future__ import annotations

import hdbscan
import numpy as np

from scripts.fx_cluster import config


class Clusterer:
    def __init__(self, min_cluster_size: int = config.HDBSCAN_MIN_CLUSTER_SIZE,
                 min_samples: int = config.HDBSCAN_MIN_SAMPLES):
        self._h = hdbscan.HDBSCAN(
            min_cluster_size=min_cluster_size, min_samples=min_samples,
            prediction_data=True,
        )
        self.labels_: np.ndarray = np.array([])

    def fit(self, z: np.ndarray) -> "Clusterer":
        self.labels_ = self._h.fit_predict(np.asarray(z, dtype=float))
        return self

    def predict(self, z: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        labels, strengths = hdbscan.approximate_predict(self._h, np.asarray(z, dtype=float))
        return labels, strengths
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/fx_cluster/test_embed_cluster.py -v`
Expected: PASS (2 tests).

- [ ] **Step 6: Commit**

```bash
git add scripts/fx_cluster/embed.py scripts/fx_cluster/cluster.py tests/fx_cluster/test_embed_cluster.py
git commit -m "feat(fx_cluster): causal UMAP + HDBSCAN wrappers (train fit, OOS predict)"
```

---

## Task 8: Cluster scoring (`score.py`)

Per-cluster scoring with the look-ahead-safe statistics: block bootstrap, persistence
filter, direction assignment, selection, BH-FDR. Each piece is unit-tested.

**Files:**
- Create: `scripts/fx_cluster/score.py`
- Create: `tests/fx_cluster/test_score.py`

- [ ] **Step 1: Write the failing test**

Create `tests/fx_cluster/test_score.py`:
```python
import numpy as np
import polars as pl

from scripts.fx_cluster.score import (
    bh_fdr,
    block_bootstrap_pvalue,
    score_clusters,
    select_clusters,
)


def test_block_bootstrap_detects_real_positive_mean():
    rng = np.random.default_rng(0)
    blocks = rng.integers(0, 20, 2000)
    rets = rng.normal(0.5, 1.0, 2000)        # clearly positive mean
    p = block_bootstrap_pvalue(rets, blocks, n_boot=2000, seed=1)
    assert p < 0.05


def test_block_bootstrap_noise_not_significant():
    rng = np.random.default_rng(2)
    blocks = rng.integers(0, 20, 2000)
    rets = rng.normal(0.0, 1.0, 2000)
    p = block_bootstrap_pvalue(rets, blocks, n_boot=2000, seed=1)
    assert p > 0.05


def test_bh_fdr_rejects_small_pvalues():
    p = np.array([0.001, 0.02, 0.2, 0.8])
    rej = bh_fdr(p, alpha=0.10)
    assert rej[0] and not rej[3]


def test_score_and_select_picks_profitable_cluster():
    # cluster 0 = strong long edge; cluster 1 = noise; -1 = noise label (ignored).
    n = 1200
    rng = np.random.default_rng(3)
    labels = np.array([0] * 400 + [1] * 400 + [-1] * 400)
    df = pl.DataFrame({
        "cluster": labels,
        "block": rng.integers(0, 30, n),
        "ret_long": np.concatenate([rng.normal(1.0, 1.0, 400), rng.normal(0.0, 1.0, 400), rng.normal(0, 1, 400)]),
        "ret_short": np.concatenate([rng.normal(-1.0, 1.0, 400), rng.normal(0.0, 1.0, 400), rng.normal(0, 1, 400)]),
        "mfe": np.full(n, 5.0), "mae": np.full(n, -1.0), "hold_bars": np.full(n, 6),
    })
    report = score_clusters(df, cost_bps=0.7)
    sel = select_clusters(report, margin_bps=0.2)
    assert 0 in [r["cluster"] for r in sel]
    assert all(r["side"] == 1 for r in sel if r["cluster"] == 0)
    assert 1 not in [r["cluster"] for r in sel]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/fx_cluster/test_score.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `scripts/fx_cluster/score.py`**

```python
"""Per-cluster scoring with look-ahead-safe statistics.

block_bootstrap_pvalue: one-sided p that the mean > 0, resampling whole time-blocks
so correlated same-period trades are not treated as independent.
score_clusters: per cluster, pick the better side, compute mean net, persistence
metrics, and a bootstrap p-value. select_clusters: keep clusters whose mean net
beats the cost floor by margin, pass the persistence filter, then BH-FDR.
"""

from __future__ import annotations

import numpy as np
import polars as pl

from scripts.fx_cluster import config


def block_bootstrap_pvalue(rets: np.ndarray, blocks: np.ndarray,
                           n_boot: int = config.BOOTSTRAP_BLOCKS, seed: int = config.RANDOM_SEED) -> float:
    """One-sided p-value for H0: mean(rets) <= 0, via block resampling of unique blocks."""
    rets = np.asarray(rets, dtype=float)
    uniq = np.unique(blocks)
    by_block = [rets[blocks == b] for b in uniq]
    rng = np.random.default_rng(seed)
    obs = rets.mean()
    centered = [g - obs for g in by_block]   # impose H0 mean 0
    count = 0
    nb = len(uniq)
    for _ in range(n_boot):
        pick = rng.integers(0, nb, nb)
        sample = np.concatenate([centered[k] for k in pick])
        if sample.mean() >= obs:
            count += 1
    return (count + 1) / (n_boot + 1)


def bh_fdr(pvals: np.ndarray, alpha: float = config.FDR_ALPHA) -> np.ndarray:
    """Benjamini-Hochberg: boolean reject mask."""
    p = np.asarray(pvals, dtype=float)
    m = len(p)
    order = np.argsort(p)
    thresh = alpha * (np.arange(1, m + 1) / m)
    passed = p[order] <= thresh
    reject = np.zeros(m, dtype=bool)
    if passed.any():
        kmax = np.max(np.where(passed))
        reject[order[: kmax + 1]] = True
    return reject


def score_clusters(df: pl.DataFrame, cost_bps: float) -> list[dict]:
    """df columns: cluster, block, ret_long, ret_short, mfe, mae, hold_bars.
    cost is already inside ret_long/ret_short; cost_bps is kept for reporting."""
    out = []
    for cl in sorted(set(df["cluster"].to_list())):
        if cl == -1:
            continue
        sub = df.filter(pl.col("cluster") == cl)
        ml, ms = sub["ret_long"].mean(), sub["ret_short"].mean()
        side = 1 if ml >= ms else -1
        rets = (sub["ret_long"] if side == 1 else sub["ret_short"]).to_numpy()
        rets = rets[~np.isnan(rets)]
        blocks = sub["block"].to_numpy()[: len(rets)]
        mfe_mae = abs(sub["mfe"].mean() / sub["mae"].mean()) if sub["mae"].mean() != 0 else np.inf
        out.append({
            "cluster": cl, "side": side, "n": len(rets),
            "mean_net": float(np.mean(rets)) if len(rets) else float("nan"),
            "win_rate": float((rets > 0).mean()) if len(rets) else float("nan"),
            "pvalue": block_bootstrap_pvalue(rets, blocks) if len(rets) > 10 else 1.0,
            "mfe_mae": float(mfe_mae), "median_hold": float(sub["hold_bars"].median()),
            "cost_bps": cost_bps,
        })
    return out


def select_clusters(report: list[dict], margin_bps: float = config.SELECT_MARGIN_BPS) -> list[dict]:
    """Keep clusters that beat cost by margin, pass persistence, then BH-FDR."""
    cand = [r for r in report
            if r["mean_net"] > margin_bps
            and r["mfe_mae"] >= config.PERSIST_MIN_MFE_MAE
            and r["median_hold"] >= config.PERSIST_MIN_HOLD_BARS]
    if not cand:
        return []
    reject = bh_fdr(np.array([r["pvalue"] for r in cand]))
    return [r for r, keep in zip(cand, reject) if keep]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/fx_cluster/test_score.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/fx_cluster/score.py tests/fx_cluster/test_score.py
git commit -m "feat(fx_cluster): cluster scoring (block bootstrap, persistence, BH-FDR)"
```

---

## Task 9: Kill-test orchestrator (`killtest.py`)

Wires the pipeline end-to-end on the train/test split and writes the GO/NO-GO report.
Tested for orchestration glue on a tiny synthetic dataset; the real run is a data step.

**Files:**
- Create: `scripts/fx_cluster/killtest.py`
- Create: `tests/fx_cluster/test_killtest.py`

- [ ] **Step 1: Write the failing test**

Create `tests/fx_cluster/test_killtest.py`:
```python
from datetime import datetime, timedelta

import numpy as np
import polars as pl

from scripts.fx_cluster.killtest import assemble_points, add_block_index


def _bars(seed):
    rng = np.random.default_rng(seed)
    n = 400
    t0 = datetime(2020, 1, 1)
    mid = 1.0 + np.cumsum(rng.normal(0, 1e-4, n))
    return pl.DataFrame({
        "bucket": [t0 + timedelta(hours=i) for i in range(n)],
        "mid": mid, "mid_high": mid + 1e-4, "mid_low": mid - 1e-4,
        "bid": mid - 5e-5, "ask": mid + 5e-5, "n_ticks": np.full(n, 100),
    })


def test_assemble_points_joins_features_and_labels():
    bars = {p: _bars(i) for i, p in enumerate(["EURUSD", "GBPUSD", "AUDUSD"])}
    pts = assemble_points(bars)
    assert {"pair", "bucket", "ret_long", "ret_short"}.issubset(pts.columns)
    assert pts.height > 0


def test_add_block_index_is_stable_and_integer():
    df = pl.DataFrame({"bucket": [datetime(2020, 1, 1) + timedelta(days=d) for d in range(20)]})
    out = add_block_index(df, block_days=5)
    assert out["block"].dtype == pl.Int64 or out["block"].dtype == pl.Int32
    assert out["block"].n_unique() == 4
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/fx_cluster/test_killtest.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `scripts/fx_cluster/killtest.py`**

```python
"""Kill-test orchestrator (spec section 6.1): single causal split, train-only fit,
OOS assignment, simulate selected clusters, write the GO/NO-GO report."""

from __future__ import annotations

import numpy as np
import polars as pl

from scripts.fx_cluster import config
from scripts.fx_cluster.bars import load_bars
from scripts.fx_cluster.cluster import Clusterer
from scripts.fx_cluster.embed import Embedder
from scripts.fx_cluster.features import build_features
from scripts.fx_cluster.labels import build_labels
from scripts.fx_cluster.score import score_clusters, select_clusters


def add_block_index(df: pl.DataFrame, block_days: int = config.BLOCK_DAYS) -> pl.DataFrame:
    epoch_day = (pl.col("bucket").dt.epoch(time_unit="d"))
    return df.with_columns((epoch_day // block_days).cast(pl.Int64).alias("block"))


def assemble_points(bars: dict[str, pl.DataFrame]) -> pl.DataFrame:
    feats, names = build_features(bars)
    label_frames = []
    for p, b in bars.items():
        lab = build_labels(b.sort("bucket")).select(
            "bucket", "ret_long", "ret_short", "mfe", "mae", "hold_bars"
        ).with_columns(pl.lit(p).alias("pair"))
        label_frames.append(lab)
    labels = pl.concat(label_frames)
    pts = feats.join(labels, on=["pair", "bucket"], how="inner")
    pts = add_block_index(pts)
    pts.feature_names = names  # type: ignore[attr-defined]
    return pts


def _feature_cols(pts: pl.DataFrame) -> list[str]:
    drop = {"pair", "bucket", "block", "ret_long", "ret_short", "mfe", "mae", "hold_bars"}
    return [c for c in pts.columns if c not in drop]


def run(write_report: bool = True) -> list[dict]:
    bars = {p: load_bars(p) for p in config.POOL_PAIRS}
    pts = assemble_points(bars).drop_nulls()
    fcols = _feature_cols(pts)

    train = pts.filter((pl.col("bucket") >= config.TRAIN_START) & (pl.col("bucket") < config.TRAIN_END))
    test = pts.filter((pl.col("bucket") >= config.TEST_START) & (pl.col("bucket") < config.TEST_END))

    emb = Embedder().fit(train.select(fcols).to_numpy())
    clu = Clusterer().fit(emb.transform(train.select(fcols).to_numpy()))

    train_scored = train.with_columns(pl.Series("cluster", clu.labels_))
    report = score_clusters(train_scored, cost_bps=config.COMMISSION_BPS_RT)
    selection = select_clusters(report)

    test_labels, _ = clu.predict(emb.transform(test.select(fcols).to_numpy()))
    test_scored = test.with_columns(pl.Series("cluster", test_labels))

    oos = []
    for sel in selection:
        sub = test_scored.filter(pl.col("cluster") == sel["cluster"])
        col = "ret_long" if sel["side"] == 1 else "ret_short"
        rets = sub[col].drop_nulls().to_numpy()
        if len(rets) == 0:
            continue
        per_year = (
            sub.with_columns(pl.col("bucket").dt.year().alias("yr"))
            .group_by("yr").agg(pl.col(col).mean().alias("m"))
        )
        oos.append({
            "cluster": sel["cluster"], "side": sel["side"], "n_oos": len(rets),
            "oos_mean_net": float(np.mean(rets)), "oos_win": float((rets > 0).mean()),
            "pos_years": int((per_year["m"] > 0).sum()), "n_years": per_year.height,
        })

    if write_report:
        _write_report(report, selection, oos)
    return oos


def _write_report(report, selection, oos) -> None:
    lines = ["# FX Cluster Kill-Test Report", ""]
    lines.append(f"Pool pairs: {', '.join(config.POOL_PAIRS)} (USDJPY held out).")
    lines.append(f"Train {config.TRAIN_START:%Y-%m} .. {config.TRAIN_END:%Y-%m}, "
                 f"Test {config.TEST_START:%Y-%m} .. {config.TEST_END:%Y-%m}.")
    lines.append(f"Cost floor ~{config.COMMISSION_BPS_RT} bps commission + crossed spread.")
    lines.append("")
    lines.append(f"Train clusters scored: {len(report)}; selected: {len(selection)}.")
    lines.append("")
    lines.append("## OOS performance of selected clusters")
    lines.append("")
    lines.append("| cluster | side | n_oos | oos_mean_net (bps) | win | pos_years/total |")
    lines.append("|---|---|---|---|---|---|")
    for o in oos:
        lines.append(f"| {o['cluster']} | {o['side']} | {o['n_oos']} | "
                     f"{o['oos_mean_net']:.3f} | {o['oos_win']:.2f} | {o['pos_years']}/{o['n_years']} |")
    survivors = [o for o in oos if o["oos_mean_net"] > config.SELECT_MARGIN_BPS
                 and o["pos_years"] >= max(1, o["n_years"] - 1)]
    verdict = "GO" if survivors else "NO_GO"
    lines += ["", f"## Verdict: {verdict}", ""]
    if survivors:
        lines.append(f"{len(survivors)} cluster(s) clear cost with margin and are stable OOS.")
    else:
        lines.append("No cluster shows an OOS-stable, cost-net edge. Cheap NO_GO.")
    with open(config.REPORT_PATH, "w") as f:
        f.write("\n".join(lines) + "\n")


def main() -> None:
    oos = run(write_report=True)
    print(f"Selected clusters survived OOS check: {len(oos)}; report -> {config.REPORT_PATH}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/fx_cluster/test_killtest.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/fx_cluster/killtest.py tests/fx_cluster/test_killtest.py
git commit -m "feat(fx_cluster): kill-test orchestrator + GO/NO-GO report writer"
```

---

## Task 10: Run the kill-test and record the verdict

**Files:**
- Create (by running): `docs/analysis/fx_cluster_killtest_report.md`

- [ ] **Step 1: Ensure bars exist** (from Task 2 Step 5; rebuild if missing)

Run: `uv run python scripts/fx_cluster/bars.py`
Expected: 6 parquets in `data/tick_bars/`.

- [ ] **Step 2: Run the kill-test**

Run: `uv run python scripts/fx_cluster/killtest.py`
Expected: prints the survivor count and writes `docs/analysis/fx_cluster_killtest_report.md`. (This may take several minutes — UMAP/HDBSCAN over ~200k+ training points.)

- [ ] **Step 3: Read the report and decompose the result**

Read `docs/analysis/fx_cluster_killtest_report.md`. Apply the decomposition discipline:
separate gross vs cost vs significance; confirm any survivor is stable across years
(`pos_years` near `n_years`), not carried by one period; sanity-check that survivor
clusters are economically sized (`n_oos` not tiny). Add a short "Interpretation" section
to the report stating GO / NO_GO and *why*, in the repo's canonical verdict vocabulary.

- [ ] **Step 4: Commit the report**

```bash
git add docs/analysis/fx_cluster_killtest_report.md
git commit -m "docs(fx_cluster): kill-test verdict (GO/NO_GO) with decomposition"
```

---

## Task 11: Quality gate and PR

- [ ] **Step 1: Run the repo quality gate**

Run: `make quality`
Expected: ty + ruff + vulture + smellcheck + radon + xenon pass. Fix any findings in
`scripts/fx_cluster/` (type hints, unused imports). Re-run until green.

- [ ] **Step 2: Run the full package tests once more**

Run: `uv run pytest tests/fx_cluster/ -q`
Expected: all tests pass.

- [ ] **Step 3: Open the PR**

```bash
git push -u origin worktree-fx-cluster-regimes
gh pr create --title "FX cluster-regime discovery (UMAP+HDBSCAN) kill-test" \
  --body "$(cat <<'EOF'
Unsupervised UMAP+HDBSCAN discovery of recurring (pair,time) situations in the FX
dollar complex, with a causal single-split kill-test for an OOS, cost-net,
vol-scaled triple-barrier edge at the multi-hour-to-1-day horizon.

Spec: docs/superpowers/specs/2026-06-16-fx-cluster-regimes-design.md
Plan: docs/superpowers/plans/2026-06-16-fx-cluster-regimes.md
Verdict: docs/analysis/fx_cluster_killtest_report.md

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-Review notes (addressed)

- **Spec coverage:** timescale → barrier `TARGET_H`/`PATIENCE_BARS` (Task 1/5); unit `(pair,t)` → features (Task 6); spatial/temporal/regime blocks → Task 6; triple-barrier + persistence → Tasks 5/8; causal honest bars → Task 2; train-only UMAP/HDBSCAN + OOS predict → Tasks 7/9; block bootstrap + BH-FDR + decomposition → Tasks 8/10; JPY held out → `POOL_PAIRS` (Task 1, used in Task 9); kill-test split + GO/NO-GO → Task 9/10; deps → Task 1.
- **Deferred spec item resolved:** intrabar barrier ambiguity → conservative "stop-first" rule, implemented and tested in Task 5.
- **Risk-PC2 simplification:** the spec's risk-PC2 feature is omitted from the first feature set to avoid fragile rolling PCA on 6 assets (spec section 4.2 allowed this fallback); dispersion + cross-sectional rank already encode cross-currency regime. Revisit only if the kill-test is GO and a refinement is warranted.
- **Type consistency:** `Embedder.fit/transform`, `Clusterer.fit/predict/labels_`, `score_clusters`/`select_clusters`/`block_bootstrap_pvalue`/`bh_fdr` names are used identically across Tasks 7–9.
