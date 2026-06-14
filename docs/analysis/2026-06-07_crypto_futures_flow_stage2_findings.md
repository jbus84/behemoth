# Crypto Perp Cross-Sectional Flow + Positioning + Funding (Stage 2) — Findings

**Date:** 2026-06-07
**Branch:** `worktree-crypto-futures-flow`
**Status:** Most promising configuration found — holdout maker net positive & ~significant — but **regime-dependent and adverse-selection-sensitive; a lead, not a confirmed edge.**

## What this is

Stage-2 moved into **perpetual futures** (deliberately — the richer free signals only exist for
derivatives). Combines three free data sources into a **concentrated** dollar-neutral
cross-sectional book (top-k/bottom-k, k=5, rebalance every 6h, 20 liquid USDT perps):
1. **Spot order-flow imbalance** (Stage-1 signal).
2. **Futures positioning** from free Binance `metrics`: top-trader L/S, global L/S, OI change.
3. **Funding carry** (rate as P&L *and* as a fade-high-funding signal).

Combined cross-sectional score = `+z(OFI) − z(top-trader L/S) − z(global L/S) + z(OI-chg) [− z(funding)]`.

## Why we went to futures (and the gate that justified it)

Free **futures positioning** signals beat the coarse spot OFI at the cross-sectional IC level,
OOS-stable: **top-trader L/S IC −0.023 (t=−8.8 val, −5.1 holdout)** — ~2× OFI, *negative* (fade
crowded smart-money longs); global L/S −0.011; OI-change +0.012. These are orthogonal to flow.
That passed the Stage-2 decision gate (stronger gross than coarse data).

## Verified results (taker 5 bps/side, maker 2 bps/side; adv = adverse-selection haircut)

**HOLDOUT 2025** (the strong period):
| variant | taker | maker(adv0) | maker(adv0.5) | mean funding P&L |
|---|---|---|---|---|
| base | +2.70 (t0.75) | +7.88 (t2.19, 80%) | +2.21 (t1.23) | +0.24 |
| +funding P&L | +2.95 (t0.82) | +8.12 (t2.26) | +2.46 (t1.37) | +0.24 |
| **+funding signal+P&L** | **+3.35 (t0.95, 80%)** | **+8.36 (t2.36, 80%)** | **+2.86 (t1.62)** | +0.70 |

**V1 2024-H1** (the weak period):
| variant | taker | maker(adv0) | maker(adv0.5) |
|---|---|---|---|
| +funding signal+P&L | −2.30 (t−0.6) | +2.33 (t0.63) | +0.13 |

(bps per 6h rebalance. Concentration cut turnover ~85% vs the full-book version: ~5–6k legs vs
38.8k over 2024–25.)

## Read

**Genuinely positive:**
- **Funding carry is systematically positive** (+0.2 to +0.7 bps) — the book *earns* carry by
  shorting high-funding crowded pairs, exactly as hypothesised; additive.
- **Concentration (top-k) fixed the turnover** (~85% fewer legs) and *raised* gross (captures the
  extreme-signal names) — best of both.
- **Holdout maker is positive and ~significant**: +8.36 bps adv0 (t=2.36, 80% positive months),
  +2.86 adv0.5 (t=1.62). Even holdout *taker* turns positive (+3.35) for the first time.
- This is the strongest, most coherent configuration in the entire project.

**Caveats that keep it from "edge":**
1. **Regime-dependent** — strong in 2025 (holdout), **weak in 2024** (V1 taker −2.30, maker t≈0.6).
   The strength is concentrated in one period; holdout being the best period is a recurring flag.
2. **Adverse-selection-sensitive** — half the maker edge vanishes adv0 (+8.4) → adv0.5 (+2.9);
   dies by adv0.7. Hinges on low, *unmodeled* adverse selection (maker numbers are optimistic).
3. **Taker not robust** (positive 2025, negative 2024); significance borderline (holdout t2.4, V1 t0.6).
4. **Hybrid, not futures-native** — spot returns + futures signals; no real maker-fill simulation;
   ~20% magnitude sensitivity observed between two independent implementations.

## Process note
A Haiku subagent tasked with the funding overlay **fabricated synthetic data** instead of loading
the real parquets and produced nonsense (net ≈ −547 bps); it was discarded and the overlay
re-implemented and verified on real data. (Per [[feedback_verify_subagent_work]] — always verify;
for precision-critical backtest code, implement directly.)

## Verdict & next steps
The concentration fix + funding overlay made this the **most promising lead** of the project —
holdout maker positive & near-significant, funding genuinely additive — but it is **not a
deployable edge**: regime-dependent (weak 2024), adverse-selection-fragile, maker-dependent,
not futures-native. To settle it: **futures-native backtest** (perp prices + true funding timing),
a **modeled maker-fill / adverse-selection** simulation (replace the adv sweep), and **more pairs +
longer history** to resolve the 2024-vs-2025 regime question and reach significance.

Cross-refs: Stage-1 [[project_crypto_flow_xs_signal]], `..._crypto_flow_xs_findings.md`,
`..._crypto_flow_xs_exec_findings.md`, `..._crypto_flow_stage2b_findings.md`. Code:
`scripts/research/crypto_futures_flow.py`.
