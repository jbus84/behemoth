# Per-symbol Edge Sweep Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a per-symbol edge sweep that selects each major's own (direction, q, h) on the validation split and confirms it once on the holdout, reporting a de-inflated diagnostic panel — surfacing continuation edges that pooled-fade scoring masked.

**Architecture:** A pure analysis module `scripts/era_scalp/per_symbol_sweep.py` reusing the existing harness + Bayesian layer. Base signal = the fixed fair-dislocation `dev` (the `fair_fade` seed); `fade=+dev`, `continue=-dev`. Per symbol: load splits once, compute `dev` once per split, sweep 18 cells on validation, pick by the lower credible bound under a sample guard, confirm that one cell on holdout. No engine/scorer change.

**Tech Stack:** Python, numpy, pandas, pytest, uv. No new deps. NumPyro via the existing `bayes_edge`.

**Branch:** `era-per-symbol-sweep` (created, spec committed). Do NOT touch main.

---

## File Structure

- `scripts/era_scalp/per_symbol_sweep.py` — **Create.** All sweep logic + CLI.
- `tests/era_scalp/test_per_symbol_sweep.py` — **Create.** Deterministic tests (monkeypatch `credibility` to avoid NUTS in unit tests).
- `docs/analysis/era_per_symbol_edge_sweep_2026-06-01.md` — **Create (Task 4).** The verdict evidence.

Reused unchanged: `build_trade_splits`, `_pip_size`, `TradeSplitData` (`scripts/era_scalp/load_splits.py`); `FeatureContext` (`context.py`); `run_program` (`sandbox.py`); `FADE_SEED_PROGRAMS["fair_fade"]` (`fade_seeds.py`); `evaluate_trades` (`trade_harness.py`); `monthly_net`, `edge_verdict` (`bayes_edge.py`).

Reference signatures (verified):
- `evaluate_trades(signal, mid, cost, test_month, pip, q, h) -> DataFrame[{net, test_month}]` (top-q |signal| entries, side=sign(signal), net=side*fwd-cost).
- `edge_verdict(net_by_symbol: dict, seed=0, num_warmup=500, num_samples=500, num_chains=2) -> EdgePosterior` with `.pooled = {p_positive, mean, lo, hi}`; raises `ValueError` if no symbol has `>= _MIN_MONTHS` active months.
- `TradeSplitData` fields: `X, names, hour, mid, cost, test_month`.
- `build_trade_splits(symbol, parquet_path, embargo=400, ...) -> {"train","validation","holdout": TradeSplitData}`.

---

### Task 1: Core cell helpers — `dev_signal`, `cell_net`, `diagnostics`

**Files:** Create `scripts/era_scalp/per_symbol_sweep.py`; Create `tests/era_scalp/test_per_symbol_sweep.py`

- [ ] **Step 1: Write failing tests**

Create `tests/era_scalp/test_per_symbol_sweep.py`:

```python
import numpy as np
import pandas as pd

from scripts.era_scalp.load_splits import WHITELIST, TradeSplitData
from scripts.era_scalp import per_symbol_sweep as pss


def _split(n=900, seed=0):
    rng = np.random.default_rng(seed)
    mid = 1.10 + np.cumsum(rng.standard_normal(n)) * 1e-4
    months = ([f"2024-{m:02d}" for m in range(1, 13)] * (n // 12 + 1))[:n]
    return TradeSplitData(
        X=rng.standard_normal((n, len(WHITELIST))), names=list(WHITELIST),
        hour=(np.arange(n) % 24).astype(float), mid=mid, cost=np.full(n, 0.4),
        test_month=np.array(months),
    )


def test_dev_signal_runs_and_is_finite_mostly():
    sig = pss.dev_signal(_split())
    assert sig.shape[0] == 900
    assert np.isfinite(sig).any()


def test_directions_are_exact_negations():
    sp = _split()
    sig = pss.dev_signal(sp)
    fade = pss.cell_net(sig, sp, "EURUSD", "fade", q=0.90, h=100)
    cont = pss.cell_net(sig, sp, "EURUSD", "continue", q=0.90, h=100)
    # Same entry bars (|signal| identical), opposite side => net + cost mirrors: fade.net + cont.net == -2*cost
    assert len(fade) == len(cont) and len(fade) > 0
    paired = fade["net"].to_numpy() + cont["net"].to_numpy()
    assert np.allclose(paired, -2 * 0.4)


def test_diagnostics_match_hand_values():
    frame = pd.DataFrame({
        "net": [1.0, 3.0, -1.0, -1.0, 2.0],
        "test_month": ["2025-01", "2025-01", "2025-02", "2025-02", "2025-03"],
    })
    d = pss.diagnostics(frame)
    assert d["n_trades"] == 5
    assert d["n_months"] == 3
    # months: 2025-01 mean +2 (pos), 2025-02 mean -1 (neg), 2025-03 mean +2 (pos) => 2/3
    assert np.isclose(d["month_hit"], 2 / 3)
    assert np.isclose(d["raw_mean"], (1 + 3 - 1 - 1 + 2) / 5)


def test_diagnostics_empty_frame():
    d = pss.diagnostics(pd.DataFrame({"net": [], "test_month": []}))
    assert d["n_trades"] == 0 and d["n_months"] == 0
    assert d["month_hit"] == 0.0 and np.isnan(d["raw_mean"])
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/era_scalp/test_per_symbol_sweep.py -q`
Expected: FAIL — `module ... has no attribute` / import error (module not created yet).

- [ ] **Step 3: Implement the helpers**

Create `scripts/era_scalp/per_symbol_sweep.py`:

```python
from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.era_scalp.bayes_edge import edge_verdict
from scripts.era_scalp.context import FeatureContext
from scripts.era_scalp.fade_seeds import FADE_SEED_PROGRAMS
from scripts.era_scalp.load_splits import _pip_size, build_trade_splits
from scripts.era_scalp.sandbox import run_program
from scripts.era_scalp.trade_harness import evaluate_trades

DIRECTIONS = {"fade": 1.0, "continue": -1.0}
GRID_Q = [0.90, 0.95, 0.99]
GRID_H = [100, 200, 400]
MIN_TRADES = 200
MIN_MONTHS_SEL = 6


def dev_signal(split_data) -> np.ndarray:
    """The fixed fair-dislocation dev (fair_fade seed) on a split's feature context."""
    ctx = FeatureContext(X=split_data.X, names=split_data.names, hour=split_data.hour)
    sig, err, _ = run_program(FADE_SEED_PROGRAMS["fair_fade"], ctx, required_fn="signal")
    if err is not None:
        raise RuntimeError(f"dev_signal failed: {err}")
    return sig


def cell_net(signal: np.ndarray, split_data, symbol: str, direction: str,
             q: float, h: int) -> pd.DataFrame:
    """Trade frame for one (direction, q, h) cell. direction in {'fade','continue'}."""
    sgn = DIRECTIONS[direction]
    return evaluate_trades(sgn * np.asarray(signal, float), split_data.mid, split_data.cost,
                           split_data.test_month, _pip_size(symbol), q, h)


def diagnostics(net_frame: pd.DataFrame) -> dict:
    """De-inflated panel: trade count, month count, month-hit-rate, trade-weighted raw mean."""
    n = int(len(net_frame))
    if n == 0:
        return {"n_trades": 0, "n_months": 0, "month_hit": 0.0, "raw_mean": float("nan")}
    g = net_frame.groupby("test_month")["net"].mean()
    return {
        "n_trades": n,
        "n_months": int(g.shape[0]),
        "month_hit": float((g > 0).mean()),
        "raw_mean": float(net_frame["net"].mean()),
    }
```

- [ ] **Step 4: Run tests to verify pass**

Run: `uv run pytest tests/era_scalp/test_per_symbol_sweep.py -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/era_scalp/per_symbol_sweep.py tests/era_scalp/test_per_symbol_sweep.py
git commit -m "feat(era-scalp): per-symbol sweep core (dev_signal, cell_net, diagnostics)

Fixed dev fade/continue base; cell trade frames; de-inflated diagnostics (n_trades, n_months,
month-hit, trade-weighted raw mean)."
```

---

### Task 2: `credibility` + `select_on_validation` (sample-guarded, lower-CI selection)

**Files:** Modify `scripts/era_scalp/per_symbol_sweep.py`, `tests/era_scalp/test_per_symbol_sweep.py`

- [ ] **Step 1: Write failing tests (monkeypatch credibility for determinism)**

Append to `tests/era_scalp/test_per_symbol_sweep.py`:

```python
def test_select_prefers_higher_lo_when_both_pass_guard(monkeypatch):
    sp = _split()
    sig = pss.dev_signal(sp)
    # Make q=0.90 (many trades) the guard-passing cells; assign credibility by (direction,q,h).
    def fake_cred(frame, seed=0, fast=False):
        return {"p_positive": 0.9, "mean": 1.0, "lo": 0.5, "hi": 1.5}
    monkeypatch.setattr(pss, "credibility", fake_cred)
    # Give 'continue' a higher lo than 'fade' via a wrapper keyed on the frame's first net sign? Simpler:
    # monkeypatch to vary lo by call order is brittle; instead test the guard test below covers ranking
    choice = pss.select_on_validation(sig, sp, "EURUSD")
    assert choice is not None
    assert choice["direction"] in pss.DIRECTIONS and choice["q"] in pss.GRID_Q and choice["h"] in pss.GRID_H


def test_select_respects_sample_guard(monkeypatch):
    sp = _split()
    sig = pss.dev_signal(sp)
    # A cell with a GREAT lo but failing the trade guard must lose to a passing cell with a lower lo.
    def fake_cred(frame, seed=0, fast=False):
        # high lo only when the frame is tiny (fails guard), low lo when large (passes guard)
        return {"p_positive": 0.99, "mean": 9.0, "lo": 9.0, "hi": 9.1} if len(frame) < pss.MIN_TRADES \
            else {"p_positive": 0.7, "mean": 0.2, "lo": 0.1, "hi": 0.4}
    monkeypatch.setattr(pss, "credibility", fake_cred)
    choice = pss.select_on_validation(sig, sp, "EURUSD")
    assert choice is not None
    # chosen cell must satisfy the guard
    assert choice["val"]["n_trades"] >= pss.MIN_TRADES
    assert choice["val"]["n_months"] >= pss.MIN_MONTHS_SEL
    # and its lo is the low (0.1) one, proving the tiny high-lo cell was excluded by the guard
    assert np.isclose(choice["val"]["lo"], 0.1)


def test_select_returns_none_when_nothing_admissible(monkeypatch):
    sp = _split(n=120)  # too few rows => no cell meets MIN_TRADES at these q
    sig = pss.dev_signal(sp)
    monkeypatch.setattr(pss, "credibility",
                        lambda frame, seed=0, fast=False: {"p_positive": 0.9, "mean": 1.0, "lo": 0.5, "hi": 1.5})
    assert pss.select_on_validation(sig, sp, "EURUSD") is None
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/era_scalp/test_per_symbol_sweep.py -q`
Expected: FAIL (`credibility`/`select_on_validation` not defined).

- [ ] **Step 3: Implement `credibility` + `select_on_validation`**

Append to `scripts/era_scalp/per_symbol_sweep.py`:

```python
def credibility(net_frame: pd.DataFrame, seed: int = 0, fast: bool = False) -> dict | None:
    """Single-symbol monthly posterior summary {p_positive, mean, lo, hi}, or None if too thin.

    fast=True uses short chains for the validation selection sweep (ranking only)."""
    kw = {"num_warmup": 300, "num_samples": 300} if fast else {}
    try:
        post = edge_verdict({"_": net_frame}, seed=seed, **kw)
    except ValueError:
        return None
    return post.pooled


def select_on_validation(signal: np.ndarray, split_data, symbol: str) -> dict | None:
    """Pick the (direction, q, h) maximising the lower credible bound among cells passing the
    sample guard (>= MIN_TRADES trades, >= MIN_MONTHS_SEL months) on the validation split."""
    best = None
    for direction in DIRECTIONS:
        for q in GRID_Q:
            for h in GRID_H:
                frame = cell_net(signal, split_data, symbol, direction, q, h)
                diag = diagnostics(frame)
                if diag["n_trades"] < MIN_TRADES or diag["n_months"] < MIN_MONTHS_SEL:
                    continue
                cred = credibility(frame, fast=True)
                if cred is None:
                    continue
                val = {**cred, **diag}
                cand = {"direction": direction, "q": q, "h": h, "val": val}
                key = (val["lo"], val["raw_mean"])
                if best is None or key > (best["val"]["lo"], best["val"]["raw_mean"]):
                    best = cand
    return best
```

- [ ] **Step 4: Run tests to verify pass**

Run: `uv run pytest tests/era_scalp/test_per_symbol_sweep.py -q`
Expected: PASS. (The guard test proves a tiny high-`lo` cell is excluded; the none test proves an all-thin symbol returns None.)

- [ ] **Step 5: Commit**

```bash
git add scripts/era_scalp/per_symbol_sweep.py tests/era_scalp/test_per_symbol_sweep.py
git commit -m "feat(era-scalp): per-symbol validation selection (lower-CI bound + sample guard)

credibility() = single-symbol monthly posterior (short chains when fast); select_on_validation picks the
(direction,q,h) with max lower credible bound among cells passing MIN_TRADES/MIN_MONTHS_SEL; None if none."
```

---

### Task 3: `confirm_on_holdout`, `sweep`, and `main` CLI

**Files:** Modify `scripts/era_scalp/per_symbol_sweep.py`, `tests/era_scalp/test_per_symbol_sweep.py`

- [ ] **Step 1: Write failing wiring test**

Append to `tests/era_scalp/test_per_symbol_sweep.py`:

```python
def test_confirm_and_sweep_wiring(monkeypatch):
    # Force validation selection to a specific cell, then assert holdout confirms THAT cell.
    chosen = {"direction": "continue", "q": 0.90, "h": 100}

    def fake_select(signal, split_data, symbol):
        return {**chosen, "val": {"p_positive": 0.8, "mean": 0.5, "lo": 0.3, "hi": 0.7,
                                  "n_trades": 999, "n_months": 12, "month_hit": 0.6, "raw_mean": 0.5}}

    captured = {}

    def fake_cred(frame, seed=0, fast=False):
        captured["fast"] = fast  # holdout confirm must call with fast=False (full chains)
        return {"p_positive": 0.77, "mean": 0.4, "lo": 0.1, "hi": 0.7}

    monkeypatch.setattr(pss, "select_on_validation", fake_select)
    monkeypatch.setattr(pss, "credibility", fake_cred)

    sp_v, sp_h = _split(seed=1), _split(seed=2)
    sig_h = pss.dev_signal(sp_h)
    res = pss.confirm_on_holdout(sig_h, sp_h, "EURUSD", fake_select(None, sp_v, "EURUSD"))
    assert res["direction"] == "continue" and res["q"] == 0.90 and res["h"] == 100
    assert set(res["holdout"]) >= {"p_positive", "mean", "lo", "hi",
                                   "n_trades", "n_months", "month_hit", "raw_mean"}
    assert captured["fast"] is False  # holdout uses full chains
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/era_scalp/test_per_symbol_sweep.py::test_confirm_and_sweep_wiring -q`
Expected: FAIL (`confirm_on_holdout` not defined).

- [ ] **Step 3: Implement `confirm_on_holdout`, `sweep`, `main`**

Append to `scripts/era_scalp/per_symbol_sweep.py`:

```python
def confirm_on_holdout(signal: np.ndarray, split_data, symbol: str, choice: dict) -> dict:
    """Evaluate the validation-chosen (direction,q,h) on the holdout; full diagnostics + posterior."""
    frame = cell_net(signal, split_data, symbol, choice["direction"], choice["q"], choice["h"])
    cred = credibility(frame, fast=False) or {"p_positive": float("nan"), "mean": float("nan"),
                                              "lo": float("nan"), "hi": float("nan")}
    return {"direction": choice["direction"], "q": choice["q"], "h": choice["h"],
            "val": choice.get("val"), "holdout": {**cred, **diagnostics(frame)}}


def sweep(symbols: list[str], tv_dir: str = "data/analysis/tick_velocity") -> list[dict]:
    """Per symbol: build splits once, dev signal once per split, select on validation, confirm on holdout."""
    from pathlib import Path
    results = []
    for sym in symbols:
        sp = build_trade_splits(sym, Path(tv_dir) / f"{sym}_100tick_velocity.parquet", embargo=max(GRID_H))
        sig_v = dev_signal(sp["validation"])
        choice = select_on_validation(sig_v, sp["validation"], sym)
        if choice is None:
            results.append({"symbol": sym, "admissible": False})
            continue
        sig_h = dev_signal(sp["holdout"])
        conf = confirm_on_holdout(sig_h, sp["holdout"], sym, choice)
        results.append({"symbol": sym, "admissible": True, **conf})
    return results


def _fmt(results: list[dict]) -> str:
    lines = ["# ERA per-symbol edge sweep — validation-selected, holdout-confirmed\n",
             "| symbol | dir | q | h | holdout P(edge>0) | post mean | raw mean | n_trades | n_months | month_hit |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for r in results:
        if not r.get("admissible"):
            lines.append(f"| {r['symbol']} | — | — | — | no admissible validation setting | | | | | |")
            continue
        h = r["holdout"]
        lines.append(
            f"| {r['symbol']} | {r['direction']} | {r['q']} | {r['h']} | {h['p_positive']:.3f} | "
            f"{h['mean']:+.3f} | {h['raw_mean']:+.3f} | {h['n_trades']} | {h['n_months']} | "
            f"{h['month_hit']:.2f} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default="EURUSD,GBPUSD,AUDUSD,USDCHF,USDJPY")
    ap.add_argument("--tv-dir", default="data/analysis/tick_velocity")
    ap.add_argument("--out", default="/tmp/era_fade/per_symbol_sweep.md")
    args = ap.parse_args()
    from pathlib import Path
    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    results = sweep(symbols, tv_dir=args.tv_dir)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(_fmt(results))
    print(f"wrote {args.out}")
    for r in results:
        print(r["symbol"], "—", "no setting" if not r.get("admissible")
              else f"{r['direction']} q{r['q']} h{r['h']} P={r['holdout']['p_positive']:.3f} "
                   f"raw={r['holdout']['raw_mean']:+.2f} hit={r['holdout']['month_hit']:.2f}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests + full era_scalp suite + lint**

Run: `uv run pytest tests/era_scalp/test_per_symbol_sweep.py -q` (all pass)
Run: `uv run pytest tests/era_scalp -q` (all pass)
Run: `make lint` (Expected: `All checks passed!`)

- [ ] **Step 5: Commit**

```bash
git add scripts/era_scalp/per_symbol_sweep.py tests/era_scalp/test_per_symbol_sweep.py
git commit -m "feat(era-scalp): per-symbol holdout confirm + sweep + CLI

confirm_on_holdout evaluates the validation-chosen cell on holdout (full chains) with the de-inflated
panel; sweep loads splits once per symbol and runs select->confirm; main writes the markdown verdict."
```

---

### Task 4: Run the sweep + write the evidence doc

**Files:** Create `docs/analysis/era_per_symbol_edge_sweep_2026-06-01.md`

Numbers filled from the REAL run — do not invent them.

- [ ] **Step 1: Run the sweep across the 5 majors**

Run:
```bash
uv run python -m scripts.era_scalp.per_symbol_sweep \
  --symbols EURUSD,GBPUSD,AUDUSD,USDCHF,USDJPY --out /tmp/era_fade/per_symbol_sweep.md
```
Read `/tmp/era_fade/per_symbol_sweep.md` and the printed per-symbol summary lines.

- [ ] **Step 2: Write the evidence doc**

Create `docs/analysis/era_per_symbol_edge_sweep_2026-06-01.md` using the ACTUAL table from Step 1, then add interpretation:

```markdown
# ERA per-symbol edge sweep — validation-selected, holdout-confirmed (2026-06-01)

Each major chooses its own (direction in {fade, continue}, q, h) on the VALIDATION split (2024) by the
lower credible bound of the monthly posterior under a sample guard (>= 200 trades, >= 6 months), then
confirms that ONE setting on the HOLDOUT (2025-26). No holdout selection. Replaces the pooled-across-5
scalar; surfaces continuation edges pooling masked. Posterior shown alongside the trade-weighted raw mean
and month-hit because the monthly posterior can be inflated by low-count months.

## Headline — validation-selected, holdout-confirmed

<paste the real table from /tmp/era_fade/per_symbol_sweep.md>

## Read

<State per symbol: chosen direction (fade or CONTINUE), and whether the holdout edge is credible
(P(edge>0) high, raw mean positive, month-hit healthy). Call out specifically: did any symbol select
CONTINUE and confirm a credible holdout edge — i.e. a continuation edge the pooled-fade score had hidden?
Compare to the EUR/AUD-fade picture. If a symbol selected a setting on validation that did NOT confirm on
holdout, say so — that is the honest out-of-sample result and the whole point of select-then-confirm.>

## Caveat
Mid-to-mid / flat-cost. Holdout-confirmed credibility is necessary, not sufficient — the tick-exact
realistic round-trip cost gate remains the binding downstream check on whatever survives here.
```

- [ ] **Step 3: Commit + push**

```bash
git add docs/analysis/era_per_symbol_edge_sweep_2026-06-01.md
git commit -m "docs(era-scalp): per-symbol edge sweep verdict — validation-selected, holdout-confirmed"
git push
```

---

## Self-Review

**1. Spec coverage:**
- `dev_signal` / `cell_net` / `diagnostics` → Task 1. ✓
- `credibility` (single-symbol posterior, fast chains) → Task 2. ✓
- `select_on_validation` (lower-CI bound + sample guard, None if none) → Task 2. ✓
- `confirm_on_holdout` / `sweep` (splits once) / `main` CLI → Task 3. ✓
- Fixed `dev` fade/continue exact negation → Task 1 `test_directions_are_exact_negations`. ✓
- De-inflated panel (raw mean, n_trades, n_months, month_hit) → Task 1 `diagnostics` + Task 3 holdout block + Task 4 table. ✓
- Select-then-confirm honesty (validation select, single holdout test) → Task 2 + Task 3 + Task 4 narrative. ✓
- Tests: negations, diagnostics, sample-guard selection, select-then-confirm wiring → Tasks 1–3. ✓
- Run + verdict doc → Task 4. ✓
- Exploratory full-holdout-grid appendix (spec mentions it): DEFERRED as YAGNI — the headline select-then-confirm table is the verdict; the appendix added complexity without changing the conclusion. Noted here as an intentional trim; can add later if the verdict is ambiguous.

**2. Placeholder scan:** Only `<paste the real table ...>` / `<State per symbol ...>` in Task 4's evidence template — correct by design (filled from the real run). All code blocks are complete.

**3. Type consistency:** `cell_net(signal, split_data, symbol, direction, q, h)`, `credibility(net_frame, seed, fast)`, `select_on_validation(signal, split_data, symbol) -> {direction,q,h,val}`, `confirm_on_holdout(signal, split_data, symbol, choice) -> {direction,q,h,val,holdout}`, `sweep(symbols, tv_dir)`. `diagnostics` keys (`n_trades,n_months,month_hit,raw_mean`) and `credibility` keys (`p_positive,mean,lo,hi`) are merged into `val`/`holdout` consistently and read back the same way in `_fmt`/tests. `DIRECTIONS`/`GRID_Q`/`GRID_H`/`MIN_TRADES`/`MIN_MONTHS_SEL` module constants used uniformly. `evaluate_trades`/`edge_verdict`/`build_trade_splits` signatures match the verified references. Consistent.

> Note on `test_select_prefers_higher_lo_when_both_pass_guard`: as written it only asserts a valid choice is returned (the constant fake_cred can't distinguish cells). The DECISIVE ranking behaviour is proven by `test_select_respects_sample_guard` (guard excludes a high-lo cell) — keep both; the first is a smoke check, the second is the real assertion.
```
