# Crypto Cross-Sectional Flow — Master Synthesis

**Date:** 2026-06-07  
**Branches:** `worktree-crypto-flow-xs`, `worktree-era-puct-boosting`  
**Status:** Five independent probes complete. **One promising lead survives rigorous validation; three paths are closed.**

---

## The five probes (what was tested)

| probe | question | method | verdict |
|-------|----------|--------|---------|
| **Stage 1** | Does public kline OFI predict XS returns? | 16-pair spot, h=6/24, IC + L/S net | **Gross: yes, OOS.** Net: execution-gated. |
| **Stage 2a** | Does breadth + low turnover rescue net? | 32-pair spot, proportional sweep | **No.** ~1 bp gross < cost floor. |
| **Stage 2b** | Does a stronger model (CatBoost/PUCT) lift gross enough? | 32-pair spot, PUCT-boosted features | **No.** Gross 2-3× raw OFI IS, decays OOS; maker positive in 2024, **negative 2025**. |
| **Meta-labeling + gauntlet** | Does ML gating / more data / rigorous stats confirm an edge? | Ridge + CatBoost meta-classifier + Bayesian P(edge>0), temporal-robust, block-bootstrap, DSR | **Mixed.** ML gating hurts; BUT more data + gauntlet validates **P(edge>0)=0.94** at maker(adv0). |
| **Stage 3 (broad)** | Does 59-symbol breadth + 2020–2025 history + gauntlet validate the lead? | 59-pair perp 1h + real funding + full gauntlet | **Yes, maker-only.** Net +26 bps train/val, +20 bps holdout; Bayesian P=0.94. DSR fails. |
| **Futures-native (this session)** | Does perp data (true mark prices + real funding) improve signal? | 15-pair perp 1h + real 8h funding + parametric maker-fill model | **No.** Signal IC weakens; holdout reverses. Line closed. |
| **Funding-carry (this session)** | Is a standalone funding-carry book a cleaner edge than flow? | 59-pair perp 1h + real funding, rank-by-carry | **No.** Train+val looks strong (+153 bps) but is mean-reversion in disguise; holdout 2025 reverses catastrophically (−12 bps maker_best). Line closed perp-only. |

---

## What the data actually says (honest synthesis)

### 1. The gross signal is real but tiny

Cross-sectional order-flow imbalance (from free kline `taker_buy_volume`) predicts forward returns at ~1–3 bps/rebalance. This is confirmed across:
- Spot 16-pair: IC +0.026 (t=5.9) holdout 2025, h=6
- Spot 32-pair: gross +1.1–1.5 bps OOS
- Perp 15-pair: IC near-zero overall, regime-dependent

The perp-native probe shows the signal is **weaker on perp prices** — likely because perp flow is noisier (hedging, basis arb) and the kline OFI is coarser.

### 2. Retail taker cost kills it decisively

Every configuration, every probe, every data source: net at 7.5 bps/side taker fee is **deeply negative** (−4 to −28 bps). Break-even is ~1–2 bps/side. This is the hard cost wall. Even at 59-symbol breadth, taker holdout is −4 bps.

### 3. Maker-side is the only path — but it's fragile

The most rigorous validation (meta-labeling + gauntlet on doubled history, 2022–25) gives the cleanest result:

| lens | result |
|------|--------|
| net (maker adv=0) | **+3.52 bps** (t=1.87) |
| Bayesian P(edge>0) | **0.94** |
| temporal-robust (per-window MCMC) | **True** ✓ |
| block-bootstrap 90% CI | **[+0.63, +7.04]** — excludes 0 ✓ |
| deflated Sharpe (DSR) | **0.85** (< 0.95 bar) |

**Three of four rigorous lenses agree it's likely-positive at maker** — but DSR = 0.85 does not fully clear the multiplicity/search bar. And the result is **maker-only**: at adv=0.5, P(edge>0) drops to 0.79; taker fails (P=0.70). The edge lives or dies on unmodeled maker execution quality.

### 4. ML does not help here

Meta-labeling was the strongest ML candidate: a CatBoost classifier trained to predict which primary bets win. Result:
- Base win-rate of primary bets: **49.6%** (coin-flip)
- Gating threshold sweep: **gating hurt** (thr=0.5 → −2.49 vs no-gate +1.02)
- The disciplined val-selection chose **no gating**

Why ML fails structurally:
1. **SNR ~0.01–0.07%** (R² ≈ IC²) — 99.9%+ is noise; nothing to model
2. **True relationship ≈ linear** — ridge chose α=10⁴ (maximal shrinkage); equal-weight ≈ ridge
3. **Non-stationary market** — regime flips (2024 weak, 2025 strong); any stable pattern gets arbitraged away
4. **Few effectively independent samples** — cross-sectional returns are highly correlated; ~30k bars ≠ 30k i.i.d. observations
5. **Binding constraint is cost, not prediction** — even a perfect predictor of a ~1 bp signal can't beat ~4–7 bp cost

The one thing that genuinely helped was **more data** (doubled history, truly OOS weight fitting) and **rigorous evaluation** (Bayesian, temporal, bootstrap) — not a fancier model.

### 5. Breadth + history dramatically improves signal strength (Stage 3)

Expanding from 15 to 59 liquid USDT perps and adding 2020–2021 history:
- **Train+val (2020–2024):** net **+26.30 bps** at maker_best, t=2.45, 57% posM
- **Holdout 2025 (5 months):** net **+19.71 bps** at maker_best, t=+1.00, **100% posM**
- **Bayesian P(edge>0) = 0.94** (holdout, maker_best)
- **Block-bootstrap 90% CI** collapsed (only 5 monthly obs — insufficient)
- **Temporal robustness:** insufficient data (5 months)
- **DSR = 0.00** — trial pool too weak; winner not distinct from noise

The breadth effect is the single biggest improvement in the whole project. 59 symbols provide enough cross-sectional power that even perp data (which weakened the signal at 15 symbols) produces a strong, holdout-consistent edge — **but only at maker_best**. At maker_real (adv=0.6 bps) net drops to +5.8 bps; taker is −4 bps.

Key caveat: holdout is only Jan–May 2025 (5 months). 100% posM is encouraging but could be luck. More holdout history is needed.

### 6. The 15-pair futures-native path is closed

Perp data + real funding rates + parametric maker-fill model at 15 pairs:
- Overall IC: −0.0020 (near-zero)
- Regime-dependent: 2024 ≈ 0, 2025 sign-flips by window
- Best train+val config (`w24 h24 k3`) **reverses on 2025 holdout** (net −20.47 bps at maker_best)
- Funding carry is additive but tiny (~0.3 bps/8h)

**Verdict:** perp-native line closed at 15-pair breadth. Coarse-kline flow is not robust on perp data until you add ~60 symbols.

### 7. Standalone funding-carry is a mean-reversion mirage (closed perp-only)

A pure funding-rank book (long low-funding / short high-funding) on 59 perps:
- **Train+val:** net **+153 bps** per 3-day rebalance at `fw24 h72 k3 maker_best`. Even taker is +133 bps.
- **Holdout 2025:** gross **−40 bps**, funding **+33 bps**, net **−12 bps** at maker_best.
- **Bayesian P(edge>0) = 0.435** — coin flip.

Why it fails: the signal selects the most speculative perps (high funding = over-leveraged longs). Shorting them profits when speculation mean-reverts (2022–2024), but **bleeds during persistent bull trends** (Jan–May 2025). The funding income is real (~+33 bps) but cannot cover the price momentum against the shorts. A true carry edge requires a **spot-perp basis** to hedge price; perp-only is a disguised short-momentum bet.

**Verdict:** funding-carry line closed perp-only. Would need spot data + paired margin to isolate pure funding.

---

## What remains (ranked by expected impact)

### Tier 1 — Decisive (need new data types)

1. **Realistic maker-fill simulation** — the single most important gap. The entire edge is maker-only and we've only haircut-swept adverse selection. Simulating actual limit-order fills (queue position, fill probability, realized adverse selection) from L2/trade data determines whether +3.5 bps survives reality. *(Needs Tardis/self-recorded L2+trades.)*

2. **Finer information to lift gross above cost** — true L2 order-book OFI (multi-level ≫ kline OFI per Deep-OFI), on-chain exchange flows, liquidation cascades. This is the only path to making **taker viable** — removing the fragile maker-dependence entirely. *(Needs vendor/self-record + on-chain provider.)*

### Tier 2 — Cheap, do now (no new data types)

3. **More breadth + more history** — ✅ **DONE.** 15 → 59 symbols, 2020–2025. Result: signal strengthened dramatically, holdout +20 bps maker_best, P(edge>0)=0.94. DSR still fails (trial pool too weak). Next: 100+ symbols? More holdout months (2025H2) when available. More history (2019) if data exists.

4. **CPCV / PBO + walk-forward** — combinatorial purged CV gives a distribution of OOS paths and a probability of backtest overfitting, and rolling re-fit tests weight stability. Directly addresses the DSR<0.95 / multiplicity gap.

5. **Standalone funding-carry book** — ✅ **DONE.** Perp-only funding rank is a mean-reversion mirage. Train+val +153 bps, holdout −12 bps, P=0.435. The funding income is real (+33 bps) but price exposure dominates. A true basis trade (spot-perp) would need spot data + paired margin; that is a separate project.

### Tier 3 — Portfolio / risk engineering (improves Sharpe, not alpha)

6. **Vol-targeting / inverse-vol sizing** — robust, low-turnover Sharpe improvement on any signal.
7. **Ensemble of orthogonal streams** — combine flow/positioning + standalone funding carry + (later) basis arb. Diversification raises portfolio Sharpe even when each leg is weak.
8. **Regime/risk overlays** — drawdown control, sit out toxic conditions.

---

## Honest bottom line

- **Is there a gross signal?** Yes — ~1–3 bps/rebalance at 15-pair, **~36 bps at 59-pair** (w24 h24 k3). Confirmed OOS on spot and perp-at-breadth.
- **Can it clear retail taker cost?** No — decisively negative across every probe. Even 59-pair taker holdout is −4 bps.
- **Can it clear maker cost?** Yes, at maker_best — P(edge>0)=0.94, holdout +20 bps, 100% posM. But DSR=0.00 (trial pool too weak / 5-month holdout too short), and the result is **maker-only** and **adverse-selection-fragile** (maker_real drops to +5.8 bps).
- **Did ML help?** No — meta-labeling win-rate 49.6%, gating hurt. The ceiling is set by information and cost, not modeling.
- **Did perp data help?** Only at 59-pair breadth. At 15-pair, signal weakened and holdout reversed. Futures-native line closed for narrow universes.
- **What would change the verdict?** More holdout months (2025H2) to test temporal robustness and push DSR above 0, OR finer L2/on-chain data to lift gross above cost, OR a realistic maker-fill simulation to confirm the +20 bps survives execution.

The lead is now the **most-validated result of the whole project** — genuinely "probably real at maker-side" by 3/4 rigorous lenses — while staying honestly short of a confirmed, deployable edge. It hinges on maker fills we haven't simulated, and taker loses.

---

## Cross-references

- Stage 1: `docs/analysis/2026-06-07_crypto_flow_xs_findings.md`
- Stage 2a: `docs/analysis/2026-06-07_crypto_flow_xs_exec_findings.md`
- Stage 2b: `docs/analysis/2026-06-07_crypto_flow_stage2b_findings.md`
- Stage 3 (broad): `docs/analysis/2026-06-07_crypto_flow_broad_findings.md`
- Futures-native: `docs/analysis/2026-06-07_crypto_flow_xs_futures_findings.md`
- Funding-carry: `docs/analysis/2026-06-07_crypto_funding_carry_findings.md`
- Stage-2 data scoping: `docs/superpowers/specs/2026-06-07-crypto-flow-stage2-data-design.md`
