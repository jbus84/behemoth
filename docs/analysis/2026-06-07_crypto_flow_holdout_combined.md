# Combined overlay holdout test (2025)

- Train guard + momentum-stop grid on 2020-2024
- Best train: guard=(-0.08, -0.15, 0.25)  mom_stop=(3, -0.02, 0.5)

| variant | Sharpe | maxDD | final | pos/neg days |
|---------|--------|-------|-------|-------------|
| baseline (2025) | +2.83 | -9.4% | 1.31x | 47/28 |
| trained combined (2025) | +5.27 | -6.1% | 1.54x | 47/28 |
| naive combined (2025) | +4.57 | -6.1% | 1.44x | 47/28 |
