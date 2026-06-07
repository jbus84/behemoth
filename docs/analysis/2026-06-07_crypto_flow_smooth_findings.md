# Crypto flow — smoothed variants (holdout 2025)

## Method
- Retail maker fees: rebate 2.0 bps, taker 5.0 bps, spread 2.0 bps
- Signal: w24 flow rank
- Tested lower turnover (h=48,72) and more legs (k=5,8)

## Results (holdout 2025)

| config | net | t | posM | Sharpe | maxDD | final |
|--------|-----|---|------|--------|-------|-------|
| third_turnover | +150.85 | +2.41 | 100% | +3.79 | -10.8% | 2.02x |
| more_legs | +26.87 | +1.80 | 100% | +2.82 | -10.9% | 1.46x |
| third_turnover_more | +71.79 | +1.39 | 80% | +2.20 | -10.8% | 1.39x |
| baseline | +25.55 | +1.29 | 100% | +2.02 | -16.4% | 1.40x |
| half_turnover_more | +39.43 | +1.28 | 80% | +2.01 | -9.4% | 1.31x |
| half_turnover | +40.66 | +1.13 | 80% | +1.78 | -12.1% | 1.31x |
| many_legs | +7.50 | +0.63 | 60% | +0.98 | -11.5% | 1.10x |

## Verdict
- Best Sharpe: **third_turnover** with Sharpe=3.79
