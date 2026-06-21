# Path-Geometry Phase A — Engine + Distribution-Shift Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the shared empirical-path engine (conditional path ensemble + matched unconditional null fan + path excursion metrics) for both validated edges, and run the **distribution-shift gate** — the cheap test of whether each edge's conditional future-path distribution differs from random-walk, which greenlights or kills the whole path-geometry idea before any bracket optimization.

**Architecture:** Three small units under `scripts/fx_coint/`: (1) `path_geometry_paths.py` vendors the verified 1-minute path-reconstruction helpers (self-contained — the PF branch's `pf_paths.py` is not yet on `main`); (2) `path_ensemble.py` turns an edge's entries into a vol-normalized path ensemble with terminal-return and MFE/MAE excursion metrics, plus a matched random (unconditional) ensemble; (3) `path_shift_gate.py` runs two-sample tests (conditional vs unconditional) and a CLI report. Edges are configs, not code paths.

**Tech Stack:** Python 3.12, numpy, pandas, polars, scipy.stats, pytest. Reuses `scripts/fx_coint/reg_signal_hunt.py` (panel/bars/COST_BPS), `tail_wfo.py` (walk_forward ridge), `validate_reversion_cell.py` (causal reversion entries).

## Global Constraints

- This is a **risk/execution** study, not alpha discovery: the path distribution's value is conditional-vs-unconditional difference, nothing more. (spec §1)
- The "distribution" is the **empirical conditional path ensemble** — actual historical 1-minute intra-hold paths. No simulator in Phase A. (spec §1)
- All selection is **causal**: 2h tail-long entries come from `tail_wfo.walk_forward` (train-split ridge, OOS test entries); reversion entries from the existing causal expanding-window decile fade. Never full-sample. (spec §3)
- Vol-normalize every path by the entry bar's `sigma_h` (panel column) so pairs/time are comparable; excursions/returns reported in **σ units** and in **bps**. (spec §2a)
- Unconditional null entries are a **random-offset placebo**: real signal entries shifted by a random whole-day offset (same time-of-day, different day, hold window non-overlapping, excluding real-signal days). NOT random unrelated bars; NOT data augmentation. (spec §2b)
- A **small-offset robustness probe** (±1–3 bar jitter, same day) is reported alongside gate 1; the conditional metrics must be stable under it. (spec §2b2)
- Net of real cost uses `reg_signal_hunt.COST_BPS[sym]`. (spec §2c)
- Edges/pairs: TIGHT_MAJORS = `["EURUSD","GBPUSD","USDJPY"]` first; helpers must accept any of the 6 majors. (spec §3)
- Gate-1 decision: if the conditional ensemble is statistically indistinguishable from the unconditional fan, **STOP** that edge. (spec §4 gate 1)
- New code under `scripts/fx_coint/`; tests under `tests/fx_coint/`.

---

## Task 1: Vendor verified 1-minute path helpers (parameterized hold)

**Files:**
- Create: `scripts/fx_coint/path_geometry_paths.py`
- Test: `tests/fx_coint/test_path_geometry_paths.py`

**Interfaces:**
- Produces:
  - `build_minute_index(sym: str) -> tuple[np.ndarray, np.ndarray]` — `(buckets_ns int64, mids float)` sorted by bucket.
  - `hold_path(entry_bucket, freq: str, buckets_ns, mids, n_bars: int = 1) -> np.ndarray` — 1m mids in `[B+freq, B+(n_bars+1)*freq)` (the `n_bars` held bars after the signal bar B).
  - `path_to_volnorm_returns(path_mids, sigma_bps: float) -> np.ndarray` — per-step log-returns in bps ÷ sigma_bps; length `len-1`; empty if `len<2` or `sigma_bps<=0`.

- [ ] **Step 1: Write the failing test**

```python
# tests/fx_coint/test_path_geometry_paths.py
import numpy as np
import pandas as pd
from scripts.fx_coint.path_geometry_paths import hold_path, path_to_volnorm_returns

def _synth():
    base = pd.Timestamp("2022-01-03 08:00")
    buckets = pd.date_range(base, periods=480, freq="1min").values
    mids = np.linspace(1.10, 1.12, 480)
    return buckets.astype("datetime64[ns]").astype("int64"), mids

def test_hold_path_one_bar_window():
    bn, mids = _synth()
    # 2h bar at 08:00 -> held next bar [10:00, 12:00) -> indices 120..239 (120 marks)
    path = hold_path(np.datetime64("2022-01-03 08:00"), "2h", bn, mids, n_bars=1)
    assert len(path) == 120
    assert np.isclose(path[0], mids[120])
    assert np.isclose(path[-1], mids[239])

def test_hold_path_two_bars_window():
    bn, mids = _synth()
    # n_bars=2 -> [10:00, 14:00) -> indices 120..359 (240 marks)
    path = hold_path(np.datetime64("2022-01-03 08:00"), "2h", bn, mids, n_bars=2)
    assert len(path) == 240
    assert np.isclose(path[0], mids[120])
    assert np.isclose(path[-1], mids[359])

def test_volnorm_guards():
    assert path_to_volnorm_returns(np.array([1.0]), 1.0).size == 0
    assert path_to_volnorm_returns(np.array([1.0, 1.1]), 0.0).size == 0
    out = path_to_volnorm_returns(np.array([1.0, 1.0001, 1.0002]), 1.0)
    assert out.shape == (2,) and np.all(out > 0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/repositories/behemoth/.claude/worktrees/fx-path-geometry && uv run pytest tests/fx_coint/test_path_geometry_paths.py -q`
Expected: FAIL `ModuleNotFoundError: scripts.fx_coint.path_geometry_paths`.

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/fx_coint/path_geometry_paths.py
"""Intra-hold 1-minute mid-path reconstruction (vendored, verified in PF Phase-1).

Entry signal at bar bucket B; position held over the n_bars bars AFTER B, i.e. the
window [B+freq, B+(n_bars+1)*freq). The entry is anchored by the caller at the signal
bar's CLOSE mid (bars["mid"] at B). At hold-to-cap the last minute equals the held
window's final bar close, so a no-bracket terminal return reproduces the panel
close-to-close return exactly.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import polars as pl

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.fx_coint.reg_signal_hunt import FREQ_MINUTES  # noqa: E402

_NS_PER_MIN = 60_000_000_000


def build_minute_index(sym: str) -> tuple[np.ndarray, np.ndarray]:
    df = pl.read_parquet(_REPO_ROOT / f"data/tick_bars/{sym}_1m_flow.parquet").sort("bucket")
    buckets_ns = df["bucket"].to_numpy().astype("datetime64[ns]").astype("int64")
    mids = df["mid"].to_numpy().astype(float)
    return buckets_ns, mids


def hold_path(entry_bucket, freq: str, buckets_ns: np.ndarray, mids: np.ndarray,
              n_bars: int = 1) -> np.ndarray:
    step_ns = FREQ_MINUTES[freq] * _NS_PER_MIN
    e = np.datetime64(entry_bucket, "ns").astype("int64")
    i0 = np.searchsorted(buckets_ns, e + step_ns, side="left")
    i1 = np.searchsorted(buckets_ns, e + (n_bars + 1) * step_ns, side="left")
    return mids[i0:i1]


def path_to_volnorm_returns(path_mids: np.ndarray, sigma_bps: float) -> np.ndarray:
    if len(path_mids) < 2 or sigma_bps <= 0:
        return np.empty(0)
    lr_bps = (np.log(path_mids[1:]) - np.log(path_mids[:-1])) * 1e4
    return lr_bps / sigma_bps
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/repositories/behemoth/.claude/worktrees/fx-path-geometry && uv run pytest tests/fx_coint/test_path_geometry_paths.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
cd ~/repositories/behemoth/.claude/worktrees/fx-path-geometry
for s in EURUSD GBPUSD USDJPY USDCAD AUDUSD USDCHF; do ln -sfn ~/repositories/behemoth/data/tick_bars/${s}_1m_flow.parquet data/tick_bars/${s}_1m_flow.parquet; done
git add scripts/fx_coint/path_geometry_paths.py tests/fx_coint/test_path_geometry_paths.py
git commit -m "feat(fx_coint): vendor parameterized 1-min hold-path helpers for path-geometry"
```

---

## Task 2: Path excursion metrics (terminal / MFE / MAE)

**Files:**
- Create: `scripts/fx_coint/path_metrics.py`
- Test: `tests/fx_coint/test_path_metrics.py`

**Interfaces:**
- Produces:
  - `path_excursions(entry_mid: float, minutes: np.ndarray, side: str, sigma_bps: float) -> dict` — signed (by side) excursions in σ units over a held path. Returns `{"terminal_sigma","mfe_sigma","mae_sigma","terminal_bps","n_steps"}` where `mfe_sigma = max favorable signed excursion ≥ 0`, `mae_sigma = min signed excursion ≤ 0` (most adverse). `terminal_bps = sign*(log(minutes[-1]/entry_mid))*1e4`; σ versions divide by `sigma_bps`. Empty minutes → all-NaN dict with `n_steps=0`.

- [ ] **Step 1: Write the failing test**

```python
# tests/fx_coint/test_path_metrics.py
import numpy as np
from scripts.fx_coint.path_metrics import path_excursions

def test_long_excursions():
    entry = 1.0
    # path goes up to +20bps then down to -10bps, ends +5bps (approx via small moves)
    mins = entry * np.exp(np.array([0.0010, 0.0020, -0.0010, 0.0005]))  # cumulative? no: levels
    # build explicit levels: +10, +20, -10, +5 bps from entry
    mins = entry * np.exp(np.array([10, 20, -10, 5]) / 1e4)
    r = path_excursions(entry, mins, "long", sigma_bps=10.0)
    assert np.isclose(r["terminal_bps"], 5.0, atol=1e-6)
    assert np.isclose(r["mfe_sigma"], 2.0, atol=1e-6)   # +20bps / 10
    assert np.isclose(r["mae_sigma"], -1.0, atol=1e-6)  # -10bps / 10
    assert r["n_steps"] == 4

def test_short_flips_sign():
    entry = 1.0
    mins = entry * np.exp(np.array([10, -20, 5]) / 1e4)  # raw +10,-20,+5
    r = path_excursions(entry, mins, "short", sigma_bps=10.0)
    # short: signed = -raw -> -10,+20,-5 ; mfe=+20bps/10=2, mae=-10bps/10=-1, terminal=-5
    assert np.isclose(r["terminal_bps"], -5.0, atol=1e-6)
    assert np.isclose(r["mfe_sigma"], 2.0, atol=1e-6)
    assert np.isclose(r["mae_sigma"], -1.0, atol=1e-6)

def test_empty():
    r = path_excursions(1.0, np.empty(0), "long", 10.0)
    assert r["n_steps"] == 0 and np.isnan(r["terminal_bps"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/repositories/behemoth/.claude/worktrees/fx-path-geometry && uv run pytest tests/fx_coint/test_path_metrics.py -q`
Expected: FAIL `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/fx_coint/path_metrics.py
"""Signed path excursions (terminal / max-favorable / max-adverse) in sigma units."""
from __future__ import annotations

import numpy as np


def path_excursions(entry_mid: float, minutes: np.ndarray, side: str,
                    sigma_bps: float) -> dict:
    if len(minutes) < 1 or sigma_bps <= 0:
        return {"terminal_sigma": float("nan"), "mfe_sigma": float("nan"),
                "mae_sigma": float("nan"), "terminal_bps": float("nan"), "n_steps": 0}
    sign = 1.0 if side == "long" else -1.0
    signed_bps = sign * (np.log(minutes) - np.log(entry_mid)) * 1e4
    mfe = float(max(0.0, signed_bps.max()))
    mae = float(min(0.0, signed_bps.min()))
    term = float(signed_bps[-1])
    return {"terminal_sigma": term / sigma_bps, "mfe_sigma": mfe / sigma_bps,
            "mae_sigma": mae / sigma_bps, "terminal_bps": term, "n_steps": len(minutes)}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/repositories/behemoth/.claude/worktrees/fx-path-geometry && uv run pytest tests/fx_coint/test_path_metrics.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add scripts/fx_coint/path_metrics.py tests/fx_coint/test_path_metrics.py
git commit -m "feat(fx_coint): signed path excursion metrics (terminal/MFE/MAE in sigma)"
```

---

## Task 3: Conditional + unconditional ensemble for the 2h tail-long edge

**Files:**
- Create: `scripts/fx_coint/path_ensemble.py`
- Test: `tests/fx_coint/test_path_ensemble.py`

**Interfaces:**
- Consumes: `path_geometry_paths.build_minute_index/hold_path`, `path_metrics.path_excursions`, `tail_wfo.walk_forward`, `reg_signal_hunt.build_freq_bars/build_panel/COST_BPS`.
- Produces:
  - `tail_long_entries(sym, freq="2h", q=0.95, n_folds=5) -> list[tuple]` — list of `(entry_bucket: np.datetime64, side: str, sigma_bps: float)` for OOS ridge-selected long entries (test_pred ≥ train q-quantile). side always `"long"`.
  - `offset_placebo_entries(sym, freq, signal_entries, min_off_days=3, max_off_days=60, seed=0) -> list[tuple]` — for each signal entry `(B, side, sigma)`, shift B by a random whole-day offset (sign random, `min_off_days ≤ |k| ≤ max_off_days`), KEEPING the same time-of-day and side; the shifted bucket must exist in the panel, must not be a real signal day (`B' not in {signal days}`), and its hold window must not overlap the original. Returns `(B', side, sigma_bps_at_B')`. Preserves count and side mix; same hour-of-day by construction. (This is the null AND, in Phase B, the shuffled-label null.)
  - `build_ensemble(sym, entries, freq, n_bars=1) -> pd.DataFrame` — for each entry, reconstruct the held path (anchor = bars close mid at bucket), compute `path_excursions`, return one row per entry with columns `bucket, sigma_bps, terminal_bps, terminal_sigma, mfe_sigma, mae_sigma, n_steps`. Drops entries with empty paths.

- [ ] **Step 1: Write the failing test** (real data; small, deterministic checks)

```python
# tests/fx_coint/test_path_ensemble.py
import numpy as np
from scripts.fx_coint.path_ensemble import (
    tail_long_entries, unconditional_entries, build_ensemble,
)

def test_tail_long_entries_nonempty_and_long():
    ents = tail_long_entries("EURUSD", freq="2h", q=0.95)
    assert len(ents) > 30
    assert all(side == "long" for _, side, _ in ents)
    assert all(s > 0 for _, _, s in ents)

def test_offset_placebo_same_tod_excludes_signals():
    import pandas as pd
    from scripts.fx_coint.path_ensemble import offset_placebo_entries
    ents = tail_long_entries("EURUSD", freq="2h", q=0.95)
    excl = {b for b, _, _ in ents}
    plc = offset_placebo_entries("EURUSD", "2h", ents, min_off_days=3, max_off_days=60, seed=1)
    assert len(plc) > 0.8 * len(ents)            # most entries place-able
    assert not (excl & {b for b, _, _ in plc})   # none land on a real signal bar
    # same time-of-day preserved (offset is whole days)
    sig_h = pd.to_datetime(pd.Series([b for b, _, _ in ents])).dt.hour.value_counts(normalize=True)
    plc_h = pd.to_datetime(pd.Series([b for b, _, _ in plc])).dt.hour.value_counts(normalize=True)
    assert set(plc_h.index).issubset(set(sig_h.index))

def test_build_ensemble_columns_and_terminal_matches_baseline():
    ents = tail_long_entries("EURUSD", freq="2h", q=0.95)
    df = build_ensemble("EURUSD", ents, freq="2h", n_bars=1)
    assert {"terminal_bps","mfe_sigma","mae_sigma","sigma_bps"}.issubset(df.columns)
    assert len(df) > 30
    # MFE >= 0 >= MAE by construction
    assert (df["mfe_sigma"] >= 0).all()
    assert (df["mae_sigma"] <= 0).all()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/repositories/behemoth/.claude/worktrees/fx-path-geometry && uv run pytest tests/fx_coint/test_path_ensemble.py -q`
Expected: FAIL `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/fx_coint/path_ensemble.py
"""Conditional and matched-unconditional 1-minute path ensembles for an edge."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.fx_coint.path_geometry_paths import build_minute_index, hold_path  # noqa: E402
from scripts.fx_coint.path_metrics import path_excursions  # noqa: E402
from scripts.fx_coint.reg_signal_hunt import (  # noqa: E402
    build_freq_bars,
    build_panel,
)
from scripts.fx_coint.tail_wfo import walk_forward  # noqa: E402


def _panel_and_closes(sym, freq):
    bars = build_freq_bars(pl.read_parquet(_REPO_ROOT / f"data/tick_bars/{sym}_1m_flow.parquet"), freq)
    panel = build_panel(bars)
    close = dict(zip(bars["bucket"].to_numpy(), bars["mid"].to_numpy(), strict=False))
    sig = dict(zip(panel["bucket"].to_numpy(), panel["sigma_h"].to_numpy(), strict=False))
    return panel, close, sig


def tail_long_entries(sym, freq="2h", q=0.95, n_folds=5):
    panel, _close, sig = _panel_and_closes(sym, freq)
    folds = walk_forward(panel, n_folds=n_folds)
    out = []
    for f in folds:
        thr = np.quantile(f["train_pred"], q)
        sel = f["test_pred"] >= thr
        for bk in f["test_bucket"][sel]:
            s = float(sig.get(bk, np.nan))
            if np.isfinite(s) and s > 0:
                out.append((bk, "long", s))
    return out


_NS_PER_DAY = 86_400_000_000_000


def offset_placebo_entries(sym, freq, signal_entries, min_off_days=3, max_off_days=60, seed=0):
    """Null = real entries shifted by a random whole-day offset (same time-of-day).

    Decouples the signal moment from the path while holding pair/hour/regime fixed.
    Whole-day shift preserves time-of-day exactly; |offset| >= min_off_days guarantees
    the shifted hold window cannot overlap the original (hold << 1 day for intraday edges,
    and >= a few days for the daily reversion edge — set min_off_days accordingly).
    """
    rng = np.random.default_rng(seed)
    panel, _close, sig = _panel_and_closes(sym, freq)
    valid = {int(np.datetime64(b, "ns").astype("int64")): b for b in panel["bucket"].to_numpy()
             if np.isfinite(sig.get(b, np.nan)) and sig.get(b, 0) > 0}
    signal_ns = {int(np.datetime64(b, "ns").astype("int64")) for b, _, _ in signal_entries}
    out = []
    for b, side, _s in signal_entries:
        b_ns = int(np.datetime64(b, "ns").astype("int64"))
        placed = False
        for _ in range(20):  # retry until a valid, non-signal, in-panel slot is found
            k = int(rng.integers(min_off_days, max_off_days + 1)) * (1 if rng.random() < 0.5 else -1)
            cand = b_ns + k * _NS_PER_DAY
            if cand in valid and cand not in signal_ns:
                out.append((valid[cand], side, float(sig.get(valid[cand]))))
                placed = True
                break
        # if no slot found in 20 tries, drop this entry (keeps the null clean)
        _ = placed
    return out


def jittered_entries(signal_entries, bars, freq, k_bars, sig):
    """Small-offset robustness: shift each entry by k_bars (can be +/-) within the panel.

    bars = panel bucket array (sorted); returns entries at bucket index +k_bars where valid.
    """
    idx_of = {int(np.datetime64(b, "ns").astype("int64")): i for i, b in enumerate(bars)}
    out = []
    for b, side, _s in signal_entries:
        i = idx_of.get(int(np.datetime64(b, "ns").astype("int64")))
        if i is None:
            continue
        j = i + k_bars
        if 0 <= j < len(bars):
            bj = bars[j]
            s = float(sig.get(bj, np.nan))
            if np.isfinite(s) and s > 0:
                out.append((bj, side, s))
    return out


def build_ensemble(sym, entries, freq, n_bars=1):
    _panel, close, _sig = _panel_and_closes(sym, freq)
    bn, mids = build_minute_index(sym)
    rows = []
    for bk, side, sigma_bps in entries:
        entry_mid = close.get(bk)
        if entry_mid is None or not np.isfinite(entry_mid):
            continue
        minutes = hold_path(bk, freq, bn, mids, n_bars=n_bars)
        ex = path_excursions(float(entry_mid), minutes, side, sigma_bps)
        if ex["n_steps"] == 0:
            continue
        rows.append({"bucket": bk, "sigma_bps": sigma_bps, **ex})
    return pd.DataFrame(rows)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/repositories/behemoth/.claude/worktrees/fx-path-geometry && uv run pytest tests/fx_coint/test_path_ensemble.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add scripts/fx_coint/path_ensemble.py tests/fx_coint/test_path_ensemble.py
git commit -m "feat(fx_coint): conditional + matched-unconditional path ensembles (2h tail-long)"
```

---

## Task 4: Distribution-shift gate (two-sample tests) + 2h tail-long CLI

**Files:**
- Create: `scripts/fx_coint/path_shift_gate.py`
- Test: `tests/fx_coint/test_path_shift_gate.py`

**Interfaces:**
- Consumes: `path_ensemble.{tail_long_entries,offset_placebo_entries,jittered_entries,build_ensemble,_panel_and_closes}`, `reg_signal_hunt.COST_BPS`.
- Produces:
  - `shift_tests(cond: np.ndarray, uncond: np.ndarray, seed=0, n_boot=2000) -> dict` — for one metric column: KS two-sample (`ks_stat`,`ks_p`), and a bootstrap mean-difference test (`mean_cond`,`mean_uncond`,`diff`,`boot_p` two-sided).
  - `gate_one_edge(sym_list, entries_fn, freq, n_bars, label, min_off_days=3, seed=0) -> dict` — pool conditional ensembles across `sym_list`, build the **offset-placebo** null per pair, run `shift_tests` on `terminal_sigma`, `mfe_sigma`, `mae_sigma`; ALSO compute the small-offset robustness probe (conditional mean of each metric at jitter k∈{-2,-1,0,1,2} bars). Return results + overall `shifted: bool` (any metric KS_p AND boot_p < 0.05/3 Bonferroni) + a `robustness` block.
  - `main()` — run `gate_one_edge` for the 2h tail-long edge over TIGHT_MAJORS; print and write `scripts/fx_coint/path_shift_results.md`.

- [ ] **Step 1: Write the failing test**

```python
# tests/fx_coint/test_path_shift_gate.py
import numpy as np
from scripts.fx_coint.path_shift_gate import shift_tests

def test_shift_detects_clear_difference():
    rng = np.random.default_rng(0)
    cond = rng.normal(0.5, 1.0, 800)
    uncond = rng.normal(0.0, 1.0, 800)
    r = shift_tests(cond, uncond, seed=1)
    assert r["ks_p"] < 0.01
    assert r["diff"] > 0.3
    assert r["boot_p"] < 0.05

def test_no_shift_when_same():
    rng = np.random.default_rng(2)
    a = rng.normal(0, 1, 800); b = rng.normal(0, 1, 800)
    r = shift_tests(a, b, seed=3)
    assert r["ks_p"] > 0.05
    assert r["boot_p"] > 0.05
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/repositories/behemoth/.claude/worktrees/fx-path-geometry && uv run pytest tests/fx_coint/test_path_shift_gate.py -q`
Expected: FAIL `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/fx_coint/path_shift_gate.py
"""Gate 1: does an edge's conditional path distribution differ from unconditional?

Run: uv run python scripts/fx_coint/path_shift_gate.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import ks_2samp

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.fx_coint.path_ensemble import (  # noqa: E402
    _panel_and_closes,
    build_ensemble,
    jittered_entries,
    offset_placebo_entries,
    tail_long_entries,
)

TIGHT_MAJORS = ["EURUSD", "GBPUSD", "USDJPY"]


def shift_tests(cond: np.ndarray, uncond: np.ndarray, seed: int = 0,
                n_boot: int = 2000) -> dict:
    cond = np.asarray(cond, float); cond = cond[np.isfinite(cond)]
    uncond = np.asarray(uncond, float); uncond = uncond[np.isfinite(uncond)]
    ks = ks_2samp(cond, uncond)
    rng = np.random.default_rng(seed)
    obs = cond.mean() - uncond.mean()
    pool = np.concatenate([cond, uncond]); nc = len(cond)
    null = np.empty(n_boot)
    for b in range(n_boot):
        p = rng.permutation(pool)
        null[b] = p[:nc].mean() - p[nc:].mean()
    boot_p = float((np.abs(null) >= abs(obs)).mean())
    return {"ks_stat": float(ks.statistic), "ks_p": float(ks.pvalue),
            "mean_cond": float(cond.mean()), "mean_uncond": float(uncond.mean()),
            "diff": float(obs), "boot_p": boot_p, "n_cond": nc, "n_uncond": len(uncond)}


def gate_one_edge(sym_list, entries_fn, freq, n_bars, label, min_off_days=3, seed=0) -> dict:
    metrics = ["terminal_sigma", "mfe_sigma", "mae_sigma"]
    cond_frames, uncond_frames = [], []
    robust = {k: [] for k in (-2, -1, 0, 1, 2)}
    for sym in sym_list:
        ents = entries_fn(sym, freq)
        cond_frames.append(build_ensemble(sym, ents, freq, n_bars=n_bars))
        plc = offset_placebo_entries(sym, freq, ents, min_off_days=min_off_days, seed=seed)
        uncond_frames.append(build_ensemble(sym, plc, freq, n_bars=n_bars))
        # small-offset robustness: mean terminal_sigma at jitter k
        panel, _c, sig = _panel_and_closes(sym, freq)
        bars = panel["bucket"].to_numpy()
        for k in robust:
            je = jittered_entries(ents, bars, freq, k, sig)
            df = build_ensemble(sym, je, freq, n_bars=n_bars)
            if len(df):
                robust[k].append(df["terminal_sigma"].to_numpy())
    cond = pd.concat(cond_frames, ignore_index=True)
    uncond = pd.concat(uncond_frames, ignore_index=True)
    res = {m: shift_tests(cond[m].to_numpy(), uncond[m].to_numpy(), seed=seed) for m in metrics}
    shifted = any(res[m]["ks_p"] < 0.05 / len(metrics) and res[m]["boot_p"] < 0.05 / len(metrics)
                  for m in metrics)
    robustness = {k: float(np.concatenate(v).mean()) if v else float("nan")
                  for k, v in robust.items()}
    return {"label": label, "n_cond": len(cond), "n_uncond": len(uncond),
            "metrics": res, "shifted": shifted, "robustness": robustness}


def _fmt(g) -> str:
    lines = [f"## {g['label']}  (n_cond={g['n_cond']} n_uncond={g['n_uncond']})  SHIFTED={g['shifted']}"]
    for m, r in g["metrics"].items():
        lines.append(f"  {m:>15}: cond={r['mean_cond']:+.3f} unc(placebo)={r['mean_uncond']:+.3f} "
                     f"diff={r['diff']:+.3f} ks_p={r['ks_p']:.4f} boot_p={r['boot_p']:.4f}")
    rob = g["robustness"]
    lines.append("  robustness terminal_sigma by jitter (bars): " +
                 " ".join(f"{k:+d}={rob[k]:+.3f}" for k in sorted(rob)))
    return "\n".join(lines)


def main():
    g = gate_one_edge(TIGHT_MAJORS, lambda s, f: tail_long_entries(s, f, q=0.95),
                      freq="2h", n_bars=1, label="2h tail-long", min_off_days=3)
    block = _fmt(g)
    print(block)
    (Path(__file__).resolve().parent / "path_shift_results.md").write_text(
        "# Path-shift gate (gate 1) results\n\n" + block + "\n")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests, then run the gate**

Run: `cd ~/repositories/behemoth/.claude/worktrees/fx-path-geometry && uv run pytest tests/fx_coint/test_path_shift_gate.py -q`
Expected: PASS (2 passed).

Then: `uv run python scripts/fx_coint/path_shift_gate.py`
Expected: prints the 2h tail-long block (cond vs uncond means, KS_p, boot_p per metric, SHIFTED=True/False) and writes `path_shift_results.md`. **Interpretation gate:** if `SHIFTED=False`, the conditional path distribution is indistinguishable from random-walk for the tail edge — record that and STOP this edge (no geometry can help). If `SHIFTED=True`, the edge proceeds to Phase B geometry optimization.

- [ ] **Step 5: Run quality gate and commit**

Run: `cd ~/repositories/behemoth/.claude/worktrees/fx-path-geometry && make quality`
Expected: ty + ruff clean (fix any lint in new files first).

```bash
git add scripts/fx_coint/path_shift_gate.py tests/fx_coint/test_path_shift_gate.py scripts/fx_coint/path_shift_results.md
git commit -m "feat(fx_coint): distribution-shift gate (gate 1) + 2h tail-long result"
```

---

## Task 5: Reversion edge config + gate-1 for the 2-3d reversion edge

**Files:**
- Modify: `scripts/fx_coint/path_ensemble.py` (add `reversion_entries`)
- Modify: `scripts/fx_coint/path_shift_gate.py` (run reversion in `main`)
- Test: `tests/fx_coint/test_path_ensemble.py` (add a reversion-entries test)

**Interfaces:**
- Produces:
  - `reversion_entries(sym, freq="1d", q=0.90, L=10, warmup=60) -> list[tuple]` — causal expanding-window tail-decile fade entries replicating `validate_reversion_cell.causal_fade` selection, returning `(entry_bucket, side, sigma_bps)` where overbought→`"short"`, oversold→`"long"`; `sigma_bps` = rolling daily return std (the fade vol scale). Uses `build_freq_bars(..., session=(0,24))` with `FREQ_MINUTES["1d"]=1440` injected.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/fx_coint/test_path_ensemble.py
def test_reversion_entries_signed_and_causal():
    from scripts.fx_coint.path_ensemble import reversion_entries
    ents = reversion_entries("EURUSD", freq="1d", q=0.90, L=10)
    assert len(ents) > 20
    sides = {side for _, side, _ in ents}
    assert sides <= {"long", "short"}
    assert all(s > 0 for _, _, s in ents)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/repositories/behemoth/.claude/worktrees/fx-path-geometry && uv run pytest tests/fx_coint/test_path_ensemble.py::test_reversion_entries_signed_and_causal -q`
Expected: FAIL `ImportError: cannot import name 'reversion_entries'`.

- [ ] **Step 3: Write minimal implementation**

Add to `scripts/fx_coint/path_ensemble.py`:

```python
def reversion_entries(sym, freq="1d", q=0.90, L=10, warmup=60):
    """Causal expanding-window tail-decile fade entries (mirrors validate_reversion_cell)."""
    from scripts.fx_coint.reg_signal_hunt import FREQ_MINUTES
    FREQ_MINUTES.setdefault("1d", 1440)
    bars = build_freq_bars(
        pl.read_parquet(_REPO_ROOT / f"data/tick_bars/{sym}_1m_flow.parquet"),
        freq, session=(0, 24))
    mid = bars["mid"].to_numpy()
    bk = bars["bucket"].to_numpy()
    r = np.empty(len(mid)); r[0] = np.nan
    r[1:] = (np.log(mid[1:]) - np.log(mid[:-1])) * 1e4
    r[~bars["contig"].to_numpy()] = np.nan
    rs = pd.Series(r)
    sig = (rs.rolling(L, min_periods=L // 2).sum()
           / (rs.rolling(20, min_periods=10).std() * np.sqrt(L))).to_numpy()
    vol = (rs.rolling(20, min_periods=10).std()).to_numpy()  # daily bps vol scale
    out, hist = [], []
    for i in range(len(mid)):
        s = sig[i]
        if len(hist) >= warmup and np.isfinite(s) and np.isfinite(vol[i]) and vol[i] > 0:
            hi = np.quantile(hist, q); lo = np.quantile(hist, 1 - q)
            if s >= hi:
                out.append((bk[i], "short", float(vol[i])))
            elif s <= lo:
                out.append((bk[i], "long", float(vol[i])))
        if np.isfinite(s):
            hist.append(s)
    return out
```

Add the reversion gate to `main()` in `scripts/fx_coint/path_shift_gate.py` (replace the existing `main`):

```python
def main():
    from scripts.fx_coint.path_ensemble import reversion_entries
    blocks = []
    g1 = gate_one_edge(TIGHT_MAJORS, lambda s, f: tail_long_entries(s, f, q=0.95),
                       freq="2h", n_bars=1, label="2h tail-long", min_off_days=3)
    blocks.append(_fmt(g1))
    # reversion: daily bars, hold 2 bars (~2 days); offset must clear the 2-day hold
    g2 = gate_one_edge(TIGHT_MAJORS, lambda s, f: reversion_entries(s, f, q=0.90, L=10),
                       freq="1d", n_bars=2, label="2-3d reversion", min_off_days=5)
    blocks.append(_fmt(g2))
    out = "\n\n".join(blocks)
    print(out)
    (Path(__file__).resolve().parent / "path_shift_results.md").write_text(
        "# Path-shift gate (gate 1) results\n\n" + out + "\n")
```

Note: `gate_one_edge`'s `entries_fn` is called as `entries_fn(sym, freq)`; the reversion lambda ignores extra kwargs by fixing `q`/`L`. `build_ensemble`/`unconditional_entries` already accept `freq="1d"` since `hold_path` uses `FREQ_MINUTES[freq]` (now including `"1d"`).

- [ ] **Step 4: Run tests, then re-run the gate**

Run: `cd ~/repositories/behemoth/.claude/worktrees/fx-path-geometry && uv run pytest tests/fx_coint/test_path_ensemble.py -q`
Expected: PASS (4 passed).

Then: `uv run python scripts/fx_coint/path_shift_gate.py`
Expected: prints BOTH edge blocks with SHIFTED verdicts; writes `path_shift_results.md`. Record each edge's verdict.

- [ ] **Step 5: Run quality and commit**

Run: `cd ~/repositories/behemoth/.claude/worktrees/fx-path-geometry && make quality`
Expected: clean.

```bash
git add scripts/fx_coint/path_ensemble.py scripts/fx_coint/path_shift_gate.py tests/fx_coint/test_path_ensemble.py scripts/fx_coint/path_shift_results.md
git commit -m "feat(fx_coint): reversion edge config + gate-1 for both edges"
```

---

## Self-Review notes

- **Spec coverage:** §2a conditional ensemble → Task 3; §2b offset-placebo null → Task 3 (`offset_placebo_entries`); §2b2 small-offset robustness → Task 3 (`jittered_entries`) + Task 4 (`gate_one_edge` robustness block); §2c bracket evaluator → Phase B (NOT this plan — gate 1 needs only excursions); §3 causal selection → Tasks 3/5 (walk_forward OOS, expanding decile); §4 gate 1 → Tasks 4/5; §5 phasing (Phase A only here) → whole plan. Bracket evaluator, optimizer, gates 2-3 are Phase B (separate plan).
- **Type consistency:** entries are `list[tuple[np.datetime64, str, float]]` everywhere; `build_ensemble` returns a DataFrame with `terminal_sigma/mfe_sigma/mae_sigma/terminal_bps`; `shift_tests` consumes 1-D arrays of those columns.
- **Offset discipline:** the placebo is a whole-day shift (preserves time-of-day), `|offset| ≥ min_off_days` so the shifted hold window cannot overlap the original (3 days for the 2h edge whose hold ≪ 1 day; 5 days for the reversion edge whose hold ≈ 2 days). Offsets are used ONLY for the null and the ±1–3 bar robustness probe — never to inflate sample size (data augmentation is explicitly rejected; it would create correlated near-duplicates and false power).
- **Known risk:** `offset_placebo_entries` drops an entry if no valid non-signal slot is found in 20 tries; the placebo n may be slightly below the conditional n — acceptable (KS/permutation handle unequal n). The bucket key types (np.datetime64[ns]) must match between `close`/`sig` dict keys and `f["test_bucket"]`; if a KeyError/dtype mismatch appears, normalize both to `datetime64[ns]` in `_panel_and_closes` and the entries.
- **Decision wiring:** Phase A's deliverable is the gate-1 verdict per edge. A `SHIFTED=False` is a legitimate early STOP (cheap kill); `SHIFTED=True` greenlights Phase B. Either way the result is recorded in `path_shift_results.md`.
