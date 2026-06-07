# Drawdown guard — holdout test (2025)

- Train grid-search on 2020-2024 for h48_k5
- Best train guard: soft=-10%  hard=-20%  scale=0.25

| variant | Sharpe | maxDD | final | pos/neg days |
|---------|--------|-------|-------|-------------|
| baseline (2025) | +2.83 | -9.4% | 1.31x | 47/28 |
| trained guard (2025) | +2.83 | -9.4% | 1.31x | 47/28 |
| naive -15/-25 guard (2025) | +2.83 | -9.4% | 1.31x | 47/28 |
