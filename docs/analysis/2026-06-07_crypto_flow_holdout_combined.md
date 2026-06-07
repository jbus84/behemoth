# Combined overlay holdout test (2025)

- Train guard + momentum-stop grid on 2020-2024
- Best train: guard=(-0.1, -0.2, 0.25)  mom_stop=(5, -0.03, 0.5)

| variant | Sharpe | maxDD | final | pos/neg days |
|---------|--------|-------|-------|-------------|
| baseline (2025) | +1.37 | -9.6% | 1.19x | 43/32 |
| trained combined (2025) | +0.90 | -9.6% | 1.11x | 43/32 |
| naive combined (2025) | +0.59 | -12.2% | 1.06x | 43/32 |
