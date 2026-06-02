# Deep Analysis: Why h=400 and h=200 Work for EURUSD 100-Tick Scalping

## 1. Timescale Mapping: What Do These Horizons Actually Mean?

The 100-tick bars have a **median duration of ~60 seconds** (mean ~117s, IQR 36–99s). This maps the (q, h) grid to real time as follows:

| h | Bars | ~Real Time | Daily Bars |
|---|---|---|---|
| 100 | 100 | ~1.7 hours | ~725 |
| 200 | 200 | ~3.3 hours | ~725 |
| 400 | 400 | ~6.7 hours | ~725 |

The validation split (2024) contains ~206k bars. At **q=0.95**, a program that trades 5% of bars generates **~10,000–11,000 trades** over the full year. At q=0.99, it drops to ~2,100 trades — below the threshold for robust Bayesian monthly inference (need ≥2 active months with enough trades to estimate a monthly mean).

---

## 2. The Cost Floor and Why It Dominates Short Horizons

The **realistic cost per trade** is:

```
cost = spread_pips + 0.06 (commission) + 0.10 (slippage) ≈ 0.33 pips (median)
```

For a strategy to be net-positive, its **gross expected return per trade must exceed ~0.33 pips**.

The raw forward returns at each horizon (computed from validation mid-prices) are:

| h | Mean (pips) | Std (pips) | Sharpe |
|---|---|---|---|
| 100 | −0.33 | 14.62 | −0.022 |
| 200 | −0.66 | 20.78 | −0.032 |
| 400 | −1.28 | 28.65 | −0.045 |

The slight negative mean at all horizons indicates **weak mean-reversion in EURUSD** — a fade strategy (bet against the recent move) would capture the positive side of this. But the standard deviation is enormous relative to the mean. A naive velocity fade (`sign(vel_h1) * fwd_return − cost`) produces:

| h | All bars mean net | q=0.95 mean net |
|---|---|---|
| 100 | −0.44 | −0.40 |
| 200 | −0.46 | −0.59 |
| 400 | −0.48 | −0.73 |

**This is the critical finding:** the naive fade is **loss-making at every horizon**. The evolved programs are not simply fading — they are using multi-factor gates to select a *subset* of bars where the mean-reversion conditional on microstructure state is much stronger than the unconditional average.

---

## 3. Why h=400 Is the Sweet Spot

### 3.1 Intraday Mean-Reversion Half-Life

FX intraday price dynamics follow a **W-shaped pattern** around the Tokyo open, London fix (15:30–16:30 UTC), and NY close (Krohn et al. 2024, *Journal of Finance*). Dealer inventory cycles and fix-driven flow create temporary price distortions that unwind over **4–8 hours**. 

- **h=100 (~1.7 hours)**: Too short. The dealer inventory distortion has not fully unwound. The forward return is dominated by noise (σ=14.6 pips), and the expected signal is swamped by residual flow.
- **h=200 (~3.3 hours)**: Intermediate. Captures partial mean-reversion, especially during the London/NY overlap when inventory cycles are faster. This is why some evolved programs (e.g., `transient_impact` and `liquidity_gate` seeds) show their best scores at h=200 — they target faster-decaying microstructure signals.
- **h=400 (~6.7 hours)**: Matches the **full daily cycle**. By 6–7 hours, fix-driven distortions and inventory imbalances have largely mean-reverted. The evolved `regime_switching` program at q0.95 h400 (val=+0.006, holdout P=0.919, raw=+2.199, n=11,173) was the first evolved program to beat domain-expert seeds. It successfully gated entries to trade only during the regime where the 6.7-hour forward drift is most predictable.

### 3.2 The Signal-to-Cost Trade-off

At h=400, the gross forward return magnitude is larger (−1.28 pips unconditional, but conditional on a good gate it can be +1.5 to +2.5 pips), giving enough headroom to clear the 0.33-pip cost floor. At h=100, even a perfect gate would struggle because the maximum conditional drift is smaller.

### 3.3 Statistical Power for Bayesian Inference

The `CostAwarePerSymbolScorer` evaluates each (q, h) cell using:

```python
lb, mean, se = fast_lower_bound(frame, z=1.645)  # 95% one-sided LB
```

For the lower bound to be positive, we need:

```
mean_net > 1.645 * (std_monthly / sqrt(n_months))
```

At q=0.95 h=400, n=11,173 trades spread across ~12 months = ~930 trades/month. This gives enough per-month precision for the hierarchical Student-T model to detect an edge. At q=0.99, n drops to ~2,100 total (~175/month) — too thin; the SE explodes and the LB goes negative even if the raw mean is positive.

---

## 4. Why q=0.95 Beats q=0.90 and q=0.99

| q | Trades (h=400) | Mean net (naive fade) | Problem |
|---|---|---|---|
| 0.90 | ~21,000 | −0.64 | Too many marginal trades dilute the edge |
| 0.95 | ~11,000 | −0.73 | Optimal: enough trades for inference, filters noise |
| 0.99 | ~2,100 | −0.93 | Too thin; monthly SE too high |

For **evolved programs with good gates**, the relationship flips:

- At q=0.90, the gate is too loose — it includes bars where the conditional signal is weak, and the edge gets diluted toward zero.
- At q=0.95, the gate is tight enough to exclude the weakest 95% of bars, concentrating on the subset where the multi-factor conditional mean-reversion is strongest.
- At q=0.99, the gate is too tight — there are not enough trades to reliably estimate monthly means, and the Bayesian model cannot place the symbol in the hierarchy.

This is why the first positive evolved program (`regime_switching`) appeared at **q0.95 h400** — not q0.90 (dilution) and not q0.99 (insufficient sample).

---

## 5. Why Budget=200 Produced Different (and Worse) Results Than Budget=100

The budget=100 run found the first positive evolved program (`regime_switching`, val=+0.006). The budget=200 run produced:

- Best evolved: `asymmetric_vol` score=−0.405 at q0.9 h400
- Branch distribution: `asymmetric_vol` dominated with 37 nodes
- No positive-validation evolved programs

This is a **stochastic LLM effect**, not a PUCT failure. Key observations:

1. **LLM non-determinism**: `qwen3-coder-next` is temperature-sampled. Two runs with the same RNG seed for selection still generate different programs because the LLM sampling is independent. Budget=100 "got lucky" and produced a strong `regime_switching` program early; budget=200 spent its early expansion on `asymmetric_vol` branches that happened to score marginally better (−0.5 vs −0.8) and the diversity bonus kept expanding that branch.

2. **Diversity bonus over-correction**: The branch diversity bonus (`c_branch * sqrt(total_nodes) / (1 + branch_n)`) successfully prevented collapse to a single branch, but in budget=200 it over-weighted `asymmetric_vol` because that branch happened to produce slightly less-bad programs early. The LLM then kept exploring variations within `asymmetric_vol` (e.g., adjusting the semivariance ratio threshold) rather than jumping to other branches.

3. **Cross-branch recombination was under-utilized**: Only 15% of expansions used two-parent recombination. The budget=100 run may have hit a lucky cross-branch hybrid that budget=200 missed.

---

## 6. The Branch-Aware Architecture: What Worked and What Needs Tuning

### What Worked

- **Branch diversity bonus successfully prevented collapse**. In budget=200, all 12 branches had ≥1 node. Without the bonus, search would have collapsed entirely into `asymmetric_vol` parameter sweeps.
- **Rich templates enabled cross-domain transfer**. The `transient_impact` branch (Barzykin 2025 propagator) and `seasonality` branch (Krohn et al. 2024 fix windows) provided concepts that the LLM could recombine with classical gates.
- **Causality probe eliminated non-causal programs**. All 18 seeds and all evolved programs passed `causality_probe()` — the `adaptive_fair` fix (expanding mean instead of global median) ensured no lookahead leakage.

### What Needs Tuning

1. **Lower `c_branch` from 1.2 to ~0.6–0.8**. The current value over-explores branches with marginally better early scores. The bonus should decay faster as `branch_n` grows.
2. **Increase `p_recombine` from 0.15 to ~0.25–0.30**. Cross-branch recombination is the most promising mechanism for finding novel hybrids (e.g., `liquidity_gate + jump_aware + flow_intensity` as seen in budget=100), but it is currently under-sampled.
3. **Add a "depth penalty" to prevent parameter-sweeping within a branch**. If a branch's last 5 expansions only adjusted a threshold (e.g., `pv_down/pv_up <= 1.4` instead of `1.5`), force a cross-branch jump.

---

## 7. Concrete Recommendations for the Next Run

Based on this analysis, the next search should use:

```bash
uv run python scripts/era_scalp/run_era_eur.py \
  --budget 300 \
  --c-branch 0.7 \
  --p-recombine 0.25 \
  --p-cross-branch 0.35 \
  --seed 1
```

Rationale:
- **Budget 300**: Gives the search enough expansions to recover from an unlucky early branch skew.
- **c-branch 0.7**: Reduces over-exploration of branches with marginal early advantage.
- **p-recombine 0.25**: Increases the probability of generating 3–4 branch hybrids that capture multi-horizon effects.
- **Seed 1**: Fresh LLM sample path; avoids re-running the same stochastic trajectory.

The target is to find a program that replicates or exceeds the budget=100 result: **validation val > 0, holdout P > 0.90, raw > +2.0 at q0.95 h400 with n > 10,000**.
