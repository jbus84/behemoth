# Hourly FX Flow → Direction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Test whether order-flow features give the aeon TS models next-k-bar *directional* predictability that price-only features lack (which scored dirAcc ≈ 0.50).

**Architecture:** A causal flow-feature builder + a horizon-generalised drift-immune tercile labeler feed a grid WFO harness ({1,3,6h} × {price_only,+raw_flow,+engineered,+both}). Significance uses the existing pooled-trade block-bootstrap with Šidák/BH multiplicity correction. Phase 1 is EURUSD single-pair; Phase 2 (cross-sectional) is gated on Phase 1 showing a cell that clears.

**Tech Stack:** Python, polars/pandas, numpy, aeon (QUANT/MRHydra/RDST), scikit-learn, scipy; run via `uv run`.

## Global Constraints

- All features causal: trailing stats use `.shift(1)`; flow at bar t is known at close of t and predicts t+1..t+h. No global (full-sample) normalisation — use causal rolling z only.
- Significance via `moving_block_bootstrap_ci` from `scripts/fx_coint/hourly_pooled_decomp.py` on POOLED trades — never average per-window t-stats.
- Decision gate: a horizon×arm cell "works" only if pooled dirAcc 95% CI excludes 0.50 OR signed-return net 95% CI excludes 0, **after** Šidák/BH correction across the 12-cell grid.
- Data: existing `data/tick_bars/EURUSD_1h_flow.parquet` (cols: bucket, mid, bid, ask, n_ticks, flow_tick, flow_ofi, rvol_bps, spread_bps). No new data builds.
- Cost: `DEFAULT_COST_BPS["EURUSD"] = 0.64` bps.
- WFO: 6mo train / 1mo test, lookback 24, tercile window 500 (matches established harness).
- Work on a branch in a git worktree; the spec doc rides in with the Phase-1 PR.

---

### Task 1: Horizon-generalised drift-immune tercile labeler

**Files:**
- Modify: `scripts/fx_coint/hourly_nextbar_label.py`
- Test: `tests/test_hourly_flow.py`

**Interfaces:**
- Produces: `label_horizon_tercile(df: pd.DataFrame, horizon: int, window: int = 500) -> pd.DataFrame` — adds `tb_label` ∈ {-1,0,1}, `fwd_ret_bps` (h-bar forward mid return in bps), `_label_valid` (bool). Causal rolling terciles of trailing realized 1-bar returns; the h-bar forward return is compared to those thresholds.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_hourly_flow.py
import numpy as np
import pandas as pd
from scripts.fx_coint.hourly_nextbar_label import label_horizon_tercile


def _synth(n=3000, seed=0):
    rng = np.random.default_rng(seed)
    mid = 1.10 * np.exp(np.cumsum(rng.normal(0, 1e-4, n)))
    return pd.DataFrame({"bucket": pd.date_range("2024-01-01", periods=n, freq="h"), "mid": mid})


def test_horizon_label_balanced_and_horizon_correct():
    df = label_horizon_tercile(_synth(), horizon=3, window=500)
    v = df[df["_label_valid"]]
    fracs = v["tb_label"].value_counts(normalize=True)
    for c in (-1, 0, 1):
        assert abs(fracs[c] - 1 / 3) < 0.05            # balanced ~33%
    # fwd_ret_bps at i equals 3-bar forward mid return
    mid = df["mid"].to_numpy()
    i = 1000
    expected = (mid[i + 3] / mid[i] - 1) * 1e4
    assert abs(df["fwd_ret_bps"].iloc[i] - expected) < 1e-6
    # last `horizon` valid-eligible rows are invalid (no forward data)
    assert not df["_label_valid"].iloc[-1]
    assert not df["_label_valid"].iloc[-3]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_hourly_flow.py::test_horizon_label_balanced_and_horizon_correct -v`
Expected: FAIL with `AttributeError`/`ImportError` (function not defined).

- [ ] **Step 3: Write minimal implementation**

```python
# append to scripts/fx_coint/hourly_nextbar_label.py
def label_horizon_tercile(df: pd.DataFrame, horizon: int, window: int = 500) -> pd.DataFrame:
    """Drift-immune h-bar-ahead 3-class label via rolling causal terciles.

    Thresholds at t use realized 1-bar returns known by t; the h-bar forward
    return r_{t->t+h} is labelled against them. Last `horizon` rows unlabelable.
    """
    mid = df["mid"].to_numpy()
    n = len(mid)
    realized = np.empty(n); realized[0] = np.nan
    realized[1:] = mid[1:] / mid[:-1] - 1.0          # r_t, known at t
    fwd = np.full(n, np.nan)
    fwd[: n - horizon] = mid[horizon:] / mid[: n - horizon] - 1.0   # r_{t->t+h}

    r = pd.Series(realized, index=df.index)
    q33 = r.rolling(window, min_periods=window // 2).quantile(1 / 3)
    q67 = r.rolling(window, min_periods=window // 2).quantile(2 / 3)

    label = np.zeros(n, dtype=np.int8)
    f = pd.Series(fwd, index=df.index)
    label[(f < q33).to_numpy(na_value=False)] = -1
    label[(f > q67).to_numpy(na_value=False)] = 1
    valid = (~q33.isna()).to_numpy() & (~np.isnan(fwd))
    label[~valid] = 0

    out = df.copy()
    out["tb_label"] = label
    out["fwd_ret_bps"] = fwd * 10_000.0
    out["_label_valid"] = valid
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_hourly_flow.py::test_horizon_label_balanced_and_horizon_correct -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/fx_coint/hourly_nextbar_label.py tests/test_hourly_flow.py
git commit -m "feat(fx_coint): horizon-generalised drift-immune tercile labeler"
```

---

### Task 2: Causal flow-feature builder + feature-arm channel sets

**Files:**
- Create: `scripts/fx_coint/hourly_flow_features.py`
- Test: `tests/test_hourly_flow.py`

**Interfaces:**
- Consumes: df with cols [mid, bid, ask, n_ticks, flow_tick, flow_ofi, rvol_bps, spread_bps].
- Produces:
  - `add_channels(df, z_window=24, cum_window=6) -> pd.DataFrame` — adds price + flow + engineered channels, all causal.
  - `ARMS: dict[str, list[str]]` — `price_only`, `raw_flow`, `engineered`, `both` → channel-name lists.
  - `build_panel(df, channels, lookback) -> tuple[np.ndarray, np.ndarray, np.ndarray]` — `(X float64 (n,c,L), y int8, valid_pos int idx into df.iloc[lookback:])`. No global normalisation (channels are pre-normalised causally).

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_hourly_flow.py
from scripts.fx_coint.hourly_flow_features import add_channels, ARMS, build_panel


def _synth_flow(n=2000, seed=1):
    rng = np.random.default_rng(seed)
    mid = 1.10 * np.exp(np.cumsum(rng.normal(0, 1e-4, n)))
    spread = np.abs(rng.normal(3e-5, 1e-5, n))
    return pd.DataFrame({
        "bucket": pd.date_range("2024-01-01", periods=n, freq="h"),
        "mid": mid, "bid": mid - spread / 2, "ask": mid + spread / 2,
        "n_ticks": rng.integers(50, 500, n).astype(float),
        "flow_tick": rng.normal(0, 0.03, n), "flow_ofi": rng.normal(0, 0.02, n),
        "rvol_bps": np.abs(rng.normal(1.0, 0.5, n)), "spread_bps": spread / mid * 1e4,
    })


def test_flow_channels_are_causal():
    df = _synth_flow()
    a = add_channels(df.copy())
    df2 = df.copy()
    df2.loc[df2.index[-5:], ["mid", "flow_ofi", "flow_tick"]] *= 1.5  # perturb the FUTURE
    b = add_channels(df2)
    # early-row channels must be unchanged by future perturbation (no leakage)
    cols = [c for c in ARMS["both"]]
    i = 1000
    for c in cols:
        assert abs(a[c].iloc[i] - b[c].iloc[i]) < 1e-9, f"channel {c} leaks future"


def test_build_panel_shapes():
    df = add_channels(_synth_flow())
    df["tb_label"] = np.resize([-1, 0, 1], len(df)).astype(np.int8)
    X, y, pos = build_panel(df, ARMS["both"], lookback=24)
    assert X.dtype == np.float64 and X.ndim == 3
    assert X.shape[1] == len(ARMS["both"]) and X.shape[2] == 24
    assert len(y) == X.shape[0] == len(pos)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_hourly_flow.py -k flow -v`
Expected: FAIL (ImportError: hourly_flow_features).

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/fx_coint/hourly_flow_features.py
"""Causal price + order-flow channels for the hourly direction harness."""
from __future__ import annotations

import numpy as np
import pandas as pd


def _zcausal(s: pd.Series, w: int) -> pd.Series:
    mu = s.rolling(w, min_periods=w).mean().shift(1)
    sd = s.rolling(w, min_periods=w).std().shift(1)
    return ((s - mu) / (sd + 1e-12)).fillna(0.0)


def add_channels(df: pd.DataFrame, z_window: int = 24, cum_window: int = 6) -> pd.DataFrame:
    out = df.copy()
    # --- price channels (causal) ---
    out["mid_ret"] = np.log(out["mid"]).diff().fillna(0.0)
    out["norm_ret"] = _zcausal(out["mid_ret"], z_window)
    raw_spread = out["ask"] - out["bid"]
    out["raw_spread_norm"] = _zcausal(raw_spread, z_window)
    # --- raw flow channels (causal z) ---
    for c in ["flow_tick", "flow_ofi", "n_ticks", "rvol_bps", "spread_bps"]:
        out[f"{c}_z"] = _zcausal(out[c], z_window)
    # --- engineered flow channels (causal) ---
    out["cum_flow_tick"] = out["flow_tick"].rolling(cum_window, min_periods=1).sum()
    out["cum_flow_ofi"] = out["flow_ofi"].rolling(cum_window, min_periods=1).sum()
    out["dflow_ofi"] = out["flow_ofi"].diff().fillna(0.0)
    out["ofi_z"] = _zcausal(out["flow_ofi"], z_window)
    out["actflow"] = out["flow_tick"] * out["n_ticks"]
    out["actflow_z"] = _zcausal(out["actflow"], z_window)
    # flow-price divergence: flow_ofi orthogonalised to contemporaneous return,
    # via causal rolling univariate regression residual (beta uses past only).
    x = out["mid_ret"]; y = out["flow_ofi"]
    cov = (x * y).rolling(z_window, min_periods=z_window).mean().shift(1)
    var = (x * x).rolling(z_window, min_periods=z_window).mean().shift(1)
    beta = (cov / (var + 1e-12)).fillna(0.0)
    out["flow_resid"] = (out["flow_ofi"] - beta * out["mid_ret"]).fillna(0.0)
    out["flow_resid_z"] = _zcausal(out["flow_resid"], z_window)
    return out


ARMS: dict[str, list[str]] = {
    "price_only": ["mid_ret", "norm_ret", "raw_spread_norm"],
    "raw_flow": ["flow_tick_z", "flow_ofi_z", "n_ticks_z", "rvol_bps_z", "spread_bps_z"],
    "engineered": ["cum_flow_tick", "cum_flow_ofi", "dflow_ofi", "ofi_z",
                   "actflow_z", "flow_resid_z"],
}
ARMS["both"] = ARMS["price_only"] + ARMS["raw_flow"] + ARMS["engineered"]


def build_panel(df: pd.DataFrame, channels: list[str], lookback: int):
    arr = df[channels].to_numpy(dtype=np.float64)
    n = len(df)
    ns = n - lookback
    X = np.empty((ns, len(channels), lookback), dtype=np.float64)
    for i in range(ns):
        X[i] = arr[i : i + lookback].T
    y = df["tb_label"].to_numpy()[lookback:].astype(np.int8)
    pos = np.arange(ns)
    return X, y, pos
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_hourly_flow.py -k flow -v`
Expected: PASS (both `test_flow_channels_are_causal`, `test_build_panel_shapes`).

- [ ] **Step 5: Commit**

```bash
git add scripts/fx_coint/hourly_flow_features.py tests/test_hourly_flow.py
git commit -m "feat(fx_coint): causal flow feature builder + feature arms"
```

---

### Task 3: Multiplicity helpers (Šidák + Benjamini-Hochberg)

**Files:**
- Create: `scripts/fx_coint/multiplicity.py`
- Test: `tests/test_hourly_flow.py`

**Interfaces:**
- Produces:
  - `p_from_t(t: float, n: int) -> float` — two-sided p-value, normal approx.
  - `sidak_alpha(alpha: float, m: int) -> float`.
  - `bh_reject(pvals: list[float], alpha: float = 0.05) -> list[bool]` — BH step-up mask.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_hourly_flow.py
from scripts.fx_coint.multiplicity import p_from_t, sidak_alpha, bh_reject


def test_multiplicity_helpers():
    assert abs(p_from_t(0.0, 100) - 1.0) < 1e-9
    assert p_from_t(1.96, 100) < 0.06 and p_from_t(1.96, 100) > 0.04
    assert sidak_alpha(0.05, 12) < 0.05
    # BH: one tiny p among 12 should reject; all-large should not
    assert bh_reject([0.0001] + [0.9] * 11)[0] is True
    assert bh_reject([0.9] * 12) == [False] * 12
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_hourly_flow.py::test_multiplicity_helpers -v`
Expected: FAIL (ImportError).

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/fx_coint/multiplicity.py
"""Multiplicity corrections for the flow-direction grid."""
from __future__ import annotations

import numpy as np
from scipy.stats import norm


def p_from_t(t: float, n: int) -> float:
    return float(2 * (1 - norm.cdf(abs(t))))


def sidak_alpha(alpha: float, m: int) -> float:
    return float(1 - (1 - alpha) ** (1 / m))


def bh_reject(pvals: list[float], alpha: float = 0.05) -> list[bool]:
    p = np.asarray(pvals, dtype=float)
    m = len(p)
    order = np.argsort(p)
    thresh = alpha * (np.arange(1, m + 1) / m)
    passed = p[order] <= thresh
    k = np.where(passed)[0]
    out = np.zeros(m, dtype=bool)
    if len(k):
        cutoff = order[: k.max() + 1]
        out[cutoff] = True
    return [bool(x) for x in out]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_hourly_flow.py::test_multiplicity_helpers -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/fx_coint/multiplicity.py tests/test_hourly_flow.py
git commit -m "feat(fx_coint): Sidak + BH multiplicity helpers"
```

---

### Task 4: Grid WFO harness + pooled gate (Phase 1 EURUSD)

**Files:**
- Create: `scripts/fx_coint/hourly_flow_direction_eval.py`
- Test: `tests/test_hourly_flow.py`

**Interfaces:**
- Consumes: `label_horizon_tercile`, `add_channels`/`ARMS`/`build_panel`, `multiplicity.*`, and from `hourly_pooled_decomp`: `make_model`, `moving_block_bootstrap_ci`; from `hourly_multirocket_wfo`: `load_hourly`, `classify_regime`, `DEFAULT_COST_BPS`.
- Produces:
  - `pooled_metrics(pred, fwd, y_true, cost) -> dict` — dirAcc, balAcc, signed net mean + t + CI.
  - `run_cell(symbol, year, horizon, arm, seeds) -> dict` — one grid cell, pooled over WFO.
  - `main()` — runs the {1,3,6h}×{4 arm} grid, prints table + BH/Šidák verdicts.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_hourly_flow.py
from scripts.fx_coint.hourly_flow_direction_eval import pooled_metrics


def test_pooled_metrics_detects_perfect_direction():
    rng = np.random.default_rng(0)
    fwd = rng.normal(0, 5, 2000)
    y = np.sign(fwd).astype(int)
    pred = y.copy()                      # perfect directional caller
    m = pooled_metrics(pred, fwd, y, cost=0.0)
    assert m["dir_acc"] > 0.99
    assert m["net"] > 0 and m["ci_lo"] > 0
    # random predictions -> ~chance, CI spans 0
    pred_rand = rng.choice([-1, 1], size=2000)
    mr = pooled_metrics(pred_rand, fwd, y, cost=0.0)
    assert 0.45 < mr["dir_acc"] < 0.55
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_hourly_flow.py::test_pooled_metrics_detects_perfect_direction -v`
Expected: FAIL (ImportError).

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/fx_coint/hourly_flow_direction_eval.py
"""Phase 1: does flow give the aeon models hourly directional skill?

Grid {1,3,6h} x {price_only,+raw_flow,+engineered,+both}, pooled WFO with
block-bootstrap CI + Sidak/BH. price_only is the ~0.50 control.
"""
from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import balanced_accuracy_score

warnings.filterwarnings("ignore")
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.fx_coint.hourly_multirocket_wfo import (
    DEFAULT_COST_BPS, classify_regime, load_hourly,
)
from scripts.fx_coint.hourly_nextbar_label import label_horizon_tercile
from scripts.fx_coint.hourly_flow_features import add_channels, ARMS, build_panel
from scripts.fx_coint.hourly_pooled_decomp import (
    SEEDS, make_model, fit_members, majority_vote, moving_block_bootstrap_ci,
)
from scripts.fx_coint.multiplicity import p_from_t, sidak_alpha, bh_reject

LOOKBACK = 24
TRAIN_MO = 6
TEST_MO = 1
WINDOW = 500


def pooled_metrics(pred, fwd, y_true, cost) -> dict:
    active = pred != 0
    n = int(active.sum())
    dir_acc = float((np.sign(pred[active]) == np.sign(fwd[active])).mean()) if n else np.nan
    bal = float(balanced_accuracy_score(y_true, pred))
    net = pred[active] * fwd[active] - cost
    nm = float(net.mean()) if n else np.nan
    t = float(np.sqrt(n) * nm / (net.std() + 1e-12)) if n else np.nan
    lo, hi = moving_block_bootstrap_ci(net, block=4) if n else (np.nan, np.nan)
    return {"n": n, "dir_acc": dir_acc, "bal_acc": bal, "net": nm, "t": t,
            "ci_lo": lo, "ci_hi": hi}


def run_cell(symbol, year, horizon, arm, seeds, model="QUANT") -> dict:
    cost = DEFAULT_COST_BPS[symbol]
    df = load_hourly(symbol)
    start, end = pd.Timestamp(f"{year}-01-01"), pd.Timestamp(f"{year+1}-01-01")
    df = df[(df["bucket"] >= start) & (df["bucket"] < end)].reset_index(drop=True)
    months = pd.date_range(start, end, freq="MS")
    n_windows = len(months) - TRAIN_MO - TEST_MO
    channels = ARMS[arm]
    preds_all, fwd_all, y_all = [], [], []

    for i in range(n_windows):
        tr_s, tr_e = months[i], months[i + TRAIN_MO]
        te_s = months[i + TRAIN_MO]
        te_e = months[i + TRAIN_MO + TEST_MO] if (i + TRAIN_MO + TEST_MO) < len(months) else end
        margin = tr_s - pd.Timedelta(hours=max(LOOKBACK * 2, WINDOW + 50))
        wdf = df[(df["bucket"] >= margin) & (df["bucket"] < te_e)].reset_index(drop=True)
        wdf = label_horizon_tercile(wdf, horizon=horizon, window=WINDOW)
        wdf = add_channels(wdf)
        X, y, _ = build_panel(wdf, channels, LOOKBACK)
        ts = wdf["bucket"].iloc[LOOKBACK:].reset_index(drop=True)
        valid = wdf["_label_valid"].to_numpy()[LOOKBACK:]
        tr_idx = np.where(((ts >= tr_s) & (ts < tr_e)).to_numpy() & valid)[0]
        te_idx = np.where(((ts >= te_s) & (ts < te_e)).to_numpy() & valid)[0]
        if len(tr_idx) < 500 or len(te_idx) < 100:
            continue
        X_tr, y_tr, X_te = X[tr_idx], y[tr_idx], X[te_idx]
        if np.unique(y_tr).size < 2:
            continue
        votes = fit_members(model, X_tr, y_tr, X_te, seeds)
        preds = majority_vote(votes)
        base = wdf.iloc[LOOKBACK:].reset_index(drop=True)
        preds_all.append(preds)
        fwd_all.append(base["fwd_ret_bps"].to_numpy()[te_idx])
        y_all.append(y[te_idx])

    pred = np.concatenate(preds_all); fwd = np.concatenate(fwd_all); yt = np.concatenate(y_all)
    m = pooled_metrics(pred, fwd, yt, cost)
    m.update(horizon=horizon, arm=arm)
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="EURUSD")
    ap.add_argument("--year", type=int, default=2024)
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--model", default="QUANT")
    args = ap.parse_args()
    seeds = SEEDS[: args.seeds]
    horizons = [1, 3, 6]
    arms = ["price_only", "raw_flow", "engineered", "both"]

    rows = []
    for h in horizons:
        for arm in arms:
            r = run_cell(args.symbol, args.year, h, arm, seeds, args.model)
            rows.append(r)
            print(f"  h={h} {arm:<11s} dirAcc={r['dir_acc']:.3f} balAcc={r['bal_acc']:.3f} "
                  f"net={r['net']:+.3f} t={r['t']:+.2f} CI=[{r['ci_lo']:+.3f},{r['ci_hi']:+.3f}] n={r['n']}",
                  flush=True)

    m = len(rows)
    pvals = [p_from_t(r["t"], r["n"]) for r in rows]
    bh = bh_reject(pvals, 0.05)
    sa = sidak_alpha(0.05, m)
    print(f"\nGrid={m} cells.  Sidak alpha={sa:.4f}")
    print(f"{'cell':<16s} {'dirAcc':>7s} {'net':>7s} {'p':>7s} {'BH':>4s} {'Sidak':>6s}  verdict")
    any_edge = False
    for r, p, bhr in zip(rows, pvals, bh):
        sidak_pass = p < sa
        ci_edge = (r["ci_lo"] > 0) or (r["ci_hi"] < 0)
        edge = ci_edge and (bhr or sidak_pass) and r["net"] > 0
        any_edge = any_edge or edge
        print(f"  h={r['horizon']} {r['arm']:<11s} {r['dir_acc']:>7.3f} {r['net']:>+7.3f} "
              f"{p:>7.4f} {str(bhr):>4s} {str(sidak_pass):>6s}  {'EDGE' if edge else 'noise'}")
    print(f"\nPHASE 1 VERDICT: {'EDGE FOUND -> proceed to Phase 2' if any_edge else 'NO-GO (flow does not rescue hourly direction)'}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_hourly_flow.py::test_pooled_metrics_detects_perfect_direction -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/fx_coint/hourly_flow_direction_eval.py tests/test_hourly_flow.py
git commit -m "feat(fx_coint): grid WFO flow-direction harness + pooled gate"
```

---

### Task 5: Run Phase 1, sanity-check control arm, record verdict

**Files:**
- Create: `docs/fx_coint/2026-06-18-flow-direction-phase1-results.md`
- Memory: update `project_fx_hourly_nextbar_direction` + `MEMORY.md`

- [ ] **Step 1: Full quality gate**

Run: `make quality` then `uv run pytest tests/test_hourly_flow.py -v`
Expected: all green (collection errors redden the whole CI job — see memory `project_ci_quality_gate`).

- [ ] **Step 2: Run Phase 1 grid**

Run: `PYTHONUNBUFFERED=1 uv run python scripts/fx_coint/hourly_flow_direction_eval.py --year 2024 --seeds 5 --model QUANT 2>&1 | tee /tmp/flow_dir_2024.log`
Expected: a 12-row table + Phase-1 verdict line.

- [ ] **Step 3: Sanity-check the control arm (harness-integrity gate)**

Confirm `price_only` cells show dirAcc ≈ 0.50 and net ≤ 0 (matches the established baseline). If `price_only` shows a spurious "EDGE", STOP — the harness leaks; investigate before trusting any flow cell.

- [ ] **Step 4: Attribution + write-up**

In the results doc, record: per-cell table; whether any flow cell cleared post-correction; and the attribution — does `both`/`engineered` (which include `flow_resid_z`) beat `raw_flow`? If yes → price-independent flow signal; if no → flow echoes price (consistent with `project_fx_flow_factor_deviation`).

- [ ] **Step 5: Update memory + commit**

```bash
git add docs/fx_coint/2026-06-18-flow-direction-phase1-results.md
git commit -m "docs(fx_coint): hourly flow-direction Phase 1 results + verdict"
```
Then update `project_fx_hourly_nextbar_direction` memory with the Phase-1 outcome (GO→Phase 2, or NO-GO closing hourly direction), and open the PR (worktree branch) carrying the spec, code, tests, and results.

---

## Self-Review

**Spec coverage:** hypothesis+gate → Task 4 `main`/verdict; raw+engineered+divergence features → Task 2; horizon sweep → Task 1 + Task 4 grid; multiplicity → Task 3 + Task 4; price-only control → Task 5 Step 3; orthogonalised-flow attribution → Task 5 Step 4; Phase 2 gating → Task 4 verdict + Task 5 Step 5. Cross-sectional (Phase 2) intentionally deferred — not in this plan (gated).

**Placeholder scan:** none — all steps carry real code/commands.

**Type consistency:** `add_channels`/`ARMS`/`build_panel` signatures match across Tasks 2 and 4; `pooled_metrics`/`run_cell` keys (`dir_acc`,`bal_acc`,`net`,`t`,`ci_lo`,`ci_hi`,`n`) consistent Task 4 ↔ test; `fit_members`/`majority_vote`/`moving_block_bootstrap_ci`/`SEEDS`/`make_model` are existing exports of `hourly_pooled_decomp.py` (verified this session).
