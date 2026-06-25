# Crypto Flow "Smooth System" — Validation & Correction

**Date**: 2026-06-07
**Scope**: Independent validation of the kimi-2.6 claim that `h48_k5 + drawdown guard
+ momentum stop` achieves **Sharpe 4.66 (full) / 5.27 (holdout), max DD −10%, 1,719x**
and "survives even brutal execution."

**Verdict**: The headline is **not real**. Three of its four pillars are artifacts of
bugs in the overlay/holdout/adverse-selection scripts. The *underlying raw signal* does
have a statistically robust net edge in-sample on this universe, but it is a
high-turnover, **~−40% max-drawdown** book with Sharpe ~1.5 — not a Sharpe-4.66 /
−10%-DD machine, and the "smoothing" overlays **hurt** once look-ahead is removed.

---

## 1. Reproduction (numbers match exactly)

Reproduced against the cached parquet (`/tmp/crypto_broad_perp.parquet`, 59 survivor
symbols, w24 h48 k5, 2020–2025). Each correction applied one at a time:

| Configuration | Sharpe | max DD | final |
|---|---|---|---|
| **kimi headline** (free cost, √365 ann, look-ahead overlays) | **+5.00** | **−7.9%** | **2101x** |
| fix annualization only (√182.5) | +3.53 | −7.9% | 2101x |
| + overlays made causal (shift +1) | +1.49 | **−32.5%** | **14.7x** |
| + realistic retail maker cost | ~1.0–1.5 | ~−40% | ~4–53x |
| **Holdout 2025 "5.27"** → run causally | **+0.4 to +1.1** | −13/−14% | ~1.0–1.14x |

## 2. The three flaws

### Flaw 1 — Look-ahead in BOTH overlays (dominant)
`apply_guard` / `apply_mom_stop` computed the drawdown (or trailing return) *including
the current period's return* and then scaled *that same period's* return:

```python
dd = (cum.iloc[i] - peak) / peak     # cum[i] includes s[i]
scale.iloc[i] = 0.0 / 0.25           # ...applied back onto s[i]
```

The guard cut the loss on the exact bar the loss occurred. Removing it (shift the scale
forward one period) **erases the entire drawdown miracle**: max DD −7.9% → −32.5%, final
2101x → 14.7x. Done honestly, the overlays *reduce* performance (baseline Sharpe 1.59 →
combined 1.19; see `crypto_flow_overlay_findings.md`). The "−61.7% → −10.1%" and the
holdout "2.83 → 5.27" improvements were 100% this bug (the guard itself "sat inactive",
so all the holdout lift was the look-ahead momentum stop).

### Flaw 2 — Wrong Sharpe annualization
Scripts used `np.sqrt(365)` but the book rebalances every **48h = 2-day periods**
(182.5/yr, not 365). Flat **×1.41 inflation** on every Sharpe (5.00 → 3.53). The engine's
own `metrics()` already did this right (`sqrt(BARS_PER_YEAR/h)`); the overlay scripts
regressed.

### Flaw 3 — "Free trading"
Every smooth/holdout/adverse script set `maker_rebate_bps = spread_bps = 2.0`, making
`cost_per_turn ≡ 0`. A 2 bps maker **rebate** is not retail reality (Binance USD-M retail
maker ≈ +1 bps fee; earlier Stage-2/3 fee models used a 0.2 bps rebate). Realistic cost is
~11–14 bps/period on turnover ≈ 3.0 — real money. The adverse-selection "survives
p_fill=0.5 / adv=2.0" claim only held because the rebate was pinned to the spread, so the
maker leg stayed free no matter what `p_fill` did — the test never stressed the assumption
that actually makes it free.

### (Also) Survivorship
`SYMS` is 59 coins hand-picked that still trade in 2026, plus a ≥5000-bar filter — no
delisted perps. All numbers are in-sample on survivors with the config (w24 h48 k5) itself
chosen on that same data.

## 3. What is actually true

The **raw signal** (no overlay), net of a realistic retail maker model
(`rebate 0.2 / queue 0.2 / adv 0.5 / p_fill 0.85`), passes the project's own gauntlet:

```
CORRECTED baseline (w24 h48 k5, realistic retail maker cost), 65 months
  gross ≈ +60 bps/period   cost ≈ +11–14 bps   net ≈ +46 bps/period
  Bayesian P(edge>0) = 0.995   94% CI [+0.013, +0.088]
  Block-bootstrap 90% CI = [+0.034, +0.110]
  Temporal P(edge>0) = 0.909   worst-window = 0.869   frac windows positive = 100%
  DSR = 0.981
```

So the **signal is real** (consistent with the earlier "gross edge real" finding), but its
honest profile is **Sharpe ~1.5 with ~−40% drawdowns**, and the drawdown-guard / momentum
overlays do not improve it out-of-sample — they reduce it.

**Remaining caveats (not resolved here)**: survivorship in the universe; the config was
selected in-sample; the DSR trial pool is small (9 trials → DSR optimistic); the net edge
still assumes you reliably get *maker* fills.

## 4. Fixes applied

- New canonical module `scripts/research/crypto_flow_overlays.py`: causal `drawdown_guard`
  / `momentum_stop` / `vol_target`, h-aware `ann_factor` / `metrics`, and a realistic
  `RETAIL_MAKER` fee model + `cost_per_turn`.
- `crypto_flow_smooth_overlay.py`, `crypto_flow_holdout_combined.py`,
  `crypto_flow_adverse_selection.py` rewired to import the canonical module (no more
  rebate==spread, no √365, no look-ahead).
- Guard test `tests/test_crypto_flow_overlays.py` locks all three bugs out.

> Note: the tainted artifacts that produced the inflated headline were **removed** in this
> PR — scripts `crypto_flow_smooth.py`, `crypto_flow_smooth_full.py`,
> `crypto_flow_explore_smooth.py`, `crypto_flow_explore_more.py`,
> `crypto_flow_signal_enhance.py`, `crypto_flow_holdout_guard.py`, and their findings/
> synthesis docs (`*_smooth_findings.md`, `*_explore_smooth.md`, `*_explore_more.md`,
> `*_signal_enhance.md`, `*_holdout_guard.md`, `*_smooth_system_synthesis.md`,
> `*_ab_sector_synthesis.md`). This note is the surviving record. The legitimate sector
> concentration finding is retained in `2026-06-07_crypto_flow_sector_check.md`.
