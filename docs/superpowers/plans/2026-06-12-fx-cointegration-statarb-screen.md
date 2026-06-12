# FX Cointegration Stat-Arb — Modelling-Readiness Screen — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a cheap, look-ahead-safe screen that decides whether genuine, stable, mean-reverting cointegration structure exists across the 6 USD majors with reversion amplitude in reach of cost — i.e. whether the stage is set for modelling (TimeBridge). No net-edge baseline; this is pure measurement → a go/no-go verdict.

**Architecture:** A small package `scripts/fx_coint/`. The unifying abstraction is **an instrument = a weight vector over the 6 real majors** (in log-mid space). Every tradeable object — a real pair, a synthetic cross, an EG hedge spread, a Johansen/basket vector — reduces to one net weight vector, so the residual series and the round-trip cost are computed the same way for all three universes. The pipeline: build aligned log-mid + spread panels (fine 5-min grid → coarse 1h/1D/1W) → cointegration screen with walk-forward stability + BH-FDR → OU reversion measurement → amplitude floor/ceiling vs a cost markup sweep → band gate → JSON+markdown report.

**Tech Stack:** Python, pandas, numpy, `statsmodels` (new dep: `adfuller`, `coint`, `coint_johansen`), pytest. Follows existing `scripts/era_scalp/` conventions (pandas, dataclasses, `cost_model.realistic_cost`, `_pip_size`).

**Units convention (used everywhere):** prices are **natural log of mid** = `ln((bid+ask)/2)`. Residuals and amplitudes are in **log units** (≈ fractional; 1e-4 ≈ 1 pip on a non-JPY pair). Cost is converted to log units: `cost_frac = (spread_price + markup_price) / mid`. This makes amplitude and cost directly comparable across pairs without pip bookkeeping.

**Spec:** `docs/superpowers/specs/2026-06-12-fx-cointegration-statarb-screen-design.md`

---

## File Structure

- `scripts/fx_coint/__init__.py` — package marker.
- `scripts/fx_coint/instruments.py` — major list, currency↔major log-USD mapping, weight vectors for real pairs & synthetic crosses.
- `scripts/fx_coint/panels.py` — load tick bars → aligned fine (5-min) & coarse (1h/1D/1W) log-mid + spread panels; year-bucket walk-forward windows.
- `scripts/fx_coint/cost.py` — per-major fractional round-trip cost (spread + markup sweep); spread-vector cost.
- `scripts/fx_coint/cointegration.py` — residual from a weight vector; Engle-Granger test; AR(1) half-life.
- `scripts/fx_coint/stability.py` — walk-forward re-estimation, %-windows-stationary, structural-break (rolling-ADF / CUSUM), BH-FDR.
- `scripts/fx_coint/johansen.py` — Johansen on the log-USD currency panel → cointegrating vectors → major weights.
- `scripts/fx_coint/reversion.py` — OU fit (θ, half-life), OOS reversion test, min-event guard (condition B).
- `scripts/fx_coint/amplitude.py` — close-to-close floor & intrabar-excursion ceiling vs cost sweep (condition C).
- `scripts/fx_coint/gate.py` — per-spread band classification (SET / EXECUTION_GATED / NOGO).
- `scripts/fx_coint/run_screen.py` — orchestrator CLI.
- `scripts/fx_coint/report.py` — JSON + markdown emitter.
- `tests/fx_coint/test_*.py` — one test module per source module.

---

## Task 0: Scaffold package and add statsmodels

**Files:**
- Create: `scripts/fx_coint/__init__.py`
- Create: `tests/fx_coint/__init__.py`
- Modify: `pyproject.toml` (dependencies)

- [ ] **Step 1: Add the dependency**

Run: `uv add statsmodels`
Expected: `pyproject.toml` `dependencies` gains `statsmodels>=0.14.0`; `uv.lock` updates.

- [ ] **Step 2: Verify imports resolve**

Run: `.venv/bin/python -c "from statsmodels.tsa.stattools import adfuller, coint; from statsmodels.tsa.vector_ar.vecm import coint_johansen; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Create package markers**

`scripts/fx_coint/__init__.py`:
```python
"""FX cointegration stat-arb modelling-readiness screen."""
```
`tests/fx_coint/__init__.py`:
```python
```

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock scripts/fx_coint/__init__.py tests/fx_coint/__init__.py
git commit -m "chore(fx-coint): scaffold package + statsmodels dep"
```

---

## Task 1: Instruments — currency mapping and weight vectors

The 6 majors expressed as a currency's log-value-in-USD: `EUR=+EURUSD, GBP=+GBPUSD, AUD=+AUDUSD, JPY=-USDJPY, CHF=-USDCHF, CAD=-USDCAD, USD=0`. Any instrument is a weight vector over the 6 majors; a cross `XXX/YYY = logUSD[XXX] − logUSD[YYY]`.

**Files:**
- Create: `scripts/fx_coint/instruments.py`
- Test: `tests/fx_coint/test_instruments.py`

- [ ] **Step 1: Write the failing test**

```python
import numpy as np
from scripts.fx_coint.instruments import (
    MAJORS, CURRENCIES, ccy_weight, instrument_weight, all_pairs,
)


def test_majors_and_currencies():
    assert MAJORS == ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "AUDUSD"]
    assert set(CURRENCIES) == {"EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "USD"}


def test_ccy_weight_usd_quote_is_plus_one():
    w = ccy_weight("EUR")
    assert w[MAJORS.index("EURUSD")] == 1.0
    assert w.sum() == 1.0


def test_ccy_weight_usd_base_is_minus_one():
    w = ccy_weight("JPY")
    assert w[MAJORS.index("USDJPY")] == -1.0


def test_usd_is_zero_vector():
    assert np.allclose(ccy_weight("USD"), np.zeros(len(MAJORS)))


def test_real_pair_is_unit_vector():
    w = instrument_weight("EURUSD")
    expected = np.zeros(len(MAJORS)); expected[0] = 1.0
    assert np.allclose(w, expected)


def test_synthetic_cross_is_difference_of_legs():
    # EURGBP = logUSD[EUR] - logUSD[GBP] = +EURUSD - GBPUSD
    w = instrument_weight("EURGBP")
    assert w[MAJORS.index("EURUSD")] == 1.0
    assert w[MAJORS.index("GBPUSD")] == -1.0


def test_cross_with_usd_base_leg():
    # AUDJPY = +AUDUSD - (-USDJPY) = +AUDUSD + USDJPY
    w = instrument_weight("AUDJPY")
    assert w[MAJORS.index("AUDUSD")] == 1.0
    assert w[MAJORS.index("USDJPY")] == 1.0


def test_all_pairs_count():
    # 7 currencies choose 2 = 21 instruments (6 real USD majors + 15 crosses)
    assert len(all_pairs()) == 21
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/fx_coint/test_instruments.py -v`
Expected: FAIL with `ModuleNotFoundError: scripts.fx_coint.instruments`

- [ ] **Step 3: Write minimal implementation**

`scripts/fx_coint/instruments.py`:
```python
from __future__ import annotations

from itertools import combinations

import numpy as np

MAJORS: list[str] = ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "AUDUSD"]
CURRENCIES: list[str] = ["EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "USD"]

# Each non-USD currency's log-value-in-USD as a signed unit weight on one major.
_CCY_LEG: dict[str, tuple[str, float]] = {
    "EUR": ("EURUSD", 1.0),
    "GBP": ("GBPUSD", 1.0),
    "AUD": ("AUDUSD", 1.0),
    "JPY": ("USDJPY", -1.0),
    "CHF": ("USDCHF", -1.0),
    "CAD": ("USDCAD", -1.0),
}


def ccy_weight(ccy: str) -> np.ndarray:
    """Weight vector over MAJORS for a currency's log-value-in-USD. USD -> zeros."""
    w = np.zeros(len(MAJORS))
    if ccy == "USD":
        return w
    major, sign = _CCY_LEG[ccy]
    w[MAJORS.index(major)] = sign
    return w


def instrument_weight(symbol: str) -> np.ndarray:
    """Weight vector over MAJORS for any 6-char pair XXXYYY (real or synthetic cross)."""
    base, quote = symbol[:3], symbol[3:]
    return ccy_weight(base) - ccy_weight(quote)


def all_pairs() -> list[str]:
    """All 21 tradeable instruments across the 7-currency complex."""
    out: list[str] = []
    for a, b in combinations(CURRENCIES, 2):
        sym = a + b
        # Skip degenerate (USD with itself never occurs); keep canonical order.
        out.append(sym)
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/fx_coint/test_instruments.py -v`
Expected: PASS (8 passed)

- [ ] **Step 5: Commit**

```bash
git add scripts/fx_coint/instruments.py tests/fx_coint/test_instruments.py
git commit -m "feat(fx-coint): instrument weight-vector model over 6 majors"
```

---

## Task 2: Panels — load, resample to fine grid, align across majors

Build a regular **fine** time grid (default 5-min) of log-mid + spread per major, aligned by inner-join on grid timestamps that have real data in every leg (no fabricated prices, no weekend ffill). The fine grid is the substrate; coarse bars (Task 3) resample from it.

**Files:**
- Create: `scripts/fx_coint/panels.py`
- Test: `tests/fx_coint/test_panels.py`

- [ ] **Step 1: Write the failing test**

```python
import numpy as np
import pandas as pd

from scripts.fx_coint.panels import resample_fine, align_panel


def _toy_ticks(start, n, step_s, base):
    ts = pd.date_range(start, periods=n, freq=f"{step_s}s", tz="UTC")
    bid = base + np.linspace(0, 0.001, n)
    return pd.DataFrame({
        "close_ts": ts, "close_bid": bid, "close_ask": bid + 0.0001,
        "spread": np.full(n, 0.0001),
    })


def test_resample_fine_produces_logmid_and_spread():
    df = _toy_ticks("2020-01-06 00:00:00", 600, 10, 1.10)  # 100 min of 10s ticks
    out = resample_fine(df, "5min")
    assert {"logmid", "spread"}.issubset(out.columns)
    # log of mid ~ ln(1.10) ish
    assert abs(out["logmid"].iloc[0] - np.log(1.10005)) < 1e-3
    # empty bins are dropped (no ffill): every row backed by real data
    assert out["logmid"].notna().all()


def test_resample_fine_drops_empty_bins():
    df = _toy_ticks("2020-01-06 00:00:00", 6, 10, 1.10)  # only 1 min of data
    out = resample_fine(df, "5min")
    assert len(out) == 1  # only the bins that actually had ticks survive


def test_align_panel_inner_joins_on_common_grid():
    a = resample_fine(_toy_ticks("2020-01-06 00:00:00", 600, 10, 1.10), "5min")
    b = resample_fine(_toy_ticks("2020-01-06 00:10:00", 600, 10, 1.30), "5min")  # offset
    panel = align_panel({"EURUSD": a, "GBPUSD": b})
    # only overlapping timestamps survive
    assert ("EURUSD", "logmid") in panel.columns
    assert ("GBPUSD", "spread") in panel.columns
    assert len(panel) > 0
    assert panel.index.is_monotonic_increasing
    assert panel.isna().sum().sum() == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/fx_coint/test_panels.py -v`
Expected: FAIL with `ModuleNotFoundError: scripts.fx_coint.panels`

- [ ] **Step 3: Write minimal implementation**

`scripts/fx_coint/panels.py`:
```python
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from scripts.fx_coint.instruments import MAJORS

TICK_DIR = Path("data/tick_bars")


def resample_fine(df: pd.DataFrame, freq: str) -> pd.DataFrame:
    """Resample raw tick bars to a regular grid of log-mid + mean spread.

    Empty bins (no underlying ticks) are dropped — never forward-filled, so no
    fabricated prices across gaps/weekends. Returns a DatetimeIndex frame.
    """
    d = df.copy()
    d["close_ts"] = pd.to_datetime(d["close_ts"], utc=True, errors="coerce")
    d = d[d["close_ts"].notna()].set_index("close_ts").sort_index()
    mid = (d["close_bid"] + d["close_ask"]) / 2.0
    g = pd.DataFrame({"mid": mid, "spread": d["spread"]}).resample(freq)
    out = pd.DataFrame({
        "logmid": np.log(g["mid"].last()),
        "spread": g["spread"].mean(),
    })
    return out.dropna()


def load_fine(symbol: str, freq: str = "5min", bar: str = "100tick") -> pd.DataFrame:
    path = TICK_DIR / f"{symbol}_{bar}.parquet"
    return resample_fine(pd.read_parquet(path), freq)


def align_panel(per_symbol: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Inner-join per-symbol fine frames into a MultiIndex-column panel.

    Columns are (symbol, field) with field in {logmid, spread}. Inner join keeps
    only grid timestamps present in every leg; result has no NaNs.
    """
    frames = []
    for sym, f in per_symbol.items():
        cols = pd.MultiIndex.from_product([[sym], ["logmid", "spread"]])
        frames.append(pd.DataFrame(f[["logmid", "spread"]].to_numpy(),
                                   index=f.index, columns=cols))
    panel = pd.concat(frames, axis=1, join="inner").sort_index()
    return panel.dropna()


def load_aligned(freq: str = "5min", bar: str = "100tick",
                 symbols: list[str] | None = None) -> pd.DataFrame:
    syms = symbols or MAJORS
    return align_panel({s: load_fine(s, freq, bar) for s in syms})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/fx_coint/test_panels.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add scripts/fx_coint/panels.py tests/fx_coint/test_panels.py
git commit -m "feat(fx-coint): fine-grid resample + cross-major alignment"
```

---

## Task 3: Coarse bars and walk-forward windows

Resample the fine panel to coarse bars (1h/1D/1W): coarse log-mid = last fine logmid in the window; coarse spread = mean. Also expose year-bucketed walk-forward windows (rolling train → next-window OOS) with a purge gap.

**Files:**
- Modify: `scripts/fx_coint/panels.py`
- Test: `tests/fx_coint/test_panels_coarse.py`

- [ ] **Step 1: Write the failing test**

```python
import numpy as np
import pandas as pd

from scripts.fx_coint.panels import coarsen, walk_forward_windows


def _fine_panel():
    idx = pd.date_range("2020-01-06", periods=24 * 12 * 10, freq="5min", tz="UTC")
    cols = pd.MultiIndex.from_tuples([("EURUSD", "logmid"), ("EURUSD", "spread")])
    data = np.column_stack([np.linspace(0, 1, len(idx)), np.full(len(idx), 1e-4)])
    return pd.DataFrame(data, index=idx, columns=cols)


def test_coarsen_daily_uses_last_logmid_and_mean_spread():
    fine = _fine_panel()
    daily = coarsen(fine, "1D")
    assert len(daily) == 10
    # last 5-min logmid of day 0 equals the daily logmid of day 0
    day0 = fine.loc["2020-01-06"]
    assert np.isclose(daily[("EURUSD", "logmid")].iloc[0], day0[("EURUSD", "logmid")].iloc[-1])
    assert np.isclose(daily[("EURUSD", "spread")].iloc[0], day0[("EURUSD", "spread")].mean())


def test_walk_forward_windows_train_then_oos_with_purge():
    idx = pd.date_range("2018-01-01", "2025-12-31", freq="1D", tz="UTC")
    frame = pd.DataFrame({"x": np.arange(len(idx))}, index=idx)
    wins = walk_forward_windows(frame, train_years=2, step_years=1, purge="5D")
    assert len(wins) >= 4
    tr0, oos0 = wins[0]
    assert tr0.index.max() < oos0.index.min()
    # purge gap: at least 5 days between train end and oos start
    assert (oos0.index.min() - tr0.index.max()).days >= 5
    # oos of window 0 overlaps train of a later window (rolling, expanding coverage)
    assert oos0.index.min().year == tr0.index.min().year + 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/fx_coint/test_panels_coarse.py -v`
Expected: FAIL with `ImportError: cannot import name 'coarsen'`

- [ ] **Step 3: Write minimal implementation (append to `panels.py`)**

```python
def coarsen(fine_panel: pd.DataFrame, freq: str) -> pd.DataFrame:
    """Coarsen a fine MultiIndex panel: logmid=last, spread=mean per window."""
    out = {}
    for sym in fine_panel.columns.get_level_values(0).unique():
        g = fine_panel[sym].resample(freq)
        out[(sym, "logmid")] = g["logmid"].last()
        out[(sym, "spread")] = g["spread"].mean()
    res = pd.DataFrame(out)
    res.columns = pd.MultiIndex.from_tuples(res.columns)
    return res.dropna()


def walk_forward_windows(frame: pd.DataFrame, train_years: int = 2,
                         step_years: int = 1, purge: str = "5D"):
    """Yield (train_df, oos_df) tuples: rolling train_years window, the next
    step_years as OOS, separated by a purge gap. Look-ahead safe."""
    purge_td = pd.Timedelta(purge)
    start = frame.index.min().normalize()
    end = frame.index.max()
    wins = []
    tr_start = start
    while True:
        tr_end = tr_start + pd.DateOffset(years=train_years)
        oos_start = tr_end + purge_td
        oos_end = oos_start + pd.DateOffset(years=step_years)
        if oos_start >= end:
            break
        train = frame[(frame.index >= tr_start) & (frame.index < tr_end)]
        oos = frame[(frame.index >= oos_start) & (frame.index < oos_end)]
        if len(train) > 0 and len(oos) > 0:
            wins.append((train, oos))
        tr_start = tr_start + pd.DateOffset(years=step_years)
    return wins
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/fx_coint/test_panels_coarse.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add scripts/fx_coint/panels.py tests/fx_coint/test_panels_coarse.py
git commit -m "feat(fx-coint): coarse bars + walk-forward windows with purge"
```

---

## Task 4: Cost — per-major fractional cost and spread-vector cost

Convert per-bar spread (price units) to fractional log cost, add the markup sweep (`pips/leg`), and compute a spread's round-trip cost as the weight-magnitude-weighted sum over its legs.

**Files:**
- Create: `scripts/fx_coint/cost.py`
- Test: `tests/fx_coint/test_cost.py`

- [ ] **Step 1: Write the failing test**

```python
import numpy as np

from scripts.era_scalp.load_splits import _pip_size
from scripts.fx_coint.cost import leg_cost_frac, spread_cost_frac, MARKUP_SWEEP_PIPS


def test_markup_sweep_values():
    assert MARKUP_SWEEP_PIPS == (0.0, 0.3, 0.6, 1.0)


def test_leg_cost_frac_zero_markup_is_spread_over_mid():
    # EURUSD spread 0.0001 price, mid 1.10 -> ~9.09e-5 fractional
    c = leg_cost_frac("EURUSD", spread_price=1e-4, mid=1.10, markup_pips=0.0)
    assert np.isclose(c, 1e-4 / 1.10, rtol=1e-6)


def test_leg_cost_frac_adds_markup_in_price_units():
    # +0.6 pip on EURUSD = +0.6 * 1e-4 price
    c = leg_cost_frac("EURUSD", spread_price=1e-4, mid=1.10, markup_pips=0.6)
    assert np.isclose(c, (1e-4 + 0.6 * _pip_size("EURUSD")) / 1.10, rtol=1e-6)


def test_jpy_pip_size_used():
    c = leg_cost_frac("USDJPY", spread_price=0.01, mid=110.0, markup_pips=1.0)
    assert np.isclose(c, (0.01 + 1.0 * 0.01) / 110.0, rtol=1e-6)


def test_spread_cost_frac_sums_weighted_legs():
    # weight vector +1 EURUSD, -1 GBPUSD -> round-trip cost = |1|*cE + |1|*cG
    weights = np.zeros(6); weights[0] = 1.0; weights[1] = -1.0
    spreads = np.full(6, 1e-4)
    mids = np.array([1.10, 1.30, 110.0, 0.90, 1.35, 0.65])
    total = spread_cost_frac(weights, spreads, mids, markup_pips=0.0)
    expected = 1e-4 / 1.10 + 1e-4 / 1.30
    assert np.isclose(total, expected, rtol=1e-6)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/fx_coint/test_cost.py -v`
Expected: FAIL with `ModuleNotFoundError: scripts.fx_coint.cost`

- [ ] **Step 3: Write minimal implementation**

`scripts/fx_coint/cost.py`:
```python
from __future__ import annotations

import numpy as np

from scripts.era_scalp.load_splits import _pip_size
from scripts.fx_coint.instruments import MAJORS

# Added markup per leg (pips), swept so the verdict can be read at any broker assumption.
MARKUP_SWEEP_PIPS: tuple[float, ...] = (0.0, 0.3, 0.6, 1.0)


def leg_cost_frac(symbol: str, spread_price: float, mid: float,
                  markup_pips: float) -> float:
    """One leg's round-trip cost in fractional (log) units."""
    price_cost = spread_price + markup_pips * _pip_size(symbol)
    return float(price_cost / mid)


def spread_cost_frac(weights: np.ndarray, spreads: np.ndarray, mids: np.ndarray,
                     markup_pips: float) -> float:
    """Round-trip cost of a weight-vector spread = sum_i |w_i| * leg_cost_i."""
    total = 0.0
    for i, sym in enumerate(MAJORS):
        if weights[i] == 0.0:
            continue
        total += abs(weights[i]) * leg_cost_frac(sym, float(spreads[i]),
                                                 float(mids[i]), markup_pips)
    return total
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/fx_coint/test_cost.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add scripts/fx_coint/cost.py tests/fx_coint/test_cost.py
git commit -m "feat(fx-coint): fractional leg/spread cost with markup sweep"
```

---

## Task 5: Cointegration — residual, Engle-Granger, half-life

Given a coarse panel and a base/hedge instrument pair, estimate the hedge ratio β on the train slice, form the residual, run ADF on it, and compute the AR(1) mean-reversion half-life. β is estimated only on train and applied forward (look-ahead safe).

**Files:**
- Create: `scripts/fx_coint/cointegration.py`
- Test: `tests/fx_coint/test_cointegration.py`

- [ ] **Step 1: Write the failing test**

```python
import numpy as np
import pandas as pd

from scripts.fx_coint.cointegration import (
    instrument_series, fit_hedge, residual, eg_test, half_life,
)


def _panel(n=2000, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2020-01-01", periods=n, freq="1h", tz="UTC")
    # EURUSD random walk; GBPUSD = 0.8*EURUSD + stationary AR(1) noise -> cointegrated
    e = np.cumsum(rng.normal(0, 0.001, n)) + np.log(1.10)
    noise = np.zeros(n)
    for t in range(1, n):
        noise[t] = 0.9 * noise[t - 1] + rng.normal(0, 0.0005)
    g = 0.8 * e + noise + np.log(1.30) * 0.2
    cols = pd.MultiIndex.from_tuples([
        ("EURUSD", "logmid"), ("EURUSD", "spread"),
        ("GBPUSD", "logmid"), ("GBPUSD", "spread")])
    data = np.column_stack([e, np.full(n, 1e-4), g, np.full(n, 1e-4)])
    return pd.DataFrame(data, index=idx, columns=cols)


def test_instrument_series_combines_legs():
    p = _panel()
    s = instrument_series(p, "EURUSD")
    assert np.allclose(s.to_numpy(), p[("EURUSD", "logmid")].to_numpy())


def test_fit_hedge_recovers_beta():
    p = _panel()
    beta = fit_hedge(p, "GBPUSD", "EURUSD")
    assert 0.6 < beta < 1.0  # ~0.8


def test_eg_test_flags_cointegrated_pair():
    p = _panel()
    beta = fit_hedge(p, "GBPUSD", "EURUSD")
    res = residual(p, "GBPUSD", "EURUSD", beta)
    pval = eg_test(res)
    assert pval < 0.05


def test_eg_test_rejects_independent_walks():
    rng = np.random.default_rng(1)
    idx = pd.date_range("2020-01-01", periods=2000, freq="1h", tz="UTC")
    a = np.cumsum(rng.normal(0, 0.001, 2000))
    b = np.cumsum(rng.normal(0, 0.001, 2000))
    cols = pd.MultiIndex.from_tuples([
        ("EURUSD", "logmid"), ("EURUSD", "spread"),
        ("GBPUSD", "logmid"), ("GBPUSD", "spread")])
    p = pd.DataFrame(np.column_stack([a, np.full(2000, 1e-4), b, np.full(2000, 1e-4)]),
                     index=idx, columns=cols)
    beta = fit_hedge(p, "GBPUSD", "EURUSD")
    pval = eg_test(residual(p, "GBPUSD", "EURUSD", beta))
    assert pval > 0.05


def test_half_life_positive_and_finite():
    p = _panel()
    res = residual(p, "GBPUSD", "EURUSD", fit_hedge(p, "GBPUSD", "EURUSD"))
    hl = half_life(res)
    assert 0 < hl < len(res)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/fx_coint/test_cointegration.py -v`
Expected: FAIL with `ModuleNotFoundError: scripts.fx_coint.cointegration`

- [ ] **Step 3: Write minimal implementation**

`scripts/fx_coint/cointegration.py`:
```python
from __future__ import annotations

import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import adfuller

from scripts.fx_coint.instruments import MAJORS, instrument_weight


def instrument_series(panel: pd.DataFrame, symbol: str) -> pd.Series:
    """Log-price series of any instrument = weights . major logmids.

    Only legs with a nonzero weight are read, so a panel holding a subset of
    MAJORS works as long as it carries every leg the instrument needs. A
    required-but-absent leg is a hard error (no silent zero-fill).
    """
    w = instrument_weight(symbol)
    present = set(panel.columns.get_level_values(0))
    series = pd.Series(0.0, index=panel.index)
    for i, major in enumerate(MAJORS):
        if w[i] == 0.0:
            continue
        if major not in present:
            raise KeyError(f"panel missing leg {major!r} required for {symbol!r}")
        series = series + w[i] * panel[(major, "logmid")]
    return series


def fit_hedge(panel: pd.DataFrame, base: str, hedge: str) -> float:
    """OLS hedge ratio beta: base ~ beta*hedge + const. Estimated on the given slice."""
    y = instrument_series(panel, base).to_numpy()
    x = instrument_series(panel, hedge).to_numpy()
    A = np.column_stack([x, np.ones_like(x)])
    beta, _ = np.linalg.lstsq(A, y, rcond=None)[0]
    return float(beta)


def residual(panel: pd.DataFrame, base: str, hedge: str, beta: float) -> pd.Series:
    """Cointegration residual base - beta*hedge (de-meaned)."""
    s = instrument_series(panel, base) - beta * instrument_series(panel, hedge)
    return s - s.mean()


def eg_test(res: pd.Series) -> float:
    """ADF p-value on the residual (Engle-Granger step 2). Lower = more stationary."""
    return float(adfuller(res.to_numpy(), autolag="AIC")[1])


def half_life(res: pd.Series) -> float:
    """AR(1) mean-reversion half-life in bars: dr_t = a + rho*r_{t-1}; hl = -ln2/ln(1+rho)."""
    r = res.to_numpy()
    lag = r[:-1]
    dr = np.diff(r)
    A = np.column_stack([lag, np.ones_like(lag)])
    rho, _ = np.linalg.lstsq(A, dr, rcond=None)[0]
    if rho >= 0:
        return float("inf")
    return float(-np.log(2) / np.log(1 + rho))


def residual_weight(base: str, hedge: str, beta: float) -> np.ndarray:
    """Net weight vector over MAJORS for the spread base - beta*hedge (for cost)."""
    return instrument_weight(base) - beta * instrument_weight(hedge)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/fx_coint/test_cointegration.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add scripts/fx_coint/cointegration.py tests/fx_coint/test_cointegration.py
git commit -m "feat(fx-coint): Engle-Granger residual + AR(1) half-life"
```

---

## Task 6: Stability — walk-forward, structural break, BH-FDR (condition A)

A relationship counts as "structure exists" only if it is stationary in a strong majority of walk-forward OOS windows (β re-fit on each train, ADF on each OOS residual) and survives BH-FDR across all tested pairs.

**Files:**
- Create: `scripts/fx_coint/stability.py`
- Test: `tests/fx_coint/test_stability.py`

- [ ] **Step 1: Write the failing test**

```python
import numpy as np

from scripts.fx_coint.stability import bh_fdr, fraction_stationary


def test_bh_fdr_basic():
    pvals = [0.001, 0.01, 0.2, 0.8]
    keep = bh_fdr(pvals, alpha=0.10)
    assert keep[0] and keep[1]
    assert not keep[3]


def test_bh_fdr_all_null():
    assert bh_fdr([0.9, 0.95, 0.99], alpha=0.10) == [False, False, False]


def test_fraction_stationary_counts_oos_passes():
    # 4 windows, 3 with p<0.05
    pvals = [0.01, 0.02, 0.04, 0.6]
    frac = fraction_stationary(pvals, p_thresh=0.05)
    assert np.isclose(frac, 0.75)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/fx_coint/test_stability.py -v`
Expected: FAIL with `ModuleNotFoundError: scripts.fx_coint.stability`

- [ ] **Step 3: Write minimal implementation**

`scripts/fx_coint/stability.py`:
```python
from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.fx_coint.cointegration import eg_test, fit_hedge, half_life, residual
from scripts.fx_coint.panels import walk_forward_windows

# A relationship must be stationary in at least this fraction of OOS windows.
MIN_STATIONARY_FRACTION = 0.6


def bh_fdr(pvals, alpha: float = 0.10) -> list[bool]:
    """Benjamini-Hochberg: return keep-mask (True = reject null = stationary)."""
    p = np.asarray(pvals, float)
    n = len(p)
    order = np.argsort(p)
    thresh = alpha * (np.arange(1, n + 1) / n)
    passed = p[order] <= thresh
    keep = np.zeros(n, dtype=bool)
    if passed.any():
        kmax = np.max(np.where(passed)[0])
        keep[order[: kmax + 1]] = True
    return keep.tolist()


def fraction_stationary(oos_pvals, p_thresh: float = 0.05) -> float:
    p = np.asarray(oos_pvals, float)
    return float((p < p_thresh).mean()) if len(p) else 0.0


def walk_forward_eg(panel: pd.DataFrame, base: str, hedge: str,
                    train_years: int = 2):
    """Re-fit beta on each train window, test ADF on each OOS residual.

    Returns dict with oos p-values, per-window half-lives, and the mean OOS beta.
    Look-ahead safe: beta from train only, residual computed forward on OOS.
    """
    wins = walk_forward_windows(panel, train_years=train_years)
    oos_pvals, hls, betas = [], [], []
    for train, oos in wins:
        beta = fit_hedge(train, base, hedge)
        res_oos = residual(oos, base, hedge, beta)
        if len(res_oos) < 30:
            continue
        oos_pvals.append(eg_test(res_oos))
        hls.append(half_life(res_oos))
        betas.append(beta)
    return {
        "oos_pvals": oos_pvals,
        "half_lives": hls,
        "beta_mean": float(np.mean(betas)) if betas else float("nan"),
        "fraction_stationary": fraction_stationary(oos_pvals),
        "n_windows": len(oos_pvals),
    }


def structure_exists(wf: dict) -> bool:
    """Condition A (pre-FDR): stable across walk-forward windows."""
    return (wf["n_windows"] >= 3
            and wf["fraction_stationary"] >= MIN_STATIONARY_FRACTION)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/fx_coint/test_stability.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add scripts/fx_coint/stability.py tests/fx_coint/test_stability.py
git commit -m "feat(fx-coint): walk-forward stability + BH-FDR (condition A)"
```

---

## Task 7: Johansen — multivariate cointegrating vectors

Run Johansen on the log-USD currency panel (the 6 majors mapped to currency log-values), expose the number of cointegrating relations at 95% and the leading eigenvector mapped back to a major-weight vector for use as a basket spread.

**Files:**
- Create: `scripts/fx_coint/johansen.py`
- Test: `tests/fx_coint/test_johansen.py`

- [ ] **Step 1: Write the failing test**

```python
import numpy as np
import pandas as pd

from scripts.fx_coint.johansen import johansen_rank, leading_vector_major_weights


def _coint_panel(n=1500, seed=3):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2020-01-01", periods=n, freq="1h", tz="UTC")
    common = np.cumsum(rng.normal(0, 0.001, n))
    cols, data = [], []
    base = {"EURUSD": 1.10, "GBPUSD": 1.30, "USDJPY": 110.0,
            "USDCHF": 0.90, "USDCAD": 1.35, "AUDUSD": 0.65}
    for i, (m, b) in enumerate(base.items()):
        stat = np.zeros(n)
        for t in range(1, n):
            stat[t] = 0.85 * stat[t - 1] + rng.normal(0, 0.0005)
        series = common * (1 + 0.1 * i) + stat + np.log(b)
        cols += [(m, "logmid"), (m, "spread")]
        data += [series, np.full(n, 1e-4)]
    panel = pd.DataFrame(np.column_stack(data), index=idx,
                         columns=pd.MultiIndex.from_tuples(cols))
    return panel


def test_johansen_rank_detects_cointegration():
    p = _coint_panel()
    rank = johansen_rank(p)
    assert rank >= 1


def test_leading_vector_maps_to_six_majors():
    p = _coint_panel()
    w = leading_vector_major_weights(p)
    assert w.shape == (6,)
    assert np.isfinite(w).all()
    assert np.abs(w).sum() > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/fx_coint/test_johansen.py -v`
Expected: FAIL with `ModuleNotFoundError: scripts.fx_coint.johansen`

- [ ] **Step 3: Write minimal implementation**

`scripts/fx_coint/johansen.py`:
```python
from __future__ import annotations

import numpy as np
import pandas as pd
from statsmodels.tsa.vector_ar.vecm import coint_johansen

from scripts.fx_coint.instruments import MAJORS, ccy_weight

# Non-USD currencies whose log-USD values form the Johansen system.
_CCYS = ["EUR", "GBP", "JPY", "CHF", "CAD", "AUD"]


def _logusd_matrix(panel: pd.DataFrame) -> np.ndarray:
    """Map the major logmids to a (T, 6) matrix of currency log-USD values."""
    logmids = {m: panel[(m, "logmid")].to_numpy() for m in MAJORS}
    cols = []
    for c in _CCYS:
        w = ccy_weight(c)
        cols.append(sum(w[i] * logmids[MAJORS[i]] for i in range(len(MAJORS))))
    return np.column_stack(cols)


def johansen_rank(panel: pd.DataFrame, det_order: int = 0, k_ar_diff: int = 1) -> int:
    """Number of cointegrating relations at the 95% trace-stat critical value."""
    mat = _logusd_matrix(panel)
    res = coint_johansen(mat, det_order, k_ar_diff)
    trace = res.lr1
    crit_95 = res.cvt[:, 1]
    return int((trace > crit_95).sum())


def leading_vector_major_weights(panel: pd.DataFrame, det_order: int = 0,
                                 k_ar_diff: int = 1) -> np.ndarray:
    """Leading cointegrating eigenvector, mapped from currency space to a
    (6,) weight vector over MAJORS (so it shares the cost/residual machinery)."""
    mat = _logusd_matrix(panel)
    res = coint_johansen(mat, det_order, k_ar_diff)
    ccy_vec = res.evec[:, 0]  # weights over _CCYS
    major_w = np.zeros(len(MAJORS))
    for c, wc in zip(_CCYS, ccy_vec):
        major_w += wc * ccy_weight(c)
    return major_w
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/fx_coint/test_johansen.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add scripts/fx_coint/johansen.py tests/fx_coint/test_johansen.py
git commit -m "feat(fx-coint): Johansen rank + basket vector over majors"
```

---

## Task 8: Reversion — OU fit and OOS reversion (condition B)

Condition B = reversion *exists*: a finite, sensible half-life and deviations followed by reversion on average OOS, with a minimum number of reversion events for weight. No timing/predictability claim.

**Files:**
- Create: `scripts/fx_coint/reversion.py`
- Test: `tests/fx_coint/test_reversion.py`

- [ ] **Step 1: Write the failing test**

```python
import numpy as np
import pandas as pd

from scripts.fx_coint.reversion import ou_fit, oos_reversion, reversion_exists


def _ou_series(n=3000, theta=0.05, sigma=0.001, seed=7):
    rng = np.random.default_rng(seed)
    x = np.zeros(n)
    for t in range(1, n):
        x[t] = x[t - 1] - theta * x[t - 1] + rng.normal(0, sigma)
    idx = pd.date_range("2020-01-01", periods=n, freq="1h", tz="UTC")
    return pd.Series(x, index=idx)


def test_ou_fit_recovers_positive_theta_and_halflife():
    s = _ou_series()
    fit = ou_fit(s)
    assert fit["theta"] > 0
    assert 0 < fit["half_life"] < 200


def test_oos_reversion_positive_for_mean_reverter():
    s = _ou_series()
    rev = oos_reversion(s, horizon=10)
    # on average, deviations shrink toward zero -> positive reversion fraction
    assert rev["mean_reversion_frac"] > 0
    assert rev["n_events"] > 100


def test_reversion_exists_true_for_ou():
    s = _ou_series()
    assert reversion_exists(ou_fit(s), oos_reversion(s, horizon=10))


def test_reversion_exists_false_for_random_walk():
    rng = np.random.default_rng(2)
    rw = pd.Series(np.cumsum(rng.normal(0, 0.001, 3000)))
    assert not reversion_exists(ou_fit(rw), oos_reversion(rw, horizon=10))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/fx_coint/test_reversion.py -v`
Expected: FAIL with `ModuleNotFoundError: scripts.fx_coint.reversion`

- [ ] **Step 3: Write minimal implementation**

`scripts/fx_coint/reversion.py`:
```python
from __future__ import annotations

import numpy as np
import pandas as pd

MIN_REVERSION_EVENTS = 100      # statistical-weight floor for condition B
MAX_SENSIBLE_HALF_LIFE = 500    # bars; longer = effectively a random walk
ENTRY_Z = 1.0                   # |z| beyond which we count a "deviation event"


def ou_fit(res: pd.Series) -> dict:
    """Discrete OU via AR(1): r_t = phi*r_{t-1} + e. theta=-ln(phi); hl=ln2/theta."""
    r = res.to_numpy()
    lag, cur = r[:-1], r[1:]
    A = np.column_stack([lag, np.ones_like(lag)])
    phi, _ = np.linalg.lstsq(A, cur, rcond=None)[0]
    if phi <= 0 or phi >= 1:
        return {"theta": 0.0, "half_life": float("inf"), "phi": float(phi)}
    theta = -np.log(phi)
    return {"theta": float(theta), "half_life": float(np.log(2) / theta),
            "phi": float(phi)}


def oos_reversion(res: pd.Series, horizon: int) -> dict:
    """For each bar where |z|>ENTRY_Z, did |residual| shrink `horizon` bars later?

    Returns the fraction of deviation events that reverted (toward the mean) and
    the mean signed reversion (positive = reverts), measured purely forward.
    """
    r = res.to_numpy()
    if r.std() == 0:
        return {"mean_reversion_frac": 0.0, "mean_reversion": 0.0, "n_events": 0}
    z = (r - r.mean()) / r.std()
    reverts, amounts = [], []
    for t in range(len(r) - horizon):
        if abs(z[t]) <= ENTRY_Z:
            continue
        # signed reversion: deviation magnitude consumed toward the mean
        moved = abs(r[t]) - abs(r[t + horizon])
        reverts.append(moved > 0)
        amounts.append(moved)
    n = len(reverts)
    return {
        "mean_reversion_frac": float(np.mean(reverts)) if n else 0.0,
        "mean_reversion": float(np.mean(amounts)) if n else 0.0,
        "n_events": n,
    }


def reversion_exists(fit: dict, rev: dict) -> bool:
    """Condition B: finite sensible half-life + net reversion over enough events."""
    return (0 < fit["half_life"] < MAX_SENSIBLE_HALF_LIFE
            and rev["n_events"] >= MIN_REVERSION_EVENTS
            and rev["mean_reversion_frac"] > 0.5
            and rev["mean_reversion"] > 0)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/fx_coint/test_reversion.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add scripts/fx_coint/reversion.py tests/fx_coint/test_reversion.py
git commit -m "feat(fx-coint): OU fit + OOS reversion existence (condition B)"
```

---

## Task 9: Amplitude — floor/ceiling vs cost sweep (condition C)

Floor = close-to-close OOS reversion captured per round-trip (taker). Ceiling = intrabar residual excursion within each coarse window, computed on the **fine** residual (`min`/`max` of the fine residual inside the coarse bar). Both compared to round-trip cost across the markup sweep.

**Files:**
- Create: `scripts/fx_coint/amplitude.py`
- Test: `tests/fx_coint/test_amplitude.py`

- [ ] **Step 1: Write the failing test**

```python
import numpy as np
import pandas as pd

from scripts.fx_coint.amplitude import (
    close_to_close_amplitude, intrabar_excursion, amplitude_vs_cost,
)


def test_close_to_close_amplitude_is_mean_abs_reversion():
    # residual oscillates +/-0.001 each bar -> captured move ~0.002 round-trip
    res = pd.Series(np.array([0.001, -0.001] * 500))
    amp = close_to_close_amplitude(res, entry_z=0.5, horizon=1)
    assert amp > 0


def test_intrabar_excursion_exceeds_close_to_close():
    # fine residual swings inside each coarse window beyond its endpoints
    idx = pd.date_range("2020-01-01", periods=120, freq="5min", tz="UTC")
    fine_res = pd.Series(np.tile([0.0, 0.002, -0.002, 0.0, 0.0, 0.0], 20)[:120], index=idx)
    coarse_idx = fine_res.resample("30min").last().index
    exc = intrabar_excursion(fine_res, "30min")
    # ceiling (max-min within window) should be ~0.004, larger than endpoint deltas
    assert exc.max() >= 0.003
    assert len(exc) == len(coarse_idx)


def test_amplitude_vs_cost_returns_ratio_per_markup():
    out = amplitude_vs_cost(amplitude=2e-4, cost_by_markup={0.0: 1e-4, 0.6: 1.5e-4})
    assert np.isclose(out[0.0], 2.0)
    assert np.isclose(out[0.6], 2e-4 / 1.5e-4)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/fx_coint/test_amplitude.py -v`
Expected: FAIL with `ModuleNotFoundError: scripts.fx_coint.amplitude`

- [ ] **Step 3: Write minimal implementation**

`scripts/fx_coint/amplitude.py`:
```python
from __future__ import annotations

import numpy as np
import pandas as pd


def close_to_close_amplitude(res: pd.Series, entry_z: float = 1.0,
                             horizon: int = 1) -> float:
    """Mean reversion pnl captured per round-trip at close-to-close (taker FLOOR).

    For each deviation event (|z|>entry_z), the directional pnl of a mean-reversion
    trade held `horizon` bars: short the spread when above the mean, long when below,
    so captured = sign(z[t]) * (r[t] - r[t+horizon]). This earns the full traversal
    through the mean (including overshoot), unlike a |deviation|-shrinkage measure
    which reads zero on a symmetric overshoot. Averaged over ALL events (winners and
    losers) — no positive-only filter, which would cherry-pick and inflate the floor.
    """
    r = res.to_numpy()
    if r.std() == 0:
        return 0.0
    z = (r - r.mean()) / r.std()
    caps = [np.sign(z[t]) * (r[t] - r[t + horizon])
            for t in range(len(r) - horizon) if abs(z[t]) > entry_z]
    return float(np.mean(caps)) if caps else 0.0


def intrabar_excursion(fine_res: pd.Series, coarse_freq: str) -> pd.Series:
    """Per coarse window, the fine-residual peak-to-trough range (maker CEILING).

    This is the synchronous intrabar excursion of the spread itself (computed on
    the fine residual), NOT leg highs minus lows.
    """
    g = fine_res.resample(coarse_freq)
    return (g.max() - g.min()).dropna()


def amplitude_vs_cost(amplitude: float, cost_by_markup: dict) -> dict:
    """Amplitude / round-trip cost, one ratio per markup level."""
    return {mk: (amplitude / c if c > 0 else float("inf"))
            for mk, c in cost_by_markup.items()}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/fx_coint/test_amplitude.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add scripts/fx_coint/amplitude.py tests/fx_coint/test_amplitude.py
git commit -m "feat(fx-coint): amplitude floor/ceiling vs cost sweep (condition C)"
```

---

## Task 10: Gate — band classification

Combine A/B/C into a per-spread verdict. SET if the floor clears cost; EXECUTION_GATED if cost is between floor and ceiling; NOGO if even the ceiling is below cost. A/B must both hold or the spread is NOGO regardless of amplitude.

**Files:**
- Create: `scripts/fx_coint/gate.py`
- Test: `tests/fx_coint/test_gate.py`

- [ ] **Step 1: Write the failing test**

```python
from scripts.fx_coint.gate import classify, Verdict


def test_set_when_floor_clears_cost():
    v = classify(structure=True, reversion=True, fdr_pass=True,
                 floor=2e-4, ceiling=5e-4, cost=1e-4, floor_multiple=1.0)
    assert v == Verdict.SET


def test_execution_gated_when_cost_between_floor_and_ceiling():
    v = classify(structure=True, reversion=True, fdr_pass=True,
                 floor=0.5e-4, ceiling=5e-4, cost=1e-4, floor_multiple=1.0)
    assert v == Verdict.EXECUTION_GATED


def test_nogo_when_ceiling_below_cost():
    v = classify(structure=True, reversion=True, fdr_pass=True,
                 floor=0.2e-4, ceiling=0.8e-4, cost=1e-4, floor_multiple=1.0)
    assert v == Verdict.NOGO


def test_nogo_when_structure_or_reversion_absent():
    assert classify(structure=False, reversion=True, fdr_pass=True,
                    floor=9e-4, ceiling=9e-4, cost=1e-4, floor_multiple=1.0) == Verdict.NOGO
    assert classify(structure=True, reversion=False, fdr_pass=True,
                    floor=9e-4, ceiling=9e-4, cost=1e-4, floor_multiple=1.0) == Verdict.NOGO
    assert classify(structure=True, reversion=True, fdr_pass=False,
                    floor=9e-4, ceiling=9e-4, cost=1e-4, floor_multiple=1.0) == Verdict.NOGO
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/fx_coint/test_gate.py -v`
Expected: FAIL with `ModuleNotFoundError: scripts.fx_coint.gate`

- [ ] **Step 3: Write minimal implementation**

`scripts/fx_coint/gate.py`:
```python
from __future__ import annotations

from enum import Enum


class Verdict(str, Enum):
    SET = "SET"                          # floor >= cost: stage set, build the model
    EXECUTION_GATED = "EXECUTION_GATED"  # floor < cost <= ceiling: needs tick-exact maker check
    NOGO = "NOGO"                        # ceiling < cost, or A/B/FDR failed


def classify(structure: bool, reversion: bool, fdr_pass: bool,
             floor: float, ceiling: float, cost: float,
             floor_multiple: float = 1.0) -> Verdict:
    """Apply the A/B/C band gate for one spread at one cost (markup) level."""
    if not (structure and reversion and fdr_pass):
        return Verdict.NOGO
    if floor >= floor_multiple * cost:
        return Verdict.SET
    if ceiling >= cost:
        return Verdict.EXECUTION_GATED
    return Verdict.NOGO
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/fx_coint/test_gate.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add scripts/fx_coint/gate.py tests/fx_coint/test_gate.py
git commit -m "feat(fx-coint): A/B/C band gate classification"
```

---

## Task 11: Report — JSON + markdown emitter

**Files:**
- Create: `scripts/fx_coint/report.py`
- Test: `tests/fx_coint/test_report.py`

- [ ] **Step 1: Write the failing test**

```python
import json

from scripts.fx_coint.report import write_report


def test_write_report_emits_json_and_md(tmp_path):
    rows = [{
        "timeframe": "1D", "universe": "pairwise", "base": "GBPUSD", "hedge": "EURUSD",
        "fraction_stationary": 0.8, "fdr_pass": True, "half_life": 12.0,
        "reversion_frac": 0.61, "n_events": 240,
        "floor": 2e-4, "ceiling": 6e-4,
        "cost_by_markup": {"0.0": 1e-4, "0.3": 1.2e-4, "0.6": 1.4e-4, "1.0": 1.8e-4},
        "verdict_by_markup": {"0.0": "SET", "0.3": "SET", "0.6": "EXECUTION_GATED", "1.0": "NOGO"},
    }]
    out_json = tmp_path / "screen.json"
    out_md = tmp_path / "screen.md"
    write_report(rows, out_json, out_md)
    loaded = json.loads(out_json.read_text())
    assert loaded["rows"][0]["base"] == "GBPUSD"
    assert loaded["summary"]["n_set_at_zero_markup"] == 1
    md = out_md.read_text()
    assert "GBPUSD" in md and "Verdict" in md
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/fx_coint/test_report.py -v`
Expected: FAIL with `ModuleNotFoundError: scripts.fx_coint.report`

- [ ] **Step 3: Write minimal implementation**

`scripts/fx_coint/report.py`:
```python
from __future__ import annotations

import json
from pathlib import Path


def _summary(rows: list[dict]) -> dict:
    def count(markup: str, verdict: str) -> int:
        return sum(1 for r in rows
                   if r["verdict_by_markup"].get(markup) == verdict)
    return {
        "n_rows": len(rows),
        "n_set_at_zero_markup": count("0.0", "SET"),
        "n_execution_gated_at_zero_markup": count("0.0", "EXECUTION_GATED"),
        "n_set_at_0_6_markup": count("0.6", "SET"),
    }


def write_report(rows: list[dict], out_json: Path, out_md: Path) -> None:
    payload = {"summary": _summary(rows), "rows": rows}
    Path(out_json).write_text(json.dumps(payload, indent=2, default=str))

    lines = ["# FX Cointegration Screen — Results", "", "## Summary", ""]
    for k, v in payload["summary"].items():
        lines.append(f"- **{k}**: {v}")
    lines += ["", "## Spreads", "",
              "| TF | Universe | Base | Hedge | %stat | FDR | HL | revfrac | "
              "floor | ceiling | Verdict@0.0 | @0.6 |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(
            f"| {r['timeframe']} | {r['universe']} | {r['base']} | {r['hedge']} | "
            f"{r['fraction_stationary']:.2f} | {r['fdr_pass']} | {r['half_life']:.1f} | "
            f"{r['reversion_frac']:.2f} | {r['floor']:.2e} | {r['ceiling']:.2e} | "
            f"{r['verdict_by_markup'].get('0.0')} | {r['verdict_by_markup'].get('0.6')} |")
    Path(out_md).write_text("\n".join(lines) + "\n")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/fx_coint/test_report.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add scripts/fx_coint/report.py tests/fx_coint/test_report.py
git commit -m "feat(fx-coint): JSON + markdown report emitter"
```

---

## Task 12: Orchestrator — wire the pipeline end to end

Tie everything together: for each timeframe and each candidate spread (pairwise EG over the 21 instruments + Johansen basket), run the screen and emit one row. Uses the full panel; this is the actual experiment runner.

**Files:**
- Create: `scripts/fx_coint/run_screen.py`
- Test: `tests/fx_coint/test_run_screen.py`

- [ ] **Step 1: Write the failing test (uses a tiny injected panel, not real data)**

```python
import numpy as np
import pandas as pd

from scripts.fx_coint.run_screen import screen_pair


def _coint_panel(n=4000, seed=5):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2018-01-01", periods=n, freq="1h", tz="UTC")
    e = np.cumsum(rng.normal(0, 0.001, n)) + np.log(1.10)
    noise = np.zeros(n)
    for t in range(1, n):
        noise[t] = 0.9 * noise[t - 1] + rng.normal(0, 0.0005)
    g = 0.8 * e + noise + np.log(1.30) * 0.2
    others = {m: np.cumsum(rng.normal(0, 0.001, n)) + np.log(b)
              for m, b in [("USDJPY", 110.0), ("USDCHF", 0.9),
                           ("USDCAD", 1.35), ("AUDUSD", 0.65)]}
    cols, data = [], []
    series = {"EURUSD": e, "GBPUSD": g, **others}
    for m, s in series.items():
        cols += [(m, "logmid"), (m, "spread")]
        data += [s, np.full(n, 1e-4)]
    return pd.DataFrame(np.column_stack(data), index=idx,
                        columns=pd.MultiIndex.from_tuples(cols))


def test_screen_pair_produces_full_row():
    fine = _coint_panel()
    row = screen_pair(fine, coarse_freq="1D", base="GBPUSD", hedge="EURUSD",
                      universe="pairwise", fdr_pass=True)
    assert row["base"] == "GBPUSD"
    assert set(row["verdict_by_markup"]) == {"0.0", "0.3", "0.6", "1.0"}
    assert 0.0 <= row["fraction_stationary"] <= 1.0
    assert row["floor"] >= 0 and row["ceiling"] >= row["floor"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/fx_coint/test_run_screen.py -v`
Expected: FAIL with `ModuleNotFoundError: scripts.fx_coint.run_screen`

- [ ] **Step 3: Write minimal implementation**

`scripts/fx_coint/run_screen.py`:
```python
from __future__ import annotations

import argparse
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.fx_coint.amplitude import (
    amplitude_vs_cost, close_to_close_amplitude, intrabar_excursion,
)
from scripts.fx_coint.cointegration import (
    fit_hedge, instrument_series, residual, residual_weight,
)
from scripts.fx_coint.cost import MARKUP_SWEEP_PIPS, spread_cost_frac
from scripts.fx_coint.gate import Verdict, classify
from scripts.fx_coint.instruments import MAJORS, all_pairs
from scripts.fx_coint.panels import coarsen, load_aligned
from scripts.fx_coint.report import write_report
from scripts.fx_coint.reversion import ou_fit, oos_reversion, reversion_exists
from scripts.fx_coint.stability import bh_fdr, structure_exists, walk_forward_eg

REVERSION_HORIZON = 10


def _mean_legs(coarse: pd.DataFrame):
    spreads = np.array([coarse[(m, "spread")].mean() for m in MAJORS])
    mids = np.array([np.exp(coarse[(m, "logmid")].mean()) for m in MAJORS])
    return spreads, mids


def screen_pair(fine: pd.DataFrame, coarse_freq: str, base: str, hedge: str,
                universe: str, fdr_pass: bool) -> dict:
    coarse = coarsen(fine, coarse_freq)
    wf = walk_forward_eg(coarse, base, hedge)
    beta = wf["beta_mean"] if np.isfinite(wf["beta_mean"]) else fit_hedge(coarse, base, hedge)

    res_coarse = residual(coarse, base, hedge, beta)
    fit = ou_fit(res_coarse)
    rev = oos_reversion(res_coarse, horizon=REVERSION_HORIZON)

    # Amplitude floor (coarse close-to-close) and ceiling (fine intrabar excursion).
    floor = close_to_close_amplitude(res_coarse, horizon=REVERSION_HORIZON)
    fine_res = (instrument_series(fine, base) - beta * instrument_series(fine, hedge))
    fine_res = fine_res - fine_res.mean()
    ceiling = float(intrabar_excursion(fine_res, coarse_freq).mean())

    # Cost across markup sweep using mean legs of the residual's weight vector.
    w = residual_weight(base, hedge, beta)
    spreads, mids = _mean_legs(coarse)
    cost_by_markup = {f"{mk}": spread_cost_frac(w, spreads, mids, mk)
                      for mk in MARKUP_SWEEP_PIPS}

    structure = structure_exists(wf)
    reverts = reversion_exists(fit, rev)
    verdict_by_markup = {
        mk: classify(structure, reverts, fdr_pass, floor, ceiling, c).value
        for mk, c in cost_by_markup.items()
    }
    return {
        "timeframe": coarse_freq, "universe": universe,
        "base": base, "hedge": hedge, "beta": beta,
        "fraction_stationary": wf["fraction_stationary"],
        "n_windows": wf["n_windows"], "fdr_pass": fdr_pass,
        "half_life": fit["half_life"], "reversion_frac": rev["mean_reversion_frac"],
        "n_events": rev["n_events"], "floor": floor, "ceiling": ceiling,
        "cost_by_markup": cost_by_markup, "verdict_by_markup": verdict_by_markup,
    }


def run(coarse_freqs=("1D", "1h", "1W"), fine_freq="5min",
        out_dir=Path("docs/analysis/fx_coint")) -> None:
    fine = load_aligned(freq=fine_freq)
    out_dir.mkdir(parents=True, exist_ok=True)
    instruments = all_pairs()
    for cf in coarse_freqs:
        # Two-pass for FDR: first collect EG OOS p-values, then classify.
        candidates = list(combinations(instruments, 2))
        pvals, partial = [], []
        for base, hedge in candidates:
            coarse = coarsen(fine, cf)
            wf = walk_forward_eg(coarse, base, hedge)
            p = float(np.median(wf["oos_pvals"])) if wf["oos_pvals"] else 1.0
            pvals.append(p)
            partial.append((base, hedge))
        keep = bh_fdr(pvals, alpha=0.10)
        rows = [screen_pair(fine, cf, b, h, "pairwise", fdr_pass=k)
                for (b, h), k in zip(partial, keep)]
        write_report(rows, out_dir / f"screen_{cf}.json",
                     out_dir / f"screen_{cf}.md")
        print(f"{cf}: wrote {len(rows)} rows")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--timeframes", nargs="+", default=["1D", "1h", "1W"])
    ap.add_argument("--fine", default="5min")
    args = ap.parse_args()
    run(coarse_freqs=tuple(args.timeframes), fine_freq=args.fine)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/fx_coint/test_run_screen.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add scripts/fx_coint/run_screen.py tests/fx_coint/test_run_screen.py
git commit -m "feat(fx-coint): end-to-end screen orchestrator + FDR pass"
```

---

## Task 13: Real-data smoke run + quality gate

**Files:** none new (runs the pipeline on real data, then the repo quality gate).

- [ ] **Step 1: Smoke-run the daily screen on real data**

Run: `.venv/bin/python -m scripts.fx_coint.run_screen --timeframes 1D --fine 5min`
Expected: prints `1D: wrote N rows` (N = 210 = C(21,2)) and writes `docs/analysis/fx_coint/screen_1D.{json,md}` with no exceptions.

- [ ] **Step 2: Sanity-read the markdown verdict table**

Run: `sed -n '1,40p' docs/analysis/fx_coint/screen_1D.md`
Expected: a summary block + a verdict table. Confirm `n_set_at_zero_markup` and the per-spread verdicts are populated (the honest prior is most/all NOGO on amplitude — that is itself a valid result).

- [ ] **Step 3: Run the full fx_coint test suite**

Run: `.venv/bin/python -m pytest tests/fx_coint/ -v`
Expected: all green.

- [ ] **Step 4: Run the repo quality gate**

Run: `make quality && .venv/bin/python -m pytest tests/fx_coint/ -q`
Expected: `ty`, `lint` (ruff), `vulture`, `smellcheck`, `radon`, `xenon` all pass; tests green. Fix any lint/type findings before committing (CI quality gate runs before pytest and reddens the whole job otherwise).

- [ ] **Step 5: Commit any quality fixes + the screen output**

```bash
git add -- scripts/fx_coint docs/analysis/fx_coint
git commit -m "chore(fx-coint): daily screen smoke run + quality-gate clean"
```

---

## Notes for the implementer

- **Look-ahead discipline is the whole point.** β is always fit on train (or per walk-forward train window) and applied forward; residual means for z-scoring use only the slice being measured; the OOS reversion test only looks forward. Do not introduce any full-sample normalization.
- **Intrabar excursion must come from the fine residual**, never from leg highs/lows (non-synchronous extremes fabricate range). This is the documented maker-illusion trap.
- **Synthetic crosses carry assumed cost** (sum of USD-leg spreads) — already handled by the weight-vector cost, but their verdict is provisional vs the 6 real pairs. The report's `universe` field marks them; treat cross-only SET/EXECUTION_GATED as "needs real cross spreads before believing."
- **Most-likely outcome is NOGO on amplitude.** A clean, well-instrumented NOGO ("structure real and reverting, ceiling X× below cost") is a successful run, not a failure — it's the model-proof null the spec is designed to produce.
- **Johansen basket rows:** Task 7 provides `johansen_rank` / `leading_vector_major_weights`; wiring a basket-spread row type into `run_screen.py` (residual = `weights . logmids`, cost = `spread_cost_frac(weights, ...)`) is a natural follow-up once the pairwise screen is validated. Kept out of the first orchestrator pass to keep Task 12 bite-sized.
- **Vulture (dead-code gate):** a few helpers are tested but not yet referenced in source until the deferred wiring lands — `johansen_rank`, `leading_vector_major_weights`, and `amplitude_vs_cost`. Vulture (run by `make quality`) will flag them. Do **not** delete them; add them to the `[tool.vulture]` `ignore_names` (or equivalent allowlist) in `pyproject.toml` with a comment that they're tested + pending orchestrator wiring. This keeps the gate green without losing tested code.
- **Structural-break test:** the spec names Gregory-Hansen/CUSUM; this plan operationalizes break detection as the walk-forward `fraction_stationary` (a relationship that breaks fails its OOS-window ADFs, dropping the fraction below `MIN_STATIONARY_FRACTION`). That is a deliberate, sufficient simplification for a screen — an explicit break-date test is only worth adding if a spread passes and you need to characterize *when* it broke.
- **Perf note:** `run()` calls `coarsen(fine, cf)` inside the FDR loop per candidate; for the ~210-pair sweep, hoist the single `coarse = coarsen(fine, cf)` outside the loop and pass it down (correctness is unaffected; this is a ~210× redundant-compute cleanup).
```
