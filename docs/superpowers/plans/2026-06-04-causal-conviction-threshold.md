# Causal Conviction Threshold (Plan A) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the full-sample (look-ahead) conviction-quantile threshold in `evaluate_trades` with an opt-in causal expanding-window threshold, and provide an A/B that measures the edge delta.

**Architecture:** Add a pure helper `expanding_quantile_threshold(s, q, warmup, recompute_every)` that, at each bar `t`, returns the q-quantile of `|s[:t+1]|` over finite values seen *so far* (recomputed on a cadence, held constant between recomputes, NaN until `warmup` finite samples accrue). Wire it into `evaluate_trades` behind a `causal_threshold=False` flag so existing callers/tests are unchanged. Add an A/B script that scores a seed both ways on a real split and reports the net-edge difference.

**Tech Stack:** numpy, pandas, pytest. All changes in `scripts/era_scalp/trade_harness.py` + tests under `tests/era_scalp/`.

---

### Background (why this change)

`scripts/era_scalp/trade_harness.py:28` computes `thr = np.quantile(np.abs(s[fin]), q)` over the **entire split**. At bar `t` you cannot know the whole-period quantile, so this is in-sample threshold leakage that inflates the reported edge. The `causality_probe` does not catch it because the threshold lives in the harness layer, outside the probed `signal()` function. This plan makes the threshold causal and quantifies the inflation.

---

### Task 1: Causal expanding-quantile helper

**Files:**
- Modify: `scripts/era_scalp/trade_harness.py`
- Test: `tests/era_scalp/test_causal_threshold.py` (create)

- [ ] **Step 1: Write the failing tests**

```python
# tests/era_scalp/test_causal_threshold.py
import numpy as np

from scripts.era_scalp.trade_harness import expanding_quantile_threshold


def test_threshold_is_nan_before_warmup():
    s = np.arange(1, 101, dtype=float)
    thr = expanding_quantile_threshold(s, q=0.9, warmup=20, recompute_every=1)
    assert np.all(np.isnan(thr[:19]))      # < 20 finite samples seen
    assert np.isfinite(thr[19])            # 20th finite sample unlocks trading


def test_threshold_only_uses_past():
    # Perturbing the future must not change a past threshold value.
    rng = np.random.default_rng(0)
    s = rng.standard_normal(500)
    thr_a = expanding_quantile_threshold(s, q=0.95, warmup=50, recompute_every=10)
    s2 = s.copy()
    s2[300:] = rng.standard_normal(200) * 50.0   # blow up the future
    thr_b = expanding_quantile_threshold(s2, q=0.95, warmup=50, recompute_every=10)
    finite = np.isfinite(thr_a[:300]) & np.isfinite(thr_b[:300])
    assert finite.any()
    assert np.allclose(thr_a[:300][finite[:300]], thr_b[:300][finite[:300]])


def test_threshold_handles_nan_signal():
    s = np.array([np.nan, 1.0, np.nan, 2.0, 3.0, 4.0, 5.0, 6.0])
    thr = expanding_quantile_threshold(s, q=0.5, warmup=3, recompute_every=1)
    # Only 4 finite values exist; warmup=3 means index 4 (3rd finite) is first armed.
    assert np.isnan(thr[0]) and np.isnan(thr[1])
    assert np.isfinite(thr[4])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/era_scalp/test_causal_threshold.py -v`
Expected: FAIL with `ImportError: cannot import name 'expanding_quantile_threshold'`

- [ ] **Step 3: Implement the helper**

Add to `scripts/era_scalp/trade_harness.py` (after `forward_return`):

```python
def expanding_quantile_threshold(
    signal: np.ndarray, q: float, warmup: int = 2000, recompute_every: int = 500
) -> np.ndarray:
    """Causal per-bar conviction threshold.

    At bar t the threshold is the q-quantile of |signal[:t+1]| over the finite
    values seen so far. To bound cost it is recomputed every `recompute_every`
    bars and held constant between recomputes. Returns NaN (no-trade) until at
    least `warmup` finite samples have accrued. Uses only past data, so a future
    perturbation can never change a past threshold value.
    """
    a = np.abs(np.asarray(signal, float))
    n = a.shape[0]
    thr = np.full(n, np.nan)
    fin = np.isfinite(a)
    cum_fin = np.cumsum(fin)            # finite-sample count up to and including t
    last = np.nan
    for t in range(n):
        if cum_fin[t] < warmup:
            continue
        if not np.isfinite(last) or (t % recompute_every == 0):
            hist = a[: t + 1][fin[: t + 1]]
            last = float(np.quantile(hist, q))
        thr[t] = last
    return thr
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/era_scalp/test_causal_threshold.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add scripts/era_scalp/trade_harness.py tests/era_scalp/test_causal_threshold.py
git commit -m "feat(era-scalp): causal expanding-quantile conviction threshold helper"
```

---

### Task 2: Wire causal threshold into evaluate_trades

**Files:**
- Modify: `scripts/era_scalp/trade_harness.py:19-31` (`evaluate_trades`)
- Test: `tests/era_scalp/test_causal_threshold.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/era_scalp/test_causal_threshold.py`:

```python
from scripts.era_scalp.trade_harness import evaluate_trades


def test_evaluate_trades_causal_flag_changes_entries():
    n = 5000
    rng = np.random.default_rng(1)
    signal = rng.standard_normal(n)
    mid = 1.0 + np.cumsum(rng.standard_normal(n)) * 1e-5
    cost = np.full(n, 0.0)
    tm = np.array(["2024-01"] * n)
    full = evaluate_trades(signal, mid, cost, tm, pip=1e-4, q=0.95, h=10)
    causal = evaluate_trades(
        signal, mid, cost, tm, pip=1e-4, q=0.95, h=10,
        causal_threshold=True, warmup=500, recompute_every=200,
    )
    # Causal path can never trade before warmup, so it has strictly fewer entries.
    assert len(causal) < len(full)
    assert len(causal) > 0


def test_evaluate_trades_default_is_unchanged():
    # Default (full-sample) path must be byte-identical to the legacy behaviour.
    n = 100
    signal = np.concatenate([np.full(50, 2.0), np.full(50, 0.0)])
    mid = 1.0 + np.arange(n) * 1e-4
    cost = np.full(n, 0.4)
    tm = np.array(["2024-01"] * n)
    df = evaluate_trades(signal, mid, cost, tm, pip=1e-4, q=0.50, h=10)
    assert len(df) > 0 and df["net"].mean() > 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/era_scalp/test_causal_threshold.py::test_evaluate_trades_causal_flag_changes_entries -v`
Expected: FAIL with `TypeError: evaluate_trades() got an unexpected keyword argument 'causal_threshold'`

- [ ] **Step 3: Modify `evaluate_trades`**

Replace the body of `evaluate_trades` in `scripts/era_scalp/trade_harness.py` with:

```python
def evaluate_trades(signal, mid, cost, test_month, pip, q, h,
                    causal_threshold=False, warmup=2000, recompute_every=500):
    """Top-q |conviction| entries; side=sign(signal); exit at t+h; net = side*fwd - cost.

    causal_threshold=False (default): conviction cutoff is the full-sample q-quantile
    of |scaled signal| (legacy; uses look-ahead, kept for A/B and backward compat).
    causal_threshold=True: cutoff is a causal expanding-window quantile (no look-ahead).
    """
    raw = np.asarray(signal, float)
    s = scale_signal(raw)
    fwd = forward_return(mid, pip, h)
    cost = np.asarray(cost, float)
    fin = np.isfinite(s)
    if fin.sum() < 2:
        return pd.DataFrame({"net": np.array([]), "test_month": np.array([])})
    if causal_threshold:
        thr = expanding_quantile_threshold(s, q, warmup=warmup, recompute_every=recompute_every)
        armed = np.isfinite(thr)
        entry = fin & np.isfinite(fwd) & np.isfinite(cost) & armed & (np.abs(s) >= thr)
    else:
        thr = np.quantile(np.abs(s[fin]), q)
        entry = fin & np.isfinite(fwd) & np.isfinite(cost) & (np.abs(s) >= thr)
    net = np.sign(raw) * fwd - cost
    return pd.DataFrame({"net": net[entry], "test_month": np.asarray(test_month)[entry]})
```

- [ ] **Step 4: Run the full harness test suite**

Run: `uv run pytest tests/era_scalp/test_causal_threshold.py tests/era_scalp/test_trade_harness.py -v`
Expected: PASS (all). The legacy `test_trade_harness.py` cases must still pass unchanged.

- [ ] **Step 5: Commit**

```bash
git add scripts/era_scalp/trade_harness.py tests/era_scalp/test_causal_threshold.py
git commit -m "feat(era-scalp): opt-in causal threshold in evaluate_trades (default unchanged)"
```

---

### Task 3: A/B driver — measure the look-ahead inflation

**Files:**
- Create: `scripts/era_scalp/ab_causal_threshold.py`
- Test: `tests/era_scalp/test_causal_threshold.py`

- [ ] **Step 1: Write the failing test for the A/B aggregation helper**

Append to `tests/era_scalp/test_causal_threshold.py`:

```python
from scripts.era_scalp.ab_causal_threshold import ab_edge_delta


def test_ab_edge_delta_reports_both_modes():
    n = 4000
    rng = np.random.default_rng(2)
    signal = rng.standard_normal(n)
    mid = 1.0 + np.cumsum(rng.standard_normal(n)) * 1e-5
    cost = np.full(n, 0.0)
    tm = np.array(["2024-%02d" % (1 + (i // 400) % 12) for i in range(n)])
    out = ab_edge_delta(signal, mid, cost, tm, pip=1e-4, q=0.95, h=10,
                        warmup=500, recompute_every=200)
    assert set(out) >= {"full_mean_net", "causal_mean_net", "full_n", "causal_n", "delta"}
    assert out["full_n"] >= out["causal_n"]      # causal trades no more than full-sample
    assert np.isclose(out["delta"], out["full_mean_net"] - out["causal_mean_net"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/era_scalp/test_causal_threshold.py::test_ab_edge_delta_reports_both_modes -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.era_scalp.ab_causal_threshold'`

- [ ] **Step 3: Implement the A/B driver**

Create `scripts/era_scalp/ab_causal_threshold.py`:

```python
#!/usr/bin/env python3
"""A/B the full-sample (look-ahead) vs causal expanding-quantile conviction threshold.

Scores a single seed program on a symbol's holdout split both ways and reports the
net-edge delta. The delta is the edge inflation attributable to threshold look-ahead.
"""
from __future__ import annotations

import numpy as np

from scripts.era_scalp.trade_harness import evaluate_trades


def ab_edge_delta(signal, mid, cost, test_month, pip, q, h,
                  warmup=2000, recompute_every=500) -> dict:
    """Return mean-net and entry-count for both threshold modes plus their delta."""
    full = evaluate_trades(signal, mid, cost, test_month, pip, q, h,
                           causal_threshold=False)
    causal = evaluate_trades(signal, mid, cost, test_month, pip, q, h,
                             causal_threshold=True, warmup=warmup,
                             recompute_every=recompute_every)
    full_mean = float(full["net"].mean()) if len(full) else float("nan")
    causal_mean = float(causal["net"].mean()) if len(causal) else float("nan")
    return {
        "full_mean_net": full_mean,
        "causal_mean_net": causal_mean,
        "full_n": int(len(full)),
        "causal_n": int(len(causal)),
        "delta": full_mean - causal_mean,
    }


def main() -> None:
    import argparse
    from pathlib import Path

    from scripts.era_scalp.context import FeatureContext
    from scripts.era_scalp.cost_model import realistic_cost
    from scripts.era_scalp.fade_seeds import FADE_SEED_PROGRAMS
    from scripts.era_scalp.load_splits import _pip_size, build_trade_splits
    from scripts.era_scalp.sandbox import run_program

    ap = argparse.ArgumentParser()
    ap.add_argument("--seed-name", default="vr_gated_fade")
    ap.add_argument("--symbol", default="EURUSD")
    ap.add_argument("--tv-dir", default="data/analysis/tick_velocity")
    ap.add_argument("--q", type=float, default=0.99)
    ap.add_argument("--h", type=int, default=100)
    ap.add_argument("--warmup", type=int, default=20000)
    ap.add_argument("--recompute-every", type=int, default=2000)
    args = ap.parse_args()

    src = FADE_SEED_PROGRAMS[args.seed_name]
    sp = build_trade_splits(
        args.symbol, Path(args.tv_dir) / f"{args.symbol}_100tick_velocity.parquet",
        embargo=args.h,
    )
    d = sp["holdout"]
    ctx = FeatureContext(X=d.X, names=d.names, hour=d.hour)
    sig, err, _ = run_program(src, ctx, required_fn="signal")
    if err is not None:
        raise SystemExit(f"program error: {err}")
    cost = realistic_cost(d.spread_pips)
    out = ab_edge_delta(sig, d.mid, cost, d.test_month, _pip_size(args.symbol),
                        args.q, args.h, warmup=args.warmup,
                        recompute_every=args.recompute_every)
    print(f"seed={args.seed_name} symbol={args.symbol} q={args.q} h={args.h}")
    print(f"  full-sample : mean_net={out['full_mean_net']:+.4f}  n={out['full_n']}")
    print(f"  causal      : mean_net={out['causal_mean_net']:+.4f}  n={out['causal_n']}")
    print(f"  look-ahead inflation (delta) = {out['delta']:+.4f} pips/trade")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/era_scalp/test_causal_threshold.py -v`
Expected: PASS (all tests in file).

- [ ] **Step 5: Commit**

```bash
git add scripts/era_scalp/ab_causal_threshold.py tests/era_scalp/test_causal_threshold.py
git commit -m "feat(era-scalp): A/B driver for threshold look-ahead inflation"
```

---

### Self-Review checklist

- **Spec coverage:** expanding-quantile helper (Task 1) ✓; opt-in wiring with default unchanged (Task 2) ✓; A/B measurement (Task 3) ✓.
- **Type consistency:** `expanding_quantile_threshold(signal, q, warmup, recompute_every)` signature identical in helper, `evaluate_trades`, and `ab_edge_delta`. `ab_edge_delta` keys match the test assertion set.
- **Placeholders:** none — every step has full code and exact commands.
- **Out of scope (follow-up):** flipping the default to `causal_threshold=True` across drivers (`run_era_eur`, `run_era_fade`, `per_symbol_sweep`, `cost_aware_score`) once the A/B quantifies the delta on real data — do this as a separate PR after reviewing the inflation number.
