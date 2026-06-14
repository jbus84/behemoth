# Crypto Cross-Sectional Order-Flow Validation (Stage 1) — Design

**Date:** 2026-06-07
**Branch:** `worktree-crypto-flow-xs`
**Status:** Approved ("do it"); building.

## Thesis being tested

Intraday price moves are driven by **order flow** (Evans–Lyons). In FX that flow is private
(dealer moat); in **crypto it is public**. Binance free historical klines expose
`taker_buy_volume`, giving a free **order-flow-imbalance** signal: `ofi = (2·taker_buy − vol)/vol`.
Crypto also has the **breadth** FX lacked (many liquid tokens) and **vol ≫ cost**. So the
strongest retail-reachable version of the flow thesis is a **dollar-neutral cross-sectional
book** ranking tokens by flow + momentum, tested honestly net of realistic fees.

This is the highest-EV experiment remaining (see [[reference_retail_edge_landscape]],
[[project_retail_fx_edge_cost_wall]]). Stage 1 uses the *coarse* (kline-derived) flow signal;
full L2 OFI / on-chain is a later, data-acquisition-gated stage.

## Scope (locked)

- **Universe:** ~16 liquid USDT spot pairs that existed by 2022-01.
- **Bars:** 1h. **History:** 2022-01 → 2025 (bear + recovery + bull = regime diversity).
- **Splits:** train/val for exploration; **holdout = most recent ~20%, read once.**
- **Signals (per symbol, causal):** flow imbalance (raw + smoothed), multi-horizon momentum
  (e.g. 6h/24h), short reversal (1–3h). Cross-sectional z-scored each bar.
- **Construction:** rank each rebalance bar; long top-k / short bottom-k, dollar-neutral
  (`Σw=0`); hold h hours; turnover-aware cost.
- **Cost:** realistic **taker ~7.5 bps/side** (gating verdict); maker reported for context.
- **Verdict:** gross vs cost vs significance decomposed separately; t-stat + positive-period
  fraction; OOS holdout once. (Reuse the engine's discipline; a focused probe is fine for
  Stage 1 rather than a full RunSpec.)

## Honest gate / what a pass means

A pass = **cost-surviving net edge out-of-sample, with the right sign across periods and a
t-stat that isn't coin-flip** — i.e. "worth paper-trading," NOT proven live. The kline OFI is
coarser than true L2 OFI, and live fills/latency differ. Per
[[feedback_gross_cost_significance_decomposition]]: never trust a net mean; report gross,
cost, net, t, and positive-month %.

## Out of scope (Stage 2+)

Full L2 order-book OFI, on-chain exchange flows, liquidations (vendor/self-record data);
live/paper forward testing; maker-side execution modelling.
