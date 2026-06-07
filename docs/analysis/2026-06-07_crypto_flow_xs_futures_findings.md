# Crypto cross-sectional flow — Stage-2b futures-native + maker-fill
Date: 2026-06-07 15:46 UTC
## Method
- Data: Binance USD-M perp 1h klines (4 symbols).
- Funding: real 8h funding rates, as-of joined per symbol.
- Signal: causal 6-bar rolling OFI (`flow6`).
- Book: concentrated top-k / bottom-k dollar-neutral, rebalanced every h bars.
- Maker model: parametric fill probability (queue position) + post-fill adverse selection.

## Best config (train+val)
- `w24 h24 k1 maker_best`

## Holdout 2025

## Caveats
- Holdout is a single 5-month window; t≈0.8–2.4 depending on maker assumption.
- Maker edge is highly sensitive to queue position / adverse selection.
- No real order-book or queue simulation; effective cost is parametric.
- Regime-dependent (strong 2025, weaker 2024).
