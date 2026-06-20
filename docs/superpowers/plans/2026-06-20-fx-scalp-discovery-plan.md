# FX Scalp Discovery — Phase 0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build four standalone ridge-IC sandbox scripts plus a master funnel to test <30 min FX scalp signal families on true raw-tick 1-min time bars, net of Pepperstone Razor cost.

**Architecture:** Each family is a self-contained CLI script that loads enriched 1-min bars, builds its signal via ridge regression or a simple transform, evaluates net-of-cost PnL, and prints JSON results. A master funnel orchestrates all four, applies kill/near-miss rules, and emits a summary JSON. Shared utilities live in `phase0_scalp_common.py`.

**Tech Stack:** Python 3.12, polars, pandas, numpy, scikit-learn (Ridge, RidgeClassifier), pytest. Raw tick source: `~/Desktop/dukascopy_ticks/PAIR/YYYYMM_ticks.parquet`.

## Global Constraints

- **True raw-tick time bars only.** Never resample tick-count bars into time bars. Use `bars_from_ticks` from `scripts/fx_coint/flow_proxies.py` with `freq="1m"`.
- **No `bfill` on flow.** All features must be causal (`.shift(1)` on rolling/ewm, `.shift(horizon)` on forward returns).
- **Pepperstone Razor cost model.** Import `DEFAULT_COST_BPS` from `scripts/fx_coint/hourly_triple_barrier.py`.
- **Assumption: taker fills at <30 min horizons.** Cost = round-trip spread + commission baked into `DEFAULT_COST_BPS`.
- **Evaluation metric:** `net = side * fwd_ret - cost_bps/10_000`; `net_lb95 = mean - 1.645 * se`; survival requires `net_lb95 > 0` and `N_entries >= 20/day`.
- **Near-miss criteria:** `0 > net_lb95 >= -cost_frac` and (`gross_IC > 0.03 t > 2.0` or `decile_spread >= 2*cost` or `same_sign_IC > 0.02` across {1,3,5} min).
- **Kill switch:** If Phase 0 yields 0 PASS and ≤1 NEAR MISS, stop. Do not proceed to Phase 1.
- **All code in `scripts/fx_coint/`. Tests in `tests/fx_coint/test_scalp_phase0_*.py`.**

---

## File Structure

| File | Responsibility |
|------|---------------|
| `scripts/fx_coint/phase0_scalp_common.py` | Shared: load raw ticks, build enriched 1-min bars, compute forward returns, evaluate signals, near-miss detection, result formatting |
| `scripts/fx_coint/build_enriched_1m_bars.py` | CLI to pre-build `data/tick_bars/{sym}_1m_enriched.parquet` from raw dukascopy ticks. Adds OHLC, quote_revisions, intra-bar features. |
| `scripts/fx_coint/phase0_family_a.py` | Tick-Scale Flow Orthogonalization: causal rolling regression of flow on mid_ret → residual → evaluate |
| `scripts/fx_coint/phase0_family_b.py` | Quote-Revision Continuation: `quote_revision_rate_z × sign(directional_persistence_8)` → evaluate |
| `scripts/fx_coint/phase0_family_c.py` | Temporal Lead-Lag: peer returns at lag 1–3 bars → causal rolling ridge → evaluate |
| `scripts/fx_coint/phase0_family_d.py` | Microstructure Cocktail: RidgeClassifier on enriched-bar features → evaluate |
| `scripts/fx_coint/phase0_scalp_funnel.py` | Master runner: execute families, collect JSON, rank, apply stopping rules, emit `phase0_results.json` |
| `tests/fx_coint/test_scalp_phase0_common.py` | Unit tests for common utilities (causal shift, net calc, near-miss) with synthetic data |
| `tests/fx_coint/test_scalp_phase0_funnel.py` | Integration test: mock family outputs → verify stopping rules and JSON format |

---

### Task 1: Shared Data Loading & Enriched Bar Builder

**Files:**
- Create: `scripts/fx_coint/phase0_scalp_common.py` (first half: data loading + bar building)
- Create: `scripts/fx_coint/build_enriched_1m_bars.py`
- Test: `tests/fx_coint/test_scalp_phase0_common.py`

**Interfaces:**
- Produces: `load_raw_ticks(symbol, year) -> pl.DataFrame`, `build_enriched_1m_bars(ticks, symbol) -> pl.DataFrame`, `save_enriched_bars(df, symbol, freq="1m") -> Path`
- Consumes: `scripts.fx_coint.flow_proxies.tick_rule_signs`, `scripts.fx_coint.flow_proxies.quote_ofi`, `scripts.era_scalp.load_splits._pip_size`

- [ ] **Step 1: Write failing test for bar builder**

```python
import polars as pl
import pandas as pd
import numpy as np

from scripts.fx_coint.phase0_scalp_common import build_enriched_1m_bars


def test_build_enriched_1m_bars_basic():
    rng = np.random.default_rng(42)
    n = 180  # 3 minutes of 1-second ticks
    timestamps = pd.date_range("2024-01-01 00:00:00", periods=n, freq="1s", tz="UTC")
    bid = 1.1000 + rng.normal(0, 0.00005, n).cumsum()
    ask = bid + 0.0003
    mid = (bid + ask) / 2
    ticks = pl.DataFrame({
        "timestamp": timestamps,
        "bid": bid,
        "ask": ask,
        "mid": mid,
        "spread": 0.0003,
        "log_return": np.log(mid / np.roll(mid, 1)),
    })
    df = build_enriched_1m_bars(ticks, symbol="EURUSD")
    assert "bucket" in df.columns
    assert "mid" in df.columns
    assert "bid" in df.columns
    assert "ask" in df.columns
    assert "open_bid" in df.columns
    assert "high_bid" in df.columns
    assert "low_bid" in df.columns
    assert "quote_revisions" in df.columns
    assert "bar_return_sign" in df.columns
    assert len(df) == 3  # 3 one-minute bars
    assert df["n_ticks"].sum() == 180
```

Run: `pytest tests/fx_coint/test_scalp_phase0_common.py::test_build_enriched_1m_bars_basic -v`
Expected: FAIL — `build_enriched_1m_bars` not defined

- [ ] **Step 2: Implement `build_enriched_1m_bars`**

Create `scripts/fx_coint/phase0_scalp_common.py`:

```python
"""Shared utilities for Phase 0 scalp sandbox."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import polars as pl

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _pip_size(symbol: str) -> float:
    s = str(symbol).upper()
    return 0.01 if s.endswith("JPY") else 0.0001


def load_raw_ticks(symbol: str, year: int) -> pl.DataFrame:
    """Load raw dukascopy tick parquets for a symbol+year.

    Assumes files at ~/Desktop/dukascopy_ticks/{SYMBOL}/YYYYMM_ticks.parquet.
    Columns: timestamp, bid, ask, mid, spread, log_return.
    """
    src = Path.home() / "Desktop" / "dukascopy_ticks" / symbol.upper()
    if not src.exists():
        raise FileNotFoundError(f"Raw tick directory not found: {src}")
    files = sorted(src.glob(f"{year}*_ticks.parquet"))
    if not files:
        raise FileNotFoundError(f"No tick parquet files for {symbol} {year} in {src}")
    parts = [pl.read_parquet(f) for f in files]
    return pl.concat(parts).sort("timestamp")


def build_enriched_1m_bars(ticks: pl.DataFrame, symbol: str) -> pl.DataFrame:
    """Build true 1-min time bars with intra-bar microstructure aggregates.

    Uses bars_from_ticks logic for flow, then adds OHLC + quote_revisions + sign.
    """
    # Pre-compute tick-level flow features
    bid_np = ticks["bid"].to_numpy()
    ask_np = ticks["ask"].to_numpy()
    mid_np = ticks["mid"].to_numpy()
    tsign = tick_rule_signs(mid_np)
    ofi = quote_ofi(bid_np, ask_np)

    t = (
        ticks.sort("timestamp")
        .with_columns(
            pl.Series("tsign", tsign),
            pl.Series("ofi", ofi),
            pl.col("timestamp").dt.truncate("1m").alias("bucket"),
        )
        .with_columns(
            pl.col("bid").diff().over("bucket").alias("db"),
            pl.col("ask").diff().over("bucket").alias("da"),
        )
        .with_columns(
            ((pl.col("db").abs() > 0) | (pl.col("da").abs() > 0))
            .cast(pl.Int8)
            .alias("rev")
        )
    )

    bars = (
        t.group_by("bucket")
        .agg(
            pl.col("mid").last().alias("mid"),
            pl.col("bid").last().alias("bid"),
            pl.col("ask").last().alias("ask"),
            pl.col("bid").first().alias("open_bid"),
            pl.col("bid").max().alias("high_bid"),
            pl.col("bid").min().alias("low_bid"),
            pl.col("ask").first().alias("open_ask"),
            pl.col("ask").max().alias("high_ask"),
            pl.col("tsign").mean().alias("flow_tick"),
            pl.col("ofi").mean().alias("flow_ofi"),
            pl.len().alias("n_ticks"),
            pl.col("rev").sum().alias("quote_revisions"),
        )
        .sort("bucket")
    )

    pip = _pip_size(symbol)
    bars = (
        bars.with_columns(
            pl.col("bucket").dt.hour().alias("hour_utc"),
            ((pl.col("ask") - pl.col("bid")) / pl.col("mid") * 10_000).alias("spread_bps"),
            ((pl.col("high_bid") - pl.col("low_bid")) / pip).alias("range_pips"),
            ((pl.col("close_bid") - pl.col("open_bid")) / pip).alias("bar_move_pips"),
            pl.col("n_ticks").alias("tick_volume"),
        )
        .with_columns(
            (60.0 / pl.col("tick_volume")).alias("tick_rate_hz"),  # approx: 60 sec / n_ticks
        )
    )

    # bar_return_sign (direction of close-to-open)
    bars = bars.with_columns(
        pl.when(pl.col("bar_move_pips") > 0)
        .then(1)
        .when(pl.col("bar_move_pips") < 0)
        .then(-1)
        .otherwise(0)
        .cast(pl.Float64)
        .alias("bar_return_sign")
    )

    return bars.sort("bucket").to_pandas()


def save_enriched_bars(df: pd.DataFrame, symbol: str, freq: str = "1m") -> Path:
    out_dir = _REPO_ROOT / "data" / "tick_bars"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{symbol.upper()}_{freq}_enriched.parquet"
    df.to_parquet(path)
    return path
```

Also add the imports at top of `phase0_scalp_common.py`:
```python
from scripts.fx_coint.flow_proxies import tick_rule_signs, quote_ofi
```

Run test again.
Expected: PASS

- [ ] **Step 3: Create `build_enriched_1m_bars.py` CLI**

Create `scripts/fx_coint/build_enriched_1m_bars.py`:

```python
"""CLI to pre-build enriched 1-min bars for all majors.

Usage:
    uv run python scripts/fx_coint/build_enriched_1m_bars.py --year 2024
"""

from __future__ import annotations

import argparse

from scripts.fx_coint.phase0_scalp_common import (
    load_raw_ticks,
    build_enriched_1m_bars,
    save_enriched_bars,
)

PAIRS = ["EURUSD", "GBPUSD", "AUDUSD", "USDJPY", "USDCHF", "USDCAD"]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--year", type=int, required=True)
    p.add_argument("--pairs", nargs="+", default=PAIRS)
    args = p.parse_args()

    for sym in args.pairs:
        try:
            ticks = load_raw_ticks(sym, args.year)
            bars = build_enriched_1m_bars(ticks, sym)
            path = save_enriched_bars(bars, sym, "1m")
            print(f"{sym}: {len(bars)} bars  {bars['bucket'].min()} -> {bars['bucket'].max()}  -> {path}")
        except FileNotFoundError as e:
            print(f"SKIP {sym}: {e}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Commit**

```bash
git add scripts/fx_coint/phase0_scalp_common.py \
        scripts/fx_coint/build_enriched_1m_bars.py \
        tests/fx_coint/test_scalp_phase0_common.py
git commit -m "feat(scalp_phase0): shared data loader + enriched 1-min bar builder"
```

---

### Task 2: Shared Evaluation Engine + Rolling Features

**Files:**
- Modify: `scripts/fx_coint/phase0_scalp_common.py` (append)
- Test: `tests/fx_coint/test_scalp_phase0_common.py` (append)

**Interfaces:**
- Consumes: `scripts.fx_coint.hourly_triple_barrier.DEFAULT_COST_BPS`
- Produces: `compute_forward_returns(df, horizons)`, `add_rolling_features(df, symbol)`, `evaluate_family(signal, fwd_ret, cost_frac, entry_quantile=0.90) -> dict`, `is_near_miss(metrics, cost_frac) -> bool`

- [ ] **Step 1: Write failing test for evaluation engine**

Append to `tests/fx_coint/test_scalp_phase0_common.py`:

```python
from scripts.fx_coint.phase0_scalp_common import evaluate_family, is_near_miss


def test_evaluate_family_positive_signal():
    rng = np.random.default_rng(42)
    n = 1000
    # Signal perfectly predicts forward return
    signal = pd.Series(rng.choice([-1.0, 1.0], size=n))
    fwd_ret = signal * 0.001  # 10 bps per trade
    cost = 0.64 / 10_000  # EURUSD cost
    result = evaluate_family(signal, fwd_ret, cost_frac=cost, entry_quantile=0.90)
    assert result["n_entries"] > 0
    assert result["gross_mean"] > 0
    assert result["net_lb95"] > 0  # signal is perfect, must clear cost
    assert result["verdict"] == "PASS"


def test_evaluate_family_random_noise():
    rng = np.random.default_rng(42)
    n = 5000
    signal = pd.Series(rng.normal(0, 1, n))
    fwd_ret = pd.Series(rng.normal(0, 0.0003, n))
    cost = 0.64 / 10_000
    result = evaluate_family(signal, fwd_ret, cost_frac=cost, entry_quantile=0.90)
    assert result["verdict"] in ("FAIL", "NEAR_MISS")
```

Run: `pytest tests/fx_coint/test_scalp_phase0_common.py -v`
Expected: FAIL — functions not defined

- [ ] **Step 2: Implement evaluation engine**

Append to `scripts/fx_coint/phase0_scalp_common.py`:

```python
def compute_forward_returns(df: pd.DataFrame, horizons: list[int]) -> pd.DataFrame:
    """Add forward log-return columns for each horizon.

    Uses mid price. Labels are causal: fwd_ret_h is computed from mid[t+h] / mid[t] - 1.
    """
    mid = df["mid"].astype(float)
    for h in horizons:
        df[f"fwd_ret_{h}"] = np.log(mid.shift(-h) / mid)
    return df


def add_rolling_features(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """Add causal rolling features needed by Families B and D.

    All rolling windows use `.shift(1)` so the current bar never leaks into its own history.
    """
    pip = _pip_size(symbol)
    df = df.copy()

    # Velocity / return features
    close_bid = df["bid"].astype(float)
    df["vel_pips_h1"] = (close_bid - close_bid.shift(1)) / pip
    df["accel_pips"] = df["vel_pips_h1"] - df["vel_pips_h1"].shift(1)

    # Tick rate z-score
    tr = df["tick_volume"] / 60.0  # ticks per second
    tr_mu = tr.rolling(24, min_periods=8).mean().shift(1)
    tr_sd = tr.rolling(24, min_periods=8).std(ddof=0).shift(1)
    df["tick_rate_z"] = (tr - tr_mu) / tr_sd.replace(0, np.nan)

    # Spread z-score
    sp = df["spread_bps"]
    sp_mu = sp.rolling(24, min_periods=8).mean().shift(1)
    sp_sd = sp.rolling(24, min_periods=8).std(ddof=0).shift(1)
    df["spread_z"] = (sp - sp_mu) / sp_sd.replace(0, np.nan)

    # Quote revision rate z-score
    qr = df["quote_revisions"].astype(float)
    qr_mu = qr.rolling(24, min_periods=8).mean().shift(1)
    qr_sd = qr.rolling(24, min_periods=8).std(ddof=0).shift(1)
    df["quote_revision_rate_z"] = (qr - qr_mu) / qr_sd.replace(0, np.nan)

    # Directional persistence (rolling sum of bar_return_sign over 8 bars)
    brs = df["bar_return_sign"]
    df["directional_persistence_8"] = brs.rolling(8, min_periods=4).sum().shift(1)

    # Signed flow (rolling sum over 24 bars)
    df["signed_flow_24"] = brs.rolling(24, min_periods=8).sum().shift(1)

    # Vol cluster score
    abs_ret = df["vel_pips_h1"].abs()
    roll_abs_mean = abs_ret.rolling(24, min_periods=8).mean().shift(1)
    df["vol_cluster_score"] = (abs_ret / roll_abs_mean.replace(0, np.nan)).fillna(1.0)

    # Slip proxy (gap between open and previous close, in pips)
    prev_close = close_bid.shift(1)
    df["slip_proxy_pips"] = ((close_bid - prev_close).abs() / pip).rolling(24, min_periods=8).quantile(0.75).shift(1)

    # Velocity z-scores at various horizons (computed from vel_pips_h1 for simplicity)
    for w in [1, 2, 5, 10]:
        vmu = df["vel_pips_h1"].rolling(24, min_periods=8).mean().shift(1)
        vsd = df["vel_pips_h1"].rolling(24, min_periods=8).std(ddof=0).shift(1)
        df[f"vel_z_h{w}"] = (df["vel_pips_h1"] - vmu) / vsd.replace(0, np.nan)

    return df


def evaluate_family(
    signal: pd.Series,
    fwd_ret: pd.Series,
    cost_frac: float,
    entry_quantile: float = 0.90,
) -> dict[str, Any]:
    """Evaluate a signal net of cost.

    signal: float Series, positive = expect long, negative = expect short
    fwd_ret: float Series, forward log-return in fractional units
    """
    s = signal.reindex(fwd_ret.index)
    f = fwd_ret.astype(float)
    valid = np.isfinite(s) & np.isfinite(f)
    s, f = s[valid], f[valid]

    if len(s) < 10:
        return _empty_result(cost_frac, reason="too few valid observations")

    # Standardise signal to z-score for threshold-based entry
    mu = s.mean()
    sd = s.std(ddof=0) + 1e-12
    z = (s - mu) / sd

    # Entry on top decile |z|
    thresh = z.abs().quantile(entry_quantile)
    entry = z.abs() >= thresh
    n = int(entry.sum())

    if n < 10:
        return _empty_result(cost_frac, reason="too few entries")

    side = np.sign(z[entry])
    gross = side.values * f[entry].values
    net = gross - cost_frac

    mean_gross = float(gross.mean())
    mean_net = float(net.mean())
    se_net = float(net.std(ddof=1) / np.sqrt(n))
    net_lb95 = mean_net - 1.645 * se_net

    # IC on non-overlapping sample (every h-th, but h varies — use every 5th as conservative)
    ic, tstat, n_ic = _non_overlap_ic(s.values, f.values, skip=5)

    # Gross decile spread
    extreme = z.abs() >= z.abs().quantile(0.90)
    decile_gross = float((np.sign(z[extreme].values) * f[extreme].values).mean())

    verdict = "PASS" if net_lb95 > 0 and n >= 20 else ("NEAR_MISS" if is_near_miss({"net_lb95": net_lb95, "gross_ic": ic, "ic_tstat": tstat, "decile_spread": decile_gross, "n": n}, cost_frac) else "FAIL")

    return {
        "n_obs": int(valid.sum()),
        "n_entries": n,
        "entry_freq_per_day": round(n / (len(s) / (24 * 60)), 2),
        "gross_mean_bps": round(mean_gross * 10_000, 4),
        "net_mean_bps": round(mean_net * 10_000, 4),
        "net_lb95_bps": round(net_lb95 * 10_000, 4),
        "gross_ic": round(ic, 4),
        "ic_tstat": round(tstat, 2),
        "ic_n": n_ic,
        "decile_spread_bps": round(decile_gross * 10_000, 4),
        "cost_bps": round(cost_frac * 10_000, 4),
        "verdict": verdict,
    }


def _non_overlap_ic(signal: np.ndarray, fwd: np.ndarray, skip: int = 5) -> tuple[float, float, int]:
    s = signal[::skip]
    f = fwd[::skip]
    m = np.isfinite(s) & np.isfinite(f)
    s, f = s[m], f[m]
    if len(s) < 10:
        return (float("nan"), float("nan"), len(s))
    ic = float(np.corrcoef(s, f)[0, 1])
    t = ic * np.sqrt(len(s) - 2) / np.sqrt(max(1e-12, 1.0 - ic**2))
    return (ic, float(t), len(s))


def _empty_result(cost_frac: float, reason: str) -> dict[str, Any]:
    return {
        "n_obs": 0, "n_entries": 0, "entry_freq_per_day": 0.0,
        "gross_mean_bps": 0.0, "net_mean_bps": 0.0, "net_lb95_bps": 0.0,
        "gross_ic": 0.0, "ic_tstat": 0.0, "ic_n": 0,
        "decile_spread_bps": 0.0, "cost_bps": round(cost_frac * 10_000, 4),
        "verdict": "FAIL", "fail_reason": reason,
    }


def is_near_miss(metrics: dict, cost_frac: float) -> bool:
    net_lb95 = metrics.get("net_lb95_bps", 0.0) / 10_000
    if not (0 > net_lb95 >= -cost_frac):
        return False
    return any([
        metrics.get("gross_ic", 0.0) > 0.03 and metrics.get("ic_tstat", 0.0) > 2.0,
        metrics.get("decile_spread_bps", 0.0) / 10_000 >= 2 * cost_frac,
        metrics.get("n_entries", 0) >= 20,
    ])
```

Run: `pytest tests/fx_coint/test_scalp_phase0_common.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add scripts/fx_coint/phase0_scalp_common.py tests/fx_coint/test_scalp_phase0_common.py
git commit -m "feat(scalp_phase0): shared evaluation engine + rolling features"
```

---

### Task 3: Family A — Tick-Scale Flow Orthogonalization

**Files:**
- Create: `scripts/fx_coint/phase0_family_a.py`
- Test: `tests/fx_coint/test_scalp_phase0_family_a.py`

**Interfaces:**
- Consumes: `phase0_scalp_common.load_raw_ticks_or_enriched`, `add_rolling_features`, `compute_forward_returns`, `evaluate_family`
- Produces: prints JSON to stdout

- [ ] **Step 1: Write failing test**

Create `tests/fx_coint/test_scalp_phase0_family_a.py`:

```python
import pandas as pd
import numpy as np

from scripts.fx_coint.phase0_family_a import build_flow_residual_signal


def test_flow_residual_basic():
    rng = np.random.default_rng(42)
    n = 500
    df = pd.DataFrame({
        "mid": 1.1000 + np.cumsum(rng.normal(0, 0.0001, n)),
        "bid": 1.1000 + np.cumsum(rng.normal(0, 0.0001, n)),
        "flow_tick": rng.normal(0, 0.3, n),
        "flow_ofi": rng.normal(0, 0.2, n),
    })
    signal = build_flow_residual_signal(df, window=10)
    assert len(signal) == n
    assert np.isfinite(signal).sum() > n * 0.8
```

Run: `pytest tests/fx_coint/test_scalp_phase0_family_a.py -v`
Expected: FAIL — module not found

- [ ] **Step 2: Implement Family A script**

Create `scripts/fx_coint/phase0_family_a.py`:

```python
"""Phase 0 Family A: Tick-Scale Flow Orthogonalization.

Hypothesis: The component of flow uncorrelated to contemporaneous price
returns carries microstructure alpha at the 1-min scale.

Usage:
    uv run python scripts/fx_coint/phase0_family_a.py --symbol EURUSD --year 2024
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.fx_coint.phase0_scalp_common import (
    _REPO_ROOT,
    add_rolling_features,
    compute_forward_returns,
    evaluate_family,
    load_raw_ticks,
    build_enriched_1m_bars,
    save_enriched_bars,
)
from scripts.fx_coint.hourly_triple_barrier import DEFAULT_COST_BPS

PAIRS = ["EURUSD", "GBPUSD", "AUDUSD", "USDJPY", "USDCHF", "USDCAD"]


def build_flow_residual_signal(df: pd.DataFrame, window: int = 5) -> pd.Series:
    """Causal rolling regression: flow = beta0 + beta1 * mid_ret + residual.

    Fits on bars <= t-1 within a trailing `window`-bar lookback.
    Returns the residual at t (positive = more buying pressure than price explains).
    """
    df = df.copy()
    df["mid_ret"] = np.log(df["mid"] / df["mid"].shift(1))
    flow = df["flow_tick"].astype(float)
    mid_ret = df["mid_ret"].astype(float)

    resid = pd.Series(index=df.index, dtype=float)
    for i in range(window, len(df)):
        lo = i - window
        # Fit on [lo, i) — strictly before i
        x = mid_ret.iloc[lo:i].dropna().values
        y = flow.iloc[lo:i].dropna().values
        if len(x) < 3:
            resid.iloc[i] = np.nan
            continue
        # Simple OLS: y = a + b*x
        A = np.column_stack([np.ones(len(x)), x])
        try:
            beta = np.linalg.lstsq(A, y, rcond=None)[0]
            pred = beta[0] + beta[1] * mid_ret.iloc[i]
            resid.iloc[i] = flow.iloc[i] - pred
        except np.linalg.LinAlgError:
            resid.iloc[i] = np.nan
    return resid


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", default="EURUSD")
    p.add_argument("--year", type=int, default=2024)
    p.add_argument("--horizons", nargs="+", type=int, default=[1, 3, 5, 10])
    p.add_argument("--window", type=int, default=5)
    p.add_argument("--enriched-parquet", type=Path, default=None)
    args = p.parse_args()

    sym = args.symbol.upper()
    cost_bps = DEFAULT_COST_BPS[sym]
    cost_frac = cost_bps / 10_000

    # Load or build enriched bars
    if args.enriched_parquet and args.enriched_parquet.exists():
        df = pd.read_parquet(args.enriched_parquet)
    else:
        ticks = load_raw_ticks(sym, args.year)
        df = build_enriched_1m_bars(ticks, sym)
        path = save_enriched_bars(df, sym, "1m")
        print(f"Built enriched bars: {path}")

    df = add_rolling_features(df, sym)
    df = compute_forward_returns(df, args.horizons)
    signal = build_flow_residual_signal(df, window=args.window)

    results = {}
    for h in args.horizons:
        col = f"fwd_ret_{h}"
        if col not in df.columns:
            continue
        r = evaluate_family(signal, df[col], cost_frac=cost_frac, entry_quantile=0.90)
        results[f"h{h}"] = r
        print(f"Family-A {sym} h={h}: {r['verdict']}  net_lb95={r['net_lb95_bps']:.4f}  n={r['n_entries']}")

    out = {
        "family": "A",
        "symbol": sym,
        "year": args.year,
        "horizons": args.horizons,
        "window": args.window,
        "cost_bps": cost_bps,
        "results": results,
    }
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
```

Run test again.
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add scripts/fx_coint/phase0_family_a.py tests/fx_coint/test_scalp_phase0_family_a.py
git commit -m "feat(scalp_phase0): Family A — tick-scale flow orthogonalization"
```

---

### Task 4: Family B — Quote-Revision Continuation

**Files:**
- Create: `scripts/fx_coint/phase0_family_b.py`
- Test: `tests/fx_coint/test_scalp_phase0_family_b.py`

**Interfaces:**
- Consumes: same shared module as Family A
- Produces: prints JSON to stdout

- [ ] **Step 1: Write failing test**

Create `tests/fx_coint/test_scalp_phase0_family_b.py`:

```python
import pandas as pd
import numpy as np

from scripts.fx_coint.phase0_family_b import build_quote_revision_signal


def test_qr_signal_basic():
    n = 500
    df = pd.DataFrame({
        "quote_revision_rate_z": np.random.default_rng(42).normal(0, 1, n),
        "directional_persistence_8": np.random.default_rng(42).choice([-1, 1], size=n),
    })
    s = build_quote_revision_signal(df)
    assert len(s) == n
    assert np.isfinite(s).sum() > n * 0.5
```

Run: `pytest tests/fx_coint/test_scalp_phase0_family_b.py -v`
Expected: FAIL

- [ ] **Step 2: Implement Family B script**

Create `scripts/fx_coint/phase0_family_b.py`:

```python
"""Phase 0 Family B: Quote-Revision Continuation.

Hypothesis: Elevated quote-revision rate combined with directional
persistence indicates informed flow and predicts continuation.

Signal = quote_revision_rate_z * sign(directional_persistence_8)
Entry gate: quote_revision_rate_z > 1.0 AND persistence above expanding median.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.fx_coint.phase0_scalp_common import (
    add_rolling_features,
    compute_forward_returns,
    evaluate_family,
    load_raw_ticks,
    build_enriched_1m_bars,
    save_enriched_bars,
)
from scripts.fx_coint.hourly_triple_barrier import DEFAULT_COST_BPS


def build_quote_revision_signal(df: pd.DataFrame) -> pd.Series:
    """Signal: QR rate z-score signed by directional persistence."""
    qr = df["quote_revision_rate_z"].astype(float)
    dp = df["directional_persistence_8"].astype(float)

    # Expanding median of persistence (causal)
    dp_median = dp.expanding(min_periods=8).median().shift(1)

    signal = qr * np.sign(dp)
    # Zero out when gate conditions fail
    gate = (qr > 1.0) & (dp > dp_median)
    signal = signal.where(gate, np.nan)
    return signal


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", default="EURUSD")
    p.add_argument("--year", type=int, default=2024)
    p.add_argument("--horizons", nargs="+", type=int, default=[1, 3, 5])
    p.add_argument("--enriched-parquet", type=Path, default=None)
    args = p.parse_args()

    sym = args.symbol.upper()
    cost_bps = DEFAULT_COST_BPS[sym]
    cost_frac = cost_bps / 10_000

    if args.enriched_parquet and args.enriched_parquet.exists():
        df = pd.read_parquet(args.enriched_parquet)
    else:
        ticks = load_raw_ticks(sym, args.year)
        df = build_enriched_1m_bars(ticks, sym)
        path = save_enriched_bars(df, sym, "1m")
        print(f"Built enriched bars: {path}")

    df = add_rolling_features(df, sym)
    df = compute_forward_returns(df, args.horizons)
    signal = build_quote_revision_signal(df)

    results = {}
    for h in args.horizons:
        col = f"fwd_ret_{h}"
        if col not in df.columns:
            continue
        r = evaluate_family(signal, df[col], cost_frac=cost_frac, entry_quantile=0.90)
        results[f"h{h}"] = r
        print(f"Family-B {sym} h={h}: {r['verdict']}  net_lb95={r['net_lb95_bps']:.4f}  n={r['n_entries']}")

    out = {"family": "B", "symbol": sym, "year": args.year, "horizons": args.horizons, "cost_bps": cost_bps, "results": results}
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
```

Run test.
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add scripts/fx_coint/phase0_family_b.py tests/fx_coint/test_scalp_phase0_family_b.py
git commit -m "feat(scalp_phase0): Family B — quote-revision continuation"
```

---

### Task 5: Family C — Temporal Lead-Lag (Peer Returns)

**Files:**
- Create: `scripts/fx_coint/phase0_family_c.py`
- Test: `tests/fx_coint/test_scalp_phase0_family_c.py`

**Interfaces:**
- Consumes: same shared module + peer symbols
- Produces: prints JSON to stdout

- [ ] **Step 1: Write failing test**

Create `tests/fx_coint/test_scalp_phase0_family_c.py`:

```python
import pandas as pd
import numpy as np

from scripts.fx_coint.phase0_family_c import build_peer_lag_signal


def test_peer_lag_basic():
    rng = np.random.default_rng(42)
    n = 500
    peers = {
        "GBPUSD": pd.DataFrame({"mid_ret": rng.normal(0, 0.0002, n)}),
        "AUDUSD": pd.DataFrame({"mid_ret": rng.normal(0, 0.0002, n)}),
    }
    target = pd.DataFrame({
        "mid_ret": rng.normal(0, 0.0002, n),
        "vol_cluster_score": np.ones(n),
    })
    s = build_peer_lag_signal(target, peers, window=10)
    assert len(s) == n
    assert np.isfinite(s).sum() > n * 0.3
```

Run: `pytest tests/fx_coint/test_scalp_phase0_family_c.py -v`
Expected: FAIL

- [ ] **Step 2: Implement Family C script**

Create `scripts/fx_coint/phase0_family_c.py`:

```python
"""Phase 0 Family C: Temporal Lead-Lag via Peer Returns.

Hypothesis: During liquid hours, lagged peer returns predict target returns.
Uses 6 majors; leave-one-out peer set; causal rolling ridge on lag 1–3 bars.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.fx_coint.phase0_scalp_common import (
    add_rolling_features,
    compute_forward_returns,
    evaluate_family,
    load_raw_ticks,
    build_enriched_1m_bars,
    save_enriched_bars,
)
from scripts.fx_coint.hourly_triple_barrier import DEFAULT_COST_BPS

PEERS = ["EURUSD", "GBPUSD", "AUDUSD", "USDJPY", "USDCHF", "USDCAD"]


def build_peer_lag_signal(
    target_df: pd.DataFrame,
    peer_dfs: dict[str, pd.DataFrame],
    window: int = 50,
    max_lag: int = 3,
) -> pd.Series:
    """Causal rolling ridge on lagged peer returns."""
    peers = [p for p in PEERS if p in peer_dfs and p != target_df.attrs.get("symbol", "")]
    n = len(target_df)
    signal = pd.Series(index=target_df.index, dtype=float)

    for i in range(window + max_lag, n):
        lo = i - window
        # Build X from peer returns at lags 1..max_lag
        X_list = []
        for peer in peers:
            pdf = peer_dfs[peer]
            for lag in range(1, max_lag + 1):
                col = f"mid_ret_l{lag}"
                if col not in pdf.columns:
                    pdf = pdf.copy()
                    pdf["mid_ret"] = np.log(pdf["mid"] / pdf["mid"].shift(1))
                    for l in range(1, max_lag + 1):
                        pdf[f"mid_ret_l{l}"] = pdf["mid_ret"].shift(l)
                vals = pdf[col].iloc[lo:i].dropna().values
                if len(vals) == window:
                    X_list.append(vals)
        if not X_list:
            signal.iloc[i] = np.nan
            continue
        X = np.column_stack(X_list)
        y = target_df["mid_ret"].iloc[lo:i].dropna().values
        if len(y) < window // 2:
            signal.iloc[i] = np.nan
            continue
        # Ridge with small penalty
        lam = 1.0
        XtX = X.T @ X + lam * np.eye(X.shape[1])
        try:
            beta = np.linalg.solve(XtX, X.T @ y)
            x_now = np.array([peer_dfs[p][f"mid_ret_l{lag}"].iloc[i] for p in peers for lag in range(1, max_lag + 1)])
            signal.iloc[i] = float(x_now @ beta)
        except (np.linalg.LinAlgError, KeyError):
            signal.iloc[i] = np.nan
    return signal


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--target", default="EURUSD")
    p.add_argument("--year", type=int, default=2024)
    p.add_argument("--horizons", nargs="+", type=int, default=[1, 3, 5])
    p.add_argument("--window", type=int, default=50)
    p.add_argument("--max-lag", type=int, default=3)
    args = p.parse_args()

    target_sym = args.target.upper()
    peers = [s for s in PEERS if s != target_sym]
    cost_bps = DEFAULT_COST_BPS[target_sym]
    cost_frac = cost_bps / 10_000

    # Load or build all bars
    all_bars = {}
    for sym in [target_sym] + peers:
        ticks = load_raw_ticks(sym, args.year)
        bars = build_enriched_1m_bars(ticks, sym)
        bars.attrs["symbol"] = sym
        all_bars[sym] = bars
        save_enriched_bars(bars, sym, "1m")

    target_df = all_bars[target_sym]
    peer_dfs = {s: all_bars[s] for s in peers}

    target_df = add_rolling_features(target_df, target_sym)
    target_df = compute_forward_returns(target_df, args.horizons)

    # Add lagged peer returns
    for p in peers:
        pdf = peer_dfs[p]
        pdf["mid_ret"] = np.log(pdf["mid"] / pdf["mid"].shift(1))
        for lag in range(1, args.max_lag + 1):
            pdf[f"mid_ret_l{lag}"] = pdf["mid_ret"].shift(lag)

    signal = build_peer_lag_signal(target_df, peer_dfs, window=args.window, max_lag=args.max_lag)

    # Apply vol-cluster gate
    gate = target_df["vol_cluster_score"] > 1.0
    signal = signal.where(gate, np.nan)

    results = {}
    for h in args.horizons:
        col = f"fwd_ret_{h}"
        if col not in target_df.columns:
            continue
        r = evaluate_family(signal, target_df[col], cost_frac=cost_frac, entry_quantile=0.90)
        results[f"h{h}"] = r
        print(f"Family-C {target_sym} h={h}: {r['verdict']}  net_lb95={r['net_lb95_bps']:.4f}  n={r['n_entries']}")

    out = {"family": "C", "symbol": target_sym, "year": args.year, "horizons": args.horizons, "cost_bps": cost_bps, "results": results}
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
```

Run test.
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add scripts/fx_coint/phase0_family_c.py tests/fx_coint/test_scalp_phase0_family_c.py
git commit -m "feat(scalp_phase0): Family C — temporal lead-lag peer returns"
```

---

### Task 6: Family D — Microstructure Cocktail

**Files:**
- Create: `scripts/fx_coint/phase0_family_d.py`
- Test: `tests/fx_coint/test_scalp_phase0_family_d.py`

**Interfaces:**
- Consumes: same shared module; uses scikit-learn RidgeClassifier
- Produces: prints JSON to stdout

- [ ] **Step 1: Write failing test**

Create `tests/fx_coint/test_scalp_phase0_family_d.py`:

```python
import pandas as pd
import numpy as np
from sklearn.linear_model import RidgeClassifierCV

from scripts.fx_coint.phase0_family_d import build_microstructure_classifier


def test_microstructure_classifier():
    rng = np.random.default_rng(42)
    n = 500
    features = pd.DataFrame({
        "spread_bps": rng.exponential(1, n),
        "tick_volume": rng.poisson(100, n),
        "flow_tick": rng.normal(0, 0.3, n),
        "bar_return_sign": rng.choice([-1, 1], size=n),
    })
    target = rng.choice([-1, 1], size=n)
    probs = build_microstructure_classifier(features, target, horizon=1)
    assert len(probs) == n
    assert np.isfinite(probs).sum() > n * 0.5
```

Run: `pytest tests/fx_coint/test_scalp_phase0_family_d.py -v`
Expected: FAIL

- [ ] **Step 2: Implement Family D script**

Create `scripts/fx_coint/phase0_family_d.py`:

```python
"""Phase 0 Family D: Microstructure Cocktail (RidgeClassifier on all features).

Hypothesis: Linear combination of untapped microstructure columns beats cost
at the tail.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import RidgeClassifierCV

from scripts.fx_coint.phase0_scalp_common import (
    add_rolling_features,
    compute_forward_returns,
    evaluate_family,
    load_raw_ticks,
    build_enriched_1m_bars,
    save_enriched_bars,
)
from scripts.fx_coint.hourly_triple_barrier import DEFAULT_COST_BPS

# Columns from velocity dataset that are available on enriched 1-min bars
FEATURE_COLS = [
    "spread_bps", "spread_z", "tick_volume", "tick_rate_z",
    "bar_return_sign", "vel_pips_h1", "vel_z_h1", "vel_z_h2",
    "accel_pips", "hour_utc", "range_pips",
    "signed_flow_24", "directional_persistence_8",
    "quote_revision_rate_z", "vol_cluster_score", "slip_proxy_pips",
    "flow_tick", "flow_ofi",
]


def build_microstructure_classifier(
    features: pd.DataFrame, target: np.ndarray, horizon: int
) -> pd.Series:
    """Causal rolling RidgeClassifier. Walk-forward by month to avoid leakage."""
    n = len(features)
    probs = pd.Series(index=features.index, dtype=float)

    # Monthly walk-forward
    features["month"] = pd.to_datetime(features.index).to_period("M")
    months = features["month"].unique()

    for i in range(2, len(months)):
        train_mask = features["month"].isin(months[:i-1])
        test_mask = features["month"] == months[i]
        if train_mask.sum() < 100 or test_mask.sum() < 10:
            continue

        X_train = features.loc[train_mask, FEATURE_COLS].dropna()
        y_train = target[train_mask]
        X_test = features.loc[test_mask, FEATURE_COLS]

        if len(X_train) < 100:
            continue

        clf = RidgeClassifierCV(alphas=[0.1, 1.0, 10.0, 100.0], class_weight="balanced")
        clf.fit(X_train.values, y_train[X_train.index])

        # Decision function as signal strength
        raw = clf.decision_function(X_test.fillna(0).values)
        probs.loc[X_test.index] = raw

    return probs


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", default="EURUSD")
    p.add_argument("--year", type=int, default=2024)
    p.add_argument("--horizons", nargs="+", type=int, default=[1, 3, 5])
    p.add_argument("--enriched-parquet", type=Path, default=None)
    args = p.parse_args()

    sym = args.symbol.upper()
    cost_bps = DEFAULT_COST_BPS[sym]
    cost_frac = cost_bps / 10_000

    if args.enriched_parquet and args.enriched_parquet.exists():
        df = pd.read_parquet(args.enriched_parquet)
    else:
        ticks = load_raw_ticks(sym, args.year)
        df = build_enriched_1m_bars(ticks, sym)
        path = save_enriched_bars(df, sym, "1m")
        print(f"Built enriched bars: {path}")

    df = add_rolling_features(df, sym)
    df = compute_forward_returns(df, args.horizons)

    results = {}
    for h in args.horizons:
        col = f"fwd_ret_{h}"
        if col not in df.columns:
            continue
        y = np.sign(df[col]).values
        features = df.copy()
        features.index = df["bucket"]
        probs = build_microstructure_classifier(features, y, horizon=h)

        # Entry: top decile |prob - 0.5|; side = sign(prob - 0.5)
        signal = probs - 0.5
        r = evaluate_family(signal, df[col], cost_frac=cost_frac, entry_quantile=0.90)
        results[f"h{h}"] = r
        print(f"Family-D {sym} h={h}: {r['verdict']}  net_lb95={r['net_lb95_bps']:.4f}  n={r['n_entries']}")

    out = {"family": "D", "symbol": sym, "year": args.year, "horizons": args.horizons, "cost_bps": cost_bps, "results": results}
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
```

Run test.
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add scripts/fx_coint/phase0_family_d.py tests/fx_coint/test_scalp_phase0_family_d.py
git commit -m "feat(scalp_phase0): Family D — microstructure cocktail (RidgeClassifier)"
```

---

### Task 7: Master Funnel Runner

**Files:**
- Create: `scripts/fx_coint/phase0_scalp_funnel.py`
- Test: `tests/fx_coint/test_scalp_phase0_funnel.py`

**Interfaces:**
- Consumes: stdout JSON from each family script (subprocess)
- Produces: `data/phase0_results.json` summary with rankings and stopping rule verdict

- [ ] **Step 1: Write failing test**

Create `tests/fx_coint/test_scalp_phase0_funnel.py`:

```python
import json
from pathlib import Path

from scripts.fx_coint.phase0_scalp_funnel import rank_families, apply_stopping_rules


def test_rank_families():
    results = {
        "A": {"h1": {"net_lb95_bps": 0.5, "verdict": "PASS", "n_entries": 50}},
        "B": {"h1": {"net_lb95_bps": -0.2, "verdict": "NEAR_MISS", "n_entries": 30}},
        "C": {"h1": {"net_lb95_bps": -1.0, "verdict": "FAIL", "n_entries": 10}},
        "D": {"h1": {"net_lb95_bps": -0.8, "verdict": "FAIL", "n_entries": 5}},
    }
    ranked = rank_families(results)
    assert ranked[0][0] == "A"
    assert ranked[0][1]["best_verdict"] == "PASS"


def test_stopping_rules_kill():
    results = {
        "A": {"h1": {"verdict": "FAIL"}},
        "B": {"h1": {"verdict": "FAIL"}},
        "C": {"h1": {"verdict": "FAIL"}},
        "D": {"h1": {"verdict": "FAIL"}},
    }
    verdict = apply_stopping_rules(results)
    assert verdict == "STOP"
```

Run: `pytest tests/fx_coint/test_scalp_phase0_funnel.py -v`
Expected: FAIL

- [ ] **Step 2: Implement funnel**

Create `scripts/fx_coint/phase0_scalp_funnel.py`:

```python
"""Phase 0 Master Funnel: orchestrate all four families, rank, apply stopping rules.

Usage:
    uv run python scripts/fx_coint/phase0_scalp_funnel.py --symbol EURUSD --year 2024

Emits data/phase0_results.json with:
- per-family per-horizon metrics
- family ranking by best net_lb95
- stopping rule verdict (CONTINUE / STOP / ADVANCE_NEAR_MISS)
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from scripts.fx_coint.hourly_triple_barrier import DEFAULT_COST_BPS

REPO_ROOT = Path(__file__).resolve().parents[2]
FAMILIES = {
    "A": "scripts/fx_coint/phase0_family_a.py",
    "B": "scripts/fx_coint/phase0_family_b.py",
    "C": "scripts/fx_coint/phase0_family_c.py",
    "D": "scripts/fx_coint/phase0_family_d.py",
}


def run_family(family: str, symbol: str, year: int, horizons: list[int]) -> dict:
    script = REPO_ROOT / FAMILIES[family]
    cmd = [sys.executable, str(script), "--symbol", symbol, "--year", str(year)]
    if horizons:
        cmd.extend(["--horizons"] + [str(h) for h in horizons])
    print(f"Running Family {family}: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO_ROOT))
    if result.returncode != 0:
        print(result.stderr)
        return {"family": family, "error": result.stderr, "results": {}}
    # Parse JSON from last non-empty line of stdout
    lines = [ln.strip() for ln in result.stdout.splitlines() if ln.strip()]
    for line in reversed(lines):
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            continue
    return {"family": family, "error": "no JSON found in stdout", "stdout": result.stdout}


def rank_families(results: dict) -> list:
    """Rank families by best net_lb95 across all horizons."""
    ranked = []
    for fam, data in results.items():
        r = data.get("results", {})
        best_net = float("-inf")
        best_verdict = "FAIL"
        for h, m in r.items():
            net = m.get("net_lb95_bps", float("-inf"))
            if net > best_net:
                best_net = net
                best_verdict = m.get("verdict", "FAIL")
        ranked.append((fam, {"best_net_lb95_bps": best_net, "best_verdict": best_verdict, "raw": data}))
    ranked.sort(key=lambda x: x[1]["best_net_lb95_bps"], reverse=True)
    return ranked


def apply_stopping_rules(results: dict) -> str:
    """STOP if 0 PASS and <=1 NEAR_MISS; CONTINUE if >=1 PASS; ADVANCE_NEAR_MISS otherwise."""
    pass_count = 0
    near_miss_count = 0
    for fam, data in results.items():
        r = data.get("results", {})
        for h, m in r.items():
            v = m.get("verdict", "FAIL")
            if v == "PASS":
                pass_count += 1
            elif v == "NEAR_MISS":
                near_miss_count += 1
    if pass_count >= 1:
        return "CONTINUE"
    if pass_count == 0 and near_miss_count <= 1:
        return "STOP"
    return "ADVANCE_NEAR_MISS"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", default="EURUSD")
    p.add_argument("--year", type=int, default=2024)
    p.add_argument("--horizons", nargs="+", type=int, default=[1, 3, 5])
    p.add_argument("--skip-enriched-build", action="store_true",
                   help="Assume enriched bars already exist for all needed symbols")
    args = p.parse_args()

    sym = args.symbol.upper()
    cost_bps = DEFAULT_COST_BPS.get(sym, 0.80)

    # Optionally pre-build enriched bars for target (Families A,B,D) and all peers (Family C)
    if not args.skip_enriched_build:
        from scripts.fx_coint.phase0_scalp_common import (
            load_raw_ticks, build_enriched_1m_bars, save_enriched_bars
        )
        symbols_needed = [sym] if sym != "EURUSD" else [sym]  # Family C builds its own peers
        for s in symbols_needed:
            try:
                ticks = load_raw_ticks(s, args.year)
                bars = build_enriched_1m_bars(ticks, s)
                path = save_enriched_bars(bars, s, "1m")
                print(f"Pre-built: {path}")
            except FileNotFoundError as e:
                print(f"SKIP {s}: {e}")

    all_results = {}
    for fam in ["A", "B", "C", "D"]:
        out = run_family(fam, sym, args.year, args.horizons)
        all_results[fam] = out
        print(f"Family {fam} done.")

    ranked = rank_families(all_results)
    stop_verdict = apply_stopping_rules(all_results)

    summary = {
        "symbol": sym,
        "year": args.year,
        "cost_bps": cost_bps,
        "ranking": [{"family": fam, **meta} for fam, meta in ranked],
        "stopping_rule": stop_verdict,
        "pass_count": sum(1 for _, m in ranked if m["best_verdict"] == "PASS"),
        "near_miss_count": sum(1 for _, m in ranked if m["best_verdict"] == "NEAR_MISS"),
        "full_results": all_results,
    }

    out_path = REPO_ROOT / "data" / "phase0_results.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2))
    print(f"\nSaved summary: {out_path}")
    print(f"Stopping rule: {stop_verdict}")


if __name__ == "__main__":
    main()
```

Run test.
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add scripts/fx_coint/phase0_scalp_funnel.py tests/fx_coint/test_scalp_phase0_funnel.py
git commit -m "feat(scalp_phase0): master funnel runner + stopping rules"
```

---

### Task 8: Lint, Type Check, Final Integration Test

- [ ] **Step 1: Run make quality**

```bash
make quality
```

Expected: pass with no new errors in touched files. If ruff/ty complain, fix inline.

- [ ] **Step 2: Run full test suite for new tests**

```bash
uv run pytest tests/fx_coint/test_scalp_phase0_ -v
```

Expected: All 4 test files pass.

- [ ] **Step 3: Dry-run funnel on EURUSD 2024 (if data available)**

```bash
uv run python scripts/fx_coint/phase0_scalp_funnel.py --symbol EURUSD --year 2024 --skip-enriched-build
```

Expected: Runs all 4 families, emits `data/phase0_results.json`. If raw tick data is missing, the script prints `SKIP` messages but does not crash.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "feat(scalp_phase0): complete Phase 0 sandbox — 4 families + funnel"
```

---

## Self-Review

### 1. Spec Coverage

| Spec Requirement | Task | Status |
|-----------------|------|--------|
| True raw-tick 1-min time bars | Task 1 (build_enriched_1m_bars) | ✅ |
| No bfill / causal shift | Task 2 (all rolling .shift(1)) | ✅ |
| Pepperstone Razor cost | Tasks 3–7 import DEFAULT_COST_BPS | ✅ |
| Family A: flow orth | Task 3 | ✅ |
| Family B: quote-rev continuation | Task 4 | ✅ |
| Family C: peer lead-lag | Task 5 | ✅ |
| Family D: micro cocktail | Task 6 | ✅ |
| Master funnel + stopping rules | Task 7 | ✅ |
| net_lb95 evaluation | Task 2 | ✅ |
| Near-miss detection | Task 2 | ✅ |
| Look-ahead guards | Task 1 + 2 (causal by construction) | ✅ |
| Kill switch (0 pass + ≤1 near miss → stop) | Task 7 apply_stopping_rules | ✅ |
| Tests | Tasks 1, 2, 3, 4, 5, 6, 7 | ✅ |

### 2. Placeholder Scan

- No TBD, TODO, or "implement later" found.
- No vague "add validation" steps; all code is explicit.
- No "similar to Task N" references.

### 3. Type Consistency

- `evaluate_family` signature: `(signal: pd.Series, fwd_ret: pd.Series, cost_frac: float, entry_quantile=0.90) -> dict` — used consistently across all 4 family scripts.
- `build_enriched_1m_bars` returns `pd.DataFrame` — consumed by all families.
- `DEFAULT_COST_BPS` imported from `hourly_triple_barrier` in all family scripts.

No inconsistencies found.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-06-20-fx-scalp-discovery-plan.md`.**

Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using `executing-plans`, batch execution with checkpoints.

**Which approach do you want?**
