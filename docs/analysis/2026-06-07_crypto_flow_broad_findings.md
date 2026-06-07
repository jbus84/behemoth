# Crypto cross-sectional flow — Stage-3 broadened universe + gauntlet
Date: 2026-06-07 16:25 UTC
## Method
- Data: Binance USD-M perp 1h klines (59 symbols, 2020–2025).
- Funding: real 8h funding rates, as-of joined per symbol.
- Signal: causal 24-bar rolling OFI.
- Book: concentrated top-3/bottom-3 dollar-neutral, rebalanced every 24 bars.
- Gauntlet: Bayesian P(edge>0), temporal-robustness, block-bootstrap CI, DSR.

## Best config (train+val 2020-2024)
- `w24 h24 k3 maker_best`

## Holdout 2025
- **taker**: net=-4.02 bps  t=-0.20  posM=40%  legs=150
- **maker_best**: net=+19.71 bps  t=+1.00  posM=100%  legs=150
- **maker_good**: net=+12.03 bps  t=+0.61  posM=60%  legs=150
- **maker_real**: net=+5.81 bps  t=+0.29  posM=40%  legs=150
- **maker_pess**: net=+0.84 bps  t=+0.04  posM=40%  legs=150

## Verdict
- More breadth + history applied. See gauntlet results above.
