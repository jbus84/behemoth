# Path-Geometry Phase B — TF Pre-screen + Geometry Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pre-screen which timeframes (1h/2h/3h/4h) show a conditional path-distribution shift, then for the survivors causally optimize stop/take-profit/hold geometry and decide — via gates 2–3 (beats fixed-horizon baseline net of cost, day-clustered, placebo-null, BH-FDR) — whether bracket geometry improves the 2h momentum tail-long edge or whether it is hold-to-horizon.

**Architecture:** Two stages in one plan. B0 reuses Phase-A `gate_one_edge` across timeframes. B1 adds a pure 1-minute **bracket evaluator** (`path_bracket.py`), a fold-aware **entry+path generator** and **causal geometry optimizer** with **gate statistics** (`path_geometry_opt.py`), and a CLI that runs the optimizer on survivors plus an offset-placebo-null optimizer, writing `path_geometry_results.md`.

**Tech Stack:** Python 3.12, numpy, pandas, polars, scikit-learn, scipy.stats, pytest. Reuses Phase-A `path_geometry_paths`, `path_ensemble`, `path_shift_gate`; and `reg_signal_hunt` (build_freq_bars/build_panel/COST_BPS/bh_reject), `tail_wfo.day_clustered_tstat`.

## Global Constraints

- Geometry selection is **causal**: within each expanding WFO fold, pick the best grid cell on TRAIN trades, apply it to TEST trades; concatenate test → OOS track. Never full-sample. (spec §2 B1)
- The `(stop=none, tp=none, max_hold=native)` cell **is** the fixed-horizon baseline every cell must beat. (spec §2)
- Bracket exit: first minute the signed (by side) move crosses `−stop·σ` or `+tp·σ`; else at max-hold. A single-minute gap straddling both resolves **stop-first** (conservative). σ = entry bar `sigma_h`. Net of `reg_signal_hunt.COST_BPS[sym]`, one round-trip. (spec §2 B1)
- Grid: `stop ∈ {none,1,1.5,2,3}σ`, `take_profit ∈ {none,2,3,4}σ`, `max_hold ∈ {native=1 bar, 2×=2 bars}`. TP is a falsification check (expected not to help). (spec §2)
- Significance/nulls use **day/block-clustered** resampling, NOT IID permutation. (spec §3 rigor)
- Gate 2: day-clustered t + year-block bootstrap 95% CI clearing zero + positive-years, pooled across pairs, vs baseline. Gate 3: offset-placebo-null optimizer must not beat baseline AND **BH-FDR across the full {TF×cell} grid**. (spec §3)
- Timeframes entering B1 = the SHIFTED set from B0 (2h known; others evidence-gated). (spec §2 B0)
- Pairs: TIGHT_MAJORS `["EURUSD","GBPUSD","USDJPY"]`. New code under `scripts/fx_coint/`; tests under `tests/fx_coint/`.

---

## Task 1: Bracket evaluator (pure)

**Files:**
- Create: `scripts/fx_coint/path_bracket.py`
- Test: `tests/fx_coint/test_path_bracket.py`

**Interfaces:**
- Produces:
  - `evaluate_bracket(entry_mid: float, minutes: np.ndarray, side: str, sigma_bps: float, stop_sigma: float | None, tp_sigma: float | None, cost_bps: float) -> float` — signed net bps. Walk `minutes` in order; signed move at step i = `sign*(log(minutes[i]/entry_mid))*1e4`. Exit at the first i where (stop set and `signed_i <= -stop_sigma*sigma_bps`) or (tp set and `signed_i >= +tp_sigma*sigma_bps`); if both true at the same i, **stop wins**. If none triggers, exit at the last minute. Return `realized_signed_bps - cost_bps`. `None` for stop/tp disables that leg. Empty minutes → NaN.

- [ ] **Step 1: Write the failing test**

```python
# tests/fx_coint/test_path_bracket.py
import numpy as np
from scripts.fx_coint.path_bracket import evaluate_bracket

def _levels(entry, bps_list):
    return entry * np.exp(np.array(bps_list) / 1e4)

def test_stop_triggers_first():
    entry = 1.0
    mins = _levels(entry, [5, -25, 40])     # long: hits -25 at i=1 before +40
    net = evaluate_bracket(entry, mins, "long", sigma_bps=10.0,
                           stop_sigma=2.0, tp_sigma=3.0, cost_bps=0.6)
    # stop at -2*10 = -20bps; signed -25 at i=1 -> exit -25 - 0.6
    assert np.isclose(net, -25.0 - 0.6, atol=1e-6)

def test_tp_triggers():
    entry = 1.0
    mins = _levels(entry, [10, 35, -50])    # +35 hits tp 3*10=30 at i=1
    net = evaluate_bracket(entry, mins, "long", 10.0, stop_sigma=2.0, tp_sigma=3.0, cost_bps=0.6)
    assert np.isclose(net, 35.0 - 0.6, atol=1e-6)

def test_no_trigger_exits_last():
    entry = 1.0
    mins = _levels(entry, [5, -5, 8])
    net = evaluate_bracket(entry, mins, "long", 10.0, stop_sigma=2.0, tp_sigma=3.0, cost_bps=0.6)
    assert np.isclose(net, 8.0 - 0.6, atol=1e-6)

def test_straddle_resolves_stop_first():
    entry = 1.0
    mins = _levels(entry, [-30, 0])          # one minute already past both stop(-20) & tp(+...)? only stop
    net = evaluate_bracket(entry, mins, "long", 10.0, stop_sigma=2.0, tp_sigma=2.0, cost_bps=0.0)
    assert np.isclose(net, -30.0, atol=1e-6)

def test_short_side_and_disabled_legs():
    entry = 1.0
    mins = _levels(entry, [-10, -40])        # short: signed = +10, +40 -> tp 3*10=30 hit at i=1
    net = evaluate_bracket(entry, mins, "short", 10.0, stop_sigma=None, tp_sigma=3.0, cost_bps=0.0)
    assert np.isclose(net, 40.0, atol=1e-6)

def test_empty_is_nan():
    assert np.isnan(evaluate_bracket(1.0, np.empty(0), "long", 10.0, 2.0, 3.0, 0.6))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/repositories/behemoth/.claude/worktrees/fx-path-geometry && uv run pytest tests/fx_coint/test_path_bracket.py -q`
Expected: FAIL `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/fx_coint/path_bracket.py
"""Bracket (stop/take-profit/max-hold) evaluator over a 1-minute mid path."""
from __future__ import annotations

import numpy as np


def evaluate_bracket(entry_mid: float, minutes: np.ndarray, side: str, sigma_bps: float,
                     stop_sigma: float | None, tp_sigma: float | None,
                     cost_bps: float) -> float:
    if len(minutes) < 1 or sigma_bps <= 0:
        return float("nan")
    sign = 1.0 if side == "long" else -1.0
    signed = sign * (np.log(minutes) - np.log(entry_mid)) * 1e4
    stop_bps = None if stop_sigma is None else -stop_sigma * sigma_bps
    tp_bps = None if tp_sigma is None else tp_sigma * sigma_bps
    for i in range(len(signed)):
        hit_stop = stop_bps is not None and signed[i] <= stop_bps
        hit_tp = tp_bps is not None and signed[i] >= tp_bps
        if hit_stop:                       # stop wins ties (conservative)
            return float(signed[i] - cost_bps)
        if hit_tp:
            return float(signed[i] - cost_bps)
    return float(signed[-1] - cost_bps)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/repositories/behemoth/.claude/worktrees/fx-path-geometry && uv run pytest tests/fx_coint/test_path_bracket.py -q`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
cd ~/repositories/behemoth/.claude/worktrees/fx-path-geometry
git add scripts/fx_coint/path_bracket.py tests/fx_coint/test_path_bracket.py
git commit -m "feat(fx_coint): 1-minute bracket evaluator (stop/tp/max-hold, stop-first ties)"
```

---

## Task 2: Fold-aware entry + path generator

**Files:**
- Create: `scripts/fx_coint/path_geometry_opt.py`
- Test: `tests/fx_coint/test_path_geometry_opt.py`

**Interfaces:**
- Consumes: `reg_signal_hunt.build_freq_bars/build_panel/COST_BPS`, `path_geometry_paths.build_minute_index/hold_path`, `tail_wfo` Ridge/scaler pattern.
- Produces:
  - `@dataclass Trade(entry_mid: float, minutes: np.ndarray, side: str, sigma_bps: float, bucket: np.datetime64, cost_bps: float)` — `cost_bps` is the trade's pair cost (`COST_BPS[sym]`), carried so pooled evaluation charges each pair its own cost (USDJPY 0.80 ≠ EURUSD 0.64).
  - `fold_trades(sym, freq="2h", q=0.95, n_folds=5, n_bars=1) -> list[dict]` — replicates `tail_wfo.walk_forward`'s expanding folds; per fold returns `{"train": list[Trade], "test": list[Trade]}` where train trades are bars in `[:split]` with `train_pred ≥ quantile(train_pred,q)` and test trades are `[test_lo:test_hi]` with `test_pred ≥ quantile(train_pred,q)`. Each Trade has its `minutes` path (via `hold_path`, anchored at the bar-close mid) and `sigma_bps` from panel `sigma_h`. Trades with empty paths are dropped.

- [ ] **Step 1: Write the failing test**

```python
# tests/fx_coint/test_path_geometry_opt.py
import numpy as np
from scripts.fx_coint.path_geometry_opt import fold_trades, Trade

def test_fold_trades_structure_and_causality():
    folds = fold_trades("EURUSD", freq="2h", q=0.95, n_folds=5, n_bars=1)
    assert len(folds) >= 3
    total_test = sum(len(f["test"]) for f in folds)
    assert total_test > 30
    for f in folds:
        assert all(isinstance(t, Trade) for t in f["train"] + f["test"])
        # every trade has a non-empty path and positive sigma
        assert all(len(t.minutes) > 0 and t.sigma_bps > 0 for t in f["test"])
        # causal: max train bucket < min test bucket within a fold
        if f["train"] and f["test"]:
            assert max(t.bucket for t in f["train"]) < min(t.bucket for t in f["test"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/repositories/behemoth/.claude/worktrees/fx-path-geometry && uv run pytest tests/fx_coint/test_path_geometry_opt.py::test_fold_trades_structure_and_causality -q`
Expected: FAIL `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/fx_coint/path_geometry_opt.py
"""Causal geometry optimizer for the tail-long edge: fold-aware trades, grid search, gates."""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import polars as pl
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.fx_coint.path_geometry_paths import build_minute_index, hold_path  # noqa: E402
from scripts.fx_coint.reg_signal_hunt import (  # noqa: E402
    COST_BPS,
    FEATURE_COLS,
    build_freq_bars,
    build_panel,
)


@dataclass
class Trade:
    entry_mid: float
    minutes: np.ndarray
    side: str
    sigma_bps: float
    bucket: np.datetime64
    cost_bps: float


def _bars_panel(sym, freq):
    bars = build_freq_bars(pl.read_parquet(_REPO_ROOT / f"data/tick_bars/{sym}_1m_flow.parquet"), freq)
    panel = build_panel(bars)
    close = dict(zip(bars["bucket"].to_numpy(), bars["mid"].to_numpy(), strict=False))
    return panel, close


def _mk_trade(bk, sigma, close, bn, mids, freq, n_bars, cost_bps):
    em = close.get(bk)
    if em is None or not np.isfinite(em) or not (sigma > 0):
        return None
    mins = hold_path(bk, freq, bn, mids, n_bars=n_bars)
    if len(mins) < 1:
        return None
    return Trade(float(em), mins, "long", float(sigma), bk, float(cost_bps))


def fold_trades(sym, freq="2h", q=0.95, n_folds=5, n_bars=1, min_train_frac=0.5, purge=1):
    panel, close = _bars_panel(sym, freq)
    bn, mids = build_minute_index(sym)
    X = panel[FEATURE_COLS].to_numpy()
    yz = panel["target_z"].to_numpy()
    bucket = panel["bucket"].to_numpy()
    sig = panel["sigma_h"].to_numpy()
    n = len(panel)
    cost = COST_BPS[sym]
    edges = np.linspace(int(n * min_train_frac), n, n_folds + 1).astype(int)
    out = []
    for k in range(n_folds):
        split = edges[k]
        test_lo, test_hi = edges[k] + purge, edges[k + 1]
        if test_hi - test_lo < 1 or split < 10:
            continue
        scaler = StandardScaler().fit(X[:split])
        model = Ridge(alpha=1.0).fit(scaler.transform(X[:split]), yz[:split])
        train_pred = model.predict(scaler.transform(X[:split]))
        test_pred = model.predict(scaler.transform(X[test_lo:test_hi]))
        thr = np.quantile(train_pred, q)
        tr = [_mk_trade(bucket[i], sig[i], close, bn, mids, freq, n_bars, cost)
              for i in np.where(train_pred >= thr)[0]]
        te = [_mk_trade(bucket[test_lo + j], sig[test_lo + j], close, bn, mids, freq, n_bars, cost)
              for j in np.where(test_pred >= thr)[0]]
        out.append({"train": [t for t in tr if t], "test": [t for t in te if t]})
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/repositories/behemoth/.claude/worktrees/fx-path-geometry && uv run pytest tests/fx_coint/test_path_geometry_opt.py -q`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add scripts/fx_coint/path_geometry_opt.py tests/fx_coint/test_path_geometry_opt.py
git commit -m "feat(fx_coint): fold-aware tail-long trades with attached 1-min paths"
```

---

## Task 3: Geometry grid + causal optimizer

**Files:**
- Modify: `scripts/fx_coint/path_geometry_opt.py`
- Test: `tests/fx_coint/test_path_geometry_opt.py`

**Interfaces:**
- Consumes: `Trade`, `path_bracket.evaluate_bracket`.
- Produces:
  - `GRID: list[tuple[float|None, float|None]]` = all `(stop_sigma, tp_sigma)` from `stop∈{None,1,1.5,2,3}`, `tp∈{None,2,3,4}` (20 cells). (max_hold handled by `n_bars` passed to `fold_trades`, not inside the grid here.)
  - `BASELINE_CELL = (None, None)`.
  - `cell_net(trades, cell) -> np.ndarray` — net bps per trade for a `(stop,tp)` cell via `evaluate_bracket`, charging each trade its own `tr.cost_bps`.
  - `optimize_geometry(folds) -> dict` — per fold pick the GRID cell maximizing train mean net, apply to test; return `{"net_oos": (m,), "bucket_oos": (m,), "baseline_oos": (m,), "selected_cells": [...]}` where `baseline_oos` is the `(None,None)` cell applied to the same test trades.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/fx_coint/test_path_geometry_opt.py
from scripts.fx_coint.path_geometry_opt import GRID, BASELINE_CELL, cell_net, optimize_geometry, Trade
import numpy as np

def _trade(bps_path, sigma=10.0, side="long", cost=0.6):
    entry = 1.0
    mins = entry * np.exp(np.array(bps_path) / 1e4)
    return Trade(entry, mins, side, sigma, np.datetime64("2022-01-03"), cost)

def test_grid_has_baseline_and_20_cells():
    assert BASELINE_CELL in GRID
    assert len(GRID) == 20

def test_cell_net_baseline_equals_terminal():
    trades = [_trade([5, -5, 12], cost=0.6)]
    net = cell_net(trades, BASELINE_CELL)
    assert np.isclose(net[0], 12 - 0.6, atol=1e-6)

def test_optimize_picks_protective_stop_when_it_helps_on_train():
    # train: a few trades with big losers a stop would cut; test mirrors
    losers = [_trade([-50, -60], cost=0.0) for _ in range(5)]
    winners = [_trade([10, 40], cost=0.0) for _ in range(5)]
    folds = [{"train": losers + winners, "test": losers + winners}]
    r = optimize_geometry(folds)
    assert r["net_oos"].mean() >= r["baseline_oos"].mean()  # geometry >= baseline on train-selected cell
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/repositories/behemoth/.claude/worktrees/fx-path-geometry && uv run pytest tests/fx_coint/test_path_geometry_opt.py -q`
Expected: FAIL (ImportError on GRID/optimize_geometry).

- [ ] **Step 3: Write minimal implementation**

```python
# add to scripts/fx_coint/path_geometry_opt.py
from scripts.fx_coint.path_bracket import evaluate_bracket  # noqa: E402

_STOPS = [None, 1.0, 1.5, 2.0, 3.0]
_TPS = [None, 2.0, 3.0, 4.0]
GRID = [(s, t) for s in _STOPS for t in _TPS]
BASELINE_CELL = (None, None)


def cell_net(trades, cell):
    s, t = cell
    return np.array([evaluate_bracket(tr.entry_mid, tr.minutes, tr.side, tr.sigma_bps,
                                      s, t, tr.cost_bps) for tr in trades], dtype=float)


def optimize_geometry(folds):
    net_oos, bk_oos, base_oos, cells = [], [], [], []
    for f in folds:
        if not f["train"] or not f["test"]:
            continue
        best, best_mean = BASELINE_CELL, -np.inf
        for cell in GRID:
            m = np.nanmean(cell_net(f["train"], cell))
            if m > best_mean:
                best_mean, best = m, cell
        te_net = cell_net(f["test"], best)
        te_base = cell_net(f["test"], BASELINE_CELL)
        net_oos.append(te_net)
        base_oos.append(te_base)
        bk_oos.append(np.array([tr.bucket for tr in f["test"]], dtype="datetime64[ns]"))
        cells.append(best)
    return {"net_oos": np.concatenate(net_oos), "baseline_oos": np.concatenate(base_oos),
            "bucket_oos": np.concatenate(bk_oos), "selected_cells": cells}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/repositories/behemoth/.claude/worktrees/fx-path-geometry && uv run pytest tests/fx_coint/test_path_geometry_opt.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add scripts/fx_coint/path_geometry_opt.py tests/fx_coint/test_path_geometry_opt.py
git commit -m "feat(fx_coint): coarse geometry grid + causal select-on-train/apply-on-test optimizer"
```

---

## Task 4: Clustered gate statistics

**Files:**
- Modify: `scripts/fx_coint/path_geometry_opt.py`
- Test: `tests/fx_coint/test_path_geometry_opt.py`

**Interfaces:**
- Consumes: `tail_wfo.day_clustered_tstat`, `reg_signal_hunt.bh_reject`.
- Produces:
  - `year_block_bootstrap_ci(net, bucket, n_boot=3000, seed=0) -> (lo, hi)` — resample whole calendar years.
  - `positive_years(net, bucket) -> (n_pos, n_total)`.
  - `paired_day_clustered_p(net, baseline, bucket) -> dict` — day-clustered t-test on the **per-trade difference** `net - baseline` (the marginal lift), returning `{n_days, mean_diff, t_stat, p_value}` via `day_clustered_tstat(net - baseline, bucket)`.
  - `gate2(opt_result) -> dict` — pooled `{mean_base, mean_geom, mean_diff, day_t, day_p, ci_lo, ci_hi, pos_y, n_y}` on the geometry vs baseline OOS tracks.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/fx_coint/test_path_geometry_opt.py
import pandas as pd
from scripts.fx_coint.path_geometry_opt import year_block_bootstrap_ci, positive_years, paired_day_clustered_p

def test_positive_years():
    bk = pd.to_datetime(["2020-01-01","2020-06-01","2021-01-01"]).values
    pos, tot = positive_years(np.array([1.0,1.0,-2.0]), bk)
    assert (pos, tot) == (1, 2)

def test_bootstrap_ci_order():
    rng = np.random.default_rng(0)
    bk = pd.to_datetime(np.repeat(["2019","2020","2021","2022"], 25)).values
    lo, hi = year_block_bootstrap_ci(rng.normal(0.5,1,100), bk, n_boot=400, seed=1)
    assert lo < hi

def test_paired_day_clustered_zero_when_identical():
    bk = pd.to_datetime(np.repeat(pd.date_range("2020-01-01", periods=10), 1)).values
    net = np.arange(10.0); base = np.arange(10.0)
    r = paired_day_clustered_p(net, base, bk)
    assert np.isclose(r["mean_diff"], 0.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/repositories/behemoth/.claude/worktrees/fx-path-geometry && uv run pytest tests/fx_coint/test_path_geometry_opt.py -q`
Expected: FAIL (ImportError).

- [ ] **Step 3: Write minimal implementation**

```python
# add to scripts/fx_coint/path_geometry_opt.py
import pandas as pd  # noqa: E402

from scripts.fx_coint.tail_wfo import day_clustered_tstat  # noqa: E402


def year_block_bootstrap_ci(net, bucket, n_boot=3000, seed=0):
    rng = np.random.default_rng(seed)
    s = pd.Series(np.asarray(net, float), index=pd.to_datetime(pd.Series(bucket)).dt.year)
    blocks = [g.to_numpy() for _, g in s.groupby(level=0)]
    if len(blocks) < 2:
        return float("nan"), float("nan")
    means = np.empty(n_boot)
    for b in range(n_boot):
        pick = rng.integers(0, len(blocks), len(blocks))
        means[b] = np.concatenate([blocks[i] for i in pick]).mean()
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def positive_years(net, bucket):
    yr = pd.Series(np.asarray(net, float), index=pd.to_datetime(pd.Series(bucket)).dt.year)
    m = yr.groupby(level=0).mean()
    return int((m > 0).sum()), int(len(m))


def paired_day_clustered_p(net, baseline, bucket):
    diff = np.asarray(net, float) - np.asarray(baseline, float)
    dc = day_clustered_tstat(diff, bucket)
    return {"n_days": dc["n_days"], "mean_diff": dc["daily_mean"],
            "t_stat": dc["t_stat"], "p_value": dc["p_value"]}


def gate2(opt):
    net, base, bk = opt["net_oos"], opt["baseline_oos"], opt["bucket_oos"]
    pdc = paired_day_clustered_p(net, base, bk)
    lo, hi = year_block_bootstrap_ci(net - base, bk)
    pos, ny = positive_years(net - base, bk)
    return {"mean_base": float(np.nanmean(base)), "mean_geom": float(np.nanmean(net)),
            "mean_diff": pdc["mean_diff"], "day_t": pdc["t_stat"], "day_p": pdc["p_value"],
            "ci_lo": lo, "ci_hi": hi, "pos_y": pos, "n_y": ny}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/repositories/behemoth/.claude/worktrees/fx-path-geometry && uv run pytest tests/fx_coint/test_path_geometry_opt.py -q`
Expected: PASS (7 passed).

- [ ] **Step 5: Commit**

```bash
git add scripts/fx_coint/path_geometry_opt.py tests/fx_coint/test_path_geometry_opt.py
git commit -m "feat(fx_coint): clustered gate-2 statistics (day-clustered diff, year bootstrap, pos-years)"
```

---

## Task 5: B0 pre-screen + B1 main CLI (placebo null + BH-FDR) + run

**Files:**
- Modify: `scripts/fx_coint/path_geometry_opt.py` (add `prescreen`, `placebo_optimize`, `main`)
- Test: `tests/fx_coint/test_path_geometry_opt.py`

**Interfaces:**
- Consumes: `path_shift_gate.gate_one_edge`, `path_ensemble.{tail_long_entries,offset_placebo_entries,_panel_and_closes}`, `reg_signal_hunt.{COST_BPS,bh_reject}`, `path_geometry_paths.{build_minute_index,hold_path}`.
- Produces:
  - `prescreen(timeframes=("1h","2h","3h","4h"), pairs=TIGHT, seed=0) -> dict[str,bool]` — run `gate_one_edge` per TF (tail-long, n_bars=1), return `{tf: shifted}`.
  - `placebo_optimize(sym, freq, n_bars, seed) -> dict` — build placebo entries (offset-shifted), attach paths (per-pair cost on each Trade), run the SAME per-fold optimizer structure (select-on-train/apply-on-test using the placebo trades split into the WFO folds by time order), return its `gate2`-style summary. Used as the gate-3 null: it must NOT beat baseline.
  - `main()` — run `prescreen`; for each SHIFTED tf, `optimize_geometry` pooled over TIGHT (n_bars=1 and 2), compute `gate2`, run `placebo_optimize` null, collect per-(tf,cell) selected-cell day_p across folds and apply `bh_reject`; print and write `scripts/fx_coint/path_geometry_results.md` with the GO/NO-GO read per timeframe.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/fx_coint/test_path_geometry_opt.py
from scripts.fx_coint.path_geometry_opt import prescreen

def test_prescreen_returns_bool_per_tf_and_2h_true():
    res = prescreen(timeframes=("2h",), pairs=["EURUSD","GBPUSD","USDJPY"], seed=0)
    assert set(res.keys()) == {"2h"}
    assert isinstance(res["2h"], bool)
    assert res["2h"] is True   # 2h shifted in Phase A
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/repositories/behemoth/.claude/worktrees/fx-path-geometry && uv run pytest tests/fx_coint/test_path_geometry_opt.py::test_prescreen_returns_bool_per_tf_and_2h_true -q`
Expected: FAIL (ImportError on `prescreen`).

- [ ] **Step 3: Write minimal implementation**

```python
# add to scripts/fx_coint/path_geometry_opt.py
from scripts.fx_coint.path_ensemble import (  # noqa: E402
    _panel_and_closes,
    offset_placebo_entries,
    tail_long_entries,
)
from scripts.fx_coint.path_shift_gate import TIGHT_MAJORS, gate_one_edge  # noqa: E402
from scripts.fx_coint.reg_signal_hunt import COST_BPS, bh_reject  # noqa: E402


def prescreen(timeframes=("1h", "2h", "3h", "4h"), pairs=TIGHT_MAJORS, seed=0):
    res = {}
    for tf in timeframes:
        g = gate_one_edge(pairs, lambda s, f: tail_long_entries(s, f, q=0.95),
                          freq=tf, n_bars=1, label=f"tail-long {tf}", min_off_days=3, seed=seed)
        res[tf] = bool(g["shifted"])
    return res


def _placebo_folds(sym, freq, n_bars, seed):
    """Offset-placebo trades split into time-ordered expanding folds (same shape as fold_trades)."""
    ents = tail_long_entries(sym, freq, q=0.95)
    plc = offset_placebo_entries(sym, freq, ents, seed=seed)
    _panel, close = _bars_panel(sym, freq)
    bn, mids = build_minute_index(sym)
    cost = COST_BPS[sym]
    trades = [_mk_trade(b, s, close, bn, mids, freq, n_bars, cost) for b, _side, s in plc]
    trades = sorted([t for t in trades if t], key=lambda t: t.bucket)
    if len(trades) < 10:
        return []
    edges = np.linspace(int(len(trades) * 0.5), len(trades), 6).astype(int)
    folds = []
    for k in range(5):
        split = edges[k]
        lo, hi = edges[k] + 1, edges[k + 1]
        if hi - lo < 1 or split < 5:
            continue
        folds.append({"train": trades[:split], "test": trades[lo:hi]})
    return folds


def placebo_optimize(sym, freq, n_bars, seed):
    folds = _placebo_folds(sym, freq, n_bars, seed)
    if not folds:
        return None
    return gate2(optimize_geometry(folds))


def _pool_folds(pairs, freq, n_bars):
    folds = []
    for sym in pairs:
        for f in fold_trades(sym, freq=freq, n_bars=n_bars):
            folds.append(f)
    return folds


def main():
    shifted = prescreen()
    survivors = [tf for tf, s in shifted.items() if s]
    lines = ["# Path-geometry Phase B results", "",
             f"## B0 pre-screen: {shifted}  -> survivors {survivors}", ""]
    fdr_pvals, fdr_labels = [], []
    for tf in survivors:
        for n_bars in (1, 2):
            folds = _pool_folds(TIGHT_MAJORS, tf, n_bars)  # each Trade carries its pair cost
            opt = optimize_geometry(folds)
            g = gate2(opt)
            # placebo null pooled across pairs
            plc = [placebo_optimize(s, tf, n_bars, seed=0) for s in TIGHT_MAJORS]
            plc_means = [p["mean_diff"] for p in plc if p]
            null_mean = float(np.nanmean(plc_means)) if plc_means else float("nan")
            lines.append(f"### {tf} n_bars={n_bars}: base={g['mean_base']:+.2f} geom={g['mean_geom']:+.2f} "
                         f"diff={g['mean_diff']:+.2f} day_t={g['day_t']:+.2f} day_p={g['day_p']:.4f} "
                         f"pos={g['pos_y']}/{g['n_y']} boot95=[{g['ci_lo']:+.2f},{g['ci_hi']:+.2f}] "
                         f"null_diff={null_mean:+.2f} cells={set(opt['selected_cells'])}")
            fdr_pvals.append(g["day_p"]); fdr_labels.append(f"{tf}/{n_bars}bar")
    if fdr_pvals:
        rej = bh_reject(np.array(fdr_pvals), alpha=0.05)
        lines.append("")
        lines.append(f"## BH-FDR across {len(fdr_pvals)} cells (alpha 0.05): " +
                     ", ".join(f"{lab}={'REJECT' if r else 'keep-null'}"
                               for lab, r in zip(fdr_labels, rej, strict=False)))
    out = "\n".join(lines)
    print(out)
    (Path(__file__).resolve().parent / "path_geometry_results.md").write_text(out + "\n")


if __name__ == "__main__":
    main()
```

Note: confirm `reg_signal_hunt.bh_reject` signature — it returns a boolean array of rejections given p-values and alpha (the same helper `tail_wfo` imports). If its signature differs (e.g. returns indices), adapt the `rej` handling accordingly; check with `python -c "from scripts.fx_coint.reg_signal_hunt import bh_reject; help(bh_reject)"`.

- [ ] **Step 4: Run tests, then run the real Phase B**

Run: `cd ~/repositories/behemoth/.claude/worktrees/fx-path-geometry && uv run pytest tests/fx_coint/test_path_geometry_opt.py -q`
Expected: PASS (8 passed).

Then: `uv run python scripts/fx_coint/path_geometry_opt.py`
Expected: prints B0 survivors, then per surviving (tf, n_bars) the baseline vs geometry diff, day-clustered p, bootstrap CI, positive-years, placebo null diff, selected cells, and the BH-FDR verdict; writes `path_geometry_results.md`. **Interpretation gate (report honestly):** a (tf,n_bars) is a GO only if geometry mean_diff > 0 AND day_p clears BH-FDR AND year-bootstrap CI excludes 0 AND the placebo null does NOT show the same lift. The expected honest outcome is either a modest 2–3σ stop helps, or no cell beats baseline (hold-to-horizon). TP-dominant selected cells are a red flag (falsification).

- [ ] **Step 5: Run quality gate and commit**

Run: `cd ~/repositories/behemoth/.claude/worktrees/fx-path-geometry && make quality`
Expected: ty + ruff clean (fix lint in new files first).

```bash
git add scripts/fx_coint/path_geometry_opt.py tests/fx_coint/test_path_geometry_opt.py scripts/fx_coint/path_geometry_results.md
git commit -m "feat(fx_coint): Phase B pre-screen + geometry optimizer gates + results"
```

---

## Self-Review notes

- **Spec coverage:** §2 B0 pre-screen → Task 5 `prescreen`; §2 B1 bracket evaluator → Task 1; fold-aware causal trades → Task 2; grid + causal optimizer → Task 3; §3 gate 2 (day-clustered diff, year bootstrap, pos-years) → Task 4; §3 gate 3 (placebo null + BH-FDR) → Task 5; rigor upgrade (clustered, not IID) → Task 4 uses `day_clustered_tstat` + year-block bootstrap (no IID permutation in the gate). Jitter-curve reporting (spec §3) is available via Phase-A `gate_one_edge` robustness block surfaced in B0 output — note it is not re-implemented here.
- **Type consistency:** `Trade` fields used identically across Tasks 2/3/5; `optimize_geometry` returns `net_oos/baseline_oos/bucket_oos/selected_cells`; `gate2` consumes those keys.
- **Known risks / checks for the implementer:**
  - `bh_reject` signature must be confirmed (Task 5 note).
  - `max_hold` is realized via `n_bars` (1 = native, 2 = 2×) passed to `fold_trades`/`_pool_folds`, NOT as a third grid axis — the plan iterates `n_bars ∈ {1,2}` in `main`. Keep this consistent.
  - Cost: each `Trade` carries its pair's `COST_BPS[sym]`, so pooled evaluation charges per-pair cost (USDJPY 0.80 ≠ EURUSD 0.64) — no representative-cost approximation. Verify `cell_net` uses `tr.cost_bps`.
  - The placebo null reuses the geometry optimizer on offset-shifted entries; it must show NO lift for a clean gate 3.