# Crypto Cross-Sectional Order-Flow Validation (Stage 1) — Findings

**Date:** 2026-06-07
**Branch:** `worktree-crypto-flow-xs`
**Status:** Stage 1 complete. **Gross signal validated out-of-sample; net is execution-gated.**

## Headline

**The order-flow-imbalance thesis is real and survives out-of-sample at the gross level** — the
first OOS-validated predictive signal in this whole research arc. Cross-sectional order-flow
imbalance (from free Binance kline `taker_buy_volume`) significantly predicts forward returns
across crypto majors, in-sample *and* in a sealed 2025 holdout. **However, net of realistic
taker fees (7.5 bps/side) it does not clear** — break-even is ~1–2 bps/side, so capturing it
requires maker-side execution, and even then it is marginal. The open question has shifted from
*"is there signal?"* (FX answer: no) to *"can it be executed net-positive?"* (crypto: maybe,
maker-dependent) — a much better place to be.

## Setup

- **Data:** Binance free historical klines (data.binance.vision), 16 liquid USDT spot pairs,
  hourly, 2022-01 → 2025-05. ~472k bars. **Order-flow imbalance** = `(2·taker_buy_vol − vol)/vol`
  per bar (free, no L2 needed). *Note:* Binance switched kline timestamps to **microseconds in
  2025** — must unit-detect (`ts<1e14 → ms else µs`) or 2025 silently drops.
- **Splits:** train+val 2022-2024 (exploration); **holdout 2025, read once.**
- **Signals (causal):** `flow` = 6h-smoothed OFI; `flow24` = 24h-smoothed OFI; `rev3` = −(3h
  return); momentum `mom24/72`. Cross-sectionally z-scored each bar.
- **Metrics:** (a) cross-sectional IC (per-bar Spearman of signal vs forward h-return, averaged);
  (b) dollar-neutral long-top-3/short-bottom-3 net P&L after taker fee.

## Gross predictive power — cross-sectional IC

| signal | h | IC train+val (t) | IC holdout 2025 (t) | read |
|--------|---|------------------|---------------------|------|
| flow   | 6 | +0.0030 (1.8) | **+0.0263 (5.9)** | **strengthens OOS** ✓ |
| flow   | 24| +0.0090 (5.5) | +0.0141 (3.1) | persists ✓ |
| flow24 | 6 | +0.0069 (4.1) | +0.0119 (2.7) | persists ✓ |
| flow24 | 24| +0.0099 (6.0) | +0.0121 (2.6) | persists ✓ |
| rev3   | 1 | +0.0520 (26.4)| +0.0191 (3.3) | persists, decayed |
| rev3   | 6 | +0.0382 (19.7)| **−0.0211 (−3.8)** | **sign-flips OOS** ✗ unstable |
| mom24/72 | * | negative (t −7..−14) | — | hourly XS momentum *reverses* |

**Read:** order-flow imbalance is the robust, OOS-persistent signal (flow h6 t=5.9 in holdout).
Short reversal is strong in-sample but unstable OOS. Hourly cross-sectional momentum reverses.

## Net of cost — fee sweep (long/short k=3, train+val, bps per rebalance)

| signal | h | gross | net @7.5bps | net @2.5 | net @1.0 | net @0 |
|--------|---|-------|-------------|----------|----------|--------|
| rev3   | 6 | +4.93 | −18.7 (t−8.8) | −2.9 | +1.8 (t0.8) | +4.9 (t2.3) |
| flow   | 6 | +1.54 | −19.4 (t−11.9)| −5.5 | −1.3 | +1.5 (t0.9) |
| flow24 | 6 | +2.93 | −6.6 (t−4.0) | −0.2 | +1.7 (t1.0) | +2.9 (t1.8) |

- **Break-even fee ≈ 1–2 bps/side.** At retail taker (7.5 bps) everything is deeply negative.
- At maker-ish (~1 bps) the best configs are marginally positive but **not significant** (t≈1).
- **Turnover band had ~no effect** (k=3/16 reshuffles > band threshold) — same lesson as the FX
  basket band.

## Honest verdict

1. **Gross signal: VALIDATED.** Public crypto order-flow imbalance predicts cross-sectional
   returns, significantly, in-sample and out-of-sample. The user's flow thesis is correct, and
   crypto (public flow + breadth) is where it's retail-reachable — exactly as predicted.
2. **Net tradeability: NOT established at taker fees; maker-dependent and marginal.** The ~2–5
   bps gross edge per rebalance needs ≤~1–2 bps/side execution to net positive, and even then
   t≈1. **Maker fills carry unmodeled adverse-selection cost**, so the maker-fee net here is an
   optimistic upper bound.
3. **Reversal is not reliable** (OOS sign-flip); the flow signal is the durable one.

## Next stage (where the question now lives — execution, not signal)

- **Model maker-side execution + adverse selection** (the real determinant now).
- **Reduce turnover**: larger universe (per-rebalance churn becomes a smaller fraction), smoother
  signals, longer holds, proper banding.
- **Finer signal**: true L2 order-book OFI + on-chain exchange flows + liquidations (Stage 2,
  vendor/self-record data) — likely a stronger, slower-decaying signal than kline-OFI.
- **Forward paper-trade** before any capital — backtest→live gap, especially maker fills.

Per [[feedback_gross_cost_significance_decomposition]] and [[reference_retail_edge_landscape]]:
gross/cost/significance reported separately; holdout read once.
