# Crypto Order-Flow — Stage 2b: PUCT-Boosting Repointed (Coarse-Data Line CLOSED)

**Date:** 2026-06-07
**Branch:** `worktree-era-puct-boosting` (PR #330)
**Status:** Complete. Stronger model lifts gross but **no robust net edge** on coarse kline data. Coarse-data line closed; next lever is finer data (Stage 2).

## What was tested
Repointed the PUCT-boosting engine (CatBoost on PUCT-evolved features) at crypto cross-sectional flow, 32 USDT pairs, hourly, train 2022-23 / val 2024 / holdout 2025. Goal: does a stronger model (vs raw OFI) clear the cost floor that Stage-2a hit?

## Cheap gate — does CatBoost beat raw OFI? (validation 2024 cross-sectional IC, h=6)
| feature set | val IC | t |
|---|---|---|
| raw OFI (ma6) | +0.0025 | 1.2 |
| **CatBoost flow-only (6 feats)** | **+0.0076** | **3.5** |
| CatBoost + research factors (11) | +0.0008 | 0.3 |

CatBoost **does** add real cross-sectional signal (~3x raw OFI, significant). BUT the documented monthly/daily crypto factors (Amihud illiquidity, realized/downside vol, skewness, dollar-volume, vol-shock; Cakici 2024, CTREND) **degrade** the hourly model (0.0076 -> 0.0008) — they are slow, near-constant-per-symbol characteristics that overfit at hourly horizon. Kept in taxonomy, NOT seeded.

## Decisive check — does the flow-CatBoost NET clear cost? (full cost-aware portfolio, bps/rebalance)
| split | gross | taker net | maker(adv0) net | maker(adv.5) net |
|---|---|---|---|---|
| V1 2024a | +3.33 | -6.74 (t-2.8) | +1.99 (t0.83, 67% posM) | +0.32 |
| V2 2024b | +2.17 | -8.00 (t-2.7) | +0.81 (t0.27, 42%) | -0.27 |
| **HOLDOUT 2025** | **+0.74** | **-8.99 (t-2.2, 0% posM)** | **-0.56 (t-0.14)** | **-0.93** |

## Verdict
- Gross is real and stronger than raw OFI in-sample (+2-3 bps) but **decays out-of-sample** (holdout +0.74).
- **Taker: dead everywhere** (net -7 to -9 bps; conviction-gated turnover cost ~10 bps >> gross).
- **Maker(adv0): positive in 2024 (V1/V2) but NEGATIVE on 2025 holdout** -> not robust across regimes.
- **Maker(adv.5, realistic): breakeven-to-negative throughout.**

A stronger model cannot convert a ~1-3 bp decaying gross signal into a robust net edge against retail cost. The binding constraint is **signal strength / data resolution**, not model power or execution tuning — confirmed three independent ways (Stage-2a turnover sweep, this flow-CatBoost net, maker non-robustness). The 2-3 hr full PUCT search was **gated out** by these cheap checks (it would only tweak feature composition marginally).

## Engine improvement shipped
Fixed a look-ahead in `crypto_boost_spec.score_frame`: the conviction threshold is now computed CAUSALLY per bar (current cross-section only), not over the full split.

## Conclusion
**The coarse-kline crypto-flow line is closed: signal real, net not viable at retail cost.** Only remaining lever = finer data (Stage 2). See `docs/superpowers/specs/2026-06-07-crypto-flow-stage2-data-design.md`. Cross-refs: Stage-1 (`docs/analysis/2026-06-07_crypto_flow_xs_findings.md`), Stage-2a (`..._crypto_flow_xs_exec_findings.md`).
