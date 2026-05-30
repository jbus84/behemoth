# ERA Range-Harvest Scalping Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a direction-agnostic **range-harvest** mode to `scripts/era_scalp/`: programs emit a non-directional `deploy(ctx)` regime score, a two-sided maker-bracket harness rests symmetric limits (market picks the side), and PUCT fuses literature seeds (realized-range, variance-ratio/OU regime, VPIN/OFI toxicity veto, Hawkes burst veto, Avellaneda-Stoikov spread-harvest) toward a net-of-cost edge.

**Architecture:** Reuse the `era_scalp` package (`context.FeatureContext`, `sandbox.run_program`/`causality_probe`, `harness.task_score`) and the `era` engine (`puct`, `select`, `llm` with `rules=`). Add a bracket payoff harness, deploy-score seeds, a range prompt, a range scorer, an extended split loader, and a driver. The directional code is untouched (it's the documented negative result).

**Tech Stack:** Python 3.12, numpy, pandas, pyarrow, pytest, `uv run`. Generator `qwen3-coder-next` via `scripts/cheap_llm.sh` (live run only; unit tests use seeds/mocked writers).

**Spec:** `docs/superpowers/specs/2026-05-30-era-range-harvest-scalping-design.md`

**Prerequisite:** PR #280 (directional `era_scalp` + engine generalizations) must be merged to `main`; branch this work off fresh `main`.

**Causal contract:** programs define `deploy(ctx) -> np.ndarray` — a per-bar NON-directional score (high = deploy a two-sided bracket; `np.nan` = stand aside). `deploy[k]` may depend only on bars ≤ k (causality probe enforces). The feature whitelist is the separate gate against baked-in column leakage.

**Reused signatures (already on `main` after #280):**
- `scripts/era_scalp/context.py`: `FeatureContext(X, names, hour=None)` with `.n_bars`, `.col(name)`.
- `scripts/era_scalp/sandbox.py`: `run_program(src, ctx, timeout=10.0)`, `causality_probe(src, ctx, clean, n_cuts=2, seed=0)`, both built on `FeatureContext`; `static_check(src, required_fn=...)` from `scripts/era/sandbox.py`.
- `scripts/era_scalp/harness.py`: `task_score(df)` (reused from `scripts/era/harness.py`).
- `scripts/era_scalp/load_splits.py`: `WHITELIST`, `build_splits(...)`, `cap_recent(split, max_bars)`.
- `scripts/era/llm.py`: `propose_program(...rules=)`, `recombine_program(...rules=)`.
- `scripts/era/puct.py`: `Node`, `puct_search`. `scripts/era/select.py`: `bh_fdr`, `holdout_pvalue`.

---

## File Structure

- Modify: `scripts/era_scalp/load_splits.py` — add `bar_range_pips` to `WHITELIST`; add `RangeSplitData` + `build_range_splits` (carry `close_bid`/`high_bid`/`low_bid`/`spread_pips`/`cost`, `K`-bar embargo).
- Create: `scripts/era_scalp/bracket_harness.py` — `simulate_bracket`, `evaluate_deploy`, `deploy_diagnostics`.
- Create: `scripts/era_scalp/range_score.py` — `RangeScorer` (uses `RangeSplitData`).
- Create: `scripts/era_scalp/range_seeds.py` — `DEPLOY_SEED_PROGRAMS`, `BASELINE_SEED_NAMES`, `RESEARCH_IDEAS`.
- Create: `scripts/era_scalp/range_prompt.py` — `RANGE_RULES`, `DEPLOY_FEATURE_NAMES`.
- Create: `scripts/era_scalp/run_era_range.py` — driver.
- Tests under `tests/era_scalp/`: `test_bracket_harness.py`, `test_range_seeds.py`, `test_range_prompt.py`, `test_load_splits_range.py`, `test_range_integration.py`.

**Note on the deploy gate:** to compare `deploy` scores across programs, the harness deploys on the **top-`q`** of a program's own finite scores on the split (`q ∈ {0.1,0.2,0.4}`), mirroring the directional MAD-scale posture. Implemented as: `cut = nanquantile(score, 1-q); deploy = finite(score) & (score >= cut)`.

---

## Task R1: Split loader — `bar_range_pips` + `RangeSplitData` + `K`-embargo

**Files:**
- Modify: `scripts/era_scalp/load_splits.py`
- Test: `tests/era_scalp/test_load_splits_range.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# tests/era_scalp/test_load_splits_range.py
import numpy as np
import pandas as pd

from scripts.era_scalp.load_splits import WHITELIST, build_range_splits


def _write_fake(path, n=3000):
    rng = np.random.default_rng(0)
    ts = pd.to_datetime(np.r_[
        pd.date_range("2023-06-01", periods=n // 3, freq="5min", tz="UTC"),
        pd.date_range("2024-06-01", periods=n // 3, freq="5min", tz="UTC"),
        pd.date_range("2025-06-01", periods=n - 2 * (n // 3), freq="5min", tz="UTC"),
    ])
    cols = {c: rng.standard_normal(n) for c in WHITELIST if c != "bar_range_pips"}
    cols["close_ts"] = ts
    cols["close_bid"] = 1.1 + rng.standard_normal(n) * 1e-3
    cols["high_bid"] = cols["close_bid"] + np.abs(rng.standard_normal(n)) * 1e-3
    cols["low_bid"] = cols["close_bid"] - np.abs(rng.standard_normal(n)) * 1e-3
    cols["spread_pips"] = np.full(n, 0.3)
    cols["cost_est_pips"] = np.full(n, 0.4)
    pd.DataFrame(cols).to_parquet(path)


def test_build_range_splits_carries_prices_and_embargo(tmp_path):
    p = tmp_path / "EURUSD_100tick_velocity.parquet"
    _write_fake(p)
    splits = build_range_splits("EURUSD", p, max_hold=4,
                                train=("2023",), validation=("2024",), holdout=("2025",))
    for name in ("train", "validation", "holdout"):
        d = splits[name]
        assert d.X.shape[1] == len(WHITELIST)
        assert "bar_range_pips" in d.names
        # harness-side price arrays present and aligned
        assert len(d.close_bid) == len(d.high_bid) == len(d.low_bid) == d.X.shape[0]
        assert len(d.spread) == len(d.cost) == d.X.shape[0]
    full_train = (pd.read_parquet(p)["close_ts"].dt.year == 2023).sum()
    assert splits["train"].X.shape[0] == full_train - 4  # K-bar tail embargo


def test_bar_range_pips_is_in_whitelist_and_nonneg(tmp_path):
    p = tmp_path / "EURUSD_100tick_velocity.parquet"
    _write_fake(p)
    splits = build_range_splits("EURUSD", p, max_hold=4,
                                train=("2023",), validation=("2024",), holdout=("2025",))
    j = splits["train"].names.index("bar_range_pips")
    assert np.all(splits["train"].X[:, j] >= 0)
```

- [ ] **Step 2: Run — expect FAIL** (`cannot import name 'build_range_splits'`)

Run: `uv run pytest tests/era_scalp/test_load_splits_range.py -q`

- [ ] **Step 3: Edit `scripts/era_scalp/load_splits.py`**

Add `"bar_range_pips"` to the end of the `WHITELIST` list. Then add a dataclass + builder (after `build_splits`):

```python
from dataclasses import dataclass


def _pip_size(symbol: str) -> float:
    s = str(symbol).upper()
    if s.endswith("JPY"):
        return 0.01
    return 0.0001


@dataclass
class RangeSplitData:
    X: np.ndarray
    names: list[str]
    hour: np.ndarray | None
    close_bid: np.ndarray
    high_bid: np.ndarray
    low_bid: np.ndarray
    spread: np.ndarray
    cost: np.ndarray
    test_month: np.ndarray


def build_range_splits(
    symbol: str,
    parquet_path: Path,
    max_hold: int = 4,
    train=("2018", "2019", "2020", "2021", "2022", "2023"),
    validation=("2024",),
    holdout=("2025", "2026"),
) -> dict[str, RangeSplitData]:
    pip = _pip_size(symbol)
    df = pd.read_parquet(parquet_path)
    df["close_ts"] = pd.to_datetime(df["close_ts"], utc=True, errors="coerce")
    df = df[df["close_ts"].notna()].sort_values("close_ts").reset_index(drop=True)
    df["bar_range_pips"] = (df["high_bid"] - df["low_bid"]).abs() / pip
    df["year"] = df["close_ts"].dt.strftime("%Y")
    df["test_month"] = df["close_ts"].dt.strftime("%Y-%m")

    def _split(years, embargo_tail: bool) -> RangeSplitData:
        d = df[df["year"].isin(years)].reset_index(drop=True)
        if embargo_tail and len(d) > max_hold:
            d = d.iloc[: len(d) - max_hold].reset_index(drop=True)
        return RangeSplitData(
            X=d[WHITELIST].to_numpy(float),
            names=list(WHITELIST),
            hour=d["hour_utc"].to_numpy(float),
            close_bid=d["close_bid"].to_numpy(float),
            high_bid=d["high_bid"].to_numpy(float),
            low_bid=d["low_bid"].to_numpy(float),
            spread=d["spread_pips"].to_numpy(float),
            cost=d["cost_est_pips"].to_numpy(float),
            test_month=d["test_month"].to_numpy(),
        )

    return {
        "train": _split(train, embargo_tail=True),
        "validation": _split(validation, embargo_tail=True),
        "holdout": _split(holdout, embargo_tail=False),
    }
```

(`bar_range_pips` is built from `high_bid`/`low_bid` which are contemporaneous → causal; it is a program-visible feature, while the raw `high_bid`/`low_bid` price arrays are harness-side only.)

- [ ] **Step 4: Run — expect PASS.** `uv run pytest tests/era_scalp/test_load_splits_range.py -q`

- [ ] **Step 5: Commit**

```bash
git add scripts/era_scalp/load_splits.py tests/era_scalp/test_load_splits_range.py
git commit -m "feat(era-scalp): RangeSplitData + bar_range_pips + K-bar embargo for range harvest"
```

---

## Task R2: Bracket payoff harness

**Files:**
- Create: `scripts/era_scalp/bracket_harness.py`
- Test: `tests/era_scalp/test_bracket_harness.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/era_scalp/test_bracket_harness.py
import numpy as np

from scripts.era_scalp.bracket_harness import deploy_gate, evaluate_deploy, simulate_bracket


def test_deploy_gate_topq():
    score = np.array([1.0, 2.0, 3.0, 4.0, 5.0, np.nan])
    g = deploy_gate(score, q=0.4)  # top 40% of 5 finite -> top 2: values 4,5
    assert g.tolist() == [False, False, False, True, True, False]


def _flat_prices(n, p=1.10):
    return {"close": np.full(n, p), "high": np.full(n, p), "low": np.full(n, p)}


def test_simulate_bracket_oscillation_tp():
    # price dips to lower band then reverts to center -> BUY fills, TP at center
    n = 6
    close = np.array([1.1000, 1.1000, 1.0996, 1.1000, 1.1000, 1.1000])
    high = np.array([1.1000, 1.1001, 1.0998, 1.1001, 1.1000, 1.1000])
    low = np.array([1.1000, 1.0999, 1.0995, 1.0998, 1.1000, 1.1000])
    # deploy at bar 0; delta=3 pips, stop=3 pips, K=4, pip=1e-4
    out = simulate_bracket(k=0, close=close, high=high, low=low, spread=np.full(n, 0.3),
                           delta_pips=3.0, stop_pips=3.0, max_hold=4, pip=1e-4,
                           commission_pips=0.07)
    assert out["filled"] and out["side"] == 1  # bought the dip
    assert out["exit"] == "tp"
    assert abs(out["net_pips"] - (3.0 - 0.07)) < 1e-6  # +delta - commission, maker both ends


def test_simulate_bracket_trend_sl():
    # price falls straight through lower band and keeps going -> BUY fills then SL
    n = 6
    close = np.array([1.1000, 1.0996, 1.0990, 1.0985, 1.0980, 1.0975])
    high = np.array([1.1000, 1.0999, 1.0996, 1.0990, 1.0985, 1.0980])
    low = np.array([1.1000, 1.0995, 1.0989, 1.0984, 1.0979, 1.0974])
    out = simulate_bracket(k=0, close=close, high=high, low=low, spread=np.full(n, 0.3),
                           delta_pips=3.0, stop_pips=3.0, max_hold=4, pip=1e-4,
                           commission_pips=0.07)
    assert out["filled"] and out["side"] == 1 and out["exit"] == "sl"
    # SL net = -stop - spread_exit - commission
    assert out["net_pips"] < 0


def test_evaluate_deploy_returns_net_frame():
    n = 50
    rng = np.random.default_rng(0)
    close = 1.1 + np.cumsum(rng.standard_normal(n)) * 1e-4
    high = close + 2e-4
    low = close - 2e-4
    score = rng.standard_normal(n)
    df = evaluate_deploy(
        deploy_score=score, close=close, high=high, low=low,
        spread=np.full(n, 0.3), cost=np.full(n, 0.4),
        test_month=np.array(["2024-01"] * n),
        q=0.4, delta_pips=3.0, stop_pips=3.0, max_hold=5, pip=1e-4, commission_pips=0.07,
    )
    assert set(df.columns) == {"net", "test_month"}
```

- [ ] **Step 2: Run — expect FAIL.** `uv run pytest tests/era_scalp/test_bracket_harness.py -q`

- [ ] **Step 3: Create `scripts/era_scalp/bracket_harness.py`**

```python
from __future__ import annotations

import numpy as np
import pandas as pd


def deploy_gate(deploy_score: np.ndarray, q: float) -> np.ndarray:
    """Boolean mask: deploy on the top-q of the program's own finite scores."""
    s = np.asarray(deploy_score, float)
    finite = np.isfinite(s)
    if finite.sum() == 0:
        return np.zeros_like(s, dtype=bool)
    cut = np.nanquantile(s[finite], 1.0 - float(q))
    return finite & (s >= cut)


def simulate_bracket(*, k, close, high, low, spread, delta_pips, stop_pips,
                     max_hold, pip, commission_pips):
    """Two-sided maker bracket from bar k. Returns dict(filled, side, exit, net_pips).

    BUY limit L=P-delta, SELL limit U=P+delta over bars k+1..k+K. First edge traded
    through wins (maker fill). Then TP=center P (maker), SL beyond band (taker), else
    time-stop (taker). Same-bar TP&SL -> SL (pessimistic). Net in pips.
    """
    n = len(close)
    p = float(close[k])
    d = delta_pips * pip
    L, U = p - d, p + d
    lo_band = p - d - stop_pips * pip   # SL for a long
    hi_band = p + d + stop_pips * pip   # SL for a short
    end = min(n - 1, k + int(max_hold))

    side = 0
    entry_i = None
    for i in range(k + 1, end + 1):
        hit_buy = low[i] <= L
        hit_sell = high[i] >= U
        if hit_buy and hit_sell:
            return {"filled": False, "side": 0, "exit": "ambiguous", "net_pips": 0.0}
        if hit_buy:
            side, entry_i, entry_px = 1, i, L
            break
        if hit_sell:
            side, entry_i, entry_px = -1, i, U
            break
    if side == 0:
        return {"filled": False, "side": 0, "exit": "nofill", "net_pips": 0.0}

    tp = p  # center
    sl = lo_band if side == 1 else hi_band
    for i in range(entry_i, end + 1):
        if side == 1:
            hit_tp = high[i] >= tp
            hit_sl = low[i] <= sl
        else:
            hit_tp = low[i] <= tp
            hit_sl = high[i] >= sl
        if hit_sl:  # pessimistic: SL wins same-bar ties
            net = -stop_pips - float(spread[i]) - commission_pips
            return {"filled": True, "side": side, "exit": "sl", "net_pips": net}
        if hit_tp:
            net = delta_pips - commission_pips  # maker both ends, capture +delta
            return {"filled": True, "side": side, "exit": "tp", "net_pips": net}
    # time-stop: taker close at end
    gross = (close[end] - entry_px) / pip * side
    net = gross - float(spread[end]) - commission_pips
    return {"filled": True, "side": side, "exit": "timeout", "net_pips": net}


def evaluate_deploy(*, deploy_score, close, high, low, spread, cost, test_month,
                    q, delta_pips, stop_pips, max_hold, pip, commission_pips):
    """Run the bracket for every gated deploy bar; return DataFrame(net, test_month)."""
    gate = deploy_gate(deploy_score, q)
    nets, months = [], []
    idx = np.where(gate)[0]
    for k in idx:
        r = simulate_bracket(
            k=int(k), close=close, high=high, low=low, spread=spread,
            delta_pips=delta_pips, stop_pips=stop_pips, max_hold=max_hold,
            pip=pip, commission_pips=commission_pips,
        )
        if not r["filled"]:
            continue
        nets.append(r["net_pips"])
        months.append(test_month[k])
    return pd.DataFrame({"net": np.asarray(nets, float),
                         "test_month": np.asarray(months)})


def deploy_diagnostics(*, deploy_score, close, high, low, spread, cost, test_month,
                       q, delta_pips, stop_pips, max_hold, pip, commission_pips):
    gate = deploy_gate(deploy_score, q)
    idx = np.where(gate)[0]
    n_deploy = len(idx)
    if n_deploy == 0:
        return {"deploy_rate": 0.0, "fill_rate": float("nan"), "tp_rate": float("nan"),
                "sl_rate": float("nan"), "timeout_rate": float("nan"),
                "mean_net": float("nan"), "month_hit_rate": float("nan")}
    fills, tps, sls, tos, nets, months = 0, 0, 0, 0, [], []
    for k in idx:
        r = simulate_bracket(
            k=int(k), close=close, high=high, low=low, spread=spread,
            delta_pips=delta_pips, stop_pips=stop_pips, max_hold=max_hold,
            pip=pip, commission_pips=commission_pips,
        )
        if not r["filled"]:
            continue
        fills += 1
        tps += r["exit"] == "tp"
        sls += r["exit"] == "sl"
        tos += r["exit"] == "timeout"
        nets.append(r["net_pips"])
        months.append(test_month[k])
    if fills == 0:
        return {"deploy_rate": n_deploy / len(close), "fill_rate": 0.0,
                "tp_rate": float("nan"), "sl_rate": float("nan"),
                "timeout_rate": float("nan"), "mean_net": float("nan"),
                "month_hit_rate": float("nan")}
    monthly = pd.Series(nets).groupby(np.asarray(months)).mean()
    return {
        "deploy_rate": n_deploy / len(close),
        "fill_rate": fills / n_deploy,
        "tp_rate": tps / fills,
        "sl_rate": sls / fills,
        "timeout_rate": tos / fills,
        "mean_net": float(np.mean(nets)),
        "month_hit_rate": float((monthly > 0).mean()),
    }
```

- [ ] **Step 4: Run — expect PASS** (all 4 tests). `uv run pytest tests/era_scalp/test_bracket_harness.py -q`

- [ ] **Step 5: Commit**

```bash
git add scripts/era_scalp/bracket_harness.py tests/era_scalp/test_bracket_harness.py
git commit -m "feat(era-scalp): two-sided maker-bracket payoff harness (conservative fills)"
```

---

## Task R3: RangeScorer

**Files:**
- Create: `scripts/era_scalp/range_score.py`
- Test: `tests/era_scalp/test_range_integration.py` (create; scorer portion)

- [ ] **Step 1: Write the failing test**

```python
# tests/era_scalp/test_range_integration.py
import numpy as np

from scripts.era_scalp.load_splits import RangeSplitData, WHITELIST
from scripts.era_scalp.range_score import RangeScorer


def _data(n=300, seed=0):
    rng = np.random.default_rng(seed)
    close = 1.1 + np.cumsum(rng.standard_normal(n)) * 1e-4
    return RangeSplitData(
        X=rng.standard_normal((n, len(WHITELIST))),
        names=list(WHITELIST),
        hour=(np.arange(n) % 24).astype(float),
        close_bid=close, high_bid=close + 2e-4, low_bid=close - 2e-4,
        spread=np.full(n, 0.3), cost=np.full(n, 0.4),
        test_month=np.array(["2024-01"] * (n // 2) + ["2024-02"] * (n - n // 2)),
    )


def test_range_scorer_runs_causal_deploy():
    scorer = RangeScorer(splits={"validation": _data()}, symbol="EURUSD")
    s, _ = scorer.score("def deploy(ctx):\n    return ctx.col('bar_range_pips')\n", "validation")
    assert np.isfinite(s)


def test_range_scorer_rejects_noncausal():
    scorer = RangeScorer(splits={"validation": _data()}, symbol="EURUSD")
    fwd = ("def deploy(ctx):\n"
           "    x = ctx.col('bar_range_pips').copy()\n"
           "    x[:-1] = x[1:]\n"
           "    return x\n")
    s, logs = scorer.score(fwd, "validation")
    assert s == -1e6 and "causal" in logs.lower()
```

- [ ] **Step 2: Run — expect FAIL.** `uv run pytest tests/era_scalp/test_range_integration.py -q`

- [ ] **Step 3: Create `scripts/era_scalp/range_score.py`**

```python
from __future__ import annotations

import numpy as np

from scripts.era_scalp.bracket_harness import evaluate_deploy
from scripts.era_scalp.context import FeatureContext
from scripts.era_scalp.harness import task_score
from scripts.era_scalp.sandbox import causality_probe, run_program

_PIP = {"EURUSD": 1e-4, "GBPUSD": 1e-4, "AUDUSD": 1e-4,
        "USDCHF": 1e-4, "USDCAD": 1e-4, "USDJPY": 1e-2}

# search grid for the bracket geometry
_QS = [0.1, 0.2, 0.4]
_DELTAS = [2.0, 3.0, 5.0]
_STOPS = [2.0, 4.0]
_MAXHOLDS = [5, 10]


class RangeScorer:
    def __init__(self, splits, symbol: str, commission_pips: float = 0.07,
                 timeout: float = 10.0):
        self.splits = splits
        self.pip = _PIP[str(symbol).upper()]
        self.commission_pips = commission_pips
        self.timeout = timeout

    def score(self, src: str, split: str) -> tuple[float, str]:
        d = self.splits[split]
        ctx = FeatureContext(X=d.X, names=d.names, hour=d.hour)
        sig, err, logs = run_program(src, ctx, timeout=self.timeout)
        if err is not None:
            return -1e6, f"static_check/exec: {err}" if "static_check" in (
                err or ""
            ) else f"exec: {err}\n{logs}"
        ok, reason = causality_probe(src, ctx, sig)
        if not ok:
            return -1e6, f"causality_probe: {reason}"
        best = -1e9
        for q in _QS:
            for delta in _DELTAS:
                for stop in _STOPS:
                    for kbars in _MAXHOLDS:
                        df = evaluate_deploy(
                            deploy_score=sig, close=d.close_bid, high=d.high_bid,
                            low=d.low_bid, spread=d.spread, cost=d.cost,
                            test_month=d.test_month, q=q, delta_pips=delta,
                            stop_pips=stop, max_hold=kbars, pip=self.pip,
                            commission_pips=self.commission_pips,
                        )
                        best = max(best, task_score(df))
        return float(best), logs
```

- [ ] **Step 4: Run — expect PASS.** `uv run pytest tests/era_scalp/test_range_integration.py -q`

- [ ] **Step 5: Commit**

```bash
git add scripts/era_scalp/range_score.py tests/era_scalp/test_range_integration.py
git commit -m "feat(era-scalp): RangeScorer (causal probe + bracket payoff grid sweep)"
```

---

## Task R4: Deploy seeds (literature streams)

**Files:**
- Create: `scripts/era_scalp/range_seeds.py`
- Test: `tests/era_scalp/test_range_seeds.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/era_scalp/test_range_seeds.py
import numpy as np

from scripts.era_scalp.context import FeatureContext
from scripts.era_scalp.load_splits import WHITELIST
from scripts.era_scalp.range_seeds import BASELINE_SEED_NAMES, DEPLOY_SEED_PROGRAMS, RESEARCH_IDEAS
from scripts.era_scalp.sandbox import causality_probe, run_program


def _ctx(n=400, seed=1):
    rng = np.random.default_rng(seed)
    X = np.abs(rng.standard_normal((n, len(WHITELIST))))  # nonneg-ish microstructure
    return FeatureContext(X=X, names=list(WHITELIST), hour=(np.arange(n) % 24).astype(float))


def test_expected_seeds_present():
    for name in ("range_vol_deploy", "meanrev_regime_deploy", "toxicity_gate_deploy",
                 "burst_veto_deploy", "spread_harvest_deploy"):
        assert name in DEPLOY_SEED_PROGRAMS
    for b in BASELINE_SEED_NAMES:
        assert b in DEPLOY_SEED_PROGRAMS


def test_all_seeds_run_causal_and_nondirectional():
    ctx = _ctx()
    bad = []
    for name, src in DEPLOY_SEED_PROGRAMS.items():
        sig, err, _ = run_program(src, ctx)
        if err is not None:
            bad.append(f"{name}: {err}")
            continue
        ok, reason = causality_probe(src, ctx, sig)
        if not ok:
            bad.append(f"{name}: {reason}")
            continue
        finite = sig[np.isfinite(sig)]
        if finite.size and finite.min() < 0:
            bad.append(f"{name}: emitted negative (should be non-directional >=0 or nan)")
    assert not bad, "; ".join(bad)


def test_research_ideas_cite_streams_and_combination():
    blob = " ".join(RESEARCH_IDEAS).lower()
    for kw in ["realized range", "variance ratio", "vpin", "hawkes", "avellaneda", "combine"]:
        assert kw in blob, f"missing idea keyword: {kw}"
```

- [ ] **Step 2: Run — expect FAIL.** `uv run pytest tests/era_scalp/test_range_seeds.py -q`

- [ ] **Step 3: Create `scripts/era_scalp/range_seeds.py`** (all causal, numpy-only, non-directional `deploy`; copy verbatim)

```python
"""Range-harvest deploy seeds (causal, numpy-only). deploy(ctx)->non-directional score.

Four literature streams fused by PUCT recombination:
realized-range/vol (Parkinson; Yang-Zhang; HAR-RV Corsi 2009),
mean-reversion regime (variance ratio Lo-MacKinlay 1988; OU half-life),
flow-toxicity veto (VPIN Easley-Lopez de Prado-O'Hara; OFI Cont-Kukanov-Stoikov),
Hawkes burst veto (Bacry-Mastromatteo-Muzy), spread-harvest (Avellaneda-Stoikov).
"""

DEPLOY_SEED_PROGRAMS: dict[str, str] = {
    # realized-range: deploy when trailing range is wide vs its own trailing average
    "range_vol_deploy": (
        "def deploy(ctx):\n"
        "    rng = ctx.col('bar_range_pips'); n = rng.shape[0]; W = 120\n"
        "    x = np.where(np.isfinite(rng), rng, 0.0)\n"
        "    k = np.arange(n); lo = np.maximum(0, k - W); m = (k - lo).astype(float)\n"
        "    ms = np.where(m > 0, m, 1.0)\n"
        "    c = np.concatenate(([0.0], np.cumsum(x)))\n"
        "    avg = (c[k] - c[lo]) / ms  # trailing mean range (excludes current)\n"
        "    out = x / (avg + 1e-9)  # wide-vs-normal; >=0\n"
        "    out[m < 20] = np.nan\n"
        "    return out\n"
    ),
    # mean-reversion regime: deploy when lag-1 return autocorr is negative (reverting).
    # score = max(0, -rho) so higher = more mean-reverting; non-directional.
    "meanrev_regime_deploy": (
        "def deploy(ctx):\n"
        "    r = ctx.col('vel_pips_h1'); n = r.shape[0]; W = 120\n"
        "    x = np.where(np.isfinite(r), r, 0.0); xp = np.concatenate(([0.0], x[:-1]))\n"
        "    k = np.arange(n); lo = np.maximum(0, k - W); m = (k - lo).astype(float)\n"
        "    ms = np.where(m > 0, m, 1.0)\n"
        "    cxx = np.concatenate(([0.0], np.cumsum(x * x)))\n"
        "    cxy = np.concatenate(([0.0], np.cumsum(x * xp)))\n"
        "    sxx = cxx[k] - cxx[lo]; sxy = cxy[k] - cxy[lo]\n"
        "    rho = sxy / (sxx + 1e-9)  # trailing lag-1 autocorr proxy\n"
        "    out = np.maximum(0.0, -rho)  # reverting (rho<0) -> deploy; non-directional\n"
        "    out[m < 20] = np.nan\n"
        "    return out\n"
    ),
    # toxicity veto: high realized range, but suppressed when signed flow imbalance is high
    "toxicity_gate_deploy": (
        "def deploy(ctx):\n"
        "    rng = ctx.col('bar_range_pips'); sgn = ctx.col('bar_return_sign')\n"
        "    vol = ctx.col('tick_volume'); n = rng.shape[0]; W = 60; a = 0.1\n"
        "    flow = np.where(np.isfinite(sgn) & np.isfinite(vol), sgn * vol, 0.0)\n"
        "    acc = 0.0; ewma = np.empty(n)\n"
        "    for i in range(n):\n"
        "        acc = (1 - a) * acc + a * flow[i]; ewma[i] = acc\n"
        "    vbar = np.where(np.isfinite(vol), np.abs(vol), 0.0) + 1.0\n"
        "    tox = np.abs(ewma) / (vbar + 1e-9)  # imbalance intensity\n"
        "    base = np.where(np.isfinite(rng), rng, 0.0)\n"
        "    out = np.where(tox <= np.nanmedian(tox), base, np.nan)\n"
        "    return out\n"
    ),
    # Hawkes burst veto: suppress deploy when EWMA tick intensity is elevated
    "burst_veto_deploy": (
        "def deploy(ctx):\n"
        "    inten = ctx.col('tick_burst_score'); rng = ctx.col('bar_range_pips')\n"
        "    n = inten.shape[0]; a = 0.2; acc = 0.0; ew = np.empty(n)\n"
        "    for i in range(n):\n"
        "        xi = inten[i] if np.isfinite(inten[i]) else 0.0\n"
        "        acc = (1 - a) * acc + a * max(xi, 0.0); ew[i] = acc\n"
        "    base = np.where(np.isfinite(rng), rng, 0.0)\n"
        "    return np.where(ew < 1.0, base, np.nan)  # calm -> deploy; bursting -> veto\n"
    ),
    # spread-harvest: deploy when spread is wide (more to capture) but flow balanced
    "spread_harvest_deploy": (
        "def deploy(ctx):\n"
        "    spz = ctx.col('spread_z'); sp = ctx.col('spread_pips')\n"
        "    sgn = ctx.col('bar_return_sign')\n"
        "    base = np.where(np.isfinite(sp), np.maximum(sp, 0.0), np.nan)\n"
        "    wide = np.isfinite(spz) & (spz > 0.0)\n"
        "    return np.where(wide, base, np.nan)\n"
    ),
}

# Canonical baselines the rediscovery tracer must regenerate when removed.
BASELINE_SEED_NAMES = ("range_vol_deploy", "meanrev_regime_deploy",
                       "toxicity_gate_deploy", "spread_harvest_deploy")

RESEARCH_IDEAS: list[str] = [
    "Realized range / volatility (Parkinson 1980; Yang-Zhang; HAR-RV Corsi 2009): deploy "
    "when the trailing realized range (bar_range_pips) or multi-scale realized vol is large "
    "vs cost - the band must be wide enough to harvest.",
    "Mean-reversion regime (variance ratio, Lo-MacKinlay 1988; Hurst; OU half-life): deploy "
    "when a causal trailing variance-ratio < 1 or lag-1 return autocorrelation is negative - "
    "price reverts from extremes rather than trending.",
    "Flow-toxicity veto (VPIN, Easley-Lopez de Prado-O'Hara; OFI, Cont-Kukanov-Stoikov): do "
    "NOT deploy when signed order-flow imbalance is high - one-sided flow breaks the range.",
    "Hawkes self-exciting bursts (Bacry-Mastromatteo-Muzy): veto deploy when EWMA tick "
    "intensity spikes - clustering precedes breakouts.",
    "Spread harvest (Avellaneda-Stoikov; Stoikov micro-price): deploy when the spread is wide "
    "AND flow is balanced - the wide-spread-benign-flow sweet spot, since maker entry earns "
    "the spread.",
    "Combine: gate any wide-range/vol deploy signal by BOTH a mean-reversion-regime test and "
    "a flow-toxicity (and burst) veto - the best detector is the intersection, not any single "
    "stream.",
]
```

- [ ] **Step 4: Run — expect PASS** (all 3 tests, esp. causal + non-directional). `uv run pytest tests/era_scalp/test_range_seeds.py -q`

- [ ] **Step 5: Commit**

```bash
git add scripts/era_scalp/range_seeds.py tests/era_scalp/test_range_seeds.py
git commit -m "feat(era-scalp): range-harvest deploy seeds (4 literature streams) + ideas"
```

---

## Task R5: Range prompt

**Files:**
- Create: `scripts/era_scalp/range_prompt.py`
- Test: `tests/era_scalp/test_range_prompt.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/era_scalp/test_range_prompt.py
def test_range_rules_cover_deploy_contract():
    from scripts.era.llm import build_prompt
    from scripts.era_scalp.range_prompt import DEPLOY_FEATURE_NAMES, RANGE_RULES

    p = build_prompt("def deploy(ctx):\n    return ctx.col('bar_range_pips')\n", 0.0, "", "idea",
                     rules=RANGE_RULES).lower()
    assert "deploy(ctx)" in p
    assert "non-directional" in p or "not predict a direction" in p
    assert "future" in p and ("trailing" in p or "expanding" in p)
    assert "bar_range_pips" in p
    assert "bar_range_pips" in DEPLOY_FEATURE_NAMES and "y_fwd" not in " ".join(DEPLOY_FEATURE_NAMES)
```

- [ ] **Step 2: Run — expect FAIL.** `uv run pytest tests/era_scalp/test_range_prompt.py -q`

- [ ] **Step 3: Create `scripts/era_scalp/range_prompt.py`**

```python
from __future__ import annotations

from scripts.era_scalp.load_splits import WHITELIST

DEPLOY_FEATURE_NAMES: list[str] = list(WHITELIST)

RANGE_RULES = (
    "You write `deploy(ctx) -> np.ndarray` for direction-agnostic 100-tick range scalping.\n"
    "Return a per-bar NON-DIRECTIONAL score: HIGH = 'a two-sided maker bracket is worth\n"
    "deploying at this bar', and np.nan = stand aside. You do NOT predict a direction -\n"
    "the harness rests BOTH a buy limit below and a sell limit above; whichever the market\n"
    "hits first sets the side, and it takes profit back at the center. Your only job is to\n"
    "detect WHEN the next window is range-bound and wide enough to harvest net of cost.\n"
    "Higher score = more confident; keep it >= 0 (magnitude only, no sign meaning).\n"
    "ctx.col(name) gives a causal per-bar feature; ctx.X is (n_bars x n_feat); ctx.n_bars;\n"
    "ctx.hour is UTC hour. `np` is available. NO imports.\n"
    "Causal features (all backward/as-of, NEVER forward):\n"
    f"  {', '.join(DEPLOY_FEATURE_NAMES)}\n"
    "No y_fwd/cost/future. Use the time axis causally (trailing/expanding/EWMA over bars\n"
    "<= k only; never x[k:], no centered windows, no full-sample stats). A causality probe\n"
    "perturbs future rows and REJECTS any program whose past output changes.\n"
    "Ingredients to combine (recent literature): realized-range/vol size (deploy when wide),\n"
    "mean-reversion regime (variance-ratio<1 / negative autocorrelation), flow-toxicity veto\n"
    "(suppress when order-flow imbalance is one-sided), Hawkes burst veto (suppress when tick\n"
    "intensity spikes), wide-spread-with-balanced-flow harvest. The best detector is usually\n"
    "the INTERSECTION of a wide-range signal and the regime/toxicity vetoes.\n"
    "PERFORMANCE: ~50k bars, run 3x; prefer vectorised cumsum windows over per-bar window\n"
    "loops (a single O(n) EWMA pass is fine); >10s is REJECTED. Output ONLY one ```python\n"
    "code block.\n"
)
```

- [ ] **Step 4: Run — expect PASS.** `uv run pytest tests/era_scalp/test_range_prompt.py -q`

- [ ] **Step 5: Commit**

```bash
git add scripts/era_scalp/range_prompt.py tests/era_scalp/test_range_prompt.py
git commit -m "feat(era-scalp): range-harvest generator prompt (deploy contract + ingredients)"
```

---

## Task R6: Driver

**Files:**
- Create: `scripts/era_scalp/run_era_range.py`
- Test: `tests/era_scalp/test_range_integration.py` (append)

- [ ] **Step 1: Write the failing test (append)**

```python
def test_select_seed_programs_ablation():
    from scripts.era_scalp.run_era_range import select_seed_programs

    full = select_seed_programs(no_baseline=False)
    ablated = select_seed_programs(no_baseline=True)
    for b in ("range_vol_deploy", "meanrev_regime_deploy", "toxicity_gate_deploy",
              "spread_harvest_deploy"):
        assert b in full and b not in ablated
    assert "burst_veto_deploy" in ablated


def test_run_search_with_mocked_writer():
    from scripts.era_scalp.run_era_range import run_search

    splits = {"validation": _data(), "holdout": _data(seed=2)}

    def fake_writer(parent_src, parent_score, logs, idea, cache_dir, rules=None, caller=None):
        return "def deploy(ctx):\n    return ctx.col('bar_range_pips')\n"

    nodes = run_search(splits, symbol="EURUSD", budget=3, writer=fake_writer, p_recombine=0.0)
    assert len(nodes) >= 3
    import numpy as np
    assert all(np.isfinite(n.score) for n in nodes)
```

- [ ] **Step 2: Run — expect FAIL.** `uv run pytest tests/era_scalp/test_range_integration.py -q`

- [ ] **Step 3: Create `scripts/era_scalp/run_era_range.py`**

```python
from __future__ import annotations

import argparse
import random
from pathlib import Path

import numpy as np

from scripts.era.llm import propose_program, recombine_program
from scripts.era.puct import Node, puct_search
from scripts.era.select import bh_fdr, holdout_pvalue
from scripts.era_scalp.bracket_harness import deploy_diagnostics, evaluate_deploy
from scripts.era_scalp.range_prompt import RANGE_RULES
from scripts.era_scalp.range_score import RangeScorer, _DELTAS, _MAXHOLDS, _PIP, _QS, _STOPS
from scripts.era_scalp.range_seeds import BASELINE_SEED_NAMES, DEPLOY_SEED_PROGRAMS, RESEARCH_IDEAS


def select_seed_programs(no_baseline: bool = False) -> dict:
    if not no_baseline:
        return dict(DEPLOY_SEED_PROGRAMS)
    return {k: v for k, v in DEPLOY_SEED_PROGRAMS.items() if k not in BASELINE_SEED_NAMES}


def finalize_selection(holdout_nets: dict, q: float = 0.10) -> list[str]:
    names = list(holdout_nets)
    pvals = np.array([holdout_pvalue(holdout_nets[n]["net"].to_numpy(float)) for n in names])
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
               cache_dir: str = "/tmp/era_range_cache", p_recombine: float = 0.3,
               seed_programs=None):
    ideas = ideas or RESEARCH_IDEAS
    seed_programs = seed_programs or DEPLOY_SEED_PROGRAMS
    scorer = RangeScorer(splits=splits, symbol=symbol)
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
                                              cache_dir=cache_dir, rules=RANGE_RULES)
            else:
                child_src = writer(parent.payload, parent.score, parent.logs,
                                   rng.choice(ideas), cache_dir=cache_dir, rules=RANGE_RULES)
        else:
            child_src = writer(parent.payload, parent.score, parent.logs,
                               rng.choice(ideas), cache_dir=cache_dir, rules=RANGE_RULES)
        s, lg = scorer.score(child_src, split_for_rank)
        child = Node(payload=child_src, score=s, parent=parent, logs=lg)
        all_nodes.append(child)
        return child

    return puct_search(forest, expand, budget=budget, c_puct=1.0, seed=seed)


def _best_holdout_df(src, d, symbol, commission_pips):
    from scripts.era_scalp.context import FeatureContext
    from scripts.era_scalp.sandbox import run_program

    ctx = FeatureContext(X=d.X, names=d.names, hour=d.hour)
    sig, err, _ = run_program(src, ctx)
    if err is not None:
        return None, {}
    pip = _PIP[str(symbol).upper()]
    best = None
    best_params = None
    for q in _QS:
        for delta in _DELTAS:
            for stop in _STOPS:
                for kbars in _MAXHOLDS:
                    df = evaluate_deploy(
                        deploy_score=sig, close=d.close_bid, high=d.high_bid, low=d.low_bid,
                        spread=d.spread, cost=d.cost, test_month=d.test_month, q=q,
                        delta_pips=delta, stop_pips=stop, max_hold=kbars, pip=pip,
                        commission_pips=commission_pips)
                    if len(df) >= 20 and (best is None or len(df) < len(best)):
                        best, best_params = df, (q, delta, stop, kbars)
    if best is None:
        return None, {}
    q, delta, stop, kbars = best_params
    diag = deploy_diagnostics(
        deploy_score=sig, close=d.close_bid, high=d.high_bid, low=d.low_bid,
        spread=d.spread, cost=d.cost, test_month=d.test_month, q=q, delta_pips=delta,
        stop_pips=stop, max_hold=kbars, pip=pip, commission_pips=commission_pips)
    return best, diag


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="EURUSD")
    ap.add_argument("--parquet", required=True)
    ap.add_argument("--max-hold", type=int, default=10)
    ap.add_argument("--budget", type=int, default=60)
    ap.add_argument("--no-baseline-seeds", action="store_true")
    ap.add_argument("--holdout-top", type=int, default=5)
    ap.add_argument("--score-max-bars", type=int, default=50000)
    ap.add_argument("--commission-pips", type=float, default=0.07)
    ap.add_argument("--out", default="/tmp/era_range/report.md")
    args = ap.parse_args()
    from scripts.era_scalp.load_splits import build_range_splits, cap_recent

    splits = build_range_splits(args.symbol, Path(args.parquet), max_hold=args.max_hold)
    cap = args.score_max_bars or None
    if cap and splits["validation"].X.shape[0] > cap:
        splits["validation"] = cap_recent(splits["validation"], cap)
    seed_programs = select_seed_programs(no_baseline=args.no_baseline_seeds)
    nodes = run_search(splits, symbol=args.symbol, budget=args.budget,
                       seed_programs=seed_programs)
    nodes.sort(key=lambda n: n.score, reverse=True)

    hold = splits["holdout"]
    top = nodes[: args.holdout_top]
    holdout_nets, diag_rows = {}, {}
    for i, nd in enumerate(top):
        df, diag = _best_holdout_df(nd.payload, hold, args.symbol, args.commission_pips)
        if df is None:
            continue
        holdout_nets[f"node{i}"] = df
        diag_rows[f"node{i}"] = diag
    survivors = finalize_selection(holdout_nets, q=0.10) if holdout_nets else []
    health = summarize_rejections(nodes)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w") as f:
        f.write(f"# ERA-range run — {args.symbol} 100tick (max_hold={args.max_hold})\n\n")
        f.write(f"nodes: {len(nodes)} | no_baseline_seeds={args.no_baseline_seeds} "
                f"| score_max_bars={cap}\n\n")
        f.write(f"## Search health: {health}\n\n")
        f.write(f"## BH-FDR holdout survivors (q=0.10): {survivors or 'none'}\n\n")
        f.write("## Top by validation score (with holdout diagnostics)\n\n")
        for i, nd in enumerate(top):
            d = diag_rows.get(f"node{i}", {})
            f.write(f"- val_score={nd.score:.4f} holdout={d}\n```python\n{nd.payload}\n```\n")
    print(f"wrote {args.out}; survivors={survivors}")


if __name__ == "__main__":
    main()
```

> `cap_recent` operates on the generic split fields it shares with `RangeSplitData`
> (`X`, `names`, `hour`, `test_month`); if `cap_recent`'s current implementation is typed
> to `ScalpSplitData` it must slice the `RangeSplitData` price arrays too — verify in Step 4
> and, if it only handles the directional fields, add a `RangeSplitData` branch (slice
> `close_bid/high_bid/low_bid/spread/cost`). Keep the change minimal and covered by a test.

- [ ] **Step 4: Run — expect PASS** (ablation + mocked-writer search). `uv run pytest tests/era_scalp/test_range_integration.py -q`

  If `cap_recent` does not slice `RangeSplitData` price arrays, add a dedicated
  `cap_recent_range(split, max_bars)` in `load_splits.py` (slicing all `RangeSplitData`
  arrays), import it in the driver instead, and add a one-line test asserting the capped
  split's `close_bid` length equals `max_bars`.

- [ ] **Step 5: Commit**

```bash
git add scripts/era_scalp/run_era_range.py scripts/era_scalp/load_splits.py tests/era_scalp/test_range_integration.py
git commit -m "feat(era-scalp): range-harvest driver (deploy search + holdout BH-FDR + diagnostics)"
```

---

## Task R7: Quality gate + open PR

- [ ] **Step 1: Full suite + quality**

Run: `uv run pytest -q tests/era_scalp/ tests/era/ && make quality`
Expected: all pass; `make quality` exit 0. Fix only new-file ruff issues (line length/imports); do not touch unrelated pre-existing INFO findings.

- [ ] **Step 2: Push + open PR** (branch off `main`, e.g. `era-range-harvest`)

```bash
git push -u origin era-range-harvest
gh pr create --base main --title "feat(era-scalp): direction-agnostic range-harvest scalping" --body "$(cat <<'EOF'
Adds a range-harvest mode to scripts/era_scalp/: programs emit a non-directional deploy(ctx)
regime score; a two-sided maker-bracket harness rests symmetric limits (market picks the
side), takes profit at the center, stops beyond the band, with conservative fills. Literature
seeds across four streams (realized-range/HAR-RV, variance-ratio/OU regime, VPIN/OFI toxicity
veto, Hawkes burst veto, Avellaneda-Stoikov spread-harvest), fused by PUCT recombination.
Maker entry earns the spread (the structural win over the directional variant).

Causal discipline: causality probe + audited feature whitelist (+ bar_range_pips). Honest
gates: K-bar embargo, full-holdout BH-FDR, search-health rejection accounting. Conservative
fast-loop fills; survivors promote to the existing tick-exact barrier-touch / OCO tickfill
layer (not in this PR).

Spec: docs/superpowers/specs/2026-05-30-era-range-harvest-scalping-design.md

Tests: tests/era_scalp/ (bracket harness, seeds, prompt, range splits, integration) + era
regressions; make quality green.

Live qwen evidence run to follow as a maintainer step.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Task R8: Opus live evidence run (maintainer step — NOT Haiku)

**Requires:** `OLLAMA_API_KEY` in `.env`, `data/analysis/tick_velocity/EURUSD_100tick_velocity.parquet`.

- [ ] **Step 1: Budget-6 smoke** on real data; confirm seeds score (no timeouts), report has Search-health + deploy diagnostics.

```bash
ERA_GEN_TEMP=0.8 uv run python -m scripts.era_scalp.run_era_range \
  --symbol EURUSD --parquet data/analysis/tick_velocity/EURUSD_100tick_velocity.parquet \
  --max-hold 10 --budget 6 --out /tmp/era_range/smoke.md
```

- [ ] **Step 2: Coverage (budget 80) + rediscovery (budget 40, `--no-baseline-seeds`).**

- [ ] **Step 3: Write evidence doc** `docs/analysis/era_range_harvest_evidence_<DATE>.md` — top programs, fill-rate, tp/sl/timeout rates, mean net, month consistency, BH-FDR holdout survivors, search-health, and an honest verdict (deployable only after tick-exact maker-fill verification + the governance ladder). Commit.

---

## Self-Review

**Spec coverage:** `deploy` contract → R3/R4/R5; two-sided maker bracket payoff (TP-center, break-SL, time-stop, maker entry, commission, conservative same-bar SL, ambiguous-skip) → R2; top-q deploy gate → R2 (`deploy_gate`); literature seeds (5 streams) + research ideas + recombination prompt → R4/R5; `bar_range_pips` + harness-side prices + K-embargo splits → R1; driver + holdout BH-FDR + search-health + ablation → R6; grid sweep (w/S/K/q) → R3; testing → each task; evidence → R8. All covered.

**Placeholder scan:** no TBD/TODO; every code step complete; commands have expected output. (R6 Step 3/4 flags a verify-and-maybe-extend on `cap_recent` — this is a concrete conditional with the exact fallback code path specified, not a placeholder.)

**Type/name consistency:** `deploy(ctx)` contract consistent R2–R6; `simulate_bracket(k, close, high, low, spread, delta_pips, stop_pips, max_hold, pip, commission_pips)` and `evaluate_deploy(...)`/`deploy_diagnostics(...)` kwargs consistent R2/R3/R6; the single `RangeSplitData` dataclass (`X, names, hour, close_bid, high_bid, low_bid, spread, cost, test_month`) is defined in R1 and reused everywhere — `RangeScorer` (R3) and the driver (R6) both consume it (no parallel `RangeScoreData`); `RangeScorer(splits, symbol, commission_pips=, timeout=)` + grid constants `_QS/_DELTAS/_STOPS/_MAXHOLDS/_PIP` consistent R3/R6; `select_seed_programs`/`finalize_selection`/`summarize_rejections`/`run_search(splits, symbol, budget, ...)` consistent R6; `RANGE_RULES`/`DEPLOY_FEATURE_NAMES` R5; `BASELINE_SEED_NAMES` R4/R6.
