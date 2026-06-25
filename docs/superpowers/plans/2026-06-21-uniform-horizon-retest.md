# Uniform 1h-Grid Multi-Horizon Net-Edge Re-test Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** On a uniform 1h bar grid with the holding horizon decoupled as a parameter (H ∈ {1,2,3,4} hours), measure the tail-long net-after-cost directional edge per horizon with dual inference (overlapping/clustered AND non-overlapping, both must agree), fixing the coarse-timeframe decimation artifact and directly answering whether 1h clears cost and whether 3h/4h hold an edge.

**Architecture:** A horizon-parameterized panel builder reuses `build_panel`'s features and swaps the target to the forward-H-bar return on the 1h grid. A causal ridge WFO per horizon yields OOS tail-long trades (net = sign·forward-H return − per-pair cost; bar-close return, no 1-min path needed). Dual inference compares the full overlapping track (day-clustered t + year bootstrap, effective-N reported) against a stride-H non-overlapping subset; both must clear zero. A CLI sweeps horizons pooled over TIGHT majors with BH-FDR.

**Tech Stack:** Python 3.12, numpy, pandas, polars, scikit-learn, scipy.stats, pytest. Reuses `reg_signal_hunt` (build_freq_bars/build_panel/FEATURE_COLS/COST_BPS/bh_reject), `tail_wfo` (Ridge WFO pattern, day_clustered_tstat), `path_geometry_opt` (year_block_bootstrap_ci, positive_years).

## Global Constraints

- One bar grid: **1h** on session (7,21) via `build_freq_bars(df, "1h")`. Horizon H is a separate parameter; entries can occur at any 1h bar. (spec §2)
- Forward-H target = `(log(mid[t+H]) − log(mid[t]))·1e4`, valid only if bars `t..t+H` are all contiguous; vol-normalized by `sigma_h·sqrt(H)`. (spec §2)
- Causal ridge WFO per horizon (expanding folds, train-split quantile threshold). Features reused from `build_panel` unchanged. (spec §2)
- Net = `sign·forward_H_bps − COST_BPS[sym]` (long side, one round-trip; bar-close return — the 1-min path is downstream, not needed here). (spec §3)
- **Dual inference, both must agree:** overlapping (all hourly entries; day-clustered t + year-block bootstrap CI; report effective non-overlapping N) AND non-overlapping (stride-H subset; own t/CI). Edge real only if both clear zero same sign. (spec §3)
- Pooled across TIGHT majors `["EURUSD","GBPUSD","USDJPY"]`, per-pair cost. BH-FDR across the {horizon} grid. (spec §3)
- New code: `scripts/fx_coint/horizon_retest.py`; tests `tests/fx_coint/test_horizon_retest.py`.

---

## Task 1: Horizon-parameterized panel builder

**Files:**
- Create: `scripts/fx_coint/horizon_retest.py`
- Test: `tests/fx_coint/test_horizon_retest.py`

**Interfaces:**
- Consumes: `reg_signal_hunt.build_panel`, `FEATURE_COLS`.
- Produces:
  - `build_horizon_panel(bars: pd.DataFrame, H: int, vol_lookback: int = 24) -> pd.DataFrame` — start from `build_panel(bars)` (features + `sigma_h` + `bucket` for feature-valid rows), then attach the **forward-H-bar return** computed on `bars` (NaN unless `bars[i..i+H]` all contiguous), as `ret_fwd_bps`; set `target_z = ret_fwd_bps / (sigma_h·sqrt(H))`; drop rows with non-finite `ret_fwd_bps`/`target_z`. Returns columns: `FEATURE_COLS + ["bucket","sigma_h","ret_fwd_bps","target_z"]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/fx_coint/test_horizon_retest.py
import numpy as np
import pandas as pd
from scripts.fx_coint.horizon_retest import build_horizon_panel

def _bars(n=400, start="2022-01-03 07:00"):
    # contiguous 1h bars within session, mid a gentle random walk
    idx = pd.date_range(start, periods=n, freq="1h")
    # keep only session hours 7..20 so build_freq_bars-style contig holds intraday
    rng = np.random.default_rng(0)
    mid = 1.10 * np.exp(np.cumsum(rng.normal(0, 1e-4, n)))
    df = pd.DataFrame({"bucket": idx, "mid": mid})
    df["contig"] = True
    df.loc[0, "contig"] = False
    return df

def test_forward_h_target_matches_h_bar_return():
    bars = _bars()
    p = build_horizon_panel(bars, H=3)
    # pick a row and verify ret_fwd_bps == 3-bar forward return at that bucket
    row = p.iloc[10]
    i = bars.index[bars["bucket"] == row["bucket"]][0]
    expect = (np.log(bars["mid"].iloc[i + 3]) - np.log(bars["mid"].iloc[i])) * 1e4
    assert np.isclose(row["ret_fwd_bps"], expect, atol=1e-6)
    assert "target_z" in p.columns and np.isfinite(p["target_z"]).all()

def test_non_contiguous_window_dropped():
    bars = _bars()
    bars.loc[20, "contig"] = False   # breaks any window spanning bar 20
    p = build_horizon_panel(bars, H=3)
    # buckets whose [i, i+3] window includes the broken bar 20 must be absent
    broken_buckets = set(bars["bucket"].iloc[17:20])
    assert not (broken_buckets & set(p["bucket"]))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/repositories/behemoth/.claude/worktrees/fx-path-geometry && uv run pytest tests/fx_coint/test_horizon_retest.py -q`
Expected: FAIL `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/fx_coint/horizon_retest.py
"""Uniform 1h-grid multi-horizon tail-long net-edge re-test."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.fx_coint.reg_signal_hunt import FEATURE_COLS, build_panel  # noqa: E402


def build_horizon_panel(bars: pd.DataFrame, H: int, vol_lookback: int = 24) -> pd.DataFrame:
    panel = build_panel(bars, vol_lookback=vol_lookback).reset_index(drop=True)
    b = bars.reset_index(drop=True)
    mid = b["mid"].to_numpy()
    contig = b["contig"].to_numpy()
    n = len(b)
    fwd = np.full(n, np.nan)
    # forward-H window [i, i+H] valid only if bars i+1..i+H are all contiguous
    for i in range(n - H):
        if contig[i + 1:i + 1 + H].all():
            fwd[i] = (np.log(mid[i + H]) - np.log(mid[i])) * 1e4
    fwd_by_bucket = dict(zip(b["bucket"].to_numpy(), fwd, strict=False))
    rf = panel["bucket"].map(lambda x: fwd_by_bucket.get(x, np.nan)).to_numpy()
    out = panel.copy()
    out["ret_fwd_bps"] = rf
    out["target_z"] = rf / (out["sigma_h"].to_numpy() * np.sqrt(H))
    keep = np.isfinite(out["ret_fwd_bps"].to_numpy()) & np.isfinite(out["target_z"].to_numpy())
    return out[keep].reset_index(drop=True)[FEATURE_COLS + ["bucket", "sigma_h", "ret_fwd_bps", "target_z"]]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/repositories/behemoth/.claude/worktrees/fx-path-geometry && uv run pytest tests/fx_coint/test_horizon_retest.py -q`
Expected: PASS (2 passed). If `build_panel` requires a `contig` column and a real bar shape the synthetic lacks, adjust `_bars` to include exactly what `build_panel` reads (`mid`, `contig`, `bucket`) — confirm by reading `build_panel`.

- [ ] **Step 5: Commit**

```bash
cd ~/repositories/behemoth/.claude/worktrees/fx-path-geometry
for s in EURUSD GBPUSD USDJPY USDCAD AUDUSD USDCHF; do ln -sfn ~/repositories/behemoth/data/tick_bars/${s}_1m_flow.parquet data/tick_bars/${s}_1m_flow.parquet; done
git add scripts/fx_coint/horizon_retest.py tests/fx_coint/test_horizon_retest.py
git commit -m "feat(fx_coint): horizon-parameterized 1h-grid panel (forward-H target)"
```

---

## Task 2: Per-horizon causal WFO tail-long net track

**Files:**
- Modify: `scripts/fx_coint/horizon_retest.py`
- Test: `tests/fx_coint/test_horizon_retest.py`

**Interfaces:**
- Consumes: `build_horizon_panel`, `reg_signal_hunt.build_freq_bars/COST_BPS/FEATURE_COLS`, sklearn Ridge/StandardScaler.
- Produces:
  - `horizon_net_track(sym, H, q=0.95, n_folds=5, min_train_frac=0.5, purge=1) -> dict` — build 1h bars, `build_horizon_panel(.., H)`, expanding WFO; per fold fit Ridge on train, threshold `quantile(train_pred,q)`, select test rows `test_pred ≥ thr`; net = `ret_fwd_bps[sel] − COST_BPS[sym]` (long). Return `{"net": (m,), "bucket": (m,) datetime64, "n": m}` concatenated over folds (the OVERLAPPING track — entries every 1h).

- [ ] **Step 1: Write the failing test**

```python
# add to tests/fx_coint/test_horizon_retest.py
from scripts.fx_coint.horizon_retest import horizon_net_track

def test_horizon_net_track_shapes_and_more_entries_at_h1():
    t1 = horizon_net_track("EURUSD", H=1)
    t4 = horizon_net_track("EURUSD", H=4)
    assert t1["n"] > 200 and t4["n"] > 200
    assert t1["net"].shape == (t1["n"],)
    assert t1["bucket"].shape == (t1["n"],)
    # hourly sampling => H=1 and H=4 have comparable entry counts (both ~hourly grid),
    # and BOTH are far larger than the old disjoint 4-bar/day 4h panel (~196)
    assert t4["n"] > 500
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/repositories/behemoth/.claude/worktrees/fx-path-geometry && uv run pytest tests/fx_coint/test_horizon_retest.py::test_horizon_net_track_shapes_and_more_entries_at_h1 -q`
Expected: FAIL (ImportError).

- [ ] **Step 3: Write minimal implementation**

```python
# add to scripts/fx_coint/horizon_retest.py
import polars as pl  # noqa: E402
from sklearn.linear_model import Ridge  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402

from scripts.fx_coint.reg_signal_hunt import COST_BPS, build_freq_bars  # noqa: E402


def horizon_net_track(sym, H, q=0.95, n_folds=5, min_train_frac=0.5, purge=1):
    bars = build_freq_bars(pl.read_parquet(_REPO_ROOT / f"data/tick_bars/{sym}_1m_flow.parquet"), "1h")
    panel = build_horizon_panel(bars, H)
    X = panel[FEATURE_COLS].to_numpy()
    yz = panel["target_z"].to_numpy()
    fwd = panel["ret_fwd_bps"].to_numpy()
    bucket = panel["bucket"].to_numpy()
    cost = COST_BPS[sym]
    n = len(panel)
    edges = np.linspace(int(n * min_train_frac), n, n_folds + 1).astype(int)
    nets, bks = [], []
    for k in range(n_folds):
        split = edges[k]
        lo, hi = edges[k] + purge, edges[k + 1]
        if hi - lo < 1 or split < 10:
            continue
        sc = StandardScaler().fit(X[:split])
        model = Ridge(alpha=1.0).fit(sc.transform(X[:split]), yz[:split])
        thr = np.quantile(model.predict(sc.transform(X[:split])), q)
        tp = model.predict(sc.transform(X[lo:hi]))
        sel = tp >= thr
        nets.append(fwd[lo:hi][sel] - cost)
        bks.append(bucket[lo:hi][sel])
    net = np.concatenate(nets) if nets else np.array([])
    bk = np.concatenate(bks) if bks else np.array([], dtype="datetime64[ns]")
    return {"net": net, "bucket": bk, "n": len(net)}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/repositories/behemoth/.claude/worktrees/fx-path-geometry && uv run pytest tests/fx_coint/test_horizon_retest.py -q`
Expected: PASS (3 passed). The headline check: H=4 now yields >500 entries (vs the artifact's ~196), confirming the decimation is fixed.

- [ ] **Step 5: Commit**

```bash
git add scripts/fx_coint/horizon_retest.py tests/fx_coint/test_horizon_retest.py
git commit -m "feat(fx_coint): per-horizon causal WFO tail-long net track (1h grid)"
```

---

## Task 3: Dual inference (overlapping-clustered + non-overlapping) helpers

**Files:**
- Modify: `scripts/fx_coint/horizon_retest.py`
- Test: `tests/fx_coint/test_horizon_retest.py`

**Interfaces:**
- Consumes: `tail_wfo.day_clustered_tstat`, `path_geometry_opt.year_block_bootstrap_ci`, `path_geometry_opt.positive_years`.
- Produces:
  - `non_overlap_mask(bucket: np.ndarray, H_hours: int) -> np.ndarray` — greedy left-to-right boolean mask keeping entries ≥ `H_hours` apart (independent subset).
  - `summarize_track(net, bucket, label) -> dict` — `{label, n, mean, day_t, day_p, ci_lo, ci_hi, pos_y, n_y}` (day-clustered t via `day_clustered_tstat`, year-block CI, positive-years).
  - `dual_inference(net, bucket, H_hours, label) -> dict` — `{"overlapping": summarize(all), "nonoverlap": summarize(subset), "eff_n": int(mask.sum()), "raw_n": len(net), "agree": bool}` where `agree` = both means same sign AND both day_p < 0.05 AND both bootstrap CIs exclude 0.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/fx_coint/test_horizon_retest.py
import pandas as pd
from scripts.fx_coint.horizon_retest import non_overlap_mask, summarize_track, dual_inference

def test_non_overlap_mask_spacing():
    bk = pd.to_datetime(["2022-01-03 07:00","2022-01-03 08:00","2022-01-03 11:00",
                         "2022-01-03 12:00"]).values
    m = non_overlap_mask(bk, H_hours=3)
    # 07:00 kept; 08:00 too close (kept-prev 07:00 +3h=10:00) -> drop; 11:00 kept; 12:00 drop
    assert m.tolist() == [True, False, True, False]

def test_dual_inference_agree_flag_false_on_noise():
    rng = np.random.default_rng(0)
    bk = pd.to_datetime(np.repeat(pd.date_range("2019-01-01", periods=200, freq="3h"), 1)).values
    net = rng.normal(0.0, 1.0, len(bk))   # pure noise -> not significant
    r = dual_inference(net, bk, H_hours=3, label="noise")
    assert r["agree"] is False
    assert r["raw_n"] == len(bk) and r["eff_n"] <= r["raw_n"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/repositories/behemoth/.claude/worktrees/fx-path-geometry && uv run pytest tests/fx_coint/test_horizon_retest.py -q`
Expected: FAIL (ImportError).

- [ ] **Step 3: Write minimal implementation**

```python
# add to scripts/fx_coint/horizon_retest.py
from scripts.fx_coint.path_geometry_opt import positive_years, year_block_bootstrap_ci  # noqa: E402
from scripts.fx_coint.tail_wfo import day_clustered_tstat  # noqa: E402

_NS_PER_HOUR = 3_600_000_000_000


def non_overlap_mask(bucket: np.ndarray, H_hours: int) -> np.ndarray:
    order = np.argsort(bucket)
    ns = bucket.astype("datetime64[ns]").astype("int64")
    keep = np.zeros(len(bucket), dtype=bool)
    last = -np.inf
    for idx in order:
        if ns[idx] - last >= H_hours * _NS_PER_HOUR:
            keep[idx] = True
            last = ns[idx]
    return keep


def summarize_track(net, bucket, label):
    net = np.asarray(net, float)
    if len(net) < 3:
        return {"label": label, "n": len(net), "mean": float("nan"), "day_t": float("nan"),
                "day_p": float("nan"), "ci_lo": float("nan"), "ci_hi": float("nan"),
                "pos_y": 0, "n_y": 0}
    dc = day_clustered_tstat(net, bucket)
    lo, hi = year_block_bootstrap_ci(net, bucket)
    pos, ny = positive_years(net, bucket)
    return {"label": label, "n": len(net), "mean": float(net.mean()),
            "day_t": dc["t_stat"], "day_p": dc["p_value"], "ci_lo": lo, "ci_hi": hi,
            "pos_y": pos, "n_y": ny}


def dual_inference(net, bucket, H_hours, label):
    net = np.asarray(net, float)
    mask = non_overlap_mask(bucket, H_hours)
    ov = summarize_track(net, bucket, f"{label}/overlap")
    no = summarize_track(net[mask], bucket[mask], f"{label}/nonoverlap")

    def _ok(s):
        return (np.isfinite(s["day_p"]) and s["day_p"] < 0.05
                and s["ci_lo"] > 0 and s["mean"] > 0)
    agree = bool(_ok(ov) and _ok(no))
    return {"overlapping": ov, "nonoverlap": no, "eff_n": int(mask.sum()),
            "raw_n": len(net), "agree": agree}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/repositories/behemoth/.claude/worktrees/fx-path-geometry && uv run pytest tests/fx_coint/test_horizon_retest.py -q`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add scripts/fx_coint/horizon_retest.py tests/fx_coint/test_horizon_retest.py
git commit -m "feat(fx_coint): dual inference (overlap-clustered + non-overlap) for horizon re-test"
```

---

## Task 4: Pooled horizon sweep CLI + BH-FDR + run

**Files:**
- Modify: `scripts/fx_coint/horizon_retest.py`
- Test: `tests/fx_coint/test_horizon_retest.py`

**Interfaces:**
- Consumes: `horizon_net_track`, `dual_inference`, `reg_signal_hunt.bh_reject`.
- Produces:
  - `pooled_horizon(H, pairs=TIGHT) -> dict` — concatenate `horizon_net_track` net/bucket across pairs (each already cost-netted with its pair cost), run `dual_inference(.., H_hours=H, ..)`.
  - `main()` — for H in (1,2,3,4): `pooled_horizon`; collect overlapping day_p; apply `bh_reject(pvals, q=0.05)`; print + write `scripts/fx_coint/horizon_retest_results.md` with, per H: raw_n, eff_n, overlapping mean/day_p/CI/pos-years, non-overlap mean/day_p/CI/pos-years, `agree`, and BH-FDR reject flag. GO for a horizon = `agree` True AND BH-FDR reject.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/fx_coint/test_horizon_retest.py
from scripts.fx_coint.horizon_retest import pooled_horizon

def test_pooled_horizon_runs_and_reports_both_tracks():
    r = pooled_horizon(2)
    assert r["raw_n"] > 300
    assert "overlapping" in r and "nonoverlap" in r and "agree" in r
    assert r["eff_n"] < r["raw_n"]   # H=2 overlapping => fewer independent
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/repositories/behemoth/.claude/worktrees/fx-path-geometry && uv run pytest tests/fx_coint/test_horizon_retest.py::test_pooled_horizon_runs_and_reports_both_tracks -q`
Expected: FAIL (ImportError).

- [ ] **Step 3: Write minimal implementation**

```python
# add to scripts/fx_coint/horizon_retest.py
from scripts.fx_coint.reg_signal_hunt import bh_reject  # noqa: E402

TIGHT = ["EURUSD", "GBPUSD", "USDJPY"]


def pooled_horizon(H, pairs=TIGHT):
    nets, bks = [], []
    for sym in pairs:
        t = horizon_net_track(sym, H)
        if t["n"]:
            nets.append(t["net"])
            bks.append(t["bucket"])
    net = np.concatenate(nets)
    bk = np.concatenate(bks)
    return dual_inference(net, bk, H_hours=H, label=f"H={H}")


def _fmt(H, r, reject):
    ov, no = r["overlapping"], r["nonoverlap"]
    go = "GO" if (r["agree"] and reject) else "no"
    return (f"## H={H}h  raw_n={r['raw_n']} eff_n={r['eff_n']}  agree={r['agree']} "
            f"BH={'reject' if reject else 'keep-null'}  -> {go}\n"
            f"   overlap : mean={ov['mean']:+.3f} day_p={ov['day_p']:.4f} "
            f"ci=[{ov['ci_lo']:+.3f},{ov['ci_hi']:+.3f}] pos={ov['pos_y']}/{ov['n_y']}\n"
            f"   nonovlp : mean={no['mean']:+.3f} day_p={no['day_p']:.4f} "
            f"ci=[{no['ci_lo']:+.3f},{no['ci_hi']:+.3f}] pos={no['pos_y']}/{no['n_y']}")


def main():
    results = {H: pooled_horizon(H) for H in (1, 2, 3, 4)}
    pvals = np.array([results[H]["overlapping"]["day_p"] for H in (1, 2, 3, 4)])
    finite = np.isfinite(pvals)
    rej = np.zeros(4, dtype=bool)
    if finite.any():
        rr = bh_reject(pvals[finite], q=0.05)
        rej[np.where(finite)[0]] = rr
    blocks = [_fmt(H, results[H], bool(rej[i])) for i, H in enumerate((1, 2, 3, 4))]
    out = "# Uniform 1h-grid multi-horizon net-edge re-test\n\n" + "\n\n".join(blocks) + "\n"
    print(out)
    (Path(__file__).resolve().parent / "horizon_retest_results.md").write_text(out)


if __name__ == "__main__":
    main()
```

Note: confirm `bh_reject` signature is `bh_reject(pvals, q=0.10)` (as found in Phase B) — the call uses `q=0.05`. If it returns indices rather than a boolean mask, adapt `rej` assignment.

- [ ] **Step 4: Run test, then run the real re-test**

Run: `cd ~/repositories/behemoth/.claude/worktrees/fx-path-geometry && uv run pytest tests/fx_coint/test_horizon_retest.py -q`
Expected: PASS (6 passed).

Then: `uv run python scripts/fx_coint/horizon_retest.py`
Expected: prints H=1..4 with raw_n/eff_n, both tracks' mean/day_p/CI/pos-years, `agree`, BH verdict; writes `horizon_retest_results.md`. **Interpretation (report honestly):** a horizon is a GO only if `agree` (both overlapping AND non-overlapping clear zero, same positive sign) AND it survives BH-FDR. Expected per the spec: longer H clears cost more readily than 1h; 1h likely net-negative (answers the 1h question with a number); 3h/4h now have raw_n in the hundreds-to-thousands (decimation fixed) so their verdict is finally trustworthy.

- [ ] **Step 5: Run quality and commit**

Run: `cd ~/repositories/behemoth/.claude/worktrees/fx-path-geometry && make quality`
Expected: ty + ruff clean (fix any lint first).

```bash
git add scripts/fx_coint/horizon_retest.py tests/fx_coint/test_horizon_retest.py scripts/fx_coint/horizon_retest_results.md
git commit -m "feat(fx_coint): pooled multi-horizon net-edge sweep + dual inference + BH-FDR + results"
```

---

## Self-Review notes

- **Spec coverage:** §2 1h grid + forward-H target → Task 1; per-horizon causal WFO net → Task 2; §3 dual inference (overlap-clustered + non-overlap, agree) + decision metric → Task 3; pooled + BH-FDR + run → Task 4. §4 expectation is an interpretation note, not code. §5 scope (net edge only; geometry downstream) respected — no path/geometry here.
- **Type consistency:** tracks are `{"net","bucket","n"}`; `dual_inference` returns `{"overlapping","nonoverlap","eff_n","raw_n","agree"}` consumed identically in Task 4.
- **Decimation-fix assertion is explicit** (Task 2 test: H=4 raw_n > 500 vs the artifact's ~196) — this is the load-bearing proof the root cause is fixed.
- **Known checks for the implementer:**
  - `bh_reject` signature (Task 4 note).
  - `build_panel` synthetic-bar compatibility (Task 1 Step 4 note) — the test's `_bars` must supply exactly the columns `build_panel`/`build_freq_bars` read; if `build_panel` needs a longer warmup than the synthetic provides, lengthen `_bars`.
  - Per-pair cost is charged inside `horizon_net_track` (each pair its own `COST_BPS[sym]`) before pooling — confirm no flat cost.
  - `non_overlap_mask` greedy spacing uses `≥ H_hours`; verify against the Task 3 test exactly.
