# ERA Fair-Price Prediction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `fair` mode to `scripts/era_scalp/`: programs emit a per-bar predicted mispricing `(fair − mid)` in pips; score = out-of-sample **information coefficient** (correlation with the forward de-noised mid), embargoed + two-sided BH-FDR — a calibrated fair-value/efficient-price estimator, decoupled from execution cost.

**Architecture:** Reuse the `scripts/era/` engine (`puct`, `select.bh_fdr`, `llm` with `rules=`), `era_scalp/context.FeatureContext`, and `era_scalp/sandbox` (`run_program`/`causality_probe` with `required_fn="fair"`). New files: an IC harness, a scorer, micro-price seeds, a prompt, a split loader extension, and a driver. Directional + range-harvest modes untouched.

**Tech Stack:** Python 3.12, numpy, pandas, pyarrow, pytest, `uv run`. Generator `qwen3-coder-next` via `scripts/cheap_llm.sh` (live run only; unit tests use seeds / mocked writers).

**Spec:** `docs/superpowers/specs/2026-05-31-era-fair-price-prediction-design.md`

**Prerequisite / branch:** branch off `main` (which has `era_scalp` + the `required_fn` sandbox from #280). Suggested branch `era-fair-price`. (The fair-price spec doc currently sits on the `era-range-harvest` branch; bring it across or leave it — harmless.)

**Causal contract:** `fair(ctx) -> np.ndarray` is a per-bar predicted mispricing in pips; `fair[k]` depends only on bars ≤ k (causality probe enforces). Programs are **level-free** — they use returns (`vel_pips_h1`) + microstructure, never raw price. The harness owns `mid` only to build the label.

**Reused signatures (on `main`):** `era_scalp.context.FeatureContext(X, names, hour=None)`; `era_scalp.sandbox.run_program(src, ctx, timeout=10.0, required_fn="signal")`, `causality_probe(src, ctx, clean, n_cuts=2, seed=0, required_fn="signal")`; `era_scalp.load_splits.WHITELIST`, `cap_recent`; `era.puct.Node/puct_search`; `era.select.bh_fdr`; `era.llm.propose_program(...rules=)/recombine_program(...rules=)`.

---

## File Structure

- Create: `scripts/era_scalp/fair_harness.py` — `W_GRID`, `forward_dev`, `info_coefficient`, `fair_node_score`, `ic_pvalue`, `fair_diagnostics`.
- Modify: `scripts/era_scalp/load_splits.py` — add `FairSplitData` + `build_fair_splits` (mid + embargo).
- Create: `scripts/era_scalp/fair_score.py` — `FairScorer`.
- Create: `scripts/era_scalp/fair_seeds.py` — `FAIR_SEED_PROGRAMS`, `BASELINE_SEED_NAMES`, `RESEARCH_IDEAS`.
- Create: `scripts/era_scalp/fair_prompt.py` — `FAIR_RULES`, `FAIR_FEATURE_NAMES`.
- Create: `scripts/era_scalp/run_era_fair.py` — driver.
- Tests under `tests/era_scalp/`: `test_fair_harness.py`, `test_load_splits_fair.py`, `test_fair_score.py`, `test_fair_seeds.py`, `test_fair_prompt.py`, `test_fair_integration.py`.

---

## Task F1: IC harness

**Files:** Create `scripts/era_scalp/fair_harness.py`; Test `tests/era_scalp/test_fair_harness.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/era_scalp/test_fair_harness.py
import numpy as np

from scripts.era_scalp.fair_harness import (
    fair_diagnostics, fair_node_score, forward_dev, ic_pvalue, info_coefficient,
)


def test_forward_dev_matches_naive():
    rng = np.random.default_rng(0)
    mid = 1.1 + np.cumsum(rng.standard_normal(200)) * 1e-4
    W, pip = 10, 1e-4
    fd = forward_dev(mid, pip, W)
    # naive reference
    ref = np.full(len(mid), np.nan)
    for t in range(len(mid)):
        if t + W <= len(mid) - 1:
            ref[t] = (mid[t + 1:t + 1 + W].mean() - mid[t]) / pip
    fin = np.isfinite(ref)
    assert np.allclose(fd[fin], ref[fin], atol=1e-9)
    assert not np.isfinite(fd[-1])  # last bars have no full forward window


def test_info_coefficient_perfect_and_random():
    rng = np.random.default_rng(1)
    realized = rng.standard_normal(500)
    ic_perfect, n = info_coefficient(realized.copy(), realized)
    assert ic_perfect > 0.99 and n == 500
    ic_rand, _ = info_coefficient(rng.standard_normal(500), realized)
    assert abs(ic_rand) < 0.2


def test_node_score_sign_agnostic():
    rng = np.random.default_rng(2)
    mid = 1.1 + np.cumsum(rng.standard_normal(800)) * 1e-4
    pip = 1e-4
    rd = forward_dev(mid, pip, 20)
    pred = np.where(np.isfinite(rd), rd, 0.0)
    s_pos = fair_node_score(pred, mid, pip, [20, 60])
    s_neg = fair_node_score(-pred, mid, pip, [20, 60])
    assert s_pos > 0 and abs(s_pos - s_neg) < 1e-6  # |IC| -> sign agnostic


def test_ic_pvalue():
    assert ic_pvalue(0.0, 1000) > 0.5
    assert ic_pvalue(0.3, 1000) < 0.01
    assert ic_pvalue(0.9, 10) == 1.0  # too few points


def test_fair_diagnostics_keys():
    rng = np.random.default_rng(3)
    mid = 1.1 + np.cumsum(rng.standard_normal(400)) * 1e-4
    rd = forward_dev(mid, 1e-4, 20)
    pred = np.where(np.isfinite(rd), rd, 0.0)
    tm = np.array(["2025-01"] * 200 + ["2025-02"] * 200)
    d = fair_diagnostics(pred, mid, 1e-4, tm, 20)
    assert set(d) >= {"ic", "n_eff", "ic_by_month_consistency", "mean_abs_pred_pips",
                      "dev_sign_hitrate"}
    assert d["ic"] > 0.9
```

- [ ] **Step 2: Run — expect FAIL** (`ModuleNotFoundError`). `uv run pytest tests/era_scalp/test_fair_harness.py -q`

- [ ] **Step 3: Create `scripts/era_scalp/fair_harness.py`**

```python
from __future__ import annotations

import math

import numpy as np
import pandas as pd

# forward-window grid (bars) for the de-noised target y_fair
W_GRID = [20, 60, 200]
_MIN_PTS = 30


def forward_dev(mid: np.ndarray, pip: float, W: int) -> np.ndarray:
    """realized_dev[t] = (mean(mid[t+1..t+W]) - mid[t]) / pip; NaN where no full window."""
    mid = np.asarray(mid, float)
    n = mid.shape[0]
    out = np.full(n, np.nan)
    if n <= W:
        return out
    cm = np.concatenate(([0.0], np.cumsum(mid)))  # cm[i] = sum(mid[:i])
    t = np.arange(n)
    valid = t + W <= n - 1
    tv = t[valid]
    yfair = (cm[tv + W + 1] - cm[tv + 1]) / W
    out[tv] = (yfair - mid[tv]) / pip
    return out


def info_coefficient(pred: np.ndarray, realized: np.ndarray) -> tuple[float, int]:
    p = np.asarray(pred, float)
    r = np.asarray(realized, float)
    m = np.isfinite(p) & np.isfinite(r)
    n = int(m.sum())
    if n < _MIN_PTS:
        return float("nan"), n
    pp, rr = p[m], r[m]
    if pp.std() == 0 or rr.std() == 0:
        return float("nan"), n
    return float(np.corrcoef(pp, rr)[0, 1]), n


def fair_node_score(pred: np.ndarray, mid: np.ndarray, pip: float, w_grid=None) -> float:
    """Continuous, sign-agnostic per-node signal: best |IC|*sqrt(n_eff) over the W grid."""
    w_grid = w_grid or W_GRID
    best = 0.0
    for W in w_grid:
        ic, n = info_coefficient(pred, forward_dev(mid, pip, W))
        if np.isfinite(ic):
            best = max(best, abs(ic) * math.sqrt(n))
    return float(best)


def ic_pvalue(ic: float, n: int) -> float:
    """Two-sided p-value for a correlation via the normal approx (no scipy)."""
    if n < _MIN_PTS or not np.isfinite(ic) or abs(ic) >= 1.0:
        return 1.0
    t = ic * math.sqrt(n - 2) / math.sqrt(1.0 - ic * ic)
    return float(math.erfc(abs(t) / math.sqrt(2.0)))


def fair_diagnostics(pred, mid, pip, test_month, W) -> dict:
    rd = forward_dev(mid, pip, W)
    p = np.asarray(pred, float)
    m = np.isfinite(p) & np.isfinite(rd)
    n = int(m.sum())
    if n < _MIN_PTS:
        return {"ic": float("nan"), "n_eff": n, "ic_by_month_consistency": float("nan"),
                "mean_abs_pred_pips": float("nan"), "dev_sign_hitrate": float("nan")}
    ic, _ = info_coefficient(p, rd)
    pp, rr = p[m], rd[m]
    months = np.asarray(test_month)[m]
    by = pd.DataFrame({"p": pp, "r": rr, "mo": months}).groupby("mo")
    mics = by.apply(lambda g: float(np.corrcoef(g["p"], g["r"])[0, 1])
                    if len(g) >= _MIN_PTS and g["p"].std() and g["r"].std() else np.nan)
    mics = mics.dropna()
    consist = float((np.sign(mics) == np.sign(ic)).mean()) if len(mics) else float("nan")
    return {
        "ic": float(ic),
        "n_eff": n,
        "ic_by_month_consistency": consist,
        "mean_abs_pred_pips": float(np.mean(np.abs(pp))),
        "dev_sign_hitrate": float((np.sign(pp) == np.sign(rr)).mean()),
    }
```

- [ ] **Step 4: Run — expect PASS.** `uv run pytest tests/era_scalp/test_fair_harness.py -q`

- [ ] **Step 5: Commit**

```bash
git add scripts/era_scalp/fair_harness.py tests/era_scalp/test_fair_harness.py
git commit -m "feat(era-scalp): fair-price IC harness (forward_dev, info_coefficient, node_score, ic_pvalue)"
```

---

## Task F2: Fair split loader

**Files:** Modify `scripts/era_scalp/load_splits.py`; Test `tests/era_scalp/test_load_splits_fair.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/era_scalp/test_load_splits_fair.py
import numpy as np
import pandas as pd

from scripts.era_scalp.load_splits import WHITELIST, build_fair_splits


def _write_fake(path, n=3000):
    rng = np.random.default_rng(0)
    ts = pd.to_datetime(np.r_[
        pd.date_range("2023-06-01", periods=n // 3, freq="5min", tz="UTC"),
        pd.date_range("2024-06-01", periods=n // 3, freq="5min", tz="UTC"),
        pd.date_range("2025-06-01", periods=n - 2 * (n // 3), freq="5min", tz="UTC"),
    ])
    cols = {c: rng.standard_normal(n) for c in WHITELIST}
    cols["close_ts"] = ts
    cols["close_bid"] = 1.1 + rng.standard_normal(n) * 1e-3
    cols["close_ask"] = cols["close_bid"] + 3e-5
    pd.DataFrame(cols).to_parquet(path)


def test_build_fair_splits_mid_and_embargo(tmp_path):
    p = tmp_path / "EURUSD_100tick_velocity.parquet"
    _write_fake(p)
    splits = build_fair_splits("EURUSD", p, embargo=50,
                               train=("2023",), validation=("2024",), holdout=("2025",))
    for name in ("train", "validation", "holdout"):
        d = splits[name]
        assert d.X.shape[1] == len(WHITELIST)
        assert len(d.mid) == d.X.shape[0] == len(d.test_month)
        assert "close_bid" not in d.names and "close_ask" not in d.names
        assert np.all(d.mid > 1.0)  # mid is a price
    full_train = (pd.read_parquet(p)["close_ts"].dt.year == 2023).sum()
    assert splits["train"].X.shape[0] == full_train - 50  # embargo tail
```

- [ ] **Step 2: Run — expect FAIL.** `uv run pytest tests/era_scalp/test_load_splits_fair.py -q`

- [ ] **Step 3: Edit `scripts/era_scalp/load_splits.py`** — add (after the existing `build_range_splits`):

```python
@dataclass
class FairSplitData:
    X: np.ndarray
    names: list[str]
    hour: np.ndarray | None
    mid: np.ndarray
    test_month: np.ndarray


def build_fair_splits(
    symbol: str,
    parquet_path: Path,
    embargo: int = 200,
    train=("2018", "2019", "2020", "2021", "2022", "2023"),
    validation=("2024",),
    holdout=("2025", "2026"),
) -> dict[str, FairSplitData]:
    df = pd.read_parquet(parquet_path)
    df["close_ts"] = pd.to_datetime(df["close_ts"], utc=True, errors="coerce")
    df = df[df["close_ts"].notna()].sort_values("close_ts").reset_index(drop=True)
    df["mid"] = (df["close_bid"] + df["close_ask"]) / 2.0
    df["year"] = df["close_ts"].dt.strftime("%Y")
    df["test_month"] = df["close_ts"].dt.strftime("%Y-%m")

    def _split(years, embargo_tail: bool) -> FairSplitData:
        d = df[df["year"].isin(years)].reset_index(drop=True)
        if embargo_tail and len(d) > embargo:
            d = d.iloc[: len(d) - embargo].reset_index(drop=True)
        return FairSplitData(
            X=d[WHITELIST].to_numpy(float),
            names=list(WHITELIST),
            hour=d["hour_utc"].to_numpy(float),
            mid=d["mid"].to_numpy(float),
            test_month=d["test_month"].to_numpy(),
        )

    return {
        "train": _split(train, embargo_tail=True),
        "validation": _split(validation, embargo_tail=True),
        "holdout": _split(holdout, embargo_tail=False),
    }
```

(`mid` and the raw bid/ask are NOT in `WHITELIST`, so they never enter `FeatureContext` — only the harness-side `mid` array carries them.)

- [ ] **Step 4: Run — expect PASS.** Also run `uv run pytest tests/era_scalp/test_load_splits.py tests/era_scalp/test_load_splits_range.py -q` to confirm no regression.

- [ ] **Step 5: Commit**

```bash
git add scripts/era_scalp/load_splits.py tests/era_scalp/test_load_splits_fair.py
git commit -m "feat(era-scalp): FairSplitData + build_fair_splits (mid + embargo)"
```

---

## Task F3: FairScorer

**Files:** Create `scripts/era_scalp/fair_score.py`; Test `tests/era_scalp/test_fair_score.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/era_scalp/test_fair_score.py
import numpy as np

from scripts.era_scalp.fair_score import FairScorer
from scripts.era_scalp.load_splits import WHITELIST, FairSplitData


def _data(n=600, seed=0):
    rng = np.random.default_rng(seed)
    mid = 1.1 + np.cumsum(rng.standard_normal(n)) * 1e-4
    return FairSplitData(
        X=rng.standard_normal((n, len(WHITELIST))), names=list(WHITELIST),
        hour=(np.arange(n) % 24).astype(float), mid=mid,
        test_month=np.array(["2024-01"] * (n // 2) + ["2024-02"] * (n - n // 2)),
    )


def test_fair_scorer_runs_causal():
    sc = FairScorer(splits={"validation": _data()}, symbol="EURUSD")
    s, _ = sc.score("def fair(ctx):\n    return ctx.col('vel_pips_h1')\n", "validation")
    assert np.isfinite(s) and s >= 0.0


def test_fair_scorer_rejects_noncausal():
    sc = FairScorer(splits={"validation": _data()}, symbol="EURUSD")
    fwd = ("def fair(ctx):\n"
           "    x = ctx.col('vel_pips_h1').copy()\n"
           "    x[:-1] = x[1:]\n"
           "    return x\n")
    s, logs = sc.score(fwd, "validation")
    assert s == -1e6 and "causal" in logs.lower()


def test_fair_scorer_requires_fair_not_signal():
    sc = FairScorer(splits={"validation": _data()}, symbol="EURUSD")
    s, logs = sc.score("def signal(ctx):\n    return ctx.col('vel_pips_h1')\n", "validation")
    assert s == -1e6 and "fair" in logs.lower()
```

- [ ] **Step 2: Run — expect FAIL.** `uv run pytest tests/era_scalp/test_fair_score.py -q`

- [ ] **Step 3: Create `scripts/era_scalp/fair_score.py`**

```python
from __future__ import annotations

from scripts.era_scalp.context import FeatureContext
from scripts.era_scalp.fair_harness import W_GRID, fair_node_score
from scripts.era_scalp.sandbox import causality_probe, run_program

_PIP = {"EURUSD": 1e-4, "GBPUSD": 1e-4, "AUDUSD": 1e-4,
        "USDCHF": 1e-4, "USDCAD": 1e-4, "USDJPY": 1e-2}


class FairScorer:
    def __init__(self, splits, symbol: str, timeout: float = 10.0):
        self.splits = splits
        self.pip = _PIP[str(symbol).upper()]
        self.timeout = timeout

    def score(self, src: str, split: str) -> tuple[float, str]:
        d = self.splits[split]
        ctx = FeatureContext(X=d.X, names=d.names, hour=d.hour)
        pred, err, logs = run_program(src, ctx, timeout=self.timeout, required_fn="fair")
        if err is not None:
            return -1e6, f"static_check/exec: {err}" if "static_check" in (
                err or ""
            ) else f"exec: {err}\n{logs}"
        ok, reason = causality_probe(src, ctx, pred, required_fn="fair")
        if not ok:
            return -1e6, f"causality_probe: {reason}"
        return fair_node_score(pred, d.mid, self.pip, W_GRID), logs
```

- [ ] **Step 4: Run — expect PASS.** `uv run pytest tests/era_scalp/test_fair_score.py -q`

- [ ] **Step 5: Commit**

```bash
git add scripts/era_scalp/fair_score.py tests/era_scalp/test_fair_score.py
git commit -m "feat(era-scalp): FairScorer (causal probe + IC node score over W grid)"
```

---

## Task F4: Fair-value seeds

**Files:** Create `scripts/era_scalp/fair_seeds.py`; Test `tests/era_scalp/test_fair_seeds.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/era_scalp/test_fair_seeds.py
import numpy as np

from scripts.era_scalp.context import FeatureContext
from scripts.era_scalp.fair_seeds import BASELINE_SEED_NAMES, FAIR_SEED_PROGRAMS, RESEARCH_IDEAS
from scripts.era_scalp.load_splits import WHITELIST
from scripts.era_scalp.sandbox import causality_probe, run_program


def _ctx(n=400, seed=1):
    rng = np.random.default_rng(seed)
    return FeatureContext(X=rng.standard_normal((n, len(WHITELIST))),
                          names=list(WHITELIST), hour=(np.arange(n) % 24).astype(float))


def test_expected_seeds_present():
    for name in ("ewma_denoise_dev", "bounce_reversal_dev", "microprice_imbalance_dev",
                 "trailing_anchor_dev", "ofi_adjusted_dev"):
        assert name in FAIR_SEED_PROGRAMS
    for b in BASELINE_SEED_NAMES:
        assert b in FAIR_SEED_PROGRAMS


def test_all_seeds_run_causal_finite():
    ctx = _ctx()
    bad = []
    for name, src in FAIR_SEED_PROGRAMS.items():
        pred, err, _ = run_program(src, ctx, required_fn="fair")
        if err is not None:
            bad.append(f"{name}: {err}")
            continue
        ok, reason = causality_probe(src, ctx, pred, required_fn="fair")
        if not ok:
            bad.append(f"{name}: {reason}")
            continue
        if not np.isfinite(pred[np.isfinite(pred)]).all() or pred.shape[0] != ctx.n_bars:
            bad.append(f"{name}: bad output")
    assert not bad, "; ".join(bad)


def test_research_ideas_cite_streams():
    blob = " ".join(RESEARCH_IDEAS).lower()
    for kw in ["micro-price", "efficient price", "bid-ask bounce", "order flow", "combine"]:
        assert kw in blob, f"missing idea keyword: {kw}"
```

- [ ] **Step 2: Run — expect FAIL.** `uv run pytest tests/era_scalp/test_fair_seeds.py -q`

- [ ] **Step 3: Create `scripts/era_scalp/fair_seeds.py`** (level-free: use `vel_pips_h1` return path + microstructure; emit pips; copy verbatim)

```python
"""Fair-price (mispricing) seeds — predict (fair - mid) in pips, level-free, causal.

Streams: efficient-price denoising (Hasbrouck), bid-ask bounce (Roll 1984), micro-price
imbalance (Stoikov 2018), trailing anchor / mean reversion, OFI tilt (Cont-Kukanov-Stoikov;
Sirignano-Cont). Programs use the return series (vel_pips_h1) + microstructure only — never an
absolute price — so the predicted deviation is a stationary pip quantity.
"""

FAIR_SEED_PROGRAMS: dict[str, str] = {
    # fair = EWMA of the relative price path; dev = ewma(path) - path (level cancels)
    "ewma_denoise_dev": (
        "def fair(ctx):\n"
        "    r = ctx.col('vel_pips_h1'); n = r.shape[0]; a = 0.05\n"
        "    p = np.cumsum(np.where(np.isfinite(r), r, 0.0))  # relative path (pips)\n"
        "    ew = np.empty(n); acc = p[0]\n"
        "    for i in range(n):\n"
        "        acc = (1 - a) * acc + a * p[i]; ew[i] = acc\n"
        "    return ew - p  # >0 => mid below fair => expect up-reversion\n"
    ),
    # bid-ask bounce: recent return is partly transient overshoot; fade it
    "bounce_reversal_dev": (
        "def fair(ctx):\n"
        "    r = ctx.col('vel_pips_h1')\n"
        "    return -1.0 * np.where(np.isfinite(r), r, 0.0)\n"
    ),
    # Stoikov micro-price proxy: fair tilts toward where the bar's flow/ticks cluster
    "microprice_imbalance_dev": (
        "def fair(ctx):\n"
        "    imb = ctx.col('hl_pos_delta_tick'); sgn = ctx.col('bar_return_sign')\n"
        "    x = np.where(np.isfinite(imb), imb, 0.0)\n"
        "    s = np.where(np.isfinite(sgn), sgn, 0.0)\n"
        "    return x * np.abs(s)  # imbalance magnitude, signed by bar direction proxy\n"
    ),
    # trailing-mean anchor: dev = trailing-mean(path, W) - path (causal, cumsum)
    "trailing_anchor_dev": (
        "def fair(ctx):\n"
        "    r = ctx.col('vel_pips_h1'); n = r.shape[0]; W = 60\n"
        "    p = np.cumsum(np.where(np.isfinite(r), r, 0.0))\n"
        "    k = np.arange(n); lo = np.maximum(0, k - W); m = (k - lo).astype(float)\n"
        "    ms = np.where(m > 0, m, 1.0)\n"
        "    cp = np.concatenate(([0.0], np.cumsum(p)))\n"
        "    anchor = (cp[k] - cp[lo]) / ms  # trailing mean of path (excl current)\n"
        "    out = anchor - p\n"
        "    out[m < 20] = np.nan\n"
        "    return out\n"
    ),
    # OFI tilt: signed order-flow EWMA; persistent flow => fair moved (same sign),
    # so dev ~ -ewma(flow) (mid lags fair when flow persistent)
    "ofi_adjusted_dev": (
        "def fair(ctx):\n"
        "    sgn = ctx.col('bar_return_sign'); vol = ctx.col('tick_volume')\n"
        "    n = sgn.shape[0]; a = 0.1\n"
        "    flow = np.where(np.isfinite(sgn) & np.isfinite(vol), sgn * np.sqrt(np.abs(vol)), 0.0)\n"
        "    ew = np.empty(n); acc = 0.0\n"
        "    for i in range(n):\n"
        "        acc = (1 - a) * acc + a * flow[i]; ew[i] = acc\n"
        "    return ew\n"
    ),
}

BASELINE_SEED_NAMES = ("ewma_denoise_dev", "bounce_reversal_dev",
                       "microprice_imbalance_dev", "trailing_anchor_dev")

RESEARCH_IDEAS: list[str] = [
    "Efficient price denoising (Hasbrouck): the observed mid = efficient price (martingale) + "
    "transient noise; estimate fair by low-pass filtering the relative return path (EWMA) and "
    "predict dev = smoothed - path.",
    "Bid-ask bounce (Roll 1984): a move smaller than the spread is mostly transient bounce; the "
    "fair price lags the last print, so dev reverses the recent return.",
    "Micro-price (Stoikov 2018): fair sits toward the heavier side of flow; tilt the deviation by "
    "tick-position / order imbalance (hl_pos_delta_tick, bar_return_sign, tick_volume).",
    "Trailing anchor / mean reversion: fair as a causal trailing mean of the price path; dev = "
    "anchor - path.",
    "Order flow (Cont-Kukanov-Stoikov; Sirignano-Cont): persistent signed flow means fair has "
    "moved (mid lags); transient flow means overshoot (mid leads) - separate the two.",
    "Combine: blend an EWMA-denoised fair with a micro-price imbalance tilt and a bounce "
    "correction; the best estimator mixes denoising, imbalance, and reversal.",
]
```

- [ ] **Step 4: Run — expect PASS.** `uv run pytest tests/era_scalp/test_fair_seeds.py -q`

  Then a 20k-bar perf check (guard O(n²)):
  `uv run python -c "import numpy as np; from scripts.era_scalp.context import FeatureContext; from scripts.era_scalp.load_splits import WHITELIST; from scripts.era_scalp.fair_seeds import FAIR_SEED_PROGRAMS as S; from scripts.era_scalp.sandbox import run_program; import time; ctx=FeatureContext(X=np.random.default_rng(0).standard_normal((20000,len(WHITELIST))),names=list(WHITELIST),hour=(np.arange(20000)%24).astype(float));\nimport sys\n[print(k, ('%.2fs'%((lambda t0: (run_program(v,ctx,required_fn='fair'),time.time()-t0)[1])(time.time())))) for k,v in S.items()]"`
  Expected: each < ~2s (all are O(n)).

- [ ] **Step 5: Commit**

```bash
git add scripts/era_scalp/fair_seeds.py tests/era_scalp/test_fair_seeds.py
git commit -m "feat(era-scalp): fair-value seeds (denoise/bounce/micro-price/anchor/OFI) + ideas"
```

---

## Task F5: Fair prompt

**Files:** Create `scripts/era_scalp/fair_prompt.py`; Test `tests/era_scalp/test_fair_prompt.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/era_scalp/test_fair_prompt.py
def test_fair_rules_cover_contract():
    from scripts.era.llm import build_prompt
    from scripts.era_scalp.fair_prompt import FAIR_FEATURE_NAMES, FAIR_RULES

    p = build_prompt("def fair(ctx):\n    return ctx.col('vel_pips_h1')\n", 0.0, "", "idea",
                     rules=FAIR_RULES).lower()
    assert "fair(ctx)" in p
    assert "mispricing" in p or "fair - mid" in p or "fair minus mid" in p
    assert "pip" in p
    assert "future" in p and ("trailing" in p or "expanding" in p or "ewma" in p)
    assert "vel_pips_h1" in p
    assert "y_fwd" not in " ".join(FAIR_FEATURE_NAMES)
```

- [ ] **Step 2: Run — expect FAIL.** `uv run pytest tests/era_scalp/test_fair_prompt.py -q`

- [ ] **Step 3: Create `scripts/era_scalp/fair_prompt.py`**

```python
from __future__ import annotations

from scripts.era_scalp.load_splits import WHITELIST

FAIR_FEATURE_NAMES: list[str] = list(WHITELIST)

FAIR_RULES = (
    "You write `fair(ctx) -> np.ndarray` for 100-tick FX fair-price estimation.\n"
    "Return a per-bar predicted MISPRICING (fair - mid) in PIPS: sign = the direction mid is\n"
    "mispriced (positive => mid is BELOW fair => fair is higher), magnitude = how far. np.nan\n"
    "= abstain on that bar. You are NOT predicting the next tick; you estimate the deviation of\n"
    "the current mid from the efficient (fair) price, which is scored by its correlation with\n"
    "the realized de-noised future move over thousands of bars.\n"
    "LEVEL-FREE: you never see an absolute price. Use the RETURN series (vel_pips_h1, pips) and\n"
    "microstructure features. To denoise/anchor, build a RELATIVE path p = np.cumsum(vel_pips_h1)\n"
    "and subtract its own EWMA / trailing-mean (the origin cancels). `np` is available, NO imports.\n"
    "ctx.col(name) gives a causal per-bar feature; ctx.X is (n_bars x n_feat); ctx.n_bars; ctx.hour.\n"
    "Causal features (all backward/as-of, NEVER forward):\n"
    f"  {', '.join(FAIR_FEATURE_NAMES)}\n"
    "Use the time axis causally (trailing/expanding/EWMA over bars <= k only; never x[k:], no\n"
    "centered windows, no full-sample stats). A causality probe perturbs future rows and REJECTS\n"
    "any program whose past output changes.\n"
    "Ingredients (recent literature): EWMA/efficient-price denoising (Hasbrouck), bid-ask bounce\n"
    "reversal (Roll), micro-price imbalance tilt (Stoikov), trailing anchor, order-flow tilt\n"
    "(persistent vs transient). The best estimator usually BLENDS denoising + imbalance + bounce.\n"
    "PERFORMANCE: ~50k bars, run 3x; prefer vectorised cumsum windows over per-bar loops (a single\n"
    "O(n) EWMA pass is fine); >10s is REJECTED. Output ONLY one ```python code block.\n"
)
```

- [ ] **Step 4: Run — expect PASS.** `uv run pytest tests/era_scalp/test_fair_prompt.py -q`

- [ ] **Step 5: Commit**

```bash
git add scripts/era_scalp/fair_prompt.py tests/era_scalp/test_fair_prompt.py
git commit -m "feat(era-scalp): fair-price generator prompt (mispricing contract + ingredients)"
```

---

## Task F6: Driver

**Files:** Create `scripts/era_scalp/run_era_fair.py`; Test `tests/era_scalp/test_fair_integration.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/era_scalp/test_fair_integration.py
import numpy as np

from scripts.era_scalp.load_splits import WHITELIST, FairSplitData
from scripts.era_scalp.run_era_fair import finalize_selection, run_search, select_seed_programs


def _data(n=600, seed=0):
    rng = np.random.default_rng(seed)
    mid = 1.1 + np.cumsum(rng.standard_normal(n)) * 1e-4
    return FairSplitData(
        X=rng.standard_normal((n, len(WHITELIST))), names=list(WHITELIST),
        hour=(np.arange(n) % 24).astype(float), mid=mid,
        test_month=np.array(["2024-01"] * (n // 2) + ["2024-02"] * (n - n // 2)),
    )


def test_select_seed_programs_ablation():
    full = select_seed_programs(no_baseline=False)
    ablated = select_seed_programs(no_baseline=True)
    for b in ("ewma_denoise_dev", "bounce_reversal_dev", "microprice_imbalance_dev",
              "trailing_anchor_dev"):
        assert b in full and b not in ablated
    assert "ofi_adjusted_dev" in ablated


def test_finalize_applies_bh_fdr():
    # winner: high-IC (n=400); null: zero-IC. finalize keeps winner only.
    cand = {"winner": (0.30, 400), "null": (0.001, 400)}
    survivors = finalize_selection(cand, q=0.10)
    assert "winner" in survivors and "null" not in survivors


def test_run_search_with_mocked_writer():
    splits = {"validation": _data(), "holdout": _data(seed=2)}

    def fake_writer(parent_src, parent_score, logs, idea, cache_dir, rules=None, caller=None):
        return "def fair(ctx):\n    return ctx.col('vel_pips_h1')\n"

    nodes = run_search(splits, symbol="EURUSD", budget=3, writer=fake_writer, p_recombine=0.0)
    assert len(nodes) >= 3
    assert all(np.isfinite(n.score) for n in nodes)
```

- [ ] **Step 2: Run — expect FAIL.** `uv run pytest tests/era_scalp/test_fair_integration.py -q`

- [ ] **Step 3: Create `scripts/era_scalp/run_era_fair.py`**

```python
from __future__ import annotations

import argparse
import random
from pathlib import Path

import numpy as np

from scripts.era.llm import propose_program, recombine_program
from scripts.era.puct import Node, puct_search
from scripts.era.select import bh_fdr
from scripts.era_scalp.context import FeatureContext
from scripts.era_scalp.fair_harness import (
    W_GRID, fair_diagnostics, forward_dev, ic_pvalue, info_coefficient,
)
from scripts.era_scalp.fair_prompt import FAIR_RULES
from scripts.era_scalp.fair_score import FairScorer, _PIP
from scripts.era_scalp.fair_seeds import BASELINE_SEED_NAMES, FAIR_SEED_PROGRAMS, RESEARCH_IDEAS
from scripts.era_scalp.sandbox import run_program


def select_seed_programs(no_baseline: bool = False) -> dict:
    if not no_baseline:
        return dict(FAIR_SEED_PROGRAMS)
    return {k: v for k, v in FAIR_SEED_PROGRAMS.items() if k not in BASELINE_SEED_NAMES}


def finalize_selection(cand_ic_n: dict, q: float = 0.10) -> list[str]:
    """cand_ic_n: name -> (holdout_ic, n_eff). BH-FDR over two-sided IC p-values."""
    names = list(cand_ic_n)
    pvals = np.array([ic_pvalue(cand_ic_n[n][0], cand_ic_n[n][1]) for n in names])
    keep = bh_fdr(pvals, q=q)
    return [n for n, k in zip(names, keep, strict=True) if k]


def summarize_rejections(nodes) -> dict:
    rej = {"total": len(nodes), "rejected": 0, "timeout": 0,
           "causality": 0, "static_or_exec": 0, "other": 0}
    for nd in nodes:
        if nd.score > -1e6 + 1.0:
            continue
        rej["rejected"] += 1
        lg = (nd.logs or "").lower()
        if "timeout" in lg:
            rej["timeout"] += 1
        elif "causality_probe" in lg:
            rej["causality"] += 1
        elif "static_check" in lg or "exec" in lg:
            rej["static_or_exec"] += 1
        else:
            rej["other"] += 1
    return rej


def run_search(splits, symbol, budget, writer=propose_program, ideas=None, seed: int = 0,
               cache_dir: str = "/tmp/era_fair_cache", p_recombine: float = 0.3,
               seed_programs=None):
    ideas = ideas or RESEARCH_IDEAS
    seed_programs = seed_programs or FAIR_SEED_PROGRAMS
    scorer = FairScorer(splits=splits, symbol=symbol)
    rng = random.Random(seed)
    split_for_rank = "validation" if "validation" in splits else "train"
    forest = []
    for _name, src in seed_programs.items():
        s, lg = scorer.score(src, split_for_rank)
        forest.append(Node(payload=src, score=s, parent=None, logs=lg))
    all_nodes = list(forest)

    def expand(parent: Node) -> Node:
        if rng.random() < p_recombine and len(all_nodes) >= 2:
            distinct = {}
            for nd in all_nodes:
                key = id(nd.payload)
                if key not in distinct or nd.score > distinct[key].score:
                    distinct[key] = nd
            cands = sorted(distinct.values(), key=lambda n: n.score, reverse=True)
            if len(cands) >= 2:
                child_src = recombine_program(cands[0].payload, cands[0].score,
                                              cands[1].payload, cands[1].score,
                                              cache_dir=cache_dir, rules=FAIR_RULES)
            else:
                child_src = writer(parent.payload, parent.score, parent.logs,
                                   rng.choice(ideas), cache_dir=cache_dir, rules=FAIR_RULES)
        else:
            child_src = writer(parent.payload, parent.score, parent.logs,
                               rng.choice(ideas), cache_dir=cache_dir, rules=FAIR_RULES)
        s, lg = scorer.score(child_src, split_for_rank)
        child = Node(payload=child_src, score=s, parent=parent, logs=lg)
        all_nodes.append(child)
        return child

    return puct_search(forest, expand, budget=budget, c_puct=1.0, seed=seed)


def _holdout_best(src, d, symbol):
    """Best |IC| over the W grid on the holdout; returns (ic, n, W, diag) or None."""
    ctx = FeatureContext(X=d.X, names=d.names, hour=d.hour)
    pred, err, _ = run_program(src, ctx, required_fn="fair")
    if err is not None:
        return None
    pip = _PIP[str(symbol).upper()]
    best = None
    for W in W_GRID:
        ic, n = info_coefficient(pred, forward_dev(d.mid, pip, W))
        if np.isfinite(ic) and (best is None or abs(ic) > abs(best[0])):
            best = (ic, n, W)
    if best is None:
        return None
    ic, n, W = best
    return ic, n, W, fair_diagnostics(pred, d.mid, pip, d.test_month, W)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="EURUSD")
    ap.add_argument("--parquet", required=True)
    ap.add_argument("--budget", type=int, default=60)
    ap.add_argument("--no-baseline-seeds", action="store_true")
    ap.add_argument("--holdout-top", type=int, default=8)
    ap.add_argument("--score-max-bars", type=int, default=50000)
    ap.add_argument("--out", default="/tmp/era_fair/report.md")
    args = ap.parse_args()
    from scripts.era_scalp.load_splits import build_fair_splits, cap_recent

    splits = build_fair_splits(args.symbol, Path(args.parquet), embargo=max(W_GRID))
    cap = args.score_max_bars or None
    if cap and splits["validation"].X.shape[0] > cap:
        v = splits["validation"]
        sl = slice(v.X.shape[0] - cap, None)
        splits["validation"] = type(v)(X=v.X[sl], names=v.names,
                                        hour=None if v.hour is None else v.hour[sl],
                                        mid=v.mid[sl], test_month=v.test_month[sl])
    seed_programs = select_seed_programs(no_baseline=args.no_baseline_seeds)
    nodes = run_search(splits, symbol=args.symbol, budget=args.budget,
                       seed_programs=seed_programs)
    nodes.sort(key=lambda n: n.score, reverse=True)

    hold = splits["holdout"]
    top = nodes[: args.holdout_top]
    cand, diag_rows = {}, {}
    for i, nd in enumerate(top):
        res = _holdout_best(nd.payload, hold, args.symbol)
        if res is None:
            continue
        ic, n, W, diag = res
        cand[f"node{i}"] = (ic, n)
        diag_rows[f"node{i}"] = {"W": W, **diag}
    survivors = finalize_selection(cand, q=0.10) if cand else []
    health = summarize_rejections(nodes)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w") as f:
        f.write(f"# ERA-fair run - {args.symbol} 100tick\n\n")
        f.write(f"nodes: {len(nodes)} | no_baseline_seeds={args.no_baseline_seeds} "
                f"| score_max_bars={cap}\n\n")
        f.write(f"## Search health: {health}\n\n")
        f.write(f"## BH-FDR holdout IC survivors (q=0.10): {survivors or 'none'}\n\n")
        f.write("## Top by validation node-score (with holdout IC diagnostics)\n\n")
        for i, nd in enumerate(top):
            dd = diag_rows.get(f"node{i}", {})
            f.write(f"- node_score={nd.score:.3f} holdout={dd}\n```python\n{nd.payload}\n```\n")
    print(f"wrote {args.out}; survivors={survivors}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run — expect PASS.** `uv run pytest tests/era_scalp/test_fair_integration.py -q`

- [ ] **Step 5: Commit**

```bash
git add scripts/era_scalp/run_era_fair.py tests/era_scalp/test_fair_integration.py
git commit -m "feat(era-scalp): fair-price driver (IC search + holdout BH-FDR + diagnostics)"
```

---

## Task F7: Quality gate + PR

- [ ] **Step 1:** `uv run pytest -q tests/era_scalp/ tests/era/ && make quality` → all pass; quality exit 0 (fix only new-file ruff issues).
- [ ] **Step 2:** Push branch `era-fair-price` (off `main`) and open PR:

```bash
git push -u origin era-fair-price
gh pr create --base main --title "feat(era-scalp): fair-price (micro-price) prediction via ERA" --body "$(cat <<'EOF'
Adds a `fair` mode to scripts/era_scalp/: programs emit a per-bar predicted mispricing
(fair-mid) in pips; label = forward de-noised mid (~efficient price); score = out-of-sample
information coefficient (Pearson), node-signal |IC|*sqrt(n), final = two-sided BH-FDR over
holdout IC with a max(W)-bar embargo. A calibrated efficient-price estimator, decoupled from
execution cost and foundational for the range-harvest/reversion variants.

Seeds (level-free from returns + microstructure): EWMA-denoise (Hasbrouck), bounce reversal
(Roll), micro-price imbalance (Stoikov), trailing anchor, OFI tilt (Cont-Kukanov-Stoikov).
Reuses the engine + FeatureContext + causality probe (required_fn="fair").

Spec: docs/superpowers/specs/2026-05-31-era-fair-price-prediction-design.md
Tests: tests/era_scalp/ (harness, splits, scorer, seeds, prompt, integration) + era regressions.

Live qwen evidence run to follow as a maintainer step.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Task F8: Opus live evidence run (maintainer step — NOT Haiku)

**Requires:** `OLLAMA_API_KEY` in `.env`; `data/analysis/tick_velocity/EURUSD_100tick_velocity.parquet`.

- [ ] **Step 1: Budget-6 smoke** — confirm pipeline runs, search-health timeouts 0, holdout IC diagnostics populated:

```bash
ERA_GEN_TEMP=0.8 uv run python -m scripts.era_scalp.run_era_fair \
  --symbol EURUSD --parquet data/analysis/tick_velocity/EURUSD_100tick_velocity.parquet \
  --budget 6 --out /tmp/era_fair/smoke.md
```

- [ ] **Step 2: Coverage (budget 80) + rediscovery (budget 40, `--no-baseline-seeds`)** on EURUSD 100-tick; then repeat on 1000-tick (the de-noising window W is in bars, so 1000-tick tests a different horizon).
- [ ] **Step 3: Write evidence doc** `docs/analysis/era_fair_price_evidence_<DATE>.md` — best holdout IC, n_eff, IC-by-month consistency, BH-FDR survivors, search-health; honest verdict on whether fair price is reliably predictable (IC>0 significant) and the caveat that IC>0 ≠ tradeable. Commit.

---

## Self-Review

**Spec coverage:** `fair(ctx)` mispricing contract → F3/F4/F5; IC harness (`forward_dev`/`info_coefficient`/`fair_node_score` `|IC|·√n`/`ic_pvalue`/`fair_diagnostics`) → F1; FairSplitData + mid + `max(W)` embargo → F2; FairScorer (causal probe + W-grid) → F3; level-free literature seeds → F4; prompt → F5; driver + holdout IC + two-sided BH-FDR + search-health + ablation → F6; testing → each task + F7; evidence → F8. All covered.

**Placeholder scan:** no TBD/TODO; every code step complete; commands have expected output.

**Type/name consistency:** `fair(ctx)` everywhere; `FairSplitData(X, names, hour, mid, test_month)` consistent F2/F3/F6; `FairScorer(splits, symbol, timeout=)` + `_PIP` F3/F6; `W_GRID`, `forward_dev(mid,pip,W)`, `info_coefficient(pred,realized)->(ic,n)`, `fair_node_score(pred,mid,pip,w_grid)`, `ic_pvalue(ic,n)`, `fair_diagnostics(pred,mid,pip,test_month,W)` consistent F1/F3/F6; `finalize_selection(cand_ic_n: name->(ic,n))` F6 (note: takes (ic,n) tuples, not DataFrames — distinct from the other drivers, matches its test); `select_seed_programs`/`summarize_rejections`/`run_search(splits,symbol,budget,...)` F6; `FAIR_RULES`/`FAIR_FEATURE_NAMES` F5; `BASELINE_SEED_NAMES` F4/F6; `required_fn="fair"` in F3/F6. The driver's inline validation cap uses `type(v)(...)` to rebuild the `FairSplitData` slice (avoids importing a separate helper).
