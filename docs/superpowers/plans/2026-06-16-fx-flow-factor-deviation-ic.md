# FX Flow-Factor Deviation IC Probe — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Measure, gross of cost, whether a deviation in normalised quote flow (the PCA residual after extracting a USD-flow factor) predicts forward price — an IC sweep across horizons with IS/OOS and a price baseline, ending in a go/no-go verdict. No strategy build.

**Architecture:** Pure, unit-tested numeric kernels in `scripts/fx_coint/` (flow proxies, causal z-score, bar aggregation, USD-factor decomposition, IC/tail/FDR metrics) + two orchestration scripts (build cached 1-min flow bars from raw dukascopy ticks; run the IC probe and emit a report). Tests import `from scripts.fx_coint.<module>` (repo root is on `sys.path` via `tests/conftest.py`).

**Tech Stack:** Python 3.12, polars, numpy, pytest, `uv run`. Raw ticks at `~/Desktop/dukascopy_ticks/<PAIR>/<PAIR>_YYYYMM_ticks.parquet` (cols `timestamp,bid,ask,mid,spread`).

**Spec:** `docs/superpowers/specs/2026-06-16-fx-flow-factor-deviation-ic-design.md`

**Execution note:** Run in a fresh git worktree off `main` (the current branch is the unrelated NO-GO PR #334). All test commands use `uv run pytest`.

---

## File structure

- `scripts/fx_coint/flow_proxies.py` — pure: `tick_rule_signs`, `quote_ofi`, `causal_zscore`, `bars_from_ticks`.
- `scripts/fx_coint/usd_flow_factor.py` — pure: `orient`, `usd_factor_residual`.
- `scripts/fx_coint/flow_metrics.py` — pure: `information_coefficient`, `deviation_tail_return`, `bh_fdr`.
- `scripts/fx_coint/build_flow_bars.py` — orchestration: raw ticks → cached 1-min flow bars.
- `scripts/fx_coint/flow_factor_deviation_ic.py` — orchestration: the probe; prints tables + writes report data.
- `tests/fx_coint/test_flow_proxies.py`, `test_usd_flow_factor.py`, `test_flow_metrics.py` — unit tests.
- `docs/analysis/fx_flow_factor_deviation_ic.md` — final report (Task 7).

PAIRS orientation (reuse `from scripts.fx_coint.usd_factor_residual_probe import PAIRS`):
`{EURUSD:-1, GBPUSD:-1, AUDUSD:-1, USDJPY:+1, USDCHF:+1, USDCAD:+1}` (+ = USD strength).

---

### Task 1: Flow proxy kernels

**Files:**
- Create: `scripts/fx_coint/flow_proxies.py`
- Test: `tests/fx_coint/test_flow_proxies.py`

- [ ] **Step 1: Write failing tests for the per-tick proxies**

```python
# tests/fx_coint/test_flow_proxies.py
import numpy as np
import polars as pl

from scripts.fx_coint.flow_proxies import tick_rule_signs, quote_ofi


def test_tick_rule_ffills_zero_diffs():
    mid = np.array([1.0, 1.1, 1.1, 1.0, 1.2])
    # diffs(prepend first)=[0,+,0,-,+] -> ffill zeros -> [0,1,1,-1,1]
    assert tick_rule_signs(mid).tolist() == [0.0, 1.0, 1.0, -1.0, 1.0]


def test_quote_ofi_sign_of_bid_minus_ask():
    bid = np.array([1.0, 1.1, 1.1, 1.0])
    ask = np.array([1.2, 1.2, 1.1, 1.1])
    # db=[0,+1,0,-1] da=[0,0,-1,0] -> db-da=[0,1,1,-1]
    assert quote_ofi(bid, ask).tolist() == [0.0, 1.0, 1.0, -1.0]
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `uv run pytest tests/fx_coint/test_flow_proxies.py -q`
Expected: FAIL (ModuleNotFoundError / ImportError: cannot import name).

- [ ] **Step 3: Implement the per-tick proxies**

```python
# scripts/fx_coint/flow_proxies.py
"""Pure quote-flow kernels: tick-rule signed flow, sizeless Cont OFI,
causal z-score, and raw-tick -> time-bar aggregation. No import-time side effects."""

from __future__ import annotations

import numpy as np
import polars as pl


def tick_rule_signs(mid: np.ndarray) -> np.ndarray:
    """Lee-Ready tick rule: +1 uptick, -1 downtick, 0-diff carries the last sign.
    First element has no prior tick -> 0."""
    d = np.sign(np.diff(mid, prepend=mid[0]))
    out = np.zeros(len(d), dtype=float)
    last = 0.0
    for i in range(len(d)):
        if d[i] != 0.0:
            last = d[i]
        out[i] = last
    return out


def quote_ofi(bid: np.ndarray, ask: np.ndarray) -> np.ndarray:
    """Sizeless Cont order-flow imbalance per tick: sign(Δbid) - sign(Δask).
    + = buy pressure (bid rising and/or ask falling)."""
    db = np.sign(np.diff(bid, prepend=bid[0]))
    da = np.sign(np.diff(ask, prepend=ask[0]))
    return db - da
```

- [ ] **Step 4: Run tests, verify pass**

Run: `uv run pytest tests/fx_coint/test_flow_proxies.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add scripts/fx_coint/flow_proxies.py tests/fx_coint/test_flow_proxies.py
git commit -m "feat(fx_coint): tick-rule + sizeless Cont OFI flow proxies"
```

---

### Task 2: Causal z-score (look-ahead-free normalisation)

**Files:**
- Modify: `scripts/fx_coint/flow_proxies.py` (append `causal_zscore`)
- Test: `tests/fx_coint/test_flow_proxies.py` (append)

- [ ] **Step 1: Write the failing causality test**

```python
# append to tests/fx_coint/test_flow_proxies.py
from scripts.fx_coint.flow_proxies import causal_zscore


def test_causal_zscore_is_look_ahead_free():
    # two series identical up to index k, different after; z must match up to k
    base = [0.0, 1.0, -1.0, 0.5, 2.0, -0.5, 1.5, 0.0, 1.0, -1.0, 0.3, 0.7]
    k = 6
    a = pl.Series(base)
    b = pl.Series(base[: k + 1] + [9.9, -9.9, 9.9, -9.9, 9.9])
    za = causal_zscore(a, span=4).to_numpy()
    zb = causal_zscore(b, span=4).to_numpy()
    np.testing.assert_allclose(za[: k + 1], zb[: k + 1], equal_nan=True)
```

- [ ] **Step 2: Run test, verify it fails**

Run: `uv run pytest tests/fx_coint/test_flow_proxies.py::test_causal_zscore_is_look_ahead_free -q`
Expected: FAIL (cannot import name `causal_zscore`).

- [ ] **Step 3: Implement causal_zscore**

```python
# append to scripts/fx_coint/flow_proxies.py
def causal_zscore(x: pl.Series, span: int) -> pl.Series:
    """EWMA z-score using only information up to t-1 (mean/std shifted by one bar),
    so x_t never enters its own normalisation."""
    mean = x.ewm_mean(span=span, min_periods=span).shift(1)
    std = x.ewm_std(span=span, min_periods=span).shift(1)
    return (x - mean) / std
```

- [ ] **Step 4: Run test, verify pass**

Run: `uv run pytest tests/fx_coint/test_flow_proxies.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add scripts/fx_coint/flow_proxies.py tests/fx_coint/test_flow_proxies.py
git commit -m "feat(fx_coint): causal EWMA z-score for flow normalisation"
```

---

### Task 3: Bar aggregation (raw ticks → per-bar flow)

**Files:**
- Modify: `scripts/fx_coint/flow_proxies.py` (append `bars_from_ticks`)
- Test: `tests/fx_coint/test_flow_proxies.py` (append)

- [ ] **Step 1: Write the failing aggregation test**

```python
# append to tests/fx_coint/test_flow_proxies.py
from datetime import datetime

from scripts.fx_coint.flow_proxies import bars_from_ticks


def test_bars_from_ticks_aggregates_last_and_mean():
    ticks = pl.DataFrame(
        {
            "timestamp": [
                datetime(2020, 1, 1, 0, 0, 1),
                datetime(2020, 1, 1, 0, 0, 30),
                datetime(2020, 1, 1, 0, 1, 5),
                datetime(2020, 1, 1, 0, 1, 50),
            ],
            "bid": [1.0, 1.1, 1.1, 1.2],
            "ask": [1.2, 1.2, 1.3, 1.3],
            "mid": [1.10, 1.15, 1.20, 1.25],
        }
    )
    bars = bars_from_ticks(ticks, "1m")
    assert bars.height == 2
    # last tick mid of the second bucket
    assert bars.sort("bucket")["mid"].to_list()[-1] == 1.25
    assert {"bucket", "mid", "bid", "ask", "flow_tick", "flow_ofi", "n_ticks"} <= set(bars.columns)
```

- [ ] **Step 2: Run test, verify it fails**

Run: `uv run pytest tests/fx_coint/test_flow_proxies.py::test_bars_from_ticks_aggregates_last_and_mean -q`
Expected: FAIL (cannot import name `bars_from_ticks`).

- [ ] **Step 3: Implement bars_from_ticks**

```python
# append to scripts/fx_coint/flow_proxies.py
def bars_from_ticks(ticks: pl.DataFrame, freq: str) -> pl.DataFrame:
    """ticks: timestamp, bid, ask, mid. Build true time bars (last tick before each
    boundary) with mean tick-rule flow + mean OFI + tick count per bar."""
    t = ticks.sort("timestamp")
    t = t.with_columns(
        pl.Series("tsign", tick_rule_signs(t["mid"].to_numpy())),
        pl.Series("ofi", quote_ofi(t["bid"].to_numpy(), t["ask"].to_numpy())),
        pl.col("timestamp").dt.truncate(freq).alias("bucket"),
    )
    return (
        t.group_by("bucket")
        .agg(
            pl.col("mid").last(),
            pl.col("bid").last(),
            pl.col("ask").last(),
            pl.col("tsign").mean().alias("flow_tick"),
            pl.col("ofi").mean().alias("flow_ofi"),
            pl.len().alias("n_ticks"),
        )
        .sort("bucket")
    )
```

- [ ] **Step 4: Run test, verify pass**

Run: `uv run pytest tests/fx_coint/test_flow_proxies.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add scripts/fx_coint/flow_proxies.py tests/fx_coint/test_flow_proxies.py
git commit -m "feat(fx_coint): aggregate raw ticks into 1-min flow bars"
```

---

### Task 4: USD-flow factor decomposition

**Files:**
- Create: `scripts/fx_coint/usd_flow_factor.py`
- Test: `tests/fx_coint/test_usd_flow_factor.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/fx_coint/test_usd_flow_factor.py
import numpy as np

from scripts.fx_coint.usd_flow_factor import orient, usd_factor_residual


def test_orient_applies_signs():
    flow = np.array([[1.0, 2.0], [3.0, 4.0]])
    signs = np.array([-1.0, 1.0])
    np.testing.assert_allclose(orient(flow, signs), np.array([[-1.0, 2.0], [-3.0, 4.0]]))


def test_factor_is_mean_and_residual_sums_to_zero():
    flow_oriented = np.array([[1.0, 3.0, 2.0], [0.0, 0.0, 6.0]])
    factor, residual = usd_factor_residual(flow_oriented)
    np.testing.assert_allclose(factor, np.array([2.0, 2.0]))
    np.testing.assert_allclose(residual.sum(axis=1), np.zeros(2), atol=1e-12)
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `uv run pytest tests/fx_coint/test_usd_flow_factor.py -q`
Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 3: Implement the decomposition**

```python
# scripts/fx_coint/usd_flow_factor.py
"""Estimation-free USD-flow factor decomposition (no look-ahead: purely
cross-sectional at each t). Mirrors the price USD-factor trick (EW ≈ PC1)."""

from __future__ import annotations

import numpy as np


def orient(flow: np.ndarray, signs: np.ndarray) -> np.ndarray:
    """flow (T, P) -> oriented to USD strength via signs (P,) of +-1."""
    return flow * signs[None, :]


def usd_factor_residual(flow_oriented: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Dollar-flow factor = cross-pair mean (T,); residual = oriented - factor (T, P)."""
    factor = flow_oriented.mean(axis=1)
    residual = flow_oriented - factor[:, None]
    return factor, residual
```

- [ ] **Step 4: Run tests, verify pass**

Run: `uv run pytest tests/fx_coint/test_usd_flow_factor.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add scripts/fx_coint/usd_flow_factor.py tests/fx_coint/test_usd_flow_factor.py
git commit -m "feat(fx_coint): estimation-free USD-flow factor + residual"
```

---

### Task 5: IC, deviation-tail, and BH-FDR metrics

**Files:**
- Create: `scripts/fx_coint/flow_metrics.py`
- Test: `tests/fx_coint/test_flow_metrics.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/fx_coint/test_flow_metrics.py
import numpy as np

from scripts.fx_coint.flow_metrics import (
    bh_fdr,
    deviation_tail_return,
    information_coefficient,
)


def test_ic_detects_strong_correlation():
    rng = np.random.default_rng(0)
    sig = rng.standard_normal(5000)
    fwd = 0.5 * sig + 0.1 * rng.standard_normal(5000)
    ic, t, n = information_coefficient(sig, fwd, horizon=1)
    assert ic > 0.7 and t > 10 and n == 5000


def test_ic_non_overlap_subsamples():
    sig = np.arange(100.0)
    _, _, n = information_coefficient(sig, sig, horizon=5)
    assert n == 20  # every 5th observation


def test_deviation_tail_follow_positive_when_signal_equals_fwd():
    rng = np.random.default_rng(1)
    sig = rng.standard_normal(2000)
    follow, fade = deviation_tail_return(sig, sig, q=0.90)
    assert follow > 0 and np.isclose(fade, -follow)


def test_bh_fdr_rejects_small_pvalues():
    p = np.array([0.001, 0.2, 0.04, 0.8, 0.0001])
    mask = bh_fdr(p, alpha=0.05)
    assert mask[0] and mask[4] and not mask[3]
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `uv run pytest tests/fx_coint/test_flow_metrics.py -q`
Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 3: Implement the metrics**

```python
# scripts/fx_coint/flow_metrics.py
"""Gross predictability metrics: non-overlap IC, deviation-tail conditional return,
Benjamini-Hochberg FDR. Pure numpy, no side effects."""

from __future__ import annotations

import numpy as np


def information_coefficient(signal: np.ndarray, fwd: np.ndarray, horizon: int) -> tuple[float, float, int]:
    """Pearson IC with NON-OVERLAPPING sampling (every `horizon` obs) for an honest
    t-stat. Returns (ic, tstat, n_used)."""
    s = signal[::horizon]
    f = fwd[::horizon]
    m = np.isfinite(s) & np.isfinite(f)
    s, f = s[m], f[m]
    if len(s) < 10:
        return (float("nan"), float("nan"), len(s))
    ic = float(np.corrcoef(s, f)[0, 1])
    t = ic * np.sqrt(len(s) - 2) / np.sqrt(max(1e-12, 1.0 - ic**2))
    return (ic, float(t), len(s))


def deviation_tail_return(signal: np.ndarray, fwd: np.ndarray, q: float = 0.90) -> tuple[float, float]:
    """Mean forward return in the |signal| top-(1-q) tail. follow = mean(sign(signal)*fwd)
    (+ = continuation); fade = -follow. Same units as fwd."""
    a = np.abs(signal)
    m = np.isfinite(a) & np.isfinite(fwd) & np.isfinite(signal)
    a, sig, f = a[m], signal[m], fwd[m]
    if len(a) < 10:
        return (float("nan"), float("nan"))
    sel = a >= np.quantile(a, q)
    follow = float((np.sign(sig[sel]) * f[sel]).mean())
    return (follow, -follow)


def bh_fdr(pvals: np.ndarray, alpha: float = 0.05) -> np.ndarray:
    """Benjamini-Hochberg. Returns a boolean rejection mask aligned with `pvals`."""
    p = np.asarray(pvals, dtype=float)
    n = len(p)
    order = np.argsort(p)
    ranked = p[order]
    passed = ranked <= alpha * (np.arange(1, n + 1) / n)
    out = np.zeros(n, dtype=bool)
    if passed.any():
        k = int(np.where(passed)[0].max()) + 1
        out[order[:k]] = True
    return out
```

- [ ] **Step 4: Run tests, verify pass**

Run: `uv run pytest tests/fx_coint/test_flow_metrics.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add scripts/fx_coint/flow_metrics.py tests/fx_coint/test_flow_metrics.py
git commit -m "feat(fx_coint): IC / deviation-tail / BH-FDR metrics"
```

---

### Task 6: Build cached 1-min flow bars from raw ticks

**Files:**
- Create: `scripts/fx_coint/build_flow_bars.py`

This is orchestration over real data (no unit test; verified by running). Reuses the tested `bars_from_ticks`.

- [ ] **Step 1: Implement the builder**

```python
# scripts/fx_coint/build_flow_bars.py
"""Build cached 1-min flow bars (mid/bid/ask + tick-rule flow + OFI) from raw
dukascopy ticks. Output: data/tick_bars/{sym}_1m_flow.parquet.

Usage: python scripts/fx_coint/build_flow_bars.py
"""

from __future__ import annotations

import glob
import os

import polars as pl

from scripts.fx_coint.flow_proxies import bars_from_ticks

SRC = os.path.expanduser("~/Desktop/dukascopy_ticks")
PAIRS = ["EURUSD", "GBPUSD", "AUDUSD", "USDJPY", "USDCHF", "USDCAD"]
FREQ = "1m"
OUT = "data/tick_bars"


def build(sym: str) -> pl.DataFrame:
    files = sorted(glob.glob(f"{SRC}/{sym}/*_ticks.parquet"))
    parts = [
        bars_from_ticks(pl.read_parquet(f).select("timestamp", "bid", "ask", "mid"), FREQ)
        for f in files
    ]
    return pl.concat(parts).sort("bucket").unique(subset="bucket", keep="last")


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    for sym in PAIRS:
        df = build(sym)
        path = f"{OUT}/{sym}_{FREQ}_flow.parquet"
        df.write_parquet(path)
        print(f"{sym}: {df.height} bars  {df['bucket'].min()} -> {df['bucket'].max()}  -> {path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the builder**

Run: `uv run python scripts/fx_coint/build_flow_bars.py`
Expected: 6 lines, each ~ `EURUSD: ~2.1M-bar count ... -> data/tick_bars/EURUSD_1m_flow.parquet` spanning 2018→2026. (1-min bars over ~8.5 years of 24×5 trading ≈ 2.0–2.2M rows/pair.)

- [ ] **Step 3: Commit**

```bash
git add scripts/fx_coint/build_flow_bars.py
git commit -m "feat(fx_coint): build cached 1-min flow bars from raw ticks"
```

---

### Task 7: The IC probe runner

**Files:**
- Create: `scripts/fx_coint/flow_factor_deviation_ic.py`

Orchestration; verified by running. Uses tested kernels.

- [ ] **Step 1: Implement the probe**

```python
# scripts/fx_coint/flow_factor_deviation_ic.py
"""STEP 1 PROBE: does a deviation in normalised quote flow (USD-factor residual)
predict forward price? Gross IC sweep across horizons, USD-factor vs residual,
per-pair + pooled, IS/OOS, with a price-residual baseline and BH-FDR. No strategy.

Usage: python scripts/fx_coint/flow_factor_deviation_ic.py [proxy]   (flow_tick | flow_ofi)
"""

from __future__ import annotations

import sys

import numpy as np
import polars as pl

from scripts.fx_coint.flow_metrics import bh_fdr, deviation_tail_return, information_coefficient
from scripts.fx_coint.flow_proxies import causal_zscore
from scripts.fx_coint.usd_factor_residual_probe import PAIRS
from scripts.fx_coint.usd_flow_factor import orient, usd_factor_residual

PROXY = sys.argv[1] if len(sys.argv) > 1 else "flow_ofi"
HORIZONS = [1, 5, 15, 30, 60]   # minutes / bars
ZSPAN = 240                     # 4h EWMA normalisation window
IS_END = np.datetime64("2022-12-31")


def load() -> pl.DataFrame:
    syms = list(PAIRS)
    df = None
    for s in syms:
        d = pl.read_parquet(f"data/tick_bars/{s}_1m_flow.parquet").select(
            "bucket",
            causal_zscore(pl.col(PROXY), ZSPAN).alias(f"zf_{s}"),
            pl.col("mid").alias(f"mid_{s}"),
        )
        df = d if df is None else df.join(d, on="bucket", how="inner")
    return df.drop_nulls().sort("bucket")


def main() -> None:
    syms = list(PAIRS)
    df = load()
    signs = np.array([PAIRS[s] for s in syms], dtype=float)
    zf = np.column_stack([df[f"zf_{s}"].to_numpy() for s in syms])
    logmid = np.column_stack([np.log(df[f"mid_{s}"].to_numpy()) for s in syms])
    times = df["bucket"].to_numpy().astype("datetime64[D]")

    oriented = orient(zf, signs)
    factor, residual = usd_factor_residual(oriented)
    # oriented price returns: r_i(t->t+h) * sign_i ; basket = mean over pairs
    is_mask = times <= IS_END

    print(f"PROXY={PROXY}  bars={len(df)}  zspan={ZSPAN}  IS<= {IS_END}\n")
    print("  signal     horizon  sample   IC      t      tail_follow(bps)")
    pvals, labels = [], []

    def report(name: str, sig_col: np.ndarray, fwd: np.ndarray, mask: np.ndarray, h: int, tag: str) -> None:
        ic, t, n = information_coefficient(sig_col[mask], fwd[mask], horizon=h)
        follow, _ = deviation_tail_return(sig_col[mask], fwd[mask], q=0.90)
        # two-sided p from t (normal approx)
        from math import erfc, sqrt
        p = erfc(abs(t) / sqrt(2)) if np.isfinite(t) else 1.0
        pvals.append(p)
        labels.append(f"{name}|{tag}|h{h}")
        print(f"  {name:9s}  h{h:<5d}  {tag:6s}  {ic:+.4f}  {t:+5.1f}  {follow*1e4:+7.2f}")

    for h in HORIZONS:
        # forward oriented return per pair, basket
        fwd_pair = np.full_like(logmid, np.nan)
        fwd_pair[:-h] = (logmid[h:] - logmid[:-h]) * signs[None, :]
        fwd_basket = np.nanmean(fwd_pair, axis=1)
        for tag, mask in (("IS", is_mask), ("OOS", ~is_mask)):
            # FACTOR signal -> basket
            report("factor", factor, fwd_basket, mask, h, tag)
            # RESIDUAL signal -> own pair (pooled across pairs)
            sig_pool = residual.reshape(-1)
            fwd_pool = fwd_pair.reshape(-1)
            mask_pool = np.repeat(mask, len(syms))
            report("residual", sig_pool, fwd_pool, mask_pool, h, tag)
            # PRICE baseline: residual of oriented price returns (1-bar), same decomposition
            pr = (logmid[1:] - logmid[:-1]) * signs[None, :]
            pr = np.vstack([np.full((1, len(syms)), np.nan), pr])
            _, pres = usd_factor_residual(np.nan_to_num(pr))
            report("price_res", pres.reshape(-1), fwd_pool, np.repeat(mask, len(syms)), h, tag)

    rej = bh_fdr(np.array(pvals), alpha=0.05)
    print(f"\nBH-FDR @0.05: {int(rej.sum())}/{len(rej)} tests significant")
    for lbl, p, r in sorted(zip(labels, pvals, rej, strict=True), key=lambda x: x[1])[:12]:
        print(f"  {'REJECT' if r else '  ----'}  {lbl:24s}  p={p:.2e}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the probe (OFI proxy)**

Run: `uv run python scripts/fx_coint/flow_factor_deviation_ic.py flow_ofi`
Expected: a table of IC/t/tail per signal × horizon × IS/OOS, then a BH-FDR summary. No crash; finite ICs.

- [ ] **Step 3: Run the probe (tick-rule proxy)**

Run: `uv run python scripts/fx_coint/flow_factor_deviation_ic.py flow_tick`
Expected: second table for cross-check.

- [ ] **Step 4: Commit**

```bash
git add scripts/fx_coint/flow_factor_deviation_ic.py
git commit -m "feat(fx_coint): flow-factor deviation IC probe (gross, IS/OOS)"
```

---

### Task 8: Write the report + go/no-go verdict

**Files:**
- Create: `docs/analysis/fx_flow_factor_deviation_ic.md`

- [ ] **Step 1: Capture results into the report**

Paste both probe runs' tables into the report with this structure (fill the bracketed values from the actual run output):

```markdown
# FX flow-factor deviation — gross predictability (Step 1 results)

**Question:** does a deviation in normalised quote flow (USD-factor residual) predict forward price, gross of cost?

## Setup
Raw-tick 1-min flow bars, two proxies (sizeless Cont OFI, tick-rule), causal z-score
(span 240), estimation-free USD-flow factor + residual. IS ≤ 2022, OOS 2023–2026.
Non-overlapping IC t-stats; BH-FDR over all tests.

## Results — OFI proxy
[paste IC/t/tail table]

## Results — tick-rule proxy
[paste IC/t/tail table]

## Price baseline
[summarise price_res IC vs flow IC — does flow add anything?]

## Verdict
[GO / PARK / NO-GO per the spec thresholds: pooled IC stable IS->OOS AND tail move
>= ~0.7 bps -> GO; real but sub-cost -> PARK; IC~0 or sign-flip -> NO-GO. State the
best horizon and which signal (factor vs residual).]
```

- [ ] **Step 2: Apply the go/no-go decision** from `docs/superpowers/specs/2026-06-16-fx-flow-factor-deviation-ic-design.md` and write the verdict explicitly (GO / PARK / NO-GO with the numbers that drove it).

- [ ] **Step 3: Run the full test suite once**

Run: `uv run pytest tests/fx_coint/ -q`
Expected: all green (flow_proxies 4, usd_flow_factor 2, flow_metrics 4, plus existing cointegration tests).

- [ ] **Step 4: Run quality gate**

Run: `make quality`
Expected: `✅ All quality checks complete` (ruff clean on new files).

- [ ] **Step 5: Commit**

```bash
git add docs/analysis/fx_flow_factor_deviation_ic.md
git commit -m "docs(fx_coint): flow-factor deviation IC results + go/no-go verdict"
```

---

## Self-review

**Spec coverage:**
- Flow proxies (tick-rule + Cont OFI) → Task 1. Causal normalisation → Task 2. 1-min raw-tick bars → Tasks 3, 6. USD-flow factor + residual → Task 4. IC across horizons + deviation-tail + decomposition + price baseline + IS/OOS + BH-FDR → Tasks 5, 7. Report + go/no-go → Task 8. All spec sections covered.
- Conditioning variables (tick intensity / `quote_revisions`) are emitted (`n_ticks`) but not required for the Step-1 verdict; intentionally minimal (YAGNI) — promote to a signal only if the core probe shows life.

**Placeholder scan:** Tasks 1–7 contain complete code. Task 8's bracketed values are run-output transcription (unavoidable: results don't exist until the probe runs), with explicit structure and decision rule — not a code placeholder.

**Type consistency:** `bars_from_ticks` emits `flow_tick`/`flow_ofi`/`mid`/`bucket`; the probe reads exactly those. `usd_factor_residual` returns `(factor, residual)` used consistently. `information_coefficient` returns `(ic, t, n)` and `deviation_tail_return` returns `(follow, fade)` — matched at call sites. `PAIRS` imported from the existing probe module (sign convention consistent with orientation).
