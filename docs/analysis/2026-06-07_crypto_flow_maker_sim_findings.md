# Crypto flow — Monte-Carlo maker execution simulation
Date: 2026-06-07 17:00 UTC
## Method
- Period: **holdout 2025**
- Signal: w24 h24 k3 flow rank (59 symbols)
- Simulation: 1000 independent execution paths per rebalance
- Legs fill independently as maker with probability p_fill, else taker
- Post-fill adverse selection drawn from N(adv_mean, adv_std²) in bps

## Best scenario (highest expected net)
- p_fill=1.00, adv_mean=0.0 bps, adv_std=0.0 bps
- Expected net: **+25.55 bps** (t=+1.29, sharpe=+2.02)
- Probability of positive per rebalance: 52.7%

## Break-even observations
See JSON grid for full parameter sweep.

## Verdict
- The signal's viability is a function of fill probability and adverse selection.
- See break-even frontier above for required execution quality.
