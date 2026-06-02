# Budget=300 Tuned Search Analysis

## Search Configuration
- **budget**: 300
- **seed**: 2
- **policy**: diversity
- **c_branch**: 0.7 (reduced from 1.2)
- **p_recombine**: 0.25 (increased from 0.15)
- **branch_depth_limit**: 3

## Results

### Final Verdict (Top 5)
| Rank | Type | Branch | Val Score | Holdout P | Raw | (q, h) | n |
|------|------|--------|-----------|-----------|-----|--------|---|
| 1 | evolved | flow_intensity | -0.701 | 0.780 | -1.374 | q0.99 h100 | 2,840 |
| 2 | evolved | liquidity_gate | -0.769 | 0.905 | +0.139 | q0.9 h400 | 23,662 |
| 3 | evolved | liquidity_gate | -0.833 | 0.922 | +0.252 | q0.95 h100 | 11,265 |
| 4 | evolved | flow_intensity | -0.906 | 0.731 | -1.871 | q0.9 h400 | 15,216 |
| 5 | evolved | flow_intensity | -0.908 | 0.880 | -0.926 | q0.9 h100 | 28,317 |

### Key Observations

1. **No positive validation program found**. Best evolved score is -0.701, worse than the budget=100 result (regime_switching val=+0.006).

2. **Severe branch imbalance**. `flow_intensity` accumulated 75 nodes (24% of all nodes) vs ~20 for other branches. The diversity bonus at c_branch=0.7 is still insufficient to prevent branch capture.

3. **Score plateau for 220 expansions**. After the breakthrough at expansion 80 (best_score=-0.701), no further improvement occurred through expansion 300.

4. **liquidity_gate programs show promising holdout P values** (0.905, 0.922) but negative validation scores, suggesting they overfit the validation period.

5. **q0.99 h100 produces thin trades** (n=2,840) — below the threshold for robust Bayesian monthly inference.

## Comparison to Budget=100

| Metric | Budget=100 (seed=0) | Budget=300 (seed=2) |
|--------|---------------------|---------------------|
| Best evolved score | +0.006 (regime_switching) | -0.701 (flow_intensity) |
| Holdout P | 0.919 | 0.780 |
| Raw mean | +2.199 | -1.374 |
| (q, h) | q0.95 h400 | q0.99 h100 |
| n trades | 11,173 | 2,840 |

The budget=100 run was lucky — it found a positive program early. The budget=300 run with tuned parameters failed to replicate this.

## Diagnosis: Why the Tuned Run Failed

1. **LLM stochasticity dominates**. `qwen3-coder-next` with temperature=0.7 produces highly variable outputs. Two runs with different seeds produce qualitatively different program distributions.

2. **Branch depth limit ineffective**. The `branch_depth_limit=3` only forces jumps during *propose* operations, not *recombine*. With p_recombine=0.25, 75 of 300 expansions were recombinations that could stay in the same branch.

3. **flow_intensity template may be too narrow**. The rich template for this branch focuses on Hawkes self-excitation, which the LLM interprets as "adjust alpha and beta parameters" rather than "combine with other concepts".

## Recommendations for Next Run

### Option A: Increase cross-branch pressure
```bash
--c-branch 0.3 --p-recombine 0.4 --p-cross-branch 0.5 --branch-depth-limit 2
```

### Option B: Use a stronger LLM
Switch from `qwen3-coder-next` to `claude-opus-4-8` or `gpt-4o` for program generation. The current model may lack the reasoning depth to combine 3-4 branch concepts effectively.

### Option C: Seed the search with the budget=100 winner
Start the search with the `regime_switching` program that scored +0.006, and let the LLM refine it rather than exploring from scratch.

### Option D: Expand the grid
Try q=0.93 (between 0.90 and 0.95) and h=300 (between 200 and 400) to find the true optimal cell.

## Conclusion

The tuned budget=300 run demonstrates that **parameter tuning alone cannot overcome LLM stochasticity**. The branch-aware architecture works (prevented total collapse to one branch), but the LLM's ability to generate novel cross-branch hybrids is the bottleneck. 

The budget=100 result (regime_switching, val=+0.006) remains the **best evolved program to date**. The next step is to run a seed-from-winner search starting with this program, rather than continuing to explore from the seed library.
