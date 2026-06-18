# FX Tail-Edge Walk-Forward Confirmation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Confirm or kill the PR #340 tail edge by walk-forward evaluating a long-only top-decile strategy with no-look-ahead decile gating and decile-level significance net of real cost.

**Architecture:** New importable script `scripts/fx_coint/tail_wfo.py` of small pure functions: `walk_forward` (refit Ridge per expanding fold, returns per-fold train/test prediction arrays), `gate_trades` (select trades using the TRAIN-derived quantile threshold — the key no-look-ahead fix), `cell_stats` (per-trade significance + per-fold robustness), and a `main()` orchestrator that loops the universe, applies BH-FDR across cells, runs a q-sensitivity sweep, and prints the verdict table. Reuses `build_freq_bars`, `build_panel`, `FEATURE_COLS`, `COST_BPS` from `scripts/fx_coint/reg_signal_hunt.py` (this branch stacks on PR #340).

**Tech Stack:** Python, polars (bars), pandas/numpy, scikit-learn (Ridge, StandardScaler), scipy.stats (ttest_1samp), the existing `reg_signal_hunt` module.

## Global Constraints

- Reuse from `scripts/fx_coint.reg_signal_hunt`: `build_freq_bars`, `build_panel`, `FEATURE_COLS` (["r_1","mom_short","mom_long","rvol_24","hour"]), `COST_BPS`, `bh_reject`. Do NOT duplicate these.
- Tight-cost majors (primary): EURUSD, GBPUSD, USDJPY. Secondary: USDCAD. Costs from `COST_BPS`.
- Horizons: `["2h", "3h"]` only.
- **No-look-ahead decile gating:** the selection threshold is `quantile(train_preds, q)` from each fold's TRAIN predictions, applied to that fold's TEST predictions. Never use test-set percentiles to gate.
- Walk-forward: expanding window, refit Ridge each fold, purge gap of 1 bar between train and test (next-bar target), StandardScaler fit on train only.
- Long-only is primary (`side="long"`); `side="short"` is a separate reported variant (for USDJPY 3h reversion). Never pool opposite signs.
- Go/no-go gate per cell: `mean_net_bps > 0` AND BH-significant (q=0.10) AND `pos_fold_pct >= 0.6`.
- Net return per trade = `actual_bps - cost_bps` (long) or `-actual_bps - cost_bps` (short).
- Run `make quality` before any push.

---

### Task 1: `walk_forward` — expanding-window per-fold Ridge predictions

**Files:**
- Create: `scripts/fx_coint/tail_wfo.py`
- Test: `tests/fx_coint/test_tail_wfo.py`

**Interfaces:**
- Consumes: `build_panel` output (DataFrame with `FEATURE_COLS` + `ret_next_bps`, `hour`).
- Produces: `walk_forward(panel: pd.DataFrame, n_folds: int = 5, min_train_frac: float = 0.5, purge: int = 1, alpha: float = 1.0) -> list[dict]`. Returns one dict per fold with keys `train_pred` (np.ndarray of train predictions), `test_pred`, `test_actual_bps`, `test_hour` (all np.ndarray). Expanding train: fold k trains on rows `[0 : split_k]`, tests on `[split_k + purge : split_{k+1}]`, where the test blocks evenly partition the rows after the initial `min_train_frac`. Ridge predicts `target_z`; `test_pred` is in z-units (gating is rank-based so units are fine). `test_actual_bps` is `ret_next_bps`.

- [ ] **Step 1: Write the failing test**

```python
# tests/fx_coint/test_tail_wfo.py
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import polars as pl

from scripts.fx_coint.reg_signal_hunt import build_freq_bars, build_panel
from scripts.fx_coint.tail_wfo import walk_forward


def _synthetic_1m(start, n, seed=0):
    ts = [start + timedelta(minutes=i) for i in range(n)]
    rng = np.random.default_rng(seed)
    steps = 1e-5 + rng.normal(0.0, 5e-5, n)
    mid = 1.10 + np.cumsum(steps)
    return pl.DataFrame({
        "bucket": ts, "mid": mid, "bid": mid - 5e-5, "ask": mid + 5e-5,
        "n_ticks": np.ones(n, dtype=np.int64), "flow_tick": np.zeros(n), "flow_ofi": np.zeros(n),
    })


def test_walk_forward_folds_expanding_and_oos():
    df = _synthetic_1m(datetime(2025, 1, 6, 7, 0), 1500 * 60)
    panel = build_panel(build_freq_bars(df, "2h", session=(0, 24)))
    folds = walk_forward(panel, n_folds=4, min_train_frac=0.5)
    assert len(folds) == 4
    # train grows across folds; every fold has non-empty test arrays of equal length
    prev_train = 0
    for f in folds:
        assert len(f["train_pred"]) > prev_train
        prev_train = len(f["train_pred"])
        assert len(f["test_pred"]) == len(f["test_actual_bps"]) == len(f["test_hour"]) > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/fx_coint/test_tail_wfo.py::test_walk_forward_folds_expanding_and_oos -v`
Expected: FAIL (`ModuleNotFoundError` / function not defined).

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/fx_coint/tail_wfo.py
"""Walk-forward confirmation of the PR #340 tail edge: long-only top-decile,
no-look-ahead decile gating, decile-level significance net of real cost.

Usage:
    uv run python scripts/fx_coint/tail_wfo.py --symbol all --freq all
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
from scipy.stats import ttest_1samp
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.fx_coint.reg_signal_hunt import (  # noqa: E402
    COST_BPS,
    FEATURE_COLS,
    bh_reject,
    build_freq_bars,
    build_panel,
)

TIGHT_MAJORS = ["EURUSD", "GBPUSD", "USDJPY"]
UNIVERSE = ["EURUSD", "GBPUSD", "USDJPY", "USDCAD"]
FREQS = ["2h", "3h"]


def walk_forward(
    panel: pd.DataFrame,
    n_folds: int = 5,
    min_train_frac: float = 0.5,
    purge: int = 1,
    alpha: float = 1.0,
) -> list[dict]:
    n = len(panel)
    start = int(n * min_train_frac)
    edges = np.linspace(start, n, n_folds + 1).astype(int)
    X = panel[FEATURE_COLS].to_numpy()
    yz = panel["target_z"].to_numpy()
    act = panel["ret_next_bps"].to_numpy()
    hour = panel["hour"].to_numpy()

    folds: list[dict] = []
    for k in range(n_folds):
        split = edges[k]
        test_lo, test_hi = edges[k] + purge, edges[k + 1]
        if test_hi - test_lo < 1 or split < 10:
            continue
        scaler = StandardScaler().fit(X[:split])
        model = Ridge(alpha=alpha).fit(scaler.transform(X[:split]), yz[:split])
        folds.append({
            "train_pred": model.predict(scaler.transform(X[:split])),
            "test_pred": model.predict(scaler.transform(X[test_lo:test_hi])),
            "test_actual_bps": act[test_lo:test_hi],
            "test_hour": hour[test_lo:test_hi],
        })
    return folds
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/fx_coint/test_tail_wfo.py::test_walk_forward_folds_expanding_and_oos -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/fx_coint/tail_wfo.py tests/fx_coint/test_tail_wfo.py
git commit -m "feat(fx_coint): walk_forward expanding-window per-fold predictions

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: `gate_trades` — no-look-ahead train-quantile trade selection

**Files:**
- Modify: `scripts/fx_coint/tail_wfo.py`
- Test: `tests/fx_coint/test_tail_wfo.py`

**Interfaces:**
- Consumes: the `folds` list from `walk_forward`.
- Produces: `gate_trades(folds: list[dict], q: float, cost_bps: float, side: str = "long") -> dict` with keys `net` (np.ndarray of per-trade net bps), `fold_id` (np.ndarray int), `hour` (np.ndarray), `n` (int). For each fold, threshold `thr = np.quantile(train_pred, q)`; **long** selects `test_pred >= thr` with `net = test_actual_bps - cost_bps`; **short** selects `test_pred <= np.quantile(train_pred, 1 - q)` with `net = -test_actual_bps - cost_bps`. Threshold ALWAYS from train_pred, never test.

- [ ] **Step 1: Write the failing test**

```python
def test_gate_trades_uses_train_threshold_long_and_short():
    from scripts.fx_coint.tail_wfo import gate_trades
    # one fold: train preds 0..99, q=0.9 -> thr ~ 89.1; test preds chosen around it
    train = np.arange(100.0)
    test_pred = np.array([50.0, 90.0, 95.0, 10.0])
    test_act = np.array([1.0, 2.0, 3.0, 4.0])
    test_hour = np.array([12, 13, 14, 15])
    folds = [{"train_pred": train, "test_pred": test_pred,
              "test_actual_bps": test_act, "test_hour": test_hour}]
    # long: thr=quantile(0..99,0.9)=89.1 -> selects test_pred 90,95 -> net = act - cost
    res = gate_trades(folds, q=0.9, cost_bps=0.5, side="long")
    assert res["n"] == 2
    assert np.allclose(sorted(res["net"]), sorted([2.0 - 0.5, 3.0 - 0.5]))
    assert set(res["hour"].tolist()) == {13, 14}
    # short: thr_low=quantile(0..99,0.1)=9.9 -> selects test_pred 10? (10>=9.9 false for <=) -> none<=9.9
    res_s = gate_trades(folds, q=0.9, cost_bps=0.5, side="short")
    assert res_s["n"] == 0
    # widen: q=0.85 -> thr_low=quantile(.,0.15)=14.85 -> selects 10.0 -> net = -act - cost
    res_s2 = gate_trades(folds, q=0.85, cost_bps=0.5, side="short")
    assert res_s2["n"] == 1
    assert np.allclose(res_s2["net"], [-4.0 - 0.5])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/fx_coint/test_tail_wfo.py::test_gate_trades_uses_train_threshold_long_and_short -v`
Expected: FAIL (`gate_trades` not defined).

- [ ] **Step 3: Write minimal implementation**

```python
def gate_trades(folds: list[dict], q: float, cost_bps: float, side: str = "long") -> dict:
    nets: list[np.ndarray] = []
    fids: list[np.ndarray] = []
    hours: list[np.ndarray] = []
    for i, f in enumerate(folds):
        tp = f["test_pred"]
        if side == "long":
            thr = np.quantile(f["train_pred"], q)
            sel = tp >= thr
            net = f["test_actual_bps"][sel] - cost_bps
        elif side == "short":
            thr = np.quantile(f["train_pred"], 1.0 - q)
            sel = tp <= thr
            net = -f["test_actual_bps"][sel] - cost_bps
        else:
            raise ValueError(f"side must be 'long' or 'short', got {side!r}")
        if sel.any():
            nets.append(net)
            fids.append(np.full(int(sel.sum()), i))
            hours.append(f["test_hour"][sel])
    if not nets:
        return {"net": np.array([]), "fold_id": np.array([], int), "hour": np.array([]), "n": 0}
    net_all = np.concatenate(nets)
    return {
        "net": net_all,
        "fold_id": np.concatenate(fids),
        "hour": np.concatenate(hours),
        "n": len(net_all),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/fx_coint/test_tail_wfo.py::test_gate_trades_uses_train_threshold_long_and_short -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(fx_coint): gate_trades with no-look-ahead train-quantile selection

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: `cell_stats` — significance + per-fold robustness

**Files:**
- Modify: `scripts/fx_coint/tail_wfo.py`
- Test: `tests/fx_coint/test_tail_wfo.py`

**Interfaces:**
- Consumes: `gate_trades` output (`net`, `fold_id`).
- Produces: `cell_stats(net: np.ndarray, fold_id: np.ndarray) -> dict` with keys `n`, `mean_net_bps`, `t_stat`, `p_value` (two-sided one-sample t-test vs 0; nan if n<3), `pos_fold_pct` (fraction of distinct folds whose mean net > 0; nan if no folds), `hit_rate` (fraction of trades with net > 0), `total_net_bps`.

- [ ] **Step 1: Write the failing test**

```python
def test_cell_stats_known_arrays():
    from scripts.fx_coint.tail_wfo import cell_stats
    # 2 folds: fold 0 all positive, fold 1 mostly negative
    net = np.array([1.0, 2.0, 1.5, -1.0, -0.5, -2.0])
    fid = np.array([0, 0, 0, 1, 1, 1])
    s = cell_stats(net, fid)
    assert s["n"] == 6
    assert abs(s["mean_net_bps"] - net.mean()) < 1e-9
    assert abs(s["total_net_bps"] - net.sum()) < 1e-9
    assert s["pos_fold_pct"] == 0.5  # fold 0 positive, fold 1 negative
    assert abs(s["hit_rate"] - 3 / 6) < 1e-9
    assert np.isfinite(s["t_stat"]) and np.isfinite(s["p_value"])
    # n<3 -> nan stats guard
    s2 = cell_stats(np.array([1.0, 2.0]), np.array([0, 0]))
    assert np.isnan(s2["t_stat"]) and np.isnan(s2["p_value"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/fx_coint/test_tail_wfo.py::test_cell_stats_known_arrays -v`
Expected: FAIL (`cell_stats` not defined).

- [ ] **Step 3: Write minimal implementation**

```python
def cell_stats(net: np.ndarray, fold_id: np.ndarray) -> dict:
    net = np.asarray(net, float)
    n = len(net)
    if n == 0:
        return {"n": 0, "mean_net_bps": float("nan"), "t_stat": float("nan"),
                "p_value": float("nan"), "pos_fold_pct": float("nan"),
                "hit_rate": float("nan"), "total_net_bps": 0.0}
    if n >= 3:
        tt = ttest_1samp(net, 0.0)
        t_stat, p_value = float(tt.statistic), float(tt.pvalue)
    else:
        t_stat = p_value = float("nan")
    folds = np.unique(fold_id)
    if len(folds) > 0:
        pos = np.mean([net[fold_id == fk].mean() > 0 for fk in folds])
    else:
        pos = float("nan")
    return {
        "n": n,
        "mean_net_bps": float(net.mean()),
        "t_stat": t_stat,
        "p_value": p_value,
        "pos_fold_pct": float(pos),
        "hit_rate": float((net > 0).mean()),
        "total_net_bps": float(net.sum()),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/fx_coint/test_tail_wfo.py::test_cell_stats_known_arrays -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(fx_coint): cell_stats significance + per-fold robustness

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: Orchestrator — `run_cell_wfo`, BH-FDR, q-sensitivity, CLI

**Files:**
- Modify: `scripts/fx_coint/tail_wfo.py`
- Test: `tests/fx_coint/test_tail_wfo.py`

**Interfaces:**
- Consumes: all prior functions.
- Produces:
  - `run_cell_wfo(sym: str, freq: str, side: str = "long", q: float = 0.9, n_folds: int = 5) -> dict | None` — loads `_REPO_ROOT/"data/tick_bars/{sym}_1m_flow.parquet"`, builds panel, runs `walk_forward` + `gate_trades` + `cell_stats`; returns a flat row `{symbol, freq, side, q, n, mean_net_bps, t_stat, p_value, pos_fold_pct, hit_rate, total_net_bps}` or `None` if data missing / panel < 200.
  - `main()` — argparse `--symbol` (UNIVERSE or `all`), `--freq` (FREQS or `all`), `--q` (default 0.9). Runs long-only over the requested universe at the chosen q, applies `bh_reject` across the cells, prints a verdict table with a `BHsig` and `GO` column (`GO = mean_net_bps>0 and BHsig and pos_fold_pct>=0.6`). Then prints a q-sensitivity block (q in [0.8, 0.9, 0.95]) of `mean_net_bps` per cell, and a USDJPY-3h short-side line.

- [ ] **Step 1: Write the failing test**

```python
def test_run_cell_wfo_on_synthetic(tmp_path, monkeypatch):
    import scripts.fx_coint.tail_wfo as tw
    df = _synthetic_1m(datetime(2025, 1, 6, 7, 0), 3000 * 60)
    d = tmp_path / "data" / "tick_bars"
    d.mkdir(parents=True)
    df.write_parquet(d / "EURUSD_1m_flow.parquet")
    monkeypatch.setattr(tw, "_REPO_ROOT", tmp_path)
    row = tw.run_cell_wfo("EURUSD", "2h", side="long", q=0.9, n_folds=4)
    assert row is not None
    assert row["symbol"] == "EURUSD" and row["freq"] == "2h" and row["side"] == "long"
    for k in ["n", "mean_net_bps", "t_stat", "p_value", "pos_fold_pct", "hit_rate"]:
        assert k in row
    assert row["n"] > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/fx_coint/test_tail_wfo.py::test_run_cell_wfo_on_synthetic -v`
Expected: FAIL (`run_cell_wfo` not defined).

- [ ] **Step 3: Write minimal implementation**

```python
def run_cell_wfo(
    sym: str, freq: str, side: str = "long", q: float = 0.9, n_folds: int = 5
) -> dict | None:
    src = _REPO_ROOT / f"data/tick_bars/{sym}_1m_flow.parquet"
    if not src.exists():
        return None
    panel = build_panel(build_freq_bars(pl.read_parquet(src), freq))
    if len(panel) < 200:
        return None
    cost = COST_BPS[sym]
    folds = walk_forward(panel, n_folds=n_folds)
    trades = gate_trades(folds, q=q, cost_bps=cost, side=side)
    s = cell_stats(trades["net"], trades["fold_id"])
    return {"symbol": sym, "freq": freq, "side": side, "q": q, **s}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="all", choices=UNIVERSE + ["all"])
    ap.add_argument("--freq", default="all", choices=FREQS + ["all"])
    ap.add_argument("--q", type=float, default=0.9)
    args = ap.parse_args()
    syms = UNIVERSE if args.symbol == "all" else [args.symbol]
    freqs = FREQS if args.freq == "all" else [args.freq]

    rows = [r for s in syms for f in freqs
            if (r := run_cell_wfo(s, f, side="long", q=args.q)) is not None]
    if not rows:
        print("No cells produced (missing data?).")
        return
    rej = bh_reject([r["p_value"] for r in rows], q=0.10)
    hdr = (f"{'pair':>7} {'freq':>4} {'q':>4} {'n':>5} {'meanNet':>8} {'t':>6} "
           f"{'posFold':>7} {'hit':>5} {'totNet':>8} {'BH':>3} {'GO':>3}")
    print(hdr)
    print("-" * len(hdr))
    for r, sig in zip(rows, rej):
        go = bool(r["mean_net_bps"] > 0 and sig and r["pos_fold_pct"] >= 0.6)
        print(f"{r['symbol']:>7} {r['freq']:>4} {r['q']:>4.2f} {r['n']:>5} "
              f"{r['mean_net_bps']:>+8.3f} {r['t_stat']:>+6.2f} {r['pos_fold_pct']:>7.2f} "
              f"{r['hit_rate']*100:>4.0f}% {r['total_net_bps']:>+8.1f} "
              f"{str(sig):>3} {str(go):>3}")

    print("\nq-sensitivity (mean net bps, long-only):")
    print(f"{'pair':>7} {'freq':>4} {'q0.80':>7} {'q0.90':>7} {'q0.95':>7}")
    for s in syms:
        for f in freqs:
            vals = []
            for qq in (0.80, 0.90, 0.95):
                rr = run_cell_wfo(s, f, side="long", q=qq)
                vals.append(rr["mean_net_bps"] if rr else float("nan"))
            print(f"{s:>7} {f:>4} {vals[0]:>+7.3f} {vals[1]:>+7.3f} {vals[2]:>+7.3f}")

    jpy = run_cell_wfo("USDJPY", "3h", side="short", q=0.9)
    if jpy:
        print(f"\nUSDJPY 3h SHORT-side: n={jpy['n']} meanNet={jpy['mean_net_bps']:+.3f} "
              f"t={jpy['t_stat']:+.2f} posFold={jpy['pos_fold_pct']:.2f} hit={jpy['hit_rate']*100:.0f}%")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests + quality**

Run: `uv run pytest tests/fx_coint/test_tail_wfo.py -v`
Expected: all PASS.
Run: `make quality`
Expected: ty + ruff clean for the new files (fix any new lint).

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(fx_coint): tail-WFO orchestrator, BH-FDR, q-sensitivity, CLI

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: Run the confirmation and record the verdict

**Files:**
- Create: `scripts/fx_coint/tail_wfo_results.md`

- [ ] **Step 1: Run the WFO**

Run: `uv run python scripts/fx_coint/tail_wfo.py --symbol all --freq all`
Capture the verdict table, q-sensitivity block, and USDJPY-3h short line.

- [ ] **Step 2: Record verdict**

Write `scripts/fx_coint/tail_wfo_results.md`: per cell, mean net bps / t / p / pos_fold_pct / hit / BH / GO. Apply the gate (`mean_net_bps>0 AND BH-sig AND pos_fold_pct>=0.6`). State which cells CONFIRM and the overall GO/NO-GO. Interpret q-sensitivity: is net monotone increasing in q (more conviction → more net, the signature of a real tail edge) or flat/noisy? Note whether the #340 single-split result survived walk-forward, and whether USDJPY 3h short confirms its reversion. If confirmed, next step = tick-exact fill verification; if not, decompose (did it die on significance, per-fold instability, or did the no-look-ahead train threshold erase the in-sample tail edge?).

- [ ] **Step 3: Commit**

```bash
git add scripts/fx_coint/tail_wfo_results.md
git commit -m "docs(fx_coint): tail-edge walk-forward confirmation results + verdict

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:**
- No-look-ahead train-quantile gating → Task 2 (`gate_trades`, threshold from `train_pred`). ✓
- Walk-forward expanding, refit per fold, purge, train-only scaler → Task 1. ✓
- Long-only primary + short variant (USDJPY 3h) → Task 2 (`side`), Task 4 (short line). ✓
- Universe (tight majors + USDCAD), 2h/3h → Global Constraints, Task 4 (`UNIVERSE`/`FREQS`). ✓
- Per-trade significance + pos_fold_pct + hit + total → Task 3. ✓
- BH-FDR across cells → Task 4. ✓
- Go/no-go gate (mean>0 AND BH AND pos_fold>=0.6) → Task 4 (`GO` column), Task 5 (applied). ✓
- q-sensitivity (0.8/0.9/0.95) → Task 4, interpreted Task 5. ✓
- Results doc + verdict → Task 5. ✓
- Out-of-scope (richer models, pooling, tick-exact, sizing) correctly omitted. ✓

**Placeholder scan:** No TBD/TODO; every code step has complete code. ✓

**Type consistency:** fold dict keys (`train_pred`/`test_pred`/`test_actual_bps`/`test_hour`) consistent across Tasks 1→2; `gate_trades` output keys (`net`/`fold_id`/`hour`/`n`) consumed by Task 3/4; `cell_stats` keys spread into the row in Task 4 and printed consistently. `_REPO_ROOT` is a module attribute (monkeypatched in Task 4 test), matching the reg_signal_hunt pattern. ✓
