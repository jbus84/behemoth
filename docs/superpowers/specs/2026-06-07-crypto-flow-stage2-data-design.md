# Crypto Flow — Stage 2: Finer-Data Acquisition (Scoping)

**Date:** 2026-06-07
**Status:** Scoping. The only remaining lever after coarse-kline flow was shown signal-real / net-unviable (Stage 2b).

## Premise
Coarse kline OFI (taker_buy_volume) gross is ~1-3 bps and decays OOS — below the ~4-10 bp retail cost floor. A model cannot fix data resolution. Stage 2 tests whether FINER flow data lifts gross materially.

## Candidate data sources
1. **True L2 order-book OFI** — multi-level book updates (resting bid/ask deltas), the real OFI from the matching engine. Source: Tardis.dev / Kaiko / CoinAPI (paid; limited free samples), or self-record live via exchange WebSocket for weeks. Strongest expected uplift (Deep-OFI literature: multi-level >> single-level).
2. **On-chain exchange flows** — exchange in/outflows, whale transfers, stablecoin flows. Source: Glassnode / Amberdata / Nansen (paid; free tiers limited) or own node + Dune. Slower-horizon, structural; may suit daily more than hourly.
3. **Liquidation cascades** — forced-flow that is partly anticipatable from open-interest + funding. Source: exchange liquidation streams / Coinglass. Event-driven.

## Decision gate (before committing $ or weeks)
Acquire a SAMPLE (free tier / short self-record) for a few liquid pairs, compute the SAME cross-sectional IC + cost-aware net (taker gating) as Stage 1/2. Proceed to full acquisition ONLY if sample gross materially exceeds coarse-kline gross AND projects to clear the cost floor. Reuse the existing verdict layer (DSR / temporal robustness / V1-V2 / holdout-once).

## Honest prior
Even finer flow may not clear retail cost (taker ~7.5 bps/side is the wall; maker needs measured adverse selection). L2 OFI is the best shot; on-chain/liquidations are slower/structural. Forward paper-trade before capital regardless.

## Cost/effort
L2 vendor data: ~$100s-$1000s for history, or weeks of self-recording (free but slow). On-chain: free tier limited, paid for depth. This is a real data-engineering project, not a model tweak.
