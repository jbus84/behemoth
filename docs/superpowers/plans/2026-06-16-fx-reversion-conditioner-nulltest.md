# FX Reversion-Conditioner Null-Test — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Test whether a candidate fade trade's forward reversion (`signed_fade`) is predictable ex-ante from features other than displacement size, reporting it separately from raw move magnitude, with a STOP/PROCEED gate. No selection model, no strategy.

**Architecture:** Reuse the tested kernels (`usd_flow_factor.usd_factor_residual`, `flow_proxies.causal_zscore`, `flow_metrics`) and the cached 1-min flow bars. Add: a 30m feature-panel aggregator, target/metric helpers (all pure + unit-tested), and one orchestration runner that prints univariate Spearman ICs (signed-fade vs magnitude, IS/OOS), a joint ridge OOS IC/R², and top-quantile gross-vs-cost.

**Tech Stack:** Python 3.12, polars, numpy (no sklearn — ridge is closed-form numpy), pytest, `uv run`. Inputs: `data/tick_bars/{sym}_1m_flow.parquet` (already built).

**Spec:** `docs/superpowers/specs/2026-06-16-fx-reversion-conditioner-nulltest-design.md`

**Execution note:** Current git worktree (PR #334 thread). Scripts use absolute imports (`from scripts.fx_coint...`); run them with `PYTHONPATH=. uv run python ...`. Tests run with `uv run pytest` (repo root already on path via `tests/conftest.py`).

---

## File structure

- `scripts/fx_coint/feature_bars_30m.py` — pure: `aggregate_30m(flow_1m)` → 30m feature panel.
- `scripts/fx_coint/build_feature_bars_30m.py` — orchestration: 1-min bars → cached 30m feature bars.
- `scripts/fx_coint/reversion_targets.py` — pure: `compute_targets(lr, residual)` → `(signed_fade, abs_move)`.
- `scripts/fx_coint/flow_metrics.py` — MODIFY: add `spearman_ic`, `ridge_oos`.
- `scripts/fx_coint/reversion_conditioner_nulltest.py` — orchestration: the null-test.
- Tests: `tests/fx_coint/test_feature_bars_30m.py`, `test_reversion_targets.py`, append to `test_flow_metrics.py`.
- `docs/analysis/fx_reversion_conditioner_nulltest.md` — report (Task 6).

PAIRS orientation: `from scripts.fx_coint.usd_factor_residual_probe import PAIRS`
(`{EURUSD:-1, GBPUSD:-1, AUDUSD:-1, USDJPY:+1, USDCHF:+1, USDCAD:+1}`).

Lookback defaults: `K=4` bars; vol/intensity z-score window `16` bars. Cost `0.70` bps.

---

### Task 1: 30m feature aggregator

**Files:**
- Create: `scripts/fx_coint/feature_bars_30m.py`
- Test: `tests/fx_coint/test_feature_bars_30m.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/fx_coint/test_feature_bars_30m.py
from datetime import datetime

import polars as pl

from scripts.fx_coint.feature_bars_30m import aggregate_30m


def test_aggregate_30m_rolls_up_one_bucket():
    # 3 one-minute bars inside a single 30m bucket
    flow_1m = pl.DataFrame(
        {
            "bucket": [datetime(2020, 1, 1, 0, m) for m in (0, 1, 2)],
            "mid": [1.0000, 1.0010, 1.0005],
            "bid": [0.9999, 1.0009, 1.0004],
            "ask": [1.0001, 1.0011, 1.0006],
            "flow_tick": [0.5, 1.0, -1.0],
            "flow_ofi": [0.2, 0.4, -0.2],
            "n_ticks": [10, 20, 30],
        }
    )
    out = aggregate_30m(flow_1m)
    assert out.height == 1
    row = out.row(0, named=True)
    assert row["mid"] == 1.0005          # last
    assert row["n_ticks"] == 60          # sum
    assert abs(row["flow_ofi"] - (0.2 + 0.4 - 0.2) / 3) < 1e-12   # mean
    assert row["rvol_bps"] > 0           # std of 1-min log returns, in bps
    assert row["spread_bps"] > 0         # mean relative spread, in bps
```

- [ ] **Step 2: Run test, verify it fails**

Run: `uv run pytest tests/fx_coint/test_feature_bars_30m.py -q`
Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 3: Implement aggregate_30m**

```python
# scripts/fx_coint/feature_bars_30m.py
"""Aggregate 1-min flow bars into a 30m feature panel (causal within-bar stats).
Pure: no import-time side effects."""

from __future__ import annotations

import polars as pl


def aggregate_30m(flow_1m: pl.DataFrame) -> pl.DataFrame:
    """flow_1m cols: bucket, mid, bid, ask, flow_tick, flow_ofi, n_ticks (sorted).
    Returns 30m bars: last mid/bid/ask, summed n_ticks, mean flow, realized vol
    (std of 1-min log-returns, bps) and mean relative spread (bps)."""
    t = flow_1m.sort("bucket").with_columns(
        pl.col("mid").log().diff().alias("lr1"),
        ((pl.col("ask") - pl.col("bid")) / pl.col("mid")).alias("relspr"),
        pl.col("bucket").dt.truncate("30m").alias("b30"),
    )
    return (
        t.group_by("b30")
        .agg(
            pl.col("mid").last(),
            pl.col("bid").last(),
            pl.col("ask").last(),
            pl.col("n_ticks").sum(),
            pl.col("flow_tick").mean(),
            pl.col("flow_ofi").mean(),
            (pl.col("lr1").std() * 1e4).alias("rvol_bps"),
            (pl.col("relspr").mean() * 1e4).alias("spread_bps"),
        )
        .rename({"b30": "bucket"})
        .sort("bucket")
    )
```

- [ ] **Step 4: Run test, verify pass**

Run: `uv run pytest tests/fx_coint/test_feature_bars_30m.py -q`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add scripts/fx_coint/feature_bars_30m.py tests/fx_coint/test_feature_bars_30m.py
git commit -m "feat(fx_coint): 30m feature-panel aggregator from 1-min flow bars"
```

---

### Task 2: Build cached 30m feature bars

**Files:**
- Create: `scripts/fx_coint/build_feature_bars_30m.py`

Orchestration; verified by running.

- [ ] **Step 1: Implement the builder**

```python
# scripts/fx_coint/build_feature_bars_30m.py
"""Build cached 30m feature bars from the 1-min flow bars.
Output: data/tick_bars/{sym}_30m_feat.parquet

Usage: PYTHONPATH=. uv run python scripts/fx_coint/build_feature_bars_30m.py
"""

from __future__ import annotations

import polars as pl

from scripts.fx_coint.feature_bars_30m import aggregate_30m

PAIRS = ["EURUSD", "GBPUSD", "AUDUSD", "USDJPY", "USDCHF", "USDCAD"]
OUT = "data/tick_bars"


def main() -> None:
    for sym in PAIRS:
        flow_1m = pl.read_parquet(f"{OUT}/{sym}_1m_flow.parquet")
        df = aggregate_30m(flow_1m).drop_nulls()
        path = f"{OUT}/{sym}_30m_feat.parquet"
        df.write_parquet(path)
        print(f"{sym}: {df.height} bars  {df['bucket'].min()} -> {df['bucket'].max()}  -> {path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the builder**

Run: `PYTHONPATH=. uv run python scripts/fx_coint/build_feature_bars_30m.py`
Expected: 6 lines, each ~`EURUSD: ~104k bars 2018... -> 2026... -> data/tick_bars/EURUSD_30m_feat.parquet`.

- [ ] **Step 3: Commit**

```bash
git add scripts/fx_coint/build_feature_bars_30m.py
git commit -m "feat(fx_coint): build cached 30m feature bars"
```

---

### Task 3: Targets (signed_fade, abs_move)

**Files:**
- Create: `scripts/fx_coint/reversion_targets.py`
- Test: `tests/fx_coint/test_reversion_targets.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/fx_coint/test_reversion_targets.py
import numpy as np

from scripts.fx_coint.reversion_targets import compute_targets


def test_signed_fade_uses_forward_return_against_residual_sign():
    # 3 bars, 1 pair. lr[t] = oriented return completing at bar t.
    lr = np.array([[np.nan], [0.0010], [-0.0004]])
    residual = np.array([[np.nan], [0.0010], [-0.0004]])
    signed, absm = compute_targets(lr, residual)
    # at t=1: resid>0 -> fade short -> signed = -sign(+)*lr[2] = -1 * -0.0004 = +0.0004 -> +4 bps
    assert np.isclose(signed[1, 0], 4.0)
    assert np.isclose(absm[1, 0], 4.0)        # |lr[2]| in bps
    assert np.isnan(signed[2, 0])             # last bar has no forward return
```

- [ ] **Step 2: Run test, verify it fails**

Run: `uv run pytest tests/fx_coint/test_reversion_targets.py -q`
Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 3: Implement compute_targets**

```python
# scripts/fx_coint/reversion_targets.py
"""Forward fade target for the reversion null-test. Pure numpy."""

from __future__ import annotations

import numpy as np


def compute_targets(lr: np.ndarray, residual: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """lr, residual: (T, P) oriented returns / residuals, lr[t] completing at bar t.
    signed_fade[t] = -sign(residual[t]) * lr[t+1] * 1e4  (bps a fade earns, gross).
    abs_move[t]    = |lr[t+1]| * 1e4. Last row is NaN (no forward return)."""
    signed = np.full_like(lr, np.nan, dtype=float)
    absm = np.full_like(lr, np.nan, dtype=float)
    fwd = lr[1:]
    signed[:-1] = -np.sign(residual[:-1]) * fwd * 1e4
    absm[:-1] = np.abs(fwd) * 1e4
    return signed, absm
```

- [ ] **Step 4: Run test, verify pass**

Run: `uv run pytest tests/fx_coint/test_reversion_targets.py -q`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add scripts/fx_coint/reversion_targets.py tests/fx_coint/test_reversion_targets.py
git commit -m "feat(fx_coint): forward-fade targets (signed_fade, abs_move)"
```

---

### Task 4: Metrics — Spearman IC + closed-form ridge OOS

**Files:**
- Modify: `scripts/fx_coint/flow_metrics.py` (append two functions)
- Test: `tests/fx_coint/test_flow_metrics.py` (append)

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/fx_coint/test_flow_metrics.py
from scripts.fx_coint.flow_metrics import ridge_oos, spearman_ic


def test_spearman_ic_monotonic():
    x = np.arange(200.0)
    y = x ** 2  # monotonic increasing -> rank IC ~ 1
    ic, t, n = spearman_ic(x, y)
    assert ic > 0.99 and n == 200


def test_ridge_oos_recovers_linear_signal():
    rng = np.random.default_rng(0)
    X_is = rng.standard_normal((4000, 3))
    y_is = X_is[:, 0] * 0.8 + 0.1 * rng.standard_normal(4000)
    X_oos = rng.standard_normal((2000, 3))
    y_oos = X_oos[:, 0] * 0.8 + 0.1 * rng.standard_normal(2000)
    ic, r2, pred = ridge_oos(X_is, y_is, X_oos, y_oos, lam=10.0)
    assert ic > 0.9 and r2 > 0.7 and len(pred) == 2000


def test_ridge_oos_noise_gives_no_skill():
    rng = np.random.default_rng(1)
    X_is = rng.standard_normal((4000, 3))
    y_is = rng.standard_normal(4000)
    X_oos = rng.standard_normal((2000, 3))
    y_oos = rng.standard_normal(2000)
    ic, r2, _ = ridge_oos(X_is, y_is, X_oos, y_oos, lam=10.0)
    assert abs(ic) < 0.1 and r2 < 0.05
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `uv run pytest tests/fx_coint/test_flow_metrics.py -q`
Expected: FAIL (cannot import name `spearman_ic`).

- [ ] **Step 3: Implement the two functions**

```python
# append to scripts/fx_coint/flow_metrics.py
def spearman_ic(a: np.ndarray, b: np.ndarray) -> tuple[float, float, int]:
    """Rank IC over the finite intersection. Returns (ic, tstat, n)."""
    m = np.isfinite(a) & np.isfinite(b)
    a, b = a[m], b[m]
    if len(a) < 10:
        return (float("nan"), float("nan"), len(a))
    ra = np.argsort(np.argsort(a)).astype(float)
    rb = np.argsort(np.argsort(b)).astype(float)
    ic = float(np.corrcoef(ra, rb)[0, 1])
    t = ic * np.sqrt(len(a) - 2) / np.sqrt(max(1e-12, 1.0 - ic**2))
    return (ic, float(t), len(a))


def ridge_oos(X_is: np.ndarray, y_is: np.ndarray, X_oos: np.ndarray, y_oos: np.ndarray,
              lam: float = 10.0) -> tuple[float, float, np.ndarray]:
    """Standardise on IS, fit ridge (intercept unpenalised), eval OOS.
    Returns (oos_ic, oos_r2, oos_pred). NaN rows are dropped per split."""
    fi = np.isfinite(X_is).all(1) & np.isfinite(y_is)
    fo = np.isfinite(X_oos).all(1) & np.isfinite(y_oos)
    Xi, yi, Xo, yo = X_is[fi], y_is[fi], X_oos[fo], y_oos[fo]
    mu, sd = Xi.mean(0), Xi.std(0) + 1e-9
    Xi = np.column_stack([np.ones(len(Xi)), (Xi - mu) / sd])
    Xo = np.column_stack([np.ones(len(Xo)), (Xo - mu) / sd])
    pen = np.eye(Xi.shape[1])
    pen[0, 0] = 0.0
    w = np.linalg.solve(Xi.T @ Xi + lam * pen, Xi.T @ yi)
    pred = Xo @ w
    ic = float(np.corrcoef(pred, yo)[0, 1]) if len(yo) > 2 else float("nan")
    ss_tot = float(((yo - yo.mean()) ** 2).sum())
    r2 = float(1.0 - ((yo - pred) ** 2).sum() / ss_tot) if ss_tot > 0 else float("nan")
    return (ic, r2, pred)
```

- [ ] **Step 4: Run tests, verify pass**

Run: `uv run pytest tests/fx_coint/test_flow_metrics.py -q`
Expected: PASS (7 passed).

- [ ] **Step 5: Commit**

```bash
git add scripts/fx_coint/flow_metrics.py tests/fx_coint/test_flow_metrics.py
git commit -m "feat(fx_coint): spearman_ic + closed-form ridge_oos metrics"
```

---

### Task 5: The null-test runner

**Files:**
- Create: `scripts/fx_coint/reversion_conditioner_nulltest.py`

Orchestration; verified by running. Uses tested kernels.

- [ ] **Step 1: Implement the runner**

```python
# scripts/fx_coint/reversion_conditioner_nulltest.py
"""STEP 0 NULL-TEST: is a candidate fade trade's forward reversion (signed_fade)
predictable ex-ante from features OTHER than displacement size? Reports univariate
Spearman ICs vs signed_fade AND vs |move| (the decoy), IS/OOS, BH-FDR; a joint ridge
OOS IC/R²; and the top-decile predicted gross vs cost. No model selection, no strategy.

Usage: PYTHONPATH=. uv run python scripts/fx_coint/reversion_conditioner_nulltest.py
"""

from __future__ import annotations

import numpy as np
import polars as pl

from scripts.fx_coint.flow_metrics import bh_fdr, ridge_oos, spearman_ic
from scripts.fx_coint.flow_proxies import causal_zscore
from scripts.fx_coint.reversion_targets import compute_targets
from scripts.fx_coint.usd_factor_residual_probe import PAIRS
from scripts.fx_coint.usd_flow_factor import usd_factor_residual

K = 4
ZWIN = 16
IS_END = np.datetime64("2022-12-31")
COST = 0.70


def load() -> pl.DataFrame:
    df = None
    for s in PAIRS:
        d = pl.read_parquet(f"data/tick_bars/{s}_30m_feat.parquet").select(
            "bucket",
            pl.col("mid").alias(f"mid_{s}"),
            pl.col("rvol_bps").alias(f"rvol_{s}"),
            pl.col("spread_bps").alias(f"spr_{s}"),
            pl.col("n_ticks").cast(pl.Float64).alias(f"nt_{s}"),
            pl.col("flow_ofi").alias(f"fofi_{s}"),
            pl.col("flow_tick").alias(f"ftick_{s}"),
        )
        df = d if df is None else df.join(d, on="bucket", how="inner")
    return df.drop_nulls().sort("bucket")


def _shift(a: np.ndarray, k: int) -> np.ndarray:
    out = np.full_like(a, np.nan)
    out[k:] = a[:-k]
    return out


def _rollsum(a: np.ndarray, k: int) -> np.ndarray:
    c = np.cumsum(np.nan_to_num(a), axis=0)
    out = np.full_like(a, np.nan)
    out[k - 1:] = c[k - 1:] - np.vstack([np.zeros((1, a.shape[1])), c[:-k]])
    return out


def main() -> None:
    syms = list(PAIRS)
    df = load()
    signs = np.array([PAIRS[s] for s in syms], dtype=float)
    logmid = np.column_stack([np.log(df[f"mid_{s}"].to_numpy()) for s in syms])
    times = df["bucket"].to_numpy().astype("datetime64[D]")
    hours = df["bucket"].dt.hour().to_numpy().astype(float)
    dows = df["bucket"].dt.weekday().to_numpy().astype(float)
    T, P = logmid.shape

    lr = np.full((T, P), np.nan)
    lr[1:] = (logmid[1:] - logmid[:-1]) * signs[None, :]
    factor, residual = usd_factor_residual(np.nan_to_num(lr))
    factor[0] = np.nan
    residual[0] = np.nan
    signed, absm = compute_targets(lr, residual)

    is_mask = times <= IS_END
    cand = np.zeros((T, P), dtype=bool)
    for j in range(P):
        col = np.abs(residual[is_mask, j])
        thr = np.median(col[np.isfinite(col)])
        cand[:, j] = np.abs(residual[:, j]) >= thr

    nt = np.column_stack([df[f"nt_{s}"].to_numpy() for s in syms])
    feats: dict[str, np.ndarray] = {
        "abs_resid": np.abs(residual),
        "cum_resid": _rollsum(residual, K),
        "resid_speed": residual - _shift(residual, K),
        "rvol": np.column_stack([df[f"rvol_{s}"].to_numpy() for s in syms]),
        "spread": np.column_stack([df[f"spr_{s}"].to_numpy() for s in syms]),
        "n_ticks": nt,
        "nt_z": np.column_stack([causal_zscore(pl.Series(nt[:, j]), ZWIN).to_numpy() for j in range(P)]),
        "basket_disp": np.repeat(np.nansum(np.abs(residual), axis=1)[:, None], P, axis=1),
        "n_disloc": np.repeat(cand.sum(axis=1)[:, None].astype(float), P, axis=1),
        "factor_share": np.repeat(
            (np.abs(factor) / (np.abs(factor) + np.nanmean(np.abs(residual), axis=1) + 1e-12))[:, None], P, axis=1
        ),
        "flow_ofi": np.column_stack([df[f"fofi_{s}"].to_numpy() for s in syms]),
        "flow_tick": np.column_stack([df[f"ftick_{s}"].to_numpy() for s in syms]),
        "hour": np.repeat(hours[:, None], P, axis=1),
        "dow": np.repeat(dows[:, None], P, axis=1),
        "mom": _rollsum(lr, K),
    }
    names = list(feats)

    def pool(mask1d: np.ndarray, arr: np.ndarray) -> np.ndarray:
        sel = cand & mask1d[:, None] & np.isfinite(signed)
        return arr[sel]

    print(f"bars={T}  pairs={P}  IS<= {IS_END}  cost={COST}bps  "
          f"IS_cand={int((cand & is_mask[:, None] & np.isfinite(signed)).sum())}  "
          f"OOS_cand={int((cand & (~is_mask)[:, None] & np.isfinite(signed)).sum())}\n")
    print(f"  {'feature':12s} {'IC_signed_IS':>13s} {'IC_signed_OOS':>14s} {'IC_|move|_OOS':>14s}")

    pvals, labels = [], []
    for nm in names:
        ic_is, t_is, _ = spearman_ic(pool(is_mask, feats[nm]), pool(is_mask, signed))
        ic_oos, t_oos, _ = spearman_ic(pool(~is_mask, feats[nm]), pool(~is_mask, signed))
        ic_mag, _, _ = spearman_ic(pool(~is_mask, feats[nm]), pool(~is_mask, absm))
        pvals.append(__import__("math").erfc(abs(t_oos) / 2 ** 0.5) if np.isfinite(t_oos) else 1.0)
        labels.append(nm)
        print(f"  {nm:12s} {ic_is:>+13.4f} {ic_oos:>+14.4f} {ic_mag:>+14.4f}")

    rej = bh_fdr(np.array(pvals), alpha=0.05)
    print(f"\nBH-FDR @0.05 (signed-fade OOS): {int(rej.sum())}/{len(rej)} features significant: "
          f"{[labels[i] for i in range(len(rej)) if rej[i]]}")

    # joint ridge: stack features over candidates
    def matrix(mask1d: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        sel = cand & mask1d[:, None] & np.isfinite(signed)
        X = np.column_stack([feats[nm][sel] for nm in names])
        y = signed[sel]
        return X, y

    Xi, yi = matrix(is_mask)
    Xo, yo = matrix(~is_mask)
    ic, r2, pred = ridge_oos(Xi, yi, Xo, yo, lam=50.0)
    print(f"\nJOINT ridge (lam=50): OOS IC={ic:+.4f}  OOS R2={r2:+.5f}  n_oos={len(pred)}")

    # top-decile OOS by predicted signed-fade -> actual gross vs cost
    fo = np.isfinite(Xo).all(1) & np.isfinite(yo)
    yo_f = yo[fo]
    thr = np.quantile(pred, 0.90)
    top = pred >= thr
    print(f"  unconditional OOS gross: {yo_f.mean():+.3f} bps")
    print(f"  top-decile predicted gross: {yo_f[top].mean():+.3f} bps  (n={int(top.sum())})  vs cost {COST}")
    print(f"  -> {'CLEARS' if yo_f[top].mean() > COST else 'BELOW'} cost")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the null-test**

Run: `PYTHONPATH=. uv run python scripts/fx_coint/reversion_conditioner_nulltest.py`
Expected: a feature table (IC signed IS/OOS, IC |move| OOS), a BH-FDR line, the joint ridge OOS IC/R², and the top-decile gross-vs-cost line. No crash; finite numbers.

- [ ] **Step 3: Commit**

```bash
git add scripts/fx_coint/reversion_conditioner_nulltest.py
git commit -m "feat(fx_coint): reversion-conditioner null-test runner"
```

---

### Task 6: Report + gate verdict

**Files:**
- Create: `docs/analysis/fx_reversion_conditioner_nulltest.md`

- [ ] **Step 1: Capture results into the report**

Fill the bracketed values from the actual run:

```markdown
# FX reversion-conditioner null-test (Step 0 results)

**Question:** is a candidate fade trade's forward reversion (signed_fade) predictable
ex-ante from features other than displacement size?

## Setup
Honest 30m feature bars (aggregated from 1-min flow bars), 6 USD majors, 2018-2026.
USD-factor residual displacement; candidate = |residual| >= IS-median per pair; target
signed_fade = -sign(residual)*forward oriented return (bps), 1-bar hold. Features:
[list]. Spearman ICs vs signed_fade AND vs |move|, IS (<=2022) / OOS; BH-FDR; joint
closed-form ridge OOS IC/R²; top-decile predicted gross vs 0.70 bps cost.

## Univariate ICs
[paste feature table]

## Magnitude vs signed (the guard)
[note which features predict |move| (OOS) but NOT signed_fade — the decoys]

## Joint ridge
OOS IC = [..], OOS R² = [..]; top-decile gross [..] bps vs 0.70 cost.

## Verdict
[PROCEED to walk-forward selection model if signed_fade predictable OOS (FDR-sig or
joint OOS R²>0) AND top-decile gross approaches/exceeds cost; else STOP (NO-GO),
stating that magnitude was/wasn't predictable while direction was not.]
```

- [ ] **Step 2: Write the gate verdict** explicitly per the spec thresholds, with the numbers that drove it.

- [ ] **Step 3: Run the full fx_coint suite**

Run: `uv run pytest tests/fx_coint/ -q`
Expected: all green.

- [ ] **Step 4: Run the quality gate**

Run: `make quality`
Expected: `✅ All quality checks complete`.

- [ ] **Step 5: Commit**

```bash
git add docs/analysis/fx_reversion_conditioner_nulltest.md
git commit -m "docs(fx_coint): reversion-conditioner null-test results + verdict"
```

---

## Self-review

**Spec coverage:**
- 30m honest bars + features aggregated from 1-min flow bars → Tasks 1, 2. USD-factor
  residual displacement + candidate mask (|residual| ≥ IS-median) → Task 5. Targets
  signed_fade + abs_move → Task 3. Univariate Spearman ICs (signed vs magnitude, IS/OOS)
  + BH-FDR → Tasks 4, 5. Joint ridge OOS IC/R² + top-quantile gross-vs-cost → Tasks 4, 5.
  Report + gate verdict → Task 6. Covered.
- Spec mentioned "mutual information" and "shallow GBM"; simplified to Spearman rank-IC
  (captures monotonic predictability) + closed-form ridge (no sklearn dependency). This
  is the intentionally minimal, dependency-light first cut; GBM/MI are a follow-up only
  if the linear/rank test shows life (YAGNI). Noted in the report.

**Placeholder scan:** Tasks 1–5 contain complete code. Task 6's bracketed values are
run-output transcription (results don't exist until the runner runs), with explicit
structure and the decision rule spelled out.

**Type consistency:** `aggregate_30m` emits `mid/bid/ask/n_ticks/flow_tick/flow_ofi/rvol_bps/spread_bps/bucket`;
the runner's `load()` reads exactly those. `compute_targets(lr, residual) -> (signed, absm)`,
`spearman_ic -> (ic,t,n)`, `ridge_oos -> (ic,r2,pred)`, `bh_fdr -> mask` — all matched at
call sites. `usd_factor_residual` and `causal_zscore` reused with their existing
signatures. `PAIRS` from the existing probe module.
```
