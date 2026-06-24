# Two-Track Edge-Based Feature Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a feature search whose objective is edge (walk-forward non-overlap net bps over a fixed base), via two prediction tracks (direction, magnitude) plus a conditioning/interaction lens — no modelling.

**Architecture:** A cheap Stage-1 screen (`edge_feature_search.py`) ranks each of the ~25 tick-native features by an edge-leaning statistic per role: |return|-weighted directional IC, magnitude IC vs |return|, and tercile net-bps spread of the base P&L. Survivors are confirmed in Stage 2 by marginal net-bps lift over the fixed base on the existing walk-forward non-overlap harness (extended in `pnl_walkforward.py`). A report module emits tables + plots.

**Tech Stack:** Python, numpy, pandas, scipy.stats, matplotlib (Agg). Reuses `feature_ic_definitive.build_all`, `triple_barrier.triple_barrier_core`, `pnl_walkforward`. Tests via pytest, run from repo root, imported as `from scripts.fx_coint.X import Y`.

## Global Constraints

- New code in `scripts/fx_coint/`; tests in `tests/fx_coint/` named `test_*.py`; reports in `reports/edge_feature_search/`.
- Modules follow existing convention: pure functions + a thin `main()` under `if __name__ == "__main__":`. Intra-package imports use `sys.path.insert(0, parent)` + bare module names (e.g. `from feature_ic_definitive import build_all`).
- **No modelling** — every feature/base combination is a simple non-fit rule (ranking, agreement-veto, tercile restriction). This produces feature assessments only.
- Fixed base strategy: fade `ffd_zvol20` (direction `-sign(ffd_zvol20)`) × top-decile `|ffd_zvol20|` selection; triple-barrier target, barriers `1.0 * vol * sqrt(N)`; pooled 5 ex-JPY majors `["AUDUSD","EURUSD","GBPUSD","USDCAD","USDCHF"]`; cost 1.0 bps round-trip; N=50 primary, N=30 secondary.
- Conditioning value judged in **net-bps, not IC** (the session's central lesson).
- A feature is an "edge feature" only if it clears **both** the Stage-1 screen and the Stage-2 net-bps confirm in at least one role (multiplicity guard).
- Per-bar `vol` and feature dicts come from `build_all(sym) -> (logp, f, vol, bph)`. First-touch return uses `entry = ev + 1`, `vert = min(entry + N, n-1)`.
- `run make quality` (ruff + ty + ...) before any PR, not just pytest.

---

### Task 1: Stage-1 screen scorers — weighted directional IC + magnitude IC

**Files:**
- Create: `scripts/fx_coint/edge_feature_search.py`
- Test: `tests/fx_coint/test_edge_feature_search.py`

**Interfaces:**
- Consumes: nothing (first task).
- Produces:
  - `weighted_directional_ic(feat: np.ndarray, ret: np.ndarray) -> float` — weighted rank correlation of `feat` vs `ret`, event weights ∝ `|ret|` (emphasises big-money events). NaN-safe (drops non-finite pairs).
  - `magnitude_ic(feat: np.ndarray, ret: np.ndarray) -> float` — Spearman IC of `feat` vs `|ret|`. NaN-safe.

- [ ] **Step 1: Write the failing tests**

```python
# tests/fx_coint/test_edge_feature_search.py
import numpy as np
from scipy import stats

from scripts.fx_coint.edge_feature_search import magnitude_ic, weighted_directional_ic


def test_weighted_directional_ic_emphasises_big_moves():
    rng = np.random.default_rng(0)
    n = 4000
    ret = rng.standard_normal(n)
    big = np.abs(ret) > 1.0
    # feature agrees with return sign on BIG moves, disagrees on small ones
    feat = np.where(big, np.sign(ret), -np.sign(ret)) + 0.1 * rng.standard_normal(n)
    wic = weighted_directional_ic(feat, ret)
    plain = stats.spearmanr(feat, ret)[0]
    assert wic > 0.2                 # big-move-weighted -> clearly positive
    assert wic > plain               # weighting beats the unweighted view


def test_weighted_directional_ic_nan_safe():
    feat = np.array([1.0, 2.0, np.nan, 4.0, 5.0])
    ret = np.array([0.5, np.nan, 3.0, -1.0, 2.0])
    assert np.isfinite(weighted_directional_ic(feat, ret))


def test_magnitude_ic_detects_size_then_noise():
    rng = np.random.default_rng(1)
    ret = rng.standard_normal(3000)
    feat = np.abs(ret) + 0.1 * rng.standard_normal(3000)
    assert magnitude_ic(feat, ret) > 0.5
    noise = rng.standard_normal(3000)
    assert abs(magnitude_ic(noise, ret)) < 0.1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/fx_coint/test_edge_feature_search.py -v`
Expected: FAIL with `ModuleNotFoundError` / `ImportError`.

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/fx_coint/edge_feature_search.py
"""Two-track edge-based feature search (Stage 1 screen).

Replaces IC as the search objective with edge-leaning statistics, after this
project established that IC robustness != tradeable P&L. Per role:
  direction : |return|-weighted directional IC (emphasises big-money events)
  magnitude : IC of feature vs |return| (rank move size -> select cost-clearers)
  condition : tercile net-bps spread of the base fade P&L (interaction value)
Survivors are confirmed by marginal net-bps lift in pnl_walkforward (Stage 2).

No modelling: all combinations are simple non-fit rules.

Usage: uv run python scripts/fx_coint/edge_feature_search.py
"""
from __future__ import annotations

import numpy as np
from scipy import stats


def _finite_pair(a, b):
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    ok = np.isfinite(a) & np.isfinite(b)
    return a[ok], b[ok]


def weighted_directional_ic(feat: np.ndarray, ret: np.ndarray) -> float:
    """Weighted rank correlation of feat vs ret, weights ∝ |ret|.

    Uses weighted Pearson correlation of the rank-transformed series, so large
    moves (which dominate P&L) dominate the statistic. Returns 0.0 if degenerate.
    """
    f, r = _finite_pair(feat, ret)
    if f.size < 10:
        return 0.0
    w = np.abs(r)
    if w.sum() == 0:
        return 0.0
    fr = stats.rankdata(f)
    rr = stats.rankdata(r)

    def wmean(x):
        return np.sum(w * x) / np.sum(w)

    fm, rm = wmean(fr), wmean(rr)
    cov = wmean((fr - fm) * (rr - rm))
    vf = wmean((fr - fm) ** 2)
    vr = wmean((rr - rm) ** 2)
    den = np.sqrt(vf * vr)
    return float(cov / den) if den > 0 else 0.0


def magnitude_ic(feat: np.ndarray, ret: np.ndarray) -> float:
    """Spearman IC of feat vs |ret| — does the feature rank move size?"""
    f, r = _finite_pair(feat, ret)
    if f.size < 10 or np.unique(f).size < 3:
        return 0.0
    return float(stats.spearmanr(f, np.abs(r))[0])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/fx_coint/test_edge_feature_search.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/fx_coint/edge_feature_search.py tests/fx_coint/test_edge_feature_search.py
git commit -m "feat(fx_coint): edge search Stage-1 scorers (weighted dir IC + magnitude IC)"
```

---

### Task 2: Stage-1 conditioning scorer — tercile net-bps spread

**Files:**
- Modify: `scripts/fx_coint/edge_feature_search.py`
- Test: `tests/fx_coint/test_edge_feature_search.py` (add tests)

**Interfaces:**
- Consumes: nothing new.
- Produces:
  - `tercile_netbps_spread(base_pnl: np.ndarray, gate: np.ndarray) -> dict` → keys `unc` (unconditional mean base P&L), `t_means` (list of 3 tercile means, low→high gate), `best_lift` (max tercile mean − `unc`), `best_tercile` (0/1/2). Cost cancels in the spread, so this runs on the base fade P&L directly. NaN-safe.

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/fx_coint/test_edge_feature_search.py
from scripts.fx_coint.edge_feature_search import tercile_netbps_spread


def test_tercile_netbps_spread_finds_conditioning():
    rng = np.random.default_rng(2)
    n = 6000
    gate = rng.standard_normal(n)
    base_pnl = 2.0 * gate + rng.standard_normal(n)     # high gate -> high P&L
    out = tercile_netbps_spread(base_pnl, gate)
    assert out["best_tercile"] == 2                    # top gate tercile is best
    assert out["best_lift"] > 0.5
    assert len(out["t_means"]) == 3


def test_tercile_netbps_spread_null_gate_small_lift():
    rng = np.random.default_rng(3)
    n = 6000
    base_pnl = rng.standard_normal(n)
    gate = rng.standard_normal(n)                      # independent of P&L
    out = tercile_netbps_spread(base_pnl, gate)
    assert out["best_lift"] < 0.15
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/fx_coint/test_edge_feature_search.py -k tercile -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Write minimal implementation**

```python
# add to scripts/fx_coint/edge_feature_search.py
def tercile_netbps_spread(base_pnl: np.ndarray, gate: np.ndarray) -> dict:
    """Net-bps spread of base P&L across terciles of `gate`. Judged in net-bps
    (cost cancels in the spread), not IC — the project's central lesson."""
    p = np.asarray(base_pnl, dtype=float)
    g = np.asarray(gate, dtype=float)
    ok = np.isfinite(p) & np.isfinite(g)
    p, g = p[ok], g[ok]
    if p.size < 30:
        return {"unc": float("nan"), "t_means": [float("nan")] * 3,
                "best_lift": float("nan"), "best_tercile": -1}
    unc = float(p.mean())
    q1, q2 = np.quantile(g, [1 / 3, 2 / 3])
    masks = [g <= q1, (g > q1) & (g <= q2), g > q2]
    t_means = [float(p[m].mean()) if m.sum() > 10 else float("nan") for m in masks]
    lifts = [tm - unc for tm in t_means]
    best = int(np.nanargmax(lifts))
    return {"unc": unc, "t_means": t_means,
            "best_lift": float(lifts[best]), "best_tercile": best}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/fx_coint/test_edge_feature_search.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/fx_coint/edge_feature_search.py tests/fx_coint/test_edge_feature_search.py
git commit -m "feat(fx_coint): edge search conditioning scorer (tercile net-bps spread)"
```

---

### Task 3: Stage-1 orchestration — base P&L builder + per-feature screen table

**Files:**
- Modify: `scripts/fx_coint/edge_feature_search.py`
- Test: `tests/fx_coint/test_edge_feature_search.py` (add tests)

**Interfaces:**
- Consumes: `weighted_directional_ic`, `magnitude_ic`, `tercile_netbps_spread` (Tasks 1-2); `build_all` from `feature_ic_definitive`; `triple_barrier_core` from `triple_barrier`.
- Produces:
  - `base_fade_pnl(logp, vol, ev, n_tb) -> np.ndarray` → per-event gross fade P&L in bps: `-sign(ffd_zvol20)` is applied by the caller; this returns the first-touch return `(logp[t1]-logp[entry])*1e4` so the caller forms `-sign(signal)*ret`. Signature: `base_fade_pnl(logp: np.ndarray, vol: np.ndarray, ev: np.ndarray, n_tb: int) -> np.ndarray` returning `ret_bps` aligned to `ev`.
  - `screen(n_grid=(30, 50)) -> pandas.DataFrame` → one row per (feature, N) with columns `feature, N, dir_wic, mag_ic, cond_lift, cond_tercile, sign_dir` (per-symbol sign agreement k/5 on `dir_wic`). Loads the 5 majors via `build_all`, samples 40000 events/symbol (seed 0), pools.
  - `main()` — runs `screen`, prints ranked tables per role, writes `reports/edge_feature_search/screen.csv`.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/fx_coint/test_edge_feature_search.py
from scripts.fx_coint.edge_feature_search import base_fade_pnl


def test_base_fade_pnl_matches_first_touch_return():
    # monotone uptrend: first-touch return from entry is positive
    logp = np.log(np.linspace(100, 110, 80))
    vol = np.full(80, 0.001)
    ev = np.array([0, 10, 20])
    ret = base_fade_pnl(logp, vol, ev, n_tb=30)
    assert ret.shape == (3,)
    assert np.all(ret > 0)             # uptrend -> positive forward move in bps
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/fx_coint/test_edge_feature_search.py -k base_fade -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Write minimal implementation**

```python
# add to scripts/fx_coint/edge_feature_search.py (imports at top of file)
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from feature_ic_definitive import build_all  # noqa: E402
from triple_barrier import triple_barrier_core  # noqa: E402

POOL = ["AUDUSD", "EURUSD", "GBPUSD", "USDCAD", "USDCHF"]
N_EVENTS = 40000
BASE = "ffd_0.1"          # ffd control kept for reference
SELECTOR = "ffd_zvol20"   # the fixed-base signal (direction + magnitude)
OUT_DIR = Path("reports/edge_feature_search")


def base_fade_pnl(logp, vol, ev, n_tb):
    entry = ev + 1
    vert = np.minimum(entry + n_tb, len(logp) - 1)
    _, ret, _, _ = triple_barrier_core(logp, entry, vert, 1.0 * vol[entry] * np.sqrt(n_tb))
    return ret


def screen(n_grid=(30, 50)) -> pd.DataFrame:
    rng = np.random.default_rng(0)
    cache = {s: build_all(s) for s in POOL}
    evset = {}
    for s in POOL:
        logp, f, vol, bph = cache[s]
        n = len(logp)
        warm = int(96 * bph) + 60
        idx = np.arange(warm, n - max(n_grid) - 3)
        idx = idx[np.isfinite(vol[idx + 1]) & (vol[idx + 1] > 0)]
        evset[s] = np.sort(rng.choice(idx, min(N_EVENTS, len(idx)), replace=False))
    feats = [k for k in cache[POOL[0]][1] if k != SELECTOR]
    rows = []
    for n_tb in n_grid:
        # per-symbol arrays
        per = {}
        for s in POOL:
            logp, f, vol, bph = cache[s]
            ev = evset[s]
            ret = base_fade_pnl(logp, vol, ev, n_tb)
            base_pnl = -np.sign(f[SELECTOR][ev]) * ret      # fade the deviation
            per[s] = (f, ev, ret, base_pnl)
        for fn in feats:
            wics, migs, lifts, terc = [], [], [], []
            for s in POOL:
                f, ev, ret, base_pnl = per[s]
                x = f[fn][ev]
                wics.append(weighted_directional_ic(x, ret))
                migs.append(magnitude_ic(x, ret))
                cs = tercile_netbps_spread(base_pnl, x)
                lifts.append(cs["best_lift"])
                terc.append(cs["best_tercile"])
            wics = np.array(wics)
            rows.append(dict(
                feature=fn, N=n_tb,
                dir_wic=float(np.nanmean(wics)),
                mag_ic=float(np.nanmean(migs)),
                cond_lift=float(np.nanmean(lifts)),
                cond_tercile=int(np.round(np.nanmean(terc))),
                sign_dir=int((np.sign(wics) == np.sign(np.nanmean(wics))).sum())))
    return pd.DataFrame(rows)


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    res = screen()
    res.to_csv(OUT_DIR / "screen.csv", index=False)
    pd.set_option("display.width", 200, "display.float_format", lambda x: f"{x:8.4f}")
    for role, col in [("DIRECTION (|ret|-weighted IC)", "dir_wic"),
                      ("MAGNITUDE (IC vs |ret|)", "mag_ic"),
                      ("CONDITIONING (tercile net-bps lift)", "cond_lift")]:
        print(f"\n=== {role} — top by |{col}| ===")
        for n_tb in sorted(res.N.unique()):
            d = res[res.N == n_tb].copy()
            d = d.reindex(d[col].abs().sort_values(ascending=False).index).head(8)
            print(f"-- N={n_tb} --")
            print(d[["feature", col, "sign_dir"]].to_string(index=False))
    print(f"\nscreen -> {OUT_DIR / 'screen.csv'}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/fx_coint/test_edge_feature_search.py -v`
Expected: PASS (all edge_feature_search tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/fx_coint/edge_feature_search.py tests/fx_coint/test_edge_feature_search.py
git commit -m "feat(fx_coint): edge search Stage-1 orchestration (base P&L + 3-role screen)"
```

---

### Task 4: Stage-2 confirm — marginal net-bps lift over the base (walk-forward non-overlap)

**Files:**
- Modify: `scripts/fx_coint/pnl_walkforward.py` (expose `greedy_nonoverlap`; add `marginal_lift`)
- Test: `tests/fx_coint/test_pnl_walkforward.py` (create)

**Interfaces:**
- Consumes: `build_all`, `triple_barrier_core`; the existing `_greedy_nonoverlap` logic.
- Produces:
  - `greedy_nonoverlap(entry: np.ndarray, t1: np.ndarray) -> np.ndarray` — public rename of the existing `_greedy_nonoverlap` (boolean keep-mask; keep trade if `entry >= last kept t1`).
  - `marginal_lift(cache, evset, n_tb, feature, role, cost=1.0, n_folds=5) -> dict` → keys `base_net`, `cand_net`, `lift` (= `cand_net - base_net`), `folds_pos`, `n_trades`; walk-forward (expanding), non-overlapping, pooled 5 majors. `role` ∈ `{"magnitude","direction","conditioner"}`:
    - `magnitude`: select top-decile by avg-rank of (`feature`, `|ffd_zvol20|`) instead of `|ffd_zvol20|` alone.
    - `direction`: base selection, but keep only trades where `sign(feature)` agrees with the fade direction `-sign(ffd_zvol20)`.
    - `conditioner`: base selection, restrict to the `feature` tercile with best train net-bps.

- [ ] **Step 1: Write the failing tests**

```python
# tests/fx_coint/test_pnl_walkforward.py
import numpy as np

from scripts.fx_coint.pnl_walkforward import greedy_nonoverlap


def test_greedy_nonoverlap_excludes_overlapping_holds():
    entry = np.array([0, 1, 5, 6, 12])
    t1 = np.array([4, 5, 9, 10, 14])     # each trade exits at t1
    keep = greedy_nonoverlap(entry, t1)
    # 0 kept (exit 4); 1 starts at 1<4 skip; 5>=4 keep (exit 9); 6<9 skip; 12>=9 keep
    assert keep.tolist() == [True, False, True, False, True]


def test_greedy_nonoverlap_all_disjoint_kept():
    entry = np.array([0, 10, 20])
    t1 = np.array([5, 15, 25])
    assert greedy_nonoverlap(entry, t1).all()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/fx_coint/test_pnl_walkforward.py -v`
Expected: FAIL with `ImportError` (function is currently `_greedy_nonoverlap`).

- [ ] **Step 3: Write minimal implementation**

In `scripts/fx_coint/pnl_walkforward.py`, rename `_greedy_nonoverlap` to `greedy_nonoverlap` (update its call site in `main`), then add:

```python
# add to scripts/fx_coint/pnl_walkforward.py
SELECTOR = "ffd_zvol20"


def _fade_pnl(logp, vol, ev, n_tb):
    entry = ev + 1
    t1, ret, _, _ = triple_barrier_core(
        logp, entry, np.minimum(entry + n_tb, len(logp) - 1),
        1.0 * vol[entry] * np.sqrt(n_tb))
    return entry, t1, ret


def _rank(a):
    from scipy.stats import rankdata
    out = np.full(len(a), np.nan)
    ok = np.isfinite(a)
    out[ok] = rankdata(a[ok]) / ok.sum()
    return out


def marginal_lift(cache, evset, n_tb, feature, role, cost=1.0, n_folds=5) -> dict:
    """Walk-forward non-overlap net-bps lift of `feature` (in `role`) over the
    fixed base (fade ffd_zvol20 x top-decile |ffd_zvol20|)."""
    sym_d = {}
    for s in POOL:
        logp, f, vol, bph = cache[s]
        ev = evset[s]
        entry, t1, ret = _fade_pnl(logp, vol, ev, n_tb)
        pnl = -np.sign(f[SELECTOR][ev]) * ret
        sym_d[s] = dict(entry=entry, t1=t1, pnl=pnl,
                        sel=f[SELECTOR][ev], feat=f[feature][ev])
    all_entry = np.concatenate([sym_d[s]["entry"] for s in POOL])
    edges = np.quantile(all_entry, np.linspace(0, 1, n_folds + 1))

    def fold_net(select_fn):
        nets = []
        for k in range(1, n_folds):
            lo, hi = edges[k], edges[k + 1]
            fold = []
            for s in POOL:
                d = sym_d[s]
                tr = d["entry"] < lo
                te = (d["entry"] >= lo) & (d["entry"] < hi)
                if tr.sum() < 200 or te.sum() < 20:
                    continue
                sel = select_fn(d, tr, te)
                order = np.argsort(d["entry"][sel])
                ko = greedy_nonoverlap(d["entry"][sel][order], d["t1"][sel][order])
                p = d["pnl"][sel][order][ko] - cost
                if len(p):
                    fold.append(p)
            if fold:
                nets.append(np.mean(np.concatenate(fold)))
        return np.array(nets)

    def base_select(d, tr, te):
        thr = np.nanquantile(np.abs(d["sel"][tr]), 0.90)
        return te & (np.abs(d["sel"]) >= thr) & np.isfinite(d["pnl"])

    def cand_select(d, tr, te):
        base = base_select(d, tr, te)
        if role == "magnitude":
            thr = np.nanquantile(
                (_rank(np.abs(d["sel"])) + _rank(np.abs(d["feat"]))) / 2, 0.90)
            comb = (_rank(np.abs(d["sel"])) + _rank(np.abs(d["feat"]))) / 2
            return te & (comb >= thr) & np.isfinite(d["pnl"])
        if role == "direction":
            fade_dir = -np.sign(d["sel"])
            return base & (np.sign(d["feat"]) == fade_dir)
        # conditioner: restrict to best-train-net-bps tercile of feature
        q1, q2 = np.nanquantile(d["feat"][tr], [1 / 3, 2 / 3])
        terc_masks = [d["feat"] <= q1, (d["feat"] > q1) & (d["feat"] <= q2), d["feat"] > q2]
        # pick tercile by train net-bps
        best, best_net = 0, -1e9
        btr = base_select(d, tr, tr)
        for ti, m in enumerate(terc_masks):
            mm = btr & m
            if mm.sum() > 20:
                net = np.nanmean(d["pnl"][mm]) - cost
                if net > best_net:
                    best, best_net = ti, net
        return base & terc_masks[best]

    base_net = fold_net(base_select)
    cand_net = fold_net(cand_select)
    return dict(base_net=float(np.mean(base_net)) if len(base_net) else float("nan"),
                cand_net=float(np.mean(cand_net)) if len(cand_net) else float("nan"),
                lift=float(np.mean(cand_net) - np.mean(base_net)) if len(cand_net) and len(base_net) else float("nan"),
                folds_pos=int((cand_net > 0).sum()),
                n_trades=int(len(cand_net)))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/fx_coint/test_pnl_walkforward.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/fx_coint/pnl_walkforward.py tests/fx_coint/test_pnl_walkforward.py
git commit -m "feat(fx_coint): edge search Stage-2 marginal-lift confirm (3 role rules)"
```

---

### Task 5: Confirm driver + report (screen survivors → net-bps lift → plots + markdown)

**Files:**
- Modify: `scripts/fx_coint/edge_feature_search.py` (add `confirm` + report to `main`)
- Test: `tests/fx_coint/test_edge_feature_search.py` (add a survivor-selection test)

**Interfaces:**
- Consumes: `screen` (Task 3); `marginal_lift`, and `build_all`/`evset` construction (Task 4).
- Produces:
  - `survivors(screen_df, top_k=5) -> dict` → `{"direction": [...], "magnitude": [...], "conditioner": [...]}`, the top-`top_k` features per role at N=50 by the role's screen column (`dir_wic`, `mag_ic`, `cond_lift`), requiring `sign_dir >= 4` for the direction role.
  - `main()` extended: run `screen`, pick `survivors`, run `marginal_lift` for each (feature, role) at N=50 and N=30, write `reports/edge_feature_search/confirm.csv`, a `net_lift.png` bar plot (lift per surviving feature, grouped by role), and `REPORT.md` summarising screen + confirm with the no-modelling boundary and the planned HistGBM-under-P&L next phase noted.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/fx_coint/test_edge_feature_search.py
import pandas as pd

from scripts.fx_coint.edge_feature_search import survivors


def test_survivors_picks_top_per_role_and_requires_sign():
    df = pd.DataFrame([
        dict(feature="a", N=50, dir_wic=0.05, mag_ic=0.01, cond_lift=0.00, cond_tercile=2, sign_dir=5),
        dict(feature="b", N=50, dir_wic=0.04, mag_ic=0.02, cond_lift=0.00, cond_tercile=2, sign_dir=2),
        dict(feature="c", N=50, dir_wic=0.00, mag_ic=0.06, cond_lift=0.00, cond_tercile=2, sign_dir=5),
        dict(feature="d", N=50, dir_wic=0.00, mag_ic=0.00, cond_lift=0.50, cond_tercile=2, sign_dir=5),
    ])
    out = survivors(df, top_k=2)
    assert "a" in out["direction"]          # high dir_wic, sign 5/5
    assert "b" not in out["direction"]      # sign 2/5 -> excluded from direction
    assert "c" in out["magnitude"]
    assert "d" in out["conditioner"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/fx_coint/test_edge_feature_search.py -k survivors -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Write minimal implementation**

```python
# add to scripts/fx_coint/edge_feature_search.py
def survivors(screen_df, top_k: int = 5) -> dict:
    d = screen_df[screen_df.N == 50].copy()
    out = {}
    dir_ok = d[d.sign_dir >= 4]
    out["direction"] = dir_ok.reindex(
        dir_ok.dir_wic.abs().sort_values(ascending=False).index).head(top_k).feature.tolist()
    out["magnitude"] = d.reindex(
        d.mag_ic.abs().sort_values(ascending=False).index).head(top_k).feature.tolist()
    out["conditioner"] = d.reindex(
        d.cond_lift.sort_values(ascending=False).index).head(top_k).feature.tolist()
    return out
```

Then extend `main()` (replace its body after `screen`) to run the confirm and write the report:

```python
# replace the body of main() in scripts/fx_coint/edge_feature_search.py
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pnl_walkforward import marginal_lift  # noqa: E402


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    res = screen()
    res.to_csv(OUT_DIR / "screen.csv", index=False)
    surv = survivors(res)

    rng = np.random.default_rng(0)
    cache = {s: build_all(s) for s in POOL}
    evset = {}
    for s in POOL:
        logp, f, vol, bph = cache[s]
        n = len(logp)
        warm = int(96 * bph) + 60
        idx = np.arange(warm, n - 53)
        idx = idx[np.isfinite(vol[idx + 1]) & (vol[idx + 1] > 0)]
        evset[s] = np.sort(rng.choice(idx, min(N_EVENTS, len(idx)), replace=False))

    crows = []
    for role, feats in surv.items():
        for fn in feats:
            for n_tb in (50, 30):
                m = marginal_lift(cache, evset, n_tb, fn, role)
                crows.append(dict(role=role, feature=fn, N=n_tb, **m))
    conf = pd.DataFrame(crows)
    conf.to_csv(OUT_DIR / "confirm.csv", index=False)

    c50 = conf[conf.N == 50]
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar([f"{r['role'][:3]}:{r['feature']}" for _, r in c50.iterrows()],
           c50["lift"].to_numpy(), color="steelblue")
    ax.axhline(0, color="k", linewidth=1)
    ax.set_ylabel("net-bps lift over base (N=50)")
    ax.tick_params(axis="x", labelrotation=80, labelsize=7)
    ax.set_title("Edge-feature confirm — marginal net-bps lift (walk-forward non-overlap)")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "net_lift.png", dpi=110)
    plt.close(fig)

    lines = ["# Edge-Based Feature Search — Report", "",
             "Two-track (direction, magnitude) + conditioning lens. Stage-1 screen "
             "(|ret|-weighted dir IC / IC vs |ret| / tercile net-bps spread) -> Stage-2 "
             "marginal net-bps lift over the fixed base (fade ffd_zvol20 x top-decile "
             "|ffd_zvol20|), walk-forward non-overlap, cost 1.0bps.", "",
             "**No modelling.** All combinations are simple non-fit rules. Full "
             "higher-order non-linear interaction discovery (HistGBM importance under a "
             "P&L objective) is the deferred next phase.", "",
             "## Confirm — marginal net-bps lift (N=50)", "",
             "![net lift](net_lift.png)", "",
             c50.sort_values("lift", ascending=False)[
                 ["role", "feature", "lift", "cand_net", "base_net", "folds_pos"]
             ].to_markdown(index=False)]
    (OUT_DIR / "REPORT.md").write_text("\n".join(lines) + "\n")
    print(f"report -> {OUT_DIR / 'REPORT.md'}")
```

(Remove the earlier print-only `main()` body from Task 3 — this replaces it. Keep the role-screen prints if desired by calling them before the confirm.)

- [ ] **Step 4: Run test + full suite + quality**

Run: `uv run pytest tests/fx_coint/test_edge_feature_search.py tests/fx_coint/test_pnl_walkforward.py -q && make quality`
Expected: all tests pass; ruff/ty clean on the new/changed modules.

- [ ] **Step 5: Run the analysis end-to-end and commit**

```bash
uv run python scripts/fx_coint/edge_feature_search.py
git add scripts/fx_coint/edge_feature_search.py tests/fx_coint/test_edge_feature_search.py reports/edge_feature_search/
git commit -m "feat(fx_coint): edge search confirm driver + report (survivors -> net-bps lift)"
```

---

## Notes for the implementer

- Run everything from the repo/worktree root so `from scripts.fx_coint.X import Y` resolves and `reports/` paths are correct.
- The CLI (`main`) reads parquet under `data/tick_bars/` and is exercised by hand; CI covers the pure scorers (`weighted_directional_ic`, `magnitude_ic`, `tercile_netbps_spread`, `base_fade_pnl`, `greedy_nonoverlap`, `survivors`) on synthetic data.
- `marginal_lift` retrains nothing — it only re-selects/filters trades. Keep it that way (no-modelling boundary).
- Building features for 5 symbols via `build_all` is slow (De Prado features) — the end-to-end `main` run takes several minutes; that is expected.
- Keep `make quality` green: watch ruff SIM/ E702 (no `;` multi-statements), and the matplotlib `Agg` backend must be set before `pyplot` import.
