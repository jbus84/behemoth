# Crypto standalone funding-carry — findings

**Date:** 2026-06-07  
**Probe:** Standalone funding-carry book (perp-only, no flow signal)

## Method

- **Data:** Binance USD-M perp 1h klines (59 symbols, 2020–2025).
- **Funding:** real 8h funding rates, as-of joined per symbol.
- **Signal:** rolling mean of 8h funding rate (`fund_window` = 1, 8, 24, 72 bars).
- **Book:** concentrated top-k/bottom-k dollar-neutral, rebalanced every h bars.
  - Long most negative funding (receives funding when rate < 0).
  - Short most positive funding (receives funding when rate > 0).
- **Fee models:** same 5-tier maker/taker sweep as flow probes.
- **Gauntlet:** Bayesian P(edge>0), block-bootstrap CI on holdout.

## Train+val (2020–2024) — suspiciously strong, regime-dependent

Best config: `fw24 h72 k3 maker_best`

| component | bps / rebalance |
|-----------|-----------------|
| gross (price return) | +115.73 |
| cost (maker_best) | −4.80 |
| fund_pnl (carry) | +42.20 |
| **net** | **+153.10** |
| t-stat | +4.54 |
| posM | 72% |
| legs | 608 |

The numbers are enormous — 153 bps per 3-day rebalance ≈ 50 bps/day. This is not a "carry" edge; it is a **short-momentum/mean-reversion** strategy dressed in funding clothing. The signal (funding rank) selects the most speculative, over-leveraged perps (high funding) and shorts them, while buying the most neglected (low/negative funding). In choppy/bear regimes (2022 crash, 2023 chop) this prints. In persistent bull trends it bleeds.

Key evidence that this is price-driven, not carry-driven:
- Even **taker** is +133 bps on the best train+val config. If this were a pure carry edge, taker cost (~25 bps/turn) should overwhelm it.
- The `fw01` (1-bar lookback) variants are almost as strong as `fw24`, meaning the signal does not require smoothing — it is a snapshot of current speculative positioning.
- `h=8` (8-hour hold) still shows strong train+val results, but with lower absolute P&L because the price mean-reversion happens over days, not hours.

## Holdout 2025 — catastrophic reversal

| fee model | gross | cost | fund_pnl | net | t | posM |
|-----------|-------|------|----------|-----|---|------|
| taker | −39.64 | +24.33 | +32.87 | −31.10 | −0.56 | 60% |
| maker_best | −39.64 | +4.80 | +32.87 | **−11.57** | −0.21 | 60% |
| maker_good | −39.64 | +11.13 | +32.87 | −17.89 | −0.32 | 60% |
| maker_real | −39.64 | +16.25 | +32.87 | −23.01 | −0.42 | 60% |
| maker_pess | −39.64 | +20.33 | +32.87 | −27.10 | −0.49 | 60% |

**The price component reversed violently.** Gross went from +115 bps in train to −40 bps in holdout — a 155 bps swing. The funding income stayed positive (+33 bps), but could not cover the price loss.

This is exactly the risk of a perp-only "carry" book: you are **short the most speculative names during a bull run**. In Jan–May 2025, the high-funding perps (meme coins, leveraged alts) kept rallying. Shorting them was suicide.

## Gauntlet (holdout, maker_best)

| lens | result |
|------|--------|
| Monthly obs | 5 (Jan–May 2025) |
| Bayesian P(edge>0) | **0.435** (coin flip) |
| 94% CI | [−0.111, +0.086] — **crosses 0** |
| Block-bootstrap 90% CI | [+0.002, +0.002] — collapsed, meaningless with 5 months |

**Verdict: FAIL.** All rigorous lenses agree there is no detectable edge in holdout.

## Decomposition: gross vs carry vs cost

| scenario | gross | fund_pnl | net (maker_best) | interpretation |
|----------|-------|----------|------------------|----------------|
| Train+val 2020-2024 | +115.73 | +42.20 | +153.10 | Price mean-reversion + carry both positive |
| Holdout 2025 | −39.64 | +32.87 | −11.57 | Price mean-reversion **reversed**, carry insufficient |
| Hypothetical pure carry (gross=0) | 0 | +32.87 | +28.07 | If you could hedge price perfectly, carry alone is profitable |

The **pure carry component** (~+33 bps per 3 days, or ~11 bps/day) is actually attractive. The problem is the perp-only book cannot isolate it — the required price hedge (spot-perp basis) is absent.

## What this means

1. **Funding carry is real but not extractable perp-only.** The funding payments are mechanically positive for a properly-constructed rank book, but the price exposure dominates and is regime-dependent.
2. **The train+val performance is a mean-reversion mirage.** It looks like a carry edge because funding income is always positive, but the bulk of the return comes from price decay in speculative perps. That decay is not reliable.
3. **A true funding-carry edge requires a basis setup:** long spot + short perp (or vice versa) to isolate the funding differential. This needs spot data, more capital (2× notional), and exchange support for paired margin.
4. **This path is closed for now.** Without a price hedge, the standalone funding-carry book is a bet against crypto momentum — and that bet lost in 2025.

## Cross-reference

- Master synthesis: `docs/analysis/2026-06-07_crypto_flow_master_synthesis.md`
