# BoostLSS XS Anomaly Detection + Meta-Labeler Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a distributional boosting pipeline that models the full conditional return distribution across a 21-pair FX universe at 1000-tick resolution, flags anomalous (symbol, bar) observations across four channels, and passes those flags to a meta-labeler that assesses 5-bar gross profitability.

**Architecture:** Five BoostLSS models (one per horizon N=1..5) × two distribution families (StudentTLSS, GEVLSS) fit on pooled (symbol, bar) rows with within-symbol + cross-sectional features. Four-channel flagging (μ, σ, ν per family; ν acts as tail-asymmetry in GEV). HistGBM meta-labeler trained on OOS-only flags across all horizons and families.

**Tech Stack:** `boostlss-py` (Rust-backed distributional boosting), `polars`, `numpy`, `pandas`, `scikit-learn` (HistGBM), `scipy` (kurtosis, MAD).

## Global Constraints

- Data root: `/Users/danielfisher/repositories/behemoth/data/tick_bars/`; files named `{SYMBOL}_1m_flow.parquet` with columns `bucket` (datetime[μs]), `mid` (f64), `n_ticks` (i64)
- 1000-tick bars are built from 1m flow files by cumulating `n_ticks` — there are no pre-built tick bar parquets
- `boostlss-py` API: `from boostlss_py import PyFamily, PyLinearLearner, PyTreeLearner, BoostLssModel`
- StudentTLSS parameters: `"mu"` (location, identity link), `"sigma"` (scale, log link), `"nu"` (degrees of freedom, log link)
- GEVLSS parameters: `"mu"` (location, identity link), `"sigma"` (scale, log link), `"nu"` (shape ξ, identity link — positive = heavy right tail, negative = bounded upper tail)
- No look-ahead anywhere: all XS features use backward as-of join (`close_ts` of peer ≤ `close_ts` of target bar)
- WFO: 5 causal expanding folds; hyperparameters fixed at `mstop=200, step_length=0.1, max_depth=3` (tunable post-exploration)
- USD orientation: EURUSD/GBPUSD/AUDUSD/NZDUSD sign=+1 (USD quote), USDJPY/USDCAD/USDCHF sign=−1 (USD base)
- USDJPY encoded with `is_jpy=1`; pooled with all others (do not exclude)
- Gross returns only — no cost adjustment at this stage
- Line length 100, ruff lint (`E`, `F`, `W`), `ty` type checking — run `make quality` before any commit
- All new files in `scripts/boostlss_xs/`; tests in `tests/`

---

## File Map

| File | Responsibility |
|---|---|
| `scripts/boostlss_xs/__init__.py` | Empty package marker |
| `scripts/boostlss_xs/universe.py` | Load all 21-pair 1m flow parquets, build 1000-tick bars, orient USD, vol-standardize, return per-symbol DataFrames |
| `scripts/boostlss_xs/features.py` | `build_features()`: within-symbol + XS robust features → numpy array + feature name list |
| `scripts/boostlss_xs/model.py` | `BoostLssWFO`: family-parameterized 5-fold WFO, fits N horizons, returns OOS parameter predictions |
| `scripts/boostlss_xs/flagging.py` | `flag_channels()`: converts predicted parameters to binary flags + magnitudes per channel |
| `scripts/boostlss_xs/meta_labeler.py` | `MetaLabeler`: HistGBM on OOS flags across all horizons; constructs labels and predicts P(profitable) |
| `scripts/boostlss_xs/run.py` | `run_pipeline()`: end-to-end for both families, writes trade log CSV and comparison report |
| `tests/test_boostlss_xs_universe.py` | Universe loader tests |
| `tests/test_boostlss_xs_features.py` | Feature engineering tests (causal + correctness) |
| `tests/test_boostlss_xs_flagging.py` | Flagging channel logic tests |
| `tests/test_boostlss_xs_meta_labeler.py` | Meta-labeler label construction + prediction tests |

---

## Task 1: Add Dependency + Universe Loader

**Files:**
- Modify: `pyproject.toml`
- Create: `scripts/boostlss_xs/__init__.py`
- Create: `scripts/boostlss_xs/universe.py`
- Create: `tests/test_boostlss_xs_universe.py`

**Interfaces:**
- Produces: `load_universe(data_dir: str) -> dict[str, pl.DataFrame]`
  - Returns dict keyed by symbol (e.g. `"EURUSD"`) → polars DataFrame with columns:
    `close_ts` (datetime), `mid` (f64), `n_ticks` (i64), `log_ret_bps` (f64), `vol_std` (f64), `is_jpy` (i64)
  - `log_ret_bps`: log return in basis points, oriented to USD-strength
  - `vol_std`: each symbol's returns divided by its full-sample MAD (vol-standardization for pooling)

- [ ] **Step 1: Add boostlss-py to pyproject.toml**

In `pyproject.toml`, add to the `dependencies` list:
```toml
"boostlss-py>=0.1.0",
```
Then run:
```bash
uv sync
```
Expected: resolves without error. If version constraint fails, use `"boostlss-py"` without version pin.

- [ ] **Step 2: Verify import works**

```bash
uv run python -c "from boostlss_py import PyFamily, PyTreeLearner, BoostLssModel; print('ok')"
```
Expected: `ok`

- [ ] **Step 3: Write the failing test**

Create `tests/test_boostlss_xs_universe.py`:
```python
"""Tests for universe.py loader."""
from __future__ import annotations

import numpy as np
import polars as pl
import pytest

DATA_DIR = "/Users/danielfisher/repositories/behemoth/data/tick_bars"


def test_load_universe_returns_dict():
    from scripts.boostlss_xs.universe import load_universe

    result = load_universe(DATA_DIR)
    assert isinstance(result, dict)
    assert len(result) >= 6  # at least the 6 majors


def test_each_symbol_has_required_columns():
    from scripts.boostlss_xs.universe import load_universe

    result = load_universe(DATA_DIR)
    required = {"close_ts", "mid", "n_ticks", "log_ret_bps", "vol_std", "is_jpy"}
    for sym, df in result.items():
        assert required <= set(df.columns), f"{sym} missing columns"


def test_usd_orientation_eurusd():
    """EURUSD price rise = USD weakness → log_ret_bps should be negated vs raw."""
    from scripts.boostlss_xs.universe import load_universe

    result = load_universe(DATA_DIR)
    eurusd = result["EURUSD"]
    # raw return = log(mid[t]/mid[t-1]) * 1e4; oriented = sign=-1 → negated
    raw = (eurusd["mid"].log() - eurusd["mid"].shift(1).log()) * 1e4
    expected = raw * -1
    # compare non-null rows (first row is null due to diff)
    a = eurusd["log_ret_bps"].drop_nulls().to_numpy()
    b = expected.drop_nulls().to_numpy()
    np.testing.assert_allclose(a, b, rtol=1e-6)


def test_usdjpy_is_jpy_flag():
    from scripts.boostlss_xs.universe import load_universe

    result = load_universe(DATA_DIR)
    assert result["USDJPY"]["is_jpy"].unique().to_list() == [1]
    assert result["EURUSD"]["is_jpy"].unique().to_list() == [0]


def test_1000tick_bars_have_at_least_1000_ticks():
    from scripts.boostlss_xs.universe import load_universe

    result = load_universe(DATA_DIR)
    for sym, df in result.items():
        assert (df["n_ticks"] >= 1000).all(), f"{sym} has bars with < 1000 ticks"


def test_vol_std_has_unit_mad():
    """vol_std = log_ret_bps / full-sample MAD → MAD of vol_std ≈ 1."""
    from scripts.boostlss_xs.universe import load_universe

    result = load_universe(DATA_DIR)
    for sym, df in result.items():
        vals = df["vol_std"].drop_nulls().to_numpy()
        mad = float(np.median(np.abs(vals - np.median(vals))))
        assert abs(mad - 1.0) < 0.05, f"{sym} MAD={mad:.3f}, expected ≈1.0"
```

- [ ] **Step 4: Run test to verify it fails**

```bash
uv run pytest tests/test_boostlss_xs_universe.py -v
```
Expected: `ModuleNotFoundError: No module named 'scripts.boostlss_xs'`

- [ ] **Step 5: Create package marker**

Create `scripts/boostlss_xs/__init__.py` — empty file.

- [ ] **Step 6: Implement universe.py**

Create `scripts/boostlss_xs/universe.py`:
```python
"""Load 21-pair FX universe as 1000-tick bars, USD-oriented and vol-standardized."""
from __future__ import annotations

import glob
import os

import numpy as np
import polars as pl

# USD-strength orientation: +1 = pair return already = USD weakening (price up = USD down)
# We negate so that positive log_ret_bps = USD strengthened
_USD_SIGN: dict[str, int] = {
    "EURUSD": -1, "GBPUSD": -1, "AUDUSD": -1, "NZDUSD": -1,
    "USDJPY": 1,  "USDCAD": 1,  "USDCHF": 1,
}

_JPY_SYMBOLS = {"USDJPY", "EURJPY", "GBPJPY", "AUDJPY", "CADJPY", "NZDJPY"}


def _symbol_from_path(path: str) -> str:
    return os.path.basename(path).replace("_1m_flow.parquet", "")


def _usd_sign(symbol: str) -> int:
    """Return USD-strength orientation sign for a symbol."""
    # For crosses not in the dict, use +1 as a neutral default
    return _USD_SIGN.get(symbol, 1)


def _build_1000tick_bars(df: pl.DataFrame) -> pl.DataFrame:
    """Aggregate 1m flow bars into 1000-tick bars.

    Bars close when cumulative n_ticks >= 1000. The closing bar's timestamp
    and mid price define the bar. This is a causal aggregation — no look-ahead.
    """
    df = df.sort("bucket")
    ticks = df["n_ticks"].to_numpy()
    mids = df["mid"].to_numpy()
    buckets = df["bucket"].to_numpy()

    close_ts_list: list = []
    mid_list: list[float] = []
    n_ticks_list: list[int] = []

    cum: int = 0
    for i in range(len(ticks)):
        cum += int(ticks[i])
        if cum >= 1000:
            close_ts_list.append(buckets[i])
            mid_list.append(float(mids[i]))
            n_ticks_list.append(cum)
            cum = 0

    return pl.DataFrame({
        "close_ts": close_ts_list,
        "mid": mid_list,
        "n_ticks": n_ticks_list,
    }).with_columns(pl.col("close_ts").cast(pl.Datetime("us")))


def load_universe(data_dir: str) -> dict[str, pl.DataFrame]:
    """Load all available symbols as 1000-tick bars.

    Returns a dict symbol → DataFrame with columns:
        close_ts, mid, n_ticks, log_ret_bps, vol_std, is_jpy
    log_ret_bps is oriented to USD-strength (positive = USD strengthened).
    vol_std divides log_ret_bps by the full-sample MAD for cross-symbol pooling.
    """
    paths = sorted(glob.glob(os.path.join(data_dir, "*_1m_flow.parquet")))
    result: dict[str, pl.DataFrame] = {}

    for path in paths:
        sym = _symbol_from_path(path)
        raw = pl.read_parquet(path).sort("bucket")
        bars = _build_1000tick_bars(raw)

        # USD-oriented log return in bps
        sign = _usd_sign(sym)
        log_mid = bars["mid"].log()
        ret_raw = (log_mid - log_mid.shift(1)) * 1e4 * sign
        bars = bars.with_columns(ret_raw.alias("log_ret_bps"))

        # Vol-standardize: divide by full-sample MAD so pooled rows are comparable
        vals = bars["log_ret_bps"].drop_nulls().to_numpy()
        full_mad = float(np.median(np.abs(vals - np.median(vals)))) * 1.4826
        full_mad = max(full_mad, 1e-9)
        bars = bars.with_columns((pl.col("log_ret_bps") / full_mad).alias("vol_std"))

        # JPY flag
        is_jpy = 1 if sym in _JPY_SYMBOLS else 0
        bars = bars.with_columns(pl.lit(is_jpy).alias("is_jpy"))

        result[sym] = bars

    return result
```

- [ ] **Step 7: Run tests to verify they pass**

```bash
uv run pytest tests/test_boostlss_xs_universe.py -v
```
Expected: all 6 tests PASS.

- [ ] **Step 8: Run quality check**

```bash
make quality
```
Expected: no ruff or ty errors for the new files.

- [ ] **Step 9: Commit**

```bash
git add pyproject.toml scripts/boostlss_xs/__init__.py scripts/boostlss_xs/universe.py \
    tests/test_boostlss_xs_universe.py
git commit -m "feat(boostlss_xs): add boostlss-py dependency and 1000-tick universe loader"
```

---

## Task 2: Within-Symbol Features

**Files:**
- Create: `scripts/boostlss_xs/features.py`
- Create: `tests/test_boostlss_xs_features.py`

**Interfaces:**
- Consumes: `load_universe()` output — dict[str, pl.DataFrame] with `log_ret_bps`, `n_ticks`, `close_ts`, `is_jpy`
- Produces: `within_symbol_features(df: pl.DataFrame, symbol: str) -> pl.DataFrame`
  - Appends 17 feature columns to `df` (see `WITHIN_SYMBOL_FEATURES` list below)
  - All computations are strictly causal (rolling windows on past data only)

**Feature columns produced (indices 0–16 in final matrix):**

```
ret_5, ret_10, ret_20, ret_50, ret_100      — rolling sum of log_ret_bps
mad_vol_20, mad_vol_50                       — 1.4826 × rolling MAD of log_ret_bps
mom_rank_20, mom_rank_50                     — quantile rank of log_ret_bps in rolling window
n_ticks_bar                                  — log(n_ticks) of this bar
hour, dow, session                           — time features from close_ts
vol_of_vol_20                               — rolling MAD of mad_vol_20
roll_kurt_50, roll_kurt_100                  — excess kurtosis of log_ret_bps in rolling window
tail_count_100                               — count of |log_ret_bps| > 3×mad_vol_20 in last 100
```

- [ ] **Step 1: Write the failing test**

Create `tests/test_boostlss_xs_features.py`:
```python
"""Tests for within-symbol feature engineering."""
from __future__ import annotations

import numpy as np
import polars as pl
import pytest

from scripts.boostlss_xs.universe import load_universe

DATA_DIR = "/Users/danielfisher/repositories/behemoth/data/tick_bars"


@pytest.fixture(scope="module")
def eurusd_bars():
    uni = load_universe(DATA_DIR)
    return uni["EURUSD"]


def test_within_symbol_features_adds_all_columns(eurusd_bars):
    from scripts.boostlss_xs.features import WITHIN_SYMBOL_FEATURES, within_symbol_features

    result = within_symbol_features(eurusd_bars, "EURUSD")
    for col in WITHIN_SYMBOL_FEATURES:
        assert col in result.columns, f"missing column: {col}"


def test_rolling_ret_5_is_sum_of_last_5(eurusd_bars):
    from scripts.boostlss_xs.features import within_symbol_features

    result = within_symbol_features(eurusd_bars, "EURUSD")
    rets = eurusd_bars["log_ret_bps"].to_numpy()
    expected_ret5 = sum(rets[10:15])  # row 14 = sum of rows 10..14
    actual = result["ret_5"].to_numpy()[14]
    assert abs(actual - expected_ret5) < 1e-6


def test_no_look_ahead_in_rolling_features(eurusd_bars):
    """Causal check: features at row i must not use data from row i+1."""
    from scripts.boostlss_xs.features import within_symbol_features

    # Build features on first N rows; check feature at N-1 matches same row in full build
    N = 200
    sub = eurusd_bars.head(N)
    full = within_symbol_features(eurusd_bars, "EURUSD")
    partial = within_symbol_features(sub, "EURUSD")

    full_val = full["mad_vol_20"].to_numpy()[N - 1]
    partial_val = partial["mad_vol_20"].to_numpy()[N - 1]
    assert abs(full_val - partial_val) < 1e-9, (
        f"Look-ahead detected: full={full_val}, partial={partial_val}"
    )


def test_mom_rank_in_unit_interval(eurusd_bars):
    from scripts.boostlss_xs.features import within_symbol_features

    result = within_symbol_features(eurusd_bars, "EURUSD")
    ranks = result["mom_rank_20"].drop_nulls().to_numpy()
    assert ranks.min() >= 0.0
    assert ranks.max() <= 1.0


def test_session_flag_values(eurusd_bars):
    from scripts.boostlss_xs.features import within_symbol_features

    result = within_symbol_features(eurusd_bars, "EURUSD")
    assert set(result["session"].drop_nulls().unique().to_list()).issubset({0, 1, 2, 3})


def test_tail_count_non_negative(eurusd_bars):
    from scripts.boostlss_xs.features import within_symbol_features

    result = within_symbol_features(eurusd_bars, "EURUSD")
    assert (result["tail_count_100"].drop_nulls() >= 0).all()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_boostlss_xs_features.py -v
```
Expected: `ImportError: cannot import name 'within_symbol_features'`

- [ ] **Step 3: Implement features.py (within-symbol part)**

Create `scripts/boostlss_xs/features.py`:
```python
"""Feature engineering for BoostLSS XS anomaly pipeline.

Two stages:
1. within_symbol_features(): per-symbol rolling features, strictly causal.
2. xs_features(): cross-sectional features via backward as-of join (added in Task 3).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import polars as pl
from scipy.stats import kurtosis as scipy_kurtosis

if TYPE_CHECKING:
    pass

# Ordered list of within-symbol feature column names (indices 0-16 in final matrix)
WITHIN_SYMBOL_FEATURES: list[str] = [
    "ret_5", "ret_10", "ret_20", "ret_50", "ret_100",
    "mad_vol_20", "mad_vol_50",
    "mom_rank_20", "mom_rank_50",
    "n_ticks_bar",
    "hour", "dow", "session",
    "vol_of_vol_20",
    "roll_kurt_50", "roll_kurt_100",
    "tail_count_100",
]


def _rolling_mad(arr: np.ndarray, window: int) -> np.ndarray:
    """Causal rolling 1.4826×MAD. Returns nan for rows with < window observations."""
    out = np.full(len(arr), np.nan)
    for i in range(window - 1, len(arr)):
        w = arr[i - window + 1: i + 1]
        out[i] = 1.4826 * float(np.median(np.abs(w - np.median(w))))
    return out


def _rolling_quantile_rank(arr: np.ndarray, window: int) -> np.ndarray:
    """Rank of arr[i] within arr[i-window+1:i+1], normalized to [0,1]."""
    out = np.full(len(arr), np.nan)
    for i in range(window - 1, len(arr)):
        w = arr[i - window + 1: i + 1]
        rank = float(np.sum(w <= arr[i])) / window
        out[i] = rank
    return out


def _rolling_excess_kurtosis(arr: np.ndarray, window: int) -> np.ndarray:
    """Causal rolling excess kurtosis (Fisher definition, bias=False)."""
    out = np.full(len(arr), np.nan)
    for i in range(window - 1, len(arr)):
        w = arr[i - window + 1: i + 1]
        if np.std(w) < 1e-12:
            out[i] = 0.0
        else:
            out[i] = float(scipy_kurtosis(w, fisher=True, bias=False))
    return out


def _session_flag(hour: int) -> int:
    """Classify UTC hour into FX session: 0=Asia, 1=London, 2=Overlap, 3=NY."""
    if 22 <= hour or hour < 8:
        return 0  # Asia
    if 8 <= hour < 12:
        return 1  # London
    if 12 <= hour < 16:
        return 2  # London/NY overlap
    return 3  # NY


def within_symbol_features(df: pl.DataFrame, symbol: str) -> pl.DataFrame:  # noqa: ARG001
    """Append 17 within-symbol feature columns to df. Strictly causal."""
    ret = df["log_ret_bps"].to_numpy()
    close_ts = df["close_ts"].to_numpy()
    n_ticks = df["n_ticks"].to_numpy()

    # Rolling return sums
    for L, col in [(5, "ret_5"), (10, "ret_10"), (20, "ret_20"),
                   (50, "ret_50"), (100, "ret_100")]:
        out = np.full(len(ret), np.nan)
        cs = np.nancumsum(np.where(np.isnan(ret), 0, ret))
        # sum of last L bars ending at i = cs[i] - cs[i-L] (handle boundary)
        for i in range(L - 1, len(ret)):
            if i - L >= 0:
                out[i] = cs[i] - cs[i - L]
            else:
                out[i] = cs[i]
        df = df.with_columns(pl.Series(col, out))

    # Robust vol (rolling MAD)
    mad20 = _rolling_mad(ret, 20)
    mad50 = _rolling_mad(ret, 50)
    df = df.with_columns([
        pl.Series("mad_vol_20", mad20),
        pl.Series("mad_vol_50", mad50),
    ])

    # Momentum quantile rank
    df = df.with_columns([
        pl.Series("mom_rank_20", _rolling_quantile_rank(ret, 20)),
        pl.Series("mom_rank_50", _rolling_quantile_rank(ret, 50)),
    ])

    # Bar activity: log(n_ticks)
    df = df.with_columns(pl.Series("n_ticks_bar", np.log(n_ticks.astype(float) + 1)))

    # Time features from close_ts
    import pandas as pd
    ts = pd.to_datetime(close_ts).tz_localize("UTC") if hasattr(
        pd.to_datetime(close_ts[:1]), "tz"
    ) else pd.to_datetime(close_ts)
    hours = ts.hour.to_numpy().astype(int)
    dows = ts.dayofweek.to_numpy().astype(int)
    sessions = np.array([_session_flag(int(h)) for h in hours], dtype=int)
    df = df.with_columns([
        pl.Series("hour", hours),
        pl.Series("dow", dows),
        pl.Series("session", sessions),
    ])

    # Vol-of-vol: rolling MAD of mad_vol_20
    df = df.with_columns(pl.Series("vol_of_vol_20", _rolling_mad(mad20, 20)))

    # Rolling excess kurtosis
    df = df.with_columns([
        pl.Series("roll_kurt_50", _rolling_excess_kurtosis(ret, 50)),
        pl.Series("roll_kurt_100", _rolling_excess_kurtosis(ret, 100)),
    ])

    # Tail event count: bars in last 100 where |ret| > 3×mad_vol_20
    tail = np.full(len(ret), np.nan)
    for i in range(99, len(ret)):
        w_ret = np.abs(ret[i - 99: i + 1])
        threshold = 3.0 * (mad20[i] if not np.isnan(mad20[i]) else 0.0)
        tail[i] = float(np.sum(w_ret > threshold))
    df = df.with_columns(pl.Series("tail_count_100", tail))

    return df
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_boostlss_xs_features.py -v
```
Expected: all 6 tests PASS. Note: `_rolling_mad`, `_rolling_quantile_rank`, `_rolling_excess_kurtosis` are O(N×W) — slow on 3M rows. If test runtime exceeds 60s, reduce fixture to `.head(2000)` in the test file.

- [ ] **Step 5: Quality check + commit**

```bash
make quality
git add scripts/boostlss_xs/features.py tests/test_boostlss_xs_features.py
git commit -m "feat(boostlss_xs): within-symbol features (rolling robust + time)"
```

---

## Task 3: Cross-Sectional Features

**Files:**
- Modify: `scripts/boostlss_xs/features.py` (add `xs_features()` and `build_features()`)
- Modify: `tests/test_boostlss_xs_features.py` (add XS tests)

**Interfaces:**
- Consumes: `load_universe()` output
- Produces:
  - `xs_features(universe: dict[str, pl.DataFrame]) -> dict[str, pl.DataFrame]`
    - Appends 13 XS feature columns to each symbol's DataFrame (see `XS_FEATURES` list)
  - `build_features(universe: dict[str, pl.DataFrame]) -> tuple[np.ndarray, np.ndarray, list[str], list[str]]`
    - Returns `(X, close_ts_arr, feature_names, symbols_arr)` — stacked matrix of all (symbol, bar) rows
    - `X`: shape `(total_rows, 30)`, float32, NaN rows dropped
    - `close_ts_arr`: datetime per row, aligned with X
    - `symbols_arr`: symbol string per row, aligned with X

**XS feature columns produced (indices 17–29 in final matrix):**
```
xs_rank, xs_robust_z, usd_factor_resid,
xs_iqr, xs_iqr_trend, xs_dispersion_zz,
loo_robust_z, xs_kurt, xs_bimodality,
pair_corr_mean, mom_vol_interaction,
is_jpy, symbol_code
```

- [ ] **Step 1: Add XS tests to test file**

Append to `tests/test_boostlss_xs_features.py`:
```python
def test_xs_features_adds_all_xs_columns():
    from scripts.boostlss_xs.features import XS_FEATURES, xs_features
    from scripts.boostlss_xs.universe import load_universe

    uni = load_universe(DATA_DIR)
    # Add within-symbol features first (xs_features requires them)
    from scripts.boostlss_xs.features import within_symbol_features
    uni = {sym: within_symbol_features(df, sym) for sym, df in uni.items()}
    result = xs_features(uni)
    for sym, df in result.items():
        for col in XS_FEATURES:
            assert col in df.columns, f"{sym} missing xs column: {col}"


def test_xs_no_look_ahead():
    """XS features at bar T must not use peer bars with close_ts > T."""
    from scripts.boostlss_xs.features import within_symbol_features, xs_features
    from scripts.boostlss_xs.universe import load_universe

    uni = load_universe(DATA_DIR)
    # Truncate EURUSD to simulate future data being unavailable
    cutoff_idx = len(uni["EURUSD"]) // 2
    cutoff_ts = uni["EURUSD"]["close_ts"].to_numpy()[cutoff_idx]

    uni_ws = {sym: within_symbol_features(df, sym) for sym, df in uni.items()}
    full = xs_features(uni_ws)

    # Now run with EURUSD truncated at cutoff
    uni_trunc = dict(uni_ws)
    uni_trunc["EURUSD"] = uni_ws["EURUSD"].filter(
        pl.col("close_ts") <= pl.lit(cutoff_ts).cast(pl.Datetime("us"))
    )
    partial = xs_features(uni_trunc)

    # xs_rank at the last row of partial must match xs_rank at cutoff_idx in full
    full_val = full["EURUSD"]["xs_rank"].to_numpy()[cutoff_idx]
    partial_val = partial["EURUSD"]["xs_rank"].to_numpy()[-1]
    assert abs(full_val - partial_val) < 1e-6, (
        f"Look-ahead in xs_rank: full={full_val:.4f}, partial={partial_val:.4f}"
    )


def test_build_features_shape():
    from scripts.boostlss_xs.features import build_features, within_symbol_features, xs_features
    from scripts.boostlss_xs.universe import load_universe

    uni = load_universe(DATA_DIR)
    uni = {sym: within_symbol_features(df, sym) for sym, df in uni.items()}
    uni = xs_features(uni)
    X, close_ts_arr, feature_names, symbols_arr = build_features(uni)

    assert X.ndim == 2
    assert X.shape[1] == 30
    assert len(close_ts_arr) == X.shape[0]
    assert len(symbols_arr) == X.shape[0]
    assert len(feature_names) == 30
    assert X.dtype == np.float32
```

- [ ] **Step 2: Run new tests to verify they fail**

```bash
uv run pytest tests/test_boostlss_xs_features.py::test_xs_features_adds_all_xs_columns -v
```
Expected: `ImportError: cannot import name 'xs_features'`

- [ ] **Step 3: Add xs_features() and build_features() to features.py**

Append to `scripts/boostlss_xs/features.py`:
```python
# Ordered XS feature column names (indices 17-29 in final matrix)
XS_FEATURES: list[str] = [
    "xs_rank", "xs_robust_z", "usd_factor_resid",
    "xs_iqr", "xs_iqr_trend", "xs_dispersion_zz",
    "loo_robust_z", "xs_kurt", "xs_bimodality",
    "pair_corr_mean", "mom_vol_interaction",
    "is_jpy", "symbol_code",
]

# Full ordered feature list (30 features)
ALL_FEATURES: list[str] = WITHIN_SYMBOL_FEATURES + XS_FEATURES

# Symbol encoding (sorted alphabetically, stable)
_SYMBOL_CODES: dict[str, int] = {}


def _encode_symbol(symbol: str) -> int:
    if symbol not in _SYMBOL_CODES:
        _SYMBOL_CODES[symbol] = len(_SYMBOL_CODES)
    return _SYMBOL_CODES[symbol]


def xs_features(universe: dict[str, pl.DataFrame]) -> dict[str, pl.DataFrame]:
    """Append cross-sectional features to each symbol using backward as-of join.

    For each target (symbol, bar) at close_ts=T, XS features are computed from
    the most recent bar for each peer with close_ts <= T (look-ahead-free).
    """
    # Pre-sort each symbol's frame by close_ts for merge_asof
    sorted_uni = {sym: df.sort("close_ts") for sym, df in universe.items()}
    symbols = sorted(sorted_uni.keys())
    n_syms = len(symbols)

    result: dict[str, pl.DataFrame] = {}

    for target_sym in symbols:
        target = sorted_uni[target_sym].clone()
        target_ts = target["close_ts"]
        target_ret = target["log_ret_bps"].to_numpy()
        n = len(target)

        # Collect peer returns at each target bar via backward as-of join
        peer_rets: dict[str, np.ndarray] = {}
        for peer_sym in symbols:
            if peer_sym == target_sym:
                continue
            peer = sorted_uni[peer_sym].select(["close_ts", "log_ret_bps"])
            # merge_asof: for each target close_ts, find latest peer bar with ts <= target_ts
            joined = target.select(["close_ts"]).join_asof(
                peer.rename({"log_ret_bps": f"_peer_{peer_sym}"}),
                on="close_ts",
                strategy="backward",
            )
            peer_rets[peer_sym] = joined[f"_peer_{peer_sym}"].to_numpy()

        # Stack peer returns: shape (n, n_peers)
        peer_syms = [s for s in symbols if s != target_sym]
        peer_mat = np.column_stack([peer_rets[s] for s in peer_syms])  # (n, n_peers)

        # Full cross-section: (n, n_syms) — target + peers combined
        full_mat = np.column_stack([target_ret, peer_mat])

        # XS rank of target (ordinal rank normalized [0,1])
        xs_rank = np.array([
            float(np.sum(~np.isnan(full_mat[i]) & (full_mat[i] <= target_ret[i])))
            / max(float(np.sum(~np.isnan(full_mat[i]))), 1.0)
            for i in range(n)
        ])

        # XS robust z: (target - xs_median) / (1.4826 × xs_MAD)
        xs_robust_z = np.full(n, np.nan)
        xs_iqr = np.full(n, np.nan)
        xs_kurt = np.full(n, np.nan)
        xs_bimodality = np.full(n, np.nan)

        for i in range(n):
            row = full_mat[i]
            valid = row[~np.isnan(row)]
            if len(valid) < 3:
                continue
            med = float(np.median(valid))
            mad = 1.4826 * float(np.median(np.abs(valid - med)))
            xs_robust_z[i] = (target_ret[i] - med) / max(mad, 1e-9)
            q75, q25 = float(np.percentile(valid, 75)), float(np.percentile(valid, 25))
            xs_iqr[i] = q75 - q25
            if len(valid) >= 4:
                xs_kurt[i] = float(scipy_kurtosis(valid, fisher=True, bias=False))
                sk = float(np.mean(((valid - np.mean(valid)) / (np.std(valid) + 1e-9)) ** 3))
                xs_bimodality[i] = (sk ** 2 + 1.0) / (xs_kurt[i] + 3.0 + 1e-9)

        # XS IQR trend: bar-over-bar change
        xs_iqr_trend = np.concatenate([[np.nan], np.diff(xs_iqr)])

        # XS dispersion z-of-z: robust z of xs_iqr within its own rolling history (W=100)
        xs_dispersion_zz = _rolling_mad(xs_iqr, 100)

        # LOO robust z: target vs peers only (excluding self)
        loo_robust_z = np.full(n, np.nan)
        for i in range(n):
            peers = peer_mat[i]
            valid = peers[~np.isnan(peers)]
            if len(valid) < 2:
                continue
            med = float(np.median(valid))
            mad = 1.4826 * float(np.median(np.abs(valid - med)))
            loo_robust_z[i] = (target_ret[i] - med) / max(mad, 1e-9)

        # USD-factor residual: causal rolling OLS residual of target vs basket mean
        basket = np.nanmean(full_mat, axis=1)
        usd_factor_resid = np.full(n, np.nan)
        W = 250
        for i in range(W, n):
            yw = target_ret[i - W:i]
            xw = basket[i - W:i]
            valid = ~(np.isnan(yw) | np.isnan(xw))
            if valid.sum() < 50:
                continue
            xv, yv = xw[valid], yw[valid]
            beta = float(np.cov(xv, yv)[0, 1]) / max(float(np.var(xv)), 1e-12)
            alpha = float(np.mean(yv)) - beta * float(np.mean(xv))
            usd_factor_resid[i] = target_ret[i] - (alpha + beta * basket[i])

        # Rolling mean pairwise correlation (W=100)
        pair_corr_mean = np.full(n, np.nan)
        for i in range(100, n):
            block = full_mat[i - 100:i]
            valid_cols = ~np.all(np.isnan(block), axis=0)
            if valid_cols.sum() < 2:
                continue
            with np.errstate(divide="ignore", invalid="ignore"):
                corr = np.corrcoef(block[:, valid_cols].T)
            if corr.shape[0] > 1:
                mask = ~np.eye(corr.shape[0], dtype=bool)
                pair_corr_mean[i] = float(np.nanmean(corr[mask]))

        # Interaction: mom_rank_20 × vol_of_vol_20
        mom_rank_20 = target["mom_rank_20"].to_numpy() if "mom_rank_20" in target.columns \
            else np.full(n, np.nan)
        vol_of_vol_20 = target["vol_of_vol_20"].to_numpy() if "vol_of_vol_20" in target.columns \
            else np.full(n, np.nan)
        mom_vol_interaction = mom_rank_20 * vol_of_vol_20

        # Symbol code
        sym_code = float(_encode_symbol(target_sym))

        target = target.with_columns([
            pl.Series("xs_rank", xs_rank),
            pl.Series("xs_robust_z", xs_robust_z),
            pl.Series("usd_factor_resid", usd_factor_resid),
            pl.Series("xs_iqr", xs_iqr),
            pl.Series("xs_iqr_trend", xs_iqr_trend),
            pl.Series("xs_dispersion_zz", xs_dispersion_zz),
            pl.Series("loo_robust_z", loo_robust_z),
            pl.Series("xs_kurt", xs_kurt),
            pl.Series("xs_bimodality", xs_bimodality),
            pl.Series("pair_corr_mean", pair_corr_mean),
            pl.Series("mom_vol_interaction", mom_vol_interaction),
            pl.col("is_jpy").cast(pl.Float64),
            pl.Series("symbol_code", np.full(n, sym_code)),
        ])
        result[target_sym] = target

    return result


def build_features(
    universe: dict[str, pl.DataFrame],
) -> tuple[np.ndarray, np.ndarray, list[str], list[str]]:
    """Stack all symbols into a single feature matrix.

    Returns:
        X: float32 array of shape (valid_rows, 30)
        close_ts_arr: datetime64 array aligned with X rows
        feature_names: list of 30 feature column names
        symbols_arr: symbol string per row
    """
    X_parts: list[np.ndarray] = []
    ts_parts: list[np.ndarray] = []
    sym_parts: list[list[str]] = []

    for sym in sorted(universe.keys()):
        df = universe[sym]
        mat = df.select(ALL_FEATURES).to_numpy().astype(np.float32)
        ts = df["close_ts"].to_numpy()

        # Drop rows with any NaN
        valid = ~np.any(np.isnan(mat), axis=1)
        X_parts.append(mat[valid])
        ts_parts.append(ts[valid])
        sym_parts.append([sym] * int(valid.sum()))

    X = np.vstack(X_parts)
    close_ts_arr = np.concatenate(ts_parts)
    symbols_arr: list[str] = sum(sym_parts, [])
    return X, close_ts_arr, ALL_FEATURES, symbols_arr
```

- [ ] **Step 4: Run all feature tests**

```bash
uv run pytest tests/test_boostlss_xs_features.py -v
```
Expected: all 9 tests PASS. If XS tests are slow due to O(N²) peer loops, this is expected — the implementation prioritises correctness; vectorised optimisation is a follow-on.

- [ ] **Step 5: Quality check + commit**

```bash
make quality
git add scripts/boostlss_xs/features.py tests/test_boostlss_xs_features.py
git commit -m "feat(boostlss_xs): cross-sectional features and stacked feature matrix"
```

---

## Task 4: BoostLSS WFO Model

**Files:**
- Create: `scripts/boostlss_xs/model.py`

**Interfaces:**
- Consumes:
  - `X: np.ndarray` — shape `(N, 30)`, float32
  - `y_all: np.ndarray` — shape `(N,)`, target returns (built per horizon in run.py)
  - `close_ts_arr: np.ndarray` — datetime64 per row (for fold splitting by time)
  - `family: str` — `"StudentTLSS"` or `"GEVLSS"`
- Produces: `BoostLssWFO.fit_predict(X, y_all, close_ts_arr) -> dict[str, np.ndarray]`
  - Returns `{"mu": arr, "sigma": arr, "nu": arr}` — OOS predictions, same length as X, NaN for train rows

```python
FAMILY_PARAMS: dict[str, list[str]] = {
    "StudentTLSS": ["mu", "sigma", "nu"],  # nu = degrees of freedom
    "GEVLSS":      ["mu", "sigma", "nu"],  # nu = shape ξ
}
```

- [ ] **Step 1: Implement model.py**

Create `scripts/boostlss_xs/model.py`:
```python
"""BoostLSS JSU/GEV causal walk-forward model."""
from __future__ import annotations

import numpy as np
from boostlss_py import BoostLssModel, PyFamily, PyTreeLearner

# Parameters exposed by each distribution family
FAMILY_PARAMS: dict[str, list[str]] = {
    "StudentTLSS": ["mu", "sigma", "nu"],
    "GEVLSS":      ["mu", "sigma", "nu"],
}

# Fixed hyperparameters — tune on fold 1 if needed
_MSTOP = 200
_STEP_LENGTH = 0.1
_MAX_DEPTH = 3
_N_FOLDS = 5


def _make_fold_boundaries(close_ts: np.ndarray, n_folds: int) -> list[tuple[int, int, int]]:
    """Return (train_end, test_start, test_end) index triples for expanding WFO.

    The series is split into n_folds+1 equal time blocks. Fold k uses blocks 0..k
    as train and block k+1 as test.
    """
    n = len(close_ts)
    block = n // (n_folds + 1)
    folds = []
    for k in range(n_folds):
        train_end = block * (k + 1)
        test_start = train_end
        test_end = min(block * (k + 2), n)
        folds.append((train_end, test_start, test_end))
    return folds


class BoostLssWFO:
    """Causal walk-forward BoostLSS model.

    For each fold: fit on train rows, predict on test rows.
    Assembles OOS predictions across all folds.
    """

    def __init__(self, family: str = "StudentTLSS") -> None:
        if family not in FAMILY_PARAMS:
            raise ValueError(f"family must be one of {list(FAMILY_PARAMS)}, got {family!r}")
        self.family = family
        self.params = FAMILY_PARAMS[family]

    def _build_model(self, n_features: int) -> BoostLssModel:
        model = BoostLssModel(
            PyFamily(self.family),
            mstop=_MSTOP,
            step_length=_STEP_LENGTH,
        )
        all_feat_idx = list(range(n_features))
        for param in self.params:
            model.add_learner(param, PyTreeLearner(
                feature_indices=all_feat_idx,
                max_depth=_MAX_DEPTH,
            ))
        return model

    def fit_predict(
        self,
        X: np.ndarray,
        y: np.ndarray,
        close_ts: np.ndarray,
    ) -> dict[str, np.ndarray]:
        """Fit WFO, return OOS parameter predictions (NaN for train rows)."""
        n, n_features = X.shape
        oos_preds: dict[str, np.ndarray] = {p: np.full(n, np.nan) for p in self.params}

        folds = _make_fold_boundaries(close_ts, _N_FOLDS)

        for fold_idx, (train_end, test_start, test_end) in enumerate(folds):
            X_train = X[:train_end].astype(np.float64)
            y_train = y[:train_end].astype(np.float64)
            X_test = X[test_start:test_end].astype(np.float64)

            # Drop NaN rows from training
            valid = ~(np.isnan(X_train).any(axis=1) | np.isnan(y_train))
            if valid.sum() < 100:
                continue

            model = self._build_model(n_features)
            model.fit(X_train[valid], y_train[valid])

            for param in self.params:
                pred = np.array(model.predict(X_test, param))
                oos_preds[param][test_start:test_end] = pred

            print(f"  Fold {fold_idx + 1}/{_N_FOLDS}: "
                  f"train={valid.sum()} rows, test={test_end - test_start} rows")

        return oos_preds
```

- [ ] **Step 2: Smoke test (no formal test file — model is tested end-to-end in Task 7)**

```bash
uv run python -c "
import numpy as np
from scripts.boostlss_xs.model import BoostLssWFO
rng = np.random.default_rng(0)
X = rng.standard_normal((500, 30)).astype(np.float32)
y = rng.standard_normal(500)
ts = np.arange(500, dtype='datetime64[s]')
wfo = BoostLssWFO('StudentTLSS')
preds = wfo.fit_predict(X, y, ts)
print('mu non-nan:', (~np.isnan(preds['mu'])).sum())
print('ok')
"
```
Expected: prints fold progress and `ok` with non-zero non-nan count.

- [ ] **Step 3: Quality check + commit**

```bash
make quality
git add scripts/boostlss_xs/model.py
git commit -m "feat(boostlss_xs): BoostLSS causal WFO wrapper (StudentTLSS + GEVLSS)"
```

---

## Task 5: Four-Channel Flagging

**Files:**
- Create: `scripts/boostlss_xs/flagging.py`
- Create: `tests/test_boostlss_xs_flagging.py`

**Interfaces:**
- Consumes: `preds: dict[str, np.ndarray]` from `BoostLssWFO.fit_predict()`; `y: np.ndarray` (target returns, for unconditional thresholds)
- Produces: `flag_channels(preds, y, family) -> dict[str, np.ndarray]`
  - Returns dict with keys: `"mu_flag"`, `"mu_mag"`, `"sigma_flag"`, `"sigma_mag"`, `"nu_flag"`, `"nu_mag"`, `"direction"` (sign of predicted mu, float ±1)
  - All arrays have same length as input preds arrays; NaN where preds are NaN

**Channel definitions:**

| Channel | Family | Trigger | Flag |
|---|---|---|---|
| μ (directional) | Both | \|pred_mu\| > 1.5 × unconditional MAD(y) | 1 if triggered |
| σ (calm-regime) | Both | pred_sigma < 20th pctile of OOS pred_sigma | 1 if triggered |
| ν (tail, Student-T) | StudentTLSS | pred_nu < 5 | 1 if triggered |
| ν (shape, GEV) | GEVLSS | \|pred_nu\| > 0.2 | 1 if triggered |

- [ ] **Step 1: Write the failing test**

Create `tests/test_boostlss_xs_flagging.py`:
```python
"""Tests for 4-channel flagging."""
from __future__ import annotations

import numpy as np
import pytest


def _mock_preds(n: int = 200) -> dict[str, np.ndarray]:
    """Synthetic OOS predictions — NaN for first 100 (train), values for rest."""
    rng = np.random.default_rng(42)
    preds = {
        "mu": np.concatenate([np.full(100, np.nan), rng.normal(0, 2.0, 100)]),
        "sigma": np.concatenate([np.full(100, np.nan), rng.uniform(0.5, 3.0, 100)]),
        "nu": np.concatenate([np.full(100, np.nan), rng.uniform(1.5, 20.0, 100)]),
    }
    return preds


def test_flag_channels_returns_expected_keys():
    from scripts.boostlss_xs.flagging import flag_channels

    preds = _mock_preds()
    y = np.random.default_rng(0).normal(0, 1, 200)
    result = flag_channels(preds, y, "StudentTLSS")
    for key in ["mu_flag", "mu_mag", "sigma_flag", "sigma_mag", "nu_flag", "nu_mag", "direction"]:
        assert key in result, f"missing key: {key}"


def test_mu_flag_fires_on_large_predicted_mu():
    from scripts.boostlss_xs.flagging import flag_channels

    preds = _mock_preds()
    y = np.random.default_rng(0).normal(0, 1, 200)
    # Force a large mu prediction
    preds["mu"][150] = 100.0
    result = flag_channels(preds, y, "StudentTLSS")
    assert result["mu_flag"][150] == 1


def test_mu_flag_zero_for_small_predicted_mu():
    from scripts.boostlss_xs.flagging import flag_channels

    preds = _mock_preds()
    y = np.zeros(200)
    preds["mu"][150] = 0.001  # tiny
    result = flag_channels(preds, y, "StudentTLSS")
    assert result["mu_flag"][150] == 0


def test_nu_flag_student_t_fires_below_5():
    from scripts.boostlss_xs.flagging import flag_channels

    preds = _mock_preds()
    preds["nu"][150] = 2.0  # below threshold of 5
    y = np.ones(200)
    result = flag_channels(preds, y, "StudentTLSS")
    assert result["nu_flag"][150] == 1


def test_nu_flag_gev_fires_on_large_abs_shape():
    from scripts.boostlss_xs.flagging import flag_channels

    preds = _mock_preds()
    preds["nu"][150] = 0.5  # |0.5| > 0.2
    y = np.ones(200)
    result = flag_channels(preds, y, "GEVLSS")
    assert result["nu_flag"][150] == 1


def test_direction_sign_matches_mu():
    from scripts.boostlss_xs.flagging import flag_channels

    preds = _mock_preds()
    preds["mu"][150] = 5.0
    preds["mu"][160] = -5.0
    y = np.ones(200)
    result = flag_channels(preds, y, "StudentTLSS")
    assert result["direction"][150] == 1.0
    assert result["direction"][160] == -1.0


def test_nan_propagated_for_train_rows():
    from scripts.boostlss_xs.flagging import flag_channels

    preds = _mock_preds()
    y = np.ones(200)
    result = flag_channels(preds, y, "StudentTLSS")
    assert np.isnan(result["mu_flag"][:100]).all()
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/test_boostlss_xs_flagging.py -v
```
Expected: `ImportError`

- [ ] **Step 3: Implement flagging.py**

Create `scripts/boostlss_xs/flagging.py`:
```python
"""Four-channel flagging from BoostLSS predicted distribution parameters."""
from __future__ import annotations

import numpy as np

_MU_MAD_MULTIPLIER = 1.5       # |pred_mu| > 1.5 × unconditional MAD(y)
_SIGMA_PERCENTILE = 20.0       # pred_sigma below 20th pctile of OOS sigma
_NU_STUDENT_T_THRESHOLD = 5.0  # pred_nu < 5 for Student-T → fat-tail flag
_NU_GEV_THRESHOLD = 0.2        # |pred_nu| > 0.2 for GEV → tail-asymmetry flag


def flag_channels(
    preds: dict[str, np.ndarray],
    y: np.ndarray,
    family: str,
) -> dict[str, np.ndarray]:
    """Convert predicted parameters to binary flags and magnitudes.

    Args:
        preds: output of BoostLssWFO.fit_predict() — {"mu", "sigma", "nu"}
        y: full target array (used to compute unconditional MAD threshold)
        family: "StudentTLSS" or "GEVLSS"

    Returns:
        dict with keys: mu_flag, mu_mag, sigma_flag, sigma_mag,
                        nu_flag, nu_mag, direction
        All arrays are same length as preds arrays.
        NaN where preds are NaN (train rows).
    """
    mu = preds["mu"]
    sigma = preds["sigma"]
    nu = preds["nu"]
    n = len(mu)

    # Unconditional MAD of y (on non-NaN y values)
    y_valid = y[~np.isnan(y)]
    uncond_mad = 1.4826 * float(np.median(np.abs(y_valid - np.median(y_valid))))
    mu_threshold = _MU_MAD_MULTIPLIER * max(uncond_mad, 1e-9)

    # OOS sigma 20th percentile (only where sigma is not NaN)
    oos_sigma = sigma[~np.isnan(sigma)]
    sigma_threshold = float(np.percentile(oos_sigma, _SIGMA_PERCENTILE)) if len(oos_sigma) > 0 \
        else 0.0

    # Initialise output arrays with NaN
    mu_flag = np.full(n, np.nan)
    mu_mag = np.full(n, np.nan)
    sigma_flag = np.full(n, np.nan)
    sigma_mag = np.full(n, np.nan)
    nu_flag = np.full(n, np.nan)
    nu_mag = np.full(n, np.nan)
    direction = np.full(n, np.nan)

    oos_mask = ~np.isnan(mu)

    mu_flag[oos_mask] = (np.abs(mu[oos_mask]) > mu_threshold).astype(float)
    mu_mag[oos_mask] = np.abs(mu[oos_mask])

    sigma_flag[oos_mask] = (sigma[oos_mask] < sigma_threshold).astype(float)
    sigma_mag[oos_mask] = sigma[oos_mask]

    if family == "StudentTLSS":
        nu_flag[oos_mask] = (nu[oos_mask] < _NU_STUDENT_T_THRESHOLD).astype(float)
    else:  # GEVLSS
        nu_flag[oos_mask] = (np.abs(nu[oos_mask]) > _NU_GEV_THRESHOLD).astype(float)
    nu_mag[oos_mask] = nu[oos_mask]

    direction[oos_mask] = np.sign(mu[oos_mask])

    return {
        "mu_flag": mu_flag,
        "mu_mag": mu_mag,
        "sigma_flag": sigma_flag,
        "sigma_mag": sigma_mag,
        "nu_flag": nu_flag,
        "nu_mag": nu_mag,
        "direction": direction,
    }
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_boostlss_xs_flagging.py -v
```
Expected: all 7 tests PASS.

- [ ] **Step 5: Quality check + commit**

```bash
make quality
git add scripts/boostlss_xs/flagging.py tests/test_boostlss_xs_flagging.py
git commit -m "feat(boostlss_xs): four-channel flagging from predicted distribution params"
```

---

## Task 6: Meta-Labeler

**Files:**
- Create: `scripts/boostlss_xs/meta_labeler.py`
- Create: `tests/test_boostlss_xs_meta_labeler.py`

**Interfaces:**
- Consumes:
  - `flags_by_horizon: dict[int, dict[str, np.ndarray]]` — keys are N=1..5; each value is output of `flag_channels()`
  - `y_by_horizon: dict[int, np.ndarray]` — gross return arrays per horizon
  - `direction: np.ndarray` — predicted direction from μ channel (for label construction)
  - `symbols_arr: list[str]` — symbol per row (for per-symbol label thresholds)
  - `close_ts_arr: np.ndarray` — timestamps (for WFO fold alignment)
- Produces: `MetaLabeler.fit_predict() -> np.ndarray`
  - Shape `(N,)` float array of P(profitable) predictions, NaN for train rows

**Label definition:** For horizon N, row i is labelled 1 if:
- `direction[i] != 0` (μ channel predicts a direction)
- `y_by_horizon[N][i] * direction[i] > symbol_median_abs_return[symbol_i][N]`

where `symbol_median_abs_return` is computed on training data only (causal).

**Meta-labeler inputs (30 features per row):**
- For each horizon N (1..5): mu_flag, mu_mag, sigma_flag, sigma_mag, nu_flag, nu_mag (6 per horizon = 30)
- `horizon_agreement`: count of horizons where mu_flag=1 across N=1..5
- `mu_sigma_agreement`: 1 if both mu_flag and sigma_flag fire
- `direction` (from μ channel, taken from N=1 as primary)

- [ ] **Step 1: Write the failing test**

Create `tests/test_boostlss_xs_meta_labeler.py`:
```python
"""Tests for MetaLabeler."""
from __future__ import annotations

import numpy as np
import pytest


def _make_synthetic_flags(n: int = 400, n_horizons: int = 5) -> dict:
    rng = np.random.default_rng(7)
    train_n = n // 2
    flags_by_horizon: dict[int, dict[str, np.ndarray]] = {}
    y_by_horizon: dict[int, np.ndarray] = {}

    for h in range(1, n_horizons + 1):
        mu = np.concatenate([np.full(train_n, np.nan), rng.normal(0, 1.5, n - train_n)])
        sigma = np.concatenate([np.full(train_n, np.nan), rng.uniform(0.5, 2.0, n - train_n)])
        nu = np.concatenate([np.full(train_n, np.nan), rng.uniform(2, 15, n - train_n)])
        direction = np.concatenate([np.full(train_n, np.nan), np.sign(mu[train_n:])])
        flags_by_horizon[h] = {
            "mu_flag": np.concatenate([np.full(train_n, np.nan),
                                       (np.abs(mu[train_n:]) > 1.5).astype(float)]),
            "mu_mag": np.abs(mu),
            "sigma_flag": np.concatenate([np.full(train_n, np.nan),
                                          (sigma[train_n:] < 1.0).astype(float)]),
            "sigma_mag": sigma,
            "nu_flag": np.concatenate([np.full(train_n, np.nan),
                                       (nu[train_n:] < 5).astype(float)]),
            "nu_mag": nu,
            "direction": direction,
        }
        y_by_horizon[h] = rng.normal(0, 2, n)

    symbols = ["EURUSD"] * (n // 2) + ["GBPUSD"] * (n // 2)
    close_ts = np.arange(n, dtype="datetime64[s]")
    return {
        "flags_by_horizon": flags_by_horizon,
        "y_by_horizon": y_by_horizon,
        "direction": flags_by_horizon[1]["direction"],
        "symbols_arr": symbols,
        "close_ts_arr": close_ts,
    }


def test_meta_labeler_returns_probability_array():
    from scripts.boostlss_xs.meta_labeler import MetaLabeler

    data = _make_synthetic_flags()
    ml = MetaLabeler()
    probs = ml.fit_predict(**data)
    assert probs.shape == (400,)
    oos = probs[~np.isnan(probs)]
    assert (oos >= 0).all() and (oos <= 1).all()


def test_meta_labeler_nan_for_train_rows():
    from scripts.boostlss_xs.meta_labeler import MetaLabeler

    data = _make_synthetic_flags(n=400)
    ml = MetaLabeler()
    probs = ml.fit_predict(**data)
    # First half should be NaN (train rows)
    assert np.isnan(probs[:200]).all()


def test_label_construction_direction_aware():
    """Label is 1 only when return aligns with predicted direction."""
    from scripts.boostlss_xs.meta_labeler import _build_label

    direction = np.array([1.0, -1.0, 1.0, -1.0])
    y = np.array([2.0, -2.0, -2.0, 2.0])  # first two align, last two don't
    threshold = 1.0
    labels = _build_label(direction, y, threshold)
    np.testing.assert_array_equal(labels, [1, 1, 0, 0])
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/test_boostlss_xs_meta_labeler.py -v
```
Expected: `ImportError`

- [ ] **Step 3: Implement meta_labeler.py**

Create `scripts/boostlss_xs/meta_labeler.py`:
```python
"""HistGBM meta-labeler on OOS BoostLSS flags across all horizons."""
from __future__ import annotations

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier

_HORIZONS = list(range(1, 6))  # N = 1, 2, 3, 4, 5
_META_THRESHOLD = 0.55
_N_FOLDS = 5


def _build_label(direction: np.ndarray, y: np.ndarray, threshold: float) -> np.ndarray:
    """Binary label: 1 if y * direction > threshold, else 0."""
    return ((y * direction) > threshold).astype(float)


def _build_meta_features(
    flags_by_horizon: dict[int, dict[str, np.ndarray]],
    direction: np.ndarray,
) -> np.ndarray:
    """Stack flag outputs across horizons into meta-feature matrix.

    Returns array of shape (N, 30+) — 6 channels × 5 horizons + interaction features.
    """
    cols: list[np.ndarray] = []
    mu_flags: list[np.ndarray] = []

    for h in _HORIZONS:
        f = flags_by_horizon[h]
        cols.extend([
            f["mu_flag"], f["mu_mag"],
            f["sigma_flag"], f["sigma_mag"],
            f["nu_flag"], f["nu_mag"],
        ])
        mu_flags.append(f["mu_flag"])

    # Horizon agreement: how many horizons fired mu_flag
    mu_stack = np.column_stack(mu_flags)
    horizon_agreement = np.nansum(mu_stack, axis=1).astype(float)
    cols.append(horizon_agreement)

    # mu+sigma co-fire at horizon 1
    h1 = flags_by_horizon[1]
    mu_sigma_agree = np.where(
        np.isnan(h1["mu_flag"]) | np.isnan(h1["sigma_flag"]),
        np.nan,
        (h1["mu_flag"] * h1["sigma_flag"]),
    )
    cols.append(mu_sigma_agree)

    # Direction from primary horizon (N=1)
    cols.append(direction)

    return np.column_stack(cols)


def _fold_boundaries(close_ts: np.ndarray, n_folds: int) -> list[tuple[int, int, int]]:
    n = len(close_ts)
    block = n // (n_folds + 1)
    return [
        (block * (k + 1), block * (k + 1), min(block * (k + 2), n))
        for k in range(n_folds)
    ]


class MetaLabeler:
    """HistGBM meta-labeler trained on OOS BoostLSS flags.

    WFO is aligned to the same fold boundaries as the BoostLSS model.
    Training data for fold k contains only OOS predictions from folds 1..k-1.
    """

    def __init__(self, threshold: float = _META_THRESHOLD) -> None:
        self.threshold = threshold

    def fit_predict(
        self,
        flags_by_horizon: dict[int, dict[str, np.ndarray]],
        y_by_horizon: dict[int, np.ndarray],
        direction: np.ndarray,
        symbols_arr: list[str],
        close_ts_arr: np.ndarray,
    ) -> np.ndarray:
        """Fit meta-labeler, return P(profitable) for OOS rows.

        Returns array of length N; NaN for train rows.
        """
        n = len(direction)
        meta_X = _build_meta_features(flags_by_horizon, direction)

        # Build label using horizon N=1 as primary, per-symbol median threshold
        y1 = y_by_horizon[1]
        symbols = np.array(symbols_arr)

        probs = np.full(n, np.nan)
        folds = _fold_boundaries(close_ts_arr, _N_FOLDS)

        for fold_idx, (train_end, test_start, test_end) in enumerate(folds):
            if fold_idx == 0:
                # No OOS predictions available yet to train meta-labeler on
                continue

            # Build labels for training rows (only OOS rows from previous folds)
            # First fold's test rows are the earliest OOS predictions available
            first_oos_start = folds[0][1]
            train_meta_end = train_end

            X_meta_train = meta_X[first_oos_start:train_meta_end]
            y1_train = y1[first_oos_start:train_meta_end]
            dir_train = direction[first_oos_start:train_meta_end]
            sym_train = symbols[first_oos_start:train_meta_end]

            # Per-symbol median |return| threshold, computed on train window
            thresholds: dict[str, float] = {}
            for sym in np.unique(sym_train):
                mask = sym_train == sym
                y_sym = y1_train[mask]
                valid = y_sym[~np.isnan(y_sym)]
                thresholds[sym] = float(np.median(np.abs(valid))) if len(valid) > 0 else 0.0

            # Build per-row thresholds
            row_thresh = np.array([
                thresholds.get(s, 0.0) for s in sym_train
            ])
            labels = _build_label(dir_train, y1_train, row_thresh)

            # Drop rows where either X or label has NaN
            valid_mask = ~(
                np.isnan(X_meta_train).any(axis=1)
                | np.isnan(dir_train)
                | np.isnan(y1_train)
            )
            if valid_mask.sum() < 20:
                continue

            clf = HistGradientBoostingClassifier(max_iter=100, learning_rate=0.05,
                                                 max_depth=3, random_state=42)
            clf.fit(X_meta_train[valid_mask], labels[valid_mask])

            X_test = meta_X[test_start:test_end]
            valid_test = ~np.isnan(X_test).any(axis=1)
            if valid_test.sum() == 0:
                continue

            test_probs = np.full(test_end - test_start, np.nan)
            test_probs[valid_test] = clf.predict_proba(X_test[valid_test])[:, 1]
            probs[test_start:test_end] = test_probs

        return probs
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_boostlss_xs_meta_labeler.py -v
```
Expected: all 3 tests PASS.

- [ ] **Step 5: Quality check + commit**

```bash
make quality
git add scripts/boostlss_xs/meta_labeler.py tests/test_boostlss_xs_meta_labeler.py
git commit -m "feat(boostlss_xs): HistGBM meta-labeler on OOS distributional flags"
```

---

## Task 7: End-to-End Pipeline + Trade Log

**Files:**
- Create: `scripts/boostlss_xs/run.py`

**Interfaces:**
- Produces: `run_pipeline(data_dir, output_dir, families, horizons, meta_threshold)`
  - Writes per-family CSV trade logs: `{output_dir}/trade_log_{family}.csv`
  - Writes comparison summary: `{output_dir}/family_comparison.csv`
  - Trade log columns: `symbol, close_ts, horizon, direction, meta_prob, gross_return, mu_flag, sigma_flag, nu_flag, mu_mag, sigma_mag, nu_mag`

- [ ] **Step 1: Implement run.py**

Create `scripts/boostlss_xs/run.py`:
```python
"""End-to-end BoostLSS XS anomaly detection pipeline.

Usage:
    uv run python scripts/boostlss_xs/run.py \
        --data-dir /path/to/tick_bars \
        --output-dir /tmp/boostlss_xs_out \
        [--families StudentTLSS GEVLSS] \
        [--horizons 1 2 3 4 5] \
        [--meta-threshold 0.55]
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.boostlss_xs.features import build_features, within_symbol_features, xs_features
from scripts.boostlss_xs.flagging import flag_channels
from scripts.boostlss_xs.meta_labeler import MetaLabeler
from scripts.boostlss_xs.model import BoostLssWFO
from scripts.boostlss_xs.universe import load_universe


def _build_horizon_target(y_raw: np.ndarray, horizon: int) -> np.ndarray:
    """Gross return over next N=horizon bars (forward sum of log_ret_bps)."""
    out = np.full(len(y_raw), np.nan)
    for i in range(len(y_raw) - horizon):
        window = y_raw[i + 1: i + 1 + horizon]
        if not np.isnan(window).any():
            out[i] = float(np.sum(window))
    return out


def run_pipeline(
    data_dir: str,
    output_dir: str,
    families: list[str] | None = None,
    horizons: list[int] | None = None,
    meta_threshold: float = 0.55,
) -> None:
    families = families or ["StudentTLSS", "GEVLSS"]
    horizons = horizons or [1, 2, 3, 4, 5]
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    print("Loading universe...")
    uni = load_universe(data_dir)
    print(f"  {len(uni)} symbols loaded")

    print("Computing within-symbol features...")
    uni = {sym: within_symbol_features(df, sym) for sym, df in uni.items()}

    print("Computing cross-sectional features...")
    uni = xs_features(uni)

    print("Building stacked feature matrix...")
    X, close_ts_arr, feature_names, symbols_arr = build_features(uni)
    print(f"  Feature matrix: {X.shape}")

    # Build horizon targets from vol_std returns (stacked same way as X)
    print("Building horizon targets...")
    # We need the stacked vol_std column aligned with X rows
    y_vol_std_parts = []
    for sym in sorted(uni.keys()):
        df = uni[sym]
        from scripts.boostlss_xs.features import ALL_FEATURES
        mat = df.select(ALL_FEATURES).to_numpy()
        valid = ~np.any(np.isnan(mat), axis=1)
        y_vol_std_parts.append(df["vol_std"].to_numpy()[valid])
    y_raw_stacked = np.concatenate(y_vol_std_parts)

    y_by_horizon = {h: _build_horizon_target(y_raw_stacked, h) for h in horizons}

    comparison_rows = []

    for family in families:
        print(f"\n=== Family: {family} ===")
        all_flags: dict[int, dict[str, np.ndarray]] = {}

        for horizon in horizons:
            print(f"  Horizon N={horizon}...")
            y = y_by_horizon[horizon]
            wfo = BoostLssWFO(family=family)
            preds = wfo.fit_predict(X, y, close_ts_arr)
            flags = flag_channels(preds, y, family)
            all_flags[horizon] = flags

        print("  Running meta-labeler...")
        ml = MetaLabeler(threshold=meta_threshold)
        direction = all_flags[1]["direction"]
        meta_probs = ml.fit_predict(
            flags_by_horizon=all_flags,
            y_by_horizon=y_by_horizon,
            direction=direction,
            symbols_arr=list(symbols_arr),
            close_ts_arr=close_ts_arr,
        )

        # Build trade log: one row per (bar, horizon) where meta_prob > threshold
        print("  Building trade log...")
        rows = []
        for i in range(len(X)):
            if np.isnan(meta_probs[i]) or meta_probs[i] < meta_threshold:
                continue
            for h in horizons:
                f = all_flags[h]
                if np.isnan(f["mu_flag"][i]):
                    continue
                rows.append({
                    "symbol": symbols_arr[i],
                    "close_ts": close_ts_arr[i],
                    "horizon": h,
                    "direction": float(direction[i]),
                    "meta_prob": float(meta_probs[i]),
                    "gross_return": float(y_by_horizon[h][i])
                    if not np.isnan(y_by_horizon[h][i]) else np.nan,
                    "mu_flag": float(f["mu_flag"][i]),
                    "sigma_flag": float(f["sigma_flag"][i]),
                    "nu_flag": float(f["nu_flag"][i]),
                    "mu_mag": float(f["mu_mag"][i]),
                    "sigma_mag": float(f["sigma_mag"][i]),
                    "nu_mag": float(f["nu_mag"][i]),
                })

        trade_log = pd.DataFrame(rows)
        out_path = os.path.join(output_dir, f"trade_log_{family}.csv")
        trade_log.to_csv(out_path, index=False)
        print(f"  Trade log: {len(trade_log)} rows → {out_path}")

        # Per-channel PnL attribution
        if len(trade_log) > 0:
            signed_ret = trade_log["gross_return"] * trade_log["direction"]
            mean_ret = float(signed_ret.mean())
            pos_months = float((signed_ret > 0).mean())
            comparison_rows.append({
                "family": family,
                "n_trades": len(trade_log),
                "mean_net_ret_bps": mean_ret,
                "pos_frac": pos_months,
                "mu_flag_rate": float(trade_log["mu_flag"].mean()),
                "sigma_flag_rate": float(trade_log["sigma_flag"].mean()),
                "nu_flag_rate": float(trade_log["nu_flag"].mean()),
            })

    # Comparison summary
    if comparison_rows:
        comp = pd.DataFrame(comparison_rows)
        comp_path = os.path.join(output_dir, "family_comparison.csv")
        comp.to_csv(comp_path, index=False)
        print(f"\nComparison summary → {comp_path}")
        print(comp.to_string(index=False))


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--data-dir", default="/Users/danielfisher/repositories/behemoth/data/tick_bars")
    p.add_argument("--output-dir", default="/tmp/boostlss_xs_out")
    p.add_argument("--families", nargs="+", default=["StudentTLSS", "GEVLSS"])
    p.add_argument("--horizons", nargs="+", type=int, default=[1, 2, 3, 4, 5])
    p.add_argument("--meta-threshold", type=float, default=0.55)
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    run_pipeline(
        data_dir=args.data_dir,
        output_dir=args.output_dir,
        families=args.families,
        horizons=args.horizons,
        meta_threshold=args.meta_threshold,
    )
```

- [ ] **Step 2: Smoke test with single family + reduced horizon**

```bash
uv run python scripts/boostlss_xs/run.py \
    --families StudentTLSS \
    --horizons 1 \
    --output-dir /tmp/boostlss_xs_out
```
Expected: prints progress, writes `trade_log_StudentTLSS.csv`. Runtime ~5-20min depending on universe size and mstop.

- [ ] **Step 3: Run full pipeline (both families, all horizons)**

```bash
uv run python scripts/boostlss_xs/run.py \
    --families StudentTLSS GEVLSS \
    --horizons 1 2 3 4 5 \
    --output-dir /tmp/boostlss_xs_out
```
Expected: writes 2 trade logs + `family_comparison.csv`.

- [ ] **Step 4: Quality check + commit**

```bash
make quality
git add scripts/boostlss_xs/run.py
git commit -m "feat(boostlss_xs): end-to-end pipeline with trade log and family comparison"
```

---

## Self-Review

**Spec coverage check:**

| Spec Section | Task |
|---|---|
| 21-pair 1000-tick universe | Task 1 (universe.py) |
| Within-symbol features (rolling, robust, time) | Task 2 |
| XS features (backward as-of, robust stats) | Task 3 |
| JSU → StudentTLSS + GEVLSS families | Tasks 4-5 |
| PyTreeLearner for all parameters | Task 4 |
| 5-fold causal WFO | Task 4 |
| Hyperparams fixed on fold 1 | Task 4 (fixed globally, tunable) |
| 4-channel flagging (μ/σ/ν) | Task 5 |
| N=1..5 multi-horizon targets | Tasks 4, 7 |
| Meta-labeler on OOS-only predictions | Task 6 |
| Per-symbol label threshold | Task 6 |
| Horizon-agreement features | Task 6 |
| Trade log with per-channel attribution | Task 7 |
| Both families compared | Task 7 |

**No placeholders found.**

**Type consistency confirmed:** `BoostLssWFO.fit_predict()` returns `dict[str, np.ndarray]`; `flag_channels()` consumes same type; `MetaLabeler.fit_predict()` consumes `flags_by_horizon: dict[int, dict[str, np.ndarray]]` — all consistent across tasks.

**One performance note:** `_rolling_mad()`, `_rolling_quantile_rank()`, `_rolling_excess_kurtosis()` and the XS peer-loop in `xs_features()` are O(N×W) Python loops. For 21 pairs × 15k-20k tick bars each, expect feature build time of 10-30 minutes. This is acceptable for exploration; vectorisation is a natural follow-on optimisation once the pipeline is validated.
