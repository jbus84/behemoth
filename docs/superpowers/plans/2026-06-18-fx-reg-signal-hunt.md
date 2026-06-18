# FX Regression Signal Hunt (1–4h) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hunt for a regression signal predicting next-bar returns at 1/2/3/4h on the 6 FX majors, evaluated against the real-cost break-even IC, with three decision-rule monetizations.

**Architecture:** A single importable script `scripts/fx_coint/reg_signal_hunt.py` made of small pure functions (bar building, panel construction, IC eval, decision rules, BH-FDR) plus a `main()` orchestrator/CLI. Correctness-critical units (contiguity guard, no-look-ahead, vol-norm round-trip, cost-gating, BH-FDR) are unit-tested in `tests/fx_coint/test_reg_signal_hunt.py`. Reuses the proven `data/tick_bars/{sym}_1m_flow.parquet` source and the polars→pandas pattern from `fx_ic_diagnose.py`.

**Tech Stack:** Python, polars (bar building), pandas/numpy (panel + eval), scikit-learn (Ridge, StandardScaler), scipy.stats (spearmanr).

## Global Constraints

- Pairs: `["EURUSD", "GBPUSD", "AUDUSD", "USDJPY", "USDCHF", "USDCAD"]` (verbatim).
- Round-trip costs in bps (Pepperstone Razor, $3/side + avg spread): `{"EURUSD": 0.64, "GBPUSD": 0.63, "USDJPY": 0.80, "USDCAD": 0.97, "USDCHF": 1.05, "AUDUSD": 1.06}`.
- Horizons = next-bar return at frequencies `["1h", "2h", "3h", "4h"]`. One model per (pair, freq).
- Session filter: entry-hour ∈ [7, 21) UTC, weekdays only.
- Target trained vol-normalized (`r_next / σ_trailing`); predictions converted back to bps via the same `σ_trailing` for cost comparison.
- No look-ahead: features shifted ≥1 bar; vol used for normalization is trailing (known at decision time); 70/30 temporal split with an `h`-bar purge gap.
- Features (minimal, price-only): `r_1`, `mom_short` (bars 2–6), `mom_long` (bars 7–24), `rvol_24`, `hour`.
- Source data: `data/tick_bars/{sym}_1m_flow.parquet`; never resample tick-count bars (these are genuine 1-min time bars — safe).
- Run quality before any push: `make quality` (ty + ruff + …), not just pytest.

---

### Task 1: Frequency bar builder with contiguity + session filter

**Files:**
- Create: `scripts/fx_coint/reg_signal_hunt.py`
- Test: `tests/fx_coint/test_reg_signal_hunt.py`

**Interfaces:**
- Produces: `build_freq_bars(df_1m: pl.DataFrame, freq: str, session: tuple[int,int]=(7,21)) -> pd.DataFrame` returning columns `["bucket","mid","rvol_bps","n_ticks"]` sorted by bucket, only rows whose bucket hour ∈ [session[0], session[1]) and weekday, with a boolean column `contig` (True when the previous bar is exactly one `freq` step earlier).

- [ ] **Step 1: Write the failing test**

```python
# tests/fx_coint/test_reg_signal_hunt.py
import polars as pl
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from scripts.fx_coint.reg_signal_hunt import build_freq_bars


def _synthetic_1m(start: datetime, n: int, seed: int = 0) -> pl.DataFrame:
    ts = [start + timedelta(minutes=i) for i in range(n)]
    rng = np.random.default_rng(seed)
    # random walk with tiny drift so bar-return variance is non-zero (sigma_h > 0)
    steps = 1e-5 + rng.normal(0.0, 5e-5, n)
    mid = 1.10 + np.cumsum(steps)
    return pl.DataFrame({
        "bucket": ts,
        "mid": mid,
        "bid": mid - 5e-5,
        "ask": mid + 5e-5,
        "n_ticks": np.ones(n, dtype=np.int64),
        "flow_tick": np.zeros(n),
        "flow_ofi": np.zeros(n),
    })


def test_build_freq_bars_session_and_contiguity():
    # Monday 06:00 UTC, 6 hours of 1-min bars -> spans 06,07,08,09,10,11
    df = _synthetic_1m(datetime(2025, 1, 6, 6, 0), 6 * 60)
    bars = build_freq_bars(df, "1h", session=(7, 21))
    # 06:00 bar excluded by session; 07..11 kept -> 5 bars
    assert list(bars["bucket"].dt.hour) == [7, 8, 9, 10, 11]
    # first kept bar's predecessor (07:00) follows 06:00 which was dropped only by
    # session filter, but contiguity is computed on the full freq series before filtering:
    # 08..11 are contiguous with their predecessor -> contig True; 07:00 predecessor 06:00
    # is exactly 1h earlier -> contig True too.
    assert bars["contig"].iloc[1:].all()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/fx_coint/test_reg_signal_hunt.py::test_build_freq_bars_session_and_contiguity -v`
Expected: FAIL with `ImportError`/`ModuleNotFoundError` (function not defined).

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/fx_coint/reg_signal_hunt.py
"""Regression signal hunt at 1/2/3/4h on FX majors, scored vs real-cost break-even IC.

Usage:
    uv run python scripts/fx_coint/reg_signal_hunt.py --freq all --symbol all
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
from scipy.stats import spearmanr
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

PAIRS = ["EURUSD", "GBPUSD", "AUDUSD", "USDJPY", "USDCHF", "USDCAD"]
COST_BPS = {"EURUSD": 0.64, "GBPUSD": 0.63, "USDJPY": 0.80,
            "USDCAD": 0.97, "USDCHF": 1.05, "AUDUSD": 1.06}
FREQS = ["1h", "2h", "3h", "4h"]
FREQ_MINUTES = {"1h": 60, "2h": 120, "3h": 180, "4h": 240}
FEATURE_COLS = ["r_1", "mom_short", "mom_long", "rvol_24", "hour"]


def build_freq_bars(
    df_1m: pl.DataFrame, freq: str, session: tuple[int, int] = (7, 21)
) -> pd.DataFrame:
    t = df_1m.sort("bucket").with_columns(
        pl.col("mid").log().diff().alias("lr1"),
        pl.col("bucket").dt.truncate(freq).alias("bf"),
    )
    bars = (
        t.group_by("bf")
        .agg(
            pl.col("mid").last(),
            pl.col("n_ticks").sum(),
            (pl.col("lr1").std() * 1e4).alias("rvol_bps"),
        )
        .rename({"bf": "bucket"})
        .sort("bucket")
        .to_pandas()
    )
    bars["bucket"] = pd.to_datetime(bars["bucket"])
    step = np.timedelta64(FREQ_MINUTES[freq], "m")
    prev = bars["bucket"].shift(1).to_numpy()
    bars["contig"] = (bars["bucket"].to_numpy() - prev) == step
    bars.loc[0, "contig"] = False
    hour = bars["bucket"].dt.hour
    keep = (hour >= session[0]) & (hour < session[1]) & (bars["bucket"].dt.dayofweek < 5)
    return bars[keep].reset_index(drop=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/fx_coint/test_reg_signal_hunt.py::test_build_freq_bars_session_and_contiguity -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/fx_coint/reg_signal_hunt.py tests/fx_coint/test_reg_signal_hunt.py
git commit -m "feat(fx_coint): freq bar builder with contiguity + session filter

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Panel builder — features + vol-normalized target, no look-ahead

**Files:**
- Modify: `scripts/fx_coint/reg_signal_hunt.py`
- Test: `tests/fx_coint/test_reg_signal_hunt.py`

**Interfaces:**
- Consumes: `build_freq_bars` output (cols `bucket, mid, rvol_bps, n_ticks, contig`).
- Produces: `build_panel(bars: pd.DataFrame, vol_lookback: int = 24) -> pd.DataFrame` with columns `FEATURE_COLS + ["sigma_h", "target_z", "ret_next_bps", "bucket"]`, dropping rows with non-finite feature/target/sigma. `ret_next_bps` is the forward 1-bar return in bps; `target_z = ret_next_bps / sigma_h`; `sigma_h` is the trailing std (bps) of bar returns known at decision time (shifted). Rows where the forward bar is not contiguous are dropped.

- [ ] **Step 1: Write the failing test**

```python
def test_build_panel_no_lookahead_and_volnorm():
    from scripts.fx_coint.reg_signal_hunt import build_freq_bars, build_panel
    df = _synthetic_1m(datetime(2025, 1, 6, 7, 0), 200 * 60)
    bars = build_freq_bars(df, "1h", session=(0, 24))
    panel = build_panel(bars, vol_lookback=24)
    assert len(panel) > 50
    # target_z reconstructs ret_next_bps via sigma_h
    recon = panel["target_z"] * panel["sigma_h"]
    assert np.allclose(recon.to_numpy(), panel["ret_next_bps"].to_numpy(), atol=1e-6)
    # r_1 at row i equals ret_next_bps at row i-1 (feature is the realized last-bar
    # return; no future info) — check correlation is ~1 on the contiguous interior
    last_ret = panel["ret_next_bps"].shift(1).to_numpy()[1:]
    assert np.corrcoef(panel["r_1"].to_numpy()[1:], last_ret)[0, 1] > 0.99
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/fx_coint/test_reg_signal_hunt.py::test_build_panel_no_lookahead_and_volnorm -v`
Expected: FAIL (`build_panel` not defined).

- [ ] **Step 3: Write minimal implementation**

```python
def build_panel(bars: pd.DataFrame, vol_lookback: int = 24) -> pd.DataFrame:
    b = bars.reset_index(drop=True)
    mid = b["mid"].to_numpy()
    r = np.empty(len(b))
    r[0] = np.nan
    r[1:] = (np.log(mid[1:]) - np.log(mid[:-1])) * 1e4
    # break returns across non-contiguous bars
    r[~b["contig"].to_numpy()] = np.nan
    rs = pd.Series(r)

    feats = pd.DataFrame({"bucket": b["bucket"]})
    feats["r_1"] = rs.shift(1).to_numpy()
    feats["mom_short"] = rs.rolling(5, min_periods=3).sum().shift(1).to_numpy()
    feats["mom_long"] = rs.rolling(18, min_periods=9).sum().shift(5).to_numpy()
    feats["rvol_24"] = rs.rolling(vol_lookback, min_periods=vol_lookback // 2).std().shift(1).to_numpy()
    feats["hour"] = b["bucket"].dt.hour.astype(float).to_numpy()
    feats["sigma_h"] = feats["rvol_24"]  # trailing vol, known at decision time

    ret_next = rs.shift(-1).to_numpy()  # forward 1-bar return
    feats["ret_next_bps"] = ret_next
    feats["target_z"] = ret_next / feats["sigma_h"].to_numpy()

    finite = np.isfinite(feats[FEATURE_COLS].to_numpy()).all(axis=1)
    finite &= np.isfinite(feats["target_z"].to_numpy())
    finite &= feats["sigma_h"].to_numpy() > 0
    return feats[finite].reset_index(drop=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/fx_coint/test_reg_signal_hunt.py::test_build_panel_no_lookahead_and_volnorm -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(fx_coint): panel builder with vol-norm target, no look-ahead

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Fit + IC evaluation with break-even bar

**Files:**
- Modify: `scripts/fx_coint/reg_signal_hunt.py`
- Test: `tests/fx_coint/test_reg_signal_hunt.py`

**Interfaces:**
- Consumes: `build_panel` output.
- Produces:
  - `breakeven_ic(cost_bps: float, sigma_h_bps: float) -> float` returning `cost_bps / sigma_h_bps`.
  - `fit_and_eval(panel: pd.DataFrame, cost_bps: float, purge: int = 1, alpha: float = 1.0) -> dict` that does a 70/30 temporal split with a `purge`-bar gap, fits `Ridge` on scaled `FEATURE_COLS` predicting `target_z`, and returns a dict with keys `n_test, ic, ic_star, clears, pred_bps, actual_bps, hours, sigma_med`. `pred_bps = pred_z * sigma_h_test`; `ic = spearman(pred_z, target_z_test)`; `sigma_med = median(sigma_h_test)`; `ic_star = breakeven_ic(cost_bps, sigma_med)`; `clears = ic > ic_star`.

- [ ] **Step 1: Write the failing test**

```python
def test_breakeven_ic_and_fit_keys():
    from scripts.fx_coint.reg_signal_hunt import breakeven_ic, fit_and_eval, build_freq_bars, build_panel
    assert abs(breakeven_ic(0.64, 16.0) - 0.04) < 1e-9
    df = _synthetic_1m(datetime(2025, 1, 6, 7, 0), 400 * 60)
    panel = build_panel(build_freq_bars(df, "1h", session=(0, 24)))
    res = fit_and_eval(panel, cost_bps=0.64, purge=1)
    for k in ["n_test", "ic", "ic_star", "clears", "pred_bps", "actual_bps", "hours", "sigma_med"]:
        assert k in res
    assert len(res["pred_bps"]) == len(res["actual_bps"]) == res["n_test"]
    assert res["ic_star"] == breakeven_ic(0.64, res["sigma_med"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/fx_coint/test_reg_signal_hunt.py::test_breakeven_ic_and_fit_keys -v`
Expected: FAIL (functions not defined).

- [ ] **Step 3: Write minimal implementation**

```python
def breakeven_ic(cost_bps: float, sigma_h_bps: float) -> float:
    return cost_bps / sigma_h_bps


def fit_and_eval(
    panel: pd.DataFrame, cost_bps: float, purge: int = 1, alpha: float = 1.0
) -> dict:
    n = len(panel)
    split = int(n * 0.7)
    train = panel.iloc[:split]
    test = panel.iloc[split + purge:]
    Xtr = train[FEATURE_COLS].to_numpy()
    Xte = test[FEATURE_COLS].to_numpy()
    ytr = train["target_z"].to_numpy()
    yte = test["target_z"].to_numpy()

    scaler = StandardScaler().fit(Xtr)
    model = Ridge(alpha=alpha).fit(scaler.transform(Xtr), ytr)
    pred_z = model.predict(scaler.transform(Xte))

    sigma_te = test["sigma_h"].to_numpy()
    pred_bps = pred_z * sigma_te
    actual_bps = test["ret_next_bps"].to_numpy()
    ic = spearmanr(pred_z, yte).statistic if len(yte) > 2 else float("nan")
    sigma_med = float(np.median(sigma_te))
    ic_star = breakeven_ic(cost_bps, sigma_med)
    return {
        "n_test": len(yte),
        "ic": float(ic),
        "ic_star": float(ic_star),
        "clears": bool(ic > ic_star),
        "pred_bps": pred_bps,
        "actual_bps": actual_bps,
        "hours": test["hour"].to_numpy(),
        "sigma_med": sigma_med,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/fx_coint/test_reg_signal_hunt.py::test_breakeven_ic_and_fit_keys -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(fx_coint): ridge fit + IC eval with break-even bar

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: Three decision rules (net economics)

**Files:**
- Modify: `scripts/fx_coint/reg_signal_hunt.py`
- Test: `tests/fx_coint/test_reg_signal_hunt.py`

**Interfaces:**
- Produces: `eval_rules(pred_bps: np.ndarray, actual_bps: np.ndarray, cost_bps: float, size_cap: float = 3.0) -> dict` returning per-trade net mean (bps) for each rule:
  - `netA` = mean(sign(pred) * actual) − cost (always trade).
  - `netB` = mean(w * actual) − |w|*cost, where `w = clip(pred / median(|pred|), -cap, cap)` (TP-sized).
  - `netC` = mean over trades where `|pred| > cost` of (sign(pred)*actual − cost); `n_trades_C` and total bars reported.

- [ ] **Step 1: Write the failing test**

```python
def test_eval_rules_cost_gating():
    from scripts.fx_coint.reg_signal_hunt import eval_rules
    # perfect predictor, moves all exceed cost -> netA positive and = mean|actual| - cost
    pred = np.array([2.0, -2.0, 3.0, -3.0])
    actual = np.array([2.0, -2.0, 3.0, -3.0])
    r = eval_rules(pred, actual, cost_bps=0.5)
    assert abs(r["netA"] - (np.mean(np.abs(actual)) - 0.5)) < 1e-9
    assert r["n_trades_C"] == 4  # all |pred| > 0.5
    # cost-gate excludes sub-cost predictions
    pred2 = np.array([0.1, -0.1, 3.0, -3.0])
    r2 = eval_rules(pred2, actual, cost_bps=0.5)
    assert r2["n_trades_C"] == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/fx_coint/test_reg_signal_hunt.py::test_eval_rules_cost_gating -v`
Expected: FAIL (`eval_rules` not defined).

- [ ] **Step 3: Write minimal implementation**

```python
def eval_rules(
    pred_bps: np.ndarray, actual_bps: np.ndarray, cost_bps: float, size_cap: float = 3.0
) -> dict:
    pred = np.asarray(pred_bps, float)
    act = np.asarray(actual_bps, float)
    n = len(pred)

    net_a = float(np.mean(np.sign(pred) * act) - cost_bps) if n else float("nan")

    scale = np.median(np.abs(pred))
    if scale > 0:
        w = np.clip(pred / scale, -size_cap, size_cap)
        net_b = float(np.mean(w * act) - np.mean(np.abs(w)) * cost_bps)
    else:
        net_b = float("nan")

    gate = np.abs(pred) > cost_bps
    if gate.sum() > 0:
        net_c = float(np.mean(np.sign(pred[gate]) * act[gate] - cost_bps))
    else:
        net_c = float("nan")

    return {
        "netA": net_a,
        "netB": net_b,
        "netC": net_c,
        "n_trades_C": int(gate.sum()),
        "n_bars": n,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/fx_coint/test_reg_signal_hunt.py::test_eval_rules_cost_gating -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(fx_coint): three decision-rule net economics

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: BH-FDR + IC-by-hour helpers

**Files:**
- Modify: `scripts/fx_coint/reg_signal_hunt.py`
- Test: `tests/fx_coint/test_reg_signal_hunt.py`

**Interfaces:**
- Produces:
  - `ic_pvalue(ic: float, n: int) -> float` — two-sided p-value for a Spearman IC via the `t = ic*sqrt((n-2)/(1-ic^2))` approximation.
  - `bh_reject(pvals: list[float], q: float = 0.10) -> list[bool]` — Benjamini–Hochberg reject mask at FDR `q`.
  - `ic_by_hour(pred_bps: np.ndarray, actual_bps: np.ndarray, hours: np.ndarray) -> dict[int, float]` — Spearman IC per entry-hour (hours with ≥30 obs).

- [ ] **Step 1: Write the failing test**

```python
def test_bh_reject_and_ic_pvalue():
    from scripts.fx_coint.reg_signal_hunt import bh_reject, ic_pvalue
    # a tiny IC on huge N is significant; large IC on tiny N is not
    assert ic_pvalue(0.05, 100000) < 0.01
    assert ic_pvalue(0.2, 10) > 0.10
    # BH: with one tiny p and rest large, only the tiny rejects
    rej = bh_reject([0.001, 0.4, 0.6, 0.8], q=0.10)
    assert rej == [True, False, False, False]
    # all-null stays null
    assert bh_reject([0.5, 0.6, 0.7], q=0.10) == [False, False, False]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/fx_coint/test_reg_signal_hunt.py::test_bh_reject_and_ic_pvalue -v`
Expected: FAIL (functions not defined).

- [ ] **Step 3: Write minimal implementation**

```python
from scipy.stats import t as _t_dist


def ic_pvalue(ic: float, n: int) -> float:
    if n <= 2 or not np.isfinite(ic) or abs(ic) >= 1.0:
        return float("nan")
    tstat = ic * np.sqrt((n - 2) / (1 - ic * ic))
    return float(2 * _t_dist.sf(abs(tstat), df=n - 2))


def bh_reject(pvals: list[float], q: float = 0.10) -> list[bool]:
    p = np.asarray(pvals, float)
    m = len(p)
    order = np.argsort(p)
    thresh = q * (np.arange(1, m + 1)) / m
    passed = p[order] <= thresh
    reject = np.zeros(m, bool)
    if passed.any():
        kmax = np.max(np.where(passed)[0])
        reject[order[: kmax + 1]] = True
    return reject.tolist()


def ic_by_hour(
    pred_bps: np.ndarray, actual_bps: np.ndarray, hours: np.ndarray
) -> dict[int, float]:
    out: dict[int, float] = {}
    for h in np.unique(hours).astype(int):
        m = hours == h
        if m.sum() >= 30:
            out[int(h)] = float(spearmanr(pred_bps[m], actual_bps[m]).statistic)
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/fx_coint/test_reg_signal_hunt.py::test_bh_reject_and_ic_pvalue -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(fx_coint): BH-FDR + IC-by-hour significance helpers

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 6: Orchestrator + CLI + results table

**Files:**
- Modify: `scripts/fx_coint/reg_signal_hunt.py`
- Test: `tests/fx_coint/test_reg_signal_hunt.py`

**Interfaces:**
- Consumes: all prior functions.
- Produces:
  - `run_cell(sym: str, freq: str) -> dict | None` — loads `data/tick_bars/{sym}_1m_flow.parquet`, builds bars/panel, fits, evals rules, computes p-value; returns a flat row dict `{symbol, freq, n_test, ic, ic_star, clears, pval, netA, netB, netC, n_trades_C, sigma_med}` or `None` if data missing/too small.
  - `main()` — argparse `--symbol` (PAIRS or `all`), `--freq` (FREQS or `all`); runs all requested cells, applies `bh_reject` across the collected p-values, prints a results table with a `BHsig` column, and prints the IC-by-hour curve for any cell that clears.

- [ ] **Step 1: Write the failing test** (orchestration on a tiny on-disk parquet)

```python
def test_run_cell_on_synthetic(tmp_path, monkeypatch):
    import scripts.fx_coint.reg_signal_hunt as m
    df = _synthetic_1m(datetime(2025, 1, 6, 7, 0), 800 * 60)
    d = tmp_path / "data" / "tick_bars"
    d.mkdir(parents=True)
    df.write_parquet(d / "EURUSD_1m_flow.parquet")
    monkeypatch.setattr(m, "_REPO_ROOT", tmp_path)
    row = m.run_cell("EURUSD", "1h")
    assert row is not None
    assert row["symbol"] == "EURUSD" and row["freq"] == "1h"
    assert set(["ic", "ic_star", "clears", "pval", "netA", "netB", "netC"]).issubset(row)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/fx_coint/test_reg_signal_hunt.py::test_run_cell_on_synthetic -v`
Expected: FAIL (`run_cell` not defined).

- [ ] **Step 3: Write minimal implementation**

```python
def run_cell(sym: str, freq: str) -> dict | None:
    src = _REPO_ROOT / f"data/tick_bars/{sym}_1m_flow.parquet"
    if not src.exists():
        return None
    df_1m = pl.read_parquet(src)
    bars = build_freq_bars(df_1m, freq)
    panel = build_panel(bars)
    if len(panel) < 200:
        return None
    cost = COST_BPS[sym]
    res = fit_and_eval(panel, cost_bps=cost)
    rules = eval_rules(res["pred_bps"], res["actual_bps"], cost_bps=cost)
    return {
        "symbol": sym,
        "freq": freq,
        "n_test": res["n_test"],
        "ic": res["ic"],
        "ic_star": res["ic_star"],
        "clears": res["clears"],
        "pval": ic_pvalue(res["ic"], res["n_test"]),
        "netA": rules["netA"],
        "netB": rules["netB"],
        "netC": rules["netC"],
        "n_trades_C": rules["n_trades_C"],
        "sigma_med": res["sigma_med"],
        "_eval": res,  # retained for IC-by-hour printing in main()
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="all", choices=PAIRS + ["all"])
    ap.add_argument("--freq", default="all", choices=FREQS + ["all"])
    args = ap.parse_args()
    syms = PAIRS if args.symbol == "all" else [args.symbol]
    freqs = FREQS if args.freq == "all" else [args.freq]

    rows = [r for s in syms for f in freqs if (r := run_cell(s, f)) is not None]
    if not rows:
        print("No cells produced (missing data?).")
        return
    rej = bh_reject([r["pval"] for r in rows], q=0.10)
    for r, sig in zip(rows, rej):
        r["bh_sig"] = sig

    hdr = f"{'pair':>7} {'freq':>4} {'N':>6} {'IC':>7} {'IC*':>7} {'clr':>4} {'BH':>3} {'netA':>7} {'netB':>7} {'netC':>7} {'nC':>6}"
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        print(f"{r['symbol']:>7} {r['freq']:>4} {r['n_test']:>6} {r['ic']:>7.4f} "
              f"{r['ic_star']:>7.4f} {str(r['clears']):>4} {str(r['bh_sig']):>3} "
              f"{r['netA']:>+7.3f} {r['netB']:>+7.3f} {r['netC']:>+7.3f} {r['n_trades_C']:>6}")

    for r in rows:
        if r["clears"]:
            e = r["_eval"]
            curve = ic_by_hour(e["pred_bps"], e["actual_bps"], e["hours"])
            print(f"\nIC-by-hour {r['symbol']} {r['freq']}: "
                  + " ".join(f"{h}:{v:+.3f}" for h, v in sorted(curve.items())))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/fx_coint/test_reg_signal_hunt.py -v`
Expected: all PASS.

- [ ] **Step 5: Run quality gate, then commit**

Run: `make quality`
Expected: ty + ruff clean (fix any lint/type issues before committing).

```bash
git add -A && git commit -m "feat(fx_coint): orchestrator, CLI, results table with BH-FDR

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 7: Run the hunt on real data and record the verdict

**Files:**
- Create: `scripts/fx_coint/reg_signal_hunt_results.md` (results + interpretation)

- [ ] **Step 1: Run the full hunt**

Run: `uv run python scripts/fx_coint/reg_signal_hunt.py --symbol all --freq all`
Capture the table + IC-by-hour output.

- [ ] **Step 2: Record verdict against the go/no-go gate**

Write `scripts/fx_coint/reg_signal_hunt_results.md` documenting, per cell: OOS IC vs IC*, BH-significance, netA/netB/netC. Apply the gate: a cell is a candidate only if it **clears IC\* AND is BH-significant AND netC > 0**. State which cells (if any) survive and the overall GO / NO-GO. If nothing survives, decompose: was it gross IC below the bar, cost, or significance? (per the decompose-gross-vs-cost-vs-significance rule).

- [ ] **Step 3: Commit**

```bash
git add scripts/fx_coint/reg_signal_hunt_results.md
git commit -m "docs(fx_coint): regression signal hunt 1-4h results + verdict

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:**
- Data/bars + resample 1m→{1,2,3,4}h + contiguity + session filter → Task 1. ✓
- Vol-normalized target, bps conversion, no look-ahead, purge → Task 2 + Task 3. ✓
- Minimal price-only features → Task 2 (`FEATURE_COLS`). ✓
- Ridge, one model per (pair,freq), 70/30 split → Task 3. ✓
- Continuous IC + break-even IC* + clears flag → Task 3. ✓
- Three decision rules A/B/C net of cost → Task 4. ✓
- BH-FDR across cells + IC-by-hour → Task 5 + Task 6. ✓
- Results table + go/no-go gate → Task 6 + Task 7. ✓
- Out-of-scope items (flow, pooling, regimes, tick-exact, full WFO) correctly omitted. ✓

**Placeholder scan:** No TBD/TODO; every code step has complete code. ✓

**Type consistency:** `build_freq_bars`→`build_panel`→`fit_and_eval`→`eval_rules`/`ic_by_hour` column and dict-key names match across tasks (`sigma_h`, `target_z`, `ret_next_bps`, `pred_bps`, `actual_bps`, `hours`, `ic`, `ic_star`). ✓

**Note on sign-stability:** The spec lists sign-stability as a check. In v1 it is covered implicitly by the IC-by-hour curve (Task 6) and BH-significance; a dedicated cross-fold sign-stability test is deferred to a follow-up if a cell survives, consistent with the spec's "graduate to further verification" framing.
