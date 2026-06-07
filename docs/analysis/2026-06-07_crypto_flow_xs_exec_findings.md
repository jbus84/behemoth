# Crypto Order-Flow — Stage 2a: Execution Viability — Findings

**Date:** 2026-06-07
**Branch:** `worktree-crypto-flow-xs` (follow-on to the Stage-1 validation)
**Status:** Complete. **Turnover reduction + breadth do NOT make the gross signal net-positive.**

## Question

Stage 1 ([[project_crypto_flow_xs_signal]]) validated the gross OFI signal OOS but it failed
net of taker fees (turnover×fee). Stage 2a tests whether **more breadth + lower turnover**
rescues it: 32 USDT pairs, sweep over smoothing `w∈{6,24}`, horizon `h∈{6,12,24,48}`, book
width `k∈{3,5,8}`, and a lower-churn **proportional** (rank-z) weighting vs top-k.

## Method
Same data pipeline (free Binance klines → OFI), 32 pairs hourly 2022-2025, dollar-neutral
cross-sectional long/short. Select on 2022-2024 (taker fee = gating); **holdout 2025 read once**.
Cost = turnover × fee/side. Maker scenarios add an explicit adverse-selection haircut
(net = gross·(1−adv) − cost). Implemented by a Haiku subagent; **independently verified** (numbers
reproduced exactly with clean `.transform` code; fixed a cosmetic gross-label bug in the
subagent's metrics and its fragile `groupby().apply` → `.transform`).

## Results — all 32 configs net-negative at taker fees (train+val 2022-2024)
| config (best few) | gross bps | cost bps | net bps | t | posM |
|---|---|---|---|---|---|
| w24 h6 proportional | +0.68 | 3.97 | **−3.29** | −6.2 | 17% |
| w24 h12 proportional | +1.61 | 5.84 | −4.23 | −3.8 | 36% |
| w6 h24 proportional | +3.77 | 9.78 | −6.01 | −2.9 | 31% |
| w6 h24 topk k3 | +15.68 | 24.90 | −9.23 | −1.2 | 42% |

- Higher-gross configs (e.g. w6 h24 topk k3, gross +15.7 bps) carry *higher* turnover/cost
  (24.9 bps) → still deeply negative. Proportional weighting minimises cost (~4 bps) but also
  gross; **nothing clears the ~bps gross vs ~4–25 bps taker cost gap.**

## Holdout 2025 (best config w24 h6 proportional, read once)
| scenario | gross | cost | net | t | posM |
|---|---|---|---|---|---|
| **taker 7.5 bps (gating)** | +1.10 | 4.19 | **−3.09** | −2.13 | 20% | → **fails** |
| maker 1 bps, adv=0 (optimistic) | +1.10 | 0.56 | +0.54 | +0.37 | 40% | insignificant |
| maker 1 bps, adv=0.5 (realistic) | +1.10 | 0.56 | −0.01 | −0.01 | 40% | breakeven |

## Verdict
- **Gross signal confirmed real but small** (+1.1 bps OOS, consistent with Stage-1 IC) — and
  **too small to clear realistic cost** even with 32-pair breadth + low-turnover proportional
  weighting.
- **Taker: fails decisively** (net −3.1 bps, t=−2.1).
- **Maker only marginally positive at *zero* adverse selection** (net +0.54, **t=0.37** — not
  significant, 40% pos-months); **realistic adverse selection (50%) → breakeven.**
- So execution-via-turnover-reduction is **not** the unlock. The bottleneck is **signal
  strength**: ~1 bp gross is below the cost floor.

## What this leaves (narrowed next steps)
1. **Stronger signal (Stage 2):** true L2 order-book OFI + on-chain exchange in/outflows +
   liquidation-cascade features (vendor or self-recorded data) — likely larger, slower-decaying
   than coarse kline-OFI. This is the only path that could lift gross above the cost floor.
2. **Measured (not assumed) maker execution + adverse selection** — requires live/recorded
   limit-order fill data; the maker numbers here are an optimistic upper bound.
3. Forward paper-trade before any capital.

Per [[feedback_gross_cost_significance_decomposition]] and [[feedback_verify_subagent_work]]:
gross/cost/significance reported separately; holdout once; subagent output independently verified.
